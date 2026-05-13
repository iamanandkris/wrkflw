#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


STORY_HEADER = re.compile(r"^##\s+Story\s+(\d+)\s*:?\s*(.*)$", re.IGNORECASE)
STORY_REF = re.compile(r"\bstory[-\s]+(\d+)\b", re.IGNORECASE)
INPUT_FILES = [
    "stories.md",
    "dependencies.md",
    "issue-advisor.json",
    "feedback-synthesis.json",
    "review-log.md",
    "role-reviews.md",
    "conflicts.md",
    "records/debt.jsonl",
    "records/memory.jsonl",
]


@dataclass
class StoryBlock:
    number: int
    title: str
    body: str
    depends_on: list[int]
    covers: list[str]

    @property
    def name(self) -> str:
        return f"Story {self.number}"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def timestamp_id() -> str:
    return re.sub(r"[^0-9]", "", utc_now())[:14]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_text_if_changed(path: Path, content: str) -> None:
    if path.exists() and read_text(path) == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def workflow_path(root: Path, slug: str, relative: str) -> Path:
    return root / ".workflow" / slug / relative


def replan_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "replan.json")


def replan_summary_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "replan.md")


def replan_records_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "records/replans.jsonl")


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        values[key.strip()] = value.strip()
    return values


def active_story(root: Path, slug: str) -> str:
    state = parse_kv_list(workflow_path(root, slug, "state.md"))
    return state.get("Active items", "").split(",", 1)[0].strip()


def story_number(value: str) -> int | None:
    match = re.search(r"\bstory\s+(\d+)\b", value or "", flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_story_refs(raw: str) -> list[int]:
    return [int(match.group(1)) for match in STORY_REF.finditer(raw)]


def parse_comma_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip() and item.strip() != "-"]


def parse_directives(raw: str | None) -> dict[str, str]:
    directives: dict[str, str] = {}
    if not raw or not raw.strip():
        return directives
    for segment in [item.strip() for item in re.split(r"[;\n]+", raw) if item.strip()]:
        if ":" in segment:
            key, value = segment.split(":", 1)
        elif "=" in segment:
            key, value = segment.split("=", 1)
        else:
            continue
        directives[key.strip().lower()] = value.strip()
    return directives


def story_names_from_text(raw: str) -> list[str]:
    names: list[str] = []
    for match in STORY_REF.finditer(raw or ""):
        name = f"Story {int(match.group(1))}"
        if name not in names:
            names.append(name)
    return names


def split_mutation_entries(raw: str) -> list[str]:
    return [item.strip() for item in re.split(r"\s*\|\s*", raw or "") if item.strip()]


def dependency_mutations(raw: str) -> list[dict[str, object]]:
    changes: list[dict[str, object]] = []
    for entry in split_mutation_entries(raw):
        lhs = ""
        rhs = ""
        if "->" in entry:
            lhs, rhs = entry.split("->", 1)
        elif re.search(r"\bdepends\s+on\b", entry, flags=re.IGNORECASE):
            lhs, rhs = re.split(r"\bdepends\s+on\b", entry, maxsplit=1, flags=re.IGNORECASE)
        elif ":" in entry:
            lhs, rhs = entry.split(":", 1)
        else:
            continue
        target_names = story_names_from_text(lhs)
        if not target_names:
            continue
        depends_on = [] if rhs.strip() in {"", "-"} else story_names_from_text(rhs)
        changes.append({"operation": "set_dependencies", "story": target_names[0], "depends_on": depends_on})
    return changes


def manual_mutation_changes(directives: dict[str, str]) -> list[dict[str, object]]:
    changes: list[dict[str, object]] = []
    for key in ["skip", "skipped", "skip story", "skip-story", "defer", "deferred", "defer story", "defer-story"]:
        for story in story_names_from_text(directives.get(key, "")):
            changes.append({"operation": "skip_story", "story": story, "reason": "Skipped by approved runtime plan mutation."})
    for key in ["remove", "removed", "delete", "remove story", "remove-story"]:
        for story in story_names_from_text(directives.get(key, "")):
            changes.append({"operation": "remove_story", "story": story, "reason": "Removed by approved runtime plan mutation."})
    for key in ["depends", "dependency", "dependencies", "dependency rewrite", "rewrite dependencies", "rewrite-dependencies"]:
        changes.extend(dependency_mutations(directives.get(key, "")))
    reorder = directives.get("reorder", "") or directives.get("order", "")
    if reorder:
        ordered = story_names_from_text(reorder)
        if ordered:
            changes.append({"operation": "reorder_stories", "order": ordered})
    return changes


def parse_stories(path: Path) -> list[StoryBlock]:
    stories: list[StoryBlock] = []
    current_number: int | None = None
    current_title = ""
    current_lines: list[str] = []

    def finish_current() -> None:
        if current_number is None:
            return
        body = "\n".join(current_lines).strip()
        depends: list[int] = []
        covers: list[str] = []
        for raw_line in body.splitlines():
            stripped = raw_line.strip()
            lower = stripped.lower()
            if lower.startswith("depends on:"):
                depends = parse_story_refs(stripped.split(":", 1)[1])
            elif lower.startswith("covers:"):
                covers = parse_comma_list(stripped.split(":", 1)[1])
        stories.append(StoryBlock(current_number, current_title, body, depends, covers))

    for line in read_text(path).splitlines():
        match = STORY_HEADER.match(line.strip())
        if match:
            finish_current()
            current_number = int(match.group(1))
            current_title = match.group(2).strip()
            current_lines = []
            continue
        if current_number is not None:
            current_lines.append(line)
    finish_current()
    return stories


def stories_preamble(path: Path) -> str:
    lines: list[str] = []
    for line in read_text(path).splitlines():
        if STORY_HEADER.match(line.strip()):
            break
        lines.append(line)
    preamble = "\n".join(lines).rstrip()
    return preamble or "# Stories"


def story_heading(story: StoryBlock) -> str:
    title = f": {story.title}" if story.title else ""
    return f"## Story {story.number}{title}"


def render_story_blocks(preamble: str, stories: list[StoryBlock]) -> str:
    parts = [preamble.rstrip(), ""]
    for story in stories:
        parts.append(story_heading(story))
        if story.body:
            parts.append(story.body.rstrip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def set_depends_line(body: str, depends_on: list[str]) -> str:
    replacement = "Depends on: " + (", ".join(depends_on) if depends_on else "-")
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower().startswith("depends on:"):
            lines[index] = replacement
            return "\n".join(lines).rstrip()
    return (replacement + ("\n" + body if body.strip() else "")).rstrip()


def dependency_names_for_story(story: StoryBlock) -> list[str]:
    for raw_line in story.body.splitlines():
        stripped = raw_line.strip()
        if stripped.lower().startswith("depends on:"):
            return story_names_from_text(stripped.split(":", 1)[1])
    return [f"Story {number}" for number in story.depends_on]


def story_by_name(root: Path, slug: str, story_name: str) -> StoryBlock | None:
    number = story_number(story_name)
    if number is None:
        return None
    for story in parse_stories(workflow_path(root, slug, "stories.md")):
        if story.number == number:
            return story
    return None


def story_file(root: Path, slug: str, story_name_or_number: str | int) -> Path:
    number = story_name_or_number if isinstance(story_name_or_number, int) else story_number(story_name_or_number)
    number = number or 1
    return workflow_path(root, slug, f"story-{number}.md")


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_hashes(root: Path, slug: str, story_name: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    inputs = list(INPUT_FILES)
    number = story_number(story_name)
    if number is not None:
        inputs.append(f"story-{number}.md")
    for relative in inputs:
        hashes[relative] = sha256_file(workflow_path(root, slug, relative))
    return hashes


def replan_id(seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    return f"replan-{timestamp_id()}-{digest}"


def clean_title(raw: object, fallback: str) -> str:
    title = re.sub(r"\s+", " ", str(raw or "").strip())
    title = re.sub(r"^Story\s+\d+[A-Za-z]?\s*:?\s*", "", title, flags=re.IGNORECASE).strip()
    return title or fallback


def list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r";|\n", value) if item.strip()]
    return []


def issue_advisor(root: Path, slug: str) -> dict[str, object]:
    return read_json(workflow_path(root, slug, "issue-advisor.json"))


def feedback_synthesis(root: Path, slug: str) -> dict[str, object]:
    return read_json(workflow_path(root, slug, "feedback-synthesis.json"))


def max_story_number(root: Path, slug: str) -> int:
    numbers = [story.number for story in parse_stories(workflow_path(root, slug, "stories.md"))]
    return max(numbers) if numbers else 0


def completed_story_names(root: Path, slug: str) -> set[str]:
    completed: set[str] = set()
    for block in re.split(r"(?=^##\s+Event\s+\d+\b)", read_text(workflow_path(root, slug, "history.md")), flags=re.MULTILINE):
        values: dict[str, str] = {}
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line.startswith("- "):
                continue
            key, _, value = line[2:].partition(":")
            values[key.strip().lower()] = value.strip()
        if values.get("to stage", "").lower() != "done":
            continue
        for story in story_names_from_text(values.get("active items", "")):
            completed.add(story)
        for story in story_names_from_text(values.get("focus items", "")):
            completed.add(story)
    return completed


def sub_story_specs(advisor: dict[str, object], story: StoryBlock | None) -> list[dict[str, object]]:
    raw = advisor.get("sub_stories") or advisor.get("sub_issues") or []
    if isinstance(raw, list) and raw:
        specs = [item for item in raw if isinstance(item, dict)]
        if specs:
            return specs
    title = story.title if story else "Replanned story"
    return [
        {
            "title": f"{title} core path",
            "acceptance_criteria": ["Deliver the smallest core behavior for the replanned slice."],
            "test_expectations": ["Validate the core path."],
        },
        {
            "title": f"{title} follow-up behavior",
            "acceptance_criteria": ["Deliver remaining edge cases and integration behavior."],
            "test_expectations": ["Validate follow-up behavior and regression coverage."],
        },
    ]


def proposal_from_inputs(root: Path, slug: str, note: str | None = None) -> dict[str, object]:
    story_name = active_story(root, slug)
    story = story_by_name(root, slug, story_name)
    advisor = issue_advisor(root, slug)
    feedback = feedback_synthesis(root, slug)
    directives = parse_directives(note)
    manual_changes = manual_mutation_changes(directives)
    advisor_action = str(advisor.get("action") or "").strip().lower()
    feedback_recommendation = str(feedback.get("recommendation") or "").strip().lower()
    plan_type = "manual_replan"
    apply_supported = False
    summary = "No automatic story mutation is available from current evidence; review manually."
    proposed_changes: list[dict[str, object]] = []
    next_number = max_story_number(root, slug) + 1
    rid = replan_id("|".join([slug, story_name, advisor_action, feedback_recommendation, note or ""]))

    if manual_changes:
        plan_type = "runtime_plan_mutation"
        action = "modify_dag"
        apply_supported = True
        summary = "Apply approved runtime plan mutation directives while preserving completed story history."
        proposed_changes.extend(manual_changes)
    elif advisor_action == "split" or feedback_recommendation == "split":
        plan_type = "split_story"
        action = "modify_dag"
        apply_supported = True
        summary = f"Split {story_name or 'the active story'} into smaller follow-up stories and defer the original story."
        specs = sub_story_specs(advisor, story)
        previous_number = next_number
        for index, spec in enumerate(specs):
            number = next_number + index
            depends_on = story.depends_on if index == 0 and story else [previous_number]
            previous_number = number
            proposed_changes.append(
                {
                    "operation": "append_story",
                    "story_number": number,
                    "title": clean_title(spec.get("title"), f"Replanned slice {index + 1}"),
                    "depends_on": [f"Story {item}" for item in depends_on],
                    "acceptance_criteria": list_value(spec.get("acceptance_criteria")),
                    "test_expectations": list_value(spec.get("test_expectations")),
                    "replanned_from": story_name,
                }
            )
        proposed_changes.append({"operation": "defer_story", "story": story_name, "reason": "Replanned into smaller stories."})
    elif advisor_action == "retry_modified" and list_value(advisor.get("modified_acceptance_criteria")):
        plan_type = "modify_acceptance"
        action = "reduce_scope"
        apply_supported = True
        summary = f"Update {story_name or 'the active story'} acceptance criteria from advisor-approved modified scope."
        proposed_changes.append(
            {
                "operation": "replace_acceptance_criteria",
                "story": story_name,
                "acceptance_criteria": list_value(advisor.get("modified_acceptance_criteria")),
                "dropped_criteria": list_value(advisor.get("dropped_criteria")),
            }
        )
    elif advisor_action == "escalate_to_replan" or feedback_recommendation == "replan":
        plan_type = "dependency_replan"
        action = "modify_dag"
        summary = "Escalate to human DAG replanning because evidence points to dependency or architecture structure."
        proposed_changes.append(
            {
                "operation": "manual_dependency_replan",
                "story": story_name,
                "context": advisor.get("suggested_restructuring") or advisor.get("escalation_context") or [],
            }
        )
    elif advisor_action == "accept_with_debt":
        plan_type = "debt_replan"
        action = "continue"
        summary = "Keep story structure stable and record explicit debt before retrying downstream planning."
        proposed_changes.append(
            {
                "operation": "record_debt_before_replan",
                "story": story_name,
                "debt_entries": advisor.get("debt_entries") or advisor.get("suggested_debt") or [],
            }
        )
    else:
        action = "continue"

    payload: dict[str, object] = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": utc_now(),
        "replan_id": rid,
        "status": "proposed",
        "active_story": story_name,
        "action": action,
        "plan_type": plan_type,
        "summary": summary,
        "apply_supported": apply_supported,
        "apply_requires": "confirm: replan",
        "source": {
            "issue_advisor_action": advisor_action,
            "feedback_synthesis_recommendation": feedback_recommendation,
        },
        "proposed_changes": proposed_changes,
        "updated_items": [change for change in proposed_changes if isinstance(change, dict) and change.get("operation") == "replace_acceptance_criteria"],
        "removed_items": [story_name] if plan_type == "split_story" else [
            change.get("story")
            for change in proposed_changes
            if isinstance(change, dict) and change.get("operation") == "remove_story"
        ],
        "skipped_items": [
            change.get("story")
            for change in proposed_changes
            if isinstance(change, dict) and change.get("operation") == "skip_story"
        ],
        "new_items": [change for change in proposed_changes if isinstance(change, dict) and change.get("operation") == "append_story"],
        "dependency_edges": [
            {"story": change.get("story_number") or change.get("story"), "depends_on": change.get("depends_on", [])}
            for change in proposed_changes
            if isinstance(change, dict) and change.get("operation") in {"append_story", "set_dependencies"}
        ],
        "debt_items": advisor.get("debt_entries") or advisor.get("suggested_debt") or [],
        "validation_errors": [],
        "warnings": [] if apply_supported else ["This plan requires manual story or dependency editing before it can be applied automatically."],
        "input_hashes": input_hashes(root, slug, story_name),
    }
    if note and note.strip():
        payload["operator_note"] = note.strip()
    return payload


def current_inputs_match(root: Path, slug: str, proposal: dict[str, object]) -> tuple[bool, list[str]]:
    story = str(proposal.get("active_story") or "")
    recorded = proposal.get("input_hashes", {})
    if not isinstance(recorded, dict):
        return False, ["proposal is missing input hashes"]
    current = input_hashes(root, slug, story)
    changed = [name for name, digest in recorded.items() if current.get(name) != digest]
    return not changed, changed


def completed_apply_blockers(root: Path, slug: str, proposal: dict[str, object]) -> list[str]:
    completed = completed_story_names(root, slug)
    if not completed:
        return []
    plan_type = str(proposal.get("plan_type") or "")
    targets: list[str] = []
    if plan_type == "split_story":
        targets.append(str(proposal.get("active_story") or "").strip())
    elif plan_type == "modify_acceptance":
        for change in proposal.get("proposed_changes", []):
            if isinstance(change, dict) and change.get("operation") == "replace_acceptance_criteria":
                targets.append(str(change.get("story") or proposal.get("active_story") or "").strip())
    blockers: list[str] = []
    for target in targets:
        if target and target in completed:
            blockers.append(f"cannot apply `{plan_type}` to `{target}` because completed history is immutable")
    return blockers


def archive_before_apply(root: Path, slug: str, proposal: dict[str, object]) -> str:
    archive_id = str(proposal.get("replan_id") or replan_id(slug))
    archive_dir = workflow_path(root, slug, f"replans/{archive_id}/before")
    archive_dir.mkdir(parents=True, exist_ok=True)
    story = str(proposal.get("active_story") or "")
    relatives = ["stories.md", "dag.json", "dag.md", "dag-validation.md", "issue-advisor.json", "replan.json"]
    number = story_number(story)
    if number is not None:
        relatives.append(f"story-{number}.md")
    for change in proposal.get("proposed_changes", []):
        if not isinstance(change, dict):
            continue
        target_story = str(change.get("story") or "").strip()
        target_number = story_number(target_story)
        if target_number is not None:
            relative = f"story-{target_number}.md"
            if relative not in relatives:
                relatives.append(relative)
        if change.get("operation") == "append_story":
            new_number = change.get("story_number")
            try:
                relative = f"story-{int(new_number)}.md"
            except (TypeError, ValueError):
                relative = ""
            if relative and relative not in relatives:
                relatives.append(relative)
    for relative in relatives:
        source = workflow_path(root, slug, relative)
        if source.exists():
            target = archive_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return str(archive_dir.relative_to(root))


def append_story_blocks(root: Path, slug: str, proposal: dict[str, object]) -> dict[str, object]:
    stories_path = workflow_path(root, slug, "stories.md")
    text = read_text(stories_path).rstrip() + "\n\n"
    replan_marker = f"Replan id: {proposal.get('replan_id')}"
    if replan_marker in text:
        return {"status": "blocked", "blockers": ["this replan has already been applied to stories.md"]}
    appended_numbers: list[int] = []
    for change in proposal.get("proposed_changes", []):
        if not isinstance(change, dict) or change.get("operation") != "append_story":
            continue
        number = int(change.get("story_number") or 0)
        title = clean_title(change.get("title"), f"Replanned slice {number}")
        depends_on = list_value(change.get("depends_on"))
        acceptance = list_value(change.get("acceptance_criteria"))
        tests = list_value(change.get("test_expectations"))
        text += f"## Story {number}: {title}\n"
        text += f"Depends on: {', '.join(depends_on) if depends_on else '-'}\n"
        text += f"Replanned from: {change.get('replanned_from', proposal.get('active_story', '-'))}\n"
        text += f"{replan_marker}\n\n"
        text += "Acceptance criteria:\n"
        text += "\n".join(f"- {item}" for item in (acceptance or ["Review replanned acceptance criteria."])) + "\n\n"
        text += "Test expectations:\n"
        text += "\n".join(f"- {item}" for item in (tests or ["Review replanned validation expectations."])) + "\n\n"
        write_story_file(root, slug, number, title, depends_on, acceptance, tests, proposal)
        appended_numbers.append(number)
    stories_path.write_text(text, encoding="utf-8")
    return {
        "status": "applied",
        "active_items": f"Story {appended_numbers[0]}" if appended_numbers else str(proposal.get("active_story") or ""),
        "deferred_items": str(proposal.get("active_story") or ""),
    }


def write_story_file(
    root: Path,
    slug: str,
    number: int,
    title: str,
    depends_on: list[str],
    acceptance: list[str],
    tests: list[str],
    proposal: dict[str, object],
) -> None:
    lines = [
        f"# Story {number}",
        "",
        "## Story",
        title,
        "",
        "## Scope",
        f"Replanned from {proposal.get('active_story', '-')}.",
        "",
        "## Dependencies",
        ", ".join(depends_on) if depends_on else "-",
        "",
        "## Acceptance Criteria",
        *[f"- {item}" for item in (acceptance or ["Review replanned acceptance criteria."])],
        "",
        "## Test Expectations",
        *[f"- {item}" for item in (tests or ["Review replanned validation expectations."])],
        "",
        "## Risks",
        "- Replanned story requires review before implementation resumes.",
        "",
        "## Replan Notes",
        f"- Replan id: {proposal.get('replan_id', '-')}",
        f"- Replanned from: {proposal.get('active_story', '-')}",
        "",
    ]
    write_text_if_changed(story_file(root, slug, number), "\n".join(lines))


def replace_acceptance_section(path: Path, criteria: list[str], dropped: list[str], replan: dict[str, object]) -> None:
    lines = read_text(path).splitlines()
    output: list[str] = []
    index = 0
    replaced = False
    while index < len(lines):
        line = lines[index]
        if line.strip().lower() == "## acceptance criteria":
            output.append(line)
            output.extend(f"- {item}" for item in criteria)
            index += 1
            while index < len(lines) and not lines[index].startswith("## "):
                index += 1
            replaced = True
            continue
        output.append(line)
        index += 1
    if not replaced:
        output.extend(["", "## Acceptance Criteria", *[f"- {item}" for item in criteria]])
    output.extend(
        [
            "",
            "## Replan Notes",
            f"- Replan id: {replan.get('replan_id', '-')}",
            f"- Dropped criteria: {'; '.join(dropped) if dropped else '-'}",
        ]
    )
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def apply_modify_acceptance(root: Path, slug: str, proposal: dict[str, object]) -> dict[str, object]:
    for change in proposal.get("proposed_changes", []):
        if not isinstance(change, dict) or change.get("operation") != "replace_acceptance_criteria":
            continue
        story = str(change.get("story") or proposal.get("active_story") or "")
        criteria = list_value(change.get("acceptance_criteria"))
        dropped = list_value(change.get("dropped_criteria"))
        if not criteria:
            return {"status": "blocked", "blockers": ["modified acceptance proposal has no criteria"]}
        replace_acceptance_section(story_file(root, slug, story), criteria, dropped, proposal)
        return {"status": "applied", "active_items": story, "deferred_items": "", "stage": "story-enrichment"}
    return {"status": "blocked", "blockers": ["no replace_acceptance_criteria operation was found"]}


def apply_runtime_plan_mutation(root: Path, slug: str, proposal: dict[str, object]) -> dict[str, object]:
    stories_path = workflow_path(root, slug, "stories.md")
    stories = parse_stories(stories_path)
    if not stories:
        return {"status": "blocked", "blockers": ["stories.md has no stories to mutate"]}
    preamble = stories_preamble(stories_path)
    by_name = {story.name: story for story in stories}
    completed = completed_story_names(root, slug)
    blockers: list[str] = []
    skipped: list[str] = []
    removed: list[str] = []
    updated: list[str] = []
    ordered_names: list[str] = []
    notes: list[str] = []

    for change in proposal.get("proposed_changes", []):
        if not isinstance(change, dict):
            continue
        operation = str(change.get("operation") or "")
        story_name = str(change.get("story") or "").strip()
        if operation in {"skip_story", "remove_story", "set_dependencies"}:
            if story_name not in by_name:
                blockers.append(f"{operation} target `{story_name or '-'}` is not present in stories.md")
                continue
            if story_name in completed:
                blockers.append(f"{operation} target `{story_name}` is already completed; completed history is immutable")
                continue
        if operation == "skip_story":
            if story_name not in skipped:
                skipped.append(story_name)
            notes.append(f"{story_name}: skipped by replan")
        elif operation == "remove_story":
            if story_name not in removed:
                removed.append(story_name)
            notes.append(f"{story_name}: removed from remaining plan by replan")
        elif operation == "set_dependencies":
            deps = [str(item).strip() for item in list_value(change.get("depends_on"))]
            missing_deps = [dep for dep in deps if dep not in by_name]
            if missing_deps:
                blockers.append(f"{story_name} depends on unknown story/stories: {', '.join(missing_deps)}")
                continue
            by_name[story_name].body = set_depends_line(by_name[story_name].body, deps)
            if story_name not in updated:
                updated.append(story_name)
            notes.append(f"{story_name}: dependencies set to {', '.join(deps) if deps else '-'}")
        elif operation == "reorder_stories":
            ordered_names = [name for name in list_value(change.get("order")) if name in by_name and name not in completed]
            missing_order = [name for name in list_value(change.get("order")) if name not in by_name]
            if missing_order:
                blockers.append("reorder references unknown story/stories: " + ", ".join(missing_order))
            completed_order = [name for name in list_value(change.get("order")) if name in completed]
            if completed_order:
                notes.append("Completed stories were left in their original order: " + ", ".join(completed_order))

    removed_set = set(removed)
    if removed_set:
        for story in stories:
            if story.name in removed_set:
                continue
            dangling = [dep for dep in dependency_names_for_story(by_name[story.name]) if dep in removed_set]
            if dangling:
                blockers.append(
                    f"remove_story would leave `{story.name}` depending on removed story/stories: "
                    + ", ".join(dangling)
                    + "; rewrite dependencies in the same replan"
                )

    if blockers:
        return {"status": "blocked", "blockers": blockers}

    remaining_stories = [story for story in stories if story.name not in removed]
    if ordered_names:
        order_index = {name: index for index, name in enumerate(ordered_names)}
        original_index = {story.name: index for index, story in enumerate(remaining_stories)}
        remaining_stories = sorted(
            remaining_stories,
            key=lambda story: (
                0 if story.name in completed else 1,
                original_index.get(story.name, story.number) if story.name in completed else order_index.get(story.name, len(order_index) + story.number),
                story.number,
            ),
        )
    stories_path.write_text(render_story_blocks(preamble, remaining_stories), encoding="utf-8")

    for story_name in skipped + removed + updated:
        path = story_file(root, slug, story_name)
        if not path.exists():
            continue
        existing = read_text(path).rstrip()
        marker = f"- Replan id: {proposal.get('replan_id', '-')}"
        if marker in existing:
            continue
        extra = [
            "",
            "## Replan Notes",
            marker,
        ]
        if story_name in skipped:
            extra.append("- Runtime mutation: skipped")
        if story_name in removed:
            extra.append("- Runtime mutation: removed from remaining plan")
        if story_name in updated:
            extra.append("- Runtime mutation: dependencies updated")
        path.write_text(existing + "\n" + "\n".join(extra).rstrip() + "\n", encoding="utf-8")

    active_items = ""
    for story in remaining_stories:
        if story.name not in skipped and story.name not in completed:
            active_items = story.name
            break
    return {
        "status": "applied",
        "active_items": active_items,
        "deferred_items": ", ".join(skipped),
        "removed_items": ", ".join(removed),
        "stage": "story-slicing",
        "mutation_notes": notes,
    }


def apply_proposal(root: Path, slug: str, proposal: dict[str, object]) -> dict[str, object]:
    if not proposal.get("apply_supported"):
        return {"status": "blocked", "blockers": ["this replan proposal is advisory and cannot be applied automatically"]}
    matches, changed = current_inputs_match(root, slug, proposal)
    if not matches:
        return {"status": "blocked", "blockers": ["replan proposal is stale because inputs changed: " + ", ".join(changed[:4])]}
    completed_blockers = completed_apply_blockers(root, slug, proposal)
    if completed_blockers:
        return {"status": "blocked", "blockers": completed_blockers}
    archive_path = archive_before_apply(root, slug, proposal)
    plan_type = str(proposal.get("plan_type") or "")
    if plan_type == "split_story":
        result = append_story_blocks(root, slug, proposal)
    elif plan_type == "modify_acceptance":
        result = apply_modify_acceptance(root, slug, proposal)
    elif plan_type == "runtime_plan_mutation":
        result = apply_runtime_plan_mutation(root, slug, proposal)
    else:
        result = {"status": "blocked", "blockers": [f"automatic apply is not implemented for plan type `{plan_type}`"]}
    result["archive_path"] = archive_path
    return result


def append_replan_record(root: Path, slug: str, payload: dict[str, object]) -> None:
    record = {
        "recorded_at": utc_now(),
        "workflow_slug": slug,
        "replan_id": payload.get("replan_id", ""),
        "status": payload.get("status", ""),
        "active_story": payload.get("active_story", ""),
        "plan_type": payload.get("plan_type", ""),
        "summary": payload.get("summary", ""),
    }
    path = replan_records_path(root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def render_markdown(payload: dict[str, object]) -> str:
    changes = payload.get("proposed_changes", [])
    blockers = payload.get("blockers", [])
    warnings = payload.get("warnings", [])
    state_updates = payload.get("state_updates", {})
    lines = [
        "# Replan",
        "",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Replan id: {payload.get('replan_id', '-')}",
        f"- Status: {payload.get('status', '-')}",
        f"- Active story: {payload.get('active_story', '-') or '-'}",
        f"- Plan type: {payload.get('plan_type', '-')}",
        f"- Apply supported: {'yes' if payload.get('apply_supported') else 'no'}",
        f"- Apply requires: {payload.get('apply_requires', '-')}",
        f"- Summary: {payload.get('summary', '-')}",
        "",
        "## Proposed Changes",
    ]
    if isinstance(changes, list) and changes:
        for change in changes:
            if isinstance(change, dict):
                lines.append(f"- {change.get('operation', '-')}: {change.get('story') or change.get('title') or change.get('story_number') or '-'}")
    else:
        lines.append("- none")
    lines.extend(["", "## State Updates"])
    if isinstance(state_updates, dict) and state_updates:
        lines.extend(f"- {key}: {value}" for key, value in state_updates.items())
    else:
        lines.append("- none")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in blockers if str(item).strip()) if isinstance(blockers, list) and blockers else lines.append("- none")
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in warnings if str(item).strip()) if isinstance(warnings, list) and warnings else lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def ensure_replan_artifact(root: Path, slug: str) -> None:
    path = replan_summary_path(root, slug)
    if path.exists():
        return
    write_text_if_changed(
        path,
        f"""# Replan

- Workflow slug: {slug}
- Status:
- Plan type:
- Summary:

## Proposed Changes
- none

## Blockers
- none
""",
    )


def run_replanner(root: Path, slug: str, note: str | None = None, apply_changes: bool = False) -> dict[str, object]:
    if apply_changes:
        proposal = read_json(replan_path(root, slug))
        if not proposal or str(proposal.get("status") or "").strip().lower() == "not_recorded":
            payload = proposal_from_inputs(root, slug, note)
            payload["status"] = "blocked"
            payload["blockers"] = ["cannot apply replan before a proposal exists"]
        else:
            result = apply_proposal(root, slug, proposal)
            payload = dict(proposal)
            payload["generated_at"] = utc_now()
            payload["status"] = result.get("status", "blocked")
            payload["blockers"] = result.get("blockers", [])
            payload["archive_path"] = result.get("archive_path", "")
            payload["state_updates"] = {
                key: value
                for key, value in result.items()
                if key in {"active_items", "deferred_items", "stage"} and str(value).strip()
            }
    else:
        payload = proposal_from_inputs(root, slug, note)
    write_text_if_changed(replan_path(root, slug), json.dumps(payload, indent=2) + "\n")
    write_text_if_changed(replan_summary_path(root, slug), render_markdown(payload))
    append_replan_record(root, slug, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Propose or apply a human-approved story/DAG replan.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--note", default="")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    run_replanner(Path(args.root).resolve(), args.slug, args.note, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

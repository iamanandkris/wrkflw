#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from workflow_debt import (
    blocking_debt_records,
    debt_for_node_id,
    format_debt_summary,
    has_blocking_debt,
    load_debt_records,
    render_debt_summary,
)
from workflow_execution_paths import execution_path_for_metadata, risk_metadata_for_story


STORY_HEADER = re.compile(r"^##\s+Story\s+(\d+)\s*:?\s*(.*)$", re.IGNORECASE)
STORY_REF = re.compile(r"\bstory[-\s]+(\d+)\b", re.IGNORECASE)
SPECIAL_DEPENDENCIES = {
    "",
    "-",
    "none",
    "n/a",
    "completed prior epic",
    "completed prior epics",
    "completed dependencies",
}
RISK_KEYWORDS = {
    "approval",
    "audit",
    "auth",
    "credential",
    "database",
    "migration",
    "permission",
    "policy",
    "remote",
    "security",
    "secret",
    "side effect",
    "side-effect",
    "sql",
    "tenant",
    "transport",
}


@dataclass
class Story:
    number: int
    title: str
    body: str
    depends_on: list[str]
    covers: list[str]

    @property
    def story_name(self) -> str:
        return f"Story {self.number}"

    @property
    def node_id(self) -> str:
        return f"story-{self.number}"

    @property
    def label(self) -> str:
        return f"{self.story_name}: {self.title}" if self.title else self.story_name


@dataclass
class LaneDependencies:
    depends_on: list[str]
    blocked_by: list[str]
    satisfied_by: list[str]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        values[key.strip()] = value.strip()
    return values


def parse_story_refs(raw: str) -> list[int]:
    if raw.strip().lower() in SPECIAL_DEPENDENCIES:
        return []
    return [int(match.group(1)) for match in STORY_REF.finditer(raw)]


def parse_comma_list(raw: str) -> list[str]:
    items: list[str] = []
    for item in raw.split(","):
        cleaned = item.strip()
        if cleaned and cleaned.lower() not in SPECIAL_DEPENDENCIES:
            items.append(cleaned)
    return items


def parse_stories(path: Path) -> list[Story]:
    stories: list[Story] = []
    current_number: int | None = None
    current_title = ""
    current_lines: list[str] = []

    def finish_current() -> None:
        if current_number is None:
            return
        body = "\n".join(current_lines).strip()
        depends: list[str] = []
        covers: list[str] = []
        for raw_line in body.splitlines():
            stripped = raw_line.strip()
            lower = stripped.lower()
            if lower.startswith("depends on:"):
                depends = [f"story-{number}" for number in parse_story_refs(stripped.split(":", 1)[1])]
            elif lower.startswith("covers:"):
                covers = parse_comma_list(stripped.split(":", 1)[1])
        stories.append(
            Story(
                number=current_number,
                title=current_title,
                body=body,
                depends_on=depends,
                covers=covers,
            )
        )

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
    return sorted(stories, key=lambda story: story.number)


def section_bullets(path: Path, section_names: set[str]) -> list[str]:
    bullets: list[str] = []
    active = False
    for raw_line in read_text(path).splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("## "):
            heading = stripped.lstrip("#").strip().lower()
            active = heading in section_names
            continue
        if active and stripped.startswith("- "):
            item = stripped[2:].strip()
            if item:
                bullets.append(item)
    return bullets


def story_detail(path: Path) -> dict[str, list[str]]:
    return {
        "acceptance": section_bullets(path, {"acceptance criteria"}),
        "validation": section_bullets(path, {"test expectations", "validation"}),
        "risks": section_bullets(path, {"risks"}),
        "allowed_paths": section_bullets(path, {"allowed write paths", "likely changed paths", "write paths"}),
    }


def risk_for_story(story: Story, detail: dict[str, list[str]]) -> str:
    haystack = " ".join([story.title, story.body, *detail.get("risks", [])]).lower()
    return "high" if any(keyword in haystack for keyword in RISK_KEYWORDS) else "normal"


def parse_story_numbers(raw: str) -> set[int]:
    return {int(match.group(1)) for match in STORY_REF.finditer(raw or "")}


def completed_story_numbers(workflow_dir: Path, state: dict[str, str]) -> set[int]:
    completed: set[int] = set()
    history_path = workflow_dir / "history.md"
    for block in re.split(r"(?=^##\s+Event\s+\d+\b)", read_text(history_path), flags=re.MULTILINE):
        values: dict[str, str] = {}
        for line in block.splitlines():
            if not line.startswith("- "):
                continue
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
        if values.get("To stage", "").strip() != "done":
            continue
        completed.update(parse_story_numbers(values.get("Active items", "")))
        completed.update(parse_story_numbers(values.get("Focus items", "")))
    if state.get("Current stage", "").strip() == "done":
        completed.update(parse_story_numbers(state.get("Active items", "")))
    return completed


def workflow_slugs(root: Path) -> list[str]:
    workflow_root = root / ".workflow"
    if not workflow_root.exists():
        return []
    return sorted(
        path.name
        for path in workflow_root.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    )


def completed_workflow_dependencies(root: Path) -> set[str]:
    completed: set[str] = set()
    for slug in workflow_slugs(root):
        state = parse_kv_list(root / ".workflow" / slug / "state.md")
        if state.get("Current stage", "").strip() == "done":
            completed.add(slug)
    return completed


def lane_dependencies(root: Path, workflow_slug: str) -> LaneDependencies:
    values = parse_kv_list(root / ".workflow" / workflow_slug / "dependencies.md")
    depends_on = parse_comma_list(values.get("Depends on", ""))
    explicit_blocked = parse_comma_list(values.get("Blocked by", ""))
    completed = completed_workflow_dependencies(root)
    satisfied = [item for item in depends_on if item in completed]
    computed_blocked = [item for item in depends_on if item not in completed]
    blocked = sorted(set(explicit_blocked) | set(computed_blocked))
    return LaneDependencies(depends_on=depends_on, blocked_by=blocked, satisfied_by=sorted(set(satisfied)))


def topological_levels(stories: list[Story]) -> tuple[list[list[str]], dict[str, list[str]], list[str]]:
    errors: list[str] = []
    story_counts: dict[str, int] = {}
    for story in stories:
        story_counts[story.node_id] = story_counts.get(story.node_id, 0) + 1
    duplicates = sorted((node_id for node_id, count in story_counts.items() if count > 1), key=story_sort_key)
    if duplicates:
        errors.append(f"Duplicate story ids: {', '.join(duplicates)}")
    story_ids = {story.node_id for story in stories}
    unknown = {
        dep
        for story in stories
        for dep in story.depends_on
        if dep not in story_ids
    }
    if unknown:
        errors.append(f"Unknown story dependencies: {', '.join(sorted(unknown))}")

    dependents: dict[str, list[str]] = {story.node_id: [] for story in stories}
    remaining_deps: dict[str, set[str]] = {
        story.node_id: {dep for dep in story.depends_on if dep in story_ids}
        for story in stories
    }
    for story in stories:
        for dep in story.depends_on:
            if dep in dependents:
                dependents[dep].append(story.node_id)

    if errors:
        return [], {node: sorted(nodes, key=story_sort_key) for node, nodes in dependents.items()}, errors

    levels: list[list[str]] = []
    ready = sorted((node for node, deps in remaining_deps.items() if not deps), key=story_sort_key)
    emitted: set[str] = set()
    while ready:
        level = ready
        levels.append(level)
        next_ready: list[str] = []
        for node in level:
            emitted.add(node)
            for dependent in dependents[node]:
                remaining_deps[dependent].discard(node)
                if not remaining_deps[dependent]:
                    next_ready.append(dependent)
        ready = sorted((node for node in next_ready if node not in emitted), key=story_sort_key)

    if len(emitted) != len(stories):
        cyclic = sorted(set(remaining_deps) - emitted, key=story_sort_key)
        errors.append(f"Cycle detected in story dependencies: {', '.join(cyclic)}")
    return levels, {node: sorted(nodes, key=story_sort_key) for node, nodes in dependents.items()}, errors


def story_sort_key(node_id: str) -> int:
    match = re.search(r"(\d+)$", node_id)
    return int(match.group(1)) if match else 999999


def story_dependency_blockers(story: Story, completed: set[int], known_ids: set[str]) -> list[str]:
    blockers: list[str] = []
    for dep in story.depends_on:
        if dep not in known_ids:
            blockers.append(dep)
            continue
        if story_sort_key(dep) not in completed:
            blockers.append(dep)
    return blockers


def status_for_story(story: Story, state: dict[str, str], completed: set[int], story_blockers: list[str], lane_blockers: list[str]) -> str:
    active = parse_story_numbers(state.get("Active items", ""))
    deferred = parse_story_numbers(state.get("Deferred items", ""))
    if story.number in deferred:
        return "deferred"
    if story.number in completed:
        return "completed"
    if story_blockers or lane_blockers:
        return "blocked"
    if story.number in active:
        return "active"
    return "ready"


def table_cell(value: object) -> str:
    if isinstance(value, list):
        text = ", ".join(str(item).strip() for item in value if str(item).strip())
    elif isinstance(value, bool):
        text = "yes" if value else "no"
    else:
        text = str(value).strip() if value is not None else "-"
    if not text:
        return "-"
    return re.sub(r"\s+", " ", text).replace("|", "\\|")


def render_mermaid(stories: list[Story]) -> list[str]:
    lines = ["```mermaid", "flowchart LR"]
    for story in stories:
        node = story.node_id.replace("-", "_")
        lines.append(f'  {node}["{table_cell(story.label)}"]')
    for story in stories:
        target = story.node_id.replace("-", "_")
        for dep in story.depends_on:
            source = dep.replace("-", "_")
            lines.append(f"  {source} --> {target}")
    lines.append("```")
    return lines


def render_markdown(
    workflow_slug: str,
    generated_at: str,
    source: str,
    state: dict[str, str],
    levels: list[list[str]],
    nodes: list[dict[str, object]],
    stories: list[Story],
    validation: dict[str, object],
    lane_metadata: dict[str, object],
) -> str:
    output = [
        "# Story DAG",
        "",
        f"- Workflow slug: {workflow_slug}",
        f"- Generated at: {generated_at}",
        f"- Source: `{source}`",
        f"- Validation status: {validation.get('status', '-') or '-'}",
        f"- Current stage: {state.get('Current stage', '') or '-'}",
        f"- Active items: {state.get('Active items', '') or '-'}",
        f"- Deferred items: {state.get('Deferred items', '') or '-'}",
        "",
        "This is a derived scheduler artifact. `state.md` remains the workflow source of truth.",
        "",
        "## Lane Dependencies",
        "",
        f"- Depends on: {table_cell(lane_metadata.get('depends_on', []))}",
        f"- Blocked by: {table_cell(lane_metadata.get('blocked_by', []))}",
        f"- Satisfied by: {table_cell(lane_metadata.get('satisfied_by', []))}",
        "",
        "## Graph",
        "",
        *render_mermaid(stories),
        "",
        "## Execution Levels",
        "",
        "| Level | Nodes |",
        "| --- | --- |",
    ]
    for index, level in enumerate(levels, start=1):
        output.append(f"| {index} | {', '.join(level)} |")
    output.extend(
        [
            "",
            "## Nodes",
            "",
            "| ID | Story | Status | Depends On | Lane Blockers | Write Paths | Path | Scope | Risk | QA | Debt | Review Focus |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for node in nodes:
        execution_path = node.get("execution_path", {})
        execution_path = execution_path if isinstance(execution_path, dict) else {}
        output.append(
            "| "
            + " | ".join(
                table_cell(value)
                for value in [
                    node.get("id", ""),
                    node.get("story", ""),
                    node.get("status", ""),
                    node.get("depends_on", ""),
                    node.get("blocked_by_lanes", ""),
                    node.get("allowed_paths", ""),
                    execution_path.get("path", ""),
                    node.get("estimated_scope", ""),
                    node.get("risk", ""),
                    node.get("needs_deeper_qa", ""),
                    node.get("debt_summary", ""),
                    node.get("review_focus", ""),
                ]
            )
            + " |"
        )
    output.append("")
    return "\n".join(output)


def render_validation_markdown(
    workflow_slug: str,
    generated_at: str,
    source: str,
    validation: dict[str, object],
    lane_metadata: dict[str, object],
    levels: list[list[str]],
) -> str:
    errors = validation.get("errors", [])
    warnings = validation.get("warnings", [])
    output = [
        "# DAG Validation",
        "",
        f"- Workflow slug: {workflow_slug}",
        f"- Generated at: {generated_at}",
        f"- Source: `{source}`",
        f"- Status: {validation.get('status', '-') or '-'}",
        f"- Valid graph: {'yes' if validation.get('valid') else 'no'}",
        "",
        "## Errors",
    ]
    if isinstance(errors, list) and errors:
        for item in errors:
            output.append(f"- {item}")
    else:
        output.append("- none")
    output.extend(["", "## Warnings"])
    if isinstance(warnings, list) and warnings:
        for item in warnings:
            output.append(f"- {item}")
    else:
        output.append("- none")
    output.extend(
        [
            "",
            "## Lane Dependencies",
            f"- Depends on: {table_cell(lane_metadata.get('depends_on', []))}",
            f"- Blocked by: {table_cell(lane_metadata.get('blocked_by', []))}",
            f"- Satisfied by: {table_cell(lane_metadata.get('satisfied_by', []))}",
            "",
            "## Execution Levels",
        ]
    )
    if levels:
        for index, level in enumerate(levels, start=1):
            output.append(f"- Level {index}: {', '.join(level)}")
    else:
        output.append("- none")
    output.append("")
    return "\n".join(output)


def stable_payload(payload: dict[str, object]) -> dict[str, object]:
    stable = deepcopy(payload)
    stable.pop("generated_at", None)
    return stable


def reuse_generated_at_if_unchanged(path: Path, payload: dict[str, object], fallback: str) -> str:
    if not path.exists():
        return fallback
    try:
        existing = json.loads(read_text(path))
    except json.JSONDecodeError:
        return fallback
    if not isinstance(existing, dict):
        return fallback
    if stable_payload(existing) == stable_payload(payload):
        existing_generated_at = str(existing.get("generated_at", "")).strip()
        if existing_generated_at:
            return existing_generated_at
    return fallback


def write_text_if_changed(path: Path, content: str) -> None:
    if path.exists() and read_text(path) == content:
        return
    path.write_text(content, encoding="utf-8")


def generate(root: Path, workflow_slug: str) -> None:
    workflow_dir = root / ".workflow" / workflow_slug
    workflow_dir.mkdir(parents=True, exist_ok=True)
    stories_path = workflow_dir / "stories.md"
    stories = parse_stories(stories_path)

    state = parse_kv_list(workflow_dir / "state.md")
    generated_at = utc_now()
    lane_deps = lane_dependencies(root, workflow_slug)
    levels, dependents, graph_errors = topological_levels(stories)
    warnings: list[str] = []
    if not stories:
        graph_errors.append(f"No stories found in {stories_path}")
    lane_metadata = {
        "depends_on": lane_deps.depends_on,
        "blocked_by": lane_deps.blocked_by,
        "satisfied_by": lane_deps.satisfied_by,
    }
    if lane_deps.blocked_by:
        warnings.append(f"Lane is blocked by incomplete workflow dependencies: {', '.join(lane_deps.blocked_by)}")
    validation_status = "invalid" if graph_errors else "blocked" if lane_deps.blocked_by else "valid"
    validation = {
        "status": validation_status,
        "valid": not graph_errors,
        "errors": graph_errors,
        "warnings": warnings,
    }
    completed = completed_story_numbers(workflow_dir, state)
    nodes: list[dict[str, object]] = []
    known_story_ids = {story.node_id for story in stories}
    debt_records = load_debt_records(root, workflow_slug)
    blocking_debt = blocking_debt_records(debt_records)
    if blocking_debt:
        warnings.append(
            "Open high/critical technical debt exists: "
            + "; ".join(format_debt_summary([record], 1) for record in blocking_debt[:3])
        )
        validation["warnings"] = warnings

    level_lookup = {
        node_id: level_index
        for level_index, level in enumerate(levels, start=1)
        for node_id in level
    }
    for story in stories:
        detail = story_detail(workflow_dir / f"story-{story.number}.md")
        base_risk = risk_for_story(story, detail)
        story_blockers = story_dependency_blockers(story, completed, known_story_ids)
        technical_debt = debt_for_node_id(story.node_id, debt_records, dependents, known_story_ids)
        has_debt_block = has_blocking_debt(technical_debt)
        planner_metadata = risk_metadata_for_story(
            title=story.title,
            body=story.body,
            risks=list(detail.get("risks", [])),
            acceptance=list(detail.get("acceptance", [])),
            validation=list(detail.get("validation", [])),
            allowed_paths=list(detail.get("allowed_paths", [])),
            dependents=dependents.get(story.node_id, []),
            technical_debt=technical_debt,
        )
        if base_risk == "high" and "risk keyword or sensitive domain" not in planner_metadata["flag_reasons"]:
            planner_metadata["flag_reasons"].append("risk keyword or sensitive domain")
            planner_metadata["needs_deeper_qa"] = True
            planner_metadata["risk_rationale"] = "; ".join(planner_metadata["flag_reasons"])
        execution_path = execution_path_for_metadata(planner_metadata)
        risk = "high" if planner_metadata["needs_deeper_qa"] or has_debt_block else "normal"
        nodes.append(
            {
                "id": story.node_id,
                "story": story.story_name,
                "title": story.title,
                "label": story.label,
                "status": status_for_story(story, state, completed, story_blockers, lane_deps.blocked_by),
                "level": level_lookup.get(story.node_id),
                "depends_on": story.depends_on,
                "dependents": dependents.get(story.node_id, []),
                "blocked_by_stories": story_blockers,
                "blocked_by_lanes": lane_deps.blocked_by,
                "covers": story.covers,
                "risk": risk,
                "estimated_scope": planner_metadata["estimated_scope"],
                "touches_interfaces": planner_metadata["touches_interfaces"],
                "needs_new_tests": planner_metadata["needs_new_tests"],
                "needs_deeper_qa": planner_metadata["needs_deeper_qa"],
                "testing_guidance": planner_metadata["testing_guidance"],
                "review_focus": planner_metadata["review_focus"],
                "risk_rationale": planner_metadata["risk_rationale"],
                "flag_reasons": planner_metadata["flag_reasons"],
                "planner_metadata": planner_metadata,
                "execution_path": execution_path,
                "acceptance": detail.get("acceptance", []),
                "validation": detail.get("validation", []),
                "allowed_paths": detail.get("allowed_paths", []),
                "technical_debt": technical_debt,
                "debt_summary": format_debt_summary(technical_debt),
                "has_blocking_debt": has_debt_block,
                "source": f".workflow/{workflow_slug}/stories.md",
            }
        )

    payload: dict[str, object] = {
        "schema_version": 1,
        "workflow_slug": workflow_slug,
        "generated_at": generated_at,
        "source": f".workflow/{workflow_slug}/stories.md",
        "current_stage": state.get("Current stage", ""),
        "human_gate_status": state.get("Human gate status", ""),
        "active_items": state.get("Active items", ""),
        "deferred_items": state.get("Deferred items", ""),
        "validation": validation,
        "lane_dependencies": lane_metadata,
        "levels": levels,
        "nodes": nodes,
    }
    generated_at = reuse_generated_at_if_unchanged(workflow_dir / "dag.json", payload, generated_at)
    payload["generated_at"] = generated_at
    render_debt_summary(root, workflow_slug, debt_records)

    write_text_if_changed(workflow_dir / "dag.json", json.dumps(payload, indent=2) + "\n")
    write_text_if_changed(
        workflow_dir / "dag.md",
        render_markdown(workflow_slug, generated_at, payload["source"], state, levels, nodes, stories, validation, lane_metadata),
    )
    write_text_if_changed(
        workflow_dir / "dag-validation.md",
        render_validation_markdown(workflow_slug, generated_at, payload["source"], validation, lane_metadata, levels),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate story DAG artifacts from .workflow/<slug>/stories.md.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    generate(Path(args.root).resolve(), args.slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

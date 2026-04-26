#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from subprocess import run


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "workflow-change"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def parse_state(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def openspec_lane_active(contract: dict[str, str]) -> bool:
    return contract.get("OpenSpec lane active", "false").strip().lower() in {"true", "1", "yes", "on"}


def initiative_status(state: dict[str, str]) -> str:
    stage = state.get("Current stage", "").strip() or "discuss"
    gate = state.get("Human gate status", "").strip()
    if stage == "done":
        return "done"
    if gate == "blocked":
        return "blocked"
    if gate == "approved":
        return "in-progress"
    return "pending"


def update_initiative_index(root: Path, workflow_slug: str) -> None:
    workflow_root = root / ".workflow"
    index_path = workflow_root / "initiative-index.md"
    state = parse_state(workflow_root / workflow_slug / "state.md")
    links = parse_kv_list(workflow_root / workflow_slug / "links.md")

    row = {
        "Workflow slug": workflow_slug,
        "Status": initiative_status(state),
        "Current stage": state.get("Current stage", "").strip() or "discuss",
        "Design seed": links.get("Design seed", "").strip() or "-",
        "OpenSpec change": links.get("OpenSpec change", "").strip() or "-",
        "Docs": links.get("Docs", "").strip() or "-",
    }

    rows: list[dict[str, str]] = []
    for line in read_text(index_path).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "Workflow slug" in stripped or set(stripped) <= {"|", "-", " "}:
            continue
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        if len(parts) != 6:
            continue
        rows.append(
            {
                "Workflow slug": parts[0],
                "Status": parts[1],
                "Current stage": parts[2],
                "Design seed": parts[3],
                "OpenSpec change": parts[4],
                "Docs": parts[5],
            }
        )

    replaced = False
    for index, existing in enumerate(rows):
        if existing["Workflow slug"] == workflow_slug:
            rows[index] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)

    rows.sort(key=lambda item: item["Workflow slug"])
    output = [
        "# Initiative Index",
        "",
        "| Workflow slug | Status | Current stage | Design seed | OpenSpec change | Docs |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in rows:
        output.append(
            f"| {item['Workflow slug']} | {item['Status']} | {item['Current stage']} | {item['Design seed']} | {item['OpenSpec change']} | {item['Docs']} |"
        )
    output.append("")
    write_text(index_path, "\n".join(output))


def parse_state_active_item(state_path: Path) -> str:
    for line in read_text(state_path).splitlines():
        if line.startswith("- Active items:"):
            return line.split(":", 1)[1].strip()
    return ""


def parse_story_block(stories_text: str, active_story: str) -> tuple[str, str]:
    lines = stories_text.splitlines()
    capture = False
    block: list[str] = []
    story_header = active_story
    for line in lines:
        if line.startswith("## "):
            current_header = line[3:].strip()
            current_name = current_header.split(":", 1)[0].strip()
            if current_name == active_story:
                capture = True
                story_header = current_header
                block.append(line)
                continue
            if capture:
                break
        if capture:
            block.append(line)
    return story_header, "\n".join(block).strip()


def parse_markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current = line[3:].strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def section_paragraph(sections: dict[str, list[str]], name: str) -> str:
    return " ".join(line.strip() for line in sections.get(name, []) if line.strip())


def section_bullets(sections: dict[str, list[str]], name: str) -> list[str]:
    bullets: list[str] = []
    for line in sections.get(name, []):
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def parse_capability_inventory(text: str) -> tuple[str, list[dict[str, object]]]:
    mode = "general-delivery"
    capabilities: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("- Mode:"):
            mode = stripped.split(":", 1)[1].strip()
            continue
        if line.startswith("### "):
            if current is not None:
                capabilities.append(current)
            current = {"name": line[4:].strip(), "status": "optional", "why": "", "why_now": "", "story_prompts": []}
            current_section = None
            continue
        if current is None:
            continue
        if stripped.startswith("- Status:"):
            current["status"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- Why:"):
            current["why"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- Why now:"):
            current["why_now"] = stripped.split(":", 1)[1].strip()
        elif stripped == "- Story prompts:":
            current_section = "story_prompts"
        elif current_section == "story_prompts" and stripped.startswith("- "):
            prompts = current["story_prompts"]  # type: ignore[assignment]
            prompts.append(stripped[2:].strip())
        elif stripped:
            current_section = None
    if current is not None:
        capabilities.append(current)
    return mode, capabilities


def infer_story_coverage(
    story_title: str,
    story_scope: str,
    story_acceptance: list[str],
    story_test_expectations: list[str],
    capabilities: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    text = " ".join([story_title, story_scope, *story_acceptance, *story_test_expectations]).lower()
    covered: list[dict[str, object]] = []
    deferred: list[dict[str, object]] = []
    for capability in capabilities:
        name = str(capability["name"])
        status = str(capability["status"])
        prompts = capability["story_prompts"]  # type: ignore[assignment]
        capability_text = " ".join([name, str(capability.get("why", "")), str(capability.get("why_now", "")), *prompts]).lower()
        name_tokens = re.findall(r"[a-z0-9]+", name.lower())
        prompt_hits = sum(1 for token in re.findall(r"[a-z0-9]+", capability_text) if len(token) > 4 and token in text)
        title_hits = sum(1 for token in name_tokens if token in text)
        if title_hits > 0 or prompt_hits >= 2:
            covered.append(capability)
        elif status in {"required", "recommended"}:
            deferred.append(capability)
    return covered, deferred


def ensure_change(root: Path, change_slug: str, description: str) -> Path:
    change_dir = root / "openspec" / "changes" / change_slug
    if change_dir.exists():
        return change_dir
    run(
        ["openspec", "new", "change", change_slug, "--description", description],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return change_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Bridge current wrkflw story artifacts into a real OpenSpec change.")
    parser.add_argument("--slug", required=True, help="Workflow slug")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--change-slug", help="Override OpenSpec change slug")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    workflow_dir = root / ".workflow" / args.slug
    state_path = workflow_dir / "state.md"
    links_path = workflow_dir / "links.md"
    stories_path = workflow_dir / "stories.md"
    contract = parse_kv_list(workflow_dir / "workflow-contract.md")

    if not openspec_lane_active(contract):
        print("openspec lane inactive")
        return 0

    active_items = parse_state_active_item(state_path)
    active_story = active_items.split(",", 1)[0].strip() if active_items else "Story 1"
    story_num_match = re.search(r"(\d+)", active_story)
    story_num = story_num_match.group(1) if story_num_match else "1"

    story_file_path = workflow_dir / f"story-{story_num}.md"
    story_spec_path = workflow_dir / "specs" / f"story-{story_num}-spec.md"
    story_header, story_block = parse_story_block(read_text(stories_path), active_story)
    story_title = story_header.split(":", 1)[1].strip() if ":" in story_header else active_story
    capability_slug = slugify(story_title)
    workflow_prefixed_story_slug = f"{args.slug}-{capability_slug}"
    change_slug = args.change_slug or workflow_prefixed_story_slug

    story_enrichment = read_text(story_file_path).strip()
    enrichment_sections = parse_markdown_sections(story_enrichment)
    story_scope = section_paragraph(enrichment_sections, "Scope")
    story_acceptance = section_bullets(enrichment_sections, "Acceptance Criteria")
    story_test_expectations = section_bullets(enrichment_sections, "Test Expectations")
    story_risks = section_bullets(enrichment_sections, "Risks")
    workflow_spec = read_text(story_spec_path).strip()
    capability_mode, capability_inventory = parse_capability_inventory(read_text(workflow_dir / "capabilities.md"))
    covered_capabilities, deferred_capabilities = infer_story_coverage(
        story_title,
        story_scope,
        story_acceptance,
        story_test_expectations,
        capability_inventory,
    )

    change_dir = ensure_change(root, change_slug, f"{active_story}: {story_title}")
    specs_dir = change_dir / "specs" / capability_slug
    specs_dir.mkdir(parents=True, exist_ok=True)

    story_desc = ""
    for line in story_block.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("## ") and not stripped.lower().startswith("depends on:"):
            story_desc = stripped
            break
    story_desc = story_desc or story_scope or f"The system SHALL support {story_title.lower()}."

    proposal_lines = [
        "## Why",
        "",
        f"{story_title} is the current active story in the workflow and needs a real OpenSpec change so spec authoring is tracked in the standard artifact model.",
        "",
        "## What Changes",
        "",
        f"- Align the active workflow story `{active_story}` with a real OpenSpec change.",
        f"- Capture `{story_title}` as the next focused Concentric capability slice.",
    ]
    if story_scope:
        proposal_lines.append(f"- Carry the approved story scope into OpenSpec: {story_scope}")
    if covered_capabilities:
        proposal_lines.extend(
            [
                f"- Keep this story aligned to workflow mode `{capability_mode}`.",
                "- Treat the following capability categories as intentionally covered by this story:",
                *[f"  - {capability['name']}" for capability in covered_capabilities],
            ]
        )
    if deferred_capabilities:
        proposal_lines.extend(
            [
                "- Keep these remaining capability categories visible as deferred follow-up coverage:",
                *[f"  - {capability['name']} [{capability['status']}]" for capability in deferred_capabilities[:6]],
            ]
        )
    proposal_lines.extend(
        [
            "",
            "## Capabilities",
            "",
            "### New Capabilities",
            f"- `{capability_slug}`: {story_title}",
            "",
            "### Modified Capabilities",
            "- None.",
            "",
            "## Impact",
            "",
            f"- OpenSpec change: `openspec/changes/{change_slug}`",
            f"- Workflow story context: `{active_story}`",
            f"- Affects the sample test suite for `{story_title}`.",
            f"- Workflow mode: `{capability_mode}`",
            "",
            "<!-- Migrated workflow story context -->",
            story_enrichment or story_block,
            "",
            "<!-- Capability inventory context -->",
            read_text(workflow_dir / "capabilities.md").strip(),
            "",
        ]
    )
    proposal = "\n".join(proposal_lines).strip() + "\n"

    spec_lines = [
        "## ADDED Requirements",
        "",
        f"### Requirement: {story_title}",
        f"The system SHALL support {story_title.lower()} for the active workflow story.",
        "",
        "#### Scenario: Story scope is present",
        f"- **WHEN** a developer inspects the active story `{active_story}`",
        f"- **THEN** the project reflects this behavior: {story_scope or story_desc}",
        "",
    ]
    if covered_capabilities:
        spec_lines.extend(
            [
                "#### Scenario: Story capability coverage is explicit",
                "- **WHEN** the OpenSpec change is reviewed",
                f"- **THEN** it is clear that this story covers: {', '.join(str(cap['name']) for cap in covered_capabilities)}",
                "",
            ]
        )
    if deferred_capabilities:
        spec_lines.extend(
            [
                "#### Scenario: Deferred capability coverage remains visible",
                "- **WHEN** the story is accepted as a partial slice",
                f"- **THEN** the still-deferred capability categories remain explicit: {', '.join(str(cap['name']) for cap in deferred_capabilities[:6])}",
                "",
            ]
        )
    for criterion in story_acceptance[:6]:
        scenario_title = criterion[:80]
        spec_lines.extend(
            [
                f"#### Scenario: {scenario_title}",
                "- **WHEN** the story is implemented in the sample project",
                f"- **THEN** {criterion}",
                "",
            ]
        )
    spec_lines.extend(
        [
            "<!-- Migrated workflow spec context",
            workflow_spec or story_enrichment or story_block,
            "-->",
            "",
        ]
    )
    spec = "\n".join(spec_lines).strip() + "\n"

    task_lines = ["## 1. Story Tasks"]
    index = 1
    for bullet in story_test_expectations:
        task_lines.append(f"- [ ] 1.{index} {bullet}")
        index += 1
    for capability in covered_capabilities[:4]:
        task_lines.append(f"- [ ] 1.{index} Make the `{capability['name']}` capability explicit in this story's implementation and documentation.")
        index += 1
    if story_scope:
        task_lines.append(f"- [ ] 1.{index} Implement the approved story scope: {story_scope}")
        index += 1
    if deferred_capabilities:
        task_lines.append(
            f"- [ ] 1.{index} Leave clear follow-up context for deferred capabilities: {', '.join(str(cap['name']) for cap in deferred_capabilities[:4])}."
        )
        index += 1
    for risk in story_risks[:2]:
        task_lines.append(f"- [ ] 1.{index} Keep the slice small enough to avoid this risk: {risk}")
        index += 1
    if len(task_lines) == 1:
        task_lines.extend(
            [
                f"- [ ] 1.1 Review the enrichment for `{active_story}`",
                "- [ ] 1.2 Align tasks with the approved story scope",
            ]
        )
    tasks = "\n".join(task_lines).strip() + "\n"

    write_text(change_dir / "proposal.md", proposal)
    write_text(specs_dir / "spec.md", spec)
    write_text(change_dir / "tasks.md", tasks)

    links = read_text(links_path)
    openspec_line = f"- OpenSpec change: openspec/changes/{change_slug}"
    if "- OpenSpec change:" in links:
        links = re.sub(r"^- OpenSpec change:.*$", openspec_line, links, flags=re.MULTILINE)
    else:
        links = links.rstrip() + ("\n" if links.strip() else "") + openspec_line + "\n"
    write_text(links_path, links)
    update_initiative_index(root, args.slug)
    run(
        ["python3", str(Path(__file__).with_name("generate_workflow_diagram.py")), "--slug", args.slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )

    print(change_slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

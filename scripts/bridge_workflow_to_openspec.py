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

    active_items = parse_state_active_item(state_path)
    active_story = active_items.split(",", 1)[0].strip() if active_items else "Story 1"
    story_num_match = re.search(r"(\d+)", active_story)
    story_num = story_num_match.group(1) if story_num_match else "1"

    story_file_path = workflow_dir / f"story-{story_num}.md"
    story_spec_path = workflow_dir / "specs" / f"story-{story_num}-spec.md"
    story_header, story_block = parse_story_block(read_text(stories_path), active_story)
    story_title = story_header.split(":", 1)[1].strip() if ":" in story_header else active_story
    capability_slug = slugify(story_title)
    change_slug = args.change_slug or slugify(story_title)

    story_enrichment = read_text(story_file_path).strip()
    enrichment_sections = parse_markdown_sections(story_enrichment)
    story_scope = section_paragraph(enrichment_sections, "Scope")
    story_acceptance = section_bullets(enrichment_sections, "Acceptance Criteria")
    story_test_expectations = section_bullets(enrichment_sections, "Test Expectations")
    story_risks = section_bullets(enrichment_sections, "Risks")
    workflow_spec = read_text(story_spec_path).strip()

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
            "",
            "<!-- Migrated workflow story context -->",
            story_enrichment or story_block,
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
    if story_scope:
        task_lines.append(f"- [ ] 1.{index} Implement the approved story scope: {story_scope}")
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

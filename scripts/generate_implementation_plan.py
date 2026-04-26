#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def parse_state(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        values[key.strip()] = value.strip()
    return values


def parse_items(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def story_number(name: str) -> str | None:
    match = re.search(r"(\d+)", name)
    return match.group(1) if match else None


def parse_story_sections(path: Path) -> dict[str, list[str] | str]:
    sections: dict[str, list[str] | str] = {
        "Story": "",
        "Scope": "",
        "Acceptance Criteria": [],
        "Test Expectations": [],
        "Risks": [],
    }
    if not path.exists():
        return sections

    current: str | None = None
    current_list: list[str] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            current = line[3:].strip()
            current_list = None
            if current in {"Acceptance Criteria", "Test Expectations", "Risks"}:
                current_list = sections[current]  # type: ignore[assignment]
            continue
        if current in {"Story", "Scope"} and line and not line.startswith("- "):
            sections[current] = line.strip()
        elif current_list is not None and line.startswith("- "):
            current_list.append(line[2:].strip())
    return sections


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def parse_team_settings(root: Path, slug: str) -> dict[str, str]:
    base = parse_kv_list(root / ".workflow" / "team-config.md")
    override = parse_kv_list(root / ".workflow" / slug / "team-overrides.md")
    settings = dict(base)
    if override.get("Team size override", "").strip():
        settings["Team size"] = override["Team size override"].strip()
    if override.get("Parallel implementation slots override", "").strip():
        settings["Parallel implementation slots"] = override["Parallel implementation slots override"].strip()
    return settings


def parse_execution_board(path: Path) -> dict[str, str]:
    board = {"Active owner": "-", "Current handoff": "-", "Active story": "-"}
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        if line.startswith("- ") and ":" in line:
            key, _, value = line[2:].partition(":")
            if key.strip() in board:
                board[key.strip()] = value.strip()
    return board


def implementation_slots(settings: dict[str, str]) -> int:
    raw = settings.get("Parallel implementation slots", "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def distribute_items(items: list[str], slots: int) -> list[list[str]]:
    buckets: list[list[str]] = [[] for _ in range(slots)]
    for index, item in enumerate(items):
        buckets[index % slots].append(item)
    return buckets


def first_n(items: list[str], n: int) -> list[str]:
    return items[:n]


def remaining(items: list[str], n: int) -> list[str]:
    return items[n:]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an implementation plan for the active workflow story.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    workflow_dir = root / ".workflow" / args.slug
    state = parse_state(workflow_dir / "state.md")
    active_items = parse_items(state.get("Active items", ""))
    active_story = active_items[0] if active_items else "Current Story"
    number = story_number(active_story)
    story_path = workflow_dir / f"story-{number}.md" if number else workflow_dir / "story.md"
    story = parse_story_sections(story_path)

    title = str(story.get("Story") or active_story)
    scope = str(story.get("Scope") or f"Advance {active_story} with a small, reviewable slice.")
    acceptance = list(story.get("Acceptance Criteria") or [])
    tests = list(story.get("Test Expectations") or [])
    risks = list(story.get("Risks") or [])
    team = parse_team_settings(root, args.slug)
    board = parse_execution_board(workflow_dir / "execution-board.md")

    included = first_n(tests, 3) or first_n(acceptance, 3) or [scope]
    deferred = remaining(tests, 3) + remaining(acceptance, 3)
    slots = implementation_slots(team)
    workstreams = distribute_items(included or [scope], slots)

    lines = [
        "# Implementation Plan",
        "",
        "## Active Story",
        active_story,
        "",
        "## Story Title",
        title,
        "",
        "## Planning Goal",
        f"Choose the smallest reviewable slice that advances this scope: {scope}",
        "",
        "## Team Execution Context",
        f"- Team size: {team.get('Team size', '-') or '-'}",
        f"- Parallel implementation slots: {team.get('Parallel implementation slots', '-') or '-'}",
        f"- Active owner from execution board: {board.get('Active owner', '-') or '-'}",
        f"- Current handoff: {board.get('Current handoff', '-') or '-'}",
        "",
        "## Recommended First PR Slice",
        "Take the first focused, demonstrable subset of the story that can land safely without pulling in broader cleanup or later-story work.",
        "",
        "## Included In PR 1",
    ]
    for item in included:
        lines.append(f"- {item}")
    if not included:
        lines.append(f"- {scope}")

    lines.extend([
        "",
        "## Ownership And Handoffs",
        "- Product Owner: confirm scope boundaries and acceptance clarity before the slice is treated as implementation-ready.",
        "- Tech Lead: finalize the smallest viable slice and keep ownership boundaries coherent.",
    ])
    for index, bucket in enumerate(workstreams, start=1):
        label = f"Implementer {index}" if slots > 1 else "Implementer 1"
        if bucket:
            lines.append(f"- {label}: " + "; ".join(bucket))
    lines.extend(
        [
            "- Reviewer QA: review the implemented slice against design, workflow, and OpenSpec before release-planning.",
            "",
            "## Team Discussion Prompts",
            "- Product Owner challenge: is any included work drifting beyond the approved story scope?",
            "- Tech Lead challenge: can any included item be deferred without harming the first useful slice?",
            "- Reviewer QA challenge: which acceptance/test expectation is most likely to be missed if the slice is rushed?",
        ]
    )

    lines.extend([
        "",
        "## Deferred To Later Slice(s)",
    ])
    if deferred:
        for item in deferred:
            lines.append(f"- {item}")
    else:
        lines.append("- Additional scope beyond the first focused slice.")

    lines.extend([
        "",
        "## Risks To Watch",
    ])
    if risks:
        for risk in risks:
            lines.append(f"- {risk}")
    else:
        lines.append("- Keep the slice small enough to remain reviewable and aligned with the story scope.")

    lines.extend([
        "",
        "## Review Standard",
        "- The PR should make the selected slice obvious to a reviewer.",
        "- The diff should stay small enough to review in one sitting.",
        "- Existing behavior from earlier completed stories should remain intact unless the story explicitly changes it.",
        "",
    ])

    (workflow_dir / "implementation-plan.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def parse_markdown_table_rows(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        if parts and parts[0] not in {"Role", "Work Item", "Date"}:
            rows.append(parts)
    return rows


def parse_story_sections(path: Path) -> dict[str, list[str] | str]:
    sections: dict[str, list[str] | str] = {
        "Story": "",
        "Scope": "",
        "Acceptance Criteria": [],
        "Test Expectations": [],
        "Risks": [],
    }
    current: str | None = None
    current_list: list[str] | None = None
    for raw in read_text(path).splitlines():
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


def parse_active_story(state: dict[str, str]) -> str:
    active = state.get("Active items", "").split(",", 1)[0].strip()
    return active


def story_number(name: str) -> str | None:
    match = re.search(r"(\d+)", name)
    return match.group(1) if match else None


def parse_assignment_rows(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for parts in parse_markdown_table_rows(path):
        if len(parts) < 6:
            continue
        rows.append(
            {
                "Role": parts[0],
                "Slot": parts[1],
                "Responsibility Focus": parts[2],
                "Default Ownership": parts[3],
                "Allowed Write Paths": parts[4],
                "Status": parts[5],
            }
        )
    return rows


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
    values = {"Active story": "-", "Active owner": "-", "Current handoff": "-"}
    for line in read_text(path).splitlines():
        if line.startswith("- ") and ":" in line:
            key, _, value = line[2:].partition(":")
            if key.strip() in values:
                values[key.strip()] = value.strip()
    return values


def parse_review_roles(path: Path) -> list[str]:
    roles: list[str] = []
    for parts in parse_markdown_table_rows(path):
        if len(parts) >= 2 and parts[1] and parts[1] not in roles:
            roles.append(parts[1])
    return roles


def recommended_agent_type(role: str) -> str:
    if role.startswith("Implementer"):
        return "worker"
    if role == "Tech Lead":
        return "default"
    if role in {"Product Owner", "Reviewer QA"}:
        return "default"
    return "default"


def packet_body(
    role: str,
    row: dict[str, str],
    slug: str,
    state: dict[str, str],
    board: dict[str, str],
    story: dict[str, list[str] | str],
    team: dict[str, str],
    review_roles: list[str],
) -> str:
    acceptance = list(story.get("Acceptance Criteria") or [])[:5]
    tests = list(story.get("Test Expectations") or [])[:5]
    risks = list(story.get("Risks") or [])[:5]
    role_specific = {
        "Product Owner": [
            "Validate that execution stays within the approved story boundary.",
            "Challenge scope drift, acceptance ambiguity, and hidden follow-on work.",
            "Record findings in review-log.md and avoid editing canonical state.md directly.",
        ],
        "Tech Lead": [
            "Refine the smallest viable execution split for the active story.",
            "Keep implementer ownership disjoint and surface interface risks early.",
            "Update workflow notes only where your role is allowed; do not rewrite canonical state.md directly.",
        ],
        "Implementer 1": [
            "Own only the file scope implied by your assignment.",
            "Implement the smallest reviewable slice and include tests where appropriate.",
            "Do not revert or rewrite other lanes of work; coordinate through execution-board.md notes if needed.",
        ],
        "Implementer 2": [
            "Own only the second disjoint slice if it is active for this story.",
            "Implement the smallest reviewable slice and include tests where appropriate.",
            "Do not overlap Implementer 1 ownership; coordinate through execution-board.md notes if needed.",
        ],
        "Reviewer QA": [
            "Review current work against design, workflow intent, and acceptance criteria.",
            "Look for regressions, missing tests, and weak assumptions.",
            "Record findings in review-log.md and challenge the work when needed.",
        ],
    }.get(role, ["Follow the assignment and keep ownership bounded."])

    lines = [
        f"# {role} Dispatch Packet",
        "",
        f"- Workflow slug: {slug}",
        f"- Role: {role}",
        f"- Slot: {row['Slot']}",
        f"- Recommended agent type: {recommended_agent_type(role)}",
        f"- Active story: {state.get('Active items', '').split(',', 1)[0].strip() or '-'}",
        f"- Current stage: {state.get('Current stage', '-') or '-'}",
        f"- Active owner: {board.get('Active owner', '-') or '-'}",
        f"- Current handoff: {board.get('Current handoff', '-') or '-'}",
        f"- Team size: {team.get('Team size', '-') or '-'}",
        f"- Parallel implementation slots: {team.get('Parallel implementation slots', '-') or '-'}",
        f"- Responsibility focus: {row['Responsibility Focus']}",
        f"- Default ownership: {row['Default Ownership']}",
        f"- Allowed write paths: {row.get('Allowed Write Paths', '-') or '-'}",
        f"- Existing review roles: {', '.join(review_roles) if review_roles else '-'}",
        "",
        "## Shared Inputs",
        "- `.workflow/<slug>/design-slice.md`",
        "- `.workflow/<slug>/state.md`",
        "- `.workflow/<slug>/stories.md`",
        "- `.workflow/<slug>/execution-board.md`",
        "- `.workflow/<slug>/review-log.md`",
        "- `.workflow/<slug>/team-minutes.md`",
        "- `.workflow/<slug>/links.md`",
        "- `.workflow/<slug>/workflow-contract.md`",
        "",
        "## Story Context",
        str(story.get("Story") or state.get("Active items", "").split(",", 1)[0].strip() or "-"),
        "",
        "## Scope",
        str(story.get("Scope") or "-"),
        "",
        "## Role Mission",
    ]
    for item in role_specific:
        lines.append(f"- {item}")
    lines.extend(["", "## Acceptance Focus"])
    if acceptance:
        for item in acceptance:
            lines.append(f"- {item}")
    else:
        lines.append("- No explicit acceptance criteria recorded yet.")
    lines.extend(["", "## Test Focus"])
    if tests:
        for item in tests:
            lines.append(f"- {item}")
    else:
        lines.append("- No explicit test expectations recorded yet.")
    lines.extend(["", "## Risks"])
    if risks:
        for item in risks:
            lines.append(f"- {item}")
    else:
        lines.append("- Keep the slice small and aligned with the approved story.")
    lines.extend(
        [
            "",
            "## Execution Rules",
            "- You are not alone in the codebase; accommodate other role lanes instead of reverting them.",
            "- Keep changes within your role ownership and the active story boundary.",
            f"- Stay inside these allowed write paths: {row.get('Allowed Write Paths', '-') or '-'}",
            "- Do not edit canonical `state.md` directly.",
            "- Summarize important discussions, decisions, and handoffs in `team-minutes.md`.",
            "- Surface findings through `review-log.md` or `execution-board.md` notes as appropriate.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate team dispatch artifacts for delegated workflow execution.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wf = root / ".workflow" / args.slug
    state = parse_kv_list(wf / "state.md")
    active_story = parse_active_story(state)
    story_path = wf / "story.md"
    number = story_number(active_story)
    if number:
        numbered = wf / f"story-{number}.md"
        if numbered.exists():
            story_path = numbered
    story = parse_story_sections(story_path)
    team = parse_team_settings(root, args.slug)
    board = parse_execution_board(wf / "execution-board.md")
    review_roles = parse_review_roles(wf / "review-log.md")
    assignments = parse_assignment_rows(wf / "agent-assignments.md")

    dispatch_dir = wf / "dispatch"
    dispatch_dir.mkdir(parents=True, exist_ok=True)

    summary_lines = [
        "# Team Dispatch",
        "",
        f"- Workflow slug: {args.slug}",
        f"- Current stage: {state.get('Current stage', '-') or '-'}",
        f"- Active story: {active_story or '-'}",
        f"- Runtime mode target: delegated-agent-team",
        f"- Team size: {team.get('Team size', '-') or '-'}",
        f"- Parallel implementation slots: {team.get('Parallel implementation slots', '-') or '-'}",
        f"- Existing review roles: {', '.join(review_roles) if review_roles else '-'}",
        "",
        "## Dispatch Order",
        "",
        "1. Product Owner verifies story boundary and acceptance clarity in parallel with Tech Lead planning.",
        "2. Tech Lead finalizes disjoint work slices and handoffs.",
        "3. Implementer lanes execute in parallel only when their ownership is disjoint.",
        "4. Reviewer QA reviews completed slices and records findings.",
        "5. The orchestrator syncs review evidence and advances workflow state when gates are satisfied.",
        "",
        "## Packet Index",
    ]
    for row in assignments:
        role = row["Role"]
        packet_name = f"{row['Slot']}.md"
        summary_lines.append(f"- {role}: `dispatch/{packet_name}` ({recommended_agent_type(role)})")
        (dispatch_dir / packet_name).write_text(
            packet_body(role, row, args.slug, state, board, story, team, review_roles),
            encoding="utf-8",
        )
    summary_lines.append("")
    (wf / "team-dispatch.md").write_text("\n".join(summary_lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from workflow_debt import format_debt_summary, has_blocking_debt
from workflow_execution_paths import enrich_node_with_execution_path
from workflow_memory import memory_bullets, memory_for_story
from workflow_worktrees import role_lane_id, worktree_records_by_lane


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


def parse_dag_node(path: Path, active_story: str) -> dict[str, object]:
    if not path.exists() or not active_story:
        return {}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    match = re.search(r"(\d+)", active_story)
    expected_id = f"story-{match.group(1)}" if match else ""
    for node in payload.get("nodes", []):
        if not isinstance(node, dict):
            continue
        if node.get("story") == active_story or node.get("id") == expected_id:
            return node
    return {}


def parse_dag_payload(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def dag_validation(payload: dict[str, object]) -> dict[str, object]:
    validation = payload.get("validation", {})
    return validation if isinstance(validation, dict) else {}


def dag_lane_dependencies(payload: dict[str, object]) -> dict[str, object]:
    dependencies = payload.get("lane_dependencies", {})
    return dependencies if isinstance(dependencies, dict) else {}


def list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def debt_records(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def debt_bullets(records: list[dict[str, object]]) -> list[str]:
    bullets: list[str] = []
    for record in records:
        relation = str(record.get("relation") or "direct")
        severity = str(record.get("severity") or "medium")
        debt_type = str(record.get("debt_type") or "technical debt")
        source = str(record.get("source_story") or "-")
        summary = str(record.get("summary") or "").strip()
        text = f"{severity} {relation} {debt_type} from {source}"
        if summary:
            text += f": {summary}"
        bullets.append(text)
    return bullets


def execution_path_payload(dag_node: dict[str, object]) -> dict[str, object]:
    path = dag_node.get("execution_path", {})
    return path if isinstance(path, dict) else {}


def planner_metadata_payload(dag_node: dict[str, object]) -> dict[str, object]:
    metadata = dag_node.get("planner_metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def recommended_agent_type(role: str) -> str:
    if role.startswith("Implementer"):
        return "worker"
    if role == "Tech Lead":
        return "default"
    if role in {"Product Owner", "Reviewer QA"}:
        return "default"
    return "default"


def packet_body(
    root: Path,
    role: str,
    row: dict[str, str],
    slug: str,
    state: dict[str, str],
    board: dict[str, str],
    story: dict[str, list[str] | str],
    team: dict[str, str],
    review_roles: list[str],
    dag_node: dict[str, object],
    dag_payload: dict[str, object],
    worktree: dict[str, object],
) -> str:
    acceptance = list(story.get("Acceptance Criteria") or [])[:5]
    tests = list(story.get("Test Expectations") or [])[:5]
    risks = list(story.get("Risks") or [])[:5]
    role_specific = {
        "Product Owner": [
            "Validate that execution stays within the approved story boundary.",
            "Challenge scope drift, acceptance ambiguity, and hidden follow-on work.",
            "Record an independent product verdict before adopting other role conclusions.",
            "Record findings in review-log.md and avoid editing canonical state.md directly.",
        ],
        "Tech Lead": [
            "Refine the smallest viable execution split for the active story.",
            "Keep implementer ownership disjoint and surface interface risks early.",
            "Challenge architecture, dependency, sequencing, and ownership assumptions.",
            "Update workflow notes only where your role is allowed; do not rewrite canonical state.md directly.",
        ],
        "Implementer 1": [
            "Own only the file scope implied by your assignment.",
            "Implement the smallest reviewable slice and include tests where appropriate.",
            "Challenge feasibility and maintainability assumptions before coding through them.",
            "Do not revert or rewrite other lanes of work; coordinate through execution-board.md notes if needed.",
        ],
        "Implementer 2": [
            "Own only the second disjoint slice if it is active for this story.",
            "Implement the smallest reviewable slice and include tests where appropriate.",
            "Challenge feasibility and maintainability assumptions before coding through them.",
            "Do not overlap Implementer 1 ownership; coordinate through execution-board.md notes if needed.",
        ],
        "Reviewer QA": [
            "Review current work against design, workflow intent, and acceptance criteria.",
            "Look for regressions, missing tests, and weak assumptions.",
            "Run a bounded red-team pass for the most likely product, test, implementation, security, or rollout failure.",
            "Record findings in review-log.md and challenge the work when needed.",
        ],
    }.get(role, ["Follow the assignment and keep ownership bounded."])
    if dag_node.get("needs_deeper_qa") and role in {"Tech Lead", "Reviewer QA"}:
        role_specific.append("Treat this as a DAG-flagged high-risk story; deepen review before approving.")
    validation = dag_validation(dag_payload)
    lane_dependencies = dag_lane_dependencies(dag_payload)
    technical_debt = debt_records(dag_node.get("technical_debt"))
    active_story = state.get("Active items", "").split(",", 1)[0].strip() or str(story.get("Story") or "")
    memory = memory_for_story(root, slug, active_story)
    if has_blocking_debt(technical_debt) and role in {"Tech Lead", "Reviewer QA", "Product Owner"}:
        role_specific.append("Open high/critical technical debt applies to this story; require resolution or explicit acceptance before release planning.")
    execution_path = execution_path_payload(dag_node)
    planner_metadata = planner_metadata_payload(dag_node)
    required_roles = list_value(execution_path.get("required_roles"))
    optional_roles = list_value(execution_path.get("optional_roles"))
    if required_roles and role not in required_roles:
        role_specific.append("This role is optional for the selected execution path; keep involvement bounded unless a gate or blocker needs your review.")
    if str(execution_path.get("path") or "").strip().lower() == "flagged":
        if role in {"Tech Lead", "Reviewer QA"}:
            role_specific.append("This is on the flagged path; record independent QA/review evidence before the orchestrator synthesizes a decision.")
        elif role.startswith("Implementer"):
            role_specific.append("This is on the flagged path; expect QA and reviewer findings to feed a synthesis/fix decision before approval.")
    result_path = f".workflow/{slug}/agent-results/{row['Slot']}.md"

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
        f"- Worktree path: {worktree.get('path', '-') or '-'}",
        f"- Worktree branch: {worktree.get('branch', '-') or '-'}",
        f"- Worktree status: {worktree.get('status', '-') or '-'}",
        f"- Result envelope path: {result_path}",
        f"- Existing review roles: {', '.join(review_roles) if review_roles else '-'}",
        f"- DAG level: {dag_node.get('level', '-') or '-'}",
        f"- DAG status: {dag_node.get('status', '-') or '-'}",
        f"- DAG validation: {validation.get('status', '-') or '-'}",
        f"- DAG risk: {dag_node.get('risk', '-') or '-'}",
        f"- Needs deeper QA: {'yes' if dag_node.get('needs_deeper_qa') else 'no'}",
        f"- Execution path: {execution_path.get('path', '-') or '-'}",
        f"- Required in path: {'yes' if not required_roles or role in required_roles else 'no'}",
        f"- Required roles: {', '.join(required_roles) or '-'}",
        f"- Optional roles: {', '.join(optional_roles) or '-'}",
        f"- Review flow: {execution_path.get('review_flow', '-') or '-'}",
        f"- Estimated scope: {planner_metadata.get('estimated_scope', '-') or '-'}",
        f"- Touches interfaces: {'yes' if planner_metadata.get('touches_interfaces') else 'no'}",
        f"- Testing guidance: {planner_metadata.get('testing_guidance', '-') or '-'}",
        f"- Risk rationale: {planner_metadata.get('risk_rationale', '-') or '-'}",
        f"- Depends on: {', '.join(str(item) for item in dag_node.get('depends_on', []) or []) or '-'}",
        f"- Downstream dependents: {', '.join(str(item) for item in dag_node.get('dependents', []) or []) or '-'}",
        f"- Lane depends on: {', '.join(list_value(lane_dependencies.get('depends_on'))) or '-'}",
        f"- Lane blocked by: {', '.join(list_value(lane_dependencies.get('blocked_by'))) or '-'}",
        f"- Technical debt: {format_debt_summary(technical_debt)}",
        "",
        "## Shared Inputs",
        "- `.workflow/<slug>/design-slice.md`",
        "- `.workflow/<slug>/state.md`",
        "- `.workflow/<slug>/stories.md`",
        "- `.workflow/<slug>/dag.json`",
        "- `.workflow/<slug>/dag.md`",
        "- `.workflow/<slug>/records/memory.jsonl`",
        "- `.workflow/<slug>/memory.md`",
        "- `.workflow/<slug>/records/debt.jsonl`",
        "- `.workflow/<slug>/debt.md`",
        "- `.workflow/<slug>/execution-board.md`",
        "- `.workflow/<slug>/review-log.md`",
        "- `.workflow/<slug>/role-reviews.md`",
        "- `.workflow/<slug>/conflicts.md`",
        "- `.workflow/<slug>/assumptions.md`",
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
    lines.extend(["", "## Technical Debt Context"])
    if technical_debt:
        lines.extend(f"- {item}" for item in debt_bullets(technical_debt))
    else:
        lines.append("- No open or accepted technical debt currently applies to this story.")
    lines.extend(["", "## Shared Learning Memory"])
    memory_lines = memory_bullets(memory)
    if memory_lines:
        lines.extend(f"- {item}" for item in memory_lines)
    else:
        lines.append("- No shared learning memory currently applies to this story.")
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
            "- Use the assigned worktree path as your execution cwd when one is listed.",
            "- Keep changes within your role ownership and the active story boundary.",
            f"- Stay inside these allowed write paths: {row.get('Allowed Write Paths', '-') or '-'}",
            "- Do not edit canonical `state.md` directly.",
            "- Record independent review evidence before reconciliation when you are reviewing an artifact.",
            "- Mark unsupported claims as assumptions and cite evidence for product or technical claims.",
            "- Put unresolved disagreement in conflict entries instead of burying it in prose.",
            "- Summarize important discussions, decisions, and handoffs in `team-minutes.md`.",
            f"- When you finish or hand off, write the final report to `{result_path}` and return the same content in chat.",
            "- If you run inside an assigned worktree, leave result envelopes under `.workflow/<slug>/agent-results/` uncommitted; the orchestrator can ingest them with `team-sync-all`.",
            "- Keep the final report schema exact so the orchestrator can ingest it without guessing.",
            "- Surface review verdicts through `role-reviews.md`, disagreements through `conflicts.md`, assumptions through `assumptions.md`, and signoff findings through `review-log.md` as appropriate.",
            "",
            "## Final Report Template",
            "```text",
            "Schema: agent-result-v1",
            f"Role: {role}",
            "Status: done",
            "Verdict: approve",
            "Summary: <one concise summary of what changed or what was verified>",
            "Files changed:",
            "- <path>",
            "Validation run:",
            "- <command and result>",
            "Missing requirements:",
            "- none",
            "Incorrect assumptions:",
            "- none",
            "Risks:",
            "- none",
            "Questions:",
            "- none",
            "Suggested changes:",
            "- none",
            "Evidence:",
            "- <file, artifact, test, or user statement>",
            "Conflict entries:",
            "- none",
            "Assumption updates:",
            "- none",
            "Red-team notes:",
            "- none",
            "Findings:",
            "- none",
            "Debt entries:",
            "- none",
            "Memory entries:",
            "- none",
            "Model:",
            "Input tokens:",
            "Output tokens:",
            "Cost USD:",
            "Elapsed seconds:",
            "Invocation ID:",
            "Run ID:",
            "Retry count:",
            "Follow-up: <next handoff or approval request>",
            "```",
            "",
            "Notes for the report:",
            "- Use one of: `planned`, `in-progress`, `in-review`, `done`, `blocked`, `optional`.",
            "- Use one verdict: `approve`, `approve-with-changes`, or `block`.",
            "- If you did not change files, write `Files changed:` then `- none`.",
            "- Keep each review section present. Use `- none` when there is no content.",
            "- For conflict entries, prefix severity when useful, for example `- high: raw SQL in MVP expands security scope`.",
            "- For assumption updates, include the assumption and validation step when known.",
            "- If you found issues, put each finding on its own bullet. Prefix severity when helpful, for example `- high: task contract is still missing`.",
            "- If you are a reviewer or product owner and no serious issues remain, write `Findings:` then `- none`.",
            "- Fill optional accounting fields only when you know them; leave cost blank when pricing is unknown rather than writing zero.",
            "",
            "## Orchestrator Sync",
            "After this report returns, the orchestrator should run:",
            "```text",
            "wrkflw:team-sync-all",
            "```",
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
    dag_payload = parse_dag_payload(wf / "dag.json")
    dag_node = enrich_node_with_execution_path(parse_dag_node(wf / "dag.json", active_story))
    validation = dag_validation(dag_payload)
    worktrees = worktree_records_by_lane(root, args.slug)
    execution_path = execution_path_payload(dag_node)
    planner_metadata = planner_metadata_payload(dag_node)

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
        f"- DAG validation: {validation.get('status', '-') or '-'}",
        f"- DAG status: {dag_node.get('status', '-') or '-'}",
        f"- DAG risk: {dag_node.get('risk', '-') or '-'}",
        f"- Needs deeper QA: {'yes' if dag_node.get('needs_deeper_qa') else 'no'}",
        f"- Execution path: {execution_path.get('path', '-') or '-'}",
        f"- Required roles: {', '.join(list_value(execution_path.get('required_roles'))) or '-'}",
        f"- Review flow: {execution_path.get('review_flow', '-') or '-'}",
        f"- Estimated scope: {planner_metadata.get('estimated_scope', '-') or '-'}",
        f"- Risk rationale: {planner_metadata.get('risk_rationale', '-') or '-'}",
        f"- Technical debt: {format_debt_summary(debt_records(dag_node.get('technical_debt')))}",
        "",
        "## Dispatch Order",
        "",
        "1. Product Owner and Tech Lead review the active artifact independently before reconciliation.",
        "2. Tech Lead finalizes disjoint work slices and handoffs after review conflicts are visible.",
        "3. Implementer lanes execute in parallel only when their ownership is disjoint.",
        "4. Reviewer QA reviews completed slices, runs a bounded red-team pass, and records findings.",
        "5. The orchestrator syncs role reviews, conflicts, assumptions, review evidence, and advances workflow state when gates are satisfied.",
        "",
        "## Packet Index",
    ]
    for row in assignments:
        role = row["Role"]
        packet_name = f"{row['Slot']}.md"
        lane_id = role_lane_id(active_story, row["Slot"])
        worktree = worktrees.get(lane_id, {})
        worktree_text = f", worktree `{worktree.get('path')}`" if worktree.get("path") else ""
        summary_lines.append(f"- {role}: `dispatch/{packet_name}` ({recommended_agent_type(role)}{worktree_text})")
        (dispatch_dir / packet_name).write_text(
            packet_body(root, role, row, args.slug, state, board, story, team, review_roles, dag_node, dag_payload, worktree),
            encoding="utf-8",
        )
    summary_lines.append("")
    (wf / "team-dispatch.md").write_text("\n".join(summary_lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

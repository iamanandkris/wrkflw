#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from workflow_accounting import format_accounting_summary, load_invocation_records
from workflow_debt import format_debt_summary, has_blocking_debt
from workflow_execution_paths import enrich_node_with_execution_path
from workflow_memory import memory_bullets, memory_for_story


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


def parse_runtime_contract(path: Path) -> dict[str, str]:
    values = parse_kv_list(path)
    return {
        "Runtime mode": values.get("Runtime mode", "-").strip() or "-",
        "Delegated execution ready": values.get("Delegated execution ready", "-").strip() or "-",
    }


def parse_dag(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def node_story_number(node: dict[str, object]) -> int:
    match = re.search(r"(\d+)", str(node.get("id") or node.get("story") or ""))
    return int(match.group(1)) if match else 999999


def dag_nodes(dag: dict[str, object]) -> list[dict[str, object]]:
    nodes = dag.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    return [node for node in nodes if isinstance(node, dict)]


def find_dag_node(dag: dict[str, object], story: str) -> dict[str, object]:
    number = story_number(story)
    expected_id = f"story-{number}" if number else ""
    for node in dag_nodes(dag):
        if node.get("story") == story or node.get("id") == expected_id:
            return node
    return {}


def first_ready_dag_node(dag: dict[str, object]) -> dict[str, object]:
    ready = [
        node for node in dag_nodes(dag)
        if str(node.get("status", "")).strip().lower() in {"active", "ready"}
    ]
    return sorted(ready, key=node_story_number)[0] if ready else {}


def list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def node_label(node: dict[str, object]) -> str:
    return str(node.get("label") or node.get("story") or node.get("id") or "-")


def dag_validation(dag: dict[str, object]) -> dict[str, object]:
    validation = dag.get("validation", {})
    return validation if isinstance(validation, dict) else {}


def dag_lane_dependencies(dag: dict[str, object]) -> dict[str, object]:
    dependencies = dag.get("lane_dependencies", {})
    return dependencies if isinstance(dependencies, dict) else {}


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
        owner = str(record.get("owner") or "").strip()
        suffix = f" Owner: {owner}." if owner else ""
        text = f"{severity} {relation} {debt_type} from {source}"
        if summary:
            text += f": {summary}"
        bullets.append(text + suffix)
    return bullets


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
    dag = parse_dag(workflow_dir / "dag.json")
    active_items = parse_items(state.get("Active items", ""))
    active_story = active_items[0] if active_items else "Current Story"
    dag_node = find_dag_node(dag, active_story)
    if active_story == "Current Story":
        dag_node = first_ready_dag_node(dag)
        if dag_node:
            active_story = str(dag_node.get("story") or active_story)
    dag_node = enrich_node_with_execution_path(dag_node)
    number = story_number(active_story)
    story_path = workflow_dir / f"story-{number}.md" if number else workflow_dir / "story.md"
    story = parse_story_sections(story_path)
    dag_ready_nodes = [
        node for node in dag_nodes(dag)
        if str(node.get("status", "")).strip().lower() in {"active", "ready"}
    ]

    title = str(story.get("Story") or dag_node.get("title") or active_story)
    scope = str(story.get("Scope") or f"Advance {active_story} with a small, reviewable slice.")
    acceptance = list(story.get("Acceptance Criteria") or []) or list_value(dag_node.get("acceptance"))
    tests = list(story.get("Test Expectations") or []) or list_value(dag_node.get("validation"))
    risks = list(story.get("Risks") or [])
    if dag_node.get("risk") == "high":
        risks = risks or [str(dag_node.get("review_focus") or "DAG marks this story as high risk.")]
    technical_debt = debt_records(dag_node.get("technical_debt"))
    memory = memory_for_story(root, args.slug, active_story)
    accounting_records = load_invocation_records(root, args.slug)
    story_accounting_summary = format_accounting_summary(accounting_records, active_story)
    if has_blocking_debt(technical_debt):
        risks.append("Open high/critical technical debt applies to this story; resolve or explicitly accept it before release planning.")
    team = parse_team_settings(root, args.slug)
    board = parse_execution_board(workflow_dir / "execution-board.md")
    runtime = parse_runtime_contract(workflow_dir / "runtime-contract.md")
    validation = dag_validation(dag)
    lane_dependencies = dag_lane_dependencies(dag)
    execution_path = dag_node.get("execution_path", {})
    execution_path = execution_path if isinstance(execution_path, dict) else {}
    planner_metadata = dag_node.get("planner_metadata", {})
    planner_metadata = planner_metadata if isinstance(planner_metadata, dict) else {}

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
        f"- Runtime mode: {runtime.get('Runtime mode', '-') or '-'}",
        f"- Delegated execution ready: {runtime.get('Delegated execution ready', '-') or '-'}",
        f"- Active owner from execution board: {board.get('Active owner', '-') or '-'}",
        f"- Current handoff: {board.get('Current handoff', '-') or '-'}",
        "",
        "## DAG Execution Context",
        f"- DAG node: {node_label(dag_node)}",
        f"- DAG level: {dag_node.get('level', '-') or '-'}",
        f"- DAG status: {dag_node.get('status', '-') or '-'}",
        f"- DAG validation: {validation.get('status', '-') or '-'}",
        f"- DAG risk: {dag_node.get('risk', '-') or '-'}",
        f"- Needs deeper QA: {'yes' if dag_node.get('needs_deeper_qa') else 'no'}",
        f"- Execution path: {execution_path.get('path', '-') or '-'}",
        f"- Required roles: {', '.join(list_value(execution_path.get('required_roles'))) or '-'}",
        f"- Review flow: {execution_path.get('review_flow', '-') or '-'}",
        f"- Estimated scope: {planner_metadata.get('estimated_scope', '-') or '-'}",
        f"- Touches interfaces: {'yes' if planner_metadata.get('touches_interfaces') else 'no'}",
        f"- Testing guidance: {planner_metadata.get('testing_guidance', '-') or '-'}",
        f"- Risk rationale: {planner_metadata.get('risk_rationale', '-') or '-'}",
        f"- Depends on: {', '.join(list_value(dag_node.get('depends_on'))) or '-'}",
        f"- Downstream dependents: {', '.join(list_value(dag_node.get('dependents'))) or '-'}",
        f"- Lane depends on: {', '.join(list_value(lane_dependencies.get('depends_on'))) or '-'}",
        f"- Lane blocked by: {', '.join(list_value(lane_dependencies.get('blocked_by'))) or '-'}",
        f"- Ready now: {', '.join(node_label(node) for node in dag_ready_nodes) if dag_ready_nodes else '-'}",
        f"- Technical debt: {format_debt_summary(technical_debt)}",
        f"- Invocation accounting: {story_accounting_summary}",
        "",
        "## Technical Debt Context",
    ]
    if technical_debt:
        lines.extend(f"- {item}" for item in debt_bullets(technical_debt))
    else:
        lines.append("- No open or accepted technical debt currently applies to this story.")
    lines.extend([
        "",
        "## Shared Learning Memory",
    ])
    memory_lines = memory_bullets(memory)
    if memory_lines:
        lines.extend(f"- {item}" for item in memory_lines)
    else:
        lines.append("- No shared learning memory currently applies to this story.")
    lines.extend([
        "",
        "## Invocation Accounting",
        f"- Active story: {story_accounting_summary}",
        f"- Workflow total: {format_accounting_summary(accounting_records)}",
        "- Zero-dollar workflow-command entries are bookkeeping unless a role explicitly records model tokens or estimated cost.",
    ])
    lines.extend([
        "",
        "## Recommended First PR Slice",
        "Take the first focused, demonstrable subset of the story that can land safely without pulling in broader cleanup or later-story work.",
        "",
        "## Included In PR 1",
    ])
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

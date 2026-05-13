#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from workflow_debt import format_debt_summary, has_blocking_debt
from workflow_execution_paths import enrich_node_with_execution_path
from workflow_memory import memory_bullets, memory_for_story
from workflow_worktrees import worktree_records_by_lane


READY_STATUSES = {"active", "ready"}


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


def parse_dag(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def dag_nodes(payload: dict[str, object]) -> list[dict[str, object]]:
    nodes = payload.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    return [node for node in nodes if isinstance(node, dict)]


def list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def story_sort_key(node: dict[str, object]) -> tuple[int, int]:
    level = node.get("level")
    try:
        level_value = int(level) if level is not None else 999999
    except (TypeError, ValueError):
        level_value = 999999
    match = re.search(r"(\d+)", str(node.get("id") or node.get("story") or ""))
    story_value = int(match.group(1)) if match else 999999
    return level_value, story_value


def story_number(node: dict[str, object]) -> str:
    match = re.search(r"(\d+)", str(node.get("id") or node.get("story") or ""))
    return match.group(1) if match else ""


def story_file(root: Path, slug: str, node: dict[str, object]) -> Path:
    number = story_number(node)
    return root / ".workflow" / slug / f"story-{number}.md" if number else root / ".workflow" / slug / "story.md"


def section_bullets(path: Path, section_names: set[str]) -> list[str]:
    bullets: list[str] = []
    active = False
    for raw_line in read_text(path).splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("## "):
            active = stripped.lstrip("#").strip().lower() in section_names
            continue
        if active and stripped.startswith("- "):
            item = stripped[2:].strip()
            if item:
                bullets.append(item)
    return bullets


def story_sections(path: Path) -> dict[str, list[str] | str]:
    return {
        "scope": "\n".join(section_bullets(path, {"scope"})),
        "acceptance": section_bullets(path, {"acceptance criteria"}),
        "validation": section_bullets(path, {"test expectations", "validation"}),
        "risks": section_bullets(path, {"risks"}),
    }


def normalize_path(path: str) -> str:
    return path.strip().lstrip("./").rstrip("/")


def paths_overlap(left: str, right: str) -> bool:
    a = normalize_path(left)
    b = normalize_path(right)
    if not a or not b:
        return False
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


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


def execution_path_payload(node: dict[str, object]) -> dict[str, object]:
    path = node.get("execution_path", {})
    return path if isinstance(path, dict) else {}


def planner_metadata_payload(node: dict[str, object]) -> dict[str, object]:
    metadata = node.get("planner_metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def ready_nodes(payload: dict[str, object]) -> list[dict[str, object]]:
    ready = []
    for node in dag_nodes(payload):
        status = str(node.get("status", "")).strip().lower()
        if status not in READY_STATUSES:
            continue
        if list_value(node.get("blocked_by_lanes")) or list_value(node.get("blocked_by_stories")):
            continue
        ready.append(node)
    if not ready:
        return []
    min_level = min(story_sort_key(node)[0] for node in ready)
    return sorted([node for node in ready if story_sort_key(node)[0] == min_level], key=story_sort_key)


def validation_blockers(payload: dict[str, object]) -> list[str]:
    validation = payload.get("validation", {})
    if not isinstance(validation, dict):
        return ["DAG validation metadata is missing."]
    status = str(validation.get("status", "")).strip().lower()
    blockers = list_value(validation.get("errors"))
    lane_dependencies = payload.get("lane_dependencies", {})
    if isinstance(lane_dependencies, dict):
        blockers.extend(f"incomplete lane dependency: {item}" for item in list_value(lane_dependencies.get("blocked_by")))
    if status in {"invalid", "blocked"} and not blockers:
        blockers.append(f"DAG validation status is {status}.")
    return blockers


def scope_blockers(nodes: list[dict[str, object]]) -> list[str]:
    blockers: list[str] = []
    for node in nodes:
        if not list_value(node.get("allowed_paths")):
            blockers.append(f"{node.get('story') or node.get('id')} is missing allowed write paths.")
    for index, left in enumerate(nodes):
        for right in nodes[index + 1:]:
            for left_path in list_value(left.get("allowed_paths")):
                for right_path in list_value(right.get("allowed_paths")):
                    if paths_overlap(left_path, right_path):
                        blockers.append(
                            f"{left.get('story') or left.get('id')} path `{left_path}` overlaps "
                            f"{right.get('story') or right.get('id')} path `{right_path}`."
                        )
    return blockers


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
    if isinstance(existing, dict) and stable_payload(existing) == stable_payload(payload):
        generated_at = str(existing.get("generated_at", "")).strip()
        if generated_at:
            return generated_at
    return fallback


def write_text_if_changed(path: Path, content: str) -> None:
    if path.exists() and read_text(path) == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def clear_existing_packets(output_root: Path) -> None:
    if not output_root.exists():
        return
    for packet in output_root.glob("*/implementer.md"):
        packet.unlink()
        try:
            packet.parent.rmdir()
        except OSError:
            pass
    for entry in output_root.iterdir():
        if entry.is_dir() and not any(entry.iterdir()):
            shutil.rmtree(entry)


def render_story_packet(root: Path, slug: str, node: dict[str, object], story: dict[str, list[str] | str], output_dir: str) -> str:
    acceptance = story.get("acceptance", [])
    validation = story.get("validation", [])
    risks = story.get("risks", [])
    technical_debt = debt_records(node.get("technical_debt"))
    memory = memory_for_story(root, slug, str(node.get("story") or ""))
    worktree = node.get("worktree", {})
    worktree = worktree if isinstance(worktree, dict) else {}
    execution_path = execution_path_payload(node)
    planner_metadata = planner_metadata_payload(node)
    lines = [
        f"# {node.get('label') or node.get('story') or node.get('id')} Parallel Dispatch",
        "",
        f"- Workflow slug: {slug}",
        f"- DAG node: {node.get('id', '-') or '-'}",
        f"- Story: {node.get('story', '-') or '-'}",
        f"- DAG level: {node.get('level', '-') or '-'}",
        f"- DAG risk: {node.get('risk', '-') or '-'}",
        f"- Needs deeper QA: {'yes' if node.get('needs_deeper_qa') else 'no'}",
        f"- Execution path: {execution_path.get('path', '-') or '-'}",
        f"- Required roles: {', '.join(list_value(execution_path.get('required_roles'))) or '-'}",
        f"- Review flow: {execution_path.get('review_flow', '-') or '-'}",
        f"- Estimated scope: {planner_metadata.get('estimated_scope', '-') or '-'}",
        f"- Touches interfaces: {'yes' if planner_metadata.get('touches_interfaces') else 'no'}",
        f"- Testing guidance: {planner_metadata.get('testing_guidance', '-') or '-'}",
        f"- Risk rationale: {planner_metadata.get('risk_rationale', '-') or '-'}",
        f"- Allowed write paths: {', '.join(list_value(node.get('allowed_paths'))) or '-'}",
        f"- Worktree path: {worktree.get('path', '-') or '-'}",
        f"- Worktree branch: {worktree.get('branch', '-') or '-'}",
        f"- Worktree status: {worktree.get('status', '-') or '-'}",
        f"- Technical debt: {format_debt_summary(technical_debt)}",
        f"- Result envelope path: .workflow/{slug}/agent-results/{node.get('id', 'story')}.md",
        "",
        "## Scope",
        str(story.get("scope") or node.get("title") or "-"),
        "",
        "## Acceptance Focus",
    ]
    lines.extend(f"- {item}" for item in acceptance if item)
    if not acceptance:
        lines.append("- No explicit acceptance criteria recorded yet.")
    lines.extend(["", "## Test Focus"])
    lines.extend(f"- {item}" for item in validation if item)
    if not validation:
        lines.append("- No explicit test expectations recorded yet.")
    lines.extend(["", "## Technical Debt Context"])
    if technical_debt:
        lines.extend(f"- {item}" for item in debt_bullets(technical_debt))
        if has_blocking_debt(technical_debt):
            lines.append("- Resolve or explicitly accept open high/critical debt before release planning.")
    else:
        lines.append("- No open or accepted technical debt currently applies to this story.")
    lines.extend(["", "## Shared Learning Memory"])
    memory_lines = memory_bullets(memory)
    if memory_lines:
        lines.extend(f"- {item}" for item in memory_lines)
    else:
        lines.append("- No shared learning memory currently applies to this story.")
    lines.extend(["", "## Risks"])
    lines.extend(f"- {item}" for item in risks if item)
    if not risks:
        lines.append("- Keep this story inside its declared write scope.")
    lines.extend(
        [
            "",
            "## Execution Rules",
            "- You are not alone in the codebase; this is a parallel level dispatch.",
            "- Use the assigned worktree path as your execution cwd when one is listed.",
            "- Stay inside this story's allowed write paths.",
            "- Follow the execution path above; flagged stories require independent QA/review evidence before approval.",
            "- Do not edit canonical `state.md` directly.",
            "- Return a structured final report for `wrkflw:team-sync-all`.",
            "- After all parallel lanes are synced, the orchestrator must run `wrkflw:merge-gate` before review approval.",
            "- After merge-gate passes and committed lane changes exist, the orchestrator must run `wrkflw:merge-apply \"confirm: merge-apply\"` before integration-gate.",
            "- After merge-apply, the orchestrator must run `wrkflw:integration-gate` before review approval.",
            "",
            "## Final Report Template",
            "```text",
            "Schema: agent-result-v1",
            "Role: Implementer 1",
            "Status: done",
            "Verdict: approve",
            "Summary: <what changed>",
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
            "Follow-up: Reviewer QA review this story packet",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def render_markdown(payload: dict[str, object]) -> str:
    nodes = payload.get("nodes", [])
    blockers = payload.get("blockers", [])
    lines = [
        "# Parallel Dispatch",
        "",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Status: {payload.get('status', '-')}",
        f"- DAG level: {payload.get('level', '-') or '-'}",
        f"- Output directory: `{payload.get('output_dir', '-')}`",
        "",
        "## Blockers",
    ]
    if isinstance(blockers, list) and blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Dispatch Nodes",
            "",
            "| Story | Node | Path | Write Paths | Worktree | Debt | Packet |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if isinstance(nodes, list) and nodes:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            lines.append(
                f"| {node.get('story', '-') or '-'} | {node.get('id', '-') or '-'} | "
                f"{execution_path_payload(node).get('path', '-') or '-'} | "
                f"{', '.join(list_value(node.get('allowed_paths'))) or '-'} | "
                f"`{(node.get('worktree') if isinstance(node.get('worktree'), dict) else {}).get('path', '-') or '-'}` | "
                f"{node.get('debt_summary', '-') or '-'} | "
                f"`{node.get('packet', '-') or '-'}` |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Execution Rule",
            "",
            "Run packets in this dispatch together only while their declared write paths remain disjoint.",
            "After packet results are synchronized, run `wrkflw:merge-gate`, `wrkflw:merge-apply \"confirm: merge-apply\"` when committed lane changes exist, and then `wrkflw:integration-gate` before review approval.",
            "",
        ]
    )
    return "\n".join(lines)


def generate(root: Path, slug: str) -> dict[str, object]:
    wf = root / ".workflow" / slug
    dag = parse_dag(wf / "dag.json")
    generated_at = utc_now()
    output_dir = f".workflow/{slug}/parallel-dispatch"
    worktrees = worktree_records_by_lane(root, slug)
    clear_existing_packets(root / output_dir)
    blockers = validation_blockers(dag)
    selected = ready_nodes(dag) if not blockers else []
    if not blockers and len(selected) < 2:
        blockers.append("Fewer than two ready DAG nodes exist in the earliest ready level; use wrkflw:team-run for single-story dispatch.")
    if not blockers:
        blockers.extend(scope_blockers(selected))

    status = "ready" if not blockers else "blocked"
    level = story_sort_key(selected[0])[0] if selected else None
    packet_nodes: list[dict[str, object]] = []
    for node in selected:
        node = enrich_node_with_execution_path(node)
        story_path = story_file(root, slug, node)
        packet_path = f"{output_dir}/{node.get('id')}/implementer.md"
        lane_id = str(node.get("id", ""))
        worktree = worktrees.get(lane_id, {})
        packet_nodes.append(
            {
                "id": node.get("id", ""),
                "story": node.get("story", ""),
                "label": node.get("label", ""),
                "level": node.get("level"),
                "risk": node.get("risk", ""),
                "needs_deeper_qa": node.get("needs_deeper_qa", False),
                "planner_metadata": planner_metadata_payload(node),
                "execution_path": execution_path_payload(node),
                "allowed_paths": list_value(node.get("allowed_paths")),
                "technical_debt": debt_records(node.get("technical_debt")),
                "debt_summary": format_debt_summary(debt_records(node.get("technical_debt"))),
                "worktree": worktree,
                "packet": packet_path if status == "ready" else "",
                "result_envelope": f".workflow/{slug}/agent-results/{lane_id}.md" if lane_id else "",
            }
        )
        if status == "ready":
            packet_node = packet_nodes[-1]
            write_text_if_changed(
                root / packet_path,
                render_story_packet(root, slug, packet_node, story_sections(story_path), output_dir),
            )

    payload: dict[str, object] = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": generated_at,
        "status": status,
        "level": level,
        "source": f".workflow/{slug}/dag.json",
        "output_dir": output_dir,
        "blockers": blockers,
        "nodes": packet_nodes,
    }
    generated_at = reuse_generated_at_if_unchanged(wf / "parallel-dispatch.json", payload, generated_at)
    payload["generated_at"] = generated_at
    write_text_if_changed(wf / "parallel-dispatch.json", json.dumps(payload, indent=2) + "\n")
    write_text_if_changed(wf / "parallel-dispatch.md", render_markdown(payload))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate parallel dispatch artifacts for the earliest ready DAG level.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    generate(Path(args.root).resolve(), args.slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

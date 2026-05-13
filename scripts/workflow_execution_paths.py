#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from workflow_debt import format_debt_summary, has_blocking_debt


SCOPE_ORDER = {"trivial": 0, "small": 1, "medium": 2, "large": 3}
INTERFACE_KEYWORDS = {
    "api",
    "auth",
    "boundary",
    "contract",
    "database",
    "endpoint",
    "event",
    "interface",
    "migration",
    "public",
    "schema",
    "transport",
}
HIGH_RISK_KEYWORDS = {
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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"yes", "true", "1", "required"}
    return bool(value)


def debt_records(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


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


def story_sort_key(node: dict[str, object]) -> tuple[int, int]:
    level = node.get("level")
    try:
        level_value = int(level) if level is not None else 999999
    except (TypeError, ValueError):
        level_value = 999999
    match = re.search(r"(\d+)", str(node.get("id") or node.get("story") or ""))
    story_value = int(match.group(1)) if match else 999999
    return level_value, story_value


def story_number(value: str) -> str:
    match = re.search(r"(\d+)", value or "")
    return match.group(1) if match else ""


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


def scope_rank(scope: str) -> int:
    return SCOPE_ORDER.get(scope, SCOPE_ORDER["medium"])


def estimate_scope(text: str, allowed_paths: list[str], acceptance: list[str], validation: list[str]) -> str:
    word_count = len(re.findall(r"\w+", text))
    path_count = len(allowed_paths)
    acceptance_count = len(acceptance)
    validation_count = len(validation)
    if path_count <= 1 and acceptance_count <= 1 and validation_count <= 1 and word_count < 35:
        return "trivial"
    if path_count <= 2 and acceptance_count <= 3 and validation_count <= 2 and word_count < 120:
        return "small"
    if path_count >= 5 or acceptance_count >= 7 or validation_count >= 5 or word_count > 260:
        return "large"
    return "medium"


def contains_keyword(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def risk_metadata_for_story(
    *,
    title: str,
    body: str,
    risks: list[str],
    acceptance: list[str],
    validation: list[str],
    allowed_paths: list[str],
    dependents: list[str],
    technical_debt: list[dict[str, object]],
) -> dict[str, object]:
    text = " ".join([title, body, *risks, *allowed_paths, *acceptance, *validation])
    estimated_scope = estimate_scope(text, allowed_paths, acceptance, validation)
    touches_interfaces = contains_keyword(text, INTERFACE_KEYWORDS) or len(dependents) >= 2
    needs_new_tests = bool(validation) or not any(keyword in text.lower() for keyword in {"documentation only", "docs only", "version bump"})
    blocking_debt = has_blocking_debt(technical_debt)
    high_risk_text = contains_keyword(text, HIGH_RISK_KEYWORDS)

    flag_reasons: list[str] = []
    if high_risk_text:
        flag_reasons.append("risk keyword or sensitive domain")
    if touches_interfaces:
        flag_reasons.append("touches interfaces or has multiple dependents")
    if scope_rank(estimated_scope) >= scope_rank("large"):
        flag_reasons.append("large estimated scope")
    if blocking_debt:
        flag_reasons.append("open high/critical technical debt")
    if len(allowed_paths) >= 4:
        flag_reasons.append("broad write surface")

    needs_deeper_qa = bool(flag_reasons)
    if blocking_debt:
        review_focus = "technical debt resolution, acceptance gaps, and regression risk"
    elif needs_deeper_qa:
        review_focus = "interface contracts, regression risk, test adequacy, and cross-module behavior"
    else:
        review_focus = "standard acceptance and regression review"

    if not needs_new_tests:
        testing_guidance = "No new tests required unless the implementation changes executable behavior."
    elif touches_interfaces:
        testing_guidance = "Add or run boundary-focused validation that proves the changed interface contract still holds."
    elif estimated_scope in {"trivial", "small"}:
        testing_guidance = "Run the smallest relevant unit or smoke check for the changed path."
    else:
        testing_guidance = "Add or run focused regression coverage for the changed behavior and affected dependents."

    risk_rationale = "; ".join(flag_reasons) if flag_reasons else "No high-risk routing trigger detected."
    return {
        "estimated_scope": estimated_scope,
        "touches_interfaces": touches_interfaces,
        "needs_new_tests": needs_new_tests,
        "needs_deeper_qa": needs_deeper_qa,
        "testing_guidance": testing_guidance,
        "review_focus": review_focus,
        "risk_rationale": risk_rationale,
        "flag_reasons": flag_reasons,
    }


def execution_path_for_metadata(metadata: dict[str, object]) -> dict[str, object]:
    flagged = bool_value(metadata.get("needs_deeper_qa"))
    if flagged:
        return {
            "path": "flagged",
            "label": "flagged QA/reviewer/synthesis path",
            "required_roles": ["Tech Lead", "Implementer 1", "Reviewer QA"],
            "optional_roles": ["Product Owner", "Implementer 2"],
            "review_flow": "Implementer -> Reviewer QA + Tech Lead review -> synthesis decision",
            "synthesis_required": True,
            "qa_required": True,
            "retry_policy": "If Reviewer QA or Tech Lead blocks, route to feedback synthesis or issue-advisor work before retrying.",
        }
    return {
        "path": "simple",
        "label": "simple implementer/reviewer path",
        "required_roles": ["Implementer 1", "Reviewer QA"],
        "optional_roles": ["Product Owner", "Tech Lead", "Implementer 2"],
        "review_flow": "Implementer -> Reviewer QA",
        "synthesis_required": False,
        "qa_required": False,
        "retry_policy": "If Reviewer QA blocks repeatedly, escalate to flagged path or issue-advisor work.",
    }


def enrich_node_with_execution_path(node: dict[str, object]) -> dict[str, object]:
    enriched = deepcopy(node)
    technical_debt = debt_records(enriched.get("technical_debt"))
    metadata = {
        "estimated_scope": str(enriched.get("estimated_scope") or "medium"),
        "touches_interfaces": bool_value(enriched.get("touches_interfaces")),
        "needs_new_tests": bool_value(enriched.get("needs_new_tests")),
        "needs_deeper_qa": bool_value(enriched.get("needs_deeper_qa")),
        "testing_guidance": str(enriched.get("testing_guidance") or ""),
        "review_focus": str(enriched.get("review_focus") or ""),
        "risk_rationale": str(enriched.get("risk_rationale") or ""),
        "flag_reasons": list_value(enriched.get("flag_reasons")),
    }
    if has_blocking_debt(technical_debt) and "open high/critical technical debt" not in metadata["flag_reasons"]:
        metadata["flag_reasons"].append("open high/critical technical debt")
        metadata["needs_deeper_qa"] = True
        if not metadata["risk_rationale"] or metadata["risk_rationale"] == "No high-risk routing trigger detected.":
            metadata["risk_rationale"] = "open high/critical technical debt"
    path = execution_path_for_metadata(metadata)
    enriched["planner_metadata"] = metadata
    enriched["execution_path"] = path
    return enriched


def active_node(payload: dict[str, object], active_story: str | None = None) -> dict[str, object]:
    nodes = dag_nodes(payload)
    if active_story:
        active_number = story_number(active_story)
        expected_id = f"story-{active_number}" if active_number else ""
        for node in nodes:
            if node.get("story") == active_story or node.get("id") == expected_id:
                return node
    active = [
        node
        for node in nodes
        if str(node.get("status", "")).strip().lower() in {"active", "ready"}
    ]
    return sorted(active, key=story_sort_key)[0] if active else {}


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


def table_cell(value: object) -> str:
    if isinstance(value, list):
        text = ", ".join(str(item).strip() for item in value if str(item).strip())
    elif isinstance(value, bool):
        text = "yes" if value else "no"
    else:
        text = str(value).strip() if value is not None else "-"
    return re.sub(r"\s+", " ", text).replace("|", "\\|") if text else "-"


def render_markdown(payload: dict[str, object]) -> str:
    node = payload.get("node", {})
    node = node if isinstance(node, dict) else {}
    metadata = payload.get("planner_metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    path = payload.get("execution_path", {})
    path = path if isinstance(path, dict) else {}
    return "\n".join(
        [
            "# Execution Path",
            "",
            f"- Workflow slug: {payload.get('workflow_slug', '-')}",
            f"- Generated at: {payload.get('generated_at', '-')}",
            f"- Source: `{payload.get('source', '-')}`",
            f"- Story: {node.get('story', '-') or '-'}",
            f"- DAG node: {node.get('id', '-') or '-'}",
            f"- DAG status: {node.get('status', '-') or '-'}",
            f"- Execution path: {path.get('path', '-') or '-'}",
            f"- Path label: {path.get('label', '-') or '-'}",
            f"- Review flow: {path.get('review_flow', '-') or '-'}",
            f"- Required roles: {table_cell(path.get('required_roles'))}",
            f"- Optional roles: {table_cell(path.get('optional_roles'))}",
            f"- QA required: {table_cell(path.get('qa_required'))}",
            f"- Synthesis required: {table_cell(path.get('synthesis_required'))}",
            f"- Retry policy: {path.get('retry_policy', '-') or '-'}",
            "",
            "## Planner Metadata",
            "",
            f"- Estimated scope: {metadata.get('estimated_scope', '-') or '-'}",
            f"- Touches interfaces: {table_cell(metadata.get('touches_interfaces'))}",
            f"- Needs new tests: {table_cell(metadata.get('needs_new_tests'))}",
            f"- Needs deeper QA: {table_cell(metadata.get('needs_deeper_qa'))}",
            f"- Testing guidance: {metadata.get('testing_guidance', '-') or '-'}",
            f"- Review focus: {metadata.get('review_focus', '-') or '-'}",
            f"- Risk rationale: {metadata.get('risk_rationale', '-') or '-'}",
            f"- Flag reasons: {table_cell(metadata.get('flag_reasons'))}",
            "",
            "## Technical Debt",
            "",
            f"- {format_debt_summary(debt_records(node.get('technical_debt')))}",
            "",
        ]
    )


def generate(root: Path, slug: str, active_story: str | None = None) -> dict[str, object]:
    wf = root / ".workflow" / slug
    dag = parse_dag(wf / "dag.json")
    node = active_node(dag, active_story)
    enriched = enrich_node_with_execution_path(node) if node else {}
    payload: dict[str, object] = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": utc_now(),
        "source": f".workflow/{slug}/dag.json",
        "node": enriched,
        "planner_metadata": enriched.get("planner_metadata", {}) if enriched else {},
        "execution_path": enriched.get("execution_path", {}) if enriched else {},
    }
    generated_at = reuse_generated_at_if_unchanged(wf / "execution-path.json", payload, str(payload["generated_at"]))
    payload["generated_at"] = generated_at
    write_text_if_changed(wf / "execution-path.json", json.dumps(payload, indent=2) + "\n")
    write_text_if_changed(wf / "execution-path.md", render_markdown(payload))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the risk-based execution path artifact for a workflow story.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--active-story", default="")
    args = parser.parse_args()
    generate(Path(args.root).resolve(), args.slug, args.active_story or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


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


def workflow_path(root: Path, slug: str, relative: str) -> Path:
    return root / ".workflow" / slug / relative


def category_for_class(failure_class: str) -> str:
    normalized = failure_class.strip().lower()
    if normalized in {"dependency_block", "design_contradiction", "stale_gate_evidence"}:
        return "dependency_or_architecture"
    if normalized in {"scope_too_broad", "scope_too_large"}:
        return "scope_too_large"
    if normalized in {"environment_failure", "ci_infrastructure", "ci_timeout", "integration_timeout", "agent_timeout"}:
        return "environment_failure"
    if normalized in {"policy_or_scope_block", "policy_or_configuration_block", "security_or_policy_block"}:
        return "policy_or_security_block"
    if normalized in {"merge_conflict"}:
        return "merge_conflict"
    if normalized in {"missing_validation_evidence", "insufficient_evidence", "ci_missing_or_pending"}:
        return "insufficient_evidence"
    if normalized in {"test_failure", "build_failure", "lint_failure", "integration_test_failure", "ci_failure"}:
        return "implementation"
    if normalized in {"known_gap", "technical_debt"}:
        return "known_gap"
    return normalized or "unknown"


def recommended_gate_for_class(failure_class: str) -> str:
    category = category_for_class(failure_class)
    if category == "dependency_or_architecture":
        return "replan"
    if category == "scope_too_large":
        return "split"
    if category in {"environment_failure", "policy_or_security_block", "merge_conflict", "insufficient_evidence"}:
        return "block"
    if category == "known_gap":
        return "debt"
    return "fix"


def classification(
    failure_class: str,
    *,
    source: str,
    summary: str = "",
    retryable: bool | None = None,
    severity: str = "",
) -> dict[str, object]:
    normalized = failure_class.strip().lower() or "unknown"
    category = category_for_class(normalized)
    if retryable is None:
        retryable = category in {"environment_failure", "implementation"} and normalized not in {"policy_or_scope_block"}
    return {
        "failure_class": normalized,
        "failure_category": category,
        "source": source,
        "summary": summary,
        "retryable": retryable,
        "recommended_gate": recommended_gate_for_class(normalized),
        "severity": severity or ("high" if category in {"dependency_or_architecture", "merge_conflict"} else "medium"),
    }


def classify_text(source: str, text: str) -> dict[str, object]:
    lower = text.lower()
    if any(item in lower for item in ["cycle", "missing dependency", "dependency graph", "stale", "head changed"]):
        return classification("stale_gate_evidence" if "stale" in lower or "head changed" in lower else "dependency_block", source=source, summary=text)
    if any(item in lower for item in ["out-of-scope", "outside allowed", "policy", "allowlist", "not allowed"]):
        return classification("policy_or_scope_block", source=source, summary=text, retryable=False)
    if any(item in lower for item in ["dirty", "missing", "cannot inspect", "timeout", "timed out"]):
        return classification("environment_failure", source=source, summary=text)
    if any(item in lower for item in ["conflict", "merge failed"]):
        return classification("merge_conflict", source=source, summary=text)
    if any(item in lower for item in ["integration validation", "test", "failed"]):
        return classification("integration_test_failure", source=source, summary=text)
    return classification("unknown", source=source, summary=text)


def issue_advisor_classification(root: Path, slug: str) -> dict[str, object]:
    payload = read_json(workflow_path(root, slug, "issue-advisor.json"))
    failure_category = str(payload.get("failure_category") or "").strip()
    if not failure_category:
        return {}
    action = str(payload.get("action") or "").strip()
    diagnosis = str(payload.get("failure_diagnosis") or payload.get("summary") or "").strip()
    return {
        "failure_class": failure_category,
        "failure_category": failure_category,
        "source": "issue-advisor",
        "summary": diagnosis,
        "retryable": action in {"retry_approach", "retry_modified"},
        "recommended_gate": "replan" if action == "escalate_to_replan" else action or recommended_gate_for_class(failure_category),
        "severity": "high" if action in {"escalate_to_replan", "split"} else "medium",
    }


def artifact_classifications(root: Path, slug: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for relative, source in [
        ("merge-gate.json", "merge-gate"),
        ("merge-apply.json", "merge-apply"),
        ("integration-test-gate.json", "integration-gate"),
        ("ci-feedback.json", "ci-feedback"),
    ]:
        payload = read_json(workflow_path(root, slug, relative))
        if not payload:
            continue
        top = payload.get("failure_classification")
        if isinstance(top, dict) and top.get("failure_class"):
            entries.append(top)
        for key in ["failure_classifications", "fix_tasks", "entries"]:
            raw = payload.get(key)
            if not isinstance(raw, list):
                continue
            for item in raw:
                if not isinstance(item, dict):
                    continue
                nested = item.get("failure_classification")
                if isinstance(nested, dict) and nested.get("failure_class"):
                    entries.append(nested)
                elif item.get("failure_class"):
                    entries.append(
                        classification(
                            str(item.get("failure_class") or ""),
                            source=source,
                            summary=str(item.get("summary") or item.get("failure") or ""),
                            retryable=bool(item.get("retryable")) if "retryable" in item else None,
                            severity=str(item.get("severity") or ""),
                        )
                    )
    advisor = issue_advisor_classification(root, slug)
    if advisor:
        entries.append(advisor)
    return entries


def highest_priority_classification(entries: list[dict[str, object]]) -> dict[str, object]:
    if not entries:
        return {}
    priority = {
        "dependency_or_architecture": 0,
        "merge_conflict": 1,
        "policy_or_security_block": 2,
        "environment_failure": 3,
        "scope_too_large": 4,
        "implementation": 5,
        "known_gap": 6,
        "insufficient_evidence": 7,
        "unknown": 8,
    }
    return sorted(entries, key=lambda item: priority.get(str(item.get("failure_category") or "unknown"), 99))[0]

#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = "agent-result-v1"
VALID_ROLES = {"Product Owner", "Tech Lead", "Implementer 1", "Implementer 2", "Reviewer QA"}
VALID_STATUSES = {"planned", "in-progress", "in-review", "done", "blocked", "optional"}
VALID_VERDICTS = {"", "approve", "approve-with-changes", "block", "blocked", "n/a", "none"}
REQUIRED_SCALAR_FIELDS = ["schema", "role", "status", "verdict", "summary", "follow-up"]
REQUIRED_LIST_FIELDS = [
    "files-changed",
    "validation-run",
    "missing-requirements",
    "incorrect-assumptions",
    "risks",
    "questions",
    "suggested-changes",
    "evidence",
    "conflict-entries",
    "assumption-updates",
    "red-team-notes",
    "findings",
    "debt-entries",
    "memory-entries",
]
OPTIONAL_SCALAR_FIELDS = [
    "model",
    "input-tokens",
    "output-tokens",
    "cost-usd",
    "estimated-cost-usd",
    "cost-source",
    "elapsed-seconds",
    "duration-ms",
    "invocation-id",
    "execution-id",
    "run-id",
    "parent-invocation-id",
    "agent-node-id",
    "reasoner-id",
    "attempt",
    "retry-count",
    "transport-retry-count",
]


ROLE_ALIASES = {
    "product owner": "Product Owner",
    "po": "Product Owner",
    "tech lead": "Tech Lead",
    "technical lead": "Tech Lead",
    "implementer": "Implementer 1",
    "implementer 1": "Implementer 1",
    "implementer-1": "Implementer 1",
    "implementer 2": "Implementer 2",
    "implementer-2": "Implementer 2",
    "reviewer qa": "Reviewer QA",
    "qa": "Reviewer QA",
    "reviewer": "Reviewer QA",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_role(value: object) -> str:
    text = str(value or "").strip()
    if text in VALID_ROLES:
        return text
    return ROLE_ALIASES.get(text.lower(), text)


def schema_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "schemas" / "agent-result.schema.json"


def schema_doc_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "agent-result-schema.md"


def validation_records_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "records" / "agent-result-validation.jsonl"


def agent_result_schema_payload() -> dict[str, object]:
    properties: dict[str, object] = {
        "schema": {"const": SCHEMA_VERSION},
        "role": {"enum": sorted(VALID_ROLES)},
        "status": {"enum": sorted(VALID_STATUSES)},
        "verdict": {"enum": sorted(item for item in VALID_VERDICTS if item)},
        "summary": {"type": "string", "minLength": 1},
        "follow-up": {"type": "string", "minLength": 1},
    }
    for field in REQUIRED_LIST_FIELDS:
        properties[field] = {"type": "array", "items": {"type": "string"}}
    for field in OPTIONAL_SCALAR_FIELDS:
        properties[field] = {"type": "string"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "wrkflw.agent-result.schema.json",
        "title": "wrkflw delegated agent result",
        "type": "object",
        "additionalProperties": False,
        "required": REQUIRED_SCALAR_FIELDS + REQUIRED_LIST_FIELDS,
        "properties": properties,
    }


def render_schema_doc(workflow_slug: str) -> str:
    required = REQUIRED_SCALAR_FIELDS + REQUIRED_LIST_FIELDS
    lines = [
        "# Agent Result Schema",
        "",
        f"- Workflow slug: {workflow_slug}",
        f"- Schema version: {SCHEMA_VERSION}",
        "- Applies to: `.workflow/<slug>/agent-results/*.md` and worktree result envelopes synchronized with `wrkflw:team-sync-all`",
        "",
        "## Required Fields",
    ]
    lines.extend(f"- {field}" for field in required)
    lines.extend(
        [
            "",
            "## Optional Accounting Fields",
            "- " + ", ".join(OPTIONAL_SCALAR_FIELDS),
            "",
            "## Notes",
            "- Use `- none` for empty list fields.",
            "- Stored result envelopes are rejected before ingest when required fields are missing or invalid.",
            "- Direct one-line `wrkflw:team-sync` status updates remain supported for lightweight human handoffs.",
            "",
        ]
    )
    return "\n".join(lines)


def ensure_agent_result_schema_artifacts(root: Path, workflow_slug: str) -> None:
    path = schema_path(root, workflow_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(agent_result_schema_payload(), indent=2, sort_keys=True) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != payload:
        path.write_text(payload, encoding="utf-8")
    doc_path = schema_doc_path(root, workflow_slug)
    doc = render_schema_doc(workflow_slug)
    if not doc_path.exists() or doc_path.read_text(encoding="utf-8") != doc:
        doc_path.write_text(doc, encoding="utf-8")


def strict_schema_required(report: dict[str, object], source: str | None, raw: str) -> bool:
    if source:
        return True
    schema = str(report.get("schema") or "").strip()
    if schema:
        return True
    return False


def list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def validate_agent_result_report(report: dict[str, object], strict: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not strict:
        return errors, warnings

    missing = [field for field in REQUIRED_SCALAR_FIELDS + REQUIRED_LIST_FIELDS if field not in report]
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))

    schema = str(report.get("schema") or "").strip()
    if schema and schema != SCHEMA_VERSION:
        errors.append(f"unsupported schema `{schema}`; expected `{SCHEMA_VERSION}`")
    elif "schema" in report and not schema:
        errors.append("schema must be non-empty")

    role = canonical_role(report.get("role"))
    if "role" in report and role not in VALID_ROLES:
        errors.append("role must be one of: " + ", ".join(sorted(VALID_ROLES)))

    status = str(report.get("status") or "").strip().lower()
    if "status" in report and status not in VALID_STATUSES:
        errors.append("status must be one of: " + ", ".join(sorted(VALID_STATUSES)))

    verdict = str(report.get("verdict") or "").strip().lower()
    if "verdict" in report and verdict not in VALID_VERDICTS:
        errors.append("verdict must be approve, approve-with-changes, block, blocked, none, or n/a")

    for field in ["summary", "follow-up"]:
        if field in report and not str(report.get(field) or "").strip():
            errors.append(f"{field} must be non-empty")

    for field in REQUIRED_LIST_FIELDS:
        if field in report and not isinstance(report.get(field), list):
            errors.append(f"{field} must be a list; use bullets or `- none`")

    if status == "done" and not list_value(report.get("evidence")) and not list_value(report.get("validation-run")):
        warnings.append("done result has no evidence or validation-run entries")
    if role.startswith("Implementer") and status == "done" and "files-changed" in report and "validation-run" in report:
        if not list_value(report.get("files-changed")) and not list_value(report.get("validation-run")):
            warnings.append("implementer done result reports no changed files and no validation")
    return errors, warnings


def append_agent_result_validation_record(
    root: Path,
    workflow_slug: str,
    source: str,
    status: str,
    errors: Iterable[str],
    warnings: Iterable[str],
) -> None:
    path = validation_records_path(root, workflow_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "recorded_at": utc_now(),
        "workflow_slug": workflow_slug,
        "source": source or "direct-team-sync",
        "status": status,
        "failure_type": "schema_validation" if status == "invalid" else "none",
        "errors": [str(item) for item in errors if str(item).strip()],
        "warnings": [str(item) for item in warnings if str(item).strip()],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")

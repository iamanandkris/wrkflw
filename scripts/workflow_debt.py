#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


RESOLVED_STATUSES = {"resolved", "closed"}
BLOCKING_STATUSES = {"open"}
BLOCKING_SEVERITIES = {"high", "critical"}
SEVERITIES = {"info", "low", "medium", "high", "critical"}
DEBT_TYPES = {
    "dropped acceptance criterion",
    "missing functionality",
    "known regression risk",
    "deferred test",
    "unresolved design gap",
    "operational limitation",
    "security limitation",
    "operational or security limitation",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def debt_records_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "records" / "debt.jsonl"


def debt_summary_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "debt.md"


def normalize_story_id(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or text in {"-", "none", "n/a"}:
        return ""
    match = re.search(r"\bstory[-\s]*(\d+)\b", text, flags=re.IGNORECASE)
    if match:
        return f"story-{int(match.group(1))}"
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return f"story-{int(match.group(1))}"
    cleaned = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return cleaned


def story_label(story_id: str) -> str:
    match = re.search(r"(\d+)$", story_id or "")
    return f"Story {int(match.group(1))}" if match else story_id or "-"


def parse_story_id_list(value: object) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw = str(value or "").strip()
        if not raw or raw.lower() in {"-", "none", "n/a"}:
            return []
        raw_items = re.split(r"[,;\n]+", raw)
    normalized = []
    for item in raw_items:
        story_id = normalize_story_id(item)
        if story_id and story_id not in normalized:
            normalized.append(story_id)
    return normalized


def normalize_debt_type(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", " ").replace("-", " "))
    if not text:
        return "unresolved design gap"
    return text if text in DEBT_TYPES else text


def normalize_severity(value: object) -> str:
    severity = str(value or "").strip().lower()
    return severity if severity in SEVERITIES else "medium"


def normalize_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status in {"", "-", "none"}:
        return "open"
    if status in {"accepted debt", "accept"}:
        return "accepted"
    return status


def normalize_propagation(value: object) -> str:
    propagation = str(value or "").strip().lower().replace("_", "-")
    if propagation in {"direct", "none"}:
        return "direct"
    if propagation in {"global", "all"}:
        return "global"
    return "downstream"


def load_debt_records(root: Path, workflow_slug: str) -> list[dict[str, object]]:
    path = debt_records_path(root, workflow_slug)
    records: list[dict[str, object]] = []
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(normalize_record(payload))
    return records


def normalize_record(record: dict[str, object]) -> dict[str, object]:
    normalized = dict(record)
    normalized.pop("_explicit_fields", None)
    normalized["source_story"] = normalize_story_id(
        normalized.get("source_story") or normalized.get("story") or normalized.get("source")
    )
    normalized["source_story_label"] = str(
        normalized.get("source_story_label") or story_label(str(normalized.get("source_story") or ""))
    )
    normalized["debt_type"] = normalize_debt_type(normalized.get("debt_type") or normalized.get("type"))
    normalized["severity"] = normalize_severity(normalized.get("severity"))
    normalized["status"] = normalize_status(normalized.get("status"))
    normalized["summary"] = str(normalized.get("summary") or normalized.get("note") or "").strip()
    normalized["impact"] = str(normalized.get("impact") or "").strip()
    normalized["owner"] = str(normalized.get("owner") or "").strip()
    normalized["resolution"] = str(normalized.get("resolution") or "").strip()
    normalized["propagation"] = normalize_propagation(normalized.get("propagation"))
    normalized["applies_to"] = parse_story_id_list(normalized.get("applies_to"))
    return normalized


def visible_debt_records(records: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    return [
        record
        for record in records
        if str(record.get("status", "")).strip().lower() not in RESOLVED_STATUSES
    ]


def make_debt_id(record: dict[str, object], timestamp: str) -> str:
    seed = "|".join(
        [
            timestamp,
            str(record.get("source_story") or ""),
            str(record.get("debt_type") or ""),
            str(record.get("severity") or ""),
            str(record.get("summary") or ""),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    stamp = re.sub(r"[^0-9]", "", timestamp)[:14]
    return f"debt-{stamp}-{digest}"


def write_debt_records(root: Path, workflow_slug: str, records: list[dict[str, object]]) -> None:
    path = debt_records_path(root, workflow_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = "\n".join(json.dumps(record, sort_keys=True) for record in records)
    path.write_text((output + "\n") if output else "", encoding="utf-8")


def append_or_update_debt_record(root: Path, workflow_slug: str, record: dict[str, object]) -> dict[str, object]:
    timestamp = utc_now()
    explicit_fields = {
        str(item)
        for item in record.get("_explicit_fields", [])
        if str(item).strip()
    } if isinstance(record.get("_explicit_fields"), list) else set()
    normalized = normalize_record(record)
    normalized["workflow_slug"] = workflow_slug
    normalized["updated_at"] = timestamp
    records = load_debt_records(root, workflow_slug)
    record_id = str(normalized.get("id") or "").strip()
    if not record_id:
        normalized["created_at"] = timestamp
        normalized["id"] = make_debt_id(normalized, timestamp)
        records.append(normalized)
        write_debt_records(root, workflow_slug, records)
        render_debt_summary(root, workflow_slug, records)
        return normalized

    normalized["id"] = record_id
    for index, existing in enumerate(records):
        if str(existing.get("id") or "") != record_id:
            continue
        merged = deepcopy(existing)
        for key, value in normalized.items():
            if key in {"created_at"}:
                continue
            meaningful = value is not None and value != "" and value != []
            always_update = key in {"id", "workflow_slug", "status", "resolution", "updated_at"}
            explicitly_update = not explicit_fields or key in explicit_fields
            if always_update or (explicitly_update and meaningful):
                merged[key] = value
        merged["created_at"] = existing.get("created_at") or timestamp
        records[index] = normalize_record(merged)
        write_debt_records(root, workflow_slug, records)
        render_debt_summary(root, workflow_slug, records)
        return records[index]

    normalized["created_at"] = timestamp
    records.append(normalized)
    write_debt_records(root, workflow_slug, records)
    render_debt_summary(root, workflow_slug, records)
    return normalized


def descendant_ids(dependents: dict[str, list[str]], source: str) -> set[str]:
    visited: set[str] = set()
    pending = list(dependents.get(source, []))
    while pending:
        current = pending.pop(0)
        if current in visited:
            continue
        visited.add(current)
        pending.extend(dependents.get(current, []))
    return visited


def record_relation_to_node(
    record: dict[str, object],
    node_id: str,
    dependents: dict[str, list[str]],
    known_node_ids: set[str],
) -> str:
    if str(record.get("status", "")).strip().lower() in RESOLVED_STATUSES:
        return ""
    source = normalize_story_id(record.get("source_story"))
    applies_to = parse_story_id_list(record.get("applies_to"))
    propagation = normalize_propagation(record.get("propagation"))
    if propagation == "global":
        return "direct" if source == node_id else "inherited"
    if source and source == node_id:
        return "direct"
    if applies_to and node_id in applies_to:
        return "inherited"
    if source and source in known_node_ids and propagation == "downstream":
        if node_id in descendant_ids(dependents, source):
            return "inherited"
    return ""


def compact_debt_record(record: dict[str, object], relation: str) -> dict[str, object]:
    return {
        "id": record.get("id", ""),
        "relation": relation,
        "source_story": normalize_story_id(record.get("source_story")),
        "debt_type": normalize_debt_type(record.get("debt_type")),
        "severity": normalize_severity(record.get("severity")),
        "status": normalize_status(record.get("status")),
        "summary": str(record.get("summary") or "").strip(),
        "impact": str(record.get("impact") or "").strip(),
        "owner": str(record.get("owner") or "").strip(),
        "resolution": str(record.get("resolution") or "").strip(),
    }


def debt_for_node_id(
    node_id: str,
    records: list[dict[str, object]],
    dependents: dict[str, list[str]],
    known_node_ids: set[str],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for record in visible_debt_records(records):
        relation = record_relation_to_node(record, node_id, dependents, known_node_ids)
        if relation:
            items.append(compact_debt_record(record, relation))
    return sorted(items, key=lambda item: (str(item.get("relation")), str(item.get("severity")), str(item.get("id"))))


def debt_for_node_from_payload(payload: dict[str, object], node_id: str) -> list[dict[str, object]]:
    nodes = payload.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if str(node.get("id") or "") == node_id:
            debt = node.get("technical_debt", [])
            return [item for item in debt if isinstance(item, dict)] if isinstance(debt, list) else []
    return []


def has_blocking_debt(records: list[dict[str, object]]) -> bool:
    for record in records:
        status = normalize_status(record.get("status"))
        severity = normalize_severity(record.get("severity"))
        if status in BLOCKING_STATUSES and severity in BLOCKING_SEVERITIES:
            return True
    return False


def blocking_debt_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        record
        for record in visible_debt_records(records)
        if normalize_status(record.get("status")) in BLOCKING_STATUSES
        and normalize_severity(record.get("severity")) in BLOCKING_SEVERITIES
    ]


def format_debt_summary(records: list[dict[str, object]], limit: int = 3) -> str:
    if not records:
        return "-"
    output: list[str] = []
    for record in records[:limit]:
        source = normalize_story_id(record.get("source_story"))
        relation = str(record.get("relation") or "direct")
        severity = normalize_severity(record.get("severity"))
        debt_type = normalize_debt_type(record.get("debt_type"))
        summary = str(record.get("summary") or "").strip()
        prefix = f"{severity} {relation} {debt_type}"
        if source:
            prefix += f" from {source}"
        output.append(f"{prefix}: {summary}" if summary else prefix)
    if len(records) > limit:
        output.append(f"+{len(records) - limit} more")
    return "; ".join(output)


def markdown_cell(value: object) -> str:
    if isinstance(value, list):
        text = ", ".join(str(item).strip() for item in value if str(item).strip())
    else:
        text = str(value or "").strip()
    return re.sub(r"\s+", " ", text).replace("|", "\\|") if text else "-"


def render_debt_summary(root: Path, workflow_slug: str, records: list[dict[str, object]] | None = None) -> None:
    all_records = records if records is not None else load_debt_records(root, workflow_slug)
    visible = visible_debt_records(all_records)
    blocking = blocking_debt_records(all_records)
    lines = [
        "# Technical Debt Ledger",
        "",
        f"- Workflow slug: {workflow_slug}",
        f"- Source: `.workflow/{workflow_slug}/records/debt.jsonl`",
        f"- Open or accepted entries: {len(visible)}",
        f"- Blocking open high/critical entries: {len(blocking)}",
        "",
        "## Entries",
        "",
        "| ID | Story | Type | Severity | Status | Summary | Propagation | Applies To | Owner | Resolution |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if all_records:
        for record in all_records:
            lines.append(
                "| "
                + " | ".join(
                    markdown_cell(value)
                    for value in [
                        record.get("id", ""),
                        record.get("source_story") or record.get("source_story_label") or "-",
                        record.get("debt_type", ""),
                        record.get("severity", ""),
                        record.get("status", ""),
                        record.get("summary", ""),
                        record.get("propagation", ""),
                        record.get("applies_to", []),
                        record.get("owner", ""),
                        record.get("resolution", ""),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - | - | - |")
    lines.append("")
    path = debt_summary_path(root, workflow_slug)
    path.write_text("\n".join(lines), encoding="utf-8")


def ensure_debt_artifacts(root: Path, workflow_slug: str) -> None:
    records_path = debt_records_path(root, workflow_slug)
    records_path.parent.mkdir(parents=True, exist_ok=True)
    if not records_path.exists():
        records_path.write_text("", encoding="utf-8")
    render_debt_summary(root, workflow_slug)

#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ACTIVE_STATUSES = {"active"}
VISIBLE_STATUSES = {"active", "superseded", "invalid"}
MEMORY_CATEGORIES = {
    "repo-convention",
    "failure-pattern",
    "interface-note",
    "validated-test-command",
    "implementation-pattern",
}
CATEGORY_ALIASES = {
    "convention": "repo-convention",
    "repo convention": "repo-convention",
    "repository convention": "repo-convention",
    "failure": "failure-pattern",
    "failure pattern": "failure-pattern",
    "interface": "interface-note",
    "interface note": "interface-note",
    "test": "validated-test-command",
    "test command": "validated-test-command",
    "validated command": "validated-test-command",
    "validated test": "validated-test-command",
    "implementation": "implementation-pattern",
    "pattern": "implementation-pattern",
    "implementation pattern": "implementation-pattern",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def memory_records_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "records" / "memory.jsonl"


def memory_summary_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "memory.md"


def normalize_story_id(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or text in {"-", "none", "n/a", "global", "repo", "repository"}:
        return ""
    match = re.search(r"\bstory[-\s]*(\d+)\b", text, flags=re.IGNORECASE)
    if match:
        return f"story-{int(match.group(1))}"
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return f"story-{int(match.group(1))}"
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def story_label(story_id: str) -> str:
    match = re.search(r"(\d+)$", story_id or "")
    return f"Story {int(match.group(1))}" if match else story_id or "repo"


def parse_list(value: object) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw = str(value or "").strip()
        if not raw or raw.lower() in {"-", "none", "n/a"}:
            return []
        raw_items = re.split(r"[,;\n]+", raw)
    result: list[str] = []
    for item in raw_items:
        cleaned = str(item or "").strip()
        if cleaned and cleaned.lower() not in {"-", "none", "n/a"} and cleaned not in result:
            result.append(cleaned)
    return result


def parse_story_id_list(value: object) -> list[str]:
    story_ids: list[str] = []
    for item in parse_list(value):
        story_id = normalize_story_id(item)
        if story_id and story_id not in story_ids:
            story_ids.append(story_id)
    return story_ids


def normalize_category(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower().replace("_", "-"))
    text = text.replace(" ", "-")
    if text in MEMORY_CATEGORIES:
        return text
    alias_key = text.replace("-", " ")
    return CATEGORY_ALIASES.get(alias_key, "implementation-pattern")


def normalize_status(value: object) -> str:
    status = str(value or "").strip().lower().replace("_", "-")
    if status in {"", "-", "none"}:
        return "active"
    if status in {"retired", "obsolete"}:
        return "superseded"
    if status in VISIBLE_STATUSES:
        return status
    return "active"


def normalize_confidence(value: object) -> str:
    confidence = str(value or "").strip().lower()
    return confidence if confidence in {"low", "medium", "high"} else "medium"


def redact_sensitive_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*[^,\s;]+",
        lambda match: f"{match.group(1)}=<redacted>",
        text,
    )
    text = re.sub(r"\b(sk|ghp|github_pat)_[A-Za-z0-9_]{12,}\b", "<redacted-token>", text)
    return text


def normalize_record(record: dict[str, object]) -> dict[str, object]:
    normalized = dict(record)
    normalized.pop("_explicit_fields", None)
    normalized["category"] = normalize_category(normalized.get("category") or normalized.get("type"))
    normalized["status"] = normalize_status(normalized.get("status"))
    normalized["confidence"] = normalize_confidence(normalized.get("confidence"))
    story = normalized.get("story") or normalized.get("source_story")
    normalized["story"] = normalize_story_id(story)
    normalized["story_label"] = str(normalized.get("story_label") or story_label(str(normalized.get("story") or "")))
    normalized["applies_to"] = parse_story_id_list(normalized.get("applies_to"))
    normalized["tags"] = parse_list(normalized.get("tags"))
    for key in ["summary", "details", "evidence", "command", "result", "owner", "source"]:
        normalized[key] = redact_sensitive_text(normalized.get(key))
    return normalized


def load_memory_records(root: Path, workflow_slug: str) -> list[dict[str, object]]:
    path = memory_records_path(root, workflow_slug)
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


def visible_memory_records(records: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    return [
        record
        for record in records
        if str(record.get("status") or "active").strip().lower() in VISIBLE_STATUSES
    ]


def active_memory_records(records: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    return [
        record
        for record in visible_memory_records(records)
        if str(record.get("status") or "active").strip().lower() in ACTIVE_STATUSES
    ]


def make_memory_id(record: dict[str, object], timestamp: str) -> str:
    seed = "|".join(
        [
            timestamp,
            str(record.get("category") or ""),
            str(record.get("story") or ""),
            str(record.get("summary") or ""),
            str(record.get("command") or ""),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]
    stamp = re.sub(r"[^0-9]", "", timestamp)[:14]
    return f"memory-{stamp}-{digest}"


def write_memory_records(root: Path, workflow_slug: str, records: list[dict[str, object]]) -> None:
    path = memory_records_path(root, workflow_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    output = "\n".join(json.dumps(record, sort_keys=True) for record in records)
    path.write_text((output + "\n") if output else "", encoding="utf-8")


def append_or_update_memory_record(root: Path, workflow_slug: str, record: dict[str, object]) -> dict[str, object]:
    timestamp = utc_now()
    explicit_fields = {
        str(item)
        for item in record.get("_explicit_fields", [])
        if str(item).strip()
    } if isinstance(record.get("_explicit_fields"), list) else set()
    normalized = normalize_record(record)
    normalized["workflow_slug"] = workflow_slug
    normalized["updated_at"] = timestamp
    records = load_memory_records(root, workflow_slug)
    record_id = str(normalized.get("id") or "").strip()
    if not record_id:
        normalized["created_at"] = timestamp
        normalized["id"] = make_memory_id(normalized, timestamp)
        records.append(normalized)
        write_memory_records(root, workflow_slug, records)
        render_memory_summary(root, workflow_slug, records)
        return normalized

    normalized["id"] = record_id
    for index, existing in enumerate(records):
        if str(existing.get("id") or "") != record_id:
            continue
        merged = deepcopy(existing)
        for key, value in normalized.items():
            if key == "created_at":
                continue
            meaningful = value is not None and value != "" and value != []
            always_update = key in {"id", "workflow_slug", "status", "updated_at"}
            explicitly_update = not explicit_fields or key in explicit_fields
            if always_update or (explicitly_update and meaningful):
                merged[key] = value
        merged["created_at"] = existing.get("created_at") or timestamp
        records[index] = normalize_record(merged)
        write_memory_records(root, workflow_slug, records)
        render_memory_summary(root, workflow_slug, records)
        return records[index]

    normalized["created_at"] = timestamp
    records.append(normalized)
    write_memory_records(root, workflow_slug, records)
    render_memory_summary(root, workflow_slug, records)
    return normalized


def applies_to_story(record: dict[str, object], story: str) -> bool:
    story_id = normalize_story_id(story)
    record_story = str(record.get("story") or "").strip()
    applies_to = [str(item) for item in record.get("applies_to", []) if str(item).strip()]
    if not story_id:
        return not record_story and not applies_to
    return not record_story or record_story == story_id or story_id in applies_to


def memory_for_story(root: Path, workflow_slug: str, story: str, limit: int = 8) -> list[dict[str, object]]:
    records = [
        record
        for record in active_memory_records(load_memory_records(root, workflow_slug))
        if applies_to_story(record, story)
    ]
    records.sort(key=lambda record: (str(record.get("category") or ""), str(record.get("updated_at") or "")), reverse=True)
    return records[:limit]


def memory_bullets(records: Iterable[dict[str, object]]) -> list[str]:
    bullets: list[str] = []
    for record in records:
        category = str(record.get("category") or "memory")
        summary = str(record.get("summary") or "").strip()
        command = str(record.get("command") or "").strip()
        result = str(record.get("result") or "").strip()
        evidence = str(record.get("evidence") or "").strip()
        text = f"{category}: {summary or command or evidence or record.get('id') or '-'}"
        if command and command not in text:
            text += f" (`{command}`"
            if result:
                text += f", {result}"
            text += ")"
        elif result:
            text += f" ({result})"
        if evidence and evidence not in text:
            text += f" Evidence: {evidence}"
        bullets.append(text)
    return bullets


def format_memory_summary(records: Iterable[dict[str, object]], limit: int = 5) -> str:
    visible = active_memory_records(records)
    if not visible:
        return "none"
    counts: dict[str, int] = {}
    for record in visible:
        category = str(record.get("category") or "memory")
        counts[category] = counts.get(category, 0) + 1
    parts = [f"{category}: {count}" for category, count in sorted(counts.items())]
    return ", ".join(parts[:limit])


def render_memory_summary(root: Path, workflow_slug: str, records: list[dict[str, object]] | None = None) -> None:
    records = load_memory_records(root, workflow_slug) if records is None else records
    visible = visible_memory_records(records)
    path = memory_summary_path(root, workflow_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Shared Learning Memory",
        "",
        f"- Workflow slug: {workflow_slug}",
        f"- Active entries: {len(active_memory_records(visible))}",
        f"- Summary: {format_memory_summary(visible)}",
        "",
        "## Categories",
        "- repo-convention: stable repository conventions or local implementation rules",
        "- failure-pattern: repeated failure modes, flakes, or risky sequences",
        "- interface-note: cross-module contracts, API shapes, or integration boundaries",
        "- validated-test-command: commands that were run and what result they produced",
        "- implementation-pattern: successful local design or coding patterns worth reusing",
        "",
        "## Entries",
        "| ID | Status | Category | Story | Summary | Command | Result | Evidence | Tags |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in visible:
        row = [
            str(record.get("id") or "-"),
            str(record.get("status") or "active"),
            str(record.get("category") or "-"),
            str(record.get("story_label") or story_label(str(record.get("story") or ""))),
            str(record.get("summary") or "-"),
            str(record.get("command") or "-"),
            str(record.get("result") or "-"),
            str(record.get("evidence") or "-"),
            ", ".join(str(item) for item in record.get("tags", []) or []) or "-",
        ]
        lines.append("| " + " | ".join(table_cell(item) for item in row) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def table_cell(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned.replace("|", "\\|") if cleaned else "-"


def ensure_memory_artifacts(root: Path, workflow_slug: str) -> None:
    memory_records_path(root, workflow_slug).parent.mkdir(parents=True, exist_ok=True)
    if not memory_records_path(root, workflow_slug).exists():
        memory_records_path(root, workflow_slug).write_text("", encoding="utf-8")
    if not memory_summary_path(root, workflow_slug).exists():
        render_memory_summary(root, workflow_slug, [])

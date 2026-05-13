#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


RETRY_COMMANDS = {"rework", "rework-item", "issue-advisor", "replan"}
DEFAULT_STATUSES = {"succeeded", "failed", "blocked", "cancelled", "unknown"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def workflow_path(root: Path, slug: str, relative: str) -> Path:
    return root / ".workflow" / slug / relative


def invocation_records_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "records/invocations.jsonl")


def accounting_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "accounting.json")


def accounting_summary_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "accounting.md")


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        values[key.strip()] = value.strip()
    return values


def active_story_from_state(root: Path, slug: str) -> str:
    state = parse_kv_list(workflow_path(root, slug, "state.md"))
    return state.get("Active items", "").split(",", 1)[0].strip()


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


def parse_directives(raw: str | None) -> dict[str, str]:
    if not raw or not raw.strip():
        return {}
    directives: dict[str, str] = {}
    for segment in [item.strip() for item in re.split(r"[;\n]+", raw) if item.strip()]:
        if ":" in segment:
            key, value = segment.split(":", 1)
        elif "=" in segment:
            key, value = segment.split("=", 1)
        else:
            continue
        directives[key.strip().lower()] = value.strip()
    if not directives:
        directives["summary"] = raw.strip()
    return directives


def parse_bool(value: object) -> bool:
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def parse_float(value: object) -> float:
    text = "" if value is None else str(value).strip().replace("$", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def parse_optional_float(value: object) -> float | None:
    text = "" if value is None else str(value).strip().replace("$", "")
    if not text or text.lower() in {"-", "none", "n/a", "unknown"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: object) -> int:
    text = "" if value is None else str(value).strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def normalize_status(value: object) -> str:
    status = str(value or "").strip().lower().replace("_", "-")
    if not status or status in {"-", "none"}:
        return "unknown"
    if status in {"success", "passed", "pass", "complete", "completed", "done"}:
        return "succeeded"
    if status in {"failure", "errored", "error"}:
        return "failed"
    if status in DEFAULT_STATUSES:
        return status
    return status


def current_head(root: Path) -> str:
    import subprocess

    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def make_invocation_id(record: dict[str, object], timestamp: str) -> str:
    seed = "|".join(
        [
            timestamp,
            str(record.get("workflow_slug") or ""),
            str(record.get("source") or ""),
            str(record.get("kind") or ""),
            str(record.get("command") or ""),
            str(record.get("role") or ""),
            str(record.get("story") or ""),
            str(record.get("summary") or ""),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    stamp = re.sub(r"[^0-9]", "", timestamp)[:14]
    return f"invocation-{stamp}-{digest}"


def normalize_record(record: dict[str, object]) -> dict[str, object]:
    normalized = dict(record)
    story = normalized.get("story") or normalized.get("active_story")
    story_id = normalize_story_id(story)
    normalized["story"] = story_id
    normalized["story_label"] = str(normalized.get("story_label") or story_label(story_id))
    normalized["source"] = str(normalized.get("source") or "manual").strip() or "manual"
    normalized["kind"] = str(normalized.get("kind") or "agent-run").strip() or "agent-run"
    normalized["command"] = str(normalized.get("command") or "").strip()
    normalized["requested_command"] = str(normalized.get("requested_command") or normalized.get("command") or "").strip()
    normalized["role"] = str(normalized.get("role") or "").strip()
    normalized["status"] = normalize_status(normalized.get("status"))
    normalized["retry"] = bool(normalized.get("retry")) or bool(normalized.get("retry_of")) or normalized.get("command") in RETRY_COMMANDS
    normalized["avoided_rework"] = bool(normalized.get("avoided_rework"))
    normalized["elapsed_seconds"] = round(max(0.0, parse_float(normalized.get("elapsed_seconds"))), 3)
    cost = parse_optional_float(normalized.get("estimated_cost_usd"))
    normalized["cost_known"] = bool(normalized.get("cost_known")) or cost is not None
    normalized["estimated_cost_usd"] = round(max(0.0, cost), 6) if cost is not None else None
    normalized["input_tokens"] = max(0, parse_int(normalized.get("input_tokens")))
    normalized["output_tokens"] = max(0, parse_int(normalized.get("output_tokens")))
    normalized["model"] = str(normalized.get("model") or "").strip()
    normalized["run_id"] = str(normalized.get("run_id") or "").strip()
    normalized["execution_id"] = str(normalized.get("execution_id") or "").strip()
    normalized["parent_invocation_id"] = str(normalized.get("parent_invocation_id") or "").strip()
    normalized["agent_node_id"] = str(normalized.get("agent_node_id") or "").strip()
    normalized["reasoner_id"] = str(normalized.get("reasoner_id") or "").strip()
    normalized["attempt"] = max(0, parse_int(normalized.get("attempt")))
    normalized["transport_retry_count"] = max(0, parse_int(normalized.get("transport_retry_count")))
    normalized["cost_source"] = str(normalized.get("cost_source") or ("reported" if normalized["cost_known"] else "unknown")).strip()
    normalized["duration_ms"] = max(0, parse_int(normalized.get("duration_ms")))
    if normalized["duration_ms"] and not normalized["elapsed_seconds"]:
        normalized["elapsed_seconds"] = round(normalized["duration_ms"] / 1000, 3)
    normalized["summary"] = str(normalized.get("summary") or "").strip()
    normalized["evidence"] = str(normalized.get("evidence") or "").strip()
    normalized["retry_of"] = str(normalized.get("retry_of") or "").strip()
    normalized["transaction_id"] = str(normalized.get("transaction_id") or "").strip()
    normalized["current_head"] = str(normalized.get("current_head") or "").strip()
    return normalized


def load_invocation_records(root: Path, slug: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in read_text(invocation_records_path(root, slug)).splitlines():
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


def write_invocation_record(root: Path, slug: str, record: dict[str, object]) -> dict[str, object]:
    timestamp = str(record.get("recorded_at") or utc_now())
    normalized = normalize_record(record)
    normalized["schema_version"] = 1
    normalized["workflow_slug"] = slug
    normalized["recorded_at"] = timestamp
    normalized["id"] = str(normalized.get("id") or make_invocation_id(normalized, timestamp))
    path = invocation_records_path(root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized, sort_keys=True) + "\n")
    render_accounting(root, slug)
    return normalized


def summarize_records(records: Iterable[dict[str, object]]) -> dict[str, object]:
    totals = {
        "invocation_count": 0,
        "retry_count": 0,
        "avoided_rework_count": 0,
        "elapsed_seconds": 0.0,
        "estimated_cost_usd": 0.0,
        "known_cost_record_count": 0,
        "unknown_cost_record_count": 0,
        "input_tokens": 0,
        "output_tokens": 0,
    }
    by_story: dict[str, dict[str, object]] = {}
    by_kind: dict[str, int] = {}
    by_command: dict[str, int] = {}
    by_status: dict[str, int] = {}
    last_recorded_at = ""
    for record in records:
        totals["invocation_count"] += 1
        if record.get("retry"):
            totals["retry_count"] += 1
        if record.get("avoided_rework"):
            totals["avoided_rework_count"] += 1
        totals["elapsed_seconds"] = round(float(totals["elapsed_seconds"]) + parse_float(record.get("elapsed_seconds")), 3)
        if record.get("cost_known"):
            totals["known_cost_record_count"] += 1
            totals["estimated_cost_usd"] = round(float(totals["estimated_cost_usd"]) + parse_float(record.get("estimated_cost_usd")), 6)
        else:
            totals["unknown_cost_record_count"] += 1
        totals["input_tokens"] += parse_int(record.get("input_tokens"))
        totals["output_tokens"] += parse_int(record.get("output_tokens"))
        story = str(record.get("story") or "")
        story_key = story or "repo"
        story_bucket = by_story.setdefault(
            story_key,
            {
                "story": story,
                "story_label": story_label(story),
                "invocation_count": 0,
                "retry_count": 0,
                "avoided_rework_count": 0,
                "elapsed_seconds": 0.0,
                "estimated_cost_usd": 0.0,
                "known_cost_record_count": 0,
                "unknown_cost_record_count": 0,
            },
        )
        story_bucket["invocation_count"] = int(story_bucket["invocation_count"]) + 1
        if record.get("retry"):
            story_bucket["retry_count"] = int(story_bucket["retry_count"]) + 1
        if record.get("avoided_rework"):
            story_bucket["avoided_rework_count"] = int(story_bucket["avoided_rework_count"]) + 1
        story_bucket["elapsed_seconds"] = round(float(story_bucket["elapsed_seconds"]) + parse_float(record.get("elapsed_seconds")), 3)
        if record.get("cost_known"):
            story_bucket["known_cost_record_count"] = int(story_bucket["known_cost_record_count"]) + 1
            story_bucket["estimated_cost_usd"] = round(float(story_bucket["estimated_cost_usd"]) + parse_float(record.get("estimated_cost_usd")), 6)
        else:
            story_bucket["unknown_cost_record_count"] = int(story_bucket["unknown_cost_record_count"]) + 1
        kind = str(record.get("kind") or "unknown")
        command = str(record.get("command") or "-")
        status = str(record.get("status") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
        by_command[command] = by_command.get(command, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        last_recorded_at = max(last_recorded_at, str(record.get("recorded_at") or ""))
    return {
        "totals": totals,
        "by_story": dict(sorted(by_story.items())),
        "by_kind": dict(sorted(by_kind.items())),
        "by_command": dict(sorted(by_command.items())),
        "by_status": dict(sorted(by_status.items())),
        "last_recorded_at": last_recorded_at,
    }


def dollars(value: object) -> str:
    amount = parse_optional_float(value) or 0.0
    return f"${amount:.6f}".rstrip("0").rstrip(".") if amount else "$0"


def cost_display(record: dict[str, object]) -> str:
    if not record.get("cost_known"):
        return "unknown"
    return dollars(record.get("estimated_cost_usd"))


def format_seconds(value: object) -> str:
    seconds = parse_float(value)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}m"
    return f"{minutes / 60:.1f}h"


def format_accounting_summary(records: Iterable[dict[str, object]], story: str | None = None) -> str:
    normalized_records = [normalize_record(record) for record in records]
    if story:
        story_id = normalize_story_id(story)
        normalized_records = [record for record in normalized_records if str(record.get("story") or "") == story_id]
    if not normalized_records:
        return "none"
    summary = summarize_records(normalized_records)
    totals = summary["totals"]
    return (
        f"{totals['invocation_count']} invocation(s), "
        f"{totals['retry_count']} retry marker(s), "
        f"{totals['avoided_rework_count']} avoided-rework marker(s), "
        f"{format_seconds(totals['elapsed_seconds'])}, "
        f"{dollars(totals['estimated_cost_usd'])} known cost"
        + (f", {totals['unknown_cost_record_count']} unknown-cost record(s)" if totals.get("unknown_cost_record_count") else "")
    )


def render_markdown(slug: str, records: list[dict[str, object]], summary: dict[str, object]) -> str:
    totals = summary.get("totals", {})
    by_story = summary.get("by_story", {})
    by_story = by_story if isinstance(by_story, dict) else {}
    lines = [
        "# Invocation Accounting",
        "",
        f"- Workflow slug: {slug}",
        f"- Last recorded at: {summary.get('last_recorded_at', '-') or '-'}",
        f"- Invocation count: {totals.get('invocation_count', 0)}",
        f"- Retry markers: {totals.get('retry_count', 0)}",
        f"- Avoided rework markers: {totals.get('avoided_rework_count', 0)}",
        f"- Elapsed time: {format_seconds(totals.get('elapsed_seconds', 0))}",
        f"- Estimated known cost: {dollars(totals.get('estimated_cost_usd', 0))}",
        f"- Known-cost records: {totals.get('known_cost_record_count', 0)}",
        f"- Unknown-cost records: {totals.get('unknown_cost_record_count', 0)}",
        f"- Tokens: input {totals.get('input_tokens', 0)}, output {totals.get('output_tokens', 0)}",
        "",
        "## By Story",
        "",
        "| Story | Invocations | Retries | Avoided Rework | Elapsed | Known Cost | Unknown Cost Records |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if by_story:
        for bucket in by_story.values():
            if not isinstance(bucket, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(bucket.get("story_label") or "-"),
                        str(bucket.get("invocation_count", 0)),
                        str(bucket.get("retry_count", 0)),
                        str(bucket.get("avoided_rework_count", 0)),
                        format_seconds(bucket.get("elapsed_seconds", 0)),
                        dollars(bucket.get("estimated_cost_usd", 0)),
                        str(bucket.get("unknown_cost_record_count", 0)),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | 0 | 0 | 0 | 0.0s | $0 | 0 |")
    lines.extend(
        [
            "",
            "## Recent Records",
            "",
            "| Recorded | Source | Kind | Story | Command | Role | Status | Retry | Avoided Rework | Elapsed | Cost | Summary |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for record in records[-20:]:
        row = [
            str(record.get("recorded_at") or "-"),
            str(record.get("source") or "-"),
            str(record.get("kind") or "-"),
            str(record.get("story_label") or "-"),
            str(record.get("command") or "-"),
            str(record.get("role") or "-"),
            str(record.get("status") or "-"),
            "yes" if record.get("retry") else "no",
            "yes" if record.get("avoided_rework") else "no",
            format_seconds(record.get("elapsed_seconds", 0)),
            cost_display(record),
            str(record.get("summary") or "-"),
        ]
        lines.append("| " + " | ".join(item.replace("|", "\\|") for item in row) + " |")
    if not records:
        lines.append("| - | - | - | - | - | - | - | no | no | 0.0s | unknown | - |")
    lines.append("")
    return "\n".join(lines)


def render_accounting(root: Path, slug: str) -> dict[str, object]:
    records = load_invocation_records(root, slug)
    summary = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": utc_now(),
        **summarize_records(records),
    }
    write_text(accounting_path(root, slug), json.dumps(summary, indent=2, sort_keys=True) + "\n")
    write_text(accounting_summary_path(root, slug), render_markdown(slug, records, summary))
    return summary


def record_manual_invocation(root: Path, slug: str, directive_text: str | None) -> dict[str, object]:
    directives = parse_directives(directive_text)
    story = directives.get("story") or directives.get("active-story") or active_story_from_state(root, slug)
    record = {
        "source": directives.get("source") or "manual",
        "kind": directives.get("kind") or directives.get("type") or "agent-run",
        "story": story,
        "role": directives.get("role") or directives.get("agent") or "",
        "command": directives.get("command") or directives.get("tool") or "",
        "requested_command": directives.get("requested-command") or directives.get("command") or "",
        "status": directives.get("status") or "succeeded",
        "retry": parse_bool(directives.get("retry")),
        "retry_of": directives.get("retry-of") or directives.get("retry_of") or "",
        "avoided_rework": parse_bool(directives.get("avoided-rework") or directives.get("avoided_rework")),
        "elapsed_seconds": parse_float(directives.get("elapsed") or directives.get("elapsed-seconds") or directives.get("seconds")),
        "estimated_cost_usd": parse_optional_float(directives.get("cost") or directives.get("estimated-cost") or directives.get("estimated-cost-usd")),
        "cost_known": parse_optional_float(directives.get("cost") or directives.get("estimated-cost") or directives.get("estimated-cost-usd")) is not None,
        "cost_source": directives.get("cost-source") or directives.get("cost_source") or "",
        "input_tokens": parse_int(directives.get("input-tokens") or directives.get("tokens-in") or directives.get("prompt-tokens")),
        "output_tokens": parse_int(directives.get("output-tokens") or directives.get("tokens-out") or directives.get("completion-tokens")),
        "model": directives.get("model") or "",
        "run_id": directives.get("run-id") or directives.get("run_id") or "",
        "execution_id": directives.get("execution-id") or directives.get("execution_id") or directives.get("invocation-id") or "",
        "parent_invocation_id": directives.get("parent-invocation-id") or directives.get("parent_invocation_id") or "",
        "agent_node_id": directives.get("agent-node-id") or directives.get("agent_node_id") or "",
        "reasoner_id": directives.get("reasoner-id") or directives.get("reasoner_id") or "",
        "attempt": parse_int(directives.get("attempt")),
        "transport_retry_count": parse_int(directives.get("transport-retry-count") or directives.get("transport_retry_count")),
        "summary": directives.get("summary") or directives.get("note") or "",
        "evidence": directives.get("evidence") or directives.get("url") or "",
        "current_head": current_head(root),
    }
    return write_invocation_record(root, slug, record)


def record_command_invocation(
    root: Path,
    slug: str,
    command: str,
    requested_command: str,
    before_state: dict[str, str],
    after_state: dict[str, str],
    elapsed_seconds: float,
    transaction_id: str,
    resumed: bool,
) -> dict[str, object]:
    story = after_state.get("Active items") or before_state.get("Active items") or active_story_from_state(root, slug)
    retry = command in RETRY_COMMANDS or str(after_state.get("Next action") or "").lower().startswith("retry ")
    source = "workflow-resume" if resumed else "workflow-command"
    summary = f"{command}: {before_state.get('Current stage', '-') or '-'} -> {after_state.get('Current stage', '-') or '-'}; gate={after_state.get('Human gate status', '-') or '-'}"
    record = {
        "source": source,
        "kind": "workflow-command",
        "story": story,
        "command": command,
        "requested_command": requested_command,
        "status": "succeeded",
        "retry": retry,
        "avoided_rework": resumed,
        "elapsed_seconds": elapsed_seconds,
        "estimated_cost_usd": 0.0,
        "cost_known": True,
        "cost_source": "workflow-control",
        "summary": summary,
        "evidence": after_state.get("Blocked reason") or after_state.get("Item note") or after_state.get("Next action") or "",
        "transaction_id": transaction_id,
        "current_head": current_head(root),
    }
    return write_invocation_record(root, slug, record)


def record_agent_result_invocation(
    root: Path,
    slug: str,
    report: dict[str, object],
    source: str,
    role: str,
    story: str,
    status: str,
) -> dict[str, object] | None:
    usage_keys = {
        "model",
        "input-tokens",
        "output-tokens",
        "cost-usd",
        "estimated-cost-usd",
        "elapsed-seconds",
        "duration-ms",
        "invocation-id",
        "execution-id",
        "run-id",
        "attempt",
        "retry-count",
        "transport-retry-count",
    }
    if not any(key in report and str(report.get(key) or "").strip() for key in usage_keys):
        return None
    cost = parse_optional_float(report.get("cost-usd") or report.get("estimated-cost-usd"))
    record = {
        "source": "agent-result",
        "kind": "delegated-agent",
        "story": story,
        "role": role,
        "command": "team-sync",
        "status": status or "unknown",
        "retry": parse_int(report.get("retry-count")) > 0,
        "elapsed_seconds": parse_optional_float(report.get("elapsed-seconds")) or 0.0,
        "duration_ms": parse_int(report.get("duration-ms")),
        "estimated_cost_usd": cost,
        "cost_known": cost is not None,
        "cost_source": str(report.get("cost-source") or "agent-report").strip(),
        "input_tokens": parse_int(report.get("input-tokens")),
        "output_tokens": parse_int(report.get("output-tokens")),
        "model": str(report.get("model") or "").strip(),
        "run_id": str(report.get("run-id") or "").strip(),
        "execution_id": str(report.get("execution-id") or report.get("invocation-id") or "").strip(),
        "parent_invocation_id": str(report.get("parent-invocation-id") or "").strip(),
        "agent_node_id": str(report.get("agent-node-id") or "").strip(),
        "reasoner_id": str(report.get("reasoner-id") or "").strip(),
        "attempt": parse_int(report.get("attempt")),
        "transport_retry_count": parse_int(report.get("transport-retry-count")),
        "summary": str(report.get("summary") or "").strip(),
        "evidence": source,
        "current_head": current_head(root),
    }
    return write_invocation_record(root, slug, record)


def ensure_accounting_artifacts(root: Path, slug: str) -> None:
    invocation_records_path(root, slug).parent.mkdir(parents=True, exist_ok=True)
    if not accounting_path(root, slug).exists() or not accounting_summary_path(root, slug).exists():
        render_accounting(root, slug)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record or render wrkflw invocation accounting.")
    parser.add_argument("command", choices=["record", "render"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "record":
        record = record_manual_invocation(root, args.slug, args.evidence)
        print(f"accounting-record {record.get('id')}")
    else:
        summary = render_accounting(root, args.slug)
        print(f"accounting-render {summary.get('totals', {}).get('invocation_count', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

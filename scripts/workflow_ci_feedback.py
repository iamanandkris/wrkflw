#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from workflow_failure_classification import classification


PASSING_STATUSES = {"passed", "success", "succeeded", "ok", "green"}
FAILING_STATUSES = {"failed", "failure", "red"}
TIMEOUT_STATUSES = {"timed_out", "timed-out", "timeout"}
PENDING_STATUSES = {"pending", "running", "queued", "in_progress", "in-progress"}
ERROR_STATUSES = {"error", "errored", "cancelled", "canceled", "no_checks", "no-checks", "missing"}
ACTION_STATUSES = {"failed", "timed_out", "error", "cancelled", "no_checks", "pending"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def ci_feedback_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "ci-feedback.json")


def ci_feedback_summary_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "ci-feedback.md")


def ci_feedback_records_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "records/ci-feedback.jsonl")


def ci_run_path(root: Path, slug: str, run_id: str) -> Path:
    return workflow_path(root, slug, f"ci-runs/{slugify(run_id)}.json")


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_head(root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        values[key.strip()] = value.strip()
    return values


def active_story(root: Path, slug: str) -> str:
    state = parse_kv_list(workflow_path(root, slug, "state.md"))
    return state.get("Active items", "").split(",", 1)[0].strip()


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


def split_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text or text == "-":
        return []
    return [item.strip() for item in re.split(r"\s*\|\s*|\s*,\s*|\s*;\s*", text) if item.strip()]


def normalize_status(value: object) -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    if text in PASSING_STATUSES:
        return "passed"
    if text in FAILING_STATUSES:
        return "failed"
    if text in TIMEOUT_STATUSES:
        return "timed_out"
    if text in PENDING_STATUSES:
        return "pending"
    if text in {"cancelled", "canceled"}:
        return "cancelled"
    if text in {"no_checks", "no-checks", "no checks"}:
        return "no_checks"
    if text in ERROR_STATUSES:
        return "error"
    return text or "missing"


def compact(value: object, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def slugify(value: object) -> str:
    text = compact(value, 80).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or "ci"


def input_hashes(root: Path, slug: str) -> dict[str, str]:
    return {
        "merge-gate.json": sha256_file(workflow_path(root, slug, "merge-gate.json")),
        "merge-apply.json": sha256_file(workflow_path(root, slug, "merge-apply.json")),
        "integration-test-gate.json": sha256_file(workflow_path(root, slug, "integration-test-gate.json")),
    }


def finding_type_for(status: str, failure: str) -> str:
    lower = failure.lower()
    if status == "timed_out":
        return "ci_timeout"
    if status in {"pending", "no_checks"}:
        return "ci_missing_or_pending"
    if status in {"error", "cancelled"}:
        return "ci_infrastructure"
    if any(keyword in lower for keyword in ["test", "spec", "assert", "pytest", "jest", "sbt", "mvn"]):
        return "test_failure"
    if any(keyword in lower for keyword in ["lint", "format", "style"]):
        return "lint_failure"
    if any(keyword in lower for keyword in ["build", "compile", "typecheck", "type check"]):
        return "build_failure"
    return "ci_failure"


def fix_task_for(story: str, check: dict[str, object]) -> dict[str, object]:
    name = compact(check.get("name") or "ci")
    status = str(check.get("status") or "")
    failure = compact(check.get("failure") or check.get("summary") or f"CI check `{name}` reported {status}.")
    finding_type = finding_type_for(status, failure)
    failure_classification = classification(
        finding_type,
        source="ci-feedback",
        summary=failure,
        retryable=bool(check.get("retryable")) or status in {"timed_out", "pending", "error"},
        severity="high" if status in {"failed", "timed_out"} else "medium",
    )
    return {
        "id": f"ci-{slugify(name)}-{slugify(status)}",
        "story": story or "-",
        "check": name,
        "type": finding_type,
        "failure_class": failure_classification["failure_class"],
        "failure_category": failure_classification["failure_category"],
        "retryable": failure_classification["retryable"],
        "recommended_gate": failure_classification["recommended_gate"],
        "failure_classification": failure_classification,
        "severity": "high" if status in {"failed", "timed_out"} else "medium",
        "status": "open",
        "summary": failure,
        "recommended_action": f"Fix or explicitly resolve `{name}` before review approval.",
        "suggested_command": f"wrkflw:rework-item \"{story or 'current story'}: fix CI check {name}\"",
    }


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def render_markdown(payload: dict[str, object]) -> str:
    checks = payload.get("checks", [])
    fix_tasks = payload.get("fix_tasks", [])
    blockers = payload.get("blockers", [])
    warnings = payload.get("warnings", [])
    lines = [
        "# CI Feedback",
        "",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Active story: {payload.get('active_story', '-') or '-'}",
        f"- Status: {payload.get('status', '-')}",
        f"- Expected HEAD SHA: `{payload.get('expected_head_sha', '-') or '-'}`",
        f"- Observed HEAD SHA: `{payload.get('observed_head_sha', '-') or '-'}`",
        f"- Summary: {payload.get('summary', '-')}",
        f"- Failure class: {payload.get('failure_class', '-') or '-'}",
        f"- Failure category: {payload.get('failure_category', '-') or '-'}",
        f"- Recommended gate: {payload.get('recommended_gate', '-') or '-'}",
        f"- Run result: `{payload.get('run_result_path', '-') or '-'}`",
        "",
        "## Checks",
        "",
        "| Check | Status | URL | Failure |",
        "| --- | --- | --- | --- |",
    ]
    if isinstance(checks, list) and checks:
        for check in checks:
            if isinstance(check, dict):
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            compact(check.get("name", "-")).replace("|", "\\|"),
                            compact(check.get("status", "-")).replace("|", "\\|"),
                            compact(check.get("url", "-") or "-").replace("|", "\\|"),
                            compact(check.get("failure", "-") or "-").replace("|", "\\|"),
                        ]
                    )
                    + " |"
                )
    else:
        lines.append("| - | - | - | - |")
    lines.extend(["", "## Fix Tasks"])
    if isinstance(fix_tasks, list) and fix_tasks:
        for task in fix_tasks:
            if isinstance(task, dict):
                lines.append(f"- `{task.get('id', '-')}`: {task.get('summary', '-')}")
    else:
        lines.append("- none")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in blockers if str(item).strip()) if isinstance(blockers, list) and blockers else lines.append("- none")
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in warnings if str(item).strip()) if isinstance(warnings, list) and warnings else lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def run_ci_feedback(root: Path, slug: str, directive_text: str | None = None) -> dict[str, object]:
    generated_at = utc_now()
    directives = parse_directives(directive_text)
    story = directives.get("story", "").strip() or active_story(root, slug)
    expected_head = current_head(root)
    observed_head = (
        directives.get("head-sha")
        or directives.get("head sha")
        or directives.get("head_sha")
        or directives.get("sha")
        or directives.get("commit")
        or expected_head
    ).strip()
    check_name = (
        directives.get("check")
        or directives.get("check-name")
        or directives.get("name")
        or directives.get("workflow")
        or "ci"
    ).strip()
    status = normalize_status(directives.get("status") or directives.get("conclusion") or directives.get("result"))
    log_excerpt = (directives.get("logs") or directives.get("log") or "").strip()
    failure = (
        directives.get("failure")
        or directives.get("finding")
        or directives.get("error")
        or log_excerpt
        or directives.get("summary")
        or ""
    ).strip()
    url = directives.get("url") or directives.get("run-url") or directives.get("details") or ""
    artifacts = split_values(directives.get("artifact") or directives.get("artifacts"))
    retryable_value = (directives.get("retryable") or "").strip().lower()
    retryable = retryable_value in {"true", "yes", "1", "on"}
    blockers: list[str] = []
    warnings: list[str] = []
    if status == "missing":
        blockers.append("CI feedback requires a status.")
    if expected_head and observed_head and observed_head != expected_head:
        blockers.append("CI feedback is stale because the reported head SHA does not match repository HEAD.")
    if status in ACTION_STATUSES and not failure and status not in {"pending", "no_checks"}:
        warnings.append("CI feedback did not include a failure summary.")
    provider = directives.get("provider", "") or "manual"
    run_id = (directives.get("run-id") or directives.get("run id") or "").strip()
    if not run_id:
        run_id_seed = f"{slug}|{story}|{check_name}|{status}|{observed_head}|{generated_at}"
        run_id = "ci-" + hashlib.sha256(run_id_seed.encode("utf-8")).hexdigest()[:12]
    check = {
        "name": check_name,
        "status": status,
        "url": url,
        "details_url": url,
        "failure": failure,
        "logs_excerpt": compact(log_excerpt, 1000),
        "artifacts": artifacts,
        "retryable": retryable,
        "provider": provider,
        "pr_number": directives.get("pr") or directives.get("pr-number") or directives.get("pr number") or "",
        "run_id": run_id,
        "expected_head_sha": expected_head,
        "observed_head_sha": observed_head,
    }
    fix_tasks = [] if status == "passed" else [fix_task_for(story, check)]
    failure_classifications = [
        task["failure_classification"]
        for task in fix_tasks
        if isinstance(task, dict) and isinstance(task.get("failure_classification"), dict)
    ]
    top_failure = failure_classifications[0] if failure_classifications else {}
    if status == "passed" and not blockers:
        overall_status = "ready"
        summary = f"CI check `{check_name}` passed for the recorded head."
    elif blockers:
        overall_status = "blocked"
        summary = "CI feedback is blocked or stale."
    else:
        overall_status = "action_required"
        summary = f"CI check `{check_name}` reported `{status}`."
    run_path = ci_run_path(root, slug, run_id)
    run_result_relative = str(run_path.relative_to(root))
    payload = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": generated_at,
        "command": "ci-feedback",
        "active_story": story,
        "status": overall_status,
        "summary": summary,
        "head_sha": observed_head,
        "current_head": expected_head,
        "expected_head_sha": expected_head,
        "observed_head_sha": observed_head,
        "provider": provider,
        "run_id": run_id,
        "run_result_path": run_result_relative,
        "checks": [check],
        "fix_tasks": fix_tasks,
        "failure_class": top_failure.get("failure_class", ""),
        "failure_category": top_failure.get("failure_category", ""),
        "retryable": top_failure.get("retryable", False),
        "recommended_gate": top_failure.get("recommended_gate", ""),
        "failure_classification": top_failure,
        "failure_classifications": failure_classifications,
        "blockers": blockers,
        "warnings": warnings,
        "input_hashes": input_hashes(root, slug),
    }
    write_text(run_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_text(ci_feedback_path(root, slug), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_text(ci_feedback_summary_path(root, slug), render_markdown(payload))
    append_jsonl(
        ci_feedback_records_path(root, slug),
        {
            "schema_version": 1,
            "recorded_at": generated_at,
            "workflow_slug": slug,
            "active_story": story,
            "status": overall_status,
            "provider": provider,
            "run_id": run_id,
            "run_result_path": run_result_relative,
            "check": check_name,
            "check_status": status,
            "failure_class": top_failure.get("failure_class", ""),
            "failure_category": top_failure.get("failure_category", ""),
            "retryable": top_failure.get("retryable", False),
            "recommended_gate": top_failure.get("recommended_gate", ""),
            "head_sha": observed_head,
            "current_head": expected_head,
            "expected_head_sha": expected_head,
            "observed_head_sha": observed_head,
            "fix_task_count": len(fix_tasks),
        },
    )
    return payload


def default_ci_feedback(slug: str) -> str:
    return f"""# CI Feedback

- Workflow slug: {slug}
- Status:
- Expected HEAD SHA:
- Observed HEAD SHA:
- Summary:

## Checks

| Check | Status | URL | Failure |
| --- | --- | --- | --- |
| - | - | - | - |

## Fix Tasks
- none
"""


def ensure_ci_feedback_artifact(root: Path, slug: str) -> None:
    path = ci_feedback_summary_path(root, slug)
    if not path.exists():
        write_text(path, default_ci_feedback(slug))
    ci_feedback_records_path(root, slug).parent.mkdir(parents=True, exist_ok=True)
    workflow_path(root, slug, "ci-runs").mkdir(parents=True, exist_ok=True)


def ci_feedback_block(root: Path, slug: str, stage: str) -> tuple[bool, str]:
    if stage not in {"review", "release-planning", "done"}:
        return False, ""
    path = ci_feedback_path(root, slug)
    if not path.exists():
        return False, ""
    payload = read_json(path)
    if not payload:
        return True, "CI feedback artifact is unreadable; rerun wrkflw:ci-feedback."
    status = str(payload.get("status") or "").strip().lower()
    if status in {"", "not_recorded"}:
        return False, ""
    head = current_head(root)
    if head and str(payload.get("head_sha") or "") != head:
        return True, "CI feedback is stale because repository HEAD changed; rerun wrkflw:ci-feedback."
    story = active_story(root, slug)
    if story and str(payload.get("active_story") or "") != story:
        return True, "CI feedback is stale because the active story changed; rerun wrkflw:ci-feedback."
    recorded_hashes = payload.get("input_hashes", {})
    recorded_hashes = recorded_hashes if isinstance(recorded_hashes, dict) else {}
    for relative, digest in input_hashes(root, slug).items():
        if str(recorded_hashes.get(relative) or "") != digest:
            return True, f"CI feedback is stale because `{relative}` changed; rerun wrkflw:ci-feedback."
    if status != "ready":
        blockers = payload.get("blockers", [])
        if isinstance(blockers, list) and blockers:
            return True, "CI feedback is blocked: " + "; ".join(str(item) for item in blockers[:3])
        tasks = payload.get("fix_tasks", [])
        task_count = len(tasks) if isinstance(tasks, list) else 0
        return True, f"CI feedback requires fixes or retry for {task_count} check(s)."
    return False, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Record typed CI feedback and generate fix tasks.")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()
    payload = run_ci_feedback(Path(args.root).resolve(), args.slug, args.evidence)
    print(f"ci-feedback {payload.get('status')}")
    return 1 if payload.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())

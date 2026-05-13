#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from workflow_failure_classification import classification, classify_text


MAX_EXECUTION_OUTPUT_CHARS = 4000
MAX_TIMEOUT_SECONDS = 900
DEFAULT_TIMEOUT_SECONDS = 120
FORBIDDEN_EXECUTABLES = {"bash", "sh", "zsh", "fish", "ksh", "csh", "tcsh"}
FORBIDDEN_INLINE_FLAGS = {"-c", "-e", "--eval", "--execute", "-Command", "-EncodedCommand"}
SAFE_ENV_ALLOWLIST = {
    "CI",
    "HOME",
    "LANG",
    "LC_ALL",
    "PATH",
    "PYTHONDONTWRITEBYTECODE",
    "TMPDIR",
}

SENSITIVE_PATH_PATTERNS = [
    r"(^|/)api(/|$)",
    r"(^|/)auth(/|$)",
    r"(^|/)config(/|$)",
    r"(^|/)contracts?(/|$)",
    r"(^|/)db(/|$)",
    r"(^|/)database(/|$)",
    r"(^|/)migrations?(/|$)",
    r"(^|/)routes?(/|$)",
    r"(^|/)schemas?(/|$)",
    r"(^|/)services?(/|$)",
    r"(^|/)shared(/|$)",
    r"(^|/)transport(/|$)",
    r"(^|/)package(-lock)?\.json$",
    r"(^|/)pnpm-lock\.yaml$",
    r"(^|/)yarn\.lock$",
    r"(^|/)build\.sbt$",
    r"(^|/)pom\.xml$",
    r"(^|/)Cargo\.toml$",
    r"(^|/)go\.mod$",
    r"(^|/)pyproject\.toml$",
    r"(^|/)requirements.*\.txt$",
    r"\.sql$",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_git(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def integration_gate_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "integration-test-gate.json"


def integration_gate_summary_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "integration-test-gate.md"


def integration_allowlist_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "integration-test-allowlist.json"


def integration_allowlist_summary_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "integration-test-allowlist.md"


def merge_gate_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "merge-gate.json"


def merge_apply_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "merge-apply.json"


def dag_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "dag.json"


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(payload: object) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def tail_text(text: str, limit: int = MAX_EXECUTION_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def redact_output(text: str) -> str:
    redacted_lines: list[str] = []
    key_value_secret = re.compile(r"(?i)(\b(?:token|secret|password|api[_-]?key|authorization)\b\s*[:=]\s*)(.+)$")
    auth_scheme_secret = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]+")
    for line in text.splitlines():
        redacted = key_value_secret.sub(lambda match: match.group(1) + "<redacted>", line)
        redacted = auth_scheme_secret.sub(lambda match: match.group(1) + " <redacted>", redacted)
        redacted_lines.append(redacted)
    return "\n".join(redacted_lines)


def relative_or_absolute_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


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


def table_cell(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    return re.sub(r"\s+", " ", text).replace("|", "\\|")


def merge_gate_binding(root: Path, slug: str, merge_gate: dict[str, object]) -> dict[str, object]:
    entries = merge_gate.get("entries", [])
    entries = entries if isinstance(entries, list) else []
    changed_paths_payload = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changed_paths_payload.append(
            {
                "lane_id": entry.get("lane_id", ""),
                "branch": entry.get("branch", ""),
                "changed_paths": list_value(entry.get("changed_paths")),
                "status": entry.get("status", ""),
            }
        )
    path = merge_gate_path(root, slug)
    return {
        "path": str(path.relative_to(root)) if path.exists() else str(path),
        "sha256": sha256_file(path),
        "generated_at": merge_gate.get("generated_at", ""),
        "status": merge_gate.get("status", ""),
        "base_commit": merge_gate.get("base_commit", ""),
        "current_head": merge_gate.get("current_head", ""),
        "changed_paths_sha256": sha256_json(changed_paths_payload),
    }


def merge_gate_has_changed_paths(merge_gate: dict[str, object]) -> bool:
    entries = merge_gate.get("entries", [])
    entries = entries if isinstance(entries, list) else []
    for entry in entries:
        if isinstance(entry, dict) and list_value(entry.get("changed_paths")):
            return True
    return False


def merge_apply_binding(root: Path, slug: str, merge_apply: dict[str, object]) -> dict[str, object]:
    path = merge_apply_path(root, slug)
    return {
        "path": str(path.relative_to(root)) if path.exists() else str(path),
        "sha256": sha256_file(path),
        "generated_at": merge_apply.get("generated_at", ""),
        "status": merge_apply.get("status", ""),
        "pre_head": merge_apply.get("pre_head", ""),
        "post_head": merge_apply.get("post_head", ""),
        "candidate_head": merge_apply.get("candidate_head", ""),
        "checkpoint_ref": merge_apply.get("checkpoint_ref", ""),
    }


def dag_binding(root: Path, slug: str) -> dict[str, object]:
    path = dag_path(root, slug)
    return {
        "path": str(path.relative_to(root)) if path.exists() else str(path),
        "sha256": sha256_file(path),
    }


def dag_nodes_by_id(root: Path, slug: str) -> dict[str, dict[str, object]]:
    payload = read_json(dag_path(root, slug))
    nodes = payload.get("nodes", [])
    result: dict[str, dict[str, object]] = {}
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and node.get("id"):
                result[str(node["id"])] = node
    return result


def sensitive_path_reasons(changed_paths: list[str]) -> list[str]:
    reasons: list[str] = []
    for path in changed_paths:
        for pattern in SENSITIVE_PATH_PATTERNS:
            if re.search(pattern, path):
                reasons.append(f"`{path}` matches integration-sensitive pattern `{pattern}`")
                break
    return reasons


def requirement_decision(root: Path, slug: str, merge_gate: dict[str, object]) -> dict[str, object]:
    entries = merge_gate.get("entries", [])
    entries = entries if isinstance(entries, list) else []
    dag_nodes = dag_nodes_by_id(root, slug)
    reasons: list[str] = []
    warnings: list[str] = []
    lane_decisions: list[dict[str, object]] = []
    changed_lane_count = 0
    all_changed_paths: list[str] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        lane_id = str(entry.get("lane_id") or "")
        changed_paths = list_value(entry.get("changed_paths"))
        if changed_paths:
            changed_lane_count += 1
            all_changed_paths.extend(changed_paths)
        node = dag_nodes.get(lane_id, {})
        node_reasons: list[str] = []
        if changed_paths:
            if node.get("needs_deeper_qa"):
                node_reasons.append("story DAG marks this lane as needing deeper QA")
            if str(node.get("risk") or "").strip().lower() == "high":
                node_reasons.append("story DAG marks this lane as high risk")
            validation = " ".join(list_value(node.get("validation"))).lower()
            if "integration" in validation or "end-to-end" in validation or "e2e" in validation:
                node_reasons.append("story validation text calls for integration-style testing")
        if node_reasons:
            reasons.extend(f"{lane_id}: {item}" for item in node_reasons)
        lane_decisions.append(
            {
                "lane_id": lane_id,
                "story": entry.get("story", ""),
                "changed_paths": changed_paths,
                "requires_integration_reasons": node_reasons,
            }
        )

    if changed_lane_count > 1:
        reasons.append(f"{changed_lane_count} parallel lanes have committed changes")
    sensitive = sensitive_path_reasons(all_changed_paths)
    reasons.extend(sensitive)
    if not all_changed_paths:
        warnings.append("merge gate contains no committed changed paths")

    return {
        "required": bool(reasons),
        "reasons": reasons,
        "warnings": warnings,
        "changed_lane_count": changed_lane_count,
        "changed_paths": sorted(set(all_changed_paths)),
        "lanes": lane_decisions,
    }


def evidence_from_text(raw: str | None) -> dict[str, object]:
    directives = parse_directives(raw)
    status = (
        directives.get("status")
        or directives.get("validation status")
        or directives.get("result")
        or ""
    ).strip().lower()
    if status in {"success", "ok"}:
        status = "passed"
    command = directives.get("command") or directives.get("command id") or directives.get("cmd") or ""
    evidence = directives.get("evidence") or directives.get("artifact") or directives.get("output") or ""
    summary = directives.get("summary") or directives.get("note") or directives.get("reason") or ""
    return {
        "source": "manual-record" if directives else "none",
        "status": status or "missing",
        "command": command,
        "evidence": evidence,
        "summary": summary,
        "raw": raw or "",
    }


def requested_test_id(raw: str | None) -> str:
    directives = parse_directives(raw)
    for key in ("test-id", "test id", "test_id", "run", "allowlisted-test", "allowlisted test"):
        value = directives.get(key)
        if value:
            return value.strip()
    return ""


def default_integration_allowlist(slug: str) -> str:
    payload = {
        "schema_version": 1,
        "workflow_slug": slug,
        "tests": [],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def default_integration_allowlist_summary(slug: str) -> str:
    return f"""# Integration Test Allowlist

- Workflow slug: {slug}
- Source of truth: `integration-test-allowlist.json`

## Format

Add reviewed commands as structured argv entries. `command:` evidence in `wrkflw:integration-gate` remains manual text and is never executed.

```json
{{
  "schema_version": 1,
  "workflow_slug": "{slug}",
  "tests": [
    {{
      "id": "api-smoke",
      "description": "Run API smoke tests after merge-apply",
      "argv": ["./scripts/run-api-tests.sh"],
      "cwd": ".",
      "timeout_seconds": 180,
      "env": {{"CI": "1"}},
      "max_attempts": 1,
      "retry_on": []
    }}
  ]
}}
```

Run with:

```text
wrkflw:integration-gate "test-id: api-smoke"
```
"""


def ensure_integration_gate_artifacts(root: Path, slug: str) -> None:
    allowlist_path = integration_allowlist_path(root, slug)
    if not allowlist_path.exists():
        write_text(allowlist_path, default_integration_allowlist(slug))
    summary_path = integration_allowlist_summary_path(root, slug)
    if not summary_path.exists():
        write_text(summary_path, default_integration_allowlist_summary(slug))


def allowlist_binding(root: Path, slug: str) -> dict[str, object]:
    path = integration_allowlist_path(root, slug)
    return {
        "path": relative_or_absolute_path(root, path),
        "sha256": sha256_file(path),
        "exists": path.exists(),
    }


def normalize_timeout(value: object, errors: list[str]) -> int:
    if value in (None, ""):
        return DEFAULT_TIMEOUT_SECONDS
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        errors.append("timeout_seconds must be an integer")
        return DEFAULT_TIMEOUT_SECONDS
    if timeout < 1 or timeout > MAX_TIMEOUT_SECONDS:
        errors.append(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
        return DEFAULT_TIMEOUT_SECONDS
    return timeout


def normalize_max_attempts(value: object, errors: list[str]) -> int:
    if value in (None, ""):
        return 1
    try:
        attempts = int(value)
    except (TypeError, ValueError):
        errors.append("max_attempts must be an integer")
        return 1
    if attempts < 1 or attempts > 3:
        errors.append("max_attempts must be between 1 and 3")
        return 1
    return attempts


def list_of_strings(value: object, field: str, errors: list[str]) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be a list")
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field} entries must be non-empty strings")
            continue
        result.append(item.strip())
    return result


def validate_argv(argv: object, errors: list[str]) -> list[str]:
    if not isinstance(argv, list) or not argv:
        errors.append("argv must be a non-empty list of strings")
        return []
    result: list[str] = []
    for arg in argv:
        if not isinstance(arg, str) or not arg.strip():
            errors.append("argv entries must be non-empty strings")
            continue
        if "\x00" in arg or "\n" in arg or "\r" in arg:
            errors.append("argv entries must not contain control characters")
            continue
        result.append(arg)
    if result:
        executable = Path(result[0]).name.lower()
        if executable in FORBIDDEN_EXECUTABLES:
            errors.append(f"argv executable `{result[0]}` is not allowed for integration-gate execution")
        if any(arg in FORBIDDEN_INLINE_FLAGS for arg in result[1:]):
            errors.append("inline evaluation flags such as -c or -e are not allowed")
    return result


def validate_cwd(root: Path, value: object, errors: list[str]) -> Path:
    cwd_value = str(value or ".").strip()
    if not cwd_value:
        cwd_value = "."
    candidate = (root / cwd_value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        errors.append("cwd must resolve inside the repository root")
        return root
    if not candidate.exists() or not candidate.is_dir():
        errors.append(f"cwd `{cwd_value}` does not exist or is not a directory")
        return root
    return candidate


def validate_env(value: object, errors: list[str]) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        errors.append("env must be an object")
        return {}
    env: dict[str, str] = {}
    for key, raw_value in value.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            errors.append("env keys must be valid environment variable names")
            continue
        if raw_value is None:
            env[key] = ""
        elif isinstance(raw_value, (str, int, float, bool)):
            env[key] = str(raw_value)
        else:
            errors.append(f"env value for `{key}` must be scalar")
    return env


def validate_allowlist_entry(root: Path, entry: object) -> tuple[dict[str, object] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(entry, dict):
        return None, ["allowlist entries must be objects"]
    allowed_fields = {
        "id",
        "description",
        "argv",
        "cwd",
        "timeout_seconds",
        "env",
        "enabled",
        "max_attempts",
        "retry_on",
        "artifacts",
        "allowed_dirty_paths",
    }
    extra_fields = sorted(set(entry) - allowed_fields)
    if extra_fields:
        errors.append(f"unsupported fields: {', '.join(extra_fields)}")
    test_id = str(entry.get("id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", test_id):
        errors.append("id must be 1-80 characters using letters, numbers, _, ., :, or -")
    argv = validate_argv(entry.get("argv"), errors)
    cwd = validate_cwd(root, entry.get("cwd", "."), errors)
    env = validate_env(entry.get("env"), errors)
    timeout_seconds = normalize_timeout(entry.get("timeout_seconds"), errors)
    max_attempts = normalize_max_attempts(entry.get("max_attempts"), errors)
    retry_on = list_of_strings(entry.get("retry_on"), "retry_on", errors)
    unsupported_retry = sorted(set(retry_on) - {"failed", "timed_out", "error"})
    if unsupported_retry:
        errors.append(f"unsupported retry_on values: {', '.join(unsupported_retry)}")
    artifacts = list_of_strings(entry.get("artifacts"), "artifacts", errors)
    allowed_dirty_paths = list_of_strings(entry.get("allowed_dirty_paths"), "allowed_dirty_paths", errors)
    enabled = entry.get("enabled", True)
    if not isinstance(enabled, bool):
        errors.append("enabled must be a boolean when provided")
        enabled = False
    normalized = {
        "id": test_id,
        "description": str(entry.get("description") or "").strip(),
        "argv": argv,
        "cwd": str(cwd),
        "cwd_relative": relative_or_absolute_path(root, cwd),
        "timeout_seconds": timeout_seconds,
        "env": env,
        "enabled": enabled,
        "max_attempts": max_attempts,
        "retry_on": retry_on,
        "artifacts": artifacts,
        "allowed_dirty_paths": allowed_dirty_paths,
    }
    return (None if errors else normalized), errors


def load_allowlist(root: Path, slug: str) -> tuple[dict[str, object], dict[str, dict[str, object]], list[str]]:
    path = integration_allowlist_path(root, slug)
    binding = allowlist_binding(root, slug)
    if not path.exists():
        return binding, {}, [f"Integration test allowlist is missing at `{relative_or_absolute_path(root, path)}`."]
    payload = read_json(path)
    if not payload:
        return binding, {}, ["Integration test allowlist is unreadable or is not a JSON object."]
    if set(payload) - {"schema_version", "workflow_slug", "tests"}:
        return binding, {}, ["Integration test allowlist contains unsupported top-level fields."]
    if payload.get("schema_version") != 1:
        return binding, {}, ["Integration test allowlist schema_version must be 1."]
    tests = payload.get("tests", [])
    if not isinstance(tests, list):
        return binding, {}, ["Integration test allowlist `tests` must be a list."]
    errors: list[str] = []
    entries: dict[str, dict[str, object]] = {}
    for index, entry in enumerate(tests):
        normalized, entry_errors = validate_allowlist_entry(root, entry)
        if entry_errors:
            errors.extend(f"tests[{index}]: {item}" for item in entry_errors)
            continue
        if not normalized:
            continue
        test_id = str(normalized["id"])
        if test_id in entries:
            errors.append(f"duplicate test id `{test_id}`")
            continue
        entries[test_id] = normalized
    return binding, entries, errors


def dirty_nonworkflow_paths(root: Path, allowed_prefixes: list[str]) -> list[str]:
    status = run_git(root, ["status", "--short"])
    if status.returncode != 0:
        return []
    allowed = [prefix.rstrip("/") + "/" for prefix in allowed_prefixes if prefix.strip()]
    allowed_exact = {prefix.rstrip("/") for prefix in allowed_prefixes if prefix.strip()}
    dirty: list[str] = []
    for line in status.stdout.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if not path or path.startswith(".workflow/"):
            continue
        if path in allowed_exact or any(path.startswith(prefix) for prefix in allowed):
            continue
        dirty.append(path)
    return sorted(set(dirty))


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def run_allowlisted_test(root: Path, slug: str, test_id: str, prerequisite_blockers: list[str]) -> tuple[dict[str, object], list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    binding, entries, allowlist_errors = load_allowlist(root, slug)
    allowlist_hash = str(binding.get("sha256") or "")
    if allowlist_errors:
        blockers.extend(allowlist_errors)
    entry = entries.get(test_id)
    if not entry and not allowlist_errors:
        blockers.append(f"Integration test id `{test_id}` is not present in the allowlist.")
    if entry and not bool(entry.get("enabled", True)):
        blockers.append(f"Integration test id `{test_id}` is disabled in the allowlist.")
    if prerequisite_blockers:
        blockers.append("Integration test execution was skipped because prerequisite gate checks are blocked.")
    if blockers:
        execution = {
            "requested": True,
            "status": "blocked",
            "test_id": test_id,
            "allowlist": binding,
            "blockers": blockers,
        }
        return (
            {
                "source": "allowlisted-run",
                "status": "failed",
                "command": test_id,
                "evidence": "",
                "summary": "; ".join(blockers[:3]),
                "raw": "",
                "test_id": test_id,
                "allowlist": binding,
                "execution": execution,
            },
            blockers,
            warnings,
        )

    assert entry is not None
    started_at = utc_now()
    run_seed = f"{slug}:{test_id}:{started_at}:{allowlist_hash}"
    run_id = "integration-" + hashlib.sha256(run_seed.encode("utf-8")).hexdigest()[:16]
    argv = [str(item) for item in entry.get("argv", [])]
    cwd = Path(str(entry.get("cwd") or root))
    timeout_seconds = int(entry.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    retry_on = set(list_value(entry.get("retry_on")))
    max_attempts = int(entry.get("max_attempts") or 1)
    env = {key: value for key, value in os.environ.items() if key in SAFE_ENV_ALLOWLIST}
    env.update({str(key): str(value) for key, value in (entry.get("env") if isinstance(entry.get("env"), dict) else {}).items()})
    attempts: list[dict[str, object]] = []
    final_status = "error"
    final_exit_code: int | None = None
    for attempt_number in range(1, max_attempts + 1):
        attempt_started = time.monotonic()
        attempt_started_at = utc_now()
        stdout = ""
        stderr = ""
        exit_code: int | None = None
        status = "error"
        try:
            result = subprocess.run(
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                shell=False,
                check=False,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            exit_code = result.returncode
            status = "passed" if result.returncode == 0 else "failed"
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            status = "timed_out"
        except OSError as exc:
            stderr = str(exc)
            status = "error"
        duration_ms = int((time.monotonic() - attempt_started) * 1000)
        attempts.append(
            {
                "attempt": attempt_number,
                "started_at": attempt_started_at,
                "finished_at": utc_now(),
                "duration_ms": duration_ms,
                "status": status,
                "exit_code": exit_code,
                "stdout_tail": tail_text(redact_output(stdout)),
                "stderr_tail": tail_text(redact_output(stderr)),
            }
        )
        final_status = status
        final_exit_code = exit_code
        if status == "passed" or status not in retry_on:
            break
        time.sleep(min(2, attempt_number))

    dirty_paths = dirty_nonworkflow_paths(root, list_value(entry.get("allowed_dirty_paths")))
    if dirty_paths:
        final_status = "failed"
        blockers.append("Allowlisted integration test left dirty non-workflow paths: " + ", ".join(dirty_paths[:5]))
    finished_at = utc_now()
    duration_ms = sum(int(attempt.get("duration_ms") or 0) for attempt in attempts)
    argv_hash = hashlib.sha256(json.dumps(argv, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
    execution = {
        "schema_version": 1,
        "run_id": run_id,
        "workflow_slug": slug,
        "test_id": test_id,
        "description": entry.get("description", ""),
        "status": final_status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "exit_code": final_exit_code,
        "attempts": attempts,
        "argv": argv,
        "argv_sha256": argv_hash,
        "cwd": relative_or_absolute_path(root, cwd),
        "timeout_seconds": timeout_seconds,
        "max_attempts": max_attempts,
        "retry_on": sorted(retry_on),
        "allowlist": binding,
        "artifacts": list_value(entry.get("artifacts")),
        "dirty_paths": dirty_paths,
        "blockers": blockers,
        "warnings": warnings,
    }
    result_path = root / ".workflow" / slug / "integration-runs" / f"{run_id}.json"
    execution["result_path"] = relative_or_absolute_path(root, result_path)
    write_text(result_path, json.dumps(execution, indent=2, sort_keys=True) + "\n")
    records_path = root / ".workflow" / slug / "records" / "integration-gate-runs.jsonl"
    append_jsonl(
        records_path,
        {
            "schema_version": 1,
            "recorded_at": finished_at,
            "run_id": run_id,
            "workflow_slug": slug,
            "test_id": test_id,
            "status": final_status,
            "exit_code": final_exit_code,
            "duration_ms": duration_ms,
            "attempt_count": len(attempts),
            "argv_sha256": argv_hash,
            "allowlist_sha256": allowlist_hash,
            "result_path": relative_or_absolute_path(root, result_path),
        },
    )
    evidence_status = "passed" if final_status == "passed" else final_status
    evidence = {
        "source": "allowlisted-run",
        "status": evidence_status,
        "command": test_id,
        "evidence": relative_or_absolute_path(root, result_path),
        "summary": f"allowlisted integration test `{test_id}` {final_status}",
        "raw": "",
        "test_id": test_id,
        "allowlist": binding,
        "execution": execution,
    }
    if blockers:
        evidence["status"] = "failed"
    return evidence, blockers, warnings


def classify_status(required: bool, evidence: dict[str, object]) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    evidence_status = str(evidence.get("status") or "missing").strip().lower()

    if not required and evidence_status in {"missing", ""}:
        return "not_required", blockers, warnings
    if evidence_status in {"missing", ""}:
        blockers.append("Integration validation is required, but no validation evidence was recorded.")
        return "blocked", blockers, warnings
    if evidence_status in {"failed", "failure", "timed_out", "timed-out", "timeout", "blocked", "error"}:
        blockers.append(f"Integration validation reported `{evidence_status}`.")
        return "blocked", blockers, warnings
    if evidence_status == "flaky":
        blockers.append("Integration validation reported flaky results; record a bounded retry outcome or explicit waiver.")
        return "blocked", blockers, warnings
    if evidence_status == "waived":
        if not str(evidence.get("summary") or "").strip() and not str(evidence.get("evidence") or "").strip():
            blockers.append("Integration validation waiver requires an explicit reason or evidence reference.")
            return "blocked", blockers, warnings
        warnings.append("Integration validation was explicitly waived; residual integration risk remains.")
        return "ready", blockers, warnings
    if evidence_status == "passed":
        if not str(evidence.get("command") or "").strip():
            blockers.append("Passing integration validation evidence must include the command that was run.")
        if not str(evidence.get("evidence") or "").strip() and not str(evidence.get("summary") or "").strip():
            blockers.append("Passing integration validation evidence must include output, artifact, or summary evidence.")
        return ("blocked" if blockers else "ready"), blockers, warnings
    blockers.append(f"Unsupported integration validation status `{evidence_status}`.")
    return "blocked", blockers, warnings


def integration_failure_classification(required: bool, blockers: list[str], evidence: dict[str, object]) -> dict[str, object]:
    evidence_status = str(evidence.get("status") or "missing").strip().lower()
    summary = "; ".join(blockers[:3]) or str(evidence.get("summary") or evidence.get("evidence") or "")
    if blockers:
        lower = summary.lower()
        if "stale" in lower or "head changed" in lower or "changed; rerun" in lower:
            return classification("stale_gate_evidence", source="integration-gate", summary=summary, retryable=False, severity="high")
        if "allowlist" in lower or "not present" in lower or "not allowed" in lower or "disabled" in lower:
            return classification("policy_or_configuration_block", source="integration-gate", summary=summary, retryable=False, severity="high")
        if "missing" in lower and "evidence" in lower:
            return classification("missing_validation_evidence", source="integration-gate", summary=summary, retryable=False)
        if "timed" in lower or evidence_status in {"timed_out", "timed-out", "timeout", "error"}:
            return classification("environment_failure", source="integration-gate", summary=summary)
        if "failed" in lower or evidence_status in {"failed", "failure"}:
            return classification("integration_test_failure", source="integration-gate", summary=summary)
        return classify_text("integration-gate", summary)
    if evidence_status in {"failed", "failure"}:
        return classification("integration_test_failure", source="integration-gate", summary=summary)
    if evidence_status in {"timed_out", "timed-out", "timeout", "error"}:
        return classification("environment_failure", source="integration-gate", summary=summary)
    if evidence_status in {"missing", ""} and required:
        return classification("missing_validation_evidence", source="integration-gate", summary=summary, retryable=False)
    return {}


def render_summary(payload: dict[str, object]) -> str:
    requirement = payload.get("requirement", {})
    requirement = requirement if isinstance(requirement, dict) else {}
    evidence = payload.get("evidence", {})
    evidence = evidence if isinstance(evidence, dict) else {}
    execution = evidence.get("execution", {})
    execution = execution if isinstance(execution, dict) else {}
    blockers = list_value(payload.get("blockers"))
    warnings = list_value(payload.get("warnings"))
    lanes = requirement.get("lanes", [])
    lanes = lanes if isinstance(lanes, list) else []
    lines = [
        "# Integration Test Gate",
        "",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Status: {payload.get('status', '-')}",
        f"- Required: {'yes' if requirement.get('required') else 'no'}",
        f"- Evidence status: {evidence.get('status', '-')}",
        f"- Failure class: {payload.get('failure_class', '-') or '-'}",
        f"- Failure category: {payload.get('failure_category', '-') or '-'}",
        f"- Recommended gate: {payload.get('recommended_gate', '-') or '-'}",
        f"- Evidence command: `{evidence.get('command', '-') or '-'}`",
        f"- Evidence source: {evidence.get('source', '-')}",
        f"- Merge gate: `{(payload.get('merge_gate') if isinstance(payload.get('merge_gate'), dict) else {}).get('path', '-')}`",
        f"- Merge apply: `{(payload.get('merge_apply') if isinstance(payload.get('merge_apply'), dict) else {}).get('path', '-') or '-'}`",
        f"- Allowlist: `{(payload.get('allowlist') if isinstance(payload.get('allowlist'), dict) else {}).get('path', '-') or '-'}`",
        "",
        "## Requirement Reasons",
    ]
    reasons = list_value(requirement.get("reasons"))
    if reasons:
        lines.extend(f"- {item}" for item in reasons)
    else:
        lines.append("- none")
    lines.extend(["", "## Blockers"])
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings"])
    if warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- none")
    if execution:
        lines.extend(
            [
                "",
                "## Allowlisted Execution",
                "",
                f"- Test id: `{execution.get('test_id', '-')}`",
                f"- Run id: `{execution.get('run_id', '-')}`",
                f"- Status: {execution.get('status', '-')}",
                f"- Exit code: {execution.get('exit_code', '-')}",
                f"- Duration ms: {execution.get('duration_ms', '-')}",
                f"- Result: `{execution.get('result_path', '-') or '-'}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Lanes",
            "",
            "| Lane | Story | Changed paths | Integration reasons |",
            "| --- | --- | --- | --- |",
        ]
    )
    if lanes:
        for lane in lanes:
            if not isinstance(lane, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        table_cell(lane.get("lane_id", "")),
                        table_cell(lane.get("story", "")),
                        table_cell(", ".join(list_value(lane.get("changed_paths")))),
                        table_cell("; ".join(list_value(lane.get("requires_integration_reasons")))),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - |")
    lines.extend(
        [
            "",
            "## Rule",
            "",
            "This gate records integration validation readiness. It only executes commands selected by `test-id` from `integration-test-allowlist.json`; `command:` evidence remains manual text.",
            "",
        ]
    )
    return "\n".join(lines)


def run_integration_gate(root: Path, slug: str, evidence_text: str | None = None) -> dict[str, object]:
    generated_at = utc_now()
    blockers: list[str] = []
    warnings: list[str] = []
    merge_path = merge_gate_path(root, slug)
    merge_gate = read_json(merge_path)
    apply_path = merge_apply_path(root, slug)
    merge_apply = read_json(apply_path)
    current_head = ""
    head = run_git(root, ["rev-parse", "HEAD"])
    if head.returncode == 0:
        current_head = head.stdout.strip()
    else:
        blockers.append(f"Cannot read current HEAD: {head.stderr.strip() or head.stdout.strip()}")

    if not merge_path.exists():
        blockers.append("Merge gate artifact is missing; run wrkflw:merge-gate first.")
    elif not merge_gate:
        blockers.append("Merge gate artifact is unreadable; rerun wrkflw:merge-gate.")
    elif str(merge_gate.get("status") or "").strip().lower() != "ready":
        blockers.append("Merge gate must be ready before integration-test-gate can pass.")
    has_changed_paths = merge_gate_has_changed_paths(merge_gate) if merge_gate else False
    if merge_gate and has_changed_paths:
        if not apply_path.exists():
            blockers.append("Merge apply artifact is missing; run wrkflw:merge-apply before integration-gate.")
        elif not merge_apply:
            blockers.append("Merge apply artifact is unreadable; rerun wrkflw:merge-apply.")
        elif str(merge_apply.get("status") or "").strip().lower() != "applied":
            blockers.append("Merge apply must be applied before integration-gate can pass.")
        elif current_head and str(merge_apply.get("post_head") or "") != current_head:
            blockers.append("Merge apply is stale because repository HEAD changed; rerun merge-gate and merge-apply.")
        if merge_apply:
            apply_merge_gate = merge_apply.get("merge_gate", {})
            apply_merge_gate = apply_merge_gate if isinstance(apply_merge_gate, dict) else {}
            if str(apply_merge_gate.get("sha256") or "") != sha256_file(merge_path):
                blockers.append("Merge apply is stale because merge-gate changed; rerun wrkflw:merge-apply.")
            if str(merge_apply.get("pre_head") or "") != str(merge_gate.get("current_head") or ""):
                blockers.append("Merge apply is not anchored to the merge-gate HEAD; rerun merge-gate and merge-apply.")
    elif merge_gate and current_head and str(merge_gate.get("current_head") or "") != current_head:
        blockers.append("Merge gate is stale because repository HEAD changed; rerun wrkflw:merge-gate.")

    requirement = requirement_decision(root, slug, merge_gate) if merge_gate else {
        "required": False,
        "reasons": [],
        "warnings": [],
        "changed_lane_count": 0,
        "changed_paths": [],
        "lanes": [],
    }
    warnings.extend(list_value(requirement.get("warnings")))
    test_id = requested_test_id(evidence_text)
    if test_id:
        evidence, execution_blockers, execution_warnings = run_allowlisted_test(root, slug, test_id, blockers.copy())
        blockers.extend(execution_blockers)
        warnings.extend(execution_warnings)
    else:
        evidence = evidence_from_text(evidence_text)
    status, evidence_blockers, evidence_warnings = classify_status(bool(requirement.get("required")), evidence)
    blockers.extend(evidence_blockers)
    warnings.extend(evidence_warnings)
    if blockers:
        status = "blocked"
    failure = integration_failure_classification(bool(requirement.get("required")), blockers, evidence)
    payload = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": generated_at,
        "status": status,
        "command": "integration-test-gate",
        "current_head": current_head,
        "merge_gate": merge_gate_binding(root, slug, merge_gate) if merge_gate else {},
        "merge_apply": merge_apply_binding(root, slug, merge_apply) if merge_apply else {},
        "dag": dag_binding(root, slug),
        "allowlist": allowlist_binding(root, slug) if test_id else {},
        "requirement": requirement,
        "evidence": evidence,
        "failure_class": failure.get("failure_class", ""),
        "failure_category": failure.get("failure_category", ""),
        "retryable": failure.get("retryable", False),
        "recommended_gate": failure.get("recommended_gate", ""),
        "failure_classification": failure,
        "blockers": blockers,
        "warnings": warnings,
    }
    write_text(integration_gate_path(root, slug), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_text(integration_gate_summary_path(root, slug), render_summary(payload))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or record wrkflw integration validation gate evidence.")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    payload = run_integration_gate(root, args.slug, args.evidence)
    if payload.get("status") == "blocked":
        print("integration test gate blocked")
        return 1
    print(f"integration test gate {payload.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from workflow_failure_classification import classify_text, highest_priority_classification


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_git(root: Path, args: list[str], cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd or root,
        capture_output=True,
        text=True,
        check=check,
    )


def safe_segment(value: object, fallback: str = "item", max_length: int = 48) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._/-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-/._")
    if not text:
        text = fallback
    text = text.replace("/", "-")
    return text[:max_length].strip("-/._") or fallback


def short_digest(*parts: object) -> str:
    seed = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


def manifest_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "worktrees" / "manifest.json"


def summary_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "worktrees.md"


def merge_gate_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "merge-gate.json"


def merge_gate_summary_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "merge-gate.md"


def merge_apply_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "merge-apply.json"


def merge_apply_summary_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "merge-apply.md"


def default_external_root(root: Path) -> Path:
    configured = os.environ.get("WRKFLW_WORKTREE_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    root_id = f"{safe_segment(root.name, 'repo')}-{short_digest(root.resolve())}"
    return root.parent / ".wrkflw-worktrees" / root_id


def load_manifest(root: Path, slug: str) -> dict[str, object]:
    path = manifest_path(root, slug)
    if not path.exists():
        return {"schema_version": 1, "workflow_slug": slug, "entries": []}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {"schema_version": 1, "workflow_slug": slug, "entries": []}
    return payload if isinstance(payload, dict) else {"schema_version": 1, "workflow_slug": slug, "entries": []}


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(root: Path, slug: str, payload: dict[str, object]) -> None:
    write_text(manifest_path(root, slug), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_text(summary_path(root, slug), render_summary(payload))


def write_merge_gate(root: Path, slug: str, payload: dict[str, object]) -> None:
    write_text(merge_gate_path(root, slug), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_text(merge_gate_summary_path(root, slug), render_merge_gate_summary(payload))


def write_merge_apply(root: Path, slug: str, payload: dict[str, object]) -> None:
    write_text(merge_apply_path(root, slug), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_text(merge_apply_summary_path(root, slug), render_merge_apply_summary(payload))


def render_summary(payload: dict[str, object]) -> str:
    blockers = payload.get("blockers", [])
    warnings = payload.get("warnings", [])
    entries = payload.get("entries", [])
    lines = [
        "# Worktree Isolation",
        "",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Status: {payload.get('status', '-')}",
        f"- Base ref: {payload.get('base_ref', '-') or '-'}",
        f"- Base commit: {payload.get('base_commit', '-') or '-'}",
        f"- Main worktree dirty: {'yes' if payload.get('main_dirty') else 'no'}",
        f"- Worktree root: `{payload.get('worktree_root', '-')}`",
        "",
        "## Blockers",
    ]
    if isinstance(blockers, list) and blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings"])
    if isinstance(warnings, list) and warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Entries",
            "",
            "| Lane | Story | Branch | Path | Status | Cleanup |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if isinstance(entries, list) and entries:
        for item in entries:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"| {item.get('lane_id', '-') or '-'} | {item.get('story', '-') or '-'} | "
                f"`{item.get('branch', '-') or '-'}` | `{item.get('path', '-') or '-'}` | "
                f"{item.get('status', '-') or '-'} | {item.get('cleanup_status', '-') or '-'} |"
            )
    else:
        lines.append("| - | - | - | - | - | - |")
    lines.append("")
    return "\n".join(lines)


def render_merge_gate_summary(payload: dict[str, object]) -> str:
    blockers = payload.get("blockers", [])
    warnings = payload.get("warnings", [])
    entries = payload.get("entries", [])
    lines = [
        "# Merge Gate",
        "",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Status: {payload.get('status', '-')}",
        f"- Base commit: {payload.get('base_commit', '-') or '-'}",
        f"- Current HEAD: {payload.get('current_head', '-') or '-'}",
        f"- Source manifest: `{payload.get('source_manifest', '-')}`",
        "",
        "## Blockers",
    ]
    if isinstance(blockers, list) and blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings"])
    if isinstance(warnings, list) and warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Lane Readiness",
            "",
            "| Lane | Story | Branch | Changed files | Out of scope | Dirty | Conflict probe | Status |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if isinstance(entries, list) and entries:
        for item in entries:
            if not isinstance(item, dict):
                continue
            changed = item.get("changed_paths", [])
            invalid = item.get("out_of_scope_paths", [])
            changed_text = ", ".join(str(path) for path in changed) if isinstance(changed, list) and changed else "-"
            invalid_text = ", ".join(str(path) for path in invalid) if isinstance(invalid, list) and invalid else "-"
            conflict = item.get("conflict_probe", {})
            conflict_status = conflict.get("status", "-") if isinstance(conflict, dict) else "-"
            lines.append(
                f"| {item.get('lane_id', '-') or '-'} | {item.get('story', '-') or '-'} | "
                f"`{item.get('branch', '-') or '-'}` | {changed_text} | {invalid_text} | "
                f"{'yes' if item.get('dirty') else 'no'} | {conflict_status} | {item.get('status', '-') or '-'} |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Rule",
            "",
            "This gate is read-only. It verifies readiness for an explicit human-controlled merge or reconciliation step; it does not merge branches.",
            "",
        ]
    )
    return "\n".join(lines)


def render_merge_apply_summary(payload: dict[str, object]) -> str:
    blockers = payload.get("blockers", [])
    warnings = payload.get("warnings", [])
    entries = payload.get("entries", [])
    merge_gate = payload.get("merge_gate", {})
    merge_gate = merge_gate if isinstance(merge_gate, dict) else {}
    lines = [
        "# Merge Apply",
        "",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Status: {payload.get('status', '-')}",
        f"- Pre-apply HEAD: {payload.get('pre_head', '-') or '-'}",
        f"- Post-apply HEAD: {payload.get('post_head', '-') or '-'}",
        f"- Candidate branch: `{payload.get('candidate_branch', '-') or '-'}`",
        f"- Merge gate: `{merge_gate.get('path', '-') or '-'}`",
        "",
        "## Blockers",
    ]
    if isinstance(blockers, list) and blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings"])
    if isinstance(warnings, list) and warnings:
        lines.extend(f"- {item}" for item in warnings)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Applied Lanes",
            "",
            "| Lane | Story | Branch | Branch HEAD | Changed files | Status | Merge commit |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if isinstance(entries, list) and entries:
        for item in entries:
            if not isinstance(item, dict):
                continue
            changed = item.get("changed_paths", [])
            changed_text = ", ".join(str(path) for path in changed) if isinstance(changed, list) and changed else "-"
            lines.append(
                f"| {item.get('lane_id', '-') or '-'} | {item.get('story', '-') or '-'} | "
                f"`{item.get('branch', '-') or '-'}` | `{item.get('branch_head', '-') or '-'}` | "
                f"{changed_text} | {item.get('status', '-') or '-'} | `{item.get('merge_commit', '-') or '-'}` |"
            )
    else:
        lines.append("| - | - | - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Rule",
            "",
            "This command is explicit and state-changing. It applies only ready wrkflw lane branches after merge-gate, using a temporary integration branch before fast-forwarding the target checkout.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_worktree_list(root: Path) -> list[dict[str, str]]:
    result = run_git(root, ["worktree", "list", "--porcelain"])
    if result.returncode != 0:
        return []
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw in result.stdout.splitlines():
        if not raw.strip():
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = raw.partition(" ")
        if key == "worktree":
            if current:
                records.append(current)
            current = {"path": value.strip()}
        elif key == "branch":
            current["branch"] = value.strip().removeprefix("refs/heads/")
        elif key == "HEAD":
            current["head"] = value.strip()
    if current:
        records.append(current)
    return records


def registered_worktree_for_path(root: Path, path: Path) -> dict[str, str] | None:
    resolved = str(path.resolve())
    for record in parse_worktree_list(root):
        if str(Path(record.get("path", "")).resolve()) == resolved:
            return record
    return None


def registered_worktree_for_branch(root: Path, branch: str) -> dict[str, str] | None:
    for record in parse_worktree_list(root):
        if record.get("branch") == branch:
            return record
    return None


def branch_exists(root: Path, branch: str) -> bool:
    result = run_git(root, ["rev-parse", "--verify", f"refs/heads/{branch}"])
    return result.returncode == 0


def commit_exists(root: Path, commit: str) -> bool:
    if not commit:
        return False
    result = run_git(root, ["cat-file", "-e", f"{commit}^{{commit}}"])
    return result.returncode == 0


def rev_parse(root: Path, ref: str, cwd: Path | None = None) -> str:
    result = run_git(root, ["rev-parse", ref], cwd=cwd)
    return result.stdout.strip() if result.returncode == 0 else ""


def git_status_paths(output: str) -> list[str]:
    paths: list[str] = []
    for raw in output.splitlines():
        if not raw.strip():
            continue
        path = raw[3:].strip() if len(raw) > 3 else raw.strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1].strip()
        path = path.strip()
        if path.startswith("./"):
            path = path[2:]
        if path:
            paths.append(path)
    return paths


def workflow_artifact_path(path: str) -> bool:
    normalized = path.strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.startswith(".workflow/") or normalized.startswith("openspec/")


def dirty_non_workflow_paths(root: Path) -> tuple[list[str], str]:
    status = run_git(root, ["status", "--porcelain", "--untracked-files=all"])
    if status.returncode != 0:
        return [], status.stderr.strip() or status.stdout.strip()
    paths = git_status_paths(status.stdout)
    return [path for path in paths if not workflow_artifact_path(path)], ""


def git_operation_blockers(root: Path) -> list[str]:
    blockers: list[str] = []
    state_refs = {
        "MERGE_HEAD": "an in-progress merge",
        "CHERRY_PICK_HEAD": "an in-progress cherry-pick",
        "REVERT_HEAD": "an in-progress revert",
        "BISECT_LOG": "an in-progress bisect",
    }
    for ref, description in state_refs.items():
        result = run_git(root, ["rev-parse", "--git-path", ref])
        if result.returncode == 0 and Path(result.stdout.strip()).exists():
            blockers.append(f"Repository has {description}; resolve it before merge-apply.")
    rebase_merge = run_git(root, ["rev-parse", "--git-path", "rebase-merge"])
    if rebase_merge.returncode == 0 and Path(rebase_merge.stdout.strip()).exists():
        blockers.append("Repository has an in-progress rebase; resolve it before merge-apply.")
    rebase_apply = run_git(root, ["rev-parse", "--git-path", "rebase-apply"])
    if rebase_apply.returncode == 0 and Path(rebase_apply.stdout.strip()).exists():
        blockers.append("Repository has an in-progress rebase/apply; resolve it before merge-apply.")
    unmerged = run_git(root, ["diff", "--name-only", "--diff-filter=U"])
    if unmerged.returncode == 0 and unmerged.stdout.strip():
        blockers.append("Repository has unmerged paths; resolve them before merge-apply.")
    elif unmerged.returncode != 0:
        blockers.append(f"Cannot inspect unmerged paths: {unmerged.stderr.strip() or unmerged.stdout.strip()}")
    return blockers


def list_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def normalize_paths(value: object) -> list[str]:
    normalized: list[str] = []
    for item in list_value(value):
        path = item.strip().lstrip("./").rstrip("/")
        if path:
            normalized.append(path)
    return normalized


def path_allowed(changed_path: str, allowed_paths: list[str]) -> bool:
    normalized = changed_path.strip().lstrip("./").rstrip("/")
    if not normalized:
        return True
    for allowed in allowed_paths:
        allowed_normalized = allowed.strip().lstrip("./").rstrip("/")
        if allowed_normalized in {"*", ".", "/"}:
            return True
        if normalized == allowed_normalized or normalized.startswith(allowed_normalized + "/"):
            return True
    return False


def dispatch_nodes_by_lane(root: Path, slug: str) -> dict[str, dict[str, object]]:
    path = root / ".workflow" / slug / "parallel-dispatch.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    nodes = payload.get("nodes", []) if isinstance(payload, dict) else []
    result: dict[str, dict[str, object]] = {}
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict) and node.get("id"):
                result[str(node["id"])] = node
    return result


def merge_conflict_probe(root: Path, branch: str) -> dict[str, str]:
    result = run_git(root, ["merge-tree", "--write-tree", "--quiet", "HEAD", branch])
    if result.returncode == 0:
        return {"status": "clean", "message": ""}
    message = (result.stderr.strip() or result.stdout.strip() or "merge-tree reported a conflict").splitlines()
    return {"status": "blocked", "message": message[0] if message else "merge-tree reported a conflict"}


def git_repo_context(root: Path) -> tuple[dict[str, object], list[str]]:
    blockers: list[str] = []
    top = run_git(root, ["rev-parse", "--show-toplevel"])
    if top.returncode != 0:
        blockers.append("Git worktree isolation requires a git repository.")
        return {}, blockers
    git_root = Path(top.stdout.strip()).resolve()
    if git_root != root.resolve():
        blockers.append(f"Git worktree isolation must run at repository root `{git_root}`.")
        return {}, blockers
    base_commit = run_git(root, ["rev-parse", "HEAD"])
    if base_commit.returncode != 0:
        blockers.append("Git worktree isolation requires a committed HEAD.")
        return {}, blockers
    branch = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    status = run_git(root, ["status", "--porcelain"])
    dirty_lines = [line for line in status.stdout.splitlines() if line.strip()] if status.returncode == 0 else []
    return {
        "git_root": str(git_root),
        "base_commit": base_commit.stdout.strip(),
        "base_ref": branch.stdout.strip() if branch.returncode == 0 else "HEAD",
        "main_dirty": bool(dirty_lines),
        "main_dirty_count": len(dirty_lines),
    }, blockers


def lane_branch(slug: str, lane_id: str, base_commit: str) -> str:
    safe_slug = safe_segment(slug, "workflow", 36)
    safe_lane = safe_segment(lane_id, "lane", 48)
    digest = short_digest(slug, lane_id, base_commit)
    return f"wrkflw/{safe_slug}/{safe_lane}-{digest}"


def role_lane_id(active_story: str, slot: str) -> str:
    safe_story = safe_segment(active_story, "story", 36)
    safe_slot = safe_segment(slot, "role", 24)
    return f"{safe_story}-{safe_slot}"


def lane_path(root: Path, slug: str, lane_id: str, base_commit: str) -> Path:
    safe_slug = safe_segment(slug, "workflow", 36)
    safe_lane = safe_segment(lane_id, "lane", 48)
    digest = short_digest(slug, lane_id, base_commit)
    return default_external_root(root) / safe_slug / f"{safe_lane}-{digest}"


def parse_assignment_rows(root: Path, slug: str) -> dict[str, dict[str, str]]:
    path = root / ".workflow" / slug / "agent-assignments.md"
    rows: dict[str, dict[str, str]] = {}
    for line in read_text(path).splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        if len(parts) < 6 or parts[0] == "Role":
            continue
        rows[parts[0]] = {
            "Role": parts[0],
            "Slot": parts[1],
            "Responsibility Focus": parts[2],
            "Default Ownership": parts[3],
            "Allowed Write Paths": parts[4],
            "Status": parts[5],
        }
    return rows


def parse_state_active_story(root: Path, slug: str) -> str:
    path = root / ".workflow" / slug / "state.md"
    for line in read_text(path).splitlines():
        if line.startswith("- Active items:"):
            return line.split(":", 1)[1].split(",", 1)[0].strip()
    return ""


def assignment_sha256(root: Path, slug: str) -> str:
    return sha256_file(root / ".workflow" / slug / "agent-assignments.md")


def parallel_lanes(payload: dict[str, object]) -> list[dict[str, object]]:
    nodes = payload.get("nodes", [])
    lanes: list[dict[str, object]] = []
    if not isinstance(nodes, list):
        return lanes
    for node in nodes:
        if not isinstance(node, dict):
            continue
        lane_id = str(node.get("id") or node.get("story") or "").strip()
        if not lane_id:
            continue
        lanes.append(
            {
                "lane_id": lane_id,
                "story": str(node.get("story") or lane_id),
                "label": str(node.get("label") or node.get("story") or lane_id),
                "owner": "parallel-dispatch",
                "allowed_paths": node.get("allowed_paths", []),
                "packet": node.get("packet", ""),
            }
        )
    return lanes


def team_run_lanes(root: Path, slug: str, active_story: str, assignment_rows: dict[str, dict[str, str]], parallel_slots: int) -> tuple[list[dict[str, object]], list[str]]:
    blockers: list[str] = []
    lanes: list[dict[str, object]] = []
    roles = ["Implementer 1"]
    if parallel_slots > 1:
        roles.append("Implementer 2")
    for role in roles:
        row = assignment_rows.get(role)
        if not row:
            blockers.append(f"{role} assignment is missing; cannot prepare an isolated implementation worktree.")
            continue
        allowed_paths = normalize_paths(row.get("Allowed Write Paths"))
        if not allowed_paths:
            blockers.append(f"{role} requires explicit Allowed Write Paths before isolated team-run dispatch.")
            continue
        slot = str(row.get("Slot") or safe_segment(role, "role"))
        lane_id = role_lane_id(active_story, slot)
        lanes.append(
            {
                "lane_id": lane_id,
                "story": active_story,
                "label": f"{active_story} / {role}",
                "owner": role,
                "slot": slot,
                "role": role,
                "allowed_paths": allowed_paths,
                "packet": f".workflow/{slug}/dispatch/{slot}.md",
                "result_envelope": f".workflow/{slug}/agent-results/{slot}.md",
                "active_story": active_story,
                "merge_eligible": True,
            }
        )
    return lanes, blockers


def existing_manifest_entries(root: Path, slug: str) -> dict[str, dict[str, object]]:
    payload = load_manifest(root, slug)
    entries = payload.get("entries", [])
    result: dict[str, dict[str, object]] = {}
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and entry.get("lane_id"):
                result[str(entry["lane_id"])] = entry
    return result


def prepare_worktrees(root: Path, slug: str, lanes: list[dict[str, object]], command: str) -> dict[str, object]:
    generated_at = utc_now()
    context, blockers = git_repo_context(root)
    warnings: list[str] = []
    entries: list[dict[str, object]] = []
    if context.get("main_dirty"):
        warnings.append(
            f"Main worktree has {context.get('main_dirty_count')} uncommitted change(s); isolated worktrees are created from committed HEAD only."
        )
    if not lanes:
        blockers.append("No dispatch lanes are available for worktree isolation.")
    base_commit = str(context.get("base_commit") or "")
    worktree_root = default_external_root(root)

    if not blockers:
        for lane in lanes:
            lane_id = str(lane.get("lane_id") or "").strip()
            branch = lane_branch(slug, lane_id, base_commit)
            path = lane_path(root, slug, lane_id, base_commit)
            registered_path = registered_worktree_for_path(root, path)
            registered_branch = registered_worktree_for_branch(root, branch)
            if path.exists() and registered_path is None:
                blockers.append(f"Worktree path `{path}` already exists and is not a registered wrkflw worktree.")
                continue
            if registered_branch and str(Path(registered_branch.get("path", "")).resolve()) != str(path.resolve()):
                blockers.append(f"Branch `{branch}` is already checked out at `{registered_branch.get('path')}`.")
                continue
            if registered_path and registered_path.get("branch") != branch:
                blockers.append(f"Worktree path `{path}` is registered for branch `{registered_path.get('branch')}`, expected `{branch}`.")
                continue
            entries.append(
                {
                    "lane_id": lane_id,
                    "story": lane.get("story", ""),
                    "label": lane.get("label", ""),
                    "owner": lane.get("owner", ""),
                    "role": lane.get("role", lane.get("owner", "")),
                    "slot": lane.get("slot", ""),
                    "allowed_paths": lane.get("allowed_paths", []),
                    "active_story": lane.get("active_story", ""),
                    "merge_eligible": bool(lane.get("merge_eligible", True)),
                    "branch": branch,
                    "path": str(path),
                    "base_commit": base_commit,
                    "base_ref": context.get("base_ref", "HEAD"),
                    "status": "planned",
                    "cleanup_status": "not-started",
                    "command": command,
                    "packet": lane.get("packet", ""),
                    "result_envelope": lane.get("result_envelope", ""),
                }
            )

    if not blockers:
        for entry in entries:
            path = Path(str(entry["path"]))
            branch = str(entry["branch"])
            registered_path = registered_worktree_for_path(root, path)
            if registered_path:
                entry["status"] = "reused"
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            if branch_exists(root, branch):
                result = run_git(root, ["worktree", "add", str(path), branch])
            else:
                result = run_git(root, ["worktree", "add", "-b", branch, str(path), base_commit])
            if result.returncode != 0:
                blockers.append(f"Failed to create worktree `{path}`: {result.stderr.strip() or result.stdout.strip()}")
                entry["status"] = "failed"
                break
            entry["status"] = "prepared"
            entry["created_at"] = generated_at

    status = "ready" if not blockers else "blocked"
    payload = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": generated_at,
        "status": status,
        "command": command,
        "git_root": context.get("git_root", ""),
        "base_ref": context.get("base_ref", ""),
        "base_commit": context.get("base_commit", ""),
        "main_dirty": bool(context.get("main_dirty")),
        "main_dirty_count": context.get("main_dirty_count", 0),
        "worktree_root": str(worktree_root),
        "blockers": blockers,
        "warnings": warnings,
        "entries": entries,
    }
    write_manifest(root, slug, payload)
    return payload


def prepare_parallel_worktrees(root: Path, slug: str, dispatch_payload: dict[str, object]) -> dict[str, object]:
    if str(dispatch_payload.get("status") or "").strip().lower() != "ready":
        payload = {
            "schema_version": 1,
            "workflow_slug": slug,
            "generated_at": utc_now(),
            "status": "blocked",
            "command": "team-run-level",
            "blockers": ["Parallel dispatch is not ready; worktrees were not created."],
            "warnings": [],
            "entries": [],
        }
        write_manifest(root, slug, payload)
        return payload
    return prepare_worktrees(root, slug, parallel_lanes(dispatch_payload), "team-run-level")


def prepare_team_run_worktrees(
    root: Path,
    slug: str,
    active_story: str,
    assignment_rows: dict[str, dict[str, str]],
    parallel_slots: int,
) -> dict[str, object]:
    lanes, lane_blockers = team_run_lanes(root, slug, active_story, assignment_rows, parallel_slots)
    dirty_paths, dirty_error = dirty_non_workflow_paths(root)
    dirty_scope: list[str] = []
    if dirty_paths:
        for dirty_path in dirty_paths:
            for lane in lanes:
                if path_allowed(dirty_path, normalize_paths(lane.get("allowed_paths"))):
                    dirty_scope.append(dirty_path)
                    break
    blockers = list(lane_blockers)
    if dirty_error:
        blockers.append(f"Cannot inspect target checkout status: {dirty_error}")
    if dirty_scope:
        blockers.append("Target checkout has uncommitted path(s) inside active role scope: " + ", ".join(sorted(set(dirty_scope))[:8]))
    if blockers:
        payload = {
            "schema_version": 1,
            "workflow_slug": slug,
            "generated_at": utc_now(),
            "status": "blocked",
            "command": "team-run",
            "active_story": active_story,
            "source_assignments": f".workflow/{slug}/agent-assignments.md",
            "assignment_sha256": assignment_sha256(root, slug),
            "blockers": blockers,
            "warnings": [],
            "entries": lanes,
        }
        write_manifest(root, slug, payload)
        return payload
    payload = prepare_worktrees(root, slug, lanes, "team-run")
    payload["active_story"] = active_story
    payload["source_assignments"] = f".workflow/{slug}/agent-assignments.md"
    payload["assignment_sha256"] = assignment_sha256(root, slug)
    write_manifest(root, slug, payload)
    return payload


def worktree_records_by_lane(root: Path, slug: str) -> dict[str, dict[str, object]]:
    return existing_manifest_entries(root, slug)


def run_merge_gate(root: Path, slug: str) -> dict[str, object]:
    generated_at = utc_now()
    source = manifest_path(root, slug)
    manifest = load_manifest(root, slug)
    entries = manifest.get("entries", [])
    entries = entries if isinstance(entries, list) else []
    blockers: list[str] = []
    warnings: list[str] = []
    gate_entries: list[dict[str, object]] = []
    context, context_blockers = git_repo_context(root)
    blockers.extend(context_blockers)
    dispatch_nodes = dispatch_nodes_by_lane(root, slug)

    if not source.exists():
        blockers.append("Worktree manifest is missing; run wrkflw:team-run-level or wrkflw:team-run before merge-gate.")
    if str(manifest.get("status") or "").strip().lower() != "ready":
        manifest_blockers = list_value(manifest.get("blockers"))
        blockers.append("Worktree manifest is not ready: " + "; ".join(manifest_blockers or ["manifest status is not ready"]))
    if not entries:
        blockers.append("Worktree manifest has no entries to reconcile.")

    current_head = ""
    if not context_blockers:
        head = run_git(root, ["rev-parse", "HEAD"])
        if head.returncode == 0:
            current_head = head.stdout.strip()
        else:
            blockers.append(f"Cannot read current HEAD: {head.stderr.strip() or head.stdout.strip()}")
        status = run_git(root, ["status", "--porcelain"])
        if status.returncode == 0:
            main_dirty_paths = git_status_paths(status.stdout)
            if main_dirty_paths:
                warnings.append(
                    f"Main checkout has {len(main_dirty_paths)} uncommitted path(s); merge-gate does not merge into a dirty checkout."
                )
        else:
            main_dirty_paths = []
            blockers.append(f"Cannot inspect main checkout status: {status.stderr.strip() or status.stdout.strip()}")
    else:
        main_dirty_paths = []

    manifest_base = str(manifest.get("base_commit") or "")
    if manifest_base and current_head and current_head != manifest_base:
        blockers.append(
            f"Current HEAD `{current_head}` differs from dispatch base `{manifest_base}`; rebase or regenerate worktrees before merge-gate."
        )
    manifest_command = str(manifest.get("command") or "")
    assignment_rows = parse_assignment_rows(root, slug) if manifest_command == "team-run" else {}
    current_active_story = parse_state_active_story(root, slug) if manifest_command == "team-run" else ""
    if manifest_command == "team-run":
        if str(manifest.get("active_story") or "") != current_active_story:
            blockers.append("Worktree manifest is stale because the active story changed; rerun wrkflw:team-run.")

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        lane_id = str(entry.get("lane_id") or "").strip()
        story = str(entry.get("story") or "").strip()
        branch = str(entry.get("branch") or "").strip()
        path = Path(str(entry.get("path") or ""))
        base_commit = str(entry.get("base_commit") or manifest_base or "")
        allowed_paths = normalize_paths(entry.get("allowed_paths"))
        entry_blockers: list[str] = []
        entry_warnings: list[str] = []
        changed_paths: list[str] = []
        dirty_paths: list[str] = []
        branch_head = ""
        conflict_probe = {"status": "not-run", "message": ""}

        dispatch_node = dispatch_nodes.get(lane_id)
        entry_command = str(entry.get("command") or manifest.get("command") or "")
        if entry_command == "team-run-level":
            if not dispatch_nodes:
                entry_blockers.append("parallel-dispatch.json is missing or unreadable")
            elif not dispatch_node:
                entry_blockers.append("lane is not present in current parallel-dispatch.json")
            else:
                dispatch_allowed = normalize_paths(dispatch_node.get("allowed_paths"))
                if sorted(dispatch_allowed) != sorted(allowed_paths):
                    entry_blockers.append("allowed paths differ from current parallel-dispatch.json")
        elif entry_command == "team-run":
            owner = str(entry.get("owner") or entry.get("role") or "").strip()
            row = assignment_rows.get(owner, {})
            if not row:
                entry_blockers.append(f"role `{owner or '-'}` is not present in current agent-assignments.md")
            else:
                current_allowed = normalize_paths(row.get("Allowed Write Paths"))
                if sorted(current_allowed) != sorted(allowed_paths):
                    entry_blockers.append("allowed paths differ from current agent-assignments.md")
                if str(entry.get("active_story") or manifest.get("active_story") or "") != current_active_story:
                    entry_blockers.append("entry active story differs from current workflow state")

        if not branch.startswith("wrkflw/"):
            entry_blockers.append(f"branch `{branch}` is not a wrkflw-owned branch")
        if not branch_exists(root, branch):
            entry_blockers.append(f"branch `{branch}` is missing")
        else:
            branch_head = rev_parse(root, branch)
        if not path.exists():
            entry_blockers.append(f"worktree path `{path}` is missing")
        registered = registered_worktree_for_path(root, path) if path.exists() else None
        if path.exists() and not registered:
            entry_blockers.append(f"worktree path `{path}` is not registered with git")
        if registered and registered.get("branch") != branch:
            entry_blockers.append(f"registered branch is `{registered.get('branch')}`, expected `{branch}`")
        if not commit_exists(root, base_commit):
            entry_blockers.append(f"base commit `{base_commit}` is missing")

        if not entry_blockers:
            ancestor = run_git(root, ["merge-base", "--is-ancestor", base_commit, branch])
            if ancestor.returncode != 0:
                entry_blockers.append(f"branch `{branch}` does not descend from base commit `{base_commit}`")
            status = run_git(root, ["status", "--porcelain", "--untracked-files=all"], cwd=path)
            if status.returncode != 0:
                entry_blockers.append(f"cannot inspect worktree status: {status.stderr.strip() or status.stdout.strip()}")
            else:
                dirty_paths = git_status_paths(status.stdout)
                ignored_dirty = [
                    dirty
                    for dirty in dirty_paths
                    if dirty.startswith(f".workflow/{slug}/agent-results/")
                ]
                dirty_paths = [dirty for dirty in dirty_paths if dirty not in ignored_dirty]
                if ignored_dirty:
                    entry_warnings.append(
                        f"worktree has {len(ignored_dirty)} unsynced agent result envelope(s); run team-sync-all before cleanup"
                    )
                if dirty_paths:
                    entry_blockers.append(f"worktree has {len(dirty_paths)} uncommitted path(s)")
            diff = run_git(root, ["diff", "--name-only", f"{base_commit}..{branch}"])
            if diff.returncode != 0:
                entry_blockers.append(f"cannot inspect changed paths: {diff.stderr.strip() or diff.stdout.strip()}")
            else:
                changed_paths = [line.strip() for line in diff.stdout.splitlines() if line.strip()]
            if not allowed_paths and changed_paths:
                entry_blockers.append("changed paths exist, but the lane has no allowed_paths")
            out_of_scope = [changed for changed in changed_paths if not path_allowed(changed, allowed_paths)]
            if out_of_scope:
                entry_blockers.append(f"changed paths outside allowed scope: {', '.join(out_of_scope[:5])}")
            dirty_scope = [dirty for dirty in main_dirty_paths if allowed_paths and path_allowed(dirty, allowed_paths)]
            if dirty_scope:
                entry_blockers.append(f"main checkout has uncommitted paths in this lane scope: {', '.join(dirty_scope[:5])}")
            if not entry_blockers:
                conflict_probe = merge_conflict_probe(root, branch)
                if conflict_probe.get("status") == "blocked":
                    entry_blockers.append(f"merge conflict probe failed: {conflict_probe.get('message')}")
            if not changed_paths and not dirty_paths:
                entry_warnings.append("lane branch has no committed changes relative to its base")
        else:
            out_of_scope = []

        status_value = "blocked" if entry_blockers else ("ready" if changed_paths else "no-changes")
        for blocker in entry_blockers:
            blockers.append(f"{lane_id or branch}: {blocker}")
        gate_entries.append(
            {
                "lane_id": lane_id,
                "story": story,
                "branch": branch,
                "branch_head": branch_head,
                "path": str(path),
                "base_commit": base_commit,
                "allowed_paths": allowed_paths,
                "changed_paths": changed_paths,
                "out_of_scope_paths": out_of_scope,
                "dirty": bool(dirty_paths),
                "dirty_paths": dirty_paths,
                "conflict_probe": conflict_probe,
                "warnings": entry_warnings,
                "blockers": entry_blockers,
                "status": status_value,
            }
        )

    warnings.extend(
        f"{entry.get('lane_id') or entry.get('branch')}: {warning}"
        for entry in gate_entries
        for warning in list_value(entry.get("warnings"))
    )
    classifications = [classify_text("merge-gate", blocker) for blocker in blockers]
    top_failure = highest_priority_classification(classifications)
    payload = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": generated_at,
        "status": "blocked" if blockers else "ready",
        "command": "merge-gate",
        "source_manifest": str(source.relative_to(root)) if source.exists() else str(source),
        "git_root": context.get("git_root", ""),
        "base_commit": manifest_base,
        "current_head": current_head,
        "manifest_generated_at": manifest.get("generated_at", ""),
        "failure_class": top_failure.get("failure_class", ""),
        "failure_category": top_failure.get("failure_category", ""),
        "retryable": top_failure.get("retryable", False),
        "recommended_gate": top_failure.get("recommended_gate", ""),
        "failure_classification": top_failure,
        "failure_classifications": classifications,
        "blockers": blockers,
        "warnings": warnings,
        "entries": gate_entries,
    }
    write_merge_gate(root, slug, payload)
    return payload


def merge_apply_confirmed(confirmation_text: str | None) -> bool:
    normalized = (confirmation_text or "").strip().lower()
    return any(
        token in normalized
        for token in {
            "confirm: merge-apply",
            "confirm=merge-apply",
            "confirm: apply",
            "confirm=apply",
        }
    )


def merge_gate_apply_binding(root: Path, slug: str, merge_gate: dict[str, object]) -> dict[str, object]:
    path = merge_gate_path(root, slug)
    return {
        "path": str(path.relative_to(root)) if path.exists() else str(path),
        "sha256": sha256_file(path),
        "generated_at": merge_gate.get("generated_at", ""),
        "status": merge_gate.get("status", ""),
        "base_commit": merge_gate.get("base_commit", ""),
        "current_head": merge_gate.get("current_head", ""),
    }


def cleanup_merge_apply_candidate(root: Path, temp_path: Path, temp_branch: str, warnings: list[str], delete_branch: bool) -> None:
    if temp_path.exists() or registered_worktree_for_path(root, temp_path):
        remove = run_git(root, ["worktree", "remove", str(temp_path)])
        if remove.returncode != 0:
            warnings.append(f"Could not remove merge-apply temp worktree `{temp_path}`: {remove.stderr.strip() or remove.stdout.strip()}")
    if delete_branch and branch_exists(root, temp_branch):
        delete = run_git(root, ["branch", "-D", temp_branch])
        if delete.returncode != 0:
            warnings.append(f"Could not delete merge-apply temp branch `{temp_branch}`: {delete.stderr.strip() or delete.stdout.strip()}")


def run_merge_apply(root: Path, slug: str, confirmation_text: str | None = None) -> dict[str, object]:
    generated_at = utc_now()
    blockers: list[str] = []
    warnings: list[str] = []
    apply_entries: list[dict[str, object]] = []
    merge_path = merge_gate_path(root, slug)
    merge_gate = read_json(merge_path)
    context, context_blockers = git_repo_context(root)
    blockers.extend(context_blockers)
    pre_head = rev_parse(root, "HEAD") if not context_blockers else ""
    post_head = pre_head
    candidate_branch = ""
    candidate_head = ""
    temp_path = Path("")
    checkpoint_ref = ""

    if not merge_apply_confirmed(confirmation_text):
        blockers.append("Merge apply requires explicit human confirmation: include `confirm: merge-apply` in the command reason.")
    if str(context.get("base_ref") or "") == "HEAD":
        blockers.append("Merge apply requires a named target branch, not a detached HEAD checkout.")
    blockers.extend(git_operation_blockers(root))
    dirty_paths, dirty_error = dirty_non_workflow_paths(root)
    if dirty_error:
        blockers.append(f"Cannot inspect target checkout status: {dirty_error}")
    if dirty_paths:
        blockers.append("Target checkout has uncommitted non-workflow path(s): " + ", ".join(dirty_paths[:8]))

    if not merge_path.exists():
        blockers.append("Merge gate artifact is missing; run wrkflw:merge-gate before merge-apply.")
    elif not merge_gate:
        blockers.append("Merge gate artifact is unreadable; rerun wrkflw:merge-gate.")
    elif str(merge_gate.get("status") or "").strip().lower() != "ready":
        blockers.append("Merge gate must be ready before merge-apply can run.")
    if merge_gate and pre_head and str(merge_gate.get("current_head") or "") != pre_head:
        blockers.append("Merge gate is stale because repository HEAD changed; rerun wrkflw:merge-gate.")

    gate_entries = merge_gate.get("entries", []) if isinstance(merge_gate, dict) else []
    gate_entries = gate_entries if isinstance(gate_entries, list) else []
    if merge_gate and not gate_entries:
        blockers.append("Merge gate contains no lane entries to apply.")

    pending_indexes: list[int] = []
    for entry in gate_entries:
        if not isinstance(entry, dict):
            continue
        branch = str(entry.get("branch") or "").strip()
        changed_paths = list_value(entry.get("changed_paths"))
        entry_status = str(entry.get("status") or "").strip().lower()
        recorded_head = str(entry.get("branch_head") or "").strip()
        record = {
            "lane_id": entry.get("lane_id", ""),
            "story": entry.get("story", ""),
            "branch": branch,
            "branch_head": recorded_head,
            "changed_paths": changed_paths,
            "status": "pending",
            "merge_commit": "",
            "blockers": [],
        }
        entry_blockers: list[str] = []
        if entry_status == "no-changes" or not changed_paths:
            record["status"] = "skipped-no-changes"
        elif entry_status != "ready":
            entry_blockers.append(f"merge-gate entry status is `{entry_status or 'missing'}`")
        elif not branch.startswith("wrkflw/"):
            entry_blockers.append(f"branch `{branch}` is not a wrkflw-owned branch")
        elif not branch_exists(root, branch):
            entry_blockers.append(f"branch `{branch}` is missing")
        else:
            current_branch_head = rev_parse(root, branch)
            record["current_branch_head"] = current_branch_head
            if recorded_head and current_branch_head != recorded_head:
                entry_blockers.append(f"branch `{branch}` moved after merge-gate; rerun wrkflw:merge-gate")
        if entry_blockers:
            record["status"] = "blocked"
            record["blockers"] = entry_blockers
            blockers.extend(f"{record.get('lane_id') or branch}: {item}" for item in entry_blockers)
        elif record["status"] == "pending":
            pending_indexes.append(len(apply_entries))
        apply_entries.append(record)

    if not pending_indexes and merge_gate:
        warnings.append("Merge gate has no committed lane changes; merge-apply is not required.")

    payload_base = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": generated_at,
        "command": "merge-apply",
        "git_root": context.get("git_root", ""),
        "target_branch": context.get("base_ref", ""),
        "pre_head": pre_head,
        "post_head": post_head,
        "candidate_branch": candidate_branch,
        "candidate_head": candidate_head,
        "checkpoint_ref": checkpoint_ref,
        "merge_gate": merge_gate_apply_binding(root, slug, merge_gate) if merge_gate else {},
        "confirmation": confirmation_text or "",
        "entries": apply_entries,
        "blockers": blockers,
        "warnings": warnings,
    }
    if blockers:
        payload = {**payload_base, "status": "blocked"}
        write_merge_apply(root, slug, payload)
        return payload
    if not pending_indexes:
        payload = {**payload_base, "status": "not_required"}
        write_merge_apply(root, slug, payload)
        return payload

    digest = short_digest(slug, pre_head, generated_at)
    candidate_branch = f"wrkflw/{safe_segment(slug, 'workflow', 36)}/merge-apply-{digest}"
    temp_path = default_external_root(root) / safe_segment(slug, "workflow", 36) / f"merge-apply-{digest}"
    checkpoint_ref = f"refs/wrkflw/{safe_segment(slug, 'workflow', 36)}/pre-merge-apply-{digest}"

    if branch_exists(root, candidate_branch):
        blockers.append(f"Merge-apply temp branch `{candidate_branch}` already exists.")
    if temp_path.exists() and not registered_worktree_for_path(root, temp_path):
        blockers.append(f"Merge-apply temp path `{temp_path}` already exists and is not a registered git worktree.")
    if not blockers:
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        create = run_git(root, ["worktree", "add", "-b", candidate_branch, str(temp_path), pre_head])
        if create.returncode != 0:
            blockers.append(f"Could not create merge-apply temp worktree: {create.stderr.strip() or create.stdout.strip()}")

    if not blockers:
        for index in pending_indexes:
            record = apply_entries[index]
            branch = str(record.get("branch") or "")
            probe = run_git(root, ["merge-tree", "--write-tree", "--quiet", "HEAD", branch], cwd=temp_path)
            if probe.returncode != 0:
                message = (probe.stderr.strip() or probe.stdout.strip() or "merge-tree reported a conflict").splitlines()[0]
                record["status"] = "blocked"
                record["blockers"] = [f"candidate merge conflict probe failed: {message}"]
                blockers.append(f"{record.get('lane_id') or branch}: candidate merge conflict probe failed: {message}")
                break
            merge = run_git(root, ["merge", "--no-ff", "--no-edit", branch], cwd=temp_path)
            if merge.returncode != 0:
                message = (merge.stderr.strip() or merge.stdout.strip() or "git merge failed").splitlines()[0]
                abort = run_git(root, ["merge", "--abort"], cwd=temp_path)
                if abort.returncode != 0:
                    warnings.append(f"Could not abort failed candidate merge: {abort.stderr.strip() or abort.stdout.strip()}")
                record["status"] = "failed"
                record["blockers"] = [f"candidate merge failed: {message}"]
                blockers.append(f"{record.get('lane_id') or branch}: candidate merge failed: {message}")
                break
            record["status"] = "merged"
            record["merge_commit"] = rev_parse(root, "HEAD", cwd=temp_path)
        if not blockers:
            candidate_head = rev_parse(root, "HEAD", cwd=temp_path)
        cleanup_merge_apply_candidate(root, temp_path, candidate_branch, warnings, delete_branch=bool(blockers))

    if not blockers:
        current_head = rev_parse(root, "HEAD")
        if current_head != pre_head:
            blockers.append("Target checkout HEAD changed during merge-apply; rerun merge-gate before applying.")
        blockers.extend(git_operation_blockers(root))
        dirty_paths, dirty_error = dirty_non_workflow_paths(root)
        if dirty_error:
            blockers.append(f"Cannot recheck target checkout status: {dirty_error}")
        if dirty_paths:
            blockers.append("Target checkout gained uncommitted non-workflow path(s): " + ", ".join(dirty_paths[:8]))

    if not blockers:
        checkpoint = run_git(root, ["update-ref", checkpoint_ref, pre_head])
        if checkpoint.returncode != 0:
            blockers.append(f"Could not create pre-apply checkpoint ref `{checkpoint_ref}`: {checkpoint.stderr.strip() or checkpoint.stdout.strip()}")

    if not blockers:
        apply_result = run_git(root, ["merge", "--ff-only", candidate_branch])
        if apply_result.returncode != 0:
            blockers.append(f"Could not fast-forward target checkout to candidate branch: {apply_result.stderr.strip() or apply_result.stdout.strip()}")
        else:
            post_head = rev_parse(root, "HEAD")
            delete = run_git(root, ["branch", "-D", candidate_branch])
            if delete.returncode != 0:
                warnings.append(f"Could not delete merge-apply temp branch `{candidate_branch}`: {delete.stderr.strip() or delete.stdout.strip()}")

    classifications = [classify_text("merge-apply", blocker) for blocker in blockers]
    top_failure = highest_priority_classification(classifications)
    payload = {
        **payload_base,
        "status": "blocked" if blockers else "applied",
        "post_head": post_head,
        "candidate_branch": candidate_branch,
        "candidate_head": candidate_head,
        "checkpoint_ref": checkpoint_ref,
        "entries": apply_entries,
        "failure_class": top_failure.get("failure_class", ""),
        "failure_category": top_failure.get("failure_category", ""),
        "retryable": top_failure.get("retryable", False),
        "recommended_gate": top_failure.get("recommended_gate", ""),
        "failure_classification": top_failure,
        "failure_classifications": classifications,
        "blockers": blockers,
        "warnings": warnings,
    }
    write_merge_apply(root, slug, payload)
    return payload


def cleanup_worktrees(root: Path, slug: str) -> dict[str, object]:
    payload = load_manifest(root, slug)
    entries = payload.get("entries", [])
    blockers: list[str] = []
    cleaned: list[str] = []
    context, context_blockers = git_repo_context(root)
    blockers.extend(context_blockers)
    if not isinstance(entries, list):
        entries = []
    if not blockers:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            branch = str(entry.get("branch") or "")
            path = Path(str(entry.get("path") or ""))
            if not branch.startswith("wrkflw/"):
                blockers.append(f"Refusing to clean non-wrkflw branch `{branch}`.")
                continue
            registered = registered_worktree_for_path(root, path)
            if not registered:
                entry["cleanup_status"] = "missing"
                continue
            if registered.get("branch") != branch:
                blockers.append(f"Refusing to clean `{path}` because registered branch is `{registered.get('branch')}`, expected `{branch}`.")
                continue
            status = run_git(root, ["status", "--porcelain", "--untracked-files=all"], cwd=path)
            if status.returncode != 0:
                blockers.append(f"Cannot inspect worktree `{path}`: {status.stderr.strip() or status.stdout.strip()}")
                continue
            dirty = [line for line in status.stdout.splitlines() if line.strip()]
            if dirty:
                entry["cleanup_status"] = "blocked-dirty"
                blockers.append(f"Worktree `{path}` has {len(dirty)} uncommitted change(s); cleanup refused.")
                continue
            result = run_git(root, ["worktree", "remove", str(path)])
            if result.returncode != 0:
                entry["cleanup_status"] = "failed"
                blockers.append(f"Failed to remove worktree `{path}`: {result.stderr.strip() or result.stdout.strip()}")
                continue
            entry["cleanup_status"] = "removed"
            entry["status"] = "removed"
            cleaned.append(str(path))
    payload["generated_at"] = utc_now()
    payload["status"] = "blocked" if blockers else "cleaned"
    payload["blockers"] = blockers
    payload["cleaned"] = cleaned
    payload["git_root"] = context.get("git_root", payload.get("git_root", ""))
    write_manifest(root, slug, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare, inspect, or clean wrkflw-owned git worktrees.")
    parser.add_argument("command", choices=["cleanup", "merge-gate", "merge-apply"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "cleanup":
        payload = cleanup_worktrees(root, args.slug)
        if payload.get("status") == "blocked":
            print("worktree cleanup blocked")
            return 1
        print("worktree cleanup complete")
        return 0
    if args.command == "merge-gate":
        payload = run_merge_gate(root, args.slug)
        if payload.get("status") == "blocked":
            print("merge gate blocked")
            return 1
        print("merge gate ready")
        return 0
    if args.command == "merge-apply":
        payload = run_merge_apply(root, args.slug, args.confirmation)
        if payload.get("status") == "blocked":
            print("merge apply blocked")
            return 1
        print(f"merge apply {payload.get('status')}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

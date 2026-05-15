#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
from fnmatch import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from subprocess import run

from workflow_accounting import (
    ensure_accounting_artifacts,
    format_accounting_summary,
    load_invocation_records,
    record_agent_result_invocation,
    record_command_invocation,
    record_manual_invocation,
)
from workflow_debt import (
    append_or_update_debt_record,
    blocking_debt_records,
    ensure_debt_artifacts,
    format_debt_summary,
    load_debt_records,
    normalize_debt_type,
    normalize_severity,
    normalize_status,
    normalize_story_id,
    parse_story_id_list,
    render_debt_summary,
)
from workflow_agent_result_schema import (
    append_agent_result_validation_record,
    ensure_agent_result_schema_artifacts,
    strict_schema_required,
    validate_agent_result_report,
)
from workflow_action_menu import run_action_menu
from workflow_capability_synth import run_capability_synth
from workflow_ci_feedback import ci_feedback_block, run_ci_feedback
from workflow_feedback_synthesizer import feedback_synthesis_block, run_feedback_synthesis
from workflow_integration_gate import integration_allowlist_path, integration_gate_path, run_integration_gate
from workflow_issue_advisor import run_issue_advisor
from workflow_stage_synth import SYNTH_COMMAND_KINDS, run_stage_synth
from workflow_memory import (
    append_or_update_memory_record,
    ensure_memory_artifacts,
    format_memory_summary,
    load_memory_records,
    normalize_category as normalize_memory_category,
    normalize_confidence as normalize_memory_confidence,
    normalize_status as normalize_memory_status,
    parse_list as parse_memory_list,
    parse_story_id_list as parse_memory_story_id_list,
    render_memory_summary,
)
from workflow_replanner import run_replanner
from workflow_runtime_contract import (
    GENERATED_SHARED_ARTIFACTS,
    REQUIRED_SHARED_INPUTS,
    REQUIRED_SHARED_OUTPUTS,
    format_shared_items,
)
from workflow_verify_fix import run_verify_fix, verify_fix_block
from workflow_worktrees import (
    cleanup_worktrees,
    merge_apply_path,
    merge_gate_path,
    prepare_parallel_worktrees,
    prepare_team_run_worktrees,
    run_merge_apply,
    run_merge_gate,
)


STAGE_ORDER = [
    "discuss",
    "capability-review",
    "epic-shaping",
    "story-slicing",
    "story-enrichment",
    "spec-authoring",
    "implementation-planning",
    "implementation",
    "review",
    "release-planning",
    "done",
]

GATED_STAGES = {
    "capability-review",
    "epic-shaping",
    "story-slicing",
    "story-enrichment",
    "spec-authoring",
    "review",
    "release-planning",
}

BLOCKED_STATES = {"blocked"}

GATE_FIELDS = [f"{stage}.autoApprove" for stage in STAGE_ORDER if stage in GATED_STAGES]

APPROVAL_NEXT_STAGE = {
    "discuss": "capability-review",
    "capability-review": "epic-shaping",
    "epic-shaping": "story-slicing",
    "story-slicing": "story-enrichment",
    "story-enrichment": "spec-authoring",
    "spec-authoring": "implementation-planning",
    "implementation-planning": "implementation",
    "implementation": "review",
    "review": "release-planning",
    "release-planning": "done",
}

REWORK_TARGET = {
    "capability-review": "capability-review",
    "epic-shaping": "epic-shaping",
    "story-slicing": "story-slicing",
    "story-enrichment": "story-enrichment",
    "spec-authoring": "spec-authoring",
    "review": "implementation-planning",
    "release-planning": "release-planning",
}

NEXT_ACTION = {
    "discuss": "classify initiative and gather context",
    "capability-review": "review capability inventory and approve or reject before epic shaping continues",
    "epic-shaping": "review epic draft and approve or reject before story slicing continues",
    "story-slicing": "review story slices and approve or reject before story enrichment continues",
    "story-enrichment": "review story scope, acceptance criteria, and test expectations",
    "spec-authoring": "review proposal/spec/tasks and approve or reject before implementation continues",
    "implementation-planning": "choose the next PR-sized slice",
    "implementation": "implement the selected slice and run validation",
    "review": "review PR outcome and approve or reject",
    "release-planning": "review rollout plan and approve or reject",
    "done": "workflow complete",
}

STATE_FIELDS = [
    "Current stage",
    "Human gate status",
    "Blocked reason",
    "Rework target",
    "Rejection reason",
    "Approval note",
    "Active items",
    "Deferred items",
    "Item note",
    "Challenge note",
    "Next action",
]

CONTRACT_FIELDS = [
    "OpenSpec required",
    "OpenSpec initialized",
    "OpenSpec waived",
    "OpenSpec waiver reason",
    "OpenSpec lane active",
]

DEPENDENCY_FIELDS = [
    "Workflow slug",
    "Depends on",
    "Satisfies",
    "Blocked by",
    "Unlocks",
    "Notes",
]

STAGE_ALIASES = {
    "epic-complete": "done",
    "epic complete": "done",
    "epic-shaped": "epic-shaping",
    "epic shaped": "epic-shaping",
    "story-sliced": "story-slicing",
    "story sliced": "story-slicing",
    "story-enriched": "story-enrichment",
    "story enriched": "story-enrichment",
    "implementation-planned": "implementation-planning",
    "implementation planned": "implementation-planning",
}

GATE_STATUS_ALIASES = {
    "awaiting approval": "pending",
    "awaiting epic and story approval": "pending",
    "awaiting story approval": "pending",
    "awaiting review": "pending",
    "epic approved and complete": "approved",
    "approved": "approved",
    "pending": "pending",
    "blocked": "blocked",
    "rejected": "rejected",
}


def normalize_stage_name(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        return ""
    if cleaned in STAGE_ORDER:
        return cleaned
    return STAGE_ALIASES.get(cleaned, cleaned)


def normalize_gate_status(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        return ""
    return GATE_STATUS_ALIASES.get(cleaned, cleaned)


def normalize_state_dict(state: dict[str, str]) -> dict[str, str]:
    normalized = dict(state)
    normalized["Current stage"] = normalize_stage_name(normalized.get("Current stage", ""))
    normalized["Human gate status"] = normalize_gate_status(normalized.get("Human gate status", ""))
    normalized["Rework target"] = normalize_stage_name(normalized.get("Rework target", ""))
    active_items = normalized.get("Active items", "").strip().lower()
    if normalized["Current stage"] == "done" and active_items == "epic complete":
        normalized["Active items"] = ""
    return normalized


def parse_state(path: Path) -> dict[str, str]:
    state = {field: "" for field in STATE_FIELDS}
    if not path.exists():
        return state
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        if key in state:
            state[key] = value.strip()
    return normalize_state_dict(state)


def write_state(path: Path, state: dict[str, str]) -> None:
    state = normalize_state_dict(state)
    lines = ["# State", ""]
    for field in STATE_FIELDS:
        lines.append(f"- {field}: {state.get(field, '').strip()}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def transaction_root(root: Path) -> Path:
    path = root / ".workflow" / "_transactions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_dir_contents(src: Path, dest: Path, skip_names: set[str] | None = None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    skip_names = skip_names or set()
    for child in src.iterdir():
        if child.name in skip_names:
            continue
        target = dest / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)


def clear_directory(path: Path, preserve: set[str] | None = None) -> None:
    preserve = preserve or set()
    if not path.exists():
        return
    for child in path.iterdir():
        if child.name in preserve:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def snapshot_environment(root: Path, workflow_slug: str, command: str) -> Path:
    tx_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    tx_path = transaction_root(root) / workflow_slug / f"{tx_id}-{command}"
    before = tx_path / "before"
    before.mkdir(parents=True, exist_ok=True)
    metadata = {
        "workflow_slug": workflow_slug,
        "command": command,
        "started_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "in-progress",
        "before_fingerprint": environment_fingerprint(root),
    }
    (tx_path / "transaction.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    workflow_root = root / ".workflow"
    if workflow_root.exists():
        copy_dir_contents(workflow_root, before / "workflow", skip_names={"_transactions"})
    openspec_root = root / "openspec"
    if openspec_root.exists():
        copy_dir_contents(openspec_root, before / "openspec")
    return tx_path


COMMAND_PHASES = ["prepare", "command", "postprocess", "diagram", "commit"]


class ResumeRefused(RuntimeError):
    pass


def phase_index(phase: str) -> int:
    return COMMAND_PHASES.index(phase) if phase in COMMAND_PHASES else 0


def next_phase_after(phase: str) -> str:
    index = phase_index(phase)
    if index + 1 >= len(COMMAND_PHASES):
        return "commit"
    return COMMAND_PHASES[index + 1]


def should_run_phase(start_phase: str, phase: str) -> bool:
    return phase_index(start_phase) <= phase_index(phase)


def transaction_metadata(tx_path: Path) -> dict[str, object]:
    metadata_path = tx_path / "transaction.json"
    if not metadata_path.exists():
        return {}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def write_transaction_metadata(tx_path: Path, metadata: dict[str, object]) -> None:
    (tx_path / "transaction.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


def copy_environment_snapshot(root: Path, snapshot_root: Path) -> None:
    workflow_root = root / ".workflow"
    if workflow_root.exists():
        copy_dir_contents(workflow_root, snapshot_root / "workflow", skip_names={"_transactions"})
    openspec_root = root / "openspec"
    if openspec_root.exists():
        copy_dir_contents(openspec_root, snapshot_root / "openspec")


def hash_tree(path: Path, skip_names: set[str] | None = None) -> str:
    skip_names = skip_names or set()
    digest = hashlib.sha256()
    if not path.exists():
        digest.update(b"<missing>")
        return digest.hexdigest()
    for file_path in sorted((item for item in path.rglob("*") if item.is_file()), key=lambda item: item.relative_to(path).as_posix()):
        if any(part in skip_names for part in file_path.relative_to(path).parts):
            continue
        relative = file_path.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def environment_fingerprint(root: Path) -> dict[str, str]:
    return {
        "workflow": hash_tree(root / ".workflow", skip_names={"_transactions"}),
        "openspec": hash_tree(root / "openspec"),
    }


def write_phase_checkpoint(
    root: Path,
    tx_path: Path,
    phase: str,
    context: dict[str, object],
) -> None:
    checkpoint_path = tx_path / "checkpoints" / phase
    if checkpoint_path.exists():
        shutil.rmtree(checkpoint_path)
    checkpoint_path.mkdir(parents=True, exist_ok=True)
    copy_environment_snapshot(root, checkpoint_path / "snapshot")
    completed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    checkpoint_metadata = {
        "phase": phase,
        "next_phase": next_phase_after(phase),
        "completed_at": completed_at,
        "environment_fingerprint": environment_fingerprint(root),
        "context": context,
    }
    (checkpoint_path / "checkpoint.json").write_text(json.dumps(checkpoint_metadata, indent=2) + "\n", encoding="utf-8")

    metadata = transaction_metadata(tx_path)
    history = metadata.get("checkpoint_history", [])
    if not isinstance(history, list):
        history = []
    history.append({"phase": phase, "completed_at": completed_at})
    metadata["status"] = "in-progress"
    metadata["latest_checkpoint"] = phase
    metadata["checkpoint_history"] = history
    write_transaction_metadata(tx_path, metadata)

    if os.environ.get("WRKFLW_FAIL_AFTER_CHECKPOINT", "").strip() == phase:
        raise RuntimeError(f"Injected failure after checkpoint `{phase}`")


def write_command_progress_checkpoint(
    root: Path,
    tx_path: Path,
    name: str,
    context: dict[str, object],
) -> None:
    checkpoint_path = tx_path / "command-checkpoints" / name
    if checkpoint_path.exists():
        shutil.rmtree(checkpoint_path)
    checkpoint_path.mkdir(parents=True, exist_ok=True)
    copy_environment_snapshot(root, checkpoint_path / "snapshot")
    completed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    checkpoint_metadata = {
        "phase": "command",
        "checkpoint_type": "command-progress",
        "name": name,
        "next_phase": "command",
        "completed_at": completed_at,
        "environment_fingerprint": environment_fingerprint(root),
        "context": context,
    }
    (checkpoint_path / "checkpoint.json").write_text(json.dumps(checkpoint_metadata, indent=2) + "\n", encoding="utf-8")

    metadata = transaction_metadata(tx_path)
    history = metadata.get("command_checkpoint_history", [])
    if not isinstance(history, list):
        history = []
    history.append({"name": name, "completed_at": completed_at, "context": context})
    metadata["status"] = "in-progress"
    metadata["latest_command_checkpoint"] = {
        "name": name,
        "completed_at": completed_at,
        "command": str(context.get("command") or ""),
        "completed_count": context.get("completed_count", 0),
    }
    metadata["command_checkpoint_history"] = history
    write_transaction_metadata(tx_path, metadata)

    if os.environ.get("WRKFLW_FAIL_AFTER_COMMAND_CHECKPOINT", "").strip() == name:
        raise RuntimeError(f"Injected failure after command progress checkpoint `{name}`")
    fail_after_count = os.environ.get("WRKFLW_FAIL_AFTER_TEAM_SYNC_ENVELOPES", "").strip()
    if fail_after_count and str(context.get("command") or "") == "team-sync-all":
        try:
            should_fail = int(fail_after_count) == int(context.get("completed_count") or 0)
        except ValueError:
            should_fail = False
        if should_fail:
            raise RuntimeError(f"Injected failure after {fail_after_count} team-sync-all envelope checkpoint(s)")


def restore_snapshot(root: Path, snapshot_root: Path) -> None:
    workflow_snapshot = snapshot_root / "workflow"
    openspec_snapshot = snapshot_root / "openspec"

    workflow_root = root / ".workflow"
    workflow_root.mkdir(parents=True, exist_ok=True)
    clear_directory(workflow_root, preserve={"_transactions"})
    if workflow_snapshot.exists():
        copy_dir_contents(workflow_snapshot, workflow_root)

    openspec_root = root / "openspec"
    if openspec_snapshot.exists():
        if openspec_root.exists():
            shutil.rmtree(openspec_root)
        copy_dir_contents(openspec_snapshot, openspec_root)
    elif openspec_root.exists():
        shutil.rmtree(openspec_root)


def latest_checkpoint_phase(tx_path: Path) -> str:
    metadata = transaction_metadata(tx_path)
    phase = str(metadata.get("latest_checkpoint") or "").strip()
    if phase:
        return phase
    checkpoint_root = tx_path / "checkpoints"
    if not checkpoint_root.exists():
        return ""
    phases = [item.name for item in checkpoint_root.iterdir() if item.is_dir()]
    phases = [phase for phase in phases if phase in COMMAND_PHASES]
    return sorted(phases, key=phase_index)[-1] if phases else ""


def load_checkpoint(tx_path: Path, phase: str) -> dict[str, object]:
    checkpoint_json = tx_path / "checkpoints" / phase / "checkpoint.json"
    if not checkpoint_json.exists():
        return {}
    try:
        payload = json.loads(checkpoint_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_command_progress_checkpoint(tx_path: Path, name: str) -> dict[str, object]:
    checkpoint_json = tx_path / "command-checkpoints" / name / "checkpoint.json"
    if not checkpoint_json.exists():
        return {}
    try:
        payload = json.loads(checkpoint_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def latest_command_progress_checkpoint(tx_path: Path, command: str) -> str:
    metadata = transaction_metadata(tx_path)
    checkpoint = metadata.get("latest_command_checkpoint")
    if not isinstance(checkpoint, dict):
        return ""
    if str(checkpoint.get("command") or "").strip() != command:
        return ""
    name = str(checkpoint.get("name") or "").strip()
    if not name:
        return ""
    checkpoint_json = tx_path / "command-checkpoints" / name / "checkpoint.json"
    return name if checkpoint_json.exists() else ""


def find_resumable_transaction(root: Path, workflow_slug: str, command: str | None = None) -> tuple[Path, str, dict[str, object]]:
    tx_root = transaction_root(root) / workflow_slug
    if not tx_root.exists():
        raise RuntimeError("No transaction history exists for this workflow.")
    for tx_path in sorted((item for item in tx_root.iterdir() if item.is_dir()), reverse=True):
        metadata = transaction_metadata(tx_path)
        tx_command = str(metadata.get("command") or "").strip()
        if command and tx_command != command:
            continue
        if str(metadata.get("status") or "").strip() == "committed":
            continue
        phase = latest_checkpoint_phase(tx_path)
        if phase:
            return tx_path, phase, metadata
    command_note = f" for command `{command}`" if command else ""
    raise RuntimeError(f"No resumable checkpoint found{command_note}.")


def refuse_stale_rollback_resume(root: Path, tx_path: Path, metadata: dict[str, object]) -> None:
    expected_fingerprint = metadata.get("before_fingerprint")
    if str(metadata.get("status") or "").strip() == "rolled-back" and isinstance(expected_fingerprint, dict):
        current_fingerprint = environment_fingerprint(root)
        if current_fingerprint != expected_fingerprint:
            raise ResumeRefused(
                "Refusing to resume because .workflow or openspec changed after rollback. "
                "Start a new command or restore the transaction baseline first."
            )


def restore_from_checkpoint(root: Path, tx_path: Path, phase: str) -> dict[str, object]:
    checkpoint_path = tx_path / "checkpoints" / phase
    if not checkpoint_path.exists():
        raise RuntimeError(f"Checkpoint `{phase}` is missing from {tx_path}.")
    metadata = transaction_metadata(tx_path)
    refuse_stale_rollback_resume(root, tx_path, metadata)
    restore_snapshot(root, checkpoint_path / "snapshot")
    checkpoint = load_checkpoint(tx_path, phase)
    metadata["status"] = "resuming"
    metadata["resumed_from_checkpoint"] = phase
    metadata["resumed_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write_transaction_metadata(tx_path, metadata)
    return checkpoint


def restore_from_command_progress_checkpoint(root: Path, tx_path: Path, name: str) -> dict[str, object]:
    checkpoint_path = tx_path / "command-checkpoints" / name
    if not checkpoint_path.exists():
        raise RuntimeError(f"Command progress checkpoint `{name}` is missing from {tx_path}.")
    metadata = transaction_metadata(tx_path)
    refuse_stale_rollback_resume(root, tx_path, metadata)
    restore_snapshot(root, checkpoint_path / "snapshot")
    checkpoint = load_command_progress_checkpoint(tx_path, name)
    metadata["status"] = "resuming"
    metadata["resumed_from_command_checkpoint"] = name
    metadata["resumed_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write_transaction_metadata(tx_path, metadata)
    return checkpoint


def restore_environment(root: Path, tx_path: Path, error: str) -> None:
    restore_snapshot(root, tx_path / "before")

    metadata = transaction_metadata(tx_path)
    metadata["status"] = "rolled-back"
    metadata["rolled_back_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    metadata["error"] = error
    write_transaction_metadata(tx_path, metadata)


def commit_environment(tx_path: Path) -> None:
    metadata = transaction_metadata(tx_path)
    metadata["status"] = "committed"
    metadata["completed_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    write_transaction_metadata(tx_path, metadata)


def history_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "history.md"


def append_history_event(
    root: Path,
    workflow_slug: str,
    command: str,
    before: dict[str, str],
    after: dict[str, str],
) -> None:
    path = history_path(root, workflow_slug)
    existing = path.read_text(encoding="utf-8") if path.exists() else "# History\n\n"
    seq = len(re.findall(r"^## Event \d+\b", existing, flags=re.MULTILINE)) + 1
    before_active = before.get("Active items", "").strip()
    after_active = after.get("Active items", "").strip()
    focus = after_active or before_active
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    block = [
        f"## Event {seq:03d}",
        f"- Timestamp: {timestamp}",
        f"- Command: {command}",
        f"- From stage: {ensure_stage(before.get('Current stage') or 'discuss') if before.get('Current stage') else '-'}",
        f"- To stage: {ensure_stage(after.get('Current stage') or 'discuss')}",
        f"- Gate: {after.get('Human gate status', '').strip()}",
        f"- Focus items: {focus}",
        f"- Active items: {after_active}",
        f"- Deferred items: {after.get('Deferred items', '').strip()}",
        f"- Approval note: {after.get('Approval note', '').strip()}",
        f"- Rejection reason: {after.get('Rejection reason', '').strip()}",
        f"- Blocked reason: {after.get('Blocked reason', '').strip()}",
        f"- Next action: {after.get('Next action', '').strip()}",
        "",
    ]
    path.write_text(existing.rstrip() + "\n\n" + "\n".join(block), encoding="utf-8")


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        values[key.strip()] = value.strip()
    return values


def clean_markdown_path_ref(value: str) -> str:
    cleaned = value.strip()
    while len(cleaned) >= 2 and cleaned[0] == "`" and cleaned[-1] == "`":
        cleaned = cleaned[1:-1].strip()
    if len(cleaned) >= 2 and cleaned[0] == "<" and cleaned[-1] == ">":
        cleaned = cleaned[1:-1].strip()
    return cleaned


def write_kv_list(path: Path, title: str, fields: list[str], values: dict[str, str]) -> None:
    lines = [f"# {title}", ""]
    for field in fields:
        lines.append(f"- {field}: {values.get(field, '').strip()}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def initiative_status(state: dict[str, str]) -> str:
    stage = ensure_stage(state.get("Current stage") or "discuss")
    gate = (state.get("Human gate status") or "").strip()
    if stage == "done":
        return "done"
    if gate == "blocked":
        return "blocked"
    if gate == "approved":
        return "in-progress"
    return "pending"


def update_initiative_index(root: Path, workflow_slug: str, state: dict[str, str] | None = None) -> None:
    workflow_root = root / ".workflow"
    workflow_root.mkdir(parents=True, exist_ok=True)
    index_path = workflow_root / "initiative-index.md"
    current_state = state or parse_state(workflow_root / workflow_slug / "state.md")
    links = parse_kv_list(workflow_root / workflow_slug / "links.md")

    row = {
        "Workflow slug": workflow_slug,
        "Status": initiative_status(current_state),
        "Current stage": ensure_stage(current_state.get("Current stage") or "discuss"),
        "Design seed": links.get("Design seed", "").strip() or "-",
        "OpenSpec change": links.get("OpenSpec change", "").strip() or "-",
        "Docs": links.get("Docs", "").strip() or "-",
    }

    rows: list[dict[str, str]] = []
    for line in index_path.read_text(encoding="utf-8").splitlines() if index_path.exists() else []:
        stripped = line.strip()
        if not stripped.startswith("|") or "Workflow slug" in stripped or set(stripped) <= {"|", "-", " "}:
            continue
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        if len(parts) != 6:
            continue
        rows.append(
            {
                "Workflow slug": parts[0],
                "Status": parts[1],
                "Current stage": parts[2],
                "Design seed": parts[3],
                "OpenSpec change": parts[4],
                "Docs": parts[5],
            }
        )

    replaced = False
    for index, existing in enumerate(rows):
        if existing["Workflow slug"] == workflow_slug:
            rows[index] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)

    rows.sort(key=lambda item: item["Workflow slug"])
    output = [
        "# Initiative Index",
        "",
        "| Workflow slug | Status | Current stage | Design seed | OpenSpec change | Docs |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in rows:
        output.append(
            f"| {item['Workflow slug']} | {item['Status']} | {item['Current stage']} | {item['Design seed']} | {item['OpenSpec change']} | {item['Docs']} |"
        )
    output.append("")
    index_path.write_text("\n".join(output), encoding="utf-8")


def ensure_stage(stage: str) -> str:
    return stage if stage in STAGE_ORDER else "discuss"


def parse_gate_settings(path: Path) -> dict[str, bool]:
    raw = parse_kv_list(path)
    settings: dict[str, bool] = {}
    for stage in GATED_STAGES:
        value = raw.get(f"{stage}.autoApprove", "false").strip().lower()
        settings[stage] = value in {"true", "1", "yes", "on"}
    return settings


def gate_settings_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "gates.md"


def auto_approve_enabled(root: Path, workflow_slug: str, stage: str) -> bool:
    if stage not in GATED_STAGES:
        return False
    return parse_gate_settings(gate_settings_path(root, workflow_slug)).get(stage, False)


def workflow_contract_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "workflow-contract.md"


def detect_openspec_initialized(root: Path) -> bool:
    return (root / "openspec").exists()


def read_workflow_contract(root: Path, workflow_slug: str) -> dict[str, str]:
    path = workflow_contract_path(root, workflow_slug)
    values = parse_kv_list(path)
    normalized = {field: values.get(field, "").strip() for field in CONTRACT_FIELDS}
    return normalized


def write_workflow_contract(root: Path, workflow_slug: str, values: dict[str, str]) -> None:
    write_kv_list(workflow_contract_path(root, workflow_slug), "Workflow Contract", CONTRACT_FIELDS, values)


def refresh_workflow_contract(root: Path, workflow_slug: str) -> dict[str, str]:
    contract = read_workflow_contract(root, workflow_slug)
    if not contract["OpenSpec required"]:
        contract["OpenSpec required"] = "true"
    contract["OpenSpec initialized"] = "true" if detect_openspec_initialized(root) else "false"
    if not contract["OpenSpec waived"]:
        contract["OpenSpec waived"] = "false"
    if not contract["OpenSpec lane active"]:
        contract["OpenSpec lane active"] = "false"
    write_workflow_contract(root, workflow_slug, contract)
    return contract


def workflow_slugs(root: Path) -> list[str]:
    workflow_root = root / ".workflow"
    if not workflow_root.exists():
        return []
    return sorted(
        path.name
        for path in workflow_root.iterdir()
        if path.is_dir() and not path.name.startswith("_")
    )


def dependency_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "dependencies.md"


def read_dependency_metadata(root: Path, workflow_slug: str) -> dict[str, str]:
    values = parse_kv_list(dependency_path(root, workflow_slug))
    return {field: values.get(field, "").strip() for field in DEPENDENCY_FIELDS}


def write_dependency_metadata(root: Path, workflow_slug: str, values: dict[str, str]) -> None:
    merged = {field: values.get(field, "").strip() for field in DEPENDENCY_FIELDS}
    merged["Workflow slug"] = workflow_slug
    write_kv_list(dependency_path(root, workflow_slug), "Dependencies", DEPENDENCY_FIELDS, merged)


def parse_capability_inventory(path: Path) -> list[dict[str, str]]:
    capabilities: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        line = raw_line.strip()
        if line.startswith("### "):
            if current:
                capabilities.append(current)
            current = {"name": line[4:].strip(), "status": "", "owner": ""}
        elif current and line.startswith("- Status:"):
            current["status"] = line.split(":", 1)[1].strip().lower()
        elif current and line.startswith("- Owning workflow:"):
            current["owner"] = normalize_item_name(line.split(":", 1)[1].strip())
    if current:
        capabilities.append(current)
    return capabilities


def refresh_lane_dependencies(root: Path, workflow_slug: str) -> dict[str, str]:
    existing = read_dependency_metadata(root, workflow_slug)
    depends_on: set[str] = {item.strip() for item in existing.get("Depends on", "").split(",") if item.strip()}
    unlocks: set[str] = {item.strip() for item in existing.get("Unlocks", "").split(",") if item.strip()}
    completed = completed_workflow_dependencies(root)
    capability_path = root / ".workflow" / workflow_slug / "capabilities.md"
    for capability in parse_capability_inventory(capability_path):
        owner = capability.get("owner", "").strip()
        status = capability.get("status", "").strip().lower()
        if owner and owner != workflow_slug:
            if status == "satisfied by prior epic":
                depends_on.add(owner)
            elif status in {"deferred to later epic", "recommended follow-up"}:
                unlocks.add(owner)
    blocked_by = sorted(dep for dep in depends_on if dep not in completed)
    values = {
        "Workflow slug": workflow_slug,
        "Depends on": ", ".join(sorted(depends_on)),
        "Satisfies": workflow_slug,
        "Blocked by": ", ".join(blocked_by),
        "Unlocks": ", ".join(sorted(unlocks)),
        "Notes": existing.get("Notes", ""),
    }
    write_dependency_metadata(root, workflow_slug, values)
    return values


def unresolved_lane_dependencies(root: Path, workflow_slug: str) -> list[str]:
    values = refresh_lane_dependencies(root, workflow_slug)
    blocked = [item.strip() for item in values.get("Blocked by", "").split(",") if item.strip()]
    return blocked


def lane_dependency_block(root: Path, workflow_slug: str, stage: str) -> tuple[bool, str]:
    if stage in {"discuss", "capability-review"}:
        return False, ""
    blocked = unresolved_lane_dependencies(root, workflow_slug)
    if not blocked:
        return False, ""
    return True, f"This workflow depends on incomplete lanes: {', '.join(blocked)}"


def openspec_lane_active(contract: dict[str, str]) -> bool:
    return contract.get("OpenSpec lane active", "false").lower() in {"true", "1", "yes", "on"}


def active_openspec_lanes(root: Path, exclude_slug: str | None = None) -> list[str]:
    active: list[str] = []
    for slug in workflow_slugs(root):
        if exclude_slug and slug == exclude_slug:
            continue
        contract = read_workflow_contract(root, slug)
        state = parse_state(root / ".workflow" / slug / "state.md")
        if openspec_lane_active(contract) and ensure_stage(state.get("Current stage") or "discuss") != "done":
            active.append(slug)
    return active


def set_openspec_lane_active(root: Path, workflow_slug: str, active: bool) -> None:
    contract = refresh_workflow_contract(root, workflow_slug)
    contract["OpenSpec lane active"] = "true" if active else "false"
    write_workflow_contract(root, workflow_slug, contract)


def ensure_openspec_lane(root: Path, workflow_slug: str) -> tuple[bool, str]:
    others = active_openspec_lanes(root, exclude_slug=workflow_slug)
    if others:
        return False, f"Another epic lane already owns active OpenSpec execution: {', '.join(others)}"
    set_openspec_lane_active(root, workflow_slug, True)
    return True, ""


def openspec_block_required(root: Path, workflow_slug: str, stage: str) -> tuple[bool, str]:
    if stage != "spec-authoring":
        return False, ""
    contract = refresh_workflow_contract(root, workflow_slug)
    required = contract.get("OpenSpec required", "true").lower() in {"true", "1", "yes", "on"}
    initialized = contract.get("OpenSpec initialized", "false").lower() in {"true", "1", "yes", "on"}
    waived = contract.get("OpenSpec waived", "false").lower() in {"true", "1", "yes", "on"}
    if required and not initialized and not waived:
        return True, "OpenSpec is required for this workflow but is not initialized. Initialize OpenSpec or use an explicit override before implementation continues."
    return False, ""


def maybe_bridge_to_openspec(root: Path, workflow_slug: str) -> None:
    openspec_dir = root / "openspec"
    bridge_script = Path(__file__).with_name("bridge_workflow_to_openspec.py")
    if not openspec_dir.exists() or not bridge_script.exists():
        return
    contract = refresh_workflow_contract(root, workflow_slug)
    if not openspec_lane_active(contract):
        return
    run(
        ["python3", str(bridge_script), "--slug", workflow_slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_generate_release_plan(root: Path, workflow_slug: str) -> None:
    release_script = Path(__file__).with_name("generate_release_plan.py")
    if not release_script.exists():
        return
    run(
        ["python3", str(release_script), "--slug", workflow_slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_generate_implementation_plan(root: Path, workflow_slug: str) -> None:
    plan_script = Path(__file__).with_name("generate_implementation_plan.py")
    if not plan_script.exists():
        return
    run(
        ["python3", str(plan_script), "--slug", workflow_slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_generate_team_dispatch(root: Path, workflow_slug: str) -> None:
    dispatch_script = Path(__file__).with_name("generate_team_dispatch.py")
    if not dispatch_script.exists():
        return
    run(
        ["python3", str(dispatch_script), "--slug", workflow_slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_generate_parallel_dispatch(root: Path, workflow_slug: str) -> None:
    dispatch_script = Path(__file__).with_name("generate_parallel_dispatch.py")
    if not dispatch_script.exists():
        return
    run(
        ["python3", str(dispatch_script), "--slug", workflow_slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_generate_execution_path(root: Path, workflow_slug: str, active_story: str | None = None) -> None:
    path_script = Path(__file__).with_name("workflow_execution_paths.py")
    dag_path = root / ".workflow" / workflow_slug / "dag.json"
    if not path_script.exists() or not dag_path.exists():
        return
    command = ["python3", str(path_script), "--slug", workflow_slug, "--root", str(root)]
    if active_story:
        command.extend(["--active-story", active_story])
    run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_generate_story_slices(root: Path, workflow_slug: str) -> None:
    story_script = Path(__file__).with_name("generate_story_slices.py")
    if not story_script.exists():
        return
    run(
        ["python3", str(story_script), "--slug", workflow_slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_generate_story_dag(root: Path, workflow_slug: str, required: bool = False) -> None:
    stories_path = root / ".workflow" / workflow_slug / "stories.md"
    dag_script = Path(__file__).with_name("generate_story_dag.py")
    if not dag_script.exists():
        return
    if not stories_path.exists() and not required:
        return
    if stories_path.exists() and not required and not re.search(r"^##\s+Story\s+", stories_path.read_text(encoding="utf-8"), flags=re.MULTILINE):
        return
    run(
        ["python3", str(dag_script), "--slug", workflow_slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_generate_story_enrichment(root: Path, workflow_slug: str) -> None:
    enrichment_script = Path(__file__).with_name("generate_story_enrichment.py")
    if not enrichment_script.exists():
        return
    run(
        ["python3", str(enrichment_script), "--slug", workflow_slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_seed_from_design(root: Path, workflow_slug: str, design_file: str | None = None) -> None:
    seed_script = Path(__file__).with_name("seed_workflow_from_design.py")
    if not seed_script.exists():
        return
    command = ["python3", str(seed_script), "--slug", workflow_slug, "--root", str(root)]
    if design_file:
        command.extend(["--design-file", design_file])
    run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_generate_capability_inventory(root: Path, workflow_slug: str) -> None:
    inventory_script = Path(__file__).with_name("generate_capability_inventory.py")
    if not inventory_script.exists():
        return
    run(
        ["python3", str(inventory_script), "--slug", workflow_slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def maybe_ensure_team_artifacts(root: Path, workflow_slug: str) -> None:
    team_script = Path(__file__).with_name("ensure_team_artifacts.py")
    if not team_script.exists():
        return
    run(
        ["python3", str(team_script), "--slug", workflow_slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )


def parse_team_settings(root: Path, workflow_slug: str) -> dict[str, str]:
    base = parse_kv_list(root / ".workflow" / "team-config.md")
    override = parse_kv_list(root / ".workflow" / workflow_slug / "team-overrides.md")
    settings = dict(base)
    if override.get("Team size override", "").strip():
        settings["Team size"] = override["Team size override"].strip()
    if override.get("Parallel implementation slots override", "").strip():
        settings["Parallel implementation slots"] = override["Parallel implementation slots override"].strip()
    return settings


def parse_markdown_table_rows(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if "---" in stripped:
            continue
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        if parts and parts[0] not in {"Role", "Work Item", "Date"}:
            rows.append(parts)
    return rows


def unresolved_review_summary(path: Path) -> str:
    findings: list[str] = []
    for row in parse_markdown_table_rows(path):
        if len(row) < 5:
            continue
        role, severity, finding, resolution = row[1], row[2], row[3], row[4]
        if not finding:
            continue
        if not resolution.strip() or resolution.strip().lower() in {"-", "open", "pending"}:
            findings.append(f"{role} ({severity}): {finding}")
    return "; ".join(findings[:3])


OPEN_RESOLUTION_VALUES = {"", "-", "open", "pending", "unresolved", "todo", "tbd"}
BLOCKING_CONFLICT_VALUES = {"blocking", "blocker", "critical", "high"}


def unresolved_review_block_summary(path: Path) -> str:
    findings: list[str] = []
    for row in parse_markdown_table_rows(path):
        if len(row) < 5:
            continue
        role, severity, finding, resolution = row[1], row[2], row[3], row[4]
        if severity.strip().lower() not in BLOCKING_CONFLICT_VALUES:
            continue
        if resolution.strip().lower() not in OPEN_RESOLUTION_VALUES:
            continue
        if finding.strip():
            findings.append(f"{role} ({severity}): {finding}")
    return "; ".join(findings[:3])


def unresolved_conflict_summary(path: Path, blocking_only: bool = True) -> str:
    conflicts: list[str] = []
    for row in parse_markdown_table_rows(path):
        if len(row) < 9:
            continue
        _, _, raised_by, severity, conflict, _, _, resolution, _ = row[:9]
        severity_clean = severity.strip().lower()
        resolution_clean = resolution.strip().lower()
        if blocking_only and severity_clean not in BLOCKING_CONFLICT_VALUES:
            continue
        if resolution_clean not in OPEN_RESOLUTION_VALUES:
            continue
        if conflict.strip():
            conflicts.append(f"{raised_by} ({severity}): {conflict}")
    return "; ".join(conflicts[:3])


def collaboration_block(root: Path, workflow_slug: str) -> tuple[bool, str]:
    review_summary = unresolved_review_block_summary(root / ".workflow" / workflow_slug / "review-log.md")
    if review_summary:
        return True, f"Unresolved blocking review finding: {review_summary}"
    summary = unresolved_conflict_summary(root / ".workflow" / workflow_slug / "conflicts.md")
    if summary:
        return True, f"Unresolved blocking collaboration conflict: {summary}"
    return False, ""


def payload_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(";") if item.strip()]
    return []


def merge_gate_required(root: Path, workflow_slug: str, stage: str) -> bool:
    if stage not in {"review", "release-planning", "done"}:
        return False
    runtime = parse_kv_list(root / ".workflow" / workflow_slug / "runtime-contract.md")
    if runtime.get("Runtime mode", "").strip() == "parallel-dag-level-team":
        return True
    manifest_path = root / ".workflow" / workflow_slug / "worktrees" / "manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True
    entries = manifest.get("entries", []) if isinstance(manifest, dict) else []
    command = str(manifest.get("command", "") if isinstance(manifest, dict) else "")
    return command in {"team-run-level", "team-run"} and isinstance(entries, list) and bool(entries)


def merge_apply_complete(root: Path, workflow_slug: str) -> bool:
    path = merge_apply_path(root, workflow_slug)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if str(payload.get("status") or "").strip().lower() != "applied":
        return False
    current_head = run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    if current_head.returncode != 0:
        return False
    if str(payload.get("post_head") or "") != current_head.stdout.strip():
        return False
    merge_path = merge_gate_path(root, workflow_slug)
    merge_gate = payload.get("merge_gate", {})
    merge_gate = merge_gate if isinstance(merge_gate, dict) else {}
    return str(merge_gate.get("sha256") or "") == file_sha256(merge_path)


def merge_gate_block(root: Path, workflow_slug: str, stage: str) -> tuple[bool, str]:
    if not merge_gate_required(root, workflow_slug, stage):
        return False, ""
    if merge_apply_complete(root, workflow_slug):
        return False, ""
    gate_path = merge_gate_path(root, workflow_slug)
    if not gate_path.exists():
        return True, "Merge gate is required after isolated worktree dispatch; run wrkflw:merge-gate before review approval."
    try:
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True, "Merge gate artifact is unreadable; rerun wrkflw:merge-gate."
    manifest_path = root / ".workflow" / workflow_slug / "worktrees" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return True, "Worktree manifest is missing or unreadable; rerun wrkflw:team-run-level or reconcile the worktrees."
    if str(gate.get("manifest_generated_at") or "") != str(manifest.get("generated_at") or ""):
        return True, "Merge gate is stale because worktree manifest changed; rerun wrkflw:merge-gate."
    current_head = run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    if current_head.returncode == 0 and str(gate.get("current_head") or "") != current_head.stdout.strip():
        return True, "Merge gate is stale because repository HEAD changed; rerun wrkflw:merge-gate."
    if str(gate.get("status") or "").strip().lower() != "ready":
        blockers = payload_list(gate.get("blockers"))
        return True, "Merge gate is blocked: " + "; ".join(blockers[:3] or ["review merge-gate.md"])
    return False, ""


def file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merge_gate_has_changed_paths(gate: dict[str, object]) -> bool:
    entries = gate.get("entries", [])
    entries = entries if isinstance(entries, list) else []
    for entry in entries:
        if isinstance(entry, dict) and payload_list(entry.get("changed_paths")):
            return True
    return False


def merge_apply_required(root: Path, workflow_slug: str, stage: str) -> bool:
    if not merge_gate_required(root, workflow_slug, stage):
        return False
    gate_path = merge_gate_path(root, workflow_slug)
    if not gate_path.exists():
        return False
    try:
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return str(gate.get("status") or "").strip().lower() == "ready" and merge_gate_has_changed_paths(gate)


def merge_apply_block(root: Path, workflow_slug: str, stage: str) -> tuple[bool, str]:
    if not merge_apply_required(root, workflow_slug, stage):
        return False, ""
    if merge_apply_complete(root, workflow_slug):
        return False, ""
    path = merge_apply_path(root, workflow_slug)
    if not path.exists():
        return True, "Merge apply is required after merge-gate; run wrkflw:merge-apply with `confirm: merge-apply` before integration-gate or review approval."
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True, "Merge apply artifact is unreadable; rerun wrkflw:merge-apply."
    status = str(payload.get("status") or "").strip().lower()
    if status != "applied":
        blockers = payload_list(payload.get("blockers"))
        return True, "Merge apply is blocked: " + "; ".join(blockers[:3] or ["review merge-apply.md"])
    return True, "Merge apply is stale because repository HEAD or merge-gate changed; rerun merge-gate and merge-apply."


def integration_gate_required(root: Path, workflow_slug: str, stage: str) -> bool:
    return merge_gate_required(root, workflow_slug, stage)


def integration_gate_block(root: Path, workflow_slug: str, stage: str) -> tuple[bool, str]:
    if not integration_gate_required(root, workflow_slug, stage):
        return False, ""
    gate_path = integration_gate_path(root, workflow_slug)
    if not gate_path.exists():
        return True, "Integration test gate is required after merge-gate; run wrkflw:integration-gate before review approval."
    try:
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True, "Integration test gate artifact is unreadable; rerun wrkflw:integration-gate."
    if str(gate.get("status") or "").strip().lower() in {"", "not_recorded"}:
        return True, "Integration test gate is required after merge-gate; run wrkflw:integration-gate before review approval."
    merge_path = merge_gate_path(root, workflow_slug)
    if not merge_path.exists():
        return True, "Merge gate artifact is missing; rerun wrkflw:merge-gate before integration-gate."
    try:
        merge_payload = json.loads(merge_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True, "Merge gate artifact is unreadable; rerun wrkflw:merge-gate before integration-gate."
    merge_gate = gate.get("merge_gate", {})
    merge_gate = merge_gate if isinstance(merge_gate, dict) else {}
    if str(merge_gate.get("sha256") or "") != file_sha256(merge_path):
        return True, "Integration test gate is stale because merge-gate changed; rerun wrkflw:integration-gate."
    if merge_gate_has_changed_paths(merge_payload):
        apply_path = merge_apply_path(root, workflow_slug)
        if not apply_path.exists():
            return True, "Merge apply artifact is missing; rerun wrkflw:merge-apply before integration-gate."
        merge_apply = gate.get("merge_apply", {})
        merge_apply = merge_apply if isinstance(merge_apply, dict) else {}
        if str(merge_apply.get("sha256") or "") != file_sha256(apply_path):
            return True, "Integration test gate is stale because merge-apply changed; rerun wrkflw:integration-gate."
    dag = gate.get("dag", {})
    dag = dag if isinstance(dag, dict) else {}
    dag_path_value = root / ".workflow" / workflow_slug / "dag.json"
    if str(dag.get("sha256") or "") != file_sha256(dag_path_value):
        return True, "Integration test gate is stale because dag.json changed; rerun wrkflw:integration-gate."
    allowlist = gate.get("allowlist", {})
    allowlist = allowlist if isinstance(allowlist, dict) else {}
    if allowlist:
        allowlist_path = integration_allowlist_path(root, workflow_slug)
        if str(allowlist.get("sha256") or "") != file_sha256(allowlist_path):
            return True, "Integration test gate is stale because integration-test-allowlist.json changed; rerun wrkflw:integration-gate."
    current_head = run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True)
    if current_head.returncode == 0 and str(gate.get("current_head") or "") != current_head.stdout.strip():
        return True, "Integration test gate is stale because repository HEAD changed; rerun wrkflw:integration-gate."
    status = str(gate.get("status") or "").strip().lower()
    if status not in {"ready", "not_required"}:
        blockers = payload_list(gate.get("blockers"))
        return True, "Integration test gate is blocked: " + "; ".join(blockers[:3] or ["review integration-test-gate.md"])
    return False, ""


def replace_or_append_bullet(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    target = f"- {key}:"
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith(target):
            lines[index] = f"{target} {value}"
            replaced = True
            break
    if not replaced:
        insert_at = next((index for index, line in enumerate(lines) if line.startswith("## ")), len(lines))
        while insert_at > 0 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, f"{target} {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def replace_or_append_role_line(path: Path, role: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    target = f"- {role}:"
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith(target):
            lines[index] = f"{target} {value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{target} {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_directives(raw: str | None) -> dict[str, str]:
    if not raw or not raw.strip():
        return {}
    segments = [segment.strip() for segment in re.split(r"[;\n]+", raw) if segment.strip()]
    directives: dict[str, str] = {}
    parsed_any = False
    for segment in segments:
        if ":" in segment:
            key, value = segment.split(":", 1)
        elif "=" in segment:
            key, value = segment.split("=", 1)
        else:
            continue
        parsed_any = True
        directives[key.strip().lower()] = value.strip()
    if not parsed_any:
        directives["note"] = raw.strip()
    return directives


REPORT_LABELS = {
    "role": "role",
    "status": "status",
    "verdict": "verdict",
    "summary": "summary",
    "note": "summary",
    "follow-up": "follow-up",
    "follow up": "follow-up",
    "blocked by": "blocked-by",
    "blocked-by": "blocked-by",
    "reviewer": "reviewer",
    "files changed": "files-changed",
    "changed files": "files-changed",
    "validation run": "validation-run",
    "validation": "validation-run",
    "missing requirements": "missing-requirements",
    "missing requirement": "missing-requirements",
    "incorrect assumptions": "incorrect-assumptions",
    "incorrect assumption": "incorrect-assumptions",
    "risks": "risks",
    "risk": "risks",
    "questions": "questions",
    "question": "questions",
    "suggested changes": "suggested-changes",
    "suggested change": "suggested-changes",
    "evidence": "evidence",
    "conflict entries": "conflict-entries",
    "conflict entry": "conflict-entries",
    "conflicts": "conflict-entries",
    "assumption updates": "assumption-updates",
    "assumption update": "assumption-updates",
    "assumptions": "assumption-updates",
    "red-team notes": "red-team-notes",
    "red team notes": "red-team-notes",
    "red-team note": "red-team-notes",
    "red team note": "red-team-notes",
    "findings": "findings",
    "debt entries": "debt-entries",
    "debt entry": "debt-entries",
    "technical debt": "debt-entries",
    "memory entries": "memory-entries",
    "memory entry": "memory-entries",
    "shared memory": "memory-entries",
    "learning memory": "memory-entries",
    "model": "model",
    "input tokens": "input-tokens",
    "input-tokens": "input-tokens",
    "tokens in": "input-tokens",
    "prompt tokens": "input-tokens",
    "output tokens": "output-tokens",
    "output-tokens": "output-tokens",
    "tokens out": "output-tokens",
    "completion tokens": "output-tokens",
    "cost usd": "cost-usd",
    "cost-usd": "cost-usd",
    "estimated cost usd": "estimated-cost-usd",
    "estimated-cost-usd": "estimated-cost-usd",
    "cost source": "cost-source",
    "elapsed seconds": "elapsed-seconds",
    "elapsed-seconds": "elapsed-seconds",
    "duration ms": "duration-ms",
    "duration-ms": "duration-ms",
    "invocation id": "invocation-id",
    "invocation-id": "invocation-id",
    "execution id": "execution-id",
    "execution-id": "execution-id",
    "run id": "run-id",
    "run-id": "run-id",
    "parent invocation id": "parent-invocation-id",
    "parent-invocation-id": "parent-invocation-id",
    "agent node id": "agent-node-id",
    "agent-node-id": "agent-node-id",
    "reasoner id": "reasoner-id",
    "reasoner-id": "reasoner-id",
    "attempt": "attempt",
    "retry count": "retry-count",
    "retry-count": "retry-count",
    "transport retry count": "transport-retry-count",
    "transport-retry-count": "transport-retry-count",
    "schema": "schema",
    "schema version": "schema",
    "schema-version": "schema",
}

REPORT_LIST_FIELDS = {
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
}


def parse_structured_agent_report(raw: str | None) -> dict[str, object]:
    if not raw or not raw.strip():
        return {}
    lines = [line.rstrip() for line in raw.strip().splitlines()]
    values: dict[str, object] = {}
    current_key: str | None = None
    current_items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("```"):
            continue
        if ":" in stripped:
            raw_key, raw_value = stripped.split(":", 1)
            normalized = REPORT_LABELS.get(raw_key.strip().lower())
            if normalized:
                if current_key and current_key in REPORT_LIST_FIELDS:
                    values[current_key] = list(current_items)
                elif current_key and current_items and current_key not in values:
                    values[current_key] = " ".join(current_items).strip()
                current_key = normalized
                current_items = []
                value = raw_value.strip()
                if normalized in REPORT_LIST_FIELDS:
                    if value and value.lower() != "none":
                        current_items.append(value)
                    elif value.lower() == "none":
                        values[normalized] = []
                        current_key = None
                    continue
                if value:
                    values[normalized] = value
                    current_key = None
                continue
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if current_key in REPORT_LIST_FIELDS:
                if item.lower() == "none":
                    values[current_key] = []
                    current_key = None
                    current_items = []
                else:
                    current_items.append(item)
            elif current_key:
                current_items.append(item)
        elif current_key:
            current_items.append(stripped)
    if current_key and current_key in REPORT_LIST_FIELDS:
        values[current_key] = list(current_items)
    elif current_key and current_items and current_key not in values:
        values[current_key] = " ".join(current_items).strip()
    return values


def report_list(report: dict[str, object], key: str) -> list[str]:
    value = report.get(key, [])
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def agent_results_dir(root: Path, workflow_slug: str) -> Path:
    path = root / ".workflow" / workflow_slug / "agent-results"
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent_sync_ledger_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "agent-sync-ledger.md"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def parse_sync_ledger(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for row in parse_markdown_table_rows(path):
        if row and row[0] == "Timestamp":
            continue
        if len(row) >= 4:
            entries[row[1]] = row[2]
    return entries


def append_sync_ledger_entry(path: Path, source: str, digest: str, role: str, status: str) -> None:
    if not path.exists():
        path.write_text(
            "# Agent Sync Ledger\n\n| Timestamp | Source | Digest | Role | Status |\n| --- | --- | --- | --- | --- |\n",
            encoding="utf-8",
        )
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"| {timestamp} | {source} | {digest} | {role} | {status} |\n")


def load_team_sync_payload(root: Path, workflow_slug: str, raw: str) -> tuple[str, str | None, str | None]:
    candidate = raw.strip()
    if not candidate:
        return "", None, None
    if "\n" in candidate or "\r" in candidate:
        return raw, None, None
    possible = Path(candidate)
    if not possible.is_absolute():
        possible = (root / candidate).resolve()
    try:
        is_result_file = possible.exists() and possible.is_file()
    except OSError:
        return raw, None, None
    if is_result_file:
        digest = file_hash(possible)
        try:
            source = str(possible.relative_to(root))
        except ValueError:
            source = str(possible)
        return possible.read_text(encoding="utf-8"), source, digest
    return raw, None, None


def agent_result_candidate_paths(root: Path, workflow_slug: str) -> list[Path]:
    candidates = set(agent_results_dir(root, workflow_slug).glob("*.md"))
    manifest_path = root / ".workflow" / workflow_slug / "worktrees" / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
        entries = manifest.get("entries", []) if isinstance(manifest, dict) else []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                worktree_path = Path(str(entry.get("path") or ""))
                result_envelope = str(entry.get("result_envelope") or "").strip()
                if worktree_path.exists() and result_envelope:
                    candidates.add(worktree_path / result_envelope)
    return sorted(path for path in candidates if path.exists() and path.is_file())


def path_source(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def canonical_role_name(value: str) -> str:
    cleaned = value.strip().lower()
    aliases = {
        "product owner": "Product Owner",
        "po": "Product Owner",
        "tech lead": "Tech Lead",
        "tl": "Tech Lead",
        "implementer": "Implementer 1",
        "implementer 1": "Implementer 1",
        "implementer1": "Implementer 1",
        "implementer-1": "Implementer 1",
        "implementer 2": "Implementer 2",
        "implementer2": "Implementer 2",
        "implementer-2": "Implementer 2",
        "reviewer qa": "Reviewer QA",
        "reviewer": "Reviewer QA",
        "qa": "Reviewer QA",
    }
    return aliases.get(cleaned, value.strip())


def role_slot(role: str) -> str:
    return {
        "Product Owner": "product-owner",
        "Tech Lead": "tech-lead",
        "Implementer 1": "implementer-1",
        "Implementer 2": "implementer-2",
        "Reviewer QA": "reviewer-qa",
    }.get(role, re.sub(r"[^a-z0-9]+", "-", role.strip().lower()).strip("-"))


def team_role_directives(directives: dict[str, str]) -> dict[str, str]:
    role_updates: dict[str, str] = {}
    for key, value in directives.items():
        role = canonical_role_name(key)
        if role in {"Product Owner", "Tech Lead", "Implementer 1", "Implementer 2", "Reviewer QA"}:
            role_updates[role] = value
    return role_updates


def team_role_ownership_directives(directives: dict[str, str]) -> dict[str, str]:
    ownership_updates: dict[str, str] = {}
    for key, value in directives.items():
        normalized = key.strip().lower()
        if normalized.endswith(" ownership"):
            role = canonical_role_name(normalized[: -len(" ownership")])
            if role in {"Product Owner", "Tech Lead", "Implementer 1", "Implementer 2", "Reviewer QA"}:
                ownership_updates[role] = value
    return ownership_updates


def parse_assignment_rows(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for parts in parse_markdown_table_rows(path):
        if len(parts) < 6:
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


def write_assignment_rows(path: Path, workflow_slug: str, rows: dict[str, dict[str, str]]) -> None:
    order = ["Product Owner", "Tech Lead", "Implementer 1", "Implementer 2", "Reviewer QA"]
    output = [
        "# Agent Assignments",
        "",
        f"- Workflow slug: {workflow_slug}",
        "- Team config source: `.workflow/team-config.md`",
        f"- Override source: `.workflow/{workflow_slug}/team-overrides.md`",
        "",
        "| Role | Slot | Responsibility Focus | Default Ownership | Allowed Write Paths | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for role in order:
        row = rows.get(role)
        if not row:
            continue
        output.append(
            f"| {row['Role']} | {row['Slot']} | {row['Responsibility Focus']} | {row['Default Ownership']} | {row.get('Allowed Write Paths', '')} | {row['Status']} |"
        )
    output.extend(
        [
            "",
            "## Assignment Rules",
            "",
            "- Do not let every role write to every file.",
            "- Treat workflow/OpenSpec/design artifacts as the shared contract.",
            "- Keep implementer ownership disjoint when parallel implementation slots are greater than 1.",
            "- Express write scope as comma-separated path prefixes in `Allowed Write Paths`.",
            "- Record independent role verdicts in `role-reviews.md` before reconciliation when reviewing scope, spec, implementation plan, or release readiness.",
            "",
        ]
    )
    path.write_text("\n".join(output), encoding="utf-8")


PLACEHOLDER_ALLOWED_PATHS = {
    "-",
    "none",
    "declare concrete module/file prefixes before parallel team-run",
}


def parse_allowed_paths(value: str) -> list[str]:
    items: list[str] = []
    for raw_line in value.splitlines() or [value]:
        line = raw_line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        for item in line.split(","):
            cleaned = item.strip().rstrip("/")
            if not cleaned:
                continue
            if cleaned.lower() in PLACEHOLDER_ALLOWED_PATHS:
                continue
            items.append(cleaned)
    return items


def story_allowed_write_paths(root: Path, workflow_slug: str, active_story: str) -> list[str]:
    match = re.search(r"(\d+)", active_story)
    if not match:
        return []
    story_path = root / ".workflow" / workflow_slug / f"story-{match.group(1)}.md"
    if not story_path.exists():
        return []

    capture = False
    lines: list[str] = []
    for raw_line in story_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("## "):
            if capture:
                break
            capture = stripped[3:].strip().lower() == "allowed write paths"
            continue
        if capture:
            lines.append(raw_line)
    return parse_allowed_paths("\n".join(lines))


def paths_overlap(left: str, right: str) -> bool:
    a = left.rstrip("/")
    b = right.rstrip("/")
    if not a or not b:
        return False
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def implementer_scope_conflict(rows: dict[str, dict[str, str]], parallel_slots: int) -> tuple[bool, str]:
    if parallel_slots <= 1:
        return False, ""
    lane1 = rows.get("Implementer 1")
    lane2 = rows.get("Implementer 2")
    if not lane1 or not lane2:
        return True, "Parallel implementer lanes are enabled, but implementer assignments are incomplete."
    paths1 = parse_allowed_paths(lane1.get("Allowed Write Paths", ""))
    paths2 = parse_allowed_paths(lane2.get("Allowed Write Paths", ""))
    if not paths1 or not paths2:
        return True, "Parallel implementer lanes require explicit allowed write paths for both Implementer 1 and Implementer 2."
    for left in paths1:
        for right in paths2:
            if paths_overlap(left, right):
                return True, f"Parallel implementer ownership overlaps: `{left}` conflicts with `{right}`."
    return False, ""


def path_allowed(changed_path: str, allowed_paths: list[str]) -> bool:
    normalized = changed_path.strip().lstrip("./").rstrip("/")
    if not normalized:
        return True
    for allowed in allowed_paths:
        allowed_normalized = allowed.strip().lstrip("./").rstrip("/")
        if not allowed_normalized:
            continue
        if allowed_normalized.endswith("/**"):
            prefix = allowed_normalized[:-3].rstrip("/")
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True
        if "*" in allowed_normalized or "?" in allowed_normalized:
            if fnmatch(normalized, allowed_normalized):
                return True
        if normalized == allowed_normalized or normalized.startswith(allowed_normalized + "/"):
            return True
    return False


def validate_changed_paths(
    role: str,
    rows: dict[str, dict[str, str]],
    changed_paths: list[str],
    fallback_allowed_paths: list[str] | None = None,
) -> tuple[bool, str]:
    if not changed_paths:
        return True, ""
    allowed_paths = parse_allowed_paths(rows.get(role, {}).get("Allowed Write Paths", ""))
    if not allowed_paths and role.startswith("Implementer"):
        allowed_paths = fallback_allowed_paths or []
    if not allowed_paths:
        return True, ""
    invalid = [path for path in changed_paths if path.lower() != "none" and not path_allowed(path, allowed_paths)]
    if invalid:
        return (
            False,
            f"{role} reported changes outside allowed write scope: {', '.join(invalid[:3])}. "
            f"Allowed paths: {', '.join(allowed_paths)}",
        )
    return True, ""


def clear_resolved_team_sync_block(state: dict[str, str]) -> None:
    if state.get("Human gate status") != "blocked":
        return
    reason = state.get("Blocked reason", "").strip()
    team_sync_block = (
        reason.startswith("team-sync requires")
        or reason.startswith("team-sync received unsupported status")
        or reason.startswith("Agent result schema validation failed")
        or "reported changes outside allowed write scope" in reason
    )
    if not team_sync_block:
        return
    current = ensure_stage(state.get("Current stage") or "discuss")
    state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
    state["Blocked reason"] = ""


def finding_severity_and_text(raw: str) -> tuple[str, str]:
    text = raw.strip()
    if not text:
        return "medium", ""
    match = re.match(r"^(critical|high|medium|low|info)\s*:\s*(.+)$", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower(), match.group(2).strip()
    return "medium", text


def conflict_severity_and_text(raw: str) -> tuple[str, str]:
    direct = re.match(r"^(blocking|important|minor)\s*:\s*(.+)$", raw.strip(), flags=re.IGNORECASE)
    if direct:
        return direct.group(1).lower(), direct.group(2).strip()
    severity, text = finding_severity_and_text(raw)
    if severity in {"critical", "high"}:
        return "blocking", text
    if severity == "medium":
        return "important", text
    if severity in {"low", "info"}:
        return "minor", text
    lowered = severity.lower()
    if lowered in {"blocking", "important", "minor"}:
        return lowered, text
    return "important", text


def table_cell(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned.replace("|", "\\|") if cleaned else "-"


def list_table_cell(items: list[str]) -> str:
    return "; ".join(item for item in items if item.strip()) or "-"


def ensure_table_file(path: Path, title: str, header: str, divider: str) -> str:
    text = path.read_text(encoding="utf-8") if path.exists() else f"# {title}\n\n{header}\n{divider}\n"
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def append_role_review_entry(
    path: Path,
    story: str,
    role: str,
    verdict: str,
    missing_requirements: list[str],
    incorrect_assumptions: list[str],
    risks: list[str],
    questions: list[str],
    suggested_changes: list[str],
    evidence: list[str],
    red_team_notes: list[str],
) -> None:
    text = ensure_table_file(
        path,
        "Role Reviews",
        "| Date | Story | Role | Verdict | Missing Requirements | Incorrect Assumptions | Risks | Questions | Suggested Changes | Evidence | Red-team Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    )
    date_value = datetime.now(timezone.utc).date().isoformat()
    row = [
        date_value,
        story or "-",
        role,
        verdict or "-",
        list_table_cell(missing_requirements),
        list_table_cell(incorrect_assumptions),
        list_table_cell(risks),
        list_table_cell(questions),
        list_table_cell(suggested_changes),
        list_table_cell(evidence),
        list_table_cell(red_team_notes),
    ]
    path.write_text(text + "| " + " | ".join(table_cell(item) for item in row) + " |\n", encoding="utf-8")


def append_conflict_entry(
    path: Path,
    story: str,
    role: str,
    severity: str,
    conflict: str,
    recommendation: str,
    resolution: str,
) -> None:
    text = ensure_table_file(
        path,
        "Conflict Register",
        "| Date | Story | Raised By | Severity | Conflict | Options | Recommendation | Resolution | Owner |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    )
    date_value = datetime.now(timezone.utc).date().isoformat()
    row = [
        date_value,
        story or "-",
        role,
        severity or "important",
        conflict,
        "-",
        recommendation or "-",
        resolution or "open",
        role,
    ]
    path.write_text(text + "| " + " | ".join(table_cell(item) for item in row) + " |\n", encoding="utf-8")


def append_assumption_entry(
    path: Path,
    story: str,
    role: str,
    confidence: str,
    assumption: str,
    impact: str,
    validation_step: str,
) -> None:
    text = ensure_table_file(
        path,
        "Assumption Ledger",
        "| Date | Story | Source | Confidence | Assumption | Impact If Wrong | Validation Step |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    )
    date_value = datetime.now(timezone.utc).date().isoformat()
    row = [
        date_value,
        story or "-",
        role,
        confidence or "unknown",
        assumption,
        impact or "-",
        validation_step or "-",
    ]
    path.write_text(text + "| " + " | ".join(table_cell(item) for item in row) + " |\n", encoding="utf-8")


def append_review_log_entry(
    path: Path,
    role: str,
    severity: str,
    finding: str,
    resolution: str,
) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else "# Review Log\n\n## Findings\n\n| Date | Role | Severity | Finding | Resolution |\n| --- | --- | --- | --- | --- |\n"
    if text and not text.endswith("\n"):
        text += "\n"
    date_value = datetime.now(timezone.utc).date().isoformat()
    entry = f"| {date_value} | {role} | {severity} | {finding} | {resolution} |\n"
    path.write_text(text + entry, encoding="utf-8")


def append_team_minute(
    path: Path,
    kind: str,
    participants: str,
    summary: str,
    follow_up: str,
) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else "# Team Minutes\n\n## Interaction Log\n\n| Timestamp | Kind | Participants | Summary | Follow-up |\n| --- | --- | --- | --- | --- |\n"
    if text and not text.endswith("\n"):
        text += "\n"
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    row = f"| {timestamp} | {kind} | {participants} | {summary} | {follow_up} |\n"
    path.write_text(text + row, encoding="utf-8")


def debt_record_from_directives(
    directives: dict[str, str],
    workflow_slug: str,
    active_story: str,
    default_owner: str = "",
) -> dict[str, object]:
    directive_keys = set(directives)
    story = (
        directives.get("story")
        or directives.get("source story")
        or directives.get("source-story")
        or active_story
    )
    debt_type = directives.get("type") or directives.get("debt type") or directives.get("debt-type")
    applies_to = (
        directives.get("applies to")
        or directives.get("applies-to")
        or directives.get("targets")
        or directives.get("target stories")
        or directives.get("downstream")
        or ""
    )
    summary = directives.get("summary") or directives.get("note") or directives.get("debt") or ""
    explicit_fields: set[str] = set()
    if directive_keys & {"story", "source story", "source-story", "source"}:
        explicit_fields.update({"source_story", "source_story_label"})
    if directive_keys & {"type", "debt type", "debt-type"}:
        explicit_fields.add("debt_type")
    if directive_keys & {"severity", "risk"}:
        explicit_fields.add("severity")
    if "status" in directive_keys:
        explicit_fields.add("status")
    if directive_keys & {"summary", "note", "debt"}:
        explicit_fields.add("summary")
    if "impact" in directive_keys:
        explicit_fields.add("impact")
    if directive_keys & {"owner", "role"}:
        explicit_fields.add("owner")
    if "resolution" in directive_keys:
        explicit_fields.add("resolution")
    if directive_keys & {"propagation"}:
        explicit_fields.add("propagation")
    if directive_keys & {"applies to", "applies-to", "targets", "target stories", "downstream"}:
        explicit_fields.add("applies_to")
    return {
        "id": directives.get("id", "").strip(),
        "workflow_slug": workflow_slug,
        "source_story": normalize_story_id(story),
        "source_story_label": story.strip() if isinstance(story, str) and story.strip() else active_story,
        "debt_type": normalize_debt_type(debt_type),
        "severity": normalize_severity(directives.get("severity") or directives.get("risk") or "medium"),
        "status": normalize_status(directives.get("status") or "open"),
        "summary": summary.strip(),
        "impact": (directives.get("impact") or "").strip(),
        "owner": (directives.get("owner") or directives.get("role") or default_owner).strip(),
        "resolution": (directives.get("resolution") or "").strip(),
        "propagation": (directives.get("propagation") or "downstream").strip(),
        "applies_to": parse_story_id_list(applies_to),
        "_explicit_fields": sorted(explicit_fields),
    }


def record_debt_entries_from_report(
    root: Path,
    workflow_slug: str,
    active_story: str,
    role: str,
    entries: list[str],
) -> list[dict[str, object]]:
    recorded: list[dict[str, object]] = []
    for entry in entries:
        directives = parse_directives(entry)
        if not directives:
            directives = {"summary": entry}
        record = debt_record_from_directives(directives, workflow_slug, active_story, role)
        if not str(record.get("summary") or "").strip():
            continue
        recorded.append(append_or_update_debt_record(root, workflow_slug, record))
    return recorded


def memory_record_from_directives(
    directives: dict[str, str],
    workflow_slug: str,
    active_story: str,
    default_owner: str = "",
) -> dict[str, object]:
    directive_keys = set(directives)
    story = (
        directives.get("story")
        or directives.get("source story")
        or directives.get("source-story")
        or directives.get("source")
        or active_story
    )
    category = (
        directives.get("category")
        or directives.get("type")
        or directives.get("memory type")
        or ("validated-test-command" if directives.get("command") else "implementation-pattern")
    )
    summary = (
        directives.get("summary")
        or directives.get("note")
        or directives.get("memory")
        or directives.get("pattern")
        or directives.get("convention")
        or directives.get("command")
        or ""
    )
    applies_to = (
        directives.get("applies to")
        or directives.get("applies-to")
        or directives.get("targets")
        or directives.get("target stories")
        or ""
    )
    tags = directives.get("tags") or directives.get("tag") or ""
    explicit_fields: set[str] = set()
    if directive_keys & {"category", "type", "memory type"}:
        explicit_fields.add("category")
    if directive_keys & {"status"}:
        explicit_fields.add("status")
    if directive_keys & {"confidence"}:
        explicit_fields.add("confidence")
    if directive_keys & {"story", "source story", "source-story"}:
        explicit_fields.update({"story", "story_label"})
    if directive_keys & {"summary", "note", "memory", "pattern", "convention"}:
        explicit_fields.add("summary")
    if directive_keys & {"details", "detail"}:
        explicit_fields.add("details")
    if directive_keys & {"evidence"}:
        explicit_fields.add("evidence")
    if directive_keys & {"command"}:
        explicit_fields.add("command")
    if directive_keys & {"result", "outcome"}:
        explicit_fields.add("result")
    if directive_keys & {"owner", "role"}:
        explicit_fields.add("owner")
    if directive_keys & {"applies to", "applies-to", "targets", "target stories"}:
        explicit_fields.add("applies_to")
    if directive_keys & {"tags", "tag"}:
        explicit_fields.add("tags")
    return {
        "id": directives.get("id", "").strip(),
        "workflow_slug": workflow_slug,
        "category": normalize_memory_category(category),
        "status": normalize_memory_status(directives.get("status") or "active"),
        "confidence": normalize_memory_confidence(directives.get("confidence") or "medium"),
        "story": normalize_story_id(story),
        "story_label": story.strip() if isinstance(story, str) and story.strip() else active_story,
        "summary": summary.strip(),
        "details": (directives.get("details") or directives.get("detail") or "").strip(),
        "evidence": (directives.get("evidence") or "").strip(),
        "command": (directives.get("command") or "").strip(),
        "result": (directives.get("result") or directives.get("outcome") or "").strip(),
        "owner": (directives.get("owner") or directives.get("role") or default_owner).strip(),
        "source": (directives.get("source") or default_owner).strip(),
        "applies_to": parse_memory_story_id_list(applies_to),
        "tags": parse_memory_list(tags),
        "_explicit_fields": sorted(explicit_fields),
    }


def record_memory_entries_from_report(
    root: Path,
    workflow_slug: str,
    active_story: str,
    role: str,
    entries: list[str],
) -> list[dict[str, object]]:
    recorded: list[dict[str, object]] = []
    for entry in entries:
        directives = parse_directives(entry)
        if not directives:
            directives = {"summary": entry}
        record = memory_record_from_directives(directives, workflow_slug, active_story, role)
        if not str(record.get("summary") or record.get("command") or record.get("id") or "").strip():
            continue
        recorded.append(append_or_update_memory_record(root, workflow_slug, record))
    if recorded:
        render_memory_summary(root, workflow_slug)
    return recorded


def technical_debt_block(root: Path, workflow_slug: str) -> tuple[bool, str]:
    blocking = blocking_debt_records(load_debt_records(root, workflow_slug))
    if not blocking:
        return False, ""
    return (
        True,
        "Open high/critical technical debt blocks release planning: " + format_debt_summary(blocking, 3),
    )


def is_technical_debt_block(reason: str) -> bool:
    return reason.strip().startswith("Open high/critical technical debt blocks")


def update_execution_review_row(path: Path, reviewer: str, notes: str) -> None:
    if not path.exists():
        return
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line
        if line.startswith("| Review and challenge |"):
            parts = [part.strip() for part in line.strip().strip("|").split("|")]
            while len(parts) < 6:
                parts.append("")
            parts[4] = reviewer
            parts[5] = notes
            line = "| " + " | ".join(parts) + " |"
        lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


STATUS_RANK = {
    "optional": 0,
    "planned": 1,
    "in-progress": 2,
    "in-review": 3,
    "done": 4,
}


def stronger_status(baseline: str, existing: str) -> str:
    existing_clean = existing.strip().lower()
    baseline_clean = baseline.strip().lower()
    if existing_clean == "blocked":
        return "blocked"
    if baseline_clean == "blocked":
        return baseline_clean
    if STATUS_RANK.get(existing_clean, -1) >= STATUS_RANK.get(baseline_clean, -1):
        return existing_clean or baseline_clean
    return baseline_clean


def execution_board_rows(path: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    board = {"Workflow slug": "-", "Active story": "-", "Active owner": "-", "Current handoff": "-"}
    rows: dict[str, list[str]] = {}
    if not path.exists():
        return board, rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- ") and ":" in line:
            key, _, value = line[2:].partition(":")
            key = key.strip()
            if key in board:
                board[key] = value.strip()
    for parts in parse_markdown_table_rows(path):
        if len(parts) >= 6:
            rows[parts[0]] = parts[:6]
        elif len(parts) == 5:
            parts.insert(4, "Reviewer QA")
            rows[parts[0]] = parts[:6]
    return board, rows


def write_execution_board(
    path: Path,
    workflow_slug: str,
    active_story: str,
    active_owner: str,
    current_handoff: str,
    rows: list[list[str]],
) -> None:
    lines = [
        "# Execution Board",
        "",
        f"- Workflow slug: {workflow_slug}",
        f"- Active story: {active_story}",
        f"- Active owner: {active_owner}",
        f"- Current handoff: {current_handoff}",
        "",
        "| Work Item | Owner Role | Status | Blocked By | Reviewer | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    lines.extend(
        [
            "",
            "## Status Vocabulary",
            "",
            "- `planned`",
            "- `in-progress`",
            "- `blocked`",
            "- `in-review`",
            "- `done`",
            "- `optional`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def execution_row_name_for_role(role: str) -> str:
    return {
        "Product Owner": "Story scope and acceptance review",
        "Tech Lead": "Technical decomposition",
        "Implementer 1": "Implementation slice 1",
        "Implementer 2": "Implementation slice 2",
        "Reviewer QA": "Review and challenge",
    }.get(role, "")


def update_execution_row_for_role(
    path: Path,
    workflow_slug: str,
    role: str,
    status: str,
    note: str,
    blocked_by: str = "",
    reviewer: str | None = None,
) -> None:
    board, row_map = execution_board_rows(path)
    row_name = execution_row_name_for_role(role)
    if not row_name:
        return
    row = row_map.get(row_name, [row_name, role, "planned", "", reviewer or "", ""])
    while len(row) < 6:
        row.append("")
    row[1] = role
    row[2] = status
    row[3] = blocked_by
    if reviewer is not None:
        row[4] = reviewer
    elif not row[4]:
        row[4] = "Reviewer QA" if role != "Reviewer QA" else "Product Owner"
    if note:
        row[5] = note
    ordered_names = [
        "Story scope and acceptance review",
        "Technical decomposition",
        "Implementation slice 1",
        "Implementation slice 2",
        "Review and challenge",
    ]
    rows = []
    row_map[row_name] = row
    for name in ordered_names:
        existing = row_map.get(name)
        if existing:
            rows.append(existing)
    write_execution_board(
        path,
        workflow_slug,
        board.get("Active story", "-"),
        board.get("Active owner", "-"),
        board.get("Current handoff", "-"),
        rows,
    )


def role_status_from_board(path: Path, role: str) -> str:
    _, row_map = execution_board_rows(path)
    row_name = execution_row_name_for_role(role)
    row = row_map.get(row_name, [])
    return row[2].strip().lower() if len(row) >= 3 else ""


def infer_role_from_output(
    directive_text: str,
    rows: dict[str, dict[str, str]],
) -> str:
    lowered = directive_text.lower()
    directives = parse_directives(directive_text)
    report = parse_structured_agent_report(directive_text)
    explicit = canonical_role_name(
        directives.get("role", "")
        or directives.get("owner", "")
        or str(report.get("role", ""))
    )
    if explicit in rows or explicit in {"Product Owner", "Tech Lead", "Implementer 1", "Implementer 2", "Reviewer QA"}:
        return explicit
    changed_match = re.search(r"Changed\s+[`']?([^`'\n]+)[`']?", directive_text, flags=re.IGNORECASE)
    if changed_match:
        changed_path = changed_match.group(1).strip()
        for role, row in rows.items():
            for allowed in parse_allowed_paths(row.get("Allowed Write Paths", "")):
                if changed_path == allowed or changed_path.startswith(allowed.rstrip("/") + "/"):
                    return role
    if "no serious findings" in lowered or "reviewer qa" in lowered or "re-review" in lowered:
        return "Reviewer QA"
    if "scope is mostly clear" in lowered or "out of scope" in lowered:
        return "Product Owner"
    if "boundary check" in lowered or "coordination risk" in lowered:
        return "Tech Lead"
    return ""


def infer_status_from_output(directive_text: str) -> str:
    lowered = directive_text.lower()
    directives = parse_directives(directive_text)
    report = parse_structured_agent_report(directive_text)
    explicit = directives.get("status", "").strip().lower() or str(report.get("status", "")).strip().lower()
    if explicit:
        return explicit
    if "no serious findings" in lowered or "changed " in lowered or "fixes made" in lowered or "specific fixes" in lowered:
        return "done"
    if "blocked" in lowered or "cannot proceed" in lowered:
        return "blocked"
    if "finding" in lowered or "findings" in lowered or "review" in lowered:
        return "in-review"
    return "in-progress"


def sync_execution_board(root: Path, workflow_slug: str, state: dict[str, str]) -> None:
    board_path = root / ".workflow" / workflow_slug / "execution-board.md"
    if not board_path.exists():
        return
    stage = ensure_stage(state.get("Current stage") or "discuss")
    active_story = active_story_name(state) or "-"
    team = parse_team_settings(root, workflow_slug)
    try:
        parallel_slots = max(1, int(team.get("Parallel implementation slots", "1").strip()))
    except ValueError:
        parallel_slots = 1

    board, row_map = execution_board_rows(board_path)
    active_story_key = normalize_item_name(active_story)
    previous_active_story = normalize_item_name(board.get("Active story", ""))
    stale_note_story = ""
    for row in row_map.values():
        note = row[5] if len(row) > 5 else ""
        for match in re.findall(r"\bStory\s+\d+\b", note, flags=re.IGNORECASE):
            matched_story = normalize_item_name(match)
            if matched_story and matched_story != active_story_key:
                stale_note_story = matched_story
                break
        if stale_note_story:
            break
    if (
        previous_active_story
        and previous_active_story != "-"
        and previous_active_story != active_story_key
    ) or stale_note_story:
        row_map = {}

    def canonical_row(name: str, owner: str, reviewer: str, status: str) -> list[str]:
        row = row_map.get(name, [name, owner, status, "", reviewer, ""])
        while len(row) < 6:
            row.append("")
        row[0] = name
        row[1] = owner
        row[2] = stronger_status(status, row[2])
        if not row[4]:
            row[4] = reviewer
        return row

    active_owner = "Product Owner"
    current_handoff = "Product Owner -> Tech Lead"
    scope_status = "planned"
    decomp_status = "planned"
    impl1_status = "planned"
    impl2_status = "optional" if parallel_slots == 1 else "planned"
    review_status = "planned"

    if stage in {"story-slicing", "story-enrichment"}:
        scope_status = "in-progress"
    elif stage in {"spec-authoring", "implementation-planning"}:
        scope_status = "done"
        decomp_status = "in-progress"
        active_owner = "Tech Lead"
        current_handoff = "Tech Lead -> Implementer 1" if parallel_slots == 1 else "Tech Lead -> Implementer 1 + Implementer 2"
    elif stage == "implementation":
        scope_status = "done"
        decomp_status = "done"
        impl1_status = "in-progress"
        impl2_status = "in-progress" if parallel_slots > 1 else "optional"
        active_owner = "Implementer 1" if parallel_slots == 1 else "Implementer 1 + Implementer 2"
        current_handoff = "Implementer 1 -> Reviewer QA" if parallel_slots == 1 else "Implementer 1 + Implementer 2 -> Reviewer QA"
    elif stage in {"review", "release-planning"}:
        scope_status = "done"
        decomp_status = "done"
        impl1_status = "done"
        impl2_status = "done" if parallel_slots > 1 else "optional"
        review_status = "in-progress"
        active_owner = "Reviewer QA"
        current_handoff = "Reviewer QA -> Product Owner"
    elif stage == "done":
        scope_status = "done"
        decomp_status = "done"
        impl1_status = "done"
        impl2_status = "done" if parallel_slots > 1 else "optional"
        review_status = "done"
        active_owner = "Product Owner"
        current_handoff = "Complete"

    rows = [
        canonical_row("Story scope and acceptance review", "Product Owner", "Reviewer QA", scope_status),
        canonical_row("Technical decomposition", "Tech Lead", "Product Owner", decomp_status),
        canonical_row("Implementation slice 1", "Implementer 1", "Reviewer QA", impl1_status),
        canonical_row("Implementation slice 2", "Implementer 2", "Reviewer QA", impl2_status),
        canonical_row("Review and challenge", "Reviewer QA", "Product Owner", review_status),
    ]
    row_lookup = {row[0]: row for row in rows}
    impl1_live = row_lookup["Implementation slice 1"][2]
    impl2_live = row_lookup["Implementation slice 2"][2]
    review_live = row_lookup["Review and challenge"][2]
    active_impl_roles = []
    if impl1_live in {"in-progress", "in-review", "done"}:
        active_impl_roles.append("Implementer 1")
    if parallel_slots > 1 and impl2_live in {"in-progress", "in-review", "done"}:
        active_impl_roles.append("Implementer 2")
    all_impl_done = impl1_live == "done" and (parallel_slots == 1 or impl2_live == "done")
    if review_live in {"in-progress", "in-review"}:
        active_owner = "Reviewer QA"
        current_handoff = "Reviewer QA -> Product Owner"
    elif all_impl_done:
        active_owner = "Reviewer QA"
        current_handoff = "Reviewer QA -> Product Owner"
    elif active_impl_roles:
        active_owner = " + ".join(active_impl_roles)
        current_handoff = f"{active_owner} -> Reviewer QA"
    elif row_lookup["Technical decomposition"][2] in {"done", "in-progress"} and stage in {"implementation-planning", "implementation"}:
        active_owner = "Tech Lead"
        current_handoff = "Tech Lead -> Implementer 1" if parallel_slots == 1 else "Tech Lead -> Implementer 1 + Implementer 2"
    write_execution_board(board_path, workflow_slug, active_story, active_owner, current_handoff, rows)


def review_log_roles(path: Path) -> set[str]:
    roles: set[str] = set()
    for row in parse_markdown_table_rows(path):
        if len(row) >= 4 and row[1]:
            roles.add(row[1])
    return roles


def role_review_roles(path: Path) -> set[str]:
    roles: set[str] = set()
    for row in parse_markdown_table_rows(path):
        if len(row) >= 4 and row[2]:
            roles.add(row[2])
    return roles


def table_entry_count(path: Path) -> int:
    return len(parse_markdown_table_rows(path))


def sync_runtime_contract(root: Path, workflow_slug: str, state: dict[str, str]) -> None:
    runtime_path = root / ".workflow" / workflow_slug / "runtime-contract.md"
    if not runtime_path.exists():
        return
    board = parse_kv_list(root / ".workflow" / workflow_slug / "execution-board.md")
    roles = sorted(review_log_roles(root / ".workflow" / workflow_slug / "review-log.md"))
    role_review_role_names = sorted(role_review_roles(root / ".workflow" / workflow_slug / "role-reviews.md"))
    open_conflicts = unresolved_conflict_summary(root / ".workflow" / workflow_slug / "conflicts.md")
    open_debt = blocking_debt_records(load_debt_records(root, workflow_slug))
    memory_records = load_memory_records(root, workflow_slug)
    runtime_values = parse_kv_list(runtime_path)
    runtime_mode = runtime_values.get("Runtime mode", "file-driven").strip() or "file-driven"
    replace_or_append_bullet(runtime_path, "Active story", active_story_name(state) or "-")
    replace_or_append_bullet(runtime_path, "Active owner", board.get("Active owner", "-") or "-")
    replace_or_append_bullet(runtime_path, "Current handoff", board.get("Current handoff", "-") or "-")
    replace_or_append_bullet(
        runtime_path,
        "Delegated execution ready",
        "true" if runtime_mode == "delegated-agent-team" and (root / ".workflow" / workflow_slug / "team-dispatch.md").exists() else "false",
    )
    replace_or_append_bullet(
        runtime_path,
        "Recorded review roles",
        ", ".join(roles) if roles else "-",
    )
    replace_or_append_bullet(
        runtime_path,
        "Recorded role review roles",
        ", ".join(role_review_role_names) if role_review_role_names else "-",
    )
    replace_or_append_bullet(
        runtime_path,
        "Open blocking conflicts",
        open_conflicts or "-",
    )
    replace_or_append_bullet(
        runtime_path,
        "Assumption entries",
        str(table_entry_count(root / ".workflow" / workflow_slug / "assumptions.md")),
    )
    replace_or_append_bullet(
        runtime_path,
        "Blocking technical debt",
        format_debt_summary(open_debt) if open_debt else "-",
    )
    replace_or_append_bullet(
        runtime_path,
        "Shared learning memory",
        format_memory_summary(memory_records),
    )
    invocation_records = load_invocation_records(root, workflow_slug)
    replace_or_append_bullet(
        runtime_path,
        "Invocation accounting",
        format_accounting_summary(invocation_records),
    )
    replace_or_append_bullet(
        runtime_path,
        "Required shared inputs",
        format_shared_items(REQUIRED_SHARED_INPUTS),
    )
    replace_or_append_bullet(
        runtime_path,
        "Generated shared artifacts",
        format_shared_items(GENERATED_SHARED_ARTIFACTS),
    )
    replace_or_append_bullet(
        runtime_path,
        "Required shared outputs",
        format_shared_items(REQUIRED_SHARED_OUTPUTS),
    )
    replace_or_append_bullet(
        runtime_path,
        "Agent results directory",
        f".workflow/{workflow_slug}/agent-results",
    )
    replace_or_append_bullet(
        runtime_path,
        "Agent sync ledger",
        f".workflow/{workflow_slug}/agent-sync-ledger.md",
    )


def set_runtime_mode(root: Path, workflow_slug: str, mode: str, spawn_policy: str) -> None:
    runtime_path = root / ".workflow" / workflow_slug / "runtime-contract.md"
    if not runtime_path.exists():
        return
    replace_or_append_bullet(runtime_path, "Runtime mode", mode)
    replace_or_append_bullet(runtime_path, "Spawn policy", spawn_policy)


def team_minutes_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "team-minutes.md"


def sync_team_story_headers(root: Path, workflow_slug: str, story: str) -> None:
    if not story or story == "-":
        return
    replace_or_append_bullet(root / ".workflow" / workflow_slug / "review-log.md", "Current story", story)
    replace_or_append_bullet(root / ".workflow" / workflow_slug / "role-reviews.md", "Current story", story)
    replace_or_append_bullet(root / ".workflow" / workflow_slug / "conflicts.md", "Current story", story)
    replace_or_append_bullet(root / ".workflow" / workflow_slug / "assumptions.md", "Current story", story)
    replace_or_append_bullet(team_minutes_path(root, workflow_slug), "Current story", story)


def maybe_stage_for_team_status(state: dict[str, str], role: str, status: str, root: Path, workflow_slug: str) -> None:
    current = ensure_stage(state.get("Current stage") or "discuss")
    board_path = root / ".workflow" / workflow_slug / "execution-board.md"
    if role in {"Implementer 1", "Implementer 2"} and status in {"in-progress", "in-review", "done"}:
        if current == "implementation-planning":
            state["Current stage"] = "implementation"
            state["Human gate status"] = "approved"
        if current in {"implementation-planning", "implementation"}:
            impl1_status = role_status_from_board(board_path, "Implementer 1")
            impl2_status = role_status_from_board(board_path, "Implementer 2")
            team = parse_team_settings(root, workflow_slug)
            try:
                parallel_slots = max(1, int(team.get("Parallel implementation slots", "1").strip()))
            except ValueError:
                parallel_slots = 1
            all_done = impl1_status == "done" and (parallel_slots == 1 or impl2_status == "done")
            if all_done:
                state["Next action"] = "run Reviewer QA review and synchronize findings for the active story"
            else:
                state["Next action"] = "continue delegated implementation and keep handoffs synchronized"
        state["Item note"] = f"{role} marked {status}"
    elif role == "Reviewer QA" and status in {"in-progress", "in-review", "done"}:
        if current in {"implementation-planning", "implementation"}:
            state["Current stage"] = "review"
            state["Human gate status"] = "pending"
        state["Next action"] = (
            "review evidence is ready; approve when the current gate is satisfied"
            if status == "done"
            else "continue review and record findings in review-log.md"
        )
        state["Item note"] = f"Reviewer QA marked {status}"
    elif role == "Tech Lead" and status == "done":
        state["Next action"] = "start delegated implementation and keep implementer handoffs explicit"
        state["Item note"] = "technical decomposition completed"
    elif role == "Product Owner" and status == "done":
        state["Item note"] = "product-owner scope review completed"


def handle_team_sync(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    directive_text: str,
) -> dict[str, str]:
    payload, sync_source, sync_digest = load_team_sync_payload(root, workflow_slug, directive_text)
    directives = parse_directives(payload)
    report = parse_structured_agent_report(payload)
    schema_required = strict_schema_required(report, sync_source, payload)
    ensure_agent_result_schema_artifacts(root, workflow_slug)
    schema_errors, schema_warnings = validate_agent_result_report(report, schema_required)
    if schema_required:
        append_agent_result_validation_record(
            root,
            workflow_slug,
            sync_source or "direct-team-sync",
            "invalid" if schema_errors else "valid",
            schema_errors,
            schema_warnings,
        )
    if schema_errors:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Agent result schema validation failed: " + "; ".join(schema_errors[:3])
        state["Item note"] = "agent result rejected before ingest"
        state["Challenge note"] = "; ".join(schema_warnings[:3])
        state["Next action"] = "fix the agent result envelope to match agent-result.schema.json, then rerun team-sync"
        return state
    assignments_path = root / ".workflow" / workflow_slug / "agent-assignments.md"
    rows = parse_assignment_rows(assignments_path)
    role = canonical_role_name(
        directives.get("role", "")
        or directives.get("owner", "")
        or str(report.get("role", ""))
        or ""
    )
    if role not in {"Product Owner", "Tech Lead", "Implementer 1", "Implementer 2", "Reviewer QA"}:
        role = infer_role_from_output(payload, rows)
    if role not in {"Product Owner", "Tech Lead", "Implementer 1", "Implementer 2", "Reviewer QA"}:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "team-sync requires a recognized role."
        state["Next action"] = "provide role, status, and note for the team member being synchronized"
        return state
    explicit_status = directives.get("status", "").strip().lower() or str(report.get("status", "")).strip().lower()
    status = explicit_status or infer_status_from_output(payload)
    if status not in {"planned", "in-progress", "in-review", "done", "blocked", "optional"}:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = f"team-sync received unsupported status: {status}"
        state["Next action"] = "use one of planned, in-progress, in-review, done, blocked, or optional"
        return state
    note = (
        directives.get("note", "").strip()
        or directives.get("summary", "").strip()
        or str(report.get("summary", "")).strip()
    )
    if not note:
        stripped = payload.strip()
        if stripped:
            note = stripped.replace("\n", " ").strip()
    follow_up = (
        directives.get("follow-up", "").strip()
        or directives.get("follow up", "").strip()
        or str(report.get("follow-up", "")).strip()
    )
    blocked_by = directives.get("blocked by", "").strip() or str(report.get("blocked-by", "")).strip()
    reviewer = directives.get("reviewer", "").strip() or str(report.get("reviewer", "")).strip() or None
    changed_paths = report_list(report, "files-changed")
    validation_runs = report_list(report, "validation-run")
    verdict = str(report.get("verdict", "")).strip()
    missing_requirements = report_list(report, "missing-requirements")
    incorrect_assumptions = report_list(report, "incorrect-assumptions")
    risks = report_list(report, "risks")
    questions = report_list(report, "questions")
    suggested_changes = report_list(report, "suggested-changes")
    evidence = report_list(report, "evidence")
    conflict_entries = report_list(report, "conflict-entries")
    assumption_updates = report_list(report, "assumption-updates")
    red_team_notes = report_list(report, "red-team-notes")
    findings = report_list(report, "findings")
    debt_entries = report_list(report, "debt-entries")
    memory_entries = report_list(report, "memory-entries")
    active_story = active_story_name(state) or "-"
    sync_team_story_headers(root, workflow_slug, active_story)

    fallback_allowed_paths = story_allowed_write_paths(root, workflow_slug, active_story)
    allowed, scope_reason = validate_changed_paths(role, rows, changed_paths, fallback_allowed_paths)
    if not allowed:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = scope_reason
        state["Item note"] = f"{role} reported out-of-scope file changes"
        state["Next action"] = "correct the assignment or keep changes inside the declared write scope before continuing"
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "team-sync-blocked",
            f"{role}, Workflow Orchestrator",
            f"{active_story}: {scope_reason}",
            "Reconcile the reported file changes with the declared write scope",
        )
        return state

    clear_resolved_team_sync_block(state)

    details: list[str] = []
    if sync_source:
        details.append(f"source: {sync_source}")
    if verdict:
        details.append(f"verdict: {verdict}")
    if changed_paths:
        details.append("files: " + ", ".join(changed_paths[:4]))
    if validation_runs:
        details.append("validation: " + "; ".join(validation_runs[:2]))
    if note and details:
        note = f"{note} ({'; '.join(details)})"
    elif details:
        note = "; ".join(details)

    board_path = root / ".workflow" / workflow_slug / "execution-board.md"
    update_execution_row_for_role(board_path, workflow_slug, role, status, note, blocked_by, reviewer)

    if role in rows:
        rows[role]["Status"] = status
        write_assignment_rows(assignments_path, workflow_slug, rows)

    review_content_present = bool(
        verdict
        or missing_requirements
        or incorrect_assumptions
        or risks
        or questions
        or suggested_changes
        or evidence
        or red_team_notes
    )
    if review_content_present:
        append_role_review_entry(
            root / ".workflow" / workflow_slug / "role-reviews.md",
            active_story,
            role,
            verdict,
            missing_requirements,
            incorrect_assumptions,
            risks,
            questions,
            suggested_changes,
            evidence,
            red_team_notes,
        )

    blocking_conflicts: list[str] = []
    if conflict_entries:
        for raw_conflict in conflict_entries:
            conflict_severity, conflict_text = conflict_severity_and_text(raw_conflict)
            if not conflict_text:
                continue
            append_conflict_entry(
                root / ".workflow" / workflow_slug / "conflicts.md",
                active_story,
                role,
                conflict_severity,
                conflict_text,
                suggested_changes[0] if suggested_changes else follow_up,
                "open",
            )
            if conflict_severity == "blocking":
                blocking_conflicts.append(conflict_text)

    verdict_clean = verdict.strip().lower()
    if verdict_clean in {"block", "blocked"} and not conflict_entries:
        conflict_text = note or "review verdict requires changes before the gate can advance"
        append_conflict_entry(
            root / ".workflow" / workflow_slug / "conflicts.md",
            active_story,
            role,
            "blocking",
            conflict_text,
            suggested_changes[0] if suggested_changes else follow_up,
            "open",
        )
        blocking_conflicts.append(conflict_text)

    for raw_assumption in assumption_updates:
        if not raw_assumption.strip():
            continue
        append_assumption_entry(
            root / ".workflow" / workflow_slug / "assumptions.md",
            active_story,
            role,
            "unknown",
            raw_assumption,
            "not recorded",
            follow_up or "validate before approving if material",
        )
    for raw_assumption in incorrect_assumptions:
        if not raw_assumption.strip():
            continue
        append_assumption_entry(
            root / ".workflow" / workflow_slug / "assumptions.md",
            active_story,
            role,
            "contested",
            raw_assumption,
            "artifact may be wrong if this assumption remains unresolved",
            follow_up or "resolve during reconciliation",
        )

    recorded_debt = record_debt_entries_from_report(root, workflow_slug, active_story, role, debt_entries)
    if recorded_debt:
        debt_ids = ", ".join(str(item.get("id")) for item in recorded_debt[:3])
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "debt-record",
            f"{role}, Workflow Orchestrator",
            f"{active_story}: recorded technical debt {debt_ids}",
            "Debt will propagate through DAG, planning, and dispatch artifacts",
        )
    recorded_memory = record_memory_entries_from_report(root, workflow_slug, active_story, role, memory_entries)
    if recorded_memory:
        memory_ids = ", ".join(str(item.get("id")) for item in recorded_memory[:3])
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "memory-record",
            f"{role}, Workflow Orchestrator",
            f"{active_story}: recorded shared memory {memory_ids}",
            "Memory will be available to story enrichment, implementation planning, and dispatch packets",
        )
    recorded_usage = record_agent_result_invocation(
        root,
        workflow_slug,
        report,
        sync_source or "direct-team-sync",
        role,
        active_story,
        status,
    )
    if recorded_usage:
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "accounting-record",
            f"{role}, Workflow Orchestrator",
            f"{active_story}: recorded delegated invocation {recorded_usage.get('id')}",
            "Usage will be summarized in accounting.md and implementation planning context",
        )

    if role in {"Reviewer QA", "Product Owner"}:
        if findings:
            for raw_finding in findings:
                severity, finding_text = finding_severity_and_text(raw_finding)
                if not finding_text:
                    continue
                append_review_log_entry(
                    root / ".workflow" / workflow_slug / "review-log.md",
                    role,
                    severity,
                    f"{active_story}: {finding_text}",
                    follow_up or "open",
                )
        elif status == "done":
            append_review_log_entry(
                root / ".workflow" / workflow_slug / "review-log.md",
                role,
                "info",
                f"{active_story}: no serious findings remain",
                follow_up or "approved for current gate",
            )

    if sync_source and sync_digest:
        append_sync_ledger_entry(agent_sync_ledger_path(root, workflow_slug), sync_source, sync_digest, role, status)

    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "handoff" if status == "done" else "team-sync",
        f"{role}, Workflow Orchestrator",
        f"{active_story}: {note or f'{role} marked {status}'}",
        follow_up or "Refresh workflow visibility and continue the active handoff",
    )
    if status == "blocked":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = note or f"{role} is blocked"
        state["Item note"] = f"{role} marked blocked"
        state["Next action"] = follow_up or f"resolve the {role} block before continuing"
    else:
        if note == state.get("Blocked reason", "").strip():
            state["Blocked reason"] = ""
        maybe_stage_for_team_status(state, role, status, root, workflow_slug)
        if role in {"Reviewer QA", "Product Owner"} and findings:
            high_findings = []
            normal_findings = []
            for raw_finding in findings:
                severity, finding_text = finding_severity_and_text(raw_finding)
                if severity in {"critical", "high"}:
                    high_findings.append(finding_text)
                else:
                    normal_findings.append(finding_text)
            if high_findings:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = f"{role} reported blocking findings for {active_story}: {'; '.join(high_findings[:2])}"
                state["Challenge note"] = "; ".join(f"{role} ({finding_severity_and_text(item)[0]}): {finding_severity_and_text(item)[1]}" for item in findings[:3])
                state["Next action"] = follow_up or f"address the {role} findings before continuing"
            elif normal_findings:
                state["Challenge note"] = "; ".join(
                    f"{role} ({finding_severity_and_text(item)[0]}): {finding_severity_and_text(item)[1]}"
                    for item in findings[:3]
                )
                state["Next action"] = follow_up or f"review and respond to the {role} findings for {active_story}"
        if verdict_clean in {"block", "blocked"}:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = f"{role} blocked {active_story}: {note or 'review verdict requires changes'}"
            state["Challenge note"] = f"{role} verdict: {verdict_clean}"
            state["Next action"] = follow_up or f"resolve the {role} review block before continuing"
        elif blocking_conflicts:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = f"{role} reported blocking conflict for {active_story}: {'; '.join(blocking_conflicts[:2])}"
            state["Challenge note"] = "; ".join(f"{role} conflict: {item}" for item in blocking_conflicts[:3])
            state["Next action"] = follow_up or f"resolve blocking conflicts before continuing"
    return state


def handle_team_sync_all(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    note: str | None,
    tx_path: Path | None = None,
    checkpoint_before_state: dict[str, str] | None = None,
) -> dict[str, str]:
    ledger = parse_sync_ledger(agent_sync_ledger_path(root, workflow_slug))
    pending: list[Path] = []
    already_synced_sources: list[str] = []
    for result_path in agent_result_candidate_paths(root, workflow_slug):
        digest = file_hash(result_path)
        source = path_source(root, result_path)
        if ledger.get(source) == digest:
            already_synced_sources.append(source)
            continue
        pending.append(result_path)

    if not pending:
        state["Item note"] = "no pending agent result envelopes to synchronize"
        if note and note.strip():
            state["Next action"] = note.strip()
        return state

    preflight_errors: list[str] = []
    ensure_agent_result_schema_artifacts(root, workflow_slug)
    for result_path in pending:
        payload = result_path.read_text(encoding="utf-8")
        report = parse_structured_agent_report(payload)
        source = path_source(root, result_path)
        schema_required = strict_schema_required(report, source, payload)
        schema_errors, schema_warnings = validate_agent_result_report(report, schema_required)
        if schema_errors:
            append_agent_result_validation_record(
                root,
                workflow_slug,
                source,
                "invalid",
                schema_errors,
                schema_warnings,
            )
            preflight_errors.append(f"{source}: {'; '.join(schema_errors[:2])}")
    if preflight_errors:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Agent result schema validation failed before batch ingest: " + " | ".join(preflight_errors[:3])
        state["Item note"] = "team-sync-all rejected invalid result envelope before ingest"
        state["Next action"] = "fix invalid agent result envelopes, then rerun team-sync-all"
        return state

    synced_sources: list[str] = []
    for result_path in pending:
        state = handle_team_sync(state, root, workflow_slug, str(result_path))
        synced_sources.append(path_source(root, result_path))
        if tx_path is not None:
            write_command_progress_checkpoint(
                root,
                tx_path,
                f"team-sync-all-{len(already_synced_sources) + len(synced_sources)}",
                {
                    "command": "team-sync-all",
                    "completed_sources": already_synced_sources + synced_sources,
                    "completed_count": len(already_synced_sources) + len(synced_sources),
                    "pending_sources": [path_source(root, path) for path in pending[len(synced_sources) :]],
                    "state": state,
                    "before_state": checkpoint_before_state or {},
                    "note": note or "",
                },
            )
    state["Item note"] = "agent result envelopes synchronized: " + ", ".join(already_synced_sources + synced_sources)
    if note and note.strip():
        state["Next action"] = note.strip()
    return state


def team_review_block(root: Path, workflow_slug: str, stage: str) -> tuple[bool, str]:
    settings = parse_team_settings(root, workflow_slug)
    blocked, conflict_reason = collaboration_block(root, workflow_slug)
    if blocked:
        return True, conflict_reason
    review_roles = review_log_roles(root / ".workflow" / workflow_slug / "review-log.md")
    reviewer_required = settings.get("Reviewer required", "false").strip().lower() in {"true", "1", "yes", "on"}
    po_required = settings.get("Product owner required", "false").strip().lower() in {"true", "1", "yes", "on"}
    if stage == "release-planning" and reviewer_required and "Reviewer QA" not in review_roles:
        return True, "Reviewer QA signoff is missing in review-log.md for this story."
    if stage == "done" and po_required and "Product Owner" not in review_roles:
        return True, "Product Owner signoff is missing in review-log.md for this story."
    return False, ""


def handle_staff(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    directive_text: str,
    scope: str | None,
) -> dict[str, str]:
    directives = parse_directives(directive_text)
    override_path = root / ".workflow" / workflow_slug / "team-overrides.md"
    config_path = root / ".workflow" / "team-config.md"
    applied: list[str] = []

    team_size = directives.get("team size") or directives.get("team size override")
    parallel = (
        directives.get("parallel implementation slots")
        or directives.get("parallel implementation slots override")
        or directives.get("parallel slots")
    )
    notes = directives.get("notes") or directives.get("note")
    role_updates = team_role_directives(directives)

    if scope and scope.strip().lower() == "initiative":
        if team_size:
            replace_or_append_bullet(config_path, "Team size", team_size)
            applied.append(f"initiative team size={team_size}")
        if parallel:
            replace_or_append_bullet(config_path, "Parallel implementation slots", parallel)
            applied.append(f"initiative parallel slots={parallel}")
    else:
        if team_size:
            replace_or_append_bullet(override_path, "Team size override", team_size)
            applied.append(f"team size override={team_size}")
        if parallel:
            replace_or_append_bullet(override_path, "Parallel implementation slots override", parallel)
            applied.append(f"parallel slots override={parallel}")
        if notes:
            replace_or_append_bullet(override_path, "Notes", notes)
            applied.append("team notes updated")

    for role, value in role_updates.items():
        replace_or_append_role_line(override_path, role, value)
        applied.append(f"{role} override updated")

    if not applied and directive_text.strip():
        replace_or_append_bullet(override_path, "Notes", directive_text.strip())
        applied.append("team notes updated")

    state["Item note"] = "staffing updated: " + ", ".join(applied) if applied else "staffing reviewed with no changes"
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "staffing",
        "Workflow Orchestrator, Product Owner, Tech Lead",
        "; ".join(applied) if applied else "Reviewed staffing with no changes",
        "Review the updated team configuration before continuing",
    )
    if state.get("Human gate status") == "blocked":
        blocked_reason = state.get("Blocked reason", "").strip() or "active workflow block"
        state["Next action"] = f"resolve the current workflow block before continuing: {blocked_reason}"
    else:
        state["Challenge note"] = ""
        state["Next action"] = "review the updated team configuration and continue with the current workflow lane"
    if ensure_stage(state.get("Current stage") or "discuss") == "implementation-planning":
        maybe_generate_implementation_plan(root, workflow_slug)
    return state


def handle_assign(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    directive_text: str,
) -> dict[str, str]:
    directives = parse_directives(directive_text)
    assignments_path = root / ".workflow" / workflow_slug / "agent-assignments.md"
    rows = parse_assignment_rows(assignments_path)
    applied: list[str] = []
    ownership_updates = team_role_ownership_directives(directives)

    for role, value in team_role_directives(directives).items():
        row = rows.get(role, {
            "Role": role,
            "Slot": role_slot(role),
            "Responsibility Focus": value,
            "Default Ownership": "assigned scope only",
            "Allowed Write Paths": "",
            "Status": "assigned",
        })
        row["Responsibility Focus"] = value
        row["Status"] = "assigned"
        rows[role] = row
        applied.append(f"{role} assigned")

    for role, value in ownership_updates.items():
        row = rows.get(role, {
            "Role": role,
            "Slot": role_slot(role),
            "Responsibility Focus": "",
            "Default Ownership": "assigned scope only",
            "Allowed Write Paths": "",
            "Status": "assigned",
        })
        row["Allowed Write Paths"] = value
        row["Status"] = "assigned"
        rows[role] = row
        applied.append(f"{role} write scope updated")

    if directives.get("default ownership"):
        for role in ["Implementer 1", "Implementer 2"]:
            if role in rows:
                rows[role]["Default Ownership"] = directives["default ownership"]
        applied.append("implementer ownership updated")

    write_assignment_rows(assignments_path, workflow_slug, rows)
    state["Item note"] = "assignments updated: " + ", ".join(applied) if applied else "assignments reviewed with no changes"
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "assignment",
        ", ".join(sorted(rows.keys())) if rows else "Workflow Orchestrator",
        "; ".join(applied) if applied else "Reviewed assignments with no changes",
        "Keep ownership boundaries explicit during execution",
    )
    if state.get("Human gate status") == "blocked":
        blocked_reason = state.get("Blocked reason", "").strip() or "active workflow block"
        state["Next action"] = f"resolve the current workflow block before continuing: {blocked_reason}"
    else:
        state["Challenge note"] = ""
        state["Next action"] = "execute or review the assigned ownership boundaries and keep handoffs explicit"
    if ensure_stage(state.get("Current stage") or "discuss") == "implementation-planning":
        maybe_generate_implementation_plan(root, workflow_slug)
    return state


def handle_challenge(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    directive_text: str,
    role_hint: str | None,
) -> dict[str, str]:
    directives = parse_directives(directive_text)
    role = canonical_role_name(directives.get("role", "") or (role_hint or "") or "Reviewer QA")
    severity = directives.get("severity", "medium").strip() or "medium"
    finding = directives.get("finding") or directives.get("note") or directive_text.strip() or "challenge raised"
    resolution = directives.get("resolution", "").strip()
    review_path = root / ".workflow" / workflow_slug / "review-log.md"
    sync_team_story_headers(root, workflow_slug, active_story_name(state) or "-")
    append_review_log_entry(review_path, role, severity, finding, resolution)
    update_execution_review_row(root / ".workflow" / workflow_slug / "execution-board.md", role, finding)
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "challenge",
        f"{role}, Workflow Orchestrator",
        finding,
        resolution or "Address the challenge before continuing",
    )

    state["Challenge note"] = f"{role} challenge ({severity}): {finding}"
    state["Item note"] = f"challenge recorded by {role}"
    if severity.lower() in {"high", "critical", "blocker"}:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = f"{role} raised a {severity} challenge: {finding}"
        state["Next action"] = f"address the {role} challenge before continuing: {finding}"
    else:
        current = ensure_stage(state.get("Current stage") or "discuss")
        if current in GATED_STAGES and state.get("Human gate status") != "blocked":
            state["Human gate status"] = "pending"
        state["Blocked reason"] = ""
        state["Next action"] = f"review and respond to the {role} challenge: {finding}"
    return state


def handle_review_sync(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    note: str | None,
) -> dict[str, str]:
    review_path = root / ".workflow" / workflow_slug / "review-log.md"
    sync_team_story_headers(root, workflow_slug, active_story_name(state) or "-")
    roles = sorted(review_log_roles(review_path))
    summary = ", ".join(roles) if roles else "none"
    update_execution_review_row(
        root / ".workflow" / workflow_slug / "execution-board.md",
        summary,
        note.strip() if note and note.strip() else f"review evidence recorded from: {summary}",
    )
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "review-sync",
        summary,
        note.strip() if note and note.strip() else f"Review evidence synchronized from: {summary}",
        "Approve when the current gate is satisfied",
    )
    current = ensure_stage(state.get("Current stage") or "discuss")
    unresolved = unresolved_review_summary(review_path)
    unresolved_conflicts = unresolved_conflict_summary(root / ".workflow" / workflow_slug / "conflicts.md")
    blocked, block_reason = team_review_block(root, workflow_slug, current)
    merge_blocked, merge_reason = merge_gate_block(root, workflow_slug, current)
    apply_blocked, apply_reason = merge_apply_block(root, workflow_slug, current) if not merge_blocked else (False, "")
    integration_blocked, integration_reason = integration_gate_block(root, workflow_slug, current) if not merge_blocked and not apply_blocked else (False, "")
    ci_blocked, ci_reason = ci_feedback_block(root, workflow_slug, current) if not merge_blocked and not apply_blocked and not integration_blocked else (False, "")
    synthesis_blocked, synthesis_reason = feedback_synthesis_block(root, workflow_slug, current) if not merge_blocked and not apply_blocked and not integration_blocked and not ci_blocked else (False, "")
    verify_blocked, verify_reason = verify_fix_block(root, workflow_slug, current) if not merge_blocked and not apply_blocked and not integration_blocked and not ci_blocked and not synthesis_blocked else (False, "")
    if not blocked and state.get("Human gate status") == "blocked":
        blocked_reason = state.get("Blocked reason", "")
        if (
            not merge_blocked
            and not apply_blocked
            and not integration_blocked
            and not ci_blocked
            and not synthesis_blocked
            and not verify_blocked
            and ("signoff is missing in review-log.md" in blocked_reason or (not unresolved and not unresolved_conflicts))
        ):
            state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
            state["Blocked reason"] = ""
    state["Item note"] = f"review evidence synchronized: {summary}"
    state["Challenge note"] = "; ".join(item for item in [unresolved, unresolved_conflicts] if item)
    if blocked:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = block_reason
        state["Next action"] = "resolve blocking review findings or record a concrete conflict resolution before approval"
    elif merge_blocked:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = merge_reason
        state["Next action"] = "run or repair merge-gate before review approval"
    elif apply_blocked:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = apply_reason
        state["Next action"] = "run or repair merge-apply before integration-gate and review approval"
    elif integration_blocked:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = integration_reason
        state["Next action"] = "run or repair integration-gate before review approval"
    elif ci_blocked:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = ci_reason
        state["Next action"] = "run or repair ci-feedback before review approval"
    elif synthesis_blocked:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = synthesis_reason
        state["Next action"] = "run or repair feedback-synth before review approval"
    elif verify_blocked:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = verify_reason
        state["Next action"] = "run or repair verify-fix before review approval"
    else:
        state["Next action"] = "review evidence is synchronized; approve when the current gate is satisfied"
    return state


def handle_feedback_synth(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    note: str | None,
) -> dict[str, str]:
    payload = run_feedback_synthesis(root, workflow_slug, note)
    recommendation = str(payload.get("recommendation") or "").strip().lower()
    summary = str(payload.get("summary") or "").strip()
    blockers = list_payload_value(payload.get("blockers"))
    warnings = list_payload_value(payload.get("warnings"))
    active_story = str(payload.get("active_story") or active_story_name(state) or "-")
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "feedback-synth",
        "Workflow Orchestrator, Tech Lead, Reviewer QA",
        f"{active_story}: synthesis recommends {recommendation or '-'}",
        summary or "Review feedback-synthesis.md before the next gate decision",
    )
    state["Item note"] = f"feedback synthesis recommends {recommendation or '-'}"
    state["Challenge note"] = "; ".join((blockers + warnings)[:3])
    current = ensure_stage(state.get("Current stage") or "discuss")
    if recommendation == "approve":
        if state.get("Human gate status") == "blocked" and state.get("Blocked reason", "").startswith("Feedback synthesis"):
            state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
            state["Blocked reason"] = ""
        state["Next action"] = "review feedback-synthesis.md, then run review-sync or approve when the current gate is satisfied"
    else:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = f"Feedback synthesis recommends `{recommendation}`: {summary or 'review feedback-synthesis.md'}"
        if recommendation == "fix":
            state["Next action"] = "address synthesized review feedback, sync the role results, then rerun feedback-synth"
        elif recommendation == "split":
            state["Next action"] = "split the active story or rework story slicing before retrying implementation"
        elif recommendation == "defer":
            state["Next action"] = "defer the disputed scope or move it to a later slice before approval"
        elif recommendation == "replan":
            state["Next action"] = "run replanning work before another implementation retry"
        else:
            state["Next action"] = "resolve the synthesis blockers before approval"
    return state


def handle_issue_advisor(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    note: str | None,
) -> dict[str, str]:
    payload = run_issue_advisor(root, workflow_slug, note)
    action = str(payload.get("action") or "").strip().lower()
    summary = str(payload.get("summary") or payload.get("failure_diagnosis") or "").strip()
    evidence = list_payload_value(payload.get("evidence"))
    active_story = str(payload.get("active_story") or active_story_name(state) or "-")
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "issue-advisor",
        "Workflow Orchestrator, Tech Lead, Reviewer QA",
        f"{active_story}: advisor recommends {action or '-'}",
        summary or "Review issue-advisor.md before retrying implementation",
    )
    state["Item note"] = f"issue advisor recommends {action or '-'}"
    state["Challenge note"] = "; ".join(evidence[:3])
    current = ensure_stage(state.get("Current stage") or "discuss")
    if current in GATED_STAGES:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = f"Issue advisor recommends `{action or 'review'}`: {summary or 'review issue-advisor.md'}"
    if action == "retry_approach":
        state["Next action"] = "retry implementation using issue-advisor.md guidance, then rerun merge/apply/integration gates and feedback-synth"
    elif action == "retry_modified":
        state["Next action"] = "review proposed acceptance changes in issue-advisor.md; explicitly refine story scope and record dropped criteria as debt before retrying"
    elif action == "accept_with_debt":
        state["Next action"] = "record or accept the suggested debt with debt-record, then rerun dag-sync and feedback-synth"
    elif action == "split":
        state["Next action"] = "split the active story, rerun dag-sync and execution-path, then retry the first ready sub-story"
    elif action == "escalate_to_replan":
        state["Next action"] = "rework story slicing or DAG dependencies before another implementation retry"
    else:
        state["Next action"] = "review issue-advisor.md and choose an explicit recovery path"
    return state


def handle_replan(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    directive_text: str,
) -> dict[str, str]:
    directives = parse_directives(directive_text)
    confirm = directives.get("confirm", "").strip().lower()
    apply_value = directives.get("apply", "").strip().lower()
    apply_changes = confirm == "replan" or apply_value in {"true", "yes", "replan"}
    payload = run_replanner(root, workflow_slug, directive_text, apply_changes)
    status = str(payload.get("status") or "").strip().lower()
    plan_type = str(payload.get("plan_type") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    active_story = str(payload.get("active_story") or active_story_name(state) or "-")
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "replan",
        "Workflow Orchestrator, Product Owner, Tech Lead",
        f"{active_story}: replan {status or '-'} ({plan_type or '-'})",
        summary or "Review replan.md before continuing",
    )
    state["Item note"] = f"replan {status or '-'}: {plan_type or '-'}"
    blockers = list_payload_value(payload.get("blockers"))
    warnings = list_payload_value(payload.get("warnings"))
    state["Challenge note"] = "; ".join((blockers + warnings)[:3])
    if status == "applied":
        updates = payload.get("state_updates", {})
        updates = updates if isinstance(updates, dict) else {}
        if str(updates.get("active_items") or "").strip():
            state["Active items"] = str(updates.get("active_items") or "").strip()
        if str(updates.get("deferred_items") or "").strip():
            existing_deferred = [item.strip() for item in parse_items(state.get("Deferred items", "")) if item.strip()]
            for item in parse_items(str(updates.get("deferred_items") or "")):
                if item and item not in existing_deferred:
                    existing_deferred.append(item)
            state["Deferred items"] = ", ".join(existing_deferred)
        next_stage = str(updates.get("stage") or ("story-slicing" if plan_type == "split_story" else "story-enrichment")).strip()
        if next_stage:
            state["Current stage"] = ensure_stage(next_stage)
        state["Human gate status"] = "pending" if state["Current stage"] in GATED_STAGES else "approved"
        state["Blocked reason"] = ""
        state["Next action"] = "review updated replan.md, stories.md, story files, and dag.md before approving the replanned story scope"
    elif status == "blocked":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Replan blocked: " + "; ".join(blockers[:3] or ["review replan.md"])
        state["Next action"] = "refresh the replan proposal or resolve blockers before applying"
    else:
        current = ensure_stage(state.get("Current stage") or "discuss")
        if current in GATED_STAGES:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = f"Replan proposal requires review: {summary or 'review replan.md'}"
        state["Next action"] = "review replan.md; apply with `confirm: replan` or reject/refine the proposal"
    return state


def handle_verify_fix(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    directive_text: str | None,
) -> dict[str, str]:
    payload = run_verify_fix(root, workflow_slug, directive_text)
    status = str(payload.get("status") or "").strip().lower()
    recommendation = str(payload.get("recommendation") or "").strip().lower()
    summary = str(payload.get("summary") or "").strip()
    active_story = str(payload.get("active_story") or active_story_name(state) or "-")
    fix_tasks = payload.get("fix_tasks", [])
    task_count = len(fix_tasks) if isinstance(fix_tasks, list) else 0
    blockers = list_payload_value(payload.get("blockers"))
    warnings = list_payload_value(payload.get("warnings"))
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "verify-fix",
        "Workflow Orchestrator, Reviewer QA, Product Owner",
        f"{active_story}: verify-fix {status or '-'} with {task_count} fix task(s)",
        summary or "Review verify-fix.md before approval",
    )
    state["Item note"] = f"verify-fix {status or '-'}: {task_count} fix task(s)"
    state["Challenge note"] = "; ".join((blockers + warnings)[:3])
    current = ensure_stage(state.get("Current stage") or "discuss")
    if status == "ready":
        if state.get("Human gate status") == "blocked" and state.get("Blocked reason", "").startswith("Verify-fix"):
            state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
            state["Blocked reason"] = ""
        state["Next action"] = "run review-sync or approve when the remaining review gates are satisfied"
    elif status == "blocked":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Verify-fix is blocked: " + "; ".join(blockers[:3] or ["review verify-fix.md"])
        state["Next action"] = "add acceptance criteria or active-story evidence, then rerun verify-fix"
    else:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = f"Verify-fix recommends `{recommendation or 'fix'}`: {summary or 'review verify-fix.md'}"
        state["Next action"] = "address the generated fix tasks or record explicit pass evidence, then rerun verify-fix"
    return state


def handle_ci_feedback(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    directive_text: str | None,
) -> dict[str, str]:
    payload = run_ci_feedback(root, workflow_slug, directive_text)
    status = str(payload.get("status") or "").strip().lower()
    summary = str(payload.get("summary") or "").strip()
    active_story = str(payload.get("active_story") or active_story_name(state) or "-")
    fix_tasks = payload.get("fix_tasks", [])
    task_count = len(fix_tasks) if isinstance(fix_tasks, list) else 0
    blockers = list_payload_value(payload.get("blockers"))
    warnings = list_payload_value(payload.get("warnings"))
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "ci-feedback",
        "Workflow Orchestrator, Reviewer QA",
        f"{active_story}: CI feedback {status or '-'} with {task_count} fix task(s)",
        summary or "Review ci-feedback.md before approval",
    )
    state["Item note"] = f"CI feedback {status or '-'}: {task_count} fix task(s)"
    state["Challenge note"] = "; ".join((blockers + warnings)[:3])
    current = ensure_stage(state.get("Current stage") or "discuss")
    if status == "ready":
        if state.get("Human gate status") == "blocked" and state.get("Blocked reason", "").startswith("CI feedback"):
            state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
            state["Blocked reason"] = ""
        state["Next action"] = "run review-sync or approve when the remaining review gates are satisfied"
    elif status == "blocked":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "CI feedback is blocked: " + "; ".join(blockers[:3] or ["review ci-feedback.md"])
        state["Next action"] = "record CI feedback for the current HEAD, then rerun ci-feedback"
    else:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = f"CI feedback requires fixes: {summary or 'review ci-feedback.md'}"
        state["Next action"] = "address CI fix tasks, rerun CI, then record passing ci-feedback"
    return state


def handle_accounting_record(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    directive_text: str | None,
) -> dict[str, str]:
    record = record_manual_invocation(root, workflow_slug, directive_text)
    record_id = str(record.get("id") or "")
    story = str(record.get("story_label") or "-")
    cost_value = record.get("estimated_cost_usd")
    cost = float(cost_value) if cost_value is not None else 0.0
    cost_text = f"${cost:.6f}" if record.get("cost_known") else "unknown cost"
    elapsed = float(record.get("elapsed_seconds") or 0.0)
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "accounting-record",
        "Workflow Orchestrator",
        f"{story}: recorded {record.get('kind', 'invocation')} {record_id}",
        str(record.get("summary") or "Invocation accounting updated"),
    )
    state["Item note"] = f"accounting recorded: {record_id}"
    state["Challenge note"] = f"{story}: cost {cost_text}, elapsed {elapsed:.1f}s"
    state["Next action"] = "review accounting.md when planning further retries or delegated work"
    return state


def handle_debt_record(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    directive_text: str,
) -> dict[str, str]:
    ensure_debt_artifacts(root, workflow_slug)
    directives = parse_directives(directive_text)
    if not directives:
        directives = {"summary": directive_text.strip()}
    active_story = active_story_name(state) or directives.get("story", "").strip() or "-"
    record = debt_record_from_directives(directives, workflow_slug, active_story, "Workflow Orchestrator")
    if not str(record.get("summary") or "").strip() and not str(record.get("id") or "").strip():
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "debt-record requires a summary or an existing debt id to update."
        state["Next action"] = "rerun debt-record with summary, type, severity, and owner"
        return state

    recorded = append_or_update_debt_record(root, workflow_slug, record)
    render_debt_summary(root, workflow_slug)
    debt_id = str(recorded.get("id") or "-")
    severity = str(recorded.get("severity") or "medium")
    status = str(recorded.get("status") or "open")
    summary = str(recorded.get("summary") or "").strip()
    state["Item note"] = f"technical debt recorded: {debt_id} ({severity}, {status})"
    if severity in {"high", "critical"} and status == "open":
        state["Challenge note"] = f"Open {severity} technical debt: {summary or debt_id}"
    elif severity in {"high", "critical"} and status not in {"resolved", "closed"}:
        state["Challenge note"] = f"{status.title()} {severity} technical debt: {summary or debt_id}"
    elif "technical debt" in state.get("Challenge note", "").lower():
        state["Challenge note"] = ""
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "debt-record",
        "Workflow Orchestrator",
        f"{active_story}: {debt_id} {severity}/{status} {summary}".strip(),
        "Regenerate DAG, implementation plan, and dispatch artifacts so downstream stories inherit the warning",
    )
    current = ensure_stage(state.get("Current stage") or "discuss")
    blocked_by_debt, debt_reason = technical_debt_block(root, workflow_slug)
    if current in {"release-planning", "done"} and blocked_by_debt:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = debt_reason
        state["Next action"] = "resolve or explicitly accept high/critical technical debt before release planning continues"
        return state
    if state.get("Human gate status") == "blocked" and is_technical_debt_block(state.get("Blocked reason", "")) and not blocked_by_debt:
        state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
        state["Blocked reason"] = ""
    state["Next action"] = "review debt.md and use dag-sync to refresh downstream debt propagation"
    return state


def handle_memory_record(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    directive_text: str,
) -> dict[str, str]:
    ensure_memory_artifacts(root, workflow_slug)
    directives = parse_directives(directive_text)
    if not directives:
        directives = {"summary": directive_text.strip()}
    active_story = active_story_name(state) or directives.get("story", "").strip() or "-"
    record = memory_record_from_directives(directives, workflow_slug, active_story, "Workflow Orchestrator")
    if not str(record.get("summary") or record.get("command") or record.get("id") or "").strip():
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "memory-record requires a summary, command, or existing memory id to update."
        state["Next action"] = "rerun memory-record with category, summary or command, evidence, and owner"
        return state

    recorded = append_or_update_memory_record(root, workflow_slug, record)
    render_memory_summary(root, workflow_slug)
    memory_id = str(recorded.get("id") or "-")
    category = str(recorded.get("category") or "implementation-pattern")
    status = str(recorded.get("status") or "active")
    summary = str(recorded.get("summary") or recorded.get("command") or "").strip()
    state["Item note"] = f"shared memory recorded: {memory_id} ({category}, {status})"
    state["Challenge note"] = ""
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "memory-record",
        "Workflow Orchestrator",
        f"{active_story}: {memory_id} {category}/{status} {summary}".strip(),
        "Regenerate story enrichment, implementation plan, and dispatch artifacts so later work can reuse the learning",
    )
    state["Next action"] = "review memory.md, then continue the current workflow gate"
    return state


def handle_dag_sync(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
) -> dict[str, str]:
    stories_path = root / ".workflow" / workflow_slug / "stories.md"
    if not stories_path.exists():
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Cannot generate a story DAG before stories.md exists."
        state["Next action"] = "enter or rework story-slicing so .workflow/<slug>/stories.md exists"
        return state
    maybe_generate_story_dag(root, workflow_slug, required=True)
    payload = load_story_dag(root, workflow_slug)
    block_reason = dag_block_reason(payload)
    state["Item note"] = "story DAG synchronized"
    state["Challenge note"] = ""
    if block_reason:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = block_reason
        state["Next action"] = "review dag-validation.md and resolve DAG blockers before implementation planning relies on the graph"
    elif state.get("Human gate status") == "blocked":
        blocked_reason = state.get("Blocked reason", "").strip()
        if blocked_reason.startswith("Story DAG "):
            current = ensure_stage(state.get("Current stage") or "discuss")
            state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
            state["Blocked reason"] = ""
            state["Next action"] = "review dag.md/dag.json and use ready levels for implementation planning"
        else:
            state["Next action"] = f"story DAG synchronized; resolve current block before continuing: {blocked_reason or 'active workflow block'}"
    else:
        state["Blocked reason"] = ""
        state["Next action"] = "review dag.md/dag.json and use ready levels for implementation planning"
    return state


def handle_actions(state: dict[str, str], root: Path, workflow_slug: str) -> dict[str, str]:
    run_action_menu(root, workflow_slug, state)
    return state


def handle_capability_synth(state: dict[str, str], root: Path, workflow_slug: str, objective: str | None) -> dict[str, str]:
    payload = run_capability_synth(root, workflow_slug, objective or "")
    validation = payload.get("validation", {}) if isinstance(payload, dict) else {}
    status = str(validation.get("status") or "unknown")
    state["Item note"] = "capability synthesis packet refreshed"
    if status == "fail":
        state["Blocked reason"] = "Capability synthesis validation has errors; review capability-synth-validation.md."
        state["Human gate status"] = "blocked"
    state["Next action"] = "review capability-synth.md, let Codex synthesize/update capabilities.md, then approve or refine capability review"
    return state


def handle_stage_synth(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    command: str,
    objective: str | None,
) -> dict[str, str]:
    kind = SYNTH_COMMAND_KINDS[command]
    payload = run_stage_synth(root, workflow_slug, kind, objective or "")
    validation = payload.get("validation", {}) if isinstance(payload, dict) else {}
    status = str(validation.get("status") or "unknown")
    artifact_stem = str(payload.get("artifact_stem") or command)
    title = str(payload.get("title") or artifact_stem)
    state["Item note"] = f"{title} refreshed"
    if status == "fail":
        state["Blocked reason"] = f"{title} validation has errors; review {artifact_stem}-validation.md."
        state["Human gate status"] = "blocked"
    state["Next action"] = f"review {artifact_stem}.md, let Codex synthesize/update the related workflow artifact, then approve or refine the current gate"
    return state


def dag_validation(payload: dict[str, object]) -> dict[str, object]:
    validation = payload.get("validation", {})
    return validation if isinstance(validation, dict) else {}


def dag_lane_dependencies(payload: dict[str, object]) -> dict[str, object]:
    dependencies = payload.get("lane_dependencies", {})
    return dependencies if isinstance(dependencies, dict) else {}


def list_payload_value(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def dag_block_reason(payload: dict[str, object]) -> str:
    if not payload:
        return "Story DAG is missing; run dag-sync after stories.md exists."
    validation = dag_validation(payload)
    if not validation:
        return "Story DAG validation metadata is missing; rerun dag-sync."
    status = str(validation.get("status", "")).strip().lower()
    errors = list_payload_value(validation.get("errors"))
    if status == "invalid" or errors:
        return "Story DAG is invalid: " + "; ".join(errors or ["validation failed"])
    lane_dependencies = dag_lane_dependencies(payload)
    lane_blockers = list_payload_value(lane_dependencies.get("blocked_by"))
    if status == "blocked" or lane_blockers:
        return "Story DAG is blocked by incomplete workflow lanes: " + ", ".join(lane_blockers or ["unknown lane dependency"])
    if not dag_nodes(payload):
        return "Story DAG has no nodes; define stories before delegated execution."
    return ""


def load_story_dag(root: Path, workflow_slug: str) -> dict[str, object]:
    path = root / ".workflow" / workflow_slug / "dag.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_execution_path(root: Path, workflow_slug: str) -> dict[str, object]:
    path = root / ".workflow" / workflow_slug / "execution-path.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def load_parallel_dispatch(root: Path, workflow_slug: str) -> dict[str, object]:
    path = root / ".workflow" / workflow_slug / "parallel-dispatch.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def dag_nodes(payload: dict[str, object]) -> list[dict[str, object]]:
    nodes = payload.get("nodes", [])
    if not isinstance(nodes, list):
        return []
    return [node for node in nodes if isinstance(node, dict)]


def dag_node_sort_key(node: dict[str, object]) -> tuple[int, int]:
    level = node.get("level")
    try:
        level_value = int(level) if level is not None else 999999
    except (TypeError, ValueError):
        level_value = 999999
    match = re.search(r"(\d+)", str(node.get("id") or node.get("story") or ""))
    story_value = int(match.group(1)) if match else 999999
    return level_value, story_value


def dag_story_name(node: dict[str, object]) -> str:
    return str(node.get("story") or "").strip()


def dag_node_for_story(payload: dict[str, object], story: str) -> dict[str, object]:
    match = re.search(r"(\d+)", story or "")
    expected_id = f"story-{match.group(1)}" if match else ""
    for node in dag_nodes(payload):
        if node.get("story") == story or node.get("id") == expected_id:
            return node
    return {}


def dag_dependency_blockers(payload: dict[str, object], node: dict[str, object]) -> list[str]:
    if not node:
        return []
    node_by_id = {str(item.get("id", "")): item for item in dag_nodes(payload)}
    blockers: list[str] = []
    deps = node.get("depends_on", [])
    if not isinstance(deps, list):
        return blockers
    for dep in deps:
        dep_id = str(dep).strip()
        dep_node = node_by_id.get(dep_id)
        if not dep_node:
            blockers.append(dep_id)
            continue
        if str(dep_node.get("status", "")).strip().lower() != "completed":
            blockers.append(str(dep_node.get("story") or dep_id))
    return blockers


def first_ready_dag_node(payload: dict[str, object]) -> dict[str, object]:
    ready = [
        node
        for node in dag_nodes(payload)
        if str(node.get("status", "")).strip().lower() in {"active", "ready"}
    ]
    return sorted(ready, key=dag_node_sort_key)[0] if ready else {}


def handle_execution_path(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
) -> dict[str, str]:
    maybe_generate_story_dag(root, workflow_slug, required=True)
    dag_payload = load_story_dag(root, workflow_slug)
    block_reason = dag_block_reason(dag_payload)
    if block_reason:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = block_reason
        state["Next action"] = "review dag-validation.md before selecting an execution path"
        return state
    active_story = active_story_name(state)
    if not active_story:
        node = first_ready_dag_node(dag_payload)
        active_story = dag_story_name(node)
    maybe_generate_execution_path(root, workflow_slug, active_story)
    payload = load_execution_path(root, workflow_slug)
    path = payload.get("execution_path", {})
    path = path if isinstance(path, dict) else {}
    node = payload.get("node", {})
    node = node if isinstance(node, dict) else {}
    state["Item note"] = f"execution path selected for {node.get('story') or active_story or 'ready story'}: {path.get('path') or '-'}"
    state["Next action"] = "review execution-path.md and run team-run or team-run-level when ownership scopes are ready"
    return state


def handle_team_run(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    reason: str | None,
) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    active_story = active_story_name(state)
    if current not in {"implementation-planning", "implementation", "review"}:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Delegated team execution is only valid during implementation-planning, implementation, or review."
        state["Next action"] = "advance the workflow to implementation-planning or later before running the team"
        return state
    maybe_generate_story_dag(root, workflow_slug, required=True)
    dag_payload = load_story_dag(root, workflow_slug)
    block_reason = dag_block_reason(dag_payload)
    if block_reason:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = block_reason
        state["Next action"] = "review dag-validation.md and resolve DAG blockers before delegated team execution"
        return state
    if not active_story:
        ready_node = first_ready_dag_node(dag_payload)
        ready_story = dag_story_name(ready_node)
        if ready_story:
            active_story = ready_story
            state["Active items"] = ready_story
            state["Item note"] = f"selected ready DAG story for team-run: {ready_story}"
            write_state(root / ".workflow" / workflow_slug / "state.md", state)
            maybe_generate_story_dag(root, workflow_slug)
            dag_payload = load_story_dag(root, workflow_slug)
        else:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = "No active story or ready DAG node is recorded for delegated team execution."
            state["Next action"] = "set an active story or resolve DAG dependencies before running the team"
            return state
    dag_node = dag_node_for_story(dag_payload, active_story)
    if not dag_node:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = f"Active story `{active_story}` is not present in the story DAG."
        state["Next action"] = "select a ready DAG node or rerun dag-sync after updating stories.md"
        return state
    dag_status = str(dag_node.get("status", "")).strip().lower()
    if dag_status in {"blocked", "deferred", "completed"}:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = f"Active story `{active_story}` is `{dag_status}` in the story DAG."
        state["Next action"] = "select a ready DAG node or resolve story dependencies before delegated team execution"
        return state
    blockers = dag_dependency_blockers(dag_payload, dag_node)
    if blockers:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = f"Active story `{active_story}` has unsatisfied DAG dependencies: {', '.join(blockers)}."
        state["Next action"] = "complete or replan the prerequisite story dependencies before delegated team execution"
        return state
    maybe_generate_execution_path(root, workflow_slug, active_story)
    execution_payload = load_execution_path(root, workflow_slug)
    execution_path = execution_payload.get("execution_path", {})
    execution_path = execution_path if isinstance(execution_path, dict) else {}
    if current == "implementation-planning":
        maybe_generate_implementation_plan(root, workflow_slug)
    sync_team_story_headers(root, workflow_slug, active_story)
    assignment_rows = parse_assignment_rows(root / ".workflow" / workflow_slug / "agent-assignments.md")
    parallel_slots = 1
    try:
        parallel_slots = max(1, int(parse_team_settings(root, workflow_slug).get("Parallel implementation slots", "1").strip()))
    except ValueError:
        parallel_slots = 1
    blocked, scope_reason = implementer_scope_conflict(assignment_rows, parallel_slots)
    if blocked:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = scope_reason
        state["Next action"] = "assign explicit, disjoint implementer write scopes before delegated team execution continues"
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "team-run-blocked",
            "Workflow Orchestrator, Tech Lead, Implementer 1, Implementer 2",
            scope_reason,
            "Assign explicit, disjoint implementer write scopes",
        )
        return state
    if state.get("Human gate status") == "blocked" and "Parallel implementer ownership overlaps:" in state.get("Blocked reason", ""):
        state["Human gate status"] = "approved"
        state["Blocked reason"] = ""
    agent_results_dir(root, workflow_slug)
    worktree_payload = prepare_team_run_worktrees(root, workflow_slug, active_story, assignment_rows, parallel_slots)
    worktree_blockers = list_payload_value(worktree_payload.get("blockers"))
    if str(worktree_payload.get("status") or "").strip().lower() != "ready":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Git worktree isolation is blocked: " + "; ".join(worktree_blockers or ["worktree setup failed"])
        state["Next action"] = "review worktrees.md and resolve git worktree blockers before delegated team execution"
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "worktree-isolation-blocked",
            "Workflow Orchestrator, Tech Lead, Implementer lanes",
            state["Blocked reason"],
            "Resolve git repository/worktree setup blockers before dispatching active-story implementers",
        )
        return state
    worktree_warning = "; ".join(list_payload_value(worktree_payload.get("warnings")))
    maybe_generate_team_dispatch(root, workflow_slug)
    set_runtime_mode(root, workflow_slug, "delegated-agent-team", "explicit wrkflw:team-run")
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "team-run",
        "Workflow Orchestrator, Product Owner, Tech Lead, Implementer 1, Implementer 2, Reviewer QA",
        f"Prepared delegated dispatch for {active_story}",
        "Run the role packets from assigned worktrees, sync result envelopes, then run merge-gate, merge-apply when needed, and integration-gate before review approval",
    )
    path_label = str(execution_path.get("path") or "-")
    state["Item note"] = f"team dispatch prepared for {active_story} using {path_label} execution path"
    state["Challenge note"] = worktree_warning
    if state.get("Human gate status") == "blocked":
        blocked_reason = state.get("Blocked reason", "").strip() or "active workflow block"
        state["Next action"] = f"resolve the current workflow block before delegated execution continues: {blocked_reason}"
    else:
        state["Next action"] = (
            "run the role packets from .workflow/"
            f"{workflow_slug}/dispatch/ using assigned worktrees, follow the {path_label} execution path, then synchronize results through team-sync-all and run merge-gate"
        )
    if reason and reason.strip():
        state["Approval note"] = reason.strip()
    return state


def handle_team_run_level(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    reason: str | None,
) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    if current not in {"implementation-planning", "implementation", "review"}:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Parallel level dispatch is only valid during implementation-planning, implementation, or review."
        state["Next action"] = "advance the workflow to implementation-planning or later before preparing parallel dispatch"
        return state
    maybe_generate_story_dag(root, workflow_slug, required=True)
    dag_payload = load_story_dag(root, workflow_slug)
    block_reason = dag_block_reason(dag_payload)
    if block_reason:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = block_reason
        state["Next action"] = "review dag-validation.md and resolve DAG blockers before parallel dispatch"
        return state
    maybe_generate_parallel_dispatch(root, workflow_slug)
    payload = load_parallel_dispatch(root, workflow_slug)
    status = str(payload.get("status", "")).strip().lower()
    blockers = list_payload_value(payload.get("blockers"))
    if status != "ready":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Parallel dispatch is blocked: " + "; ".join(blockers or ["no ready parallel level"])
        state["Next action"] = "review parallel-dispatch.md and add disjoint Allowed Write Paths or use single-story team-run"
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "team-run-level-blocked",
            "Workflow Orchestrator, Tech Lead, Implementer lanes",
            state["Blocked reason"],
            "Resolve parallel dispatch blockers or run a single story",
        )
        return state

    worktree_payload = prepare_parallel_worktrees(root, workflow_slug, payload)
    worktree_blockers = list_payload_value(worktree_payload.get("blockers"))
    if str(worktree_payload.get("status") or "").strip().lower() != "ready":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Git worktree isolation is blocked: " + "; ".join(worktree_blockers or ["worktree setup failed"])
        state["Next action"] = "review worktrees.md and resolve git worktree blockers before parallel execution"
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "worktree-isolation-blocked",
            "Workflow Orchestrator, Tech Lead, Implementer lanes",
            state["Blocked reason"],
            "Resolve git repository/worktree setup blockers before dispatching parallel implementers",
        )
        return state
    worktree_warning = "; ".join(list_payload_value(worktree_payload.get("warnings")))
    maybe_generate_parallel_dispatch(root, workflow_slug)
    payload = load_parallel_dispatch(root, workflow_slug)

    nodes = payload.get("nodes", [])
    node_count = len(nodes) if isinstance(nodes, list) else 0
    level = payload.get("level", "-") or "-"
    set_runtime_mode(root, workflow_slug, "parallel-dag-level-team", "explicit wrkflw:team-run-level")
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "team-run-level",
        "Workflow Orchestrator, Tech Lead, Implementer lanes, Reviewer QA",
        f"Prepared parallel dispatch for DAG level {level} with {node_count} stories",
        "Run story packets, sync result envelopes through team-sync-all, then run merge-gate, merge-apply when needed, and integration-gate before review approval",
    )
    state["Item note"] = f"parallel dispatch prepared for DAG level {level} ({node_count} stories)"
    state["Challenge note"] = worktree_warning
    state["Next action"] = f"run packets from .workflow/{workflow_slug}/parallel-dispatch/, synchronize results through team-sync-all, then run merge-gate, merge-apply when needed, and integration-gate"
    if reason and reason.strip():
        state["Approval note"] = reason.strip()
    return state


def handle_worktree_cleanup(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
) -> dict[str, str]:
    payload = cleanup_worktrees(root, workflow_slug)
    blockers = list_payload_value(payload.get("blockers"))
    if str(payload.get("status") or "").strip().lower() == "blocked":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Git worktree cleanup is blocked: " + "; ".join(blockers or ["cleanup failed"])
        state["Next action"] = "review worktrees.md and clean or commit dirty worktrees before retrying cleanup"
        return state
    state["Item note"] = "git worktree cleanup completed"
    state["Next action"] = "review worktrees.md and continue workflow review or release planning"
    if state.get("Human gate status") == "blocked" and state.get("Blocked reason", "").startswith("Git worktree cleanup"):
        current = ensure_stage(state.get("Current stage") or "discuss")
        state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
        state["Blocked reason"] = ""
    return state


def handle_merge_gate(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
) -> dict[str, str]:
    payload = run_merge_gate(root, workflow_slug)
    blockers = list_payload_value(payload.get("blockers"))
    warnings = list_payload_value(payload.get("warnings"))
    entries = payload.get("entries", [])
    entry_count = len(entries) if isinstance(entries, list) else 0
    if str(payload.get("status") or "").strip().lower() == "blocked":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Merge gate is blocked: " + "; ".join(blockers[:3] or ["review merge-gate.md"])
        state["Item note"] = f"merge gate inspected {entry_count} lane(s)"
        state["Challenge note"] = "; ".join(warnings[:3])
        state["Next action"] = "review merge-gate.md, fix out-of-scope or dirty worktree issues, then rerun merge-gate"
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "merge-gate-blocked",
            "Workflow Orchestrator, Implementer lanes, Reviewer QA",
            state["Blocked reason"],
            "Fix merge/reconcile blockers before review approval",
        )
        return state

    current = ensure_stage(state.get("Current stage") or "discuss")
    if state.get("Human gate status") == "blocked" and state.get("Blocked reason", "").startswith("Merge gate"):
        state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
        state["Blocked reason"] = ""
    state["Item note"] = f"merge gate ready for {entry_count} lane(s)"
    state["Challenge note"] = "; ".join(warnings[:3])
    changed_count = 0
    if isinstance(entries, list):
        changed_count = sum(1 for entry in entries if isinstance(entry, dict) and list_payload_value(entry.get("changed_paths")))
    state["Next action"] = (
        "run merge-apply with `confirm: merge-apply`, then integration-gate before review approval"
        if changed_count
        else "run integration-gate, then review-sync and approve when the review gate is satisfied"
    )
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "merge-gate",
        "Workflow Orchestrator, Implementer lanes, Reviewer QA",
        f"Merge gate passed for {entry_count} lane(s)",
        "Run merge-apply before integration-gate when lane branches contain committed changes",
    )
    return state


def handle_merge_apply(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    confirmation_text: str | None,
) -> dict[str, str]:
    payload = run_merge_apply(root, workflow_slug, confirmation_text)
    blockers = list_payload_value(payload.get("blockers"))
    warnings = list_payload_value(payload.get("warnings"))
    entries = payload.get("entries", [])
    entry_count = len(entries) if isinstance(entries, list) else 0
    status = str(payload.get("status") or "").strip().lower()
    if status == "blocked":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Merge apply is blocked: " + "; ".join(blockers[:3] or ["review merge-apply.md"])
        state["Item note"] = f"merge apply inspected {entry_count} lane(s)"
        state["Challenge note"] = "; ".join(warnings[:3])
        state["Next action"] = "review merge-apply.md, refresh stale gates or fix target checkout blockers, then rerun merge-apply"
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "merge-apply-blocked",
            "Workflow Orchestrator, Implementer lanes, Reviewer QA",
            state["Blocked reason"],
            "Resolve merge/apply blockers before integration-gate",
        )
        return state

    current = ensure_stage(state.get("Current stage") or "discuss")
    if state.get("Human gate status") == "blocked" and state.get("Blocked reason", "").startswith("Merge apply"):
        state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
        state["Blocked reason"] = ""
    state["Item note"] = "merge apply completed" if status == "applied" else "merge apply not required"
    state["Challenge note"] = "; ".join(warnings[:3])
    state["Next action"] = "run integration-gate against the applied result, then review-sync and approve when the review gate is satisfied"
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "merge-apply",
        "Workflow Orchestrator, Implementer lanes, Reviewer QA",
        f"Merge apply status: {status}; lanes inspected: {entry_count}",
        "Run integration-gate before review approval",
    )
    return state


def handle_integration_gate(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    evidence_text: str | None,
) -> dict[str, str]:
    payload = run_integration_gate(root, workflow_slug, evidence_text)
    blockers = list_payload_value(payload.get("blockers"))
    warnings = list_payload_value(payload.get("warnings"))
    requirement = payload.get("requirement", {})
    requirement = requirement if isinstance(requirement, dict) else {}
    required = bool(requirement.get("required"))
    status = str(payload.get("status") or "").strip().lower()
    if status == "blocked":
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "Integration test gate is blocked: " + "; ".join(blockers[:3] or ["review integration-test-gate.md"])
        state["Item note"] = "integration test gate inspected merge-gate evidence"
        state["Challenge note"] = "; ".join(warnings[:3])
        state["Next action"] = "record passing integration evidence, run an allowlisted test-id, fix failed validation, or explicitly waive with a reason"
        append_team_minute(
            team_minutes_path(root, workflow_slug),
            "integration-gate-blocked",
            "Workflow Orchestrator, Reviewer QA",
            state["Blocked reason"],
            "Provide integration validation evidence before review approval",
        )
        return state

    current = ensure_stage(state.get("Current stage") or "discuss")
    if state.get("Human gate status") == "blocked" and state.get("Blocked reason", "").startswith("Integration test gate"):
        state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
        state["Blocked reason"] = ""
    state["Item note"] = "integration validation required" if required else "integration validation not required"
    state["Challenge note"] = "; ".join(warnings[:3])
    state["Next action"] = "run review-sync, complete review evidence, then approve when the review gate is satisfied"
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "integration-gate",
        "Workflow Orchestrator, Reviewer QA",
        f"Integration test gate status: {status}",
        "Proceed to review evidence and human approval",
    )
    return state


def maybe_archive_openspec(root: Path, workflow_slug: str) -> None:
    links_path = root / ".workflow" / workflow_slug / "links.md"
    links = parse_kv_list(links_path)
    change_ref = clean_markdown_path_ref(links.get("OpenSpec change", ""))
    if not change_ref:
        return

    change_name = Path(change_ref).name
    active_change_dir = root / "openspec" / "changes" / change_name
    if not active_change_dir.exists():
        return

    run(
        ["openspec", "archive", change_name, "--yes"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )

    archive_root = root / "openspec" / "changes" / "archive"
    archived_matches = sorted(archive_root.glob(f"*-{change_name}")) if archive_root.exists() else []
    if archived_matches:
        links["OpenSpec change"] = str(archived_matches[-1].relative_to(root))
        write_kv_list(links_path, "Links", ["Tracker", "Design seed", "OpenSpec change", "PRs", "Docs"], links)
    set_openspec_lane_active(root, workflow_slug, False)


def active_story_name(state: dict[str, str]) -> str:
    active_items = [item.strip() for item in parse_items(state.get("Active items", "")) if item.strip()]
    return active_items[0] if active_items else ""


def detect_artifact_drift(
    root: Path,
    workflow_slug: str,
    stage: str,
    state: dict[str, str],
) -> tuple[bool, str]:
    if stage not in {"release-planning", "done"}:
        return False, ""

    contract = refresh_workflow_contract(root, workflow_slug)
    required = contract.get("OpenSpec required", "true").lower() in {"true", "1", "yes", "on"}
    initialized = contract.get("OpenSpec initialized", "false").lower() in {"true", "1", "yes", "on"}
    waived = contract.get("OpenSpec waived", "false").lower() in {"true", "1", "yes", "on"}
    if not required or waived or not initialized:
        return False, ""

    links = parse_kv_list(root / ".workflow" / workflow_slug / "links.md")
    change_ref = clean_markdown_path_ref(links.get("OpenSpec change", ""))
    if not change_ref:
        return True, "OpenSpec is required, but no active OpenSpec change is recorded in links.md."

    if "openspec/changes/archive/" in change_ref.replace("\\", "/") and stage != "done":
        return True, "The workflow points at an archived OpenSpec change before completion. Refresh the active OpenSpec change before continuing."

    change_dir = root / change_ref
    proposal_path = change_dir / "proposal.md"
    if not proposal_path.exists():
        return True, f"The recorded OpenSpec change `{change_ref}` is missing `proposal.md`. Refresh OpenSpec before continuing."

    active_story = active_story_name(state)
    if active_story:
        proposal_text = proposal_path.read_text(encoding="utf-8")
        if active_story not in proposal_text:
            return True, f"The active OpenSpec change `{change_ref}` does not mention the active workflow story `{active_story}`. Reconcile workflow/OpenSpec state before continuing."

    return False, ""


def apply_stage_entry_effects(stage: str, root: Path, workflow_slug: str) -> None:
    if stage == "story-slicing":
        maybe_generate_story_slices(root, workflow_slug)
        maybe_generate_story_dag(root, workflow_slug)
    if stage == "story-enrichment":
        maybe_generate_story_dag(root, workflow_slug)
        maybe_generate_story_enrichment(root, workflow_slug)
        maybe_generate_story_dag(root, workflow_slug)
    if stage == "spec-authoring":
        maybe_bridge_to_openspec(root, workflow_slug)
    if stage == "release-planning":
        maybe_bridge_to_openspec(root, workflow_slug)
        maybe_generate_release_plan(root, workflow_slug)
    if stage == "done":
        maybe_archive_openspec(root, workflow_slug)


def enter_stage(
    state: dict[str, str],
    stage: str,
    root: Path | None = None,
    workflow_slug: str | None = None,
) -> dict[str, str]:
    stage = ensure_stage(stage)
    state["Current stage"] = stage
    if root is not None and workflow_slug is not None:
        dep_blocked, dep_reason = lane_dependency_block(root, workflow_slug, stage)
        if dep_blocked:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = dep_reason
            state["Next action"] = "finish the prerequisite workflow lanes before advancing this lane"
            return state
        if stage == "spec-authoring":
            activated, activation_reason = ensure_openspec_lane(root, workflow_slug)
            if not activated:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = activation_reason
                state["Next action"] = "finish or deactivate the currently active OpenSpec lane before advancing this epic"
                return state
        blocked, reason = openspec_block_required(root, workflow_slug, stage)
        if blocked:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = reason
            state["Next action"] = "initialize OpenSpec or use an explicit override before continuing"
            return state
        blocked, conflict_reason = collaboration_block(root, workflow_slug)
        if blocked:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = conflict_reason
            state["Next action"] = "resolve blocking review findings or record a concrete conflict resolution before continuing"
            return state
        merge_blocked, merge_reason = merge_gate_block(root, workflow_slug, stage)
        if merge_blocked:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = merge_reason
            state["Next action"] = "run or repair merge-gate before advancing from review"
            return state
        apply_blocked, apply_reason = merge_apply_block(root, workflow_slug, stage)
        if apply_blocked:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = apply_reason
            state["Next action"] = "run or repair merge-apply before integration-gate and review approval"
            return state
        integration_blocked, integration_reason = integration_gate_block(root, workflow_slug, stage)
        if integration_blocked:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = integration_reason
            state["Next action"] = "run or repair integration-gate before advancing from review"
            return state
        ci_blocked, ci_reason = ci_feedback_block(root, workflow_slug, stage)
        if ci_blocked:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = ci_reason
            state["Next action"] = "run or repair ci-feedback before advancing from review"
            return state
        synthesis_blocked, synthesis_reason = feedback_synthesis_block(root, workflow_slug, stage)
        if synthesis_blocked:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = synthesis_reason
            state["Next action"] = "run or repair feedback-synth before advancing from review"
            return state
        verify_blocked, verify_reason = verify_fix_block(root, workflow_slug, stage)
        if verify_blocked:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = verify_reason
            state["Next action"] = "run or repair verify-fix before advancing from review"
            return state
        if stage == "done":
            blocked_by_debt, debt_reason = technical_debt_block(root, workflow_slug)
            if blocked_by_debt:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = debt_reason
                state["Next action"] = "resolve or explicitly accept high/critical technical debt before closing the workflow"
                return state
            blocked_by_team, team_reason = team_review_block(root, workflow_slug, stage)
            if blocked_by_team:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = team_reason
                state["Next action"] = "resolve collaboration blocks or record the required team review/signoff before closing the workflow"
                return state
            drift, drift_reason = detect_artifact_drift(root, workflow_slug, stage, state)
            if drift:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = drift_reason
                state["Next action"] = "run wrkflw:openspec-sync or wrkflw:reconcile before marking the workflow done"
                return state
        apply_stage_entry_effects(stage, root, workflow_slug)
        if stage == "release-planning":
            blocked_by_debt, debt_reason = technical_debt_block(root, workflow_slug)
            if blocked_by_debt:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = debt_reason
                state["Next action"] = "resolve or explicitly accept high/critical technical debt before release planning continues"
                return state
            blocked_by_team, team_reason = team_review_block(root, workflow_slug, stage)
            if blocked_by_team:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = team_reason
                state["Next action"] = "resolve collaboration blocks or record the required team review/signoff before release planning continues"
                return state
        if stage != "done":
            drift, drift_reason = detect_artifact_drift(root, workflow_slug, stage, state)
            if drift:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = drift_reason
                state["Next action"] = "run wrkflw:openspec-sync or wrkflw:reconcile before continuing"
                return state
    state["Human gate status"] = "pending" if stage in GATED_STAGES else "approved"
    state["Blocked reason"] = ""
    if stage in {"story-enrichment", "spec-authoring", "implementation-planning", "implementation", "review", "release-planning"}:
        if not state.get("Active items", "").strip():
            first_story = first_story_item(root, workflow_slug) if root is not None and workflow_slug is not None else ""
            if first_story:
                state["Active items"] = first_story
    state["Next action"] = NEXT_ACTION.get(stage, "")
    return state


def auto_progress_gates(
    state: dict[str, str],
    root: Path | None = None,
    workflow_slug: str | None = None,
) -> dict[str, str]:
    if root is None or workflow_slug is None:
        return state
    current = ensure_stage(state.get("Current stage") or "discuss")
    auto_notes: list[str] = []
    while current in GATED_STAGES and state.get("Human gate status") not in BLOCKED_STATES and auto_approve_enabled(root, workflow_slug, current):
        auto_notes.append(current)
        state["Human gate status"] = "approved"
        nxt = APPROVAL_NEXT_STAGE.get(current, current)
        if nxt == current:
            break
        enter_stage(state, nxt, root, workflow_slug)
        current = ensure_stage(state.get("Current stage") or "discuss")
    if auto_notes:
        note = "auto-approved gate(s): " + ", ".join(auto_notes)
        existing = state.get("Approval note", "").strip()
        state["Approval note"] = f"{existing} | {note}" if existing else note
    return state


def parse_items(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def normalize_item_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip())


def load_story_dependencies(root: Path, slug: str) -> dict[str, list[str]]:
    stories_path = root / ".workflow" / slug / "stories.md"
    if not stories_path.exists():
        return {}

    dependencies: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in stories_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            current = normalize_item_name(line[3:].split(":", 1)[0])
            dependencies.setdefault(current, [])
        elif current and line.lower().startswith("depends on:"):
            values = line.split(":", 1)[1]
            dependencies[current] = [normalize_item_name(item) for item in parse_items(values)]
    return dependencies


def first_story_item(root: Path, slug: str) -> str:
    stories_path = root / ".workflow" / slug / "stories.md"
    if not stories_path.exists():
        return ""
    for raw_line in stories_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("## Story "):
            return normalize_item_name(line[3:].split(":", 1)[0])
    return ""


SPECIAL_SATISFIED_DEPENDENCIES = {
    "completed prior epic",
    "completed prior epics",
    "completed dependencies",
}


def completed_workflow_dependencies(root: Path) -> set[str]:
    done: set[str] = set()
    for workflow_slug in workflow_slugs(root):
        state = parse_state(root / ".workflow" / workflow_slug / "state.md")
        if ensure_stage(state.get("Current stage") or "discuss") == "done":
            done.add(normalize_item_name(workflow_slug))
    return done


def extract_story_number(name: str) -> int | None:
    match = re.search(r"(\d+)", name)
    return int(match.group(1)) if match else None


def completed_items_from_history(root: Path, workflow_slug: str) -> set[str]:
    completed: set[str] = set()
    text = history_path(root, workflow_slug).read_text(encoding="utf-8") if history_path(root, workflow_slug).exists() else ""
    for block in re.split(r"(?=^##\s+Event\s+\d+\b)", text, flags=re.MULTILINE):
        values: dict[str, str] = {}
        for line in block.splitlines():
            if not line.startswith("- "):
                continue
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
        if ensure_stage(values.get("To stage", "")) != "done":
            continue
        for item in parse_items(values.get("Active items", "")) + parse_items(values.get("Focus items", "")):
            completed.add(normalize_item_name(item))
    return completed


def completed_items(
    state: dict[str, str],
    known_items: set[str],
    root: Path | None = None,
    workflow_slug: str | None = None,
) -> set[str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    active = [normalize_item_name(item) for item in parse_items(state.get("Active items", ""))]
    completed_names = completed_items_from_history(root, workflow_slug) if root is not None and workflow_slug is not None else set()
    if current == "done":
        completed_names.update(active)
    completed = {
        item
        for item in known_items
        if normalize_item_name(item) in completed_names
    }
    if completed:
        return completed
    for item in known_items:
        item_number = extract_story_number(item)
        if item_number is None:
            continue
        if current == "done" and item_number in {
            extract_story_number(active_item)
            for active_item in active
            if extract_story_number(active_item) is not None
        }:
            completed.add(item)
    return completed


def missing_dependencies(
    selected_items: list[str],
    dependencies: dict[str, list[str]],
    completed: set[str],
    completed_workflows: set[str] | None = None,
) -> dict[str, list[str]]:
    selected_set = {normalize_item_name(item) for item in selected_items}
    satisfied = selected_set | completed | (completed_workflows or set())
    missing: dict[str, list[str]] = {}
    for item in selected_set:
        deps = [
            dep
            for dep in dependencies.get(item, [])
            if dep.lower() not in SPECIAL_SATISFIED_DEPENDENCIES and dep not in satisfied
        ]
        if deps:
            missing[item] = deps
    return missing


def challenge_message_for_missing(missing: dict[str, list[str]]) -> str:
    parts = []
    for item, deps in missing.items():
        parts.append(f"{item} depends on {', '.join(deps)}")
    return "; ".join(parts)


def handle_approve(state: dict[str, str]) -> dict[str, str]:
    return handle_approve_with_reason(state, None)


def handle_approve_with_reason(
    state: dict[str, str],
    reason: str | None,
    root: Path | None = None,
    workflow_slug: str | None = None,
) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    state["Rework target"] = ""
    state["Rejection reason"] = ""
    state["Approval note"] = (reason or "").strip()
    state["Item note"] = ""
    state["Challenge note"] = ""
    if (state.get("Human gate status") or "").strip() in BLOCKED_STATES and root is not None and workflow_slug is not None:
        enter_stage(state, current, root, workflow_slug)
        if (state.get("Human gate status") or "").strip() in BLOCKED_STATES:
            return state
        return state
    state["Blocked reason"] = ""
    nxt = APPROVAL_NEXT_STAGE.get(current, current)
    enter_stage(state, nxt, root, workflow_slug)
    return auto_progress_gates(state, root, workflow_slug)


def handle_reject(state: dict[str, str], reason: str) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    target = REWORK_TARGET.get(current, current)
    state["Current stage"] = target
    state["Human gate status"] = "rejected"
    state["Blocked reason"] = ""
    state["Rework target"] = target
    state["Rejection reason"] = reason
    state["Approval note"] = ""
    state["Blocked reason"] = ""
    state["Item note"] = ""
    state["Challenge note"] = ""
    state["Next action"] = f"rework {target} to address rejection: {reason}".strip()
    return state


def handle_refine(
    state: dict[str, str],
    reason: str,
    root: Path | None = None,
    workflow_slug: str | None = None,
) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    existing_block = (state.get("Human gate status") or "").strip() in BLOCKED_STATES
    blocked_reason = state.get("Blocked reason", "").strip()
    state["Current stage"] = current
    state["Human gate status"] = "blocked" if existing_block else "pending"
    state["Rework target"] = current
    state["Rejection reason"] = ""
    state["Approval note"] = ""
    state["Blocked reason"] = blocked_reason if existing_block else ""
    state["Item note"] = ""
    state["Challenge note"] = ""
    if existing_block:
        state["Next action"] = f"resolve workflow block before refining {current}: {reason}".strip()
    else:
        state["Next action"] = f"refine {current}: {reason}".strip()
    if current == "implementation-planning" and root is not None and workflow_slug is not None:
        maybe_generate_implementation_plan(root, workflow_slug)
    if current == "story-enrichment" and root is not None and workflow_slug is not None:
        maybe_generate_story_enrichment(root, workflow_slug)
    return state


def handle_reconcile(
    state: dict[str, str],
    reason: str,
) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    state["Current stage"] = current
    state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
    state["Rework target"] = current
    state["Rejection reason"] = ""
    state["Approval note"] = ""
    state["Blocked reason"] = ""
    state["Item note"] = "workflow artifact reconciliation requested"
    state["Challenge note"] = ""
    state["Next action"] = f"reconcile workflow metadata and OpenSpec artifacts with implemented repo state: {reason}".strip()
    return state


def handle_openspec_sync(
    state: dict[str, str],
    root: Path,
    workflow_slug: str,
    reason: str | None,
) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    if not detect_openspec_initialized(root):
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "OpenSpec is not initialized in this repository."
        state["Item note"] = "OpenSpec sync requested but openspec/ is missing"
        state["Next action"] = "initialize OpenSpec before running wrkflw:openspec-sync"
        return state

    lane_ok, lane_reason = ensure_openspec_lane(root, workflow_slug)
    if not lane_ok:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = lane_reason
        state["Item note"] = "OpenSpec sync blocked by an active lane conflict"
        state["Next action"] = "finish or deactivate the currently active OpenSpec lane before syncing"
        return state

    maybe_bridge_to_openspec(root, workflow_slug)
    refresh_workflow_contract(root, workflow_slug)
    if state.get("Human gate status") == "blocked" and "OpenSpec" in state.get("Blocked reason", ""):
        state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
        state["Blocked reason"] = ""
    state["Item note"] = "OpenSpec artifacts synchronized from workflow state"
    state["Next action"] = reason.strip() if reason and reason.strip() else "review synchronized OpenSpec artifacts and continue the current gate"
    return state


def merge_csv(existing: str, new_items: str) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for chunk in [existing, new_items]:
        for item in [part.strip() for part in chunk.split(",") if part.strip()]:
            if item not in seen:
                seen.add(item)
                values.append(item)
    return ", ".join(values)


def handle_rework_item(state: dict[str, str], items: str, reason: str | None) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    state["Current stage"] = current
    state["Human gate status"] = "pending"
    state["Rework target"] = current
    state["Rejection reason"] = ""
    state["Approval note"] = ""
    state["Blocked reason"] = ""
    state["Item note"] = f"rework item(s): {items}" + (f" | {reason}" if reason else "")
    state["Challenge note"] = ""
    state["Next action"] = f"rework item(s) in {current}: {items}" + (f" because {reason}" if reason else "")
    return state


def handle_proceed_only(state: dict[str, str], items: str, reason: str | None, root: Path, slug: str) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    selected = [normalize_item_name(item) for item in parse_items(items)]
    dependencies = load_story_dependencies(root, slug)
    completed = completed_items(state, set(dependencies) | set(selected), root, slug)
    missing = missing_dependencies(selected, dependencies, completed, completed_workflow_dependencies(root))
    state["Current stage"] = current
    state["Human gate status"] = "pending"
    state["Blocked reason"] = ""
    if missing:
        challenge = challenge_message_for_missing(missing)
        state["Challenge note"] = f"Cannot proceed-only yet: {challenge}"
        state["Item note"] = f"proceed-only challenged: {items}" + (f" | {reason}" if reason else "")
        state["Next action"] = f"resolve dependency challenge before narrowing scope: {challenge}"
    else:
        state["Active items"] = ", ".join(selected)
        state["Challenge note"] = ""
        state["Item note"] = f"proceed only with: {', '.join(selected)}" + (f" | {reason}" if reason else "")
        if current == "done":
            state["Approval note"] = ""
            state["Rework target"] = ""
            state["Rejection reason"] = ""
            enter_stage(state, "story-enrichment", root, slug)
            auto_progress_gates(state, root, slug)
        else:
            state["Next action"] = f"proceed only with {', '.join(selected)}" + (f" because {reason}" if reason else "")
    return state


def handle_defer(state: dict[str, str], items: str, reason: str | None, root: Path, slug: str) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    deferred = [normalize_item_name(item) for item in parse_items(items)]
    active = [normalize_item_name(item) for item in parse_items(state.get("Active items", ""))]
    dependencies = load_story_dependencies(root, slug)
    completed = completed_items(state, set(dependencies) | set(active) | set(deferred), root, slug)
    completed_workflows = completed_workflow_dependencies(root)
    missing = {
        item: [
            dep
            for dep in dependencies.get(item, [])
            if dep.lower() not in SPECIAL_SATISFIED_DEPENDENCIES and dep in deferred and dep not in completed and dep not in completed_workflows
        ]
        for item in active
        if any(
            dep.lower() not in SPECIAL_SATISFIED_DEPENDENCIES and dep in deferred and dep not in completed and dep not in completed_workflows
            for dep in dependencies.get(item, [])
        )
    }
    missing = {item: deps for item, deps in missing.items() if deps}
    state["Current stage"] = current
    state["Human gate status"] = "pending"
    state["Blocked reason"] = ""
    if missing:
        challenge = challenge_message_for_missing(missing)
        state["Challenge note"] = f"Cannot defer yet: active scope depends on deferred item(s): {challenge}"
        state["Item note"] = f"defer challenged: {', '.join(deferred)}" + (f" | {reason}" if reason else "")
        state["Next action"] = f"resolve dependency challenge before deferring items: {challenge}"
    else:
        state["Deferred items"] = merge_csv(state.get("Deferred items", ""), ", ".join(deferred))
        state["Challenge note"] = ""
        state["Item note"] = f"defer item(s): {', '.join(deferred)}" + (f" | {reason}" if reason else "")
        state["Next action"] = f"defer {', '.join(deferred)}" + (f" because {reason}" if reason else "")
    return state


def handle_next(
    state: dict[str, str],
    root: Path | None = None,
    workflow_slug: str | None = None,
) -> dict[str, str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    gate_status = (state.get("Human gate status") or "").strip()
    if gate_status in BLOCKED_STATES:
        state["Next action"] = state.get("Next action") or "resolve the current workflow block before continuing"
        return state
    if current == "done" and root is not None and workflow_slug is not None:
        maybe_generate_story_dag(root, workflow_slug, required=True)
        dag_payload = load_story_dag(root, workflow_slug)
        block_reason = dag_block_reason(dag_payload)
        if block_reason:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = block_reason
            state["Next action"] = "review dag-validation.md before selecting the next story"
            return state
        ready_node = first_ready_dag_node(dag_payload)
        ready_story = dag_story_name(ready_node)
        if ready_story and normalize_item_name(ready_story) != normalize_item_name(active_story_name(state)):
            return handle_proceed_only(state, ready_story, "selected next DAG-ready story", root, workflow_slug)
    if current in GATED_STAGES and gate_status != "approved":
        if root is not None and workflow_slug is not None and auto_approve_enabled(root, workflow_slug, current):
            return handle_approve_with_reason(state, "auto-approved via wrkflw:next", root, workflow_slug)
        state["Next action"] = f"human gate still pending at {current}; approve or reject before continuing"
        return state
    return handle_approve_with_reason(state, None, root, workflow_slug)


def handle_override(state: dict[str, str], reason: str, root: Path, workflow_slug: str) -> dict[str, str]:
    contract = refresh_workflow_contract(root, workflow_slug)
    contract["OpenSpec waived"] = "true"
    contract["OpenSpec waiver reason"] = reason
    write_workflow_contract(root, workflow_slug, contract)

    current = ensure_stage(state.get("Current stage") or "discuss")
    state["Blocked reason"] = ""
    if state.get("Human gate status") == "blocked":
        state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
        state["Next action"] = NEXT_ACTION.get(current, "")
    state["Approval note"] = f"override applied: {reason}"
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Handle workflow command intents such as approve, reject, reconcile, rework, refine, rework-item, proceed-only, defer, next, resume, override, openspec-sync, actions, synthesis packet generation, dag-sync, execution-path, feedback-synth, issue-advisor, replan, verify-fix, ci-feedback, accounting-record, memory-record, debt-record, merge-gate, merge-apply, integration-gate, worktree-clean, and team operations.")
    parser.add_argument("--slug", required=True, help="Workflow slug, e.g. add-scim-managed-optout")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--command", required=True, choices=["approve", "reject", "reconcile", "rework", "refine", "rework-item", "proceed-only", "defer", "next", "override", "openspec-sync", "actions", "capability-synth", "design-synth", "story-synth", "story-enrichment-synth", "openspec-synth", "implementation-plan-synth", "dag-sync", "execution-path", "feedback-synth", "issue-advisor", "replan", "verify-fix", "ci-feedback", "accounting-record", "memory-record", "debt-record", "merge-gate", "merge-apply", "integration-gate", "worktree-clean", "staff", "assign", "challenge", "review-sync", "team-run", "team-run-level", "team-sync", "team-sync-all", "resume"])
    parser.add_argument("--reason", help="Approval, rejection, refine, or rework reason")
    parser.add_argument("--items", help="Comma-separated epic items or stories for targeted commands")
    parser.add_argument("--design-file", help="Optional explicit design.md path to seed workflow context")
    parser.add_argument("--resume", action="store_true", help="Resume the latest checkpoint for the requested command instead of starting a new transaction.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    requested_command = args.command
    effective_command = requested_command
    started_monotonic = time.monotonic()
    tx_path: Path | None = None
    try:
        checkpoint_context: dict[str, object] = {}
        start_phase = "prepare"
        if args.resume or requested_command == "resume":
            command_filter = None if requested_command == "resume" else requested_command
            tx_path, checkpoint_phase, tx_metadata = find_resumable_transaction(root, args.slug, command_filter)
            effective_command = str(tx_metadata.get("command") or command_filter or "").strip()
            if not effective_command or effective_command == "resume":
                raise RuntimeError("The selected checkpoint does not record a resumable command.")
            command_checkpoint = latest_command_progress_checkpoint(tx_path, effective_command) if checkpoint_phase == "prepare" else ""
            if command_checkpoint:
                checkpoint = restore_from_command_progress_checkpoint(root, tx_path, command_checkpoint)
                checkpoint_context = checkpoint.get("context", {}) if isinstance(checkpoint.get("context"), dict) else {}
                start_phase = "command"
            else:
                checkpoint = restore_from_checkpoint(root, tx_path, checkpoint_phase)
                checkpoint_context = checkpoint.get("context", {}) if isinstance(checkpoint.get("context"), dict) else {}
                start_phase = next_phase_after(checkpoint_phase)
        else:
            tx_path = snapshot_environment(root, args.slug, effective_command)

        state_path = root / ".workflow" / args.slug / "state.md"
        state_path.parent.mkdir(parents=True, exist_ok=True)

        state = parse_state(state_path)
        command_checkpoint_state = checkpoint_context.get("state")
        if start_phase == "command" and isinstance(command_checkpoint_state, dict):
            state.update({str(key): str(value) for key, value in command_checkpoint_state.items()})
        before_state_payload = checkpoint_context.get("before_state")
        before_state = before_state_payload if isinstance(before_state_payload, dict) else {}
        checkpoint_args = {
            "command": effective_command,
            "reason": args.reason or "",
            "items": args.items or "",
            "design_file": args.design_file or "",
        }

        if should_run_phase(start_phase, "prepare"):
            if not state["Current stage"]:
                state["Current stage"] = "discuss"
                state["Human gate status"] = "pending"
                state["Blocked reason"] = ""
                state["Challenge note"] = ""
                state["Next action"] = NEXT_ACTION["discuss"]

            maybe_seed_from_design(root, args.slug, args.design_file)
            maybe_generate_capability_inventory(root, args.slug)
            maybe_ensure_team_artifacts(root, args.slug)
            ensure_accounting_artifacts(root, args.slug)
            refresh_lane_dependencies(root, args.slug)
            refresh_workflow_contract(root, args.slug)
            before_state = deepcopy(state)
            write_phase_checkpoint(root, tx_path, "prepare", {"before_state": before_state, "args": checkpoint_args})
        elif not before_state:
            before_state = deepcopy(state)

        if should_run_phase(start_phase, "command"):
            if effective_command == "approve":
                state = handle_approve_with_reason(state, args.reason, root, args.slug)
            elif effective_command in {"reject", "rework"}:
                state = handle_reject(state, args.reason or "feedback not provided")
            elif effective_command == "reconcile":
                state = handle_reconcile(state, args.reason or "repository evidence is ahead of workflow or OpenSpec artifacts")
            elif effective_command == "refine":
                state = handle_refine(state, args.reason or "refinement requested", root, args.slug)
            elif effective_command == "rework-item":
                state = handle_rework_item(state, args.items or args.reason or "unspecified item", args.reason)
            elif effective_command == "proceed-only":
                state = handle_proceed_only(state, args.items or args.reason or "unspecified item", args.reason, root, args.slug)
            elif effective_command == "defer":
                state = handle_defer(state, args.items or args.reason or "unspecified item", args.reason, root, args.slug)
            elif effective_command == "next":
                state = handle_next(state, root, args.slug)
            elif effective_command == "override":
                state = handle_override(state, args.reason or "override reason not provided", root, args.slug)
            elif effective_command == "openspec-sync":
                state = handle_openspec_sync(state, root, args.slug, args.reason or args.items)
            elif effective_command == "actions":
                state = handle_actions(state, root, args.slug)
            elif effective_command == "capability-synth":
                state = handle_capability_synth(state, root, args.slug, args.reason or args.items)
            elif effective_command in SYNTH_COMMAND_KINDS:
                state = handle_stage_synth(state, root, args.slug, effective_command, args.reason or args.items)
            elif effective_command == "dag-sync":
                state = handle_dag_sync(state, root, args.slug)
            elif effective_command == "execution-path":
                state = handle_execution_path(state, root, args.slug)
            elif effective_command == "memory-record":
                state = handle_memory_record(state, root, args.slug, args.reason or args.items or "")
            elif effective_command == "debt-record":
                state = handle_debt_record(state, root, args.slug, args.reason or args.items or "")
            elif effective_command == "merge-gate":
                state = handle_merge_gate(state, root, args.slug)
            elif effective_command == "merge-apply":
                state = handle_merge_apply(state, root, args.slug, args.reason or args.items or "")
            elif effective_command == "integration-gate":
                state = handle_integration_gate(state, root, args.slug, args.reason or args.items or "")
            elif effective_command == "worktree-clean":
                state = handle_worktree_cleanup(state, root, args.slug)
            elif effective_command == "staff":
                state = handle_staff(state, root, args.slug, args.reason or args.items or "", args.items)
            elif effective_command == "assign":
                state = handle_assign(state, root, args.slug, args.reason or args.items or "")
            elif effective_command == "challenge":
                state = handle_challenge(state, root, args.slug, args.reason or args.items or "challenge raised", args.items)
            elif effective_command == "review-sync":
                state = handle_review_sync(state, root, args.slug, args.reason)
            elif effective_command == "feedback-synth":
                state = handle_feedback_synth(state, root, args.slug, args.reason or args.items)
            elif effective_command == "issue-advisor":
                state = handle_issue_advisor(state, root, args.slug, args.reason or args.items)
            elif effective_command == "replan":
                state = handle_replan(state, root, args.slug, args.reason or args.items or "")
            elif effective_command == "verify-fix":
                state = handle_verify_fix(state, root, args.slug, args.reason or args.items or "")
            elif effective_command == "ci-feedback":
                state = handle_ci_feedback(state, root, args.slug, args.reason or args.items or "")
            elif effective_command == "accounting-record":
                state = handle_accounting_record(state, root, args.slug, args.reason or args.items or "")
            elif effective_command == "team-run":
                state = handle_team_run(state, root, args.slug, args.reason)
            elif effective_command == "team-run-level":
                state = handle_team_run_level(state, root, args.slug, args.reason)
            elif effective_command == "team-sync":
                state = handle_team_sync(state, root, args.slug, args.reason or args.items or "")
            elif effective_command == "team-sync-all":
                state = handle_team_sync_all(state, root, args.slug, args.reason, tx_path, before_state)
            else:
                raise RuntimeError(f"Unsupported resumable command `{effective_command}`.")

            write_state(state_path, state)
            write_phase_checkpoint(root, tx_path, "command", {"before_state": before_state, "args": checkpoint_args})
        else:
            state = parse_state(state_path)

        if should_run_phase(start_phase, "postprocess"):
            maybe_generate_story_dag(root, args.slug)
            maybe_generate_execution_path(root, args.slug, active_story_name(state))
            refresh_lane_dependencies(root, args.slug)
            sync_execution_board(root, args.slug, state)
            sync_runtime_contract(root, args.slug, state)
            if ensure_stage(state.get("Current stage") or "discuss") in {"implementation-planning", "implementation", "review"}:
                maybe_generate_implementation_plan(root, args.slug)
            update_initiative_index(root, args.slug, state)
            append_history_event(root, args.slug, effective_command, before_state, state)
            record_command_invocation(
                root,
                args.slug,
                effective_command,
                requested_command,
                before_state,
                state,
                time.monotonic() - started_monotonic,
                tx_path.name if tx_path is not None else "",
                requested_command == "resume" or args.resume,
            )
            write_phase_checkpoint(root, tx_path, "postprocess", {"before_state": before_state, "args": checkpoint_args})

        if should_run_phase(start_phase, "diagram"):
            run(
                ["python3", str(Path(__file__).with_name("generate_workflow_diagram.py")), "--slug", args.slug, "--root", str(root)],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            write_phase_checkpoint(root, tx_path, "diagram", {"before_state": before_state, "args": checkpoint_args})

        commit_environment(tx_path)
        display_command = f"resume:{effective_command}" if requested_command == "resume" or args.resume else effective_command
        print(f"{display_command}: {state['Current stage']} | gate={state['Human gate status']} | next={state['Next action']}")
        return 0
    except Exception as exc:
        if tx_path is not None and not isinstance(exc, ResumeRefused):
            restore_environment(root, tx_path, str(exc))
        status = "resume refused" if isinstance(exc, ResumeRefused) else "rolled back"
        print(f"{requested_command}: {status} | error={exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

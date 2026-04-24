#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
import re
from datetime import datetime, timezone
from pathlib import Path
from subprocess import run


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
]


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
    return state


def write_state(path: Path, state: dict[str, str]) -> None:
    lines = ["# State", ""]
    for field in STATE_FIELDS:
        lines.append(f"- {field}: {state.get(field, '').strip()}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


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


def write_kv_list(path: Path, title: str, fields: list[str], values: dict[str, str]) -> None:
    lines = [f"# {title}", ""]
    for field in fields:
        lines.append(f"- {field}: {values.get(field, '').strip()}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


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
    write_workflow_contract(root, workflow_slug, contract)
    return contract


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


def maybe_archive_openspec(root: Path, workflow_slug: str) -> None:
    links_path = root / ".workflow" / workflow_slug / "links.md"
    links = parse_kv_list(links_path)
    change_ref = links.get("OpenSpec change", "").strip()
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


def apply_stage_entry_effects(stage: str, root: Path, workflow_slug: str) -> None:
    if stage == "story-slicing":
        maybe_generate_story_slices(root, workflow_slug)
    if stage == "spec-authoring":
        maybe_bridge_to_openspec(root, workflow_slug)
    if stage == "release-planning":
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
        blocked, reason = openspec_block_required(root, workflow_slug, stage)
        if blocked:
            state["Human gate status"] = "blocked"
            state["Blocked reason"] = reason
            state["Next action"] = "initialize OpenSpec or use an explicit override before continuing"
            return state
        apply_stage_entry_effects(stage, root, workflow_slug)
    state["Human gate status"] = "pending" if stage in GATED_STAGES else "approved"
    state["Blocked reason"] = ""
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


def extract_story_number(name: str) -> int | None:
    match = re.search(r"(\d+)", name)
    return int(match.group(1)) if match else None


def completed_items(state: dict[str, str], known_items: set[str]) -> set[str]:
    current = ensure_stage(state.get("Current stage") or "discuss")
    active = [normalize_item_name(item) for item in parse_items(state.get("Active items", ""))]
    active_number = next((extract_story_number(item) for item in active if extract_story_number(item) is not None), None)
    completed: set[str] = set()
    for item in known_items:
        item_number = extract_story_number(item)
        if item_number is None or active_number is None:
            continue
        if item_number < active_number:
            completed.add(item)
        elif item_number == active_number and current == "done":
            completed.add(item)
    return completed


def missing_dependencies(selected_items: list[str], dependencies: dict[str, list[str]], completed: set[str]) -> dict[str, list[str]]:
    selected_set = {normalize_item_name(item) for item in selected_items}
    satisfied = selected_set | completed
    missing: dict[str, list[str]] = {}
    for item in selected_set:
        deps = [dep for dep in dependencies.get(item, []) if dep not in satisfied]
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
    nxt = APPROVAL_NEXT_STAGE.get(current, current)
    state["Rework target"] = ""
    state["Rejection reason"] = ""
    state["Approval note"] = (reason or "").strip()
    state["Blocked reason"] = ""
    state["Item note"] = ""
    state["Challenge note"] = ""
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
    state["Current stage"] = current
    state["Human gate status"] = "pending"
    state["Rework target"] = current
    state["Rejection reason"] = ""
    state["Approval note"] = ""
    state["Blocked reason"] = ""
    state["Item note"] = ""
    state["Challenge note"] = ""
    state["Next action"] = f"refine {current}: {reason}".strip()
    if current == "implementation-planning" and root is not None and workflow_slug is not None:
        maybe_generate_implementation_plan(root, workflow_slug)
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
    completed = completed_items(state, set(dependencies) | set(selected))
    missing = missing_dependencies(selected, dependencies, completed)
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
    completed = completed_items(state, set(dependencies) | set(active) | set(deferred))
    missing = {
        item: [dep for dep in dependencies.get(item, []) if dep in deferred and dep not in completed]
        for item in active
        if any(dep in deferred and dep not in completed for dep in dependencies.get(item, []))
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
    parser = argparse.ArgumentParser(description="Handle workflow command intents such as approve, reject, rework, refine, rework-item, proceed-only, defer, next, and override.")
    parser.add_argument("--slug", required=True, help="Workflow slug, e.g. add-scim-managed-optout")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--command", required=True, choices=["approve", "reject", "rework", "refine", "rework-item", "proceed-only", "defer", "next", "override"])
    parser.add_argument("--reason", help="Approval, rejection, refine, or rework reason")
    parser.add_argument("--items", help="Comma-separated epic items or stories for targeted commands")
    parser.add_argument("--design-file", help="Optional explicit design.md path to seed workflow context")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    state_path = root / ".workflow" / args.slug / "state.md"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    state = parse_state(state_path)
    if not state["Current stage"]:
        state["Current stage"] = "discuss"
        state["Human gate status"] = "pending"
        state["Blocked reason"] = ""
        state["Challenge note"] = ""
        state["Next action"] = NEXT_ACTION["discuss"]

    maybe_seed_from_design(root, args.slug, args.design_file)
    maybe_generate_capability_inventory(root, args.slug)
    refresh_workflow_contract(root, args.slug)
    before_state = deepcopy(state)

    if args.command == "approve":
        state = handle_approve_with_reason(state, args.reason, root, args.slug)
    elif args.command in {"reject", "rework"}:
        state = handle_reject(state, args.reason or "feedback not provided")
    elif args.command == "refine":
        state = handle_refine(state, args.reason or "refinement requested", root, args.slug)
    elif args.command == "rework-item":
        state = handle_rework_item(state, args.items or args.reason or "unspecified item", args.reason)
    elif args.command == "proceed-only":
        state = handle_proceed_only(state, args.items or args.reason or "unspecified item", args.reason, root, args.slug)
    elif args.command == "defer":
        state = handle_defer(state, args.items or args.reason or "unspecified item", args.reason, root, args.slug)
    elif args.command == "next":
        state = handle_next(state, root, args.slug)
    elif args.command == "override":
        state = handle_override(state, args.reason or "override reason not provided", root, args.slug)

    write_state(state_path, state)
    append_history_event(root, args.slug, args.command, before_state, state)
    run(
        ["python3", str(Path(__file__).with_name("generate_workflow_diagram.py")), "--slug", args.slug, "--root", str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    print(f"{args.command}: {state['Current stage']} | gate={state['Human gate status']} | next={state['Next action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

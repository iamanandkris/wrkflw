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
    "OpenSpec lane active",
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
        insert_at = 2 if len(lines) >= 2 else len(lines)
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
            "",
        ]
    )
    path.write_text("\n".join(output), encoding="utf-8")


def parse_allowed_paths(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


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
    explicit = canonical_role_name(
        parse_directives(directive_text).get("role", "") or parse_directives(directive_text).get("owner", "")
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
    explicit = directives.get("status", "").strip().lower()
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

    _, row_map = execution_board_rows(board_path)

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


def sync_runtime_contract(root: Path, workflow_slug: str, state: dict[str, str]) -> None:
    runtime_path = root / ".workflow" / workflow_slug / "runtime-contract.md"
    if not runtime_path.exists():
        return
    board = parse_kv_list(root / ".workflow" / workflow_slug / "execution-board.md")
    roles = sorted(review_log_roles(root / ".workflow" / workflow_slug / "review-log.md"))
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


def set_runtime_mode(root: Path, workflow_slug: str, mode: str, spawn_policy: str) -> None:
    runtime_path = root / ".workflow" / workflow_slug / "runtime-contract.md"
    if not runtime_path.exists():
        return
    replace_or_append_bullet(runtime_path, "Runtime mode", mode)
    replace_or_append_bullet(runtime_path, "Spawn policy", spawn_policy)


def team_minutes_path(root: Path, workflow_slug: str) -> Path:
    return root / ".workflow" / workflow_slug / "team-minutes.md"


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
    directives = parse_directives(directive_text)
    assignments_path = root / ".workflow" / workflow_slug / "agent-assignments.md"
    rows = parse_assignment_rows(assignments_path)
    role = canonical_role_name(directives.get("role", "") or directives.get("owner", "") or "")
    if role not in {"Product Owner", "Tech Lead", "Implementer 1", "Implementer 2", "Reviewer QA"}:
        role = infer_role_from_output(directive_text, rows)
    if role not in {"Product Owner", "Tech Lead", "Implementer 1", "Implementer 2", "Reviewer QA"}:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "team-sync requires a recognized role."
        state["Next action"] = "provide role, status, and note for the team member being synchronized"
        return state
    status = infer_status_from_output(directive_text)
    if status not in {"planned", "in-progress", "in-review", "done", "blocked", "optional"}:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = f"team-sync received unsupported status: {status}"
        state["Next action"] = "use one of planned, in-progress, in-review, done, blocked, or optional"
        return state
    note = directives.get("note", "").strip() or directives.get("summary", "").strip()
    if not note:
        stripped = directive_text.strip()
        if stripped:
            note = stripped.replace("\n", " ").strip()
    follow_up = directives.get("follow-up", "").strip() or directives.get("follow up", "").strip()
    blocked_by = directives.get("blocked by", "").strip()
    reviewer = directives.get("reviewer", "").strip() or None

    board_path = root / ".workflow" / workflow_slug / "execution-board.md"
    update_execution_row_for_role(board_path, workflow_slug, role, status, note, blocked_by, reviewer)

    if role in rows:
        rows[role]["Status"] = status
        write_assignment_rows(assignments_path, workflow_slug, rows)

    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "handoff" if status == "done" else "team-sync",
        f"{role}, Workflow Orchestrator",
        note or f"{role} marked {status}",
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
    return state


def team_review_block(root: Path, workflow_slug: str, stage: str) -> tuple[bool, str]:
    settings = parse_team_settings(root, workflow_slug)
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
    blocked, _ = team_review_block(root, workflow_slug, current)
    if not blocked and state.get("Human gate status") == "blocked":
        blocked_reason = state.get("Blocked reason", "")
        if "signoff is missing in review-log.md" in blocked_reason or not unresolved:
            state["Human gate status"] = "pending" if current in GATED_STAGES else "approved"
            state["Blocked reason"] = ""
    state["Item note"] = f"review evidence synchronized: {summary}"
    state["Challenge note"] = unresolved
    state["Next action"] = "review evidence is synchronized; approve when the current gate is satisfied"
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
    if not active_story:
        state["Human gate status"] = "blocked"
        state["Blocked reason"] = "No active story is recorded for delegated team execution."
        state["Next action"] = "set or select the active story before running the team"
        return state
    if current == "implementation-planning":
        maybe_generate_implementation_plan(root, workflow_slug)
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
    maybe_generate_team_dispatch(root, workflow_slug)
    set_runtime_mode(root, workflow_slug, "delegated-agent-team", "explicit wrkflw:team-run")
    append_team_minute(
        team_minutes_path(root, workflow_slug),
        "team-run",
        "Workflow Orchestrator, Product Owner, Tech Lead, Implementer 1, Implementer 2, Reviewer QA",
        f"Prepared delegated dispatch for {active_story}",
        "Run the role packets and record findings/handoffs in team-minutes.md and review-log.md",
    )
    state["Item note"] = f"team dispatch prepared for {active_story}"
    state["Challenge note"] = ""
    if state.get("Human gate status") == "blocked":
        blocked_reason = state.get("Blocked reason", "").strip() or "active workflow block"
        state["Next action"] = f"resolve the current workflow block before delegated execution continues: {blocked_reason}"
    else:
        state["Next action"] = (
            "run the role packets from .workflow/"
            f"{workflow_slug}/dispatch/ using parallel implementer lanes and synchronized review evidence"
        )
    if reason and reason.strip():
        state["Approval note"] = reason.strip()
    return state


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
    change_ref = links.get("OpenSpec change", "").strip()
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
    if stage == "story-enrichment":
        maybe_generate_story_enrichment(root, workflow_slug)
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
        if stage == "done":
            blocked_by_team, team_reason = team_review_block(root, workflow_slug, stage)
            if blocked_by_team:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = team_reason
                state["Next action"] = "record the required team review/signoff in review-log.md before closing the workflow"
                return state
            drift, drift_reason = detect_artifact_drift(root, workflow_slug, stage, state)
            if drift:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = drift_reason
                state["Next action"] = "run wrkflw:openspec-sync or wrkflw:reconcile before marking the workflow done"
                return state
        apply_stage_entry_effects(stage, root, workflow_slug)
        if stage == "release-planning":
            blocked_by_team, team_reason = team_review_block(root, workflow_slug, stage)
            if blocked_by_team:
                state["Human gate status"] = "blocked"
                state["Blocked reason"] = team_reason
                state["Next action"] = "record the required team review/signoff in review-log.md before release planning continues"
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
    parser = argparse.ArgumentParser(description="Handle workflow command intents such as approve, reject, reconcile, rework, refine, rework-item, proceed-only, defer, next, override, and team operations.")
    parser.add_argument("--slug", required=True, help="Workflow slug, e.g. add-scim-managed-optout")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--command", required=True, choices=["approve", "reject", "reconcile", "rework", "refine", "rework-item", "proceed-only", "defer", "next", "override", "staff", "assign", "challenge", "review-sync", "team-run", "team-sync"])
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
    maybe_ensure_team_artifacts(root, args.slug)
    refresh_workflow_contract(root, args.slug)
    before_state = deepcopy(state)

    if args.command == "approve":
        state = handle_approve_with_reason(state, args.reason, root, args.slug)
    elif args.command in {"reject", "rework"}:
        state = handle_reject(state, args.reason or "feedback not provided")
    elif args.command == "reconcile":
        state = handle_reconcile(state, args.reason or "repository evidence is ahead of workflow or OpenSpec artifacts")
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
    elif args.command == "staff":
        state = handle_staff(state, root, args.slug, args.reason or args.items or "", args.items)
    elif args.command == "assign":
        state = handle_assign(state, root, args.slug, args.reason or args.items or "")
    elif args.command == "challenge":
        state = handle_challenge(state, root, args.slug, args.reason or args.items or "challenge raised", args.items)
    elif args.command == "review-sync":
        state = handle_review_sync(state, root, args.slug, args.reason)
    elif args.command == "team-run":
        state = handle_team_run(state, root, args.slug, args.reason)
    elif args.command == "team-sync":
        state = handle_team_sync(state, root, args.slug, args.reason or args.items or "")

    write_state(state_path, state)
    sync_execution_board(root, args.slug, state)
    sync_runtime_contract(root, args.slug, state)
    if ensure_stage(state.get("Current stage") or "discuss") in {"implementation-planning", "implementation", "review"}:
        maybe_generate_implementation_plan(root, args.slug)
    update_initiative_index(root, args.slug, state)
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

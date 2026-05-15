#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


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

GATED_STAGES = {
    "capability-review",
    "epic-shaping",
    "story-slicing",
    "story-enrichment",
    "spec-authoring",
    "review",
    "release-planning",
}

MATERIAL_COMMANDS = {
    "wrkflw:team-run",
    "wrkflw:team-run-level",
    "wrkflw:merge-apply",
    "wrkflw:replan \"confirm: replan\"",
    "wrkflw:worktree-clean",
}


@dataclass(frozen=True)
class ActionOption:
    command: str | None
    label: str
    reason: str
    category: str
    stage: str
    material: bool = False
    requires_explicit_selection: bool = False
    recommended: bool = False

    def to_json(self, index: int) -> dict[str, Any]:
        return {
            "index": index,
            "command": self.command,
            "label": self.label,
            "reason": self.reason,
            "category": self.category,
            "stage": self.stage,
            "material": self.material,
            "requires_explicit_selection": self.requires_explicit_selection,
            "recommended": self.recommended,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def workflow_dir(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug


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


def artifact_exists(root: Path, slug: str, relative: str) -> bool:
    return (workflow_dir(root, slug) / relative).exists()


def option(
    stage: str,
    command: str | None,
    label: str,
    reason: str,
    category: str,
    *,
    material: bool = False,
    requires_explicit_selection: bool | None = None,
    recommended: bool = False,
) -> ActionOption:
    explicit = requires_explicit_selection if requires_explicit_selection is not None else bool(material)
    if command in MATERIAL_COMMANDS:
        material = True
        explicit = True
    return ActionOption(
        command=command,
        label=label,
        reason=reason,
        category=category,
        stage=stage,
        material=material,
        requires_explicit_selection=explicit,
        recommended=recommended,
    )


def dedupe_options(options: list[ActionOption]) -> list[ActionOption]:
    deduped: list[ActionOption] = []
    seen: set[str] = set()
    for item in options:
        key = item.command or item.label
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def common_gate_options(stage: str) -> list[ActionOption]:
    if stage not in GATED_STAGES:
        return []
    return [
        option(stage, "wrkflw:approve \"...\"", "Approve current gate", "Move forward when the current artifact is acceptable.", "human-gate"),
        option(stage, "wrkflw:reject \"...\"", "Reject and route back", "Record why this gate is not acceptable and return to the nearest corrective stage.", "human-gate"),
        option(stage, "wrkflw:refine \"...\"", "Refine current artifact", "Keep the current stage but add detail or tighten scope.", "human-gate"),
        option(stage, "wrkflw:rework \"...\"", "Force targeted rework", "Treat the current stage as needing a stronger revision.", "human-gate"),
        option(stage, "wrkflw:rework-item \"...\"", "Rework one item", "Mark a specific story or epic item for targeted correction.", "human-gate"),
    ]


def stage_options(root: Path, slug: str, state: dict[str, str]) -> list[ActionOption]:
    stage = state.get("Current stage", "").strip() or "discuss"
    options: list[ActionOption] = []

    if stage == "discuss":
        options.extend(
            [
                option(stage, "wrkflw:approve \"...\"", "Proceed to capability review", "Use when repo/design discovery is good enough to review capabilities.", "progression"),
                option(stage, "wrkflw:design-synth \"...\"", "Synthesize design and epics", "Generate a Codex-ready design/codebase analysis and epic-selection packet.", "design"),
                option(stage, "wrkflw:capability-synth \"...\"", "Synthesize rich capabilities", "Generate a Codex-ready capability synthesis packet from profile, design, and repo evidence.", "capabilities"),
                option(stage, "wrkflw:reconcile \"...\"", "Reconcile drift", "Use when code is ahead of workflow or OpenSpec artifacts.", "reconciliation"),
                option(stage, "wrkflw:refine \"...\"", "Refine discovery", "Ask for more repo, design, or drift analysis before the first gate.", "human-gate"),
            ]
        )
    elif stage == "capability-review":
        options.extend(common_gate_options(stage))
        options.extend(
            [
                option(stage, "wrkflw:capability-synth \"...\"", "Synthesize rich capabilities", "Generate or refresh the Codex-ready capability synthesis packet before approving the inventory.", "capabilities"),
                option(stage, "wrkflw:defer \"...\"", "Defer capability scope", "Explicitly postpone non-active capabilities.", "scope-control"),
            ]
        )
    elif stage == "epic-shaping":
        options.extend(common_gate_options(stage))
        options.extend(
            [
                option(stage, "wrkflw:design-synth \"...\"", "Synthesize design and epics", "Refresh semantic design/codebase analysis before approving the epic boundary.", "design"),
                option(stage, "wrkflw:defer \"...\"", "Defer epic item", "Postpone non-active epic scope without rejecting the whole stage.", "scope-control"),
            ]
        )
    elif stage == "story-slicing":
        options.extend(common_gate_options(stage))
        options.extend(
            [
                option(stage, "wrkflw:story-synth \"...\"", "Synthesize story slices", "Generate a Codex-ready story slicing packet from capabilities, design, and repo evidence.", "stories"),
                option(stage, "wrkflw:dag-sync", "Refresh story DAG", "Regenerate DAG artifacts from story dependencies and lane blockers.", "scheduler"),
                option(stage, "wrkflw:proceed-only \"Story N\"", "Select active story", "Restrict active scope to one story or item after slicing.", "scope-control"),
                option(stage, "wrkflw:defer \"Story N\"", "Defer story", "Postpone non-active stories with dependency checks.", "scope-control"),
            ]
        )
    elif stage == "story-enrichment":
        options.extend(common_gate_options(stage))
        options.extend(
            [
                option(stage, "wrkflw:story-enrichment-synth \"...\"", "Synthesize story enrichment", "Generate a Codex-ready packet for story acceptance, tests, risks, and write paths.", "stories"),
                option(stage, "wrkflw:dag-sync", "Refresh story DAG", "Update ready/blocked/deferred status after enrichment changes.", "scheduler"),
                option(stage, "wrkflw:memory-record \"...\"", "Record reusable learning", "Capture repo conventions, validated commands, or failure patterns for later stories.", "learning"),
                option(stage, "wrkflw:debt-record \"...\"", "Record technical debt", "Make a known gap visible before implementation planning.", "debt"),
            ]
        )
    elif stage == "spec-authoring":
        options.extend(common_gate_options(stage))
        options.extend(
            [
                option(stage, "wrkflw:openspec-synth \"...\"", "Synthesize OpenSpec change", "Generate a Codex-ready packet for domain-specific OpenSpec requirements and tasks.", "openspec"),
                option(stage, "wrkflw:openspec-sync", "Refresh OpenSpec change", "Regenerate or reconcile the active story's OpenSpec proposal/spec/tasks.", "openspec"),
                option(stage, "wrkflw:override \"...\"", "Waive OpenSpec requirement", "Use only when a human explicitly accepts bypassing a major workflow requirement.", "override", material=True),
            ]
        )
    elif stage == "implementation-planning":
        options.extend(common_gate_options(stage))
        options.extend(
            [
                option(stage, "wrkflw:implementation-plan-synth \"...\"", "Synthesize implementation plan", "Generate a Codex-ready packet for first PR slicing, ownership, validation, and risk.", "planning"),
                option(stage, "wrkflw:execution-path", "Refresh execution path", "Classify the active story as simple or flagged and record role routing.", "scheduler"),
                option(stage, "wrkflw:staff \"...\"", "Adjust team model", "Change team size, parallel slots, or role notes.", "team"),
                option(stage, "wrkflw:assign \"...\"", "Assign role ownership", "Record owners and allowed write scopes.", "team"),
                option(stage, "wrkflw:team-run \"...\"", "Prepare delegated team run", "Generate role packets and optional active-story worktrees.", "team", material=True),
                option(stage, "wrkflw:team-run-level \"...\"", "Prepare parallel DAG-level run", "Dispatch multiple ready DAG stories only when write scopes are disjoint.", "team", material=True),
            ]
        )
    elif stage == "implementation":
        options.extend(
            [
                option(stage, "wrkflw:next", "Move to review when implementation evidence is ready", "Advance from this non-gated stage when implementation and validation are ready for review.", "progression"),
                option(stage, "wrkflw:team-run \"...\"", "Prepare delegated team run", "Generate role packets and optional active-story worktrees.", "team", material=True),
                option(stage, "wrkflw:team-run-level \"...\"", "Prepare parallel DAG-level run", "Dispatch multiple ready DAG stories only when write scopes are disjoint.", "team", material=True),
                option(stage, "wrkflw:team-sync \"...\"", "Sync one role update", "Ingest one role progress or review report.", "team"),
                option(stage, "wrkflw:team-sync-all", "Sync all result envelopes", "Validate and ingest unsynchronized agent result envelopes.", "team"),
                option(stage, "wrkflw:challenge \"...\"", "Record a challenge", "Capture concern, review finding, or red-team note before review.", "review"),
                option(stage, "wrkflw:merge-gate", "Run merge readiness gate", "Inspect worktree diffs, ownership, conflicts, and manifest freshness.", "validation"),
                option(stage, "wrkflw:integration-gate", "Record integration validation", "Inspect or record integration gate evidence after merge readiness.", "validation"),
                option(stage, "wrkflw:ci-feedback \"...\"", "Record CI feedback", "Bind external CI status and failure classification to the active story and HEAD.", "validation"),
                option(stage, "wrkflw:verify-fix \"...\"", "Verify acceptance criteria", "Check story acceptance criteria against explicit evidence.", "validation"),
            ]
        )
    elif stage == "review":
        options.extend(common_gate_options(stage))
        options.extend(
            [
                option(stage, "wrkflw:feedback-synth", "Synthesize review evidence", "Merge role reviews, gates, CI, debt, conflicts, and failures into one recommendation.", "review"),
                option(stage, "wrkflw:review-sync \"...\"", "Refresh review state", "Synchronize execution board and review notes from collaboration evidence.", "review"),
                option(stage, "wrkflw:challenge \"...\"", "Record a challenge", "Capture a blocker, risk, or red-team finding before approval.", "review"),
                option(stage, "wrkflw:verify-fix \"...\"", "Verify acceptance criteria", "Check story acceptance criteria against explicit evidence.", "validation"),
                option(stage, "wrkflw:ci-feedback \"...\"", "Record CI feedback", "Bind external CI status and failure classification to the active story and HEAD.", "validation"),
                option(stage, "wrkflw:merge-gate", "Run merge readiness gate", "Inspect worktree diffs, ownership, conflicts, and manifest freshness.", "validation"),
                option(stage, "wrkflw:merge-apply \"confirm: merge-apply\"", "Apply approved lane merges", "Apply ready wrkflw-owned lane branches only after explicit confirmation.", "validation", material=True),
                option(stage, "wrkflw:integration-gate", "Record integration validation", "Inspect or record integration gate evidence after merge readiness.", "validation"),
                option(stage, "wrkflw:issue-advisor", "Diagnose blocked story", "Recommend retry, split, debt acceptance, or replan when review is blocked.", "recovery"),
                option(stage, "wrkflw:replan", "Propose replan", "Create an advisory story/DAG mutation proposal from evidence.", "recovery"),
            ]
        )
    elif stage == "release-planning":
        options.extend(common_gate_options(stage))
        options.extend(
            [
                option(stage, "wrkflw:debt-record \"...\"", "Resolve or accept debt", "Update technical debt before release or closeout.", "debt"),
                option(stage, "wrkflw:verify-fix \"...\"", "Recheck acceptance evidence", "Rerun acceptance verification if story, review, gates, or HEAD changed.", "validation"),
                option(stage, "wrkflw:ci-feedback \"...\"", "Refresh CI evidence", "Record current external CI status before release.", "validation"),
                option(stage, "wrkflw:openspec-sync", "Refresh OpenSpec before closeout", "Reconcile active OpenSpec change before archival.", "openspec"),
                option(stage, "wrkflw:issue-advisor", "Diagnose release blocker", "Use when release planning is blocked by evidence, debt, or validation.", "recovery"),
            ]
        )
    elif stage == "done":
        options.extend(
            [
                option(stage, "wrkflw:proceed-only \"Story N\"", "Select next story", "Use when more ready stories remain and you want to activate one explicitly.", "loop"),
                option(stage, "wrkflw:dag-sync", "Refresh remaining DAG", "Recompute remaining ready/blocked/completed story status.", "scheduler"),
                option(stage, "wrkflw:worktree-clean", "Clean safe worktrees", "Remove clean wrkflw-owned worktrees after story closeout.", "cleanup", material=True),
                option(stage, "wrkflw:memory-record \"...\"", "Record final learning", "Capture reusable lessons before leaving the workflow.", "learning"),
                option(stage, "wrkflw:debt-record \"...\"", "Update carried debt", "Record accepted or resolved remaining debt.", "debt"),
            ]
        )
    else:
        options.extend(
            [
                option(stage, "wrkflw:next", "Continue workflow", "Advance if this is a non-gated stage and no gate is pending.", "progression"),
                option(stage, "wrkflw:refine \"...\"", "Refine current stage", "Ask for a safer stage-specific artifact update.", "human-gate"),
            ]
        )

    options.append(option(stage, None, "None / manual suggestion", "Do not run a wrkflw command; provide a custom instruction instead.", "manual"))
    return dedupe_options(options)


def recommended_command(root: Path, slug: str, state: dict[str, str], options: list[ActionOption]) -> str | None:
    stage = state.get("Current stage", "").strip() or "discuss"
    gate = state.get("Human gate status", "").strip()
    next_action = state.get("Next action", "").strip().lower()
    blocked_reason = state.get("Blocked reason", "").strip().lower()
    combined = " ".join([next_action, blocked_reason])

    if "merge-gate" in combined:
        return "wrkflw:merge-gate"
    if "merge-apply" in combined:
        return "wrkflw:merge-apply \"confirm: merge-apply\""
    if "integration-gate" in combined:
        return "wrkflw:integration-gate"
    if "ci-feedback" in combined:
        return "wrkflw:ci-feedback \"...\""
    if "feedback-synth" in combined:
        return "wrkflw:feedback-synth"
    if "verify-fix" in combined:
        return "wrkflw:verify-fix \"...\""
    if "openspec-sync" in combined:
        return "wrkflw:openspec-sync"
    if "reconcile" in combined:
        return "wrkflw:reconcile \"...\""
    if "debt" in combined:
        return "wrkflw:debt-record \"...\""

    if gate == "blocked":
        if any(item.command == "wrkflw:issue-advisor" for item in options):
            return "wrkflw:issue-advisor"
        return None

    if stage == "review":
        if gate != "approved":
            return "wrkflw:feedback-synth"
        return "wrkflw:approve \"...\""
    if stage == "implementation-planning":
        if not artifact_exists(root, slug, "execution-path.md"):
            return "wrkflw:execution-path"
        return "wrkflw:approve \"...\""
    if stage == "implementation":
        return "wrkflw:next"
    if stage == "done":
        return None
    if stage in GATED_STAGES:
        return "wrkflw:approve \"...\""
    if stage == "discuss":
        return "wrkflw:approve \"...\""
    return "wrkflw:next"


def mark_recommended(options: list[ActionOption], command: str | None) -> list[ActionOption]:
    if not command:
        return options
    marked: list[ActionOption] = []
    found = False
    for item in options:
        if item.command == command:
            marked.append(
                ActionOption(
                    command=item.command,
                    label=item.label,
                    reason=item.reason,
                    category=item.category,
                    stage=item.stage,
                    material=item.material,
                    requires_explicit_selection=item.requires_explicit_selection,
                    recommended=True,
                )
            )
            found = True
        else:
            marked.append(item)
    if found:
        return marked
    stage = options[0].stage if options else "discuss"
    return [option(stage, command, "Recommended command", "Recommended from current workflow state.", "recommended", recommended=True)] + options


def action_menu_paths(root: Path, slug: str) -> tuple[Path, Path]:
    wf = workflow_dir(root, slug)
    return wf / "action-menu.json", wf / "action-menu.md"


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Action Menu",
        "",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Current stage: {payload.get('current_stage', '-')}",
        f"- Human gate status: {payload.get('human_gate_status', '-')}",
        f"- Active items: {payload.get('active_items', '-') or '-'}",
        f"- Next action: {payload.get('next_action', '-') or '-'}",
        "",
    ]
    blockers = payload.get("blocked_reason") or ""
    if blockers:
        lines.extend(["## Current Blocker", "", blockers, ""])

    recommended = payload.get("recommended")
    if isinstance(recommended, dict) and recommended.get("command"):
        material = " Material command; requires explicit selection." if recommended.get("material") else ""
        lines.extend(
            [
                "## Recommended",
                "",
                f"1. `{recommended.get('command')}` - {recommended.get('label')}",
                f"   - Why: {recommended.get('reason')}{material}",
                "",
            ]
        )
    else:
        lines.extend(["## Recommended", "", "No automatic recommendation. Choose an option or provide a manual suggestion.", ""])

    lines.extend(["## Options", ""])
    for item in payload.get("options", []):
        if not isinstance(item, dict):
            continue
        command = item.get("command")
        prefix = f"{item.get('index')}. "
        material = " [material]" if item.get("material") else ""
        if command:
            lines.append(f"{prefix}`{command}` - {item.get('label')}{material}")
        else:
            lines.append(f"{prefix}{item.get('label')}")
        lines.append(f"   - {item.get('reason')}")
    lines.append("")
    lines.extend(
        [
            "## Notes",
            "",
            "- `None / manual suggestion` means no wrkflw command should be run; the operator should provide a custom instruction.",
            "- Material commands should not run silently. They require the user to select them or give an equivalent explicit instruction.",
            "- This menu is advisory and does not approve, reject, merge, replan, or dispatch work by itself.",
            "",
        ]
    )
    return "\n".join(lines)


def run_action_menu(root: Path, slug: str, state: dict[str, str] | None = None) -> dict[str, Any]:
    root = root.resolve()
    wf = workflow_dir(root, slug)
    wf.mkdir(parents=True, exist_ok=True)
    current_state = state or parse_state(wf / "state.md")
    options = stage_options(root, slug, current_state)
    recommended = recommended_command(root, slug, current_state, options)
    options = mark_recommended(options, recommended)
    json_options = [item.to_json(index) for index, item in enumerate(options, start=1)]
    recommended_payload = next((item for item in json_options if item.get("recommended")), None)
    payload: dict[str, Any] = {
        "generated_at": utc_now(),
        "workflow_slug": slug,
        "current_stage": current_state.get("Current stage", "") or "discuss",
        "human_gate_status": current_state.get("Human gate status", ""),
        "active_items": current_state.get("Active items", ""),
        "blocked_reason": current_state.get("Blocked reason", ""),
        "next_action": current_state.get("Next action", ""),
        "recommended": recommended_payload,
        "options": json_options,
    }
    json_path, markdown_path = action_menu_paths(root, slug)
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a stage-aware wrkflw action menu.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    payload = run_action_menu(Path(args.root), args.slug)
    recommended = payload.get("recommended") or {}
    command = recommended.get("command") if isinstance(recommended, dict) else ""
    print(f"action-menu {payload.get('current_stage')} | recommended={command or 'manual'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

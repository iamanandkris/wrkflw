#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from subprocess import run


STATE_FIELDS = [
    "Current stage",
    "Human gate status",
    "Rework target",
    "Rejection reason",
    "Approval note",
    "Active items",
    "Deferred items",
    "Item note",
    "Challenge note",
    "Next action",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Update workflow state after approval, rejection, or stage changes.")
    parser.add_argument("--slug", required=True, help="Workflow slug, e.g. add-scim-managed-optout")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--stage", help="Current workflow stage")
    parser.add_argument("--gate-status", choices=["pending", "approved", "rejected"], help="Human gate status")
    parser.add_argument("--rework-target", help="Stage to return to after rejection")
    parser.add_argument("--rejection-reason", help="Why the gate was rejected")
    parser.add_argument("--approval-note", help="Why the gate was approved")
    parser.add_argument("--active-items", help="Comma-separated active epic items or stories")
    parser.add_argument("--deferred-items", help="Comma-separated deferred epic items or stories")
    parser.add_argument("--item-note", help="Targeted item-level note")
    parser.add_argument("--challenge-note", help="Challenge or dependency note")
    parser.add_argument("--next-action", help="Immediate next action")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    state_path = root / ".workflow" / args.slug / "state.md"
    state_path.parent.mkdir(parents=True, exist_ok=True)

    state = parse_state(state_path)

    if args.stage is not None:
        state["Current stage"] = args.stage
    if args.gate_status is not None:
        state["Human gate status"] = args.gate_status
    if args.rework_target is not None:
        state["Rework target"] = args.rework_target
    if args.rejection_reason is not None:
        state["Rejection reason"] = args.rejection_reason
    if args.approval_note is not None:
        state["Approval note"] = args.approval_note
    if args.active_items is not None:
        state["Active items"] = args.active_items
    if args.deferred_items is not None:
        state["Deferred items"] = args.deferred_items
    if args.item_note is not None:
        state["Item note"] = args.item_note
    if args.challenge_note is not None:
        state["Challenge note"] = args.challenge_note
    if args.next_action is not None:
        state["Next action"] = args.next_action

    if args.gate_status == "approved":
        state["Rework target"] = ""
        state["Rejection reason"] = ""

    write_state(state_path, state)
    run(
        ["python3", str(Path(__file__).with_name("generate_workflow_diagram.py")), "--slug", args.slug, "--root", str(root)],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

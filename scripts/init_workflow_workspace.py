#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from subprocess import run


def write_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def parse_state(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def initiative_status(state: dict[str, str]) -> str:
    stage = state.get("Current stage", "").strip() or "discuss"
    gate = state.get("Human gate status", "").strip()
    if stage == "done":
        return "done"
    if gate == "blocked":
        return "blocked"
    if gate == "approved":
        return "in-progress"
    return "pending"


def update_initiative_index(root: Path, slug: str) -> None:
    workflow_root = root / ".workflow"
    workflow_root.mkdir(parents=True, exist_ok=True)
    index_path = workflow_root / "initiative-index.md"
    state = parse_state(workflow_root / slug / "state.md")
    links = parse_kv_list(workflow_root / slug / "links.md")

    row = {
        "Workflow slug": slug,
        "Status": initiative_status(state),
        "Current stage": state.get("Current stage", "").strip() or "discuss",
        "Design seed": links.get("Design seed", "").strip() or "-",
        "OpenSpec change": links.get("OpenSpec change", "").strip() or "-",
        "Docs": links.get("Docs", "").strip() or "-",
    }

    rows: list[dict[str, str]] = []
    lines = read_text(index_path).splitlines()
    for line in lines:
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
        if existing["Workflow slug"] == slug:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a local workflow workspace in the current repo.")
    parser.add_argument("--slug", required=True, help="Workflow slug, e.g. add-scim-managed-optout")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--design-file", help="Optional explicit design.md path to seed workflow context")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wf = root / ".workflow" / args.slug
    wf.mkdir(parents=True, exist_ok=True)

    write_if_missing(
        wf / "context.md",
        "# Context\n\n- Problem:\n- Goal:\n- Non-goals:\n- Constraints:\n",
    )
    write_if_missing(
        wf / "capabilities.md",
        "# Capability Inventory\n\n## Workflow Mode\n\n- Mode: general-delivery\n- Rationale: No capability inventory has been generated yet.\n",
    )
    write_if_missing(
        wf / "state.md",
        "# State\n\n- Current stage:\n- Human gate status:\n- Rework target:\n- Rejection reason:\n- Approval note:\n- Active items:\n- Deferred items:\n- Item note:\n- Challenge note:\n- Next action:\n",
    )
    write_if_missing(
        wf / "decisions.md",
        "# Decisions\n\n| Date | Decision | Reason |\n|---|---|---|\n",
    )
    write_if_missing(
        wf / "history.md",
        "# History\n\n"
        "## Event 001\n"
        "- Command: init\n"
        "- From stage: -\n"
        "- To stage: discuss\n"
        "- Gate: pending\n"
        "- Focus items: \n"
        "- Active items: \n"
        "- Deferred items: \n"
        "- Approval note: \n"
        "- Rejection reason: \n"
        "- Blocked reason: \n"
        "- Next action: classify initiative and gather context\n\n",
    )
    write_if_missing(
        wf / "links.md",
        "# Links\n\n- Tracker:\n- Design seed:\n- OpenSpec change:\n- PRs:\n- Docs:\n",
    )
    write_if_missing(
        wf / "gates.md",
        "# Gates\n\n"
        "- capability-review.autoApprove: false\n"
        "- epic-shaping.autoApprove: false\n"
        "- story-slicing.autoApprove: false\n"
        "- story-enrichment.autoApprove: false\n"
        "- spec-authoring.autoApprove: false\n"
        "- review.autoApprove: false\n"
        "- release-planning.autoApprove: false\n",
    )
    write_if_missing(
        wf / "workflow-contract.md",
        "# Workflow Contract\n\n"
        "- OpenSpec required: true\n"
        "- OpenSpec initialized: false\n"
        "- OpenSpec waived: false\n"
        "- OpenSpec lane active: false\n"
        "- OpenSpec waiver reason:\n",
    )
    write_if_missing(
        wf / "diagram-config.md",
        "# Diagram Config\n\n"
        "- flow.completedStoriesView: expanded\n"
        "- flow.showStoryProgressHistory: true\n"
        "- work.showStoryProgressHistory: true\n",
    )
    run(
        [
            "python3",
            str(Path(__file__).with_name("seed_workflow_from_design.py")),
            "--slug",
            args.slug,
            "--root",
            str(root),
            *(["--design-file", args.design_file] if args.design_file else []),
        ],
        check=True,
    )
    run(
        ["python3", str(Path(__file__).with_name("generate_capability_inventory.py")), "--slug", args.slug, "--root", str(root)],
        check=True,
    )
    run(
        ["python3", str(Path(__file__).with_name("ensure_team_artifacts.py")), "--slug", args.slug, "--root", str(root)],
        check=True,
    )
    run(
        ["python3", str(Path(__file__).with_name("generate_workflow_diagram.py")), "--slug", args.slug, "--root", str(root)],
        check=True,
    )
    update_initiative_index(root, args.slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

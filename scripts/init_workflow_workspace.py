#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from subprocess import run


def write_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


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
        wf / "state.md",
        "# State\n\n- Current stage:\n- Human gate status:\n- Rework target:\n- Rejection reason:\n- Approval note:\n- Active items:\n- Deferred items:\n- Item note:\n- Challenge note:\n- Next action:\n",
    )
    write_if_missing(
        wf / "decisions.md",
        "# Decisions\n\n| Date | Decision | Reason |\n|---|---|---|\n",
    )
    write_if_missing(
        wf / "links.md",
        "# Links\n\n- Tracker:\n- Design seed:\n- OpenSpec change:\n- PRs:\n- Docs:\n",
    )
    write_if_missing(
        wf / "gates.md",
        "# Gates\n\n"
        "- epic-shaping.autoApprove: false\n"
        "- story-slicing.autoApprove: false\n"
        "- story-enrichment.autoApprove: false\n"
        "- spec-authoring.autoApprove: false\n"
        "- review.autoApprove: false\n"
        "- release-planning.autoApprove: false\n",
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
        ["python3", str(Path(__file__).with_name("generate_workflow_diagram.py")), "--slug", args.slug, "--root", str(root)],
        check=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

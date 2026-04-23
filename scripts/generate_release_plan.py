#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_state(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def parse_story_block(stories_text: str, active_story: str) -> str:
    capture = False
    block: list[str] = []
    for raw_line in stories_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## Story "):
            current_name = line[3:].split(":", 1)[0].strip()
            if current_name == active_story:
                capture = True
                block.append(line)
                continue
            if capture:
                break
        elif capture:
            if line.startswith("## Recommended"):
                break
            block.append(line)
    return "\n".join(block).strip()


def story_number(name: str) -> str | None:
    match = re.search(r"(\d+)", name)
    return match.group(1) if match else None


def load_story_context(wf: Path, active_story: str) -> str:
    number = story_number(active_story)
    if number:
        story_path = wf / f"story-{number}.md"
        if story_path.exists():
            return read_text(story_path).strip()
    stories_text = read_text(wf / "stories.md")
    return parse_story_block(stories_text, active_story)


def choose_release_classification(active_story: str, story_block: str, root: Path) -> tuple[str, str]:
    sample_like = "sample" in str(root).lower() or "demo" in str(root).lower()
    local_only_terms = ["sample", "smoke test", "bootstrap", "prototype", "local"]
    if sample_like or any(term in story_block.lower() for term in local_only_terms):
        return (
            "local-only progress",
            "This story is primarily a bootstrap/sample increment. The acceptance bar is local compile/test success rather than a production rollout.",
        )
    return (
        "production-worthy",
        "This story appears to represent a meaningful increment that could be merged/released once review and validation are complete.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a release-plan artifact for the active workflow story.")
    parser.add_argument("--slug", required=True, help="Workflow slug")
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wf = root / ".workflow" / args.slug
    state = parse_state(wf / "state.md")
    active_story = state.get("Active items", "").split(",", 1)[0].strip() or "Current story"
    story_block = load_story_context(wf, active_story)
    classification, rationale = choose_release_classification(active_story, story_block, root)

    content = "\n".join(
        [
            "# Release Plan",
            "",
            f"## Active Story",
            active_story,
            "",
            "## Release Worthiness",
            classification,
            "",
            "## Rationale",
            rationale,
            "",
            "## Acceptance Bar",
            "- If production-worthy: review, merge, and rollout/consumer impact should be considered explicitly.",
            "- If local-only progress: local compile/test execution is sufficient for this increment.",
            "",
            "## Verification",
            "- Run the story's agreed validation steps.",
            "- Confirm the workflow's active story tasks are complete enough for the chosen release classification.",
            "",
            "## Rollback / Exit",
            "- Production-worthy: revert or disable the change if verification fails after merge.",
            "- Local-only progress: keep the change local or merge only when later slices raise it to a production-worthy increment.",
            "",
            "## Source Story Context",
            story_block or "-",
            "",
        ]
    )
    (wf / "release-plan.md").write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

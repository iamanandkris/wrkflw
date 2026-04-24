#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def first_meta_value(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def parse_capabilities(path: Path) -> tuple[str, list[dict[str, str]]]:
    mode = "general-delivery"
    capabilities: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in read_text(path).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("- Mode:"):
            mode = stripped.split(":", 1)[1].strip()
            continue
        if line.startswith("### "):
            if current is not None:
                capabilities.append(current)
            current = {"name": line[4:].strip(), "status": "optional", "why": "", "why_now": ""}
            continue
        if current is None:
            continue
        if stripped.startswith("- Status:"):
            current["status"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- Why:"):
            current["why"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- Why now:"):
            current["why_now"] = stripped.split(":", 1)[1].strip()
    if current is not None:
        capabilities.append(current)
    return mode, capabilities


def parse_context(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if line.startswith("- ") and ":" in line:
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def slug_title(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", " ", name).strip()


def capability_map(capabilities: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {cap["name"]: cap for cap in capabilities}


def selected_capabilities(mode: str, capabilities: list[dict[str, str]]) -> list[dict[str, str]]:
    if mode == "tutorial-sample":
        allowed = {"required", "recommended"}
    elif mode in {"feature-harness", "product-service"}:
        allowed = {"required", "recommended"}
    else:
        allowed = {"required"}
    return [cap for cap in capabilities if cap.get("status") in allowed]


def build_story_specs(mode: str, caps: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    stories: list[dict[str, object]] = []

    def has(name: str) -> bool:
        return name in caps

    if mode == "tutorial-sample":
        if has("Core Contract Usage"):
            stories.append(
                {
                    "title": "Bootstrap Core Contract Usage",
                    "depends_on": [],
                    "body": "Establish one minimal contract example so the sample has a clear starting point for later capability slices.",
                    "covers": ["Core Contract Usage"],
                }
            )
        if has("Field Validation"):
            stories.append(
                {
                    "title": "Add Field Validation Coverage",
                    "depends_on": ["Story 1"] if stories else [],
                    "body": "Add one focused validation slice that shows field annotations and multiple violations clearly.",
                    "covers": ["Field Validation"],
                }
            )
        if has("Sanitization And Visibility") or has("Lifecycle And Field Semantics"):
            stories.append(
                {
                    "title": "Add Visibility And Field Semantics",
                    "depends_on": ["Story 1"] if stories else [],
                    "body": "Demonstrate how internal, masked, reserved, or immutable fields change what is stored or exposed.",
                    "covers": [name for name in ["Sanitization And Visibility", "Lifecycle And Field Semantics"] if has(name)],
                }
            )
        if has("Nested Structures"):
            dep = []
            if any(story["covers"] == ["Field Validation"] for story in stories):
                dep = ["Story 2"] if len(stories) >= 2 else []
            stories.append(
                {
                    "title": "Add Nested Structure Coverage",
                    "depends_on": dep or (["Story 1"] if stories else []),
                    "body": "Add one nested contract example so the sample goes beyond flat toy payloads.",
                    "covers": ["Nested Structures"],
                }
            )
        if has("Developer Guidance"):
            depends = [f"Story {idx}" for idx in range(1, len(stories) + 1)] if stories else []
            stories.append(
                {
                    "title": "Add Developer Guidance",
                    "depends_on": depends,
                    "body": "Document what each sample slice demonstrates and how to run the sample locally.",
                    "covers": ["Developer Guidance"],
                }
            )
        return stories

    if mode == "feature-harness":
        ordered_groups = [
            ("Establish Core Contract Surface", ["Core Contract Usage", "Nested Structures", "Lifecycle And Field Semantics"]),
            ("Add Validation And Sanitization Coverage", ["Field Validation", "Sanitization And Visibility", "Custom Validators"]),
            ("Add Update And Schema Flows", ["Patch And Partial Validation", "Schema And Introspection"]),
            ("Add Runtime Integration Coverage", ["Runtime Integration"]),
            ("Add Developer Guidance", ["Developer Guidance"]),
        ]
    elif mode == "product-service":
        ordered_groups = [
            ("Establish Runtime Contract Surface", ["Core Contract Usage", "Nested Structures", "Runtime Integration"]),
            ("Add Validation And Field Semantics", ["Field Validation", "Lifecycle And Field Semantics", "Custom Validators"]),
            ("Add Update Flows", ["Patch And Partial Validation"]),
            ("Add Schema And Guidance", ["Schema And Introspection", "Developer Guidance"]),
        ]
    else:
        ordered_groups = [
            ("Establish Core Capability Slice", ["Core Contract Usage", "Field Validation"]),
            ("Add Deferred Capability Coverage", [cap["name"] for cap in caps.values() if cap["name"] not in {"Core Contract Usage", "Field Validation"}]),
        ]

    prior_exists = False
    story_number = 1
    for title, names in ordered_groups:
        covered = [name for name in names if has(name)]
        if not covered:
            continue
        stories.append(
            {
                "title": title,
                "depends_on": [f"Story {story_number - 1}"] if prior_exists else [],
                "body": f"Cover these capability categories in a coherent slice: {', '.join(covered)}.",
                "covers": covered,
            }
        )
        prior_exists = True
        story_number += 1
    return stories


def render_story_file(problem: str, goal: str, mode: str, stories: list[dict[str, object]]) -> str:
    lines = [
        "# Story Slices",
        "",
        "<!-- generated-by: wrkflw capability inventory -->",
        "",
        "## Context",
        "",
        f"- Workflow mode: {mode}",
        f"- Problem: {problem or '-'}",
        f"- Goal: {goal or '-'}",
        "",
    ]
    for idx, story in enumerate(stories, start=1):
        lines.extend(
            [
                f"## Story {idx}: {story['title']}",
            ]
        )
        depends = story.get("depends_on") or []
        if depends:
            lines.append(f"Depends on: {', '.join(depends)}")
        lines.append(str(story["body"]))
        covers = story.get("covers") or []
        if covers:
            lines.append(f"Covers: {', '.join(str(item) for item in covers)}")
        lines.append("")
    lines.extend(
        [
            "## Recommended Review",
            "",
            "- Check whether the first story is still small enough to merge independently.",
            "- Check whether required capabilities are visible in either the first stories or explicit deferred follow-up.",
            "- Rename stories if a more domain-specific title is clearer.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate capability-driven story slices for a workflow.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wf = root / ".workflow" / args.slug
    wf.mkdir(parents=True, exist_ok=True)

    context = parse_context(wf / "context.md")
    mode, capabilities = parse_capabilities(wf / "capabilities.md")
    selected = selected_capabilities(mode, capabilities)
    stories = build_story_specs(mode, capability_map(selected))

    rendered = render_story_file(
        problem=context.get("Problem", ""),
        goal=context.get("Goal", ""),
        mode=mode,
        stories=stories,
    )
    (wf / "stories.md").write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

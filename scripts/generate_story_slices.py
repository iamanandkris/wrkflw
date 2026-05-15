#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from workflow_profile import (
    parse_planning_profile,
    profile_domain_packs,
    profile_mode,
    profile_story_selection_allows_recommended,
)


STORY_SLICES_MARKER = "<!-- generated-by: wrkflw story slices -->"
LEGACY_GENERATED_MARKER = "<!-- generated-by: wrkflw capability inventory -->"
PLACEHOLDER_TITLES = {"# Story Slices", "# Stories"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def first_meta_value(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def parse_capabilities(path: Path) -> tuple[str, dict[str, str], list[dict[str, str]]]:
    text = read_text(path)
    raw_profile = parse_planning_profile(text)
    profile = {key: str(value) for key, value in raw_profile.items() if not isinstance(value, list)}
    profile["domain_packs"] = ", ".join(profile_domain_packs(raw_profile))
    mode = profile_mode(raw_profile)
    capabilities: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if line.startswith("### "):
            if current is not None:
                capabilities.append(current)
            current = {"name": line[4:].strip(), "status": "optional", "why": "", "why_now": ""}
            continue
        if current is None:
            continue
        if stripped.startswith("- Status:"):
            current["status"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- Owning workflow:"):
            current["owner"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- Why:"):
            current["why"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("- Why now:"):
            current["why_now"] = stripped.split(":", 1)[1].strip()
    if current is not None:
        capabilities.append(current)
    return mode, profile, capabilities


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


def selected_capabilities(profile: dict[str, object], capabilities: list[dict[str, str]]) -> list[dict[str, str]]:
    if profile_story_selection_allows_recommended(profile):
        allowed = {"required", "recommended"}
    else:
        allowed = {"required"}
    return [cap for cap in capabilities if cap.get("status") in allowed]


def should_preserve_existing_stories(path: Path) -> bool:
    if not path.exists():
        return False
    existing = path.read_text(encoding="utf-8")
    if not existing.strip():
        return False
    if STORY_SLICES_MARKER in existing or LEGACY_GENERATED_MARKER in existing:
        return False
    stripped_lines = [line.strip() for line in existing.splitlines() if line.strip()]
    if stripped_lines and stripped_lines[0] in PLACEHOLDER_TITLES and len(stripped_lines) <= 1:
        return False
    return True

PRODUCT_SERVICE_STORY_TEMPLATES = {
    "Contract Runtime Boundary": (
        "Establish Contract Runtime Boundary",
        "Create the isolated Concentric-backed contract runtime module and Java-friendly service interfaces so the rest of the platform can consume a stable lifecycle boundary.",
    ),
    "Case And Task Domain Model": (
        "Define Case And Task Domain Model",
        "Define the core aggregates, task state, and persistence-facing domain structures so later orchestration and governance slices build on explicit contracts.",
    ),
    "Lifecycle Transition Enforcement": (
        "Enforce Lifecycle Transition Rules",
        "Validate lifecycle progression through centralized transition rules and return structured blocked-transition feedback.",
    ),
    "Patch And Partial Mutation": (
        "Add Patch And Partial Mutation Flows",
        "Support controlled partial updates while preserving lifecycle, validation, and field-level semantics.",
    ),
    "Approval And Decision Governance": (
        "Enforce Approval Dependencies And Decision Records",
        "Add explicit approval requirements, decision records, and blocked-action reasons for approval-gated transitions.",
    ),
    "Evidence Intake And Secure Views": (
        "Add Evidence Intake And Secure Views",
        "Introduce evidence metadata contracts, secure view filtering, and the first controlled evidence-ingest path.",
    ),
    "Queue, SLA, And Assignment Operations": (
        "Add Queue, SLA, And Assignment Operations",
        "Represent assignment, queue, and breach-handling state explicitly so operational flows become enforceable and queryable.",
    ),
    "Audit Trail And Timeline Reconstruction": (
        "Add Audit Trail And Timeline Reconstruction",
        "Persist immutable audit events and expose timeline reconstruction behavior for review and regulatory traceability.",
    ),
    "API And Event Surface": (
        "Expose API And Event Surface",
        "Publish the first synchronous and asynchronous boundaries so external systems and UI clients can consume the platform safely.",
    ),
    "Schema And UI Metadata": (
        "Expose Schema And UI Metadata",
        "Expose contract-derived schema metadata so stage-aware forms and admin tooling stay aligned with contract evolution.",
    ),
}

PRODUCT_SERVICE_PRIORITY = {
    "Approval And Decision Governance": 10,
    "Patch And Partial Mutation": 20,
    "Contract Runtime Boundary": 30,
    "Case And Task Domain Model": 40,
    "Lifecycle Transition Enforcement": 50,
    "Evidence Intake And Secure Views": 60,
    "Queue, SLA, And Assignment Operations": 70,
    "Audit Trail And Timeline Reconstruction": 80,
    "API And Event Surface": 90,
    "Schema And UI Metadata": 100,
}


def build_story_specs(profile: dict[str, object], caps: dict[str, dict[str, str]], workflow_slug: str) -> list[dict[str, object]]:
    stories: list[dict[str, object]] = []
    mode = profile_mode(profile)
    delivery_kind = str(profile.get("delivery_kind", "general"))
    runtime_surface = str(profile.get("runtime_surface", "unspecified"))
    domain_packs = set(profile_domain_packs(profile))

    def has(name: str) -> bool:
        return name in caps

    if delivery_kind == "sample" or mode == "tutorial-sample":
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

    if runtime_surface == "mcp-server" and "database" in domain_packs:
        ordered_groups = [
            (
                "Bootstrap MCP Stdio Runtime And Connection Config",
                ["MCP Runtime And Stdio Transport", "SQL Server Connection Configuration"],
            ),
            (
                "Add Read-Only Query Execution Guardrails",
                ["Read-Only Query Execution", "Safety Guardrails And Policy Enforcement"],
            ),
            (
                "Add Schema Discovery And Result Shaping",
                ["Schema Discovery And Introspection", "Result Shaping And Error Reporting"],
            ),
            (
                "Add Operational Limits And Agent Guidance",
                ["Observability And Operational Limits", "Agent Usability Documentation"],
            ),
        ]
    elif runtime_surface == "frontend" and "game-rules" in domain_packs:
        ordered_groups = [
            (
                "Build Playable Board And Turn Loop",
                ["Board Rendering And Layout", "Turn Management", "Move Validation"],
            ),
            (
                "Add Game Outcome Detection",
                ["Win And Draw Detection"],
            ),
            (
                "Add Reset, Replay, And Accessibility",
                ["Reset And Replay Flow", "Browser Interaction And Accessibility"],
            ),
            (
                "Package Static Browser App And Guidance",
                ["Static App Packaging And Documentation"],
            ),
        ]
    elif delivery_kind == "harness" or mode == "feature-harness":
        ordered_groups = [
            ("Establish Core Contract Surface", ["Core Contract Usage", "Nested Structures", "Lifecycle And Field Semantics"]),
            ("Add Validation And Sanitization Coverage", ["Field Validation", "Sanitization And Visibility", "Custom Validators"]),
            ("Add Update And Schema Flows", ["Patch And Partial Validation", "Schema And Introspection"]),
            ("Add Runtime Integration Coverage", ["Runtime Integration"]),
            ("Add Developer Guidance", ["Developer Guidance"]),
        ]
    elif runtime_surface == "backend-api" or "workflow-governance" in domain_packs or mode == "product-service":
        actionable = [caps[name] for name in caps if caps[name].get("status") in {"required", "recommended"}]
        current_owner = [cap for cap in actionable if cap.get("owner", workflow_slug) == workflow_slug]
        ordered = sorted(
            current_owner or actionable,
            key=lambda capability: (
                PRODUCT_SERVICE_PRIORITY.get(str(capability["name"]), 999),
                str(capability["name"]),
            ),
        )
        prior_exists = False
        story_number = 1
        for capability in ordered:
            name = capability["name"]
            title, body = PRODUCT_SERVICE_STORY_TEMPLATES.get(
                name,
                (f"Implement {slug_title(name)}", f"Add a focused delivery slice for {name.lower()}."),
            )
            stories.append(
                {
                    "title": title,
                    "depends_on": [f"Story {story_number - 1}"] if prior_exists else [],
                    "body": body,
                    "covers": [name],
                }
            )
            prior_exists = True
            story_number += 1
        if stories:
            return stories
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


def render_story_file(
    problem: str,
    goal: str,
    mode: str,
    profile: dict[str, str],
    stories: list[dict[str, object]],
    completed_dependencies: list[str],
    deferred_follow_up: list[str],
) -> str:
    lines = [
        "# Story Slices",
        "",
        STORY_SLICES_MARKER,
        "",
        "## Context",
        "",
        f"- Compatibility mode: {mode}",
        f"- Problem: {problem or '-'}",
        f"- Goal: {goal or '-'}",
    ]
    if profile:
        lines.extend(
            [
                f"- Delivery kind: {profile.get('delivery_kind', '-')}",
                f"- Runtime surface: {profile.get('runtime_surface', '-')}",
                f"- Domain packs: {profile.get('domain_packs', '-')}",
                f"- Assurance level: {profile.get('assurance_level', '-')}",
                f"- Workflow strategy: {profile.get('workflow_strategy', '-')}",
            ]
        )
    if completed_dependencies:
        lines.extend(
            [
                "- Completed dependencies:",
                *[f"  - `{item}`" for item in completed_dependencies],
            ]
        )
    if deferred_follow_up:
        lines.extend(
            [
                "- Deferred follow-up lanes/capabilities:",
                *[f"  - {item}" for item in deferred_follow_up],
            ]
        )
    lines.append("")
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
    parser.add_argument("--force", action="store_true", help="Overwrite existing human-curated story slices.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wf = root / ".workflow" / args.slug
    wf.mkdir(parents=True, exist_ok=True)
    output_path = wf / "stories.md"
    if not args.force and should_preserve_existing_stories(output_path):
        return 0

    context = parse_context(wf / "context.md")
    mode, profile, capabilities = parse_capabilities(wf / "capabilities.md")
    profile_for_selection: dict[str, object] = dict(profile)
    profile_for_selection["domain_packs"] = [
        part.strip() for part in profile.get("domain_packs", "general").split(",") if part.strip()
    ]
    selected = selected_capabilities(profile_for_selection, capabilities)
    stories = build_story_specs(profile_for_selection, capability_map(selected), args.slug)
    completed_dependencies = sorted(
        {
            cap.get("owner", "").strip()
            for cap in capabilities
            if cap.get("status") == "satisfied by prior epic" and cap.get("owner", "").strip()
        }
    )
    deferred_follow_up = [
        f"{cap['name']} [{cap.get('status', '')}]"
        for cap in capabilities
        if cap.get("status") in {"deferred to later epic", "recommended follow-up"}
    ]

    rendered = render_story_file(
        problem=context.get("Problem", ""),
        goal=context.get("Goal", ""),
        mode=mode,
        profile=profile,
        stories=stories,
        completed_dependencies=completed_dependencies,
        deferred_follow_up=deferred_follow_up,
    )
    output_path.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

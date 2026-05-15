#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from workflow_synthesis import SynthesisSpec, read_text, run_synthesis_packet, validation_status, workflow_dir


SYNTH_COMMAND_KINDS = {
    "design-synth": "design",
    "story-synth": "story-slicing",
    "story-enrichment-synth": "story-enrichment",
    "openspec-synth": "openspec",
    "implementation-plan-synth": "implementation-planning",
}


STAGE_SYNTH_SPECS = {
    "design": SynthesisSpec(
        kind="design",
        title="Design And Epic Synthesis Packet",
        artifact_stem="design-synth",
        task_title="Codex Design And Epic Synthesis Task",
        default_objective="Synthesize design/codebase analysis and choose coherent epic candidates.",
        instructions=(
            "Analyze the design seed and repository evidence semantically, not as keyword buckets.",
            "Identify product boundaries, users, runtime surfaces, domain concepts, constraints, non-goals, and risk areas.",
            "Propose epic candidates that are coherent delivery lanes and explain why each lane belongs together.",
            "Call out where existing code already satisfies, constrains, or contradicts the design.",
        ),
        expected_output=(
            "Update or refine `.workflow/<slug>/normalized-design.md`, `.workflow/<slug>/epic-candidates.md`, and `.workflow/<slug>/design-slice.md` when needed.",
            "Each epic candidate includes scope, non-goals, dependencies, risk, and evidence.",
            "The selected epic is small enough to enter capability review without hiding unrelated design scope.",
        ),
        validation_expectations=(
            "Do not flatten a broad design into one generic backlog.",
            "Do not select an epic solely by slug/token overlap when semantic evidence points elsewhere.",
            "Keep completed or unrelated codebase behavior visible as constraints, not duplicate scope.",
        ),
        input_paths=(
            ".workflow/<slug>/context.md",
            ".workflow/<slug>/design-seed.md",
            ".workflow/<slug>/normalized-design.md",
            ".workflow/<slug>/epic-candidates.md",
            ".workflow/<slug>/design-slice.md",
            ".workflow/<slug>/state.md",
            "README.md",
            "docs/design.md",
            "design.md",
        ),
    ),
    "story-slicing": SynthesisSpec(
        kind="story-slicing",
        title="Story Slicing Synthesis Packet",
        artifact_stem="story-synth",
        task_title="Codex Story Slicing Synthesis Task",
        default_objective="Synthesize story slices from capabilities, design, and repo evidence.",
        instructions=(
            "Use the approved capabilities, Planning Profile, design context, and repo evidence to propose PR-sized story slices.",
            "Avoid fixed template grouping. Each story should represent a coherent behavior boundary with explicit capability coverage.",
            "Make dependencies explicit and flag any required capability that is intentionally deferred.",
            "Prefer small independently mergeable stories over broad phase-based stories.",
        ),
        expected_output=(
            "Update `.workflow/<slug>/stories.md` with story titles, descriptions, dependencies, and capability coverage.",
            "Each required capability is covered by a story or explicitly deferred with rationale.",
            "Story dependencies are acyclic and describe real implementation prerequisites.",
        ),
        validation_expectations=(
            "The first story is executable, not test-only or documentation-only unless the design itself is documentation-only.",
            "High-risk/interface stories do not hide required acceptance criteria in later untracked slices.",
            "Deferred items are deliberate and visible to the human gate.",
        ),
        input_paths=(
            ".workflow/<slug>/context.md",
            ".workflow/<slug>/design-slice.md",
            ".workflow/<slug>/capabilities.md",
            ".workflow/<slug>/stories.md",
            ".workflow/<slug>/dependencies.md",
            ".workflow/<slug>/state.md",
            "README.md",
        ),
    ),
    "story-enrichment": SynthesisSpec(
        kind="story-enrichment",
        title="Story Enrichment Synthesis Packet",
        artifact_stem="story-enrichment-synth",
        task_title="Codex Story Enrichment Synthesis Task",
        default_objective="Synthesize acceptance criteria, tests, risks, and write boundaries for the active story.",
        instructions=(
            "Use the active story, capabilities, DAG context, design evidence, and repo evidence to enrich the story file.",
            "Write domain-specific acceptance criteria instead of capability-name boilerplate.",
            "Include test expectations that prove the story behavior through the right surface for this project.",
            "Include risks and allowed write paths that match the implementation surface and dependencies.",
        ),
        expected_output=(
            "Update `.workflow/<slug>/story-N.md` for the active story.",
            "The story includes scope, dependencies, capability coverage, acceptance criteria, test expectations, risks, and allowed write paths.",
            "Acceptance criteria are specific enough for `verify-fix` and review gates to reason about.",
        ),
        validation_expectations=(
            "Do not generate generic sample wording for non-sample workflows.",
            "Do not omit acceptance criteria that are needed for the approved story to work.",
            "Allowed write paths should be concrete enough for merge/worktree gates.",
        ),
        input_paths=(
            ".workflow/<slug>/state.md",
            ".workflow/<slug>/context.md",
            ".workflow/<slug>/design-slice.md",
            ".workflow/<slug>/capabilities.md",
            ".workflow/<slug>/stories.md",
            ".workflow/<slug>/story-*.md",
            ".workflow/<slug>/dag.json",
            ".workflow/<slug>/records/memory.jsonl",
            ".workflow/<slug>/records/debt.jsonl",
            "README.md",
        ),
    ),
    "openspec": SynthesisSpec(
        kind="openspec",
        title="OpenSpec Synthesis Packet",
        artifact_stem="openspec-synth",
        task_title="Codex OpenSpec Synthesis Task",
        default_objective="Synthesize a domain-specific OpenSpec change for the active story.",
        instructions=(
            "Use the active story enrichment, capability coverage, design context, and repo evidence to author real OpenSpec requirements.",
            "Avoid generic wording like `The system SHALL support <story title>` unless it is expanded into concrete scenarios.",
            "Each scenario should describe observable behavior, failure behavior, or contract expectations relevant to the story.",
            "Keep deferred capability context visible without smuggling later-story scope into the current spec.",
        ),
        expected_output=(
            "Update `openspec/changes/<change>/proposal.md`, `tasks.md`, and `specs/**/spec.md` for the active story.",
            "Requirements and scenarios are domain-specific, testable, and aligned to story acceptance criteria.",
            "Tasks map to validation and implementation work without broad unrelated scope.",
        ),
        validation_expectations=(
            "OpenSpec output remains valid Markdown/OpenSpec structure.",
            "Every requirement has at least one concrete scenario.",
            "Acceptance criteria from the story are represented or explicitly excluded with rationale.",
        ),
        input_paths=(
            ".workflow/<slug>/state.md",
            ".workflow/<slug>/capabilities.md",
            ".workflow/<slug>/stories.md",
            ".workflow/<slug>/story-*.md",
            ".workflow/<slug>/specs/*.md",
            ".workflow/<slug>/links.md",
            "openspec/changes/*/proposal.md",
            "openspec/changes/*/tasks.md",
            "openspec/changes/*/specs/*/spec.md",
            "README.md",
        ),
    ),
    "implementation-planning": SynthesisSpec(
        kind="implementation-planning",
        title="Implementation Plan Synthesis Packet",
        artifact_stem="implementation-plan-synth",
        task_title="Codex Implementation Plan Synthesis Task",
        default_objective="Synthesize a coherent first implementation slice and validation plan.",
        instructions=(
            "Use the active story, OpenSpec artifacts, DAG context, memory, debt, and repo evidence to propose a first PR slice.",
            "Do not mechanically defer tests or acceptance criteria. For high-risk/interface stories, keep all acceptance-bearing work unless explicitly marked as later-slice scope.",
            "Assign ownership and validation commands based on actual codebase surfaces and story allowed paths.",
            "Call out build-scope drift, dependency gaps, and work that needs a separate story.",
        ),
        expected_output=(
            "Update `.workflow/<slug>/implementation-plan.md` with included scope, deferred scope, owners, validation, risks, and review standard.",
            "The first PR slice is executable and reviewable.",
            "Deferred work is explicitly justified and does not break the active story acceptance criteria.",
        ),
        validation_expectations=(
            "Required acceptance criteria remain in the included slice unless explicitly tagged as later-slice work.",
            "Validation commands match available repo scripts or clearly state manual evidence.",
            "Ownership respects allowed write paths and active story dependencies.",
        ),
        input_paths=(
            ".workflow/<slug>/state.md",
            ".workflow/<slug>/capabilities.md",
            ".workflow/<slug>/stories.md",
            ".workflow/<slug>/story-*.md",
            ".workflow/<slug>/dag.json",
            ".workflow/<slug>/execution-path.json",
            ".workflow/<slug>/implementation-plan.md",
            ".workflow/<slug>/records/memory.jsonl",
            ".workflow/<slug>/records/debt.jsonl",
            "package.json",
            "tsconfig.json",
            "README.md",
        ),
    ),
}


def parse_state(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if line.startswith("- ") and ":" in line:
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def active_story(root: Path, slug: str) -> str:
    state = parse_state(workflow_dir(root, slug) / "state.md")
    return state.get("Active items", "").split(",", 1)[0].strip()


def active_story_path(root: Path, slug: str) -> Path:
    story = active_story(root, slug)
    match = re.search(r"(\d+)", story)
    if match:
        return workflow_dir(root, slug) / f"story-{match.group(1)}.md"
    return workflow_dir(root, slug) / "story-1.md"


def validation_for_kind(root: Path, slug: str, kind: str) -> dict[str, Any]:
    wf = workflow_dir(root, slug)
    errors: list[str] = []
    warnings: list[str] = []
    if kind == "design":
        if not any((wf / name).exists() for name in ["design-seed.md", "design-slice.md", "context.md"]):
            errors.append("No design seed, design slice, or context artifact was found.")
        if not (wf / "epic-candidates.md").exists():
            warnings.append("No epic-candidates.md exists yet; synthesis should propose or refresh epic candidates.")
    elif kind == "story-slicing":
        if not (wf / "capabilities.md").exists():
            errors.append("capabilities.md is required before story synthesis.")
        if not (wf / "design-slice.md").exists():
            warnings.append("design-slice.md is missing; story synthesis may rely only on context and capabilities.")
    elif kind == "story-enrichment":
        if not (wf / "stories.md").exists():
            errors.append("stories.md is required before story enrichment synthesis.")
        if not active_story(root, slug):
            errors.append("state.md does not record an active story.")
        elif not active_story_path(root, slug).exists():
            warnings.append("The active story file does not exist yet; synthesis should create the enriched story artifact.")
    elif kind == "openspec":
        if not active_story_path(root, slug).exists():
            errors.append("The active story enrichment file is required before OpenSpec synthesis.")
        if not (wf / "capabilities.md").exists():
            warnings.append("capabilities.md is missing; OpenSpec synthesis may lose capability coverage context.")
    elif kind == "implementation-planning":
        if not active_story_path(root, slug).exists():
            errors.append("The active story enrichment file is required before implementation-plan synthesis.")
        if not (wf / "dag.json").exists():
            warnings.append("dag.json is missing; implementation-plan synthesis may not see dependency/risk routing.")
    else:
        errors.append(f"Unsupported synthesis kind `{kind}`.")
    return validation_status(errors, warnings, 0)


def stage_context_sections(root: Path, slug: str, kind: str) -> list[dict[str, object]]:
    wf = workflow_dir(root, slug)
    story = active_story(root, slug) or "-"
    lines = [
        f"- Active story: {story}",
        f"- State path: `{(wf / 'state.md').relative_to(root) if (wf / 'state.md').exists() else '.workflow/<slug>/state.md'}`",
    ]
    if kind in {"story-enrichment", "openspec", "implementation-planning"}:
        path = active_story_path(root, slug)
        lines.append(f"- Active story file: `{path.relative_to(root) if path.exists() else path.name}`")
    return [{"title": "Stage Context", "lines": lines}]


def run_stage_synth(root: Path, slug: str, kind: str, objective: str = "") -> dict[str, Any]:
    if kind not in STAGE_SYNTH_SPECS:
        raise ValueError(f"Unsupported synthesis kind `{kind}`.")
    spec = STAGE_SYNTH_SPECS[kind]
    return run_synthesis_packet(
        root,
        slug,
        spec,
        objective,
        validation=validation_for_kind(root.resolve(), slug, kind),
        markdown_sections=stage_context_sections(root.resolve(), slug, kind),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a stage-specific AI synthesis packet and validation report.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--kind", required=True, choices=sorted(STAGE_SYNTH_SPECS))
    parser.add_argument("--objective", default="")
    args = parser.parse_args()
    run_stage_synth(Path(args.root), args.slug, args.kind, args.objective)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

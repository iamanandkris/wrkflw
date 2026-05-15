#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from workflow_synthesis import SynthesisSpec, read_text, run_synthesis_packet, validation_status, workflow_dir


STATUS_VALUES = {"required", "recommended", "optional", "satisfied by prior epic", "deferred to later epic", "recommended follow-up"}

CAPABILITY_SYNTH_SPEC = SynthesisSpec(
    kind="capability",
    title="Capability Synthesis Packet",
    artifact_stem="capability-synth",
    task_title="Codex Capability Synthesis Task",
    default_objective="Synthesize a richer workflow capability inventory.",
    instructions=(
        "Use the planning profile, design artifacts, and repo evidence below to synthesize the most appropriate capabilities for this workflow.",
        "Do not merely map the compatibility mode to a fixed list. Consider finer-grained domain behavior, user workflows, architecture, tests, operational risk, and stated non-goals.",
        "The Python command packages and validates context; Codex performs the semantic synthesis before updating `capabilities.md`.",
    ),
    expected_output=(
        "Update `.workflow/<slug>/capabilities.md` with capability headings, status, owning workflow, why, why-now, evidence, and story prompts.",
        "Use statuses `required`, `recommended`, or `optional` unless the capability is explicitly satisfied/deferred by another workflow.",
        "Include `Evidence` bullets that cite concrete design or repo signals.",
    ),
    validation_expectations=(
        "Required capabilities map to explicit design/repo evidence or high-risk profile needs.",
        "Recommended capabilities are useful follow-up coverage, not hidden acceptance criteria.",
        "Optional capabilities are safe to omit from the first iteration.",
        "Capabilities contradicted by non-goals are excluded.",
        "High-risk or regulated profiles include validation, security, audit, rollback, or operator guidance where relevant.",
    ),
    input_paths=(
        ".workflow/<slug>/context.md",
        ".workflow/<slug>/design-slice.md",
        ".workflow/<slug>/design-seed.md",
        ".workflow/<slug>/capabilities.md",
        ".workflow/<slug>/stories.md",
        ".workflow/<slug>/state.md",
        ".workflow/<slug>/dependencies.md",
        "README.md",
    ),
)


def parse_capabilities(text: str) -> list[dict[str, Any]]:
    capabilities: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_section = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if line.startswith("### "):
            if current is not None:
                capabilities.append(current)
            current = {
                "name": line[4:].strip(),
                "status": "",
                "owner": "",
                "why": "",
                "why_now": "",
                "evidence": [],
                "story_prompts": [],
            }
            current_section = ""
            continue
        if current is None:
            continue
        if stripped.startswith("- Status:"):
            current["status"] = stripped.split(":", 1)[1].strip()
            current_section = ""
        elif stripped.startswith("- Owning workflow:"):
            current["owner"] = stripped.split(":", 1)[1].strip()
            current_section = ""
        elif stripped.startswith("- Why:"):
            current["why"] = stripped.split(":", 1)[1].strip()
            current_section = ""
        elif stripped.startswith("- Why now:"):
            current["why_now"] = stripped.split(":", 1)[1].strip()
            current_section = ""
        elif stripped == "- Evidence:":
            current_section = "evidence"
        elif stripped == "- Story prompts:":
            current_section = "story_prompts"
        elif current_section in {"evidence", "story_prompts"} and stripped.startswith("- "):
            current[current_section].append(stripped[2:].strip())
    if current is not None:
        capabilities.append(current)
    return capabilities


def validation_for_capabilities(capabilities: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not capabilities:
        errors.append("No capabilities found in capabilities.md.")
    seen: set[str] = set()
    for capability in capabilities:
        name = str(capability.get("name") or "").strip()
        status = str(capability.get("status") or "").strip().lower()
        if not name:
            errors.append("Capability heading is missing a name.")
            continue
        normalized_name = re.sub(r"\s+", " ", name.lower())
        if normalized_name in seen:
            warnings.append(f"Duplicate capability name: {name}")
        seen.add(normalized_name)
        if status not in STATUS_VALUES:
            errors.append(f"{name}: status `{status or '-'}` is not one of {', '.join(sorted(STATUS_VALUES))}.")
        if not str(capability.get("why") or "").strip():
            warnings.append(f"{name}: missing `Why` rationale.")
        if not str(capability.get("why_now") or "").strip():
            warnings.append(f"{name}: missing `Why now` profile/evidence rationale.")
        if not capability.get("story_prompts"):
            warnings.append(f"{name}: missing story prompts.")
        if not capability.get("evidence"):
            warnings.append(f"{name}: no explicit evidence bullets. Add design/repo evidence for AI-synthesized capabilities.")
    result = validation_status(errors, warnings, 0)
    result["capability_count"] = len(capabilities)
    return result


def current_capability_section(capabilities: list[dict[str, Any]]) -> list[dict[str, object]]:
    if not capabilities:
        lines = ["- None"]
    else:
        lines = [f"- {capability.get('name', '-')} [{capability.get('status', '-') or '-'}]" for capability in capabilities]
    return [{"title": "Current Capabilities", "lines": lines}]


def run_capability_synth(root: Path, slug: str, objective: str = "") -> dict[str, Any]:
    wf = workflow_dir(root.resolve(), slug)
    capabilities = parse_capabilities(read_text(wf / "capabilities.md"))
    validation = validation_for_capabilities(capabilities)
    payload = run_synthesis_packet(
        root,
        slug,
        CAPABILITY_SYNTH_SPEC,
        objective,
        validation=validation,
        extra_payload={"current_capabilities": capabilities},
        markdown_sections=current_capability_section(capabilities),
    )
    payload["validation"]["input_artifact_count"] = len(payload["input_artifacts"])
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an AI-assisted capability synthesis packet and validation report.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--objective", default="")
    args = parser.parse_args()
    run_capability_synth(Path(args.root), args.slug, args.objective)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

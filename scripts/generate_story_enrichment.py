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


def active_story_name(state: dict[str, str]) -> str:
    raw = state.get("Active items", "").split(",", 1)[0].strip()
    return raw or "Story 1"


def story_number(name: str) -> str:
    match = re.search(r"(\d+)", name)
    return match.group(1) if match else "1"


def parse_story_block(stories_text: str, active_story: str) -> dict[str, str]:
    lines = stories_text.splitlines()
    capture = False
    block: list[str] = []
    header = active_story
    depends_on = ""
    covers = ""
    for line in lines:
        if line.startswith("## Story "):
            current_header = line[3:].strip()
            current_name = current_header.split(":", 1)[0].strip()
            if current_name == active_story:
                capture = True
                header = current_header
                block.append(line)
                continue
            if capture:
                break
        if not capture:
            continue
        stripped = line.strip()
        block.append(line)
        if stripped.lower().startswith("depends on:"):
            depends_on = stripped.split(":", 1)[1].strip()
        elif stripped.lower().startswith("covers:"):
            covers = stripped.split(":", 1)[1].strip()
    title = header.split(":", 1)[1].strip() if ":" in header else active_story
    scope = ""
    for line in block:
        stripped = line.strip()
        if stripped and not stripped.startswith("## ") and not stripped.lower().startswith("depends on:") and not stripped.lower().startswith("covers:"):
            scope = stripped
            break
    return {
        "title": title,
        "depends_on": depends_on,
        "covers": covers,
        "scope": scope,
    }


def parse_capabilities(path: Path) -> dict[str, dict[str, object]]:
    capabilities: dict[str, dict[str, object]] = {}
    current: dict[str, object] | None = None
    prompts: list[str] = []
    for raw_line in read_text(path).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if line.startswith("### "):
            if current is not None:
                current["story_prompts"] = list(prompts)
                capabilities[str(current["name"])] = current
            current = {"name": line[4:].strip(), "status": "optional", "why": "", "why_now": ""}
            prompts = []
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
        elif stripped.startswith("- ") and not stripped.startswith("- Status:") and not stripped.startswith("- Owning workflow:") and not stripped.startswith("- Why:") and not stripped.startswith("- Why now:"):
            prompt = stripped[2:].strip()
            if prompt and prompt.lower() != "story prompts:":
                prompts.append(prompt)
    if current is not None:
        current["story_prompts"] = list(prompts)
        capabilities[str(current["name"])] = current
    return capabilities


def capability_names(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def bullet(text: str) -> str:
    return f"- {text}"


def acceptance_for_capability(name: str, capability: dict[str, object]) -> list[str]:
    prompts = [str(item) for item in capability.get("story_prompts", [])]
    if prompts:
        return [f"The sample includes an executable example that demonstrates {prompts[0].rstrip('.')}.", f"The story makes `{name}` visible enough that a developer can identify what behavior it is proving."]
    return [f"The sample includes an executable example that demonstrates `{name}` clearly."]


def tests_for_capability(name: str) -> list[str]:
    mapping = {
        "Contract Runtime Boundary": [
            "Add or update a test that proves the Java-facing contract service can validate a representative payload through the Concentric runtime boundary.",
            "Assert that Scala-backed validation details are translated into a stable Java/platform error shape.",
        ],
        "Case And Task Domain Model": [
            "Add or update a test that validates the first representative case/task payload shape and lifecycle defaults.",
            "Keep one success-path assertion that makes the initial domain contract surface easy to inspect.",
        ],
        "Lifecycle Transition Enforcement": [
            "Add or update a test that blocks an invalid transition because required lifecycle conditions are not satisfied.",
            "Assert the structured validation feedback returned for the blocked transition.",
        ],
        "Approval And Decision Governance": [
            "Add or update a test covering approval prerequisites or invalid decision-state combinations.",
        ],
        "Evidence Intake And Secure Views": [
            "Add or update a test for evidence metadata validation and secure/internal view filtering.",
        ],
        "Queue, SLA, And Assignment Operations": [
            "Add or update a test that validates queue or SLA-related state representation for a case/task.",
        ],
        "Audit Trail And Timeline Reconstruction": [
            "Add or update a test that proves material changes produce reconstructable audit records or deltas.",
        ],
        "API And Event Surface": [
            "Add or update a test that exercises the capability through a service/API-facing boundary and verifies emitted event intent where appropriate.",
        ],
        "Schema And UI Metadata": [
            "Add or update a test that inspects contract-derived schema or metadata expected by UI/admin consumers.",
        ],
        "Core Contract Usage": [
            "Add or update a test that validates one representative raw input into the typed contract model.",
            "Keep one success-path assertion that makes the core contract surface easy to inspect.",
        ],
        "Nested Structures": [
            "Add or update a test that exercises at least one nested payload shape.",
            "Assert that nested values survive validation/decoding as expected.",
        ],
        "Lifecycle And Field Semantics": [
            "Add or update a test covering immutable, reserved, masked, or internal field behavior.",
            "Assert the difference between accepted input and externally visible output when semantics apply.",
        ],
        "Field Validation": [
            "Add or update a test that produces at least one validation failure.",
            "Prefer a case with more than one failing field if the capability slice still stays readable.",
        ],
        "Sanitization And Visibility": [
            "Add or update a test that compares internal validated state to sanitized/public output.",
        ],
        "Custom Validators": [
            "Add or update a test that proves a domain-specific validator can reject invalid business input.",
        ],
        "Patch And Partial Validation": [
            "Add or update a test for patch or partial-update validation behavior.",
        ],
        "Schema And Introspection": [
            "Add or update a test that inspects generated schema or introspection output.",
        ],
        "Runtime Integration": [
            "Add or update a test that exercises the capability through the runtime/service entry point rather than only raw contract calls.",
        ],
        "Developer Guidance": [
            "Update developer-facing documentation so the new capability slice and run command are obvious.",
        ],
    }
    return mapping.get(name, [f"Add or update a test that makes `{name}` behavior explicit."])


def risks_for_capability(name: str) -> list[str]:
    mapping = {
        "Contract Runtime Boundary": [
            "Do not leak Scala collection or Concentric-specific runtime details beyond the dedicated boundary module.",
        ],
        "Case And Task Domain Model": [
            "Avoid expanding the first story into the full platform domain; keep the initial aggregate shape minimal but extensible.",
        ],
        "Lifecycle Transition Enforcement": [
            "Keep transition-policy logic centralized so controllers and orchestration services do not drift into duplicate validation paths.",
        ],
        "Approval And Decision Governance": [
            "Do not entangle all approval edge cases in the first slice; start with one representative protected action.",
        ],
        "Evidence Intake And Secure Views": [
            "Separate metadata validation from binary-storage integration so the story remains independently reviewable.",
        ],
        "Queue, SLA, And Assignment Operations": [
            "Avoid pulling full queue balancing and scheduling behavior into the same slice unless it is required by the active story.",
        ],
        "Audit Trail And Timeline Reconstruction": [
            "Keep the initial audit slice focused on reconstructable material changes rather than a full reporting/search platform.",
        ],
        "API And Event Surface": [
            "Keep the external surface thin until the contract and lifecycle boundary is stable.",
        ],
        "Schema And UI Metadata": [
            "Avoid promising UI behavior that is not yet backed by stable contract-derived metadata.",
        ],
        "Nested Structures": ["Avoid inflating the first slice with too many domain branches or deeply nested shapes at once."],
        "Lifecycle And Field Semantics": ["Keep field-semantics examples small enough that the behavior stays readable to reviewers."],
        "Patch And Partial Validation": ["Do not mix full-update and partial-update semantics in a single unclear example."],
        "Runtime Integration": ["Keep runtime integration thin so the story remains a capability slice, not a full service build-out."],
        "Developer Guidance": ["Keep docs aligned with actual runnable tests so the harness does not drift into aspirational documentation."],
    }
    return mapping.get(name, ["Keep the slice small enough to stay independently reviewable."])


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an enriched story artifact for the active workflow story.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wf = root / ".workflow" / args.slug
    wf.mkdir(parents=True, exist_ok=True)
    state = parse_state(wf / "state.md")
    active_story = active_story_name(state)
    num = story_number(active_story)
    story = parse_story_block(read_text(wf / "stories.md"), active_story)
    capabilities = parse_capabilities(wf / "capabilities.md")
    covered = capability_names(story["covers"])

    acceptance: list[str] = []
    tests: list[str] = []
    risks: list[str] = []
    for name in covered:
        capability = capabilities.get(name, {"name": name, "story_prompts": []})
        acceptance.extend(acceptance_for_capability(name, capability))
        tests.extend(tests_for_capability(name))
        risks.extend(risks_for_capability(name))

    dedup = lambda items: list(dict.fromkeys(item for item in items if item))
    acceptance = dedup(acceptance)
    tests = dedup(tests)
    risks = dedup(risks)

    acceptance_lines = [bullet(item) for item in acceptance] or ["- Define the acceptance criteria for this story."]
    test_lines = [bullet(item) for item in tests] or ["- Define the test expectations for this story."]
    risk_lines = [bullet(item) for item in risks] or ["- Keep the slice small enough to stay independently reviewable."]

    lines = [
        f"# {active_story}",
        "",
        "## Story",
        story["title"] or active_story,
        "",
        "## Scope",
        story["scope"] or f"Advance {active_story} with a small, reviewable capability slice.",
        "",
        "## Dependencies",
        story["depends_on"] or "-",
        "",
        "## Capability Coverage",
        story["covers"] or "-",
        "",
        "## Acceptance Criteria",
        *acceptance_lines,
        "",
        "## Test Expectations",
        *test_lines,
        "",
        "## Risks",
        *risk_lines,
        "",
    ]
    (wf / f"story-{num}.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

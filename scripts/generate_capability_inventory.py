#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def first_line_starting(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def detect_mode(text: str) -> tuple[str, str]:
    lowered = text.lower()
    if any(term in lowered for term in ["harness", "testing service", "compare", "polyglot", "benchmark", "load test"]):
        return (
            "feature-harness",
            "The seed language suggests a richer feature harness rather than a minimal tutorial sample.",
        )
    if any(term in lowered for term in ["sample", "tutorial", "guide", "example", "onboarding"]):
        return (
            "tutorial-sample",
            "The seed language suggests a pedagogical sample that should teach features progressively.",
        )
    if any(term in lowered for term in ["service", "api", "endpoint", "production"]):
        return (
            "product-service",
            "The seed language suggests a runtime-facing service where workflow stories should cover realistic execution paths.",
        )
    return (
        "general-delivery",
        "No strong sample or harness signal was detected, so the workflow should treat this as general staged delivery.",
    )


CAPABILITIES = [
    {
        "name": "Core Contract Usage",
        "keywords": ["contract", "derive", "derived", "decoder", "payload"],
        "modes": {"tutorial-sample": "required", "feature-harness": "required", "product-service": "required"},
        "why": "A sample should show the core shape of the contract model before layering on advanced behavior.",
        "stories": ["Bootstrap one minimal contract example", "Show raw input validation into a typed model"],
    },
    {
        "name": "Field Validation",
        "keywords": ["validation", "@email", "@nonempty", "@positive", "@min", "constraint"],
        "modes": {"tutorial-sample": "required", "feature-harness": "required", "product-service": "recommended"},
        "why": "Validation annotations and failure behavior are usually one of the first meaningful capabilities a developer expects to see.",
        "stories": ["Add one focused validation example", "Show multiple violations in a single failing payload"],
    },
    {
        "name": "Sanitization And Visibility",
        "keywords": ["sanitize", "@internal", "@masked", "@reserved", "public view", "private view"],
        "modes": {"tutorial-sample": "recommended", "feature-harness": "required", "product-service": "recommended"},
        "why": "Libraries in this space often distinguish stored/internal fields from public output, so samples should make that explicit.",
        "stories": ["Show how sensitive fields are removed or redacted", "Compare validated internal state to sanitized output"],
    },
    {
        "name": "Nested Structures",
        "keywords": ["nested", "address", "child", "embedded", "subobject", "decoder"],
        "modes": {"tutorial-sample": "recommended", "feature-harness": "required", "product-service": "required"},
        "why": "Real payloads are rarely flat. Nested structures prove the sample is useful beyond toy fields.",
        "stories": ["Add one nested contract with raw decoding", "Show validation across nested structures"],
    },
    {
        "name": "Lifecycle And Field Semantics",
        "keywords": ["immutable", "reserved", "internal", "masked", "readonly", "lifecycle"],
        "modes": {"tutorial-sample": "recommended", "feature-harness": "required", "product-service": "recommended"},
        "why": "Field-level semantics often separate a realistic sample from a basic tutorial.",
        "stories": ["Add immutable or reserved field examples", "Document which fields are persisted vs public"],
    },
    {
        "name": "Custom Validators",
        "keywords": ["validator", "business rule", "consistency", "totals", "inventory"],
        "modes": {"tutorial-sample": "optional", "feature-harness": "recommended", "product-service": "recommended"},
        "why": "Custom validators show where contract annotations stop and domain-specific rules begin.",
        "stories": ["Add one contract-level validator", "Show a failure path for a derived business rule"],
    },
    {
        "name": "Patch And Partial Validation",
        "keywords": ["patch", "partial", "draft", "update", "merge"],
        "modes": {"tutorial-sample": "optional", "feature-harness": "recommended", "product-service": "required"},
        "why": "If the target is a service or harness, patch and partial flows are often critical to realistic coverage.",
        "stories": ["Add a patch validation example", "Add a draft or partial validation path"],
    },
    {
        "name": "Schema And Introspection",
        "keywords": ["schema", "json schema", "introspection", "metadata"],
        "modes": {"tutorial-sample": "optional", "feature-harness": "recommended", "product-service": "optional"},
        "why": "Schema generation is a meaningful differentiator if the library supports introspection or downstream integration.",
        "stories": ["Add one schema generation example", "Document how schema output relates to the contract model"],
    },
    {
        "name": "Runtime Integration",
        "keywords": ["service", "api", "endpoint", "http", "controller", "spring"],
        "modes": {"tutorial-sample": "optional", "feature-harness": "recommended", "product-service": "required"},
        "why": "Some workflows need a true service boundary, not just isolated tests. This is where realistic execution enters the sample.",
        "stories": ["Wrap the contract flow in one runtime entry point", "Show how validated raw data moves through the service"],
    },
    {
        "name": "Developer Guidance",
        "keywords": ["guide", "readme", "docs", "onboarding", "explain"],
        "modes": {"tutorial-sample": "required", "feature-harness": "recommended", "product-service": "recommended"},
        "why": "Without explicit guidance, even a good sample can feel opaque.",
        "stories": ["Add a README that explains each capability slice", "Explain how to run and extend the sample"],
    },
]


def capability_status(capability: dict[str, object], mode: str, text: str) -> tuple[str, str]:
    lowered = text.lower()
    keywords = capability["keywords"]  # type: ignore[assignment]
    if any(keyword in lowered for keyword in keywords):
        return "required", "The design/context already mentions this capability explicitly."
    modes = capability["modes"]  # type: ignore[assignment]
    status = modes.get(mode, "optional")
    if status == "required":
        return status, f"This capability is typically essential in {mode} mode."
    if status == "recommended":
        return status, f"This capability is usually expected in {mode} mode even if not stated explicitly."
    return status, "This capability is useful but not necessarily needed in the first version."


def format_inventory(mode: str, rationale: str, text: str) -> str:
    lines = [
        "# Capability Inventory",
        "",
        "## Workflow Mode",
        "",
        f"- Mode: {mode}",
        f"- Rationale: {rationale}",
        "",
        "## Coverage Guidance",
        "",
        "- Use this file before story slicing to avoid converging too early on a thin sample.",
        "- Required capabilities should usually appear in the first story plan or in explicit deferred stories.",
        "- Recommended capabilities should be reflected in future stories unless intentionally deferred.",
        "- Optional capabilities can be left out if the sample is still coherent without them.",
        "",
        "## Capability Categories",
        "",
    ]

    for capability in CAPABILITIES:
        status, why_now = capability_status(capability, mode, text)
        lines.extend(
            [
                f"### {capability['name']}",
                f"- Status: {status}",
                f"- Why: {capability['why']}",
                f"- Why now: {why_now}",
                "- Story prompts:",
            ]
        )
        for prompt in capability["stories"]:  # type: ignore[index]
            lines.append(f"  - {prompt}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a workflow capability inventory from context and design seed.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wf = root / ".workflow" / args.slug
    wf.mkdir(parents=True, exist_ok=True)

    context = read_text(wf / "context.md")
    design_seed = read_text(wf / "design-seed.md")
    combined = "\n".join(part for part in [context, design_seed] if part.strip())
    mode, rationale = detect_mode(combined)

    inventory = format_inventory(mode, rationale, combined)
    (wf / "capabilities.md").write_text(inventory, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

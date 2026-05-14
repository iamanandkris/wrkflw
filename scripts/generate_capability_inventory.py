#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


GENERATED_MARKER = "<!-- generated-by: wrkflw capability inventory -->"
PLACEHOLDER_RATIONALE = "No capability inventory has been generated yet."


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def slug_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token}


def first_line_starting(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def detect_mode(text: str) -> tuple[str, str]:
    lowered = text.lower()
    if is_sql_server_mcp(text):
        return (
            "sql-server-mcp",
            "The seed language describes a read-oriented MCP server that exposes SQL Server capabilities to human or agent clients.",
        )
    if any(
        term in lowered
        for term in [
            "spring boot",
            "modular monolith",
            "rest endpoints",
            "api service",
            "workflow platform",
            "case management",
            "production",
        ]
    ):
        return (
            "product-service",
            "The seed language describes a runtime-facing backend platform with APIs, lifecycle rules, and operational behavior.",
        )
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


SQL_SERVER_MCP_CAPABILITIES = [
    {
        "name": "MCP Runtime And Stdio Transport",
        "keywords": ["mcp", "model context protocol", "stdio", "server", "tool"],
        "modes": {"sql-server-mcp": "required"},
        "why": "A usable v1 needs a working MCP process, transport lifecycle, tool registration, and predictable request/response behavior before database features can be exposed.",
        "stories": ["Create the TypeScript MCP stdio server skeleton", "Register the initial SQL Server tools with stable names and schemas"],
    },
    {
        "name": "SQL Server Connection Configuration",
        "keywords": ["sql server", "mssql", "connection", "connection string", "authentication", "encrypt", "trustservercertificate"],
        "modes": {"sql-server-mcp": "required"},
        "why": "The server must connect to SQL Server without hard-coding credentials and must surface configuration failures clearly for local and agentic setups.",
        "stories": ["Load SQL Server connection settings from environment or config", "Validate connection configuration before tools attempt database work"],
    },
    {
        "name": "Read-Only Query Execution",
        "keywords": ["read-only", "readonly", "select", "query", "execute", "row limit", "timeout"],
        "modes": {"sql-server-mcp": "required"},
        "why": "The approved v1 scope is read-only, so query execution needs an intentionally narrow surface that can answer questions without mutating data.",
        "stories": ["Execute parameterized read-only SELECT queries", "Apply timeout and row-limit controls to result-producing queries"],
    },
    {
        "name": "Schema Discovery And Introspection",
        "keywords": ["schema", "table", "column", "catalog", "metadata", "introspection", "describe"],
        "modes": {"sql-server-mcp": "required"},
        "why": "Agents need schema context before they can ask useful questions or construct safe SQL.",
        "stories": ["Expose database, schema, table, and column discovery tools", "Return compact metadata that agents can consume without excessive token cost"],
    },
    {
        "name": "Safety Guardrails And Policy Enforcement",
        "keywords": ["write", "admin", "ddl", "dml", "delete", "update", "insert", "drop", "guardrail", "policy"],
        "modes": {"sql-server-mcp": "required"},
        "why": "A database-facing MCP server needs explicit enforcement that v1 cannot perform writes or administrative operations.",
        "stories": ["Reject mutating or administrative SQL before execution", "Document the supported read-only command envelope and known exclusions"],
    },
    {
        "name": "Result Shaping And Error Reporting",
        "keywords": ["result", "rows", "json", "error", "diagnostic", "message", "format"],
        "modes": {"sql-server-mcp": "recommended"},
        "why": "Human and machine clients both need predictable result envelopes and errors that are specific enough to recover from.",
        "stories": ["Return stable JSON result envelopes for rows and metadata", "Map SQL Server and validation failures into clear MCP errors"],
    },
    {
        "name": "Observability And Operational Limits",
        "keywords": ["logging", "telemetry", "pool", "cancellation", "limit", "timeout", "observability"],
        "modes": {"sql-server-mcp": "recommended"},
        "why": "Database tools can create expensive work quickly, so v1 should expose enough logging and limits to diagnose failures without leaking sensitive data.",
        "stories": ["Add safe operational logging around tool calls and failures", "Centralize timeout, row-limit, and connection-pool defaults"],
    },
    {
        "name": "Agent Usability Documentation",
        "keywords": ["agent", "human", "docs", "readme", "examples", "client", "setup"],
        "modes": {"sql-server-mcp": "recommended"},
        "why": "The server is meant for agentic setups, so the first release needs clear install, configuration, and client usage guidance.",
        "stories": ["Document stdio client configuration and required environment variables", "Provide example prompts and tool usage patterns for safe database exploration"],
    },
]


SERVICE_CAPABILITIES = [
    {
        "name": "Contract Runtime Boundary",
        "keywords": ["concentric", "jvmcontract", "jvmpatch", "java integration boundary", "contract-first", "caseflow-contract-runtime"],
        "why": "A Java/Spring system using Scala-backed Concentric artifacts needs a dedicated boundary so lifecycle semantics stay centralized and interop does not leak across the codebase.",
        "stories": ["Create the contract runtime module and Java-friendly service interfaces", "Translate Concentric validation results into platform error shapes"],
    },
    {
        "name": "Case And Task Domain Model",
        "keywords": ["case", "task", "casetype", "queueassignment", "decisionrecord", "approvalstep"],
        "why": "The core domain types must be explicit before APIs, policies, and projections can evolve safely.",
        "stories": ["Define the core aggregates and persistence shape", "Document stage and task lifecycle semantics"],
    },
    {
        "name": "Lifecycle Transition Enforcement",
        "keywords": ["transition", "required fields", "immutable", "masked", "internal", "allowed transitions", "stage"],
        "why": "Lifecycle enforcement is the central behavior of the platform, not a peripheral validation detail.",
        "stories": ["Validate case progression through contract and policy checks", "Return structured failure reasons for blocked transitions"],
    },
    {
        "name": "Patch And Partial Mutation",
        "keywords": ["patch", "partial", "update", "merge"],
        "why": "Patch-based writes are necessary for audit deltas, partial UI updates, and controlled integration mutations.",
        "stories": ["Expose patch-based update flows for primary write APIs", "Preserve field-level lifecycle semantics during partial updates"],
    },
    {
        "name": "Approval And Decision Governance",
        "keywords": ["approval", "approve", "reject", "delegate", "override", "decision"],
        "why": "Approval steps and structured decisions are part of the operational contract, not a later add-on.",
        "stories": ["Model approval steps and decision records with explicit validation", "Enforce approval dependencies before sensitive actions succeed"],
    },
    {
        "name": "Evidence Intake And Secure Views",
        "keywords": ["evidence", "retention", "sensitivity", "malware", "signed url", "secure download"],
        "why": "Evidence handling combines contract validation, secure metadata exposure, and operational pipelines.",
        "stories": ["Define evidence metadata contracts and secure view filtering", "Separate binary-object handling from transactional state"],
    },
    {
        "name": "Queue, SLA, And Assignment Operations",
        "keywords": ["queue", "sla", "assignment", "escalation", "claim", "aging", "supervisor"],
        "why": "Operational throughput and breach handling are core product capabilities for case-working teams.",
        "stories": ["Represent assignment and SLA state explicitly in the domain", "Support queue queries and escalation scheduling hooks"],
    },
    {
        "name": "Audit Trail And Timeline Reconstruction",
        "keywords": ["audit", "timeline", "reconstruct", "delta", "immutable"],
        "why": "A regulated workflow platform must make every material change reconstructable and reviewable.",
        "stories": ["Persist immutable audit events for material changes", "Provide timeline reconstruction semantics from domain deltas"],
    },
    {
        "name": "API And Event Surface",
        "keywords": ["api", "endpoint", "rest", "event", "kafka", "outbox", "publisher"],
        "why": "The transactional domain needs explicit synchronous and asynchronous boundaries for integrations and UI clients.",
        "stories": ["Define the initial REST write/read surface", "Emit durable domain events after successful state changes"],
    },
    {
        "name": "Schema And UI Metadata",
        "keywords": ["schema introspection", "schema", "ui", "form", "process designers", "react", "metadata"],
        "why": "The admin UI and stage-specific forms depend on reliable schema metadata from the contract layer.",
        "stories": ["Expose contract-derived schema metadata for stage-aware forms", "Document how UI expectations stay aligned with contract updates"],
    },
]

SERVICE_CAPABILITY_WORKFLOW_HINTS = {
    "Contract Runtime Boundary": "contract-and-lifecycle-foundation",
    "Case And Task Domain Model": "contract-and-lifecycle-foundation",
    "Lifecycle Transition Enforcement": "core-case-and-task-orchestration",
    "Patch And Partial Mutation": "approvals-and-decision-governance",
    "Approval And Decision Governance": "approvals-and-decision-governance",
    "Evidence Intake And Secure Views": "evidence-intake-and-secure-storage",
    "Queue, SLA, And Assignment Operations": "queue-operations-and-sla-management",
    "Audit Trail And Timeline Reconstruction": "audit-search-and-timeline-reconstruction",
    "API And Event Surface": "admin-template-design-experience",
    "Schema And UI Metadata": "admin-template-design-experience",
}


GENERIC_CAPABILITY_NAMES = {str(capability["name"]) for capability in CAPABILITIES}


def is_sql_server_mcp(text: str) -> bool:
    lowered = text.lower()
    mcp_signals = ["mcp", "model context protocol"]
    sql_server_signals = ["sql server", "mssql", "ms sql", "t-sql", "tsql", "database"]
    return any(signal in lowered for signal in mcp_signals) and any(
        signal in lowered for signal in sql_server_signals
    )


def has_generic_inventory_categories(text: str) -> bool:
    headings = set(re.findall(r"^###\s+(.+?)\s*$", text, flags=re.MULTILINE))
    if len(headings & GENERIC_CAPABILITY_NAMES) >= 2:
        return True
    lowered = text.lower()
    return "core shape of the contract model" in lowered or "validation annotations" in lowered


def should_preserve_existing_inventory(path: Path, seed_text: str) -> bool:
    if not path.exists():
        return False
    existing = path.read_text(encoding="utf-8")
    if not existing.strip():
        return False
    if GENERATED_MARKER in existing:
        return False
    if PLACEHOLDER_RATIONALE in existing:
        return False
    if is_sql_server_mcp(seed_text) and has_generic_inventory_categories(existing):
        return False
    return True


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


def is_caseflow_service(text: str) -> bool:
    lowered = text.lower()
    signals = [
        "case management",
        "workflow platform",
        "approval",
        "evidence",
        "queue",
        "sla",
        "spring boot",
        "concentric",
    ]
    return sum(1 for signal in signals if signal in lowered) >= 4


def parse_initiative_index(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "Workflow slug" in stripped or set(stripped) <= {"|", "-", " "}:
            continue
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        if len(parts) < 2:
            continue
        rows[parts[0]] = parts[1]
    return rows


def capability_workflow_owner(capability_name: str, workflow_slug: str, workflow_statuses: dict[str, str]) -> str:
    hinted = SERVICE_CAPABILITY_WORKFLOW_HINTS.get(capability_name, "")
    if hinted in workflow_statuses or hinted == workflow_slug:
        return hinted
    capability_tokens = slug_tokens(capability_name)
    current_best = ""
    current_score = 0
    for candidate in workflow_statuses:
        overlap = capability_tokens & slug_tokens(candidate)
        score = len(overlap)
        if score > current_score:
            current_best = candidate
            current_score = score
    return current_best


def service_capability_status(
    capability: dict[str, object],
    workflow_slug: str,
    workflow_statuses: dict[str, str],
    text: str,
) -> tuple[str, str, str]:
    owner = capability_workflow_owner(str(capability["name"]), workflow_slug, workflow_statuses)
    lowered = text.lower()
    explicit = any(keyword in lowered for keyword in capability["keywords"])
    if owner and owner != workflow_slug:
        owner_status = workflow_statuses.get(owner, "").strip().lower()
        if owner_status == "done":
            return "satisfied by prior epic", owner, f"This capability is already delivered by the completed `{owner}` workflow."
        return "deferred to later epic", owner, f"This capability belongs to `{owner}` and should not be pulled into `{workflow_slug}` yet."
    if explicit:
        return "required", owner or workflow_slug, "The design/context already mentions this service capability explicitly for the current epic."
    return "recommended", owner or workflow_slug, "This capability is adjacent to the current epic and can be staged behind the first required slice."


def format_inventory(mode: str, rationale: str, text: str, workflow_slug: str, workflow_statuses: dict[str, str]) -> str:
    lines = [
        "# Capability Inventory",
        "",
        GENERATED_MARKER,
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

    capabilities = CAPABILITIES
    if mode == "sql-server-mcp":
        capabilities = SQL_SERVER_MCP_CAPABILITIES
    elif mode == "product-service" and is_caseflow_service(text):
        capabilities = SERVICE_CAPABILITIES

    for capability in capabilities:
        if capabilities is SERVICE_CAPABILITIES:
            status, owner, why_now = service_capability_status(capability, workflow_slug, workflow_statuses, text)
        else:
            status, why_now = capability_status(capability, mode, text)
            owner = workflow_slug
        lines.extend(
            [
                f"### {capability['name']}",
                f"- Status: {status}",
                f"- Owning workflow: {owner or workflow_slug}",
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
    parser.add_argument("--force", action="store_true", help="Overwrite an existing human-curated capability inventory.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wf = root / ".workflow" / args.slug
    wf.mkdir(parents=True, exist_ok=True)

    context = read_text(wf / "context.md")
    design_slice = read_text(wf / "design-slice.md")
    design_seed = read_text(wf / "design-seed.md")
    combined = "\n".join(part for part in [context, design_slice, design_seed] if part.strip())
    output_path = wf / "capabilities.md"
    if not args.force and should_preserve_existing_inventory(output_path, combined):
        return 0
    mode, rationale = detect_mode(combined)
    workflow_statuses = parse_initiative_index(root / ".workflow" / "initiative-index.md")
    inventory = format_inventory(mode, rationale, combined, args.slug, workflow_statuses)
    output_path.write_text(inventory, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

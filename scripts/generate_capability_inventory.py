#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from workflow_profile import (
    detect_planning_profile,
    is_browser_game,
    is_sql_server_mcp,
    profile_domain_pack_text,
    profile_domain_packs,
)


GENERATED_MARKER = "<!-- generated-by: wrkflw capability inventory -->"
PLACEHOLDER_RATIONALE = "No capability inventory has been generated yet."


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def slug_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token}


CAPABILITIES = [
    {
        "name": "Core Contract Usage",
        "keywords": ["contract", "derive", "derived", "decoder", "payload"],
        "why": "A sample should show the core shape of the contract model before layering on advanced behavior.",
        "stories": ["Bootstrap one minimal contract example", "Show raw input validation into a typed model"],
    },
    {
        "name": "Field Validation",
        "keywords": ["validation", "@email", "@nonempty", "@positive", "@min", "constraint"],
        "why": "Validation annotations and failure behavior are usually one of the first meaningful capabilities a developer expects to see.",
        "stories": ["Add one focused validation example", "Show multiple violations in a single failing payload"],
    },
    {
        "name": "Sanitization And Visibility",
        "keywords": ["sanitize", "@internal", "@masked", "@reserved", "public view", "private view"],
        "why": "Libraries in this space often distinguish stored/internal fields from public output, so samples should make that explicit.",
        "stories": ["Show how sensitive fields are removed or redacted", "Compare validated internal state to sanitized output"],
    },
    {
        "name": "Nested Structures",
        "keywords": ["nested", "address", "child", "embedded", "subobject", "decoder"],
        "why": "Real payloads are rarely flat. Nested structures prove the sample is useful beyond toy fields.",
        "stories": ["Add one nested contract with raw decoding", "Show validation across nested structures"],
    },
    {
        "name": "Lifecycle And Field Semantics",
        "keywords": ["immutable", "reserved", "internal", "masked", "readonly", "lifecycle"],
        "why": "Field-level semantics often separate a realistic sample from a basic tutorial.",
        "stories": ["Add immutable or reserved field examples", "Document which fields are persisted vs public"],
    },
    {
        "name": "Custom Validators",
        "keywords": ["validator", "business rule", "consistency", "totals", "inventory"],
        "why": "Custom validators show where contract annotations stop and domain-specific rules begin.",
        "stories": ["Add one contract-level validator", "Show a failure path for a derived business rule"],
    },
    {
        "name": "Patch And Partial Validation",
        "keywords": ["patch", "partial", "draft", "update", "merge"],
        "why": "If the target is a service or harness, patch and partial flows are often critical to realistic coverage.",
        "stories": ["Add a patch validation example", "Add a draft or partial validation path"],
    },
    {
        "name": "Schema And Introspection",
        "keywords": ["schema", "json schema", "introspection", "metadata"],
        "why": "Schema generation is a meaningful differentiator if the library supports introspection or downstream integration.",
        "stories": ["Add one schema generation example", "Document how schema output relates to the contract model"],
    },
    {
        "name": "Runtime Integration",
        "keywords": ["service", "api", "endpoint", "http", "controller", "spring"],
        "why": "Some workflows need a true service boundary, not just isolated tests. This is where realistic execution enters the sample.",
        "stories": ["Wrap the contract flow in one runtime entry point", "Show how validated raw data moves through the service"],
    },
    {
        "name": "Developer Guidance",
        "keywords": ["guide", "readme", "docs", "onboarding", "explain"],
        "why": "Without explicit guidance, even a good sample can feel opaque.",
        "stories": ["Add a README that explains each capability slice", "Explain how to run and extend the sample"],
    },
]


SQL_SERVER_MCP_CAPABILITIES = [
    {
        "name": "MCP Runtime And Stdio Transport",
        "keywords": ["mcp", "model context protocol", "stdio", "server", "tool"],
        "why": "A usable v1 needs a working MCP process, transport lifecycle, tool registration, and predictable request/response behavior before database features can be exposed.",
        "stories": ["Create the TypeScript MCP stdio server skeleton", "Register the initial SQL Server tools with stable names and schemas"],
    },
    {
        "name": "SQL Server Connection Configuration",
        "keywords": ["sql server", "mssql", "connection", "connection string", "authentication", "encrypt", "trustservercertificate"],
        "why": "The server must connect to SQL Server without hard-coding credentials and must surface configuration failures clearly for local and agentic setups.",
        "stories": ["Load SQL Server connection settings from environment or config", "Validate connection configuration before tools attempt database work"],
    },
    {
        "name": "Read-Only Query Execution",
        "keywords": ["read-only", "readonly", "select", "query", "execute", "row limit", "timeout"],
        "why": "The approved v1 scope is read-only, so query execution needs an intentionally narrow surface that can answer questions without mutating data.",
        "stories": ["Execute parameterized read-only SELECT queries", "Apply timeout and row-limit controls to result-producing queries"],
    },
    {
        "name": "Schema Discovery And Introspection",
        "keywords": ["schema", "table", "column", "catalog", "metadata", "introspection", "describe"],
        "why": "Agents need schema context before they can ask useful questions or construct safe SQL.",
        "stories": ["Expose database, schema, table, and column discovery tools", "Return compact metadata that agents can consume without excessive token cost"],
    },
    {
        "name": "Safety Guardrails And Policy Enforcement",
        "keywords": ["write", "admin", "ddl", "dml", "delete", "update", "insert", "drop", "guardrail", "policy"],
        "why": "A database-facing MCP server needs explicit enforcement that v1 cannot perform writes or administrative operations.",
        "stories": ["Reject mutating or administrative SQL before execution", "Document the supported read-only command envelope and known exclusions"],
    },
    {
        "name": "Result Shaping And Error Reporting",
        "keywords": ["result", "rows", "json", "error", "diagnostic", "message", "format"],
        "why": "Human and machine clients both need predictable result envelopes and errors that are specific enough to recover from.",
        "stories": ["Return stable JSON result envelopes for rows and metadata", "Map SQL Server and validation failures into clear MCP errors"],
    },
    {
        "name": "Observability And Operational Limits",
        "keywords": ["logging", "telemetry", "pool", "cancellation", "limit", "timeout", "observability"],
        "why": "Database tools can create expensive work quickly, so v1 should expose enough logging and limits to diagnose failures without leaking sensitive data.",
        "stories": ["Add safe operational logging around tool calls and failures", "Centralize timeout, row-limit, and connection-pool defaults"],
    },
    {
        "name": "Agent Usability Documentation",
        "keywords": ["agent", "human", "docs", "readme", "examples", "client", "setup"],
        "why": "The server is meant for agentic setups, so the first release needs clear install, configuration, and client usage guidance.",
        "stories": ["Document stdio client configuration and required environment variables", "Provide example prompts and tool usage patterns for safe database exploration"],
    },
]


GAME_CAPABILITIES = [
    {
        "name": "Board Rendering And Layout",
        "keywords": ["board", "grid", "3x3", "cell", "screen", "layout"],
        "why": "A playable browser game needs a visible, stable play surface before rules and interactions can be verified.",
        "stories": ["Render the game board with stable cell sizing", "Show empty, occupied, and completed board states clearly"],
    },
    {
        "name": "Turn Management",
        "keywords": ["turn", "alternate", "player", "x", "o"],
        "why": "Turn order is part of the core game contract and must be explicit for human players and tests.",
        "stories": ["Alternate X and O after valid moves", "Show the current player before each move"],
    },
    {
        "name": "Move Validation",
        "keywords": ["occupied", "invalid", "prevent", "move", "cell"],
        "why": "The game must reject invalid moves so state cannot become impossible or ambiguous.",
        "stories": ["Prevent moves into occupied cells", "Keep turn state unchanged after invalid moves"],
    },
    {
        "name": "Win And Draw Detection",
        "keywords": ["win", "winner", "row", "column", "diagonal", "draw", "full board"],
        "why": "Outcome detection is the main rule boundary for a complete tic-tac-toe style game.",
        "stories": ["Detect row, column, and diagonal wins", "Detect a draw when the board fills without a winner"],
    },
    {
        "name": "Reset And Replay Flow",
        "keywords": ["reset", "restart", "replay", "new game"],
        "why": "A finished or mistaken game needs a clear way back to a fresh playable state.",
        "stories": ["Add a reset control that clears board state", "Restore the initial player and status message on reset"],
    },
    {
        "name": "Browser Interaction And Accessibility",
        "keywords": ["keyboard", "accessible", "aria", "focus", "button", "status"],
        "why": "A browser game should be operable and understandable through standard controls, not only mouse clicks.",
        "stories": ["Make board cells keyboard-operable controls", "Expose current status and outcomes in accessible text"],
    },
    {
        "name": "Static App Packaging And Documentation",
        "keywords": ["index.html", "html", "css", "javascript", "readme", "browser", "static"],
        "why": "The output should be easy to run locally and inspect without hidden build or backend assumptions.",
        "stories": ["Create the static browser files needed to run the game", "Document how to open, play, and validate the game"],
    },
]


GENERAL_DELIVERY_CAPABILITIES = [
    {
        "name": "Scope And Workflow Boundaries",
        "keywords": ["scope", "goal", "non-goal", "constraint", "boundary"],
        "why": "When no specialized domain pack dominates, the workflow still needs clear boundaries before story slicing.",
        "stories": ["Clarify the first useful delivery slice", "Record explicit non-goals and constraints"],
    },
    {
        "name": "Core User Workflow",
        "keywords": ["user", "workflow", "flow", "journey", "use case"],
        "why": "Most work needs at least one concrete path that proves the delivered change is useful.",
        "stories": ["Implement the primary user or operator path", "Show the expected happy path end to end"],
    },
    {
        "name": "Validation And Error Handling",
        "keywords": ["validation", "error", "failure", "invalid", "edge case"],
        "why": "A coherent slice should define how invalid input or expected failures are handled.",
        "stories": ["Add validation for the main input boundary", "Document or test the main failure path"],
    },
    {
        "name": "Testing And Verification",
        "keywords": ["test", "verify", "validation", "acceptance", "regression"],
        "why": "The workflow needs a visible proof point before the implementation can be reviewed safely.",
        "stories": ["Add focused acceptance or regression tests", "Document manual verification steps when automation is not practical"],
    },
    {
        "name": "Documentation And Run Guidance",
        "keywords": ["readme", "docs", "run", "setup", "guide"],
        "why": "Future agents and humans need enough run context to continue the work without re-discovering basics.",
        "stories": ["Document setup and run commands", "Capture known limitations and follow-up work"],
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
    if (is_sql_server_mcp(seed_text) or is_browser_game(seed_text)) and has_generic_inventory_categories(existing):
        return False
    return True


def capability_status(capability: dict[str, object], text: str) -> tuple[str, str]:
    lowered = text.lower()
    keywords = capability["keywords"]  # type: ignore[assignment]
    if any(keyword in lowered for keyword in keywords):
        return "required", "The design/context already mentions this capability explicitly."
    status = str(capability.get("profile_status", "optional"))
    driver = str(capability.get("profile_driver", "the planning profile"))
    if status == "required":
        return status, f"This capability is essential for {driver}."
    if status == "recommended":
        return status, f"This capability is usually expected for {driver} even if not stated explicitly."
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


def capability_with_profile_driver(
    capability: dict[str, object],
    status: str,
    driver: str,
) -> dict[str, object]:
    enriched = dict(capability)
    enriched["profile_status"] = status
    enriched["profile_driver"] = driver
    return enriched


def add_profile_capabilities(
    selected: list[dict[str, object]],
    capabilities: list[dict[str, object]],
    statuses: dict[str, str],
    default_status: str,
    driver: str,
) -> None:
    existing = {str(capability["name"]) for capability in selected}
    for capability in capabilities:
        name = str(capability["name"])
        if name in existing:
            continue
        selected.append(
            capability_with_profile_driver(
                capability,
                statuses.get(name, default_status),
                driver,
            )
        )
        existing.add(name)


def contract_capability_statuses(delivery_kind: str) -> dict[str, str]:
    if delivery_kind == "harness":
        return {
            "Core Contract Usage": "required",
            "Field Validation": "required",
            "Sanitization And Visibility": "required",
            "Nested Structures": "required",
            "Lifecycle And Field Semantics": "required",
            "Custom Validators": "recommended",
            "Patch And Partial Validation": "recommended",
            "Schema And Introspection": "recommended",
            "Runtime Integration": "recommended",
            "Developer Guidance": "recommended",
        }
    if delivery_kind == "sample":
        return {
            "Core Contract Usage": "required",
            "Field Validation": "required",
            "Developer Guidance": "required",
            "Sanitization And Visibility": "recommended",
            "Nested Structures": "recommended",
            "Lifecycle And Field Semantics": "recommended",
        }
    return {
        "Core Contract Usage": "required",
        "Field Validation": "required",
        "Nested Structures": "recommended",
        "Lifecycle And Field Semantics": "recommended",
        "Schema And Introspection": "recommended",
        "Developer Guidance": "recommended",
    }


def capabilities_for_profile(profile: dict[str, object], text: str) -> list[dict[str, object]]:
    delivery_kind = str(profile.get("delivery_kind", "general"))
    runtime_surface = str(profile.get("runtime_surface", "unspecified"))
    assurance_level = str(profile.get("assurance_level", "normal"))
    workflow_strategy = str(profile.get("workflow_strategy", "simple"))
    domain_packs = set(profile_domain_packs(profile))
    selected: list[dict[str, object]] = []

    if runtime_surface == "mcp-server" and "database" in domain_packs:
        add_profile_capabilities(
            selected,
            SQL_SERVER_MCP_CAPABILITIES,
            {
                "MCP Runtime And Stdio Transport": "required",
                "SQL Server Connection Configuration": "required",
                "Read-Only Query Execution": "required",
                "Schema Discovery And Introspection": "required",
                "Safety Guardrails And Policy Enforcement": "required",
                "Result Shaping And Error Reporting": "recommended",
                "Observability And Operational Limits": "recommended",
                "Agent Usability Documentation": "recommended",
            },
            "recommended",
            "runtime surface `mcp-server` with the `database` domain pack",
        )

    if runtime_surface == "frontend" and "game-rules" in domain_packs:
        add_profile_capabilities(
            selected,
            GAME_CAPABILITIES,
            {
                "Board Rendering And Layout": "required",
                "Turn Management": "required",
                "Move Validation": "required",
                "Win And Draw Detection": "required",
                "Reset And Replay Flow": "required",
                "Browser Interaction And Accessibility": "recommended",
                "Static App Packaging And Documentation": "required",
            },
            "recommended",
            "runtime surface `frontend` with the `game-rules` domain pack",
        )

    if "workflow-governance" in domain_packs or (
        runtime_surface == "backend-api" and is_caseflow_service(text)
    ):
        add_profile_capabilities(
            selected,
            SERVICE_CAPABILITIES,
            {},
            "recommended",
            "workflow-governance domain behavior",
        )

    if "contract-model" in domain_packs or delivery_kind in {"sample", "harness"}:
        add_profile_capabilities(
            selected,
            CAPABILITIES,
            contract_capability_statuses(delivery_kind),
            "optional",
            f"delivery kind `{delivery_kind}` with contract-model capability needs",
        )

    if not selected:
        add_profile_capabilities(
            selected,
            GENERAL_DELIVERY_CAPABILITIES,
            {
                "Scope And Workflow Boundaries": "required",
                "Core User Workflow": "required",
                "Validation And Error Handling": "recommended",
                "Testing And Verification": "recommended",
                "Documentation And Run Guidance": "recommended",
            },
            "recommended",
            f"delivery kind `{delivery_kind}`, runtime surface `{runtime_surface}`, assurance `{assurance_level}`, strategy `{workflow_strategy}`",
        )

    return selected


def format_inventory(
    mode: str,
    rationale: str,
    text: str,
    workflow_slug: str,
    workflow_statuses: dict[str, str],
    profile: dict[str, object] | None = None,
) -> str:
    profile = profile or detect_planning_profile(text)
    lines = [
        "# Capability Inventory",
        "",
        GENERATED_MARKER,
        "",
        "## Compatibility Workflow Mode",
        "",
        f"- Mode: {mode}",
        f"- Rationale: {rationale}",
        "",
        "## Planning Profile",
        "",
        f"- Delivery kind: {profile.get('delivery_kind', 'general')}",
        f"- Runtime surface: {profile.get('runtime_surface', 'unspecified')}",
        f"- Domain packs: {profile_domain_pack_text(profile)}",
        f"- Assurance level: {profile.get('assurance_level', 'normal')}",
        f"- Workflow strategy: {profile.get('workflow_strategy', 'simple')}",
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

    capabilities = capabilities_for_profile(profile, text)

    for capability in capabilities:
        if str(capability["name"]) in {str(item["name"]) for item in SERVICE_CAPABILITIES}:
            status, owner, why_now = service_capability_status(capability, workflow_slug, workflow_statuses, text)
        else:
            status, why_now = capability_status(capability, text)
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
    profile = detect_planning_profile(combined)
    mode = str(profile["mode"])
    rationale = str(profile["rationale"])
    workflow_statuses = parse_initiative_index(root / ".workflow" / "initiative-index.md")
    inventory = format_inventory(mode, rationale, combined, args.slug, workflow_statuses, profile)
    output_path.write_text(inventory, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

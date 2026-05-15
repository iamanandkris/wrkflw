from __future__ import annotations

import re


DEFAULT_PROFILE: dict[str, object] = {
    "mode": "general-delivery",
    "rationale": "No specialized legacy mode matched, so the workflow should treat this as general staged delivery.",
    "delivery_kind": "general",
    "runtime_surface": "unspecified",
    "domain_packs": ["general"],
    "assurance_level": "normal",
    "workflow_strategy": "simple",
}


PROFILE_LINE_KEYS = {
    "Mode": "mode",
    "Rationale": "rationale",
    "Delivery kind": "delivery_kind",
    "Runtime surface": "runtime_surface",
    "Domain packs": "domain_packs",
    "Assurance level": "assurance_level",
    "Workflow strategy": "workflow_strategy",
}


def contains_any(lowered: str, terms: list[str]) -> bool:
    for term in terms:
        if re.fullmatch(r"[a-z0-9]+", term):
            if re.search(rf"\b{re.escape(term)}\b", lowered):
                return True
        elif term in lowered:
            return True
    return False


def add_pack(packs: list[str], pack: str) -> None:
    if pack not in packs:
        packs.append(pack)


def is_sql_server_mcp(text: str) -> bool:
    lowered = text.lower()
    mcp_signals = ["mcp", "model context protocol"]
    sql_server_signals = ["sql server", "mssql", "ms sql", "t-sql", "tsql", "database"]
    return any(signal in lowered for signal in mcp_signals) and any(
        signal in lowered for signal in sql_server_signals
    )


def is_browser_game(text: str) -> bool:
    lowered = text.lower()
    if any(signal in lowered for signal in ["tic-tac-toe", "tic tac toe", "tictactoe"]):
        return True
    game_signals = ["game", "board", "player", "turn", "move", "win", "draw", "cell", "reset"]
    browser_signals = ["browser", "index.html", "html", "css", "javascript", "static", "ui"]
    return sum(1 for signal in game_signals if signal in lowered) >= 3 and any(
        signal in lowered for signal in browser_signals
    )


def detect_planning_profile(text: str) -> dict[str, object]:
    lowered = text.lower()
    sql_mcp = is_sql_server_mcp(text)
    browser_game = is_browser_game(text)
    harness = contains_any(lowered, ["harness", "testing service", "compare", "polyglot", "benchmark", "load test"])
    tutorial = contains_any(lowered, ["sample", "tutorial", "guide", "example", "onboarding"])
    backend_service = contains_any(
        lowered,
        ["spring boot", "modular monolith", "rest endpoints", "api service", "service", "api", "endpoint"],
    )
    cli_tool = contains_any(lowered, ["cli", "command line", "terminal command", "developer tool"])
    migration = contains_any(lowered, ["migration", "schema change", "data backfill", "database migration"])
    research = contains_any(lowered, ["research", "spike", "explore", "prototype", "proof of concept", "poc"])
    maintenance = contains_any(lowered, ["bugfix", "bug fix", "refactor", "upgrade", "dependency update", "maintenance"])
    frontend = browser_game or contains_any(
        lowered,
        ["frontend", "browser", "index.html", "html", "css", "javascript", "react", "ui", "web app"],
    )
    database = sql_mcp or contains_any(lowered, ["database", "sql", "postgres", "mysql", "mssql", "sql server", "query"])
    infra = contains_any(lowered, ["terraform", "kubernetes", "helm", "cloud", "infrastructure", "deployment"])
    batch = contains_any(lowered, ["batch", "etl", "pipeline", "scheduled job", "worker"])

    if harness:
        delivery_kind = "harness"
    elif sql_mcp or cli_tool:
        delivery_kind = "tool"
    elif migration:
        delivery_kind = "migration"
    elif research:
        delivery_kind = "research"
    elif maintenance:
        delivery_kind = "maintenance"
    elif browser_game or backend_service or frontend:
        delivery_kind = "product"
    elif tutorial:
        delivery_kind = "sample"
    else:
        delivery_kind = "general"

    if sql_mcp:
        runtime_surface = "mcp-server"
    elif frontend:
        runtime_surface = "frontend"
    elif backend_service:
        runtime_surface = "backend-api"
    elif cli_tool:
        runtime_surface = "cli"
    elif migration or database:
        runtime_surface = "database"
    elif infra:
        runtime_surface = "infra"
    elif batch:
        runtime_surface = "batch-job"
    else:
        runtime_surface = "unspecified"

    domain_packs: list[str] = []
    if database:
        add_pack(domain_packs, "database")
    if sql_mcp or contains_any(lowered, ["mcp", "agent", "agentic", "ai tool", "model context protocol"]):
        add_pack(domain_packs, "ai-agent")
    if browser_game:
        add_pack(domain_packs, "game-rules")
    if frontend:
        add_pack(domain_packs, "ui-state")
    if contains_any(lowered, ["keyboard", "accessible", "aria", "screen reader", "focus"]):
        add_pack(domain_packs, "accessibility")
    if contains_any(lowered, ["contract", "field validation", "contract validation", "schema", "decoder", "payload"]):
        add_pack(domain_packs, "contract-model")
    if contains_any(lowered, ["auth", "permission", "policy", "guardrail", "redaction", "secret", "security"]):
        add_pack(domain_packs, "security")
    if contains_any(lowered, ["audit", "compliance", "retention", "pii", "regulated", "sox", "hipaa"]):
        add_pack(domain_packs, "governance")
    if contains_any(lowered, ["observability", "logging", "telemetry", "metrics", "tracing"]):
        add_pack(domain_packs, "observability")
    if contains_any(lowered, ["readme", "docs", "documentation", "operator guide", "runbook"]):
        add_pack(domain_packs, "documentation")
    if contains_any(lowered, ["approval", "case management", "workflow platform", "sla", "queue", "evidence"]):
        add_pack(domain_packs, "workflow-governance")

    if contains_any(lowered, ["regulated", "compliance", "pii", "hipaa", "sox", "retention"]):
        assurance_level = "regulated"
    elif sql_mcp or "security" in domain_packs or contains_any(lowered, ["write", "admin", "payment", "production"]):
        assurance_level = "high-risk"
    elif research:
        assurance_level = "experimental"
    else:
        assurance_level = "normal"

    if assurance_level in {"high-risk", "regulated"} or runtime_surface in {"mcp-server", "database", "infra"}:
        workflow_strategy = "spec-driven"
    elif research or assurance_level == "experimental":
        workflow_strategy = "spike-first"
    elif contains_any(lowered, ["parallel", "multiple services", "team-run", "parallel-team"]):
        workflow_strategy = "parallel-team"
    else:
        workflow_strategy = "simple"

    mode, rationale = legacy_mode_from_profile(text, delivery_kind, runtime_surface, domain_packs)
    return {
        "mode": mode,
        "rationale": rationale,
        "delivery_kind": delivery_kind,
        "runtime_surface": runtime_surface,
        "domain_packs": domain_packs or ["general"],
        "assurance_level": assurance_level,
        "workflow_strategy": workflow_strategy,
    }


def legacy_mode_from_profile(
    text: str,
    delivery_kind: str,
    runtime_surface: str,
    domain_packs: list[str],
) -> tuple[str, str]:
    lowered = text.lower()
    if runtime_surface == "mcp-server" and "database" in domain_packs:
        return (
            "sql-server-mcp",
            "The planning profile describes an MCP-facing database tool for human or agent clients.",
        )
    if runtime_surface == "frontend" and "game-rules" in domain_packs:
        return (
            "browser-game",
            "The planning profile describes a browser-playable game with UI state, player interaction, and rule enforcement.",
        )
    if delivery_kind == "harness":
        return (
            "feature-harness",
            "The planning profile emphasizes broad capability coverage and realistic feature comparison.",
        )
    if delivery_kind == "sample":
        return (
            "tutorial-sample",
            "The planning profile emphasizes pedagogy and progressive learning.",
        )
    if runtime_surface == "backend-api" or contains_any(
        lowered,
        ["spring boot", "modular monolith", "workflow platform", "case management", "production"],
    ):
        return (
            "product-service",
            "The planning profile describes a runtime-facing backend platform with APIs, lifecycle rules, and operational behavior.",
        )
    return (
        "general-delivery",
        "No specialized legacy mode matched, so the workflow should treat this as general staged delivery.",
    )


def detect_mode(text: str) -> tuple[str, str]:
    profile = detect_planning_profile(text)
    return str(profile["mode"]), str(profile["rationale"])


def parse_planning_profile(text: str) -> dict[str, object]:
    profile = dict(DEFAULT_PROFILE)
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, _, value = stripped[2:].partition(":")
        field = PROFILE_LINE_KEYS.get(key.strip())
        if not field:
            continue
        value = value.strip()
        if field == "domain_packs":
            packs = [part.strip() for part in value.split(",") if part.strip()]
            profile[field] = packs or ["general"]
        else:
            profile[field] = value
    return profile


def profile_mode(profile: dict[str, object]) -> str:
    return str(profile.get("mode") or DEFAULT_PROFILE["mode"])


def profile_domain_packs(profile: dict[str, object]) -> list[str]:
    packs = profile.get("domain_packs", ["general"])
    if isinstance(packs, list):
        return [str(pack) for pack in packs if str(pack).strip()] or ["general"]
    return [part.strip() for part in str(packs).split(",") if part.strip()] or ["general"]


def profile_domain_pack_text(profile: dict[str, object]) -> str:
    return ", ".join(profile_domain_packs(profile))


def profile_review_lines(profile: dict[str, object]) -> list[str]:
    return [
        f"- Delivery kind: {profile.get('delivery_kind', 'general')}",
        f"- Runtime surface: {profile.get('runtime_surface', 'unspecified')}",
        f"- Domain packs: {profile_domain_pack_text(profile)}",
        f"- Assurance level: {profile.get('assurance_level', 'normal')}",
        f"- Workflow strategy: {profile.get('workflow_strategy', 'simple')}",
    ]


def profile_note_lines(profile: dict[str, object]) -> list[str]:
    return [
        f"Delivery: {profile.get('delivery_kind', 'general')}",
        f"Runtime: {profile.get('runtime_surface', 'unspecified')}",
        f"Domains: {profile_domain_pack_text(profile)}",
        f"Assurance: {profile.get('assurance_level', 'normal')}",
        f"Strategy: {profile.get('workflow_strategy', 'simple')}",
    ]


def profile_story_selection_allows_recommended(profile: dict[str, object]) -> bool:
    strategy = str(profile.get("workflow_strategy", "simple"))
    assurance = str(profile.get("assurance_level", "normal"))
    runtime = str(profile.get("runtime_surface", "unspecified"))
    delivery = str(profile.get("delivery_kind", "general"))
    return (
        strategy in {"spec-driven", "parallel-team"}
        or assurance in {"high-risk", "regulated"}
        or runtime in {"mcp-server", "backend-api", "frontend"}
        or delivery in {"product", "tool", "harness", "sample"}
    )

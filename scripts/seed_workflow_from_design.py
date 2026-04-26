#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


LINK_FIELDS = ["Tracker", "Design seed", "OpenSpec change", "PRs", "Docs"]
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "your",
    "their",
    "then",
    "than",
    "when",
    "what",
    "does",
    "have",
    "has",
    "will",
    "been",
    "are",
    "was",
    "were",
    "use",
    "uses",
    "using",
    "user",
    "users",
    "system",
    "service",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def write_kv_list(path: Path, title: str, fields: list[str], values: dict[str, str]) -> None:
    lines = [f"# {title}", ""]
    for field in fields:
        lines.append(f"- {field}: {values.get(field, '').strip()}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_context(path: Path, problem: str, goal: str, non_goals: str, constraints: str, design_seed: str, excerpt: str) -> None:
    lines = [
        "# Context",
        "",
        f"- Problem: {problem}",
        f"- Goal: {goal}",
        f"- Non-goals: {non_goals}",
        f"- Constraints: {constraints}",
        "",
        "## Design Seed",
        "",
        f"- Path: {design_seed}",
        "",
        "## Design Excerpt",
        "",
        excerpt.strip() or "-",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def normalize_heading(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "workflow-slice"


def parse_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "preamble"
    sections[current] = []
    for raw_line in text.splitlines():
        if raw_line.startswith("#"):
            heading = normalize_heading(raw_line.lstrip("#").strip())
            current = heading or current
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(raw_line.rstrip())
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def extract_labeled_block(text: str, labels: list[str]) -> str:
    normalized_labels = {normalize_heading(label) for label in labels}
    lines = text.splitlines()
    capture = False
    captured: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()
        bold_match = re.match(r"^\*\*(.+?)\*\*:?$", stripped)
        plain_match = re.match(r"^([A-Za-z0-9 /&()-]+):\s*$", stripped)
        heading_name = ""
        if bold_match:
            heading_name = normalize_heading(bold_match.group(1))
        elif plain_match:
            heading_name = normalize_heading(plain_match.group(1))

        if heading_name:
            if capture:
                break
            if heading_name in normalized_labels:
                capture = True
                continue

        if capture:
            if stripped.startswith("---"):
                break
            captured.append(raw_line.rstrip())

    return "\n".join(captured).strip()


def extract_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            bullets.append(line[2:].strip())
            continue
        numbered = re.match(r"^\d+\.\s+(.*)$", line)
        if numbered:
            bullets.append(numbered.group(1).strip())
    return bullets


def dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def first_non_empty_paragraph(text: str) -> str:
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text) if chunk.strip()]
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith("#") for line in lines):
            continue
        return chunk
    return chunks[0] if chunks else ""


def pick_section(sections: dict[str, str], names: list[str]) -> str:
    for name in names:
        for key, value in sections.items():
            if name in key and value.strip():
                return first_non_empty_paragraph(value)
    return ""


def pick_bullets(sections: dict[str, str], names: list[str]) -> list[str]:
    for name in names:
        for key, value in sections.items():
            if name in key and value.strip():
                bullets = extract_bullets(value)
                if bullets:
                    return bullets
    return []


def title_from_phrase(text: str) -> str:
    words = [word for word in re.findall(r"[A-Za-z0-9]+", text) if word]
    if not words:
        return "Workflow Slice"
    return " ".join(word.capitalize() if word.lower() not in {"api", "ui", "rbac", "abac"} else word.upper() for word in words[:6])


def summarize_paragraph(text: str, fallback: str = "-") -> str:
    paragraph = first_non_empty_paragraph(text)
    if not paragraph:
        return fallback
    return paragraph.replace("\n", " ").strip()


def infer_capability_clusters(sections: dict[str, str]) -> list[dict[str, str]]:
    feature_bullets = pick_bullets(sections, ["what it does", "capabilities", "features"])
    if not feature_bullets:
        feature_bullets = pick_bullets(sections, ["app overview", "overview"])

    grouped: dict[str, list[str]] = {
        "authorization-core": [],
        "entity-modeling": [],
        "admin-and-experience": [],
        "audit-and-compliance": [],
        "runtime-and-operations": [],
    }

    for bullet in feature_bullets:
        lower = bullet.lower()
        if any(token in lower for token in ["role", "grant", "permission", "authorize", "abac", "rbac", "decision", "inherit"]):
            grouped["authorization-core"].append(bullet)
        elif any(token in lower for token in ["entity", "schema", "parent-child", "hierarch", "attribute"]):
            grouped["entity-modeling"].append(bullet)
        elif any(token in lower for token in ["ui", "admin", "assistant", "conversation", "model complex"]):
            grouped["admin-and-experience"].append(bullet)
        elif any(token in lower for token in ["audit", "encrypted", "compliance", "access attempts"]):
            grouped["audit-and-compliance"].append(bullet)
        elif any(token in lower for token in ["rate", "quota", "cache", "redis", "kubernetes", "scale", "pub/sub", "consumption"]):
            grouped["runtime-and-operations"].append(bullet)
        else:
            grouped["authorization-core"].append(bullet)

    labels = {
        "authorization-core": "Authorization Core",
        "entity-modeling": "Entity Modeling",
        "admin-and-experience": "Admin Experience",
        "audit-and-compliance": "Audit And Compliance",
        "runtime-and-operations": "Runtime And Operations",
    }

    clusters: list[dict[str, str]] = []
    for key, items in grouped.items():
        if not items:
            continue
        summary = items[0]
        if len(items) > 1:
            summary = f"{items[0]} Additional scope includes: " + "; ".join(items[1:3])
        clusters.append(
            {
                "slug": key,
                "title": labels[key],
                "summary": summary,
                "details": "\n".join(f"- {item}" for item in items),
            }
        )

    if clusters:
        return clusters

    fallback_sections: list[dict[str, str]] = []
    for key, value in sections.items():
        if key == "preamble" or not value.strip():
            continue
        fallback_sections.append(
            {
                "slug": slugify(key),
                "title": title_from_phrase(key),
                "summary": summarize_paragraph(value),
                "details": "\n".join(f"- {bullet}" for bullet in extract_bullets(value)[:4]) or f"- {summarize_paragraph(value)}",
            }
        )
    return fallback_sections[:5]


def extract_actor_lines(sections: dict[str, str]) -> list[str]:
    actors = pick_bullets(sections, ["who uses it", "actors", "users"])
    if actors:
        return dedupe(actors)
    return []


def extract_key_decisions(sections: dict[str, str]) -> list[str]:
    decisions = pick_bullets(sections, ["key architectural decisions", "architectural decisions", "why these choices", "must follow patterns"])
    if decisions:
        return dedupe(decisions)
    return []


def extract_problem(text: str, sections: dict[str, str], excerpt: str) -> str:
    overview = pick_section(sections, ["app overview", "overview"])
    if overview:
        return overview
    problem = pick_section(sections, ["problem", "background", "context"])
    if problem:
        return problem
    return excerpt


def extract_goal(text: str, sections: dict[str, str]) -> str:
    explicit = pick_section(sections, ["goal", "objective", "outcome"])
    if explicit:
        return explicit
    what_it_does = extract_labeled_block(text, ["What It Does"])
    if what_it_does:
        bullets = extract_bullets(what_it_does)
        if bullets:
            return bullets[0]
    return "Use the normalized design slice to derive the first workflow-ready epic."


def extract_non_goals(text: str, sections: dict[str, str]) -> str:
    explicit = pick_section(sections, ["non goal", "out of scope"])
    return explicit or "-"


def extract_constraints(text: str, sections: dict[str, str]) -> str:
    explicit = pick_section(sections, ["compatibility caveats", "constraint", "dependency", "dependencies", "risk", "assumption"])
    if explicit:
        return explicit
    return "-"


def render_normalized_design(
    source_path: Path,
    problem: str,
    goal: str,
    non_goals: str,
    constraints: str,
    actors: list[str],
    decisions: list[str],
    clusters: list[dict[str, str]],
) -> str:
    lines = [
        "# Normalized Design",
        "",
        f"- Source: {source_path}",
        "- Purpose: Workflow-ready normalized view derived from a broader raw design document.",
        "",
        "## Problem",
        "",
        problem or "-",
        "",
        "## Goal",
        "",
        goal or "-",
        "",
        "## Non-goals",
        "",
        non_goals or "-",
        "",
        "## Constraints",
        "",
        constraints or "-",
        "",
        "## Actors",
        "",
    ]
    if actors:
        lines.extend(f"- {actor}" for actor in actors)
    else:
        lines.append("- No explicit actor list was detected in the raw design.")
    lines.extend(["", "## Capability Clusters", ""])
    for cluster in clusters:
        lines.extend(
            [
                f"### {cluster['title']}",
                "",
                f"- Epic slug: {cluster['slug']}",
                f"- Summary: {cluster['summary']}",
                cluster["details"],
                "",
            ]
        )
    lines.extend(["## Architectural Notes", ""])
    if decisions:
        lines.extend(f"- {decision}" for decision in decisions[:10])
    else:
        lines.append("- No dedicated architectural decision bullets were detected.")
    lines.extend([""])
    return "\n".join(lines)


def render_epic_candidates(source_path: Path, clusters: list[dict[str, str]]) -> str:
    lines = [
        "# Epic Candidates",
        "",
        f"- Source: {source_path}",
        "- Purpose: Candidate workflow splits inferred from the normalized design.",
        "",
    ]
    for index, cluster in enumerate(clusters, start=1):
        lines.extend(
            [
                f"## Epic {index}: {cluster['title']}",
                "",
                f"- Slug: {cluster['slug']}",
                f"- Summary: {cluster['summary']}",
                "- Workflow scope:",
                cluster["details"],
                "",
            ]
        )
    return "\n".join(lines)


def slug_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2 and token not in STOPWORDS}


def select_epic_for_slug(slug: str, clusters: list[dict[str, str]]) -> dict[str, str] | None:
    if not clusters:
        return None
    target = slug_tokens(slug)
    best: dict[str, str] | None = None
    best_score = -1
    for cluster in clusters:
        tokens = slug_tokens(cluster["slug"] + " " + cluster["title"] + " " + cluster["summary"])
        score = len(target & tokens)
        if score > best_score:
            best = cluster
            best_score = score
    return best or clusters[0]


def render_design_slice(
    source_path: Path,
    normalized_path: Path,
    epic_candidates_path: Path,
    selected: dict[str, str] | None,
    problem: str,
    goal: str,
    constraints: str,
) -> str:
    if selected is None:
        return "\n".join(
            [
                "# Design Slice",
                "",
                f"- Raw source: {source_path}",
                f"- Normalized design: {normalized_path}",
                f"- Epic candidates: {epic_candidates_path}",
                "",
                "## Slice Summary",
                "",
                "- No epic-specific slice could be inferred. Use the normalized design as the initial workflow planning source.",
                "",
            ]
        )

    lines = [
        "# Design Slice",
        "",
        f"- Raw source: {source_path}",
        f"- Normalized design: {normalized_path}",
        f"- Epic candidates: {epic_candidates_path}",
        f"- Selected epic slug: {selected['slug']}",
        f"- Selected epic title: {selected['title']}",
        "",
        "## Slice Summary",
        "",
        selected["summary"],
        "",
        "## Workflow Framing",
        "",
        f"- Problem: {problem}",
        f"- Goal: {goal}",
        f"- Constraints: {constraints}",
        "",
        "## In-Scope Capabilities",
        "",
        selected["details"],
        "",
        "## Planning Note",
        "",
        "- Use this slice as the primary workflow planning input for this workflow slug.",
        "- Keep the raw design and normalized design as background context rather than treating the whole source document as one workflow.",
        "",
    ]
    return "\n".join(lines)


def detect_design_file(root: Path, explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = (root / path).resolve()
        return path if path.exists() else None

    candidates = [
        root / "design.md",
        root / "Design.md",
        root / "docs" / "design.md",
        root / "docs" / "Design.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed workflow context from a design.md style file.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--design-file", help="Explicit design file path to use as workflow seed")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wf = root / ".workflow" / args.slug
    wf.mkdir(parents=True, exist_ok=True)

    design_path = detect_design_file(root, args.design_file)
    if not design_path:
        return 0

    design_text = read_text(design_path)
    sections = parse_sections(design_text)
    excerpt = first_non_empty_paragraph(design_text)
    problem = extract_problem(design_text, sections, excerpt)
    goal = extract_goal(design_text, sections)
    non_goals = extract_non_goals(design_text, sections)
    constraints = extract_constraints(design_text, sections)

    actors = extract_actor_lines(sections)
    labeled_actors = extract_bullets(extract_labeled_block(design_text, ["Who Uses It"]))
    if labeled_actors:
        actors = dedupe(labeled_actors + actors)

    decisions = extract_key_decisions(sections)
    labeled_decisions = extract_bullets(extract_labeled_block(design_text, ["Key Architectural Decisions", "Why These Choices", "Compatibility Caveats", "Must-Follow Patterns"]))
    if labeled_decisions:
        decisions = dedupe(labeled_decisions + decisions)

    clusters = infer_capability_clusters(sections)
    labeled_features = extract_bullets(extract_labeled_block(design_text, ["What It Does"]))
    if labeled_features:
        feature_sections = {"what it does": "\n".join(f"- {bullet}" for bullet in labeled_features)}
        clusters = infer_capability_clusters(feature_sections)

    normalized_root = root / ".workflow" / "_normalized"
    normalized_root.mkdir(parents=True, exist_ok=True)
    normalized_design_path = normalized_root / "master-design.md"
    normalized_design_path.write_text(
        render_normalized_design(
            source_path=design_path,
            problem=problem,
            goal=goal,
            non_goals=non_goals,
            constraints=constraints,
            actors=actors,
            decisions=decisions,
            clusters=clusters,
        ),
        encoding="utf-8",
    )
    epic_candidates_path = normalized_root / "epic-candidates.md"
    epic_candidates_path.write_text(
        render_epic_candidates(design_path, clusters),
        encoding="utf-8",
    )
    selected_epic = select_epic_for_slug(args.slug, clusters)

    context_path = wf / "context.md"
    write_context(
        context_path,
        problem=problem,
        goal=goal,
        non_goals=non_goals,
        constraints=constraints,
        design_seed=str(normalized_design_path),
        excerpt=selected_epic["summary"] if selected_epic is not None else excerpt,
    )

    seed_copy = wf / "design-seed.md"
    seed_copy.write_text(
        "\n".join(
            [
                "# Design Seed",
                "",
                f"- Source: {design_path}",
                "",
                design_text.rstrip(),
                "",
            ]
        ),
        encoding="utf-8",
    )

    design_slice_path = wf / "design-slice.md"
    design_slice_path.write_text(
        render_design_slice(
            source_path=design_path,
            normalized_path=normalized_design_path,
            epic_candidates_path=epic_candidates_path,
            selected=selected_epic,
            problem=problem,
            goal=goal,
            constraints=constraints,
        ),
        encoding="utf-8",
    )

    links_path = wf / "links.md"
    links = parse_kv_list(links_path)
    links["Design seed"] = str(design_path)
    docs_links = [str(normalized_design_path), str(epic_candidates_path), str(design_slice_path)]
    existing_docs = [item.strip() for item in links.get("Docs", "").split(",") if item.strip()]
    links["Docs"] = ", ".join(dedupe(existing_docs + docs_links))
    write_kv_list(links_path, "Links", LINK_FIELDS, links)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

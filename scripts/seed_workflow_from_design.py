#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


LINK_FIELDS = ["Tracker", "Design seed", "OpenSpec change", "PRs", "Docs"]


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
    problem = pick_section(sections, ["problem", "background", "context", "why"]) or excerpt
    goal = pick_section(sections, ["goal", "objective", "outcome"]) or "Review the design seed and derive the workflow goal from it."
    non_goals = pick_section(sections, ["non goal", "out of scope"]) or "-"
    constraints = pick_section(sections, ["constraint", "dependency", "dependencies", "risk", "assumption"]) or "-"

    context_path = wf / "context.md"
    write_context(
        context_path,
        problem=problem,
        goal=goal,
        non_goals=non_goals,
        constraints=constraints,
        design_seed=str(design_path),
        excerpt=excerpt,
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

    links_path = wf / "links.md"
    links = parse_kv_list(links_path)
    links["Design seed"] = str(design_path)
    write_kv_list(links_path, "Links", LINK_FIELDS, links)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

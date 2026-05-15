#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from workflow_profile import detect_planning_profile, parse_planning_profile, profile_domain_pack_text


EXCLUDED_PARTS = {
    ".git",
    ".workflow",
    "node_modules",
    "dist",
    "build",
    "target",
    ".venv",
    "__pycache__",
}

IMPORTANT_FILE_NAMES = {
    "README.md",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.sbt",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "compose.yml",
    "tsconfig.json",
    "vite.config.ts",
}


@dataclass(frozen=True)
class SynthesisSpec:
    kind: str
    title: str
    artifact_stem: str
    task_title: str
    default_objective: str
    instructions: tuple[str, ...]
    expected_output: tuple[str, ...]
    validation_expectations: tuple[str, ...]
    input_paths: tuple[str, ...]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def workflow_dir(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug


def truncate(value: str, limit: int = 5000) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "\n...[truncated]"


def relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def expand_input_path(root: Path, slug: str, pattern: str) -> list[Path]:
    relative = pattern.replace("<slug>", slug)
    if any(char in relative for char in "*?["):
        return sorted(path for path in root.glob(relative) if path.is_file())
    path = root / relative
    return [path] if path.exists() and path.is_file() else []


def collect_input_artifacts(root: Path, slug: str, input_paths: tuple[str, ...], limit: int = 40) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    seen: set[Path] = set()
    for pattern in input_paths:
        for path in expand_input_path(root, slug, pattern):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            artifacts.append(
                {
                    "path": relative_or_absolute(path, root),
                    "excerpt": truncate(read_text(path)),
                }
            )
            if len(artifacts) >= limit:
                return artifacts
    return artifacts


def collect_repo_evidence(root: Path, limit: int = 120) -> dict[str, Any]:
    files: list[str] = []
    important: list[str] = []
    if not root.exists():
        return {"files": files, "important_files": important}
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        rel = relative.as_posix()
        if path.name in IMPORTANT_FILE_NAMES or rel.startswith(("src/", "app/", "scripts/", "tests/", "test/")):
            important.append(rel)
        files.append(rel)
        if len(files) >= limit:
            break
    return {
        "files": files,
        "important_files": important[:limit],
        "truncated": len(files) >= limit,
    }


def selected_profile(root: Path, slug: str, artifacts: list[dict[str, str]]) -> dict[str, object]:
    wf = workflow_dir(root, slug)
    capabilities_text = read_text(wf / "capabilities.md")
    if "## Planning Profile" in capabilities_text:
        return parse_planning_profile(capabilities_text)
    workflow_context = "\n\n".join(
        item["excerpt"] for item in artifacts if item["path"].startswith(f".workflow/{slug}/")
    )
    return detect_planning_profile(workflow_context)


def validation_status(errors: list[str], warnings: list[str], artifact_count: int) -> dict[str, Any]:
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "warnings": warnings,
        "input_artifact_count": artifact_count,
    }


def default_validation(artifacts: list[dict[str, str]]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not artifacts:
        errors.append("No input artifacts were found for this synthesis packet.")
    return validation_status(errors, warnings, len(artifacts))


def render_markdown_section(section: dict[str, object]) -> list[str]:
    title = str(section.get("title") or "").strip()
    lines = section.get("lines", [])
    rendered: list[str] = []
    if title:
        rendered.extend(["", f"## {title}", ""])
    if isinstance(lines, list) and lines:
        rendered.extend(str(line) for line in lines)
    else:
        rendered.append("- None")
    return rendered


def render_synthesis_markdown(payload: dict[str, Any], spec: SynthesisSpec) -> str:
    profile = payload["planning_profile"]
    validation = payload["validation"]
    lines = [
        f"# {spec.title}",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Workflow slug: {payload['workflow_slug']}",
        f"- Synthesis kind: {payload['synthesis_kind']}",
        f"- Objective: {payload.get('objective') or spec.default_objective}",
        "",
        "## Planning Profile",
        "",
        f"- Delivery kind: {profile.get('delivery_kind', 'general')}",
        f"- Runtime surface: {profile.get('runtime_surface', 'unspecified')}",
        f"- Domain packs: {profile_domain_pack_text(profile)}",
        f"- Assurance level: {profile.get('assurance_level', 'normal')}",
        f"- Workflow strategy: {profile.get('workflow_strategy', 'simple')}",
        f"- Compatibility mode: {profile.get('mode', 'general-delivery')}",
        "",
        f"## {spec.task_title}",
        "",
    ]
    lines.extend(spec.instructions)
    lines.extend(["", "Expected output:", ""])
    lines.extend(f"- {item}" for item in spec.expected_output)
    lines.extend(["", "Validation expectations:", ""])
    lines.extend(f"- {item}" for item in spec.validation_expectations)
    lines.extend(
        [
            "",
            "## Current Validation",
            "",
            f"- Status: {validation['status']}",
            f"- Input artifact count: {validation.get('input_artifact_count', 0)}",
        ]
    )
    for error in validation["errors"]:
        lines.append(f"- Error: {error}")
    for warning in validation["warnings"][:12]:
        lines.append(f"- Warning: {warning}")
    if len(validation["warnings"]) > 12:
        lines.append(f"- Warning: {len(validation['warnings']) - 12} additional warnings omitted from markdown packet.")
    for section in payload.get("markdown_sections", []):
        if isinstance(section, dict):
            lines.extend(render_markdown_section(section))
    lines.extend(["", "## Input Artifacts", ""])
    for artifact in payload["input_artifacts"]:
        lines.extend(
            [
                f"### {artifact['path']}",
                "",
                "```text",
                artifact["excerpt"] or "-",
                "```",
                "",
            ]
        )
    lines.extend(["## Repository Evidence", ""])
    important = payload["repo_evidence"].get("important_files", [])
    if important:
        lines.extend(["Important files:", ""])
        lines.extend(f"- `{item}`" for item in important[:80])
    else:
        lines.append("- No important repo files detected.")
    lines.append("")
    return "\n".join(lines)


def render_validation_markdown(payload: dict[str, Any], spec: SynthesisSpec) -> str:
    validation = payload["validation"]
    lines = [
        f"# {spec.title} Validation",
        "",
        f"- Generated at: {payload['generated_at']}",
        f"- Workflow slug: {payload['workflow_slug']}",
        f"- Synthesis kind: {payload['synthesis_kind']}",
        f"- Status: {validation['status']}",
        f"- Input artifact count: {validation.get('input_artifact_count', 0)}",
        "",
    ]
    if validation["errors"]:
        lines.extend(["## Errors", ""])
        lines.extend(f"- {item}" for item in validation["errors"])
        lines.append("")
    if validation["warnings"]:
        lines.extend(["## Warnings", ""])
        lines.extend(f"- {item}" for item in validation["warnings"])
        lines.append("")
    if not validation["errors"] and not validation["warnings"]:
        lines.extend(["No validation issues found.", ""])
    return "\n".join(lines)


def run_synthesis_packet(
    root: Path,
    slug: str,
    spec: SynthesisSpec,
    objective: str = "",
    *,
    validation: dict[str, Any] | None = None,
    extra_payload: dict[str, Any] | None = None,
    markdown_sections: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    wf = workflow_dir(root, slug)
    wf.mkdir(parents=True, exist_ok=True)

    artifacts = collect_input_artifacts(root, slug, spec.input_paths)
    packet_validation = dict(validation) if validation is not None else default_validation(artifacts)
    packet_validation["input_artifact_count"] = len(artifacts)
    payload: dict[str, Any] = {
        "generated_at": utc_now(),
        "workflow_slug": slug,
        "synthesis_kind": spec.kind,
        "artifact_stem": spec.artifact_stem,
        "title": spec.title,
        "objective": objective,
        "planning_profile": selected_profile(root, slug, artifacts),
        "input_artifacts": artifacts,
        "repo_evidence": collect_repo_evidence(root),
        "validation": packet_validation,
        "markdown_sections": markdown_sections or [],
    }
    if extra_payload:
        payload.update(extra_payload)

    (wf / f"{spec.artifact_stem}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (wf / f"{spec.artifact_stem}.md").write_text(render_synthesis_markdown(payload, spec), encoding="utf-8")
    (wf / f"{spec.artifact_stem}-validation.json").write_text(
        json.dumps(payload["validation"], indent=2) + "\n",
        encoding="utf-8",
    )
    (wf / f"{spec.artifact_stem}-validation.md").write_text(render_validation_markdown(payload, spec), encoding="utf-8")
    return payload

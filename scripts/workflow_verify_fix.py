#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


INPUT_FILES = [
    "state.md",
    "stories.md",
    "review-log.md",
    "role-reviews.md",
    "conflicts.md",
    "feedback-synthesis.json",
    "issue-advisor.json",
    "ci-feedback.json",
    "records/ci-feedback.jsonl",
    "merge-gate.json",
    "merge-apply.json",
    "integration-test-gate.json",
    "records/debt.jsonl",
]
OPEN_VALUES = {"", "-", "open", "pending", "unresolved", "todo", "tbd"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workflow_path(root: Path, slug: str, relative: str) -> Path:
    return root / ".workflow" / slug / relative


def verify_fix_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "verify-fix.json")


def verify_fix_summary_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "verify-fix.md")


def verify_fix_records_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "records/verify-fix.jsonl")


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        values[key.strip()] = value.strip()
    return values


def parse_directives(raw: str | None) -> dict[str, str]:
    if not raw or not raw.strip():
        return {}
    directives: dict[str, str] = {}
    for segment in [item.strip() for item in re.split(r"[;\n]+", raw) if item.strip()]:
        if ":" in segment:
            key, value = segment.split(":", 1)
        elif "=" in segment:
            key, value = segment.split("=", 1)
        else:
            continue
        directives[key.strip().lower()] = value.strip()
    if not directives:
        directives["summary"] = raw.strip()
    return directives


def split_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text or text == "-":
        return []
    return [item.strip() for item in re.split(r"\s*\|\s*|\s*,\s*|\s*;\s*", text) if item.strip()]


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def slugify(value: object) -> str:
    text = normalize_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or "criterion"


def active_story(root: Path, slug: str) -> str:
    state = parse_kv_list(workflow_path(root, slug, "state.md"))
    return state.get("Active items", "").split(",", 1)[0].strip()


def story_number(value: str) -> str:
    match = re.search(r"\bstory\s+(\d+)\b", value or "", flags=re.IGNORECASE)
    return match.group(1) if match else ""


def active_story_file(root: Path, slug: str, story: str) -> Path:
    number = story_number(story)
    if number:
        path = workflow_path(root, slug, f"story-{int(number)}.md")
        if path.exists():
            return path
    workflow_dir = root / ".workflow" / slug
    for path in sorted(workflow_dir.glob("story-*.md")):
        first_heading = ""
        for line in read_text(path).splitlines():
            if line.startswith("# "):
                first_heading = line.lstrip("#").strip()
                break
        if first_heading and (first_heading == story or first_heading.startswith(story)):
            return path
    return workflow_path(root, slug, f"story-{number or 'active'}.md")


def section_bullets(text: str, headings: set[str]) -> list[str]:
    bullets: list[str] = []
    in_section = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        heading = re.match(r"^(#{2,6})\s+(.+)$", line)
        if heading:
            heading_text = heading.group(2).strip().lower()
            in_section = heading_text in headings
            continue
        if in_section:
            match = re.match(r"^\s*[-*]\s+(.+)$", line)
            if match:
                bullets.append(match.group(1).strip())
    return bullets


def table_rows(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    for raw_line in read_text(path).splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        if parts and parts[0] not in {"Date", "Role", "Work Item"}:
            rows.append(parts)
    return rows


def finding_matches_story(finding: str, story: str) -> bool:
    if not story:
        return True
    explicit = story_number(finding.split(":", 1)[0])
    active = story_number(story)
    return not explicit or not active or explicit == active


def collect_review_findings(root: Path, slug: str, story: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for row in table_rows(workflow_path(root, slug, "review-log.md")):
        if len(row) < 5:
            continue
        date, role, severity, finding, resolution = row[:5]
        if finding_matches_story(finding, story):
            findings.append(
                {
                    "date": date,
                    "role": role,
                    "severity": severity,
                    "finding": finding,
                    "resolution": resolution,
                }
            )
    return findings


def collect_role_reviews(root: Path, slug: str, story: str) -> list[dict[str, object]]:
    reviews: list[dict[str, object]] = []
    for row in table_rows(workflow_path(root, slug, "role-reviews.md")):
        if len(row) < 11:
            continue
        date, row_story, role, verdict, missing, assumptions, risks, questions, changes, evidence, red_team = row[:11]
        if row_story.strip() not in {"", "-", story}:
            continue
        reviews.append(
            {
                "date": date,
                "story": row_story,
                "role": role,
                "verdict": verdict,
                "missing_requirements": split_values(missing),
                "incorrect_assumptions": split_values(assumptions),
                "risks": split_values(risks),
                "questions": split_values(questions),
                "suggested_changes": split_values(changes),
                "evidence": split_values(evidence),
                "red_team_notes": split_values(red_team),
            }
        )
    return reviews


def current_head(root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def input_hashes(root: Path, slug: str, story_file: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in INPUT_FILES:
        hashes[relative] = sha256_file(workflow_path(root, slug, relative))
    try:
        relative_story = str(story_file.relative_to(root / ".workflow" / slug))
    except ValueError:
        relative_story = story_file.name
    hashes[relative_story] = sha256_file(story_file)
    return hashes


def criterion_matches(selector: str, criterion: str, index: int) -> bool:
    cleaned = normalize_text(selector).lower()
    if cleaned in {"all", "*", "any"}:
        return True
    if cleaned in {str(index), f"#{index}", f"criterion {index}", f"acceptance {index}"}:
        return True
    normalized_criterion = normalize_text(criterion).lower()
    return bool(cleaned) and (cleaned in normalized_criterion or normalized_criterion in cleaned)


def selected_by(selectors: list[str], criterion: str, index: int) -> list[str]:
    return [selector for selector in selectors if criterion_matches(selector, criterion, index)]


def evidence_mentions_criterion(text: str, criterion: str) -> bool:
    criterion_words = [word for word in re.findall(r"[a-z0-9]{4,}", criterion.lower()) if word not in {"should", "must", "when", "then", "with", "from", "that"}]
    if not criterion_words:
        return False
    lower = text.lower()
    matches = sum(1 for word in set(criterion_words) if word in lower)
    return matches >= min(2, len(set(criterion_words)))


def evidence_inputs(
    findings: list[dict[str, str]],
    reviews: list[dict[str, object]],
) -> tuple[list[str], list[str], list[str]]:
    failed: list[str] = []
    passed: list[str] = []
    evidence: list[str] = []
    for finding in findings:
        finding_text = normalize_text(finding.get("finding", ""))
        resolution = normalize_text(finding.get("resolution", "")).lower()
        if resolution in OPEN_VALUES:
            failed.append(finding_text)
        elif finding_text:
            evidence.append(f"{finding_text} resolved by {finding.get('resolution', '')}")
    for review in reviews:
        for item in review.get("missing_requirements", []) if isinstance(review.get("missing_requirements"), list) else []:
            failed.append(str(item))
        for item in review.get("evidence", []) if isinstance(review.get("evidence"), list) else []:
            evidence.append(str(item))
        verdict = normalize_text(review.get("verdict", "")).lower()
        if verdict in {"approve", "approved", "pass", "passed"}:
            passed.extend(str(item) for item in review.get("evidence", []) if isinstance(review.get("evidence"), list))
    return failed, passed, evidence


def classify_criterion(
    criterion: str,
    index: int,
    pass_selectors: list[str],
    fail_selectors: list[str],
    failed_evidence: list[str],
    passed_evidence: list[str],
    general_evidence: list[str],
) -> dict[str, object]:
    explicit_fail = selected_by(fail_selectors, criterion, index)
    explicit_pass = selected_by(pass_selectors, criterion, index)
    review_failures = [item for item in failed_evidence if evidence_mentions_criterion(item, criterion)]
    review_passes = [item for item in passed_evidence if evidence_mentions_criterion(item, criterion)]
    supporting = [item for item in general_evidence if evidence_mentions_criterion(item, criterion)]
    if explicit_fail or review_failures:
        status = "failed"
        confidence = "high" if explicit_fail else "medium"
        evidence = explicit_fail + review_failures + supporting
    elif explicit_pass or review_passes:
        status = "passed"
        confidence = "high" if explicit_pass else "medium"
        evidence = explicit_pass + review_passes + supporting
    else:
        status = "unverified"
        confidence = "low"
        evidence = supporting
    return {
        "id": f"ac-{index}",
        "criterion": criterion,
        "status": status,
        "confidence": confidence,
        "evidence": evidence[:5],
    }


def fix_task_for(story: str, item: dict[str, object]) -> dict[str, object]:
    criterion = normalize_text(item.get("criterion", ""))
    status = normalize_text(item.get("status", "unverified"))
    task_type = "failed_acceptance_criterion" if status == "failed" else "unverified_acceptance_criterion"
    return {
        "id": f"vf-{slugify(story)}-{item.get('id', 'criterion')}",
        "story": story,
        "type": task_type,
        "criterion": criterion,
        "status": "open",
        "recommended_action": (
            "Fix the implementation and rerun verification evidence for this acceptance criterion."
            if status == "failed"
            else "Collect concrete repo/test/review evidence or implement the missing behavior for this acceptance criterion."
        ),
        "suggested_command": f"wrkflw:rework-item \"{story}: {criterion}\"",
    }


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def render_markdown(payload: dict[str, object]) -> str:
    blockers = payload.get("blockers", [])
    warnings = payload.get("warnings", [])
    criteria = payload.get("criteria", [])
    fix_tasks = payload.get("fix_tasks", [])
    lines = [
        "# Verify Fix",
        "",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Active story: {payload.get('active_story', '-') or '-'}",
        f"- Status: {payload.get('status', '-')}",
        f"- Recommendation: {payload.get('recommendation', '-')}",
        f"- Summary: {payload.get('summary', '-')}",
        "",
        "## Criteria",
        "",
        "| ID | Status | Criterion | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    if isinstance(criteria, list) and criteria:
        for item in criteria:
            if not isinstance(item, dict):
                continue
            evidence = "; ".join(str(value) for value in item.get("evidence", []) if str(value).strip()) if isinstance(item.get("evidence"), list) else ""
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item.get("id", "-")),
                        str(item.get("status", "-")),
                        normalize_text(item.get("criterion", "-")).replace("|", "\\|"),
                        normalize_text(evidence or "-").replace("|", "\\|"),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - |")
    lines.extend(["", "## Fix Tasks"])
    if isinstance(fix_tasks, list) and fix_tasks:
        for task in fix_tasks:
            if isinstance(task, dict):
                lines.append(f"- `{task.get('id', '-')}`: {task.get('recommended_action', '-')}")
    else:
        lines.append("- none")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in blockers if str(item).strip()) if isinstance(blockers, list) and blockers else lines.append("- none")
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in warnings if str(item).strip()) if isinstance(warnings, list) and warnings else lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def run_verify_fix(root: Path, slug: str, directive_text: str | None = None) -> dict[str, object]:
    generated_at = utc_now()
    story = active_story(root, slug)
    story_file = active_story_file(root, slug, story)
    story_text = read_text(story_file)
    criteria = section_bullets(story_text, {"acceptance criteria", "acceptance", "criteria"})
    validation = section_bullets(story_text, {"tests", "validation", "test expectations"})
    blockers: list[str] = []
    warnings: list[str] = []
    if not story:
        blockers.append("No active story is recorded in state.md.")
    if not story_file.exists():
        blockers.append(f"Active story file is missing: {story_file.name}.")
    if not criteria:
        blockers.append("No acceptance criteria were found for the active story.")

    directives = parse_directives(directive_text)
    pass_selectors = split_values(directives.get("pass") or directives.get("passed") or directives.get("satisfied"))
    fail_selectors = split_values(directives.get("fail") or directives.get("failed") or directives.get("missing") or directives.get("unmet"))
    directive_evidence = split_values(directives.get("evidence") or directives.get("validation") or directives.get("summary"))
    status_directive = normalize_text(directives.get("status", "")).lower()
    if status_directive in {"passed", "pass", "ready"} and not pass_selectors:
        pass_selectors = ["all"]
    if status_directive in {"failed", "fail", "blocked"} and not fail_selectors:
        fail_selectors = ["all"]

    findings = collect_review_findings(root, slug, story)
    reviews = collect_role_reviews(root, slug, story)
    failed_evidence, passed_evidence, review_evidence = evidence_inputs(findings, reviews)
    general_evidence = directive_evidence + review_evidence
    integration_gate = read_json(workflow_path(root, slug, "integration-test-gate.json"))
    if str(integration_gate.get("status") or "").strip().lower() == "ready":
        general_evidence.append("integration-test-gate is ready")
    elif str(integration_gate.get("status") or "").strip().lower() == "blocked":
        warnings.append("integration-test-gate is blocked; acceptance verification may be incomplete")
    ci_feedback = read_json(workflow_path(root, slug, "ci-feedback.json"))
    ci_status = str(ci_feedback.get("status") or "").strip().lower()
    ci_checks = ci_feedback.get("checks", [])
    ci_checks = ci_checks if isinstance(ci_checks, list) else []
    if ci_status == "ready":
        for check in ci_checks:
            if not isinstance(check, dict):
                continue
            if str(check.get("status") or "").strip().lower() == "passed":
                evidence = f"CI check {check.get('name', 'ci')} passed for {story}."
                passed_evidence.append(evidence)
                general_evidence.append(evidence)
    elif ci_status in {"action_required", "fix_required", "failed"}:
        for check in ci_checks:
            if not isinstance(check, dict):
                continue
            if str(check.get("status") or "").strip().lower() != "passed":
                failed_evidence.append(
                    f"CI check {check.get('name', 'ci')} failed; expected pass for {story}. {check.get('failure', '')}"
                )
    elif ci_status == "blocked":
        warnings.append("ci-feedback is blocked; acceptance verification may be incomplete")

    classified = [
        classify_criterion(
            criterion,
            index,
            pass_selectors,
            fail_selectors,
            failed_evidence,
            passed_evidence,
            general_evidence,
        )
        for index, criterion in enumerate(criteria, start=1)
    ]
    fix_tasks = [fix_task_for(story, item) for item in classified if item.get("status") in {"failed", "unverified"}]
    if blockers:
        status = "blocked"
        recommendation = "block"
        summary = "Acceptance verification cannot run until the active story and criteria are available."
    elif fix_tasks:
        status = "fix_required"
        recommendation = "fix"
        summary = f"{len(fix_tasks)} acceptance criterion task(s) need implementation or evidence."
    else:
        status = "ready"
        recommendation = "approve"
        summary = "All acceptance criteria have explicit verification evidence."

    payload = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": generated_at,
        "status": status,
        "recommendation": recommendation,
        "summary": summary,
        "active_story": story,
        "story_file": str(story_file.relative_to(root)) if story_file.exists() else str(story_file),
        "current_head": current_head(root),
        "input_hashes": input_hashes(root, slug, story_file),
        "criteria": classified,
        "validation_expectations": validation,
        "fix_tasks": fix_tasks,
        "ci_feedback_status": ci_status or "missing",
        "ci_check_count": len(ci_checks),
        "review_findings_count": len(findings),
        "role_reviews_count": len(reviews),
        "blockers": blockers,
        "warnings": warnings,
    }
    write_text(verify_fix_path(root, slug), json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_text(verify_fix_summary_path(root, slug), render_markdown(payload))
    append_jsonl(
        verify_fix_records_path(root, slug),
        {
            "schema_version": 1,
            "recorded_at": generated_at,
            "workflow_slug": slug,
            "active_story": story,
            "status": status,
            "recommendation": recommendation,
            "fix_task_count": len(fix_tasks),
            "criteria_count": len(classified),
            "current_head": payload["current_head"],
        },
    )
    return payload


def default_verify_fix(slug: str) -> str:
    return f"""# Verify Fix

- Workflow slug: {slug}
- Status:
- Recommendation:
- Summary:

## Criteria

| ID | Status | Criterion | Evidence |
| --- | --- | --- | --- |
| - | - | - | - |

## Fix Tasks
- none
"""


def ensure_verify_fix_artifact(root: Path, slug: str) -> None:
    path = verify_fix_summary_path(root, slug)
    if not path.exists():
        write_text(path, default_verify_fix(slug))
    verify_fix_records_path(root, slug).parent.mkdir(parents=True, exist_ok=True)


def verify_fix_required(root: Path, slug: str, stage: str) -> bool:
    if stage not in {"review", "release-planning", "done"}:
        return False
    story = active_story(root, slug)
    if not story:
        return False
    story_file = active_story_file(root, slug, story)
    return bool(section_bullets(read_text(story_file), {"acceptance criteria", "acceptance", "criteria"}))


def verify_fix_block(root: Path, slug: str, stage: str) -> tuple[bool, str]:
    if not verify_fix_required(root, slug, stage):
        return False, ""
    path = verify_fix_path(root, slug)
    if not path.exists():
        return True, "Verify-fix is required for the active story; run wrkflw:verify-fix before approval."
    payload = read_json(path)
    if not payload:
        return True, "Verify-fix artifact is unreadable; rerun wrkflw:verify-fix."
    status = str(payload.get("status") or "").strip().lower()
    if status in {"", "not_recorded"}:
        return True, "Verify-fix is required for the active story; run wrkflw:verify-fix before approval."
    story = active_story(root, slug)
    story_file = active_story_file(root, slug, story)
    hashes = payload.get("input_hashes", {})
    hashes = hashes if isinstance(hashes, dict) else {}
    for relative, current_hash in input_hashes(root, slug, story_file).items():
        if str(hashes.get(relative) or "") != current_hash:
            return True, f"Verify-fix is stale because `{relative}` changed; rerun wrkflw:verify-fix."
    head = current_head(root)
    if head and str(payload.get("current_head") or "") != head:
        return True, "Verify-fix is stale because repository HEAD changed; rerun wrkflw:verify-fix."
    if status != "ready":
        tasks = payload.get("fix_tasks", [])
        task_count = len(tasks) if isinstance(tasks, list) else 0
        blockers = payload.get("blockers", [])
        if isinstance(blockers, list) and blockers:
            return True, "Verify-fix is blocked: " + "; ".join(str(item) for item in blockers[:3])
        return True, f"Verify-fix requires fixes or evidence for {task_count} acceptance criterion task(s)."
    return False, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify acceptance criteria and generate focused fix tasks.")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--root", default=".")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--evidence", default="")
    args = parser.parse_args()
    payload = run_verify_fix(Path(args.root).resolve(), args.slug, args.evidence)
    print(f"verify-fix {payload.get('status')}")
    return 1 if payload.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from workflow_debt import blocking_debt_records, format_debt_summary, load_debt_records
from workflow_failure_classification import artifact_classifications, highest_priority_classification


APPROVE = "approve"
FIX = "fix"
SPLIT = "split"
DEFER = "defer"
BLOCK = "block"
REPLAN = "replan"

OPEN_VALUES = {"", "-", "open", "pending", "unresolved", "todo", "tbd"}
BLOCKING_SEVERITIES = {"blocking", "blocker", "critical", "high"}
REVIEW_ROLES_FOR_FLAGGED = {"Tech Lead", "Reviewer QA"}
INPUT_FILES = [
    "stories.md",
    "dag.json",
    "role-reviews.md",
    "review-log.md",
    "conflicts.md",
    "records/debt.jsonl",
    "execution-path.json",
    "integration-test-gate.json",
    "verify-fix.json",
    "records/verify-fix.jsonl",
    "ci-feedback.json",
    "records/ci-feedback.jsonl",
    "merge-gate.json",
    "merge-apply.json",
    "issue-advisor.json",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_text_if_changed(path: Path, content: str) -> None:
    if path.exists() and read_text(path) == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sha256_file(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        values[key.strip()] = value.strip()
    return values


def active_story(root: Path, slug: str) -> str:
    state = parse_kv_list(root / ".workflow" / slug / "state.md")
    return state.get("Active items", "").split(",", 1)[0].strip()


def feedback_synthesis_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "feedback-synthesis.json"


def feedback_synthesis_summary_path(root: Path, slug: str) -> Path:
    return root / ".workflow" / slug / "feedback-synthesis.md"


def workflow_path(root: Path, slug: str, relative: str) -> Path:
    return root / ".workflow" / slug / relative


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


def story_matches(row_story: str, story: str) -> bool:
    cleaned = row_story.strip()
    if not story:
        return True
    return cleaned in {"", "-"} or cleaned == story


def story_number(value: str) -> str:
    match = re.search(r"\bstory\s+(\d+)\b", value or "", flags=re.IGNORECASE)
    return match.group(1) if match else ""


def finding_matches_story(finding: str, story: str) -> bool:
    if not story:
        return True
    explicit_story = story_number(finding.split(":", 1)[0])
    if not explicit_story:
        return True
    active_story = story_number(story)
    if active_story:
        return explicit_story == active_story
    return finding.strip().startswith(story)


def split_cell(value: str) -> list[str]:
    if not value or value.strip() == "-":
        return []
    return [item.strip() for item in value.split(";") if item.strip()]


def collect_role_reviews(root: Path, slug: str, story: str) -> list[dict[str, object]]:
    reviews: list[dict[str, object]] = []
    for row in table_rows(workflow_path(root, slug, "role-reviews.md")):
        if len(row) < 11:
            continue
        date, row_story, role, verdict, missing, assumptions, risks, questions, changes, evidence, red_team = row[:11]
        if not story_matches(row_story, story):
            continue
        reviews.append(
            {
                "date": date,
                "story": row_story,
                "role": role,
                "verdict": verdict,
                "missing_requirements": split_cell(missing),
                "incorrect_assumptions": split_cell(assumptions),
                "risks": split_cell(risks),
                "questions": split_cell(questions),
                "suggested_changes": split_cell(changes),
                "evidence": split_cell(evidence),
                "red_team_notes": split_cell(red_team),
            }
        )
    return reviews


def collect_review_findings(root: Path, slug: str, story: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for row in table_rows(workflow_path(root, slug, "review-log.md")):
        if len(row) < 5:
            continue
        date, role, severity, finding, resolution = row[:5]
        if not finding_matches_story(finding, story):
            continue
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


def collect_conflicts(root: Path, slug: str, story: str) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    for row in table_rows(workflow_path(root, slug, "conflicts.md")):
        if len(row) < 9:
            continue
        date, row_story, raised_by, severity, conflict, options, recommendation, resolution, owner = row[:9]
        if not story_matches(row_story, story):
            continue
        conflicts.append(
            {
                "date": date,
                "story": row_story,
                "raised_by": raised_by,
                "severity": severity,
                "conflict": conflict,
                "options": options,
                "recommendation": recommendation,
                "resolution": resolution,
                "owner": owner,
            }
        )
    return conflicts


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def evidence_text(
    reviews: list[dict[str, object]],
    findings: list[dict[str, str]],
    conflicts: list[dict[str, str]],
) -> str:
    parts: list[str] = []
    for review in reviews:
        for key in ["verdict", "missing_requirements", "incorrect_assumptions", "risks", "questions", "suggested_changes", "red_team_notes"]:
            value = review.get(key)
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
            else:
                parts.append(str(value or ""))
    parts.extend(item.get("finding", "") for item in findings)
    parts.extend(item.get("conflict", "") for item in conflicts)
    parts.extend(item.get("recommendation", "") for item in conflicts)
    return " ".join(parts).lower()


def has_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def repeated_issue_detected(items: list[str]) -> bool:
    normalized = [normalize_text(item).lower() for item in items if normalize_text(item).lower() not in {"", "-", "none"}]
    counts = Counter(normalized)
    return any(count >= 3 for count in counts.values())


def input_hashes(root: Path, slug: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    workflow_dir = root / ".workflow" / slug
    input_files = list(INPUT_FILES)
    if workflow_dir.exists():
        input_files.extend(path.name for path in sorted(workflow_dir.glob("story-*.md")))
    for relative in input_files:
        hashes[relative] = sha256_file(workflow_path(root, slug, relative))
    return hashes


def execution_path_payload(root: Path, slug: str) -> dict[str, object]:
    payload = read_json(workflow_path(root, slug, "execution-path.json"))
    path = payload.get("execution_path", {})
    return path if isinstance(path, dict) else {}


def synthesis_required(root: Path, slug: str) -> bool:
    path = execution_path_payload(root, slug)
    return bool(path.get("synthesis_required")) or str(path.get("path") or "").strip().lower() == "flagged"


def gate_status(root: Path, slug: str, filename: str) -> str:
    return str(read_json(workflow_path(root, slug, filename)).get("status") or "").strip().lower()


def summarize_gate_blockers(root: Path, slug: str) -> list[str]:
    blockers: list[str] = []
    for filename, label in [
        ("merge-gate.json", "merge gate"),
        ("merge-apply.json", "merge apply"),
        ("integration-test-gate.json", "integration gate"),
        ("verify-fix.json", "verify-fix"),
        ("ci-feedback.json", "CI feedback"),
    ]:
        payload = read_json(workflow_path(root, slug, filename))
        status = str(payload.get("status") or "").strip().lower()
        if status in {"blocked", "failed", "fix_required", "action_required"}:
            raw_blockers = payload.get("blockers", [])
            if isinstance(raw_blockers, list) and raw_blockers:
                blockers.append(f"{label}: " + "; ".join(str(item) for item in raw_blockers[:2]))
            elif filename in {"verify-fix.json", "ci-feedback.json"} and isinstance(payload.get("fix_tasks"), list):
                task_label = "acceptance criterion" if filename == "verify-fix.json" else "CI check"
                blockers.append(f"{label}: {len(payload.get('fix_tasks', []))} {task_label} task(s) need fixes or evidence")
            else:
                blockers.append(f"{label}: status is {status}")
    return blockers


def summarize_failure_classes(root: Path, slug: str) -> tuple[list[dict[str, object]], dict[str, object], list[str]]:
    classes = artifact_classifications(root, slug)
    top = highest_priority_classification(classes)
    summaries = [
        f"{item.get('source', '-')}: {item.get('failure_class', '-')} ({item.get('failure_category', '-')})"
        + (f" - {item.get('summary')}" if item.get("summary") else "")
        for item in classes
        if item.get("failure_class")
    ]
    return classes, top, summaries


def decide(
    root: Path,
    slug: str,
    story: str,
    reviews: list[dict[str, object]],
    findings: list[dict[str, str]],
    conflicts: list[dict[str, str]],
) -> tuple[str, str, list[str], list[str], list[str]]:
    reasons: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    required = synthesis_required(root, slug)
    path = execution_path_payload(root, slug)
    roles_with_review = {str(review.get("role") or "") for review in reviews}
    roles_with_findings = {finding.get("role", "") for finding in findings}
    available_roles = roles_with_review | roles_with_findings
    missing_roles = sorted(role for role in REVIEW_ROLES_FOR_FLAGGED if role not in available_roles)
    if required and missing_roles:
        blockers.append("Missing required synthesis input from: " + ", ".join(missing_roles))
        return BLOCK, "Required flagged-path review evidence is incomplete.", reasons, blockers, warnings

    gate_blockers = summarize_gate_blockers(root, slug)
    failure_classes, top_failure, failure_summaries = summarize_failure_classes(root, slug)
    if failure_summaries:
        warnings.extend(failure_summaries[:5])
    top_category = str(top_failure.get("failure_category") or "")
    top_class = str(top_failure.get("failure_class") or "")
    if top_category == "dependency_or_architecture":
        reasons.append(f"Typed failure classification `{top_class}` requires plan-level handling.")
        return REPLAN, "Typed failure evidence points to dependency, stale gate, or architecture-level replanning.", reasons, blockers, warnings
    if top_category == "scope_too_large":
        reasons.append(f"Typed failure classification `{top_class}` indicates the story scope is too broad.")
        return SPLIT, "Typed failure evidence recommends splitting the story before retrying.", reasons, blockers, warnings
    if top_category == "environment_failure":
        blockers.append(f"Environment failure `{top_class}` should be repaired or rerun before implementation retry.")
        return BLOCK, "Typed failure evidence points to environment or infrastructure repair before retry.", reasons, blockers, warnings
    if top_category in {"policy_or_security_block", "merge_conflict"}:
        blockers.append(f"Typed failure `{top_class}` requires explicit resolution before approval.")
        return BLOCK, "Typed failure evidence requires explicit gate resolution before continuing.", reasons, blockers, warnings

    if gate_blockers:
        blockers.extend(gate_blockers)
        return FIX, "Merge, apply, or integration gate blockers need correction before approval.", reasons, blockers, warnings

    blocking_debt = blocking_debt_records(load_debt_records(root, slug))
    if blocking_debt:
        blockers.append("Open high/critical technical debt: " + format_debt_summary(blocking_debt))

    open_blocking_findings = [
        finding
        for finding in findings
        if finding.get("severity", "").strip().lower() in BLOCKING_SEVERITIES
        and finding.get("resolution", "").strip().lower() in OPEN_VALUES
    ]
    open_blocking_conflicts = [
        conflict
        for conflict in conflicts
        if conflict.get("severity", "").strip().lower() in BLOCKING_SEVERITIES
        and conflict.get("resolution", "").strip().lower() in OPEN_VALUES
    ]
    block_verdicts = [
        review
        for review in reviews
        if str(review.get("verdict") or "").strip().lower() in {"block", "blocked"}
    ]
    fix_inputs: list[str] = []
    advisory_inputs: list[str] = []
    for review in reviews:
        for key in ["missing_requirements", "incorrect_assumptions"]:
            value = review.get(key)
            if isinstance(value, list):
                fix_inputs.extend(value)
        suggested = review.get("suggested_changes")
        if isinstance(suggested, list):
            advisory_inputs.extend(suggested)
    fix_inputs.extend(finding.get("finding", "") for finding in open_blocking_findings)
    fix_inputs.extend(conflict.get("conflict", "") for conflict in open_blocking_conflicts)
    if advisory_inputs:
        warnings.append("Non-blocking suggested changes remain: " + "; ".join(advisory_inputs[:3]))

    text = evidence_text(reviews, findings, conflicts)
    if has_any(text, {"replan", "wrong plan", "dependency graph", "design contradiction", "invalid plan"}):
        reasons.append("Evidence points to plan-level contradiction or dependency restructuring.")
        return REPLAN, "Escalate to replanning before another implementation retry.", reasons, blockers, warnings
    if has_any(text, {"split", "too broad", "too large", "smaller story", "separate story"}):
        reasons.append("Evidence suggests the story is too broad for one safe slice.")
        return SPLIT, "Split the story before continuing implementation.", reasons, blockers, warnings
    if has_any(text, {"defer", "out of scope", "later slice", "postpone"}):
        reasons.append("Evidence suggests part of the work should be deferred.")
        return DEFER, "Defer the disputed scope or move it to a later slice.", reasons, blockers, warnings

    repeated_inputs = fix_inputs + [
        str(item)
        for review in reviews
        for item in (review.get("risks") if isinstance(review.get("risks"), list) else [])
    ]
    if repeated_issue_detected(repeated_inputs):
        blockers.append("Repeated unresolved feedback suggests a stuck loop.")
        return BLOCK, "The same feedback appears repeatedly; stop blind retries and escalate.", reasons, blockers, warnings

    if blockers:
        return BLOCK, "Blocking debt or review evidence must be resolved or explicitly accepted.", reasons, blockers, warnings
    if block_verdicts or open_blocking_findings or open_blocking_conflicts or fix_inputs:
        reasons.append("Review or QA evidence requests fixes before approval.")
        return FIX, "Address the synthesized review findings before approval.", reasons, blockers, warnings

    if required and not reviews and not findings:
        blockers.append("No review evidence is available to synthesize for the flagged path.")
        return BLOCK, "Flagged-path synthesis requires review evidence.", reasons, blockers, warnings
    if path.get("path") == "simple" and not reviews and not findings:
        warnings.append("No role review evidence was found; synthesis is advisory only.")

    return APPROVE, "No blocking QA, review, conflict, debt, or gate evidence remains.", reasons, blockers, warnings


def render_markdown(payload: dict[str, object]) -> str:
    reasons = payload.get("reasons", [])
    blockers = payload.get("blockers", [])
    warnings = payload.get("warnings", [])
    inputs = payload.get("inputs", {})
    inputs = inputs if isinstance(inputs, dict) else {}
    roles = inputs.get("roles", [])
    lines = [
        "# Feedback Synthesis",
        "",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Active story: {payload.get('active_story', '-') or '-'}",
        f"- Execution path: {payload.get('execution_path', {}).get('path', '-') if isinstance(payload.get('execution_path'), dict) else '-'}",
        f"- Synthesis required: {'yes' if payload.get('synthesis_required') else 'no'}",
        f"- Recommendation: {payload.get('recommendation', '-')}",
        f"- Status: {payload.get('status', '-')}",
        f"- Summary: {payload.get('summary', '-')}",
        f"- Failure class: {payload.get('failure_class', '-') or '-'}",
        f"- Failure category: {payload.get('failure_category', '-') or '-'}",
        f"- Roles synthesized: {', '.join(str(item) for item in roles) if isinstance(roles, list) and roles else '-'}",
        "",
        "## Reasons",
    ]
    lines.extend(f"- {item}" for item in reasons if str(item).strip()) if isinstance(reasons, list) and reasons else lines.append("- none")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in blockers if str(item).strip()) if isinstance(blockers, list) and blockers else lines.append("- none")
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in warnings if str(item).strip()) if isinstance(warnings, list) and warnings else lines.append("- none")
    lines.extend(
        [
            "",
            "## Input Counts",
            f"- Role reviews: {inputs.get('role_review_count', 0)}",
            f"- Review findings: {inputs.get('review_finding_count', 0)}",
            f"- Conflicts: {inputs.get('conflict_count', 0)}",
            "",
        ]
    )
    return "\n".join(lines)


def run_feedback_synthesis(root: Path, slug: str, note: str | None = None) -> dict[str, object]:
    story = active_story(root, slug)
    reviews = collect_role_reviews(root, slug, story)
    findings = collect_review_findings(root, slug, story)
    conflicts = collect_conflicts(root, slug, story)
    recommendation, summary, reasons, blockers, warnings = decide(root, slug, story, reviews, findings, conflicts)
    if note and note.strip():
        warnings.append(f"Operator note: {note.strip()}")
    path = execution_path_payload(root, slug)
    failure_classes, top_failure, _failure_summaries = summarize_failure_classes(root, slug)
    status = "ready" if recommendation == APPROVE else "blocked" if recommendation == BLOCK else "action_required"
    payload: dict[str, object] = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": utc_now(),
        "active_story": story,
        "execution_path": path,
        "synthesis_required": synthesis_required(root, slug),
        "recommendation": recommendation,
        "status": status,
        "summary": summary,
        "reasons": reasons,
        "blockers": blockers,
        "warnings": warnings,
        "failure_class": top_failure.get("failure_class", ""),
        "failure_category": top_failure.get("failure_category", ""),
        "failure_classification": top_failure,
        "failure_classifications": failure_classes,
        "inputs": {
            "roles": sorted({str(review.get("role") or "") for review in reviews if str(review.get("role") or "").strip()}),
            "role_review_count": len(reviews),
            "review_finding_count": len(findings),
            "conflict_count": len(conflicts),
        },
        "input_hashes": input_hashes(root, slug),
    }
    write_text_if_changed(feedback_synthesis_path(root, slug), json.dumps(payload, indent=2) + "\n")
    write_text_if_changed(feedback_synthesis_summary_path(root, slug), render_markdown(payload))
    return payload


def feedback_synthesis_block(root: Path, slug: str, stage: str) -> tuple[bool, str]:
    if stage not in {"release-planning", "done"}:
        return False, ""
    path = feedback_synthesis_path(root, slug)
    required = synthesis_required(root, slug)
    if not required:
        return False, ""
    if not path.exists():
        return True, "Feedback synthesis is required for the flagged execution path; run wrkflw:feedback-synth before approval."
    payload = read_json(path)
    if not payload:
        return True, "Feedback synthesis artifact is unreadable; rerun wrkflw:feedback-synth."
    status = str(payload.get("status") or "").strip().lower()
    if status in {"", "not_recorded"}:
        return True, "Feedback synthesis is required for the flagged execution path; run wrkflw:feedback-synth before approval."
    if payload.get("active_story", "") != active_story(root, slug):
        return True, "Feedback synthesis is stale because the active story changed; rerun wrkflw:feedback-synth."
    recorded_hashes = payload.get("input_hashes", {})
    if not isinstance(recorded_hashes, dict):
        return True, "Feedback synthesis is missing input bindings; rerun wrkflw:feedback-synth."
    current_hashes = input_hashes(root, slug)
    changed = [name for name, digest in current_hashes.items() if recorded_hashes.get(name) != digest]
    if changed:
        return True, "Feedback synthesis is stale because inputs changed: " + ", ".join(changed[:3])
    recommendation = str(payload.get("recommendation") or "").strip().lower()
    if recommendation and recommendation != APPROVE:
        return True, f"Feedback synthesis recommends `{recommendation}`: {payload.get('summary', 'review feedback-synthesis.md')}"
    return False, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize team feedback into a single workflow recommendation.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    run_feedback_synthesis(Path(args.root).resolve(), args.slug, args.note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

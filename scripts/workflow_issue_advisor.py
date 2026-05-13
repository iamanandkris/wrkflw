#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from workflow_accounting import format_accounting_summary, load_invocation_records
from workflow_debt import blocking_debt_records, format_debt_summary, load_debt_records
from workflow_failure_classification import artifact_classifications, highest_priority_classification
from workflow_memory import active_memory_records, format_memory_summary, load_memory_records


RETRY_APPROACH = "retry_approach"
RETRY_MODIFIED = "retry_modified"
ACCEPT_WITH_DEBT = "accept_with_debt"
SPLIT = "split"
ESCALATE_TO_REPLAN = "escalate_to_replan"

OPEN_VALUES = {"", "-", "open", "pending", "unresolved", "todo", "tbd"}
BLOCKING_SEVERITIES = {"blocking", "blocker", "critical", "high"}
MAX_ADVISOR_INVOCATIONS = 2
INPUT_FILES = [
    "state.md",
    "stories.md",
    "dag.json",
    "dag-validation.md",
    "execution-path.json",
    "feedback-synthesis.json",
    "review-log.md",
    "role-reviews.md",
    "conflicts.md",
    "records/debt.jsonl",
    "records/memory.jsonl",
    "accounting.json",
    "records/invocations.jsonl",
    "merge-gate.json",
    "merge-apply.json",
    "integration-test-gate.json",
    "verify-fix.json",
    "records/verify-fix.jsonl",
    "ci-feedback.json",
    "records/ci-feedback.jsonl",
    "team-minutes.md",
    "history.md",
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


def workflow_path(root: Path, slug: str, relative: str) -> Path:
    return root / ".workflow" / slug / relative


def issue_advisor_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "issue-advisor.json")


def issue_advisor_summary_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "issue-advisor.md")


def adaptation_records_path(root: Path, slug: str) -> Path:
    return workflow_path(root, slug, "records/adaptations.jsonl")


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        values[key.strip()] = value.strip()
    return values


def active_story(root: Path, slug: str) -> str:
    state = parse_kv_list(workflow_path(root, slug, "state.md"))
    return state.get("Active items", "").split(",", 1)[0].strip()


def table_rows(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    for raw_line in read_text(path).splitlines():
        stripped = raw_line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue
        parts = [part.strip() for part in stripped.strip("|").split("|")]
        if parts and parts[0] not in {"Date", "Role", "Work Item", "Timestamp"}:
            rows.append(parts)
    return rows


def split_cell(value: str) -> list[str]:
    if not value or value.strip() == "-":
        return []
    return [item.strip() for item in re.split(r";|\n", value) if item.strip()]


def story_number(value: str) -> str:
    match = re.search(r"\bstory\s+(\d+)\b", value or "", flags=re.IGNORECASE)
    return match.group(1) if match else ""


def story_id(value: str) -> str:
    number = story_number(value)
    return f"story-{int(number)}" if number else ""


def story_matches(row_story: str, story: str) -> bool:
    cleaned = row_story.strip()
    if not story:
        return True
    return cleaned in {"", "-"} or cleaned == story or story_id(cleaned) == story_id(story)


def finding_matches_story(finding: str, story: str) -> bool:
    if not story:
        return True
    explicit_story = story_number(finding.split(":", 1)[0])
    if not explicit_story:
        return True
    active = story_number(story)
    return not active or explicit_story == active


def normalize_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact(value: object, limit: int = 220) -> str:
    text = normalize_text(value)
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def has_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


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


def open_blocking_findings(findings: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        finding
        for finding in findings
        if finding.get("severity", "").strip().lower() in BLOCKING_SEVERITIES
        and finding.get("resolution", "").strip().lower() in OPEN_VALUES
    ]


def open_blocking_conflicts(conflicts: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        conflict
        for conflict in conflicts
        if conflict.get("severity", "").strip().lower() in BLOCKING_SEVERITIES
        and conflict.get("resolution", "").strip().lower() in OPEN_VALUES
    ]


def story_file_path(root: Path, slug: str, story: str) -> Path:
    sid = story_id(story)
    if sid:
        return workflow_path(root, slug, sid + ".md")
    return workflow_path(root, slug, story.lower().replace(" ", "-") + ".md")


def extract_story_sections(root: Path, slug: str, story: str) -> dict[str, list[str]]:
    text = read_text(story_file_path(root, slug, story))
    sections: dict[str, list[str]] = {"acceptance_criteria": [], "test_expectations": [], "allowed_write_paths": []}
    current = ""
    for line in text.splitlines():
        header = line.strip().lower()
        if header.startswith("## "):
            if "acceptance" in header:
                current = "acceptance_criteria"
            elif "test" in header:
                current = "test_expectations"
            elif "allowed write" in header or "write paths" in header:
                current = "allowed_write_paths"
            else:
                current = ""
            continue
        if current and line.strip().startswith("- "):
            sections[current].append(line.strip()[2:].strip())
    return sections


def feedback_payload(root: Path, slug: str) -> dict[str, object]:
    return read_json(workflow_path(root, slug, "feedback-synthesis.json"))


def gate_blockers(root: Path, slug: str) -> list[str]:
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
        if status not in {"blocked", "failed", "fix_required", "action_required"}:
            continue
        raw_blockers = payload.get("blockers", [])
        if isinstance(raw_blockers, list) and raw_blockers:
            blockers.append(f"{label}: " + "; ".join(compact(item) for item in raw_blockers[:3]))
        elif filename in {"verify-fix.json", "ci-feedback.json"} and isinstance(payload.get("fix_tasks"), list):
            task_label = "acceptance criterion" if filename == "verify-fix.json" else "CI check"
            blockers.append(f"{label}: {len(payload.get('fix_tasks', []))} {task_label} task(s) need fixes or evidence")
        else:
            blockers.append(f"{label}: status is {status}")
    return blockers


def dag_payload(root: Path, slug: str) -> dict[str, object]:
    return read_json(workflow_path(root, slug, "dag.json"))


def dag_node(root: Path, slug: str, story: str) -> dict[str, object]:
    sid = story_id(story)
    for node in dag_payload(root, slug).get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        label = str(node.get("label") or "")
        if node_id == sid or label == story or story_id(label) == sid:
            return node
    return {}


def dag_validation_summary(root: Path, slug: str) -> str:
    text = read_text(workflow_path(root, slug, "dag-validation.md"))
    lines = [
        line[2:].strip()
        for line in text.splitlines()
        if line.startswith("- ") and any(keyword in line.lower() for keyword in ["error", "invalid", "blocked", "cycle", "missing"])
    ]
    return "; ".join(lines[:4])


def evidence_corpus(
    reviews: list[dict[str, object]],
    findings: list[dict[str, str]],
    conflicts: list[dict[str, str]],
    feedback: dict[str, object],
    blockers: list[str],
    dag_summary: str,
    operator_note: str,
) -> str:
    parts: list[str] = []
    for review in reviews:
        for key in [
            "verdict",
            "missing_requirements",
            "incorrect_assumptions",
            "risks",
            "questions",
            "suggested_changes",
            "red_team_notes",
        ]:
            value = review.get(key)
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
            else:
                parts.append(str(value or ""))
    parts.extend(finding.get("finding", "") for finding in findings)
    parts.extend(conflict.get("conflict", "") for conflict in conflicts)
    parts.extend(conflict.get("recommendation", "") for conflict in conflicts)
    parts.append(str(feedback.get("recommendation") or ""))
    parts.append(str(feedback.get("summary") or ""))
    for key in ["blockers", "warnings", "reasons"]:
        value = feedback.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    parts.extend(blockers)
    parts.append(dag_summary)
    parts.append(operator_note)
    return " ".join(parts).lower()


def repeated_issue_detected(items: list[str]) -> bool:
    normalized = [normalize_text(item).lower() for item in items if normalize_text(item).lower() not in {"", "-", "none"}]
    counts = Counter(normalized)
    return any(count >= 3 for count in counts.values())


def advisor_invocation(root: Path, slug: str, story: str) -> int:
    previous = read_json(issue_advisor_path(root, slug))
    if str(previous.get("active_story") or "") == story:
        try:
            return max(1, int(previous.get("advisor_invocation") or 0) + 1)
        except (TypeError, ValueError):
            return 1
    return 1


def load_adaptation_records(root: Path, slug: str, story: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in read_text(adaptation_records_path(root, slug)).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and str(payload.get("active_story") or "") == story:
            records.append(payload)
    return records


def append_adaptation_record(root: Path, slug: str, payload: dict[str, object]) -> None:
    record = {
        "recorded_at": utc_now(),
        "workflow_slug": slug,
        "active_story": payload.get("active_story", ""),
        "advisor_invocation": payload.get("advisor_invocation", 1),
        "action": payload.get("action", ""),
        "failure_category": payload.get("failure_category", ""),
        "failure_diagnosis": payload.get("failure_diagnosis", ""),
        "summary": payload.get("summary", ""),
        "decision_source": payload.get("decision_source", "deterministic"),
    }
    path = adaptation_records_path(root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def input_hashes(root: Path, slug: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    workflow_dir = root / ".workflow" / slug
    input_files = list(INPUT_FILES)
    if workflow_dir.exists():
        input_files.extend(path.name for path in sorted(workflow_dir.glob("story-*.md")))
    for relative in input_files:
        hashes[relative] = sha256_file(workflow_path(root, slug, relative))
    return hashes


def make_evidence_items(
    findings: list[dict[str, str]],
    conflicts: list[dict[str, str]],
    blockers: list[str],
    feedback: dict[str, object],
    dag_summary: str,
) -> list[str]:
    items: list[str] = []
    items.extend(
        f"review-log:{finding.get('role', '-')}/{finding.get('severity', '-')}: {compact(finding.get('finding', ''))}"
        for finding in open_blocking_findings(findings)
    )
    items.extend(
        f"conflict:{conflict.get('raised_by', '-')}/{conflict.get('severity', '-')}: {compact(conflict.get('conflict', ''))}"
        for conflict in open_blocking_conflicts(conflicts)
    )
    items.extend(blockers)
    recommendation = str(feedback.get("recommendation") or "").strip()
    if recommendation:
        items.append(f"feedback-synthesis:{recommendation}: {compact(feedback.get('summary', ''))}")
    if dag_summary:
        items.append(f"dag-validation:{compact(dag_summary)}")
    return items


def suggested_debt_from_evidence(
    story: str,
    findings: list[dict[str, str]],
    conflicts: list[dict[str, str]],
    debt_summary: str,
) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    for finding in open_blocking_findings(findings)[:3]:
        suggestions.append(
            {
                "source_story": story,
                "debt_type": "missing functionality",
                "severity": "medium",
                "summary": compact(finding.get("finding", "")),
                "owner": finding.get("role", "") or "Workflow Orchestrator",
            }
        )
    for conflict in open_blocking_conflicts(conflicts)[:2]:
        suggestions.append(
            {
                "source_story": story,
                "debt_type": "unresolved design gap",
                "severity": "medium",
                "summary": compact(conflict.get("conflict", "")),
                "owner": conflict.get("owner", "") or conflict.get("raised_by", "") or "Workflow Orchestrator",
            }
        )
    if debt_summary and not suggestions:
        suggestions.append(
            {
                "source_story": story,
                "debt_type": "unresolved design gap",
                "severity": "medium",
                "summary": compact(debt_summary),
                "owner": "Workflow Orchestrator",
            }
        )
    return suggestions


def modified_acceptance_criteria(sections: dict[str, list[str]], corpus: str) -> tuple[list[str], list[str]]:
    criteria = list(sections.get("acceptance_criteria", []))
    if not criteria:
        return [], []
    if not has_any(corpus, {"drop", "waive", "defer", "out of scope", "later slice", "acceptance"}):
        return criteria, []
    dropped = criteria[-1:]
    kept = criteria[:-1] or criteria
    return kept, dropped if kept != criteria else []


def split_suggestions(story: str, sections: dict[str, list[str]]) -> list[dict[str, object]]:
    acceptance = sections.get("acceptance_criteria", [])
    tests = sections.get("test_expectations", [])
    first_acceptance = acceptance[: max(1, len(acceptance) // 2)] if acceptance else ["Deliver the smallest core behavior for the story."]
    second_acceptance = acceptance[len(first_acceptance) :] if acceptance else ["Move remaining edge cases into a follow-up story."]
    if not second_acceptance:
        second_acceptance = ["Cover integration, edge cases, and remaining acceptance criteria."]
    return [
        {
            "title": f"{story}A: Core path",
            "acceptance_criteria": first_acceptance,
            "test_expectations": tests[: max(1, len(tests) // 2)] if tests else ["Validate the core path."],
        },
        {
            "title": f"{story}B: Remaining edge cases",
            "acceptance_criteria": second_acceptance,
            "test_expectations": tests[len(tests) // 2 :] if tests else ["Validate remaining edge cases and integration behavior."],
        },
    ]


def decide(
    root: Path,
    slug: str,
    story: str,
    note: str,
    reviews: list[dict[str, object]],
    findings: list[dict[str, str]],
    conflicts: list[dict[str, str]],
    sections: dict[str, list[str]],
) -> dict[str, object]:
    feedback = feedback_payload(root, slug)
    recommendation = str(feedback.get("recommendation") or "").strip().lower()
    blockers = gate_blockers(root, slug)
    dag_summary = dag_validation_summary(root, slug)
    node = dag_node(root, slug, story)
    node_status = str(node.get("status") or "").strip().lower()
    debt = blocking_debt_records(load_debt_records(root, slug))
    debt_summary = format_debt_summary(debt)
    memory_summary = format_memory_summary(active_memory_records(load_memory_records(root, slug)))
    accounting_summary = format_accounting_summary(load_invocation_records(root, slug), story)
    failure_classifications = [entry for entry in artifact_classifications(root, slug) if entry.get("source") != "issue-advisor"]
    top_failure = highest_priority_classification(failure_classifications)
    corpus = evidence_corpus(reviews, findings, conflicts, feedback, blockers, dag_summary, note)
    evidence = make_evidence_items(findings, conflicts, blockers, feedback, dag_summary)
    verify_fix = read_json(workflow_path(root, slug, "verify-fix.json"))
    verify_tasks = verify_fix.get("fix_tasks", [])
    verify_task_count = len(verify_tasks) if isinstance(verify_tasks, list) else 0
    ci_feedback = read_json(workflow_path(root, slug, "ci-feedback.json"))
    ci_tasks = ci_feedback.get("fix_tasks", [])
    ci_task_count = len(ci_tasks) if isinstance(ci_tasks, list) else 0
    repeated_inputs = [item.get("finding", "") for item in findings] + [item.get("conflict", "") for item in conflicts]
    invocation = advisor_invocation(root, slug, story)
    previous_adaptations = load_adaptation_records(root, slug, story)
    maxed = invocation >= MAX_ADVISOR_INVOCATIONS
    action = RETRY_APPROACH
    failure_category = "implementation"
    diagnosis = "The issue appears recoverable through a focused implementation retry."
    confidence = "medium"
    rationale: list[str] = []
    next_steps: list[str] = []

    structural_markers = {
        "replan",
        "wrong plan",
        "dependency graph",
        "invalid dag",
        "cycle",
        "missing dependency",
        "blocked dependency",
        "lane blocked",
        "architecture contradiction",
        "fundamental design",
    }
    split_markers = {"split", "too broad", "too large", "smaller story", "separate story", "multiple concerns"}
    modified_markers = {
        "drop",
        "waive",
        "defer",
        "out of scope",
        "later slice",
        "acceptance criteria",
        "criterion",
        "too strict",
        "impossible requirement",
    }
    debt_markers = {"accept with debt", "known gap", "known limitation", "missing functionality", "minor missing", "debt"}

    top_category = str(top_failure.get("failure_category") or "")
    top_class = str(top_failure.get("failure_class") or "")
    if top_category == "dependency_or_architecture":
        action = ESCALATE_TO_REPLAN
        failure_category = "dependency_or_architecture"
        diagnosis = f"Typed failure classification `{top_class}` points to stale, dependency, DAG, or architecture structure."
        confidence = "high"
        rationale.append("Typed gate/advisor evidence takes precedence over keyword retry heuristics.")
        next_steps = [
            "Review the typed failure source in CI, merge, integration, or issue-advisor artifacts.",
            "Run wrkflw:replan with explicit dependency rewrite, skip, or reorder directives if the remaining DAG needs mutation.",
        ]
    elif top_category == "scope_too_large":
        action = SPLIT
        failure_category = "scope_too_large"
        diagnosis = f"Typed failure classification `{top_class}` indicates the story should be split before another retry."
        confidence = "high"
        rationale.append("Typed failure evidence indicates the current slice is too broad.")
        next_steps = [
            "Split the active story into smaller DAG nodes.",
            "Run dag-sync and retry the first ready sub-story.",
        ]
    elif top_category == "environment_failure":
        action = RETRY_APPROACH
        failure_category = "environment_failure"
        diagnosis = f"Typed failure classification `{top_class}` points to environment or infrastructure repair before retry."
        confidence = "medium"
        rationale.append("AgentField-style operational failures should be repaired or rerun before broader replanning.")
        next_steps = [
            "Repair or rerun the failing environment, CI, merge, or integration step.",
            "Avoid changing story scope unless the same failure recurs after environment repair.",
        ]
    elif top_category in {"policy_or_security_block", "merge_conflict"}:
        action = RETRY_APPROACH
        failure_category = top_category
        diagnosis = f"Typed failure classification `{top_class}` requires explicit gate resolution before another approval attempt."
        confidence = "high"
        rationale.append("Typed policy or merge failures should be resolved directly instead of hidden as generic implementation failure.")
        next_steps = [
            "Resolve the policy, scope, or merge conflict evidence in the source gate artifact.",
            "Rerun the relevant gate and feedback-synth before approval.",
        ]
    elif node_status == "blocked" or recommendation == "replan" or has_any(corpus, structural_markers):
        action = ESCALATE_TO_REPLAN
        failure_category = "dependency_or_architecture"
        diagnosis = "The failure points at dependency, DAG, lane, or architecture structure rather than only implementation technique."
        confidence = "high"
        rationale.append("SWE-AF escalates when missing upstream work or a fundamental DAG issue prevents local progress.")
        next_steps = [
            "Review dag-validation.md, dag.json, and execution-path.json for structural mismatch.",
            "Rework story slicing or DAG dependencies before another implementation attempt.",
            "Record any accepted restructuring decision in decisions.md or team-minutes.md.",
        ]
    elif recommendation == "split" or has_any(corpus, split_markers):
        action = SPLIT
        failure_category = "scope_too_large"
        diagnosis = "The active story is carrying multiple concerns or too much scope for one safe retry."
        confidence = "high"
        rationale.append("SWE-AF splits when the coding loop reveals the issue is too broad for a single agent pass.")
        next_steps = [
            "Split the active story into smaller DAG nodes with disjoint acceptance criteria.",
            "Run dag-sync and execution-path after updating stories.md and story files.",
            "Retry only the first ready sub-story.",
        ]
    elif maxed and (debt or repeated_issue_detected(repeated_inputs) or has_any(corpus, debt_markers)):
        action = ACCEPT_WITH_DEBT
        failure_category = "stuck_loop_or_known_gap"
        diagnosis = "The advisor retry budget is effectively exhausted and the remaining gap should be explicit debt, not another blind retry."
        confidence = "medium"
        rationale.append("SWE-AF prefers accepting with debt over repeated retries on the final advisor invocation when progress is close enough.")
        next_steps = [
            "Record or accept the remaining gap with wrkflw:debt-record.",
            "Keep release planning blocked until high/critical debt is resolved or explicitly accepted.",
            "Rerun feedback-synth after debt is recorded.",
        ]
    elif has_any(corpus, modified_markers):
        action = RETRY_MODIFIED
        failure_category = "acceptance_criteria_mismatch"
        diagnosis = "The failure appears tied to acceptance scope rather than only implementation technique."
        confidence = "medium"
        rationale.append("SWE-AF retries with modified criteria when the issue contract is over-constrained, wrong, or partly out of scope.")
        next_steps = [
            "Review the proposed modified acceptance criteria below.",
            "Update story enrichment explicitly if the product owner agrees.",
            "Retry implementation against the modified scope and record dropped criteria as debt when needed.",
        ]
    elif debt or recommendation == "block" or has_any(corpus, debt_markers):
        action = ACCEPT_WITH_DEBT if maxed else RETRY_APPROACH
        if action == ACCEPT_WITH_DEBT:
            failure_category = "known_gap"
            diagnosis = "The remaining issue is better tracked as explicit debt than retried again."
            confidence = "medium"
            rationale.append("Blocking debt or known gaps require a recorded acceptance path before release.")
            next_steps = [
                "Use wrkflw:debt-record to record the remaining gap.",
                "Rerun feedback-synth and issue-advisor if the gate is still blocked.",
            ]
        else:
            failure_category = "known_gap"
            diagnosis = "There is blocking debt or gap evidence, but one focused retry remains before accepting debt."
            rationale.append("The first advisor pass should attempt a corrected approach before debt acceptance.")
            next_steps = [
                "Retry with the specific findings and debt evidence visible to the implementer.",
                "If the same blocker persists, rerun issue-advisor and expect an accept-with-debt path.",
            ]
    elif blockers or open_blocking_findings(findings) or open_blocking_conflicts(conflicts) or recommendation in {"fix", "block"}:
        action = RETRY_APPROACH
        failure_category = "implementation"
        diagnosis = "The evidence indicates fixable implementation, test, merge, or review blockers."
        rationale.append("SWE-AF retries the approach when the issue is code/test/process execution rather than story structure.")
        next_steps = [
            "Retry the implementation using the evidence list as the bounded fix target.",
            "Run merge-gate, merge-apply, integration-gate, and feedback-synth after changes.",
            "Rerun issue-advisor if the same blocker recurs.",
        ]
    else:
        action = RETRY_APPROACH
        failure_category = "insufficient_evidence"
        diagnosis = "No structural blocker is visible; retry with a narrower implementation plan and fresh validation."
        rationale.append("The least disruptive forward path is a focused retry with current acceptance criteria.")
        next_steps = [
            "Give the implementer the current story, memory.md, and validation commands.",
            "Sync review evidence after the retry.",
        ]

    kept, dropped = modified_acceptance_criteria(sections, corpus)
    escalation_context = [
        item
        for item in [
            f"DAG node status is `{node_status}`." if node_status else "",
            dag_summary,
            f"Feedback synthesis recommends `{recommendation}`." if recommendation else "",
        ]
        if item
    ]
    payload: dict[str, object] = {
        "schema_version": 1,
        "workflow_slug": slug,
        "generated_at": utc_now(),
        "active_story": story,
        "advisor_invocation": invocation,
        "max_advisor_invocations": MAX_ADVISOR_INVOCATIONS,
        "action": action,
        "decision_source": "deterministic",
        "failure_category": failure_category,
        "failure_diagnosis": diagnosis,
        "confidence": confidence,
        "summary": diagnosis,
        "rationale": rationale,
        "next_steps": next_steps,
        "evidence": evidence,
        "previous_adaptations": previous_adaptations[-5:],
        "inputs": {
            "role_review_count": len(reviews),
            "review_finding_count": len(findings),
            "conflict_count": len(conflicts),
            "gate_blocker_count": len(blockers),
            "verify_fix_task_count": verify_task_count,
            "ci_fix_task_count": ci_task_count,
            "blocking_debt_count": len(debt),
            "memory_summary": memory_summary,
            "accounting_summary": accounting_summary,
            "failure_class_count": len(failure_classifications),
            "top_failure_class": top_failure.get("failure_class", ""),
            "top_failure_category": top_failure.get("failure_category", ""),
        },
        "failure_class": top_failure.get("failure_class", ""),
        "failure_classification": top_failure,
        "failure_classifications": failure_classifications,
        "new_approach": "Retry only the evidence-backed blocker set with current acceptance criteria." if action == RETRY_APPROACH else "",
        "approach_changes": next_steps if action == RETRY_APPROACH else [],
        "suggested_debt": suggested_debt_from_evidence(story, findings, conflicts, debt_summary),
        "debt_entries": suggested_debt_from_evidence(story, findings, conflicts, debt_summary) if action == ACCEPT_WITH_DEBT else [],
        "missing_functionality": [item.get("summary", "") for item in suggested_debt_from_evidence(story, findings, conflicts, debt_summary)],
        "modified_acceptance_criteria": kept,
        "dropped_criteria": dropped,
        "sub_issues": split_suggestions(story, sections) if action == SPLIT else [],
        "sub_stories": split_suggestions(story, sections) if action == SPLIT else [],
        "escalation_context": escalation_context if action == ESCALATE_TO_REPLAN else [],
        "suggested_restructuring": escalation_context if action == ESCALATE_TO_REPLAN else [],
        "dag_impact": escalation_context,
        "downstream_impact": "Downstream stories may inherit debt or blocked dependencies; run dag-sync after accepting any advisor action.",
        "input_hashes": input_hashes(root, slug),
    }
    if note and note.strip():
        payload["operator_note"] = note.strip()
    return payload


def render_markdown(payload: dict[str, object]) -> str:
    evidence = payload.get("evidence", [])
    rationale = payload.get("rationale", [])
    next_steps = payload.get("next_steps", [])
    suggested_debt = payload.get("suggested_debt", [])
    modified = payload.get("modified_acceptance_criteria", [])
    dropped = payload.get("dropped_criteria", [])
    sub_issues = payload.get("sub_issues", [])
    escalation = payload.get("escalation_context", [])
    inputs = payload.get("inputs", {})
    inputs = inputs if isinstance(inputs, dict) else {}
    lines = [
        "# Issue Advisor",
        "",
        f"- Workflow slug: {payload.get('workflow_slug', '-')}",
        f"- Generated at: {payload.get('generated_at', '-')}",
        f"- Active story: {payload.get('active_story', '-') or '-'}",
        f"- Advisor invocation: {payload.get('advisor_invocation', 1)} of {payload.get('max_advisor_invocations', MAX_ADVISOR_INVOCATIONS)}",
        f"- Action: {payload.get('action', '-')}",
        f"- Failure class: {payload.get('failure_class', '-') or '-'}",
        f"- Failure category: {payload.get('failure_category', '-') or '-'}",
        f"- Summary: {payload.get('summary', '-')}",
        "",
        "## Rationale",
    ]
    lines.extend(f"- {item}" for item in rationale if str(item).strip()) if isinstance(rationale, list) and rationale else lines.append("- none")
    lines.extend(["", "## Evidence"])
    lines.extend(f"- {item}" for item in evidence if str(item).strip()) if isinstance(evidence, list) and evidence else lines.append("- no blocking evidence found")
    lines.extend(["", "## Next Steps"])
    lines.extend(f"- {item}" for item in next_steps if str(item).strip()) if isinstance(next_steps, list) and next_steps else lines.append("- none")
    lines.extend(["", "## Proposed Acceptance Criteria"])
    lines.extend(f"- {item}" for item in modified if str(item).strip()) if isinstance(modified, list) and modified else lines.append("- no change proposed")
    lines.extend(["", "## Dropped Criteria To Record As Debt"])
    lines.extend(f"- {item}" for item in dropped if str(item).strip()) if isinstance(dropped, list) and dropped else lines.append("- none")
    lines.extend(["", "## Suggested Debt"])
    if isinstance(suggested_debt, list) and suggested_debt:
        for item in suggested_debt:
            if not isinstance(item, dict):
                continue
            lines.append(
                "- "
                + "; ".join(
                    part
                    for part in [
                        f"type={item.get('debt_type', '-')}",
                        f"severity={item.get('severity', '-')}",
                        f"summary={item.get('summary', '-')}",
                        f"owner={item.get('owner', '-')}",
                    ]
                    if part
                )
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Split Candidates"])
    if isinstance(sub_issues, list) and sub_issues:
        for item in sub_issues:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('title', '-')}")
            criteria = item.get("acceptance_criteria", [])
            if isinstance(criteria, list):
                lines.extend(f"  - AC: {criterion}" for criterion in criteria if str(criterion).strip())
    else:
        lines.append("- none")
    lines.extend(["", "## Escalation Context"])
    lines.extend(f"- {item}" for item in escalation if str(item).strip()) if isinstance(escalation, list) and escalation else lines.append("- none")
    lines.extend(
        [
            "",
            "## Input Counts",
            f"- Role reviews: {inputs.get('role_review_count', 0)}",
            f"- Review findings: {inputs.get('review_finding_count', 0)}",
            f"- Conflicts: {inputs.get('conflict_count', 0)}",
            f"- Gate blockers: {inputs.get('gate_blocker_count', 0)}",
            f"- Blocking debt: {inputs.get('blocking_debt_count', 0)}",
            "",
        ]
    )
    return "\n".join(lines)


def ensure_issue_advisor_artifact(root: Path, slug: str) -> None:
    path = issue_advisor_summary_path(root, slug)
    if path.exists():
        return
    write_text_if_changed(
        path,
        f"""# Issue Advisor

- Workflow slug: {slug}
- Action:
- Summary:

## Rationale
- none

## Evidence
- none

## Next Steps
- none
""",
    )


def run_issue_advisor(root: Path, slug: str, note: str | None = None) -> dict[str, object]:
    story = active_story(root, slug)
    sections = extract_story_sections(root, slug, story)
    reviews = collect_role_reviews(root, slug, story)
    findings = collect_review_findings(root, slug, story)
    conflicts = collect_conflicts(root, slug, story)
    payload = decide(root, slug, story, note or "", reviews, findings, conflicts, sections)
    write_text_if_changed(issue_advisor_path(root, slug), json.dumps(payload, indent=2) + "\n")
    write_text_if_changed(issue_advisor_summary_path(root, slug), render_markdown(payload))
    append_adaptation_record(root, slug, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose stuck story evidence and recommend a SWE-AF-style recovery action.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    run_issue_advisor(Path(args.root).resolve(), args.slug, args.note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

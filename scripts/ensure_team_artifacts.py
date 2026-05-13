#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_agent_result_schema import ensure_agent_result_schema_artifacts
from workflow_accounting import ensure_accounting_artifacts
from workflow_ci_feedback import ensure_ci_feedback_artifact
from workflow_debt import ensure_debt_artifacts
from workflow_integration_gate import ensure_integration_gate_artifacts
from workflow_issue_advisor import ensure_issue_advisor_artifact
from workflow_memory import ensure_memory_artifacts
from workflow_replanner import ensure_replan_artifact
from workflow_runtime_contract import (
    GENERATED_SHARED_ARTIFACTS,
    REQUIRED_SHARED_INPUTS,
    REQUIRED_SHARED_OUTPUTS,
    format_shared_items,
)
from workflow_verify_fix import ensure_verify_fix_artifact


def write_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def write_json_if_missing(path: Path, payload: dict[str, object]) -> None:
    write_if_missing(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def touch_if_missing(path: Path) -> None:
    write_if_missing(path, "")


def not_recorded_payload(slug: str, artifact: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "workflow_slug": slug,
        "artifact": artifact,
        "status": "not_recorded",
        "summary": "This workflow artifact has not been recorded yet.",
    }


def default_team_config() -> str:
    return """# Team Config

- Team mode: multi-agent-engineering-team
- Team size: 4
- Product owner required: true
- Reviewer required: true
- Parallel implementation slots: 1
- Default approval policy: product-owner-and-reviewer-signoff
- Override instructions: Edit this file to change default team size, structure, and responsibilities. Use `team-overrides.md` inside a workflow slug for epic-specific changes.

## Role: Product Owner

- Slot: product-owner
- Enabled: true
- Responsibilities:
  - preserve design intent and scope boundaries
  - approve story scope, acceptance clarity, and out-of-scope decisions
  - challenge spec drift before workflow approval
  - record independent product review verdicts before reconciliation
- Default write scope:
  - `.workflow/<slug>/decisions.md`
  - `.workflow/<slug>/review-log.md`
  - `.workflow/<slug>/role-reviews.md`
  - `.workflow/<slug>/conflicts.md`
  - `.workflow/<slug>/assumptions.md`
  - `.workflow/<slug>/execution-board.md`
- Default review authority: required at capability-review, epic-shaping, story-slicing, and release-planning

## Role: Tech Lead

- Slot: tech-lead
- Enabled: true
- Responsibilities:
  - decompose work into PR-sized slices
  - define implementation boundaries and interface decisions
  - coordinate implementer and reviewer handoffs
  - record architecture and sequencing dissent before implementation approval
- Default write scope:
  - `.workflow/<slug>/execution-board.md`
  - `.workflow/<slug>/decisions.md`
  - `.workflow/<slug>/role-reviews.md`
  - `.workflow/<slug>/conflicts.md`
  - `.workflow/<slug>/assumptions.md`
  - code and tests when explicitly taking implementation ownership
- Default review authority: required before implementation-planning approval

## Role: Implementer

- Slot: implementer-1
- Enabled: true
- Responsibilities:
  - implement assigned code and tests
  - report files changed, validation run, and unresolved risks
  - challenge feasibility, ownership, and maintainability assumptions
- Default write scope:
  - code, tests, fixtures, docs in assigned ownership area
  - `.workflow/<slug>/execution-board.md`
  - `.workflow/<slug>/role-reviews.md`
  - `.workflow/<slug>/conflicts.md`
  - `.workflow/<slug>/assumptions.md`
- Default review authority: none

## Role: Reviewer QA

- Slot: reviewer-qa
- Enabled: true
- Responsibilities:
  - review implementation against design, workflow, and OpenSpec
  - identify regressions, missing tests, and acceptance mismatches
  - challenge weak assumptions before approval
  - run bounded red-team checks before spec and PR approval
- Default write scope:
  - `.workflow/<slug>/review-log.md`
  - `.workflow/<slug>/role-reviews.md`
  - `.workflow/<slug>/conflicts.md`
  - `.workflow/<slug>/assumptions.md`
  - `.workflow/<slug>/execution-board.md`
- Default review authority: required before review and release-planning approval

## Optional Expansion Patterns

- To run a 3-person team:
  - keep `product-owner`, `tech-lead`, and `reviewer-qa`
  - let `tech-lead` temporarily absorb implementation ownership
- To run a 5-person team:
  - increase `Team size`
  - clone the `Implementer` role into `implementer-2`
  - set `Parallel implementation slots: 2`
"""


def default_team_overrides(slug: str) -> str:
    return f"""# Team Overrides

- Workflow slug: {slug}
- Team size override:
- Parallel implementation slots override:
- Notes:

## Role Changes

- Product Owner:
- Tech Lead:
- Implementer 1:
- Implementer 2:
- Reviewer QA:
"""


def default_agent_assignments(slug: str) -> str:
    return f"""# Agent Assignments

- Workflow slug: {slug}
- Team config source: `.workflow/team-config.md`
- Override source: `.workflow/{slug}/team-overrides.md`

| Role | Slot | Responsibility Focus | Default Ownership | Allowed Write Paths | Status |
| --- | --- | --- | --- | --- | --- |
| Product Owner | product-owner | design intent, scope, acceptance, sequencing | workflow and review artifacts only | .workflow/<slug>/decisions.md, .workflow/<slug>/review-log.md, .workflow/<slug>/role-reviews.md, .workflow/<slug>/conflicts.md, .workflow/<slug>/assumptions.md, .workflow/<slug>/execution-board.md | planned |
| Tech Lead | tech-lead | architecture, decomposition, interfaces, handoffs | workflow artifacts and shared technical decisions | .workflow/<slug>/execution-board.md, .workflow/<slug>/decisions.md, .workflow/<slug>/role-reviews.md, .workflow/<slug>/conflicts.md, .workflow/<slug>/assumptions.md | planned |
| Implementer 1 | implementer-1 | code and tests for the active slice | assigned code/tests only | declare concrete module/file prefixes before parallel team-run | planned |
| Implementer 2 | implementer-2 | optional parallel code and tests for a second slice | assigned code/tests only | declare concrete module/file prefixes before parallel team-run | optional |
| Reviewer QA | reviewer-qa | review, challenge, regression and test checks | review artifacts only | .workflow/<slug>/review-log.md, .workflow/<slug>/role-reviews.md, .workflow/<slug>/conflicts.md, .workflow/<slug>/assumptions.md, .workflow/<slug>/execution-board.md | planned |

## Assignment Rules

- Do not let every role write to every file.
- Treat workflow/OpenSpec/design artifacts as the shared contract.
- Keep implementer ownership disjoint when parallel implementation slots are greater than 1.
- Express write scope as comma-separated path prefixes in `Allowed Write Paths`.
- Record independent role verdicts in `role-reviews.md` before reconciliation when a role is reviewing scope, spec, implementation plan, or release readiness.
"""


def default_execution_board(slug: str) -> str:
    return f"""# Execution Board

- Workflow slug: {slug}
- Active story:
- Active owner:
- Current handoff:

| Work Item | Owner Role | Status | Blocked By | Reviewer | Notes |
| --- | --- | --- | --- | --- | --- |
| Story scope and acceptance review | Product Owner | pending | | Reviewer QA | |
| Technical decomposition | Tech Lead | pending | | Product Owner | |
| Implementation slice 1 | Implementer 1 | pending | | Reviewer QA | |
| Implementation slice 2 | Implementer 2 | optional | | Reviewer QA | |
| Review and challenge | Reviewer QA | pending | | Product Owner | |

## Status Vocabulary

- `planned`
- `in-progress`
- `blocked`
- `in-review`
- `done`
"""


def default_review_log(slug: str) -> str:
    return f"""# Review Log

- Workflow slug: {slug}
- Current story:

## Review Policy

- Product Owner challenges scope and design drift.
- Reviewer QA challenges behavior, regressions, and missing tests.
- Tech Lead resolves ownership and integration gaps.

## Findings

| Date | Role | Severity | Finding | Resolution |
| --- | --- | --- | --- | --- |
"""


def default_role_reviews(slug: str) -> str:
    return f"""# Role Reviews

- Workflow slug: {slug}
- Current story:

## Review Protocol

- Review the active artifact independently before adopting another role's conclusion when feasible.
- Use `approve`, `approve-with-changes`, or `block` as the verdict.
- Mark unsupported claims as assumptions and cite evidence for technical or product claims.

## Reviews

| Date | Story | Role | Verdict | Missing Requirements | Incorrect Assumptions | Risks | Questions | Suggested Changes | Evidence | Red-team Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""


def default_conflicts(slug: str) -> str:
    return f"""# Conflict Register

- Workflow slug: {slug}
- Current story:

## Rules

- Do not hide unresolved disagreement inside prose.
- Blocking conflicts keep the current gate blocked or pending until the conflict row has a concrete resolution.

## Conflicts

| Date | Story | Raised By | Severity | Conflict | Options | Recommendation | Resolution | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""


def default_assumptions(slug: str) -> str:
    return f"""# Assumption Ledger

- Workflow slug: {slug}
- Current story:

## Rules

- Record assumptions that affect scope, architecture, data, security, testing, or rollout.
- Include a validation step whenever the impact of being wrong is material.

## Assumptions

| Date | Story | Source | Confidence | Assumption | Impact If Wrong | Validation Step |
| --- | --- | --- | --- | --- | --- | --- |
"""


def default_team_minutes(slug: str) -> str:
    return f"""# Team Minutes

- Workflow slug: {slug}
- Current story:

## Interaction Log

| Timestamp | Kind | Participants | Summary | Follow-up |
| --- | --- | --- | --- | --- |
"""


def default_agent_sync_ledger() -> str:
    return """# Agent Sync Ledger

| Timestamp | Source | Digest | Role | Status |
| --- | --- | --- | --- | --- |
"""


def default_feedback_synthesis(slug: str) -> str:
    return f"""# Feedback Synthesis

- Workflow slug: {slug}
- Recommendation:
- Status:
- Summary:

## Reasons
- none

## Blockers
- none

## Warnings
- none
"""


def default_issue_advisor(slug: str) -> str:
    return f"""# Issue Advisor

- Workflow slug: {slug}
- Action:
- Summary:

## Rationale
- none

## Evidence
- none

## Next Steps
- none
"""


def default_replan(slug: str) -> str:
    return f"""# Replan

- Workflow slug: {slug}
- Status:
- Plan type:
- Summary:

## Proposed Changes
- none

## Blockers
- none
"""


def default_runtime_contract(slug: str) -> str:
    return f"""# Runtime Contract

- Workflow slug: {slug}
- Runtime mode: file-driven
- Delegated execution ready: false
- Spawn policy: no automatic agent spawning; explicit orchestration only
- Dispatch artifact: `.workflow/{slug}/team-dispatch.md`
- Dispatch directory: `.workflow/{slug}/dispatch/`
- Agent results directory: `.workflow/{slug}/agent-results`
- Agent sync ledger: `.workflow/{slug}/agent-sync-ledger.md`
- State authority: `scripts/handle_workflow_command.py`
- Active story:
- Active owner:
- Current handoff:
- Recorded review roles:
- Recorded role review roles:
- Open blocking conflicts:
- Assumption entries:
- Blocking technical debt:
- Shared learning memory:
- Invocation accounting:
- Required shared inputs: {format_shared_items(REQUIRED_SHARED_INPUTS)}
- Generated shared artifacts: {format_shared_items(GENERATED_SHARED_ARTIFACTS)}
- Required shared outputs: {format_shared_items(REQUIRED_SHARED_OUTPUTS)}

## Team Runtime Rules

- Only the workflow orchestrator updates canonical `state.md`.
- Product Owner and Reviewer QA provide challenge and signoff evidence through `review-log.md`.
- All roles record independent review verdicts in `role-reviews.md` when reviewing artifacts.
- Unresolved disagreement is tracked in `conflicts.md`; important assumptions are tracked in `assumptions.md`.
- Active role ownership and handoffs stay visible in `execution-board.md`.
- Team conversations, challenge outcomes, and handoff notes should be summarized in `team-minutes.md`.
- This contract prepares the workflow for future delegated multi-agent execution without requiring it today.
"""


def ensure_on_demand_artifacts(root: Path, slug: str) -> None:
    wf = root / ".workflow" / slug
    records = wf / "records"
    for relative in [
        "records/memory.jsonl",
        "records/debt.jsonl",
        "records/invocations.jsonl",
        "records/adaptations.jsonl",
        "records/replans.jsonl",
        "records/verify-fix.jsonl",
        "records/ci-feedback.jsonl",
        "records/integration-gate-runs.jsonl",
        "records/agent-result-validation.jsonl",
    ]:
        touch_if_missing(wf / relative)
    for relative in ["agent-results", "dispatch", "parallel-dispatch", "ci-runs", "integration-runs", "replans"]:
        (wf / relative).mkdir(parents=True, exist_ok=True)
    (records).mkdir(parents=True, exist_ok=True)
    write_json_if_missing(wf / "feedback-synthesis.json", not_recorded_payload(slug, "feedback-synthesis"))
    write_json_if_missing(wf / "issue-advisor.json", not_recorded_payload(slug, "issue-advisor"))
    write_json_if_missing(wf / "replan.json", not_recorded_payload(slug, "replan"))
    write_json_if_missing(wf / "verify-fix.json", not_recorded_payload(slug, "verify-fix"))
    write_json_if_missing(wf / "ci-feedback.json", not_recorded_payload(slug, "ci-feedback"))
    write_json_if_missing(wf / "integration-test-gate.json", not_recorded_payload(slug, "integration-test-gate"))
    write_if_missing(
        wf / "integration-test-gate.md",
        f"""# Integration Test Gate

- Workflow slug: {slug}
- Status: not_recorded
- Summary: This workflow artifact has not been recorded yet.

## Blockers
- none

## Warnings
- none
""",
    )


def default_dependencies(slug: str) -> str:
    return f"""# Dependencies

- Workflow slug: {slug}
- Depends on:
- Satisfies: {slug}
- Blocked by:
- Unlocks:
- Notes:
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure team execution artifacts exist for a workflow.")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    workflow_root = root / ".workflow"
    wf = workflow_root / args.slug
    wf.mkdir(parents=True, exist_ok=True)

    write_if_missing(workflow_root / "team-config.md", default_team_config())
    write_if_missing(wf / "team-overrides.md", default_team_overrides(args.slug))
    write_if_missing(wf / "agent-assignments.md", default_agent_assignments(args.slug))
    write_if_missing(wf / "execution-board.md", default_execution_board(args.slug))
    write_if_missing(wf / "review-log.md", default_review_log(args.slug))
    write_if_missing(wf / "role-reviews.md", default_role_reviews(args.slug))
    write_if_missing(wf / "conflicts.md", default_conflicts(args.slug))
    write_if_missing(wf / "assumptions.md", default_assumptions(args.slug))
    write_if_missing(wf / "feedback-synthesis.md", default_feedback_synthesis(args.slug))
    write_if_missing(wf / "issue-advisor.md", default_issue_advisor(args.slug))
    write_if_missing(wf / "replan.md", default_replan(args.slug))
    write_if_missing(wf / "team-minutes.md", default_team_minutes(args.slug))
    write_if_missing(wf / "runtime-contract.md", default_runtime_contract(args.slug))
    write_if_missing(wf / "dependencies.md", default_dependencies(args.slug))
    write_if_missing(wf / "agent-sync-ledger.md", default_agent_sync_ledger())
    (wf / "agent-results").mkdir(parents=True, exist_ok=True)
    ensure_memory_artifacts(root, args.slug)
    ensure_accounting_artifacts(root, args.slug)
    ensure_debt_artifacts(root, args.slug)
    ensure_issue_advisor_artifact(root, args.slug)
    ensure_replan_artifact(root, args.slug)
    ensure_verify_fix_artifact(root, args.slug)
    ensure_ci_feedback_artifact(root, args.slug)
    ensure_agent_result_schema_artifacts(root, args.slug)
    ensure_integration_gate_artifacts(root, args.slug)
    ensure_on_demand_artifacts(root, args.slug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

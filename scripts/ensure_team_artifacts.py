#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def write_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


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
- Default write scope:
  - `.workflow/<slug>/decisions.md`
  - `.workflow/<slug>/review-log.md`
  - `.workflow/<slug>/execution-board.md`
- Default review authority: required at capability-review, epic-shaping, story-slicing, and release-planning

## Role: Tech Lead

- Slot: tech-lead
- Enabled: true
- Responsibilities:
  - decompose work into PR-sized slices
  - define implementation boundaries and interface decisions
  - coordinate implementer and reviewer handoffs
- Default write scope:
  - `.workflow/<slug>/execution-board.md`
  - `.workflow/<slug>/decisions.md`
  - code and tests when explicitly taking implementation ownership
- Default review authority: required before implementation-planning approval

## Role: Implementer

- Slot: implementer-1
- Enabled: true
- Responsibilities:
  - implement assigned code and tests
  - report files changed, validation run, and unresolved risks
- Default write scope:
  - code, tests, fixtures, docs in assigned ownership area
  - `.workflow/<slug>/execution-board.md`
- Default review authority: none

## Role: Reviewer QA

- Slot: reviewer-qa
- Enabled: true
- Responsibilities:
  - review implementation against design, workflow, and OpenSpec
  - identify regressions, missing tests, and acceptance mismatches
  - challenge weak assumptions before approval
- Default write scope:
  - `.workflow/<slug>/review-log.md`
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
| Product Owner | product-owner | design intent, scope, acceptance, sequencing | workflow and review artifacts only | .workflow/<slug>/decisions.md, .workflow/<slug>/review-log.md, .workflow/<slug>/execution-board.md | planned |
| Tech Lead | tech-lead | architecture, decomposition, interfaces, handoffs | workflow artifacts and shared technical decisions | .workflow/<slug>/execution-board.md, .workflow/<slug>/decisions.md | planned |
| Implementer 1 | implementer-1 | code and tests for the active slice | assigned code/tests only | declare concrete module/file prefixes before parallel team-run | planned |
| Implementer 2 | implementer-2 | optional parallel code and tests for a second slice | assigned code/tests only | declare concrete module/file prefixes before parallel team-run | optional |
| Reviewer QA | reviewer-qa | review, challenge, regression and test checks | review artifacts only | .workflow/<slug>/review-log.md, .workflow/<slug>/execution-board.md | planned |

## Assignment Rules

- Do not let every role write to every file.
- Treat workflow/OpenSpec/design artifacts as the shared contract.
- Keep implementer ownership disjoint when parallel implementation slots are greater than 1.
- Express write scope as comma-separated path prefixes in `Allowed Write Paths`.
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


def default_team_minutes(slug: str) -> str:
    return f"""# Team Minutes

- Workflow slug: {slug}
- Current story:

## Interaction Log

| Timestamp | Kind | Participants | Summary | Follow-up |
| --- | --- | --- | --- | --- |
"""


def default_runtime_contract(slug: str) -> str:
    return f"""# Runtime Contract

- Workflow slug: {slug}
- Runtime mode: file-driven
- Delegated execution ready: false
- Spawn policy: no automatic agent spawning; explicit orchestration only
- Dispatch artifact: `.workflow/{slug}/team-dispatch.md`
- Dispatch directory: `.workflow/{slug}/dispatch/`
- State authority: `scripts/handle_workflow_command.py`
- Active story:
- Active owner:
- Current handoff:
- Required shared inputs: design-slice.md, state.md, stories.md, execution-board.md, review-log.md, links.md, workflow-contract.md
- Required shared outputs: code/tests/docs in assigned scope, review-log.md evidence, execution-board.md notes, team-minutes.md updates

## Team Runtime Rules

- Only the workflow orchestrator updates canonical `state.md`.
- Product Owner and Reviewer QA provide challenge and signoff evidence through `review-log.md`.
- Active role ownership and handoffs stay visible in `execution-board.md`.
- Team conversations, challenge outcomes, and handoff notes should be summarized in `team-minutes.md`.
- This contract prepares the workflow for future delegated multi-agent execution without requiring it today.
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
    write_if_missing(wf / "team-minutes.md", default_team_minutes(args.slug))
    write_if_missing(wf / "runtime-contract.md", default_runtime_contract(args.slug))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

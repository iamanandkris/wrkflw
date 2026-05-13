# Reviewer QA Dispatch Packet

- Workflow slug: demo
- Role: Reviewer QA
- Slot: reviewer-qa
- Recommended agent type: default
- Active story: Story 2
- Current stage: implementation-planning
- Active owner: Tech Lead
- Current handoff: Tech Lead -> Implementer 1
- Team size: 4
- Parallel implementation slots: 1
- Responsibility focus: review, challenge, regression and test checks
- Default ownership: review artifacts only
- Allowed write paths: .workflow/<slug>/review-log.md, .workflow/<slug>/role-reviews.md, .workflow/<slug>/conflicts.md, .workflow/<slug>/assumptions.md, .workflow/<slug>/execution-board.md
- Result envelope path: .workflow/demo/agent-results/reviewer-qa.md
- Existing review roles: -
- DAG level: 2
- DAG status: active
- DAG risk: high
- Needs deeper QA: yes
- Depends on: story-1
- Downstream dependents: story-4

## Shared Inputs
- `.workflow/<slug>/design-slice.md`
- `.workflow/<slug>/state.md`
- `.workflow/<slug>/stories.md`
- `.workflow/<slug>/dag.json`
- `.workflow/<slug>/dag.md`
- `.workflow/<slug>/execution-board.md`
- `.workflow/<slug>/review-log.md`
- `.workflow/<slug>/role-reviews.md`
- `.workflow/<slug>/conflicts.md`
- `.workflow/<slug>/assumptions.md`
- `.workflow/<slug>/team-minutes.md`
- `.workflow/<slug>/links.md`
- `.workflow/<slug>/workflow-contract.md`

## Story Context
Story 2

## Scope
-

## Role Mission
- Review current work against design, workflow intent, and acceptance criteria.
- Look for regressions, missing tests, and weak assumptions.
- Run a bounded red-team pass for the most likely product, test, implementation, security, or rollout failure.
- Record findings in review-log.md and challenge the work when needed.
- Treat this as a DAG-flagged high-risk story; deepen review before approving.

## Acceptance Focus
- Approval policy rejects invalid transitions.

## Test Focus
- Add a regression test for approval-blocked transitions.

## Risks
- Approval policy must not drift across handlers.

## Execution Rules
- You are not alone in the codebase; accommodate other role lanes instead of reverting them.
- Keep changes within your role ownership and the active story boundary.
- Stay inside these allowed write paths: .workflow/<slug>/review-log.md, .workflow/<slug>/role-reviews.md, .workflow/<slug>/conflicts.md, .workflow/<slug>/assumptions.md, .workflow/<slug>/execution-board.md
- Do not edit canonical `state.md` directly.
- Record independent review evidence before reconciliation when you are reviewing an artifact.
- Mark unsupported claims as assumptions and cite evidence for product or technical claims.
- Put unresolved disagreement in conflict entries instead of burying it in prose.
- Summarize important discussions, decisions, and handoffs in `team-minutes.md`.
- When you finish or hand off, write the final report to `.workflow/demo/agent-results/reviewer-qa.md` and return the same content in chat.
- Keep the final report schema exact so the orchestrator can ingest it without guessing.
- Surface review verdicts through `role-reviews.md`, disagreements through `conflicts.md`, assumptions through `assumptions.md`, and signoff findings through `review-log.md` as appropriate.

## Final Report Template
```text
Role: Reviewer QA
Status: done
Verdict: approve
Summary: <one concise summary of what changed or what was verified>
Files changed:
- <path>
Validation run:
- <command and result>
Missing requirements:
- none
Incorrect assumptions:
- none
Risks:
- none
Questions:
- none
Suggested changes:
- none
Evidence:
- <file, artifact, test, or user statement>
Conflict entries:
- none
Assumption updates:
- none
Red-team notes:
- none
Findings:
- none
Follow-up: <next handoff or approval request>
```

Notes for the report:
- Use one of: `planned`, `in-progress`, `in-review`, `done`, `blocked`, `optional`.
- Use one verdict: `approve`, `approve-with-changes`, or `block`.
- If you did not change files, write `Files changed:` then `- none`.
- Keep each review section present. Use `- none` when there is no content.
- For conflict entries, prefix severity when useful, for example `- high: raw SQL in MVP expands security scope`.
- For assumption updates, include the assumption and validation step when known.
- If you found issues, put each finding on its own bullet. Prefix severity when helpful, for example `- high: task contract is still missing`.
- If you are a reviewer or product owner and no serious issues remain, write `Findings:` then `- none`.

## Orchestrator Sync
After this report returns, the orchestrator should run:
```text
wrkflw:team-sync-all
```

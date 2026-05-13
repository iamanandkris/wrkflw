# Story 2: Add Approval Policy Parallel Dispatch

- Workflow slug: demo
- DAG node: story-2
- Story: Story 2
- DAG level: 2
- DAG risk: high
- Needs deeper QA: yes
- Allowed write paths: src/approval, tests/approval
- Result envelope path: .workflow/demo/parallel-dispatch/story-2/agent-result.md

## Scope
Add Approval Policy

## Acceptance Focus
- Approval policy rejects invalid transitions.

## Test Focus
- Add a regression test for approval-blocked transitions.

## Risks
- Approval policy must not drift across handlers.

## Execution Rules
- You are not alone in the codebase; this is a parallel level dispatch.
- Stay inside this story's allowed write paths.
- Do not edit canonical `state.md` directly.
- Return a structured final report for `wrkflw:team-sync-all`.

## Final Report Template
```text
Role: Implementer 1
Status: done
Verdict: approve
Summary: <what changed>
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
Follow-up: Reviewer QA review this story packet
```

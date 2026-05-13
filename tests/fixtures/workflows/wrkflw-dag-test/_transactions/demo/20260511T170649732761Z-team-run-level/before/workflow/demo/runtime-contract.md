# Runtime Contract

- Assumption entries: 0
- Open blocking conflicts: -
- Recorded role review roles: -
- Recorded review roles: -
- Workflow slug: demo
- Runtime mode: delegated-agent-team
- Delegated execution ready: true
- Spawn policy: explicit wrkflw:team-run
- Dispatch artifact: `.workflow/demo/team-dispatch.md`
- Dispatch directory: `.workflow/demo/dispatch/`
- Agent results directory: .workflow/demo/agent-results
- Agent sync ledger: .workflow/demo/agent-sync-ledger.md
- State authority: `scripts/handle_workflow_command.py`
- Active story: Story 2
- Active owner: Tech Lead
- Current handoff: Tech Lead -> Implementer 1
- Required shared inputs: design-slice.md, state.md, stories.md, execution-board.md, role-reviews.md, conflicts.md, assumptions.md, review-log.md, links.md, workflow-contract.md
- Required shared outputs: code/tests/docs in assigned scope, role-reviews.md verdicts, conflicts.md entries, assumptions.md updates, review-log.md evidence, execution-board.md notes, team-minutes.md updates

## Team Runtime Rules

- Only the workflow orchestrator updates canonical `state.md`.
- Product Owner and Reviewer QA provide challenge and signoff evidence through `review-log.md`.
- All roles record independent review verdicts in `role-reviews.md` when reviewing artifacts.
- Unresolved disagreement is tracked in `conflicts.md`; important assumptions are tracked in `assumptions.md`.
- Active role ownership and handoffs stay visible in `execution-board.md`.
- Team conversations, challenge outcomes, and handoff notes should be summarized in `team-minutes.md`.
- This contract prepares the workflow for future delegated multi-agent execution without requiring it today.

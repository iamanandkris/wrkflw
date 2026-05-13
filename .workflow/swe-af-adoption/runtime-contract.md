# Runtime Contract

- Workflow slug: swe-af-adoption
- Runtime mode: file-driven
- Delegated execution ready: false
- Spawn policy: no automatic agent spawning; explicit orchestration only
- Dispatch artifact: `.workflow/swe-af-adoption/team-dispatch.md`
- Dispatch directory: `.workflow/swe-af-adoption/dispatch/`
- Agent results directory: .workflow/swe-af-adoption/agent-results
- Agent sync ledger: .workflow/swe-af-adoption/agent-sync-ledger.md
- State authority: `scripts/handle_workflow_command.py`
- Active story: SWE-AF adoption team hardening fixes
- Active owner: Implementer 1
- Current handoff: Implementer 1 -> Reviewer QA
- Recorded review roles: -
- Recorded role review roles: -
- Open blocking conflicts: -
- Assumption entries: 0
- Blocking technical debt: -
- Shared learning memory: none
- Invocation accounting: none
- Required shared inputs: capabilities.md, context.md, design-slice.md, design-seed.md, state.md, history.md, dependencies.md, gates.md, memory.md, records/memory.jsonl, debt.md, records/debt.jsonl, accounting.json, accounting.md, records/invocations.jsonl, execution-board.md, agent-assignments.md, team-overrides.md, dispatch/, parallel-dispatch/, role-reviews.md, review-log.md, conflicts.md, assumptions.md, decisions.md, team-minutes.md, feedback-synthesis.json, feedback-synthesis.md, issue-advisor.json, issue-advisor.md, records/adaptations.jsonl, replan.json, replan.md, records/replans.jsonl, replans/, verify-fix.json, verify-fix.md, records/verify-fix.jsonl, ci-feedback.json, ci-feedback.md, ci-runs/, records/ci-feedback.jsonl, integration-test-allowlist.json, integration-test-allowlist.md, integration-test-gate.json, integration-test-gate.md, integration-runs/, records/integration-gate-runs.jsonl, agent-results/, agent-sync-ledger.md, agent-result-schema.md, schemas/agent-result.schema.json, records/agent-result-validation.jsonl, links.md, workflow-contract.md, runtime-contract.md
- Required shared outputs: code/tests/docs in assigned scope, records/memory.jsonl updates, memory.md summaries, records/debt.jsonl updates, debt.md summaries, records/invocations.jsonl updates, accounting.md summaries, role-reviews.md verdicts, conflicts.md entries, assumptions.md updates, review-log.md evidence, feedback-synthesis.json recommendations, feedback-synthesis.md recommendations, issue-advisor.json recovery advice, issue-advisor.md recovery advice, records/adaptations.jsonl updates, replan.json proposals/applications, replan.md proposals/applications, records/replans.jsonl updates, verify-fix.json findings, verify-fix.md findings, records/verify-fix.jsonl updates, ci-feedback.json findings, ci-feedback.md findings, records/ci-feedback.jsonl updates, merge-gate.json readiness evidence, merge-gate.md readiness evidence, merge-apply.json apply evidence, merge-apply.md apply evidence, integration-test-gate.json evidence, integration-test-gate.md evidence, integration-runs/ execution records, records/integration-gate-runs.jsonl updates, records/agent-result-validation.jsonl updates, agent-results/ envelopes, agent-sync-ledger.md updates, parallel-dispatch/ packets, dispatch/ packets, worktrees/manifest.json updates, execution-board.md notes, team-minutes.md updates
- Generated shared artifacts: stories.md, story-*.md, dag.json, dag.md, dag-validation.md, execution-path.json, execution-path.md, implementation-plan.md, release-plan.md, team-dispatch.md, dispatch/*.md, parallel-dispatch.json, parallel-dispatch.md, parallel-dispatch/*, worktrees/manifest.json, worktrees.md, merge-gate.json, merge-gate.md, merge-apply.json, merge-apply.md

## Team Runtime Rules

- Only the workflow orchestrator updates canonical `state.md`.
- Product Owner and Reviewer QA provide challenge and signoff evidence through `review-log.md`.
- All roles record independent review verdicts in `role-reviews.md` when reviewing artifacts.
- Unresolved disagreement is tracked in `conflicts.md`; important assumptions are tracked in `assumptions.md`.
- Active role ownership and handoffs stay visible in `execution-board.md`.
- Team conversations, challenge outcomes, and handoff notes should be summarized in `team-minutes.md`.
- This contract prepares the workflow for future delegated multi-agent execution without requiring it today.

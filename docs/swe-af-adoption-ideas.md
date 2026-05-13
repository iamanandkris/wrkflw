# SWE-AF Adoption Ideas For wrkflw

This note records ideas from comparing `wrkflw` with SWE-AF. These are not commitments; they are candidate directions for making `wrkflw` stronger while preserving its artifact-first, human-gated operating model.

## Context

`wrkflw` is strongest as a local workflow control plane: it creates durable `.workflow/<slug>/` artifacts, keeps OpenSpec handoff explicit, preserves human gates, and records review/signoff evidence.

SWE-AF is strongest as an autonomous execution runtime: it turns a goal into a PRD, architecture, issue DAG, parallel worktree execution, review/QA loops, replanning, verification, and PR creation.

The useful direction is not to turn `wrkflw` into a full SWE-AF clone. The useful direction is to borrow the parts that improve reliability, parallelism, recovery, and evidence quality.

## Candidate Features

1. Executable Story DAG

   Turn story dependencies into an actual scheduler, not only a diagram. Compute dependency levels, detect cycles, identify ready stories or slices, and make the graph drive what can safely run in parallel.

2. Checkpoint And Resume

   Persist command progress at phase boundaries so long workflow operations can resume without redoing planning, OpenSpec sync, dispatch generation, review ingestion, or diagram generation.

   Current implementation: command transactions checkpoint `prepare`, `command`, `postprocess`, and `diagram`; `wrkflw:resume` restores the latest safe checkpoint, refuses stale rollback resume after workflow/OpenSpec edits, and `team-sync-all` now writes command-progress checkpoints after each synchronized result envelope so resumed batches skip already-ledgered envelopes.

3. Git Worktree Isolation

   For parallel implementers, create one git worktree per story, slice, or delegated agent. This would make write-scope ownership stronger than advisory path checks.

4. Risk-Based Execution Paths

   Add per-story or per-slice risk metadata:

   - simple path: implementer plus reviewer
   - flagged path: implementer plus QA plus reviewer plus synthesis

   Flagged paths should apply to SQL, auth, security, migrations, side effects, remote transport, and cross-module contracts.

5. Feedback Synthesizer

   When Product Owner, Tech Lead, Reviewer QA, Security/Ops, or implementers disagree, run a synthesis step that produces one actionable recommendation: approve, request fixes, split, defer, block, or escalate to a human gate.

6. Issue Advisor

   Add a recovery advisor for stuck stories or slices. It should be able to recommend:

   - retry with modified acceptance criteria
   - retry with a different technical approach
   - split the story
   - accept with explicit debt
   - escalate to broader replanning

7. Replanner

   Add a DAG-level replanning command that can restructure remaining stories after failures, new discoveries, dependency changes, or scope changes.

8. Typed Technical Debt

   Add a first-class record stream for debt, similar to `records/signoffs.jsonl`:

   - dropped acceptance criterion
   - missing functionality
   - known regression risk
   - deferred test
   - unresolved design gap
   - operational or security limitation

9. Debt Propagation

   If one story completes with debt, downstream stories should automatically inherit warning context in story enrichment, implementation planning, and dispatch packets.

10. Shared Learning Memory

    Store repo conventions, failure patterns, interface notes, test commands, and successful implementation patterns in typed workflow memory. Later story enrichment and dispatch packets can use this memory instead of rediscovering the same facts.

11. Planner Risk Metadata

    Add structured fields to story enrichment:

    - estimated scope
    - touches interfaces
    - needs new tests
    - needs deeper QA
    - risk rationale
    - review focus
    - likely changed paths

12. Merge Gate

    Add a formal merge/reconcile gate after delegated implementation, especially for parallel work. It should verify changed paths, inspect conflicts, run tests, and update typed records before review approval.

13. Integration Test Gate

    Separate unit validation from integration validation. Trigger integration checks only when a story touches interfaces, multiple modules, database boundaries, auth, transport, side effects, or deployment behavior.

    Current implementation: `wrkflw:integration-gate` classifies integration need from merge-gate, merge-apply, DAG, changed paths, and risk metadata. It supports manual evidence and optional allowlisted execution through `.workflow/<slug>/integration-test-allowlist.json`, selected by `test-id`, with argv-only execution and append-only `records/integration-gate-runs.jsonl` run summaries.

14. Verify-Fix Loop

    After implementation, verify the original acceptance criteria against the actual repo state. Generate focused fix tasks when criteria are unmet.

    Current implementation: `wrkflw:verify-fix` records active-story acceptance verification in `verify-fix.json` / `verify-fix.md`, appends `records/verify-fix.jsonl`, and generates focused fix tasks for failed or unverified criteria. This is evidence-backed rather than a semantic code verifier: it uses explicit operator evidence, review findings, role review evidence, and gate state, then blocks review/release approval until verification is fresh and ready.

15. CI Feedback Loop

    If a PR or CI check fails, create typed CI findings and optional fix slices instead of treating CI as an external afterthought.

    Current implementation: `wrkflw:ci-feedback` records external CI status in `ci-feedback.json` / `ci-feedback.md`, preserves per-run snapshots under `ci-runs/`, appends `records/ci-feedback.jsonl`, and creates focused fix tasks for failed, pending, timed-out, cancelled, missing, or errored checks. It binds feedback to the active story, repository `HEAD`, and merge/apply/integration gate evidence, then feeds CI blockers into feedback synthesis, issue-advisor, and verify-fix. It records external evidence only; it does not execute arbitrary CI commands.

16. Strict Agent Result Schema

    Strengthen `team-sync` by validating delegated agent reports against JSON schema before ingesting them into workflow records and rendered views.

17. Cost And Invocation Accounting

    Track agent runs, retries, elapsed time, and estimated cost per story. This would make checkpoint/resume and avoided rework measurable.

    Current implementation: `wrkflw:accounting-record` appends manual usage evidence to `records/invocations.jsonl` and refreshes `accounting.json` / `accounting.md`. Successful workflow commands are recorded automatically with workflow-control zero cost, resumed commands are marked as avoided rework, and delegated `team-sync` reports can carry optional usage fields such as model, tokens, elapsed seconds, run id, invocation id, retry count, and cost. Unknown cost is tracked separately from explicit zero cost.

18. Runtime Plan Mutation

    Allow approved commands to add, remove, split, or reorder remaining stories while preserving completed history, dependencies, and OpenSpec ownership.

    Current implementation: `wrkflw:replan` remains proposal-first and human-gated, but can now apply approved runtime directives after `confirm: replan`: `skip`/`defer`, `remove`, `depends`, and `order`. Apply validates source input hashes, snapshots pre-apply artifacts, refuses mutations against stories that already reached `done` in `history.md`, blocks removals that would leave dangling dependencies, rewrites remaining `stories.md`, and relies on handler post-processing to refresh DAG/state artifacts.

19. Parallel Level Dispatch

    Dispatch all ready DAG nodes in the same dependency level when ownership scopes are disjoint and the user has authorized delegated execution.

20. Failure Classification

    Classify failures before retrying or escalating:

    - retryable
    - blocked by dependency
    - scope too broad
    - environment failure
    - design contradiction
    - test failure
    - policy or security block

    Current implementation: `scripts/workflow_failure_classification.py` provides the shared taxonomy and promotion helper. CI feedback, integration gate, merge gate/apply, feedback synthesis, and issue advisor artifacts now expose typed `failure_class`, `failure_category`, retryability, severity, and recommended gate fields. Feedback synthesis uses promoted classes to route dependency/architecture failures to `replan`, broad scope to `split`, and environment/policy/merge failures to `block`. CI timeouts classify as environment failures; missing or pending required CI evidence classifies as insufficient evidence.

## Suggested First Increment

Start with features that fit the current artifact model and do not require a full autonomous runtime:

1. Executable story DAG
2. Checkpoint/resume
3. Typed technical debt and debt propagation
4. Risk-based QA paths
5. Git worktree isolation
6. Issue advisor and replanner commands

These would make `wrkflw` more resilient and more parallel while keeping its core identity: evidence-first, artifact-backed, and human-gated.

## Implementation Notes

- Started with the executable story DAG increment.
- Added a derived `dag.json` / `dag.md` model that turns `Depends on:` lines in `stories.md` into topological execution levels.
- Added explicit `wrkflw:dag-sync` support so the graph can be regenerated without advancing workflow state.
- Threaded active DAG context into team dispatch packets so role agents see dependency level, downstream impact, risk, and deeper-QA guidance.
- Updated implementation planning to consume `dag.json` for ready nodes, dependency level, risk, and downstream impact.
- Updated `wrkflw:team-run` to select the first ready DAG story when no active story is recorded, and to block deferred/completed/blocked DAG nodes or active nodes with unsatisfied dependencies.
- Stabilized DAG writes so unchanged graph semantics do not rewrite files only because `generated_at` changed.
- Integrated lane-level dependencies from `dependencies.md` so the DAG can block ready-looking stories when prerequisite workflow lanes are incomplete.
- Added `dag-validation.md` so graph errors, cycles, and lane blockers are readable artifacts rather than opaque command failures.
- Added `wrkflw:team-run-level` and parallel dispatch artifacts for the earliest ready DAG level, guarded by explicit non-overlapping `Allowed Write Paths`.
- Kept `state.md` as the canonical orchestrator state; the DAG is scheduler evidence and validation input, not a replacement state file.
- Added typed technical debt recording through `records/debt.jsonl` and `debt.md`.
- Added `wrkflw:debt-record` so debt can be recorded or updated without hand-editing workflow artifacts.
- Propagated open or accepted technical debt into `dag.json`, `dag.md`, story enrichment, implementation planning, team dispatch packets, and parallel dispatch packets.
- Added a release-planning/done block for unresolved open high/critical technical debt so explicit debt remains visible before closeout.
- Re-reviewed the adopted features against SWE-AF code and architecture evidence, then tightened the current implementation where claims were stronger than enforcement.
- Made `team-run` require a valid DAG instead of silently proceeding when `dag.json` is missing or empty.
- Replaced lower-story-number completion inference with `history.md` evidence that a story actually reached `done`.
- Made high/critical debt recorded during release planning or closeout block immediately, while accepted high/critical debt remains visible but no longer blocks.
- Cleared stale parallel dispatch packets before each regeneration so blocked parallel reruns do not leave old runnable packets behind.
- Added `scripts/smoke_swe_af_adoption.py` as a repeatable regression check for DAG enforcement, completion evidence, parallel packet cleanup, and debt gate transitions.
- Added phase-level checkpoint/resume around the command handler, with checkpoints for `prepare`, `command`, `postprocess`, and `diagram`.
- Added `wrkflw:resume` / `--resume` so an interrupted command can restore the latest checkpoint and continue from the next phase instead of rerunning completed phases.
- Stored workflow/OpenSpec fingerprints and refused stale resume when the user changed workflow artifacts after rollback.
- Extended the smoke suite to cover checkpoint resume and stale-checkpoint refusal.
- Added command-progress checkpoints for `team-sync-all`, snapshotting after each synchronized result envelope so resume can preserve completed ledger/accounting state and continue with remaining envelopes.
- Added smoke coverage for interrupted `team-sync-all` batches to verify resumed sync does not duplicate delegated usage records.
- Added deterministic git worktree isolation for ready `wrkflw:team-run-level` dispatch.
- Added `.workflow/<slug>/worktrees/manifest.json` and `.workflow/<slug>/worktrees.md` to record per-story branch/path/status metadata.
- Parallel dispatch packets now include worktree path, branch, status, and a `team-sync-all` compatible result envelope path.
- Added `wrkflw:worktree-clean` for conservative cleanup of clean wrkflw-owned worktrees.
- Extended smoke coverage for non-git blocking, idempotent worktree reuse, and real temporary git worktree setup.
- Added `wrkflw:merge-gate` as a read-only reconcile readiness gate after parallel worktree execution.
- Added `.workflow/<slug>/merge-gate.json` and `.workflow/<slug>/merge-gate.md` to record changed paths, out-of-scope edits, dirty worktree blockers, manifest staleness, and merge conflict probes.
- Review approval now blocks after `wrkflw:team-run-level` until `wrkflw:merge-gate` passes.
- Added `wrkflw:integration-gate` as a controlled validation gate after merge-gate.
- Added `.workflow/<slug>/integration-test-gate.json` and `.workflow/<slug>/integration-test-gate.md` to record integration validation requirement reasons, merge-gate binding, evidence status, blockers, and warnings.
- Review approval now blocks after merge-gate until integration-gate either records that integration validation is not required or records acceptable validation evidence.
- Added allowlisted integration test execution through `.workflow/<slug>/integration-test-allowlist.json`, with `test-id` selection, shell/inline-eval rejection, per-run JSON under `.workflow/<slug>/integration-runs/`, and append-only `.workflow/<slug>/records/integration-gate-runs.jsonl` summaries.
- Added `scripts/workflow_verify_fix.py` and `wrkflw:verify-fix` for evidence-backed acceptance verification and focused fix-task generation.
- Added `.workflow/<slug>/verify-fix.json`, `.workflow/<slug>/verify-fix.md`, and append-only `.workflow/<slug>/records/verify-fix.jsonl` records.
- Review/release approval now blocks when active-story acceptance criteria are failed, unverified, missing verification evidence, or stale after story/review/gate/HEAD changes.
- Feedback synthesis and issue advisor now consume verify-fix blockers and fix-task counts.
- Added `scripts/workflow_ci_feedback.py` and `wrkflw:ci-feedback` for typed external CI status recording.
- Added `.workflow/<slug>/ci-feedback.json`, `.workflow/<slug>/ci-feedback.md`, per-run `.workflow/<slug>/ci-runs/` snapshots, and append-only `.workflow/<slug>/records/ci-feedback.jsonl` records.
- Review/release approval now blocks on stale or non-ready CI feedback when the artifact exists, and CI findings feed feedback synthesis, issue advisor, and verify-fix evidence.
- Added `scripts/workflow_accounting.py` and `wrkflw:accounting-record` for invocation, retry, elapsed-time, token, cost, and avoided-rework accounting.
- Added `.workflow/<slug>/accounting.json`, `.workflow/<slug>/accounting.md`, and append-only `.workflow/<slug>/records/invocations.jsonl` records.
- Successful workflow commands now record zero-cost workflow-control invocations, resumed commands record avoided rework, and delegated result envelopes may report model/tokens/cost without forcing unknown cost to appear as `$0`.
- Added `scripts/workflow_execution_paths.py` and `wrkflw:execution-path` for explicit simple-vs-flagged routing.
- Expanded DAG and story artifacts with planner-style metadata inspired by SWE-AF `IssueGuidance`: estimated scope, interface touch, test need, deeper-QA flag, testing guidance, review focus, and risk rationale.
- Updated implementation plans and dispatch packets so simple stories call for implementer/reviewer flow, while flagged stories call for Tech Lead plus Reviewer QA evidence and later synthesis.
- Kept this as workflow policy rather than an autonomous runtime claim: wrkflw records the route and required review path; Codex or a future runtime still does actual agent spawning.
- Added `scripts/workflow_feedback_synthesizer.py` and `wrkflw:feedback-synth` to merge role reviews, review findings, conflicts, debt, execution path, and gate evidence into one recommendation.
- Required fresh approving feedback synthesis before flagged paths can advance from review to release planning.
- Added `scripts/workflow_memory.py` and `wrkflw:memory-record` for durable typed shared learning memory in `records/memory.jsonl` and `memory.md`.
- Added memory categories for repo conventions, failure patterns, interface notes, validated test commands, and implementation patterns.
- Added `Memory entries` ingestion through `team-sync` reports and propagated active memory into story enrichment, implementation planning, team dispatch, and parallel dispatch packets.
- Added `scripts/workflow_issue_advisor.py` and `wrkflw:issue-advisor` for SWE-AF-style stuck-story recovery advice.
- Added `issue-advisor.json`, `issue-advisor.md`, and append-only `records/adaptations.jsonl` artifacts with action, failure category, diagnosis, confidence, proposed acceptance changes, dropped criteria, split candidates, debt entries, DAG/downstream impact, previous adaptations, and input hashes.
- Added smoke coverage for the advisor action ladder: `retry_approach`, `retry_modified`, `accept_with_debt`, `split`, and `escalate_to_replan`.
- Added `scripts/workflow_replanner.py` and `wrkflw:replan` for human-gated DAG/story mutation proposals.
- Added `replan.json`, `replan.md`, append-only `records/replans.jsonl`, input-hash checked `confirm: replan` apply, and pre-apply snapshots under `replans/<replan-id>/before/`.
- Added smoke coverage for proposal-only behavior, stale-apply refusal, split-story apply with preserved parent history, and modified acceptance criteria apply.
- Extended `wrkflw:replan` with approved runtime plan mutation directives for `skip`/`defer`, `remove`, dependency rewrite, and remaining-story reorder.
- Kept completed story history immutable during replan apply and fixed replanner completion detection to read complete `history.md` events instead of depending on line order.
- Blocked runtime removals that would leave remaining stories with dangling dependencies.
- Added `scripts/workflow_failure_classification.py` for shared failure class/category/retryability/recommended-gate handling.
- Promoted failure classification into CI feedback, integration gate, merge gate/apply, feedback synthesis, and issue advisor artifacts.
- Added smoke coverage for runtime skip/defer DAG state, dependency rewrite blockers, safe removal, dangling-removal refusal, completed-story mutation refusal, completed-history-preserving reorder, CI failed/timeout/pending classification promotion, integration timeout classification, merge-scope classification, and dependency-class replan routing.
- Added `scripts/workflow_agent_result_schema.py` for strict delegated-agent result validation before ingest.
- Added `schemas/agent-result.schema.json`, `agent-result-schema.md`, and append-only `records/agent-result-validation.jsonl`.
- Added `team-sync-all` batch preflight so invalid stored result envelopes block the whole batch before partial ingest, while direct lightweight `team-sync` updates remain supported unless they declare `Schema: agent-result-v1`.

# SWE-AF Adoption Progress

This lane was created after the first adoption increment had already been implemented directly in the `wrkflw` plugin repo. It is therefore a backfilled tracking lane, not the original execution record.

## Adoption Status Table

| Feature | Status | Evidence | Next Step |
| --- | --- | --- | --- |
| Executable Story DAG | Implemented | `scripts/generate_story_dag.py`, `wrkflw:dag-sync`, `dag.json`, `dag.md`, `dag-validation.md`, `scripts/smoke_swe_af_adoption.py` | Keep using it as scheduler evidence for later runtime features. |
| Parallel Level Dispatch | Implemented | `scripts/generate_parallel_dispatch.py`, `wrkflw:team-run-level`, `parallel-dispatch/` packets, stale packet cleanup in smoke tests | Keep dispatch paired with `wrkflw:merge-gate`, `wrkflw:merge-apply`, and `wrkflw:integration-gate` before review approval. |
| Planner Risk Metadata | Implemented | DAG nodes and story enrichment now carry estimated scope, interface-touch, test need, testing guidance, review focus, risk rationale, flag reasons, and debt-aware deeper-QA metadata | Keep refining heuristics as real workflows expose missing risk signals. |
| Risk-Based Execution Paths | Implemented | `scripts/workflow_execution_paths.py`, `wrkflw:execution-path`, `execution-path.json`, `execution-path.md`, DAG `execution_path`, and route-aware team/parallel dispatch packets select simple vs flagged paths | Keep paired with `wrkflw:feedback-synth` so flagged paths converge conflicting QA/reviewer signals before approval. |
| Lane Dependency Blocking | Implemented | `dependencies.md` blockers affect DAG validation and team execution | Keep lane blockers visible in health/status commands when those exist. |
| Typed Technical Debt | Implemented | `records/debt.jsonl`, `debt.md`, `wrkflw:debt-record`, release/done gate enforcement in smoke tests | Add richer debt resolution and reporting views if needed. |
| Debt Propagation | Implemented | Debt flows into DAG nodes, story enrichment, implementation plans, team dispatch, parallel dispatch, issue-advisor, and replanner evidence | Keep debt visible in replan decisions; add richer debt resolution reporting only if needed. |
| Checkpoint And Resume | Implemented | `handle_workflow_command.py` phase checkpoints, `.workflow/_transactions/*/checkpoints/`, command-progress checkpoints under `.workflow/_transactions/*/command-checkpoints/`, `wrkflw:resume`, `team-sync-all` envelope resume smoke tests | Extend command-progress checkpoints to future long multi-item commands when they are added. |
| Git Worktree Isolation | Implemented | `scripts/workflow_worktrees.py`, `wrkflw:team-run`, `wrkflw:team-run-level`, `.workflow/<slug>/worktrees/manifest.json`, active-story and parallel worktree, merge-gate, and merge-apply smoke tests | Keep hardening result collection and cleanup edge cases. |
| Shared Learning Memory | Implemented | `scripts/workflow_memory.py`, `wrkflw:memory-record`, `records/memory.jsonl`, `memory.md`, memory propagation into story enrichment, implementation plans, team dispatch, and parallel dispatch | Keep memory evidence-only and non-blocking; tune categories as real workflows produce repeated learning. |
| Feedback Synthesizer | Implemented | `scripts/workflow_feedback_synthesizer.py`, `wrkflw:feedback-synth`, `feedback-synthesis.json`, `feedback-synthesis.md`, flagged-path review advancement block | Keep tuning the recommendation rules as real role-review evidence accumulates. |
| Issue Advisor | Implemented | `scripts/workflow_issue_advisor.py`, `wrkflw:issue-advisor`, `issue-advisor.json`, `issue-advisor.md`, append-only `records/adaptations.jsonl`, smoke coverage for retry, modified criteria, debt, split, and replan actions | Keep tuning deterministic decision rules against real stuck-story evidence; future runtime can apply approved advisor decisions automatically. |
| Replanner | Implemented (proposal + guarded apply) | `scripts/workflow_replanner.py`, `wrkflw:replan`, `replan.json`, `replan.md`, append-only `records/replans.jsonl`, pre-apply snapshots under `replans/<replan-id>/before/`, smoke coverage for proposal-only, stale refusal, split apply, modified-acceptance apply, skip/defer, dependency rewrite, and remaining-story reorder | Keep mutations human-gated; add new directive forms only after real workflows need them. |
| Merge Gate | Implemented | `wrkflw:merge-gate`, `wrkflw:merge-apply`, `.workflow/<slug>/merge-gate.*`, `.workflow/<slug>/merge-apply.*`, read-only readiness checks plus explicit confirmed apply, review-sync/review approval enforcement | Keep hardening around unusual git recovery cases as they appear. |
| Integration Test Gate | Implemented | `wrkflw:integration-gate`, `.workflow/<slug>/integration-test-gate.json`, `.workflow/<slug>/integration-test-gate.md`, `.workflow/<slug>/integration-test-allowlist.json`, `.workflow/<slug>/integration-runs/`, `records/integration-gate-runs.jsonl`, merge-gate/merge-apply/DAG/allowlist binding, integration-risk classification, manual evidence, allowlisted argv-only execution, and smoke tests | Tune retry policy and richer result parsing as real integration suites are added. |
| Verify-Fix Loop | Implemented | `scripts/workflow_verify_fix.py`, `wrkflw:verify-fix`, `.workflow/<slug>/verify-fix.json`, `.workflow/<slug>/verify-fix.md`, `records/verify-fix.jsonl`, review/release gate blocking, feedback-synth and issue-advisor integration, smoke coverage for ready/fix/stale paths | Keep it honest as evidence-backed verification; add deeper code-aware or test-parser checks only when backed by concrete repo conventions. |
| CI Feedback Loop | Implemented | `scripts/workflow_ci_feedback.py`, `wrkflw:ci-feedback`, `.workflow/<slug>/ci-feedback.json`, `.workflow/<slug>/ci-feedback.md`, `.workflow/<slug>/ci-runs/`, `records/ci-feedback.jsonl`, review/release gate blocking, failure classification, feedback-synth, issue-advisor, and verify-fix integration, smoke coverage for failed/passed/stale/downstream paths | Keep this evidence-only unless a future provider adapter is added; do not execute arbitrary CI commands from workflow text. |
| Strict Agent Result Schema | Implemented | `scripts/workflow_agent_result_schema.py`, `schemas/agent-result.schema.json`, `agent-result-schema.md`, `records/agent-result-validation.jsonl`, pre-ingest validation for stored result envelopes and schema-marked direct reports, batch preflight in `team-sync-all`, smoke coverage for valid/invalid envelopes | Add nested typed evidence/finding records if agent result payloads need richer machine-readable structure. |
| Cost And Invocation Accounting | Implemented | `scripts/workflow_accounting.py`, `wrkflw:accounting-record`, `.workflow/<slug>/accounting.json`, `.workflow/<slug>/accounting.md`, `records/invocations.jsonl`, automatic successful-command records, resumed-command avoided-rework markers, delegated result usage ingestion, implementation-plan and issue-advisor integration, smoke coverage for manual, command, resume, advisor, team-run, and team-sync paths | Keep unknown cost separate from explicit zero cost; add provider-native usage adapters only when a runtime supplies reliable usage data. |
| Runtime Plan Mutation | Implemented | `wrkflw:replan` supports human-approved `skip`/`defer`, `remove`, `depends`, and `order` directives for remaining stories, preserves completed history, snapshots source inputs, rewrites `stories.md`, blocks dangling dependencies, and refreshes DAG/state via the command handler | Keep completed work immutable; add richer mutation vocabulary only from observed workflow needs. |
| Failure Classification | Implemented | `scripts/workflow_failure_classification.py`, typed failure fields in CI, integration, merge gate/apply, feedback synthesis, and issue advisor artifacts, plus smoke coverage for CI failed/timeout/pending promotion, integration timeout classification, dependency replan routing, and merge-scope classification | Tune the taxonomy and provider-specific adapters against real CI/review payloads. |

## Completed In Increment 1

- Added `scripts/generate_story_dag.py` for derived story dependency graphs.
- Added `wrkflw:dag-sync` support in `scripts/handle_workflow_command.py`.
- Added DAG validation artifacts: `dag.json`, `dag.md`, and `dag-validation.md`.
- Threaded DAG context into implementation planning and delegated team dispatch packets.
- Made `wrkflw:team-run` select the first ready DAG story when no active story is set.
- Blocked team execution when the active story is invalid, deferred, completed, lane-blocked, or waiting on unsatisfied dependencies.
- Added lane dependency awareness from `.workflow/<slug>/dependencies.md`.
- Added `scripts/generate_parallel_dispatch.py`.
- Added `wrkflw:team-run-level` for earliest-ready DAG levels with disjoint `Allowed Write Paths`.
- Updated README, skill instructions, and plugin command metadata for the new DAG and parallel dispatch commands.

## Completed In Increment 2

- Added `scripts/workflow_debt.py` for typed debt records and readable debt summaries.
- Added `.workflow/<slug>/records/debt.jsonl` and `.workflow/<slug>/debt.md`.
- Added `wrkflw:debt-record` for recording or updating debt entries.
- Added `Debt entries` ingestion through structured `team-sync` reports.
- Propagated open or accepted technical debt into DAG nodes, story enrichment, implementation planning, team dispatch, and parallel dispatch packets.
- Added a release-planning/done block for unresolved open high/critical technical debt.

## Completed In Evidence Review Pass

- Rechecked the implementation against local SWE-AF architecture/code evidence instead of relying only on the adoption idea list.
- Hardened `wrkflw:team-run` so delegated execution requires a generated, valid story DAG.
- Changed story completion detection to use explicit `history.md` evidence that a story reached `done`, rather than inferring completion from lower story numbers.
- Made high/critical debt recorded during `release-planning` or `done` block the current gate immediately, and clear the block when the same debt is accepted or resolved.
- Cleared stale `parallel-dispatch/*/implementer.md` packets before regenerating parallel dispatch so blocked reruns cannot leave runnable old packets behind.
- Added `scripts/smoke_swe_af_adoption.py` to repeat the key adoption checks: DAG enforcement, evidence-backed completion, parallel packet cleanup, and debt gate block/unblock.

## Completed In Increment 3

- Added phase checkpoints under each transaction at `.workflow/_transactions/<slug>/<transaction>/checkpoints/<phase>/`.
- Checkpointed `prepare`, `command`, `postprocess`, and `diagram` boundaries so a later phase failure can resume without rerunning completed phases.
- Added `wrkflw:resume` and `--resume` support to restore the latest checkpoint and continue the original command from the next phase.
- Stored command args and workflow/OpenSpec fingerprints in transaction metadata.
- Refuse stale resume after rollback if `.workflow` or `openspec` changed since the failed command baseline.
- Added smoke coverage for command checkpoint resume and stale-checkpoint refusal.

## Completed In Increment 4

- Added `scripts/workflow_worktrees.py` for deterministic, wrkflw-owned git worktree setup and metadata.
- `wrkflw:team-run-level` now prepares one worktree per ready DAG story after DAG and write-scope blockers pass.
- Worktree metadata is persisted in `.workflow/<slug>/worktrees/manifest.json` and rendered in `.workflow/<slug>/worktrees.md`.
- Parallel dispatch packets now include worktree path, branch, status, and a `team-sync-all` compatible result envelope path.
- Added `wrkflw:worktree-clean` for conservative cleanup of clean wrkflw-owned worktrees.
- Added smoke coverage for non-git blocking, idempotent worktree reuse, and stale packet cleanup with real temporary git worktrees.

## Completed In Increment 5

- Added read-only `wrkflw:merge-gate` support after parallel worktree execution.
- Added `.workflow/<slug>/merge-gate.json` and `.workflow/<slug>/merge-gate.md` for lane-by-lane changed paths, out-of-scope files, dirty worktrees, manifest staleness, branch ancestry, and merge conflict probes.
- Made `review-sync` and review approval block after `wrkflw:team-run-level` until the merge gate passes.
- Updated parallel dispatch packets, README, plugin metadata, and skill instructions to include the required `team-run-level` -> `team-sync-all` -> `merge-gate` -> review sequence.
- Added smoke coverage for in-scope committed worktree changes, out-of-scope committed worktree changes, and missing merge-gate enforcement after parallel dispatch.

## Completed In Increment 6

- Added read-only `wrkflw:integration-gate` support after a passing merge gate.
- Added `.workflow/<slug>/integration-test-gate.json` and `.workflow/<slug>/integration-test-gate.md` for integration requirement reasons, merge-gate/DAG artifact binding, validation evidence status, blockers, and warnings.
- Made `review-sync` and review approval block after parallel dispatch until integration-gate runs and either records `not_required` or acceptable validation evidence.
- Kept the gate evidence-only; it does not execute arbitrary shell commands from agent reports.
- Added smoke coverage for missing required integration evidence, passing evidence, and no-change `not_required` classification.

## Completed In Increment 7

- Added explicit `wrkflw:merge-apply` support after a passing merge gate.
- Added `.workflow/<slug>/merge-apply.json` and `.workflow/<slug>/merge-apply.md` for confirmation, gate binding, pre/post HEAD, checkpoint ref, candidate merge branch, and lane-by-lane apply outcomes.
- Required human confirmation via `confirm: merge-apply` before any state-changing apply.
- Applied ready lane branches sequentially with `--no-ff` commits on a temporary integration branch, then fast-forwarded the target checkout only after all candidate merges passed.
- Blocked apply on stale merge-gate evidence, moved lane branches, non-wrkflw branches, dirty non-workflow target paths, and in-progress git operations.
- Changed integration-gate ordering so committed lane changes require merge-apply first, then integration evidence against the applied `HEAD`.
- Made review-sync and review approval block on missing, blocked, or stale merge-apply evidence when parallel lane changes exist.
- Updated README, plugin metadata, and skill instructions for the required `merge-gate` -> `merge-apply` -> `integration-gate` sequence.
- Added smoke coverage for confirmation blocking, successful branch application, merge-apply enforcement before review-sync, and integration-gate binding to the apply artifact.

## Completed In Increment 8

- Extended git worktree isolation from `wrkflw:team-run-level` to normal active-story `wrkflw:team-run`.
- Added merge-eligible implementer lanes keyed by active story and role slot, with branch/path metadata persisted in `.workflow/<slug>/worktrees/manifest.json`.
- Updated active-story dispatch packets to include assigned worktree path, branch, and status.
- Blocked active-story worktree dispatch when dirty non-workflow target paths overlap a merge-eligible role scope.
- Made `team-sync-all` discover result envelopes left inside isolated worktrees, while keeping those envelopes out of merge candidates.
- Extended merge-gate enforcement so active-story `team-run` worktrees require merge-gate, merge-apply when committed changes exist, and integration-gate before review approval.
- Added merge-gate validation of active-story manifests against current active story and current role allowed paths.
- Added smoke coverage for active-story worktree creation, dirty-scope blocking, worktree result envelope ingestion, and active-story merge-gate/merge-apply.

## Completed In Increment 9

- Added `scripts/workflow_execution_paths.py` as the explicit simple-vs-flagged execution router.
- Added `wrkflw:execution-path` to write `.workflow/<slug>/execution-path.json` and `.workflow/<slug>/execution-path.md`.
- Expanded DAG nodes with planner metadata: estimated scope, interface touch, test need, testing guidance, review focus, risk rationale, flag reasons, and execution path.
- Updated story enrichment, implementation planning, team dispatch, and parallel dispatch packets to show the selected execution path and required roles.
- Kept the routing model honest: wrkflw records workflow policy and dispatch expectations, while Codex or a future runtime still performs actual agent spawning and synthesis.
- Added smoke coverage for simple vs flagged story routing and execution-path artifact generation.

## Completed In Increment 10

- Added `scripts/workflow_feedback_synthesizer.py` for deterministic synthesis of role reviews, review-log findings, conflicts, debt, execution path, and merge/integration gate evidence.
- Added `wrkflw:feedback-synth` to write `.workflow/<slug>/feedback-synthesis.json` and `.workflow/<slug>/feedback-synthesis.md`.
- Feedback synthesis now recommends one of: `approve`, `fix`, `split`, `defer`, `block`, or `replan`.
- Flagged execution paths now block review advancement until feedback synthesis exists, is fresh, and recommends `approve`.
- Added default `feedback-synthesis.md` scaffolding and included it in runtime contract shared inputs/outputs.
- Added smoke coverage for missing flagged-path synthesis, missing required Tech Lead / Reviewer QA inputs, and clean approving synthesis after role evidence arrives.

## Completed In Increment 11

- Added `scripts/workflow_memory.py` for durable typed shared learning memory.
- Added `wrkflw:memory-record` to write `.workflow/<slug>/records/memory.jsonl` and `.workflow/<slug>/memory.md`.
- Supported memory categories for repo conventions, failure patterns, interface notes, validated test commands, and implementation patterns.
- Added `Memory entries` ingestion through structured `team-sync` reports.
- Propagated relevant active memory into story enrichment, implementation plans, active-story dispatch packets, and parallel dispatch packets.
- Kept memory non-blocking and evidence-only so gate enforcement remains in debt, review findings, conflicts, and synthesis.
- Added smoke coverage for direct memory recording, team-sync memory ingestion, and propagation into implementation plans, dispatch packets, and story enrichment.

## Completed In Increment 12

- Added `scripts/workflow_issue_advisor.py` for deterministic stuck-story recovery advice.
- Added `wrkflw:issue-advisor` to write `.workflow/<slug>/issue-advisor.json` and `.workflow/<slug>/issue-advisor.md`.
- Added append-only `.workflow/<slug>/records/adaptations.jsonl` so advisor decisions are recorded instead of rediscovered on every retry.
- Matched the SWE-AF recovery action ladder: `retry_approach`, `retry_modified`, `accept_with_debt`, `split`, and `escalate_to_replan`.
- Included SWE-AF-shaped decision fields such as `failure_category`, `failure_diagnosis`, `confidence`, proposed modified criteria, dropped criteria, split candidates, debt entries, DAG impact, downstream impact, previous adaptations, and input hashes.
- Kept the advisor human-gated: it updates state notes and blocks for explicit next action, but it does not silently edit story scope or write debt records.
- Added default `issue-advisor.md` scaffolding and included issue-advisor/adaptation artifacts in the runtime contract.
- Added smoke coverage for retry, modified acceptance scope, accept-with-debt after advisor budget, split, and replan paths.

## Completed In Increment 13

- Added `scripts/workflow_replanner.py` for human-gated DAG/story replanning.
- Added `wrkflw:replan` to generate `.workflow/<slug>/replan.json` and `.workflow/<slug>/replan.md`.
- Added append-only `.workflow/<slug>/records/replans.jsonl` so replan proposals and applications are preserved.
- Matched the SWE-AF `ReplanDecision` shape with `action`, `updated_items`, `removed_items`, `skipped_items`, `new_items`, `dependency_edges`, `debt_items`, `validation_errors`, source evidence, and status.
- Kept replan proposal-only by default; applying supported mutations requires `confirm: replan`.
- Added input-hash validation before apply and preserved pre-apply artifacts under `.workflow/<slug>/replans/<replan-id>/before/`.
- Implemented guarded apply for split-story replans and modified acceptance criteria replans.
- Added default `replan.md` scaffolding and included replan artifacts in the runtime contract.
- Added smoke coverage for proposal-only behavior, stale-apply refusal without overwriting human edits, split apply with deferred parent story and DAG refresh, and modified acceptance apply.

## Completed In Increment 14

- Added `scripts/workflow_agent_result_schema.py` for strict delegated-agent result validation.
- Added generated schema artifacts: `.workflow/<slug>/schemas/agent-result.schema.json` and `.workflow/<slug>/agent-result-schema.md`.
- Added append-only `.workflow/<slug>/records/agent-result-validation.jsonl` to record valid and invalid result-envelope validation outcomes.
- Required stored `.workflow/<slug>/agent-results/*.md` envelopes and schema-marked direct `team-sync` reports to include the exact `agent-result-v1` fields before ingest.
- Added `team-sync-all` batch preflight so one invalid pending envelope blocks the batch before any valid envelope is partially ingested.
- Updated dispatch packet final report templates to include `Schema: agent-result-v1`.
- Added smoke coverage for schema-marked direct report validation, valid worktree envelope ingest, and invalid batch preflight refusal without ledger updates.

## Completed In Increment 15

- Added `.workflow/<slug>/integration-test-allowlist.json` and `.workflow/<slug>/integration-test-allowlist.md` scaffolding for reviewed integration command specs.
- Extended `wrkflw:integration-gate` so `test-id: <id>` runs only an allowlisted structured `argv` command with `shell=False`, bounded timeout, minimal inherited environment, and capped/redacted stdout/stderr tails.
- Kept manual `command:` evidence as text-only evidence; it is never executed.
- Rejected shell executables and inline-eval flags in allowlist entries.
- Wrote per-run execution JSON under `.workflow/<slug>/integration-runs/` and append-only summaries under `.workflow/<slug>/records/integration-gate-runs.jsonl`.
- Bound allowlisted gate results to the allowlist hash so `review-sync` blocks stale integration evidence after allowlist edits.
- Blocked allowlisted runs that fail, timeout, hit invalid config, use unknown ids, or leave dirty non-workflow paths.
- Added smoke coverage for passing allowlisted runs, unknown ids, failing commands, shell entry rejection, manual command non-execution, and stale allowlist blocking.

## Completed In Increment 16

- Added `scripts/workflow_verify_fix.py` for evidence-backed active-story acceptance verification.
- Added `wrkflw:verify-fix` to write `.workflow/<slug>/verify-fix.json`, `.workflow/<slug>/verify-fix.md`, and append-only `.workflow/<slug>/records/verify-fix.jsonl`.
- Classified each active-story acceptance criterion as `passed`, `failed`, or `unverified` from explicit command evidence, review findings, role review evidence, and integration-gate status.
- Generated focused fix tasks for failed or unverified criteria without silently changing code or story scope.
- Required fresh ready verify-fix evidence before review/release approval when the active story has acceptance criteria.
- Included verify-fix results in feedback synthesis so failed criteria produce a `fix` recommendation.
- Included verify-fix task counts and blockers in issue-advisor evidence so recovery advice can target acceptance gaps.
- Added smoke coverage for command exposure, fix-task generation, pass evidence, stale story detection, feedback-synth integration, and issue-advisor integration.

## Completed In Increment 17

- Added `scripts/workflow_ci_feedback.py` for typed external CI status recording.
- Added `wrkflw:ci-feedback` to write `.workflow/<slug>/ci-feedback.json`, `.workflow/<slug>/ci-feedback.md`, per-run snapshots under `.workflow/<slug>/ci-runs/`, and append-only `.workflow/<slug>/records/ci-feedback.jsonl`.
- Bound CI feedback to the active story, expected repository `HEAD`, and merge/apply/integration gate evidence so stale CI cannot approve later code.
- Generated focused fix tasks for failed, pending, timed-out, cancelled, missing, or errored CI checks.
- Made review/release advancement block on stale or non-ready CI feedback when the artifact exists.
- Included CI blockers and fix-task counts in feedback synthesis and issue advisor.
- Fed passing/failing CI check evidence into verify-fix classification for matching acceptance criteria.
- Added smoke coverage for failed and passing CI feedback, stale `HEAD` blocking, feedback-synth/issue-advisor integration, and verify-fix evidence consumption.

## Completed In Increment 18

- Added `scripts/workflow_accounting.py` for artifact-backed invocation accounting.
- Added `wrkflw:accounting-record` to append manual usage evidence to `.workflow/<slug>/records/invocations.jsonl` and refresh `.workflow/<slug>/accounting.json` / `.workflow/<slug>/accounting.md`.
- Automatically record successful workflow commands with workflow-control zero cost while keeping failed rollback attempts out of the visible ledger so checkpoint/resume fingerprints stay stable.
- Mark resumed commands as avoided rework.
- Added optional delegated-agent result usage fields for model, input tokens, output tokens, cost, elapsed seconds, invocation id, run id, attempt, and retry counts.
- Ingest delegated-agent usage from `team-sync` / `team-sync-all` without duplicating already-synced result envelopes.
- Kept unknown cost separate from explicit zero cost, following the AgentField cost-estimation caution.
- Added accounting context to implementation planning and issue-advisor inputs.
- Added smoke coverage for manual records, successful command records, failed-checkpoint resume safety, issue-advisor retry accounting, team-run workflow-control cost, and delegated usage ingestion.

## Completed In Increment 19

- Added command-progress checkpoints under `.workflow/_transactions/<slug>/<transaction>/command-checkpoints/`.
- `team-sync-all` now snapshots workflow/OpenSpec state after each successfully synchronized result envelope.
- `wrkflw:resume` now restores the latest `team-sync-all` envelope checkpoint when the command phase was interrupted, then continues the command phase with remaining unsynced envelopes.
- Preserved existing all-pending schema preflight, so one invalid envelope still blocks the batch before partial ingest.
- Used `agent-sync-ledger.md` as the terminal-success guard so completed envelopes are skipped on resume and delegated accounting records are not duplicated.
- Added smoke coverage for an injected failure after the first `team-sync-all` envelope, successful resume, two synced envelopes, one resumed command record, and no duplicated delegated usage records.

## Completed In Increment 20

- Extended `wrkflw:replan` with explicit runtime mutation directives: `skip`/`defer`, `remove`, `depends`, and `order`.
- Kept runtime mutations human-gated through proposal plus `confirm: replan`, with input-hash validation and pre-apply snapshots.
- Made replan mutation apply only to remaining work and block attempts to mutate stories already completed in `history.md`.
- Fixed completed-story detection in the replanner so it reads whole history event blocks rather than assuming field order.
- Made runtime `remove` dependency-safe by blocking removals that would leave remaining stories pointing at deleted stories.
- Kept replan stale checks focused on source inputs rather than generated DAG/history artifacts that the proposal command itself may refresh.
- Added `scripts/workflow_failure_classification.py` as a shared taxonomy helper for failure class, category, retryability, severity, and recommended gate.
- Promoted typed failure classification into CI feedback, integration gate, merge gate/apply, feedback synthesis, and issue advisor artifacts.
- Mapped CI timeout to `environment_failure` and CI pending/missing checks to `insufficient_evidence`.
- Made feedback synthesis route dependency/architecture failures to `replan`, broad scope to `split`, and environment/policy/merge failures to `block`.
- Made issue advisor consume promoted typed failure categories before falling back to keyword heuristics.
- Added smoke coverage for skip/defer DAG state, dependency rewrite blockers, leaf removal, dangling-dependency removal refusal, completed-story mutation refusal, remaining-story reorder with completed-history preservation, CI failed/timeout/pending classification promotion, integration timeout classification, dependency failure replan routing, and merge-scope classification.

## Completed In Hardening Review Fixes

- Added apply-time completed-history guards for split-story and modified-acceptance replans, closing the gap where a proposal made before completion could still mutate a completed story after completion was recorded.
- Strengthened integration-gate output redaction so `Authorization: Bearer ...`, `Basic ...`, `api_key=...`, `token: ...`, `secret: ...`, and password-style output redact the full sensitive value.
- Refreshed `.workflow/swe-af-adoption/state.md` and `history.md` so the workflow lane no longer claims the adoption pass is still pending a broad hardening check.
- Updated `scripts/install_local.sh --local` so the current checkout can be synced into `~/plugins/wrkflw` and the active Codex skill copy can be refreshed without relying on a remote `git pull`.
- Added `pyproject.toml` and focused unit regression tests for the hardening fixes.
- Validated the source checkout with Python compile checks, unit regression tests, and the full SWE-AF adoption smoke scenarios.

## Completed In Team Hardening Pass

- Centralized the runtime contract shared input/output lists in `scripts/workflow_runtime_contract.py` so initialization and live command sync use the same SWE-AF artifact vocabulary, with seeded shared inputs separated from generated-on-demand artifacts.
- Expanded canonical workflow scaffolding so `.workflow/<slug>/` gets placeholder JSON, markdown, JSONL, and directory resources for feedback synthesis, issue advisor, replanning, verify-fix, CI feedback, integration-gate runs, memory, debt, accounting, dispatch, and agent-result validation.
- Made placeholder `not_recorded` JSON artifacts explicit and adjusted review blockers so placeholders are never mistaken for passing evidence.
- Added `Blocked reason` to freshly initialized `state.md` files, matching the canonical state contract.
- Moved synthetic DAG/parallel/lane-block workflow folders out of live `.workflow/wrkflw-*` paths and into `tests/fixtures/workflows/`.
- Wired the SWE-AF adoption smoke suite into standard unittest discovery through `tests/test_swe_af_smoke.py`.
- Updated `scripts/install_local.sh --local` so installed plugin copies remove stale `.workflow` state instead of carrying old local workflow resources into the active skill install.
- Moved stale installed `.workflow` cleanup outside the `--local` branch so clone/update/local install modes all remove stale workflow state from the active plugin copy.
- Rechecked the canonical lane against the runtime contract and confirmed all seeded required shared inputs exist; command-produced artifacts are now clearly labeled as generated-on-demand.
- Refreshed README and example documentation so the documented artifact model matches the current runtime contract.

## Remaining Candidate Work

- No original adoption-table item remains unimplemented at the artifact/control-plane level.
- Remaining work is ongoing operational hardening only: tune heuristics, command wording, and edge-case handling as real workflows expose new evidence.

## Current Follow-Up

Keep future changes tied to the same pattern: inspect current implementation and SWE-AF evidence, repair concrete gaps, record workflow state, and validate source plus installed copies before claiming completion.

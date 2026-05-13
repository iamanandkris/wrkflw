---
name: wrkflw-discuss
description: Use when the user writes wrkflw:discuss, asks to start a reusable engineering workflow, or wants a workflow-guided discussion that proceeds through stages, asks relevant questions, and stops at human approval gates.
---

# wrkflw:discuss

Treat `wrkflw:discuss "..."` as an explicit request to start or continue a staged workflow discussion.

When starting a workflow, inspect the current repository first when one exists:
- inspect the existing codebase before treating a design document as the primary source of truth
- start from repository evidence such as `README.md`, build files, source entrypoints, tests, and active OpenSpec artifacts
- summarize the current implementation shape, capability coverage, and obvious gaps before shaping stories
- reconcile observed code with intended behavior and surface conflicts explicitly

Then look for a design seed:
- auto-detect `design.md` or `docs/design.md` in the active repo
- if the user gives an explicit file path, prefer that path instead
- if a broad or loosely structured design exists, first normalize it into workflow-ready artifacts before shaping epic/story work
- seed the workflow from the normalized design and epic-specific design slice after the initial codebase reconnaissance
- record the seed in `.workflow/<slug>/links.md` and `.workflow/<slug>/design-seed.md`

Also treat these as workflow control intents:
- `wrkflw:approve`
- `wrkflw:approve "..."`
- `wrkflw:reject "..."`
- `wrkflw:reconcile "..."`
- `wrkflw:rework "..."`
- `wrkflw:refine "..."`
- `wrkflw:rework-item "..."`
- `wrkflw:proceed-only "..."`
- `wrkflw:defer "..."`
- `wrkflw:override "..."`
- `wrkflw:openspec-sync`
- `wrkflw:next`
- `wrkflw:resume`
- `wrkflw:dag-sync`
- `wrkflw:execution-path`
- `wrkflw:feedback-synth`
- `wrkflw:issue-advisor`
- `wrkflw:replan`
- `wrkflw:verify-fix`
- `wrkflw:ci-feedback`
- `wrkflw:accounting-record "..."`
- `wrkflw:memory-record "..."`
- `wrkflw:debt-record "..."`
- `wrkflw:merge-gate`
- `wrkflw:merge-apply`
- `wrkflw:integration-gate`
- `wrkflw:worktree-clean`
- `wrkflw:staff "..."`
- `wrkflw:assign "..."`
- `wrkflw:challenge "..."`
- `wrkflw:review-sync "..."`
- `wrkflw:team-run "..."`
- `wrkflw:team-run-level "..."`
- `wrkflw:team-sync "..."`
- `wrkflw:team-sync-all`

## Behavior

1. Classify the request as epic, story, bug, spike, or refactor.
2. Identify the current stage.
3. If a repository or existing system already exists, inspect the codebase before treating design documents as the primary source of truth.
4. Start discovery from repository evidence such as `README.md`, build files, source entrypoints, tests, and active OpenSpec artifacts.
5. Create or refresh a capability inventory before story slicing so sample and harness work does not converge too early on a thin result.
6. Ask only the minimum relevant questions.
7. Recommend the next tool and mode.
8. Stop at human approval gates.
9. If useful, initialize a local workflow workspace in the current repo.
10. Detect when repository evidence shows the implementation is ahead of workflow metadata or OpenSpec artifacts, and classify that state as workflow artifact drift instead of normal forward progression.
11. If a gate is rejected, record the rejection and route work back to the right prior stage.
12. When the user issues `wrkflw:approve`, `wrkflw:reject`, `wrkflw:reconcile`, or `wrkflw:next`, prefer the companion command handler script over manual state edits.

## Workspace Convention

Prefer a local workflow folder in the active repo:

```text
.workflow/<slug>/
```

with files such as:
- `context.md`
- `capabilities.md`
- `state.md`
- `decisions.md`
- `links.md`
- `gates.md`
- `workflow-contract.md`
- `team-overrides.md`
- `agent-assignments.md`
- `execution-board.md`
- `review-log.md`
- `role-reviews.md`
- `conflicts.md`
- `assumptions.md`
- `design-slice.md` when a broad design file is normalized into an epic-specific workflow slice
- `design-seed.md` when a design file is used

State should capture:
- current stage
- human gate status
- blocked reason when a hard workflow precondition is not satisfied
- rework target
- rejection reason
- next action

Canonical state rules:
- `state.md` is the required source of truth for current workflow status
- `history.md` is the required source of truth for completed progression trail
- `diagram-flow.puml` and `diagram-work.puml` are derived artifacts and must be regenerated after each workflow state change
- `Current stage` must use canonical stage values only:
  - `discuss`
  - `capability-review`
  - `epic-shaping`
  - `story-slicing`
  - `story-enrichment`
  - `spec-authoring`
  - `implementation-planning`
  - `implementation`
  - `review`
  - `release-planning`
  - `done`
- `Human gate status` must use canonical values only:
  - `pending`
  - `approved`
  - `blocked`
  - `rejected`
- do not write freeform substitutes such as `epic-shaped`, `story-sliced`, or `awaiting approval` into `state.md`

Team execution model:
- `wrkflw` should create a default initiative-level team configuration at `.workflow/team-config.md`
- the default team should be a 4-role engineering team:
  - `Product Owner`
  - `Tech Lead`
  - `Implementer`
  - `Reviewer QA`
- the user may override team size, role structure, and responsibilities by editing `.workflow/team-config.md`
- the user may override team composition for a specific epic by editing `.workflow/<slug>/team-overrides.md`
- `agent-assignments.md` should declare who owns which role for the epic lane
- `execution-board.md` should track current work items, owners, status, and blockers
- `review-log.md` should record challenge and review findings across Product Owner, Tech Lead, and Reviewer QA
- `team-minutes.md` should record staffing updates, assignment decisions, team discussion outcomes, challenge summaries, and handoff notes
- `runtime-contract.md` should record the file-driven runtime contract that keeps shared inputs, outputs, ownership, and state authority explicit
- `dependencies.md` should record first-class lane dependencies such as `Depends on`, `Blocked by`, `Satisfies`, and `Unlocks`
- `dag.json`, `dag.md`, and `dag-validation.md` should record the derived story execution graph from `stories.md` dependencies, lane-level dependencies, and current workflow state
- `execution-path.json` and `execution-path.md` should record the selected simple or flagged execution path for the active or first ready story
- `feedback-synthesis.json` and `feedback-synthesis.md` should record the synthesized team feedback recommendation for the active story, including promoted failure classifications when gate or CI artifacts provide them
- `issue-advisor.json`, `issue-advisor.md`, and `records/adaptations.jsonl` should record SWE-AF-style recovery advice for stuck stories without silently mutating story scope or debt, preferring promoted failure classifications before textual heuristics
- `replan.json`, `replan.md`, `records/replans.jsonl`, and `replans/<replan-id>/before/` should record human-gated DAG/story mutation proposals and preserved pre-apply artifacts, including approved remaining-story skip/defer/remove/dependency/order mutations
- `verify-fix.json`, `verify-fix.md`, and `records/verify-fix.jsonl` should record active-story acceptance verification and focused fix tasks for failed or unverified criteria
- `ci-feedback.json`, `ci-feedback.md`, `ci-runs/`, and `records/ci-feedback.jsonl` should record typed external CI status, stale-HEAD checks, focused CI fix tasks, and failure classification
- `accounting.json`, `accounting.md`, and `records/invocations.jsonl` should record workflow command invocations, delegated-agent usage, retry markers, avoided-rework markers, elapsed time, tokens, known cost, unknown cost, and correlation ids
- `integration-test-allowlist.json`, `integration-test-gate.json`, `integration-test-gate.md`, `integration-runs/`, and `records/integration-gate-runs.jsonl` should record integration validation requirements, allowlisted run specs, execution evidence, failure classification, and append-only run summaries
- `records/memory.jsonl` should record reusable typed learning; `memory.md` should render repo conventions, failure patterns, interface notes, validated test commands, and implementation patterns
- `records/debt.jsonl` should record typed technical debt entries; `debt.md` should render a readable debt ledger
- `role-reviews.md` should record independent role reviews before reconciliation so weak agreement is visible
- `conflicts.md` should record unresolved disagreements, options, recommendations, and chosen resolutions
- `assumptions.md` should record important assumptions, confidence, impact if wrong, and validation steps
- `decisions.md` should record reconciled decisions with context, options considered, consequences, and revisit triggers
- `agent-results/` should store structured delegated-agent result envelopes
- `agent-sync-ledger.md` should record which result envelopes have already been synchronized
- `schemas/agent-result.schema.json`, `agent-result-schema.md`, and `records/agent-result-validation.jsonl` should define and record strict validation for stored delegated-agent result envelopes
- `team-dispatch.md` should record the current delegated execution packet index for the active workflow lane
- `parallel-dispatch.md`, `parallel-dispatch.json`, and `parallel-dispatch/` should record DAG-level parallel dispatch packets when multiple ready stories can run safely
- dispatch packets should include active DAG context when available: execution level, dependency status, downstream dependents, risk, planner metadata, execution path, and deeper-QA flag
- `wrkflw` should synchronize `execution-board.md` with the current workflow stage so owner and handoff state remain visible
- `wrkflw` should use the team model and story DAG when generating `implementation-plan.md`, especially team size, parallel implementation slots, ready DAG nodes, dependency level, execution path, risk, and deeper-QA needs
- `wrkflw` should require late-stage review evidence in `review-log.md` when Product Owner or Reviewer QA signoff is configured as required
- `wrkflw:staff` should update team-config or team-overrides without forcing the user to hand-edit markdown for common staffing changes
- `wrkflw:assign` should update per-epic role ownership in `agent-assignments.md`
- `wrkflw:challenge` should record structured team challenges in `review-log.md` and reflect them in workflow state
- `wrkflw:review-sync` should resynchronize review and collaboration evidence back into workflow state and execution-board visibility
- `wrkflw:team-sync` should synchronize delegated role outcomes such as implementer completion, reviewer start, handoff notes, and lane status back into `execution-board.md`, `agent-assignments.md`, and `team-minutes.md`
- `wrkflw:team-sync-all` should validate unsynchronized structured result envelopes from `.workflow/<slug>/agent-results/` against `schemas/agent-result.schema.json`, ingest only valid envelopes, update `agent-sync-ledger.md`, and checkpoint after each completed envelope so an interrupted batch can resume without duplicating completed sync work.
- `wrkflw:merge-gate` should inspect actual active-story or parallel worktree git diffs against the recorded dispatch base, validate changed paths against story or role `Allowed Write Paths`, probe merge conflicts, and write `.workflow/<slug>/merge-gate.json` / `.workflow/<slug>/merge-gate.md` before review approval
- `wrkflw:merge-apply` should require explicit `confirm: merge-apply`, inspect a passing `merge-gate.json`, apply only ready wrkflw-owned lane branches through a temporary integration branch, then write `.workflow/<slug>/merge-apply.json` / `.workflow/<slug>/merge-apply.md`
- `wrkflw:integration-gate` should inspect `.workflow/<slug>/merge-gate.json` and `.workflow/<slug>/merge-apply.json` when committed lane changes exist, classify integration validation need from changed paths and DAG/story risk metadata, classify blocked validation failures, and write `.workflow/<slug>/integration-test-gate.json` / `.workflow/<slug>/integration-test-gate.md`; it may execute only explicit `test-id` entries from `.workflow/<slug>/integration-test-allowlist.json` and must not execute arbitrary `command:` text from agent reports
- `wrkflw:dag-sync` should regenerate the story DAG and validation artifact, then block on unknown story dependencies, cycles, or incomplete lane-level dependencies
- `wrkflw:execution-path` should classify the active or first ready story as `simple` or `flagged`, recording estimated scope, interface touch, test need, risk rationale, required roles, review flow, and retry policy
- `wrkflw:feedback-synth` should read role reviews, review-log findings, conflicts, debt, execution path, merge/integration gate evidence, CI feedback, and promoted failure classifications, then write one recommendation: `approve`, `fix`, `split`, `defer`, `block`, or `replan`
- `wrkflw:issue-advisor` should consume feedback synthesis, review/conflict evidence, DAG/debt/memory/gate artifacts, and promoted failure classifications, then write one recovery action without silently mutating story scope or debt
- `wrkflw:replan` should propose DAG/story mutations by default; only `confirm: replan` may apply supported mutations after input-hash validation and before-artifact archival. Supported approved directives include `skip`/`defer`, `remove`, `depends`, and `order` for remaining stories; completed history is immutable.
- `wrkflw:verify-fix` should compare active-story acceptance criteria with explicit verification evidence, write `.workflow/<slug>/verify-fix.json` / `.workflow/<slug>/verify-fix.md`, and generate focused fix tasks without silently changing code or story scope
- `wrkflw:ci-feedback` should record external CI status for the current `HEAD`, write `.workflow/<slug>/ci-feedback.json` / `.workflow/<slug>/ci-feedback.md`, preserve per-run snapshots under `.workflow/<slug>/ci-runs/`, and generate focused fix tasks plus failure classifications without executing arbitrary CI commands
- `wrkflw:accounting-record` should append manual or delegated-run usage evidence to `.workflow/<slug>/records/invocations.jsonl`, refresh `.workflow/<slug>/accounting.json` / `.workflow/<slug>/accounting.md`, and keep unknown cost distinct from explicit zero cost
- `wrkflw:memory-record` should append or update non-blocking shared learning and make it available to story enrichment, implementation planning, and dispatch packets
- `wrkflw:debt-record` should append or update typed technical debt and let open or accepted debt propagate through DAG, implementation planning, and dispatch packets
- team-control commands should also append readable minutes to `team-minutes.md` so the collaboration history is explicit
- `wrkflw:team-run` should generate a delegated execution packet set, prepare isolated git worktrees for merge-eligible implementer lanes, and, when the user has explicitly asked for multi-agent execution, use those packets to spawn real role agents
- `wrkflw:team-run` may select the first ready DAG story when no active story is recorded, but it should block if the active story is deferred, completed, blocked, or has unsatisfied dependencies in `dag.json`
- `wrkflw:team-run-level` should generate parallel dispatch packets for all ready nodes in the earliest ready DAG level, but only when each story declares non-overlapping `Allowed Write Paths`

Collaborative multi-agent review model:
- prefer artifact-centered collaboration over unstructured agent chat
- use this sequence for planning, specification, implementation planning, and review:
  1. one role drafts or updates the artifact
  2. Product Owner, Tech Lead, Implementer, and Reviewer QA perform independent reviews against the artifact
  3. each role records a structured verdict before reading or adopting other roles' conclusions when feasible
  4. the workflow compares reviews, writes disagreements into `conflicts.md`, updates `assumptions.md`, and only then reconciles the artifact
  5. the orchestrator records decisions in `decisions.md` and returns unresolved blocking conflicts to the nearest human gate
- role reviews should use this structure:
  - `Role`
  - `Verdict: approve|approve-with-changes|block`
  - `Missing requirements`
  - `Incorrect assumptions`
  - `Risks`
  - `Questions`
  - `Suggested changes`
  - `Evidence`
  - `Red-team notes`
- role bias should be explicit:
  - Product Owner challenges value, user outcomes, scope, acceptance criteria, and non-goals
  - Tech Lead challenges architecture, boundaries, sequencing, dependencies, and integration risk
  - Implementer challenges feasibility, implementation complexity, maintainability, and file ownership
  - Reviewer QA challenges testability, edge cases, regressions, and acceptance proof
  - optional Security/Ops challenges auth, data exposure, auditability, rollout, and operational risk
  - the orchestrator integrates and reconciles; it should not erase unresolved dissent
- conflict entries should capture:
  - `Conflict`
  - `Raised by`
  - `Artifact section`
  - `Severity: blocking|important|minor`
  - `Options`
  - `Recommendation`
  - `Resolution`
  - `Owner`
- assumption entries should capture:
  - `Assumption`
  - `Source`
  - `Confidence`
  - `Impact if wrong`
  - `Validation step`
- before spec approval and PR approval, run one bounded red-team pass: identify the most likely way the current artifact fails product acceptance, implementation, testing, security, or rollout
- a role may approve with changes, but a blocking Product Owner, Tech Lead, Reviewer QA, or Security/Ops finding must keep the current gate pending or blocked until resolved in the relevant review or conflict artifact

Capability inventory should capture:
- the inferred workflow mode, such as `tutorial-sample`, `feature-harness`, `product-service`, or `general-delivery`
- the capability categories the workflow should consider before writing narrow stories too early

Gate configuration should capture, per gated stage:
- `capability-review.autoApprove: true|false`
- `<stage>.autoApprove: true|false`

If `autoApprove` is `true` for a gate, the workflow should not stop for human approval at that stage and should continue automatically to the next stage.

Workflow contract should capture:
- `OpenSpec required: true|false`
- `OpenSpec initialized: true|false`
- `OpenSpec waived: true|false`
- `OpenSpec lane active: true|false`
- `OpenSpec waiver reason: ...`

The workflow should also maintain a live PlantUML diagram at:

```text
.workflow/<slug>/diagram-flow.puml
.workflow/<slug>/diagram-work.puml
```

Update it after each workflow action and OpenSpec bridge action so progress is visible in near real time.

If the workspace is missing and the user wants one, run the companion script:

```text
python3 scripts/init_workflow_workspace.py --slug <slug> --root <repo-root> [--design-file <path>]
```

To update an existing workflow state after approval or rejection, use the companion state script if available.

Preferred command handler:

```text
python3 scripts/handle_workflow_command.py --slug <slug> --root <repo-root> --command <approve|reject|reconcile|rework|refine|rework-item|proceed-only|defer|next|resume|override|openspec-sync|dag-sync|execution-path|feedback-synth|issue-advisor|replan|verify-fix|ci-feedback|accounting-record|memory-record|debt-record|merge-gate|merge-apply|integration-gate|worktree-clean|staff|assign|challenge|review-sync|team-run|team-run-level|team-sync|team-sync-all> [--reason "..."] [--items "..."] [--design-file <path>]
```

Behavior expectations:
- `wrkflw:discuss` should inspect the existing codebase first when one exists, before treating a design document or design seed as the primary source of truth.
- if the design input is broad, mixed, or not already workflow-shaped, `wrkflw:discuss` should first normalize it into a workflow-ready design artifact instead of using the raw design directly for story shaping.
- that normalization step should produce:
  - a shared normalized design under `.workflow/_normalized/`
  - epic candidates inferred from the broader design
  - an epic-specific `design-slice.md` inside `.workflow/<slug>/`
  - section-aware epic candidates that preserve capability, actor, architecture, and operational evidence instead of flattening the raw design into one mixed scope bucket
- each workflow slug should register itself in `.workflow/initiative-index.md` so multiple epic lanes can be tracked under the same repo without sharing one state file
- `wrkflw:discuss` should use repository evidence such as `README.md`, build files, source entrypoints, tests, and active OpenSpec artifacts as first-pass evidence of current behavior.
- `wrkflw:discuss` should summarize the current implementation shape, capability coverage, and obvious gaps before story slicing.
- `wrkflw:discuss` should reconcile observed code with the design seed or design document and surface conflicts explicitly before moving into epic shaping or story slicing.
- `wrkflw:discuss` should use the design seed as the primary planning input after the initial codebase reconnaissance, instead of relying only on the user’s one-line summary.
- `wrkflw:discuss` should distinguish between:
  - code vs design drift
  - code vs workflow metadata drift
  - code vs OpenSpec artifact drift
- if the codebase is materially ahead of `.workflow/...` or `openspec/changes/...`, `wrkflw:discuss` should classify the situation as workflow artifact drift or reconciliation work, not as normal feature planning.
- when workflow artifact drift is detected, `wrkflw:discuss` should recommend reconciling workflow metadata and OpenSpec with implemented reality before proposing a new epic or new capability stories.
- when the active story context is still valid and only the OpenSpec change is stale, `wrkflw:discuss` should recommend `wrkflw:openspec-sync`.
- when the broader workflow state itself is stale, `wrkflw:discuss` should recommend `wrkflw:reconcile "Reconcile workflow metadata and OpenSpec with implemented repo state"` before any new forward-planning step.
- `wrkflw:discuss` should also create or refresh `.workflow/<slug>/capabilities.md` so story slicing starts from capability categories instead of only the first obvious implementation slice.
- `wrkflw` should stop at a dedicated capability-review gate after `discuss` so the user can approve, reject, or refine the generated capability inventory before epic shaping continues.
- entering `story-slicing` should regenerate `.workflow/<slug>/stories.md` from `.workflow/<slug>/capabilities.md` so the story plan reflects the reviewed capability inventory instead of stale generic slices.
- after story slices exist, workflow commands should refresh `.workflow/<slug>/dag.json` and `.workflow/<slug>/dag.md` so story dependencies, execution levels, and ready/blocked/deferred status hints stay current.
- workflow DAG refresh should also maintain `.workflow/<slug>/dag-validation.md` so missing dependencies, cycles, and lane blockers are visible before execution.
- DAG regeneration should avoid rewriting files when graph semantics are unchanged, so timestamp-only churn does not pollute the workflow diff.
- if `OpenSpec required: true` and the workflow reaches `spec-authoring` without a valid OpenSpec initialization, the workflow must hard-block instead of continuing into implementation.
- the workflow must not silently downgrade or bypass OpenSpec on its own judgment.
- the only valid bypass is an explicit user override such as `wrkflw:override "Proceed without OpenSpec for this run"`.
- `wrkflw:approve --design <path>` or equivalent explicit file-path guidance should reseed the workflow from that design file before continuing, so the workflow can start from analyzed file context instead of only conversational text.
- `wrkflw` should respect `.workflow/<slug>/gates.md` when deciding whether a human gate must pause the workflow.
- When a gated stage is entered with `<stage>.autoApprove: true`, `wrkflw` should record that the gate was auto-approved and continue automatically.
- `wrkflw:approve` should advance the workflow from the current gate to the next stage.
- `wrkflw:approve "..."` should also record why the stage was accepted.
- `wrkflw:reject "..."` should record the reason, set the rework target, and move the workflow back to the nearest prior stage that can address the feedback.
- `wrkflw:next` should advance non-gated stages or report that a human gate is still pending.
- `wrkflw:reconcile "..."` should keep the workflow at the current stage, record that repository evidence is ahead of the workflow or OpenSpec artifacts, and set the next action to reconcile artifacts before new planning continues.
- `wrkflw:rework "..."` should behave like a targeted rejection/revision trigger.
- `wrkflw:refine "..."` should keep the workflow at the current stage, record the refinement request, and update the next action without treating it as a hard rejection.
- `wrkflw:rework-item "..."` should keep the workflow at the current stage, mark the named epic item or story for targeted rework, and update the next action accordingly.
- `wrkflw:proceed-only "..."` should restrict the active scope to the named epic items or stories and defer everything else for now.
- `wrkflw:defer "..."` should explicitly exclude or postpone the named epic items or stories without rejecting the entire stage.
- `wrkflw:override "..."` should be reserved for explicit user waivers of a major workflow requirement such as proceeding without OpenSpec.
- `wrkflw:resume` should restore the latest resumable checkpoint for the lane and continue the original command from the next phase; for `team-sync-all`, it should restore the latest completed result-envelope checkpoint and continue the command phase from remaining unsynced envelopes. It must refuse resume if workflow/OpenSpec inputs changed after rollback.
- `wrkflw:dag-sync` should regenerate the derived DAG from `stories.md` and keep `state.md` as the source of truth.
- `wrkflw:execution-path` should regenerate `.workflow/<slug>/execution-path.json` and `.workflow/<slug>/execution-path.md`; treat it as workflow policy for role routing, not as proof that agents have actually run.
- `wrkflw:feedback-synth` should regenerate `.workflow/<slug>/feedback-synthesis.json` and `.workflow/<slug>/feedback-synthesis.md`; flagged execution paths should not advance from review to release planning until synthesis exists, is fresh, and recommends `approve`. Promoted failure classes should influence `fix`, `split`, `block`, and `replan` decisions.
- `wrkflw:issue-advisor` should regenerate `.workflow/<slug>/issue-advisor.json` and `.workflow/<slug>/issue-advisor.md`, append `records/adaptations.jsonl`, and recommend one recovery action: `retry_approach`, `retry_modified`, `accept_with_debt`, `split`, or `escalate_to_replan`. Promoted failure classes should be considered before textual heuristics.
- `wrkflw:replan` should regenerate `.workflow/<slug>/replan.json` and `.workflow/<slug>/replan.md`, append `records/replans.jsonl`, and apply only with `confirm: replan` after input-hash validation. Approved `skip`/`defer`, `remove`, `depends`, and `order` directives should mutate only remaining stories.
- `wrkflw:verify-fix` should regenerate `.workflow/<slug>/verify-fix.json` and `.workflow/<slug>/verify-fix.md`, append `records/verify-fix.jsonl`, and block review approval until failed or unverified acceptance criteria have fix tasks or pass evidence.
- `wrkflw:ci-feedback "status: failed; check: unit tests; failure: pytest failed; provider: github"` should regenerate `.workflow/<slug>/ci-feedback.json` and `.workflow/<slug>/ci-feedback.md`, preserve a per-run snapshot under `.workflow/<slug>/ci-runs/`, append `records/ci-feedback.jsonl`, record failure classification, and block review approval until CI feedback for the current `HEAD` is ready.
- `wrkflw:accounting-record "story: Story 1; role: Implementer 1; model: gpt-test; input-tokens: 1200; output-tokens: 300; cost: 0.25; elapsed-seconds: 42"` should append `.workflow/<slug>/records/invocations.jsonl` and refresh `.workflow/<slug>/accounting.json` / `.workflow/<slug>/accounting.md`.
- `wrkflw:memory-record "category: validated-test-command; command: npm test; result: passed; evidence: local run"` should write `.workflow/<slug>/records/memory.jsonl`, refresh `.workflow/<slug>/memory.md`, and keep memory non-blocking.
- `wrkflw:debt-record "story: Story 1; type: deferred test; severity: high; summary: integration coverage is deferred"` should write `.workflow/<slug>/records/debt.jsonl`, refresh `.workflow/<slug>/debt.md`, and let downstream DAG stories inherit the warning.
- unresolved open high/critical debt should block `release-planning` and `done` until the debt record is updated to resolved or explicitly accepted.
- `wrkflw:staff "..."` should treat the reason text as staffing directives such as `team size: 5; parallel slots: 2; Implementer 2: own UI slice`.
- `wrkflw:assign "..."` should treat the reason text as role-to-responsibility mappings for `agent-assignments.md`.
- `wrkflw:assign "..."` should also accept explicit ownership directives such as `Implementer 1 ownership: src/session/state, test/session/state`.
- `wrkflw:challenge "..."` should support structured review evidence such as `role: Reviewer QA; severity: high; finding: acceptance coverage is incomplete`.
- `wrkflw:review-sync "..."` should refresh workflow visibility from accumulated review/collaboration evidence without pretending that real autonomous agent spawning already exists.
- `wrkflw:team-run "..."` should only activate when the workflow is at `implementation-planning`, `implementation`, or `review`, `dag.json` is valid, and either an active story or a first ready DAG story can be selected; it should prepare role worktrees for merge-eligible implementer lanes and record worktree path/branch metadata in dispatch packets.
- `wrkflw:team-run-level "..."` should only activate at `implementation-planning`, `implementation`, or `review`, after `dag.json` is valid and at least two ready nodes in the earliest ready level have disjoint write scopes; it should prepare per-story git worktrees and record worktree path/branch metadata in dispatch packets.
- `wrkflw:merge-gate` should be required after isolated `wrkflw:team-run` or `wrkflw:team-run-level` execution and `wrkflw:team-sync-all`, before review approval; it must be read-only and block dirty, missing, stale, conflict-prone, or out-of-scope worktree branches.
- `wrkflw:merge-apply "confirm: merge-apply"` should be required after a passing `wrkflw:merge-gate` when committed lane changes exist; it must block missing confirmation, stale gate evidence, moved branches, non-wrkflw branches, and dirty non-workflow target paths.
- `wrkflw:integration-gate` should be required after `wrkflw:merge-apply` when committed lane changes exist, before review approval; it must block missing, stale, failed, flaky, timed-out, or unreasoned-waived integration validation evidence when integration validation is required. It may run reviewed allowlist entries selected by `test-id`, using argv-only execution and append-only run records.
- `wrkflw:worktree-clean` should remove only clean wrkflw-owned git worktrees recorded in `.workflow/<slug>/worktrees/manifest.json`; it must refuse dirty, unregistered, or branch-mismatched worktrees.
- stories intended for `wrkflw:team-run-level` should declare:
  - `## Allowed Write Paths`
  - one bullet per allowed path prefix
- when `wrkflw:team-run` is used, first run the command handler so `.workflow/<slug>/team-dispatch.md`, `.workflow/<slug>/dispatch/*.md`, and merge-eligible implementer worktrees are generated.
- when `wrkflw:team-run-level` is used, first run the command handler so `.workflow/<slug>/parallel-dispatch.md`, `.workflow/<slug>/parallel-dispatch.json`, and `.workflow/<slug>/parallel-dispatch/<story-id>/implementer.md` are generated.
- when isolated worktree dispatch results have been synchronized, run `wrkflw:merge-gate`, then `wrkflw:merge-apply "confirm: merge-apply"` when committed lane changes exist, then `wrkflw:integration-gate` with either manual evidence or an allowlisted `test-id`, then `wrkflw:ci-feedback` when PR/CI evidence exists, and then `wrkflw:verify-fix` before `wrkflw:review-sync` or review approval.
- dispatch packets should require each delegated role to return a structured final report with:
  - `Schema`
  - `Role`
  - `Status`
  - `Verdict`
  - `Summary`
  - `Files changed`
  - `Validation run`
  - `Missing requirements`
  - `Incorrect assumptions`
  - `Risks`
  - `Questions`
  - `Suggested changes`
  - `Evidence`
  - `Conflict entries`
  - `Assumption updates`
  - `Red-team notes`
  - `Findings`
  - `Memory entries`
  - `Debt entries`
  - `Follow-up`
- after each delegated role returns, run `wrkflw:team-sync` with structured status updates such as `role: Implementer 1; status: done; note: gameplay loop landed; follow-up: Reviewer QA review the lane`.
- prefer writing the delegated role's structured final report to `.workflow/<slug>/agent-results/<slot>.md` and then running `wrkflw:team-sync-all`; direct pasting into `wrkflw:team-sync` remains supported.
- stored result envelopes and direct reports that declare `Schema: agent-result-v1` should be rejected before ingest if required fields or enum values are invalid.
- apply `wrkflw:team-sync` updates sequentially, not in parallel, because they all rewrite the same workflow coordination artifacts.
- when the returned agent output already clearly states what changed or that no serious findings remain, `wrkflw:team-sync` may infer role/status from that pasted output, but explicit `role` and `status` are still preferred.
- `wrkflw:team-sync` should validate any reported changed files against the role's `Allowed Write Paths` and block the lane if the report claims out-of-scope edits.
- when `Reviewer QA` or `Product Owner` final reports include findings, `wrkflw:team-sync` should write them into `review-log.md` automatically; when they report no serious findings, it should record explicit signoff evidence.
- when any role final report includes `Verdict`, `Missing requirements`, `Incorrect assumptions`, `Risks`, `Questions`, `Suggested changes`, `Evidence`, or `Red-team notes`, `wrkflw:team-sync` should write an independent review entry into `role-reviews.md`.
- when any role final report includes `Conflict entries`, `wrkflw:team-sync` should append them to `conflicts.md` and keep blocking or high-severity conflicts visible in workflow state.
- when any role final report includes `Assumption updates` or `Incorrect assumptions`, `wrkflw:team-sync` should append them to `assumptions.md` so later roles can validate or correct them.
- when any role final report includes `Debt entries`, `wrkflw:team-sync` should append typed debt to `records/debt.jsonl`, refresh `debt.md`, and let the DAG propagate that debt to downstream stories.
- when any role final report includes `Memory entries`, `wrkflw:team-sync` should append typed memory to `records/memory.jsonl`, refresh `memory.md`, and keep the learning available to later planning and dispatch.
- after the dispatch packets are generated, use Codex delegated agents to enact the team model:
  - `Product Owner`: use a `default` agent for scope/acceptance challenge
  - `Tech Lead`: use a `default` agent for decomposition/integration guidance
  - `Implementer` lanes: use `worker` agents with disjoint write ownership
  - `Reviewer QA`: use a `default` agent for review/challenge findings
- do not let spawned agents update canonical `state.md` directly.
- do not spawn implementer lanes in parallel unless ownership is clearly disjoint in `agent-assignments.md`.
- `wrkflw:team-run` should hard-block when parallel implementer lanes are enabled but their `Allowed Write Paths` are missing or overlap.
- prefer spawning Product Owner and Tech Lead in parallel with implementer work only when their tasks are not blocking the next step.
- after delegated work returns, use `wrkflw:team-sync` for role verdicts, handoff status, conflicts, assumptions, and findings; use `wrkflw:challenge` / `wrkflw:review-sync` for additional review evidence; then use the normal `wrkflw` commands to advance or block the workflow.
- workflow commands should run transactionally and preserve a journal under `.workflow/_transactions/` so failed workflow/OpenSpec updates can be rolled back cleanly.
- For `wrkflw:proceed-only` and `wrkflw:defer`, challenge the request if the selected items conflict with declared dependencies in the workflow artifacts. Do not silently accept a scope restriction that omits required dependencies.
- `wrkflw:openspec-sync` should bridge the current active story from `.workflow/...` into a real OpenSpec change when OpenSpec is available.
- Keep OpenSpec execution single-lane by default at the initiative level: one epic workflow may own the active OpenSpec lane at a time, while other epics remain workflow-only until they reach their own active `spec-authoring` pass.

Dependency convention:
- Prefer declaring dependencies in `stories.md` with a line such as `Depends on: Story 1, Story 3`.
- Keep lane-level dependencies explicit in `.workflow/<slug>/dependencies.md`.
- If no dependencies are declared, the workflow may still validate lane dependencies from `.workflow/<slug>/dependencies.md` and the reviewed capability inventory.

OpenSpec handoff convention:
- `wrkflw` owns orchestration before and after spec authoring.
- OpenSpec owns the spec artifacts during `spec-authoring`.
- When `spec-authoring` is reached and OpenSpec is available, prefer creating or updating a real change in `openspec/changes/<workflow-slug>-<story-slug>/`.
- Prefix OpenSpec change slugs with the workflow slug so parallel epic workflows do not collide, for example `openspec/changes/http-surface-story-1-http-api`.
- Do not pre-create OpenSpec changes across every epic lane during initialization. Park non-active epics as workflow-only until they become the active execution lane.
- Record the active OpenSpec change in `.workflow/<slug>/links.md`.
- When moving to the next story, create a new OpenSpec change for that story and keep previous changes as historical context. Continuity comes from:
  - the workflow artifacts in `.workflow/<slug>/`
  - earlier OpenSpec changes in `openspec/changes/`
- the implemented code already present in the repo
- explicit story dependencies declared in `stories.md`

Release-planning convention:
- Entering `release-planning` should create a concrete `release-plan.md` artifact in `.workflow/<slug>/`.
- The workflow should judge whether the current work is:
  - **production-worthy**: appropriate to release/merge as a meaningful increment
  - **local-only progress**: valid as local validation/prototyping but not yet a meaningful production increment
- That judgment should be recorded explicitly with rationale.
- If the work is not production-worthy, the release plan should say the acceptance bar is local execution and verification only.

## Relationship To Global Skill

Use the broader workflow-orchestrator conventions:
- shape before coding
- use OpenSpec per story
- keep PRs small
- use Plan mode for decomposition and sequencing
- stop at human gates
- rework the nearest prior stage when a gate is rejected

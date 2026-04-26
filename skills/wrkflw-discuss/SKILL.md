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
- `wrkflw:staff "..."`
- `wrkflw:assign "..."`
- `wrkflw:challenge "..."`
- `wrkflw:review-sync "..."`
- `wrkflw:team-run "..."`
- `wrkflw:team-sync "..."`

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
- `team-dispatch.md` should record the current delegated execution packet index for the active workflow lane
- `wrkflw` should synchronize `execution-board.md` with the current workflow stage so owner and handoff state remain visible
- `wrkflw` should use the team model when generating `implementation-plan.md`, especially team size and parallel implementation slots
- `wrkflw` should require late-stage review evidence in `review-log.md` when Product Owner or Reviewer QA signoff is configured as required
- `wrkflw:staff` should update team-config or team-overrides without forcing the user to hand-edit markdown for common staffing changes
- `wrkflw:assign` should update per-epic role ownership in `agent-assignments.md`
- `wrkflw:challenge` should record structured team challenges in `review-log.md` and reflect them in workflow state
- `wrkflw:review-sync` should resynchronize review evidence back into workflow state and execution-board visibility
- `wrkflw:team-sync` should synchronize delegated role outcomes such as implementer completion, reviewer start, handoff notes, and lane status back into `execution-board.md`, `agent-assignments.md`, and `team-minutes.md`
- team-control commands should also append readable minutes to `team-minutes.md` so the collaboration history is explicit
- `wrkflw:team-run` should generate a delegated execution packet set and, when the user has explicitly asked for multi-agent execution, use those packets to spawn real role agents

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
python3 scripts/handle_workflow_command.py --slug <slug> --root <repo-root> --command <approve|reject|rework|refine|rework-item|proceed-only|defer|next|staff|assign|challenge|review-sync|team-run|team-sync> [--reason "..."] [--items "..."] [--design-file <path>]
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
- `wrkflw:staff "..."` should treat the reason text as staffing directives such as `team size: 5; parallel slots: 2; Implementer 2: own UI slice`.
- `wrkflw:assign "..."` should treat the reason text as role-to-responsibility mappings for `agent-assignments.md`.
- `wrkflw:assign "..."` should also accept explicit ownership directives such as `Implementer 1 ownership: src/session/state, test/session/state`.
- `wrkflw:challenge "..."` should support structured review evidence such as `role: Reviewer QA; severity: high; finding: acceptance coverage is incomplete`.
- `wrkflw:review-sync "..."` should refresh workflow visibility from the accumulated `review-log.md` evidence without pretending that real autonomous agent spawning already exists.
- `wrkflw:team-run "..."` should only activate when the workflow already has an active story and is at `implementation-planning`, `implementation`, or `review`.
- when `wrkflw:team-run` is used, first run the command handler so `.workflow/<slug>/team-dispatch.md` and `.workflow/<slug>/dispatch/*.md` are generated.
- after each delegated role returns, run `wrkflw:team-sync` with structured status updates such as `role: Implementer 1; status: done; note: gameplay loop landed; follow-up: Reviewer QA review the lane`.
- apply `wrkflw:team-sync` updates sequentially, not in parallel, because they all rewrite the same workflow coordination artifacts.
- when the returned agent output already clearly states what changed or that no serious findings remain, `wrkflw:team-sync` may infer role/status from that pasted output, but explicit `role` and `status` are still preferred.
- after the dispatch packets are generated, use Codex delegated agents to enact the team model:
  - `Product Owner`: use a `default` agent for scope/acceptance challenge
  - `Tech Lead`: use a `default` agent for decomposition/integration guidance
  - `Implementer` lanes: use `worker` agents with disjoint write ownership
  - `Reviewer QA`: use a `default` agent for review/challenge findings
- do not let spawned agents update canonical `state.md` directly.
- do not spawn implementer lanes in parallel unless ownership is clearly disjoint in `agent-assignments.md`.
- `wrkflw:team-run` should hard-block when parallel implementer lanes are enabled but their `Allowed Write Paths` are missing or overlap.
- prefer spawning Product Owner and Tech Lead in parallel with implementer work only when their tasks are not blocking the next step.
- after delegated work returns, use `wrkflw:team-sync` for role and handoff status, use `wrkflw:challenge` / `wrkflw:review-sync` for review evidence, then use the normal `wrkflw` commands to advance or block the workflow.
- For `wrkflw:proceed-only` and `wrkflw:defer`, challenge the request if the selected items conflict with declared dependencies in the workflow artifacts. Do not silently accept a scope restriction that omits required dependencies.
- `wrkflw:openspec-sync` should bridge the current active story from `.workflow/...` into a real OpenSpec change when OpenSpec is available.
- Keep OpenSpec execution single-lane by default at the initiative level: one epic workflow may own the active OpenSpec lane at a time, while other epics remain workflow-only until they reach their own active `spec-authoring` pass.

Dependency convention:
- Prefer declaring dependencies in `stories.md` with a line such as `Depends on: Story 1, Story 3`.
- If no dependencies are declared, the workflow may proceed but should note that dependency validation is based only on explicit declarations, not inference.

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

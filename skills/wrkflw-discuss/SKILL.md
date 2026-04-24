---
name: wrkflw-discuss
description: Use when the user writes wrkflw:discuss, asks to start a reusable engineering workflow, or wants a workflow-guided discussion that proceeds through stages, asks relevant questions, and stops at human approval gates.
---

# wrkflw:discuss

Treat `wrkflw:discuss "..."` as an explicit request to start or continue a staged workflow discussion.

When starting a workflow, first look for a design seed:
- auto-detect `design.md` or `docs/design.md` in the active repo
- if the user gives an explicit file path, prefer that path instead
- seed the workflow from that file before shaping epic/story artifacts
- record the seed in `.workflow/<slug>/links.md` and `.workflow/<slug>/design-seed.md`

Also treat these as workflow control intents:
- `wrkflw:approve`
- `wrkflw:approve "..."`
- `wrkflw:reject "..."`
- `wrkflw:rework "..."`
- `wrkflw:refine "..."`
- `wrkflw:rework-item "..."`
- `wrkflw:proceed-only "..."`
- `wrkflw:defer "..."`
- `wrkflw:override "..."`
- `wrkflw:openspec-sync`
- `wrkflw:next`

## Behavior

1. Classify the request as epic, story, bug, spike, or refactor.
2. Identify the current stage.
3. Create or refresh a capability inventory before story slicing so sample and harness work does not converge too early on a thin result.
4. Ask only the minimum relevant questions.
5. Recommend the next tool and mode.
6. Stop at human approval gates.
7. If useful, initialize a local workflow workspace in the current repo.
8. If a gate is rejected, record the rejection and route work back to the right prior stage.
9. When the user issues `wrkflw:approve`, `wrkflw:reject`, or `wrkflw:next`, prefer the companion command handler script over manual state edits.

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
- `design-seed.md` when a design file is used

State should capture:
- current stage
- human gate status
- blocked reason when a hard workflow precondition is not satisfied
- rework target
- rejection reason
- next action

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
- `OpenSpec waiver reason: ...`

The workflow should also maintain a live PlantUML diagram at:

```text
.workflow/<slug>/diagram.puml
```

Update it after each workflow action and OpenSpec bridge action so progress is visible in near real time.

If the workspace is missing and the user wants one, run the companion script:

```text
python3 scripts/init_workflow_workspace.py --slug <slug> --root <repo-root> [--design-file <path>]
```

To update an existing workflow state after approval or rejection, use the companion state script if available.

Preferred command handler:

```text
python3 scripts/handle_workflow_command.py --slug <slug> --root <repo-root> --command <approve|reject|rework|refine|rework-item|proceed-only|defer|next> [--reason "..."] [--items "..."] [--design-file <path>]
```

Behavior expectations:
- `wrkflw:discuss` should prefer the design seed as the initial source of truth when one exists, instead of relying only on the user’s one-line summary.
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
- `wrkflw:rework "..."` should behave like a targeted rejection/revision trigger.
- `wrkflw:refine "..."` should keep the workflow at the current stage, record the refinement request, and update the next action without treating it as a hard rejection.
- `wrkflw:rework-item "..."` should keep the workflow at the current stage, mark the named epic item or story for targeted rework, and update the next action accordingly.
- `wrkflw:proceed-only "..."` should restrict the active scope to the named epic items or stories and defer everything else for now.
- `wrkflw:defer "..."` should explicitly exclude or postpone the named epic items or stories without rejecting the entire stage.
- `wrkflw:override "..."` should be reserved for explicit user waivers of a major workflow requirement such as proceeding without OpenSpec.
- For `wrkflw:proceed-only` and `wrkflw:defer`, challenge the request if the selected items conflict with declared dependencies in the workflow artifacts. Do not silently accept a scope restriction that omits required dependencies.
- `wrkflw:openspec-sync` should bridge the current active story from `.workflow/...` into a real OpenSpec change when OpenSpec is available.

Dependency convention:
- Prefer declaring dependencies in `stories.md` with a line such as `Depends on: Story 1, Story 3`.
- If no dependencies are declared, the workflow may proceed but should note that dependency validation is based only on explicit declarations, not inference.

OpenSpec handoff convention:
- `wrkflw` owns orchestration before and after spec authoring.
- OpenSpec owns the spec artifacts during `spec-authoring`.
- When `spec-authoring` is reached and OpenSpec is available, prefer creating or updating a real change in `openspec/changes/<slug>/`.
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

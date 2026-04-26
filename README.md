# wrkflw

`wrkflw` is a Codex plugin for staged engineering delivery. It guides work from discovery through epic shaping, story slicing, spec authoring, implementation, review, and release while keeping small PRs, human gates, OpenSpec handoff, and live workflow diagrams in sync.

## What it supports

- `wrkflw:discuss`
- `wrkflw:approve`
- `wrkflw:reject`
- `wrkflw:rework`
- `wrkflw:refine`
- `wrkflw:rework-item`
- `wrkflw:proceed-only`
- `wrkflw:defer`
- `wrkflw:override`
- `wrkflw:next`
- `wrkflw:staff`
- `wrkflw:assign`
- `wrkflw:challenge`
- `wrkflw:review-sync`
- `wrkflw:team-sync`
- `wrkflw:team-sync-all`
- `wrkflw:team-run`

It also supports:
- design seed detection from `design.md` or `docs/design.md`
- normalization of broad design documents into workflow-ready design artifacts
- automatic OpenSpec handoff during `spec-authoring`
- workflow state and PlantUML diagram generation under `.workflow/<slug>/`
- release-plan generation and OpenSpec archive on story closeout

## Install

### Quick install

Clone the repo into your local plugins directory:

```bash
git clone git@github.com:iamanandkris/wrkflw.git ~/plugins/wrkflw
```

If you use a custom plugin path, clone it there instead.

Or use the helper script from an existing clone:

```bash
./scripts/install_local.sh
```

That installs or updates the plugin into:

```text
~/plugins/wrkflw
```

### Make Codex discover it

Make sure your local Codex plugin marketplace/config points at the plugin folder.

If you already use a marketplace file such as:

```text
~/.agents/plugins/marketplace.json
```

add an entry that points at the cloned plugin directory.

Minimal example:

```json
{
  "plugins": [
    {
      "name": "wrkflw",
      "path": "/Users/<you>/plugins/wrkflw"
    }
  ]
}
```

If your Codex setup discovers plugins directly from a local plugin root, just placing the repo here is enough:

```text
~/plugins/wrkflw
```

### VS Code / Codex note

This repo is a Codex plugin plus skill bundle. It does not install as a generic VS Code marketplace extension. The usual path is:

1. clone the repo locally
2. point your Codex plugin configuration at that local path
3. restart or reload Codex if plugin discovery is cached

## Requirements

- Python 3
- PlantUML source rendering support if you want to render the generated `.puml` files
- OpenSpec installed if you want real OpenSpec changes instead of workflow-only artifacts

## Usage

Start a workflow:

```text
wrkflw:discuss "Implement feature X"
```

Example:

- `examples/caseflow-example.md`
  - end-to-end multi-epic backend example showing design normalization, OpenSpec lane control, delegated team execution, and the workflow hardening that came out of a real project

Start a workflow from a design seed:

```text
wrkflw:discuss "Start this workflow from the design in docs/design.md"
```

If the repo contains `design.md` or `docs/design.md`, `wrkflw` will use that as a seed automatically.

If the design document is broad or not already workflow-shaped, `wrkflw` first generates normalized planning artifacts and an epic-specific design slice before it uses the design for workflow shaping.
That normalization pass should preserve section semantics where possible, so overview, actor, capability, architecture, and operational sections can map into cleaner epic candidates instead of one flattened backlog.

The workflow creates artifacts under:

```text
.workflow/<slug>/
```

with a lightweight parent registry at:

```text
.workflow/initiative-index.md
```

including:
- `context.md`
- `capabilities.md`
- `state.md`
- `history.md`
- `links.md`
- `gates.md`
- `diagram-config.md`
- `workflow-contract.md`
- `dependencies.md`
- `team-overrides.md`
- `agent-assignments.md`
- `execution-board.md`
- `review-log.md`
- `team-minutes.md`
- `runtime-contract.md`
- `agent-sync-ledger.md`
- `agent-results/`
- `team-dispatch.md`
- `design-slice.md` when the workflow is seeded from a broader design source
- `design-seed.md` when applicable
- `diagram-flow.puml`
- `diagram-work.puml`

State contract:
- `state.md` is the source of truth for current workflow status
- `history.md` is the source of truth for completed progression trail
- `diagram-flow.puml` and `diagram-work.puml` are derived artifacts and should be regenerated after each workflow state change
- `Current stage` must use only:
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
- `Human gate status` must use only:
  - `pending`
  - `approved`
  - `blocked`
  - `rejected`
- avoid freeform labels like `epic-shaped`, `story-sliced`, or `awaiting approval`

When a broader design is present, `wrkflw` also creates shared normalization artifacts under:

```text
.workflow/_normalized/
```

including:
- `master-design.md`
- `epic-candidates.md`

The initiative index tracks each workflow slug as a separate epic lane with its current stage, design source, recorded OpenSpec change, and supporting docs.

### Team execution

`wrkflw` now seeds a default team model at:

```text
.workflow/team-config.md
```

The default team is:
- `Product Owner`
- `Tech Lead`
- `Implementer`
- `Reviewer QA`

Use this file to specify or override:
- team size
- team structure
- role responsibilities
- parallel implementation slots
- approval expectations

For epic-specific changes, use:

```text
.workflow/<slug>/team-overrides.md
```

Each workflow lane also gets:
- `agent-assignments.md`
- `execution-board.md`
- `review-log.md`
- `team-minutes.md`
- `runtime-contract.md`
- `dependencies.md`
- `agent-sync-ledger.md`
- `agent-results/`
- `team-dispatch.md` and `dispatch/*.md` after delegated team execution is prepared

These are intended to model a small engineering team where design, coding, and challenge/review are separated instead of letting every agent write to everything.

Current behavioral integration:
- `execution-board.md` is automatically synchronized with the active workflow stage, handoff, and owner
- `implementation-plan.md` is team-aware and uses team size / parallel implementation slots when suggesting ownership
- `review-log.md` is used for late-stage challenge/signoff checks:
  - `Reviewer QA` evidence is required before `release-planning` when reviewer signoff is enabled
  - `Product Owner` evidence is required before `done` when product-owner signoff is enabled
- `team-minutes.md` records staffing decisions, role assignments, team-run dispatch preparation, challenge discussions, and review-sync outcomes
- `runtime-contract.md` records the current file-driven team runtime contract and prepares the workflow for future delegated-agent execution without claiming automatic spawning today
- `dependencies.md` records first-class lane dependencies such as `Depends on`, `Blocked by`, and `Unlocks`
- `agent-results/` stores structured delegated-agent result envelopes
- `agent-sync-ledger.md` records which result envelopes have already been synchronized into workflow state
- `wrkflw:team-run` upgrades the current lane into delegated-runtime mode, generates role dispatch packets, and gives Codex the packets needed to spawn real role agents

Team control commands:
- `wrkflw:staff`
  - update team size, parallel slots, and role override notes in `team-config.md` or `team-overrides.md`
- `wrkflw:assign`
  - update `agent-assignments.md` with role ownership for the active workflow lane
  - include explicit write scopes such as `Implementer 1 ownership: src/session/state, test/session/state`
- `wrkflw:challenge`
  - append structured review/challenge evidence to `review-log.md` and surface it in workflow state
- `wrkflw:review-sync`
  - resynchronize workflow state and execution-board review notes from `review-log.md`
- `wrkflw:team-sync`
  - record delegated role progress such as implementer completion, reviewer start, or handoff notes
  - synchronize `execution-board.md`, `agent-assignments.md`, `team-minutes.md`, `review-log.md`, and implementation-plan context from that role update
  - validate reported changed files against the role's allowed write scope
- `wrkflw:team-sync-all`
  - ingest every unsynchronized structured result envelope from `.workflow/<slug>/agent-results/`
  - update `agent-sync-ledger.md` so replaying the same envelopes becomes a no-op
- all team commands also append an entry to `team-minutes.md` so the collaboration trail stays readable
- `wrkflw:team-run`
  - generate `.workflow/<slug>/team-dispatch.md`
  - generate `.workflow/<slug>/dispatch/*.md` role packets
  - switch `runtime-contract.md` into `delegated-agent-team` mode for the active lane

Suggested formats:

```text
wrkflw:staff "team size: 5; parallel slots: 2; Implementer 2: own UI slice"
wrkflw:assign "Implementer 1: schema and fixtures; Reviewer QA: regression and acceptance review"
wrkflw:challenge "role: Reviewer QA; severity: high; finding: acceptance coverage is incomplete"
wrkflw:review-sync "Reviewer QA and Product Owner evidence recorded"
wrkflw:team-sync "role: Implementer 1; status: done; note: gameplay loop landed; follow-up: Reviewer QA review the lane"
wrkflw:team-sync-all "batch synced delegated result envelopes"
wrkflw:team-run "Dispatch the active story with parallel implementer lanes"
```

### Delegated team run

`wrkflw:team-run` is the bridge from workflow artifacts to real parallel Codex agents.

Expected sequence:
- the workflow must already have an active story
- the current stage should be `implementation-planning`, `implementation`, or `review`
- `wrkflw` generates dispatch packets under:
  - `.workflow/<slug>/team-dispatch.md`
  - `.workflow/<slug>/dispatch/*.md`
- as delegated role work returns, write each structured final report into `.workflow/<slug>/agent-results/` and then synchronize with `wrkflw:team-sync-all` or `wrkflw:team-sync`
- each delegated role should return a structured final report with:
  - `Role`
  - `Status`
  - `Summary`
  - `Files changed`
  - `Validation run`
  - `Findings`
  - `Follow-up`
- apply `wrkflw:team-sync` updates sequentially rather than in parallel, because they update shared workflow coordination files
- prefer storing each structured final report in `.workflow/<slug>/agent-results/` and using `wrkflw:team-sync-all`; pasting directly into `wrkflw:team-sync` is still supported
- `wrkflw:team-sync` can infer role/status from pasted agent output when the output is clear, but explicit `role:` and `status:` remain safer
- reviewer and product-owner reports with findings are written into `review-log.md` automatically; clean reviewer/product-owner reports create explicit signoff evidence
- Codex can then spawn the role agents from those packets:
  - `Product Owner`
  - `Tech Lead`
  - `Implementer 1`
  - `Implementer 2` when enabled
  - `Reviewer QA`

Execution model:
- `Product Owner` and `Tech Lead` can run in parallel for scope and decomposition checks
- implementer lanes can run in parallel only when ownership is disjoint
- `Reviewer QA` reviews after implementer output exists
- canonical `state.md` remains orchestrator-owned

Current limit:
- the Python plugin scripts generate the dispatch contract and packets
- actual `spawn_agent` calls happen in Codex when `wrkflw:team-run` is invoked, not inside the Python scripts themselves
- parallel implementer lanes must have explicit, disjoint `Allowed Write Paths` in `agent-assignments.md` or `wrkflw:team-run` will block
- delegated role completion should be fed back through `wrkflw:team-sync` so execution-board status, team minutes, diagrams, and implementation-plan context stay current
- workflow commands now run inside a transaction journal under `.workflow/_transactions/`, so failed commands can roll back workflow and OpenSpec artifacts instead of leaving half-written state behind

### Diagram history and compact vs expanded views

`wrkflw` now keeps a persisted transition history in:

```text
.workflow/<slug>/history.md
```

This is used to keep completed stories visible in both diagrams instead of inferring everything only from the current `state.md` snapshot.

Diagram rendering behavior is controlled by:

```text
.workflow/<slug>/diagram-config.md
```

Default example:

```text
# Diagram Config

- flow.completedStoriesView: expanded
- flow.showStoryProgressHistory: true
- work.showStoryProgressHistory: true
```

What these do:

- `flow.completedStoriesView: expanded`
  - show each completed story with its stage trail, such as `story-enrichment -> spec-authoring -> implementation -> review -> done`
- `flow.completedStoriesView: compact`
  - keep completed stories visible, but collapse them to a shorter summary
- `flow.showStoryProgressHistory: true`
  - keep completed-story progression visible in `diagram-flow.puml`
- `work.showStoryProgressHistory: true`
  - keep story progression visible in `diagram-work.puml`

This is not interactive folding inside PlantUML itself. The intended model is:

- use `expanded` when you want the full story trail
- switch to `compact` when the completed-history panel becomes too large

### Capability inventory

Each workflow also gets:

```text
.workflow/<slug>/capabilities.md
```

This is generated automatically from the available design seed and workflow context. Its purpose is to stop `wrkflw` from converging too early on a thin result.

It captures:

- the inferred workflow mode
- the capability categories the workflow should consider
- whether each capability is `required`, `recommended`, or `optional`
- story prompts that can be turned into future slices

Typical workflow modes:

- `tutorial-sample`
  - optimize for pedagogy and a clear learning path
- `feature-harness`
  - optimize for broader capability coverage and realistic feature comparison
- `product-service`
  - optimize for runtime/service behavior and realistic execution paths
- `general-delivery`
  - default mode when no stronger signal exists

The main use of `capabilities.md` is to improve early planning:

- review it before story slicing
- use it to name stories more concretely
- use it to decide what is intentionally deferred
- use it to avoid stopping after the first few obvious examples

`wrkflw` now uses this file directly when the workflow enters `story-slicing`:

- it regenerates `.workflow/<slug>/stories.md`
- it groups capabilities differently depending on workflow mode
- it keeps story names and dependencies closer to the intended capability coverage

That means the capability inventory is no longer just review guidance. It is the actual seed for early story generation.

Example outcomes:

- `tutorial-sample`
  - tends to produce narrower learning-path stories such as:
    - core contract usage
    - field validation
    - visibility / field semantics
    - nested structures
    - developer guidance
- `feature-harness`
  - tends to produce broader grouped slices such as:
    - core contract surface
    - validation and sanitization coverage
    - update and schema flows
    - runtime integration
    - developer guidance

If the generated story slices are still too broad or too thin, review and rework `capabilities.md` at the `capability-review` gate before accepting the story plan.

### Gate configuration

Each workflow has a gate config file:

```text
.workflow/<slug>/gates.md
```

Default example:

```text
# Gates

- capability-review.autoApprove: false
- epic-shaping.autoApprove: false
- story-slicing.autoApprove: false
- story-enrichment.autoApprove: false
- spec-authoring.autoApprove: false
- review.autoApprove: false
- release-planning.autoApprove: false
```

Set a gate to `true` if you want `wrkflw` to skip waiting for manual approval at that stage.

Example:

```text
- story-enrichment.autoApprove: true
- spec-authoring.autoApprove: true
```

With that configuration, entering `story-enrichment` or `spec-authoring` will not pause for human approval. `wrkflw` will record that those gates were auto-approved and continue automatically to the next stage.

### Workflow contract

Each workflow also has:

```text
.workflow/<slug>/workflow-contract.md
```

Default example:

```text
# Workflow Contract

- OpenSpec required: true
- OpenSpec initialized: false
- OpenSpec waived: false
- OpenSpec lane active: false
- OpenSpec waiver reason:
```

This file exists to stop the agent from making major workflow deviations silently.

Hard rule:
- if `OpenSpec required: true`
- and the workflow reaches `spec-authoring`
- and OpenSpec is not initialized

then `wrkflw` must block instead of continuing toward implementation.

The only supported bypass is an explicit user waiver, for example:

```text
wrkflw:override "Proceed without OpenSpec for this run."
```

## Workflow Gates And Control Commands

`wrkflw` is intentionally stage-driven. It stops at human gates instead of pushing through the whole workflow blindly.

### Main gated stages

- `capability-review`
  - review the generated capability inventory and decide whether the sample or harness coverage is broad enough before epic shaping starts
- `epic-shaping`
  - review the business problem, goal, non-goals, and constraints
- `story-slicing`
  - review whether the capability-driven story plan is split into small, independently mergeable stories
- `story-enrichment`
  - review the active story’s scope, acceptance criteria, test expectations, and risks
- `spec-authoring`
  - review the proposal, spec, and tasks before implementation
  - if OpenSpec is required but missing, this stage blocks instead of continuing
- `review`
  - review the implemented slice and validation outcome
- `release-planning`
  - review whether the work is production-worthy or only local-only progress

### What `wrkflw:approve` means

Use `wrkflw:approve` when the current stage is good enough to move forward.

Examples:

```text
wrkflw:approve "Story 2 enrichment is ready for spec authoring."
wrkflw:approve "Proceed with the first PR-sized slice."
wrkflw:approve "This slice is local-only progress and the acceptance bar is local test success."
```

Approval does two things:
- records why the stage was accepted
- advances the workflow to the next stage

At some stages it also triggers artifact generation. The most important example is:
- approving into `story-slicing` regenerates `stories.md` from `capabilities.md`

### What `wrkflw:reject` means

Use `wrkflw:reject` when the current artifact is not good enough to proceed.

Example:

```text
wrkflw:reject "The story is too broad and needs to be split into two slices."
```

Rejection does three things:
- records the rejection reason
- routes the workflow back to the nearest stage that can address the issue
- updates the next action to reflect the rework needed

### What `wrkflw:refine` means

Use `wrkflw:refine` when the stage is mostly correct but you want to improve it without treating it as a hard rejection.

Example:

```text
wrkflw:refine "Add acceptance criteria and test expectations for Story 3 only."
```

Refine keeps the workflow on the current stage and updates the next action. It is the right command for:
- tightening wording
- generating a missing artifact
- adding detail before approval
- selecting a first PR-sized slice during implementation planning

### What `wrkflw:rework` means

Use `wrkflw:rework` for a stronger revision signal when the current stage needs to be actively reworked, but you want to express that as a targeted correction rather than just a generic rejection message.

Example:

```text
wrkflw:rework "The spec needs to reflect the design seed more closely."
```

This behaves like a targeted revision trigger and routes work back through the proper stage.

### What `wrkflw:rework-item` means

Use `wrkflw:rework-item` when only a specific story or epic item needs attention, rather than the whole current stage.

Example:

```text
wrkflw:rework-item "Story 2" "Split the capability tests into two smaller slices."
```

### What `wrkflw:proceed-only` means

Use `wrkflw:proceed-only` to narrow active scope to one or more specific stories.

Example:

```text
wrkflw:proceed-only "Story 2" "Start the first real capability slice."
```

This is useful after one story closes and you want to activate the next story explicitly.

`wrkflw` will challenge this command if the selected story depends on unfinished required stories.

### What `wrkflw:defer` means

Use `wrkflw:defer` to postpone specific stories or items without rejecting the whole stage.

Example:

```text
wrkflw:defer "Story 4" "Documentation can wait until the capability slices are in place."
```

`wrkflw` will challenge this command if active scope still depends on the deferred item.

### What `wrkflw:override` means

Use `wrkflw:override` only when you explicitly want to waive a major workflow requirement.

Example:

```text
wrkflw:override "Proceed without OpenSpec for this run."
```

This is not a normal convenience command. It exists for cases where:
- the workflow contract requires OpenSpec
- OpenSpec is not initialized
- you intentionally choose to proceed anyway

That decision must come from the user, not from the agent.

### What `wrkflw:next` means

Use `wrkflw:next` only when you want the workflow to advance automatically from a non-gated stage.

If a human gate is still pending, `wrkflw:next` should not bypass it.

### Typical approval sequence for one story

For a normal story, the flow is usually:

1. `capability-review` approved
2. `epic-shaping` approved
3. `story-slicing` approved
4. `story-enrichment` approved
5. `spec-authoring` approved
6. `implementation-planning` approved
7. implementation happens
8. `review` approved
9. `release-planning` approved
10. story closes and OpenSpec change is archived

### How to decide between commands

- Use `approve` when the current stage is ready to move on.
- Use `reject` when the stage is wrong and must go back.
- Use `refine` when the stage is close but needs more detail or sharper scope.
- Use `rework` when you want to force a stronger targeted revision.
- Use `rework-item` when only one story/item is problematic.
- Use `proceed-only` when selecting the next active story or narrowing scope.
- Use `defer` when explicitly postponing non-active items.

## OpenSpec

When the workflow reaches `spec-authoring` and OpenSpec is available, `wrkflw` creates or updates an OpenSpec change under:

```text
openspec/changes/<workflow-slug>-<story-slug>/
```

OpenSpec execution is single-lane by default at the initiative level:
- one epic workflow may own the active OpenSpec lane at a time
- other epic workflows stay workflow-only until they become the active execution lane
- `wrkflw` should not pre-create OpenSpec changes across every epic lane during initialization

On final closeout, it archives the change automatically.

If OpenSpec is required but not initialized, `wrkflw` now hard-blocks at `spec-authoring` until one of these is true:
- OpenSpec is initialized
- the user explicitly issues a waiver with `wrkflw:override "..."`

`wrkflw` now also carries capability coverage into the OpenSpec artifacts:

- `proposal.md` includes:
  - workflow mode
  - capability categories intentionally covered by the active story
  - required/recommended capabilities that remain deferred
- `spec.md` includes:
  - explicit coverage scenarios for the current story
  - explicit deferred-coverage visibility when the story is only a partial slice
- `tasks.md` includes:
  - tasks to make the intended capability coverage explicit
  - tasks to leave follow-up context for deferred capability categories

This means `capabilities.md` does not just help early story slicing. It now flows through into OpenSpec so spec authoring keeps the broader capability intent visible.

## Notes

- Dependency challenges are based on explicit story dependencies declared in `stories.md`.
- `wrkflw` is designed to keep work incremental and reviewable rather than implementing everything in one pass.

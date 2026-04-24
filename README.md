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
- `wrkflw:next`

It also supports:
- design seed detection from `design.md` or `docs/design.md`
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

Start a workflow from a design seed:

```text
wrkflw:discuss "Start this workflow from the design in docs/design.md"
```

If the repo contains `design.md` or `docs/design.md`, `wrkflw` will use that as a seed automatically.

The workflow creates artifacts under:

```text
.workflow/<slug>/
```

including:
- `context.md`
- `capabilities.md`
- `state.md`
- `links.md`
- `gates.md`
- `design-seed.md` when applicable
- `diagram-flow.puml`
- `diagram-work.puml`

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

## Workflow Gates And Control Commands

`wrkflw` is intentionally stage-driven. It stops at human gates instead of pushing through the whole workflow blindly.

### Main gated stages

- `capability-review`
  - review the generated capability inventory and decide whether the sample or harness coverage is broad enough before epic shaping starts
- `epic-shaping`
  - review the business problem, goal, non-goals, and constraints
- `story-slicing`
  - review whether the work is split into small, independently mergeable stories
- `story-enrichment`
  - review the active story’s scope, acceptance criteria, test expectations, and risks
- `spec-authoring`
  - review the proposal, spec, and tasks before implementation
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
openspec/changes/<change-slug>/
```

On final closeout, it archives the change automatically.

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

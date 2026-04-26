# wrkflw Example: CaseFlow End-to-End

This document explains how to use `wrkflw` by walking through the `caseflow-experiment` initiative from broad design to completed multi-epic delivery.

The point of this example is not only to show the happy path. It also shows how `wrkflw` was used to:

- normalize a broad design document into workflow-ready artifacts
- split a large initiative into epic-specific workflow lanes
- keep OpenSpec aligned with the active lane
- use a team-style execution model with delegated roles
- review and challenge work before approval
- detect and fix gaps in `wrkflw` itself while running a real project

## What The Project Was

The project is a backend-heavy case-management prototype built with:

- Java 21
- Spring Boot
- Maven
- Concentric for contract definitions and runtime lifecycle handling

The original design source was:

- `caseflow-orchestrator-design.md`

The completed code lives in:

- `caseflow-domain-model/`
- `caseflow-contract-runtime/`

The completed workflow initiative is tracked in:

- `.workflow/initiative-index.md`

## What wrkflw Produced

Starting from one broad design document, `wrkflw` created:

- normalized initiative design artifacts in `.workflow/_normalized/`
- one workflow lane per epic in `.workflow/<slug>/`
- one active OpenSpec lane at a time under `openspec/changes/`
- per-lane diagrams:
  - `diagram-flow.puml`
  - `diagram-work.puml`
- team execution artifacts:
  - `team-config.md`
  - `team-overrides.md`
  - `agent-assignments.md`
  - `execution-board.md`
  - `review-log.md`
  - `team-minutes.md`
  - `runtime-contract.md`
  - `dependencies.md`
  - `agent-results/`
  - `agent-sync-ledger.md`

## The Epic Split

`wrkflw` normalized the broad design and split the initiative into these lanes:

1. `contract-and-lifecycle-foundation`
2. `core-case-and-task-orchestration`
3. `approvals-and-decision-governance`
4. `evidence-intake-and-secure-storage`
5. `queue-operations-and-sla-management`
6. `audit-search-and-timeline-reconstruction`
7. `admin-template-design-experience`

An extra verification lane was later used to test the newer runtime model:

8. `spring-rest-surface`

The original seven are the real project epics. The eighth was a deliberate workflow validation lane.

## How The Workflow Was Started

The effective start pattern was:

```text
Use wrkflw for /path/to/caseflow-experiment.

Start with `wrkflw:discuss`.
A broad design document already exists at `/path/to/caseflow-orchestrator-design.md`.

Treat this as a multi-epic initiative, not a single workflow.
Inspect the existing repo first if code already exists.
Normalize the design, create `.workflow/initiative-index.md`, and initialize one workflow slug per epic.
Keep non-active epics as workflow-only until they become active.
Allow only one active OpenSpec lane at a time.
```

That caused `wrkflw` to:

- inspect the repo state
- normalize the broad design
- generate epic candidates
- create `.workflow/<slug>/design-slice.md` for each lane
- keep diagrams isolated per lane
- avoid creating OpenSpec for every lane up front

## The Typical Lane Lifecycle

For each epic lane, the flow was:

1. `discuss`
2. `capability-review`
3. `epic-shaping`
4. `story-slicing`
5. `story-enrichment`
6. `spec-authoring`
7. `implementation-planning`
8. `implementation`
9. `review`
10. `release-planning`
11. `done`

Approvals were explicit. `wrkflw` advanced lanes using commands like:

- `wrkflw:approve`
- `wrkflw:reject`
- `wrkflw:override`

## How Team Execution Worked

This project also exercised the team model, not just single-agent execution.

The workflow used these role concepts:

- `Product Owner`
- `Tech Lead`
- `Implementer 1`
- `Implementer 2`
- `Reviewer QA`

Typical commands were:

```text
wrkflw:staff "team size: 5; parallel slots: 2"
```

```text
wrkflw:assign "Implementer 1: runtime services; Implementer 1 ownership: src/main/java/...; Implementer 2: tests and secondary slice; Implementer 2 ownership: src/test/java/...; Reviewer QA: review and regression checks"
```

```text
wrkflw:team-run "Dispatch active story"
```

`wrkflw` then generated role packets under:

- `.workflow/<slug>/dispatch/`

and expected structured role outputs under:

- `.workflow/<slug>/agent-results/`

Those role outputs were ingested back into the workflow with:

```text
wrkflw:team-sync-all
```

That updated:

- `state.md`
- `execution-board.md`
- `review-log.md`
- `team-minutes.md`
- `agent-sync-ledger.md`
- diagrams

## What The Team Model Added

The team model made several things explicit:

- who owned each slice
- which paths each implementer was allowed to modify
- when a reviewer had blocked or approved work
- which findings still needed resolution
- what discussions and handoffs had happened

This mattered because the project used real parallel execution in some lanes and needed to avoid file collisions and stale workflow state.

## What Was Actually Implemented

By the end of the initiative, the caseflow prototype supported:

- contract-backed case and task models
- strict runtime sanitization of public case views
- lifecycle transition enforcement with structured validation feedback
- approval-gated progression to `approved`
- evidence metadata with secure/internal fields filtered from public views
- queue and SLA metadata on tasks
- reconstructable audit timeline records
- a thin API/event surface
- a Spring REST verification slice proving the newer delegated runtime workflow

## What We Had To Fix In wrkflw Along The Way

This project was used to harden `wrkflw` in real conditions. The important fixes were:

### 1. Multi-epic planning

Originally, `wrkflw` was too single-epic-oriented. It had to be extended to:

- normalize broad design documents first
- split a design into epic-specific lanes
- maintain `.workflow/initiative-index.md`
- keep diagrams local to each lane
- prefix OpenSpec changes with the workflow slug

### 2. OpenSpec drift and eager creation

We fixed:

- stale OpenSpec versus implemented code
- creation of too many OpenSpec changes too early
- lane confusion where later epics tried to replay completed prior-epic work

The corrected model became:

- one active OpenSpec lane at a time
- later lanes remain workflow-only until they reach `spec-authoring`
- completed prior epics count as satisfied dependencies

### 3. Diagram coherence

We fixed:

- stale or generic story labels
- team-mode status not showing correctly
- delegated execution not reflecting lane ownership and handoff clearly
- runtime and diagram state drifting apart

### 4. Team execution visibility

We added:

- execution boards
- team minutes
- review logs
- explicit write-scope enforcement
- delegated runtime packets
- role result envelopes
- batch ingestion with `team-sync-all`

### 5. Transaction safety and result ingestion

We added:

- workflow transaction snapshots and rollback support
- agent result envelopes in `.workflow/<slug>/agent-results/`
- sync ledgers
- direct ingestion of structured role results

### 6. Dependency tracking

We added:

- `.workflow/<slug>/dependencies.md`
- lane-level dependency awareness
- explicit init seeding of dependency artifacts

## Recommended Usage Pattern

If you want to use `wrkflw` on a large backend system, the CaseFlow example suggests this pattern:

1. Start from a broad design document if you have one.
2. Let `wrkflw` normalize it first.
3. Split the initiative into epic lanes.
4. Keep only one active OpenSpec lane at a time.
5. Advance one epic at a time unless there is a good reason to parallelize lanes.
6. Use the team model for implementation-heavy stories.
7. Keep implementer write scopes disjoint.
8. Use `team-sync-all` after delegated work.
9. Treat review and Product Owner findings as first-class workflow evidence.
10. Use the diagrams as derived visibility, not the source of truth.

## Minimal Command Sequence

The rough command sequence for a new initiative is:

```text
wrkflw:discuss
wrkflw:approve
wrkflw:approve
wrkflw:approve
wrkflw:approve
wrkflw:approve
```

At that point the active lane will usually be at or near `implementation-planning`.

Then, if using team execution:

```text
wrkflw:staff "team size: 5; parallel slots: 2"
wrkflw:assign "..."
wrkflw:team-run "Dispatch active story"
wrkflw:team-sync-all
wrkflw:review-sync "..."
wrkflw:approve
wrkflw:approve
```

## Bottom Line

This example shows that `wrkflw` is now capable of handling:

- broad-design normalization
- multi-epic delivery
- controlled OpenSpec usage
- backend-heavy implementation work
- team-style delegated execution
- review and challenge loops
- workflow hardening through real project use

It is not just a planning generator anymore. In this example, it acted as the operating system for the project from design intake to completed multi-epic delivery.

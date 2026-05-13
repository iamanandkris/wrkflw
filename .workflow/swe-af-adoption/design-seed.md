# Design Seed

- Source: /Users/anand.krishnan/example/wrkflw/docs/swe-af-adoption-ideas.md

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

14. Verify-Fix Loop

    After implementation, verify the original acceptance criteria against the actual repo state. Generate focused fix tasks when criteria are unmet.

15. CI Feedback Loop

    If a PR or CI check fails, create typed CI findings and optional fix slices instead of treating CI as an external afterthought.

16. Strict Agent Result Schema

    Strengthen `team-sync` by validating delegated agent reports against JSON schema before ingesting them into workflow records and rendered views.

17. Cost And Invocation Accounting

    Track agent runs, retries, elapsed time, and estimated cost per story. This would make checkpoint/resume and avoided rework measurable.

18. Runtime Plan Mutation

    Allow approved commands to add, remove, split, or reorder remaining stories while preserving completed history, dependencies, and OpenSpec ownership.

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

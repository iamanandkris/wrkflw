# Capability Inventory

## Workflow Mode

- Mode: wrkflw-runtime-evolution
- Rationale: This lane tracks adoption of SWE-AF-inspired runtime features into the `wrkflw` skill and command scripts.

## Coverage Guidance

- Use this file to decide which SWE-AF ideas are implemented, partially implemented, or still deferred.
- Keep the adoption bounded to features that improve `wrkflw`'s artifact-backed, human-gated operating model.
- Prefer script-backed artifacts over manual-only notes when a feature affects workflow execution.

## Capability Categories

### Executable Story DAG
- Status: required
- Owning workflow: swe-af-adoption
- Why: `wrkflw` diagrams and story dependencies need to drive execution order, not only documentation.
- Progress: Implemented through `generate_story_dag.py`, `wrkflw:dag-sync`, DAG-aware `team-run`, and DAG-aware implementation planning.

### Lane Dependency Blocking
- Status: recommended
- Owning workflow: swe-af-adoption
- Why: A story can be internally ready while its broader workflow lane is still blocked by another lane.
- Progress: Implemented by threading `dependencies.md` lane blockers into DAG validation and team dispatch.

### Parallel Level Dispatch
- Status: recommended
- Owning workflow: swe-af-adoption
- Why: Ready DAG nodes in the same dependency level can be delegated together when write scopes are disjoint.
- Progress: Implemented through `generate_parallel_dispatch.py`, `wrkflw:team-run-level`, and `parallel-dispatch/` packets.

### Risk-Based QA Paths
- Status: recommended
- Owning workflow: swe-af-adoption
- Why: High-risk stories should automatically get deeper review and QA instructions.
- Progress: Partially implemented through story enrichment metadata and dispatch packet prompts.

### Checkpoint And Resume
- Status: deferred
- Owning workflow: swe-af-adoption
- Why: Long-running workflow commands should resume without recomputing completed work.
- Progress: Not implemented in this increment.

### Git Worktree Isolation
- Status: deferred
- Owning workflow: swe-af-adoption
- Why: Parallel implementers need stronger isolation than advisory path checks.
- Progress: Not implemented in this increment.

### Typed Technical Debt And Propagation
- Status: implemented
- Owning workflow: swe-af-adoption
- Why: Accepted debt should be visible to downstream stories and review gates.
- Progress: Implemented through `records/debt.jsonl`, `debt.md`, `wrkflw:debt-record`, DAG propagation, planning/dispatch warnings, and release-planning blocks for open high/critical debt.

### Issue Advisor And Replanner
- Status: deferred
- Owning workflow: swe-af-adoption
- Why: Failed or stuck stories need structured recovery choices instead of ad hoc retry.
- Progress: Not implemented in this increment.

### Cost And Invocation Accounting
- Status: implemented
- Owning workflow: swe-af-adoption
- Why: Measuring avoided rework and retry cost is central to the SWE-AF value proposition.
- Progress: Implemented through `records/invocations.jsonl`, `accounting.json`, `accounting.md`, `wrkflw:accounting-record`, automatic successful-command records, delegated result usage ingestion, and resumed-command avoided-rework markers.

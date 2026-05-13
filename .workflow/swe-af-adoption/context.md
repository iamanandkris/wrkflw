# Context

- Problem: SWE-AF has useful execution-runtime ideas that can make `wrkflw` more reliable, resumable, parallel, and evidence-rich.
- Goal: Adopt the SWE-AF features that strengthen `wrkflw` while preserving its artifact-first, human-gated workflow model.
- Non-goals: Turn `wrkflw` into a fully autonomous SWE-AF clone; bypass human gates; treat advisory write scopes as a production security sandbox.
- Constraints: Keep `.workflow/<slug>/` artifacts as the source of workflow state; prefer deterministic scripts for state transitions and derived artifacts; keep OpenSpec handoff explicit.

## Design Seed

- Path: /Users/anand.krishnan/example/wrkflw/docs/swe-af-adoption-ideas.md

## Design Excerpt

The first implemented increment focuses on an executable story DAG, DAG validation, DAG-aware planning/dispatch, lane dependency blocking, and parallel dispatch for ready DAG levels with disjoint write scopes.

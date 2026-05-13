# Design Slice

- Raw source: /Users/anand.krishnan/example/wrkflw/docs/swe-af-adoption-ideas.md
- Normalized design: /Users/anand.krishnan/example/wrkflw/.workflow/_normalized/master-design.md
- Epic candidates: /Users/anand.krishnan/example/wrkflw/.workflow/_normalized/epic-candidates.md
- Selected epic slug: authorization-core
- Selected epic title: Authorization Core

## Slice Summary

Executable Story DAG Additional scope includes: Checkpoint And Resume; Git Worktree Isolation

## Workflow Framing

- Problem: `wrkflw` is strongest as a local workflow control plane: it creates durable `.workflow/<slug>/` artifacts, keeps OpenSpec handoff explicit, preserves human gates, and records review/signoff evidence.
- Goal: Use the normalized design slice to derive the first workflow-ready epic.
- Constraints: -

## In-Scope Capabilities

- Primary scope:
  - Executable Story DAG
  - Checkpoint And Resume
  - Git Worktree Isolation
  - Risk-Based Execution Paths
  - simple path: implementer plus reviewer
  - flagged path: implementer plus QA plus reviewer plus synthesis
  - Feedback Synthesizer
  - Issue Advisor
  - retry with modified acceptance criteria
  - retry with a different technical approach
  - split the story
  - accept with explicit debt
  - escalate to broader replanning
  - Replanner
  - Typed Technical Debt
  - dropped acceptance criterion
  - missing functionality
  - known regression risk
  - deferred test
  - unresolved design gap
  - operational or security limitation
  - Debt Propagation
  - Shared Learning Memory
  - Planner Risk Metadata
  - estimated scope
  - touches interfaces
  - needs new tests
  - needs deeper QA
  - risk rationale
  - review focus
  - likely changed paths
  - Merge Gate
  - Integration Test Gate
  - Verify-Fix Loop
  - CI Feedback Loop
  - Cost And Invocation Accounting
  - Runtime Plan Mutation
  - Parallel Level Dispatch
  - Failure Classification
  - retryable
  - blocked by dependency
  - scope too broad
  - environment failure
  - design contradiction
  - test failure
  - policy or security block

## Planning Note

- Use this slice as the primary workflow planning input for this workflow slug.
- Keep the raw design and normalized design as background context rather than treating the whole source document as one workflow.

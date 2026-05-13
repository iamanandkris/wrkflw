# Story DAG

- Workflow slug: demo
- Generated at: 2026-05-11T16:51:11Z
- Source: `.workflow/demo/stories.md`
- Validation status: invalid
- Current stage: implementation-planning
- Active items: Story 1
- Deferred items: -

This is a derived scheduler artifact. `state.md` remains the workflow source of truth.

## Lane Dependencies

- Depends on: -
- Blocked by: -
- Satisfied by: -

## Graph

```mermaid
flowchart LR
  story_1["Story 1: Invalid Dependency"]
  story_2 --> story_1
```

## Execution Levels

| Level | Nodes |
| --- | --- |

## Nodes

| ID | Story | Status | Depends On | Lane Blockers | Risk | QA | Review Focus |
| --- | --- | --- | --- | --- | --- | --- | --- |
| story-1 | Story 1 | blocked | story-2 | - | normal | no | standard acceptance and regression review |

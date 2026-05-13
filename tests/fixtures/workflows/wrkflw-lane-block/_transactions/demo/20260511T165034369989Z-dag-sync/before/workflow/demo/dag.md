# Story DAG

- Workflow slug: demo
- Generated at: 2026-05-11T16:48:25Z
- Source: `.workflow/demo/stories.md`
- Validation status: valid
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
  story_1["Story 1: Implement Current Lane"]
```

## Execution Levels

| Level | Nodes |
| --- | --- |
| 1 | story-1 |

## Nodes

| ID | Story | Status | Depends On | Lane Blockers | Risk | QA | Review Focus |
| --- | --- | --- | --- | --- | --- | --- | --- |
| story-1 | Story 1 | active | - | - | normal | no | standard acceptance and regression review |

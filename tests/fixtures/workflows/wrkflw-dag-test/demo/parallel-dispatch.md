# Parallel Dispatch

- Workflow slug: demo
- Generated at: 2026-05-11T17:06:50Z
- Status: ready
- DAG level: 2
- Output directory: `.workflow/demo/parallel-dispatch`

## Blockers
- none

## Dispatch Nodes

| Story | Node | Write Paths | Packet |
| --- | --- | --- | --- |
| Story 2 | story-2 | src/approval, tests/approval | `.workflow/demo/parallel-dispatch/story-2/implementer.md` |
| Story 3 | story-3 | src/audit, tests/audit | `.workflow/demo/parallel-dispatch/story-3/implementer.md` |

## Execution Rule

Run packets in this dispatch together only while their declared write paths remain disjoint.

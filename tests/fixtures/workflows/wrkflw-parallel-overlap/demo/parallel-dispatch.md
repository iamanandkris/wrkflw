# Parallel Dispatch

- Workflow slug: demo
- Generated at: 2026-05-11T17:08:37Z
- Status: blocked
- DAG level: 1
- Output directory: `.workflow/demo/parallel-dispatch`

## Blockers
- Story 1 path `src/api` overlaps Story 2 path `src/api/users`.

## Dispatch Nodes

| Story | Node | Write Paths | Packet |
| --- | --- | --- | --- |
| Story 1 | story-1 | src/api | `-` |
| Story 2 | story-2 | src/api/users | `-` |

## Execution Rule

Run packets in this dispatch together only while their declared write paths remain disjoint.

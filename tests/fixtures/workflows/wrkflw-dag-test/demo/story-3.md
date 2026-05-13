# Story 3

## Scope
Persist audit events.

## Acceptance Criteria
- Audit events are persisted for material changes.

## Test Expectations
- Add a regression test for audit event persistence.

## Risks
- Audit writes must not leak sensitive data.

## Allowed Write Paths
- src/audit
- tests/audit


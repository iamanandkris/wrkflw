# Team Dispatch

- Workflow slug: demo
- Current stage: implementation-planning
- Active story: Story 2
- Runtime mode target: delegated-agent-team
- Team size: 4
- Parallel implementation slots: 1
- Existing review roles: -
- DAG status: active
- DAG risk: high
- Needs deeper QA: yes

## Dispatch Order

1. Product Owner and Tech Lead review the active artifact independently before reconciliation.
2. Tech Lead finalizes disjoint work slices and handoffs after review conflicts are visible.
3. Implementer lanes execute in parallel only when their ownership is disjoint.
4. Reviewer QA reviews completed slices, runs a bounded red-team pass, and records findings.
5. The orchestrator syncs role reviews, conflicts, assumptions, review evidence, and advances workflow state when gates are satisfied.

## Packet Index
- Product Owner: `dispatch/product-owner.md` (default)
- Tech Lead: `dispatch/tech-lead.md` (default)
- Implementer 1: `dispatch/implementer-1.md` (worker)
- Implementer 2: `dispatch/implementer-2.md` (worker)
- Reviewer QA: `dispatch/reviewer-qa.md` (default)

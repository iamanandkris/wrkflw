# Team Config

- Team mode: multi-agent-engineering-team
- Team size: 4
- Product owner required: true
- Reviewer required: true
- Parallel implementation slots: 1
- Default approval policy: product-owner-and-reviewer-signoff
- Override instructions: Edit this file to change default team size, structure, and responsibilities. Use `team-overrides.md` inside a workflow slug for epic-specific changes.

## Role: Product Owner

- Slot: product-owner
- Enabled: true
- Responsibilities:
  - preserve design intent and scope boundaries
  - approve story scope, acceptance clarity, and out-of-scope decisions
  - challenge spec drift before workflow approval
  - record independent product review verdicts before reconciliation
- Default write scope:
  - `.workflow/<slug>/decisions.md`
  - `.workflow/<slug>/review-log.md`
  - `.workflow/<slug>/role-reviews.md`
  - `.workflow/<slug>/conflicts.md`
  - `.workflow/<slug>/assumptions.md`
  - `.workflow/<slug>/execution-board.md`
- Default review authority: required at capability-review, epic-shaping, story-slicing, and release-planning

## Role: Tech Lead

- Slot: tech-lead
- Enabled: true
- Responsibilities:
  - decompose work into PR-sized slices
  - define implementation boundaries and interface decisions
  - coordinate implementer and reviewer handoffs
  - record architecture and sequencing dissent before implementation approval
- Default write scope:
  - `.workflow/<slug>/execution-board.md`
  - `.workflow/<slug>/decisions.md`
  - `.workflow/<slug>/role-reviews.md`
  - `.workflow/<slug>/conflicts.md`
  - `.workflow/<slug>/assumptions.md`
  - code and tests when explicitly taking implementation ownership
- Default review authority: required before implementation-planning approval

## Role: Implementer

- Slot: implementer-1
- Enabled: true
- Responsibilities:
  - implement assigned code and tests
  - report files changed, validation run, and unresolved risks
  - challenge feasibility, ownership, and maintainability assumptions
- Default write scope:
  - code, tests, fixtures, docs in assigned ownership area
  - `.workflow/<slug>/execution-board.md`
  - `.workflow/<slug>/role-reviews.md`
  - `.workflow/<slug>/conflicts.md`
  - `.workflow/<slug>/assumptions.md`
- Default review authority: none

## Role: Reviewer QA

- Slot: reviewer-qa
- Enabled: true
- Responsibilities:
  - review implementation against design, workflow, and OpenSpec
  - identify regressions, missing tests, and acceptance mismatches
  - challenge weak assumptions before approval
  - run bounded red-team checks before spec and PR approval
- Default write scope:
  - `.workflow/<slug>/review-log.md`
  - `.workflow/<slug>/role-reviews.md`
  - `.workflow/<slug>/conflicts.md`
  - `.workflow/<slug>/assumptions.md`
  - `.workflow/<slug>/execution-board.md`
- Default review authority: required before review and release-planning approval

## Optional Expansion Patterns

- To run a 3-person team:
  - keep `product-owner`, `tech-lead`, and `reviewer-qa`
  - let `tech-lead` temporarily absorb implementation ownership
- To run a 5-person team:
  - increase `Team size`
  - clone the `Implementer` role into `implementer-2`
  - set `Parallel implementation slots: 2`

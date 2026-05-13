# Agent Assignments

- Workflow slug: demo
- Team config source: `.workflow/team-config.md`
- Override source: `.workflow/demo/team-overrides.md`

| Role | Slot | Responsibility Focus | Default Ownership | Allowed Write Paths | Status |
| --- | --- | --- | --- | --- | --- |
| Product Owner | product-owner | design intent, scope, acceptance, sequencing | workflow and review artifacts only | .workflow/<slug>/decisions.md, .workflow/<slug>/review-log.md, .workflow/<slug>/role-reviews.md, .workflow/<slug>/conflicts.md, .workflow/<slug>/assumptions.md, .workflow/<slug>/execution-board.md | planned |
| Tech Lead | tech-lead | architecture, decomposition, interfaces, handoffs | workflow artifacts and shared technical decisions | .workflow/<slug>/execution-board.md, .workflow/<slug>/decisions.md, .workflow/<slug>/role-reviews.md, .workflow/<slug>/conflicts.md, .workflow/<slug>/assumptions.md | planned |
| Implementer 1 | implementer-1 | code and tests for the active slice | assigned code/tests only | declare concrete module/file prefixes before parallel team-run | planned |
| Implementer 2 | implementer-2 | optional parallel code and tests for a second slice | assigned code/tests only | declare concrete module/file prefixes before parallel team-run | optional |
| Reviewer QA | reviewer-qa | review, challenge, regression and test checks | review artifacts only | .workflow/<slug>/review-log.md, .workflow/<slug>/role-reviews.md, .workflow/<slug>/conflicts.md, .workflow/<slug>/assumptions.md, .workflow/<slug>/execution-board.md | planned |

## Assignment Rules

- Do not let every role write to every file.
- Treat workflow/OpenSpec/design artifacts as the shared contract.
- Keep implementer ownership disjoint when parallel implementation slots are greater than 1.
- Express write scope as comma-separated path prefixes in `Allowed Write Paths`.
- Record independent role verdicts in `role-reviews.md` before reconciliation when a role is reviewing scope, spec, implementation plan, or release readiness.

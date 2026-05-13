# Agent Result Schema

- Workflow slug: swe-af-adoption
- Schema version: agent-result-v1
- Applies to: `.workflow/<slug>/agent-results/*.md` and worktree result envelopes synchronized with `wrkflw:team-sync-all`

## Required Fields
- schema
- role
- status
- verdict
- summary
- follow-up
- files-changed
- validation-run
- missing-requirements
- incorrect-assumptions
- risks
- questions
- suggested-changes
- evidence
- conflict-entries
- assumption-updates
- red-team-notes
- findings
- debt-entries
- memory-entries

## Optional Accounting Fields
- model, input-tokens, output-tokens, cost-usd, estimated-cost-usd, cost-source, elapsed-seconds, duration-ms, invocation-id, execution-id, run-id, parent-invocation-id, agent-node-id, reasoner-id, attempt, retry-count, transport-retry-count

## Notes
- Use `- none` for empty list fields.
- Stored result envelopes are rejected before ingest when required fields are missing or invalid.
- Direct one-line `wrkflw:team-sync` status updates remain supported for lightweight human handoffs.

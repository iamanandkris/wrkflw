# Integration Test Allowlist

- Workflow slug: swe-af-adoption
- Source of truth: `integration-test-allowlist.json`

## Format

Add reviewed commands as structured argv entries. `command:` evidence in `wrkflw:integration-gate` remains manual text and is never executed.

```json
{
  "schema_version": 1,
  "workflow_slug": "swe-af-adoption",
  "tests": [
    {
      "id": "api-smoke",
      "description": "Run API smoke tests after merge-apply",
      "argv": ["./scripts/run-api-tests.sh"],
      "cwd": ".",
      "timeout_seconds": 180,
      "env": {"CI": "1"},
      "max_attempts": 1,
      "retry_on": []
    }
  ]
}
```

Run with:

```text
wrkflw:integration-gate "test-id: api-smoke"
```

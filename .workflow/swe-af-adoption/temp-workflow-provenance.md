# Temporary Workflow Provenance

The original implementation work used temporary `.workflow` folders under `/private/tmp` as smoke-test fixtures. Selected fixtures have now been copied into this repository under `tests/fixtures/workflows/wrkflw-*` for easier inspection without mixing fixture state into the live `.workflow/` root.

## Archived Fixture Workflows

- Source: `/private/tmp/wrkflw-dag-test/.workflow`
- Archived at: `/Users/anand.krishnan/example/wrkflw/tests/fixtures/workflows/wrkflw-dag-test`

- Source: `/private/tmp/wrkflw-parallel-overlap/.workflow`
- Archived at: `/Users/anand.krishnan/example/wrkflw/tests/fixtures/workflows/wrkflw-parallel-overlap`

- Source: `/private/tmp/wrkflw-lane-block/.workflow`
- Archived at: `/Users/anand.krishnan/example/wrkflw/tests/fixtures/workflows/wrkflw-lane-block`

- Source: `/private/tmp/wrkflw-dag-invalid/.workflow`
- Archived at: `/Users/anand.krishnan/example/wrkflw/tests/fixtures/workflows/wrkflw-dag-invalid`

## Interpretation

- Most fixtures use the synthetic slug `demo`.
- Several fixtures intentionally represent blocked or invalid states.
- They validate command behavior but do not describe the actual SWE-AF adoption lane.

The canonical tracking location for ongoing work is now:

```text
/Users/anand.krishnan/example/wrkflw/.workflow/swe-af-adoption/
```

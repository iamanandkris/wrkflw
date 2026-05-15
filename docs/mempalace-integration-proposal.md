# MemPalace Integration Proposal For wrkflw

## Summary

Add optional MemPalace-backed long-term memory to wrkflw for analysis-intensive workflows.

wrkflw should continue to treat `.workflow/<slug>/...` artifacts, OpenSpec changes, story files, review logs, verification logs, and local typed memory as the source of truth. MemPalace should act as a recall and cross-checking layer: it can help find prior decisions, repeated failure patterns, repo conventions, and similar workflow history, but it should not silently mutate workflow state or approve a stage.

This proposal assumes MemPalace is available as a local-first AI memory tool with a CLI/MCP surface and local storage, based on its public repository and documentation:

- <https://github.com/MemPalace/mempalace>
- <http://mempalaceofficial.com/>
- <http://mempalaceofficial.com/guide/getting-started.html>

The exact command/API shape should be verified in an implementation spike before binding wrkflw to it.

## Motivation

wrkflw already has useful deterministic memory through `scripts/workflow_memory.py`, which records typed entries in `.workflow/<slug>/records/memory.jsonl` and renders `.workflow/<slug>/memory.md`.

That local memory is good for explicit facts such as:

- repo conventions
- failure patterns
- interface notes
- validated test commands
- implementation patterns

Analysis-heavy workflows need another layer. The weak spots are usually not missing files; they are missed connections across a long discussion or across prior workflows. Recent examples from the SQL Server MCP work include:

- generated OpenSpec changes inheriting the whole epic capability inventory instead of the current story boundary
- implementation plans deferring acceptance criteria for high-risk/interface stories
- stale execution board ownership notes
- feedback synthesis or verify-fix artifacts needing cross-checks against implementation evidence
- recurring wording that synthesis stages misread as new deferral requests

MemPalace can help wrkflw remember and retrieve those prior lessons without forcing every active prompt to carry all historical context.

## Goals

- Provide semantic recall across prior wrkflw runs, stories, reviews, implementation plans, and verification artifacts.
- Cross-check analysis reports against known risks, acceptance criteria, and prior workflow mistakes.
- Improve story enrichment, OpenSpec authoring, implementation planning, feedback synthesis, verify-fix, replan, and issue-advisor stages.
- Keep memory evidence explicit by writing recall/check artifacts into the workflow directory.
- Keep MemPalace optional so wrkflw works normally without it.
- Prevent memory from becoming hidden authority; every recalled item must be traceable and reviewable.

## Non-Goals

- Do not replace `.workflow` artifacts, OpenSpec files, or `records/memory.jsonl`.
- Do not let external memory silently mutate workflow state.
- Do not require MemPalace for standard wrkflw usage or CI.
- Do not index secrets, credentials, raw production data, raw DB query results, or high-risk PII.
- Do not use memory recall as approval. Human approval gates remain explicit.

## Proposed Architecture

Introduce a small memory backend boundary inside wrkflw:

```text
wrkflw command/stage
  -> memory service
     -> redaction and document selection
     -> backend adapter
        -> local JSONL memory backend
        -> optional MemPalace backend
  -> explicit workflow artifact output
```

The backend interface should support:

- `health()`
- `index_documents(documents, namespace)`
- `search(query, filters, limit)`
- `record_memory(item, namespace)`

The existing JSONL memory should remain the canonical local record for typed memories. MemPalace should be used for semantic recall and broad cross-workflow retrieval.

## Candidate Artifacts To Index

Index only workflow and design artifacts by default:

- `.workflow/<slug>/decisions.md`
- `.workflow/<slug>/assumptions.md`
- `.workflow/<slug>/stories.md`
- `.workflow/<slug>/story-*.md`
- `.workflow/<slug>/implementation-plan.md`
- `.workflow/<slug>/role-reviews.md`
- `.workflow/<slug>/review-log.md`
- `.workflow/<slug>/verify-fix.md`
- `.workflow/<slug>/feedback-synthesis.md`
- `.workflow/<slug>/issue-advisor.md`
- `.workflow/<slug>/replan.md`
- `.workflow/<slug>/debt.md`
- `.workflow/<slug>/memory.md`
- relevant `openspec/changes/<change>/proposal.md`
- relevant `openspec/changes/<change>/tasks.md`
- relevant `openspec/changes/<change>/specs/**/spec.md`

Do not index generated dependency folders, raw logs, environment files, or local credentials.

## Output Artifacts

Memory operations should write reviewable artifacts:

- `.workflow/<slug>/memory-recall.md`
- `.workflow/<slug>/memory-recall.json`
- `.workflow/<slug>/memory-check.md`
- `.workflow/<slug>/memory-check.json`
- `.workflow/<slug>/records/memory-index.jsonl`

Each artifact should include:

- query or check target
- backend used
- namespace
- source file references
- retrieved memories
- confidence or score when available
- stale/possibly-conflicting markers
- recommended follow-up checks
- clear note that memory is advisory, not authoritative

## Proposed Commands

### `wrkflw:memory-index`

Indexes selected workflow artifacts after redaction.

Example use:

```text
wrkflw:memory-index
```

Expected behavior:

- reads configured allowlist paths
- applies redaction
- writes an index manifest
- records skipped files and reasons
- does not change workflow stage

### `wrkflw:memory-recall "<question>"`

Retrieves relevant prior workflow context and writes `memory-recall.*`.

Example use:

```text
wrkflw:memory-recall "Have we seen implementation plans deferring acceptance criteria?"
```

Expected behavior:

- searches current workflow namespace first
- optionally searches repo/global namespaces
- returns traceable evidence
- does not change workflow state

### `wrkflw:memory-check <artifact>`

Cross-checks an artifact against acceptance criteria, recent decisions, known failure patterns, and related prior workflows.

Example use:

```text
wrkflw:memory-check implementation-plan
wrkflw:memory-check feedback-synthesis
wrkflw:memory-check verify-fix
```

Expected behavior:

- writes findings to `memory-check.md`
- separates blocking issues from advisory observations
- cites local artifact paths and recalled memory sources
- does not approve or reject the stage

### Extend `wrkflw:memory-record`

The existing typed memory command can remain the deterministic way to store important facts. If MemPalace is enabled, `memory-record` can optionally mirror redacted entries into MemPalace.

## Primary Use Cases

### 1. Story Enrichment Recall

Before finalizing a story, wrkflw can recall similar previous stories and known risks.

Useful checks:

- Did similar stories require end-to-end tests?
- Were any acceptance criteria previously deferred incorrectly?
- Are there known repo conventions for this type of work?
- Did previous role reviews expose recurring ambiguity?

### 2. OpenSpec Drift Detection

Before asking for OpenSpec approval, wrkflw can check whether the spec accidentally absorbed epic-wide scope.

Useful checks:

- Does this change include capabilities outside the approved story?
- Are deferred capabilities clearly marked as future scope?
- Did prior stories hit similar "generic capability inventory" drift?

### 3. Implementation Plan Completeness

Before implementation starts, wrkflw can cross-check the plan against the story acceptance criteria.

Useful checks:

- Does every acceptance criterion have an implementation task?
- Are high-risk/interface acceptance criteria deferred without explicit approval?
- Is the first slice executable on its own?
- Are tests included in the same slice as the runtime skeleton they require?

### 4. Feedback Synthesis Verification

After reviews, wrkflw can compare feedback synthesis against role reviews and implementation evidence.

Useful checks:

- Did synthesis lose a major finding?
- Did synthesis treat boundary evidence as a new deferral request?
- Does it cite concrete artifacts rather than vague claims?
- Are "no major findings" statements supported by review content?

### 5. Verify-Fix Evidence Quality

For fix verification, wrkflw can recall previous verification mistakes and compare claimed evidence with actual test/output artifacts.

Useful checks:

- Are failing tests rerun after the fix?
- Are manual checks documented with enough reproduction detail?
- Are skipped tests explicitly justified?
- Did a previous similar fix require a live fixture or integration test?

### 6. Replan And Issue Advisor

When implementation gets stuck, wrkflw can retrieve prior recovery patterns.

Useful checks:

- Is this blocker similar to a known dependency, sandbox, or workflow-stage problem?
- Did a previous workflow resolve this by changing story boundaries?
- Is there known debt that should be surfaced before replanning?

### 7. Repo Convention Recall

For large repos, wrkflw can recall validated commands and local conventions without relying only on active context.

Useful checks:

- What test commands are known to work?
- Which directories are owned by the current story?
- What files should not be edited for this workflow?
- Which generated files are intentionally ignored?

### 8. Release Planning

Before marking a story done, wrkflw can verify release notes against implemented behavior and known risks.

Useful checks:

- Are operator-facing changes documented?
- Are migrations, config changes, or fixture requirements mentioned?
- Are known limitations listed as follow-up debt?

## Report Cross-Checking Model

`wrkflw:memory-check` should operate as an evidence pass:

1. Load the target artifact.
2. Load current story acceptance criteria and approved scope.
3. Retrieve related memories and prior failure patterns.
4. Compare the artifact against required checks.
5. Write findings with severity, evidence, and recommendation.

Finding format:

```text
Severity: blocking | advisory | note
Target: implementation-plan.md
Evidence: story-6.md requires end-to-end validation, but implementation-plan.md has no E2E task.
Memory: prior Story 4 plan deferred acceptance criteria and required manual correction.
Recommendation: add an implementation slice that covers the missing E2E path before approval.
```

Memory findings should be treated like review findings. They can be wrong or stale, so the user should be able to inspect and dismiss them.

## Safety And Privacy

Memory integration must be conservative by default.

Required controls:

- disabled unless explicitly configured
- local-only backend by default
- path allowlist for indexing
- denylist for `.env`, credentials, raw logs, raw DB dumps, and generated dependency folders
- secret redaction before indexing
- source file hash and timestamp tracking
- namespace separation by repo and workflow slug
- explicit delete/reindex command
- no silent stage advancement based on memory output

Memory should store summaries and workflow evidence, not sensitive payloads.

## Configuration Sketch

Example `.workflow/memory-config.json`:

```json
{
  "memory": {
    "enabled": false,
    "provider": "mempalace",
    "mode": "local",
    "namespace": "repo",
    "indexAllow": [
      ".workflow/**/decisions.md",
      ".workflow/**/assumptions.md",
      ".workflow/**/stories.md",
      ".workflow/**/story-*.md",
      ".workflow/**/implementation-plan.md",
      ".workflow/**/feedback-synthesis.md",
      ".workflow/**/verify-fix.md",
      ".workflow/**/memory.md",
      "openspec/changes/**/proposal.md",
      "openspec/changes/**/tasks.md",
      "openspec/changes/**/specs/**/spec.md"
    ],
    "indexDeny": [
      "**/.env*",
      "**/node_modules/**",
      "**/dist/**",
      "**/coverage/**",
      "**/*.log",
      "**/*secret*",
      "**/*credential*"
    ],
    "recall": {
      "maxResults": 8,
      "minScore": 0.6
    }
  }
}
```

## Phased Implementation Plan

### Phase 1: Backend Boundary

- Add a memory backend interface.
- Keep the existing JSONL behavior unchanged.
- Add config parsing with memory disabled by default.
- Add fake backend tests for deterministic CI.

### Phase 2: Indexing

- Implement artifact selection.
- Reuse and expand existing secret redaction.
- Write `memory-index.jsonl` manifest records.
- Add tests for allowlist, denylist, and redaction.

### Phase 3: Recall

- Add `wrkflw:memory-recall`.
- Generate markdown and JSON recall artifacts.
- Include source references and stale/conflict warnings.
- Test with fake backend retrieval.

### Phase 4: Cross-Checking

- Add `wrkflw:memory-check implementation-plan`.
- Add `wrkflw:memory-check feedback-synthesis`.
- Add `wrkflw:memory-check verify-fix`.
- Use acceptance criteria and prior failure memories as evidence inputs.
- Add regression tests for known failure patterns.

### Phase 5: MemPalace Adapter

- Spike the MemPalace CLI/MCP API shape.
- Implement the adapter behind the backend interface.
- Keep adapter tests optional or mocked unless MemPalace is installed.
- Document local setup.

### Phase 6: Workflow Integration

- Add optional memory recall prompts to story enrichment, OpenSpec authoring, implementation planning, release planning, issue advisor, and replan.
- Keep every memory-assisted stage reviewable through generated artifacts.
- Add user-facing docs and examples.

## Acceptance Criteria For A First wrkflw Story

- With memory disabled, all existing wrkflw commands behave the same.
- `wrkflw:memory-index` writes a manifest and redacts secrets before indexing.
- `wrkflw:memory-recall` writes `memory-recall.md` and `memory-recall.json`.
- `wrkflw:memory-check implementation-plan` can flag a fixture plan that defers an acceptance criterion.
- CI does not require MemPalace; tests use a fake backend.
- MemPalace integration is behind config and documented as optional.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Stale memory creates false warnings | Include source timestamps, hashes, and stale markers. |
| Memory becomes hidden authority | Always write recall/check artifacts; never auto-approve. |
| Sensitive data is indexed | Use allowlist-first selection, denylist, and redaction. |
| Adapter dependency makes wrkflw brittle | Keep MemPalace optional and use a backend interface. |
| Retrieved context is irrelevant | Use namespaces, score thresholds, and small result limits. |
| Users cannot understand why a warning appeared | Include query, source references, and matched memory evidence. |

## Open Questions

- Should the first adapter use MemPalace CLI or its MCP server?
- Should wrkflw maintain separate namespaces for repo, workflow slug, and global user memory?
- Should code files ever be indexed, or only workflow/design artifacts?
- What retention and deletion commands are needed?
- Should memory checks run automatically at approval gates, or only when requested?
- What quality metric should determine whether memory recall is improving workflow outcomes?

## Recommendation

Proceed with a small wrkflw story that adds the backend boundary, disabled-by-default config, indexing, recall artifacts, and fake-backend tests. Defer the real MemPalace adapter until the boundary and safety model are proven.

This gives wrkflw immediate structure for memory-assisted analysis without coupling core workflow behavior to an external tool too early.

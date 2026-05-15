# wrkflw

`wrkflw` is a Codex plugin for staged engineering delivery. It guides work from discovery through epic shaping, story slicing, spec authoring, implementation, review, and release while keeping small PRs, human gates, OpenSpec handoff, and live workflow diagrams in sync.

## What it supports

- `wrkflw:discuss`
- `wrkflw:approve`
- `wrkflw:reject`
- `wrkflw:reconcile`
- `wrkflw:rework`
- `wrkflw:refine`
- `wrkflw:rework-item`
- `wrkflw:proceed-only`
- `wrkflw:defer`
- `wrkflw:override`
- `wrkflw:openspec-sync`
- `wrkflw:next`
- `wrkflw:resume`
- `wrkflw:actions`
- `wrkflw:capability-synth`
- `wrkflw:design-synth`
- `wrkflw:story-synth`
- `wrkflw:story-enrichment-synth`
- `wrkflw:openspec-synth`
- `wrkflw:implementation-plan-synth`
- `wrkflw:dag-sync`
- `wrkflw:execution-path`
- `wrkflw:feedback-synth`
- `wrkflw:issue-advisor`
- `wrkflw:replan`
- `wrkflw:verify-fix`
- `wrkflw:ci-feedback`
- `wrkflw:accounting-record`
- `wrkflw:memory-record`
- `wrkflw:debt-record`
- `wrkflw:merge-gate`
- `wrkflw:merge-apply`
- `wrkflw:integration-gate`
- `wrkflw:worktree-clean`
- `wrkflw:staff`
- `wrkflw:assign`
- `wrkflw:challenge`
- `wrkflw:review-sync`
- `wrkflw:team-sync`
- `wrkflw:team-sync-all`
- `wrkflw:team-run`
- `wrkflw:team-run-level`

It also supports:
- design seed detection from `design.md` or `docs/design.md`
- normalization of broad design documents into workflow-ready design artifacts
- automatic OpenSpec handoff during `spec-authoring`
- derived story DAG generation from `stories.md` dependencies
- risk-based execution path artifacts for simple vs flagged story routing
- feedback synthesis for flagged-path QA/reviewer convergence
- promoted failure classification across CI, integration, merge, feedback synthesis, and issue-advisor recovery
- human-gated runtime plan mutation for remaining-story skip/defer, removal, dependency rewrite, and reorder
- verify-fix acceptance checks that turn unmet criteria into focused fix tasks
- typed CI feedback records that turn failed checks into focused fix tasks
- invocation accounting for workflow commands, delegated-agent usage, retries, elapsed time, tokens, known cost, and unknown-cost records
- phase checkpoints and explicit resume for interrupted workflow commands
- stage-aware action menus that show the recommended command, alternatives, and a final manual suggestion option
- AI-assisted synthesis packets that combine planning profile, design artifacts, repo evidence, and deterministic validation before capability, story, OpenSpec, design, and implementation-planning decisions
- git worktree isolation for active-story implementer lanes and ready parallel DAG-level dispatch packets
- read-only merge-gate verification for isolated worktree diffs before review approval
- explicit human-controlled merge-apply for ready parallel worktree branches
- controlled integration-gate classification, evidence checks, and optional allowlisted command execution after merge-apply
- workflow state and PlantUML diagram generation under `.workflow/<slug>/`
- release-plan generation and OpenSpec archive on story closeout

## Install

### Quick install

Clone the repo into your local plugins directory:

```bash
git clone git@github.com:iamanandkris/wrkflw.git ~/plugins/wrkflw
```

If you use a custom plugin path, clone it there instead.

Or use the helper script from an existing clone:

```bash
./scripts/install_local.sh
```

When you are working from a local checkout and want to install the plugin and skill files from that checkout, use:

```bash
./scripts/install_local.sh --local
```

That installs or updates the plugin into:

```text
~/plugins/wrkflw
```

The helper also refreshes the active Codex skill copy at:

```text
~/.codex/skills/wrkflw-discuss/SKILL.md
```

Local workflow state under `.workflow/` is not installed as plugin content; `--local` removes any stale `.workflow/` directory from the installed plugin target.

### Make Codex discover it

Make sure your local Codex plugin marketplace/config points at the plugin folder.

If you already use a marketplace file such as:

```text
~/.agents/plugins/marketplace.json
```

add an entry that points at the cloned plugin directory.

Minimal example:

```json
{
  "plugins": [
    {
      "name": "wrkflw",
      "path": "/Users/<you>/plugins/wrkflw"
    }
  ]
}
```

If your Codex setup discovers plugins directly from a local plugin root, just placing the repo here is enough:

```text
~/plugins/wrkflw
```

### VS Code / Codex note

This repo is a Codex plugin plus skill bundle. It does not install as a generic VS Code marketplace extension. The usual path is:

1. clone the repo locally
2. point your Codex plugin configuration at that local path
3. restart or reload Codex if plugin discovery is cached

## Requirements

- Python 3
- PlantUML source rendering support if you want to render the generated `.puml` files
- OpenSpec installed if you want real OpenSpec changes instead of workflow-only artifacts

## Design Notes

- `docs/swe-af-adoption-ideas.md`
  - candidate SWE-AF-inspired features that could strengthen `wrkflw` while preserving its artifact-first, human-gated model
- `docs/mempalace-integration-proposal.md`
  - proposal for optional MemPalace-backed recall and report cross-checking for analysis-heavy workflows
- `docs/wrkflw-lifecycle-timeline.md`
  - visual timeline of human gates, lifecycle stages, and key workflow artifacts from start to story closeout
- `docs/wrkflw-lifecycle-deep-map.html`
  - expanded vertical lifecycle map with SWE-AF-inspired runtime, validation, recovery, and command details

## Usage

Start a workflow:

```text
wrkflw:discuss "Implement feature X"
```

Example:

- `examples/caseflow-example.md`
  - end-to-end multi-epic backend example showing design normalization, OpenSpec lane control, delegated team execution, and the workflow hardening that came out of a real project

Start a workflow from a design seed:

```text
wrkflw:discuss "Start this workflow from the design in docs/design.md"
```

If the repo contains `design.md` or `docs/design.md`, `wrkflw` will use that as a seed automatically.

If the design document is broad or not already workflow-shaped, `wrkflw` first generates normalized planning artifacts and an epic-specific design slice before it uses the design for workflow shaping.
That normalization pass should preserve section semantics where possible, so overview, actor, capability, architecture, and operational sections can map into cleaner epic candidates instead of one flattened backlog.

The workflow creates artifacts under:

```text
.workflow/<slug>/
```

with a lightweight parent registry at:

```text
.workflow/initiative-index.md
```

including:
- `context.md`
- `capabilities.md`
- `state.md`
- `history.md`
- `links.md`
- `gates.md`
- `diagram-config.md`
- `workflow-contract.md`
- `dependencies.md`
- `dag.json`
- `dag.md`
- `dag-validation.md`
- `records/memory.jsonl`
- `memory.md`
- `records/debt.jsonl`
- `debt.md`
- `team-overrides.md`
- `agent-assignments.md`
- `execution-board.md`
- `review-log.md`
- `role-reviews.md`
- `conflicts.md`
- `assumptions.md`
- `team-minutes.md`
- `runtime-contract.md`
- `agent-sync-ledger.md`
- `agent-results/`
- `team-dispatch.md`
- `parallel-dispatch.json`
- `parallel-dispatch.md`
- `parallel-dispatch/`
- `design-slice.md` when the workflow is seeded from a broader design source
- `design-seed.md` when applicable
- `diagram-flow.puml`
- `diagram-work.puml`

State contract:
- `state.md` is the source of truth for current workflow status
- `history.md` is the source of truth for completed progression trail
- `diagram-flow.puml` and `diagram-work.puml` are derived artifacts and should be regenerated after each workflow state change
- `Current stage` must use only:
  - `discuss`
  - `capability-review`
  - `epic-shaping`
  - `story-slicing`
  - `story-enrichment`
  - `spec-authoring`
  - `implementation-planning`
  - `implementation`
  - `review`
  - `release-planning`
  - `done`
- `Human gate status` must use only:
  - `pending`
  - `approved`
  - `blocked`
  - `rejected`
- avoid freeform labels like `epic-shaped`, `story-sliced`, or `awaiting approval`

When a broader design is present, `wrkflw` also creates shared normalization artifacts under:

```text
.workflow/_normalized/
```

including:
- `master-design.md`
- `epic-candidates.md`

The initiative index tracks each workflow slug as a separate epic lane with its current stage, design source, recorded OpenSpec change, and supporting docs.

### Story DAG

When `stories.md` exists, `wrkflw` can maintain a derived story execution graph:

```text
.workflow/<slug>/dag.json
.workflow/<slug>/dag.md
.workflow/<slug>/dag-validation.md
```

The DAG is generated from `Depends on:` lines in `stories.md`, lane-level blockers in `dependencies.md`, the current `state.md`, `history.md` completion evidence, any enriched `story-N.md` acceptance/test/risk details, and open or accepted entries in `records/debt.jsonl`. It records topological execution levels, ready/blocked/deferred/active/completed status hints, downstream dependents, high-risk stories, lane blockers, technical debt context, planner metadata, and QA focus. Implementation plans and team dispatch packets include the active story's DAG level, dependencies, dependents, risk/QA flags, execution path, and inherited debt warnings, making the reviewed story plan easier to use for parallel implementation planning without replacing the canonical workflow state.

`wrkflw:execution-path` writes `.workflow/<slug>/execution-path.json` and `.workflow/<slug>/execution-path.md` for the active or first ready story. The path is `simple` for implementer plus reviewer work, or `flagged` when planner metadata detects sensitive domains, interface changes, broad scope, broad write surface, or blocking technical debt. Flagged packets call out the extra Tech Lead / Reviewer QA review and synthesis expectation, but `wrkflw` still records this as workflow policy rather than automatically running a production agent runtime.

`wrkflw:feedback-synth` writes `.workflow/<slug>/feedback-synthesis.json` and `.workflow/<slug>/feedback-synthesis.md`. It reads role reviews, review findings, conflicts, debt, execution path, merge/integration gate evidence, CI feedback, and promoted failure classifications, then records one recommendation: `approve`, `fix`, `split`, `defer`, `block`, or `replan`. Flagged execution paths require a fresh approving synthesis before review can advance to release planning.

`wrkflw:issue-advisor` writes `.workflow/<slug>/issue-advisor.json`, `.workflow/<slug>/issue-advisor.md`, and an append-only `.workflow/<slug>/records/adaptations.jsonl` record. It consumes the active story, DAG, feedback synthesis, review/conflict evidence, debt, memory, gate artifacts, and promoted failure classifications, then recommends a bounded SWE-AF-style recovery action: `retry_approach`, `retry_modified`, `accept_with_debt`, `split`, or `escalate_to_replan`. It does not silently edit story scope or debt; it blocks the current gate and points to the next explicit recovery command.

`wrkflw:replan` writes `.workflow/<slug>/replan.json`, `.workflow/<slug>/replan.md`, and `.workflow/<slug>/records/replans.jsonl`. By default it only proposes a DAG/story mutation from issue-advisor, feedback-synthesis evidence, or explicit operator directives. Applying the mutation requires `confirm: replan`, validates proposal input hashes, snapshots the previous story/DAG artifacts under `.workflow/<slug>/replans/<replan-id>/before/`, then applies supported mutations such as story splitting, modified acceptance criteria, `skip`/`defer`, `remove`, `depends`, and `order`. Completed stories recorded in `history.md` are treated as immutable.

`wrkflw:verify-fix` writes `.workflow/<slug>/verify-fix.json`, `.workflow/<slug>/verify-fix.md`, and append-only `.workflow/<slug>/records/verify-fix.jsonl`. It checks the active story's acceptance criteria against explicit review, role, integration, and command-provided evidence, then generates focused fix tasks for failed or unverified criteria. Review approval blocks until verify-fix is fresh and ready.

`wrkflw:ci-feedback` writes `.workflow/<slug>/ci-feedback.json`, `.workflow/<slug>/ci-feedback.md`, per-run snapshots under `.workflow/<slug>/ci-runs/`, and append-only `.workflow/<slug>/records/ci-feedback.jsonl`. It records typed CI check status for the current `HEAD`, creates focused fix tasks and failure classifications for failed/pending/timeout/error checks, and blocks review until the CI feedback is fresh and ready. It records external CI evidence only; it does not run arbitrary CI commands.

`wrkflw:accounting-record` appends manual or delegated-run usage evidence to `.workflow/<slug>/records/invocations.jsonl` and refreshes `.workflow/<slug>/accounting.json` plus `.workflow/<slug>/accounting.md`. Successful workflow commands are also recorded automatically with zero workflow-control cost. Delegated agent reports may include optional usage fields such as model, tokens, elapsed seconds, run id, invocation id, and cost. Missing cost is rendered as unknown, not `$0`.

`wrkflw:integration-gate "test-id: api-smoke"` reads `.workflow/<slug>/integration-test-allowlist.json`, validates the selected entry, and runs only its structured `argv` with `shell=False`. The gate writes per-run JSON under `.workflow/<slug>/integration-runs/` and an append-only summary record to `.workflow/<slug>/records/integration-gate-runs.jsonl`. Manual `command:` evidence remains supported, but it is recorded as text and is never executed.

`dag-validation.md` records whether the graph is valid, blocked by lane dependencies, or invalid because of missing/cyclic story dependencies.

For parallel level dispatch, each ready story must declare disjoint write scope in its enriched story artifact:

```text
## Allowed Write Paths
- src/billing
- tests/billing
```

Regenerate it explicitly with:

```text
wrkflw:dag-sync
```

It is also refreshed automatically after workflow commands once story slices exist. Regeneration preserves the prior timestamp and avoids rewriting DAG files when the graph semantics have not changed.

### Technical debt

`wrkflw` tracks explicit technical debt in:

```text
.workflow/<slug>/records/debt.jsonl
.workflow/<slug>/debt.md
```

Use `wrkflw:debt-record` to record or update debt that should remain visible across later planning and review steps. Open or accepted debt propagates through `dag.json`, `implementation-plan.md`, `team-dispatch.md`, and `parallel-dispatch/` packets. Open high/critical debt blocks `release-planning` and `done` until it is resolved or explicitly accepted, including when the debt is recorded after the lane has already entered release planning.

Supported debt types are intentionally practical:

- dropped acceptance criterion
- missing functionality
- known regression risk
- deferred test
- unresolved design gap
- operational limitation
- security limitation

Example:

```text
wrkflw:debt-record "story: Story 1; type: deferred test; severity: high; summary: integration coverage is deferred; impact: Story 3 depends on this behavior; owner: Reviewer QA"
```

To update an existing debt item:

```text
wrkflw:debt-record "id: debt-20260512101010-abc123ef; status: accepted; resolution: accepted by Product Owner for this release"
```

### Shared learning memory

`wrkflw` tracks reusable repo learning in:

```text
.workflow/<slug>/records/memory.jsonl
.workflow/<slug>/memory.md
```

Use `wrkflw:memory-record` for conventions, failure patterns, interface notes, validated test commands, and implementation patterns that should be reused by later story enrichment, implementation planning, and dispatch packets. Memory is evidence-only and non-blocking; review findings, conflicts, and debt remain the gate-blocking artifacts.

Example:

```text
wrkflw:memory-record "category: validated-test-command; story: Story 1; command: npm test; result: passed; summary: npm test is the local smoke command; evidence: local run"
```

### Team execution

`wrkflw` now seeds a default team model at:

```text
.workflow/team-config.md
```

The default team is:
- `Product Owner`
- `Tech Lead`
- `Implementer`
- `Reviewer QA`

Use this file to specify or override:
- team size
- team structure
- role responsibilities
- parallel implementation slots
- approval expectations

For epic-specific changes, use:

```text
.workflow/<slug>/team-overrides.md
```

Each workflow lane also gets seeded coordination artifacts:
- `agent-assignments.md`
- `execution-board.md`
- `review-log.md`
- `role-reviews.md`
- `conflicts.md`
- `assumptions.md`
- `team-minutes.md`
- `runtime-contract.md`
- `dependencies.md`
- `feedback-synthesis.json` and `feedback-synthesis.md`
- `issue-advisor.json`, `issue-advisor.md`, and `records/adaptations.jsonl`
- `replan.json`, `replan.md`, `records/replans.jsonl`, and `replans/`
- `verify-fix.json`, `verify-fix.md`, and `records/verify-fix.jsonl`
- `ci-feedback.json`, `ci-feedback.md`, `ci-runs/`, and `records/ci-feedback.jsonl`
- `integration-test-allowlist.json`, `integration-test-allowlist.md`, `integration-test-gate.json`, `integration-test-gate.md`, `integration-runs/`, and `records/integration-gate-runs.jsonl`
- `memory.md`, `records/memory.jsonl`, `debt.md`, and `records/debt.jsonl`
- `accounting.json`, `accounting.md`, and `records/invocations.jsonl`
- `agent-sync-ledger.md`
- `agent-results/`
- `schemas/agent-result.schema.json`, `agent-result-schema.md`, and `records/agent-result-validation.jsonl`

Generated-on-demand lane artifacts include:
- `stories.md` and `story-*.md` after story slicing/enrichment
- `dag.json`, `dag.md`, and `dag-validation.md` after DAG sync
- `execution-path.json` and `execution-path.md` after execution-path routing
- `team-dispatch.md` and `dispatch/*.md` after delegated team execution is prepared
- `parallel-dispatch.json`, `parallel-dispatch.md`, and `parallel-dispatch/` after parallel DAG-level dispatch is prepared
- `worktrees/manifest.json` and `worktrees.md` after isolated worktree preparation
- `merge-gate.json`, `merge-gate.md`, `merge-apply.json`, and `merge-apply.md` after merge verification/apply commands run

These are intended to model a small engineering team where design, coding, and challenge/review are separated instead of letting every agent write to everything.

Current behavioral integration:
- `execution-board.md` is automatically synchronized with the active workflow stage, handoff, and owner
- `implementation-plan.md` is team-aware and uses team size / parallel implementation slots when suggesting ownership
- `implementation-plan.md` uses `dag.json` to show the active story's execution level, dependency status, downstream dependents, risk, deeper-QA flag, and currently ready DAG nodes
- `review-log.md` is used for late-stage challenge/signoff checks:
  - `Reviewer QA` evidence is required before `release-planning` when reviewer signoff is enabled
  - `Product Owner` evidence is required before `done` when product-owner signoff is enabled
- `role-reviews.md` records independent role verdicts before reconciliation, including missing requirements, incorrect assumptions, risks, questions, suggested changes, evidence, and red-team notes
- `conflicts.md` records unresolved disagreements; open blocking conflicts prevent gate advancement until the conflict row has a concrete resolution
- `assumptions.md` records assumptions and contested assumptions that need validation before they become hidden requirements
- `team-minutes.md` records staffing decisions, role assignments, team-run dispatch preparation, challenge discussions, and review-sync outcomes
- `runtime-contract.md` records the current file-driven team runtime contract and prepares the workflow for future delegated-agent execution without claiming automatic spawning today
- `dependencies.md` records first-class lane dependencies such as `Depends on`, `Blocked by`, and `Unlocks`
- `agent-results/` stores structured delegated-agent result envelopes
- `agent-sync-ledger.md` records which result envelopes have already been synchronized into workflow state
- `schemas/agent-result.schema.json`, `agent-result-schema.md`, and `records/agent-result-validation.jsonl` define and record strict validation for stored delegated-agent result envelopes
- `wrkflw:team-run` upgrades the current lane into delegated-runtime mode, generates role dispatch packets, and gives Codex the packets needed to spawn real role agents

Team control commands:
- `wrkflw:staff`
  - update team size, parallel slots, and role override notes in `team-config.md` or `team-overrides.md`
- `wrkflw:assign`
  - update `agent-assignments.md` with role ownership for the active workflow lane
  - include explicit write scopes such as `Implementer 1 ownership: src/session/state, test/session/state`
- `wrkflw:challenge`
  - append structured review/challenge evidence to `review-log.md` and surface it in workflow state
- `wrkflw:review-sync`
  - resynchronize workflow state and execution-board review notes from review/collaboration evidence
  - keep open blocking conflicts visible instead of clearing blocked workflow state
- `wrkflw:resume`
  - restore the latest resumable checkpoint for this workflow lane and continue the original command from the next phase
  - resume `team-sync-all` from the latest completed result-envelope checkpoint instead of re-ingesting the whole batch
  - refuse to resume after rollback if `.workflow` or `openspec` changed since the failed command baseline
- `wrkflw:actions`
  - regenerate `.workflow/<slug>/action-menu.json` and `.workflow/<slug>/action-menu.md`
  - show the recommended next command, other valid stage-specific commands, material-command warnings, and `None / manual suggestion`
  - make command choices explicit before non-obvious gates or branch points without advancing workflow state
- `wrkflw:capability-synth`
  - regenerate `.workflow/<slug>/capability-synth.md` and `.workflow/<slug>/capability-synth.json`
  - package the planning profile, design artifacts, current capabilities, and repo evidence into a Codex-ready synthesis packet
  - regenerate `.workflow/<slug>/capability-synth-validation.md` / `.json` so AI-authored capabilities remain reviewable before approval
- `wrkflw:design-synth`, `wrkflw:story-synth`, `wrkflw:story-enrichment-synth`, `wrkflw:openspec-synth`, `wrkflw:implementation-plan-synth`
  - regenerate stage-specific synthesis packets and validation artifacts through the shared synthesis framework
  - package the planning profile, current workflow artifacts, design/codebase context, and repo evidence into Codex-ready decision packets
  - keep deterministic validation around AI-authored design analysis, story slices, story enrichment, OpenSpec requirements, and implementation plans
- `wrkflw:dag-sync`
  - regenerate `.workflow/<slug>/dag.json` and `.workflow/<slug>/dag.md` from story dependencies and current workflow state
  - regenerate `.workflow/<slug>/dag-validation.md`
  - detect unknown dependencies, dependency cycles, and incomplete lane dependencies before implementation planning relies on the graph
- `wrkflw:execution-path`
  - regenerate `.workflow/<slug>/execution-path.json` and `.workflow/<slug>/execution-path.md`
  - classify the active or first ready story as `simple` or `flagged`
  - record estimated scope, interface touch, test need, risk rationale, required roles, review flow, and retry policy
- `wrkflw:feedback-synth`
  - regenerate `.workflow/<slug>/feedback-synthesis.json` and `.workflow/<slug>/feedback-synthesis.md`
  - synthesize role reviews, review-log findings, conflicts, debt, execution path, merge/integration gate state, CI feedback, and promoted failure classifications
  - recommend `approve`, `fix`, `split`, `defer`, `block`, or `replan`
  - block flagged-path review advancement when synthesis is missing, stale, or not approving
- `wrkflw:issue-advisor`
  - regenerate `.workflow/<slug>/issue-advisor.json` and `.workflow/<slug>/issue-advisor.md`
  - append `.workflow/<slug>/records/adaptations.jsonl`
  - prefer promoted failure classifications before falling back to textual recovery heuristics
  - recommend `retry_approach`, `retry_modified`, `accept_with_debt`, `split`, or `escalate_to_replan`
- `wrkflw:replan`
  - regenerate `.workflow/<slug>/replan.json` and `.workflow/<slug>/replan.md`
  - append `.workflow/<slug>/records/replans.jsonl`
  - apply only with `confirm: replan` after input-hash validation
  - support approved `skip`/`defer`, `remove`, `depends`, and `order` directives for remaining stories while preserving completed history
- `wrkflw:verify-fix`
  - regenerate `.workflow/<slug>/verify-fix.json` and `.workflow/<slug>/verify-fix.md`
  - append `.workflow/<slug>/records/verify-fix.jsonl`
  - compare active-story acceptance criteria with explicit evidence and generate focused fix tasks for failed or unverified criteria
- `wrkflw:ci-feedback`
  - regenerate `.workflow/<slug>/ci-feedback.json` and `.workflow/<slug>/ci-feedback.md`
  - write per-run snapshots under `.workflow/<slug>/ci-runs/`
  - append `.workflow/<slug>/records/ci-feedback.jsonl`
  - bind external CI status to the current `HEAD` and generate focused fix tasks plus failure classifications for failed, pending, timed-out, cancelled, missing, or errored checks
- `wrkflw:accounting-record`
  - append `.workflow/<slug>/records/invocations.jsonl`
  - regenerate `.workflow/<slug>/accounting.json` and `.workflow/<slug>/accounting.md`
  - track story, role, command, retry marker, avoided-rework marker, elapsed time, model, tokens, known cost, unknown cost, and correlation ids
- `wrkflw:memory-record`
  - append or update typed shared learning in `.workflow/<slug>/records/memory.jsonl`
  - regenerate `.workflow/<slug>/memory.md`
  - make repo conventions, failure patterns, interface notes, validated test commands, and implementation patterns available to later planning and dispatch artifacts
- `wrkflw:debt-record`
  - append or update typed technical debt in `.workflow/<slug>/records/debt.jsonl`
  - regenerate `.workflow/<slug>/debt.md`
  - propagate open or accepted debt into DAG, implementation planning, and dispatch context
  - block release planning when unresolved high/critical debt remains open
- `wrkflw:merge-gate`
  - inspect `.workflow/<slug>/worktrees/manifest.json` after active-story or parallel worktree execution
  - write `.workflow/<slug>/merge-gate.json` and `.workflow/<slug>/merge-gate.md`
  - block review approval when worktrees are dirty, missing, stale, conflict-prone, or contain committed changes outside story `Allowed Write Paths`
  - perform read-only verification only; it does not merge branches
- `wrkflw:merge-apply`
  - require explicit human confirmation with `confirm: merge-apply`
  - inspect `.workflow/<slug>/merge-gate.json` after merge-gate passes
  - write `.workflow/<slug>/merge-apply.json` and `.workflow/<slug>/merge-apply.md`
  - apply only ready wrkflw-owned lane branches, sequentially, with `--no-ff` merge commits on a temporary integration branch
  - fast-forward the target checkout only after all candidate merges pass, and record the pre-apply checkpoint ref
  - block review approval when committed lane changes have passed merge-gate but have not been explicitly applied
- `wrkflw:integration-gate`
  - inspect `.workflow/<slug>/merge-gate.json` after merge-gate passes and `.workflow/<slug>/merge-apply.json` when committed lane changes were applied
  - write `.workflow/<slug>/integration-test-gate.json` and `.workflow/<slug>/integration-test-gate.md`
  - classify whether integration validation is required from changed paths, parallel-lane changes, DAG risk, deeper-QA flags, and story validation text
  - record failure class/category/retryability/recommended gate for blocked validation
  - optionally run `test-id: <id>` from `.workflow/<slug>/integration-test-allowlist.json` with argv-only execution, bounded timeout, minimal environment, stdout/stderr tails, and append-only records under `.workflow/<slug>/records/integration-gate-runs.jsonl`
  - block review approval when required validation evidence is missing, stale, failed, flaky, timed out, or waived without a reason
  - never execute free-form `command:` evidence or shell snippets from agent reports
- `wrkflw:worktree-clean`
  - remove clean wrkflw-owned git worktrees recorded in `.workflow/<slug>/worktrees/manifest.json`
  - refuse cleanup when a worktree is dirty, missing ownership metadata, or registered to an unexpected branch
- `wrkflw:team-sync`
  - record delegated role progress such as implementer completion, reviewer start, or handoff notes
  - synchronize `execution-board.md`, `agent-assignments.md`, `team-minutes.md`, `role-reviews.md`, `conflicts.md`, `assumptions.md`, `review-log.md`, and implementation-plan context from that role update
  - validate reported changed files against the role's allowed write scope
- `wrkflw:team-sync-all`
  - ingest every unsynchronized structured result envelope from `.workflow/<slug>/agent-results/`
  - validate stored result envelopes against `schemas/agent-result.schema.json` before ingest
  - update `agent-sync-ledger.md` so replaying the same envelopes becomes a no-op
  - checkpoint after each synchronized envelope so `wrkflw:resume` can continue from the last completed envelope after an interruption
- all team commands also append an entry to `team-minutes.md` so the collaboration trail stays readable
- `wrkflw:team-run`
  - generate `.workflow/<slug>/team-dispatch.md`
  - generate `.workflow/<slug>/dispatch/*.md` role packets
  - switch `runtime-contract.md` into `delegated-agent-team` mode for the active lane
  - require a valid story DAG, select the first ready DAG story when no active story is already recorded, and block if the active story is missing, deferred, completed, blocked, or has unsatisfied DAG dependencies
  - prepare git worktrees for merge-eligible implementer lanes and record them in `.workflow/<slug>/worktrees/manifest.json`
  - include worktree path and branch in implementer dispatch packets
- `wrkflw:team-run-level`
  - generate `.workflow/<slug>/parallel-dispatch.json`
  - generate `.workflow/<slug>/parallel-dispatch.md`
  - generate `.workflow/<slug>/parallel-dispatch/<story-id>/implementer.md` packets for the earliest ready DAG level
  - prepare per-story git worktrees for ready parallel dispatch and record them in `.workflow/<slug>/worktrees/manifest.json`
  - include worktree path and branch in each parallel dispatch packet
  - require at least two ready DAG nodes and disjoint `Allowed Write Paths`
  - block instead of dispatching when write scopes are missing or overlapping

Suggested formats:

```text
wrkflw:staff "team size: 5; parallel slots: 2; Implementer 2: own UI slice"
wrkflw:assign "Implementer 1: schema and fixtures; Reviewer QA: regression and acceptance review"
wrkflw:challenge "role: Reviewer QA; severity: high; finding: acceptance coverage is incomplete"
wrkflw:review-sync "Reviewer QA and Product Owner evidence recorded"
wrkflw:resume "Continue the last interrupted workflow command"
wrkflw:actions "Show recommended and alternative commands for the current stage"
wrkflw:capability-synth "Synthesize richer capabilities from the planning profile, design, and repo evidence"
wrkflw:design-synth "Synthesize semantic design/codebase analysis and epic candidates"
wrkflw:story-synth "Synthesize PR-sized stories from approved capabilities"
wrkflw:story-enrichment-synth "Synthesize acceptance criteria, tests, risks, and write paths for the active story"
wrkflw:openspec-synth "Synthesize domain-specific OpenSpec requirements for the active story"
wrkflw:implementation-plan-synth "Synthesize the first PR slice, ownership, validation, and risk plan"
wrkflw:dag-sync "Refresh story dependency graph"
wrkflw:execution-path "Refresh simple vs flagged execution routing"
wrkflw:feedback-synth "Synthesize role feedback before review approval"
wrkflw:issue-advisor "Diagnose the stuck active story and recommend a recovery path"
wrkflw:replan "Propose a story/DAG replan from advisor evidence"
wrkflw:replan "confirm: replan"
wrkflw:verify-fix "pass: 1, 2; evidence: unit and integration tests passed"
wrkflw:ci-feedback "status: failed; check: unit tests; failure: pytest failed on profile endpoint; provider: github"
wrkflw:accounting-record "story: Story 1; role: Implementer 1; model: gpt-test; input-tokens: 1200; output-tokens: 300; cost: 0.25; elapsed-seconds: 42; summary: delegated run completed"
wrkflw:debt-record "story: Story 1; type: deferred test; severity: high; summary: integration coverage deferred; owner: Reviewer QA"
wrkflw:merge-gate "Verify isolated worktree diffs before review approval"
wrkflw:merge-apply "confirm: merge-apply"
wrkflw:integration-gate "status: passed; command: smoke integration suite; evidence: CI run 123"
wrkflw:integration-gate "test-id: api-smoke"
wrkflw:worktree-clean "Remove clean wrkflw-owned worktrees after review"
wrkflw:team-sync "role: Implementer 1; status: done; note: gameplay loop landed; follow-up: Reviewer QA review the lane"
wrkflw:team-sync-all "batch synced delegated result envelopes"
wrkflw:team-run "Dispatch the active story with parallel implementer lanes"
wrkflw:team-run-level "Dispatch every safe ready story in the earliest DAG level"
```

### Delegated team run

`wrkflw:team-run` is the bridge from workflow artifacts to real parallel Codex agents.

Expected sequence:
- the workflow must already have an active story
- the current stage should be `implementation-planning`, `implementation`, or `review`
- `wrkflw` generates dispatch packets under:
  - `.workflow/<slug>/team-dispatch.md`
  - `.workflow/<slug>/dispatch/*.md`
- as delegated role work returns, write each structured final report into `.workflow/<slug>/agent-results/` and then synchronize with `wrkflw:team-sync-all` or `wrkflw:team-sync`
- after isolated implementer worktree dispatch returns, run `wrkflw:merge-gate`, `wrkflw:merge-apply "confirm: merge-apply"` when committed lane changes exist, `wrkflw:integration-gate`, `wrkflw:ci-feedback` when PR/CI evidence exists, and `wrkflw:verify-fix` before `review-sync` or review approval
- each delegated role should return a structured final report with:
  - `Schema`
  - `Role`
  - `Status`
  - `Verdict`
  - `Summary`
  - `Files changed`
  - `Validation run`
  - `Missing requirements`
  - `Incorrect assumptions`
  - `Risks`
  - `Questions`
  - `Suggested changes`
  - `Evidence`
  - `Conflict entries`
  - `Assumption updates`
  - `Red-team notes`
  - `Findings`
  - `Debt entries`
  - `Memory entries`
  - `Follow-up`
- apply `wrkflw:team-sync` updates sequentially rather than in parallel, because they update shared workflow coordination files
- prefer storing each structured final report in `.workflow/<slug>/agent-results/` and using `wrkflw:team-sync-all`; pasting directly into `wrkflw:team-sync` is still supported
- stored result envelopes and direct reports that declare `Schema: agent-result-v1` are rejected before ingest if required fields or enum values are invalid
- `wrkflw:team-sync` can infer role/status from pasted agent output when the output is clear, but explicit `role:` and `status:` remain safer
- every report with a verdict or review fields is written into `role-reviews.md`
- report conflict entries are written into `conflicts.md`; blocking conflicts keep gates blocked until resolved
- report assumption updates and incorrect assumptions are written into `assumptions.md`
- reviewer and product-owner reports with findings are written into `review-log.md` automatically; clean reviewer/product-owner reports create explicit signoff evidence
- Codex can then spawn the role agents from those packets:
  - `Product Owner`
  - `Tech Lead`
  - `Implementer 1`
  - `Implementer 2` when enabled
  - `Reviewer QA`

Execution model:
- `Product Owner` and `Tech Lead` can run in parallel for scope and decomposition checks
- implementer lanes can run in parallel only when ownership is disjoint
- `Reviewer QA` reviews after implementer output exists
- canonical `state.md` remains orchestrator-owned

Current limit:
- the Python plugin scripts generate the dispatch contract and packets
- actual `spawn_agent` calls happen in Codex when `wrkflw:team-run` is invoked, not inside the Python scripts themselves
- parallel implementer lanes must have explicit, disjoint `Allowed Write Paths` in `agent-assignments.md` or `wrkflw:team-run` will block
- delegated role completion should be fed back through `wrkflw:team-sync` so execution-board status, team minutes, diagrams, and implementation-plan context stay current
- `wrkflw:team-run` creates worktrees for merge-eligible implementer lanes from committed `HEAD`; dirty non-workflow paths inside those role scopes block dispatch, while workflow artifacts remain orchestrator-owned
- `wrkflw:team-sync-all` can ingest result envelopes left under isolated worktrees; those envelopes should remain uncommitted and are not merge candidates
- `wrkflw:team-run-level` creates worktrees from committed `HEAD`; uncommitted changes in the orchestrator checkout are excluded and recorded as a warning in `worktrees.md`
- worktree setup touches git state outside `.workflow`, so cleanup is explicit through `wrkflw:worktree-clean` and is not hidden inside transaction rollback
- `wrkflw:merge-gate` is intentionally read-only: it verifies branch ancestry, dirty worktrees, changed paths, manifest freshness, and conflict probes, but leaves any actual merge to `wrkflw:merge-apply`
- `wrkflw:merge-apply` is intentionally explicit and state-changing: it refuses non-workflow dirty target paths, stale merge-gate evidence, moved lane branches, non-wrkflw branches, and missing confirmation; it records `.workflow/<slug>/merge-apply.*` and a pre-apply checkpoint ref
- `wrkflw:integration-gate` only executes reviewed allowlist entries selected by `test-id`; manual `command:` evidence remains text and is not executed
- `wrkflw:integration-gate` records allowlisted runs in `.workflow/<slug>/integration-runs/` and `.workflow/<slug>/records/integration-gate-runs.jsonl`, rejects shell/inline-eval allowlist entries, and blocks if the run leaves dirty non-workflow paths
- `wrkflw:integration-gate` binds its result to the current `merge-gate.json`, `merge-apply.json` when present, `dag.json`, repository `HEAD`, and `integration-test-allowlist.json` when an allowlisted run was used; rerun it after any of those change
- `wrkflw:verify-fix` binds its result to the active story file, review/role/gate artifacts, debt records, and repository `HEAD`; rerun it after any of those change
- `wrkflw:ci-feedback` binds external CI status to the active story, repository `HEAD`, and merge/apply/integration gate evidence; rerun it after new commits or gate evidence changes
- `wrkflw:accounting-record` is evidence-only and non-blocking; successful workflow commands are recorded automatically, while failed commands preserve rollback/resume behavior through transaction metadata rather than writing a visible ledger record after rollback
- workflow commands now run inside a transaction journal under `.workflow/_transactions/`, so failed commands can roll back workflow and OpenSpec artifacts instead of leaving half-written state behind
- transaction journals include phase checkpoints for `prepare`, `command`, `postprocess`, and `diagram`; `wrkflw:resume` restores the latest checkpoint and skips phases that already completed
- long multi-envelope commands can add command-progress checkpoints; `team-sync-all` snapshots after each envelope and uses the sync ledger to skip completed envelopes on resume

### Diagram history and compact vs expanded views

`wrkflw` now keeps a persisted transition history in:

```text
.workflow/<slug>/history.md
```

This is used to keep completed stories visible in both diagrams instead of inferring everything only from the current `state.md` snapshot.

Diagram rendering behavior is controlled by:

```text
.workflow/<slug>/diagram-config.md
```

Default example:

```text
# Diagram Config

- flow.completedStoriesView: expanded
- flow.showStoryProgressHistory: true
- work.showStoryProgressHistory: true
```

What these do:

- `flow.completedStoriesView: expanded`
  - show each completed story with its stage trail, such as `story-enrichment -> spec-authoring -> implementation -> review -> done`
- `flow.completedStoriesView: compact`
  - keep completed stories visible, but collapse them to a shorter summary
- `flow.showStoryProgressHistory: true`
  - keep completed-story progression visible in `diagram-flow.puml`
- `work.showStoryProgressHistory: true`
  - keep story progression visible in `diagram-work.puml`

This is not interactive folding inside PlantUML itself. The intended model is:

- use `expanded` when you want the full story trail
- switch to `compact` when the completed-history panel becomes too large

### Capability inventory

Each workflow also gets:

```text
.workflow/<slug>/capabilities.md
```

This is generated automatically from the available design seed and workflow context. Its purpose is to stop `wrkflw` from converging too early on a thin result.

It captures:

- a compatibility workflow mode used by existing scripts
- a richer planning profile that explains the shape of the work
- the capability categories the workflow should consider
- whether each capability is `required`, `recommended`, or `optional`
- story prompts that can be turned into future slices

The planning profile is the primary classification model:

- `Delivery kind`
  - `product`, `sample`, `harness`, `tool`, `migration`, `research`, `maintenance`, or `general`
- `Runtime surface`
  - `frontend`, `backend-api`, `cli`, `mcp-server`, `database`, `infra`, `batch-job`, or `unspecified`
- `Domain packs`
  - reusable capability influences such as `database`, `ai-agent`, `game-rules`, `ui-state`, `accessibility`, `security`, `governance`, `observability`, `documentation`, or `workflow-governance`
- `Assurance level`
  - `normal`, `high-risk`, `regulated`, or `experimental`
- `Workflow strategy`
  - `simple`, `spec-driven`, `parallel-team`, or `spike-first`

Compatibility workflow modes remain in the artifact so older scripts and diagrams keep working:

- `tutorial-sample`
- `feature-harness`
- `product-service`
- `sql-server-mcp`
- `browser-game`
- `general-delivery`

Capability categories are composed from the planning profile dimensions directly. The compatibility mode is display and migration metadata; it is not the primary input for capability selection.

The main use of `capabilities.md` is to improve early planning:

- review it before story slicing
- use it to name stories more concretely
- use it to decide what is intentionally deferred
- use it to avoid stopping after the first few obvious examples

`wrkflw` now uses this file directly when the workflow enters `story-slicing`:

- it regenerates `.workflow/<slug>/stories.md`
- it groups capabilities differently depending on the planning profile
- it keeps story names and dependencies closer to the intended capability coverage

That means the capability inventory is no longer just review guidance. It is the actual seed for early story generation.

Example outcomes:

- `sample` delivery with the `tutorial-sample` compatibility mode
  - tends to produce narrower learning-path stories such as:
    - core contract usage
    - field validation
    - visibility / field semantics
    - nested structures
    - developer guidance
- `harness` delivery with the `feature-harness` compatibility mode
  - tends to produce broader grouped slices such as:
    - core contract surface
    - validation and sanitization coverage
    - update and schema flows
    - runtime integration
    - developer guidance
- `tool` delivery on an `mcp-server` surface with `database`, `ai-agent`, and `security` domain packs
  - tends to produce database-tool slices such as:
    - MCP runtime and stdio transport
    - database connection configuration
    - read-only query execution and policy guardrails
    - schema discovery, result shaping, observability, and agent guidance
- `product` delivery on a `frontend` surface with `game-rules`, `ui-state`, and `accessibility` domain packs
  - tends to produce playable vertical slices such as:
    - board rendering and turn loop
    - move validation and outcome detection
    - reset and accessible interaction
    - static browser packaging and run guidance

If the generated story slices are still too broad or too thin, review and rework `capabilities.md` at the `capability-review` gate before accepting the story plan.

### Gate configuration

Each workflow has a gate config file:

```text
.workflow/<slug>/gates.md
```

Default example:

```text
# Gates

- capability-review.autoApprove: false
- epic-shaping.autoApprove: false
- story-slicing.autoApprove: false
- story-enrichment.autoApprove: false
- spec-authoring.autoApprove: false
- review.autoApprove: false
- release-planning.autoApprove: false
```

Set a gate to `true` if you want `wrkflw` to skip waiting for manual approval at that stage.

Example:

```text
- story-enrichment.autoApprove: true
- spec-authoring.autoApprove: true
```

With that configuration, entering `story-enrichment` or `spec-authoring` will not pause for human approval. `wrkflw` will record that those gates were auto-approved and continue automatically to the next stage.

### Workflow contract

Each workflow also has:

```text
.workflow/<slug>/workflow-contract.md
```

Default example:

```text
# Workflow Contract

- OpenSpec required: true
- OpenSpec initialized: false
- OpenSpec waived: false
- OpenSpec lane active: false
- OpenSpec waiver reason:
```

This file exists to stop the agent from making major workflow deviations silently.

Hard rule:
- if `OpenSpec required: true`
- and the workflow reaches `spec-authoring`
- and OpenSpec is not initialized

then `wrkflw` must block instead of continuing toward implementation.

The only supported bypass is an explicit user waiver, for example:

```text
wrkflw:override "Proceed without OpenSpec for this run."
```

## Workflow Gates And Control Commands

`wrkflw` is intentionally stage-driven. It stops at human gates instead of pushing through the whole workflow blindly.

### Main gated stages

- `capability-review`
  - review the generated capability inventory and decide whether the sample or harness coverage is broad enough before epic shaping starts
- `epic-shaping`
  - review the business problem, goal, non-goals, and constraints
- `story-slicing`
  - review whether the capability-driven story plan is split into small, independently mergeable stories
- `story-enrichment`
  - review the active story’s scope, acceptance criteria, test expectations, and risks
- `spec-authoring`
  - review the proposal, spec, and tasks before implementation
  - if OpenSpec is required but missing, this stage blocks instead of continuing
- `review`
  - review the implemented slice and validation outcome
- `release-planning`
  - review whether the work is production-worthy or only local-only progress

### What `wrkflw:approve` means

Use `wrkflw:approve` when the current stage is good enough to move forward.

Examples:

```text
wrkflw:approve "Story 2 enrichment is ready for spec authoring."
wrkflw:approve "Proceed with the first PR-sized slice."
wrkflw:approve "This slice is local-only progress and the acceptance bar is local test success."
```

Approval does two things:
- records why the stage was accepted
- advances the workflow to the next stage

At some stages it also triggers artifact generation. The most important example is:
- approving into `story-slicing` regenerates `stories.md` from `capabilities.md`

### What `wrkflw:reject` means

Use `wrkflw:reject` when the current artifact is not good enough to proceed.

Example:

```text
wrkflw:reject "The story is too broad and needs to be split into two slices."
```

Rejection does three things:
- records the rejection reason
- routes the workflow back to the nearest stage that can address the issue
- updates the next action to reflect the rework needed

### What `wrkflw:refine` means

Use `wrkflw:refine` when the stage is mostly correct but you want to improve it without treating it as a hard rejection.

Example:

```text
wrkflw:refine "Add acceptance criteria and test expectations for Story 3 only."
```

Refine keeps the workflow on the current stage and updates the next action. It is the right command for:
- tightening wording
- generating a missing artifact
- adding detail before approval
- selecting a first PR-sized slice during implementation planning

### What `wrkflw:rework` means

Use `wrkflw:rework` for a stronger revision signal when the current stage needs to be actively reworked, but you want to express that as a targeted correction rather than just a generic rejection message.

Example:

```text
wrkflw:rework "The spec needs to reflect the design seed more closely."
```

This behaves like a targeted revision trigger and routes work back through the proper stage.

### What `wrkflw:rework-item` means

Use `wrkflw:rework-item` when only a specific story or epic item needs attention, rather than the whole current stage.

Example:

```text
wrkflw:rework-item "Story 2" "Split the capability tests into two smaller slices."
```

### What `wrkflw:proceed-only` means

Use `wrkflw:proceed-only` to narrow active scope to one or more specific stories.

Example:

```text
wrkflw:proceed-only "Story 2" "Start the first real capability slice."
```

This is useful after one story closes and you want to activate the next story explicitly.

`wrkflw` will challenge this command if the selected story depends on unfinished required stories.

### What `wrkflw:defer` means

Use `wrkflw:defer` to postpone specific stories or items without rejecting the whole stage.

Example:

```text
wrkflw:defer "Story 4" "Documentation can wait until the capability slices are in place."
```

`wrkflw` will challenge this command if active scope still depends on the deferred item.

### What `wrkflw:override` means

Use `wrkflw:override` only when you explicitly want to waive a major workflow requirement.

Example:

```text
wrkflw:override "Proceed without OpenSpec for this run."
```

This is not a normal convenience command. It exists for cases where:
- the workflow contract requires OpenSpec
- OpenSpec is not initialized
- you intentionally choose to proceed anyway

That decision must come from the user, not from the agent.

### What `wrkflw:next` means

Use `wrkflw:next` only when you want the workflow to advance automatically from a non-gated stage.

If a human gate is still pending, `wrkflw:next` should not bypass it.

### Typical approval sequence for one story

For a normal story, the flow is usually:

1. `capability-review` approved
2. `epic-shaping` approved
3. `story-slicing` approved
4. `story-enrichment` approved
5. `spec-authoring` approved
6. `implementation-planning` approved
7. implementation happens
8. `review` approved
9. `release-planning` approved
10. story closes and OpenSpec change is archived

### How to decide between commands

- Use `approve` when the current stage is ready to move on.
- Use `reject` when the stage is wrong and must go back.
- Use `refine` when the stage is close but needs more detail or sharper scope.
- Use `rework` when you want to force a stronger targeted revision.
- Use `rework-item` when only one story/item is problematic.
- Use `proceed-only` when selecting the next active story or narrowing scope.
- Use `defer` when explicitly postponing non-active items.

## OpenSpec

When the workflow reaches `spec-authoring` and OpenSpec is available, `wrkflw` creates or updates an OpenSpec change under:

```text
openspec/changes/<workflow-slug>-<story-slug>/
```

OpenSpec execution is single-lane by default at the initiative level:
- one epic workflow may own the active OpenSpec lane at a time
- other epic workflows stay workflow-only until they become the active execution lane
- `wrkflw` should not pre-create OpenSpec changes across every epic lane during initialization

On final closeout, it archives the change automatically.

If OpenSpec is required but not initialized, `wrkflw` now hard-blocks at `spec-authoring` until one of these is true:
- OpenSpec is initialized
- the user explicitly issues a waiver with `wrkflw:override "..."`

`wrkflw` now also carries capability coverage into the OpenSpec artifacts:

- `proposal.md` includes:
  - planning profile dimensions
  - compatibility workflow mode
  - capability categories intentionally covered by the active story
  - required/recommended capabilities that remain deferred
- `spec.md` includes:
  - explicit coverage scenarios for the current story
  - explicit deferred-coverage visibility when the story is only a partial slice
- `tasks.md` includes:
  - tasks to make the intended capability coverage explicit
  - tasks to leave follow-up context for deferred capability categories

This means `capabilities.md` does not just help early story slicing. It now flows through into OpenSpec so spec authoring keeps the broader capability intent visible.

## Notes

- Dependency challenges are based on explicit story dependencies declared in `stories.md`.
- `wrkflw` is designed to keep work incremental and reviewable rather than implementing everything in one pass.

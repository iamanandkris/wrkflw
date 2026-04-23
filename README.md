# wrkflw

`wrkflw` is a Codex plugin for staged engineering delivery. It guides work from discovery through epic shaping, story slicing, spec authoring, implementation, review, and release while keeping small PRs, human gates, OpenSpec handoff, and live workflow diagrams in sync.

## What it supports

- `wrkflw:discuss`
- `wrkflw:approve`
- `wrkflw:reject`
- `wrkflw:rework`
- `wrkflw:refine`
- `wrkflw:rework-item`
- `wrkflw:proceed-only`
- `wrkflw:defer`
- `wrkflw:next`

It also supports:
- design seed detection from `design.md` or `docs/design.md`
- automatic OpenSpec handoff during `spec-authoring`
- workflow state and PlantUML diagram generation under `.workflow/<slug>/`
- release-plan generation and OpenSpec archive on story closeout

## Install

Clone the plugin into your local Codex plugins directory:

```bash
git clone git@github.com:iamanandkris/wrkflw.git ~/plugins/wrkflw
```

If you use a custom plugin path, clone it there instead.

Then make sure your local Codex plugin marketplace/config points at the plugin folder, for example:

```text
~/plugins/wrkflw
```

## Requirements

- Python 3
- PlantUML source rendering support if you want to render the generated `.puml` files
- OpenSpec installed if you want real OpenSpec changes instead of workflow-only artifacts

## Usage

Start a workflow:

```text
wrkflw:discuss "Implement feature X"
```

If the repo contains `design.md` or `docs/design.md`, `wrkflw` will use that as a seed automatically.

The workflow creates artifacts under:

```text
.workflow/<slug>/
```

including:
- `context.md`
- `state.md`
- `links.md`
- `design-seed.md` when applicable
- `diagram-flow.puml`
- `diagram-work.puml`

## OpenSpec

When the workflow reaches `spec-authoring` and OpenSpec is available, `wrkflw` creates or updates an OpenSpec change under:

```text
openspec/changes/<change-slug>/
```

On final closeout, it archives the change automatically.

## Notes

- Dependency challenges are based on explicit story dependencies declared in `stories.md`.
- `wrkflw` is designed to keep work incremental and reviewable rather than implementing everything in one pass.

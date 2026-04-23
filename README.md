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

That installs or updates the plugin into:

```text
~/plugins/wrkflw
```

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

## Usage

Start a workflow:

```text
wrkflw:discuss "Implement feature X"
```

Start a workflow from a design seed:

```text
wrkflw:discuss "Start this workflow from the design in docs/design.md"
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

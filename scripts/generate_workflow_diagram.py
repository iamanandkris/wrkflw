#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


STAGES = [
    "discuss",
    "capability-review",
    "epic-shaping",
    "story-slicing",
    "story-enrichment",
    "spec-authoring",
    "implementation-planning",
    "implementation",
    "review",
    "release-planning",
    "done",
]

STAGE_ALIASES = {stage: stage.replace("-", "_") for stage in STAGES}
GATED_STAGES = {
    "capability-review",
    "epic-shaping",
    "story-slicing",
    "story-enrichment",
    "spec-authoring",
    "review",
    "release-planning",
}

GATE_STATES = {"pending", "approved", "blocked", "rejected"}

STAGE_ALIASES_MAP = {
    "epic-shaped": "epic-shaping",
    "epic shaped": "epic-shaping",
    "story-sliced": "story-slicing",
    "story sliced": "story-slicing",
    "story-enriched": "story-enrichment",
    "story enriched": "story-enrichment",
    "implementation-planned": "implementation-planning",
    "implementation planned": "implementation-planning",
}

GATE_STATUS_ALIASES = {
    "awaiting approval": "pending",
    "awaiting epic and story approval": "pending",
    "awaiting story approval": "pending",
    "awaiting review": "pending",
}


def normalize_stage_name(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        return ""
    if cleaned in STAGES:
        return cleaned
    return STAGE_ALIASES_MAP.get(cleaned, cleaned)


def normalize_gate_status(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        return ""
    if cleaned in GATE_STATES:
        return cleaned
    return GATE_STATUS_ALIASES.get(cleaned, cleaned)


def normalize_state(state: dict[str, str]) -> dict[str, str]:
    normalized = dict(state)
    normalized["Current stage"] = normalize_stage_name(normalized.get("Current stage", ""))
    normalized["Human gate status"] = normalize_gate_status(normalized.get("Human gate status", ""))
    normalized["Rework target"] = normalize_stage_name(normalized.get("Rework target", ""))
    return normalized


def normalize_event(event: dict[str, str]) -> dict[str, str]:
    normalized = dict(event)
    normalized["From stage"] = normalize_stage_name(normalized.get("From stage", ""))
    normalized["To stage"] = normalize_stage_name(normalized.get("To stage", ""))
    normalized["Gate"] = normalize_gate_status(normalized.get("Gate", ""))
    return normalized


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def parse_history(path: Path) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    if not path.exists():
        return events
    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## Event "):
            if current is not None:
                events.append(normalize_event(current))
            current = {}
        elif current is not None and line.startswith("- "):
            key, _, value = line[2:].partition(":")
            current[key.strip()] = value.strip()
    if current is not None:
        events.append(normalize_event(current))
    return events


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_gate_settings(path: Path) -> dict[str, bool]:
    raw = parse_kv_list(path)
    settings: dict[str, bool] = {}
    for stage in GATED_STAGES:
        value = raw.get(f"{stage}.autoApprove", "false").strip().lower()
        settings[stage] = value in {"true", "1", "yes", "on"}
    return settings


def parse_state(path: Path) -> dict[str, str]:
    return normalize_state(parse_kv_list(path))


def parse_diagram_config(path: Path) -> dict[str, str]:
    raw = parse_kv_list(path)
    return {
        "flow.completedStoriesView": raw.get("flow.completedStoriesView", "expanded").strip() or "expanded",
        "flow.showStoryProgressHistory": raw.get("flow.showStoryProgressHistory", "true").strip() or "true",
        "work.showStoryProgressHistory": raw.get("work.showStoryProgressHistory", "true").strip() or "true",
    }


def workflow_contract(path: Path) -> dict[str, str]:
    raw = parse_kv_list(path)
    return {
        "OpenSpec required": raw.get("OpenSpec required", "").strip(),
        "OpenSpec initialized": raw.get("OpenSpec initialized", "").strip(),
        "OpenSpec waived": raw.get("OpenSpec waived", "").strip(),
        "OpenSpec waiver reason": raw.get("OpenSpec waiver reason", "").strip(),
    }


def capability_mode(path: Path) -> str:
    for line in read_text(path).splitlines():
        if line.startswith("- Mode:"):
            return line.split(":", 1)[1].strip()
    return "general-delivery"


def alias(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "node"


def puml_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace(chr(34), "'")


def parse_story_entries(stories_text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    body: list[str] = []
    for raw_line in stories_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## Recommended"):
            if current is not None:
                current["body"] = "\n".join(body).strip()
                entries.append(current)
                current = None
            break
        if line.startswith("## Story "):
            if current is not None:
                current["body"] = "\n".join(body).strip()
                entries.append(current)
            header = line[3:].strip()
            name = header.split(":", 1)[0].strip()
            title = header.split(":", 1)[1].strip() if ":" in header else name
            current = {"name": name, "title": title, "depends_on": "", "body": ""}
            body = []
        elif current is not None:
            stripped = line.strip()
            if stripped.lower().startswith("depends on:"):
                current["depends_on"] = stripped.split(":", 1)[1].strip()
            elif stripped:
                body.append(stripped)
    if current is not None:
        current["body"] = "\n".join(body).strip()
        entries.append(current)
    return entries


def extract_epic_sections(epic_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for raw_line in epic_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(body).strip()
            current = line[3:].strip()
            body = []
        elif current is not None and line.strip():
            body.append(line.strip())
    if current is not None:
        sections[current] = "\n".join(body).strip()
    return sections


def context_value(path: Path, key: str) -> str:
    raw = parse_kv_list(path)
    return raw.get(key, "").strip()


def first_design_section(text: str, section: str) -> str:
    current: str | None = None
    body: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            if current == section:
                break
            current = line[3:].strip()
            body = []
            continue
        if current == section and line.strip():
            body.append(line.strip())
    if not body:
        return ""
    first = body[0]
    if first.startswith("- "):
        return first[2:].strip()
    return first


def preferred_summary(*values: str) -> str:
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned == "-":
            continue
        if cleaned.startswith("- "):
            continue
        return cleaned
    return "-"


def story_file_progress(wf: Path, stories: list[dict[str, str]], state: dict[str, str]) -> dict[str, list[str]]:
    progress: dict[str, list[str]] = {}
    done_state = (state.get("Current stage", "") == "done")
    active_items = {item.strip() for item in state.get("Active items", "").split(",") if item.strip()}
    for story in stories:
        match = re.search(r"(\d+)", story["name"])
        if not match:
            continue
        number = match.group(1)
        story_file = wf / f"story-{number}.md"
        if story_file.exists():
            trail = ["story-enrichment"]
            if done_state and not active_items:
                trail.extend(["spec-authoring", "implementation-planning", "implementation", "review", "release-planning", "done"])
            progress[story["name"]] = trail
    return progress


def parse_task_progress(text: str) -> tuple[list[str], list[str]]:
    complete: list[str] = []
    pending: list[str] = []
    current_heading: str | None = None
    expect_description = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("- [x] "):
            task = line[6:].strip()
            complete.append(task)
            expect_description = False
        elif line.startswith("- [ ] "):
            task = line[6:].strip()
            pending.append(task)
            expect_description = False
        elif line.startswith("## Task "):
            current_heading = line[3:].strip()
            expect_description = True
        elif line.startswith("## "):
            current_heading = line[3:].strip()
            expect_description = False
        elif line.startswith("- "):
            task = line[2:].strip()
            pending.append(f"{current_heading}: {task}" if current_heading else task)
            expect_description = False
        elif expect_description and line:
            pending.append(line)
            expect_description = False
    return complete, pending


def choose_task_source(workflow_tasks: str, openspec_tasks: str) -> str:
    workflow_complete, workflow_pending = parse_task_progress(workflow_tasks)
    openspec_complete, openspec_pending = parse_task_progress(openspec_tasks)
    openspec_placeholder = all(
        "migrated workflow tasks" in task.lower() or "approved story scope" in task.lower()
        for task in (openspec_complete + openspec_pending)
    ) if (openspec_complete or openspec_pending) else False
    if openspec_placeholder and (workflow_complete or workflow_pending):
        return workflow_tasks
    workflow_score = len(workflow_complete) + len(workflow_pending)
    openspec_score = len(openspec_complete) + len(openspec_pending)
    return openspec_tasks if openspec_score >= workflow_score else workflow_tasks


def stage_color(stage: str, current: str) -> str:
    if stage == current:
        return "#8ecae6"
    if STAGES.index(stage) < STAGES.index(current):
        return "#90be6d"
    return "#d9d9d9"


def current_stage_color(stage: str, current: str, state: dict[str, str]) -> str:
    if stage == current and state.get("Human gate status", "") == "blocked":
        return "#f9c74f"
    return stage_color(stage, current)


def story_progress_from_history(
    stories: list[dict[str, str]],
    events: list[dict[str, str]],
    wf: Path,
    state: dict[str, str],
) -> dict[str, list[str]]:
    story_names = {story["name"] for story in stories}
    progress: dict[str, list[str]] = {name: [] for name in story_names}

    def add_stage(name: str, stage: str) -> None:
        if name not in progress or not stage or stage == "-":
            return
        if stage not in progress[name]:
            progress[name].append(stage)

    for event in events:
        focus_items = [item.strip() for item in event.get("Focus items", "").split(",") if item.strip()]
        to_stage = event.get("To stage", "").strip()
        from_stage = event.get("From stage", "").strip()
        command = event.get("Command", "").strip()
        for item in focus_items:
            if item in story_names:
                if not (command == "proceed-only" and from_stage == "done"):
                    add_stage(item, from_stage)
                add_stage(item, to_stage)

    fallback = story_file_progress(wf, stories, state)
    for name, trail in fallback.items():
        for stage in trail:
            add_stage(name, stage)

    if state.get("Current stage", "") == "done" and not {item.strip() for item in state.get("Active items", "").split(",") if item.strip()}:
        default_trail = [
            "story-enrichment",
            "spec-authoring",
            "implementation-planning",
            "implementation",
            "review",
            "release-planning",
            "done",
        ]
        for story in stories:
            if not progress.get(story["name"]):
                progress[story["name"]] = list(default_trail)
    return progress


def story_touch_order(events: list[dict[str, str]], stories: list[dict[str, str]]) -> list[str]:
    story_names = {story["name"] for story in stories}
    order: list[str] = []
    seen: set[str] = set()
    for event in events:
        for item in [value.strip() for value in event.get("Focus items", "").split(",") if value.strip()]:
            if item in story_names and item not in seen:
                seen.add(item)
                order.append(item)
    return order


def story_status(
    story_name: str,
    state: dict[str, str],
    current_stage: str,
    progress: dict[str, list[str]],
    touched_order: list[str],
) -> str:
    active = {item.strip() for item in state.get("Active items", "").split(",") if item.strip()}
    deferred = {item.strip() for item in state.get("Deferred items", "").split(",") if item.strip()}
    if story_name in deferred:
        return "deferred"
    if story_name in active:
        if current_stage == "done":
            return "completed"
        if current_stage in {"implementation", "review", "release-planning"}:
            return "in-progress"
        return "active"
    story_progress = progress.get(story_name, [])
    completed_markers = {"review", "release-planning", "done"}
    if story_progress and any(stage in completed_markers for stage in story_progress):
        return "completed"
    if current_stage == "done" and not active and story_progress:
        return "completed"
    if story_name in touched_order:
        touch_index = touched_order.index(story_name)
        if touch_index < len(touched_order) - 1:
            return "completed"
        if story_progress:
            return "in-progress"
    active_story_num = None
    active_text = next(iter(active), "")
    match = re.search(r"(\d+)", active_text)
    if match:
        active_story_num = int(match.group(1))
    this_match = re.search(r"(\d+)", story_name)
    this_num = int(this_match.group(1)) if this_match else None
    if active_story_num is not None and this_num is not None and this_num < active_story_num:
        return "completed"
    return "future"


def story_color(status: str) -> str:
    return {
        "completed": "#90be6d",
        "in-progress": "#8ecae6",
        "active": "#8ecae6",
        "deferred": "#f9c74f",
        "future": "#d9d9d9",
    }.get(status, "#d9d9d9")


def task_color(done: bool) -> str:
    return "#90be6d" if done else "#d9d9d9"


def active_story_spec_path(wf: Path, state: dict[str, str]) -> Path | None:
    active = state.get("Active items", "").split(",", 1)[0].strip()
    if not active:
        return None
    match = re.search(r"(\d+)", active)
    if not match:
        return None
    return wf / "specs" / f"story-{match.group(1)}-spec.md"


def stage_detail(stage: str, state: dict[str, str], links: dict[str, str], stories: list[dict[str, str]], gates: dict[str, bool]) -> str:
    active = state.get("Active items", "") or "-"
    deferred = state.get("Deferred items", "") or "-"
    next_action = state.get("Next action", "") or "-"
    current_stage = state.get("Current stage", "")
    openspec = links.get("OpenSpec change", "") or "-"
    auto = "on" if gates.get(stage, False) else "off"
    if current_stage in {"discuss", "capability-review", "epic-shaping", "story-slicing", "story-enrichment"}:
        openspec = "-"
    if stage == "discuss":
        return f"goal framing\\nactive: {active}"
    if stage == "capability-review":
        return f"capability gate\\nauto: {auto}"
    if stage == "epic-shaping":
        return f"epic review\\nauto: {auto}"
    if stage == "story-slicing":
        return f"{len(stories)} stories\\nauto: {auto}"
    if stage == "story-enrichment":
        return f"enriching {active}\\nauto: {auto}"
    if stage == "spec-authoring":
        return f"OpenSpec\\nauto: {auto}"
    if stage == "implementation-planning":
        return f"plan slice\\nactive: {active}"
    if stage == "implementation":
        return f"build/test\\nactive: {active}"
    if stage == "review":
        return f"review gate\\nauto: {auto}"
    if stage == "release-planning":
        return f"release prep\\nauto: {auto}"
    return "complete"


def story_summary_lines(
    stories: list[dict[str, str]],
    state: dict[str, str],
    progress: dict[str, list[str]],
    touched_order: list[str],
) -> list[str]:
    current_stage = state.get("Current stage", "discuss")
    lines: list[str] = []
    for story in stories[:8]:
        status = story_status(story["name"], state, current_stage, progress, touched_order)
        dep = f" -> {story['depends_on']}" if story["depends_on"] else ""
        lines.append(f"{story['name']} [{status}]{dep}")
    return lines or ["-"]


def story_execution_detail_lines(
    stories: list[dict[str, str]],
    state: dict[str, str],
    progress: dict[str, list[str]],
    touched_order: list[str],
    view: str,
) -> list[str]:
    current_stage = state.get("Current stage", "discuss")
    if not stories:
        return ["-"]

    lines: list[str] = []
    for index, story in enumerate(stories[:12], start=1):
        status = story_status(story["name"], state, current_stage, progress, touched_order)
        trail = display_progress_chain(progress.get(story["name"], []), status)
        depends = story.get("depends_on", "").strip() or "-"
        body = story.get("body", "").strip() or "-"
        lines.append(f"{story['name']} [{status}]: {story['title']}")
        lines.append(f"  depends: {depends}")
        lines.append(f"  trail: {trail}")
        if view != "compact":
            lines.append(f"  {body}")
        if index < min(len(stories), 12):
            lines.append("---")
    return lines


def task_summary_lines(completed: list[str], pending: list[str]) -> list[str]:
    lines: list[str] = []
    for task in completed[:4]:
        lines.append(f"done: {task}")
    for task in pending[:4]:
        lines.append(f"todo: {task}")
    return lines or ["-"]


def completed_story_entries(
    stories: list[dict[str, str]],
    state: dict[str, str],
    progress: dict[str, list[str]],
    touched_order: list[str],
) -> list[dict[str, str]]:
    current_stage = state.get("Current stage", "discuss")
    return [story for story in stories if story_status(story["name"], state, current_stage, progress, touched_order) == "completed"]


def compact_story_progress_line(story: dict[str, str]) -> list[str]:
    summary = (story.get("body") or "completed").splitlines()[0].strip()
    return [f"{story['name']}: {story['title']}", f"  {summary}"]


def progress_chain(stages: list[str]) -> str:
    ordered = [stage for stage in STAGES if stage in stages and stage not in {"discuss", "capability-review", "epic-shaping", "story-slicing"}]
    return " -> ".join(ordered) if ordered else "-"


def display_progress_chain(stages: list[str], status: str) -> str:
    filtered = list(stages)
    if status != "completed":
        filtered = [stage for stage in filtered if stage not in {"done", "release-planning", "review"}]
    return progress_chain(filtered)


def completed_story_summary_lines(
    stories: list[dict[str, str]],
    state: dict[str, str],
    progress: dict[str, list[str]],
    touched_order: list[str],
    view: str,
) -> list[str]:
    lines: list[str] = []
    for story in completed_story_entries(stories, state, progress, touched_order)[:8]:
        if view == "compact":
            lines.extend(compact_story_progress_line(story))
        else:
            lines.append(f"{story['name']}: {story['title']}")
            lines.append(f"  trail: {progress_chain(progress.get(story['name'], []))}")
            summary = (story.get("body") or "completed").splitlines()[0].strip()
            lines.append(f"  {summary}")
    return lines or ["-"]


def completed_story_flow_notes(
    stories: list[dict[str, str]],
    state: dict[str, str],
    progress: dict[str, list[str]],
    touched_order: list[str],
    view: str,
) -> list[str]:
    completed = completed_story_entries(stories, state, progress, touched_order)
    if not completed:
        return [
            'note "Completed story context:\\n-" as completed_story_context_empty',
            "completed_story_context_empty .. story_slicing",
        ]

    lines: list[str] = []
    for index, story in enumerate(completed[:12], start=1):
        note_alias = f"completed_story_context_{index}"
        body = story.get("body", "").strip() or "-"
        trail = progress_chain(progress.get(story["name"], []))
        if view == "compact":
            note_lines = [
                f"Completed {story['name']}",
                story["title"],
                f"trail: {trail}",
            ]
        else:
            note_lines = [
                f"Completed {story['name']}",
                story["title"],
                f"trail: {trail}",
                body,
            ]
        note_text = puml_text("\n".join(note_lines))
        lines.append(f'note "{note_text}" as {note_alias}')
        lines.append(f"{note_alias} .. story_slicing")
    return lines


def story_flow_notes(
    stories: list[dict[str, str]],
    state: dict[str, str],
    progress: dict[str, list[str]],
    touched_order: list[str],
    view: str,
) -> list[str]:
    current_stage = state.get("Current stage", "discuss")
    lines: list[str] = []
    if not stories:
        return [
            'state "Story Execution Context" as story_execution_context {',
            '  state "Story execution context\\n-" as story_execution_context_empty #d9d9d9',
            "}",
            "story_slicing --> story_execution_context",
        ]

    lines.append('state "Story Execution Context" as story_execution_context {')
    previous_alias: str | None = None
    for index, story in enumerate(stories[:12], start=1):
        node_alias = f"story_execution_context_{index}"
        status = story_status(story["name"], state, current_stage, progress, touched_order)
        body = story.get("body", "").strip() or "-"
        trail = display_progress_chain(progress.get(story["name"], []), status)
        depends = story.get("depends_on", "").strip() or "-"
        header = f"{story['name']} [{status}]"
        if view == "compact":
            note_lines = [
                header,
                story["title"],
                f"depends: {depends}",
                f"trail: {trail}",
            ]
        else:
            note_lines = [
                header,
                story["title"],
                f"depends: {depends}",
                f"trail: {trail}",
                body,
            ]
        note_text = puml_text("\n".join(note_lines))
        lines.append(f'  state "{note_text}" as {node_alias} {story_color(status)}')
        if previous_alias is not None:
            lines.append(f"  {previous_alias} --> {node_alias}")
        previous_alias = node_alias
    lines.append("}")
    lines.append("story_slicing --> story_execution_context")
    return lines


def write_flow_diagram(
    wf: Path,
    slug: str,
    state: dict[str, str],
    links: dict[str, str],
    stories: list[dict[str, str]],
    completed_tasks: list[str],
    pending_tasks: list[str],
) -> None:
    current = state.get("Current stage", "discuss") or "discuss"
    gates = parse_gate_settings(wf / "gates.md")
    contract = workflow_contract(wf / "workflow-contract.md")
    mode = capability_mode(wf / "capabilities.md")
    config = parse_diagram_config(wf / "diagram-config.md")
    events = parse_history(wf / "history.md")
    progress = story_progress_from_history(stories, events, wf, state)
    touched_order = story_touch_order(events, stories)
    epic_sections = extract_epic_sections(read_text(wf / "epic.md"))
    context_problem = context_value(wf / "context.md", "Problem")
    context_goal = context_value(wf / "context.md", "Goal")
    design_seed = read_text(wf / "design-seed.md")
    design_problem = first_design_section(design_seed, "Purpose")
    design_goal = first_design_section(design_seed, "Desired Outcome")
    epic_problem = preferred_summary(
        epic_sections.get("Problem", "").splitlines()[0] if epic_sections.get("Problem") else "",
        context_problem,
        design_problem,
    )
    epic_goal = preferred_summary(
        epic_sections.get("Goal", "").splitlines()[0] if epic_sections.get("Goal") else "",
        context_goal,
        design_goal,
    )
    lines = [
        "@startuml",
        f"title Workflow Flow: {slug}",
        "skinparam shadowing false",
        "skinparam defaultFontName Monospaced",
        "hide empty description",
        "[*] --> discuss",
    ]
    for stage in STAGES:
        detail = stage_detail(stage, state, links, stories, gates)
        lines.append(f'state "{stage}\\n{detail}" as {STAGE_ALIASES[stage]} {current_stage_color(stage, current, state)}')
    current_openspec = links.get("OpenSpec change", "") or "-"
    if current in {"discuss", "capability-review", "epic-shaping", "story-slicing", "story-enrichment"}:
        current_openspec = "-"
    active_task_lines = task_summary_lines(completed_tasks, pending_tasks)
    implementation_header = f"Active: {state.get('Active items', '-') or '-'}"
    if current in {"discuss", "capability-review", "epic-shaping", "story-slicing", "story-enrichment"}:
        active_task_lines = ["tasks pending for active story"]
        implementation_header = "Planned slice preview"
    elif STAGES.index(current) < STAGES.index("implementation"):
        implementation_header = "Planned slice preview"

    lines.extend(
        [
            "discuss --> capability_review",
            "capability_review --> epic_shaping",
            "epic_shaping --> story_slicing",
            "story_slicing --> story_enrichment",
            "story_enrichment --> spec_authoring",
            "spec_authoring --> implementation_planning",
            "implementation_planning --> implementation",
            "implementation --> review",
            "review --> release_planning",
            "release_planning --> done",
            "done --> [*]",
            f"note right of {STAGE_ALIASES[current]}",
            f"Gate: {state.get('Human gate status', '-') or '-'}",
            f"Blocked: {state.get('Blocked reason', '-') or '-'}",
            f"AutoApprove: {'on' if gates.get(current, False) else 'off'}",
            f"OpenSpec: {current_openspec}",
            f"OpenSpec required: {contract.get('OpenSpec required', '-') or '-'}",
            f"OpenSpec initialized: {contract.get('OpenSpec initialized', '-') or '-'}",
            f"Next: {state.get('Next action', '-') or '-'}",
            "end note",
            "note right of epic_shaping",
            f"Epic problem: {epic_problem}",
            f"Epic goal: {epic_goal}",
            f"Workflow mode: {mode}",
            "end note",
            "note right of story_slicing",
            *story_summary_lines(stories, state, progress, touched_order),
            "end note",
            "note right of implementation",
            implementation_header,
            f"OpenSpec: {current_openspec}",
            *active_task_lines,
            "end note",
            *story_flow_notes(stories, state, progress, touched_order, config.get("flow.completedStoriesView", "expanded")),
            "@enduml",
            "",
        ]
    )
    (wf / "diagram-flow.puml").write_text("\n".join(lines), encoding="utf-8")


def write_work_diagram(wf: Path, slug: str, state: dict[str, str], links: dict[str, str]) -> None:
    stories = parse_story_entries(read_text(wf / "stories.md"))
    gates = parse_gate_settings(wf / "gates.md")
    contract = workflow_contract(wf / "workflow-contract.md")
    mode = capability_mode(wf / "capabilities.md")
    config = parse_diagram_config(wf / "diagram-config.md")
    events = parse_history(wf / "history.md")
    progress = story_progress_from_history(stories, events, wf, state)
    touched_order = story_touch_order(events, stories)
    epic_sections = extract_epic_sections(read_text(wf / "epic.md"))
    context_problem = context_value(wf / "context.md", "Problem")
    context_goal = context_value(wf / "context.md", "Goal")
    design_seed = read_text(wf / "design-seed.md")
    design_problem = first_design_section(design_seed, "Purpose")
    design_goal = first_design_section(design_seed, "Desired Outcome")
    epic_problem = preferred_summary(
        epic_sections.get("Problem", "").splitlines()[0] if epic_sections.get("Problem") else "",
        context_problem,
        design_problem,
    )
    epic_goal = preferred_summary(
        epic_sections.get("Goal", "").splitlines()[0] if epic_sections.get("Goal") else "",
        context_goal,
        design_goal,
    )

    active_story = state.get("Active items", "").split(",", 1)[0].strip()
    current_stage = state.get("Current stage", "")
    openspec_change = links.get("OpenSpec change", "") if current_stage not in {"discuss", "capability-review", "epic-shaping", "story-slicing", "story-enrichment"} else ""
    openspec_tasks_path = Path(wf.parent.parent / openspec_change / "tasks.md") if openspec_change else None
    workflow_tasks_text = read_text(wf / "tasks.md")
    openspec_tasks_text = read_text(openspec_tasks_path) if openspec_tasks_path and openspec_tasks_path.exists() else ""
    tasks_text = choose_task_source(workflow_tasks_text, openspec_tasks_text) if openspec_change else ""
    completed_tasks, pending_tasks = parse_task_progress(tasks_text)
    if active_story and current_stage in {"review", "release-planning", "done"} and not completed_tasks:
        completed_tasks, pending_tasks = pending_tasks, []

    lines = [
        "@startuml",
        f"title Workflow Work Map: {slug}",
        "left to right direction",
        "skinparam shadowing false",
        "skinparam defaultFontName Monospaced",
        "skinparam packageStyle rectangle",
        "skinparam ArrowColor #666666",
        "",
        'legend right',
        '|= Color |= Meaning |',
        '|<#90be6d>| Completed |',
        '|<#8ecae6>| In progress / active |',
        '|<#f9c74f>| Deferred / caution |',
        '|<#d9d9d9>| Future work |',
        'endlegend',
        "",
        f'package "Epic" #white {{',
        f'  note as epic_note',
        f'  Epic problem: {epic_problem}',
        f'  Epic goal: {epic_goal}',
        f'  Workflow mode: {mode}',
        f'  Current stage: {state.get("Current stage", "-") or "-"}',
        f'  Challenge: {state.get("Challenge note", "-") or "-"}',
        f'  Blocked: {state.get("Blocked reason", "-") or "-"}',
        f'  AutoApprove current gate: {"on" if gates.get(state.get("Current stage", ""), False) else "off"}',
        f'  OpenSpec required: {contract.get("OpenSpec required", "-") or "-"}',
        f'  OpenSpec initialized: {contract.get("OpenSpec initialized", "-") or "-"}',
        f'  end note',
        "}",
        "",
        'package "Stories" #white {',
    ]

    for story in stories:
        status = story_status(story["name"], state, state.get("Current stage", "discuss"), progress, touched_order)
        color = story_color(status)
        story_alias = alias(story["name"])
        body = story["body"] or "-"
        lines.append(f'  rectangle "{puml_text(story["name"])}\\n{puml_text(story["title"])}\\n[{status}]\\n{puml_text(body)}" as {story_alias} {color}')
    lines.append("}")
    lines.append("")

    for story in stories:
        story_alias = alias(story["name"])
        if story["depends_on"]:
            for dep in [item.strip() for item in story["depends_on"].split(",") if item.strip()]:
                lines.append(f"{alias(dep)} --> {story_alias}")

    completed_stories = completed_story_entries(stories, state, progress, touched_order)
    if completed_stories:
        lines.extend(
            [
                "",
                f'package "Completed Story Context" #white {{',
            ]
        )
        for story in completed_stories[:6]:
            story_alias = alias(story["name"])
            done_alias = alias(f"{story['name']}_completed")
            body = story["body"] or "completed"
            lines.append(f'  rectangle "{puml_text(story["name"])}\\nCompleted\\n{puml_text(body)}" as {done_alias} #90be6d')
            lines.append(f"  {story_alias} --> {done_alias}")
        lines.append("}")

    if config.get("work.showStoryProgressHistory", "true").lower() in {"true", "1", "yes", "on"} and stories:
        lines.extend(["", 'package "Story Progress History" #white {'])
        for story in stories[:8]:
            status = story_status(story["name"], state, state.get("Current stage", "discuss"), progress, touched_order)
            trail = display_progress_chain(progress.get(story["name"], []), status)
            lines.append(f'  rectangle "{puml_text(story["name"])}\\n[{status}]\\ntrail: {puml_text(trail)}" as {alias(story["name"] + "_trail")} {story_color(status)}')
        lines.append("}")

    if active_story:
        task_node = alias(f"{active_story}_tasks")
        task_package = "Active Story Tasks"
        task_header_color = "#8ecae6"
        if current_stage == "done":
            task_package = "Last Completed Story Tasks"
            task_header_color = "#90be6d"
        lines.extend(
            [
                "",
                f'package "{task_package}" #white {{',
            ]
        )
        if current_stage in {"discuss", "capability-review", "epic-shaping", "story-slicing", "story-enrichment"}:
            lines.append(f'  rectangle "{puml_text(active_story)}\\nSpec/tasks pending" as {task_node} #8ecae6')
        else:
            lines.append(f'  rectangle "{puml_text(active_story)}\\nOpenSpec: {puml_text(openspec_change or "-")}" as {task_node} {task_header_color}')
            for idx, task in enumerate(completed_tasks[:6], start=1):
                lines.append(f'  rectangle "Done: {puml_text(task)}" as {task_node}_done_{idx} {task_color(True)}')
                lines.append(f"  {task_node} --> {task_node}_done_{idx}")
            for idx, task in enumerate(pending_tasks[:6], start=1):
                lines.append(f'  rectangle "Todo: {puml_text(task)}" as {task_node}_todo_{idx} {task_color(False)}')
                lines.append(f"  {task_node} --> {task_node}_todo_{idx}")
        lines.append("}")
        lines.append(f"{alias(active_story)} --> {task_node}")

    lines.extend(["", "@enduml", ""])
    (wf / "diagram-work.puml").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate live PlantUML workflow diagrams from workflow state.")
    parser.add_argument("--slug", required=True, help="Workflow slug")
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wf = root / ".workflow" / args.slug
    state = parse_state(wf / "state.md")
    links = parse_kv_list(wf / "links.md")
    stories = parse_story_entries(read_text(wf / "stories.md"))
    openspec_change = links.get("OpenSpec change", "")
    openspec_tasks_path = Path(wf.parent.parent / openspec_change / "tasks.md") if openspec_change else None
    workflow_tasks_text = read_text(wf / "tasks.md")
    openspec_tasks_text = read_text(openspec_tasks_path) if openspec_tasks_path and openspec_tasks_path.exists() else ""
    tasks_text = choose_task_source(workflow_tasks_text, openspec_tasks_text)
    completed_tasks, pending_tasks = parse_task_progress(tasks_text)
    active_story = state.get("Active items", "").split(",", 1)[0].strip()
    if active_story and state.get("Current stage", "") in {"review", "release-planning", "done"} and not completed_tasks:
        completed_tasks, pending_tasks = pending_tasks, []

    write_flow_diagram(wf, args.slug, state, links, stories, completed_tasks, pending_tasks)
    write_work_diagram(wf, args.slug, state, links)
    legacy = wf / "diagram.puml"
    if legacy.exists():
        legacy.unlink()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

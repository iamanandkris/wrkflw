#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


STAGES = [
    "discuss",
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


def parse_kv_list(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("- "):
            key, _, value = line[2:].partition(":")
            values[key.strip()] = value.strip()
    return values


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


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


def story_status(story_name: str, state: dict[str, str], current_stage: str) -> str:
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


def stage_detail(stage: str, state: dict[str, str], links: dict[str, str], stories: list[dict[str, str]]) -> str:
    active = state.get("Active items", "") or "-"
    deferred = state.get("Deferred items", "") or "-"
    next_action = state.get("Next action", "") or "-"
    challenge = state.get("Challenge note", "") or "-"
    current_stage = state.get("Current stage", "")
    openspec = links.get("OpenSpec change", "") or "-"
    if current_stage in {"discuss", "epic-shaping", "story-slicing", "story-enrichment"}:
        openspec = "-"
    if stage == "discuss":
        return f"goal framing\\nactive: {active}"
    if stage == "epic-shaping":
        return f"epic review\\ngate: {state.get('Human gate status', '-') or '-'}"
    if stage == "story-slicing":
        return f"{len(stories)} stories\\ndeferred: {deferred}"
    if stage == "story-enrichment":
        return f"enriching {active}\\nitem: {state.get('Item note', '-') or '-'}"
    if stage == "spec-authoring":
        return f"OpenSpec\\n{openspec}"
    if stage == "implementation-planning":
        return f"plan slice\\nactive: {active}"
    if stage == "implementation":
        return f"build/test\\nactive: {active}"
    if stage == "review":
        return f"review gate\\nnext: {next_action}"
    if stage == "release-planning":
        return f"release prep\\nactive: {active}"
    return "complete"


def story_summary_lines(stories: list[dict[str, str]], state: dict[str, str]) -> list[str]:
    current_stage = state.get("Current stage", "discuss")
    lines: list[str] = []
    for story in stories[:8]:
        status = story_status(story["name"], state, current_stage)
        dep = f" -> {story['depends_on']}" if story["depends_on"] else ""
        lines.append(f"{story['name']} [{status}]{dep}")
    return lines or ["-"]


def task_summary_lines(completed: list[str], pending: list[str]) -> list[str]:
    lines: list[str] = []
    for task in completed[:4]:
        lines.append(f"done: {task}")
    for task in pending[:4]:
        lines.append(f"todo: {task}")
    return lines or ["-"]


def completed_story_entries(stories: list[dict[str, str]], state: dict[str, str]) -> list[dict[str, str]]:
    current_stage = state.get("Current stage", "discuss")
    return [story for story in stories if story_status(story["name"], state, current_stage) == "completed"]


def completed_story_summary_lines(stories: list[dict[str, str]], state: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for story in completed_story_entries(stories, state)[:6]:
        summary = (story.get("body") or "completed").splitlines()[0].strip()
        lines.append(f"{story['name']}: {story['title']}")
        lines.append(f"  {summary}")
    return lines or ["-"]


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
    epic_sections = extract_epic_sections(read_text(wf / "epic.md"))
    epic_problem = epic_sections.get("Problem", "-").splitlines()[0] if epic_sections.get("Problem") else "-"
    epic_goal = epic_sections.get("Goal", "-").splitlines()[0] if epic_sections.get("Goal") else "-"
    lines = [
        "@startuml",
        f"title Workflow Flow: {slug}",
        "skinparam shadowing false",
        "skinparam defaultFontName Monospaced",
        "hide empty description",
        "[*] --> discuss",
    ]
    for stage in STAGES:
        detail = stage_detail(stage, state, links, stories)
        lines.append(f'state "{stage}\\n{detail}" as {STAGE_ALIASES[stage]} {stage_color(stage, current)}')
    current_openspec = links.get("OpenSpec change", "") or "-"
    if current in {"discuss", "epic-shaping", "story-slicing", "story-enrichment"}:
        current_openspec = "-"
    active_task_lines = task_summary_lines(completed_tasks, pending_tasks)
    if current in {"discuss", "epic-shaping", "story-slicing", "story-enrichment"}:
        active_task_lines = ["tasks pending for active story"]

    lines.extend(
        [
            "discuss --> epic_shaping",
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
            f"OpenSpec: {current_openspec}",
            f"Next: {state.get('Next action', '-') or '-'}",
            "end note",
            "note right of epic_shaping",
            f"Epic problem: {epic_problem}",
            f"Epic goal: {epic_goal}",
            "end note",
            "note right of story_slicing",
            *story_summary_lines(stories, state),
            "end note",
            "note right of implementation",
            f"Active: {state.get('Active items', '-') or '-'}",
            f"OpenSpec: {current_openspec}",
            *active_task_lines,
            "end note",
            "note left of story_slicing",
            "Completed story context:",
            *completed_story_summary_lines(stories, state),
            "end note",
            "@enduml",
            "",
        ]
    )
    (wf / "diagram-flow.puml").write_text("\n".join(lines), encoding="utf-8")


def write_work_diagram(wf: Path, slug: str, state: dict[str, str], links: dict[str, str]) -> None:
    stories = parse_story_entries(read_text(wf / "stories.md"))
    epic = read_text(wf / "epic.md")
    epic_goal = ""
    for line in epic.splitlines():
        if line.startswith("## Goal"):
            continue
        if epic_goal == "" and line.strip() and not line.startswith("#"):
            epic_goal = line.strip()
            break

    active_story = state.get("Active items", "").split(",", 1)[0].strip()
    current_stage = state.get("Current stage", "")
    openspec_change = links.get("OpenSpec change", "") if current_stage not in {"discuss", "epic-shaping", "story-slicing", "story-enrichment"} else ""
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
        f'  Epic goal: {epic_goal or "-"}',
        f'  Current stage: {state.get("Current stage", "-") or "-"}',
        f'  Challenge: {state.get("Challenge note", "-") or "-"}',
        f'  end note',
        "}",
        "",
        'package "Stories" #white {',
    ]

    for story in stories:
        status = story_status(story["name"], state, state.get("Current stage", "discuss"))
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

    completed_stories = completed_story_entries(stories, state)
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
        if current_stage in {"discuss", "epic-shaping", "story-slicing", "story-enrichment"}:
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
    state = parse_kv_list(wf / "state.md")
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

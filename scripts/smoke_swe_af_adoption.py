#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

from workflow_integration_gate import redact_output


REPO_ROOT = Path(__file__).resolve().parents[1]
HANDLER = REPO_ROOT / "scripts" / "handle_workflow_command.py"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")


def run_workflow(
    root: Path,
    command: str,
    reason: str | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    args = [
        "python3",
        str(HANDLER),
        "--slug",
        "demo",
        "--root",
        str(root),
        "--command",
        command,
    ]
    if reason:
        args.extend(["--reason", reason])
    command_env = os.environ.copy()
    if env:
        command_env.update(env)
    result = subprocess.run(args, cwd=REPO_ROOT, capture_output=True, text=True, check=False, env=command_env)
    if check and result.returncode != 0:
        raise AssertionError(
            "workflow command failed\n"
            f"command: {' '.join(args)}\n"
            f"exit: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def run_cmd(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise AssertionError(
            "command failed\n"
            f"command: {' '.join(args)}\n"
            f"exit: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def init_git_repo(root: Path) -> None:
    run_cmd(["git", "init"], root)
    run_cmd(["git", "config", "user.email", "wrkflw-smoke@example.invalid"], root)
    run_cmd(["git", "config", "user.name", "wrkflw smoke"], root)
    run_cmd(["git", "add", ".workflow"], root)
    run_cmd(["git", "commit", "-m", "baseline workflow"], root)


def parse_state(root: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    for line in (root / ".workflow" / "demo" / "state.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        key, _, value = line[2:].partition(":")
        state[key.strip()] = value.strip()
    return state


def parse_dag(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "dag.json").read_text(encoding="utf-8"))


def parse_execution_path(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "execution-path.json").read_text(encoding="utf-8"))


def parse_feedback_synthesis(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "feedback-synthesis.json").read_text(encoding="utf-8"))


def parse_issue_advisor(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "issue-advisor.json").read_text(encoding="utf-8"))


def parse_replan(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "replan.json").read_text(encoding="utf-8"))


def parse_verify_fix(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "verify-fix.json").read_text(encoding="utf-8"))


def parse_ci_feedback(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "ci-feedback.json").read_text(encoding="utf-8"))


def parse_accounting(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "accounting.json").read_text(encoding="utf-8"))


def parse_invocation_records(root: Path) -> list[dict[str, object]]:
    path = root / ".workflow" / "demo" / "records" / "invocations.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_adaptation_records(root: Path) -> list[dict[str, object]]:
    path = root / ".workflow" / "demo" / "records" / "adaptations.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_replan_records(root: Path) -> list[dict[str, object]]:
    path = root / ".workflow" / "demo" / "records" / "replans.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_agent_result_validation_records(root: Path) -> list[dict[str, object]]:
    path = root / ".workflow" / "demo" / "records" / "agent-result-validation.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_memory_records(root: Path) -> list[dict[str, object]]:
    path = root / ".workflow" / "demo" / "records" / "memory.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_worktree_manifest(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "worktrees" / "manifest.json").read_text(encoding="utf-8"))


def parse_merge_gate(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "merge-gate.json").read_text(encoding="utf-8"))


def parse_merge_apply(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "merge-apply.json").read_text(encoding="utf-8"))


def parse_integration_gate(root: Path) -> dict[str, object]:
    return json.loads((root / ".workflow" / "demo" / "integration-test-gate.json").read_text(encoding="utf-8"))


def history_event_count(root: Path) -> int:
    path = root / ".workflow" / "demo" / "history.md"
    if not path.exists():
        return 0
    return path.read_text(encoding="utf-8").count("## Event ")


def node_status(root: Path, node_id: str) -> str:
    for node in parse_dag(root).get("nodes", []):
        if isinstance(node, dict) and node.get("id") == node_id:
            return str(node.get("status") or "")
    return ""


def seed_state(root: Path, stage: str = "implementation", active: str = "") -> None:
    write(
        root / ".workflow" / "demo" / "state.md",
        f"""
        # State

        - Current stage: {stage}
        - Human gate status: approved
        - Blocked reason:
        - Rework target:
        - Rejection reason:
        - Approval note:
        - Active items: {active}
        - Deferred items:
        - Item note:
        - Challenge note:
        - Next action:
        """,
    )


def seed_three_story_graph(root: Path, active: str = "") -> None:
    seed_state(root, active=active)
    write(
        root / ".workflow" / "demo" / "stories.md",
        """
        # Stories

        ## Story 1: Foundation

        Depends on: -

        ## Story 2: API

        Depends on: Story 1

        ## Story 3: UI

        Depends on: Story 1
        """,
    )
    write(root / ".workflow" / "demo" / "story-1.md", "# Story 1\n\n## Allowed Write Paths\n- src/foundation")
    write(root / ".workflow" / "demo" / "story-2.md", "# Story 2\n\n## Allowed Write Paths\n- src/api")
    write(root / ".workflow" / "demo" / "story-3.md", "# Story 3\n\n## Allowed Write Paths\n- src/ui")


def mark_story_one_done(root: Path) -> None:
    write(
        root / ".workflow" / "demo" / "history.md",
        """
        # History

        ## Event 001
        - Timestamp: 2026-05-12T12:00:00Z
        - Command: approve
        - From stage: release-planning
        - To stage: done
        - Gate: approved
        - Focus items: Story 1
        - Active items: Story 1
        - Deferred items:
        - Approval note:
        - Rejection reason:
        - Blocked reason:
        - Next action:
        """,
    )


def commit_worktree_file(worktree: Path, relative_path: str, text: str) -> None:
    write(worktree / relative_path, text)
    run_cmd(["git", "add", relative_path], worktree)
    run_cmd(["git", "commit", "-m", f"change {relative_path}"], worktree)


def commit_repo_file(root: Path, relative_path: str, text: str) -> None:
    write(root / relative_path, text)
    run_cmd(["git", "add", relative_path], root)
    run_cmd(["git", "commit", "-m", f"add {relative_path}"], root)


def write_integration_allowlist(root: Path, tests: list[dict[str, object]]) -> None:
    path = root / ".workflow" / "demo" / "integration-test-allowlist.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "workflow_slug": "demo",
                "tests": tests,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def test_team_run_requires_dag() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-no-dag-") as tmp:
        root = Path(tmp)
        seed_state(root, active="Story 1")
        run_workflow(root, "team-run")
        state = parse_state(root)
        assert state["Human gate status"] == "blocked"
        assert state["Blocked reason"].startswith("Story DAG ")


def test_execution_path_routes_simple_and_flagged_stories() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-execution-path-") as tmp:
        root = Path(tmp)
        seed_state(root, active="Story 1")
        write(
            root / ".workflow" / "demo" / "stories.md",
            """
            # Stories

            ## Story 1: Copy update

            Depends on: -

            ## Story 2: Auth API boundary

            Depends on: Story 1
            """,
        )
        write(
            root / ".workflow" / "demo" / "story-1.md",
            """
            # Story 1

            ## Acceptance Criteria
            - Update the README wording.

            ## Allowed Write Paths
            - README.md
            """,
        )
        write(
            root / ".workflow" / "demo" / "story-2.md",
            """
            # Story 2

            ## Acceptance Criteria
            - Add the auth API boundary.

            ## Test Expectations
            - Add a boundary test for the auth API contract.

            ## Allowed Write Paths
            - src/auth
            """,
        )

        run_workflow(root, "dag-sync")
        nodes = {node["id"]: node for node in parse_dag(root)["nodes"]}
        assert nodes["story-1"]["execution_path"]["path"] == "simple"
        assert nodes["story-1"]["planner_metadata"]["needs_deeper_qa"] is False
        assert nodes["story-2"]["execution_path"]["path"] == "flagged"
        assert nodes["story-2"]["planner_metadata"]["touches_interfaces"] is True
        assert "risk" in nodes["story-2"]["planner_metadata"]["risk_rationale"]

        seed_state(root, active="Story 2")
        run_workflow(root, "execution-path")
        payload = parse_execution_path(root)
        assert payload["execution_path"]["path"] == "flagged"
        assert "Tech Lead" in payload["execution_path"]["required_roles"]
        assert "Reviewer QA" in payload["execution_path"]["required_roles"]
        markdown = (root / ".workflow" / "demo" / "execution-path.md").read_text(encoding="utf-8")
        assert "flagged QA/reviewer/synthesis path" in markdown


def test_feedback_synth_blocks_flagged_review_until_required_inputs_exist() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-feedback-synth-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        write(
            root / ".workflow" / "demo" / "stories.md",
            """
            # Stories

            ## Story 1: Auth API Boundary

            Depends on: -
            """,
        )
        write(
            root / ".workflow" / "demo" / "story-1.md",
            """
            # Story 1

            ## Acceptance Criteria
            - Add the auth API boundary.

            ## Test Expectations
            - Add a boundary test for the auth API contract.

            ## Allowed Write Paths
            - src/auth
            """,
        )
        run_workflow(root, "dag-sync")
        run_workflow(root, "execution-path")
        assert parse_execution_path(root)["execution_path"]["path"] == "flagged"

        run_workflow(root, "approve")
        state = parse_state(root)
        assert state["Human gate status"] == "blocked"
        assert state["Blocked reason"].startswith("Feedback synthesis is required")

        run_workflow(root, "feedback-synth")
        payload = parse_feedback_synthesis(root)
        assert payload["recommendation"] == "block"
        assert any("Missing required synthesis input" in item for item in payload["blockers"])
        run_workflow(root, "review-sync")
        state = parse_state(root)
        assert state["Human gate status"] == "blocked"
        assert state["Blocked reason"]

        tech_lead_report = textwrap.dedent("""
        Role: Tech Lead
        Status: done
        Verdict: approve
        Summary: architecture and interface boundaries reviewed
        Suggested changes:
        - document a non-blocking follow-up
        Evidence:
        - checked auth API boundary plan
        Findings:
        - none
        Follow-up: Reviewer QA can complete synthesis
        """).strip()
        reviewer_report = textwrap.dedent("""
        Role: Reviewer QA
        Status: done
        Verdict: approve
        Summary: QA review passed
        Evidence:
        - auth boundary test expectations reviewed
        Findings:
        - none
        Follow-up: ready for feedback synthesis
        """).strip()
        product_owner_report = textwrap.dedent("""
        Role: Product Owner
        Status: done
        Verdict: approve
        Summary: product acceptance reviewed
        Evidence:
        - acceptance expectations reviewed
        Findings:
        - none
        Follow-up: ready for release decision
        """).strip()
        run_workflow(root, "team-sync", tech_lead_report)
        run_workflow(root, "team-sync", reviewer_report)
        run_workflow(root, "team-sync", product_owner_report)
        run_workflow(root, "feedback-synth")
        payload = parse_feedback_synthesis(root)
        assert payload["recommendation"] == "approve"
        assert any("Non-blocking suggested changes" in item for item in payload["warnings"])
        markdown = (root / ".workflow" / "demo" / "feedback-synthesis.md").read_text(encoding="utf-8")
        assert "Recommendation: approve" in markdown
        write(
            root / ".workflow" / "demo" / "story-1.md",
            """
            # Story 1

            ## Acceptance Criteria
            - Add the auth API boundary.
            - Document the non-blocking follow-up.

            ## Test Expectations
            - Add a boundary test for the auth API contract.

            ## Allowed Write Paths
            - src/auth
            """,
        )
        run_workflow(root, "review-sync")
        state = parse_state(root)
        assert state["Human gate status"] == "blocked"
        assert state["Blocked reason"].startswith("Feedback synthesis is stale because inputs changed")
        run_workflow(root, "feedback-synth")
        run_workflow(root, "approve")
        state = parse_state(root)
        assert state["Current stage"] == "done"


def test_feedback_synth_ignores_boundary_language_in_approved_risks() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-feedback-synth-boundary-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        write(
            root / ".workflow" / "demo" / "execution-path.json",
            """
            {
              "execution_path": {
                "path": "flagged",
                "synthesis_required": true,
                "required_roles": ["Tech Lead", "Reviewer QA"],
                "optional_roles": []
              }
            }
            """,
        )
        write(
            root / ".workflow" / "demo" / "role-reviews.md",
            """
            # Role Reviews

            | Date | Story | Role | Verdict | Missing Requirements | Incorrect Assumptions | Risks | Questions | Suggested Changes | Evidence | Red-team Notes |
            | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
            | 2026-05-13 | Story 1 | Tech Lead | approve | - | - | Deferred scaffold must stay excluded until later stories reconcile it. | - | - | Runtime scope reviewed. | - |
            | 2026-05-13 | Story 1 | Reviewer QA | approve | - | - | Writes and HTTP remain out of scope for this story. | - | - | Protocol tests passed. | - |
            """,
        )

        run_workflow(root, "feedback-synth")
        payload = parse_feedback_synthesis(root)
        assert payload["recommendation"] == "approve"
        assert payload["status"] == "ready"


def seed_issue_advisor_story(root: Path) -> None:
    seed_state(root, stage="review", active="Story 1")
    write(
        root / ".workflow" / "demo" / "stories.md",
        """
        # Stories

        ## Story 1: Auth API Boundary

        Depends on: -
        """,
    )
    write(
        root / ".workflow" / "demo" / "story-1.md",
        """
        # Story 1

        ## Acceptance Criteria
        - Add the auth API boundary.
        - Preserve existing login behavior.
        - Document the optional audit event.

        ## Test Expectations
        - Add a boundary test for the auth API contract.
        - Run the local smoke suite.

        ## Allowed Write Paths
        - src/auth
        - tests/auth
        """,
    )


def test_issue_advisor_maps_stuck_story_evidence_to_recovery_actions() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-issue-advisor-retry-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        write(
            root / ".workflow" / "demo" / "review-log.md",
            """
            # Review Log

            | Date | Role | Severity | Finding | Resolution |
            | --- | --- | --- | --- | --- |
            | 2026-05-13 | Reviewer QA | high | Story 1: npm test fails on the auth API boundary validation command | open |
            """,
        )
        run_workflow(root, "issue-advisor")
        payload = parse_issue_advisor(root)
        assert payload["action"] == "retry_approach"
        assert payload["failure_category"] == "implementation"
        assert payload["advisor_invocation"] == 1
        assert parse_state(root)["Human gate status"] == "blocked"
        assert "Action: retry_approach" in (root / ".workflow" / "demo" / "issue-advisor.md").read_text(encoding="utf-8")
        assert parse_adaptation_records(root)[-1]["action"] == "retry_approach"

    with tempfile.TemporaryDirectory(prefix="wrkflw-issue-advisor-split-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        write(
            root / ".workflow" / "demo" / "review-log.md",
            """
            # Review Log

            | Date | Role | Severity | Finding | Resolution |
            | --- | --- | --- | --- | --- |
            | 2026-05-13 | Tech Lead | high | Story 1: too broad; split API implementation and audit documentation into separate stories | open |
            """,
        )
        run_workflow(root, "issue-advisor")
        payload = parse_issue_advisor(root)
        assert payload["action"] == "split"
        assert len(payload["sub_stories"]) == 2
        assert parse_state(root)["Next action"].startswith("split the active story")

    with tempfile.TemporaryDirectory(prefix="wrkflw-issue-advisor-replan-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        write(root / ".workflow" / "demo" / "dag-validation.md", "# DAG Validation\n\n- Error: invalid DAG cycle detected\n")
        run_workflow(root, "issue-advisor")
        payload = parse_issue_advisor(root)
        assert payload["action"] == "escalate_to_replan"
        assert payload["failure_category"] == "dependency_or_architecture"


def test_issue_advisor_handles_modified_scope_and_debt_budget() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-issue-advisor-modified-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        write(
            root / ".workflow" / "demo" / "review-log.md",
            """
            # Review Log

            | Date | Role | Severity | Finding | Resolution |
            | --- | --- | --- | --- | --- |
            | 2026-05-13 | Product Owner | high | Story 1: acceptance criteria is too strict; defer optional audit event to a later slice | open |
            """,
        )
        run_workflow(root, "issue-advisor")
        payload = parse_issue_advisor(root)
        assert payload["action"] == "retry_modified"
        assert payload["dropped_criteria"] == ["Document the optional audit event."]

    with tempfile.TemporaryDirectory(prefix="wrkflw-issue-advisor-debt-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        run_workflow(
            root,
            "debt-record",
            "story: Story 1; type: missing functionality; severity: high; summary: optional audit event is still missing; owner: QA",
        )
        run_workflow(root, "issue-advisor")
        assert parse_issue_advisor(root)["action"] == "retry_approach"
        run_workflow(root, "issue-advisor")
        payload = parse_issue_advisor(root)
        assert payload["action"] == "accept_with_debt"
        assert payload["debt_entries"]
        assert parse_adaptation_records(root)[-1]["action"] == "accept_with_debt"


def test_replanner_proposes_and_applies_split_with_history() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-split-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        original_stories = (root / ".workflow" / "demo" / "stories.md").read_text(encoding="utf-8")
        original_story_file = (root / ".workflow" / "demo" / "story-1.md").read_text(encoding="utf-8")
        write(
            root / ".workflow" / "demo" / "review-log.md",
            """
            # Review Log

            | Date | Role | Severity | Finding | Resolution |
            | --- | --- | --- | --- | --- |
            | 2026-05-13 | Tech Lead | high | Story 1: too broad; split API implementation and audit documentation into separate stories | open |
            """,
        )
        run_workflow(root, "issue-advisor")
        run_workflow(root, "replan")
        proposal = parse_replan(root)
        assert proposal["status"] == "proposed"
        assert proposal["action"] == "modify_dag"
        assert proposal["plan_type"] == "split_story"
        assert (root / ".workflow" / "demo" / "stories.md").read_text(encoding="utf-8") == original_stories
        assert (root / ".workflow" / "demo" / "story-1.md").read_text(encoding="utf-8") == original_story_file

        run_workflow(root, "replan", "confirm: replan")
        applied = parse_replan(root)
        state = parse_state(root)
        stories_text = (root / ".workflow" / "demo" / "stories.md").read_text(encoding="utf-8")
        assert applied["status"] == "applied"
        assert state["Current stage"] == "story-slicing"
        assert state["Active items"] == "Story 2"
        assert "Story 1" in state["Deferred items"]
        assert "## Story 2:" in stories_text
        assert "## Story 3:" in stories_text
        assert "Replanned from: Story 1" in stories_text
        assert (root / ".workflow" / "demo" / "story-2.md").exists()
        assert parse_replan_records(root)[-1]["status"] == "applied"
        assert applied["archive_path"]
        assert (root / applied["archive_path"] / "stories.md").exists()
        assert node_status(root, "story-1") == "deferred"
        assert node_status(root, "story-2") == "active"


def test_replanner_blocks_stale_apply_without_overwriting_edits() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-stale-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        write(
            root / ".workflow" / "demo" / "review-log.md",
            """
            # Review Log

            | Date | Role | Severity | Finding | Resolution |
            | --- | --- | --- | --- | --- |
            | 2026-05-13 | Tech Lead | high | Story 1: too broad; split API implementation and audit documentation into separate stories | open |
            """,
        )
        run_workflow(root, "issue-advisor")
        run_workflow(root, "replan")
        story_path = root / ".workflow" / "demo" / "story-1.md"
        human_edit = story_path.read_text(encoding="utf-8") + "\n## Human Edit\nKeep this section.\n"
        story_path.write_text(human_edit, encoding="utf-8")

        run_workflow(root, "replan", "confirm: replan")
        payload = parse_replan(root)
        assert payload["status"] == "blocked"
        assert "stale" in payload["blockers"][0]
        assert story_path.read_text(encoding="utf-8") == human_edit
        assert "## Story 2:" not in (root / ".workflow" / "demo" / "stories.md").read_text(encoding="utf-8")


def test_replanner_applies_modified_acceptance_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-modified-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        write(
            root / ".workflow" / "demo" / "review-log.md",
            """
            # Review Log

            | Date | Role | Severity | Finding | Resolution |
            | --- | --- | --- | --- | --- |
            | 2026-05-13 | Product Owner | high | Story 1: acceptance criteria is too strict; defer optional audit event to a later slice | open |
            """,
        )
        run_workflow(root, "issue-advisor")
        run_workflow(root, "replan")
        assert parse_replan(root)["plan_type"] == "modify_acceptance"
        run_workflow(root, "replan", "confirm: replan")
        payload = parse_replan(root)
        story_text = (root / ".workflow" / "demo" / "story-1.md").read_text(encoding="utf-8")
        state = parse_state(root)
        assert payload["status"] == "applied"
        assert state["Current stage"] == "story-enrichment"
        assert "Document the optional audit event." not in story_text.split("## Test Expectations", 1)[0]
        assert "Dropped criteria: Document the optional audit event." in story_text


def test_replanner_applies_skip_story_and_dag_marks_deferred() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-skip-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        run_workflow(root, "dag-sync")
        assert node_status(root, "story-3") == "ready"

        run_workflow(root, "replan", "skip: Story 3")
        assert parse_replan(root)["plan_type"] == "runtime_plan_mutation"
        run_workflow(root, "replan", "confirm: replan")

        payload = parse_replan(root)
        state = parse_state(root)
        assert payload["status"] == "applied"
        assert "Story 3" in state["Deferred items"]
        assert node_status(root, "story-3") == "deferred"


def test_replanner_applies_dependency_rewrite_and_blocks_dependent_until_new_parent_done() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-dependency-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        run_workflow(root, "dag-sync")
        assert node_status(root, "story-3") == "ready"

        run_workflow(root, "replan", "depends: Story 3 -> Story 2")
        run_workflow(root, "replan", "confirm: replan")

        stories_text = (root / ".workflow" / "demo" / "stories.md").read_text(encoding="utf-8")
        story_three_block = stories_text.split("## Story 3", 1)[1]
        assert "Depends on: Story 2" in story_three_block
        assert node_status(root, "story-3") == "blocked"
        dag = parse_dag(root)
        story_three = next(node for node in dag["nodes"] if node["id"] == "story-3")
        assert "story-2" in story_three["blocked_by_stories"]


def test_replanner_applies_remaining_order_without_touching_completed_history() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-order-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        run_workflow(root, "dag-sync")

        run_workflow(root, "replan", "order: Story 3, Story 2, Story 1")
        run_workflow(root, "replan", "confirm: replan")

        stories_text = (root / ".workflow" / "demo" / "stories.md").read_text(encoding="utf-8")
        assert stories_text.index("## Story 1") < stories_text.index("## Story 3") < stories_text.index("## Story 2")
        assert "To stage: done" in (root / ".workflow" / "demo" / "history.md").read_text(encoding="utf-8")
        assert parse_replan(root)["status"] == "applied"


def test_replanner_removes_leaf_story_without_dangling_dependencies() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-remove-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        run_workflow(root, "dag-sync")

        run_workflow(root, "replan", "remove: Story 3")
        run_workflow(root, "replan", "confirm: replan")

        payload = parse_replan(root)
        stories_text = (root / ".workflow" / "demo" / "stories.md").read_text(encoding="utf-8")
        dag = parse_dag(root)
        assert payload["status"] == "applied"
        assert "## Story 3" not in stories_text
        assert all(node["id"] != "story-3" for node in dag["nodes"])


def test_replanner_blocks_remove_that_creates_dangling_dependency() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-remove-dangling-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        run_workflow(root, "dag-sync")
        run_workflow(root, "replan", "depends: Story 3 -> Story 2")
        run_workflow(root, "replan", "confirm: replan")
        assert parse_replan(root)["status"] == "applied"

        run_workflow(root, "replan", "remove: Story 2")
        run_workflow(root, "replan", "confirm: replan")

        payload = parse_replan(root)
        state = parse_state(root)
        stories_text = (root / ".workflow" / "demo" / "stories.md").read_text(encoding="utf-8")
        assert payload["status"] == "blocked"
        assert any("depending on removed story" in blocker for blocker in payload["blockers"])
        assert "## Story 2" in stories_text
        assert state["Human gate status"] == "blocked"


def test_replanner_blocks_completed_story_mutation() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-completed-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        run_workflow(root, "dag-sync")

        run_workflow(root, "replan", "skip: Story 1")
        run_workflow(root, "replan", "confirm: replan")

        payload = parse_replan(root)
        state = parse_state(root)
        assert payload["status"] == "blocked"
        assert any("already completed" in blocker for blocker in payload["blockers"])
        assert "Story 1" not in state["Deferred items"]


def test_replanner_blocks_split_apply_after_story_completed() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-completed-split-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        write(
            root / ".workflow" / "demo" / "review-log.md",
            """
            # Review Log

            | Date | Role | Severity | Finding | Resolution |
            | --- | --- | --- | --- | --- |
            | 2026-05-13 | Tech Lead | high | Story 1: too broad; split API implementation and audit documentation into separate stories | open |
            """,
        )
        run_workflow(root, "issue-advisor")
        run_workflow(root, "replan")
        mark_story_one_done(root)

        run_workflow(root, "replan", "confirm: replan")

        payload = parse_replan(root)
        stories_text = (root / ".workflow" / "demo" / "stories.md").read_text(encoding="utf-8")
        assert payload["status"] == "blocked"
        assert any("completed history is immutable" in blocker for blocker in payload["blockers"])
        assert "## Story 2:" not in stories_text


def test_replanner_blocks_modified_acceptance_apply_after_story_completed() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-replan-completed-modified-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        write(
            root / ".workflow" / "demo" / "review-log.md",
            """
            # Review Log

            | Date | Role | Severity | Finding | Resolution |
            | --- | --- | --- | --- | --- |
            | 2026-05-13 | Product Owner | high | Story 1: acceptance criteria is too strict; defer optional audit event to a later slice | open |
            """,
        )
        run_workflow(root, "issue-advisor")
        run_workflow(root, "replan")
        mark_story_one_done(root)
        story_text_before = (root / ".workflow" / "demo" / "story-1.md").read_text(encoding="utf-8")

        run_workflow(root, "replan", "confirm: replan")

        payload = parse_replan(root)
        assert payload["status"] == "blocked"
        assert any("completed history is immutable" in blocker for blocker in payload["blockers"])
        assert (root / ".workflow" / "demo" / "story-1.md").read_text(encoding="utf-8") == story_text_before


def test_verify_fix_generates_fix_tasks_and_accepts_pass_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-verify-fix-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        write(
            root / ".workflow" / "demo" / "story-1.md",
            """
            # Story 1

            ## Acceptance Criteria
            - API returns the saved user profile.
            - Invalid profile payloads show validation errors.
            """,
        )

        run_workflow(root, "verify-fix")
        payload = parse_verify_fix(root)
        state = parse_state(root)
        assert payload["status"] == "fix_required"
        assert len(payload["fix_tasks"]) == 2
        assert state["Human gate status"] == "blocked"
        assert state["Blocked reason"].startswith("Verify-fix recommends")
        run_workflow(root, "review-sync")

        run_workflow(root, "verify-fix", "pass: all; evidence: local profile tests passed")
        payload = parse_verify_fix(root)
        state = parse_state(root)
        assert payload["status"] == "ready"
        assert payload["fix_tasks"] == []
        assert state["Blocked reason"] == ""
        run_workflow(root, "review-sync")
        state = parse_state(root)
        assert state["Human gate status"] == "pending"
        assert not state["Blocked reason"].startswith("Verify-fix is stale")
        records = root / ".workflow" / "demo" / "records" / "verify-fix.jsonl"
        assert '"status": "ready"' in records.read_text(encoding="utf-8")


def test_verify_fix_blocks_review_sync_when_stale() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-verify-fix-stale-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        write(
            root / ".workflow" / "demo" / "story-1.md",
            """
            # Story 1

            ## Acceptance Criteria
            - API returns the saved user profile.
            """,
        )
        run_workflow(root, "verify-fix", "pass: all; evidence: local profile tests passed")
        assert parse_verify_fix(root)["status"] == "ready"

        write(
            root / ".workflow" / "demo" / "story-1.md",
            """
            # Story 1

            ## Acceptance Criteria
            - API returns the saved user profile.
            - Profile updates are persisted after refresh.
            """,
        )
        run_workflow(root, "review-sync")
        state = parse_state(root)
        assert state["Human gate status"] == "blocked"
        assert state["Blocked reason"].startswith("Verify-fix is stale because")


def test_verify_fix_feeds_feedback_synth_and_issue_advisor() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-verify-fix-feedback-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        write(
            root / ".workflow" / "demo" / "story-1.md",
            """
            # Story 1

            ## Acceptance Criteria
            - API returns the saved user profile.
            """,
        )
        run_workflow(root, "verify-fix", "fail: 1; evidence: profile endpoint still returns 404")
        assert parse_verify_fix(root)["status"] == "fix_required"
        run_workflow(root, "feedback-synth")
        synthesis = parse_feedback_synthesis(root)
        assert synthesis["recommendation"] == "fix"
        assert any("verify-fix" in blocker for blocker in synthesis["blockers"])

        run_workflow(root, "issue-advisor")
        advisor = parse_issue_advisor(root)
        assert advisor["inputs"]["verify_fix_task_count"] == 1
        assert any("verify-fix" in item for item in advisor["evidence"])


def test_ci_feedback_records_failed_and_passed_checks() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-ci-feedback-record-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        init_git_repo(root)

        run_workflow(
            root,
            "ci-feedback",
            "status: failed; check: unit tests; failure: unit tests failed on profile endpoint; provider: github; url: https://ci.example/run/1",
        )
        payload = parse_ci_feedback(root)
        state = parse_state(root)
        assert payload["status"] == "action_required"
        assert payload["provider"] == "github"
        assert len(payload["fix_tasks"]) == 1
        assert (root / payload["run_result_path"]).exists()
        assert state["Human gate status"] == "blocked"
        assert state["Blocked reason"].startswith("CI feedback requires fixes")
        records = root / ".workflow" / "demo" / "records" / "ci-feedback.jsonl"
        assert '"check_status": "failed"' in records.read_text(encoding="utf-8")

        run_workflow(
            root,
            "ci-feedback",
            "status: passed; check: unit tests; provider: github; url: https://ci.example/run/2",
        )
        payload = parse_ci_feedback(root)
        state = parse_state(root)
        assert payload["status"] == "ready"
        assert payload["fix_tasks"] == []
        assert state["Blocked reason"] == ""


def test_ci_failure_class_promotes_to_feedback_synth_and_issue_advisor() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-failure-class-ci-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        init_git_repo(root)

        run_workflow(
            root,
            "ci-feedback",
            "status: failed; check: unit tests; failure: pytest failed on profile endpoint; provider: github",
        )
        ci = parse_ci_feedback(root)
        assert ci["failure_class"] == "test_failure"
        assert ci["failure_category"] == "implementation"

        run_workflow(root, "feedback-synth")
        synthesis = parse_feedback_synthesis(root)
        assert synthesis["failure_class"] == "test_failure"
        assert synthesis["recommendation"] == "fix"

        run_workflow(root, "issue-advisor")
        advisor = parse_issue_advisor(root)
        assert advisor["failure_class"] == "test_failure"
        assert advisor["failure_category"] == "implementation"
        assert advisor["inputs"]["top_failure_class"] == "test_failure"


def test_ci_timeout_and_pending_failure_classification() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-failure-class-ci-states-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        init_git_repo(root)

        run_workflow(root, "ci-feedback", "status: timeout; check: e2e; failure: command timed out; provider: github")
        timeout_payload = parse_ci_feedback(root)
        assert timeout_payload["failure_class"] == "ci_timeout"
        assert timeout_payload["failure_category"] == "environment_failure"
        assert timeout_payload["recommended_gate"] == "block"

        run_workflow(root, "ci-feedback", "status: pending; check: required checks; failure: required checks are still pending; provider: github")
        pending_payload = parse_ci_feedback(root)
        assert pending_payload["failure_class"] == "ci_missing_or_pending"
        assert pending_payload["failure_category"] == "insufficient_evidence"
        assert pending_payload["recommended_gate"] == "block"


def test_ci_feedback_blocks_review_sync_when_stale_head() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-ci-feedback-stale-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        init_git_repo(root)
        run_workflow(root, "ci-feedback", "status: passed; check: unit tests; provider: github")
        assert parse_ci_feedback(root)["status"] == "ready"

        commit_repo_file(root, "src/profile/change.txt", "new code after CI")
        run_workflow(root, "review-sync")
        state = parse_state(root)
        assert state["Human gate status"] == "blocked"
        assert state["Blocked reason"].startswith("CI feedback is stale because repository HEAD changed")


def test_ci_feedback_feeds_feedback_synth_and_issue_advisor() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-ci-feedback-downstream-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        init_git_repo(root)
        run_workflow(
            root,
            "ci-feedback",
            "status: failed; check: unit tests; failure: unit tests failed on profile endpoint; provider: github",
        )

        run_workflow(root, "feedback-synth")
        synthesis = parse_feedback_synthesis(root)
        assert synthesis["recommendation"] == "fix"
        assert any("CI feedback" in blocker for blocker in synthesis["blockers"])

        run_workflow(root, "issue-advisor")
        advisor = parse_issue_advisor(root)
        assert advisor["inputs"]["ci_fix_task_count"] == 1
        assert any("CI feedback" in item for item in advisor["evidence"])


def test_ci_feedback_contributes_to_verify_fix_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-ci-feedback-verify-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        write(
            root / ".workflow" / "demo" / "story-1.md",
            """
            # Story 1

            ## Acceptance Criteria
            - Unit tests pass in CI.
            """,
        )
        init_git_repo(root)
        run_workflow(root, "ci-feedback", "status: passed; check: unit tests; provider: github")
        run_workflow(root, "verify-fix")
        payload = parse_verify_fix(root)
        assert payload["status"] == "ready"
        assert payload["ci_feedback_status"] == "ready"
        assert payload["criteria"][0]["status"] == "passed"


def test_integration_timeout_classifies_environment_failure() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-failure-class-integration-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        init_git_repo(root)
        head = run_cmd(["git", "rev-parse", "HEAD"], root).stdout.strip()
        write(
            root / ".workflow" / "demo" / "merge-gate.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "workflow_slug": "demo",
                    "status": "ready",
                    "current_head": head,
                    "entries": [],
                    "blockers": [],
                },
                indent=2,
            ),
        )
        run_workflow(root, "integration-gate", "status: timeout; command: integration smoke; evidence: command timed out")
        gate = parse_integration_gate(root)
        assert gate["status"] == "blocked"
        assert gate["failure_class"] == "environment_failure"
        assert gate["failure_category"] == "environment_failure"


def test_integration_output_redaction_removes_auth_secret_values() -> None:
    raw = "\n".join(
        [
            "Authorization: Bearer abc.def.ghi",
            "api_key=secret-value",
            "token: visible-token",
            "safe line",
        ]
    )
    redacted = redact_output(raw)
    assert "abc.def.ghi" not in redacted
    assert "secret-value" not in redacted
    assert "visible-token" not in redacted
    assert "Authorization: <redacted>" in redacted
    assert "api_key=<redacted>" in redacted
    assert "token: <redacted>" in redacted
    assert "safe line" in redacted


def test_feedback_synth_replans_on_dependency_failure_class() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-failure-class-replan-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="review", active="Story 1")
        write(
            root / ".workflow" / "demo" / "ci-feedback.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "workflow_slug": "demo",
                    "active_story": "Story 1",
                    "status": "action_required",
                    "summary": "dependency graph is stale",
                    "failure_class": "dependency_block",
                    "failure_category": "dependency_or_architecture",
                    "failure_classification": {
                        "failure_class": "dependency_block",
                        "failure_category": "dependency_or_architecture",
                        "source": "ci-feedback",
                        "summary": "dependency graph is stale",
                        "retryable": False,
                        "recommended_gate": "replan",
                    },
                    "input_hashes": {
                        "merge-gate.json": "",
                        "merge-apply.json": "",
                        "integration-test-gate.json": "",
                    },
                },
                indent=2,
            ),
        )
        run_workflow(root, "feedback-synth")
        synthesis = parse_feedback_synthesis(root)
        assert synthesis["recommendation"] == "replan"
        assert synthesis["failure_class"] == "dependency_block"


def test_accounting_record_writes_jsonl_and_summary() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-accounting-record-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="implementation", active="Story 1")
        run_workflow(
            root,
            "accounting-record",
            "story: Story 1; role: Implementer 1; model: gpt-test; input-tokens: 1200; output-tokens: 300; cost: 0.25; elapsed-seconds: 42; summary: delegated run completed",
        )
        records = parse_invocation_records(root)
        manual = [record for record in records if record["kind"] == "agent-run"]
        assert len(manual) == 1
        assert manual[0]["cost_known"] is True
        assert manual[0]["estimated_cost_usd"] == 0.25
        assert manual[0]["input_tokens"] == 1200
        assert any(record["kind"] == "workflow-command" and record["command"] == "accounting-record" for record in records)
        summary = parse_accounting(root)
        assert summary["totals"]["invocation_count"] == len(records)
        assert summary["totals"]["estimated_cost_usd"] == 0.25
        markdown = (root / ".workflow" / "demo" / "accounting.md").read_text(encoding="utf-8")
        assert "$0.25" in markdown


def test_successful_command_invocation_is_recorded_once() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-accounting-command-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 1")
        run_workflow(root, "dag-sync")
        records = parse_invocation_records(root)
        command_records = [record for record in records if record["kind"] == "workflow-command" and record["command"] == "dag-sync"]
        assert len(command_records) == 1
        assert command_records[0]["source"] == "workflow-command"
        assert command_records[0]["cost_known"] is True
        assert command_records[0]["estimated_cost_usd"] == 0.0


def test_failed_checkpoint_resume_does_not_break_accounting() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-accounting-resume-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root)
        failed = run_workflow(
            root,
            "dag-sync",
            env={"WRKFLW_FAIL_AFTER_CHECKPOINT": "command"},
            check=False,
        )
        assert failed.returncode == 1
        assert not (root / ".workflow" / "demo" / "records" / "invocations.jsonl").exists()

        run_workflow(root, "resume")
        records = parse_invocation_records(root)
        resume_records = [record for record in records if record["source"] == "workflow-resume" and record["command"] == "dag-sync"]
        assert len(resume_records) == 1
        assert resume_records[0]["avoided_rework"] is True


def test_issue_advisor_records_retry_invocation() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-accounting-advisor-") as tmp:
        root = Path(tmp)
        seed_issue_advisor_story(root)
        run_workflow(root, "dag-sync")
        write(
            root / ".workflow" / "demo" / "review-log.md",
            """
            # Review Log

            | Date | Role | Severity | Finding | Resolution |
            | --- | --- | --- | --- | --- |
            | 2026-05-13 | Reviewer QA | high | Story 1: npm test fails on the auth API boundary validation command | open |
            """,
        )
        run_workflow(root, "issue-advisor")
        records = parse_invocation_records(root)
        advisor_records = [record for record in records if record["command"] == "issue-advisor"]
        assert len(advisor_records) == 1
        assert advisor_records[0]["retry"] is True
        advisor = parse_issue_advisor(root)
        assert "accounting_summary" in advisor["inputs"]


def test_completion_requires_history_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-completion-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        run_workflow(root, "dag-sync")
        assert node_status(root, "story-1") == "ready"
        assert node_status(root, "story-2") == "blocked"

        mark_story_one_done(root)
        run_workflow(root, "dag-sync")
        assert node_status(root, "story-1") == "completed"
        assert node_status(root, "story-2") == "active"


def test_shared_learning_memory_records_and_propagates() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-memory-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        run_workflow(root, "dag-sync")
        run_workflow(
            root,
            "memory-record",
            "category: validated-test-command; story: Story 2; command: npm test; result: passed; summary: npm test is the local smoke command; evidence: local run",
        )
        records = parse_memory_records(root)
        assert len(records) == 1
        assert records[0]["category"] == "validated-test-command"
        assert records[0]["command"] == "npm test"
        memory_md = (root / ".workflow" / "demo" / "memory.md").read_text(encoding="utf-8")
        assert "npm test is the local smoke command" in memory_md
        plan = (root / ".workflow" / "demo" / "implementation-plan.md").read_text(encoding="utf-8")
        assert "## Shared Learning Memory" in plan
        assert "npm test is the local smoke command" in plan

        reviewer_report = textwrap.dedent("""
        Role: Reviewer QA
        Status: done
        Verdict: approve
        Summary: reviewed reusable API boundary learning
        Evidence:
        - review pass
        Findings:
        - none
        Memory entries:
        - category: interface-note; story: Story 2; summary: API handlers should keep auth boundary checks in src/api; evidence: review pass; tags: api, auth
        Follow-up: ready for dispatch
        """).strip()
        run_workflow(root, "team-sync", reviewer_report)
        records = parse_memory_records(root)
        assert any(record["category"] == "interface-note" for record in records)

        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-memory-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "assign", "Implementer 1 ownership: src/api", env=env)
            run_workflow(root, "team-run", env=env)
            packet = (root / ".workflow" / "demo" / "dispatch" / "implementer-1.md").read_text(encoding="utf-8")
            assert "## Shared Learning Memory" in packet
            assert "API handlers should keep auth boundary checks" in packet
            assert "Memory entries:" in packet

        run_cmd(["python3", str(REPO_ROOT / "scripts" / "generate_story_enrichment.py"), "--slug", "demo", "--root", str(root)], REPO_ROOT)
        story = (root / ".workflow" / "demo" / "story-2.md").read_text(encoding="utf-8")
        assert "## Shared Learning Memory" in story
        assert "npm test is the local smoke command" in story


def test_parallel_dispatch_cleans_stale_packets() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-parallel-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-parallel-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            packet_root = root / ".workflow" / "demo" / "parallel-dispatch"
            assert (packet_root / "story-2" / "implementer.md").exists()
            assert (packet_root / "story-3" / "implementer.md").exists()
            manifest = parse_worktree_manifest(root)
            entries = manifest.get("entries", [])
            assert manifest["status"] == "ready"
            assert len(entries) == 2
            first_paths = sorted((entry["branch"], entry["path"]) for entry in entries)

            run_workflow(root, "team-run-level", env=env)
            manifest = parse_worktree_manifest(root)
            second_paths = sorted((entry["branch"], entry["path"]) for entry in manifest.get("entries", []))
            assert second_paths == first_paths

            write(root / ".workflow" / "demo" / "story-3.md", "# Story 3\n\n## Allowed Write Paths\n- src/api/sub")
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            state = parse_state(root)
            assert state["Human gate status"] == "blocked"
            assert not list(packet_root.glob("*/implementer.md"))


def test_parallel_worktree_isolation_blocks_without_git() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-parallel-no-git-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        run_workflow(root, "dag-sync")
        run_workflow(root, "team-run-level")
        state = parse_state(root)
        assert state["Human gate status"] == "blocked"
        assert state["Blocked reason"].startswith("Git worktree isolation is blocked")
        assert not (root / ".workflow" / "demo" / "worktrees" / "manifest.json").exists() or parse_worktree_manifest(root)["status"] == "blocked"


def test_team_run_prepares_active_story_worktrees() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-team-run-worktrees-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-team-run-worktree-root-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "staff", "parallel slots: 2", env=env)
            run_workflow(root, "assign", "Implementer 1 ownership: src/api; Implementer 2 ownership: src/ui", env=env)
            run_workflow(root, "team-run", env=env)

            manifest = parse_worktree_manifest(root)
            entries = manifest.get("entries", [])
            assert manifest["status"] == "ready"
            assert manifest["command"] == "team-run"
            assert manifest["active_story"] == "Story 2"
            assert len(entries) == 2
            assert {entry["owner"] for entry in entries} == {"Implementer 1", "Implementer 2"}
            packet = root / ".workflow" / "demo" / "dispatch" / "implementer-1.md"
            assert "Worktree path:" in packet.read_text(encoding="utf-8")


def test_team_run_records_dispatch_without_fake_model_cost() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-accounting-team-run-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-team-run-worktree-root-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "assign", "Implementer 1 ownership: src/api", env=env)
            run_workflow(root, "team-run", env=env)
            records = parse_invocation_records(root)
            team_run_records = [record for record in records if record["kind"] == "workflow-command" and record["command"] == "team-run"]
            delegated_records = [record for record in records if record["kind"] == "delegated-agent"]
            assert len(team_run_records) == 1
            assert team_run_records[0]["cost_source"] == "workflow-control"
            assert team_run_records[0]["estimated_cost_usd"] == 0.0
            assert delegated_records == []


def test_team_run_blocks_dirty_checkout_overlap() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-team-run-dirty-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-team-run-worktree-root-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "assign", "Implementer 1 ownership: src/api", env=env)
            write(root / "src" / "api" / "dirty.txt", "uncommitted local change")
            run_workflow(root, "team-run", env=env)
            state = parse_state(root)
            manifest = parse_worktree_manifest(root)
            assert state["Human gate status"] == "blocked"
            assert "inside active role scope" in state["Blocked reason"]
            assert manifest["status"] == "blocked"


def valid_agent_result_report(role: str = "Implementer 1", status: str = "done") -> str:
    return textwrap.dedent(
        f"""
        Schema: agent-result-v1
        Role: {role}
        Status: {status}
        Verdict: approve
        Summary: validated strict schema report
        Files changed:
        - none
        Validation run:
        - not run
        Missing requirements:
        - none
        Incorrect assumptions:
        - none
        Risks:
        - none
        Questions:
        - none
        Suggested changes:
        - none
        Evidence:
        - schema validation smoke test
        Conflict entries:
        - none
        Assumption updates:
        - none
        Red-team notes:
        - none
        Findings:
        - none
        Debt entries:
        - none
        Memory entries:
        - none
        Follow-up: ready for next gate
        """
    ).strip()


def valid_agent_result_report_with_usage(role: str = "Implementer 1", status: str = "done") -> str:
    return valid_agent_result_report(role, status).replace(
        "Follow-up: ready for next gate",
        "\n".join(
            [
                "Model: gpt-test",
                "Input tokens: 2000",
                "Output tokens: 500",
                "Cost USD: 0.75",
                "Elapsed seconds: 90",
                "Invocation ID: inv-123",
                "Run ID: run-456",
                "Retry count: 1",
                "Follow-up: ready for next gate",
            ]
        ),
    )


def test_strict_agent_result_schema_validates_direct_report() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-agent-schema-direct-") as tmp:
        root = Path(tmp)
        seed_state(root, active="Story 1")
        run_workflow(root, "team-sync", valid_agent_result_report("Reviewer QA"))
        state = parse_state(root)
        records = parse_agent_result_validation_records(root)
        assert state["Item note"] == "Reviewer QA marked done"
        assert records[-1]["status"] == "valid"
        assert (root / ".workflow" / "demo" / "schemas" / "agent-result.schema.json").exists()


def test_team_sync_ingests_agent_usage_from_result_envelope() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-accounting-team-sync-") as tmp:
        root = Path(tmp)
        seed_state(root, active="Story 1")
        run_workflow(root, "team-sync", valid_agent_result_report_with_usage("Implementer 1"))
        records = parse_invocation_records(root)
        delegated = [record for record in records if record["kind"] == "delegated-agent"]
        assert len(delegated) == 1
        assert delegated[0]["role"] == "Implementer 1"
        assert delegated[0]["model"] == "gpt-test"
        assert delegated[0]["estimated_cost_usd"] == 0.75
        assert delegated[0]["retry"] is True
        assert delegated[0]["execution_id"] == "inv-123"


def test_team_sync_all_ingests_worktree_result_envelope() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-team-run-result-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-team-run-worktree-root-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "assign", "Implementer 1 ownership: src/api", env=env)
            run_workflow(root, "team-run", env=env)
            entry = parse_worktree_manifest(root)["entries"][0]
            result_path = Path(entry["path"]) / ".workflow" / "demo" / "agent-results" / "implementer-1.md"
            write(
                result_path,
                """
                Schema: agent-result-v1
                Role: Implementer 1
                Status: done
                Verdict: approve
                Summary: implemented from active story worktree
                Files changed:
                - none
                Validation run:
                - not run
                Missing requirements:
                - none
                Incorrect assumptions:
                - none
                Risks:
                - none
                Questions:
                - none
                Suggested changes:
                - none
                Evidence:
                - worktree result envelope
                Conflict entries:
                - none
                Assumption updates:
                - none
                Red-team notes:
                - none
                Findings:
                - none
                Debt entries:
                - none
                Memory entries:
                - none
                Follow-up: ready for merge-gate
                """,
            )
            run_workflow(root, "team-sync-all", env=env)
            ledger = (root / ".workflow" / "demo" / "agent-sync-ledger.md").read_text(encoding="utf-8")
            assert "implementer-1.md" in ledger
            run_workflow(root, "merge-gate", env=env)
            assert parse_merge_gate(root)["status"] == "ready"


def test_team_sync_all_does_not_duplicate_synced_usage_records() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-accounting-team-sync-all-") as tmp:
        root = Path(tmp)
        seed_state(root, active="Story 1")
        result_path = root / ".workflow" / "demo" / "agent-results" / "implementer-usage.md"
        write(result_path, valid_agent_result_report_with_usage("Implementer 1"))
        run_workflow(root, "team-sync-all")
        run_workflow(root, "team-sync-all")
        records = parse_invocation_records(root)
        delegated = [record for record in records if record["kind"] == "delegated-agent"]
        assert len(delegated) == 1
        assert delegated[0]["estimated_cost_usd"] == 0.75


def test_team_sync_all_resume_uses_envelope_checkpoint_without_duplicate_usage() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-team-sync-all-resume-") as tmp:
        root = Path(tmp)
        seed_state(root, active="Story 1")
        result_one = root / ".workflow" / "demo" / "agent-results" / "implementer-usage.md"
        result_two = root / ".workflow" / "demo" / "agent-results" / "reviewer-usage.md"
        write(
            result_one,
            valid_agent_result_report_with_usage("Implementer 1")
            .replace("Invocation ID: inv-123", "Invocation ID: inv-implementer")
            .replace("Run ID: run-456", "Run ID: run-implementer"),
        )
        write(
            result_two,
            valid_agent_result_report_with_usage("Reviewer QA")
            .replace("Invocation ID: inv-123", "Invocation ID: inv-reviewer")
            .replace("Run ID: run-456", "Run ID: run-reviewer"),
        )

        failed = run_workflow(
            root,
            "team-sync-all",
            env={"WRKFLW_FAIL_AFTER_TEAM_SYNC_ENVELOPES": "1"},
            check=False,
        )
        assert failed.returncode == 1
        assert not (root / ".workflow" / "demo" / "records" / "invocations.jsonl").exists()

        resumed = run_workflow(root, "resume")
        assert resumed.returncode == 0
        ledger = (root / ".workflow" / "demo" / "agent-sync-ledger.md").read_text(encoding="utf-8")
        assert "implementer-usage.md" in ledger
        assert "reviewer-usage.md" in ledger

        records = parse_invocation_records(root)
        delegated = [record for record in records if record["kind"] == "delegated-agent"]
        assert len(delegated) == 2
        assert {record["execution_id"] for record in delegated} == {"inv-implementer", "inv-reviewer"}
        resume_records = [record for record in records if record["source"] == "workflow-resume" and record["command"] == "team-sync-all"]
        assert len(resume_records) == 1
        assert resume_records[0]["avoided_rework"] is True

        tx_paths = sorted((root / ".workflow" / "_transactions" / "demo").iterdir())
        tx_metadata = json.loads((tx_paths[-1] / "transaction.json").read_text(encoding="utf-8"))
        assert tx_metadata["status"] == "committed"
        assert tx_metadata["latest_command_checkpoint"]["command"] == "team-sync-all"
        assert tx_metadata["latest_command_checkpoint"]["completed_count"] == 2
        assert any(
            entry.get("context", {}).get("completed_count") == 1
            for entry in tx_metadata["command_checkpoint_history"]
        )


def test_team_sync_all_rejects_invalid_result_envelope_before_batch_ingest() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-agent-schema-batch-") as tmp:
        root = Path(tmp)
        seed_state(root, active="Story 1")
        valid_path = root / ".workflow" / "demo" / "agent-results" / "valid.md"
        invalid_path = root / ".workflow" / "demo" / "agent-results" / "invalid.md"
        write(valid_path, valid_agent_result_report("Reviewer QA"))
        write(
            invalid_path,
            """
            Schema: agent-result-v1
            Role: Implementer 1
            Status: done
            Verdict: approve
            Summary: missing required list sections
            Files changed:
            - none
            Follow-up: should not ingest
            """,
        )
        run_workflow(root, "team-sync-all")
        state = parse_state(root)
        ledger = (root / ".workflow" / "demo" / "agent-sync-ledger.md").read_text(encoding="utf-8")
        records = parse_agent_result_validation_records(root)
        assert state["Human gate status"] == "blocked"
        assert "Agent result schema validation failed before batch ingest" in state["Blocked reason"]
        assert "valid.md" not in ledger
        assert records[-1]["status"] == "invalid"


def test_team_run_merge_apply_applies_active_story_branch() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-team-run-apply-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-team-run-worktree-root-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "assign", "Implementer 1 ownership: src/api", env=env)
            run_workflow(root, "team-run", env=env)
            entry = parse_worktree_manifest(root)["entries"][0]
            commit_worktree_file(Path(entry["path"]), "src/api/active-story.txt", "active story implementation")
            run_workflow(root, "merge-gate", env=env)
            gate = parse_merge_gate(root)
            assert gate["status"] == "ready"
            assert gate["entries"][0]["status"] == "ready"

            seed_state(root, stage="review", active="Story 2")
            run_workflow(root, "review-sync", env=env)
            state = parse_state(root)
            assert state["Human gate status"] == "blocked"
            assert state["Blocked reason"].startswith("Merge apply is required")

            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            assert parse_merge_apply(root)["status"] == "applied"
            assert (root / "src" / "api" / "active-story.txt").exists()


def test_merge_gate_allows_in_scope_committed_worktree_changes() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-merge-gate-pass-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-merge-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            manifest = parse_worktree_manifest(root)
            for entry in manifest.get("entries", []):
                allowed = entry["allowed_paths"][0]
                commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", f"{entry['lane_id']} change")

            run_workflow(root, "merge-gate", env=env)
            gate = parse_merge_gate(root)
            assert gate["status"] == "ready"
            assert all(entry["status"] == "ready" for entry in gate["entries"])


def test_merge_gate_blocks_out_of_scope_worktree_changes() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-merge-gate-scope-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-merge-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            entry = parse_worktree_manifest(root)["entries"][0]
            commit_worktree_file(Path(entry["path"]), "src/out-of-scope/change.txt", "bad change")

            run_workflow(root, "merge-gate", env=env)
            gate = parse_merge_gate(root)
            state = parse_state(root)
            assert gate["status"] == "blocked"
            assert any("outside allowed scope" in blocker for blocker in gate["blockers"])
            assert gate["failure_class"] == "policy_or_scope_block"
            assert gate["failure_category"] == "policy_or_security_block"
            assert state["Human gate status"] == "blocked"
            assert state["Blocked reason"].startswith("Merge gate is blocked")


def test_review_sync_requires_merge_gate_after_parallel_dispatch() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-merge-gate-required-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-merge-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            seed_state(root, stage="review", active="Story 2")
            run_workflow(root, "approve", env=env)
            state = parse_state(root)
            assert state["Human gate status"] == "blocked"
            assert state["Blocked reason"].startswith("Merge gate is required")

            seed_state(root, stage="review", active="Story 2")
            run_workflow(root, "review-sync", env=env)
            state = parse_state(root)
            assert state["Human gate status"] == "blocked"
            assert state["Blocked reason"].startswith("Merge gate is required")


def test_merge_apply_applies_ready_parallel_branches() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-merge-apply-pass-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-merge-apply-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            manifest = parse_worktree_manifest(root)
            for entry in manifest.get("entries", []):
                allowed = entry["allowed_paths"][0]
                commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", f"{entry['lane_id']} change")

            run_workflow(root, "merge-gate", env=env)
            blocked = run_workflow(root, "merge-apply", env=env, check=False)
            assert blocked.returncode == 0
            assert parse_merge_apply(root)["status"] == "blocked"

            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            apply = parse_merge_apply(root)
            assert apply["status"] == "applied"
            assert (root / "src" / "api" / "change.txt").exists()
            assert (root / "src" / "ui" / "change.txt").exists()
            assert all(entry["status"] == "merged" for entry in apply["entries"] if entry["changed_paths"])


def test_review_sync_requires_merge_apply_after_parallel_changes() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-merge-apply-required-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-merge-apply-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            entry = parse_worktree_manifest(root)["entries"][0]
            allowed = entry["allowed_paths"][0]
            commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", "change")
            run_workflow(root, "merge-gate", env=env)

            seed_state(root, stage="review", active="Story 2")
            run_workflow(root, "review-sync", env=env)
            state = parse_state(root)
            assert state["Human gate status"] == "blocked"
            assert state["Blocked reason"].startswith("Merge apply is required")

            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            run_workflow(root, "integration-gate", "status: passed; command: smoke integration suite; evidence: smoke artifact", env=env)
            gate = parse_integration_gate(root)
            assert gate["status"] == "ready"
            assert gate["merge_apply"]["status"] == "applied"


def test_integration_gate_blocks_when_required_evidence_is_missing() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-required-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            manifest = parse_worktree_manifest(root)
            for entry in manifest.get("entries", []):
                allowed = entry["allowed_paths"][0]
                commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", f"{entry['lane_id']} change")

            run_workflow(root, "merge-gate", env=env)
            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            run_workflow(root, "integration-gate", env=env)
            gate = parse_integration_gate(root)
            state = parse_state(root)
            assert gate["status"] == "blocked"
            assert gate["requirement"]["required"] is True
            assert state["Human gate status"] == "blocked"
            assert state["Blocked reason"].startswith("Integration test gate is blocked")


def test_integration_gate_accepts_passing_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-pass-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            manifest = parse_worktree_manifest(root)
            for entry in manifest.get("entries", []):
                allowed = entry["allowed_paths"][0]
                commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", f"{entry['lane_id']} change")

            run_workflow(root, "merge-gate", env=env)
            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            run_workflow(root, "integration-gate", "status: passed; command: smoke integration suite; evidence: smoke artifact", env=env)
            gate = parse_integration_gate(root)
            assert gate["status"] == "ready"
            assert gate["evidence"]["status"] == "passed"

            seed_state(root, stage="review", active="Story 2")
            run_workflow(root, "review-sync", env=env)
            state = parse_state(root)
            assert not state["Blocked reason"].startswith("Integration test gate")


def test_integration_gate_not_required_for_no_change_merge_gate() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-none-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            run_workflow(root, "merge-gate", env=env)
            run_workflow(root, "integration-gate", env=env)
            gate = parse_integration_gate(root)
            assert gate["status"] == "not_required"
            assert gate["requirement"]["required"] is False


def test_integration_gate_blocks_when_dag_changes() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-stale-dag-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            entry = parse_worktree_manifest(root)["entries"][0]
            allowed = entry["allowed_paths"][0]
            commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", "change")
            run_workflow(root, "merge-gate", env=env)
            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            run_workflow(root, "integration-gate", "status: passed; command: smoke integration suite; evidence: smoke artifact", env=env)

            dag_path = root / ".workflow" / "demo" / "dag.json"
            dag = json.loads(dag_path.read_text(encoding="utf-8"))
            dag["stale_test_marker"] = True
            dag_path.write_text(json.dumps(dag, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            seed_state(root, stage="review", active="Story 2")
            run_workflow(root, "review-sync", env=env)
            state = parse_state(root)
            assert state["Human gate status"] == "blocked"
            assert state["Blocked reason"].startswith("Integration test gate is stale because dag.json changed")


def test_integration_gate_runs_allowlisted_command() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-allowlisted-pass-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        commit_repo_file(
            root,
            "scripts/integration_pass.py",
            """
            print("integration smoke passed")
            """,
        )
        with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            manifest = parse_worktree_manifest(root)
            for entry in manifest.get("entries", []):
                allowed = entry["allowed_paths"][0]
                commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", f"{entry['lane_id']} change")

            run_workflow(root, "merge-gate", env=env)
            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            write_integration_allowlist(
                root,
                [
                    {
                        "id": "api-smoke",
                        "description": "passing smoke test",
                        "argv": ["python3", "scripts/integration_pass.py"],
                        "cwd": ".",
                        "timeout_seconds": 30,
                    }
                ],
            )
            run_workflow(root, "integration-gate", "test-id: api-smoke", env=env)
            gate = parse_integration_gate(root)
            assert gate["status"] == "ready"
            assert gate["evidence"]["source"] == "allowlisted-run"
            assert gate["evidence"]["status"] == "passed"
            execution = gate["evidence"]["execution"]
            assert execution["status"] == "passed"
            assert execution["exit_code"] == 0
            assert (root / execution["result_path"]).exists()
            records = root / ".workflow" / "demo" / "records" / "integration-gate-runs.jsonl"
            assert '"status": "passed"' in records.read_text(encoding="utf-8")


def test_integration_gate_blocks_unknown_allowlisted_command() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-allowlisted-unknown-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        commit_repo_file(root, "scripts/integration_pass.py", "print('ok')")
        with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            entry = parse_worktree_manifest(root)["entries"][0]
            allowed = entry["allowed_paths"][0]
            commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", "change")
            run_workflow(root, "merge-gate", env=env)
            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            write_integration_allowlist(
                root,
                [{"id": "api-smoke", "argv": ["python3", "scripts/integration_pass.py"], "cwd": "."}],
            )
            run_workflow(root, "integration-gate", "test-id: missing-smoke", env=env)
            gate = parse_integration_gate(root)
            assert gate["status"] == "blocked"
            assert any("not present in the allowlist" in blocker for blocker in gate["blockers"])
            run_dir = root / ".workflow" / "demo" / "integration-runs"
            assert not run_dir.exists() or not list(run_dir.iterdir())


def test_integration_gate_blocks_failing_allowlisted_command() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-allowlisted-fail-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        commit_repo_file(
            root,
            "scripts/integration_fail.py",
            """
            import sys
            print("integration smoke failed")
            sys.exit(3)
            """,
        )
        with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            entry = parse_worktree_manifest(root)["entries"][0]
            allowed = entry["allowed_paths"][0]
            commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", "change")
            run_workflow(root, "merge-gate", env=env)
            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            write_integration_allowlist(
                root,
                [{"id": "api-smoke", "argv": ["python3", "scripts/integration_fail.py"], "cwd": "."}],
            )
            run_workflow(root, "integration-gate", "test-id: api-smoke", env=env)
            gate = parse_integration_gate(root)
            assert gate["status"] == "blocked"
            assert gate["evidence"]["source"] == "allowlisted-run"
            assert gate["evidence"]["execution"]["status"] == "failed"
            assert gate["evidence"]["execution"]["exit_code"] == 3


def test_integration_gate_rejects_shell_allowlist_entry() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-allowlisted-shell-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            entry = parse_worktree_manifest(root)["entries"][0]
            allowed = entry["allowed_paths"][0]
            commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", "change")
            run_workflow(root, "merge-gate", env=env)
            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            write_integration_allowlist(
                root,
                [{"id": "shell-smoke", "argv": ["sh", "-c", "exit 0"], "cwd": "."}],
            )
            run_workflow(root, "integration-gate", "test-id: shell-smoke", env=env)
            gate = parse_integration_gate(root)
            assert gate["status"] == "blocked"
            assert any("not allowed" in blocker or "inline evaluation" in blocker for blocker in gate["blockers"])


def test_integration_gate_does_not_execute_manual_command_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-manual-command-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        commit_repo_file(
            root,
            "scripts/pwn.py",
            """
            from pathlib import Path
            Path("pwned.txt").write_text("executed", encoding="utf-8")
            """,
        )
        with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            entry = parse_worktree_manifest(root)["entries"][0]
            allowed = entry["allowed_paths"][0]
            commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", "change")
            run_workflow(root, "merge-gate", env=env)
            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            run_workflow(
                root,
                "integration-gate",
                "status: passed; command: python3 scripts/pwn.py; evidence: manually reported external run",
                env=env,
            )
            gate = parse_integration_gate(root)
            assert gate["status"] == "ready"
            assert gate["evidence"]["source"] == "manual-record"
            assert not (root / "pwned.txt").exists()


def test_integration_gate_allowlist_change_makes_review_stale() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-allowlist-stale-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root, active="Story 2")
        mark_story_one_done(root)
        init_git_repo(root)
        commit_repo_file(root, "scripts/integration_pass.py", "print('ok')")
        with tempfile.TemporaryDirectory(prefix="wrkflw-integration-gate-worktrees-") as worktrees:
            env = {"WRKFLW_WORKTREE_ROOT": worktrees}
            run_workflow(root, "dag-sync", env=env)
            run_workflow(root, "team-run-level", env=env)
            entry = parse_worktree_manifest(root)["entries"][0]
            allowed = entry["allowed_paths"][0]
            commit_worktree_file(Path(entry["path"]), f"{allowed}/change.txt", "change")
            run_workflow(root, "merge-gate", env=env)
            run_workflow(root, "merge-apply", "confirm: merge-apply", env=env)
            write_integration_allowlist(
                root,
                [{"id": "api-smoke", "argv": ["python3", "scripts/integration_pass.py"], "cwd": "."}],
            )
            run_workflow(root, "integration-gate", "test-id: api-smoke", env=env)
            gate = parse_integration_gate(root)
            assert gate["status"] == "ready"

            write_integration_allowlist(
                root,
                [
                    {
                        "id": "api-smoke",
                        "description": "changed after gate",
                        "argv": ["python3", "scripts/integration_pass.py"],
                        "cwd": ".",
                    }
                ],
            )
            seed_state(root, stage="review", active="Story 2")
            run_workflow(root, "review-sync", env=env)
            state = parse_state(root)
            assert state["Human gate status"] == "blocked"
            assert state["Blocked reason"].startswith("Integration test gate is stale because integration-test-allowlist.json changed")


def test_debt_gate_blocks_and_unblocks() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-debt-") as tmp:
        root = Path(tmp)
        seed_state(root, stage="release-planning", active="Story 1")
        run_workflow(
            root,
            "debt-record",
            "type: missing functionality; severity: high; summary: release blocker; owner: QA",
        )
        state = parse_state(root)
        assert state["Human gate status"] == "blocked"
        assert state["Blocked reason"].startswith("Open high/critical technical debt blocks")

        debt_path = root / ".workflow" / "demo" / "records" / "debt.jsonl"
        debt_id = json.loads(debt_path.read_text(encoding="utf-8").splitlines()[0])["id"]
        run_workflow(
            root,
            "debt-record",
            f"id: {debt_id}; status: accepted; resolution: accepted by release owner",
        )
        state = parse_state(root)
        assert state["Human gate status"] == "pending"
        assert state["Blocked reason"] == ""
        assert state["Challenge note"].startswith("Accepted high technical debt")


def test_dag_sync_resume_from_command_checkpoint() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-resume-dag-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root)
        failed = run_workflow(
            root,
            "dag-sync",
            env={"WRKFLW_FAIL_AFTER_CHECKPOINT": "command"},
            check=False,
        )
        assert failed.returncode == 1
        assert not (root / ".workflow" / "demo" / "dag.json").exists()

        resumed = run_workflow(root, "resume")
        assert resumed.returncode == 0
        assert (root / ".workflow" / "demo" / "dag.json").exists()
        assert (root / ".workflow" / "demo" / "dag.md").exists()
        assert (root / ".workflow" / "demo" / "dag-validation.md").exists()
        assert history_event_count(root) == 1

        tx_paths = sorted((root / ".workflow" / "_transactions" / "demo").iterdir())
        tx_metadata = json.loads((tx_paths[-1] / "transaction.json").read_text(encoding="utf-8"))
        assert tx_metadata["status"] == "committed"
        assert tx_metadata["latest_checkpoint"] == "diagram"


def test_stale_resume_is_refused_without_overwriting_user_edits() -> None:
    with tempfile.TemporaryDirectory(prefix="wrkflw-resume-stale-") as tmp:
        root = Path(tmp)
        seed_three_story_graph(root)
        failed = run_workflow(
            root,
            "dag-sync",
            env={"WRKFLW_FAIL_AFTER_CHECKPOINT": "command"},
            check=False,
        )
        assert failed.returncode == 1
        user_note = root / ".workflow" / "demo" / "user-note.md"
        write(user_note, "# User Note\n\nDo not overwrite this.")

        resumed = run_workflow(root, "resume", check=False)
        assert resumed.returncode == 1
        assert "Refusing to resume" in resumed.stderr
        assert user_note.exists()


def main() -> int:
    tests = [
        test_team_run_requires_dag,
        test_execution_path_routes_simple_and_flagged_stories,
        test_feedback_synth_blocks_flagged_review_until_required_inputs_exist,
        test_feedback_synth_ignores_boundary_language_in_approved_risks,
        test_issue_advisor_maps_stuck_story_evidence_to_recovery_actions,
        test_issue_advisor_handles_modified_scope_and_debt_budget,
        test_replanner_proposes_and_applies_split_with_history,
        test_replanner_blocks_stale_apply_without_overwriting_edits,
        test_replanner_applies_modified_acceptance_scope,
        test_replanner_applies_skip_story_and_dag_marks_deferred,
        test_replanner_applies_dependency_rewrite_and_blocks_dependent_until_new_parent_done,
        test_replanner_applies_remaining_order_without_touching_completed_history,
        test_replanner_removes_leaf_story_without_dangling_dependencies,
        test_replanner_blocks_remove_that_creates_dangling_dependency,
        test_replanner_blocks_completed_story_mutation,
        test_replanner_blocks_split_apply_after_story_completed,
        test_replanner_blocks_modified_acceptance_apply_after_story_completed,
        test_verify_fix_generates_fix_tasks_and_accepts_pass_evidence,
        test_verify_fix_blocks_review_sync_when_stale,
        test_verify_fix_feeds_feedback_synth_and_issue_advisor,
        test_ci_feedback_records_failed_and_passed_checks,
        test_ci_failure_class_promotes_to_feedback_synth_and_issue_advisor,
        test_ci_timeout_and_pending_failure_classification,
        test_ci_feedback_blocks_review_sync_when_stale_head,
        test_ci_feedback_feeds_feedback_synth_and_issue_advisor,
        test_ci_feedback_contributes_to_verify_fix_evidence,
        test_integration_timeout_classifies_environment_failure,
        test_integration_output_redaction_removes_auth_secret_values,
        test_feedback_synth_replans_on_dependency_failure_class,
        test_accounting_record_writes_jsonl_and_summary,
        test_successful_command_invocation_is_recorded_once,
        test_failed_checkpoint_resume_does_not_break_accounting,
        test_issue_advisor_records_retry_invocation,
        test_completion_requires_history_evidence,
        test_shared_learning_memory_records_and_propagates,
        test_parallel_dispatch_cleans_stale_packets,
        test_parallel_worktree_isolation_blocks_without_git,
        test_team_run_prepares_active_story_worktrees,
        test_team_run_records_dispatch_without_fake_model_cost,
        test_team_run_blocks_dirty_checkout_overlap,
        test_strict_agent_result_schema_validates_direct_report,
        test_team_sync_ingests_agent_usage_from_result_envelope,
        test_team_sync_all_ingests_worktree_result_envelope,
        test_team_sync_all_does_not_duplicate_synced_usage_records,
        test_team_sync_all_resume_uses_envelope_checkpoint_without_duplicate_usage,
        test_team_sync_all_rejects_invalid_result_envelope_before_batch_ingest,
        test_team_run_merge_apply_applies_active_story_branch,
        test_merge_gate_allows_in_scope_committed_worktree_changes,
        test_merge_gate_blocks_out_of_scope_worktree_changes,
        test_review_sync_requires_merge_gate_after_parallel_dispatch,
        test_merge_apply_applies_ready_parallel_branches,
        test_review_sync_requires_merge_apply_after_parallel_changes,
        test_integration_gate_blocks_when_required_evidence_is_missing,
        test_integration_gate_accepts_passing_evidence,
        test_integration_gate_not_required_for_no_change_merge_gate,
        test_integration_gate_blocks_when_dag_changes,
        test_integration_gate_runs_allowlisted_command,
        test_integration_gate_blocks_unknown_allowlisted_command,
        test_integration_gate_blocks_failing_allowlisted_command,
        test_integration_gate_rejects_shell_allowlist_entry,
        test_integration_gate_does_not_execute_manual_command_evidence,
        test_integration_gate_allowlist_change_makes_review_stale,
        test_debt_gate_blocks_and_unblocks,
        test_dag_sync_resume_from_command_checkpoint,
        test_stale_resume_is_refused_without_overwriting_user_edits,
    ]
    for test in tests:
        print(f"RUN {test.__name__}", flush=True)
        test()
        print(f"OK {test.__name__}", flush=True)
    print("SWE-AF adoption smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

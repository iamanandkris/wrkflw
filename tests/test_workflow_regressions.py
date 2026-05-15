from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from workflow_integration_gate import redact_output
from workflow_replanner import completed_apply_blockers
from workflow_verify_fix import evidence_mentions_criterion
from workflow_feedback_synthesizer import feedback_synthesis_block, run_feedback_synthesis
import generate_capability_inventory
import generate_implementation_plan
import generate_story_slices
import generate_workflow_diagram
import workflow_capability_synth
import workflow_stage_synth
import bridge_workflow_to_openspec
import handle_workflow_command
import workflow_profile


class WorkflowRegressionTests(unittest.TestCase):
    def run_script_main(self, module: object, root: Path, slug: str = "sql-server-mcp-design") -> int:
        script_name = str(getattr(module, "__name__", "script"))
        with mock.patch.object(sys, "argv", [script_name, "--slug", slug, "--root", str(root)]):
            return module.main()  # type: ignore[attr-defined]

    def run_workflow_command(self, root: Path, command: str, reason: str = "", slug: str = "demo") -> int:
        argv = ["handle_workflow_command", "--slug", slug, "--root", str(root), "--command", command]
        if reason:
            argv.extend(["--reason", reason])
        with mock.patch.object(sys, "argv", argv):
            return handle_workflow_command.main()

    def write_workflow_state(
        self,
        root: Path,
        stage: str,
        gate: str = "pending",
        active_items: str = "Story 1",
        blocked_reason: str = "",
        next_action: str = "",
        slug: str = "demo",
    ) -> Path:
        workflow = root / ".workflow" / slug
        workflow.mkdir(parents=True, exist_ok=True)
        fields = {
            "Current stage": stage,
            "Human gate status": gate,
            "Blocked reason": blocked_reason,
            "Rework target": "",
            "Rejection reason": "",
            "Approval note": "",
            "Active items": active_items,
            "Deferred items": "",
            "Item note": "",
            "Challenge note": "",
            "Next action": next_action,
        }
        lines = ["# State", ""]
        lines.extend(f"- {key}: {value}" for key, value in fields.items())
        lines.append("")
        (workflow / "state.md").write_text("\n".join(lines), encoding="utf-8")
        return workflow

    def test_actions_generates_review_menu_with_manual_option(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-actions-review-") as tmp:
            root = Path(tmp)
            workflow = self.write_workflow_state(root, "review", next_action="review PR outcome and approve or reject")

            self.assertEqual(self.run_workflow_command(root, "actions"), 0)

            payload = json.loads((workflow / "action-menu.json").read_text(encoding="utf-8"))
            commands = [item.get("command") for item in payload["options"]]
            labels = [item.get("label") for item in payload["options"]]

        self.assertEqual(payload["current_stage"], "review")
        self.assertEqual(payload["recommended"]["command"], "wrkflw:feedback-synth")
        self.assertIn("wrkflw:review-sync \"...\"", commands)
        self.assertIn("wrkflw:challenge \"...\"", commands)
        self.assertIn("wrkflw:verify-fix \"...\"", commands)
        self.assertIn("wrkflw:issue-advisor", commands)
        self.assertIn("None / manual suggestion", labels)

    def test_actions_marks_material_team_run_options(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-actions-plan-") as tmp:
            root = Path(tmp)
            workflow = self.write_workflow_state(
                root,
                "implementation-planning",
                next_action="choose the next PR-sized slice",
            )

            self.assertEqual(self.run_workflow_command(root, "actions"), 0)

            payload = json.loads((workflow / "action-menu.json").read_text(encoding="utf-8"))
            team_run = next(item for item in payload["options"] if item.get("command") == "wrkflw:team-run \"...\"")
            team_run_level = next(item for item in payload["options"] if item.get("command") == "wrkflw:team-run-level \"...\"")
            markdown = (workflow / "action-menu.md").read_text(encoding="utf-8")

        self.assertEqual(payload["recommended"]["command"], "wrkflw:execution-path")
        self.assertTrue(team_run["material"])
        self.assertTrue(team_run["requires_explicit_selection"])
        self.assertTrue(team_run_level["material"])
        self.assertIn("None / manual suggestion", markdown)
        self.assertIn("Material commands should not run silently", markdown)

    def test_actions_include_capability_synthesis_at_capability_review(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-actions-capability-") as tmp:
            root = Path(tmp)
            workflow = self.write_workflow_state(
                root,
                "capability-review",
                next_action="review capability inventory",
            )

            self.assertEqual(self.run_workflow_command(root, "actions"), 0)

            payload = json.loads((workflow / "action-menu.json").read_text(encoding="utf-8"))
            commands = [item.get("command") for item in payload["options"]]
            markdown = (workflow / "action-menu.md").read_text(encoding="utf-8")

        self.assertIn("wrkflw:capability-synth \"...\"", commands)
        self.assertIn("Synthesize rich capabilities", markdown)

    def test_capability_synth_generates_codex_packet_and_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-capability-synth-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "tic-tac-toe"
            workflow.mkdir(parents=True)
            (workflow / "context.md").write_text(
                "- Problem: Build a browser-playable tic-tac-toe game.\n"
                "- Goal: 3x3 board, two local players, invalid click prevention, win/draw detection, reset.\n",
                encoding="utf-8",
            )
            (workflow / "capabilities.md").write_text(
                generate_capability_inventory.format_inventory(
                    mode="general-delivery",
                    rationale="Compatibility mode is not the capability source.",
                    text="Build a browser game with a 3x3 board, turns, invalid clicks, wins, draws, reset, and keyboard support.",
                    workflow_slug="tic-tac-toe",
                    workflow_statuses={},
                    profile={
                        "mode": "general-delivery",
                        "rationale": "Compatibility mode is not the capability source.",
                        "delivery_kind": "product",
                        "runtime_surface": "frontend",
                        "domain_packs": ["game-rules", "ui-state", "accessibility"],
                        "assurance_level": "normal",
                        "workflow_strategy": "simple",
                    },
                ),
                encoding="utf-8",
            )

            self.assertEqual(self.run_script_main(workflow_capability_synth, root, slug="tic-tac-toe"), 0)

            payload = json.loads((workflow / "capability-synth.json").read_text(encoding="utf-8"))
            packet = (workflow / "capability-synth.md").read_text(encoding="utf-8")
            validation = json.loads((workflow / "capability-synth-validation.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["planning_profile"]["runtime_surface"], "frontend")
        self.assertIn("game-rules", payload["planning_profile"]["domain_packs"])
        self.assertIn("Codex Capability Synthesis Task", packet)
        self.assertIn("Do not merely map the compatibility mode to a fixed list", packet)
        self.assertEqual(validation["status"], "pass")
        self.assertGreaterEqual(validation["capability_count"], 5)

    def test_capability_synth_command_keeps_gate_and_writes_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-capability-synth-command-") as tmp:
            root = Path(tmp)
            workflow = self.write_workflow_state(
                root,
                "capability-review",
                next_action="review capabilities",
                slug="tic-tac-toe",
            )
            (workflow / "context.md").write_text(
                "- Problem: Build a browser-playable tic-tac-toe game with board, turns, wins, draw, reset.\n",
                encoding="utf-8",
            )

            self.assertEqual(self.run_workflow_command(root, "capability-synth", "Improve capability inventory", slug="tic-tac-toe"), 0)

            state = (workflow / "state.md").read_text(encoding="utf-8")
            packet = (workflow / "capability-synth.md").read_text(encoding="utf-8")

        self.assertIn("- Current stage: capability-review", state)
        self.assertIn("capability synthesis packet refreshed", state)
        self.assertIn("Codex Capability Synthesis Task", packet)

    def test_story_synth_uses_shared_synthesis_framework(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-story-synth-") as tmp:
            root = Path(tmp)
            workflow = self.write_workflow_state(
                root,
                "story-slicing",
                active_items="Story 1",
                next_action="review story slices",
                slug="tic-tac-toe",
            )
            (workflow / "context.md").write_text(
                "- Problem: Build a browser-playable tic-tac-toe game.\n",
                encoding="utf-8",
            )
            (workflow / "capabilities.md").write_text(
                "# Capability Inventory\n\n"
                "## Planning Profile\n\n"
                "- Delivery kind: product\n"
                "- Runtime surface: frontend\n"
                "- Domain packs: game-rules, ui-state\n"
                "- Assurance level: normal\n"
                "- Workflow strategy: simple\n\n"
                "### Board Rendering And Layout\n"
                "- Status: required\n"
                "- Owning workflow: tic-tac-toe\n"
                "- Why: A visible board is required.\n"
                "- Why now: The design asks for a playable 3x3 board.\n"
                "- Evidence:\n"
                "  - design: 3x3 board\n"
                "- Story prompts:\n"
                "  - Render the board\n",
                encoding="utf-8",
            )

            payload = workflow_stage_synth.run_stage_synth(root, "tic-tac-toe", "story-slicing", "Create story slices")

            packet = (workflow / "story-synth.md").read_text(encoding="utf-8")
            validation = json.loads((workflow / "story-synth-validation.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["synthesis_kind"], "story-slicing")
        self.assertEqual(payload["artifact_stem"], "story-synth")
        self.assertIn("Codex Story Slicing Synthesis Task", packet)
        self.assertIn("Avoid fixed template grouping", packet)
        self.assertEqual(validation["status"], "pass")

    def test_stage_synth_command_writes_packet_and_preserves_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-stage-synth-command-") as tmp:
            root = Path(tmp)
            workflow = self.write_workflow_state(
                root,
                "implementation-planning",
                active_items="Story 1",
                next_action="review implementation plan",
            )
            (workflow / "story-1.md").write_text(
                "# Story 1\n\n## Acceptance Criteria\n- The board renders.\n",
                encoding="utf-8",
            )
            (workflow / "dag.json").write_text('{"nodes":[]}\n', encoding="utf-8")

            self.assertEqual(self.run_workflow_command(root, "implementation-plan-synth", "Improve PR slicing"), 0)

            state = (workflow / "state.md").read_text(encoding="utf-8")
            packet = (workflow / "implementation-plan-synth.md").read_text(encoding="utf-8")

        self.assertIn("- Current stage: implementation-planning", state)
        self.assertIn("Implementation Plan Synthesis Packet refreshed", state)
        self.assertIn("Codex Implementation Plan Synthesis Task", packet)

    def test_actions_include_stage_synthesis_options(self) -> None:
        cases = [
            ("discuss", "wrkflw:design-synth \"...\""),
            ("story-slicing", "wrkflw:story-synth \"...\""),
            ("story-enrichment", "wrkflw:story-enrichment-synth \"...\""),
            ("spec-authoring", "wrkflw:openspec-synth \"...\""),
            ("implementation-planning", "wrkflw:implementation-plan-synth \"...\""),
        ]
        for stage, command in cases:
            with self.subTest(stage=stage):
                with tempfile.TemporaryDirectory(prefix=f"wrkflw-actions-{stage}-") as tmp:
                    root = Path(tmp)
                    workflow = self.write_workflow_state(root, stage, next_action="review")

                    self.assertEqual(self.run_workflow_command(root, "actions"), 0)

                    payload = json.loads((workflow / "action-menu.json").read_text(encoding="utf-8"))
                    commands = [item.get("command") for item in payload["options"]]

                self.assertIn(command, commands)

    def test_planning_profile_gives_tool_precedence_over_example_wording(self) -> None:
        profile = workflow_profile.detect_planning_profile(
            "Build an example MCP server for SQL Server database queries from human and agent clients."
        )

        self.assertEqual(profile["mode"], "sql-server-mcp")
        self.assertEqual(profile["delivery_kind"], "tool")
        self.assertEqual(profile["runtime_surface"], "mcp-server")
        self.assertNotEqual(profile["delivery_kind"], "sample")

    def test_planning_profile_does_not_treat_click_as_cli_or_epic_as_parallel_team(self) -> None:
        profile = workflow_profile.detect_planning_profile(
            "\n".join(
                [
                    "Build a browser-playable tic-tac-toe game.",
                    "Manual browser test: invalid occupied-cell click and reset.",
                    "Selected epic slug: tic-tac-toe-game-design.",
                ]
            )
        )

        self.assertEqual(profile["mode"], "browser-game")
        self.assertEqual(profile["delivery_kind"], "product")
        self.assertEqual(profile["runtime_surface"], "frontend")
        self.assertEqual(profile["workflow_strategy"], "simple")
        self.assertNotEqual(profile["runtime_surface"], "cli")
        self.assertNotEqual(profile["workflow_strategy"], "parallel-team")

    def test_redact_output_removes_auth_secret_values(self) -> None:
        redacted = redact_output(
            "\n".join(
                [
                    "Authorization: Bearer abc.def.ghi",
                    "api_key=secret-value",
                    "token: visible-token",
                    "safe line",
                ]
            )
        )

        self.assertNotIn("abc.def.ghi", redacted)
        self.assertNotIn("secret-value", redacted)
        self.assertNotIn("visible-token", redacted)
        self.assertIn("Authorization: <redacted>", redacted)
        self.assertIn("api_key=<redacted>", redacted)
        self.assertIn("token: <redacted>", redacted)
        self.assertIn("safe line", redacted)

    def test_replan_apply_blocks_completed_split_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-regression-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "demo"
            workflow.mkdir(parents=True)
            (workflow / "history.md").write_text(
                "\n".join(
                    [
                        "# History",
                        "",
                        "## Event 001",
                        "- Command: approve",
                        "- To stage: done",
                        "- Focus items: Story 1",
                        "- Active items: Story 1",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            blockers = completed_apply_blockers(
                root,
                "demo",
                {"plan_type": "split_story", "active_story": "Story 1"},
            )

        self.assertEqual(
            blockers,
            ["cannot apply `split_story` to `Story 1` because completed history is immutable"],
        )

    def test_sql_server_mcp_inventory_replaces_legacy_generic_inventory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-sql-mcp-inventory-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "sql-server-mcp-design"
            workflow.mkdir(parents=True)
            (workflow / "context.md").write_text(
                "\n".join(
                    [
                        "# Context",
                        "",
                        "- Problem: Develop an MCP server for interacting with SQL Server from human and agent clients.",
                        "- Goal: Read-only v1 using TypeScript/Node and stdio transport.",
                        "- Constraints: Defer writes, admin tools, and HTTP transport.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "capabilities.md").write_text(
                "\n".join(
                    [
                        "# Capability Inventory",
                        "",
                        "## Capability Categories",
                        "",
                        "### Core Contract Usage",
                        "- Status: required",
                        "",
                        "### Field Validation",
                        "- Status: required",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(self.run_script_main(generate_capability_inventory, root), 0)

            inventory = (workflow / "capabilities.md").read_text(encoding="utf-8")
            self.assertIn("<!-- generated-by: wrkflw capability inventory -->", inventory)
            self.assertIn("- Mode: sql-server-mcp", inventory)
            self.assertIn("- Delivery kind: tool", inventory)
            self.assertIn("- Runtime surface: mcp-server", inventory)
            self.assertIn("- Domain packs: database, ai-agent", inventory)
            self.assertIn("- Assurance level: high-risk", inventory)
            self.assertIn("- Workflow strategy: spec-driven", inventory)
            self.assertIn("### MCP Runtime And Stdio Transport", inventory)
            self.assertIn("### Read-Only Query Execution", inventory)
            self.assertNotIn("### Core Contract Usage", inventory)

    def test_capability_inventory_preserves_human_curated_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-manual-inventory-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "sql-server-mcp-design"
            workflow.mkdir(parents=True)
            (workflow / "context.md").write_text(
                "- Problem: Develop an MCP server for interacting with SQL Server.\n",
                encoding="utf-8",
            )
            manual = "\n".join(
                [
                    "# Capability Inventory",
                    "",
                    "### Human Curated SQL Safety Boundary",
                    "- Status: required",
                    "- Why: This was reviewed by the team.",
                    "",
                ]
            )
            (workflow / "capabilities.md").write_text(manual, encoding="utf-8")

            self.assertEqual(self.run_script_main(generate_capability_inventory, root), 0)

            self.assertEqual((workflow / "capabilities.md").read_text(encoding="utf-8"), manual)

    def test_sql_server_mcp_story_slices_use_domain_specific_groups(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-sql-mcp-stories-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "sql-server-mcp-design"
            workflow.mkdir(parents=True)
            (workflow / "context.md").write_text(
                "\n".join(
                    [
                        "# Context",
                        "",
                        "- Problem: Develop an MCP server for interacting with SQL Server from human and agent clients.",
                        "- Goal: Read-only v1 using TypeScript/Node and stdio transport.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(self.run_script_main(generate_capability_inventory, root), 0)
            self.assertEqual(self.run_script_main(generate_story_slices, root), 0)

            stories = (workflow / "stories.md").read_text(encoding="utf-8")
            self.assertIn("<!-- generated-by: wrkflw story slices -->", stories)
            self.assertIn("## Story 1: Bootstrap MCP Stdio Runtime And Connection Config", stories)
            self.assertIn("Covers: MCP Runtime And Stdio Transport, SQL Server Connection Configuration", stories)
            self.assertNotIn("Core Contract Usage", stories)

    def test_browser_game_inventory_and_stories_use_game_specific_groups(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-browser-game-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "tic-tac-toe"
            workflow.mkdir(parents=True)
            (workflow / "design-seed.md").write_text(
                "\n".join(
                    [
                        "# Tic-Tac-Toe Game Design Seed",
                        "",
                        "Build a static browser tic-tac-toe game that opens from index.html.",
                        "The game needs a 3x3 board, X/O turn alternation, occupied-cell move prevention,",
                        "row, column, and diagonal win detection, draw detection, a reset button,",
                        "keyboard accessible cells, and a README explaining how to run it.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(self.run_script_main(generate_capability_inventory, root, slug="tic-tac-toe"), 0)
            self.assertEqual(self.run_script_main(generate_story_slices, root, slug="tic-tac-toe"), 0)

            inventory = (workflow / "capabilities.md").read_text(encoding="utf-8")
            self.assertIn("- Mode: browser-game", inventory)
            self.assertIn("- Delivery kind: product", inventory)
            self.assertIn("- Runtime surface: frontend", inventory)
            self.assertIn("- Domain packs: game-rules, ui-state, accessibility, documentation", inventory)
            self.assertIn("- Assurance level: normal", inventory)
            self.assertIn("- Workflow strategy: simple", inventory)
            self.assertIn("### Board Rendering And Layout", inventory)
            self.assertIn("### Turn Management", inventory)
            self.assertIn("### Move Validation", inventory)
            self.assertIn("### Win And Draw Detection", inventory)
            self.assertIn("### Reset And Replay Flow", inventory)
            self.assertIn("### Browser Interaction And Accessibility", inventory)
            self.assertIn("### Static App Packaging And Documentation", inventory)
            self.assertNotIn("### Core Contract Usage", inventory)
            self.assertNotIn("### Field Validation", inventory)

            stories = (workflow / "stories.md").read_text(encoding="utf-8")
            self.assertIn("- Compatibility mode: browser-game", stories)
            self.assertIn("- Delivery kind: product", stories)
            self.assertIn("- Runtime surface: frontend", stories)
            self.assertIn("- Domain packs: game-rules, ui-state, accessibility, documentation", stories)
            self.assertIn("## Story 1: Build Playable Board And Turn Loop", stories)
            self.assertIn("Covers: Board Rendering And Layout, Turn Management, Move Validation", stories)
            self.assertIn("## Story 2: Add Game Outcome Detection", stories)
            self.assertIn("## Story 3: Add Reset, Replay, And Accessibility", stories)
            self.assertIn("## Story 4: Package Static Browser App And Guidance", stories)
            self.assertNotIn("Core Contract Usage", stories)

    def test_capability_inventory_uses_profile_not_mode_for_capability_selection(self) -> None:
        inventory = generate_capability_inventory.format_inventory(
            mode="general-delivery",
            rationale="Compatibility mode intentionally does not drive capability selection.",
            text="Build a browser game with a board, turns, wins, draw detection, reset, and keyboard access.",
            workflow_slug="demo",
            workflow_statuses={},
            profile={
                "mode": "general-delivery",
                "rationale": "Compatibility mode intentionally does not drive capability selection.",
                "delivery_kind": "product",
                "runtime_surface": "frontend",
                "domain_packs": ["game-rules", "ui-state", "accessibility"],
                "assurance_level": "normal",
                "workflow_strategy": "simple",
            },
        )

        self.assertIn("- Mode: general-delivery", inventory)
        self.assertIn("- Runtime surface: frontend", inventory)
        self.assertIn("- Domain packs: game-rules, ui-state, accessibility", inventory)
        self.assertIn("### Board Rendering And Layout", inventory)
        self.assertIn("### Turn Management", inventory)
        self.assertIn("### Win And Draw Detection", inventory)
        self.assertNotIn("### Core Contract Usage", inventory)

    def test_story_slices_preserve_human_curated_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-manual-stories-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "sql-server-mcp-design"
            workflow.mkdir(parents=True)
            manual = "# Story Slices\n\n## Story 1: Human Curated Runtime Skeleton\nKeep this exact slice.\n"
            (workflow / "stories.md").write_text(manual, encoding="utf-8")
            (workflow / "capabilities.md").write_text(
                "# Capability Inventory\n\n## Workflow Mode\n\n- Mode: sql-server-mcp\n",
                encoding="utf-8",
            )

            self.assertEqual(self.run_script_main(generate_story_slices, root), 0)

            self.assertEqual((workflow / "stories.md").read_text(encoding="utf-8"), manual)

    def test_implementation_plan_first_pr_starts_with_implementation_not_tests(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-implementation-plan-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "sql-server-mcp-design"
            workflow.mkdir(parents=True)
            (workflow / "state.md").write_text(
                "# State\n\n- Active items: Story 1\n",
                encoding="utf-8",
            )
            (workflow / "story-1.md").write_text(
                "\n".join(
                    [
                        "# Story 1",
                        "",
                        "## Story",
                        "Bootstrap MCP Stdio Runtime And Connection Config",
                        "",
                        "## Scope",
                        "Create the TypeScript MCP stdio runtime skeleton and load SQL Server connection configuration.",
                        "",
                        "## Acceptance Criteria",
                        "- The server starts over stdio and exposes the initial SQL Server tools.",
                        "- Missing connection configuration fails before database work runs.",
                        "",
                        "## Test Expectations",
                        "- Add or update a test that starts the MCP server over stdio.",
                        "- Add or update a test that validates required SQL Server connection settings.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(self.run_script_main(generate_implementation_plan, root), 0)

            plan = (workflow / "implementation-plan.md").read_text(encoding="utf-8")
            included = plan.split("## Included In PR 1", 1)[1].split("## Ownership And Handoffs", 1)[0]
            bullets = [line for line in included.splitlines() if line.startswith("- ")]
            self.assertTrue(bullets)
            self.assertIn("Implementation:", bullets[0])
            self.assertIn("TypeScript MCP stdio runtime skeleton", bullets[0])
            self.assertTrue(any(line.startswith("- Test:") for line in bullets))

    def test_implementation_plan_keeps_all_acceptance_for_high_risk_interface_story(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-high-risk-implementation-plan-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "sql-server-mcp-design"
            workflow.mkdir(parents=True)
            (workflow / "state.md").write_text(
                "# State\n\n- Active items: Story 4\n",
                encoding="utf-8",
            )
            (workflow / "dag.json").write_text(
                json.dumps(
                    {
                        "validation": {"status": "valid"},
                        "nodes": [
                            {
                                "id": "story-4",
                                "story": "Story 4",
                                "title": "Read-Only Query Policy Classifier",
                                "status": "active",
                                "risk": "high",
                                "touches_interfaces": True,
                                "needs_deeper_qa": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (workflow / "story-4.md").write_text(
                "\n".join(
                    [
                        "# Story 4",
                        "",
                        "## Story",
                        "Read-Only Query Policy Classifier",
                        "",
                        "## Scope",
                        "Implement query normalization and policy classification before execution.",
                        "",
                        "## Acceptance Criteria",
                        "- Allows only a single SELECT or CTE statement.",
                        "- Blocks DML, DDL, EXEC, MERGE, TRUNCATE, SELECT INTO, and linked-server access.",
                        "- Applies allowed database/schema/object rules.",
                        "- Produces query hash, normalized SQL, policy violations, warnings, and effective limits.",
                        "- Treats parsing/classification as defense in depth.",
                        "",
                        "## Test Expectations",
                        "- Tests cover allowed SELECT and CTE forms.",
                        "- Tests cover blocked categories.",
                        "- Tests cover comment and string-literal attempts.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(self.run_script_main(generate_implementation_plan, root), 0)

            plan = (workflow / "implementation-plan.md").read_text(encoding="utf-8")
            included = plan.split("## Included In PR 1", 1)[1].split("## Ownership And Handoffs", 1)[0]
            deferred = plan.split("## Deferred To Later Slice(s)", 1)[1].split("## Risks To Watch", 1)[0]
            self.assertIn("Take the full acceptance-bearing slice for this high-risk/interface story", plan)
            self.assertIn("Acceptance: Applies allowed database/schema/object rules.", included)
            self.assertIn("Acceptance: Produces query hash, normalized SQL, policy violations, warnings, and effective limits.", included)
            self.assertIn("Acceptance: Treats parsing/classification as defense in depth.", included)
            self.assertIn("Test: Tests cover comment and string-literal attempts.", included)
            self.assertNotIn("Applies allowed database/schema/object rules", deferred)
            self.assertNotIn("Produces query hash", deferred)

    def test_implementation_plan_defers_only_explicit_later_slice_acceptance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-explicit-later-slice-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "sql-server-mcp-design"
            workflow.mkdir(parents=True)
            (workflow / "state.md").write_text(
                "# State\n\n- Active items: Story 1\n",
                encoding="utf-8",
            )
            (workflow / "story-1.md").write_text(
                "\n".join(
                    [
                        "# Story 1",
                        "",
                        "## Scope",
                        "Build a focused runtime slice.",
                        "",
                        "## Acceptance Criteria",
                        "- Runtime contract is implemented.",
                        "- Later slice: HTTP transport is implemented.",
                        "- [deferred] Admin tools are implemented.",
                        "",
                        "## Test Expectations",
                        "- Runtime contract tests pass.",
                        "- HTTP transport tests pass.",
                        "- Admin tool tests pass.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(self.run_script_main(generate_implementation_plan, root), 0)

            plan = (workflow / "implementation-plan.md").read_text(encoding="utf-8")
            included = plan.split("## Included In PR 1", 1)[1].split("## Ownership And Handoffs", 1)[0]
            deferred = plan.split("## Deferred To Later Slice(s)", 1)[1].split("## Risks To Watch", 1)[0]
            self.assertIn("Acceptance: Runtime contract is implemented.", included)
            self.assertNotIn("HTTP transport is implemented", included)
            self.assertNotIn("Admin tools are implemented", included)
            self.assertIn("Acceptance (explicit later slice): HTTP transport is implemented.", deferred)
            self.assertIn("Acceptance (explicit later slice): Admin tools are implemented.", deferred)
            self.assertIn("Test: Admin tool tests pass.", deferred)

    def test_implementation_plan_flags_typescript_build_scope_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-build-scope-drift-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "sql-server-mcp-design"
            workflow.mkdir(parents=True)
            (root / "src" / "server").mkdir(parents=True)
            (root / "src" / "server" / "createServer.ts").write_text("export {}\n", encoding="utf-8")
            (root / "src" / "config.ts").write_text("export const scratch = true\n", encoding="utf-8")
            (root / "tsconfig.json").write_text(
                '{ "include": ["src/**/*.ts"] }\n',
                encoding="utf-8",
            )
            (root / "package.json").write_text(
                '{ "scripts": { "typecheck": "tsc -p tsconfig.json --noEmit", "test": "vitest run" } }\n',
                encoding="utf-8",
            )
            (workflow / "state.md").write_text(
                "# State\n\n- Active items: Story 1\n",
                encoding="utf-8",
            )
            (workflow / "story-1.md").write_text(
                "\n".join(
                    [
                        "# Story 1",
                        "",
                        "## Story",
                        "Runtime Contract Registry",
                        "",
                        "## Scope",
                        "Build only the MCP runtime registry.",
                        "",
                        "## Allowed Write Paths",
                        "- src/server/**",
                        "- src/tools/**",
                        "- test/protocol/**",
                        "- tsconfig.json",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(self.run_script_main(generate_implementation_plan, root), 0)

            plan = (workflow / "implementation-plan.md").read_text(encoding="utf-8")
            self.assertIn("## Build Scope Drift Check", plan)
            self.assertIn("Status: warning before implementation starts", plan)
            self.assertIn("`src/config.ts` is included by `tsconfig.json` pattern `src/**/*.ts`", plan)
            self.assertIn("keep the drift as prior-story baseline validation evidence", plan)

    def test_verify_fix_matches_common_code_identifier_evidence(self) -> None:
        self.assertTrue(
            evidence_mentions_criterion(
                "mssql.query input schema requires connectionId and does not accept connection strings",
                "Tool input references `connectionId`, never raw connection strings.",
            )
        )
        self.assertTrue(
            evidence_mentions_criterion(
                "tests cover production TLS validation",
                "Production profiles reject `trustServerCertificate: true`.",
            )
        )

    def test_feedback_synth_does_not_stale_on_derived_dag_metadata_changes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-feedback-dag-metadata-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "demo"
            workflow.mkdir(parents=True)
            (workflow / "state.md").write_text(
                "\n".join(
                    [
                        "# State",
                        "",
                        "- Current stage: release-planning",
                        "- Human gate status: pending",
                        "- Active items: Story 2",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "stories.md").write_text("## Story 2: Config\n", encoding="utf-8")
            (workflow / "story-2.md").write_text("# Story 2\n\n## Acceptance Criteria\n- Config passes.\n", encoding="utf-8")
            (workflow / "execution-path.json").write_text(
                '{"execution_path":{"path":"flagged","synthesis_required":true}}\n',
                encoding="utf-8",
            )
            (workflow / "dag.json").write_text(
                '{"generated_at":"2026-05-14T20:00:00Z","current_stage":"review","human_gate_status":"pending"}\n',
                encoding="utf-8",
            )
            (workflow / "role-reviews.md").write_text(
                "\n".join(
                    [
                        "# Role Reviews",
                        "",
                        "| Date | Story | Role | Verdict | Missing Requirements | Incorrect Assumptions | Risks | Questions | Suggested Changes | Evidence | Red-team Notes |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                        "| 2026-05-14 | Story 2 | Tech Lead | approve | - | - | - | - | - | Config passes. | - |",
                        "| 2026-05-14 | Story 2 | Reviewer QA | approve | - | - | - | - | - | Config passes. | - |",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "review-log.md").write_text(
                "# Review Log\n\n| Date | Role | Severity | Finding | Resolution |\n| --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )
            (workflow / "conflicts.md").write_text(
                "# Conflicts\n\n| Date | Story | Role | Severity | Conflict | Recommendation | Resolution |\n| --- | --- | --- | --- | --- | --- | --- |\n",
                encoding="utf-8",
            )

            payload = run_feedback_synthesis(root, "demo", "initial synthesis")
            self.assertEqual(payload["recommendation"], "approve")

            (workflow / "dag.json").write_text(
                '{"generated_at":"2026-05-14T20:01:00Z","current_stage":"done","human_gate_status":"approved"}\n',
                encoding="utf-8",
            )

            blocked, reason = feedback_synthesis_block(root, "demo", "release-planning")
            self.assertFalse(blocked, reason)

    def test_openspec_bridge_uses_explicit_story_capability_coverage_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-openspec-coverage-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "demo"
            workflow.mkdir(parents=True)
            change = root / "openspec" / "changes" / "demo-configuration-profiles-and-sql-server-connection-boundary"
            change.mkdir(parents=True)
            (workflow / "workflow-contract.md").write_text(
                "\n".join(
                    [
                        "# Workflow Contract",
                        "",
                        "- OpenSpec lane active: true",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "state.md").write_text(
                "\n".join(
                    [
                        "# State",
                        "",
                        "- Current stage: spec-authoring",
                        "- Human gate status: pending",
                        "- Active items: Story 2",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "links.md").write_text("# Links\n\n", encoding="utf-8")
            (workflow / "stories.md").write_text(
                "## Story 2: Configuration Profiles And SQL Server Connection Boundary\nConfigure named SQL Server profiles.\n",
                encoding="utf-8",
            )
            (workflow / "story-2.md").write_text(
                "\n".join(
                    [
                        "# Story 2: Configuration Profiles And SQL Server Connection Boundary",
                        "",
                        "## Scope",
                        "Implement the read-only v1 configuration boundary for named SQL Server connection profiles.",
                        "",
                        "## Capability Coverage",
                        "- SQL Server Connection Configuration",
                        "- Security Policy Baseline",
                        "- TypeScript Runtime And Packaging",
                        "",
                        "## Acceptance Criteria",
                        "- Tool input references `connectionId`, never raw connection strings.",
                        "- Production profiles reject `trustServerCertificate: true`.",
                        "",
                        "## Test Expectations",
                        "- Tests cover duplicate profile ids and production TLS validation.",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "capabilities.md").write_text(
                "\n".join(
                    [
                        "# Capability Inventory",
                        "",
                        "## Compatibility Workflow Mode",
                        "- Mode: sql-server-mcp",
                        "",
                        "## Planning Profile",
                        "- Delivery kind: tool",
                        "- Runtime surface: mcp-server",
                        "- Domain packs: database, ai-agent, security",
                        "- Assurance level: high-risk",
                        "- Workflow strategy: spec-driven",
                        "",
                        "## Capability Categories",
                        "### MCP Protocol Baseline",
                        "- Status: required",
                        "",
                        "### TypeScript Runtime And Packaging",
                        "- Status: required",
                        "",
                        "### Schema Discovery Resources",
                        "- Status: required",
                        "",
                        "### Read-Only Query Execution",
                        "- Status: required",
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(bridge_workflow_to_openspec, "run"):
                self.assertEqual(self.run_script_main(bridge_workflow_to_openspec, root, slug="demo"), 0)

            proposal = (change / "proposal.md").read_text(encoding="utf-8")
            spec = (change / "specs" / "configuration-profiles-and-sql-server-connection-boundary" / "spec.md").read_text(
                encoding="utf-8"
            )
            tasks = (change / "tasks.md").read_text(encoding="utf-8")
            self.assertIn("SQL Server Connection Configuration", proposal)
            self.assertIn("- Delivery kind: `tool`", proposal)
            self.assertIn("- Runtime surface: `mcp-server`", proposal)
            self.assertIn("- Domain packs: `database, ai-agent, security`", proposal)
            self.assertIn("- Compatibility workflow mode: `sql-server-mcp`", proposal)
            self.assertIn("Security Policy Baseline", spec)
            self.assertNotIn("Schema Discovery Resources", proposal)
            self.assertNotIn("Read-Only Query Execution", spec)
            self.assertNotIn("Schema Discovery Resources", tasks)

    def test_openspec_bridge_uses_story_covers_before_fuzzy_capability_inference(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-openspec-story-covers-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "demo"
            workflow.mkdir(parents=True)
            change = root / "openspec" / "changes" / "demo-read-only-query-policy-classifier"
            change.mkdir(parents=True)
            (workflow / "workflow-contract.md").write_text("- OpenSpec lane active: true\n", encoding="utf-8")
            (workflow / "state.md").write_text(
                "\n".join(
                    [
                        "# State",
                        "",
                        "- Current stage: spec-authoring",
                        "- Human gate status: pending",
                        "- Active items: Story 4",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "links.md").write_text("# Links\n\n", encoding="utf-8")
            (workflow / "stories.md").write_text(
                "\n".join(
                    [
                        "# Stories",
                        "",
                        "## Story 4: Read-Only Query Policy Classifier",
                        "Implement query normalization and policy classification before execution.",
                        "Depends on: Story 2",
                        "Covers: Query Policy Engine",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "story-4.md").write_text(
                "\n".join(
                    [
                        "# Story 4: Read-Only Query Policy Classifier",
                        "",
                        "## Acceptance Criteria",
                        "- Allows only a single `SELECT` or CTE statement for v1 query execution.",
                        "- Blocks DML, DDL, `EXEC`, `MERGE`, `TRUNCATE`, `SELECT INTO`, linked-server access, dynamic SQL, bulk access, temp procedure creation, `WAITFOR`, and dangerous server features by default.",
                        "- Applies allowed database/schema/object rules.",
                        "- Produces query hash, normalized SQL, policy violations, warnings, and effective limits.",
                        "- Treats parsing/classification as defense in depth, not the only boundary.",
                        "",
                        "## Test Expectations",
                        "- Tests cover allowed select/CTE forms and all blocked categories.",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "capabilities.md").write_text(
                "\n".join(
                    [
                        "# Capability Inventory",
                        "",
                        "## Workflow Mode",
                        "- Mode: product-service",
                        "",
                        "## Capability Categories",
                        "### Read-Only Query Execution",
                        "- Status: required",
                        "- Story prompts:",
                        "- Implement single-statement `SELECT`/CTE-only execution.",
                        "",
                        "### Query Policy Engine",
                        "- Status: required",
                        "- Story prompts:",
                        "- Classify statements before execution.",
                        "",
                        "### Developer And Operator Documentation",
                        "- Status: required",
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(bridge_workflow_to_openspec, "run"):
                self.assertEqual(self.run_script_main(bridge_workflow_to_openspec, root, slug="demo"), 0)

            proposal = (change / "proposal.md").read_text(encoding="utf-8")
            spec = (change / "specs" / "read-only-query-policy-classifier" / "spec.md").read_text(encoding="utf-8")
            tasks = (change / "tasks.md").read_text(encoding="utf-8")
            self.assertIn("Query Policy Engine", proposal)
            self.assertIn("this story covers: Query Policy Engine", spec)
            self.assertNotIn("Read-Only Query Execution", proposal)
            self.assertNotIn("Developer And Operator Documentation", spec)
            self.assertNotIn("Read-Only Query Execution", tasks)

    def test_workflow_diagrams_render_planning_profile_not_primary_mode_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-profile-diagram-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "demo"
            workflow.mkdir(parents=True)
            (workflow / "state.md").write_text(
                "\n".join(
                    [
                        "# State",
                        "",
                        "- Current stage: story-slicing",
                        "- Human gate status: pending",
                        "- Active items: Story 1",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "capabilities.md").write_text(
                "\n".join(
                    [
                        "# Capability Inventory",
                        "",
                        "## Compatibility Workflow Mode",
                        "- Mode: browser-game",
                        "",
                        "## Planning Profile",
                        "- Delivery kind: product",
                        "- Runtime surface: frontend",
                        "- Domain packs: game-rules, ui-state, accessibility",
                        "- Assurance level: normal",
                        "- Workflow strategy: simple",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "stories.md").write_text(
                "# Stories\n\n## Story 1: Build Board\nCovers: Board Rendering And Layout\n",
                encoding="utf-8",
            )

            self.assertEqual(self.run_script_main(generate_workflow_diagram, root, slug="demo"), 0)

            flow = (workflow / "diagram-flow.puml").read_text(encoding="utf-8")
            work = (workflow / "diagram-work.puml").read_text(encoding="utf-8")
            self.assertIn("Compatibility mode: browser-game", flow)
            self.assertIn("Delivery: product", flow)
            self.assertIn("Runtime: frontend", flow)
            self.assertNotIn("Workflow mode:", flow)
            self.assertIn("Compatibility mode: browser-game", work)
            self.assertIn("Domains: game-rules, ui-state, accessibility", work)

    def test_policy_classifier_fuzzy_coverage_does_not_inherit_query_execution(self) -> None:
        capabilities = [
            {
                "name": "Read-Only Query Execution",
                "status": "required",
                "why": "",
                "why_now": "",
                "story_prompts": ["Implement single-statement SELECT/CTE-only execution."],
            },
            {
                "name": "Query Policy Engine",
                "status": "required",
                "why": "",
                "why_now": "",
                "story_prompts": ["Classify statements before execution.", "Block dangerous SQL Server features."],
            },
            {
                "name": "Developer And Operator Documentation",
                "status": "required",
                "why": "",
                "why_now": "",
                "story_prompts": ["Document policy examples."],
            },
        ]

        covered, _deferred = bridge_workflow_to_openspec.infer_story_coverage(
            "Read-Only Query Policy Classifier",
            "",
            [
                "Allows only a single `SELECT` or CTE statement for v1 query execution.",
                "Blocks DML, DDL, `EXEC`, `MERGE`, `TRUNCATE`, `SELECT INTO`, linked-server access, dynamic SQL, bulk access, temp procedure creation, `WAITFOR`, and dangerous server features by default.",
                "Applies allowed database/schema/object rules.",
                "Produces query hash, normalized SQL, policy violations, warnings, and effective limits.",
                "Treats parsing/classification as defense in depth, not the only boundary.",
            ],
            ["Tests cover allowed select/CTE forms and all blocked categories."],
            capabilities,
        )

        self.assertEqual([capability["name"] for capability in covered], ["Query Policy Engine"])

    def test_team_sync_valid_report_clears_previous_team_sync_block(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-team-sync-clear-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "demo"
            workflow.mkdir(parents=True)
            (workflow / "state.md").write_text(
                "\n".join(
                    [
                        "# State",
                        "",
                        "- Current stage: implementation",
                        "- Human gate status: approved",
                        "- Blocked reason:",
                        "- Active items: Story 2",
                        "- Next action: implement",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "agent-assignments.md").write_text(
                "\n".join(
                    [
                        "# Agent Assignments",
                        "",
                        "| Role | Slot | Responsibility Focus | Default Ownership | Allowed Write Paths | Status |",
                        "| --- | --- | --- | --- | --- | --- |",
                        "| Implementer 1 | implementer-1 | code | assigned code/tests only | declare concrete module/file prefixes before parallel team-run | planned |",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "story-2.md").write_text("# Story 2\n\n## Allowed Write Paths\n- src/config.ts\n", encoding="utf-8")

            self.assertEqual(self.run_workflow_command(root, "team-sync", "Status: done\nSummary: missing role"), 0)
            blocked_state = (workflow / "state.md").read_text(encoding="utf-8")
            self.assertIn("- Human gate status: blocked", blocked_state)
            self.assertIn("team-sync requires a recognized role", blocked_state)

            valid_report = "\n".join(
                [
                    "Schema: agent-result-v1",
                    "Role: Implementer 1",
                    "Status: done",
                    "Verdict: approve",
                    "Summary: implemented config boundary",
                    "Files changed:",
                    "- src/config.ts",
                    "Validation run:",
                    "- npm test passed",
                    "Missing requirements:",
                    "- none",
                    "Incorrect assumptions:",
                    "- none",
                    "Risks:",
                    "- none",
                    "Questions:",
                    "- none",
                    "Suggested changes:",
                    "- none",
                    "Evidence:",
                    "- implementation evidence",
                    "Conflict entries:",
                    "- none",
                    "Assumption updates:",
                    "- none",
                    "Red-team notes:",
                    "- none",
                    "Findings:",
                    "- none",
                    "Debt entries:",
                    "- none",
                    "Memory entries:",
                    "- none",
                    "Follow-up: review",
                ]
            )
            self.assertEqual(self.run_workflow_command(root, "team-sync", valid_report), 0)

            state = (workflow / "state.md").read_text(encoding="utf-8")
            self.assertNotIn("team-sync requires a recognized role", state)
            self.assertIn("- Blocked reason: ", state)

    def test_team_sync_uses_active_story_allowed_paths_for_direct_implementer_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-team-sync-story-paths-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "demo"
            workflow.mkdir(parents=True)
            (workflow / "state.md").write_text(
                "\n".join(
                    [
                        "# State",
                        "",
                        "- Current stage: implementation",
                        "- Human gate status: approved",
                        "- Blocked reason:",
                        "- Active items: Story 2",
                        "- Next action: implement",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "agent-assignments.md").write_text(
                "\n".join(
                    [
                        "# Agent Assignments",
                        "",
                        "| Role | Slot | Responsibility Focus | Default Ownership | Allowed Write Paths | Status |",
                        "| --- | --- | --- | --- | --- | --- |",
                        "| Implementer 1 | implementer-1 | code | assigned code/tests only | declare concrete module/file prefixes before parallel team-run | planned |",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "story-2.md").write_text(
                "\n".join(
                    [
                        "# Story 2",
                        "",
                        "## Allowed Write Paths",
                        "- src/config.ts",
                        "- test/config/**",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            valid_report = "\n".join(
                [
                    "Schema: agent-result-v1",
                    "Role: Implementer 1",
                    "Status: done",
                    "Verdict: approve",
                    "Summary: implemented config boundary",
                    "Files changed:",
                    "- src/config.ts",
                    "- test/config/config.test.ts",
                    "Validation run:",
                    "- npm test passed",
                    "Missing requirements:",
                    "- none",
                    "Incorrect assumptions:",
                    "- none",
                    "Risks:",
                    "- none",
                    "Questions:",
                    "- none",
                    "Suggested changes:",
                    "- none",
                    "Evidence:",
                    "- implementation evidence",
                    "Conflict entries:",
                    "- none",
                    "Assumption updates:",
                    "- none",
                    "Red-team notes:",
                    "- none",
                    "Findings:",
                    "- none",
                    "Debt entries:",
                    "- none",
                    "Memory entries:",
                    "- none",
                    "Follow-up: review",
                ]
            )

            self.assertEqual(self.run_workflow_command(root, "team-sync", valid_report), 0)

            state = (workflow / "state.md").read_text(encoding="utf-8")
            self.assertNotIn("reported changes outside allowed write scope", state)
            self.assertIn("- Item note: Implementer 1 marked done", state)

    def test_next_from_done_selects_next_dag_ready_story(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-next-ready-story-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "demo"
            workflow.mkdir(parents=True)
            (workflow / "state.md").write_text(
                "\n".join(
                    [
                        "# State",
                        "",
                        "- Current stage: done",
                        "- Human gate status: approved",
                        "- Blocked reason:",
                        "- Active items: Story 2",
                        "- Next action: workflow complete",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "stories.md").write_text(
                "\n".join(
                    [
                        "# Stories",
                        "",
                        "## Story 1: Runtime",
                        "",
                        "## Story 2: Config",
                        "Depends on: Story 1",
                        "",
                        "## Story 3: Schema Discovery",
                        "Depends on: Story 2",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "history.md").write_text(
                "\n".join(
                    [
                        "# History",
                        "",
                        "## Event 001",
                        "- Command: approve",
                        "- To stage: done",
                        "- Active items: Story 1",
                        "",
                        "## Event 002",
                        "- Command: approve",
                        "- To stage: done",
                        "- Active items: Story 2",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "execution-board.md").write_text(
                "\n".join(
                    [
                        "# Execution Board",
                        "",
                        "- Workflow slug: demo",
                        "- Active story: Story 2",
                        "- Active owner: Reviewer QA",
                        "- Current handoff: Reviewer QA -> Product Owner",
                        "",
                        "| Work Item | Owner Role | Status | Blocked By | Reviewer | Notes |",
                        "| --- | --- | --- | --- | --- | --- |",
                        "| Story scope and acceptance review | Product Owner | done |  | Reviewer QA | Story 2 release plan is acceptable |",
                        "| Technical decomposition | Tech Lead | done |  | Product Owner | Story 2 implementation matches the approved slice |",
                        "| Implementation slice 1 | Implementer 1 | done |  | Reviewer QA | Story 2 configuration-profile boundary implemented |",
                        "| Implementation slice 2 | Implementer 2 | optional |  | Reviewer QA |  |",
                        "| Review and challenge | Reviewer QA | done |  | Product Owner | Story 2 review evidence recorded |",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "story-3.md").write_text(
                "# Story 3\n\n## Allowed Write Paths\n- src/schema/**\n",
                encoding="utf-8",
            )

            self.assertEqual(self.run_workflow_command(root, "next"), 0)

            state = (workflow / "state.md").read_text(encoding="utf-8")
            self.assertIn("- Current stage: story-enrichment", state)
            self.assertIn("- Human gate status: pending", state)
            self.assertIn("- Active items: Story 3", state)

            board = (workflow / "execution-board.md").read_text(encoding="utf-8")
            self.assertIn("- Active story: Story 3", board)
            self.assertIn("| Story scope and acceptance review | Product Owner | in-progress |  | Reviewer QA |  |", board)
            self.assertIn("| Technical decomposition | Tech Lead | planned |  | Product Owner |  |", board)
            self.assertNotIn("Story 2 release plan is acceptable", board)
            self.assertNotIn("Story 2 configuration-profile boundary implemented", board)

    def test_execution_board_sync_clears_stale_notes_when_header_already_updated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-stale-execution-board-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "demo"
            workflow.mkdir(parents=True)
            (workflow / "execution-board.md").write_text(
                "\n".join(
                    [
                        "# Execution Board",
                        "",
                        "- Workflow slug: demo",
                        "- Active story: Story 3",
                        "- Active owner: Reviewer QA",
                        "- Current handoff: Reviewer QA -> Product Owner",
                        "",
                        "| Work Item | Owner Role | Status | Blocked By | Reviewer | Notes |",
                        "| --- | --- | --- | --- | --- | --- |",
                        "| Story scope and acceptance review | Product Owner | done |  | Reviewer QA | Story 2 release plan is acceptable |",
                        "| Technical decomposition | Tech Lead | done |  | Product Owner | Story 2 implementation matches the approved slice |",
                        "| Implementation slice 1 | Implementer 1 | done |  | Reviewer QA | Story 2 configuration-profile boundary implemented |",
                        "| Implementation slice 2 | Implementer 2 | optional |  | Reviewer QA |  |",
                        "| Review and challenge | Reviewer QA | done |  | Product Owner | Story 2 review evidence recorded |",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            handle_workflow_command.sync_execution_board(
                root,
                "demo",
                {"Current stage": "story-enrichment", "Active items": "Story 3"},
            )

            board = (workflow / "execution-board.md").read_text(encoding="utf-8")
            self.assertIn("- Active story: Story 3", board)
            self.assertIn("| Story scope and acceptance review | Product Owner | in-progress |  | Reviewer QA |  |", board)
            self.assertNotIn("Story 2 release plan is acceptable", board)
            self.assertNotIn("Story 2 configuration-profile boundary implemented", board)

    def test_openspec_drift_check_accepts_markdown_wrapped_change_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="wrkflw-openspec-link-") as tmp:
            root = Path(tmp)
            workflow = root / ".workflow" / "demo"
            workflow.mkdir(parents=True)
            change = root / "openspec" / "changes" / "demo-story-1"
            change.mkdir(parents=True)
            (change / "proposal.md").write_text(
                "# Change\n\nStory 1: Runtime Contract Registry\n",
                encoding="utf-8",
            )
            (workflow / "workflow-contract.md").write_text(
                "\n".join(
                    [
                        "# Workflow Contract",
                        "",
                        "- OpenSpec required: true",
                        "- OpenSpec initialized: true",
                        "- OpenSpec waived: false",
                        "- OpenSpec waiver reason:",
                        "- OpenSpec lane active: true",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (workflow / "links.md").write_text(
                "# Links\n\n- OpenSpec change: `openspec/changes/demo-story-1`\n",
                encoding="utf-8",
            )

            blocked, reason = handle_workflow_command.detect_artifact_drift(
                root,
                "demo",
                "done",
                {"Active items": "Story 1: Runtime Contract Registry"},
            )

            self.assertFalse(blocked, reason)


if __name__ == "__main__":
    unittest.main()

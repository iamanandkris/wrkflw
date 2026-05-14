from __future__ import annotations

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
import generate_capability_inventory
import generate_implementation_plan
import generate_story_slices


class WorkflowRegressionTests(unittest.TestCase):
    def run_script_main(self, module: object, root: Path, slug: str = "sql-server-mcp-design") -> int:
        script_name = str(getattr(module, "__name__", "script"))
        with mock.patch.object(sys, "argv", [script_name, "--slug", slug, "--root", str(root)]):
            return module.main()  # type: ignore[attr-defined]

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
            self.assertIn("Status: action required before implementation starts", plan)
            self.assertIn("`src/config.ts` is included by `tsconfig.json` pattern `src/**/*.ts`", plan)
            self.assertIn("expand Allowed Write Paths, narrow the validation/build config", plan)


if __name__ == "__main__":
    unittest.main()

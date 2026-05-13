from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from workflow_integration_gate import redact_output
from workflow_replanner import completed_apply_blockers


class WorkflowRegressionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

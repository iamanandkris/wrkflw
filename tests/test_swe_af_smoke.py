from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import smoke_swe_af_adoption


class SweAfSmokeTests(unittest.TestCase):
    def test_swe_af_adoption_smoke_suite(self) -> None:
        self.assertEqual(smoke_swe_af_adoption.main(), 0)


if __name__ == "__main__":
    unittest.main()

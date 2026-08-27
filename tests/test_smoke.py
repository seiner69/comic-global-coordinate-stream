from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_json(*arguments: str) -> dict:
    completed = subprocess.run(
        [sys.executable, *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


class EndToEndSmokeTest(unittest.TestCase):
    def test_normal_fixture_is_deterministic_and_auditable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comic-coordinate-stream-") as temporary:
            root = Path(temporary)
            input_root = root / "input"
            output_root = root / "output"

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "make_test_fixture.py"),
                    "--root",
                    str(input_root),
                    "--case",
                    "normal",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            command = (
                str(SCRIPTS / "canonicalize_chapter.py"),
                "--chapter",
                "ch_001",
                "--input-dir",
                str(input_root / "ch_001"),
                "--output-root",
                str(output_root),
                "--extension",
                ".png",
                "--width",
                "64",
                "--width-policy",
                "strict",
                "--core-height",
                "60",
                "--context",
                "20",
                "--view-height",
                "100",
                "--minimum-exact-duplicate-height",
                "16",
                "--chapter-allowlist",
                "ch_001",
            )

            first = run_json(*command)
            second = run_json(*command)
            audit = run_json(
                str(SCRIPTS / "audit_output.py"),
                "--canonical-root",
                str(output_root),
                "--chapter",
                "ch_001",
            )

            self.assertEqual(first["status"], "PENDING_RERUN")
            self.assertEqual(second["status"], "PASS")
            self.assertEqual(second["boundary_tests_passed"], 2)
            self.assertEqual(audit["status"], "PASS")


if __name__ == "__main__":
    unittest.main()

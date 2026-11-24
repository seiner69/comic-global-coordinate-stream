from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "canonicalize_chapter.py"


def make_inputs(source: Path) -> dict[str, bytes]:
    source.mkdir(parents=True, exist_ok=True)
    for index, color in enumerate(("red", "green", "blue"), 1):
        with Image.new("RGB", (64, 32), color) as image:
            image.save(source / f"{index:03d}.png")
    return {p.name: p.read_bytes() for p in source.glob("*.png")}


def build(source: Path, output: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--chapter", "ch_001",
         "--input-dir", str(source), "--output-root", str(output),
         "--extension", ".png", "--width", "64", "--width-policy", "strict",
         "--core-height", "60", "--context", "20", "--view-height", "100"],
        capture_output=True, text=True,
    )


class InputSafetyTest(unittest.TestCase):
    def test_chapter_output_inputs_are_rejected_without_touching_any_files(self) -> None:
        for location in (Path("."), Path("scans"), Path("scans/nested")):
            with self.subTest(location=location), tempfile.TemporaryDirectory(prefix="comic-input-safety-") as temporary:
                root = Path(temporary).resolve()
                output = root / "canonical"
                chapter = output / "chapters" / "ch_001"
                source = chapter / location
                self.assertTrue(source.resolve().is_relative_to(root))
                make_inputs(source)
                sentinel = chapter / "scans" / "previous.txt"
                sentinel.parent.mkdir(parents=True, exist_ok=True)
                sentinel.write_text("previous output must survive rejection", encoding="utf-8")
                before = {p.relative_to(chapter).as_posix(): p.read_bytes()
                          for p in chapter.rglob("*") if p.is_file()}

                result = build(source, output)

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Input directory may not be inside the chapter output directory", result.stderr)
                after = {p.relative_to(chapter).as_posix(): p.read_bytes()
                         for p in chapter.rglob("*") if p.is_file()}
                self.assertEqual(after, before, "rejected layout must preserve source and existing output bytes")

    def test_inputs_elsewhere_under_output_root_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comic-input-safety-") as temporary:
            root = Path(temporary).resolve()
            output = root / "canonical"
            source = output / "inputs"
            self.assertTrue(source.resolve().is_relative_to(root))
            before = make_inputs(source)
            for expected in ("PENDING_RERUN", "PASS"):
                result = build(source, output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], expected)
            self.assertEqual({p.name: p.read_bytes() for p in source.glob("*.png")}, before)


if __name__ == "__main__":
    unittest.main()

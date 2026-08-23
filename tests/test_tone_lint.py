from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "tone_lint.py"


class ToneLintTests(unittest.TestCase):
    def test_bundled_self_test_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-test"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS  tone lint self-test", result.stdout)

    def test_cli_ignores_fenced_code_and_checks_visible_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = Path(temporary_directory) / "draft.md"
            draft.write_text(
                "```text\n原因很简单：代码示例保持原样。\n```\n\n"
                "原因很简单：正文应当直接说明原因。\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(draft)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.count("FAIL"), 1)
        self.assertIn(f"{draft}:5", result.stdout)

    def test_cli_ignores_tilde_fenced_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = Path(temporary_directory) / "draft.md"
            draft.write_text(
                "~~~text\n原因很简单：代码示例保持原样。\n~~~\n\n正文直接说明原因。\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(draft)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_accepts_ensure_logic_phrase(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            draft = Path(temporary_directory) / "draft.md"
            draft.write_text("编辑时应确保逻辑清晰，并保留原意。\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(draft)],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cli_reads_chat_draft_from_stdin(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "-"],
            input="原因很简单：正文应当直接说明原因。\n",
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL  -:1", result.stdout)


if __name__ == "__main__":
    unittest.main()

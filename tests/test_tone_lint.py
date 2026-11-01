from __future__ import annotations

# The original CLI smoke tests did not cover bilingual findings or structured output.
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "tone_lint.py"


class ToneLintTests(unittest.TestCase):
    def run_cli(self, *arguments: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            input=input_text,
            check=False,
            capture_output=True,
            text=True,
        )

    def json_diagnostics(self, text: str) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
        result = self.run_cli("--format", "json", "-", input_text=text)
        report = json.loads(result.stdout)
        self.assertEqual([item["path"] for item in report["files"]], ["-"])
        diagnostics = report["files"][0]["diagnostics"]
        self.assertEqual(report["failed"], any(item["severity"] == "FAIL" for item in diagnostics))
        return result, diagnostics

    def test_bundled_self_test_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-test"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS  表达检查自测", result.stdout)

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

    def test_unslop_warnings_cover_english_stock_expressions(self) -> None:
        examples = {
            "unslop-3": "The update adds caching, highlighting the importance of speed.",
            "unslop-5": "Experts believe this approach works.",
            "unslop-7": "Additionally, the report is available.",
            "unslop-8": "This file serves as the configuration.",
            "unslop-9": "The tool is not just a parser but a formatter.",
            "unslop-13": "Read the file — then close it.",
            "unslop-16": "- **Performance:** Performance improved.",
            "unslop-18": "## 🚀 Read the guide",
            "unslop-19": "The guide calls this “automatic”.",
            "unslop-20": "I hope this helps!",
            "unslop-22": "Great question!",
            "unslop-23": "In order to read the file, open it.",
            "unslop-24": "This could potentially possibly affect the result.",
            "unslop-25": "The future looks bright.",
            "unslop-26": "The roadmap is our north star.",
            "unslop-30": "This significantly improves performance.",
            "unslop-31": "Utilize the command to read the file.",
            "unslop-32": "This is a dial worth turning.",
        }
        for rule_id, text in examples.items():
            with self.subTest(rule_id=rule_id):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                findings = [item for item in diagnostics if item["rule_id"] == rule_id]
                self.assertTrue(findings, diagnostics)
                self.assertEqual({item["severity"] for item in findings}, {"WARN"})
                self.assertEqual({item["line"] for item in findings}, {1})
                self.assertEqual({item["source_rule"] for item in findings}, {rule_id.replace("-", ":")})

    def test_plain_rewrites_and_technical_words_do_not_warn(self) -> None:
        examples = (
            "Use the API to read the file. The compiler rejects an unknown column.",
            "The vector stores numbers. The surface has four corners. A primitive integer is accepted. The test harness calls the function.",
            "The leverageable and utilized_count fields store identifiers.",
            "编辑时应确保逻辑清晰，并保留原意。",
            "这里的“结果”表示返回值，‘a’表示字符。",
            "- **Schema in TypeScript.** Tables live in one file.",
            "Values range from 1 to 10.",
        )
        for text in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(diagnostics, [])

    def test_protected_syntax_does_not_produce_findings(self) -> None:
        examples = {
            "long_fence": "````text\n```\n原因很简单：示例。\n````\nRead the file.\n",
            "indented_code": "    原因很简单：示例。\n\nRead the file.\n",
            "inline_code": "Use `原因很简单` as an example.\n",
            "long_inline_code": "Use ``原因很简单 ` embedded tick`` as an example.\n",
            "frontmatter": "---\ndescription: 原因很简单\n---\nRead the file.\n",
            "link_target": "[Read the guide](https://example.invalid/跑测试)\n",
            "bare_url": "https://example.invalid/跑测试\n",
            "reference_definition": "[guide]: https://example.invalid/跑测试 \"原因很简单\"\nRead the file.\n",
            "html_comment": "<!--\n原因很简单：隐藏注释。\n-->\nRead the file.\n",
            "script": "<script>\n原因很简单：脚本内容。\n</script>\nRead the file.\n",
            "style": "<style>原因很简单</style>\nRead the file.\n",
            "pre": "<pre>原因很简单</pre>\nRead the file.\n",
            "html_code": "<code>原因很简单</code>\nRead the file.\n",
        }
        for name, text in examples.items():
            with self.subTest(name=name):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(diagnostics, [])

    def test_hidden_regions_preserve_adjacent_prose_and_original_line_numbers(self) -> None:
        text = (
            "---\nexample: 原因很简单\n---\n"
            "<script>\n原因很简单：隐藏内容。\n</script>\n"
            "原因很简单：前面的正文。<style>原因很简单</style> 原因很简单：后面的正文。\n"
            "<code>原因很简单</code> 原因很简单：行内代码后的正文。\n"
            "[原因很简单：链接标签](https://example.invalid/跑测试)\n"
        )
        result, diagnostics = self.json_diagnostics(text)
        failures = [item for item in diagnostics if item["severity"] == "FAIL"]
        self.assertEqual(result.returncode, 1)
        self.assertEqual([item["line"] for item in failures], [7, 8, 9])
        self.assertIn("前面的正文", failures[0]["excerpt"])
        self.assertIn("后面的正文", failures[0]["excerpt"])
        self.assertNotIn("https://", failures[2]["excerpt"])

    def test_protected_regions_do_not_activate_each_others_markup(self) -> None:
        # Separate masking passes used to let hidden delimiters hide later reader-facing prose.
        examples = (
            ("<script>\nconst x = `template`;\n```\n</script>\n原因很简单：正文。", 5),
            ("Use `<script>` and then 原因很简单：正文。", 1),
        )
        for text, line in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual([(item["rule_id"], item["line"]) for item in diagnostics], [("vf-013", line)])

    def test_escaped_delimiters_and_quoted_attributes_preserve_detection_boundaries(self) -> None:
        examples = (
            (r"\<code>原因很简单</code>", ["vf-013"]),
            (r"\\`原因很简单`", []),
            ("Read ](原因很简单：正文).", ["vf-013"]),
            ('<span title="value > 原因很简单">正文</span>', []),
        )
        for text, expected_ids in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual([item["rule_id"] for item in diagnostics], expected_ids)
                self.assertEqual(result.returncode, 1 if expected_ids else 0, result.stdout + result.stderr)

    def test_indented_paragraph_and_list_continuations_remain_visible(self) -> None:
        examples = (
            ("这是段落的第一行。\n    原因很简单：这是段落的下一行。", 2),
            ("- 第一项\n    原因很简单：这是列表内正文。", 2),
            ("- item\n\n    原因很简单：正文。", 3),
        )
        for text, line in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual([(item["rule_id"], item["line"]) for item in diagnostics], [("vf-013", line)])

    def test_inline_code_does_not_cross_paragraph_or_block_boundaries(self) -> None:
        examples = (
            ("`Unclosed code\n\n原因很简单：正文。\n\nUse `field` to configure.", 3),
            ("Use `field.\n## 原因很简单：这是标题。\nUse `other.", 2),
            ("Use `field.\n- 原因很简单：这是列表正文。\nUse `other.", 2),
        )
        for text, line in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual([(item["rule_id"], item["line"]) for item in diagnostics], [("vf-013", line)])

    def test_valid_multiline_inline_code_remains_excluded(self) -> None:
        examples = (
            "Use `field\n原因很简单：这是代码。\nname` in this paragraph.",
            "Use ``field\n原因很简单：这是 `代码`。\nname`` in this paragraph.",
        )
        for text in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(diagnostics, [])

    def test_quoted_fence_stops_at_its_container_boundary(self) -> None:
        examples = (
            ("> ```\n> code example\n\n原因很简单：正文。", 4),
            ("> ```\n> code example\n原因很简单：正文。", 3),
            ("> > ```\n> > code example\n>\n> 原因很简单：外层引用正文。", 4),
        )
        for text, line in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual([(item["rule_id"], item["line"]) for item in diagnostics], [("vf-013", line)])

    def test_valid_quoted_and_unclosed_top_level_fences_remain_excluded(self) -> None:
        examples = (
            "> ```text\n> 原因很简单：这是代码。\n> ```\n\nRead the guide.",
            "> > ~~~text\n> > 原因很简单：这是代码。\n> > ~~~\n\nRead the guide.",
            "```text\n原因很简单：这是代码。",
        )
        for text in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(diagnostics, [])

    def test_undefined_reference_labels_remain_visible(self) -> None:
        examples = (
            "Read [the guide][原因很简单] now.",
            "Read [the guide][原因很简单] now.\n\n```text\n[原因很简单]: https://example.invalid\n```",
            "Read [the guide][原因很简单] now.\n\n[原因很简单]:\n\nRead the guide.",
        )
        for text in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(("vf-013", 1), [(item["rule_id"], item["line"]) for item in diagnostics])

    def test_defined_reference_labels_resolve_before_or_after_the_link(self) -> None:
        examples = (
            "[原因很简单]: https://example.invalid\n\nRead [the guide][原因很简单] now.",
            "Read [the guide][原因很简单] now.\n\n[原因很简单]: https://example.invalid",
            "Read [the guide][原因很简单 ABC] now.\n\n[原因很简单   abc]: https://example.invalid",
        )
        for text in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(diagnostics, [])

    def test_inline_code_opener_on_lazy_quote_continuation_keeps_its_owner(self) -> None:
        examples = (
            "> Start paragraph.\nUse `field\n> 原因很简单：这是代码。\n> name` here.",
            "> > Start paragraph.\n> Use `field\n> > 原因很简单：这是代码。\n> > name` here.",
        )
        for text in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(diagnostics, [])

        result, diagnostics = self.json_diagnostics(
            "Use `field\n> 原因很简单：这是新引用正文。\n> name` here."
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual([(item["rule_id"], item["line"]) for item in diagnostics], [("vf-013", 2)])

    def test_list_item_fences_remain_excluded(self) -> None:
        examples = (
            "- ```text\n  原因很简单：这是代码。\n  ```",
            "1. ```text\n   原因很简单：这是代码。\n   ```",
            "- ~~~text\n  原因很简单：这是代码。\n  ~~~",
        )
        for text in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(diagnostics, [])

        result, diagnostics = self.json_diagnostics(
            "- ```text\n  code sample\n  ```\n\n原因很简单：这是围栏外正文。"
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual([(item["rule_id"], item["line"]) for item in diagnostics], [("vf-013", 5)])

    def test_ordered_markers_interrupt_only_when_they_start_a_new_block(self) -> None:
        examples = (
            "- Use `field\n  2. 原因很简单：代码。\n  name` here.",
            "> - Use `field\n>   2. 原因很简单：代码。\n>   name` here.",
        )
        for text in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(diagnostics, [])

        visible_examples = (
            "- Use `field\n2. 原因很简单：新列表正文。\n  name` here.",
            "- Use `field\n  1. 原因很简单：新列表正文。\n  name` here.",
            "Use `field\n> 2. 原因很简单：新引用正文。\n> name` here.",
        )
        for text in visible_examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual([(item["rule_id"], item["line"]) for item in diagnostics], [("vf-013", 2)])

    def test_reference_definitions_after_protected_blocks_remain_eligible(self) -> None:
        examples = (
            "<!--\ncomment\n-->\n[原因很简单]: /guide\n\nRead [guide][原因很简单].",
            "    code sample\n[原因很简单]: /guide\n\nRead [guide][原因很简单].",
            "<script>code sample</script>\n[原因很简单]: /guide\n\nRead [guide][原因很简单].",
        )
        for text in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(diagnostics, [])

        result, diagnostics = self.json_diagnostics(
            "`code sample`\n[原因很简单]: /guide\n\nRead [guide][原因很简单]."
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual([(item["rule_id"], item["line"]) for item in diagnostics], [("vf-013", 2), ("vf-013", 4)])

    def test_raw_html_definitions_do_not_resolve_reference_labels(self) -> None:
        examples = (
            "<div>\n[原因很简单]: /guide\n</div>\n\nRead [guide][原因很简单].",
            "<section>\n[原因很简单]: /guide\n</section>\n\nRead [guide][原因很简单].",
        )
        for text in examples:
            with self.subTest(text=text):
                result, diagnostics = self.json_diagnostics(text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertEqual([(item["rule_id"], item["line"]) for item in diagnostics], [("vf-013", 2), ("vf-013", 5)])

        result, diagnostics = self.json_diagnostics(
            "<div>\nVisible paragraph.\n</div>\n\n[原因很简单]: /guide\n\nRead [guide][原因很简单]."
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(diagnostics, [])

    def test_rule_catalog_has_stable_unique_ids_and_severities(self) -> None:
        result = self.run_cli("--list-rules", "--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rules = json.loads(result.stdout)["rules"]
        ids = [item["rule_id"] for item in rules]
        self.assertEqual(len(ids), len(set(ids)))
        expected_unslop = {f"unslop-{number}" for number in (3, 5, 7, 8, 9, 13, 16, 18, 19, 20, 22, 23, 24, 25, 26, 30, 31, 32)}
        self.assertEqual(set(ids), {f"vf-{number:03d}" for number in range(1, 33)} | expected_unslop)
        for item in rules:
            self.assertEqual(set(item), {"rule_id", "severity", "message", "source_rule"})
            self.assertTrue(item["message"])
            expected = "FAIL" if item["rule_id"] in {f"vf-{number:03d}" for number in range(1, 18)} else "WARN"
            self.assertEqual(item["severity"], expected)

    def test_json_and_text_use_the_same_findings_and_failure_status(self) -> None:
        text = "原因很简单：正文。\nIn order to utilize this API, read the guide.\n"
        result, diagnostics = self.json_diagnostics(text)
        plain = self.run_cli("-", input_text=text)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(plain.returncode, 1)
        self.assertEqual(
            re.findall(r"^(FAIL|WARN)  -:(\d+):", plain.stdout, flags=re.MULTILINE),
            [(item["severity"], str(item["line"])) for item in diagnostics],
        )
        for item in diagnostics:
            self.assertEqual(set(item), {"rule_id", "severity", "line", "excerpt", "message", "source_rule"})
            self.assertIn(item["excerpt"], plain.stdout)
            self.assertIn(item["message"], plain.stdout)

    def test_multiple_files_are_reported_without_modifying_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            files = [Path(temporary_directory) / "warning.md", Path(temporary_directory) / "failure.md"]
            contents = ["In order to read the file, open it.\n", "原因很简单：正文。\n"]
            for path, content in zip(files, contents):
                path.write_text(content, encoding="utf-8")
            before = {path: path.read_bytes() for path in files}
            result = self.run_cli("--format", "json", *(str(path) for path in files))
            report = json.loads(result.stdout)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(report["failed"])
            self.assertEqual([item["path"] for item in report["files"]], [str(path) for path in files])
            self.assertEqual({path: path.read_bytes() for path in files}, before)

    def test_input_errors_exit_two_without_a_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing = Path(temporary_directory) / "missing.md"
            invalid = Path(temporary_directory) / "invalid.md"
            invalid.write_bytes(b"\xff\xfe")
            for arguments in ((), (str(missing),), (str(invalid),)):
                with self.subTest(arguments=arguments):
                    result = self.run_cli(*arguments)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

    def test_core_returns_immutable_diagnostics(self) -> None:
        # The Skill is distributed as files; this imports the same package as its script adapter.
        sys.path.insert(0, str(SCRIPT.parent))
        try:
            from _voiceforge.lint import lint

            diagnostics = lint("In order to read the file, open it.")
        finally:
            sys.path.remove(str(SCRIPT.parent))
        self.assertIsInstance(diagnostics, tuple)
        self.assertTrue(any(item.rule_id == "unslop-23" for item in diagnostics))
        with self.assertRaises((AttributeError, TypeError)):
            diagnostics[0].severity = "FAIL"


if __name__ == "__main__":
    unittest.main()

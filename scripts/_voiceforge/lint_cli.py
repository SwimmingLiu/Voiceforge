"""Adapt UTF-8 files, stdin, and process output to the lint operation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .lint import RULES, lint, self_test


def main() -> int:
	parser = argparse.ArgumentParser(description="检查中文和英文正文中的已知写作问题。")
	parser.add_argument("files", nargs="*", help="要检查的 UTF-8 文件；使用 - 表示标准输入")
	parser.add_argument("--self-test", action="store_true")
	parser.add_argument("--format", choices=("text", "json"), default="text")
	parser.add_argument("--list-rules", action="store_true", help="输出检测器实际使用的规则目录")
	args = parser.parse_args()
	if args.self_test:
		passed = self_test()
		print("PASS  表达检查自测" if passed else "FAIL  表达检查自测")
		return 0 if passed else 1
	if args.list_rules:
		rules = [
			{"rule_id": rule.rule_id, "severity": rule.severity,
			 "message": rule.message, "source_rule": rule.source_rule}
			for rule in RULES
		]
		if args.format == "json":
			print(json.dumps({"rules": rules}, ensure_ascii=False, indent=2))
		else:
			for rule in rules:
				print(f"{rule['rule_id']}  {rule['severity']}  {rule['source_rule'] or '-'}  {rule['message']}")
		return 0
	if not args.files:
		parser.error("请提供至少一个文件，或使用 --self-test、--list-rules")

	reports = []
	for name in args.files:
		try:
			text = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8")
		except (OSError, UnicodeError) as error:
			# A missing or undecodable input is an input error, not a writing
			# failure. The old traceback obscured that distinction for CLI users.
			print(f"ERROR  {name}: {error}", file=sys.stderr)
			return 2
		reports.append({"path": name, "diagnostics": [asdict(item) for item in lint(text)]})
	failed = any(item["severity"] == "FAIL" for report in reports for item in report["diagnostics"])
	if args.format == "json":
		print(json.dumps({"files": reports, "failed": failed}, ensure_ascii=False, indent=2))
		return 1 if failed else 0

	warned = False
	for report in reports:
		for item in report["diagnostics"]:
			print(f"{item['severity']}  {report['path']}:{item['line']}: {item['excerpt']}\n      {item['message']}")
			warned = warned or item["severity"] == "WARN"
	if not failed and not warned:
		print("PASS  未发现已知的通用写作问题")
	elif not failed:
		print("PASS  没有确定的通用写作问题；请结合语境检查警告")
	return 1 if failed else 0

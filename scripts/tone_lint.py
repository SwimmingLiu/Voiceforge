#!/usr/bin/env python3
"""Report universal writing failures and context-sensitive warnings in Chinese copy."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path


Rule = tuple[re.Pattern[str], str]

RULES: tuple[Rule, ...] = (
    (re.compile(r"先保哪一个|(?:^|[，。！？；：、\s]|先|只|要|得|该|需要|应该|必须|优先)保(?:重点|逻辑|意思|准确|清楚|自然|风格|质量|结构)"), "Use a precise verb such as follow, preserve, or ensure."),
    (re.compile(r"(?:一个|这个)?(?:代码)?问题.{0,8}怎么走"), "State how a code problem is usually handled."),
    (re.compile(r"(?:线索|结果|结论|内容).{0,8}(?:带回来|丢回来|交回来)"), "Name who explains or submits which information."),
    (re.compile(r"(?:先)?把(?:事实|证据).{0,8}(?:找出来|建立(?:起来)?)"), "Name the concrete action, such as inspecting calls, checking configuration, or confirming the implementation."),
    (re.compile(r"(?:逻辑|流程).{0,6}跑(?:到|下去)"), "Use execute or describe the actual call relationship."),
    (re.compile(r"(?:问题|流程|事情|能力|价值).{0,6}落(?:下去|到|地)"), "Describe the concrete implementation or handling action."),
    (re.compile(r"(?:吃下|吞下).{0,10}(?:对话|内容|信息|上下文)"), "Use a precise verb such as read, receive, or contain."),
    (re.compile(r"(?:把)?(?:内容|信息|上下文).{0,8}(?:塞进|塞到|喂给)"), "Use a precise verb such as write, add, or provide."),
    (re.compile(r"跑测试"), "Use the standard expression for running tests."),
    (re.compile(r"(?:搞|弄)(?:顺|清楚|明白|好|完|懂|定|起来|下去)"), "Name the concrete action and result instead of using a vague single-character verb."),
    (re.compile(r"承接(?:需求|任务|工作|内容)"), "Use a precise verb such as handle, own, or implement."),
    (re.compile(r"(?:赋能|撬动|抓手|闭环|沉淀价值|价值落地)"), "Remove promotional jargon and state the concrete effect."),
    (re.compile(r"原因很简单[：:，,。]?"), "Remove the formulaic lead-in and state the actual reason."),
    (re.compile(r"(?:真正重要的是|真正的关键是|这不仅仅?是|从更大的角度看)"), "Remove a summary or uplift that adds no information."),
    (re.compile(r"任务.{0,12}停在[“\"]?代码已经写出来"), "State which checks continue after Codex finishes the code."),
)

WARNING_RULES: tuple[Rule, ...] = (
    (re.compile(r"(?:在当今|在当前).{0,16}(?:时代|背景|环境)下"), "Keep this background only if it supplies necessary information."),
    (re.compile(r"随着.{0,16}(?:不断|持续)(?:发展|演变|变化)"), "Confirm that the claimed change has a concrete relationship to what follows."),
    (re.compile(r"(?:值得注意的是|需要指出的是|毋庸置疑|不可否认的是?)"), "Remove the fixed lead-in unless it performs a real qualification or transition."),
    (re.compile(r"(?:标志着|代表着).{0,24}(?:重要|关键)(?:一步|时刻|转折点)"), "Replace the importance claim with the confirmed action, change, or result."),
    (re.compile(r"为.{1,24}奠定(?:了)?(?:坚实的?)?基础"), "State the concrete condition or result that follows."),
    (re.compile(r"(?:彰显|凸显|体现)(?:了)?.{0,20}(?:重要性|意义|价值)"), "Confirm that the material supports this importance claim."),
    (re.compile(r"(?:业内|行业|专家|观察者)(?:普遍)?(?:认为|指出|表示)"), "Identify the source or remove the vague attribution."),
    (re.compile(r"(?:很多|不少|部分)用户(?:认为|指出|表示|反馈)"), "Keep this user claim only when the task evidence identifies its source."),
    (re.compile(r"(?:有|相关|多项|大量)研究(?:均)?(?:表明|显示|指出)"), "Identify the research source; do not invent one."),
    (re.compile(r"(?:从而确保|进而体现|进一步彰显|反映了更深层次)"), "Keep this analytical tail only when the evidence supports its causality or judgment."),
    (re.compile(r"尽管.{0,24}(?:挑战|困难).{0,24}(?:仍|依然|未来)"), "State the confirmed limitation, result, or next step directly."),
    (re.compile(r"(?:未来可期|迈出(?:了)?(?:至关重要|重要|关键)的一步|开启(?:了)?(?:全新|新的?)篇章)"), "Remove the generic optimistic ending and state the result or next step."),
    (re.compile(r"(?:当然可以|这是一个(?:非常|很)?好的问题|你说得(?:完全)?正确|希望这对(?:你|您)有帮助|如需更多(?:信息|帮助).{0,8}(?:请)?(?:随时)?(?:告诉我|联系我))"), "Remove chat residue or flattery from the reader-facing artifact."),
    (re.compile(r"(?:可能|或许|也许|在一定程度上|在某种程度上).{0,8}(?:可能|或许|也许|在一定程度上|在某种程度上)"), "Merge repeated uncertainty markers while preserving the actual certainty level."),
)


def read_text(name: str) -> str:
    return sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8")


def visible_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    fence_character: str | None = None
    fence_length = 0
    in_script = False
    for number, raw in enumerate(text.splitlines(), start=1):
        if fence_character is not None:
            closing_fence = re.match(
                rf"^\s{{0,3}}{re.escape(fence_character)}{{{fence_length},}}\s*$",
                raw,
            )
            if closing_fence:
                fence_character = None
                fence_length = 0
            continue
        opening_fence = re.match(r"^\s{0,3}(`{3,}|~{3,})", raw)
        if opening_fence:
            marker = opening_fence.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
            continue
        if re.search(r"<(script|style)\b", raw, flags=re.IGNORECASE):
            in_script = True
        if in_script:
            if re.search(r"</(script|style)>", raw, flags=re.IGNORECASE):
                in_script = False
            continue
        without_tags = re.sub(r"<[^>]+>", " ", raw)
        without_code = re.sub(r"`[^`]*`", " ", without_tags)
        visible = html.unescape(re.sub(r"\s+", " ", without_code)).strip()
        if visible:
            lines.append((number, visible))
    return lines


def find_matches(text: str, rules: tuple[Rule, ...]) -> list[tuple[int, str, str]]:
    matches: list[tuple[int, str, str]] = []
    for line_number, line in visible_lines(text):
        for pattern, fix in rules:
            if pattern.search(line):
                matches.append((line_number, line, fix))
    return matches


def find_failures(text: str) -> list[tuple[int, str, str]]:
    return find_matches(text, RULES)


def find_warnings(text: str) -> list[tuple[int, str, str]]:
    return find_matches(text, WARNING_RULES)


def self_test() -> int:
    bad = "\n".join((
        "模型不知道先保哪一个。",
        "一个问题平时可以怎么走。",
        "Explorer 把线索带回来。",
        "先把事实找出来。",
        "这个流程怎么跑下去。",
        "让这个能力落下去。",
        "子 Agent 直接吃下整段对话。",
        "把内容塞进提示词。",
        "让模型跑测试。",
        "先把这段流程搞顺。",
        "这个功能负责承接需求。",
        "这套方案可以赋能开发团队。",
        "原因很简单：它读取了错误的文件。",
        "真正重要的是，我们理解了工具的边界。",
        "任务不必停在“代码已经写出来”。",
    ))
    good = "\n".join((
        "模型必须先遵循事实准确这项要求。",
        "一个代码问题通常怎么处理。",
        "Explorer 把查到的调用和配置说明清楚。",
        "查看调用和配置，确认当前实现。",
        "这个流程由主 Agent 继续执行。",
        "实现这项能力。",
        "子 Agent 读取与任务有关的对话。",
        "把内容写进提示词。",
        "让模型运行测试。",
        "这个功能负责处理需求。",
        "这套方法会根据情况变化，没有固定流程。",
        "这不是固定流程，而是一套会根据情况变化的方法。",
        "使用 Codex 时，先说明任务；完成后，再查看改动。",
    ))
    warning_bad = "\n".join((
        "在当今快速变化的时代下，团队需要保持敏捷。",
        "随着人工智能技术的不断发展，工具越来越多。",
        "值得注意的是，这项功能已经发布。",
        "这标志着产品迈出了重要一步。",
        "这次更新为后续增长奠定了坚实的基础。",
        "这体现了自动化的重要性。",
        "业内普遍认为，这种方案更可靠。",
        "不少用户反馈，新的设计更自然。",
        "有研究表明，这种方法可以提高效率。",
        "这项改动进一步彰显了产品价值。",
        "尽管面临诸多挑战，团队未来仍将继续前进。",
        "产品完成升级，未来可期。",
        "希望这对你有帮助。",
        "这项政策可能在一定程度上或许会影响结果。",
    ))
    warning_good = "\n".join((
        "2025 年 3 月接口升级后，旧版客户端无法继续登录。",
        "清华大学发布的报告显示，样本中的响应时间缩短了 12%。",
        "产品支持批量处理和离线模式。",
        "这项政策可能影响结果。",
    ))
    failures = find_failures(bad)
    warnings = find_warnings(warning_bad)
    failure_lines = {line_number for line_number, _, _ in failures}
    warning_lines = {line_number for line_number, _, _ in warnings}
    if (
        failure_lines != set(range(1, len(bad.splitlines()) + 1))
        or find_failures(good)
        or warning_lines != set(range(1, len(warning_bad.splitlines()) + 1))
        or find_warnings(warning_good)
    ):
        print("FAIL  tone lint self-test")
        for failure in failures:
            print(f"      {failure}")
        for warning in warnings:
            print(f"      {warning}")
        return 1
    print("PASS  tone lint self-test")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Chinese copy for known universal writing issues.")
    parser.add_argument("files", nargs="*", help="UTF-8 files to scan, or - for stdin")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.files:
        parser.error("provide one or more files, or use --self-test")
    failed = False
    warned = False
    for name in args.files:
        content = read_text(name)
        for line_number, line, fix in find_failures(content):
            print(f"FAIL  {name}:{line_number}: {line}\n      {fix}")
            failed = True
        for line_number, line, fix in find_warnings(content):
            print(f"WARN  {name}:{line_number}: {line}\n      {fix}")
            warned = True
    if not failed and not warned:
        print("PASS  no known universal writing failures")
    elif not failed:
        print("PASS  no confirmed universal writing failures; review warnings")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

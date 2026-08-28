#!/usr/bin/env python3
"""检查中文内容中的通用写作问题，并报告需要结合语境判断的警告。"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path


Rule = tuple[re.Pattern[str], str]

RULES: tuple[Rule, ...] = (
    (re.compile(r"先保哪一个|(?:^|[，。！？；：、\s]|先|只|要|得|该|需要|应该|必须|优先)保(?:重点|逻辑|意思|准确|清楚|自然|风格|质量|结构)"), "改用遵循、保留、确保等准确动词。"),
    (re.compile(r"(?:一个|这个)?(?:代码)?问题.{0,8}怎么走"), "直接说明通常如何处理代码问题。"),
    (re.compile(r"(?:线索|结果|结论|内容).{0,8}(?:带回来|丢回来|交回来)"), "说明由谁解释或提交哪些信息。"),
    (re.compile(r"(?:先)?把(?:事实|证据).{0,8}(?:找出来|建立(?:起来)?)"), "写明具体动作，例如查看调用、检查配置或确认实现。"),
    (re.compile(r"(?:逻辑|流程).{0,6}跑(?:到|下去)"), "改用执行，或直接说明实际调用关系。"),
    (re.compile(r"(?:问题|流程|事情|能力|价值).{0,6}落(?:下去|到|地)"), "说明具体的实现或处理动作。"),
    (re.compile(r"(?:吃下|吞下).{0,10}(?:对话|内容|信息|上下文)"), "改用读取、接收、包含等准确动词。"),
    (re.compile(r"(?:把)?(?:内容|信息|上下文).{0,8}(?:塞进|塞到|喂给)"), "改用写入、添加、提供等准确动词。"),
    (re.compile(r"跑测试"), "使用“运行测试”等规范表达。"),
    (re.compile(r"(?:搞|弄)(?:顺|清楚|明白|好|完|懂|定|起来|下去)"), "不要使用含义模糊的单字动词，写明具体动作和结果。"),
    (re.compile(r"承接(?:需求|任务|工作|内容)"), "改用处理、负责、实现等准确动词。"),
    (re.compile(r"(?:赋能|撬动|抓手|闭环|沉淀价值|价值落地)"), "删除宣传式术语，直接说明具体效果。"),
    (re.compile(r"原因很简单[：:，,。]?"), "删除套话，直接说明实际原因。"),
    (re.compile(r"(?:真正重要的是|真正的关键是|这不仅仅?是|从更大的角度看)"), "删除没有新增信息的总结或拔高。"),
    (re.compile(r"(?:总而言之|综上所述)[，,：:]?(?:我们)?(?:已经|可以|能够)?(?:理解|明白|完成|实现|看出|看到)"), "删除替正文宣布结束的句子，直接在最后一项事实或判断处结束。"),
    (re.compile(r"通过以上(?:方法|步骤|分析|介绍)[，,]?(?:我们)?(?:已经|可以|能够)?(?:完成|实现|理解|看出|看到)"), "删除复述前文完成状态的收尾；只有新增结果时才保留。"),
    (re.compile(r"任务.{0,12}停在[“\"]?代码已经写出来"), "说明代码完成后还需要继续执行哪些检查。"),
)

WARNING_RULES: tuple[Rule, ...] = (
    (re.compile(r"(?:在当今|在当前).{0,16}(?:时代|背景|环境)下"), "只有这段背景提供必要信息时才保留。"),
    (re.compile(r"随着.{0,16}(?:不断|持续)(?:发展|演变|变化)"), "确认所声称的变化与后文存在具体关系。"),
    (re.compile(r"(?:值得注意的是|需要指出的是|毋庸置疑|不可否认的是?)"), "固定引导语没有承担限定或过渡作用时应删除。"),
    (re.compile(r"(?:标志着|代表着).{0,24}(?:重要|关键)(?:一步|时刻|转折点)"), "用已确认的动作、变化或结果替代重要性声称。"),
    (re.compile(r"为.{1,24}奠定(?:了)?(?:坚实的?)?基础"), "直接说明后续的具体条件或结果。"),
    (re.compile(r"(?:彰显|凸显|体现)(?:了)?.{0,20}(?:重要性|意义|价值)"), "确认材料确实支持这项重要性判断。"),
    (re.compile(r"(?:业内|行业|专家|观察者)(?:普遍)?(?:认为|指出|表示)"), "写明具体来源，或删除模糊归因。"),
    (re.compile(r"(?:很多|不少|部分)用户(?:认为|指出|表示|反馈)"), "只有任务证据能够指出来源时，才保留这项用户声称。"),
    (re.compile(r"(?:有|相关|多项|大量)研究(?:均)?(?:表明|显示|指出)"), "写明研究来源，不得编造。"),
    (re.compile(r"(?:从而确保|进而体现|进一步彰显|反映了更深层次)"), "只有证据支持相应因果或判断时，才保留这段分析。"),
    (re.compile(r"尽管.{0,24}(?:挑战|困难).{0,24}(?:仍|依然|未来)"), "直接说明已确认的限制、结果或下一步。"),
    (re.compile(r"(?:未来可期|迈出(?:了)?(?:至关重要|重要|关键)的一步|开启(?:了)?(?:全新|新的?)篇章)"), "删除泛泛的乐观结尾，改写为结果或下一步。"),
    (re.compile(r"(?:当然可以|这是一个(?:非常|很)?好的问题|你说得(?:完全)?正确|希望这对(?:你|您)有帮助|如需更多(?:信息|帮助).{0,8}(?:请)?(?:随时)?(?:告诉我|联系我))"), "删除面向读者成稿中的聊天残留或恭维。"),
    (re.compile(r"(?:可能|或许|也许|在一定程度上|在某种程度上).{0,8}(?:可能|或许|也许|在一定程度上|在某种程度上)"), "合并重复的不确定表达，并保留实际的不确定程度。"),
    (re.compile(r"(?:确认业务条件|样本收口|知识矩阵|能力闭环)"), "写清楚主体、实际动作和对象；如果无法具体说明，就删除抽象管理术语。"),
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
        "总而言之，我们已经理解了这套方法。",
        "通过以上步骤，我们完成了全部工作。",
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
        "先完成样本收口，再建立知识矩阵。",
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
        print("FAIL  表达检查自测")
        for failure in failures:
            print(f"      {failure}")
        for warning in warnings:
            print(f"      {warning}")
        return 1
    print("PASS  表达检查自测")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="检查中文内容中已知的通用写作问题。")
    parser.add_argument("files", nargs="*", help="要检查的 UTF-8 文件；使用 - 表示标准输入")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.files:
        parser.error("请提供至少一个文件，或使用 --self-test")
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
        print("PASS  未发现已知的通用写作问题")
    elif not failed:
        print("PASS  没有确定的通用写作问题；请结合语境检查警告")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

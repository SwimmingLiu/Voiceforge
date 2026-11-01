"""Inspect reader-facing prose once and return report-only writing diagnostics."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Literal


Severity = Literal["FAIL", "WARN"]


@dataclass(frozen=True)
class Rule:
	rule_id: str
	severity: Severity
	pattern: re.Pattern[str]
	message: str
	source_rule: str | None = None
	english_only: bool = False


@dataclass(frozen=True)
class Diagnostic:
	rule_id: str
	severity: Severity
	line: int
	excerpt: str
	message: str
	source_rule: str | None = None


# Keep the existing blocking policy during extraction. Unslop signals need
# context, so the additional rules below only request review.
RULES: tuple[Rule, ...] = (
	Rule("vf-001", "FAIL", re.compile(r"先保哪一个|(?:^|[，。！？；：、\s]|先|只|要|得|该|需要|应该|必须|优先)保(?:重点|逻辑|意思|准确|清楚|自然|风格|质量|结构)"), "改用遵循、保留、确保等准确动词。"),
	Rule("vf-002", "FAIL", re.compile(r"(?:一个|这个)?(?:代码)?问题.{0,8}怎么走"), "直接说明通常如何处理代码问题。"),
	Rule("vf-003", "FAIL", re.compile(r"(?:线索|结果|结论|内容).{0,8}(?:带回来|丢回来|交回来)"), "说明由谁解释或提交哪些信息。"),
	Rule("vf-004", "FAIL", re.compile(r"(?:先)?把(?:事实|证据).{0,8}(?:找出来|建立(?:起来)?)"), "写明具体动作，例如查看调用、检查配置或确认实现。"),
	Rule("vf-005", "FAIL", re.compile(r"(?:逻辑|流程).{0,6}跑(?:到|下去)"), "改用执行，或直接说明实际调用关系。"),
	Rule("vf-006", "FAIL", re.compile(r"(?:问题|流程|事情|能力|价值).{0,6}落(?:下去|到|地)"), "说明具体的实现或处理动作。"),
	Rule("vf-007", "FAIL", re.compile(r"(?:吃下|吞下).{0,10}(?:对话|内容|信息|上下文)"), "改用读取、接收、包含等准确动词。"),
	Rule("vf-008", "FAIL", re.compile(r"(?:把)?(?:内容|信息|上下文).{0,8}(?:塞进|塞到|喂给)"), "改用写入、添加、提供等准确动词。"),
	Rule("vf-009", "FAIL", re.compile(r"跑测试"), "使用“运行测试”等规范表达。"),
	Rule("vf-010", "FAIL", re.compile(r"(?:搞|弄)(?:顺|清楚|明白|好|完|懂|定|起来|下去)"), "不要使用含义模糊的单字动词，写明具体动作和结果。"),
	Rule("vf-011", "FAIL", re.compile(r"承接(?:需求|任务|工作|内容)"), "改用处理、负责、实现等准确动词。"),
	Rule("vf-012", "FAIL", re.compile(r"(?:赋能|撬动|抓手|闭环|沉淀价值|价值落地)"), "删除宣传式术语，直接说明具体效果。"),
	Rule("vf-013", "FAIL", re.compile(r"原因很简单[：:，,。]?"), "删除套话，直接说明实际原因。"),
	Rule("vf-014", "FAIL", re.compile(r"(?:真正重要的是|真正的关键是|这不仅仅?是|从更大的角度看)"), "删除没有新增信息的总结或拔高。"),
	Rule("vf-015", "FAIL", re.compile(r"(?:总而言之|综上所述)[，,：:]?(?:我们)?(?:已经|可以|能够)?(?:理解|明白|完成|实现|看出|看到)"), "删除替正文宣布结束的句子，直接在最后一项事实或判断处结束。"),
	Rule("vf-016", "FAIL", re.compile(r"通过以上(?:方法|步骤|分析|介绍)[，,]?(?:我们)?(?:已经|可以|能够)?(?:完成|实现|理解|看出|看到)"), "删除复述前文完成状态的收尾；只有新增结果时才保留。"),
	Rule("vf-017", "FAIL", re.compile(r"任务.{0,12}停在[“\"]?代码已经写出来"), "说明代码完成后还需要继续执行哪些检查。"),
	Rule("vf-018", "WARN", re.compile(r"(?:在当今|在当前).{0,16}(?:时代|背景|环境)下"), "只有这段背景提供必要信息时才保留。"),
	Rule("vf-019", "WARN", re.compile(r"随着.{0,16}(?:不断|持续)(?:发展|演变|变化)"), "确认所声称的变化与后文存在具体关系。"),
	Rule("vf-020", "WARN", re.compile(r"(?:值得注意的是|需要指出的是|毋庸置疑|不可否认的是?)"), "固定引导语没有承担限定或过渡作用时应删除。"),
	Rule("vf-021", "WARN", re.compile(r"(?:标志着|代表着).{0,24}(?:重要|关键)(?:一步|时刻|转折点)"), "用已确认的动作、变化或结果替代重要性声称。"),
	Rule("vf-022", "WARN", re.compile(r"为.{1,24}奠定(?:了)?(?:坚实的?)?基础"), "直接说明后续的具体条件或结果。"),
	Rule("vf-023", "WARN", re.compile(r"(?:彰显|凸显|体现)(?:了)?.{0,20}(?:重要性|意义|价值)"), "确认材料确实支持这项重要性判断。"),
	Rule("vf-024", "WARN", re.compile(r"(?:业内|行业|专家|观察者)(?:普遍)?(?:认为|指出|表示)"), "写明具体来源，或删除模糊归因。"),
	Rule("vf-025", "WARN", re.compile(r"(?:很多|不少|部分)用户(?:认为|指出|表示|反馈)"), "只有任务证据能够指出来源时，才保留这项用户声称。"),
	Rule("vf-026", "WARN", re.compile(r"(?:有|相关|多项|大量)研究(?:均)?(?:表明|显示|指出)"), "写明研究来源，不得编造。"),
	Rule("vf-027", "WARN", re.compile(r"(?:从而确保|进而体现|进一步彰显|反映了更深层次)"), "只有证据支持相应因果或判断时，才保留这段分析。"),
	Rule("vf-028", "WARN", re.compile(r"尽管.{0,24}(?:挑战|困难).{0,24}(?:仍|依然|未来)"), "直接说明已确认的限制、结果或下一步。"),
	Rule("vf-029", "WARN", re.compile(r"(?:未来可期|迈出(?:了)?(?:至关重要|重要|关键)的一步|开启(?:了)?(?:全新|新的?)篇章)"), "删除泛泛的乐观结尾，改写为结果或下一步。"),
	Rule("vf-030", "WARN", re.compile(r"(?:当然可以|这是一个(?:非常|很)?好的问题|你说得(?:完全)?正确|希望这对(?:你|您)有帮助|如需更多(?:信息|帮助).{0,8}(?:请)?(?:随时)?(?:告诉我|联系我))"), "删除面向读者成稿中的聊天残留或恭维。"),
	Rule("vf-031", "WARN", re.compile(r"(?:可能|或许|也许|在一定程度上|在某种程度上).{0,8}(?:可能|或许|也许|在一定程度上|在某种程度上)"), "合并重复的不确定表达，并保留实际的不确定程度。"),
	Rule("vf-032", "WARN", re.compile(r"(?:确认业务条件|样本收口|知识矩阵|能力闭环)"), "写清楚主体、实际动作和对象；如果无法具体说明，就删除抽象管理术语。"),
	Rule("unslop-3", "WARN", re.compile(r"\b(?:highlighting|ensuring|reflecting|showcasing|fostering)\s+(?:the|a|an|our|your|that)\b", re.I), "检查分词短语是否说明实际动作或有来源的结果。", "unslop:3"),
	Rule("unslop-5", "WARN", re.compile(r"\b(?:experts? (?:believe|say|argue)|industry reports? suggest|some critics? argue|studies (?:show|suggest))\b", re.I), "写明具体来源，或删除模糊归因。", "unslop:5"),
	Rule("unslop-7", "WARN", re.compile(r"\b(?:additionally|crucial|delve|enduring|enhanc(?:e|es|ed|ing)|fostering|garner|interplay|intricate|pivotal|showcase|testament|vibrant)\b|\bunderscores? the (?:importance|need|value)\b", re.I), "检查这个词是否增加准确含义，否则使用常见词或删除。", "unslop:7"),
	Rule("unslop-8", "WARN", re.compile(r"\b(?:serves? as|stands? as|boasts?)\b", re.I), "直接使用 is、has 或具体动词。", "unslop:8"),
	Rule("unslop-9", "WARN", re.compile(r"\bnot (?:just|only)\b[^.!?\n]{1,160}\bbut\b", re.I), "直接说明结论；只有真实对比需要这项限定时才保留。", "unslop:9"),
	Rule("unslop-13", "WARN", re.compile("\u2014"), "用句号或逗号分开表达，受保护的原文标点除外。", "unslop:13"),
	Rule("unslop-16", "WARN", re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+(?:\*\*[^*\n]+[:：]\*\*|\*\*[^*\n]+\*\*[:：])"), "检查加粗标签是否重复后面的内容，没有新增信息时改成正文。", "unslop:16"),
	Rule("unslop-18", "WARN", re.compile(r"^\s*(?:#{1,6}\s+|[-+*]\s+|\d+[.)]\s+)[^\n]*[\U0001f300-\U0001faff\u2600-\u27bf]"), "删除标题或列表中的装饰性 emoji，保留有实际含义的符号。", "unslop:18"),
	Rule("unslop-19", "WARN", re.compile("[\u2018\u2019\u201c\u201d]"), "英文使用直引号，受保护的原文标点除外。", "unslop:19", english_only=True),
	Rule("unslop-20", "WARN", re.compile(r"\b(?:i hope this helps|let me know if|of course|certainly|found the smoking gun)\b", re.I), "删除面向读者成稿中的聊天残留。", "unslop:20"),
	Rule("unslop-22", "WARN", re.compile(r"\b(?:great question|you['’]re absolutely right)\b", re.I), "删除恭维，直接回答或陈述事实。", "unslop:22"),
	Rule("unslop-23", "WARN", re.compile(r"\b(?:in order to|due to the fact that|it is important to note that)\b", re.I), "使用 to、because，或删除没有信息的引导语。", "unslop:23"),
	Rule("unslop-24", "WARN", re.compile(r"\b(?:could|might|may)\s+(?:potentially|possibly)\b|\b(?:potentially|possibly)\s+(?:potentially|possibly)\b", re.I), "合并重复的不确定词，保留事实需要的限定。", "unslop:24"),
	Rule("unslop-25", "WARN", re.compile(r"\b(?:the future looks bright|exciting times (?:lie )?ahead)\b", re.I), "用具体结果或下一步替代泛泛的乐观结尾。", "unslop:25"),
	Rule("unslop-26", "WARN", re.compile(r"\b(?:north star|flywheel|api surface|gold[- ]plating|endgame|paradigm shift)\b", re.I), "写明对象、动作或机制，检查比喻是否增加了准确含义。", "unslop:26"),
	Rule("unslop-30", "WARN", re.compile(r"\b(?:significantly|dramatically|remarkably)\s+(?:improv\w*|enhanc\w*|reduc\w*|increas\w*|decreas\w*)\b", re.I), "给出有来源的测量，或直接说明实际变化。", "unslop:30"),
	Rule("unslop-31", "WARN", re.compile(r"\b(?:utiliz(?:e|es|ed|ing)|leverag(?:e|es|ed|ing)|facilitat(?:e|es|ed|ing)|numerous|in the event that)\b", re.I), "优先使用 use、help、many 或 if，保留有明确含义的专业用法。", "unslop:31"),
	Rule("unslop-32", "WARN", re.compile(r"\b(?:(?:a )?dial worth turning|wire it or delete it)\b", re.I), "用实际参数或操作替代修辞和口号。", "unslop:32"),
)


def _blank(value: str) -> str:
	"""Remove nonprose while keeping source lines and token boundaries."""
	return re.sub(r"[^\r\n]", " ", value)


def _escaped(text: str, position: int) -> bool:
	start = position
	while start and text[start - 1] == "\\":
		start -= 1
	return (position - start) % 2 == 1


_QUOTE_MARKER = re.compile(r" {0,3}>[ \t]?")
_LIST_MARKER = re.compile(r" {0,3}(?:(?P<bullet>[-+*])|(?P<number>\d{1,9})[.)])[ \t]+")
_FENCE = re.compile(r" {0,3}(?P<marker>`{3,}|~{3,})(?P<info>[^\r\n]*)")
_DEFINITION = re.compile(r"^ {0,3}\[((?:\\.|[^\[\]\\\r\n]){1,999})\]:[ \t]*(.*?)[\r\n]*$")
_TAG_CONTENT = r'''(?:[^>"']|"[^"]*"|'[^']*')*'''
_TAG = re.compile(rf"</?[a-zA-Z][a-zA-Z0-9-]*(?:[ \t\r\n]+{_TAG_CONTENT})?/?>", re.I)
_RAW_BLOCK_TAG = re.compile(r" {0,3}</?(?:address|article|aside|blockquote|body|caption|center|col|colgroup|dd|details|dialog|div|dl|dt|fieldset|figcaption|figure|footer|form|h[1-6]|head|header|hr|html|iframe|legend|li|main|menu|nav|ol|p|section|summary|table|tbody|td|tfoot|th|thead|title|tr|ul)(?:[ \t\r\n>/]|$)", re.I)
_INLINE_TOKEN = re.compile(
	r"(?P<comment><!--)"
	rf"|(?P<html><(?P<tag>script|style|pre|code)\b{_TAG_CONTENT}>)"
	rf"|(?P<markup></?[a-zA-Z]{_TAG_CONTENT}>)"
	r"|(?P<ticks>(?<!`)`+(?!`))", re.I,
)
_HIDDEN_START = re.compile(rf"<!--|<(?:script|style|pre|code)\b{_TAG_CONTENT}>", re.I)
_BREAK = re.compile(r" {0,3}(?:=+|-+|(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})[ \t]*\r?\n?")


@dataclass(frozen=True)
class _Prefix:
	kind: Literal["quote", "list"]
	width: int = 0


@dataclass(frozen=True)
class _Container:
	parts: tuple[_Prefix, ...] = ()


@dataclass(frozen=True)
class _Line:
	owner: _Container
	body: str
	content: int
	continued: bool
	new_container: bool


@dataclass(frozen=True)
class _Block:
	start: int
	end: int
	kind: Literal["prose", "literal", "hidden"]


@dataclass(frozen=True)
class _Definition:
	start: int
	end: int
	label: str


@dataclass(frozen=True)
class _Paragraph:
	start: int
	end: int
	owner: _Container


@dataclass(frozen=True)
class _Fence:
	start: int
	end: int
	owner: _Container
	marker: str


@dataclass(frozen=True)
class _Indented:
	start: int
	end: int
	owner: _Container


@dataclass(frozen=True)
class _Literal:
	start: int
	end: int
	owner: _Container


def _read_line(raw: str, owner: _Container, *, expand: bool = True, paragraph: bool = False) -> _Line:
	position = 0
	parts: list[_Prefix] = []
	for index, prefix in enumerate(owner.parts):
		if prefix.kind == "quote":
			match = _QUOTE_MARKER.match(raw, position)
			if match is None:
				break
			position = match.end()
		else:
			space = re.match(r"[ \t]*", raw[position:])[0]
			width = len(space.expandtabs(4))
			if width < prefix.width:
				if not raw[position:].strip() and all(p.kind == "list" for p in owner.parts[index:]):
					return _Line(owner, raw[position:], position, True, False)
				break
			consumed = 0
			while len(space[:consumed].expandtabs(4)) < prefix.width:
				consumed += 1
			position += consumed
		parts.append(prefix)
	continued = len(parts) == len(owner.parts)
	new_container = False
	if expand:
		while True:
			quote = _QUOTE_MARKER.match(raw, position)
			if quote:
				parts.append(_Prefix("quote"))
				position = quote.end()
				new_container = True
				continue
			item = _LIST_MARKER.match(raw, position)
			if not item or _BREAK.fullmatch(raw[position:]):
				break
			can_interrupt = item["number"] in {None, "1"} and bool(raw[item.end():].strip())
			# Ordered markers other than 1 continue an existing paragraph,
			# including inside a list. A new container can start its own list.
			if paragraph and continued and not new_container and not can_interrupt:
				break
			parts.append(_Prefix("list", len(raw[position:item.end()].expandtabs(4))))
			position = item.end()
			new_container = True
	return _Line(_Container(tuple(parts)), raw[position:], position, continued, new_container)


def _opening_fence(body: str) -> str | None:
	match = _FENCE.match(body)
	if match and not (match["marker"][0] == "`" and "`" in match["info"]):
		return match["marker"]
	return None


def _starts_block(body: str) -> bool:
	return bool(
		not body.strip()
		or re.match(r"^ {0,3}#{1,6}(?:[ \t]+|$)", body)
		or _BREAK.fullmatch(body)
		or _opening_fence(body)
		or _HIDDEN_START.match(body.lstrip(" "))
		or _RAW_BLOCK_TAG.match(body)
	)


def _inline_ranges(text: str, start: int, end: int, *, code: bool = True) -> tuple[tuple[int, int], ...]:
	ranges: list[tuple[int, int]] = []
	position = start
	while match := _INLINE_TOKEN.search(text, position, end):
		if _escaped(text, match.start()):
			position = match.end()
			continue
		if match["ticks"] is not None:
			if not code:
				position = match.end()
				continue
			closing = re.compile(rf"(?<!`){re.escape(match[0])}(?!`)").search(text, match.end(), end)
			if closing is None:
				position = match.end()
				continue
			finish = closing.end()
		elif match["comment"] is not None:
			closing = re.compile(r"-->").search(text, match.end())
			finish = closing.end() if closing else len(text)
		elif match["html"] is not None:
			closing = re.compile(rf"</{match['tag']}\s*>", re.I).search(text, match.end())
			finish = closing.end() if closing else len(text)
		else:
			finish = match.end()
		ranges.append((match.start(), finish))
		position = finish
	return tuple(ranges)


def _definition_at(lines: list[str], index: int, info: _Line) -> tuple[str, int] | None:
	match = _DEFINITION.match(info.body)
	if not match or not _reference_id(match[1]):
		return None
	last = index
	tail = match[2]
	if not tail.strip() and index + 1 < len(lines):
		next_line = _read_line(lines[index + 1], info.owner, expand=False)
		if next_line.continued and not _starts_block(next_line.body) and not re.match(r"^(?: {4}|\t)", next_line.body):
			tail = next_line.body
			last += 1
	if not _reference_destination(tail):
		return None
	if last + 1 < len(lines):
		title = _read_line(lines[last + 1], info.owner, expand=False)
		if title.continued and re.fullmatch(r''' {0,3}(?:".*"|'.*'|\(.*\))[ \t]*\r?\n?''', title.body):
			if _reference_destination(tail.rstrip() + " " + title.body.strip()):
				last += 1
	return _reference_id(match[1]), last


def _block_events(text: str) -> tuple[_Block | _Definition, ...]:
	# One reducer owns block lifetime and definition eligibility. Protected
	# contents cannot reopen a paragraph or change another consumer's owner.
	lines = text.splitlines(keepends=True)
	starts = []
	position = 0
	for raw in lines:
		starts.append(position)
		position += len(raw)
	starts.append(len(text))
	events: list[_Block | _Definition] = []
	index = 0
	cursor = 0
	owner = _Container()
	active: _Paragraph | _Fence | _Indented | _Literal | None = None
	if lines and lines[0].lstrip("\ufeff").strip() == "---":
		for closing in range(1, len(lines)):
			if lines[closing].strip() in {"---", "..."}:
				cursor = starts[closing + 1]
				index = closing + 1
				events.append(_Block(0, cursor, "hidden"))
				break
	while index < len(lines):
		line_end = starts[index + 1]
		raw = text[cursor:line_end]
		if cursor > starts[index]:
			info = _Line(owner, raw, 0, True, False)
		else:
			info = _read_line(raw, active.owner if active else owner, expand=not isinstance(active, (_Fence, _Indented, _Literal)), paragraph=isinstance(active, _Paragraph))
		if isinstance(active, _Fence):
			if info.continued:
				closing = re.fullmatch(rf" {{0,3}}{re.escape(active.marker[0])}{{{len(active.marker)},}}[ \t]*\r?\n?", info.body)
				active = _Fence(active.start, line_end, active.owner, active.marker)
				if closing:
					events.append(_Block(active.start, active.end, "hidden"))
					active = None
				cursor, index = line_end, index + 1
				continue
			events.append(_Block(active.start, active.end, "hidden"))
			owner, active = info.owner, None
			continue
		if isinstance(active, _Indented):
			if info.continued and (not info.body.strip() or re.match(r"^(?: {4}|\t)", info.body)):
				active = _Indented(active.start, line_end, active.owner)
				cursor, index = line_end, index + 1
				continue
			events.append(_Block(active.start, active.end, "hidden"))
			owner, active = info.owner, None
			continue
		if isinstance(active, _Literal):
			if info.continued and info.body.strip():
				active = _Literal(active.start, line_end, active.owner)
				cursor, index = line_end, index + 1
				continue
			extent = max((end for _, end in _inline_ranges(text, active.start, active.end, code=False)), default=active.end)
			if extent > active.end:
				active = _Literal(active.start, extent, active.owner)
				cursor = extent
				while index < len(lines) and starts[index + 1] <= cursor:
					index += 1
				continue
			events.append(_Block(active.start, active.end, "literal"))
			owner, active = info.owner, None
			continue
		if isinstance(active, _Paragraph):
			continuation = not info.new_container and not _starts_block(info.body)
			if continuation:
				active = _Paragraph(active.start, line_end, active.owner)
				owner = active.owner
				cursor, index = line_end, index + 1
				continue
			# Inline HTML can contain block-looking lines. Consume that lexical
			# unit before allowing its hidden content to trigger a block change.
			ranges = _inline_ranges(text, active.start, active.end)
			extent = max((end for _, end in ranges), default=active.end)
			if extent > active.end:
				active = _Paragraph(active.start, extent, active.owner)
				cursor = extent
				while index < len(lines) and starts[index + 1] <= cursor:
					index += 1
				continue
			events.append(_Block(active.start, active.end, "prose"))
			owner, active = info.owner, None
			continue
		owner = info.owner
		if not info.body.strip():
			events.append(_Block(cursor, line_end, "prose"))
			cursor, index = line_end, index + 1
			continue
		definition = _definition_at(lines, index, info) if cursor == starts[index] else None
		if definition:
			label, last = definition
			events.append(_Definition(cursor, starts[last + 1], label))
			cursor, index = starts[last + 1], last + 1
			continue
		fence = _opening_fence(info.body)
		if fence:
			active = _Fence(cursor, line_end, owner, fence)
			cursor, index = line_end, index + 1
			continue
		if re.match(r"^(?: {4}|\t)", info.body):
			active = _Indented(cursor, line_end, owner)
			cursor, index = line_end, index + 1
			continue
		leading = len(info.body) - len(info.body.lstrip(" "))
		hidden = _HIDDEN_START.match(info.body, leading) if leading <= 3 else None
		if hidden and not _escaped(text, cursor + info.content + hidden.start()):
			begin = cursor + info.content + hidden.start()
			ranges = _inline_ranges(text, begin, cursor + info.content + hidden.end())
			end = ranges[0][1]
			events.append(_Block(cursor, end, "hidden"))
			cursor = end
			while index < len(lines) and starts[index + 1] <= cursor:
				index += 1
			continue
		if _RAW_BLOCK_TAG.match(info.body) or _TAG.fullmatch(info.body.strip()):
			active = _Literal(cursor, line_end, owner)
			cursor, index = line_end, index + 1
			continue
		if re.match(r"^ {0,3}#{1,6}(?:[ \t]+|$)", info.body) or _BREAK.fullmatch(info.body):
			events.append(_Block(cursor, line_end, "prose"))
			cursor, index = line_end, index + 1
			continue
		active = _Paragraph(cursor, line_end, owner)
		cursor, index = line_end, index + 1
	if active:
		kind = "prose" if isinstance(active, _Paragraph) else "literal" if isinstance(active, _Literal) else "hidden"
		events.append(_Block(active.start, active.end, kind))
	return tuple(events)


def _visible_source(text: str, events: tuple[_Block | _Definition, ...]) -> str:
	definitions = frozenset(event.label for event in events if isinstance(event, _Definition))
	parts: list[str] = []
	for event in events:
		piece = text[event.start:event.end]
		if isinstance(event, _Definition) or event.kind == "hidden":
			parts.append(_blank(piece))
			continue
		ranges = _inline_ranges(text, event.start, event.end, code=event.kind == "prose")
		position = event.start
		masked: list[str] = []
		for start, end in ranges:
			masked.append(text[position:start])
			masked.append(_blank(text[start:min(end, event.end)]))
			position = min(end, event.end)
		masked.append(text[position:event.end])
		piece = "".join(masked)
		if event.kind == "prose":
			piece = _mask_reference_labels(_mask_link_targets(piece), definitions)
		parts.append(piece)
	return "".join(parts)


def _mask_link_targets(text: str) -> str:
	# Mask targets rather than whole lines so labels and adjacent prose are
	# still checked, even when the URL contains parentheses.
	parts: list[str] = []
	position = 0
	labels: list[int] = []
	for match in re.finditer(r"[\[\]]", text):
		if match.start() < position or _escaped(text, match.start()):
			continue
		if match[0] == "[":
			labels.append(match.start())
			continue
		if not labels:
			continue
		labels.pop()
		if text[match.end() : match.end() + 1] != "(":
			continue
		depth = 1
		end = match.end() + 1
		while end < len(text) and depth:
			if text[end] == "\\":
				end += 2
				continue
			if text[end] == "(":
				depth += 1
			elif text[end] == ")":
				depth -= 1
			end += 1
		if depth:
			continue
		parts.append(text[position : match.start()])
		parts.append(_blank(text[match.start() : end]))
		position = end
	parts.append(text[position:])
	return "".join(parts)


def _reference_id(label: str) -> str:
	return re.sub(r"[ \t\r\n]+", " ", label).strip(" \t\r\n").casefold()


def _reference_destination(tail: str) -> bool:
	value = tail.strip(" \t\r\n")
	if not value:
		return False
	position = 0
	if value.startswith("<"):
		position = 1
		while position < len(value) and (value[position] != ">" or _escaped(value, position)):
			if value[position] in "\r\n" or (value[position] == "<" and not _escaped(value, position)):
				return False
			position += 1
		if position == len(value):
			return False
		position += 1
	else:
		depth = 0
		while position < len(value) and value[position] not in " \t\r\n":
			character = value[position]
			if not _escaped(value, position):
				if character in "<>":
					return False
				if character == "(":
					depth += 1
				elif character == ")":
					depth -= 1
					if depth < 0:
						return False
			position += 1
		if depth:
			return False
	remainder = value[position:]
	return not remainder or bool(re.fullmatch(r'''[ \t]+(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\((?:\\.|[^)\\])*\))[ \t]*''', remainder))


def _mask_reference_labels(text: str, definitions: frozenset[str]) -> str:
	# Bracket syntax alone does not make a reference. Unknown IDs remain
	# visible prose and must still reach the writing rules.
	pattern = re.compile(r"(\[(?:\\.|[^\]\\\r\n])+\])\[((?:\\.|[^\[\]\\\r\n]){0,999})\]")
	def replace(match: re.Match[str]) -> str:
		label = match[2] or match[1][1:-1]
		if _reference_id(label) not in definitions or _escaped(text, match.start()):
			return match[0]
		return match[1] + _blank(match[0][len(match[1]):])
	return pattern.sub(replace, text)


def _visible_lines(text: str) -> tuple[tuple[int, str], ...]:
	# Lint deliberately has a separate parser from memory_text: changing
	# statistical extraction would change profiles and historical evaluations.
	text = _visible_source(text, _block_events(text))
	text = re.sub(r"\b(?:https?://|mailto:|www\.)[^\s<>。！？；，]+", lambda m: _blank(m[0]), text, flags=re.I)
	lines = []
	for number, raw in enumerate(text.splitlines(), start=1):
		visible = re.sub(r"\s+", " ", html.unescape(raw)).strip()
		if visible:
			lines.append((number, visible))
	return tuple(lines)


def lint(text: str) -> tuple[Diagnostic, ...]:
	"""Inspect visible prose once. Return at most one finding per rule and line."""
	findings: list[Diagnostic] = []
	for number, line in _visible_lines(text):
		for rule in RULES:
			if rule.english_only and re.search(r"[\u3400-\u9fff]", line):
				continue
			if rule.pattern.search(line):
				findings.append(Diagnostic(rule.rule_id, rule.severity, number, line, rule.message, rule.source_rule))
	# Preserve the text CLI's FAIL-before-WARN convention. Both renderers use
	# these same objects and never run a second detection pass.
	return tuple(sorted(findings, key=lambda item: item.severity != "FAIL"))


def self_test() -> bool:
	bad = lint("原因很简单：这套方案可以赋能团队。")
	english = lint("In order to utilize the API, read the guide.")
	return (
		{item.rule_id for item in bad} >= {"vf-012", "vf-013"}
		and {item.rule_id for item in english} >= {"unslop-23", "unslop-31"}
		and not lint("编译器检查字段名称。The compiler checks field names.")
		and not lint("`原因很简单`\n[测试说明](https://example.invalid/跑测试)")
	)

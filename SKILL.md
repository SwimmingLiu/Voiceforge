---
name: voiceforge
description: 面向中文和英文读者内容的起草、改写、润色和定向编辑工具。适用于新增、删除、替换、重组、压缩、扩写、纠错、去重和按反馈修改内容。通用写作层始终生效；个人风格层只在用户明确要求并提供已确认样本时启用。不要用于只改代码逻辑、配置值、文件名或纯机器数据的任务。
---

# Voiceforge

`Voiceforge` 是本 Skill 的唯一正式名称。

Voiceforge 包含两层能力：

1. 通用写作层每次都读取并执行 [references/universal-writing-rules.md](references/universal-writing-rules.md)，完成后运行 `scripts/tone_lint.py`。
2. 只有用户明确要求个性化，并提供独立风格工作区或当前任务中的已确认样本时，才启用个人风格层。个人样本只影响语气、节奏、结构和稳定偏好。

执行顺序为：`任务证据 → 可选个性化 → 通用复核 → 确定性检查`。没有个人证据时，只跳过个性化，不得跳过通用写作层。

## 不依赖本地知识库

普通写作不得查找、要求或假设存在任何个人知识库。不要自动扫描当前目录之外的 vault、Obsidian 仓库、文章库或用户资料目录，也不要调用外部的知识库定位器。

个人风格数据只能来自以下两种渠道：

- 用户在当前任务中主动提供并明确确认代表其当前表达的文本；
- 用户明确指定的 Voiceforge 独立风格工作区。

风格工作区不是知识库。用户尚未创建工作区时，继续使用完整通用写作层完成普通任务，不要打断任务要求用户配置个性化能力。只有用户明确要求建立个人风格时，才可建议运行：

```bash
python3 <skill-dir>/scripts/voice_memory.py init --workspace <目录>
```

不得读取开发者本机的个人风格资料作为其他用户的默认样本。

## 执行通用写作层

每次起草或编辑面向读者的内容前，都要完整读取 [references/universal-writing-rules.md](references/universal-writing-rules.md)。这些规则覆盖任务范围、成稿边界、事实边界、叙述身份、措辞、句子、结构、标题、格式、常见 AI 表达、内容类型、英文写作、删除语义和完成检查。

在规划和起草时执行一次；引入个人表达后再执行一次。个人风格不得覆盖事实准确性、用户最新要求、删除语义、隐私、引用或有效格式约束。

内置检查同时支持中文和英文。修复 `FAIL`，结合语境复核 `WARN`。没有提示不代表事实或语义已经正确；强行分组、术语轮换和省略含义仍需人工判断。规则编号、JSON 输出和正文排除范围见 [检测器参考](references/lint-reference.md)。

## 选择写作路径

- 没有个性化请求时，直接根据任务事实和通用规则完成内容，不检索个人资料。
- 用户要求个性化但没有已确认样本时，继续完成可完成的写作部分，并说明无法声称复现个人风格。只有在个人风格本身是任务目标时，才请用户提供样本或初始化工作区。
- 存在合格个人证据时，从任务事实规划内容，用已确认样本和偏好调整表达，然后执行完整通用复核和检查。

## 保持证据分离

| 证据渠道 | 可以影响 | 不可以影响 |
| --- | --- | --- |
| 当前任务证据 | 事实、例子、结论 | 个人风格，除非也被确认为风格样本 |
| 已确认个人样本 | 语气、节奏、结构、稳定偏好 | 当前任务的新事实 |
| 人类写作参考 | 维护通用规则时的研究判断 | 当前成稿、个人身份、观点、经历或独特措辞 |
| 反馈和负面样本 | 用户明确希望保留或避免的表达 | 事实和未经确认的长期规则 |

不得把标记为 `secret` 的来源、样本、草稿或反馈写入风格记忆。不得把第三方写作平均成用户风格。模型草稿、未审核访谈、简历或仅发布在用户名下的文件，都不能自动成为已确认个人样本。

## 使用独立风格工作区

只有用户明确指定工作区时，才可运行相关命令。新文档和新调用统一使用 `--workspace`；`--vault` 只用于兼容旧版本。

先校验工作区：

```bash
python3 <skill-dir>/scripts/voice_memory.py validate --workspace <目录>
```

`healthy: true` 只表示数据符合格式，不代表个人风格已经成熟。只有机器返回 `readiness.activation.ready: true` 时，才能称个人风格配置成熟。

按任务范围检索风格上下文：

```bash
python3 <skill-dir>/scripts/voice_memory.py context \
  --workspace <目录> --language zh --genre technical-article \
  --audience public --intended-use unknown --query "主题和写作目的"
```

只允许 `personal`、`confirmed_preferences` 和相容的 `negative` 证据影响表达。`human_reference` 及其中的 `techniques` 只供维护者研究，不得直接进入成稿。`candidate` 样本不得作为候补证据。

默认 `context` 和 `prepare` 返回空的 `human_reference` 列表，不包含第三方摘录或方法卡片。维护通用写作规则时，显式使用 `context --research` 检索研究材料，并继续遵守用途许可。`--human-limit` 只设置研究数量，不能打开研究模式。

检索结果为 `match_quality: fallback` 时，说明语言、体裁、受众、渠道或目的不完全匹配，应降低其影响。第三方参考必须遵守返回的 `license_id`、`rights` 和 `usage_notes`；即使许可相容，也不能把来源事实或独特段落带入当前任务。

## 起草或修改

1. 从当前请求和用户提供的资料中整理事实、可编辑原文、约束和不确定项。不得从风格样本补充事实。
2. 判断语言、体裁、受众、渠道、目的和用途。用途可取 `private`、`noncommercial`、`commercial` 或 `unknown`。
3. 根据事实关系安排信息顺序。存在合格个人证据时才调整个人表达，否则直接按通用规则起草。
4. 不得复制参考资料中的长段落或具有辨识度的措辞。除非用户明确要求分析，不要模仿第三方作者。
5. 使用个人风格后，可运行 `analyze` 比较草稿与已确认配置：

```bash
python3 <skill-dir>/scripts/voice_memory.py analyze \
  --workspace <目录> --file <草稿> --language zh \
  --genre technical-article --audience public
```

6. 重新完整执行通用写作规则，检查事实、隐私、引用、受众、格式和用户要求。
7. 对文件运行 `scripts/tone_lint.py`；聊天中的短文本通过标准输入传给 `-`。修复所有 `FAIL`，结合语境检查每个 `WARN`，然后重新运行，直到没有 `FAIL`。

返回用户要求的成稿。除非用户询问，或未解决的不确定性会影响安全使用，不要把检索诊断、配置状态、过程说明或自我评价写进成稿。

## 从反馈中学习

只有在用户提交修改、明确接受最终稿、明确拒绝某种表达或直接陈述长期偏好时，才能记录信号。用户没有回复不等于接受。

反馈、负面样本和长期偏好的写入都必须先预览，再在获得对应的用户确认后使用写入标志。不得把模型未修改的输出作为训练材料。重复反馈只能提出候选偏好，不能自动升级成长期规则。

长期偏好的具体记录和替代规则见 [references/preference-memory.md](references/preference-memory.md)，样本格式见 [references/corpus-schema.md](references/corpus-schema.md)，成熟度评估见 [references/evaluation.md](references/evaluation.md)。

## 完成标准

完成前必须确认：事实和限定语没有被改变；没有加入任务范围之外的内容或把生成要求写进成稿；用户要求的删除内容及其否定改写已经完全移除；未使用未经确认的个人样本；普通任务未读取个人知识库；内容通过通用规则复核；确定性检查没有 `FAIL`。

## 与 oil-tone 的兼容关系

Voiceforge 已内置原 `oil-tone` 的通用写作规则和确定性检查。`oil-tone` 可以继续作为旧调用入口，但不是 Voiceforge 的运行依赖，也不得改变通用层与个人层的证据边界。

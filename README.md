<div align="center">
  <h1>Voiceforge</h1>
  <p><em>减少 AI 腔，保留真实、清楚的表达。</em></p>
</div>

Voiceforge 是一个面向中文和英文写作的 Agent Skill。它包含一套始终生效的通用写作规则，也支持按需启用个人风格。普通写作不需要知识库、Obsidian 或任何个人资料；只有用户明确要求个性化时，才会读取用户主动提供并确认过的样本。

<p align="center">
  <img src="okassets/voiceforge-intro-zh.png" alt="Voiceforge 减少 AI 腔，并按需学习个人表达" width="100%" />
</p>

## 适用场景

Voiceforge 可以处理这些任务：

- 起草、改写、润色和校对面向读者的中文或英文内容；
- 按要求新增、删除、替换、移动或重组内容，同时保留未受影响的部分；
- 减少空泛铺垫、宣传式表达、重复总结和其他常见 AI 写作痕迹；
- 在不改变事实、立场和约束的前提下改善句子、段落和结构；
- 根据用户明确确认的样本和偏好调整表达；
- 记录用户确认过的修改和拒绝项，供后续相似任务使用。

## 两层工作方式

| 层级 | 是否必需 | 作用 |
| --- | --- | --- |
| 通用写作层 | 始终启用 | 约束事实、语义、措辞、句子、结构、格式和删除操作，并运行确定性检查 |
| 个人风格层 | 按需启用 | 使用用户明确提供并确认的样本、偏好和反馈调整语气、节奏和结构 |

没有个人样本时，Voiceforge 会直接使用通用写作层完成任务，不会要求用户先搭建知识库，也不会自动扫描开发者或用户本机的其他目录。

## 通用写作层检查什么

通用写作层不只检查固定的 AI 表达，还会核对需要结合语境判断的事实和结构问题：

| 范围 | 检查内容 |
| --- | --- |
| 事实和数字 | 保留来源中的数值与计算口径；自行换算不一致时指出差异，不静默替换 |
| 第三方信息 | 公开点名第三方负面结果前取得确认；没有确认时使用中性、可核验的表述 |
| 读者语境 | 专有名词首次出现时说明它是什么、与当前内容有什么关系，并就近放置已有可靠链接 |
| 句子关系 | 检查主语、动作和对象，避免动作主体同时进入自己的连接、整合或合并对象 |
| 口语节奏 | 保留承担语法和节奏作用的必要虚词，把补足虚词与删除多余语气词分开处理 |
| 段落分工 | 避免相邻段落重复同一数字、事实或结论，让事实段和判断段分别承担作用 |
| 标题证据 | 区分整篇标题和文内小标题，并逐项核对标题中的第一人称、动作、时间、数量、结果和判断 |
| 动词选择 | 检查含义模糊且可以自然替换的单字动作词，同时避免为了换词制造生硬表达 |

完整规则见 [通用写作规则](references/universal-writing-rules.md)，本次与 oil-tone 的语义对照见 [通用改写规则补充记录](references/oil-tone-rule-gap.md)。

## 快速开始

把本仓库链接到 Agent Skills 目录：

```bash
mkdir -p ~/.agents/skills
ln -sfn /path/to/Voiceforge ~/.agents/skills/voiceforge
```

普通写作到这里就可以开始使用，无需额外配置。

完成文件后，可运行通用表达检查：

```bash
python3 scripts/tone_lint.py /path/to/draft.md
```

检查聊天中的短文本时，可从标准输入传入：

```bash
printf '%s' '待检查的内容' | python3 scripts/tone_lint.py -
```

## 可选的个人风格工作区

个人风格数据保存在一个独立工作区中。这个工作区由 Voiceforge 自行初始化，不属于用户的知识库，也不要求采用 Obsidian 目录结构。

```bash
python3 scripts/voice_memory.py init --workspace ~/.voiceforge
```

初始化命令只会在指定目录中创建 Voiceforge 所需的索引、配置和记录目录。它不会读取其他个人文件。

校验工作区：

```bash
python3 scripts/voice_memory.py validate --workspace ~/.voiceforge
```

按任务范围检索已确认的个人风格证据：

```bash
python3 scripts/voice_memory.py context \
  --workspace ~/.voiceforge \
  --language zh --genre technical-article --audience public \
  --intended-use unknown --query "主题和写作目的"
```

旧版的 `--vault` 参数仍可使用，但只作为 `--workspace` 的兼容别名。新项目应统一使用 `--workspace`。

## 个性化边界

Voiceforge 把不同证据分开处理：

| 证据 | 可以影响 | 不可以影响 |
| --- | --- | --- |
| 当前任务资料 | 事实、例子、结论 | 个人风格，除非同一内容也被确认为风格样本 |
| 已确认个人样本 | 语气、节奏、结构、稳定偏好 | 当前任务的新事实 |
| 人类写作参考 | 通用规则的维护研究 | 当前成稿、用户身份、观点或经历 |
| 反馈和负面样本 | 用户明确希望保留或避免的表达 | 事实和未经确认的长期规则 |

候选样本不会自动参与生成。文件归属、账号名称、发布位置和用户未回复都不能证明某份文本代表用户风格。涉及个人风格的持久化操作必须由用户明确确认。

## 工作流程

1. 从当前请求和用户提供的资料中整理事实、约束和不确定项。
2. 读取并执行 [通用写作规则](references/universal-writing-rules.md)。
3. 只有在用户明确要求个性化且提供了风格工作区时，才检索已确认的个人证据。
4. 从任务事实规划内容；个人样本只影响表达，不补充事实。
5. 完成草稿后再次执行通用规则，并检查事实、隐私、引用、受众和格式。
6. 运行 `scripts/tone_lint.py`，修复所有失败项，并结合语境判断警告项。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `SKILL.md` | Skill 的运行规则、证据边界和执行流程 |
| `agents/openai.yaml` | 展示信息和默认提示词 |
| `references/architecture.md` | 架构、数据流和隔离边界 |
| `references/corpus-schema.md` | 风格工作区中的语料索引格式 |
| `references/evaluation.md` | 个性化能力的评估门槛 |
| `references/oil-tone-rule-gap.md` | 与 oil-tone 对照后补入的通用规则及来源 |
| `references/preference-memory.md` | 长期写作偏好的记录规则 |
| `references/universal-writing-rules.md` | 完整的通用写作规则 |
| `scripts/voice_memory.py` | 风格工作区、检索、反馈和评估命令行工具 |
| `scripts/tone_lint.py` | 通用表达的确定性检查工具 |
| `tests/` | 回归测试 |

## 运行测试

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## 与 oil-tone 的关系

Voiceforge 已内置原先由 `oil-tone` 提供的通用写作规则和确定性检查。`oil-tone` 仅用于兼容旧调用，不是 Voiceforge 的运行依赖。

## 限制

Voiceforge 不会微调模型，不会把整套文章库放进提示词，也不会复刻在世作者的独特文风。风格样本不能作为事实来源，语义相似也不能证明风格相似。个人数据只保存在用户明确指定的独立工作区中。

## 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。

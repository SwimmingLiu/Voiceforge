# 风格工作区语料索引格式

## 位置和格式

使用以下命令创建独立风格工作区：

```bash
python3 scripts/voice_memory.py init --workspace <目录>
```

默认索引位于：

`05-areas/writing-style/Corpus Registry.md`

这个路径只是 Voiceforge 工作区内部布局，不要求用户搭建知识库或采用 Obsidian。索引在 `jsonl` 代码块中每行保存一个 JSON 对象。文件路径相对于工作区根目录；Markdown 文件是唯一正式记录，生成的统计和检索结果可以随时重建。

## 必填字段

| 字段 | 允许值或含义 |
| --- | --- |
| `id` | 稳定且唯一的标识符 |
| `path` | 工作区内的相对 Markdown 路径 |
| `role` | `personal`、`human-reference`、`negative` 或 `holdout` |
| `status` | `candidate`、`confirmed` 或 `rejected` |
| `authorship` | `user`、`third-party`、`mixed` 或 `unknown` |
| `approval` | `user-confirmed`、`curator-confirmed` 或 `unreviewed` |
| `language` | 通常为 `zh`、`en` 或 `mixed` |
| `genre` | 稳定体裁标签，例如 `technical-article` |
| `audience` | 稳定受众标签，例如 `public` 或 `internal` |
| `weight` | `0` 到 `2` 之间的数字，默认值为 `1` |
| `origin_claim` | `user-authored`、`pre-generative-ai`、`attributed-human`、`human-edited`、`mixed` 或 `unknown` |
| `origin_confidence` | `high`、`medium`、`low` 或 `unknown` |

可选字段包括 `channel`、`purpose`、`author`、`rights`、`license_id`、`allowed_uses`、`origin_basis`、`confirmation_evidence`、`notes` 和 `created`。

已确认的人类参考必须填写作者、来源依据、权利、许可和非空用途列表。用途值包括 `private`、`noncommercial` 和 `commercial`。已确认个人样本和留出样本必须声明 `user-authored`，来源置信度至少为 `medium`，并由 `confirmation_evidence` 指向工作区内存在的确认记录。

任何 frontmatter 中声明 `sensitivity: secret` 的文档都不得登记为写作记忆。校验和升级命令必须在检索或写入前拒绝这类文档。

长期偏好不放在语料索引中，而是按 [preference-memory.md](preference-memory.md) 写入 `Voice Profile.md`。语料索引描述文档，偏好记录描述用户确认的写作行为。

## 人类写作方法索引

方法卡片保存在：

`05-areas/writing-style/Human Technique Index.md`

每张启用卡片在 `jsonl` 代码块中占一行：

```jsonl
{"kind":"human-technique","id":"technique-example","corpus_id":"human-example","status":"confirmed","approval":"curator-confirmed","collection_id":"example-book","techniques":["先解释机制存在的原因，再说明实现","把例外放在对应规则附近"],"technique_basis":"维护者根据保存的来源归纳，仅作检索线索。","created":"2026-08-15"}
```

`corpus_id` 必须指向已确认的 `human-reference`。`techniques` 最多包含 12 个短标签，每个标签不超过 120 个字符。`technique_basis` 必须说明这些标签是维护者归纳。`collection_id` 用于把同一书籍、栏目或系列中的材料归组，以增加检索结果的多样性。

## 角色和状态

- `personal`：可以影响用户表达。已确认条目必须同时满足 `authorship: user`、`approval: user-confirmed` 和 `status: confirmed`。
- `human-reference`：只供维护通用写作规则时研究，不得直接影响当前成稿、个人身份或任务事实。
- `negative`：用户明确拒绝或已知不希望出现的表达，只作对比证据。
- `holdout`：用于评估的已确认个人文本，`context` 永不返回。
- `candidate`：可以被发现，但不能进入正常检索。
- `rejected`：保留用于追溯，不进入正向检索。

## 示例

```jsonl
{"id":"personal-article-01","path":"06-output/published/Agent Memory.md","role":"personal","status":"confirmed","authorship":"user","approval":"user-confirmed","origin_claim":"user-authored","origin_confidence":"high","confirmation_evidence":"02-sources/personal-confirmation.md","language":"zh","genre":"technical-article","audience":"public","weight":1.2,"rights":"owned"}
{"id":"human-reference-01","path":"02-sources/How Compaction Works.md","role":"human-reference","status":"confirmed","authorship":"third-party","approval":"curator-confirmed","origin_claim":"attributed-human","origin_confidence":"medium","origin_basis":"具名发布者、原始页面和维护者审核","language":"en","genre":"technical-article","audience":"technical-practitioner","weight":1.0,"author":"Example Publisher","rights":"仅供公开参考，不得复用段落","license_id":"public-reference-no-reuse","allowed_uses":["private"]}
```

## 分类规则

1. 先记录来源，再判断风格作用。
2. 不得根据文件名、账号归属、作者 frontmatter 或发布位置推断个人作者身份。
3. 用户确认前，经过模型生成或编辑的文本保持 `mixed` 或 `candidate`。
4. 第三方摘录必须简短，不得复制具有辨识度的措辞。
5. 一份文档包含明显不同的体裁或作者时，应拆成多个条目。
6. 样本足够后，将约 10%–20% 的成熟个人样本保留为 `holdout`。
7. `catalog` 的来源判断只用于提出候选，不代表人工确认。
8. 只使用升级命令确认样本，并先预览、后写入。
9. 方法卡片与语料索引分开保存，不能在没有跨体裁回归证据时升级为通用硬规则。

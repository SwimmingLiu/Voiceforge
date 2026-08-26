# oil-tone 通用改写规则补充记录

比较日期：2026-08-27。

上游基线为 oil-tone 提交 [`b9b250a`](https://github.com/oil-oil/oil-tone/commit/b9b250ad2ffd09802beec3606981ebcf7b4b87e2)，本地基线为补充前的 [universal-writing-rules.md](universal-writing-rules.md)。比较按语义进行：同义规则不计入差集，oil 的个人身份和微信公众号固定问候等个人规则不计入通用规则。以下规则已于 2026-08-27 补入 Voiceforge。

## 已补充的规则

| 规则 | 上游依据 | 补充内容 |
| --- | --- | --- |
| 衍生数字服从来源口径 | 百分比、倍数等由原始数字换算得到时，采用来源给出的数值并注明口径；自行换算与来源不一致时以来源为准。[上游第 30 行](https://github.com/oil-oil/oil-tone/blob/b9b250ad2ffd09802beec3606981ebcf7b4b87e2/skills/oil-tone/SKILL.md#L30) | 保留来源原值和口径；自行换算不一致时指出差异，不静默替换。 |
| 公开点名第三方负面结果前先确认 | 即使来源可靠，公开成稿要点名第三方产品的负面结果时，也先确认是否点名；默认中性罗列，不展开批评。[上游第 31 行](https://github.com/oil-oil/oil-tone/blob/b9b250ad2ffd09802beec3606981ebcf7b4b87e2/skills/oil-tone/SKILL.md#L31) | 没有明确确认时使用中性、可核验的表述，不扩展批评。 |
| 专有名词首次出现时补足读者语境 | 面向陌生读者时，第一次出现产品、项目、功能、Skill 或命令，要说明它是什么、与本文有什么关系；已有可靠链接时把链接放在首次介绍处，没有来源时不猜链接。[上游第 32 行](https://github.com/oil-oil/oil-tone/blob/b9b250ad2ffd09802beec3606981ebcf7b4b87e2/skills/oil-tone/SKILL.md#L32) | 首次出现时补充定义、与当前内容的关系和已有可靠链接。 |
| 避免动作主体进入自己的合并对象 | `A 把 X 和 Y 连接、整合或合并起来` 时，A 不能同时出现在 X、Y 中，避免形成自己处理自己的循环关系。[上游第 42 行](https://github.com/oil-oil/oil-tone/blob/b9b250ad2ffd09802beec3606981ebcf7b4b87e2/skills/oil-tone/SKILL.md#L42) | 增加主体与对象集合重叠检查，并要求省略宾语时仍可自然补出。 |
| 口语成稿保留必要虚词 | `在、的、了、的时候` 等虚词承担语法和节奏作用；不要为了压缩而让朗读发紧。补足必要虚词和删除多余语气词是两种操作。[上游第 45 行](https://github.com/oil-oil/oil-tone/blob/b9b250ad2ffd09802beec3606981ebcf7b4b87e2/skills/oil-tone/SKILL.md#L45) | 明确区分必要虚词和多余语气词，并要求朗读检查。 |
| 相邻段落不重复同一数字、事实或结论 | 事实段与反应、判断段分工；感想段直接写反应，不复述前段数字，收尾总结除外。[上游第 51 行](https://github.com/oil-oil/oil-tone/blob/b9b250ad2ffd09802beec3606981ebcf7b4b87e2/skills/oil-tone/SKILL.md#L51) | 增加相邻段落去重和段落分工规则。 |
| 整篇标题中的事实元素逐项取证 | 标题里的第一人称、动作、时间、数量、结果和判断都要有直接证据；只有材料证明作者开发、制作、设计、新增或开源某物时，才能使用相应所有权表达；第三方产品只写已证实的使用、测试、发现和判断。[上游第 57 行](https://github.com/oil-oil/oil-tone/blob/b9b250ad2ffd09802beec3606981ebcf7b4b87e2/skills/oil-tone/SKILL.md#L57) | 增加标题事实逐项取证、所有权表达和第三方产品行为边界。 |

## 已细化的既有原则

这些规则原本已有概括性原则，本次补充了更明确的执行边界：

| 规则 | 差异 |
| --- | --- |
| 可替换的单字动作词 | 上游明确点出 `写、看、查、改、做、用、点、跑` 等词只有在含义模糊且可自然替换时才改，并给出对应准确动词。[上游第 39–40 行](https://github.com/oil-oil/oil-tone/blob/b9b250ad2ffd09802beec3606981ebcf7b4b87e2/skills/oil-tone/SKILL.md#L39-L40) 本次已把这些词补成检查对象，同时保留“不机械替换”的边界。 |
| 区分整篇标题与文内小标题 | 上游要求小标题主要充当内容标签，整篇标题则可以表达有证据支持的动作、变化、结果或作者判断。[上游第 56 行](https://github.com/oil-oil/oil-tone/blob/b9b250ad2ffd09802beec3606981ebcf7b4b87e2/skills/oil-tone/SKILL.md#L56) 本次已明确区分两类标题的作用。 |

## 检查脚本

oil-tone 与 Voiceforge 的 `tone_lint.py` 各包含 29 个正则检测模式，语义上一一对应。Voiceforge 对第一条 `保重点、保逻辑` 等模式增加了前置边界，减少普通词组中的误报。上游没有需要补入本地的确定性检查模式，本次新增内容都属于需要结合语境人工判断的规则。

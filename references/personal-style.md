# 个人风格工作区

用户明确要求个性化后，可使用他们在当前任务中确认的样本。需要跨任务检索时，工作区必须由用户明确指定。用户要求建立工作区时，可在指定目录初始化。

```bash
python3 <skill-dir>/scripts/voice_memory.py init --workspace <目录>
```

## 按任务检索

```bash
python3 <skill-dir>/scripts/voice_memory.py context \
  --workspace <目录> --language zh --genre technical-article \
  --audience public --query "主题和写作目的"
```

按请求填写已知的语言、体裁、受众、渠道（`--channel`）和目的（`--purpose`）。需要标注用途时，用 `--intended-use` 指定 `private`、`noncommercial`、`commercial` 或 `unknown`。`--vault` 是旧版的兼容参数。

- 用 `personal`、`confirmed_preferences` 和相容的 `negative` 调整表达。优先使用范围相符的证据。查看 `fallback_fields` 判断候补证据是否仍适用。
- 样本可以影响语气、节奏、结构和已确认的表达偏好。任务事实来自用户当前提供的材料。候选、留出样本和模型原样生成的草稿排除在风格证据之外。
- 在已指定的工作区中有明确事实包时，可使用 `prepare --fact-packet <路径>` 加同样的任务参数。用 `fact_evidence` 核对事实，用 `style_context` 选择表达证据。摘录被截断时查看原始材料。

`context` 和 `prepare` 的成稿路径检查可入选的记录。`human_reference` 固定为空。工作区语法有误或入选证据不可用时，从任务材料完成有依据的部分。

## 管理与验证

- 初始化后、排查数据问题或需要核对成熟度时，运行 `python3 <skill-dir>/scripts/voice_memory.py validate --workspace <目录>` 检查整个工作区。`healthy: true` 表示数据健康。`readiness.activation.ready: true` 才支持个人配置成熟声明。`shadow` 下仍可按任务授权使用合格样本。
- 维护通用规则时，可用 `context --research` 查找第三方参考，按 `license_id`、`rights` 和 `usage_notes` 使用。`--human-limit` 调整研究结果数量。第三方摘录和方法卡片用于维护研究。
- 如需分析草稿与风格配置的差异，可运行 `analyze --workspace <目录> --file <草稿>`，辅以已知的语言、体裁和受众。统计用于诊断，事实和范围保真由内容核对。
- 当前反馈立即适用于当前任务。将用户提交的修改、明确接受或拒绝的表达、长期偏好写入工作区时，先预览并取得对应的确认。重复反馈可提出候选偏好，由用户决定是否记录。参见[语料格式](corpus-schema.md)、[长期偏好](preference-memory.md)和[成熟度评估](evaluation.md)。

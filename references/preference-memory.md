# 长期写作偏好

## 保存位置

已确认偏好保存在独立风格工作区的：

`05-areas/writing-style/Voice Profile.md`

普通写作不需要这个文件，也不会自动寻找知识库中的同名文档。用户需要持久化个人风格时，先用 `voice_memory.py init --workspace <目录>` 创建工作区。

在人类可读说明之后，用一个追加式 `jsonl` 代码块保存记录：

```jsonl
{"kind":"preference","id":"preference-example","text":"先解释机制，再给例子。","status":"confirmed","approval":"user-confirmed","basis":"explicit-user-statement","evidence":[],"language":"zh","genre":"technical-article","audience":"public","created":"2026-08-15"}
```

`text` 必须是具体、可执行的写作要求。范围只能窄到证据支持的程度。不得把任务事实、推测身份或模型生成的句子写成个人偏好。

## 升级门槛

| 依据 | 证据要求 | 确认要求 |
| --- | --- | --- |
| `explicit-user-statement` | 有证据链接时保留链接 | 用户明确确认 |
| `repeated-feedback` | 至少引用 3 条不同的已确认反馈记录 | 用户审核并确认推断出的偏好 |

先预览：

```bash
python3 <skill-dir>/scripts/voice_memory.py promote-preference \
  --workspace <目录> --text "<长期偏好>" \
  --language zh --genre technical-article --audience public \
  --basis repeated-feedback \
  --evidence <反馈-1> --evidence <反馈-2> --evidence <反馈-3>
```

只有获得确认后，才能增加 `--user-confirmed --write`。用户沉默、没有继续修改或模型自行判断都不能代替确认。记录 ID 是确定的，重复执行相同写入应保持幂等。

## 替代过期偏好

不要直接改写旧记录。用 `--supersedes <旧偏好-id>` 写入新偏好，让检索忽略被替代记录。保留旧记录，便于日后追溯偏好在何时、为何变化。

## 检索和应用顺序

从 `context` 返回的 `confirmed_preferences` 中读取偏好。精确范围匹配优先于部分匹配和候补匹配。发生冲突时按以下顺序处理：

1. 当前任务中用户最新的明确要求；
2. 范围匹配且由用户直接确认的偏好；
3. 已确认的个人样本；
4. 通用写作规则。

人类写作参考只供维护通用层时研究，不能直接影响任务成稿，也不能作为个人风格的候补来源。偏好记录不能作为事实证据。

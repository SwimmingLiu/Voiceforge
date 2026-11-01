# Voiceforge

Voiceforge 是面向中文与英文内容的 Agent Skill，把任务材料、写作规则和表达检查组织成一套起草与审校流程。普通写作即可使用，个人风格按需启用。

<p align="center">
  <img src="assets/voiceforge-intro-zh.png" alt="Voiceforge：从事实出发，把话写清楚。通用写作规则与表达检查始终启用，个人风格按需启用。" width="100%" />
</p>

## 从材料到成稿

一段话改得流畅，仍可能偏离任务要求，例如加入材料之外的事实、把删除操作写回正文，或让个人风格覆盖原意。Voiceforge 围绕这些编辑边界组织写作流程。

通用规则先约束改动范围和事实依据，再处理表达与格式。Agent 据此起草、改写和复核，Python 检测器补充可重复执行的表达检查。事实是否有依据、修改是否保留原意，仍由 Agent 结合任务材料判断。

## 开始使用

需要支持 Agent Skills 的宿主。命令行工具依赖 Python 3.10 或更高版本，仅使用标准库。

克隆完整仓库，并将它链接到宿主的 Skills 目录。下面以 `~/.agents/skills` 为例：

```bash
git clone https://github.com/SwimmingLiu/Voiceforge.git
cd Voiceforge
mkdir -p ~/.agents/skills
ln -s "$PWD" ~/.agents/skills/voiceforge
```

在宿主中调用：

```text
使用 $voiceforge，把这段产品介绍改成可以直接发布的中文成稿。保留事实，删除空泛表达。
```

需要检查已有文件时，在仓库目录运行：

```bash
python3 scripts/tone_lint.py /path/to/draft.md
python3 scripts/tone_lint.py --format json /path/to/draft.md
```

检测器扫描纯文本和 Markdown 中的已知中英文表达模式，跳过代码、链接地址和 HTML 注释等非正文内容，保留原始行号和稳定规则编号。它只报告诊断，不修改输入文件，文本和 JSON 输出共用同一套结果。

`FAIL` 使进程返回退出码 `1`，`WARN` 需要结合上下文复核。自动化接入、输出约定和完整规则见 [检测器参考](references/lint-reference.md)。

## 需要个人风格时

普通写作只使用通用层，不需要本地知识库，也不会自动扫描个人资料。希望跨任务保留个人表达时，再创建独立工作区，加入经过用户确认的样本与偏好。

```bash
python3 scripts/voice_memory.py init --workspace ~/.voiceforge
```

个人证据只影响语气、节奏与结构，不能替代当前任务的事实。候选样本不参与生成，写入样本、偏好和反馈需要对应的用户确认。数据格式与确认要求见 [语料索引格式](references/corpus-schema.md)。

第三方参考只用于维护研究。默认 `context` 和 `prepare` 不返回参考摘录或方法卡片。维护通用写作规则时，用 `context --research` 显式检索，结果仍按用途许可筛选。

## 实现与开发

宿主从 [SKILL.md](SKILL.md) 和 [通用写作规则](references/universal-writing-rules.md) 读取工作流程。`scripts/tone_lint.py` 执行表达检查，`scripts/voice_memory.py` 管理风格证据、检索与评估。

命令行入口负责参数和输出。内部的 `evidence.py` 统一处理工作区写入，`memory.py` 计算检索与报告，`lint.py` 独立执行表达检测。模块位于 `scripts/_voiceforge/`，分发时保留完整 Skill 目录。职责、依赖关系与设计取舍见 [架构说明](references/architecture.md)。

在仓库目录运行回归测试：

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

GitHub Actions 在推送、PR 和手动触发时运行同一套测试，覆盖 Python 3.10 和 3.14。配置见 [CI 工作流](.github/workflows/ci.yml)。

---

项目采用 [MIT 许可证](LICENSE)。写作规则参考了 [oil-tone](https://github.com/oil-oil/oil-tone)。

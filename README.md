<div align="center">
  <h1>Voiceforge</h1>
  <p>按通用写作规则起草和修改内容。</p>
</div>

Voiceforge 是一个面向中文和英文内容的 Agent Skill。它从任务材料确认事实，按通用写作规则起草或修改内容，再复核约束并运行表达检查。

<p align="center">
  <img src="assets/voiceforge-intro-zh.png" alt="Voiceforge 写作流程" width="100%" />
</p>

## 核心方式

Voiceforge 按以下顺序工作：

`任务事实 → 通用写作规则 → 可选个人风格 → 通用复核 → 确定性检查`

通用写作层始终启用，负责保持事实准确、语义完整、表达自然，并处理结构、格式和删除要求。个人风格层按需启用，只使用用户主动提供并确认的样本或独立风格工作区。

普通写作不需要本地知识库，也不会自动扫描用户电脑中的个人资料。

## 能做什么

- 起草、改写、润色和校对中文或英文内容；
- 新增、删除、替换、移动或重组内容，同时保留未受影响的部分；
- 检查成稿是否混入用户指令、删除要求、修改说明和其他过程信息；
- 减少多余标题、空泛铺垫、抽象管理词、模糊归因、重复总结和其他常见 AI 写作痕迹；
- 检查事实、数字、标题、段落、主语、动作、对象、读者语境和格式；
- 按用户确认的个人样本和偏好调整语气、节奏与结构。

## 快速开始

把仓库链接到 Agent Skills 目录：

```bash
mkdir -p ~/.agents/skills
ln -sfn /path/to/Voiceforge ~/.agents/skills/voiceforge
```

安装后，在写作任务中调用：

```text
使用 $voiceforge，把这段产品介绍改成可以直接发布的中文成稿。保留事实，删除空泛表达。
```

完成文件后运行表达检查：

```bash
python3 scripts/tone_lint.py /path/to/draft.md
```

检测器支持中英文提示，并提供原始行号和稳定规则编号。自动化工具可以使用 `--format json`。`FAIL` 返回退出码 `1`，`WARN` 只要求人工复核。完整规则与语义边界见 [检测器参考](references/lint-reference.md)。

## 可选个人风格

只有需要持久化个人表达时，才初始化独立风格工作区：

```bash
python3 scripts/voice_memory.py init --workspace ~/.voiceforge
```

普通任务不需要配置它。使用个人风格时，先确认作者身份和样本是否仍代表当前表达；候选样本不会自动参与生成。

## 目录

| 路径 | 作用 |
| --- | --- |
| `SKILL.md` | 运行规则和证据边界 |
| `references/universal-writing-rules.md` | 通用写作规则 |
| `references/corpus-schema.md` | 个人风格工作区的数据格式 |
| `scripts/voice_memory.py` | 风格工作区、检索、反馈和评估工具 |
| `scripts/tone_lint.py` | 确定性表达检查工具 |
| `scripts/_voiceforge/` | 按文本统计、证据、检索和检测划分的内部实现 |
| `tests/` | 回归测试 |

模块职责、依赖关系和架构取舍见 [架构说明](references/architecture.md)。复制 Skill 时保留整个目录，包括 `scripts/_voiceforge/`。直接运行原有脚本入口即可，不需要安装 Python 包。

## 验证

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

## 参考项目

- [oil-tone](https://github.com/oil-oil/oil-tone)

## 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。

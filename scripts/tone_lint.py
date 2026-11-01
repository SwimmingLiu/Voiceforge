#!/usr/bin/env python3
"""检查中文和英文正文中的已知写作问题。"""

# 原入口混合了规则、正文解析与输出。这里只保留进程入口，
# 让文本和 JSON 输出使用同一次检测，并保持直接运行脚本的方式。
from _voiceforge.lint_cli import main


if __name__ == "__main__":
    raise SystemExit(main())

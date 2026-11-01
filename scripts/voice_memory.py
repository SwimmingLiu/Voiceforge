#!/usr/bin/env python3
"""管理独立的 Voiceforge 风格工作区。"""

# 原脚本集中全部算法和写入；入口现在只调用内部进程层，保留原执行路径。
from _voiceforge.memory_cli import main


if __name__ == "__main__":
    raise SystemExit(main())

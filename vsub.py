#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""兼容入口：vsub 已拆成包，直接跑 `python -m vsub` 或安装后用 `vsub`。

这个文件只为兼容以前复制到各处的 vsub.bat（它们会找同目录/安装目录的 vsub.py）。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vsub.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())

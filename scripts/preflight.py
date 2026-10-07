#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""发布前自检：扫描仓库里有没有不该公开的东西。

    python scripts/preflight.py

检查项：
  1. 内网/公网 IP、主机名等网络拓扑信息
  2. 疑似 API key / token
  3. 用户目录绝对路径、个人身份信息
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (规则名, 正则, 说明)
RULES = [
    ("内网 IP", r"\b(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])"
                r"\.\d+\.\d+|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+)\b",
     "家庭/公司内网地址，别写进代码和文档"),
    ("主机名", r"\b(DESKTOP|LAPTOP|MACBOOK)-[A-Z0-9]{4,}\b",
     "机器名会暴露设备信息"),
    ("用户目录", r"[A-Za-z]:\\Users\\[^\\\s\"']+|/home/[A-Za-z0-9_.-]+|/Users/[A-Za-z0-9_.-]+",
     "个人路径，改成占位符"),
    ("API key", r"(sk-[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{20,}|[0-9a-f]{32}-"
                r"[0-9a-f]{2}:fx|ghp_[A-Za-z0-9]{20,})",
     "疑似密钥，立刻吊销"),
    ("私钥", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "私钥文件"),
]

SKIP_DIRS = {".git", "models", "__pycache__", ".venv", "venv", "build", "dist",
             ".pytest_cache", ".ruff_cache"}
SKIP_SUFFIX = {".mp4", ".mkv", ".wav", ".mp3", ".png", ".jpg", ".bin",
               ".pt", ".onnx", ".zip", ".gz"}
MAX_FILE = 2 * 1024 * 1024


def ignored_names():
    """读 .gitignore，这些文件不进版本库，自然也不必扫"""
    import fnmatch
    gi = ROOT / ".gitignore"
    names = set()
    if gi.exists():
        for line in gi.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                names.add(line.rstrip("/"))
    return names, fnmatch.fnmatch


def scan():
    hits = []
    skip_names, fnmatch = ignored_names()
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name in skip_names or any(fnmatch(p.name, pat) for pat in skip_names):
            continue
        if p.suffix.lower() in SKIP_SUFFIX or p.stat().st_size > MAX_FILE:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:                                   # noqa: BLE001
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for name, pat, why in RULES:
                m = re.search(pat, line)
                if m:
                    hits.append((p.relative_to(ROOT), i, name, m.group(0)[:40], why))
    return hits


def main():
    hits = scan()
    if not hits:
        print("preflight: 未发现敏感信息，可以发布。")
        return 0
    print(f"preflight: 发现 {len(hits)} 处需要检查：\n")
    for f, ln, name, sample, why in hits:
        print(f"  {f}:{ln}  [{name}]  {sample!r}")
        print(f"      -> {why}")
    print("\n处理完再跑一次：python scripts/preflight.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())

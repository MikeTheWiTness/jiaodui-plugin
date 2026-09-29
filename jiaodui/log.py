"""统一的日志出口。

旧仓 core/logging_utils.py 的 log() 同时写 UI 面板与日志文件，新仓只保留
「向 stderr 打印人类可读进度」这一条最小路径：CLI 的机器可读结果走 stdout，
进度与诊断走 stderr，互不污染。
"""
from __future__ import annotations

import sys

_QUIET = False


def set_quiet(quiet: bool) -> None:
    global _QUIET
    _QUIET = quiet


def log(message: str) -> None:
    """打印一行进度/诊断到 stderr（--quiet 时静默）。"""
    if not _QUIET:
        print(message, file=sys.stderr, flush=True)

"""单元目录的识别与排序（单一源）。

移植自旧仓 core/unit_detect.py，并按新契约扩展：
- 试卷模式：第N题（含 第1题_备份 等变体）
- 讲义模式：单元N、板块N
"""
from __future__ import annotations

import re
from pathlib import Path

# 前缀锚定（非 fullmatch）：保留「第1题_备份」「第1题(文言文)」等合法变体，
# 拒绝「试题」「错题本」等任意含「题」的误报
_UNIT_DIR_RE = re.compile(r"^(第(\d+)题|板块(\d+)|单元(\d+))")


def is_unit_dir(name: str) -> bool:
    """判断目录名是否为校对单元目录（接受纯目录名，不判断是否为目录）。"""
    return bool(_UNIT_DIR_RE.match(name))


def unit_number(name: str) -> int | None:
    """从单元目录名解析编号；无法解析返回 None。"""
    m = _UNIT_DIR_RE.match(name)
    if not m:
        return None
    for g in m.groups()[1:]:
        if g is not None:
            return int(g)
    return None


def scan_unit_dirs(root: str | Path) -> list[Path]:
    """扫描 paper_dir 下的一级单元目录，按编号排序。

    只认一级子目录中的单元命名；若一级无匹配，兼容性地检查二级子目录
    （旧仓 scan_question_dirs 的行为），返回实际包含单元目录的那一层。
    """
    root = Path(root)
    if not root.is_dir():
        return []
    subs = [x for x in sorted(root.iterdir()) if x.is_dir()]
    direct = [x for x in subs if is_unit_dir(x.name)]
    if direct:
        return sorted(direct, key=lambda p: (unit_number(p.name) or 0, p.name))
    for d in subs:
        inner = [x for x in d.iterdir() if x.is_dir()]
        matched = [x for x in inner if is_unit_dir(x.name)]
        if matched:
            return sorted(matched, key=lambda p: (unit_number(p.name) or 0, p.name))
    return []

"""单元目录的识别与排序（**单一源**，供识别层与清单层共用）。

按 2026-10 决策（REMEDIATION §3 决策 2 / R-D08）：**只接受精确名**
`第N题` / `板块N` / `单元N`。变体名（`第1题_备份`、`第1题(文言文)`）一律不认——
旧实现识别层前缀匹配、清单层 fullmatch，`--adopt-units` 因此会接纳不了自己认出来的目录。

历史目录若含变体名，需要人工作为「非单元」处理（重命名或移出单元根目录）。
"""
from __future__ import annotations

import re
from pathlib import Path

# 精确匹配：fullmatch 语义，识别层与清单层（material.check_units）共用这一份
UNIT_DIR_RE = re.compile(r"^(?:第(?P<exam>\d+)题|板块(?P<board>\d+)|单元(?P<unit>\d+))$")


def is_unit_dir(name: str) -> bool:
    """判断目录名是否为校对单元目录（接受纯目录名，不判断是否为目录）。"""
    return UNIT_DIR_RE.fullmatch(name) is not None


def unit_number(name: str) -> int | None:
    """从单元目录名解析编号；无法解析（含变体名）返回 None。"""
    m = UNIT_DIR_RE.fullmatch(name)
    if not m:
        return None
    for value in m.groupdict().values():
        if value is not None:
            return int(value)
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

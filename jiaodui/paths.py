"""产物路径与命名纪律（PRD §5.1 硬约束）。

只允许这里的约定名；禁止自由命名的 attempt / 副本文件。
"""
from __future__ import annotations

import re
from pathlib import Path

from .units import is_unit_dir

REPORT_NAME = "_校对报告.md"
DATA_NAME = "_校对数据.json"
FAIL_NAME = "_校对失败.md"
SKIP_MARKER_FILE = ".skip_proofread"
IMAGES_DIR = "images"

# 整卷报告与 Word 交付的输出目录约定
WHOLE_REPORT_DIR = "校对报告"
WORD_DIR = "校对Word"

def source_md_name(unit_dir_name: str) -> str:
    """按目录名推出单元源文约定文件名（只认精确单元名，见 units.is_unit_dir）。"""
    if not is_unit_dir(unit_dir_name):
        raise ValueError(f"不是合法的单元目录名：{unit_dir_name}")
    return f"{unit_dir_name}.md"


def find_source_md(unit_dir: str | Path) -> Path | None:
    """在单元目录内定位源文 md。

    优先约定名（第N题.md / 单元N.md）；找不到时回退到任意不以 _ 开头的 md，
    保证历史产物目录仍可读取。
    """
    unit_dir = Path(unit_dir)
    candidates = []
    name = unit_dir.name
    if is_unit_dir(name):
        candidates.append(unit_dir / source_md_name(name))
    candidates.extend(sorted(p for p in unit_dir.glob("*.md") if not p.name.startswith("_")))
    for c in candidates:
        if c.is_file():
            return c
    return None


def report_path(unit_dir: str | Path) -> Path:
    return Path(unit_dir) / REPORT_NAME


def data_path(unit_dir: str | Path) -> Path:
    return Path(unit_dir) / DATA_NAME


def fail_path(unit_dir: str | Path) -> Path:
    return Path(unit_dir) / FAIL_NAME


def is_skip_unit(unit_dir: str | Path) -> bool:
    return (Path(unit_dir) / SKIP_MARKER_FILE).exists()


def safe_name(name: str) -> str:
    """把卷名转成适合文件名的安全名（保留中文与常见符号）。"""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip() or "未命名"

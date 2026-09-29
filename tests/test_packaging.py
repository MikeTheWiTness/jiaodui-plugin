"""发行包必须自带学科配置，且与仓库 config 保持一致（防双源漂移）。"""
from __future__ import annotations

from pathlib import Path

import jiaodui

REPO = Path(__file__).resolve().parent.parent
_PKG_CFG = Path(jiaodui.__file__).parent / "data" / "subjects" / "高中物理.json"
_REPO_CFG = REPO / "config" / "subjects" / "高中物理.json"


def test_package_subject_config_exists():
    assert _PKG_CFG.is_file(), "学科配置必须随包分发（_resolve_config_dir 的兜底）"


def test_package_config_matches_repo_config():
    assert _PKG_CFG.read_bytes() == _REPO_CFG.read_bytes(), "包内配置与仓库 config 漂移"


def test_resolve_config_dir_finds_subject():
    from jiaodui.cli import _resolve_config_dir

    assert (_resolve_config_dir() / "subjects" / "高中物理.json").is_file()

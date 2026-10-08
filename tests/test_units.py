"""单元目录识别与排序（jiaodui/units.py）。

2026-10 决策 2：**只认精确名** `第N题` / `单元N` / `板块N`；变体名（`第1题_备份`）
与误报（`试题`）一并拒绝。识别层与清单层共用同一份正则，不再各写一套。
"""
from pathlib import Path

import pytest

from jiaodui.units import is_unit_dir, scan_unit_dirs, unit_number


def test_is_unit_dir_accepts_contract_names():
    assert is_unit_dir("第1题")
    assert is_unit_dir("单元3")
    assert is_unit_dir("板块2")


def test_is_unit_dir_rejects_variants_and_false_positives():
    """2026-10 决策 2：只认精确名。变体名与误报一样被拒（识别层与清单层同口径）。"""
    assert not is_unit_dir("第1题_备份")
    assert not is_unit_dir("第1题(文言文)")
    assert not is_unit_dir("第1题_尝试2")
    assert not is_unit_dir("试题")
    assert not is_unit_dir("错题本")
    assert not is_unit_dir("images")
    assert not is_unit_dir("")


def test_unit_number_parses_each_prefix():
    assert unit_number("第12题") == 12
    assert unit_number("单元3") == 3
    assert unit_number("板块2") == 2
    assert unit_number("第1题_备份") is None
    assert unit_number("试题") is None


def test_scan_unit_dirs_sorts_by_number_and_ignores_non_units(tmp_path):
    for name in ("第10题", "第2题", "第1题", "第1题_备份", "试题", "readme.md"):
        (tmp_path / name).mkdir()
    (tmp_path / "readme.md").rmdir()
    (tmp_path / "readme.md").write_text("x", encoding="utf-8")

    assert [path.name for path in scan_unit_dirs(tmp_path)] == ["第1题", "第2题", "第10题"]


def test_scan_unit_dirs_falls_back_one_level(tmp_path):
    """一级没有单元目录时，兼容旧仓行为检查二级目录。"""
    inner = tmp_path / "卷子" / "第1题"
    inner.mkdir(parents=True)
    assert [path.name for path in scan_unit_dirs(tmp_path)] == ["第1题"]


def test_scan_unit_dirs_returns_empty_for_missing_root(tmp_path):
    assert scan_unit_dirs(Path(tmp_path) / "不存在") == []


def test_layers_share_one_rule(tmp_path):
    """识别层与清单/路径层必须同口径：变体名两层都不认，不会再出现 adopt 分叉。"""
    from jiaodui import paths, material  # noqa: F401  (存在性即证明共用同一实现)

    (tmp_path / "第1题_备份").mkdir()
    assert scan_unit_dirs(tmp_path) == []
    with pytest.raises(ValueError):
        paths.source_md_name("第1题_备份")

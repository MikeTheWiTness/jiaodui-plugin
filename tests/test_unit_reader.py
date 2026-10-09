from __future__ import annotations

import pytest

from jiaodui import material
from jiaodui.errors import BusinessError
from jiaodui.unit_reader import read_unit_source
from jiaodui.workflow import convert_material, split_material


def _unit(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("1．第一行。\n第二行。\n\n2．另一个单元。\n", encoding="utf-8")
    converted = convert_material(source, material_name="分页读取", mode="exam")
    split = split_material(converted.raw_md, subject="高中物理", mode="exam")
    data = material.load(workspace / "校对" / "分页读取")
    return data, split


def test_unit_read_uses_task_unit_identity_and_pages_source(tmp_path, monkeypatch):
    data, split = _unit(tmp_path, monkeypatch)
    unit_id = data["unit_ids"][data["unit_set"][0]]
    first = read_unit_source(data["task_id"], unit_id, start_line=1, max_lines=1)
    assert first["ok"] is True
    assert first["line_start"] == 1
    assert first["line_end"] == 1
    assert first["line_count"] >= 1
    assert first["next_line"] == (2 if first["line_count"] > 1 else None)
    assert first["source_sha256"] == data["unit_inputs"][first["unit"]]["source_sha256"]
    assert first["content"]
    assert "references" in first["images"]


def test_unit_read_rejects_invalid_paging_and_changed_source(tmp_path, monkeypatch):
    data, split = _unit(tmp_path, monkeypatch)
    unit_id = data["unit_ids"][data["unit_set"][0]]
    with pytest.raises(BusinessError) as error:
        read_unit_source(data["task_id"], unit_id, start_line=0)
    assert error.value.code == "unit-read-range"
    with pytest.raises(BusinessError):
        read_unit_source(data["task_id"], unit_id, max_lines=2001)
    unit = __import__("pathlib").Path(split.unit_dirs[0])
    source = unit / f"{unit.name}.md"
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(BusinessError) as changed:
        read_unit_source(data["task_id"], unit_id)
    assert changed.value.code == "unit-input-mismatch"

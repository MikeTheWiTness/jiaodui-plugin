from __future__ import annotations

import json
import shutil

import pytest

from jiaodui import material
from jiaodui.errors import NotFoundError
from jiaodui.workflow import convert_material, split_material


def _split_material(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("1．题目甲。\n\n2．题目乙。\n", encoding="utf-8")
    converted = convert_material(source, material_name="身份测试", mode="exam")
    split = split_material(converted.raw_md, subject="高中物理", mode="exam")
    root = workspace / "校对" / "身份测试"
    return workspace, root, converted, split


def test_split_persists_stable_task_and_unit_ids(tmp_path, monkeypatch):
    workspace, root, converted, split = _split_material(tmp_path, monkeypatch)
    data = material.load(root)
    assert len(data["task_id"]) == 32
    assert set(data["unit_ids"]) == set(data["unit_set"])
    assert len(set(data["unit_ids"].values())) == len(split.unit_dirs)
    first_ids = dict(data["unit_ids"])

    split_material(converted.raw_md, subject="高中物理", mode="exam")
    data = material.load(root)
    assert data["unit_ids"] == first_ids
    for unit_name, unit_id in first_ids.items():
        found_root, unit = material.find_unit_by_id(data["task_id"], unit_id)
        assert found_root == root
        assert unit.name == unit_name


def test_unit_ids_resolve_after_material_move_but_not_in_other_workspace(tmp_path, monkeypatch):
    workspace, root, _, _ = _split_material(tmp_path, monkeypatch)
    data = material.load(root)
    task_id = data["task_id"]
    unit_id = data["unit_ids"][data["unit_set"][0]]
    moved_workspace = tmp_path / "moved-workspace"
    moved_workspace.mkdir()
    moved_root = moved_workspace / "校对" / root.name
    moved_root.parent.mkdir()
    shutil.move(str(root), str(moved_root))
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(moved_workspace))
    found_root, unit = material.find_unit_by_id(task_id, unit_id)
    assert found_root == moved_root
    assert unit.parent == moved_root / "units" / root.name

    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    with pytest.raises(NotFoundError):
        material.find_unit_by_id(task_id, unit_id)


def test_identity_manifest_rejects_duplicate_or_unmapped_unit_ids(tmp_path, monkeypatch):
    _, root, _, _ = _split_material(tmp_path, monkeypatch)
    path = root / material.MANIFEST
    data = json.loads(path.read_text(encoding="utf-8"))
    names = data["unit_set"]
    data["unit_ids"][names[1]] = data["unit_ids"][names[0]]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(Exception, match="身份映射无效"):
        material.load(root)


def test_unit_locate_cli_uses_opaque_ids_not_paths(tmp_path, monkeypatch):
    import subprocess
    import sys

    workspace, root, _, _ = _split_material(tmp_path, monkeypatch)
    data = material.load(root)
    unit_name = data["unit_set"][0]
    unit_id = data["unit_ids"][unit_name]
    result = subprocess.run(
        [sys.executable, "-m", "jiaodui", "--work-root", str(workspace), "unit-locate",
         "--task-id", data["task_id"], "--unit-id", unit_id, "--phrase", "题目", "--json"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["task_id"] == data["task_id"]
    assert payload["unit_id"] == unit_id
    assert payload["locations"]

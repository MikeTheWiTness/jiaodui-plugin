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


def test_unknown_task_placeholder_is_reported_as_missing_argument(tmp_path, monkeypatch):
    """缺参数被序列化成 'undefined' 时不能报成「材料不存在」。

    回放实测（第 11 讲 单元1）：子 agent 把 task_id/unit_id 嵌进 proposal、顶层漏传，
    结构化工具壳把缺省值序列化成字面量 `undefined`，CLI 只报「不存在此task_id」，
    调用方无从判断是自己漏传参数还是身份过期。
    """
    _split_material(tmp_path, monkeypatch)
    with pytest.raises(NotFoundError) as error:
        material.find_unit_by_id("undefined", "b" * 32)
    message = str(error.value)
    assert "占位值" in message, "必须指出这是占位值而不是真的找不到材料"
    assert "没有传 task_id" in message


def test_split_warns_only_when_it_actually_opens_a_new_round(tmp_path, monkeypatch):
    """开新轮次会使执行模式授权失效；split 必须当场告知（且只在真的开新轮时告知）。

    回放实测：父代理把 execution-policy 登记在 split 之前，split 开新轮后 8 个并发
    子代理在第 1 步 unit-snapshot 全部被 execution-policy-required 拒绝。
    """
    _workspace, _root, converted, split = _split_material(tmp_path, monkeypatch)
    assert any("execution-policy" in warning for warning in split.warnings), split.warnings

    # 参数与单元输入完全一致时不再开新轮次，授权仍然有效 → 不应重复告警
    again = split_material(converted.raw_md, subject="高中物理", mode="exam")
    assert not any("execution-policy" in warning for warning in again.warnings), again.warnings


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


def test_unknown_unit_id_reports_known_mapping_and_suggestion(tmp_path, monkeypatch):
    """回放根因：手抄 32 位 unit_id 错一位时只报「不存在」，子 agent 无从判断。

    not_found 必须给出该 task 的完整「单元名 → unit_id」映射，并对近似值给出建议。
    """
    _, root, _, _ = _split_material(tmp_path, monkeypatch)
    data = material.load(root)
    unit_name = data["unit_set"][0]
    unit_id = data["unit_ids"][unit_name]
    typo = unit_id[:-2] + ("0" if unit_id[-2] != "0" else "1") + unit_id[-1]

    with pytest.raises(NotFoundError) as error:
        material.find_unit_by_id(data["task_id"], typo)
    details = error.value.details
    assert details["known_units"] == data["unit_ids"]
    assert details["suggestion"] == {"unit": unit_name, "unit_id": unit_id}

    with pytest.raises(NotFoundError) as error:
        material.unit_progress(data["task_id"], unit_id=typo)
    assert error.value.details["suggestion"] == {"unit": unit_name, "unit_id": unit_id}


def test_unknown_unit_id_without_close_match_omits_suggestion(tmp_path, monkeypatch):
    _, root, _, _ = _split_material(tmp_path, monkeypatch)
    data = material.load(root)
    with pytest.raises(NotFoundError) as error:
        material.find_unit_by_id(data["task_id"], "f" * 32)
    assert "suggestion" not in error.value.details
    assert error.value.details["known_units"] == data["unit_ids"]


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

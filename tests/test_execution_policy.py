from __future__ import annotations

import json
from pathlib import Path

import pytest

from jiaodui.errors import BusinessError
from jiaodui import material
from jiaodui.workflow import convert_material


def _material(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("第一节\n正文。\n", encoding="utf-8")
    convert_material(source, material_name="隔离策略测试")
    return workspace / "校对" / "隔离策略测试"


def test_execution_policy_is_recorded_once_per_run(tmp_path, monkeypatch):
    root = _material(tmp_path, monkeypatch)
    policy = material.set_execution_policy(root, "automatic")

    manifest = json.loads((root / material.MANIFEST).read_text(encoding="utf-8"))
    run = manifest["runs"][-1]
    assert run["execution_policy"] == policy
    assert policy["run_id"] == manifest["current_run_id"]
    assert policy["budgets"] == {
        "call_correction": 2,
        "calc_representation": 2,
        "report_repair": 3,
        "targeted_review": 2,
        "technical_redispatch": 1,
        "image_schema_fix": 2,
    }
    assert material.set_execution_policy(root, "automatic") == policy
    with pytest.raises(BusinessError) as error:
        material.set_execution_policy(root, "interactive")
    assert error.value.code == "execution-policy-locked"


def test_execution_policy_is_invalidated_by_new_run(tmp_path, monkeypatch):
    root = _material(tmp_path, monkeypatch)
    material.set_execution_policy(root, "interactive", "confirmed")

    with material.locked(root):
        manifest = material.load(root)
        material.new_run(manifest, manifest["params"], manifest["resources"])
        material.write(root, manifest)

    manifest = material.load(root)
    assert "execution_policy" not in manifest["runs"][-1]
    assert manifest["runs"][-2]["execution_policy"]["mode"] == "interactive"
    assert Path(manifest["paths"]["paper"]).is_absolute() is False


def test_execution_policy_rejects_unknown_mode_and_origin(tmp_path, monkeypatch):
    root = _material(tmp_path, monkeypatch)
    for mode, origin, code in [
        ("auto", "user", "invalid-execution-mode"),
        ("automatic", "default", "invalid-execution-origin"),
    ]:
        with pytest.raises(BusinessError) as error:
            material.set_execution_policy(root, mode, origin)
        assert error.value.code == code


def test_execution_policy_cli_requires_workspace_and_emits_json(tmp_path, monkeypatch):
    import subprocess
    import sys

    root = _material(tmp_path, monkeypatch)
    workspace = root.parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "jiaodui", "--work-root", str(workspace), "execution-policy",
         str(root), "--mode", "automatic", "--origin", "confirmed", "--json"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["execution_policy"]["mode"] == "automatic"

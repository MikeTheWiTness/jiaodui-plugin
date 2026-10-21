"""calc CLI 契约：PRD 子命令别名、默认不回显生成代码。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(*args):
    return subprocess.run([PY, "-m", "jiaodui", *args], cwd=ROOT,
                          capture_output=True, text=True)


def test_calc_evaluate():
    r = run("calc", "evaluate", "--param", "expression=1/3+1/6", "--json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["ok"] is True
    assert payload["result"]["result"] == 0.5
    assert "code" not in payload["result"], "默认不得回显生成代码"


def test_calc_dimension_alias():
    r = run("calc", "dimension",
            "--param", 'expression=F = m * a',
            "--param", 'unit_definitions={"F":"newton","m":"kilogram","a":"meter/second**2"}',
            "--json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["result"]["result"]["consistent"] is True


def test_calc_show_code_opt_in():
    r = run("calc", "evaluate", "--param", "expression=1+1", "--show-code", "--json")
    payload = json.loads(r.stdout)
    assert payload["result"]["code"]


def test_calc_subject_declaring_calc_is_allowed():
    r = run("calc", "evaluate", "--param", "expression=1+1", "--subject", "高中物理", "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["result"]["result"] == 2


def test_calc_subject_without_calc_tool_is_unsupported(tmp_path):
    """学科工具集白名单不含 calc → 退出码 7，并说明该学科声明了什么。"""
    import os

    subjects = tmp_path / "cfg" / "subjects"
    subjects.mkdir(parents=True)
    (subjects / "古籍.json").write_text(
        json.dumps({"subject": "古籍", "tools": ["classics"]}, ensure_ascii=False),
        encoding="utf-8")
    env = {**os.environ, "JIAODUI_CONFIG_DIR": str(tmp_path / "cfg")}
    r = subprocess.run(
        [PY, "-m", "jiaodui", "calc", "evaluate",
         "--param", "expression=1+1", "--subject", "古籍", "--json"],
        cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 7, r.stderr
    error = json.loads(r.stderr)["error"]
    assert error["code"] == "unsupported"
    assert error["details"]["allowed_tools"] == ["classics"]


def test_chemistry_subject_allows_balance_and_stoichiometry():
    """高中化学学科配置放行 calc，且化学专用 operation 可端到端跑通。"""
    balanced = run("calc", "chemistry_balance", "--subject", "高中化学",
                   "--param", "equation=Fe + O2 -> Fe2O3", "--json")
    assert balanced.returncode == 0, balanced.stderr
    result = json.loads(balanced.stdout)["result"]["result"]
    assert result["balanced_equation"] == "4Fe + 3O2 -> 2Fe2O3"

    stoich = run("calc", "stoichiometry", "--subject", "高中化学",
                 "--param", "balanced_equation=2H2 + O2 -> 2H2O",
                 "--param", "known_substance=H2", "--param", "known_mass=4.0",
                 "--param", "target_substance=H2O", "--json")
    assert stoich.returncode == 0, stoich.stderr
    assert json.loads(stoich.stdout)["result"]["result"]["target_mass_g"] > 0


def test_chemistry_quantities_is_empty_but_readable():
    """化学 v1 不建量表：命令必须成功返回空表，而不是报错。"""
    r = run("quantities", "--subject", "高中化学", "--json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["count"] == 0
    assert payload["quantities"] == {}


def test_calc_unknown_subject_is_not_found():
    r = run("calc", "evaluate", "--param", "expression=1+1", "--subject", "不存在的学科", "--json")
    assert r.returncode == 5, r.stderr
    assert json.loads(r.stderr)["error"]["code"] == "not_found"

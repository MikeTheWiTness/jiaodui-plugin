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

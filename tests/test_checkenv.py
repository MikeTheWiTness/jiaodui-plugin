"""check-env 的「已安装 vs 可加载」区分测试。

锁定 _module_state：find_spec 只证明装了，真实 import 失败（例如 pip 装的
C 扩展被 macOS 代码签名拒绝）必须报告为不可用，而不是「已安装」。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jiaodui import checkenv


def test_module_state_absent(monkeypatch):
    monkeypatch.setattr(checkenv.importlib.util, "find_spec", lambda name: None)
    ok, detail = checkenv._module_state("nope")
    assert ok is False
    assert detail == "未安装"


def test_module_state_present_but_unloadable(monkeypatch):
    """装了但 dlopen 失败：必须报不可用，并带异常类型。"""
    monkeypatch.setattr(checkenv.importlib.util, "find_spec",
                        lambda name: SimpleNamespace(origin="x"))

    def boom(name):
        raise ImportError("dlopen failed: code signature in ... not valid")

    monkeypatch.setattr(checkenv.importlib, "import_module", boom)
    ok, detail = checkenv._module_state("matplotlib")
    assert ok is False
    assert "无法加载" in detail
    assert "ImportError" in detail


def test_module_state_loadable(monkeypatch):
    monkeypatch.setattr(checkenv.importlib.util, "find_spec",
                        lambda name: SimpleNamespace(origin="x"))
    monkeypatch.setattr(checkenv.importlib, "import_module", lambda name: None)
    ok, detail = checkenv._module_state("sympy")
    assert ok is True
    assert detail == "已安装"


def test_check_env_optional_matplotlib_failure_does_not_fail_report(monkeypatch):
    """matplotlib 可选：不可加载只记明细，不让 required 判定失败。"""
    monkeypatch.setattr(checkenv, "_module_state",
                        lambda name: (False, "已安装但无法加载（ImportError）")
                        if name == "matplotlib" else (True, "已安装"))
    monkeypatch.setattr(checkenv, "_find_pandoc", lambda: "/fake/pandoc")
    monkeypatch.setattr(checkenv, "_has_module", lambda name: False)
    report = checkenv.check_env()
    mpl = [i for i in report.items if "matplotlib" in i.name]
    assert mpl and mpl[0].ok is False and mpl[0].required is False
    assert report.ok is True

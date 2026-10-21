"""check-env 的「已安装 vs 可加载」区分测试。

锁定 _module_state：find_spec 只证明装了，真实 import 失败（例如 pip 装的
C 扩展被 macOS 代码签名拒绝）必须报告为不可用，而不是「已安装」。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

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


def _patch_local_env(monkeypatch):
    monkeypatch.setattr(checkenv, "_module_state", lambda name: (True, "已安装"))
    monkeypatch.setattr(checkenv, "_find_pandoc", lambda: "/fake/pandoc")
    monkeypatch.setattr(checkenv, "_has_module", lambda name: False)


def test_contract_probe_accepts_matching_plugin_expectation():
    from jiaodui import __version__

    item, contract = checkenv._contract_check(3, __version__)
    assert item.ok is True
    assert "期望提案 schema v3" in item.detail
    assert contract["supported_schema_versions"] == [2, 3]
    assert contract["problems"] == []
    assert contract["expected_schema_version"] == 3


def test_contract_probe_rejects_unsupported_schema_version():
    item, contract = checkenv._contract_check(4, None)
    assert item.ok is False
    assert "只支持 v2、v3" in item.detail
    assert contract["problems"]


def test_contract_probe_rejects_bundle_version_mismatch():
    item, contract = checkenv._contract_check(3, "9.9.9")
    assert item.ok is False
    assert "版本 9.9.9" in item.detail
    assert contract["bundle_version"] == "9.9.9"


def test_check_env_exposes_contract_item_and_verdict(monkeypatch):
    from jiaodui import __version__

    _patch_local_env(monkeypatch)
    report = checkenv.check_env(expect_schema_version=3, expect_bundle_version=__version__)
    contract = next(i for i in report.items if i.name.startswith("contract"))
    assert contract.ok is True
    assert report.contract["ok"] is True
    assert report.ok is True
    assert report.to_dict()["contract"]["expected_schema_version"] == 3


def test_workspace_required_message_does_not_describe_read_only_commands_as_writes(monkeypatch):
    from jiaodui.errors import BusinessError
    from jiaodui.workdir import workspace_root

    monkeypatch.delenv("JIAODUI_WORK_ROOT", raising=False)
    with pytest.raises(BusinessError) as error:
        workspace_root()
    assert error.value.code == "workspace-required"
    assert "写入" not in str(error.value)
    assert "--work-root" in str(error.value)

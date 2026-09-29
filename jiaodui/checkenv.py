"""环境预检 check-env（PRD §5.4 / D19）。

只检查本地确定性依赖，不含任何凭证项。明确区分「CLI 能证明的」与
「宿主必须另行验证的」：子 agent 支持与本地读图能力不在 CLI 断言范围内。
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckItem:
    name: str
    ok: bool
    detail: str
    required: bool = True
    scope: str = "local"  # local | host

    def to_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "detail": self.detail,
                "required": self.required, "scope": self.scope}


@dataclass
class EnvReport:
    items: list[CheckItem] = field(default_factory=list)
    host_checks_required: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(i.ok for i in self.items if i.required and i.scope == "local")

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "python": sys.version.split()[0],
            "items": [i.to_dict() for i in self.items],
            "host_checks_required": self.host_checks_required,
        }


def _find_pandoc() -> str | None:
    """定位 pandoc（单一源：与 convert.find_pandoc 同一实现）。"""
    try:
        from .convert import find_pandoc

        return find_pandoc()
    except Exception:  # pragma: no cover - 仅当 convert 不可用时兜底
        found = shutil.which("pandoc")
        if found:
            return found
        for cand in ("/usr/local/bin/pandoc", "/opt/homebrew/bin/pandoc", "/usr/bin/pandoc"):
            if Path(cand).is_file():
                return cand
        return None


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _module_state(name: str) -> tuple[bool, str]:
    """返回 (是否真正可加载, 说明)。

    find_spec 只证明「装了」；此处再做真实 import，暴露 dlopen 失败
    （例如 pip 装的 C 扩展被 macOS 代码签名拒绝、Team ID 不一致）这类
    「已安装但无法加载」。仅用于本地确定性依赖的自证。
    """
    try:
        if importlib.util.find_spec(name) is None:
            return False, "未安装"
    except (ImportError, ValueError):
        return False, "未安装"
    try:
        importlib.import_module(name)
        return True, "已安装"
    except Exception as exc:  # noqa: BLE001 - 任何加载失败都视为不可用
        return False, f"已安装但无法加载（{type(exc).__name__}）"


def check_env() -> EnvReport:
    report = EnvReport()
    v = sys.version_info
    report.items.append(CheckItem(
        "python", v >= (3, 12), f"Python {v.major}.{v.minor}.{v.micro}（要求 >=3.12）"))

    for mod, label, required in [
        ("sympy", "sympy（calc 符号计算）", True),
        ("docx", "python-docx（Word 批注）", True),
        ("PIL", "Pillow（图片）", True),
        ("lxml", "lxml（OpenXML）", True),
        ("matplotlib", "matplotlib（公式 PNG 渲染，可选）", False),
    ]:
        ok, detail = _module_state(mod)
        report.items.append(CheckItem(label, ok, detail, required=required))

    pandoc = _find_pandoc()
    report.items.append(CheckItem("pandoc（docx↔md、md→docx）", bool(pandoc),
                                  pandoc or "未找到；设置 JIAODUI_PANDOC 或安装 pandoc"))

    playwright = _has_module("playwright")
    report.items.append(CheckItem("playwright（classics 古籍检索，后置能力）", playwright,
                                  "已安装" if playwright else "未安装（classics 后置，不影响 v1）",
                                  required=False))

    # 宿主能力不在 CLI 证明范围（D14）：只列出必须由主 agent 实测的项目
    report.host_checks_required = [
        "宿主支持派发子 agent（一层扁平，禁止嵌套）",
        "子 agent 模型支持读取本地图片（读图是硬前提，不通过则拒绝执行）",
        "子 agent 能在单元目录内写文件并回传一行摘要",
    ]
    return report

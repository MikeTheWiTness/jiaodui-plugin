"""环境预检 check-env（PRD §5.4 / D19）。

只检查本地确定性依赖，不含任何凭证项。明确区分「CLI 能证明的」与
「宿主必须另行验证的」：子 agent 支持与本地读图能力不在 CLI 断言范围内。
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import subprocess
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


SUPPORTED_PROPOSAL_SCHEMA_VERSIONS = (2, 3)
"""CLI 实际能校验的提案 schema 版本；插件在这里声明它的期望版本。"""


@dataclass
class EnvReport:
    items: list[CheckItem] = field(default_factory=list)
    host_checks_required: list[str] = field(default_factory=list)
    runtime: dict = field(default_factory=dict)
    contract: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(i.ok for i in self.items if i.required and i.scope == "local")

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "python": sys.version.split()[0],
            "items": [i.to_dict() for i in self.items],
            "host_checks_required": self.host_checks_required,
            "runtime": self.runtime,
            "contract": self.contract,
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


def _canonical_schema(value: dict) -> str:
    """契约比对用 canonical JSON：忽略键序和空白，只比较实际结构。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _schema_file_check(path: str | None) -> tuple[list[str], dict]:
    """读取插件随包 schema 并与核心导出逐字段比对，捕获同版本的内容漂移。"""
    if path is None:
        return [], {"schema_file": None, "schema_matches": None}
    info: dict = {"schema_file": path, "schema_matches": None}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"插件 schema 文件不可读：{type(exc).__name__}"], info
    schema = payload.get("schema") if isinstance(payload, dict) and "schema" in payload else payload
    if not isinstance(schema, dict):
        return ["插件 schema 文件不是 JSON 对象"], info
    try:
        version = schema["properties"]["schema_version"]["const"]
    except (KeyError, TypeError):
        version = None
    if version not in SUPPORTED_PROPOSAL_SCHEMA_VERSIONS:
        return [f"插件 schema 文件的 schema_version 无效：{version!r}"], info
    from .report_suggestions import proposal_json_schema

    matches = _canonical_schema(schema) == _canonical_schema(
        proposal_json_schema(schema_version=version))
    info["schema_matches"] = matches
    info["schema_version"] = version
    if not matches:
        return [f"插件 schema 文件与核心导出的 v{version} 不一致（字段或默认值已漂移）"], info
    return [], info


def _contract_check(expect_schema_version: int | None,
                    expect_bundle_version: str | None,
                    expect_schema_file: str | None = None) -> tuple[CheckItem, dict]:
    """插件 ↔ CLI 契约探针：版本号相同不代表内容相同，必须显式核对 schema 能力与内容。"""
    from . import __version__

    supported = list(SUPPORTED_PROPOSAL_SCHEMA_VERSIONS)
    problems: list[str] = []
    if (expect_schema_version is not None
            and expect_schema_version not in SUPPORTED_PROPOSAL_SCHEMA_VERSIONS):
        problems.append(
            f"插件期望提案 schema v{expect_schema_version}，核心只支持 "
            + "、".join(f"v{version}" for version in supported))
    if expect_bundle_version is not None and expect_bundle_version != __version__:
        bundle_problem_label = "空字符串" if expect_bundle_version == "" else expect_bundle_version
        problems.append(
            f"插件 bundle 版本 {bundle_problem_label} 与核心 {__version__} 不一致")
    schema_problems, schema_info = _schema_file_check(expect_schema_file)
    problems.extend(schema_problems)
    ok = not problems
    bundle_label = "未声明" if expect_bundle_version is None else (expect_bundle_version or "空字符串")
    schema_label = "未声明" if expect_schema_version is None else str(expect_schema_version)
    if (expect_schema_version is None and expect_bundle_version is None
            and expect_schema_file is None):
        detail = (f"核心 {__version__}；支持提案 schema "
                  + "、".join(f"v{version}" for version in supported)
                  + "；调用方未声明插件期望（CLI 直调）")
    else:
        detail = (f"插件 bundle {bundle_label} / 核心 {__version__} / "
                  f"期望提案 schema v{schema_label} / 核心支持 "
                  + "、".join(f"v{version}" for version in supported))
    if schema_info["schema_matches"] is True:
        detail += "；插件 schema 文件与核心一致"
    elif schema_info["schema_matches"] is False:
        detail += "；插件 schema 文件与核心不一致"
    if problems:
        detail += "；" + "；".join(problems)
    item = CheckItem("contract（插件↔CLI 契约）", ok, detail)
    contract = {
        "ok": ok,
        "core_version": __version__,
        "bundle_version": expect_bundle_version,
        "supported_schema_versions": supported,
        "expected_schema_version": expect_schema_version,
        "problems": problems,
        **schema_info,
    }
    return item, contract


def check_env(*, expect_schema_version: int | None = None,
              expect_bundle_version: str | None = None,
              expect_schema_file: str | None = None) -> EnvReport:
    report = EnvReport()
    from .workflow import resolve_config_dir
    from .workdir import workspace_root
    root = workspace_root(required=False)
    cli = shutil.which("jiaodui")
    report.runtime = {"cli_path": str(Path(cli).resolve()) if cli else str(Path(sys.argv[0]).resolve()),
                      "python_path": sys.executable, "config_dir": str(resolve_config_dir().resolve()),
                      "work_root": str(root) if root else None}
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
    pandoc_detail = pandoc or "未找到；设置 JIAODUI_PANDOC 或安装 pandoc"
    if pandoc:
        try:
            version = subprocess.run([pandoc, "--version"], capture_output=True, text=True, timeout=10)
            first = version.stdout.splitlines()
            if first:
                pandoc_detail = f"{pandoc}（{first[0]}）"
        except (OSError, subprocess.TimeoutExpired):
            pandoc_detail = f"{pandoc}（版本查询失败）"
    report.items.append(CheckItem("pandoc（docx↔md、md→docx）", bool(pandoc),
                                  pandoc_detail))

    playwright = _has_module("playwright")
    report.items.append(CheckItem("playwright（classics 古籍检索，后置能力）", playwright,
                                  "已安装" if playwright else "未安装（classics 后置，不影响 v1）",
                                  required=False))

    contract_item, contract = _contract_check(
        expect_schema_version, expect_bundle_version, expect_schema_file)
    report.items.append(contract_item)
    report.contract = contract

    # 宿主能力不在 CLI 证明范围（D14）：只列出必须由主 agent 实测的项目
    report.host_checks_required = [
        "宿主支持派发子 agent（一层扁平，禁止嵌套）",
        "子 agent 模型支持读取本地图片（读图是硬前提，不通过则拒绝执行）",
        "子 agent 能在单元目录内写文件并回传一行摘要",
    ]
    return report

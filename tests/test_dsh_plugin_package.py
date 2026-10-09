"""dsh-jiaodui 插件包的打包契约测试。

只锁定「随包产物彼此一致、且是 DSH 能读的形态」，不验证宿主运行行为
（安装与实际运行需要真实 DSH profile，见 packages/dsh-jiaodui/README.md）。
YAML 用例需要 pyyaml（pyproject 的 dev 额外依赖）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packages" / "dsh-jiaodui"
SKILL_SRC = ROOT / "skills" / "jiaodui"
SKILL_PKG = PKG / "skills" / "jiaodui"


class _Loader(yaml.SafeLoader):
    """保留 !!js 表达式原文——这里只做结构检查，不求值。"""


def _js(loader: yaml.SafeLoader, node: yaml.Node) -> str:
    return loader.construct_scalar(node)  # type: ignore[arg-type]


_Loader.add_constructor("tag:yaml.org,2002:js", _js)
_Loader.add_constructor("!js", _js)


def _load_patch() -> list:
    with (PKG / "cordis.patch.yml").open(encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)


def _preset_config() -> dict:
    rows = _load_patch()[0]["insert"]
    row = next(r for r in rows if r["id"] == "preset-jiaodui")
    return row["config"]


def test_manifest_declares_bundle_plugin_and_display_metadata():
    manifest = json.loads((PKG / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "dsh-jiaodui"
    assert manifest["type"] == "module"
    assert manifest["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert (PKG / manifest["dsh"]["bundle"]["patch"]).is_file()
    # 同名包既要能被相对路径挂载，也要能按包名解析（自引用 package.json）
    assert manifest["exports"]["."] == "./tools/index.js"
    assert manifest["exports"]["./package.json"] == "./package.json"
    assert manifest["icon"].startswith("./")
    assert (PKG / "locale" / "zh.json").is_file()
    assert (PKG / "locale" / "en.json").is_file()


def test_preset_declares_jiaodui_with_minimal_agent_capabilities():
    config = _preset_config()
    assert config["id"] == "jiaodui"
    assert config["name"] == "校对"
    assert isinstance(config["order"], int)
    plugins = {p["id"]: p for p in config["plugins"]}
    for required in ("persona", "tool-skill", "tool-todo", "jiaodui-tools", "delegation"):
        assert required in plugins, f"preset 缺少校对能力：{required}"
    assert plugins["tool-fs"]["name"] == "@deepseek-ai/dsh-tool-fs"
    # 父 agent 必须有通用操作性。实测代价见 PROCESS_REWORK：无 shell 的会话能复现
    # Word 锚点丢失、能收窄到「标记落在表格行内」，却因为没有解 docx 内部 XML 的通道
    # 而无法定位根因，只能交接给另一个会话。子 agent 侧仍必须封闭（见下一个用例），
    # 「模型不写报告」这条约束的落点在子 agent 的工具目录，不在父 agent 少一把 shell。
    for tool_id in ("tool-bash", "tool-pwsh"):
        assert tool_id in plugins, f"父侧缺少 shell：{tool_id}"
        expr = plugins[tool_id].get("disabled")
        assert isinstance(expr, str) and "process.platform" in expr, f"{tool_id} 需按平台显式开关"
    assert plugins["tool-bash"]["disabled"] != plugins["tool-pwsh"]["disabled"], "bash/pwsh 必须平台互补"
    assert plugins["tool-fs-search"]["name"] == "@deepseek-ai/dsh-tool-fs-search"
    assert plugins["tool-fs-search"].get("disabled", False) is False, "父侧只读搜索应启用"
    for removed in ("command-goal", "tool-goal"):
        assert removed not in plugins or plugins[removed].get("disabled", False), f"preset 不应启用：{removed}"
    assert plugins.get("tool-web", {}).get("disabled", False) is True
    delegation = {p["id"]: p for p in plugins["delegation"]["config"]}
    assert delegation["tool-subagent-fork"]["disabled"] is True
    assert "tool-subagent" in delegation


def test_preset_uses_standard_native_tools_and_keeps_parallel_delegation():
    """校对使用标准工具呈现；PTC 引擎不启用，普通子 agent 仍可并行派发。"""
    plugins = {p["id"]: p for p in _preset_config()["plugins"]}
    assert plugins["tool-presentation"]["config"]["mode"] == "native"
    delegation = {p["id"]: p for p in plugins["delegation"]["config"]}
    assert delegation["workflow-ptc"]["disabled"] is True
    assert delegation["tool-subagent"].get("disabled", False) is False
    assert delegation["tool-subagent"]["config"]["provider"] == "spawn"
    assert delegation["tool-subagent"]["config"]["backgroundMode"] == "continuable"
    assert delegation["tool-subagent"]["config"]["maxDepth"] == 1
    child_tools = set(delegation["tool-subagent"]["config"]["toolFilter"]["allow"])
    assert {"skill", "read_image", "jiaodui_unit_read", "jiaodui_unit_submit"} <= child_tools
    assert not child_tools & {"jiaodui", "write", "edit", "bash", "web_search", "subagent",
                              "subagent_fork", "jiaodui_unit_review", "create_goal"}
    assert plugins["tool-todo"]["config"]["allowParallelInProgress"] is True


def test_preset_mounts_bundled_skill_dir_and_native_tool():
    plugins = {p["id"]: p for p in _preset_config()["plugins"]}
    assert plugins["skill-filesystem"]["config"]["includeDefaultRoots"] is False
    dirs = plugins["skill-filesystem"]["config"]["customSkillDirs"]
    assert len(dirs) == 1
    assert "'skills'" in dirs[0] and "baseUrl" in dirs[0]
    assert "resolve('dsh-jiaodui/package.json')" in dirs[0]
    assert plugins["jiaodui-tools"]["name"] == "dsh-jiaodui"


def test_calc_tool_schemas_match_python_core_export():
    result = subprocess.run(
        [sys.executable, "-m", "jiaodui", "calc-schema", "--json"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    generated = json.loads(result.stdout)
    bundled = json.loads((PKG / "tools" / "calc-schemas.json").read_text(encoding="utf-8"))
    assert bundled == generated


def test_proposal_schema_bundle_matches_python_core_export():
    result = subprocess.run(
        [sys.executable, "-m", "jiaodui", "unit-schema", "--json"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    generated = json.loads(result.stdout)
    bundled = json.loads((PKG / "tools" / "proposal-schema.json").read_text(encoding="utf-8"))
    assert bundled == generated


def test_native_tool_module_is_dependency_free_and_wired():
    source = (PKG / "tools" / "index.js").read_text(encoding="utf-8")
    assert "export function apply" in source
    assert "export const inject" in source
    assert "ctx.tools.register" in source
    assert "ctx.subprocess.spawn" in source
    # 只用 Node 内建模块：profile 里解析不到随 DSH 安装的 @deepseek-ai/* 包
    assert 'from "@deepseek-ai/' not in source
    assert "from '@deepseek-ai/" not in source
    assert 'import("@deepseek-ai/' not in source


def test_skill_frontmatter_is_discoverable():
    text = (SKILL_PKG / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "\nname: jiaodui\n" in text
    assert "\ndescription:" in text


def _skill_files(root: Path) -> set[str]:
    """比较交付文件，排除 Finder 自动生成且不入包的目录元数据。"""
    return {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and p.name != ".DS_Store"
    }


@pytest.mark.parametrize("relative", sorted(_skill_files(SKILL_SRC)))
def test_bundled_skill_matches_repo_source(relative: str):
    src = (SKILL_SRC / relative).read_bytes()
    dst = (SKILL_PKG / relative).read_bytes()
    assert src == dst, f"随包 skill 与仓库 skills/jiaodui 不一致：{relative}；请重新复制副本，勿手改"


def test_bundled_skill_has_no_extra_files():
    src_files = _skill_files(SKILL_SRC)
    dst_files = _skill_files(SKILL_PKG)
    assert dst_files == src_files


def test_vision_probe_white_png_is_ready_without_source_material():
    """白底探针随包可直接解码；透明资源无需在用户工作区现场渲染。"""
    from PIL import Image, ImageChops
    from xml.etree import ElementTree
    assets = SKILL_PKG / "assets"
    assert ElementTree.parse(assets / "vision-probe.svg").getroot().tag.endswith("svg")
    with Image.open(assets / "vision-probe-transparent.png") as source, Image.open(assets / "vision-probe.png") as ready:
        assert source.size == ready.size == (480, 480)
        assert source.mode == "RGBA" and source.getchannel("A").getextrema() == (0, 255)
        rgba = source.convert("RGBA")
        white = Image.new("RGBA", rgba.size, "white")
        white.alpha_composite(rgba)
        assert ImageChops.difference(white.convert("RGB"), ready.convert("RGB")).getbbox() is None
        assert ready.convert("RGBA").getchannel("A").getextrema() == (255, 255)
        assert ready.convert("RGB").getpixel((0, 0)) == (255, 255, 255)
        # 独立观察要求中的三个蓝点，避免提交空白或漏图的 PNG。
        for point in ((186, 415), (240, 415), (294, 415)):
            assert ready.convert("RGB").getpixel(point) == (40, 123, 209)
        assert ready.convert("RGB").getpixel((240, 240)) == (223, 51, 69)


def _cli_surface() -> tuple[set[str], set[str]]:
    """从 build_parser() 收集 (全部 option string, 全部子命令名)。"""
    import argparse

    from jiaodui.cli import build_parser

    options: set[str] = set()
    commands: set[str] = set()

    def walk(parser: argparse.ArgumentParser) -> None:
        for action in parser._actions:
            options.update(action.option_strings)
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    commands.add(name)
                    walk(sub)

    walk(build_parser())
    return options, commands


def test_plugin_emitted_subcommands_and_flags_exist_in_cli():
    """插件拼出的子命令与 --flag 必须真实注册（防臆造 / 改名漂移）。"""
    import re

    source = (PKG / "tools" / "index.js").read_text(encoding="utf-8")
    options, commands = _cli_surface()
    emitted = set(re.findall(r"'(--[a-z][a-z0-9-]+)'", source))
    unknown = sorted(emitted - options)
    assert not unknown, f"插件传了 CLI 没有注册的参数：{unknown}"
    for name in ("TASK_PREPARE_OPERATIONS", "DELIVERY_OPERATIONS"):
        assert f"const {name}" in source
        block = source.split(f"const {name} = [", 1)[1].split("]", 1)[0]
        declared = set(re.findall(r"'([a-z][a-z0-9-]*)'", block))
        assert declared <= commands, f"{name} 含未注册子命令：{sorted(declared - commands)}"


def test_prepare_and_delivery_tools_are_registered_without_argv_escape_hatch():
    """父侧准备/交付工具必须结构化注册，且不暴露 args 数组绕过 schema。"""
    source = (PKG / "tools" / "index.js").read_text(encoding="utf-8")
    for tool in ("jiaodui_task_prepare", "jiaodui_delivery"):
        assert f"'{tool}'" in source
    prepare = source.split("'jiaodui_task_prepare'", 1)[1].split("}, taskPrepareArgs)", 1)[0]
    assert "additionalProperties: false" in prepare
    assert "args:" not in prepare
    # 通用 argv 透传必须保留（CLI 是永久退路）
    assert "name: 'jiaodui'" in source

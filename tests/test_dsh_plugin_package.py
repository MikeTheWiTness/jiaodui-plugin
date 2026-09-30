"""dsh-jiaodui 插件包的打包契约测试。

只锁定「随包产物彼此一致、且是 DSH 能读的形态」，不验证宿主运行行为
（安装与实际运行需要真实 DSH profile，见 packages/dsh-jiaodui/README.md）。
YAML 用例需要 pyyaml（pyproject 的 dev 额外依赖）。
"""

from __future__ import annotations

import json
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


def test_preset_declares_jiaodui_with_full_agent_capabilities():
    config = _preset_config()
    assert config["id"] == "jiaodui"
    assert config["name"] == "校对"
    assert isinstance(config["order"], int)
    plugins = {p["id"]: p for p in config["plugins"]}
    # 预设必须自带完整 plugins 列表（DSH 不提供继承）：抽查核心能力仍在
    for required in ("persona", "tool-bash", "tool-fs", "tool-skill", "tool-todo", "tool-web"):
        assert required in plugins, f"preset 缺少公共能力：{required}"
    assert "tool-subagent" in {p["id"] for p in plugins["delegation"]["config"]}


def test_preset_mounts_bundled_skill_dir_and_native_tool():
    plugins = {p["id"]: p for p in _preset_config()["plugins"]}
    dirs = plugins["skill-filesystem"]["config"]["customSkillDirs"]
    assert len(dirs) == 1
    assert "'skills'" in dirs[0] and "baseUrl" in dirs[0]
    assert "resolve('dsh-jiaodui/package.json')" in dirs[0]
    assert plugins["jiaodui-tools"]["name"] == "dsh-jiaodui"


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

"""dsh-jiaodui / dsh-jiaodui-chemistry 插件包的打包契约测试。

只锁定「随包产物彼此一致、且是 DSH 能读的形态」，不验证宿主运行行为
（安装与实际运行需要真实 DSH profile，见 packages/*/README.md）。
YAML 用例需要 pyyaml（pyproject 的 dev 额外依赖）。

两个学科包各自独立安装，但共用同一份 Python 内核与同一套学科无关原生工具：
因此这里既按包参数化检查各自的结构，也检查两包的原生工具模块没有隐式分叉。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent

# 已落地的学科插件包：新增一个学科包就在这里加一行，全部结构契约随即覆盖它。
BUNDLES: dict[str, dict] = {
    "dsh-jiaodui": {
        "root": ROOT / "packages" / "dsh-jiaodui",
        "skill": "jiaodui",
        "preset_row": "preset-jiaodui",
        "preset_id": "jiaodui",
        "preset_name": "校对",
        "order": 10,
        "child_preset_row": "preset-jiaodui-unit",
        "child_preset_id": "jiaodui-unit",
        "child_preset_name": "校对（高中物理·单元子代理）",
        "child_order": 12,
    },
    "dsh-jiaodui-chemistry": {
        "root": ROOT / "packages" / "dsh-jiaodui-chemistry",
        "skill": "jiaodui-chemistry",
        "preset_row": "preset-jiaodui-chemistry",
        "preset_id": "jiaodui-chemistry",
        "preset_name": "校对（高中化学）",
        "order": 11,
        "child_preset_row": "preset-jiaodui-chemistry-unit",
        "child_preset_id": "jiaodui-chemistry-unit",
        "child_preset_name": "校对（高中化学·单元子代理）",
        "child_order": 13,
    },
}
BUNDLE_IDS = sorted(BUNDLES)

PKG = BUNDLES["dsh-jiaodui"]["root"]
SKILL_SRC = ROOT / "skills" / "jiaodui"
SKILL_PKG = PKG / "skills" / "jiaodui"


class _Loader(yaml.SafeLoader):
    """保留 !!js 表达式原文——这里只做结构检查，不求值。"""


def _js(loader: yaml.SafeLoader, node: yaml.Node) -> str:
    return loader.construct_scalar(node)  # type: ignore[arg-type]


_Loader.add_constructor("tag:yaml.org,2002:js", _js)
_Loader.add_constructor("!js", _js)


def _bundle(bundle: str) -> dict:
    return BUNDLES[bundle]


def _package_root(bundle: str) -> Path:
    return _bundle(bundle)["root"]


def _load_patch(bundle: str = "dsh-jiaodui") -> list:
    with (_package_root(bundle) / "cordis.patch.yml").open(encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)


def _preset_row(bundle: str = "dsh-jiaodui") -> dict:
    rows = _load_patch(bundle)[0]["insert"]
    return next(r for r in rows if r["id"] == _bundle(bundle)["preset_row"])


def _preset_config(bundle: str = "dsh-jiaodui") -> dict:
    return _preset_row(bundle)["config"]


def _preset_row_by_id(bundle: str, row_id: str) -> dict:
    rows = _load_patch(bundle)[0]["insert"]
    return next(r for r in rows if r["id"] == row_id)


def _child_preset_config(bundle: str = "dsh-jiaodui") -> dict:
    return _preset_row_by_id(bundle, _bundle(bundle)["child_preset_row"])["config"]


def test_ci_runs_final_release_installer_on_macos_and_pauses_windows():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))
    job = workflow["jobs"]["contracts"]
    assert job["env"]["PYTHONUTF8"] == "1"
    assert "windows-2022" not in job["strategy"]["matrix"]["os"]
    steps = job["steps"]
    named = {step.get("name"): step for step in steps if step.get("name")}
    prepare = named["Prepare isolated release smoke (macOS)"]
    install = named["Install final package (macOS)"]
    assert prepare["if"] == "runner.os == 'macOS'"
    assert install["if"] == "runner.os == 'macOS'"
    assert "prepare-smoke-package.py" in prepare["run"]
    assert "install-macos.sh" in install["run"]
    assert "jiaodui-release-smoke" in install["working-directory"]
    assert not any("Windows" in name for name in named)


def test_release_smoke_package_matches_final_installer_layout(tmp_path):
    import importlib.util
    import hashlib

    helper_path = ROOT / "scripts" / "release" / "prepare-smoke-package.py"
    spec = importlib.util.spec_from_file_location("prepare_smoke_package", helper_path)
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    version = json.loads((PKG / "package.json").read_text(encoding="utf-8"))["version"]
    wheel = tmp_path / f"jiaodui-{version}-py3-none-any.whl"
    wheel.write_bytes(b"synthetic wheel placeholder")
    output = helper.prepare(ROOT, wheel, tmp_path / "release")

    # 归档必须同时带两个学科 bundle：目标机可以只装其中一个，但发布只有一份。
    for name in BUNDLE_IDS:
        assert (output / name / "package.json").is_file()
        assert (output / name / "cordis.patch.yml").is_file()
    assert (output / wheel.name).is_file()
    assert (output / "install-windows.ps1").is_file()
    entries = (output / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert entries
    for entry in entries:
        digest, relative = entry.split("  ", 1)
        assert hashlib.sha256((output / relative).read_bytes()).hexdigest() == digest


def test_release_manifest_versions_and_runtime_constraints_are_complete():
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    manifest = json.loads((PKG / "package.json").read_text(encoding="utf-8"))
    assert project["version"] == manifest["version"]

    constraints_path = ROOT / "scripts" / "release" / "runtime-constraints.txt"
    constraints = {}
    for line in constraints_path.read_text(encoding="utf-8").splitlines():
        name, version = line.split("==", 1)
        key = canonicalize_name(name)
        assert key not in constraints, f"重复依赖约束：{name}"
        constraints[key] = version
    required = [*project["dependencies"], *project["optional-dependencies"]["render"]]
    for raw_requirement in required:
        requirement = Requirement(raw_requirement)
        assert canonicalize_name(requirement.name) in constraints

    for script in ("build-release.sh", "prepare-smoke-package.py", "install-macos.sh", "install-windows.ps1", "README.md"):
        assert (ROOT / "scripts" / "release" / script).is_file()
    builder = (ROOT / "scripts" / "release" / "build-release.sh").read_text(encoding="utf-8")
    assert 'tar -czf "$ARCHIVE"' in builder
    assert 'hash_files "$(basename -- "$ARCHIVE")"' in builder
    mac_installer = (ROOT / "scripts" / "release" / "install-macos.sh").read_text(encoding="utf-8")
    windows_installer = (ROOT / "scripts" / "release" / "install-windows.ps1").read_text(encoding="utf-8")
    assert "pip install --force-reinstall --constraint" in mac_installer
    assert "pip install --force-reinstall --constraint" in windows_installer
    assert "pip check" in mac_installer and "pip check" in windows_installer


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_bundle_versions_match_core_version(bundle: str):
    """两个 bundle 与 Python CLI 同版本发布：版本漂移会让 CLI 自动发现找不到运行时。"""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    manifest = json.loads((_package_root(bundle) / "package.json").read_text(encoding="utf-8"))
    assert manifest["version"] == project["version"]


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_manifest_declares_bundle_plugin_and_display_metadata(bundle: str):
    root = _package_root(bundle)
    manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == bundle
    assert manifest["type"] == "module"
    assert manifest["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert (root / manifest["dsh"]["bundle"]["patch"]).is_file()
    # 同名包既要能被相对路径挂载，也要能按包名解析（自引用 package.json）
    assert manifest["exports"]["."] == "./tools/index.js"
    assert manifest["exports"]["./package.json"] == "./package.json"
    assert manifest["icon"].startswith("./")
    assert (root / "locale" / "zh.json").is_file()
    assert (root / "locale" / "en.json").is_file()
    # 随包 skill 必须在 files 清单声明的目录下，且目录名与注册的 skill 名一致
    assert "skills/" in manifest["files"]
    assert (root / "skills" / BUNDLES[bundle]["skill"] / "SKILL.md").is_file()


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_preset_declares_subject_identity_and_minimal_agent_capabilities(bundle: str):
    meta = _bundle(bundle)
    config = _preset_config(bundle)
    assert config["id"] == meta["preset_id"]
    assert config["name"] == meta["preset_name"]
    assert config["order"] == meta["order"]
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


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_preset_uses_standard_native_tools_and_keeps_parallel_delegation(bundle: str):
    """校对使用标准工具呈现；PTC 引擎不启用，普通子 agent 仍可并行派发。"""
    plugins = {p["id"]: p for p in _preset_config(bundle)["plugins"]}
    assert plugins["tool-presentation"]["config"]["mode"] == "native"
    delegation = {p["id"]: p for p in plugins["delegation"]["config"]}
    assert delegation["workflow-ptc"]["disabled"] is True
    assert delegation["tool-subagent"].get("disabled", False) is False
    subagent = delegation["tool-subagent"]["config"]
    assert subagent["provider"] == "spawn"
    assert subagent["maxDepth"] == 1
    # 0.2.1 起子代理工具面由独立子 preset 决定；subagent 行不再接受 toolFilter/persona。
    assert subagent["agentPreset"] == _bundle(bundle)["child_preset_id"]
    assert "toolFilter" not in subagent
    assert "backgroundMode" not in subagent
    assert "persona" not in subagent
    child_plugins = {p["id"]: p for p in _child_preset_config(bundle)["plugins"]}
    assert child_plugins["jiaodui-tools"]["config"]["toolset"] == "unit"
    assert not {"agent-instructions", "tool-bash", "tool-pwsh", "tool-fs-search", "tool-todo"} & set(child_plugins)
    assert plugins["tool-todo"]["config"]["allowParallelInProgress"] is True


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_unit_subagents_cannot_cancel_their_own_unit(bundle: str):
    """单元子代理拿不到 `jiaodui_unit_cancel`：取消只由父代理/宿主记录。

    第 12 讲实测：取消曾作为 `unit-event` 的两个可选 enum 暴露，单元子代理在正常
    `prepared` 心跳里填 `user`/`user_cancel`，在 8 个单元上伪造约 29 条用户取消；
    `dispatch-plan` 只要有取消记录就永久 `stop=true`，父代理只能 `--rerun` 逃出，
    又让在途子代理的 `expected_run_id` 全部失效（`run-changed`），整轮最终无交付。
    """
    plugins = {p["id"]: p for p in _preset_config(bundle)["plugins"]}
    delegation = {p["id"]: p for p in plugins["delegation"]["config"]}
    assert delegation["tool-subagent"]["config"]["agentPreset"] == _bundle(bundle)["child_preset_id"]
    child_plugins = {p["id"]: p for p in _child_preset_config(bundle)["plugins"]}
    assert child_plugins["jiaodui-tools"]["config"]["toolset"] == "unit"
    # 具体注册集合由 test_dsh_plugin_tool_behavior.py 的真 Node 用例锁住：
    # unit 模式保留 jiaodui_unit_event，但不注册 jiaodui_unit_cancel。


def test_chemistry_child_subagents_can_use_chemistry_calc_tools():
    """化学单元子代理必须拿到配平与计量工具，否则「必须实算」在子代理侧无法执行。"""
    child_plugins = {p["id"]: p for p in _child_preset_config("dsh-jiaodui-chemistry")["plugins"]}
    assert child_plugins["jiaodui-tools"]["config"]["toolset"] == "unit"
    calc = json.loads((_package_root("dsh-jiaodui-chemistry") / "tools" / "calc-schemas.json")
                      .read_text(encoding="utf-8"))
    # toolset: unit 放行全部 calc_*；这里锁住化学两个 operation 确实在共享 schema 里。
    assert {"chemistry_balance", "stoichiometry"} <= set(calc["operations"])


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_child_preset_is_read_only_and_omits_agent_instructions(bundle: str):
    """单元子预设是封闭只读面：无 shell、无 write/edit、无父复核/取消；不挂 AGENTS.md。"""
    child = _child_preset_config(bundle)
    assert child["id"] == _bundle(bundle)["child_preset_id"]
    assert child["name"] == _bundle(bundle)["child_preset_name"]
    assert child["order"] == _bundle(bundle)["child_order"]
    plugins = {p["id"]: p for p in child["plugins"]}
    assert "agent-instructions" not in plugins, "子预设先不挂工作区指令，规则以 SKILL 与派发 prompt 为准"
    assert plugins["tool-fs"]["config"] == {
        "read": True, "readImage": True, "write": False, "edit": False}
    assert plugins["jiaodui-tools"]["name"] == bundle
    assert plugins["jiaodui-tools"]["config"]["toolset"] == "unit"
    assert plugins["tool-presentation"]["config"]["mode"] == "native"
    assert plugins["skill-filesystem"]["config"]["includeDefaultRoots"] is False
    dirs = plugins["skill-filesystem"]["config"]["customSkillDirs"]
    assert len(dirs) == 1
    assert f"resolve('{bundle}/package.json')" in dirs[0]


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_preset_mounts_bundled_skill_dir_and_native_tool(bundle: str):
    plugins = {p["id"]: p for p in _preset_config(bundle)["plugins"]}
    assert plugins["skill-filesystem"]["config"]["includeDefaultRoots"] is False
    dirs = plugins["skill-filesystem"]["config"]["customSkillDirs"]
    assert len(dirs) == 1
    assert "'skills'" in dirs[0] and "baseUrl" in dirs[0]
    assert f"resolve('{bundle}/package.json')" in dirs[0]
    assert plugins["jiaodui-tools"]["name"] == bundle


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_calc_tool_schemas_match_python_core_export(bundle: str):
    result = subprocess.run(
        [sys.executable, "-m", "jiaodui", "calc-schema", "--json"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    generated = json.loads(result.stdout)
    bundled = json.loads((_package_root(bundle) / "tools" / "calc-schemas.json").read_text(encoding="utf-8"))
    assert bundled == generated


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_proposal_schema_bundle_matches_python_core_export(bundle: str):
    result = subprocess.run(
        [sys.executable, "-m", "jiaodui", "unit-schema", "--json"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    generated = json.loads(result.stdout)
    bundled = json.loads((_package_root(bundle) / "tools" / "proposal-schema.json").read_text(encoding="utf-8"))
    assert bundled == generated


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_bind_current_proposal_schema_bundle_matches_python_core_export(bundle: str):
    result = subprocess.run(
        [sys.executable, "-m", "jiaodui", "unit-schema", "--bind-current", "--json"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    generated = json.loads(result.stdout)
    bundled = json.loads((_package_root(bundle) / "tools" / "proposal-schema-bind-current.json")
                         .read_text(encoding="utf-8"))
    assert bundled == generated
    full = json.loads((_package_root(bundle) / "tools" / "proposal-schema.json")
                      .read_text(encoding="utf-8"))["schema"]
    identities = {"task_id", "unit_id", "run_id", "source_sha256", "body_sha256", "proposal_revision"}
    assert set(full["required"]) - set(bundled["schema"]["required"]) == identities
    assert set(bundled["schema"]["required"]) <= set(full["required"])
    assert full["properties"] == bundled["schema"]["properties"]


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_v3_proposal_schema_bundle_matches_python_core_export(bundle: str):
    """正常插件提案完整复用 core v3 schema，CLI 版本选择不得漂移。"""
    from jiaodui.proposal_v3 import proposal_json_schema

    result = subprocess.run(
        [sys.executable, "-m", "jiaodui", "unit-schema", "--schema-version", "3", "--json"],
        cwd=ROOT, capture_output=True, text=True, check=True)
    bundled = json.loads((_package_root(bundle) / "tools" / "proposal-schema-v3.json")
                         .read_text(encoding="utf-8"))
    assert bundled == json.loads(result.stdout) == {"schema": proposal_json_schema()}


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_native_tool_module_is_dependency_free_and_wired(bundle: str):
    source = (_package_root(bundle) / "tools" / "index.js").read_text(encoding="utf-8")
    assert "export function apply" in source
    assert "export const inject" in source
    assert "ctx.tools.register" in source
    assert "ctx.subprocess.spawn" in source
    # 只用 Node 内建模块：profile 里解析不到随 DSH 安装的 @deepseek-ai/* 包
    assert 'from "@deepseek-ai/' not in source
    assert "from '@deepseek-ai/" not in source
    assert 'import("@deepseek-ai/' not in source


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_preset_filter_is_shipped_and_wired(bundle: str):
    """子 preset 仍可被 tool-subagent 解析；过滤插件负责把它从 UI roster 隐藏。"""
    root = _package_root(bundle)
    source = (root / "tools" / "preset-filter.js").read_text(encoding="utf-8")
    assert "export function apply" in source
    assert "export const inject = ['agentPresets']" in source
    assert "remoteExportList" in source
    assert "@deepseek-ai/" not in source
    manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
    assert manifest["exports"]["./preset-filter"] == "./tools/preset-filter.js"
    rows = _load_patch(bundle)[0]["insert"]
    assert any(row.get("name") == f"{bundle}/preset-filter" for row in rows)
    child_ids = [
        row["config"]["id"] for row in rows
        if row.get("name") == "@deepseek-ai/dsh-agent-preset"
        and str(row.get("config", {}).get("id", "")).endswith("-unit")
    ]
    assert child_ids, "每个学科包至少应声明一个内部子 agent preset"
    for identity in child_ids:
        assert f"'{identity}'" in source, f"preset-filter 未隐藏子 preset：{identity}"


def test_native_tool_modules_do_not_fork_between_bundles():
    """两个学科包的 tools/ 必须逐字节一致：工具是学科无关的，分叉意味着隐患。"""
    diffs: list[str] = []
    for relative in ("index.js", "preset-filter.js", "calc-schemas.json", "proposal-schema.json", "proposal-schema-bind-current.json", "proposal-schema-v3.json"):
        first = (BUNDLES["dsh-jiaodui"]["root"] / "tools" / relative).read_bytes()
        second = (BUNDLES["dsh-jiaodui-chemistry"]["root"] / "tools" / relative).read_bytes()
        if first != second:
            diffs.append(relative)
    assert not diffs, f"两个学科包的 tools/ 已经分叉：{diffs}；请统一改动并同步复制"


def _git_tracked(pathspec: str) -> set[str]:
    """返回 git 索引里的路径；不在工作树（如 sdist 解包）时跳过。"""
    if not (ROOT / ".git").exists():
        pytest.skip("不在 git 工作树中，跳过跟踪性检查")
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "--", pathspec],
            capture_output=True, check=True)
    except FileNotFoundError:
        pytest.skip("未安装 git，跳过跟踪性检查")
    return {item.decode("utf-8") for item in result.stdout.split(b"\0") if item}


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_bundle_tools_files_are_tracked(bundle: str):
    """发布脚本只拷 git ls-files；tools/ 里的未跟踪文件会让安装包缺文件。"""
    tools = _package_root(bundle) / "tools"
    tracked = _git_tracked(f"packages/{bundle}/tools")
    present = {
        f"packages/{bundle}/tools/{path.relative_to(tools).as_posix()}"
        for path in tools.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    }
    missing = sorted(present - tracked)
    assert not missing, f"{bundle}/tools 存在未跟踪文件，发布包会缺：{missing}"


def _timeout_values(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "timeoutMs" and isinstance(value, int) and not isinstance(value, bool):
                yield value
            else:
                yield from _timeout_values(value)
    elif isinstance(node, list):
        for item in node:
            yield from _timeout_values(item)


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_lock_wait_leaves_headroom_before_plugin_timeout(bundle: str):
    """锁等待必须显著小于插件子进程超时，否则宿主先杀进程，lock-timeout 发不出去。"""
    from jiaodui.material import MATERIAL_LOCK_TIMEOUT_SECONDS

    budgets = list(_timeout_values(_load_patch(bundle)))
    assert budgets, f"{bundle} 的 patch 未配置 timeoutMs"
    wait_ms = MATERIAL_LOCK_TIMEOUT_SECONDS * 1000
    headroom_ms = min(budgets) - wait_ms
    assert headroom_ms >= 30_000, (
        f"{bundle} 的最小 timeoutMs={min(budgets)} 与材料锁等待 {wait_ms:.0f}ms "
        f"之间只有 {headroom_ms:.0f}ms；宿主会先中止进程，结构化 lock-timeout 无法返回")


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_skill_frontmatter_is_discoverable(bundle: str):
    skill_root = _package_root(bundle) / "skills" / _bundle(bundle)["skill"]
    text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---")
    assert f"\nname: {_bundle(bundle)['skill']}\n" in text
    assert "\ndescription:" in text


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_bundled_skill_matches_repo_source(bundle: str):
    source_root = ROOT / "skills" / _bundle(bundle)["skill"]
    mirror_root = _package_root(bundle) / "skills" / _bundle(bundle)["skill"]
    files = sorted(p for p in source_root.rglob("*") if p.is_file() and p.name != ".DS_Store")
    assert files, "随包 skill 源目录不能为空"
    for path in files:
        relative = path.relative_to(source_root)
        mirror = mirror_root / relative
        assert mirror.is_file(), f"随包 skill 缺文件：{relative}"
        assert path.read_bytes() == mirror.read_bytes(), (
            f"随包 skill 与仓库 skills/{_bundle(bundle)['skill']} 不一致：{relative}；请重新复制副本，勿手改"
        )


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_bundled_skill_has_no_extra_files(bundle: str):
    source_root = ROOT / "skills" / _bundle(bundle)["skill"]
    mirror_root = _package_root(bundle) / "skills" / _bundle(bundle)["skill"]
    source_files = {p.relative_to(source_root) for p in source_root.rglob("*")
                    if p.is_file() and p.name != ".DS_Store"}
    mirror_files = {p.relative_to(mirror_root) for p in mirror_root.rglob("*")
                    if p.is_file() and p.name != ".DS_Store"}
    assert mirror_files == source_files, sorted(mirror_files ^ source_files)


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_vision_probe_white_png_is_ready_without_source_material(bundle: str):
    """白底探针随包可直接解码；透明资源无需在用户工作区现场渲染。"""
    from PIL import Image, ImageChops
    from xml.etree import ElementTree
    assets = _package_root(bundle) / "skills" / _bundle(bundle)["skill"] / "assets"
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


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_plugin_emitted_subcommands_and_flags_exist_in_cli(bundle: str):
    """插件拼出的子命令与 --flag 必须真实注册（防臆造 / 改名漂移）。"""
    import re

    source = (_package_root(bundle) / "tools" / "index.js").read_text(encoding="utf-8")
    options, commands = _cli_surface()
    emitted = set(re.findall(r"'(--[a-z][a-z0-9-]+)'", source))
    unknown = sorted(emitted - options)
    assert not unknown, f"插件传了 CLI 没有注册的参数：{unknown}"
    for name in ("TASK_PREPARE_OPERATIONS", "DELIVERY_OPERATIONS"):
        assert f"const {name}" in source
        block = source.split(f"const {name} = [", 1)[1].split("]", 1)[0]
        declared = set(re.findall(r"'([a-z][a-z0-9-]*)'", block))
        assert declared <= commands, f"{name} 含未注册子命令：{sorted(declared - commands)}"


@pytest.mark.parametrize("bundle", BUNDLE_IDS)
def test_prepare_and_delivery_tools_are_registered_without_argv_escape_hatch(bundle: str):
    """父侧准备/交付工具必须结构化注册，且不暴露 args 数组绕过 schema。"""
    source = (_package_root(bundle) / "tools" / "index.js").read_text(encoding="utf-8")
    for tool in ("jiaodui_task_prepare", "jiaodui_delivery"):
        assert f"'{tool}'" in source
    prepare = source.split("'jiaodui_task_prepare'", 1)[1].split("}, taskPrepareArgs)", 1)[0]
    assert "additionalProperties: false" in prepare
    assert "args:" not in prepare
    # 通用 argv 透传必须保留（CLI 是永久退路）
    assert "name: 'jiaodui'" in source

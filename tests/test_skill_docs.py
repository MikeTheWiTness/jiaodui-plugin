"""skill 文档 / 双副本 / 学科配置的一致性（R-H01 一致性侧、R-H04）。

文档与 CLI 是两份人工维护的清单，已经漂移过一次（速查表漏记
--out-dir/--base-name/--mathjax/--no-clean/--rerun/--version）。这里把
"文档提到的参数必须真实存在""两份副本必须字节一致"钉成测试。

入口体积另有一条硬约束：DSH 预设的 tool-result-pruner 阈值是 8192 个 Unicode 码点，
压缩触发时会把超预算的工具结果裁成「前 4096 + 标记 + 后 1024」。`skill` 工具把整份
SKILL.md 当单个文本块返回，所以入口必须留在阈值内；命令速查等细节放在
`references/operation-manual.md`，参数与命令断言因此覆盖整个 skill 目录。
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "jiaodui"
PACKAGED_DIR = ROOT / "packages" / "dsh-jiaodui" / "skills" / "jiaodui"

# 入口正文必须留在宿主工具结果修剪阈值内（Unicode 码点）
SKILL_ENTRY_MAX_CHARS = 8192

# 曾被文档漏记、必须出现在 skill 文档（入口或 references）里的实参
MUST_BE_DOCUMENTED = (
    "--out-dir", "--base-name", "--mathjax", "--no-clean", "--rerun",
    "--version", "--out-root", "--work-root", "--replace-units", "--adopt-units",
    "--apply",
)


def _skill_docs() -> dict[str, str]:
    """入口与全部 references 的文本（键为相对 SKILL_DIR 的路径）。"""
    return {
        str(path.relative_to(SKILL_DIR)): path.read_text(encoding="utf-8")
        for path in sorted(SKILL_DIR.rglob("*.md"))
    }


def _cli_options() -> set[str]:
    """递归收集 build_parser() 里注册的全部 option string。"""
    from jiaodui.cli import build_parser

    options: set[str] = set()

    def walk(parser: argparse.ArgumentParser) -> None:
        for action in parser._actions:
            options.update(action.option_strings)
            if isinstance(action, argparse._SubParsersAction):
                for sub in action.choices.values():
                    walk(sub)

    walk(build_parser())
    return options


def test_skill_documented_flags_exist_in_cli():
    """skill 文档里出现的每个 --flag 都必须在 CLI 上真实注册（防臆造/改名漂移）。"""
    options = _cli_options()
    unknown: dict[str, list[str]] = {}
    for name, text in _skill_docs().items():
        documented = set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]+", text))
        bad = sorted(documented - options)
        if bad:
            unknown[name] = bad
    assert not unknown, f"文档提到了 CLI 没有注册的参数：{unknown}"


def test_skill_documents_parameters_that_had_drifted():
    """速查表（入口或 operation-manual）必须覆盖这些实际存在的参数。"""
    corpus = "\n".join(_skill_docs().values())
    missing = [flag for flag in MUST_BE_DOCUMENTED if flag not in corpus]
    assert not missing, f"skill 文档漏记：{missing}"


def test_skill_entry_stays_within_pruner_char_budget():
    """入口正文必须 ≤ 8192 码点，否则宿主压缩时会裁掉流程主体。"""
    entry = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    length = len(entry)
    assert length <= SKILL_ENTRY_MAX_CHARS, (
        f"SKILL.md 为 {length} 码点，超过宿主修剪阈值 {SKILL_ENTRY_MAX_CHARS}；"
        "细节请移入 references/operation-manual.md"
    )


def test_skill_entry_referenced_files_exist():
    """入口里链接的 references/ 文件必须真实存在（链接不能指向空处）。"""
    entry = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    missing = []
    for target in re.findall(r"\]\((?!https?:)([^)#\s]+)\)", entry):
        if not (SKILL_DIR / target).is_file():
            missing.append(target)
    assert not missing, f"SKILL.md 链接的文件不存在：{missing}"


def test_harness_call_contract_is_documented():
    """run_code 外层 schema 与异步派发句柄必须明确，防止文档再次诱发误调用。"""
    text = (SKILL_DIR / "references" / "failure-modes.md").read_text(encoding="utf-8")
    required = ("run_code.justification", "非空完整句子", "invalid justification",
                "await Promise.allSettled(", "continuable.subagentId", "未 await 的 Promise")
    missing = [item for item in required if item not in text]
    assert not missing, f"宿主调用契约缺少说明：{missing}"


def test_repair_preview_is_documented_as_explicit_gate_auxiliary():
    """完整性修复必须是显式命令，且 verify-report 仍是唯一闸门。"""
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    failures = (SKILL_DIR / "references" / "failure-modes.md").read_text(encoding="utf-8")
    assert "jiaodui repair-report" in skill
    assert "verify-report" in skill
    assert "repair-report" in failures
    assert "唯一闸门" in skill or "唯一闸门" in failures


def _unknown_documented_commands(text: str) -> set[str]:
    """用真实 parser / calc 注册表核对文档中的具体命令；忽略占位参数。"""
    from jiaodui.calc import OPERATIONS
    from jiaodui.cli import CALC_ALIASES, build_parser

    parser = build_parser()
    commands = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            commands.update(action.choices)
    mentioned = set(re.findall(r"\bjiaodui(?:[ \t]+--(?:json|quiet))*[ \t]+([a-z][a-z-]*)", text))
    unknown = {f"jiaodui {command}" for command in mentioned - commands}
    for op in re.findall(r"\bcalc[ \t]+([a-z][a-z0-9_]*)", text):
        if CALC_ALIASES.get(op, op) not in OPERATIONS:
            unknown.add(f"calc {op}")
    return unknown


def test_command_check_rejects_nonexistent_calc_metadata_query():
    """历史误写必须被检出，即使它出现在说明段而非速查代码块。"""
    text = "内部名出在 `calc operations --json` 的元数据里。"
    assert _unknown_documented_commands(text) == {"calc operations"}


def test_command_check_accepts_real_commands_and_calc_aliases():
    """合法可见名、内部别名和占位命令不应误报。"""
    text = ("jiaodui --json status <paper_dir>\n"
            "jiaodui calc <op>\n"
            "calc dimension / calc dimensional / calc vector / calc vector_ops\n"
            "calc circle / calc circle_from_two_points")
    assert _unknown_documented_commands(text) == set()


def test_skill_concrete_commands_exist_in_cli():
    """入口及所有 references 的具体命令都应由当前 CLI 支持。"""
    problems = {}
    for path in sorted(SKILL_DIR.rglob("*.md")):
        unknown = _unknown_documented_commands(path.read_text(encoding="utf-8"))
        if unknown:
            problems[str(path.relative_to(SKILL_DIR))] = sorted(unknown)
    assert not problems, problems


def test_command_check_rejects_unknown_top_level_command():
    """不存在的顶层命令也必须被检出，包括前置全局开关。"""
    assert _unknown_documented_commands(
        "jiaodui --quiet --json invented-command <paper_dir>"
    ) == {"jiaodui invented-command"}


def test_packaged_skill_is_byte_identical():
    """skills/jiaodui 与 packages 内副本必须字节一致（.DS_Store 除外）。"""
    diffs: list[str] = []
    for path in sorted(SKILL_DIR.rglob("*")):
        if not path.is_file() or path.name == ".DS_Store":
            continue
        mirror = PACKAGED_DIR / path.relative_to(SKILL_DIR)
        if not mirror.is_file():
            diffs.append(f"缺副本：{mirror.relative_to(ROOT)}")
        elif mirror.read_bytes() != path.read_bytes():
            diffs.append(f"内容不一致：{path.relative_to(ROOT)}")
    assert not diffs, diffs


def test_subject_config_copies_are_identical():
    """运行时读 jiaodui/data/subjects/，文档与测试指向 config/subjects/。

    两份都在仓库里，必须逐份字节一致（单一来源的最终归属见决策 5 / R-H01）。
    """
    runtime = ROOT / "jiaodui" / "data" / "subjects"
    documented = ROOT / "config" / "subjects"
    diffs: list[str] = []
    for path in sorted(runtime.glob("*.json")):
        mirror = documented / path.name
        if not mirror.is_file():
            diffs.append(f"缺副本：{mirror.relative_to(ROOT)}")
        elif mirror.read_bytes() != path.read_bytes():
            diffs.append(f"内容不一致：{path.name}")
    for path in sorted(documented.glob("*.json")):
        if not (runtime / path.name).is_file():
            diffs.append(f"缺运行时副本：{path.name}")
    assert not diffs, diffs

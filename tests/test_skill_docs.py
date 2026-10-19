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

import pytest

ROOT = Path(__file__).resolve().parents[1]

# 已落地学科各有自己的入口 skill：仓库源目录 ↔ 随包副本目录。
# 两份副本必须逐字节一致，通用流程（命名 / 闸门 / 预算 / 宿主纪律）在每份里都必须完整。
SKILLS: dict[str, tuple[Path, Path]] = {
    "jiaodui": (ROOT / "skills" / "jiaodui", ROOT / "packages" / "dsh-jiaodui" / "skills" / "jiaodui"),
    "jiaodui-chemistry": (
        ROOT / "skills" / "jiaodui-chemistry",
        ROOT / "packages" / "dsh-jiaodui-chemistry" / "skills" / "jiaodui-chemistry",
    ),
}
SKILL_DIR = SKILLS["jiaodui"][0]
PACKAGED_DIR = SKILLS["jiaodui"][1]

# 注意：每个入口只需要点名「本学科」；数学/语文等学科名可以出现在入口的未落地提示里，
# 因此这里只禁用**另一门已落地学科**的专属口径词。
FOREIGN_SUBJECT_TERMS = {
    "jiaodui": ("化学方程式", "离子方程式", "电解质", "物质的量"),
    "jiaodui-chemistry": ("受力图", "量纲分析", "牛顿", "电路图"),
}

# 入口正文必须留在宿主工具结果修剪阈值内（Unicode 码点）
SKILL_ENTRY_MAX_CHARS = 8192

# 曾被文档漏记、必须出现在 skill 文档（入口或 references）里的实参
MUST_BE_DOCUMENTED = (
    "--out-dir", "--base-name", "--mathjax", "--no-clean", "--rerun",
    "--version", "--out-root", "--work-root", "--replace-units", "--adopt-units",
    "--apply",
)


def _skill_dir(skill: str) -> Path:
    return SKILLS[skill][0]


def _skill_docs(skill: str = "jiaodui") -> dict[str, str]:
    """入口与全部 references 的文本（键为相对该 skill 根目录的路径）。"""
    root = _skill_dir(skill)
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*.md"))
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


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_skill_documented_flags_exist_in_cli(skill: str):
    """skill 文档里出现的每个 --flag 都必须在 CLI 上真实注册（防臆造/改名漂移）。"""
    options = _cli_options()
    unknown: dict[str, list[str]] = {}
    for name, text in _skill_docs(skill).items():
        documented = set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]+", text))
        bad = sorted(documented - options)
        if bad:
            unknown[name] = bad
    assert not unknown, f"文档提到了 CLI 没有注册的参数：{unknown}"


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_skill_documents_parameters_that_had_drifted(skill: str):
    """速查表（入口或 operation-manual）必须覆盖这些实际存在的参数。"""
    corpus = "\n".join(_skill_docs(skill).values())
    missing = [flag for flag in MUST_BE_DOCUMENTED if flag not in corpus]
    assert not missing, f"skill 文档漏记：{missing}"


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_skill_entry_stays_within_pruner_char_budget(skill: str):
    """入口正文必须 ≤ 8192 码点，否则宿主压缩时会裁掉流程主体。"""
    entry = (_skill_dir(skill) / "SKILL.md").read_text(encoding="utf-8")
    length = len(entry)
    assert length <= SKILL_ENTRY_MAX_CHARS, (
        f"{skill}/SKILL.md 为 {length} 码点，超过宿主修剪阈值 {SKILL_ENTRY_MAX_CHARS}；"
        "细节请移入 references/operation-manual.md"
    )


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_skill_entry_referenced_files_exist(skill: str):
    """入口里链接的 references/ 文件必须真实存在（链接不能指向空处）。"""
    root = _skill_dir(skill)
    entry = (root / "SKILL.md").read_text(encoding="utf-8")
    missing = []
    for target in re.findall(r"\]\((?!https?:)([^)#\s]+)\)", entry):
        if not (root / target).is_file():
            missing.append(target)
    assert not missing, f"{skill}/SKILL.md 链接的文件不存在：{missing}"


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_skill_entry_only_speaks_for_its_own_subject(skill: str):
    """每个入口只讲自己那门学科：化学入口不得夹带物理口径，物理入口不得夹带化学口径。"""
    entry = (_skill_dir(skill) / "SKILL.md").read_text(encoding="utf-8")
    foreign = [term for term in FOREIGN_SUBJECT_TERMS[skill] if term in entry]
    assert not foreign, f"{skill}/SKILL.md 混入了其他学科的口径：{foreign}"


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_skill_declares_its_own_name(skill: str):
    """frontmatter 的 name 必须是本 skill 的目录名，否则宿主发现与调用会错位。"""
    entry = (_skill_dir(skill) / "SKILL.md").read_text(encoding="utf-8")
    assert entry.startswith("---")
    assert f"\nname: {skill}\n" in entry
    assert "\ndescription:" in entry


# 学科核验纪律：只要写在该 skill 的任意一份文档里即可（物理写在入口、化学写在学科规范），
# 但每门学科都必须完整保留这些语义，不能被学科改写时删掉。
SUBJECT_DOC_MUST_KEEP = (
    "结论断言 → calc `call_id`",
    "不能替代系数或代数推导验证",
    "解析扩写或符合题设的结论",
)


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_skill_documents_host_read_limit_and_review_scope_rules(skill: str):
    root = _skill_dir(skill)
    docs = _skill_docs(skill)
    skill_text = docs["SKILL.md"]
    operations = docs["references/operation-manual.md"]
    corpus = "\n".join(docs.values())

    assert "read limit" in skill_text and "2000" in skill_text and "offset" in skill_text
    assert "`limit` 同样不超过 2000" in operations
    missing = [item for item in SUBJECT_DOC_MUST_KEEP if item not in corpus]
    assert not missing, f"{skill} 文档缺少核验纪律：{missing}"


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_skill_documents_recovery_attempt_and_fingerprint_rules(skill: str):
    failures = (_skill_dir(skill) / "references" / "failure-modes.md").read_text(encoding="utf-8")
    assert "新的恢复动作应创建新 attempt" in failures
    assert "全零/全一占位指纹" in failures
    assert "failure payload" in failures or "failure` 对象" in failures


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_skill_documents_host_call_and_dispatch_handles(skill: str):
    """run_code 外层 schema 与异步派发句柄必须明确，防止文档再次诱发误调用。"""
    text = (_skill_dir(skill) / "references" / "failure-modes.md").read_text(encoding="utf-8")
    required = ("run_code.justification", "非空完整句子", "invalid justification",
                "await Promise.allSettled(", "continuable.subagentId", "未 await 的 Promise")
    missing = [item for item in required if item not in text]
    assert not missing, f"{skill} 宿主调用契约缺少说明：{missing}"


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_repair_preview_is_documented_as_explicit_gate_auxiliary(skill: str):
    """完整性修复必须是显式命令，且 verify-report 仍是唯一闸门。"""
    root = _skill_dir(skill)
    skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
    failures = (root / "references" / "failure-modes.md").read_text(encoding="utf-8")
    assert "jiaodui repair-report" in skill_text
    assert "verify-report" in skill_text
    assert "repair-report" in failures
    assert "唯一闸门" in skill_text or "唯一闸门" in failures


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


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_skill_concrete_commands_exist_in_cli(skill: str):
    """入口及所有 references 的具体命令都应由当前 CLI 支持。"""
    root = _skill_dir(skill)
    problems = {}
    for path in sorted(root.rglob("*.md")):
        unknown = _unknown_documented_commands(path.read_text(encoding="utf-8"))
        if unknown:
            problems[str(path.relative_to(root))] = sorted(unknown)
    assert not problems, problems


def test_command_check_rejects_unknown_top_level_command():
    """不存在的顶层命令也必须被检出，包括前置全局开关。"""
    assert _unknown_documented_commands(
        "jiaodui --quiet --json invented-command <paper_dir>"
    ) == {"jiaodui invented-command"}


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_packaged_skill_is_byte_identical(skill: str):
    """skills/<skill> 与对应 packages 内副本必须字节一致（.DS_Store 除外）。"""
    source, mirror_root = SKILLS[skill]
    diffs: list[str] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.name == ".DS_Store":
            continue
        mirror = mirror_root / path.relative_to(source)
        if not mirror.is_file():
            diffs.append(f"缺副本：{mirror.relative_to(ROOT)}")
        elif mirror.read_bytes() != path.read_bytes():
            diffs.append(f"内容不一致：{path.relative_to(ROOT)}")
    assert not diffs, diffs


@pytest.mark.parametrize("skill", sorted(SKILLS))
def test_packaged_skill_has_no_extra_files(skill: str):
    """随包副本不得多出仓库源里没有的文件（防止在包内私改）。"""
    source, mirror_root = SKILLS[skill]
    source_files = {p.relative_to(source) for p in source.rglob("*")
                    if p.is_file() and p.name != ".DS_Store"}
    mirror_files = {p.relative_to(mirror_root) for p in mirror_root.rglob("*")
                    if p.is_file() and p.name != ".DS_Store"}
    assert mirror_files == source_files, sorted(mirror_files ^ source_files)


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

"""学科配置 Schema 校验与正则编译的行为契约测试。

移植自旧仓 tests/test_config_schema.py + tests/test_config_loader.py（HEAD 1c45243），
按新契约改写：

- 不再要求 agent_prompt.json（旧 LLM 提示词链路），也不读 .env；
- 入口改为 normalize_subject_config / load_subject_config，错误类型统一为
  jiaodui.errors.ContractError（消息含文件路径与字段）。
"""
import json
import re
from pathlib import Path

import pytest

from jiaodui.config import (DEFAULT_EXAM_QUESTION_PATTERN, DEFAULT_NAV_PATTERNS,
                            DEFAULT_SECTION_PATTERN, get_compiled_title_patterns,
                            get_exam_question_pattern, get_lecture_split_mode,
                            get_nav_patterns, get_section_pattern, load_subject_config,
                            normalize_subject_config, subject_config_path)
from jiaodui.errors import ContractError

EXPECTED_SECTION_PATTERN = (
    r"^#{2,3}\s"
    r"|^\*\*(例|练|变式|真题)\d+\*\*"
    r"|^\*\*教师版\*\*"
    r"|必备知识"
    r"|模型大招"
    r"|重难点突破"
)

ALL_KEYS = {
    "tools", "extensions", "split_mode", "section_pattern", "section_extensions",
    "wrapped_patterns", "unwrapped_patterns", "exam_question_pattern",
    "nav_patterns", "subject",
}


# ─── 常量与默认值 ──────────────────────────────────────────

def test_default_section_pattern_verbatim():
    """DEFAULT_SECTION_PATTERN 必须与旧仓逐字一致。"""
    assert DEFAULT_SECTION_PATTERN == EXPECTED_SECTION_PATTERN


def test_default_exam_and_nav_patterns():
    assert DEFAULT_EXAM_QUESTION_PATTERN == r"^(\d+)．"
    assert DEFAULT_NAV_PATTERNS == [r"直击课堂", r"本讲导航"]


# ─── normalize_subject_config ─────────────────────────────

def test_normalize_fills_all_keys():
    cfg = normalize_subject_config({})
    assert set(cfg) == ALL_KEYS
    assert cfg["tools"] == []
    assert cfg["extensions"] == []
    assert cfg["split_mode"] == "section"
    assert cfg["section_pattern"] == ""
    assert cfg["section_extensions"] == []
    assert cfg["wrapped_patterns"] == []
    assert cfg["unwrapped_patterns"] == []
    assert cfg["exam_question_pattern"] == DEFAULT_EXAM_QUESTION_PATTERN
    assert cfg["nav_patterns"] == DEFAULT_NAV_PATTERNS
    assert cfg["subject"] == ""


def test_normalize_reads_flat_fields():
    cfg = normalize_subject_config({
        "subject": "高中物理",
        "tools": ["calc", "read-image"],
        "extensions": [".docx", ".md"],
        "split_mode": "title",
        "section_pattern": r"^#\s",
        "section_extensions": ["板块"],
        "wrapped_patterns": [r"例\d+"],
        "unwrapped_patterns": ["^知识"],
        "exam_question_pattern": r"^\d+[.)]",
        "nav_patterns": ["封面"],
    })
    assert cfg["subject"] == "高中物理"
    assert cfg["tools"] == ["calc", "read-image"]
    assert cfg["extensions"] == [".docx", ".md"]
    assert cfg["split_mode"] == "title"
    assert cfg["section_pattern"] == r"^#\s"
    assert cfg["section_extensions"] == ["板块"]
    assert cfg["wrapped_patterns"] == [r"例\d+"]
    assert cfg["unwrapped_patterns"] == ["^知识"]
    assert cfg["exam_question_pattern"] == r"^\d+[.)]"
    assert cfg["nav_patterns"] == ["封面"]


def test_normalize_accepts_legacy_nested():
    """旧仓 lecture_split / exam_split 嵌套写法仍可迁移。"""
    cfg = normalize_subject_config({
        "lecture_split": {
            "split_mode": "title",
            "section_pattern": r"^##\s",
            "section_pattern_extensions": ["板块"],
            "wrapped_patterns": [r"例\d+"],
            "unwrapped_patterns": ["^知识"],
        },
        "exam_split": {"question_pattern": r"^\d+[.)]"},
    })
    assert cfg["split_mode"] == "title"
    assert cfg["section_pattern"] == r"^##\s"
    assert cfg["section_extensions"] == ["板块"]
    assert cfg["wrapped_patterns"] == [r"例\d+"]
    assert cfg["unwrapped_patterns"] == ["^知识"]
    assert cfg["exam_question_pattern"] == r"^\d+[.)]"


def test_normalize_top_level_wins_over_nested():
    cfg = normalize_subject_config({
        "wrapped_patterns": ["顶层"],
        "lecture_split": {"wrapped_patterns": ["嵌套"]},
    })
    assert cfg["wrapped_patterns"] == ["顶层"]


def test_normalize_does_not_mutate_input():
    raw = {"tools": ["calc"], "lecture_split": {"wrapped_patterns": ["例"]}}
    snapshot = json.dumps(raw, ensure_ascii=False, sort_keys=True)
    normalize_subject_config(raw)
    assert json.dumps(raw, ensure_ascii=False, sort_keys=True) == snapshot


@pytest.mark.parametrize("raw,field", [
    ({"tools": "calc"}, "tools"),
    ({"tools": [1]}, "tools"),
    ({"extensions": "docx"}, "extensions"),
    ({"split_mode": 1}, "split_mode"),
    ({"section_pattern": 1}, "section_pattern"),
    ({"section_extensions": "板块"}, "section_extensions"),
    ({"wrapped_patterns": "例"}, "wrapped_patterns"),
    ({"unwrapped_patterns": [1]}, "unwrapped_patterns"),
    ({"exam_question_pattern": 1}, "exam_question_pattern"),
    ({"nav_patterns": "封面"}, "nav_patterns"),
    ({"subject": 1}, "subject"),
])
def test_normalize_type_errors_mention_field(raw, field):
    with pytest.raises(ContractError) as exc:
        normalize_subject_config(raw)
    assert field in str(exc.value)


def test_normalize_rejects_non_dict():
    with pytest.raises(ContractError):
        normalize_subject_config(["not", "a", "dict"])


# ─── load_subject_config ──────────────────────────────────

def _write_json(path: Path, data) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_subject_config_path():
    assert subject_config_path("高中物理") == Path("config") / "subjects" / "高中物理.json"
    assert subject_config_path("高中物理.json") == Path("config") / "subjects" / "高中物理.json"
    assert subject_config_path("x", "base") == Path("base") / "x.json"


def test_load_subject_config_ok(tmp_path):
    p = _write_json(tmp_path / "高中物理.json", {
        "subject": "高中物理",
        "tools": ["calc"],
        "exam_question_pattern": r"^\d+[.)]",
    })
    cfg = load_subject_config(p)
    assert cfg["subject"] == "高中物理"
    assert cfg["tools"] == ["calc"]
    assert cfg["exam_question_pattern"] == r"^\d+[.)]"
    assert set(cfg) == ALL_KEYS


def test_load_subject_config_str_path(tmp_path):
    p = _write_json(tmp_path / "s.json", {"subject": "语文"})
    assert load_subject_config(str(p))["subject"] == "语文"


def test_load_subject_config_missing_mentions_path(tmp_path):
    p = tmp_path / "不存在.json"
    with pytest.raises(ContractError) as exc:
        load_subject_config(p)
    assert str(p) in str(exc.value)
    assert "不存在" in str(exc.value)


def test_load_subject_config_type_error_mentions_path_and_field(tmp_path):
    p = _write_json(tmp_path / "bad.json", {"tools": "not-a-list"})
    with pytest.raises(ContractError) as exc:
        load_subject_config(p)
    msg = str(exc.value)
    assert str(p) in msg
    assert "tools" in msg


def test_load_subject_config_bad_json_mentions_path(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ContractError) as exc:
        load_subject_config(p)
    assert str(p) in str(exc.value)


def test_load_subject_config_directory_reads_config_json(tmp_path):
    _write_json(tmp_path / "config.json", {"subject": "目录式"})
    assert load_subject_config(tmp_path)["subject"] == "目录式"


# ─── 正则编译 getter ─────────────────────────────────────

def test_section_pattern_default_plus_extensions():
    cfg = normalize_subject_config({"section_extensions": ["板块", "重难点突破"]})
    pat = get_section_pattern(cfg)
    assert pat.pattern.startswith(DEFAULT_SECTION_PATTERN)
    assert re.escape("板块") in pat.pattern


def test_section_pattern_explicit_used():
    cfg = normalize_subject_config({"section_pattern": r"^@@", "section_extensions": ["板块"]})
    assert get_section_pattern(cfg).pattern == r"^@@"  # 显式配置优先，不带扩展


def test_section_pattern_legacy_sentinel_ignored():
    cfg = normalize_subject_config({"section_pattern": r"^##\s", "section_extensions": ["板块"]})
    pat = get_section_pattern(cfg)
    assert pat.pattern != r"^##\s"
    assert "板块" in pat.pattern


def test_section_pattern_invalid_falls_back():
    cfg = normalize_subject_config({"section_pattern": "("})
    assert get_section_pattern(cfg).pattern == DEFAULT_SECTION_PATTERN


def test_section_pattern_none_config_defaults():
    assert get_section_pattern(None).pattern == DEFAULT_SECTION_PATTERN


def test_exam_question_pattern_default_and_custom():
    assert get_exam_question_pattern(normalize_subject_config({})).pattern == DEFAULT_EXAM_QUESTION_PATTERN
    cfg = normalize_subject_config({"exam_question_pattern": r"^\d+[.)]"})
    assert get_exam_question_pattern(cfg).pattern == r"^\d+[.)]"


def test_exam_question_pattern_invalid_falls_back():
    cfg = normalize_subject_config({"exam_question_pattern": "("})
    assert get_exam_question_pattern(cfg).pattern == DEFAULT_EXAM_QUESTION_PATTERN


def test_lecture_split_mode():
    assert get_lecture_split_mode({}) == "section"
    assert get_lecture_split_mode(None) == "section"
    assert get_lecture_split_mode(normalize_subject_config({"split_mode": "title"})) == "title"


def test_compiled_title_patterns():
    cfg = normalize_subject_config({
        "wrapped_patterns": [r"例\d+"],
        "unwrapped_patterns": ["^知识"],
    })
    pats = get_compiled_title_patterns(cfg)
    assert len(pats) == 2
    assert pats[0].match("**例1** （2026·山东）") is not None
    assert pats[1].match("知识讲解") is not None


def test_compiled_title_patterns_skip_invalid():
    cfg = normalize_subject_config({
        "wrapped_patterns": ["("],
        "unwrapped_patterns": ["^知识"],
    })
    pats = get_compiled_title_patterns(cfg)
    assert len(pats) == 1
    assert pats[0].match("知识讲解") is not None


def test_nav_patterns_default_and_custom():
    assert get_nav_patterns({}) == DEFAULT_NAV_PATTERNS
    assert get_nav_patterns(None) == DEFAULT_NAV_PATTERNS
    cfg = normalize_subject_config({"nav_patterns": ["封面"]})
    assert get_nav_patterns(cfg) == ["封面"]

"""发行包必须自带学科配置，且与仓库 config 保持一致（防双源漂移）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import jiaodui

REPO = Path(__file__).resolve().parent.parent
_PKG_SUBJECTS = Path(jiaodui.__file__).parent / "data" / "subjects"
_REPO_SUBJECTS = REPO / "config" / "subjects"

# 已落地学科：每新增一门学科，包内配置与人工可读镜像都必须同时存在并逐字一致。
LANDED_SUBJECTS = ("高中物理", "高中化学")


@pytest.mark.parametrize("subject", LANDED_SUBJECTS)
def test_package_subject_config_exists(subject: str):
    assert (_PKG_SUBJECTS / f"{subject}.json").is_file(), "学科配置必须随包分发（_resolve_config_dir 的兜底）"


@pytest.mark.parametrize("subject", LANDED_SUBJECTS)
def test_package_config_matches_repo_config(subject: str):
    assert (_PKG_SUBJECTS / f"{subject}.json").read_bytes() == (
        _REPO_SUBJECTS / f"{subject}.json"
    ).read_bytes(), f"{subject} 包内配置与仓库 config 漂移"


@pytest.mark.parametrize("subject", LANDED_SUBJECTS)
def test_resolve_config_dir_finds_subject(subject: str):
    from jiaodui.cli import _resolve_config_dir

    assert (_resolve_config_dir() / "subjects" / f"{subject}.json").is_file()


def test_landed_subject_configs_share_split_rules():
    """两科配置只允许 subject / quantities 不同，拆分口径必须逐字一致（防复制时改错）。"""
    configs = {
        subject: json.loads((_PKG_SUBJECTS / f"{subject}.json").read_text(encoding="utf-8"))
        for subject in LANDED_SUBJECTS
    }
    physics, chemistry = configs["高中物理"], configs["高中化学"]
    for field in ("tools", "extensions", "split_mode", "section_pattern",
                  "section_extensions", "wrapped_patterns", "unwrapped_patterns",
                  "exam_question_pattern", "nav_patterns"):
        assert physics[field] == chemistry[field], f"学科配置字段 {field} 与高中物理不一致"
    assert chemistry["subject"] == "高中化学"
    # 化学 v1 不建量表：quantities 留空，学科文档明确化学不做量纲交叉校验。
    assert chemistry["quantities"] == {}


def test_chemistry_subject_config_passes_schema_validation():
    from jiaodui.config import load_subject_config

    config = load_subject_config(_PKG_SUBJECTS / "高中化学.json")
    assert config["subject"] == "高中化学"
    assert "calc" in config["tools"]

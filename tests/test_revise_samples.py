"""冻结候选语料的完整性、只读检查和独立标注接缝。"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "revise_ab"
SCRIPT = ROOT / "scripts" / "freeze_revise_samples.py"
SAMPLE_IDS = [f"physics/S{i}" for i in range(1, 10)] + [f"chemistry/C{i}" for i in range(1, 4)]
# 冻结后填入一次，修改语料须独立重新审阅；检查命令不更新此值。
MANIFEST_SHA256 = "cd000e065a958795e6deb468607cad1c46b10114157d7b56ebcdeeb1c5b2abd8"


def run_freezer(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), *args],
                          capture_output=True, text=True)


def test_frozen_sample_inventory_and_manifest_are_pinned():
    assert sorted(str(p.parent.relative_to(FIXTURES)) for p in FIXTURES.rglob("expected.json")) == sorted(SAMPLE_IDS)
    assert hashlib.sha256((FIXTURES / "manifest.json").read_bytes()).hexdigest() == MANIFEST_SHA256
    result = run_freezer(FIXTURES, "--check")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("sample_id", SAMPLE_IDS)
def test_annotation_spans_are_literal_source_and_review_is_honest(sample_id: str):
    folder = FIXTURES / sample_id
    expected = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
    source = (folder / "source.md").read_text(encoding="utf-8")
    assert expected["sample_id"] == sample_id
    assert expected["synthetic"] is True
    assert expected["annotation_author"] == "agent"
    assert expected["human_review"] == "pending"
    ids = [c["id"] for c in expected["final_corrections"]]
    assert len(ids) == len(set(ids))
    for correction in expected["final_corrections"]:
        span = correction["span"]
        line = source.splitlines()[span["line"] - 1]
        assert 1 <= span["start_column"] < span["end_column"] <= len(line) + 1
        assert line[span["start_column"] - 1:span["end_column"] - 1] == correction["old_text"]
        assert correction["old_text"] != correction["new_text"]
        assert correction["reason"]


@pytest.mark.parametrize("sample_id", SAMPLE_IDS)
def test_all_candidate_corrections_resolve_to_independently_annotated_spans(sample_id: str):
    """只验证确定性定位接缝，不把候选标注或干预规程冒充人工/宿主验收。"""
    from jiaodui.anchor import resolve_anchor, validate_revision_input

    folder = FIXTURES / sample_id
    expected = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
    raw = (folder / "source.md").read_bytes()
    source = raw.decode("utf-8")
    lines = source.splitlines(keepends=True)
    for correction in expected["final_corrections"]:
        span = correction["span"]
        # 预期区间来自冻结标注，不调用被测定位函数反算。
        line_start = sum(len(line) for line in lines[:span["line"] - 1])
        start = line_start + span["start_column"] - 1
        end = line_start + span["end_column"] - 1
        match = resolve_anchor(source, correction["old_text"],
                               occurrence=correction.get("match_index"))
        assert (match.start, match.end) == (start, end)
        assert (match.line, match.column) == (span["line"], span["start_column"])
        assert match.original == correction["old_text"]
        assert match.normalized_match is False
        validate_revision_input(correction["old_text"], correction["new_text"], correction["reason"])
    assert (folder / "source.md").read_bytes() == raw


def test_no_issue_and_intervention_final_sets_are_explicitly_pinned():
    no_issue = json.loads((FIXTURES / "physics/S1/expected.json").read_text(encoding="utf-8"))
    assert no_issue["final_corrections"] == []
    for sample_id, expected_ids in {
        "physics/S6": [], "physics/S7": ["p7a", "p7b"],
        "physics/S8": ["p8a", "p8b", "p8c"], "physics/S9": ["p9a", "p9b"],
        "chemistry/C3": ["c3"],
    }.items():
        expected = json.loads((FIXTURES / sample_id / "expected.json").read_text(encoding="utf-8"))
        assert [item["id"] for item in expected["final_corrections"]] == expected_ids
        assert expected["interventions"]


def test_formula_and_bold_probes_require_complete_delimiters():
    from jiaodui.anchor import AnchorError, resolve_anchor

    expected = json.loads((FIXTURES / "physics/S4/expected.json").read_text(encoding="utf-8"))
    source = (FIXTURES / "physics/S4/source.md").read_text(encoding="utf-8")
    probes = {item["old_text"]: item["required_original"] for item in expected["structure_probes"]}
    assert probes == {"mv^2": "$E_k=mv^2$", "动能为18 J": "**动能为18 J**"}
    for partial, complete in probes.items():
        with pytest.raises(AnchorError) as error:
            resolve_anchor(source, partial)
        assert error.value.code == "anchor.structure-cut"
        assert error.value.details["required_original"] == complete


def test_duplicate_phrase_uses_third_match_and_keeps_other_two():
    folder = FIXTURES / "physics" / "S3"
    source = (folder / "source.md").read_text(encoding="utf-8")
    correction = json.loads((folder / "expected.json").read_text(encoding="utf-8"))["final_corrections"][0]
    from jiaodui.source_index import query_locations
    matches = query_locations(source, hashlib.sha256(source.encode("utf-8")).hexdigest(), correction["old_text"])
    assert len(matches) == 3
    assert correction["match_index"] == 3
    assert matches[2]["line"] == 4
    assert matches[0]["line"] == 2 and matches[1]["line"] == 3
    assert source.count(correction["old_text"]) == 3


@pytest.mark.parametrize("payload", ["physics/S2/source.md", "physics/S2/expected.json", "physics/S5/images/a.png"])
def test_freeze_check_rejects_tampering_without_rewriting(tmp_path: Path, payload: str):
    copied = tmp_path / "samples"
    shutil.copytree(FIXTURES, copied)
    target = copied / payload
    target.write_bytes(target.read_bytes() + b"tampered")
    before = (copied / "manifest.json").read_bytes()
    result = run_freezer(copied, "--check")
    assert result.returncode != 0
    assert payload in result.stderr
    assert (copied / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_freeze_check_rejects_changed_file_set(tmp_path: Path, change: str):
    copied = tmp_path / "samples"
    shutil.copytree(FIXTURES, copied)
    if change == "missing":
        (copied / "physics/S1/source.md").unlink()
    else:
        (copied / "extra.md").write_text("新增未冻结文件", encoding="utf-8")
    assert run_freezer(copied, "--check").returncode != 0


def test_freeze_never_overwrites_existing_manifest(tmp_path: Path):
    copied = tmp_path / "samples"
    shutil.copytree(FIXTURES, copied)
    before = (copied / "manifest.json").read_bytes()
    result = run_freezer(copied, "--freeze")
    assert result.returncode != 0
    assert (copied / "manifest.json").read_bytes() == before


def test_initial_freeze_hashes_handwritten_expectations_without_generating_them(tmp_path: Path):
    copied = tmp_path / "samples"
    shutil.copytree(FIXTURES, copied, ignore=shutil.ignore_patterns("manifest.json"))
    expected = copied / "physics/S2/expected.json"
    before = expected.read_bytes()
    result = run_freezer(copied, "--freeze")
    assert result.returncode == 0, result.stderr
    assert expected.read_bytes() == before
    assert run_freezer(copied, "--check").returncode == 0

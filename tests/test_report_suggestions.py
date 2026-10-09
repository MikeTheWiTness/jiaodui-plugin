from __future__ import annotations

import hashlib

import pytest

from jiaodui.report_suggestions import render_suggestions
from jiaodui.report_parse import split_sections
from jiaodui.markers import split_marked_body
from jiaodui.verify import verify_report_text


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def proposal(source: str, *, phrase: str = "木板", start: int | None = None) -> dict:
    from jiaodui.source_index import query_locations

    locations = query_locations(source, digest(source), phrase)
    chosen = next((item for item in locations if item["start"] == start), locations[-1])
    return {
        "schema_version": 2,
        "task_id": "a" * 32,
        "unit_id": "b" * 32,
        "run_id": "run-1",
        "source_sha256": digest(source),
        "body_sha256": digest(source),
        "proposal_revision": 1,
        "summary": "一般问题",
        "corrections": [{
            "id": "c1",
            "location_id": chosen["location_id"],
            "expected_original": chosen["original"],
            "replacement": "木块",
            "reason": "对象与题干定义不一致。",
            "category": "term",
            "severity": "一般问题",
            "evidence_ids": ["e1"],
        }],
        "evidence": {"assumptions": [{"id": "e1", "text": "对象为物块。", "source_locations": []}]},
    }


def test_generator_replaces_only_selected_duplicate_and_restores_exact_source():
    source = "木板甲。木板乙。木板丙。"
    second_start = source.index("木板", source.index("木板") + 1)
    candidate = render_suggestions(source, proposal(source, start=second_start),
                                   expected_task_id="a" * 32,
                                   expected_unit_id="b" * 32,
                                   expected_run_id="run-1")
    _, marked, _ = split_sections(candidate.text)
    assert marked == "木板甲。" + "【1|木板|木块】" + "乙。木板丙。"
    assert split_marked_body(marked) == source
    assert verify_report_text(candidate.text, source).ok


def test_versioned_body_boundary_preserves_headings_and_preamble_like_source_lines():
    source = "第一段。\n### 修改原因\n编号：这是源文。\n内容：也是源文。\n⚠️保留。"
    payload = proposal("木板。")
    payload["source_sha256"] = payload["body_sha256"] = digest(source)
    payload["corrections"] = []
    payload["summary"] = "无问题"
    payload["evidence"] = {}
    candidate = render_suggestions(source, payload, expected_task_id="a" * 32,
                                   expected_unit_id="b" * 32, expected_run_id="run-1")
    _, marked, reasons = split_sections(candidate.text)
    assert marked == source
    assert "### 修改原因" in marked
    assert reasons.strip() == "无"
    assert verify_report_text(candidate.text, source).ok


def test_schema_v2_report_is_rejected_by_legacy_repair():
    from jiaodui.report_repair import build_repair_candidate

    source = "木板。"
    candidate = render_suggestions(source, proposal(source), expected_task_id="a" * 32,
                                   expected_unit_id="b" * 32, expected_run_id="run-1")
    result = build_repair_candidate(source, candidate.text)
    assert not result.ok
    assert result.diagnostics[0]["code"] == "repair.v2-not-supported"


def test_generator_rejects_stale_locations_duplicate_ids_overlap_and_unencodable_markers():
    source = "木板甲。木板乙。"
    payload = proposal(source)
    payload["source_sha256"] = "0" * 64
    with pytest.raises(ValueError) as stale:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert stale.value.code == "proposal.source-mismatch"

    invalid_severity = proposal(source)
    invalid_severity["corrections"][0]["severity"] = []
    with pytest.raises(ValueError) as malformed:
        render_suggestions(source, invalid_severity, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert malformed.value.code == "proposal.severity"

    pipe_source = "甲|乙。"
    pipe = proposal("木板。")
    pipe["source_sha256"] = pipe["body_sha256"] = digest(pipe_source)
    pipe["corrections"][0]["expected_original"] = "甲|乙"
    pipe["corrections"][0]["location_id"] = __import__("jiaodui.source_index", fromlist=["query_locations"]).query_locations(
        pipe_source, digest(pipe_source), "甲|乙")[0]["location_id"]
    with pytest.raises(ValueError) as invalid:
        render_suggestions(pipe_source, pipe, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert invalid.value.code == "proposal.marker-unrepresentable"

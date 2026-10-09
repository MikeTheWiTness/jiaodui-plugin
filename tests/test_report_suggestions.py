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
        "evidence": {
            "assumptions": [{"id": "e1", "text": "对象为物块。", "source_locations": []}],
            "symbols": [],
            "images": {"status": "not_applicable", "reason": "合成测试无图片"},
            "calculations": {"status": "not_applicable", "reason": "无数值或公式核验"},
        },
        "self_check": {"status": "passed", "checks": ["real_issue", "replacement_semantics",
                         "related_coverage", "scope_and_uncertainty", "severity"], "unresolved": []},
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
    payload["evidence"] = {
        "assumptions": [{"id": "e1", "text": "已核对本单元内容。", "source_locations": []}],
        "symbols": [],
        "images": {"status": "not_applicable", "reason": "无配图"},
        "calculations": {"status": "not_applicable", "reason": "无数值或公式"},
    }
    payload["self_check"] = {"status": "passed", "checks": ["no_issue_review"], "unresolved": []}
    candidate = render_suggestions(source, payload, expected_task_id="a" * 32,
                                   expected_unit_id="b" * 32, expected_run_id="run-1")
    _, marked, reasons = split_sections(candidate.text)
    assert marked == source
    assert "### 修改原因" in marked
    assert reasons.startswith("无\n")
    assert "核验说明：" in reasons
    assert verify_report_text(candidate.text, source).ok


def test_word_consumers_keep_markers_after_source_reason_heading():
    from jiaodui.docx_report import _report_marker_counts, _report_sections
    source = "开头。\n### 修改原因\n编号：末尾木板。"
    candidate = render_suggestions(source, proposal(source), expected_task_id="a" * 32,
                                   expected_unit_id="b" * 32, expected_run_id="run-1")
    assert _report_marker_counts([("单元1", candidate.text)]) == {"单元1": 1}
    body, _ = _report_sections(candidate.text)
    assert "编号：末尾【1|木板|木块】。" in body
    assert split_marked_body(body) == source


def test_self_check_and_first_pass_evidence_are_required():
    source = "木板。"
    payload = proposal(source)
    payload.pop("self_check")
    with pytest.raises(ValueError) as error:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert error.value.code == "proposal.self-check"
    payload = proposal(source)
    payload["evidence"]["assumptions"] = []
    with pytest.raises(ValueError) as error:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert error.value.code == "proposal.evidence-assumptions"


def test_fabricated_calc_call_is_rejected():
    source = "木板。"
    payload = proposal(source)
    payload["evidence"]["calculations"] = [{"id": "e2", "call_id": "fake", "expression": "1+2", "result": 3}]
    with pytest.raises(ValueError) as error:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert error.value.code == "proposal.calc-call-mismatch"


def test_schema_v2_report_is_rejected_by_legacy_repair():
    from jiaodui.report_repair import build_repair_candidate

    source = "木板。"
    candidate = render_suggestions(source, proposal(source), expected_task_id="a" * 32,
                                   expected_unit_id="b" * 32, expected_run_id="run-1")
    result = build_repair_candidate(source, candidate.text)
    assert not result.ok
    assert result.diagnostics[0]["code"] == "repair.v2-not-supported"


def test_generator_rejects_stale_locations_and_bad_severity_but_encodes_pipes():
    """旧位置与非法严重度仍拒绝；含竖线的原文按 ADR 0006 转义后必须无损通过。"""
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

    # ADR 0006：竖线不再是拒绝理由，而是转义后可无损承载的正文
    pipe_source = "甲|乙。"
    from jiaodui.source_index import query_locations

    pipe = proposal("木板。")
    pipe["source_sha256"] = pipe["body_sha256"] = digest(pipe_source)
    pipe["corrections"][0]["expected_original"] = "甲|乙"
    pipe["corrections"][0]["replacement"] = "甲或乙"
    pipe["corrections"][0]["location_id"] = query_locations(
        pipe_source, digest(pipe_source), "甲|乙")[0]["location_id"]
    candidate = render_suggestions(pipe_source, pipe, expected_task_id="a" * 32,
                                   expected_unit_id="b" * 32, expected_run_id="run-1")
    _, marked, _ = split_sections(candidate.text)
    assert marked == r"【1|甲\|乙|甲或乙】。"
    assert split_marked_body(marked, escaped=True) == pipe_source
    assert verify_report_text(candidate.text, pipe_source).ok


# ---- ADR 0006：含标记特殊字符的原文必须无损恢复（执行计划 §11.1） ----

_SEVERITY_ORDER = ["轻微问题", "一般问题", "严重错误"]


def _scaffold(source: str, corrections: list[dict], *, summary: str | None = None) -> dict:
    """构造 schema v2 建议骨架，summary 缺省按最高严重度推导。"""
    if summary is None:
        summary = ("无问题" if not corrections
                   else max((item["severity"] for item in corrections), key=_SEVERITY_ORDER.index))
    return {
        "schema_version": 2,
        "task_id": "a" * 32,
        "unit_id": "b" * 32,
        "run_id": "run-1",
        "source_sha256": digest(source),
        "body_sha256": digest(source),
        "proposal_revision": 1,
        "summary": summary,
        "corrections": corrections,
        "evidence": {
            "assumptions": [{"id": "e1", "text": "按源文逐字核对。", "source_locations": []}],
            "symbols": [],
            "images": {"status": "not_applicable", "reason": "合成测试无图片"},
            "calculations": {"status": "not_applicable", "reason": "无数值或公式核验"},
        },
        "self_check": {
            "status": "passed",
            "checks": ["no_issue_review"] if not corrections else
                      ["real_issue", "replacement_semantics", "related_coverage",
                       "scope_and_uncertainty", "severity"],
            "unresolved": [],
        },
    }


def _correction(source: str, phrase: str, replacement: str, *, cid: str = "c1", **overrides) -> dict:
    from jiaodui.source_index import query_locations

    chosen = query_locations(source, digest(source), phrase)[-1]
    return {
        "id": cid,
        "location_id": chosen["location_id"],
        "expected_original": chosen["original"],
        "replacement": replacement,
        "reason": "与源文其余写法不一致。",
        "category": "term",
        "severity": "一般问题",
        "evidence_ids": ["e1"],
        **overrides,
    }


def _render(source: str, payload: dict):
    return render_suggestions(source, payload, expected_task_id="a" * 32,
                              expected_unit_id="b" * 32, expected_run_id="run-1")


@pytest.mark.parametrize("source,phrase,replacement", [
    ("甲|乙。", "甲|乙", "甲或乙"),
    ("记为【注】。", "【注】", "（注）"),
    ("反斜杠\\与竖线|。", "反斜杠\\与竖线|", "反斜杠与竖线"),
    ("含【左】与【右】两处。", "含【左】", "含（左）"),
    ("左【中|右】尾。", "左【中|右】尾", "左中右尾"),
    (r"$\dfrac{1}{2}$与$\dfrac{3}{4}$。", r"$\dfrac{1}{2}$", r"$\dfrac{L}{2}$"),
])
def test_special_characters_round_trip_losslessly(source, phrase, replacement):
    """原文含竖线/标记括号/反斜杠时，标记正文必须能逐字恢复为源文。"""
    candidate = _render(source, _scaffold(source, [_correction(source, phrase, replacement)]))
    _, marked, _ = split_sections(candidate.text)
    assert split_marked_body(marked, escaped=True) == source
    assert verify_report_text(candidate.text, source).ok


@pytest.mark.parametrize("source,phrase,replacement", [
    ("emoji🙂与组合字符e\u0301。", "emoji🙂", "表情🙂"),
    ("零宽\u200b字符在中间。", "零宽\u200b字符", "零宽字符"),
    ("第一行|竖线。\r\n第二行【括号】。", "第一行|竖线。", "第一行或竖线。"),
    ("跨行公式$\\dfrac{a}{b}$之后|竖线。", "$\\dfrac{a}{b}$", "$\\dfrac{c}{d}$"),
])
def test_unicode_and_crlf_bodies_round_trip_losslessly(source, phrase, replacement):
    candidate = _render(source, _scaffold(source, [_correction(source, phrase, replacement)]))
    _, marked, _ = split_sections(candidate.text)
    assert split_marked_body(marked, escaped=True) == source
    assert verify_report_text(candidate.text, source).ok


def test_empty_body_is_rejected_with_explicit_code():
    """空白正文不得静默产出空报告，必须显式拒绝（ADR 0006 §8）。"""
    for source in ("", "   ", "\n\n \t\n"):
        with pytest.raises(ValueError) as error:
            _render(source, _scaffold(source, []))
        assert error.value.code == "proposal.empty-body"


def test_short_body_is_body_not_envelope():
    """回放 4讲 单元1 的 21 字符源文是短正文，不是信封，必须正常出报告。"""
    source = "第 4 讲\n\n【选修专项】简谐运动与机械波"
    assert len(source) == 21
    payload = _scaffold(source, [_correction(source, "【选修专项】", "〔选修专项〕")])
    candidate = _render(source, payload)
    _, marked, _ = split_sections(candidate.text)
    assert split_marked_body(marked, escaped=True) == source
    assert verify_report_text(candidate.text, source).ok

    # 无修改建议同样放行（短正文不等于无正文）
    quiet = _render(source, _scaffold(source, []))
    assert verify_report_text(quiet.text, source).ok


def test_source_and_body_digests_are_validated_separately():
    """source_sha256 绑定文件字节、body_sha256 绑定正文，两者分别校验（ADR 0006 §7）。"""
    source = "木板甲。"
    payload = _scaffold(source, [])
    with pytest.raises(ValueError) as file_digest:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1",
                           expected_source_sha256="0" * 64)
    assert file_digest.value.code == "proposal.source-mismatch"
    assert "source_sha256" in str(file_digest.value)

    broken_body = _scaffold(source, [])
    broken_body["body_sha256"] = "0" * 64
    with pytest.raises(ValueError) as body_digest:
        _render(source, broken_body)
    assert body_digest.value.code == "proposal.source-mismatch"
    assert "body_sha256" in str(body_digest.value)


def test_reverse_cases_still_rejected_after_lossless_encoding():
    """转义只扩大可表达字符集，不放松任何拒绝（ADR 0006 §5）。"""
    source = "木板甲。"
    # 位置与预期原文不一致 → 拒绝
    wrong_location = _scaffold(source, [_correction(source, "木板", "木块")])
    wrong_location["corrections"][0]["expected_original"] = "板甲"
    with pytest.raises(ValueError) as mismatch:
        _render(source, wrong_location)
    assert mismatch.value.code == "location.original-mismatch"

    # 空原文字段 → 拒绝
    empty_original = _scaffold(source, [_correction(source, "木板", "木块",
                                                    expected_original="")])
    with pytest.raises(ValueError) as empty:
        _render(source, empty_original)
    assert empty.value.code == "proposal.no-op"

    # 空操作（原文 == 改为）→ 拒绝
    noop = _scaffold(source, [_correction(source, "木板", "木板")])
    with pytest.raises(ValueError) as no_op:
        _render(source, noop)
    assert no_op.value.code == "proposal.no-op"

    # 区间重叠 → 拒绝
    overlap_source = "木板甲。"
    overlap = _scaffold(overlap_source, [
        _correction(overlap_source, "木板", "木块", cid="c1"),
        _correction(overlap_source, "板甲", "板块", cid="c2"),
    ])
    with pytest.raises(ValueError) as overlapped:
        _render(overlap_source, overlap)
    assert overlapped.value.code == "proposal.overlap"


def test_v2_report_does_not_strip_preamble_like_source_lines():
    """源文里长得像 v1 装饰的行属于正文，v2 不得剥离（ADR 0006 §6）。"""
    source = ("## 前置参考（这是源文里真有的小标题）\n内容一\n---\n"
              "编号：正文里的行\n内容：\n⚠️ 尾部。")
    candidate = _render(source, _scaffold(source, []))
    _, marked, _ = split_sections(candidate.text)
    assert marked == source
    assert split_marked_body(marked, escaped=True) == source
    assert verify_report_text(candidate.text, source).ok

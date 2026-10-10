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


def test_schema_error_names_missing_and_unknown_keys():
    """`proposal.schema` 必须点名缺哪个、多哪个键。

    回放实测（第 11 讲 单元1）：同一处缺键在只报「字段缺失或包含未支持字段」时
    连撞 5 次提交，196 步后放弃并由父代理重派。
    """
    source = "木板。"
    payload = proposal(source)
    payload.pop("run_id")
    payload["unexpected_key"] = 1
    with pytest.raises(ValueError) as error:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert error.value.code == "proposal.schema"
    message = str(error.value)
    assert "run_id" in message and "缺少必需字段" in message
    assert "unexpected_key" in message and "未支持字段" in message


def test_self_check_incomplete_lists_missing_required_checks():
    """必需检查项是固定字面量，报错必须列出缺哪几个、合法值是什么。"""
    source = "木板。"
    payload = proposal(source)
    payload["self_check"] = {"status": "passed", "checks": ["real_issue"], "unresolved": []}
    with pytest.raises(ValueError) as error:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert error.value.code == "proposal.self-check-incomplete"
    message = str(error.value)
    assert "replacement_semantics" in message, "缺项必须点名"
    assert "related_coverage" in message
    assert "scope_and_uncertainty" in message
    assert "severity" in message, "必须同时给出合法字面量清单"


def test_evidence_assumptions_error_names_index_and_missing_field():
    """逐项点名：只有「需含id、text和source_locations」时调用方无法定位是第几项。"""
    source = "木板。"
    payload = proposal(source)
    payload["evidence"]["assumptions"] = [
        {"id": "e0", "text": "先前假设。", "source_locations": []},
        {"id": "e1", "text": "对象为物块。"},
    ]
    with pytest.raises(ValueError) as error:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert error.value.code == "proposal.evidence-assumptions"
    message = str(error.value)
    assert "assumptions[1]" in message
    assert "source_locations" in message


def test_evidence_symbols_error_reports_actual_shape():
    """symbols 只接受数组；报错要给出实际收到的形态。"""
    source = "木板。"
    payload = proposal(source)
    payload["evidence"]["symbols"] = None
    with pytest.raises(ValueError) as error:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert error.value.code == "proposal.evidence-symbols"
    assert "NoneType" in str(error.value)


def test_evidence_calculation_error_names_index_and_missing_fields():
    """计算证据缺字段必须报出下标与字段名，而不是重写整份 evidence。"""
    source = "木板。"
    payload = proposal(source)
    payload["evidence"]["calculations"] = [{"id": "e2", "call_id": "fake"}]
    with pytest.raises(ValueError) as error:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1")
    assert error.value.code == "proposal.evidence-calculation"
    message = str(error.value)
    assert "calculations[0]" in message
    assert "expression" in message and "result" in message


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


# ---- P6：两个回放失败单元的根因回归（诊断必须指到具体条件） ----

def _calc_call(source: str, **overrides) -> dict:
    """一条与 material.record_calc_call 同形的记账记录（供校验器直接消费）。"""
    call = {
        "call_id": "call-1", "task_id": "a" * 32, "unit_id": "b" * 32, "run_id": "run-1",
        "source_sha256": digest(source), "operation": "evaluate",
        "params": {"expression": "1+2"}, "success": True,
        "result": {"success": True, "result": 3.0, "error": None},
    }
    call.update(overrides)
    return call


def _payload_with_calc(source: str, **calc_overrides) -> tuple[dict, list[dict]]:
    payload = _scaffold(source, [_correction(source, "木板", "木块")])
    item = {"id": "k1", "call_id": "call-1", "expression": "1+2", "result": 3.0}
    item.update(calc_overrides)
    payload["evidence"]["calculations"] = [item]
    payload["corrections"][0]["evidence_ids"] = ["e1", "k1"]
    return payload, [_calc_call(source, **({} if calc_overrides.get("_call") is None else {}))]


def test_calc_evidence_mismatch_names_the_failing_condition():
    """4讲单元10 的根因：绑定失败必须说清是哪一条不满足，而不是一句「未绑定」。"""
    source = "木板。"
    cases = [
        ({"expression": "1 + 2"}, None, "expression"),                 # 空白差异
        ({"result": True}, None, "result"),                            # dimensional 返回对象却写了布尔
        ({}, {"success": False}, "成功"),                               # 未成功的调用不能当证据
        ({}, {"run_id": "run-2"}, "轮次"),                              # 绑定的是另一轮
        ({}, {"source_sha256": "0" * 64}, "源文"),                      # 绑定的是另一份源文
        ({"call_id": "missing"}, None, "call_id"),                      # 不存在的调用
        ({"result": {"consistent": True}}, None, "result"),             # 只抄了对象的一部分
    ]
    for item_overrides, call_overrides, expected in cases:
        payload, _ = _payload_with_calc(source, **item_overrides)
        calls = [_calc_call(source, **(call_overrides or {}))]
        with pytest.raises(ValueError) as error:
            render_suggestions(source, payload, expected_task_id="a" * 32,
                               expected_unit_id="b" * 32, expected_run_id="run-1",
                               calc_calls=calls)
        assert error.value.code == "proposal.calc-call-mismatch"
        assert expected in str(error.value), (item_overrides, call_overrides, str(error.value))


def test_calc_evidence_accepts_verbatim_copy_of_recorded_call():
    """反向契约：逐字抄回记录（含 dimensional 的对象结果）必须通过。"""
    source = "木板。"
    recorded_result = {"consistent": True, "ambiguous": False, "left_dimensions": "T"}
    payload, _ = _payload_with_calc(source, result=recorded_result)
    calls = [_calc_call(source, operation="dimensional",
                        params={"expression": "T = lam/v"}, success=True,
                        result={"success": True, "result": recorded_result, "error": None})]
    payload["evidence"]["calculations"][0]["expression"] = "T = lam/v"
    candidate = render_suggestions(source, payload, expected_task_id="a" * 32,
                                   expected_unit_id="b" * 32, expected_run_id="run-1",
                                   calc_calls=calls)
    assert candidate.summary == "一般问题"


def test_calc_evidence_mismatch_lists_copyable_candidates_for_multi_argument_calls():
    """回放根因：equality 没有唯一 expression 字段，子 agent 用 '==' 拼两条参数后只会
    得到「不逐字一致」。报错必须列出每个可照抄的字段取值，并点明拼接写法错在哪。"""
    source = "木板。"
    payload, _ = _payload_with_calc(source, expression="2*2 == 2*4 + (-2)*2", result=True)
    calls = [_calc_call(source, operation="equality",
                        params={"expression_a": "2*2", "expression_b": "2*4 + (-2)*2",
                                "subject": "高中物理", "task_id": "a" * 32},
                        result={"success": True, "result": True, "error": None})]
    with pytest.raises(ValueError) as error:
        render_suggestions(source, payload, expected_task_id="a" * 32,
                           expected_unit_id="b" * 32, expected_run_id="run-1",
                           calc_calls=calls)
    assert error.value.code == "proposal.calc-call-mismatch"
    message = str(error.value)
    assert "expression_a='2*2'" in message and "expression_b='2*4 + (-2)*2'" in message
    assert "拼成了一条" in message and "'2*2'" in message
    assert "subject" not in message and "task_id" not in message, "身份/元数据字段不能当候选，避免诱导抄错字段"
    # 逐字抄回其中一个字段即通过：诊断不能变成新闸门。
    payload["evidence"]["calculations"][0]["expression"] = "2*4 + (-2)*2"
    candidate = render_suggestions(source, payload, expected_task_id="a" * 32,
                                   expected_unit_id="b" * 32, expected_run_id="run-1",
                                   calc_calls=calls)
    assert candidate.summary == "一般问题"


def test_image_evidence_error_lists_accepted_shapes():
    """5讲单元2 的根因：images 只接受数组或 not_applicable，报错必须给出可照抄的形态。"""
    source = "木板。"
    payload = _scaffold(source, [_correction(source, "木板", "木块")])
    payload["evidence"]["images"] = {"status": "ok", "reference_index": 1}
    with pytest.raises(ValueError) as error:
        _render(source, payload)
    assert error.value.code == "proposal.evidence-images"
    message = str(error.value)
    assert "数组" in message and "not_applicable" in message
    assert "reference_index" in message, "报错要指出实际收到的形状，便于照契约改写"

    payload["evidence"]["images"] = [{
        "id": "img1", "reference_index": 1, "original_path": "/tmp/a.png",
        "actual_read_path": "/tmp/a-whitebg.png", "position": {"line": 3, "column": 1},
        "readable": True, "semantic": "波形图", "verdict": "与题干一致",
    }]
    assert _render(source, payload).summary == "一般问题"

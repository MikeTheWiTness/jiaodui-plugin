"""schema v2 定位建议到完整校对报告的确定性生成。"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from . import markers
from .source_index import LocationError, resolve_location, source_digest

# 封套常量定义在 markers（最低层，供语法/审计/转义共用），这里保持既有导入面。
REPORT_V2_PREFIX = markers.REPORT_V2_PREFIX
BODY_END = markers.BODY_END
_SEVERITY_RANK = {"轻微问题": 1, "一般问题": 2, "严重错误": 3}


def extract_body(source_text: str) -> str:
    """提取单元源文中的**正文**；正文之外的部分（信封）不参与报告还原。

    ADR 0006 §6/§7：v2 正文当前就是源文全文——实测回放材料与冻结语料里没有一份
    源文含 `## 前置参考` 之类的信封行，那些装饰只存在于 v1 报告里。这里保留唯一的
    正文提取点：将来若真要引入源文侧信封（例如导入器写死的抬头），只改这一处，
    CAS 契约、`body_sha256` 语义与所有调用方都不必动。
    """
    return source_text
_REQUIRED_KEYS = {
    "schema_version", "task_id", "unit_id", "run_id", "source_sha256", "body_sha256",
    "proposal_revision", "summary", "corrections", "evidence",
}
_ALLOWED_KEYS = _REQUIRED_KEYS | {"self_check"}
_CORRECTION_KEYS = {
    "id", "location_id", "expected_original", "replacement", "reason", "category",
    "severity", "evidence_ids",
}


def proposal_json_schema() -> dict[str, Any]:
    """导出结构化建议schema，供DSH工具注册复用。"""
    correction = {
        "type": "object", "additionalProperties": False,
        "required": sorted(_CORRECTION_KEYS),
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "location_id": {"type": "string", "minLength": 1},
            "expected_original": {"type": "string", "minLength": 1},
            "replacement": {"type": "string"},
            "reason": {"type": "string", "minLength": 1},
            "category": {"type": "string", "minLength": 1},
            "severity": {"type": "string", "enum": sorted(_SEVERITY_RANK)},
            "evidence_ids": {"type": "array", "minItems": 1,
                             "items": {"type": "string", "minLength": 1}},
        },
    }
    self_check = {
        "type": "object", "additionalProperties": False,
        "required": ["status", "checks", "unresolved"],
        "properties": {
            "status": {"type": "string", "enum": ["passed", "needs_user"]},
            "checks": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
            "unresolved": {"type": "array", "items": {"type": "string"}},
        },
    }
    properties = {
        "schema_version": {"type": "integer", "const": 2},
        "task_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
        "unit_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
        "run_id": {"type": "string", "minLength": 1},
        "source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "body_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "proposal_revision": {"type": "integer", "minimum": 1},
        "summary": {"type": "string", "enum": ["无问题", "轻微问题", "一般问题", "严重错误"]},
        "corrections": {"type": "array", "items": correction},
        "evidence": {"type": "object", "additionalProperties": True},
        "self_check": self_check,
    }
    return {"type": "object", "additionalProperties": False,
            "required": sorted(_REQUIRED_KEYS | {"self_check"}), "properties": properties}


class SuggestionError(ValueError):
    """建议数据不符合定位、版本或报告契约。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReportCandidate:
    """已经按源文顺序编号且通过文本闸门的候选。"""

    text: str
    summary: str
    corrections: tuple[dict[str, Any], ...]
    source_sha256: str
    proposal_sha256: str


def _collect_evidence_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        if isinstance(value.get("id"), str):
            found.add(value["id"])
        for child in value.values():
            found.update(_collect_evidence_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_collect_evidence_ids(child))
    return found


_REQUIRED_SELF_CHECKS = {
    "real_issue", "replacement_semantics", "related_coverage", "scope_and_uncertainty", "severity",
}


def _validate_first_pass_evidence(evidence: dict) -> set[str]:
    assumptions = evidence.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions:
        raise _error("proposal.evidence-assumptions", "必须记录首轮假设/核验依据")
    identities: set[str] = set()
    for index, entry in enumerate(assumptions):
        # 逐项点名缺哪个字段：只说「需含 id/text/source_locations」时，调用方无法判断
        # 是第几项、哪个字段不合格，只能整体重写。
        problems: list[str] = []
        if not isinstance(entry, dict):
            problems.append("不是对象")
        else:
            if not isinstance(entry.get("id"), str) or not entry["id"]:
                problems.append("id 缺失或为空")
            if not isinstance(entry.get("text"), str) or not entry["text"].strip():
                problems.append("text 缺失或为空")
            if not isinstance(entry.get("source_locations"), list):
                problems.append("source_locations 缺失或不是数组")
        if problems:
            raise _error("proposal.evidence-assumptions",
                         f"假设证据需含id、text和source_locations；"
                         f"assumptions[{index}] 有问题：" + "、".join(problems))
        identities.add(entry["id"])
    symbols = evidence.get("symbols")
    if not isinstance(symbols, list):
        raise _error("proposal.evidence-symbols",
                     "symbols须显式列出或为空数组（无符号时写 []，不要省略或写 null）；"
                     f"实际收到：{_shape_of(symbols)}")
    images = evidence.get("images")
    calculations = evidence.get("calculations")
    item_fields = {
        "images": ("id", "reference_index", "original_path", "actual_read_path",
                   "position", "readable", "semantic", "verdict"),
        "calculations": ("id", "call_id", "expression", "result"),
    }
    for key, value in (("images", images), ("calculations", calculations)):
        if isinstance(value, list):
            continue
        if (not isinstance(value, dict) or value.get("status") != "not_applicable"
                or not isinstance(value.get("reason"), str) or not value["reason"].strip()):
            # 5讲 单元2 的根因：契约只示范了 not_applicable，模型带图时无从照抄形态
            raise _error(
                f"proposal.evidence-{key}",
                f"{key} 只接受两种形态：① 证据数组，每项含 "
                f"{'、'.join(item_fields[key])}；"
                f"② {{\"status\": \"not_applicable\", \"reason\": \"<原因>\"}}（确实不适用时才用）。"
                f"实际收到：{_shape_of(value)}")
    return identities | _collect_evidence_ids(evidence)


def _shape_of(value: Any, limit: int = 140) -> str:
    """诊断用的短形态描述：对象列出键名，其他给类型与值。"""
    if isinstance(value, dict):
        return ("对象，键=" + "、".join(sorted(str(key) for key in value)))[:limit]
    if isinstance(value, list):
        return f"数组，长度 {len(value)}"
    return f"{type(value).__name__}: {value!r}"[:limit]


def _contains_string(value: Any, expected: str) -> bool:
    if isinstance(value, str):
        return value == expected
    if isinstance(value, dict):
        return any(_contains_string(child, expected) for child in value.values())
    if isinstance(value, list):
        return any(_contains_string(child, expected) for child in value)
    return False


def _string_leaves(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    """列出参数里的全部字符串叶子（字段路径, 值），供绑定失败时给出可照抄的候选。

    多参数调用（如 `equality` 的 expression_a / expression_b）没有唯一的
    `expression` 字段；只报「不逐字一致」会让子 agent 反复试参数，因此这里把
    每个可逐字填写的取值连字段名一起列出。
    """
    if isinstance(value, str):
        return [(prefix or "value", value)]
    if isinstance(value, dict):
        leaves: list[tuple[str, str]] = []
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            leaves.extend(_string_leaves(child, child_prefix))
        return leaves
    if isinstance(value, list):
        leaves = []
        for index, child in enumerate(value):
            leaves.extend(_string_leaves(child, f"{prefix}[{index}]" if prefix else f"[{index}]"))
        return leaves
    return []


_NON_EXPRESSION_PARAMS = frozenset({
    "task_id", "unit_id", "subject", "variables", "domain", "dim_operation",
    "operation", "target_units", "quantities", "unit_definitions", "substitutions",
})
_EXPRESSION_PARAM_HINTS = ("expression", "formula", "equation")


def _expression_candidates(params: Any) -> list[tuple[str, str]]:
    """挑出可填进 `expression` 的字符串参数：优先表达式字段，排除身份/元数据字段。

    身份字段（task_id / unit_id / subject 等）与元数据子树（unit_definitions /
    substitutions）虽然也存在于 params 里，列出来只会诱导子 agent 抄错字段；
    多参数调用优先列出 expression_* / formula 这类字段。
    """
    leaves = [(path, value) for path, value in _string_leaves(params)
              if not any(segment in _NON_EXPRESSION_PARAMS
                         for segment in re.split(r"\.|\[", path))]
    preferred = [(path, value) for path, value in leaves
                 if any(hint in path.lower() for hint in _EXPRESSION_PARAM_HINTS)]
    return preferred or leaves


def _calc_expression_mismatch(call: dict, expression: str) -> str:
    """`expression` 与记账参数不逐字一致时的诊断：列出可照抄的取值并说明多参数调用写法。"""
    candidates = _expression_candidates(call.get("params"))
    listed = "、".join(f"{path}={value!r}" for path, value in candidates)
    message = (f"expression 必须与调用时传入的某个参数值逐字一致（含空格与大小写）；"
               f"你写的是 {expression!r}，该调用记录的可用取值是 {listed or '（该调用没有可用的字符串参数）'}")
    values = [value for _, value in candidates]
    if len(values) >= 2 and all(value in expression for value in values[:2]):
        joined = " 与 ".join(repr(value) for value in values[:2])
        message += (f"；你像是把 {joined} 拼成了一条。多参数调用请改成其中一个参数的"
                    f"原样值（如 {values[0]!r}），或按字段分条记录两次核验，不要用 '==' 自行拼接")
    return message


def _validate_calculation_evidence(evidence: dict, calls: list[dict] | None, *, task_id: str,
                                  unit_id: str, run_id: str, source_sha256: str) -> set[str]:
    calculations = evidence["calculations"]
    if isinstance(calculations, dict):
        return set()
    calls_by_id = {entry.get("call_id"): entry for entry in (calls or []) if isinstance(entry, dict)}
    identifiers: set[str] = set()
    for index, item in enumerate(calculations):
        # 逐项点名缺哪个字段；「须含id、call_id、expression和result」不指明位置时
        # 调用方只能重写整份 evidence。
        problems: list[str] = []
        if not isinstance(item, dict):
            problems.append("不是对象")
        else:
            if not isinstance(item.get("id"), str) or not item["id"]:
                problems.append("id 缺失或为空")
            if not isinstance(item.get("call_id"), str):
                problems.append("call_id 缺失或不是字符串")
            if not isinstance(item.get("expression"), str) or not item["expression"]:
                problems.append("expression 缺失或为空")
            if "result" not in item:
                problems.append("result 缺失")
        if problems:
            raise _error("proposal.evidence-calculation",
                         f"计算证据须含id、call_id、expression和result；"
                         f"calculations[{index}] 有问题：" + "、".join(problems))
        call = calls_by_id.get(item["call_id"])
        if call is None:
            # 4讲 单元10 的根因：7 个绑定条件只报一句「未绑定」，无法定位
            raise _error("proposal.calc-call-mismatch",
                         f"call_id {item['call_id']!r} 不在当前轮次的 calc 记账里；"
                         f"请用带 --task-id/--unit-id 的实际调用返回的 call_id")
        if call.get("task_id") != task_id or call.get("unit_id") != unit_id:
            raise _error("proposal.calc-call-mismatch",
                         f"call_id {item['call_id']!r} 属于另一个单元或另一份材料，不能作为本单元证据")
        if call.get("run_id") != run_id:
            raise _error("proposal.calc-call-mismatch",
                         f"call_id {item['call_id']!r} 记录在另一轮次（记录 run={call.get('run_id')!r}，"
                         f"当前 run={run_id!r}）；请在本轮用带身份的 calc 重新实算")
        if call.get("source_sha256") != source_sha256:
            raise _error("proposal.calc-call-mismatch",
                         f"call_id {item['call_id']!r} 绑定的是另一份源文摘要"
                         f"（记录 {str(call.get('source_sha256'))[:12]}…，当前 {source_sha256[:12]}…）；"
                         f"源文变化后必须重新实算")
        if not call.get("success"):
            raise _error("proposal.calc-call-mismatch",
                         f"call_id {item['call_id']!r} 未成功（success=false，"
                         f"error={str((call.get('result') or {}).get('error'))[:80]!r}），"
                         f"失败的计算不能作为证据")
        if not _contains_string(call.get("params"), item["expression"]):
            raise _error("proposal.calc-call-mismatch",
                         _calc_expression_mismatch(call, item["expression"]))
        recorded = (call.get("result") or {}).get("result")
        if recorded != item["result"]:
            raise _error("proposal.calc-call-mismatch",
                         f"result 必须与调用返回的 result.result 逐字一致；"
                         f"你写的是 {item['result']!r}，该调用返回的是 {recorded!r}")
        identifiers.update((item["id"], item["call_id"]))
    return identifiers


def _validate_self_check(self_check: Any, *, has_corrections: bool) -> None:
    if (not isinstance(self_check, dict) or set(self_check) != {"status", "checks", "unresolved"}
            or self_check.get("status") != "passed"
            or not isinstance(self_check.get("checks"), list)
            or any(not isinstance(item, str) for item in self_check["checks"])
            or not isinstance(self_check.get("unresolved"), list)
            or self_check["unresolved"]):
        raise _error("proposal.self-check", "建议自查未通过或存在未解决争议")
    checks = set(self_check["checks"])
    required = _REQUIRED_SELF_CHECKS if has_corrections else {"no_issue_review"}
    if not required <= checks:
        # 必需项是固定字面量；不列出缺失项时调用方只能猜拼写。实测（第 11 讲 单元3）
        # 把 checks 写成「real_issue: 说明…」这类带后缀的串，连撞 4 次。
        raise _error("proposal.self-check-incomplete",
                     "自查未覆盖全部必需检查项：缺少 " + "、".join(sorted(required - checks))
                     + "。checks 只接受这些**字面量**（不要加冒号说明后缀）："
                     + "、".join(sorted(required)))


def _error(code: str, message: str) -> SuggestionError:
    return SuggestionError(code, message)


def render_suggestions(source_text: str, payload: dict, *, expected_task_id: str,
                       expected_unit_id: str, expected_run_id: str,
                       calc_calls: list[dict] | None = None,
                       expected_source_sha256: str | None = None) -> ReportCandidate:
    """校验建议并从不可变源文生成报告全文；不读写文件。

    两个摘要分别校验（ADR 0006 §7）：`source_sha256` 绑定源文**文件字节**
    （由调用方经 `expected_source_sha256` 传入，缺省退回正文摘要以兼容直接调用），
    `body_sha256` 绑定**正文文本**。诊断因此能指出到底哪一项对不上。
    """
    if not isinstance(payload, dict):
        raise _error("proposal.schema", "建议必须是 JSON 对象")
    # 只报「字段缺失或未支持」而不点名，会让调用方逐个试键。实测（第 11 讲 单元1）
    # 同一处缺键连撞 5 次提交，196 步后放弃并由父代理重派。
    unknown = sorted(str(key) for key in set(payload) - _ALLOWED_KEYS)
    missing = sorted(_REQUIRED_KEYS - set(payload))
    if unknown or missing:
        details = []
        if missing:
            details.append("缺少必需字段 " + "、".join(missing))
        if unknown:
            details.append("包含未支持字段 " + "、".join(unknown))
        raise _error("proposal.schema",
                     "建议字段缺失或包含未支持字段：" + "；".join(details)
                     + "。允许的顶层字段只有 " + "、".join(sorted(_ALLOWED_KEYS)))
    if (type(payload.get("schema_version")) is not int or payload["schema_version"] != 2
            or payload.get("task_id") != expected_task_id
            or payload.get("unit_id") != expected_unit_id
            or payload.get("run_id") != expected_run_id):
        raise _error("proposal.identity-mismatch", "schema版本或task/unit/run身份不匹配")
    if type(payload.get("proposal_revision")) is not int or payload["proposal_revision"] < 1:
        raise _error("proposal.revision", "proposal_revision必须为正整数")
    if not isinstance(payload.get("evidence"), dict):
        raise _error("proposal.evidence", "evidence必须为对象")
    if not isinstance(payload.get("corrections"), list):
        raise _error("proposal.corrections", "corrections必须为数组")
    corrections = payload["corrections"]
    _validate_self_check(payload.get("self_check"), has_corrections=bool(corrections))

    body_text = extract_body(source_text)
    if not body_text.strip():
        raise _error("proposal.empty-body",
                     "单元源文没有正文（仅空白），不能生成空报告；该单元应按 skip 处理")
    body_digest = source_digest(body_text)
    if payload.get("body_sha256") != body_digest:
        raise _error("proposal.source-mismatch", "建议绑定的正文摘要已失效（body_sha256 不匹配）")
    file_digest = expected_source_sha256 if expected_source_sha256 is not None else source_digest(source_text)
    if payload.get("source_sha256") != file_digest:
        raise _error("proposal.source-mismatch", "建议绑定的源文文件摘要已失效（source_sha256 不匹配）")
    corrections = payload.get("corrections")
    if not isinstance(corrections, list):
        raise _error("proposal.corrections", "corrections必须为数组")
    if corrections:
        if not isinstance(payload.get("summary"), str) or payload["summary"] not in _SEVERITY_RANK:
            raise _error("proposal.summary", "含建议时summary必须为有效问题严重度")
    elif payload.get("summary") != "无问题":
        raise _error("proposal.summary", "无修改建议时summary必须为无问题")

    evidence_ids = _validate_first_pass_evidence(payload["evidence"])
    evidence_ids |= _validate_calculation_evidence(
        payload["evidence"], calc_calls, task_id=expected_task_id, unit_id=expected_unit_id,
        run_id=expected_run_id, source_sha256=file_digest)
    resolved: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in corrections:
        if not isinstance(item, dict) or set(item) != _CORRECTION_KEYS:
            raise _error("proposal.correction-schema", "修改项字段不符合schema v2")
        correction_id = item["id"]
        if not isinstance(correction_id, str) or not correction_id or correction_id in seen_ids:
            raise _error("proposal.duplicate-id", "修改项id缺失或重复")
        seen_ids.add(correction_id)
        if (not isinstance(item["expected_original"], str) or not item["expected_original"]
                or not isinstance(item["replacement"], str)
                or item["replacement"] == item["expected_original"]):
            raise _error("proposal.no-op", "原文必须非空且修改后内容不能与原文相同")
        # ADR 0006：竖线与标记括号由写入侧转义承载，不再拒绝（可表达字符集只看编码）
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            raise _error("proposal.reason", "每项修改必须提供原因")
        if not isinstance(item["category"], str) or not item["category"]:
            raise _error("proposal.category", "每项修改必须提供类别")
        if not isinstance(item["severity"], str) or item["severity"] not in _SEVERITY_RANK:
            raise _error("proposal.severity", "每项修改必须声明有效严重度")
        if (not isinstance(item["evidence_ids"], list) or not item["evidence_ids"]
                or any(not isinstance(identity, str) or identity not in evidence_ids
                       for identity in item["evidence_ids"])):
            raise _error("proposal.evidence-reference", "每项修改必须引用已提交的证据ID")
        if not isinstance(item["location_id"], str):
            raise _error("proposal.location", "location_id必须为字符串")
        try:
            # 位置索引由调用方按源文文本摘要生成，这里必须用同一份文本摘要校验
            span = resolve_location(source_text, source_digest(source_text),
                                    item["location_id"], item["expected_original"])
        except LocationError as exc:
            raise _error(exc.code, str(exc)) from exc
        from .source_index import _safe_span
        if _safe_span(source_text, span["start"], span["end"]) != (span["start"], span["end"]):
            raise _error("proposal.unsafe-location", "定位必须完整覆盖公式或加粗结构")
        resolved.append({**item, **span})

    resolved.sort(key=lambda item: (item["start"], item["end"]))
    previous_end = -1
    for item in resolved:
        if item["start"] < previous_end:
            raise _error("proposal.overlap", "多个修改区间重叠，需合并为一条建议")
        previous_end = item["end"]
    if resolved:
        actual_summary = max((item["severity"] for item in resolved), key=_SEVERITY_RANK.__getitem__)
        if payload["summary"] != actual_summary:
            raise _error("proposal.summary-mismatch", "头部严重度必须等于修改项中的最高严重度")

    chunks: list[str] = []
    cursor = 0
    reasons: list[str] = []
    numbered: list[dict[str, Any]] = []
    for number, item in enumerate(resolved, 1):
        chunks.extend((source_text[cursor:item["start"]],
                       f"【{number}|{markers.escape_marker_field(item['expected_original'])}"
                       f"|{markers.escape_marker_field(item['replacement'])}】"))
        cursor = item["end"]
        reasons.append(f"{number}. {item['reason'].strip()}")
        numbered.append({**item, "number": number})
    chunks.append(source_text[cursor:])
    marked_body = "".join(chunks)
    if markers.split_marked_body(marked_body, escaped=True) != source_text:
        raise _error("proposal.restore-mismatch", "标记正文不能逐字恢复为原始源文")

    normalized_body = marked_body.replace("\r\n", "\n").replace("\r", "\n")
    import json
    evidence_note = "核验说明：\n" + json.dumps(payload["evidence"], ensure_ascii=False, indent=2)
    report = (f"{REPORT_V2_PREFIX}\n总结行：{payload['summary']}\n\n### 标记原文\n"
              f"<!-- jiaodui-body-length:{len(marked_body)}:{len(normalized_body)} -->\n"
              f"{marked_body}\n{BODY_END}\n### 修改原因\n"
              f"{'\n'.join(reasons) if reasons else '无'}\n\n{evidence_note}\n")
    proposal_bytes = json_bytes(payload)
    return ReportCandidate(report, payload["summary"], tuple(numbered), file_digest,
                           hashlib.sha256(proposal_bytes).hexdigest())


def json_bytes(value: Any) -> bytes:
    """生成稳定的UTF-8 JSON字节。"""
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

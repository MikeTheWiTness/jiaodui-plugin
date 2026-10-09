"""schema v2 定位建议到完整校对报告的确定性生成。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from . import markers
from .source_index import LocationError, resolve_location, source_digest

REPORT_V2_PREFIX = "<!-- jiaodui-report-v2 -->"
BODY_END = "<!-- jiaodui-body-end -->"
_SEVERITY_RANK = {"轻微问题": 1, "一般问题": 2, "严重错误": 3}
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
        "self_check": {"type": "object", "additionalProperties": True},
    }
    return {"type": "object", "additionalProperties": False,
            "required": sorted(_REQUIRED_KEYS), "properties": properties}


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


def _error(code: str, message: str) -> SuggestionError:
    return SuggestionError(code, message)


def render_suggestions(source_text: str, payload: dict, *, expected_task_id: str,
                       expected_unit_id: str, expected_run_id: str) -> ReportCandidate:
    """校验建议并从不可变源文生成报告全文；不读写文件。"""
    if not isinstance(payload, dict) or set(payload) - _ALLOWED_KEYS or not _REQUIRED_KEYS <= set(payload):
        raise _error("proposal.schema", "建议字段缺失或包含未支持字段")
    if (type(payload.get("schema_version")) is not int or payload["schema_version"] != 2
            or payload.get("task_id") != expected_task_id
            or payload.get("unit_id") != expected_unit_id
            or payload.get("run_id") != expected_run_id):
        raise _error("proposal.identity-mismatch", "schema版本或task/unit/run身份不匹配")
    if type(payload.get("proposal_revision")) is not int or payload["proposal_revision"] < 1:
        raise _error("proposal.revision", "proposal_revision必须为正整数")
    if not isinstance(payload.get("evidence"), dict):
        raise _error("proposal.evidence", "evidence必须为对象")
    if "self_check" in payload and not isinstance(payload["self_check"], dict):
        raise _error("proposal.self-check", "self_check必须为对象")

    digest = source_digest(source_text)
    if payload.get("source_sha256") != digest or payload.get("body_sha256") != digest:
        raise _error("proposal.source-mismatch", "建议绑定的源文摘要已失效")
    if markers.INLINE_MARKER_CAPTURE_RE.search(source_text):
        raise _error("proposal.source-markers", "源文含契约标记语法，当前报告格式无法无损区分")
    corrections = payload.get("corrections")
    if not isinstance(corrections, list):
        raise _error("proposal.corrections", "corrections必须为数组")
    if corrections:
        if not isinstance(payload.get("summary"), str) or payload["summary"] not in _SEVERITY_RANK:
            raise _error("proposal.summary", "含建议时summary必须为有效问题严重度")
    elif payload.get("summary") != "无问题":
        raise _error("proposal.summary", "无修改建议时summary必须为无问题")

    evidence_ids = _collect_evidence_ids(payload["evidence"])
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
        if any(token in item["expected_original"] for token in ("|", "【", "】")):
            raise _error("proposal.marker-unrepresentable", "原文含当前标记语法无法无损编码的括号或竖线")
        if any(token in item["replacement"] for token in ("【", "】")):
            raise _error("proposal.marker-unrepresentable", "修改后内容含当前标记语法无法编码的标记括号")
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
            span = resolve_location(source_text, digest, item["location_id"], item["expected_original"])
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
                       f"【{number}|{item['expected_original']}|{item['replacement']}】"))
        cursor = item["end"]
        reasons.append(f"{number}. {item['reason'].strip()}")
        numbered.append({**item, "number": number})
    chunks.append(source_text[cursor:])
    marked_body = "".join(chunks)
    if markers.split_marked_body(marked_body) != source_text:
        raise _error("proposal.restore-mismatch", "标记正文不能逐字恢复为原始源文")

    normalized_body = marked_body.replace("\r\n", "\n").replace("\r", "\n")
    report = (f"{REPORT_V2_PREFIX}\n总结行：{payload['summary']}\n\n### 标记原文\n"
              f"<!-- jiaodui-body-length:{len(marked_body)}:{len(normalized_body)} -->\n"
              f"{marked_body}\n{BODY_END}\n### 修改原因\n"
              f"{'\n'.join(reasons) if reasons else '无'}\n")
    proposal_bytes = json_bytes(payload)
    return ReportCandidate(report, payload["summary"], tuple(numbered), digest,
                           hashlib.sha256(proposal_bytes).hexdigest())


def json_bytes(value: Any) -> bytes:
    """生成稳定的UTF-8 JSON字节。"""
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

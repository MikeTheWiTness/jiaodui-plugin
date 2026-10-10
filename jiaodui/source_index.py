"""与原始源文绑定的 Unicode 码点位置索引。"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass

from .markers import scan_math_spans

INDEX_VERSION = 1
_STRONG_RE = re.compile(r"\*\*(?s:.+?)\*\*")


class LocationError(ValueError):
    """位置查询或版本校验失败。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def source_digest(source_text: str) -> str:
    """按 UTF-8 原始文本字节计算摘要，不做换行或 Unicode 归一化。"""
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()


def _brief(value: str, limit: int = 120) -> str:
    """诊断用的短表示：带引号，超长截断并标出真实长度。

    错误信息会进入模型上下文，必须给足定位信息又不能把整段正文灌进去。
    """
    if len(value) <= limit:
        return repr(value)
    return f"{value[:limit]!r}…（共 {len(value)} 字符）"


def _location_id(source_sha256: str, start: int, end: int) -> str:
    raw = json.dumps({"v": INDEX_VERSION, "h": source_sha256, "s": start, "e": end},
                     separators=(",", ":"), sort_keys=True).encode("ascii")
    token = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    checksum = hashlib.sha256(raw).hexdigest()[:12]
    return f"loc1.{token}.{checksum}"


def _decode_location(location_id: str) -> tuple[str, int, int]:
    try:
        prefix, token, checksum = location_id.split(".", 2)
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        if prefix != "loc1" or hashlib.sha256(raw).hexdigest()[:12] != checksum:
            raise ValueError
        payload = json.loads(raw)
        if type(payload.get("v")) is not int or payload["v"] != INDEX_VERSION:
            raise ValueError
        start, end = payload["s"], payload["e"]
        if type(start) is not int or type(end) is not int:
            raise ValueError
        return payload["h"], start, end
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise LocationError("location.invalid", "位置ID格式无效") from exc


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    last_newline = text.rfind("\n", 0, offset)
    return line, offset - last_newline


def _safe_span(text: str, start: int, end: int) -> tuple[int, int]:
    """将命中扩至完整公式或加粗区间；不尝试改写这些结构。"""
    changed = True
    while changed:
        changed = False
        for span_start, span_end in [*scan_math_spans(text),
                                     *((m.start(), m.end()) for m in _STRONG_RE.finditer(text))]:
            if start < span_end and span_start < end and (start > span_start or end < span_end):
                start, end = min(start, span_start), max(end, span_end)
                changed = True
    return start, end


def _paragraph_id(text: str, offset: int) -> str:
    starts = [0]
    for match in re.finditer(r"\n[ \t]*\n+", text):
        starts.append(match.end())
    paragraph_start = max(start for start in starts if start <= offset)
    following = re.search(r"\n[ \t]*\n+", text[paragraph_start:])
    paragraph_end = paragraph_start + following.start() if following else len(text)
    number = starts.index(paragraph_start) + 1
    content_hash = hashlib.sha256(text[paragraph_start:paragraph_end].encode("utf-8")).hexdigest()[:12]
    return f"p{number}-{content_hash}"


def query_locations(source_text: str, source_sha256: str, phrase: str,
                    *, context_chars: int = 48) -> list[dict]:
    """列出短语在源文中的全部位置；match_index 按全文从 1 起计数。"""
    if not phrase:
        raise LocationError("location.empty-query", "定位短语不能为空")
    actual_digest = source_digest(source_text)
    if source_sha256 != actual_digest:
        raise LocationError("location.stale", "源文摘要与传入文本不一致")
    results = []
    cursor = 0
    match_index = 0
    while (start := source_text.find(phrase, cursor)) >= 0:
        match_index += 1
        end = start + len(phrase)
        safe_start, safe_end = _safe_span(source_text, start, end)
        line, column = _line_column(source_text, safe_start)
        results.append({
            "location_id": _location_id(source_sha256, safe_start, safe_end),
            "paragraph_id": _paragraph_id(source_text, safe_start),
            "match_index": match_index,
            "start": safe_start,
            "end": safe_end,
            "line": line,
            "column": column,
            "original": source_text[safe_start:safe_end],
            "context": source_text[max(0, safe_start - context_chars):min(len(source_text), safe_end + context_chars)],
        })
        cursor = start + 1
    return results


def resolve_location(source_text: str, source_sha256: str, location_id: str,
                     expected_original: str) -> dict:
    """校验位置ID、当前原文摘要和预期原文字面，返回精确码点区间。"""
    actual_digest = source_digest(source_text)
    if source_sha256 != actual_digest:
        raise LocationError("location.stale", "源文摘要已变化，位置失效")
    token_digest, start, end = _decode_location(location_id)
    if token_digest != source_sha256:
        raise LocationError("location.stale", "位置ID绑定了其他源文版本")
    if start < 0 or end <= start or end > len(source_text):
        raise LocationError("location.out-of-range", "位置区间越界或为空")
    original = source_text[start:end]
    if original != expected_original:
        # 只报「不一致」会让调用方无从修正：这里必须同时给出**实际命中的原文**与
        # **它写入的期望值**。实测（第 11 讲 单元3）同一处子串误用连撞 20 次提交，
        # 最终放弃该条修改并改报「无问题」，造成静默漏报。
        raise LocationError(
            "location.original-mismatch",
            f"位置原文与 expected_original 不一致：该 location_id 命中的原文是 {_brief(original)}，"
            f"你写的 expected_original 是 {_brief(expected_original)}；"
            f"expected_original 必须逐字复制 unit-locate 返回的 original 整段（不要只截取子串），"
            f"要改的是子串就先把 unit-locate 的 phrase 收敛到该整段")
    line, column = _line_column(source_text, start)
    return {"start": start, "end": end, "line": line, "column": column,
            "original": original, "paragraph_id": _paragraph_id(source_text, start)}

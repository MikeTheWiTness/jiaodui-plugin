"""按不可变源文解析修订锚点。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .markers import scan_math_spans

_MAX_OLD = 1000
_MAX_CONTEXT = 200
_ZERO_WIDTH = frozenset("\u200b\u200c\u200d\ufeff")
_STRONG_RE = re.compile(r"\*\*(?s:.+?)\*\*")


class AnchorError(ValueError):
    """锚点定位失败，包含可供调用方展示的结构化诊断。"""

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class AnchorMatch:
    """源文中的半开码点区间与定位信息。"""

    start: int
    end: int
    original: str
    line: int
    column: int
    normalized_match: bool


def _line_column(text: str, offset: int) -> tuple[int, int]:
    line = text.count("\n", 0, offset) + 1
    return line, offset - text.rfind("\n", 0, offset)


def _overlapping_matches(text: str, needle: str) -> list[int]:
    starts: list[int] = []
    cursor = 0
    while (start := text.find(needle, cursor)) >= 0:
        starts.append(start)
        cursor = start + 1
    return starts


def _normalize_source(text: str) -> tuple[str, list[tuple[int, int]]]:
    """返回限定归一化文本及每个码点对应的源文半开区间。"""
    chars: list[str] = []
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in _ZERO_WIDTH:
            i += 1
            continue
        if ch == "\r" and i + 1 < len(text) and text[i + 1] == "\n":
            chars.append("\n")
            spans.append((i, i + 2))
            i += 2
            continue
        chars.append(ch)
        spans.append((i, i + 1))
        i += 1
    return "".join(chars), spans


def _escape_invisible(text: str) -> str:
    escaped = {"\r": "\\r", "\n": "\\n", "\t": "\\t"}
    return "".join(escaped.get(ch, f"\\u{ord(ch):04x}" if ch in _ZERO_WIDTH else ch) for ch in text)


def _normalized_boundary(source_spans: list[tuple[int, int]], query_spans: list[tuple[int, int]],
                         source_start: int, raw_boundary: int, *, end: bool = False) -> int:
    """把组合 query 的原始边界映射到源文码点边界。"""
    for index, (query_start, query_end) in enumerate(query_spans):
        if query_start < raw_boundary < query_end:
            source_span_start, source_span_end = source_spans[source_start + index]
            source_width = source_span_end - source_span_start
            query_width = query_end - query_start
            raw_offset = raw_boundary - query_start
            return source_span_start + raw_offset * source_width // query_width
        if raw_boundary <= query_start:
            if end and index:
                return source_spans[source_start + index - 1][1]
            return source_spans[source_start + index][0]
    return source_spans[source_start + len(query_spans) - 1][1]


def _candidate_details(source: str, spans: list[tuple[int, int]],
                       starts: list[int], width: int) -> list[dict]:
    candidates = []
    for index, start in enumerate(starts[:5], 1):
        source_start, source_end = spans[start][0], spans[start + width - 1][1]
        before = source[max(0, source_start - 24):source_start]
        after = source[source_end:min(len(source), source_end + 24)]
        line, column = _line_column(source, source_start)
        candidates.append({
            "match_index": index,
            "line": line,
            "column": column,
            "context_before": _escape_invisible(before),
            "context_after": _escape_invisible(after),
        })
    return candidates


def _structure_spans(source: str) -> list[tuple[int, int]]:
    return [*scan_math_spans(source), *((m.start(), m.end()) for m in _STRONG_RE.finditer(source))]


def _expanded_structure_span(source: str, start: int, end: int) -> tuple[int, int]:
    changed = True
    while changed:
        changed = False
        for span_start, span_end in _structure_spans(source):
            if start < span_end and span_start < end and (start > span_start or end < span_end):
                start, end = min(start, span_start), max(end, span_end)
                changed = True
    return start, end


def validate_revision_input(old_text: str, new_text: str, reason: str, *,
                            evidence: list[dict] | None = None) -> None:
    """校验修订内容；锚点与上下文校验仍由 resolve_anchor 负责。

    evidence 为单条修订的结构化证据；只限制其中各文本字段长度，
    证据结构与覆盖要求留给提案校验层。
    """
    if len(new_text) > 2000 or len(reason) > 2000:
        raise AnchorError("revise.too-long", "new_text 或 reason 超过 2000 码点")
    pending: list = [evidence] if evidence is not None else []
    while pending:
        value = pending.pop()
        if isinstance(value, str):
            if len(value) > 4000:
                raise AnchorError("revise.too-long", "单条 evidence 文本超过 4000 码点")
        elif isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    if not reason.strip():
        raise AnchorError("revise.reason-empty", "reason 不能为空白")
    if old_text == new_text:
        raise AnchorError("revise.noop", "old_text 与 new_text 相同，无有效修改")


def resolve_anchor(source_text: str, old_text: str, *, context_before: str = "",
                   context_after: str = "", occurrence: int | None = None) -> AnchorMatch:
    """在源文定位 old_text；归一化只用于匹配，绝不改写返回原文。"""
    if not old_text:
        raise AnchorError("anchor.empty", "old_text 不能为空")
    if (len(old_text) > _MAX_OLD or len(context_before) > _MAX_CONTEXT
            or len(context_after) > _MAX_CONTEXT):
        raise AnchorError("anchor.too-long", "old_text 或上下文超过允许长度")
    if occurrence is not None and (type(occurrence) is not int or occurrence < 1):
        raise AnchorError("anchor.occurrence-out-of-range", "occurrence 必须是从 1 开始的整数",
                          {"match_count": 0, "candidates": [], "truncated": False})

    query = context_before + old_text + context_after
    query_start = len(context_before)
    query_end = query_start + len(old_text)
    exact_starts = _overlapping_matches(source_text, query)
    normalized_match = False
    spans: list[tuple[int, int]]

    if exact_starts:
        starts = exact_starts
        spans = [(i, i + 1) for i in range(len(source_text))]
        source_for_candidates = source_text
        match_width = len(query)
    else:
        normalized_source, spans = _normalize_source(source_text)
        normalized_query, query_spans = _normalize_source(query)
        normalized_old, _ = _normalize_source(old_text)
        starts = (_overlapping_matches(normalized_source, normalized_query)
                  if normalized_query and normalized_old else [])
        normalized_match = bool(starts)
        source_for_candidates = source_text
        match_width = len(normalized_query)

    if not starts:
        raise AnchorError("anchor.not-found", "源文中未找到匹配锚点",
                          {"match_count": 0, "candidates": [], "truncated": False})
    if occurrence is not None and occurrence > len(starts):
        raise AnchorError("anchor.occurrence-out-of-range", "occurrence 超出命中范围",
                          {"match_count": len(starts),
                           "candidates": _candidate_details(source_for_candidates, spans, starts, match_width),
                           "truncated": len(starts) > 5})
    if occurrence is None and len(starts) != 1:
        code = "anchor.ambiguous"
        raise AnchorError(code, f"锚点命中 {len(starts)} 处，请提供上下文或 occurrence",
                          {"match_count": len(starts),
                           "candidates": _candidate_details(source_for_candidates, spans, starts, match_width),
                           "truncated": len(starts) > 5})

    selected = starts[(occurrence - 1) if occurrence is not None else 0]
    if normalized_match:
        start = _normalized_boundary(spans, query_spans, selected, query_start)
        end = _normalized_boundary(spans, query_spans, selected, query_end, end=True)
    else:
        start = selected + query_start
        end = selected + query_end

    if end <= start:
        raise AnchorError("anchor.not-found", "归一化后 old_text 没有非空源文区间",
                          {"match_count": 0, "candidates": [], "truncated": False})

    expanded_start, expanded_end = _expanded_structure_span(source_text, start, end)
    if (expanded_start, expanded_end) != (start, end):
        required = source_text[expanded_start:expanded_end]
        raise AnchorError("anchor.structure-cut", "锚点只覆盖公式或加粗结构的一部分",
                          {"required_original": required,
                           "required_start": expanded_start,
                           "required_end": expanded_end})

    line, column = _line_column(source_text, start)
    return AnchorMatch(start, end, source_text[start:end], line, column, normalized_match)

"""交付即校验 verify-report（PRD §5.2 硬约束）。

模型产出与下游产物之间的唯一闸门。检查项：
1. 标记语法：必须匹配 【编号|原文|改为】；字段缺失、括号不配对 → 拒绝。
2. 修改原因对应：编号与标记原文中的标记一一对应（多、少、错位 → 拒绝）。
3. 严重度总结行：必须是 无问题 / 轻微问题 / 一般问题 / 严重错误 之一；
   缺失或裸「无」→ 拒绝；「无问题」不得同时含错误标记。
4. 原文完整性：去掉标记语法、还原各标记原文字段后，与单元源文逐段比对；
   缺段、重段、改变未标记正文 → 拒绝。仅落在无法定位的标记字段里的差异
   保留 unknown 警告。
5. 空原文字段 / 空操作 → 拒绝。
6. 原文字段能否在源文定位：unknown 不算失败，只记录。
7. 改为与原文无法区分（归一化后相同）→ 记为「需人工确认」，不拒绝。

「无问题」报告仍必须含两节（修改原因写「无」）。
"""
from __future__ import annotations

import re
import unicodedata
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import markers as M
from .report_parse import (SEVERITY_KEYWORDS, _extract_summary, marker_numbers,
                           parse_reason_entries, parse_reasons, split_sections,
                           strip_reference_preamble)

ERROR = "error"
WARNING = "warning"
MANUAL = "manual"

_ZERO_WIDTH_RE = M._ZERO_WIDTH_RE


@dataclass
class VerifyIssue:
    code: str
    message: str
    severity: str = ERROR
    location: str | None = None

    def to_dict(self) -> dict:
        d = {"code": self.code, "severity": self.severity, "message": self.message}
        if self.location:
            d["location"] = self.location
        return d


@dataclass
class VerifyResult:
    issues: list[VerifyIssue] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    summary: str = ""
    marker_count: int = 0

    @property
    def errors(self) -> list[VerifyIssue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[VerifyIssue]:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def manual(self) -> list[VerifyIssue]:
        return [i for i in self.issues if i.severity == MANUAL]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "marker_count": self.marker_count,
            "errors": [i.to_dict() for i in self.errors],
            "warnings": [i.to_dict() for i in self.warnings],
            "manual_review": [i.to_dict() for i in self.manual],
            "stats": self.stats,
        }


def _compress(text: str) -> str:
    """段落级比较前的归一化：剥离零宽字符并折叠全部空白。"""
    return "".join(_ZERO_WIDTH_RE.sub("", text).split())


def _paragraphs(text: str) -> list[str]:
    """按空行切段，返回非空段（原始，未折叠）。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = [p.strip() for p in __import__("re").split(r"\n\s*\n", text)]
    return [p for p in parts if p]


def _normalize_compare(text: str) -> str:
    """用于「改为与原文无法区分」的归一化：NFKC + 去空白 + 大小写折叠。"""
    return unicodedata.normalize("NFKC", _compress(text)).casefold()


def _line_of(text: str, needle: str, start: int = 0) -> str | None:
    idx = text.find(needle, start)
    if idx < 0:
        return None
    line = text.count("\n", 0, idx) + 1
    return f"行 {line}"


def _check_syntax(text: str, marked_section: str | None, issues: list[VerifyIssue]) -> None:
    if marked_section is None:
        return
    # 括号不配对
    opens = marked_section.count("【")
    closes = marked_section.count("】")
    if opens != closes:
        issues.append(VerifyIssue(
            "syntax.unbalanced-brackets",
            f"标记括号不配对：【 出现 {opens} 次，】 出现 {closes} 次",
        ))
    malformed = list(__import__("re").finditer(r"【\d+(?![|\d])", marked_section))
    for m in malformed:
        snippet = marked_section[m.start():m.start() + 30].replace("\n", " ")
        issues.append(VerifyIssue(
            "syntax.malformed-marker",
            f"格式异常的标记（编号后缺少竖线分隔符）：{snippet}…",
            location=_line_of(text, marked_section[m.start():m.start() + 5]) or None,
        ))
    # 字段数：每个 【编号|原文|改为】 内未转义的竖线必须恰好 2 个
    for block in __import__("re").finditer(r"【\d+[^】]*】", marked_section):
        body = block.group(0)[1:-1]  # 去掉首尾括号
        pipes = len(__import__("re").findall(r"(?<!\\)\|", body))
        if pipes != 2:
            snippet = block.group(0)[:30].replace("\n", " ")
            issues.append(VerifyIssue(
                "syntax.field-count",
                f"标记字段数错误（应为 编号|原文|改为 三段，实数竖线分隔符 {pipes} 个）：{snippet}…",
                location=_line_of(text, block.group(0)) or None,
            ))


def _check_sections(text: str, issues: list[VerifyIssue]) -> None:
    has_marked = bool(__import__("re").search(r"###\s*标记原文", text))
    has_reasons = bool(__import__("re").search(r"###\s*修改原因", text))
    if not has_marked:
        issues.append(VerifyIssue("sections.missing-marked", "缺少 ### 标记原文 段落"))
    if not has_reasons:
        issues.append(VerifyIssue("sections.missing-reasons", "缺少 ### 修改原因 段落"))


def _check_severity(text: str, summary_declared: str, marked_section: str | None,
                    issues: list[VerifyIssue]) -> str:
    if not summary_declared:
        issues.append(VerifyIssue(
            "severity.missing",
            "缺少严重度总结行（必须是 无问题 / 轻微问题 / 一般问题 / 严重错误 之一）",
        ))
        return ""
    if summary_declared not in SEVERITY_KEYWORDS:
        issues.append(VerifyIssue("severity.invalid", f"严重度取值非法：{summary_declared!r}"))
        return summary_declared
    if summary_declared == "无问题":
        nums = marker_numbers(marked_section or "")
        if nums:
            issues.append(VerifyIssue(
                "severity.contradiction",
                f"严重度为「无问题」却含 {len(nums)} 个错误标记",
            ))
    return summary_declared


def _check_reasons(marked_section: str | None, reasons_section: str | None,
                   issues: list[VerifyIssue]) -> dict[int, str]:
    entries = parse_reason_entries(reasons_section)
    reasons = parse_reasons(reasons_section)
    # 编号必须一一对应：重复编号（含区间重叠）会让前一条原因被静默覆盖
    entry_counts = Counter(n for n, _ in entries)
    for n, c in sorted(entry_counts.items()):
        if c > 1:
            issues.append(VerifyIssue(
                "reason.duplicate", f"修改原因编号 {n} 出现 {c} 次（重复或区间重叠），无法一一对应"))
    if marked_section is None:
        return reasons
    marker_nums = set(marker_numbers(marked_section))
    reason_nums = set(reasons)
    missing = sorted(marker_nums - reason_nums)
    extra = sorted(reason_nums - marker_nums)
    for n in missing:
        issues.append(VerifyIssue("reason.missing", f"标记 {n} 在修改原因中缺少对应条目"))
    for n in extra:
        issues.append(VerifyIssue("reason.orphan", f"修改原因编号 {n} 没有对应的标记"))
    if marker_nums:
        counts = Counter(marker_numbers(marked_section))
        for n, c in sorted(counts.items()):
            if c > 1:
                issues.append(VerifyIssue("marker.duplicate-num", f"标记编号 {n} 重复出现 {c} 次"))
    return reasons


def _check_marker_fields(marked_section: str | None, source_text: str | None,
                         issues: list[VerifyIssue]) -> dict:
    stats = {"empty_orig": 0, "noop": 0, "unknown": 0, "manual": 0, "restore_new": 0}
    if not marked_section:
        return stats
    for audit in M.audit_markers(marked_section, source_text):
        if audit.verdict == M.MARKER_EMPTY_ORIG:
            stats["empty_orig"] += 1
            issues.append(VerifyIssue(
                "original.empty", f"标记 {audit.num} 的原文字段为空（应填写被修改的原文）"))
        elif audit.verdict == M.MARKER_NOOP:
            stats["noop"] += 1
            issues.append(VerifyIssue(
                "original.noop",
                f"标记 {audit.num} 是空操作（原文与改为完全相同「{audit.original}」）"))
        elif audit.verdict == M.MARKER_RESTORE_NEW:
            stats["restore_new"] += 1
            issues.append(VerifyIssue(
                "original.not-locatable",
                f"标记 {audit.num} 的原文字段与题目原文对不上"
                f"（源文此处即「{audit.correction}」）：请核对原文，原文字段必须逐字一致"))
        elif audit.verdict == M.MARKER_UNKNOWN:
            stats["unknown"] += 1
            issues.append(VerifyIssue(
                "locate.unknown",
                f"标记 {audit.num} 的原文字段无法在源文定位（LaTeX 装饰差异等），仅告警",
                severity=WARNING))
        if audit.verdict not in (M.MARKER_EMPTY_ORIG, M.MARKER_NOOP) \
                and _normalize_compare(audit.original) == _normalize_compare(audit.correction):
            stats["manual"] += 1
            issues.append(VerifyIssue(
                "marker.manual-review",
                f"标记 {audit.num} 的「改为」与「原文」文本上无法区分，需人工确认",
                severity=MANUAL))
    return stats


_UNKNOWN_TOKEN = "\ue000U{}\ue000"
_UNKNOWN_TOKEN_RE = re.compile(r"\ue000U\d+\ue000")
"""unknown 标记字段的占位符：只让「落在该字段内」的差异被豁免。"""


def _reconstruct_with_unknown_tokens(marked_section: str, unknown_nums: set[int]) -> str:
    """重建正文：unknown 标记替换为占位符，其余标记还原为原文字段。"""
    def _repl(m: re.Match) -> str:
        num = int(m.group(1))
        if num in unknown_nums:
            return _UNKNOWN_TOKEN.format(num)
        return m.group(2)

    return M.INLINE_MARKER_CAPTURE_RE.sub(_repl, marked_section)


_MATH_HINT_RE = re.compile(r"[\\$^_{}]")
"""unknown 字段是否含公式/LaTeX 特征（只有这类差异才允许豁免）。"""

def _is_math_field(audit: M.MarkerAudit) -> bool:
    """unknown 的原/改字段是否可视为公式字段。"""
    return bool(_MATH_HINT_RE.search(audit.original or "")
                or _MATH_HINT_RE.search(audit.correction or ""))


def _paragraph_segments(compressed_para: str, exempt_nums: set[int]):
    """把段落切成 [字面量, None(占位符), 字面量, ...]；不可豁免时返回 None。

    不使用正则的「首个划分」，而是在匹配时对占位符逐个尝试、并要求它吸收的
    源文片段完整落在一个真实公式区间内——因此既不会吸收公式旁的正文，
    也允许公式内部局部标记、相邻公式各配一个占位符等合法划分。
    """
    tokens = list(_UNKNOWN_TOKEN_RE.finditer(compressed_para))
    if not tokens:
        return None
    for tok in tokens:
        num = int(re.search(r"\d+", tok.group(0)).group())
        if num not in exempt_nums:
            return None
    parts = _UNKNOWN_TOKEN_RE.split(compressed_para)
    segments: list[str | None] = []
    for i, part in enumerate(parts):
        if part:
            segments.append(part)
        if i < len(parts) - 1:
            segments.append(None)
    return segments


def _match_segments(segments: list[str | None], s: str,
                    spans: list[tuple[int, int]]) -> bool:
    """逐段迭代维护可达源文位置，不让标记数量受 Python 递归深度限制。

    非空匹配须完整落在同一个公式区间内且覆盖公式内容；可同时包含分隔符，
    以支持整条公式标记，但不能只拿分隔符冒充原文字段。
    空匹配仅允许在公式内容内部（含内容首尾的插入点），不能位于分隔符中间或
    整条公式前后；公式内的 LaTeX 间距差异仍可仅告警。
    """
    limits = []
    for a, b in spans:
        delimiter_width = 2 if s.startswith("$$", a) else 1
        limits.append((a, b, a + delimiter_width, b - delimiter_width))

    reachable = {0}
    for segment in segments:
        if segment is not None:
            reachable = {
                pos + len(segment) for pos in reachable if s.startswith(segment, pos)
            }
        else:
            ordered = sorted(reachable)
            following: set[int] = set()
            for a, b, content_start, content_end in limits:
                index = bisect_left(ordered, a)
                if index == len(ordered) or ordered[index] >= b:
                    continue
                first = ordered[index]
                # 同一公式的最小可达起点足以覆盖其余起点的非空终点。
                # 空匹配只允许落在内容范围；非空匹配必须与内容有交集。
                if content_start <= first <= content_end:
                    following.add(first)
                if first < content_end:
                    following.update(range(max(first + 1, content_start + 1), b + 1))
            reachable = following
        if not reachable:
            return False
    return len(s) in reachable


def _relaxed_match(src_c: str, segments: list[str | None],
                   src_spans: list[tuple[int, int]]) -> bool:
    """占位符吸收的每一段源文都必须落在同一个真实公式区间内。"""
    return _match_segments(segments, src_c, src_spans)


def _paras_match(src_c: str, rep_c: str, seg_info,
                 src_spans: list[tuple[int, int]]) -> str | None:
    """段落匹配：'exact' / 'relaxed'（差异仅落在真实公式区间内）/ None。"""
    if src_c == rep_c:
        return "exact"
    if seg_info and _relaxed_match(src_c, seg_info, src_spans):
        return "relaxed"
    return None


def _align_paragraphs(src_c: list[str], rep_c: list[str],
                      segments_list: list,
                      src_spans: list[list[tuple[int, int]]]):
    """按顺序做一对一 DP 对齐，返回 (pairs, unmatched_src, unmatched_rep)。

    只有单调且一一对应的匹配才算数：未匹配的源文段判缺段，未匹配的报告段判多段/重段，
    因此「只留带 unknown 的第一段」「把一段复制成两段」都会被拒绝。
    """
    n, m = len(src_c), len(rep_c)
    kind: list[list[str | None]] = [[None] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            kind[i][j] = _paras_match(src_c[i], rep_c[j], segments_list[j], src_spans[i])
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best = max(dp[i + 1][j], dp[i][j + 1])
            if kind[i][j]:
                best = max(best, 1 + dp[i + 1][j + 1])
            dp[i][j] = best
    pairs: list[tuple[int, int, str]] = []
    i = j = 0
    while i < n and j < m:
        if kind[i][j] and dp[i][j] == 1 + dp[i + 1][j + 1]:
            pairs.append((i, j, kind[i][j]))  # type: ignore[arg-type]
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    matched_src = {i for i, _, _ in pairs}
    matched_rep = {j for _, j, _ in pairs}
    return (pairs,
            [i for i in range(n) if i not in matched_src],
            [j for j in range(m) if j not in matched_rep])


def _check_integrity(text: str, marked_section: str | None, source_text: str | None,
                     issues: list[VerifyIssue]) -> dict:
    """全文逐段比对：缺段 / 重段 / 改变未标记正文 → 拒绝。

    - 空「标记原文」不再放行：源文有内容即判缺段；源文缺失/为空直接拒绝。
    - 段落按顺序一一对齐：未匹配的源文段 = 缺段，未匹配的报告段 = 多段/重段。
    - unknown 只豁免「可确定落在一个真实公式区间内」的差异：先用 scan_math_spans
      标出源文真正的 $…$ 区间，占位符吸收的源文片段必须落在同一个区间内；公式内部
      的局部字段可以豁免，但公式之间的普通正文（即使两侧都是 $）不可被吸收。
    """
    stats = {"source_paragraphs": 0, "report_paragraphs": 0,
             "missing_paragraphs": 0, "extra_paragraphs": 0, "duplicate_paragraphs": 0}
    body = marked_section if marked_section is not None else ""
    if source_text is None or not source_text.strip():
        issues.append(VerifyIssue(
            "integrity.no-source",
            "找不到单元源文，无法完成原文全文比对 → 拒绝（历史兼容请显式走 legacy）",
            severity=ERROR))
        return stats

    audits = M.audit_markers(body, source_text) if body else []
    unknown = [a for a in audits if a.verdict == M.MARKER_UNKNOWN]
    # 只有「公式字段」的 unknown 才替换为占位符；其余（含非公式 unknown）保留
    # 原文字面参与全文比对，避免因邻近公式的装饰差异丢掉普通标记的原文信息。
    exempt_nums = {a.num for a in unknown if _is_math_field(a)}
    reconstructed = _reconstruct_with_unknown_tokens(body, exempt_nums)
    src_paras = [p for p in _paragraphs(source_text) if p.strip()]
    rep_paras = [p for p in _paragraphs(reconstructed) if p.strip()]
    stats["source_paragraphs"] = len(src_paras)
    stats["report_paragraphs"] = len(rep_paras)
    src_c = [_compress(p) for p in src_paras]
    rep_c = [_compress(p) for p in rep_paras]
    src_spans = [M.scan_math_spans(p) for p in src_c]
    segments_list = [_paragraph_segments(rep_c[j], exempt_nums) for j in range(len(rep_c))]

    pairs, unmatched_src, unmatched_rep = _align_paragraphs(
        src_c, rep_c, segments_list, src_spans)
    for i in unmatched_src:
        stats["missing_paragraphs"] += 1
        issues.append(VerifyIssue(
            "integrity.missing-paragraph",
            f"源文第 {i + 1} 段在报告中缺失（缺段）",
            location=f"源文段 {i + 1}"))
    for j in unmatched_rep:
        stats["extra_paragraphs"] += 1
        preview = _UNKNOWN_TOKEN_RE.sub("【标记字段】", rep_paras[j])[:40]
        issues.append(VerifyIssue(
            "integrity.extra-paragraph",
            f"报告第 {j + 1} 段在源文中没有对应（多段/重段或未标记正文被改动）：{preview}…",
            location=f"报告段 {j + 1}"))
    for i, j, kind in pairs:
        if kind == "relaxed":
            issues.append(VerifyIssue(
                "integrity.unknown-diff",
                f"报告段 {j + 1} 与源文第 {i + 1} 段的差异仅落在一个公式字段内，保留 unknown 警告",
                severity=WARNING))
    return stats


def verify_report_text(text: str, source_text: str | None = None) -> VerifyResult:
    """对报告全文执行 §5.2 全部检查项。"""
    if not text or not text.strip():
        result = VerifyResult()
        result.issues.append(VerifyIssue("report.empty", "报告为空"))
        return result

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    result = VerifyResult()
    issues = result.issues

    head, marked_section, reasons_section = split_sections(text)
    if marked_section is not None:
        # 与解析共用同一清洗规则：剥掉「## 前置参考」与「编号：/内容：」装饰，
        # 否则会把报告自带的头字段误判成「改变未标记正文」。
        marked_section = strip_reference_preamble(marked_section)
    summary_declared = _extract_summary(text)

    _check_sections(text, issues)
    _check_syntax(text, marked_section, issues)
    result.summary = _check_severity(text, summary_declared, marked_section, issues)
    _check_reasons(marked_section, reasons_section, issues)
    field_stats = _check_marker_fields(marked_section, source_text, issues)
    integrity_stats = _check_integrity(text, marked_section, source_text, issues)
    result.marker_count = len(marker_numbers(marked_section or ""))
    result.stats = {**field_stats, **integrity_stats,
                    "markers": result.marker_count,
                    "error_count": 0, "warning_count": 0}
    result.stats["error_count"] = len(result.errors)
    result.stats["warning_count"] = len(result.warnings)
    return result


def verify_unit(unit_dir: str | Path, source_path: str | Path | None = None) -> VerifyResult:
    """读取单元目录中的 _校对报告.md 与源文，返回校验结果。"""
    from .paths import find_source_md, report_path

    from .workdir import input_path
    unit_dir = input_path(unit_dir)
    report = report_path(unit_dir)
    if not report.is_file():
        result = VerifyResult()
        result.issues.append(VerifyIssue("report.missing", f"找不到报告：{report}"))
        return result
    text = report.read_text(encoding="utf-8")
    src: str | None = None
    src_path = input_path(source_path) if source_path else find_source_md(unit_dir)
    if src_path and src_path.is_file():
        src = src_path.read_text(encoding="utf-8")
    return verify_report_text(text, src)

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

import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from . import markers as M
from .report_parse import (SEVERITY_KEYWORDS, _extract_summary, marker_numbers,
                           parse_reasons, split_sections, strip_reference_preamble)

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
    reasons = parse_reasons(reasons_section)
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


def _check_integrity(text: str, marked_section: str | None, source_text: str | None,
                     issues: list[VerifyIssue]) -> dict:
    """全文逐段比对：缺段 / 重段 / 改变未标记正文 → 拒绝。"""
    stats = {"source_paragraphs": 0, "report_paragraphs": 0,
             "missing_paragraphs": 0, "extra_paragraphs": 0, "duplicate_paragraphs": 0}
    if not marked_section:
        return stats
    if source_text is None or not source_text.strip():
        issues.append(VerifyIssue(
            "integrity.no-source",
            "找不到单元源文，无法做原文完整性比对（仅格式与标记检查生效）",
            severity=WARNING))
        return stats

    reconstructed = M.split_marked_body(marked_section)
    src_paras = [p for p in _paragraphs(source_text) if p.strip()]
    rep_paras = [p for p in _paragraphs(reconstructed) if p.strip()]
    stats["source_paragraphs"] = len(src_paras)
    stats["report_paragraphs"] = len(rep_paras)
    src_c = [_compress(p) for p in src_paras]
    rep_c = [_compress(p) for p in rep_paras]

    audits = M.audit_markers(marked_section, source_text)
    unknown_nums = {a.num for a in audits if a.verdict == M.MARKER_UNKNOWN}

    sm = SequenceMatcher(None, src_c, rep_c, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            for k in range(i1, i2):
                stats["missing_paragraphs"] += 1
                issues.append(VerifyIssue(
                    "integrity.missing-paragraph",
                    f"源文第 {k + 1} 段在报告中缺失（缺段）",
                    location=f"源文段 {k + 1}"))
        elif tag == "insert":
            for k in range(j1, j2):
                stats["extra_paragraphs"] += 1
                issues.append(VerifyIssue(
                    "integrity.extra-paragraph",
                    f"报告多出源文没有的段落（改变未标记正文或重段）：{rep_paras[k][:40]}…",
                    location=f"报告段 {k + 1}"))
        else:
            # replace：若涉及无法定位的标记字段，降级为 warning
            nums_in_range = set(marker_numbers(marked_section))  # 全文兜底
            del nums_in_range
            if unknown_nums:
                issues.append(VerifyIssue(
                    "integrity.unknown-diff",
                    "源文与重建正文存在差异，但涉及无法定位的标记字段，保留 unknown 警告",
                    severity=WARNING))
            else:
                stats["missing_paragraphs"] += (i2 - i1)
                stats["extra_paragraphs"] += (j2 - j1)
                issues.append(VerifyIssue(
                    "integrity.changed",
                    f"正文与源文不一致（源文段 {i1 + 1}-{i2} ↔ 报告段 {j1 + 1}-{j2}）："
                    "未标记正文不得改动"))

    # 重段：同一段在报告中出现次数多于源文
    rep_counts = Counter(rep_c)
    src_counts = Counter(src_c)
    for para, count in rep_counts.items():
        if count > 1 and src_counts.get(para, 0) < count:
            stats["duplicate_paragraphs"] += count - max(src_counts.get(para, 0), 1) + 1
            issues.append(VerifyIssue(
                "integrity.duplicate-paragraph",
                f"段落重复 {count} 次（源文仅 {src_counts.get(para, 0)} 次）：{para[:40]}…"))
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

    unit_dir = Path(unit_dir)
    report = report_path(unit_dir)
    if not report.is_file():
        result = VerifyResult()
        result.issues.append(VerifyIssue("report.missing", f"找不到报告：{report}"))
        return result
    text = report.read_text(encoding="utf-8")
    src: str | None = None
    src_path = Path(source_path) if source_path else find_source_md(unit_dir)
    if src_path and src_path.is_file():
        src = src_path.read_text(encoding="utf-8")
    return verify_report_text(text, src)

"""确定性重建校对报告正文。

修复器只负责从单元源文重建标记原文段，不判断校对意见本身是否正确，
也不替代 verify-report。
"""
from __future__ import annotations

import difflib
import os
import re
import tempfile
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import markers
from .errors import NotFoundError
from .report_parse import strip_reference_preamble
from .verify import verify_report_text, verify_unit

_MARKED_HEADING_RE = re.compile(r"(?m)^[ \t]*###\s*标记原文[^\n]*(?:\n|$)")
_REASON_HEADING_RE = re.compile(r"(?m)^[ \t]*###\s*修改原因[^\n]*(?:\n|$)")
_ALLOWED_REPAIR_ERRORS = {
    "integrity.missing-paragraph",
    "integrity.extra-paragraph",
    "integrity.duplicate-paragraph",
    "integrity.changed",
}


@dataclass
class RepairResult:
    """修复预览或应用结果。"""

    ok: bool
    text: str | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    diff: str = ""
    verified: bool = False
    image_result: dict[str, Any] | None = None

    def to_dict(self, *, include_candidate: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "verified": self.verified,
            "fields": self.fields,
            "diagnostics": self.diagnostics,
            "diff": self.diff,
        }
        if self.image_result is not None:
            payload["images"] = self.image_result
        if include_candidate and self.text is not None:
            payload["candidate"] = self.text
        return payload


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _snippet(text: str, start: int, end: int, radius: int = 40) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].replace("\n", "\\n")


def _diagnostic(code: str, message: str, **details: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message}
    result.update(details)
    return result


def _report_structure(report_text: str) -> tuple[str, str, str] | tuple[None, list[dict[str, Any]], None]:
    text = _normalize_newlines(report_text)
    marked = list(_MARKED_HEADING_RE.finditer(text))
    reasons = list(_REASON_HEADING_RE.finditer(text))
    diagnostics: list[dict[str, Any]] = []
    if len(marked) != 1:
        diagnostics.append(_diagnostic(
            "report.marked-section",
            f"报告必须恰好有一个 ### 标记原文 段落，实际 {len(marked)} 个",
        ))
    if len(reasons) != 1:
        diagnostics.append(_diagnostic(
            "report.reasons-section",
            f"报告必须恰好有一个 ### 修改原因 段落，实际 {len(reasons)} 个",
        ))
    if diagnostics:
        return None, diagnostics, None
    if marked[0].start() >= reasons[0].start():
        return None, [_diagnostic("report.section-order", "### 标记原文 必须位于 ### 修改原因 之前")], None
    raw_marked = text[marked[0].end():reasons[0].start()]
    return text, raw_marked, text[reasons[0].start():]


def _report_issue_diagnostics(report_text: str, source_text: str) -> list[dict[str, Any]]:
    verdict = verify_report_text(report_text, source_text)
    errors = [issue for issue in verdict.errors if issue.code not in _ALLOWED_REPAIR_ERRORS]
    if not errors:
        return []
    return [
        _diagnostic(
            "report.verify-failed",
            "报告存在不能由正文重建解决的契约错误",
            issues=[issue.to_dict() for issue in errors],
        ),
        *(_diagnostic(f"report.{issue.code}", issue.message, location=issue.location) for issue in errors),
    ]


def _locate_fields(source_text: str, marked_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    matches = list(markers.INLINE_MARKER_CAPTURE_RE.finditer(marked_text))
    diagnostics: list[dict[str, Any]] = []
    fields: list[dict[str, Any]] = []
    seen_numbers: set[int] = set()
    for match in matches:
        number = int(match.group(1))
        original = match.group(2)
        marker_text = match.group(0)
        field: dict[str, Any] = {
            "number": number,
            "original": original,
            "marker": marker_text,
            "source_positions": [],
        }
        if number in seen_numbers:
            diagnostics.append(_diagnostic(
                "repair.duplicate-number",
                f"标记编号 {number} 重复出现",
                number=number,
                marker=marker_text,
            ))
        seen_numbers.add(number)
        if not original:
            diagnostics.append(_diagnostic(
                "repair.empty-original",
                f"标记 {number} 的原文字段为空",
                number=number,
                marker=marker_text,
            ))
            fields.append(field)
            continue
        positions: list[int] = []
        cursor = 0
        while True:
            position = source_text.find(original, cursor)
            if position < 0:
                break
            positions.append(position)
            cursor = position + 1
        field["source_positions"] = positions
        if not positions:
            diagnostics.append(_diagnostic(
                "repair.original-not-found",
                f"标记 {number} 的原文字段无法在源文中找到",
                number=number,
                original=original,
                marker=marker_text,
                source_snippet=original[:120],
                candidate_positions=[],
            ))
        elif len(positions) > 1:
            diagnostics.append(_diagnostic(
                "repair.original-not-unique",
                f"标记 {number} 的原文字段在源文中命中 {len(positions)} 处，拒绝猜测",
                number=number,
                original=original,
                marker=marker_text,
                candidate_positions=positions,
                source_snippets=[_snippet(source_text, pos, pos + len(original)) for pos in positions],
            ))
        else:
            start = positions[0]
            end = start + len(original)
            field.update({
                "source_start": start,
                "source_end": end,
                "source_line": _line_number(source_text, start),
                "source_snippet": _snippet(source_text, start, end),
            })
        fields.append(field)

    previous_start = -1
    previous_end = -1
    for field in fields:
        if "source_start" not in field:
            continue
        start = field["source_start"]
        end = field["source_end"]
        if start < previous_start:
            diagnostics.append(_diagnostic(
                "repair.marker-order",
                f"标记 {field['number']} 的源文位置早于前一个标记",
                number=field["number"],
                source_start=start,
                previous_start=previous_start,
            ))
        elif start < previous_end:
            diagnostics.append(_diagnostic(
                "repair.marker-overlap",
                f"标记 {field['number']} 与前一个标记的源文区间重叠",
                number=field["number"],
                source_start=start,
                source_end=end,
                previous_end=previous_end,
            ))
        previous_start = start
        previous_end = end
    return fields, diagnostics


def _insert_markers(source_text: str, fields: list[dict[str, Any]], marked_text: str) -> str:
    matches = list(markers.INLINE_MARKER_CAPTURE_RE.finditer(marked_text))
    chunks: list[str] = []
    cursor = 0
    for match, field in zip(matches, fields):
        if "source_start" not in field:
            continue
        start = field["source_start"]
        end = field["source_end"]
        chunks.append(source_text[cursor:start])
        chunks.append(match.group(0))
        cursor = end
    chunks.append(source_text[cursor:])
    return "".join(chunks)


def _build_diff(before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile="_校对报告.md",
        tofile="_校对报告.md (修复候选)",
    ))


def build_repair_candidate(source_text: str, report_text: str) -> RepairResult:
    """纯函数：构造候选报告，不读取或写入文件。"""
    from .report_suggestions import REPORT_V2_PREFIX

    if report_text.startswith(REPORT_V2_PREFIX):
        return RepairResult(False, diagnostics=[_diagnostic(
            "repair.v2-not-supported", "schema v2报告由结构化建议重新提交，不走旧Markdown修复器")])
    source = _normalize_newlines(source_text)
    report = _normalize_newlines(report_text)
    if not source.strip():
        return RepairResult(False, diagnostics=[_diagnostic("repair.source-missing", "源文为空，拒绝自动修复")])
    structure = _report_structure(report)
    if structure[0] is None:
        return RepairResult(False, diagnostics=structure[1])
    normalized_report, raw_marked, _ = structure
    assert normalized_report is not None and raw_marked is not None
    diagnostics = _report_issue_diagnostics(normalized_report, source)
    if diagnostics:
        return RepairResult(False, diagnostics=diagnostics)
    marked_text = strip_reference_preamble(raw_marked)
    fields, location_diagnostics = _locate_fields(source, marked_text)
    if location_diagnostics:
        return RepairResult(False, diagnostics=location_diagnostics, fields=fields)
    canonical_body = _insert_markers(source, fields, marked_text)
    if not canonical_body.endswith("\n"):
        canonical_body += "\n"
    marked_match = _MARKED_HEADING_RE.search(normalized_report)
    reason_match = _REASON_HEADING_RE.search(normalized_report)
    assert marked_match is not None and reason_match is not None
    candidate = normalized_report[:marked_match.end()] + canonical_body + normalized_report[reason_match.start():]
    post_verdict = verify_report_text(candidate, source)
    if not post_verdict.ok:
        return RepairResult(
            False,
            diagnostics=[_diagnostic(
                "report.verify-failed",
                "重建候选未通过完整文本闸门",
                issues=[issue.to_dict() for issue in post_verdict.errors],
            )],
            fields=fields,
        )
    return RepairResult(True, text=candidate, fields=fields, diff=_build_diff(normalized_report, candidate))


def _image_diagnostics(image_result: dict[str, Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for problem in image_result.get("errors", []):
        code = problem.get("code", "unknown")
        diagnostics.append(_diagnostic(
            f"images.{code}",
            problem.get("message", f"图片检查失败：{code}"),
            reference_index=problem.get("reference_index"),
            line=problem.get("line"),
        ))
    return diagnostics


def _atomic_write(path: Path, content: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def repair_unit_report(
    unit_dir: str | Path,
    *,
    source_path: str | Path | None = None,
    apply: bool = False,
    work_root: str | Path | None = None,
) -> RepairResult:
    """预览或原子应用单元报告修复；应用失败时恢复原报告。"""
    from .material import find_material
    from .paths import find_source_md, report_path
    from .workdir import ensure_inside, input_path, workspace_scope
    from .inspect_images import inspect_unit_images

    scope = workspace_scope(work_root) if work_root is not None else nullcontext()
    with scope:
        unit = input_path(unit_dir)
        report = report_path(unit)
        if not report.is_file():
            raise NotFoundError(f"找不到报告：{report}")
        src_path = input_path(source_path) if source_path is not None else find_source_md(unit)
        if src_path is None or not src_path.is_file():
            raise NotFoundError(f"找不到单元源文：{unit}")
        report_bytes = report.read_bytes()
        report_text = report_bytes.decode("utf-8")
        source_text = src_path.read_text(encoding="utf-8")
        result = build_repair_candidate(source_text, report_text)
        if not result.ok:
            return result

        image_result = inspect_unit_images(
            unit,
            source_path=src_path,
            allow_legacy_transparent=find_material(unit) is None,
        )
        result.image_result = image_result
        image_diagnostics = _image_diagnostics(image_result)
        if image_diagnostics:
            result.ok = False
            result.diagnostics.extend(image_diagnostics)
            return result
        if not apply:
            return result

        target = ensure_inside(report)
        original_bytes = report_bytes
        try:
            _atomic_write(target, result.text.encode("utf-8"))
            post = verify_unit(unit, source_path=src_path)
            if not post.ok:
                _atomic_write(target, original_bytes)
                result.ok = False
                result.text = None
                result.diagnostics.append(_diagnostic(
                    "report.verify-after-apply",
                    "原子替换后完整 verify-unit 未通过，已恢复原报告",
                    issues=[issue.to_dict() for issue in post.errors],
                ))
                return result
        except Exception:
            if target.is_file() and target.read_bytes() != original_bytes:
                _atomic_write(target, original_bytes)
            raise
        result.verified = True
        return result

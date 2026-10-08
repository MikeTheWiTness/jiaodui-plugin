"""`_校对失败.md` 的结构校验（R-H11）。

该文件由 agent 写（Python 侧没有生产者），格式写在 failure-modes.md §六：
首行失败原因 + 最后一次 `verify-report` 完整输出 + 产物摘要。这里只对**可机检**的
部分做检查，结果作为 status 的告警——**它不是闸门**：格式不全不改变成功/失败判定，
更不会让已通过的单元回退。
"""
from __future__ import annotations

from pathlib import Path

from . import paths

# verify 输出的可识别标志（JSON 形态、命令名，或明确写了未执行）
VERIFY_OUTPUT_MARKERS = ('"ok"', "'ok'", "verify-report", "verify_report", "未执行")
# 产物摘要的三个关键词，至少命中两个才算写了摘要
SUMMARY_KEYWORDS = ("标记", "严重度", "错误")


def validate_failure_note(unit_dir: str | Path) -> list[dict]:
    """返回结构问题列表；结构完整或没有失败记录时返回空列表。

    code 与 verify 的检查项风格一致，便于 agent 直接按码消解。
    """
    path = paths.fail_path(unit_dir)
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [{"code": "failure_note.unreadable",
                 "message": f"{paths.FAIL_NAME} 无法读取：{exc}"}]

    problems: list[dict] = []
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first:
        problems.append({"code": "failure_note.empty",
                         "message": f"{paths.FAIL_NAME} 为空：至少需要首行失败原因"})
        return problems
    if not any(marker in text for marker in VERIFY_OUTPUT_MARKERS):
        problems.append({
            "code": "failure_note.no-verify-output",
            "message": f"{paths.FAIL_NAME} 未见 verify-report 输出："
                       "需贴最后一次完整输出；未执行时明确写「未执行」"})
    if sum(1 for keyword in SUMMARY_KEYWORDS if keyword in text) < 2:
        problems.append({
            "code": "failure_note.no-summary",
            "message": f"{paths.FAIL_NAME} 未见产物摘要：需写明标记数 / 严重度 / 错误数"})
    return problems

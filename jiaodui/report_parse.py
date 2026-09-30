"""校对报告文本 → _校对数据.json 的确定性解析。

移植自旧仓 core/parsing.py（HEAD 1c45243），去掉 review_mode / UI 耦合，
保留 055 的解析保真约束：
- 严重度总结行只在首个三级标题前的头部区域识别，识别不到记「未声明」而非「无问题」
- 修改原因编号行首锚定（正文行首数字不误判）
- CRLF 统一为 LF
"""
from __future__ import annotations

import json
import os
import re
import traceback

from .log import log
from .markers import INLINE_MARKER_CAPTURE_RE, INLINE_MARKER_DETECT_RE
from .workdir import ensure_inside

# 严重度总结词；未识别到任何一条时记为 UNSTATED，不冒充「无问题」
SEVERITY_KEYWORDS = ("严重错误", "一般问题", "轻微问题", "无问题")
UNSTATED = "未声明"

# 总结行区域：第一个三级及以上标题之前的所有非空行
_SUMMARY_HEADING_RE = re.compile(r"^#{3,}\s")
_SUMMARY_DECOR_RE = re.compile(r"^[\s#*>*>—•]+")
_SUMMARY_LABEL_RE = re.compile(r"^(?:总结行|总结)\s*[\*#]*\s*[:：]?\s*")

# 修改原因条目必须行首锚定：正文里的数字（如 $n\approx1.22$）不是编号。
# 编号分隔符限定为 点/顿号/右括号：纯空格分隔（"1 原因"）会让正文行首数字有机可乘
# 原因正文允许续行；裸核验说明是契约允许的非编号附注，不属于上一条原因。
# 编号后必须在同一行有非空正文，不能把下一条或附注充作空原因。
_REASON_END = (
    r"(?=\n[ \t]*\d+(?:[ \t]*[-–][ \t]*\d+)?[ \t]*[\.\)、]"
    r"|\n[ \t]*[①-⑳]|\n[ \t]*\n"
    r"|\n[ \t]*(?:\*\*)?核验说明(?:\*\*)?[ \t]*[：:]|\Z)"
)
_REASON_ASCII_RE = re.compile(
    r"(?m)^[ \t]*(\d+)(?:[ \t]*[-–][ \t]*(\d+))?[ \t]*[\.\)、][ \t]*"
    r"(?=\S)([\s\S]+?)" + _REASON_END
)
_REASON_CIRCLED_RE = re.compile(
    r"(?m)^[ \t]*(?>([①-⑳](?:[ \t]*[-–][ \t]*([①-⑳]))?)[ \t]*[\.\)、]?[ \t]*)"
    r"(?=\S)([\s\S]+?)" + _REASON_END
)


def _extract_summary(text: str) -> str:
    """从报告头部提取严重度总结词，识别不到时返回空串。"""
    candidates = []
    for raw in text.splitlines():
        s = raw.strip()
        if _SUMMARY_HEADING_RE.match(s):
            break
        if not s:
            continue
        candidates.append(s)
    for line in candidates:
        body = _SUMMARY_DECOR_RE.sub("", line).strip().rstrip("*# \t")
        body = _SUMMARY_LABEL_RE.sub("", body).strip()
        for kw in SEVERITY_KEYWORDS:
            if body.startswith(kw):
                return kw
    return ""


def _circle_to_int(ch: str) -> int | None:
    code = ord(ch)
    if 0x2460 <= code <= 0x2473:
        return code - 0x2460 + 1
    return None


def _parse_marker_num(s: str) -> int:
    n = _circle_to_int(s[0])
    if n is not None:
        return n
    return int(s)


def split_sections(text: str) -> tuple[str, str | None, str | None]:
    """把报告切成 (头部, 标记原文段, 修改原因段)。

    标记段以 「### 标记原文」标题开始（标题行可有附加说明），到「### 修改原因」截止；
    原因段从「### 修改原因」标题的下一行开始，到下一个 ### 或 --- 或文末截止。
    找不到对应标题时返回 None。
    """
    text = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    reason_m = re.search(r"\n###\s*修改原因[^\n]*\n", text)
    if not reason_m:
        marker_only = re.search(r"^###\s*标记原文[^\n]*\n(.*)", text, re.MULTILINE | re.DOTALL)
        head = text[:marker_only.start()] if marker_only else text
        return head, (marker_only.group(1) if marker_only else None), None
    head_and_marker = text[:reason_m.start()]
    reasons_section = text[reason_m.end():]
    marker_pos = re.search(r"^###\s*标记原文[^\n]*\n?", head_and_marker, re.MULTILINE)
    if marker_pos:
        head = head_and_marker[:marker_pos.start()]
        marked_section = head_and_marker[marker_pos.end():]
    else:
        head = ""
        marked_section = head_and_marker
    return head, marked_section, reasons_section


def _strip_reference_preamble(marked_section: str) -> str:
    """剥离前置参考段落（## 前置参考 → 权威原文 → 字面差异 → ⚠️ → ---）。"""
    marked_section = re.sub(
        r"##\s*前置参考[^\n]*\n.*?\n---\n", "", marked_section, count=1, flags=re.DOTALL
    )
    marked_section = re.sub(r"^##\s*前置参考[^\n]*\n", "", marked_section, flags=re.MULTILINE)
    marked_section = re.sub(r"^###\s*(?:权威原文|字面差异)[^\n]*\n", "", marked_section, flags=re.MULTILINE)
    marked_section = re.sub(r"^⚠️[^\n]*\n?", "", marked_section, flags=re.MULTILINE)
    marked_section = marked_section.strip()
    marked_section = re.sub(r"^编号：.+\n?", "", marked_section, flags=re.MULTILINE)
    marked_section = re.sub(r"^内容：\n?", "", marked_section, flags=re.MULTILINE)
    return marked_section


def strip_reference_preamble(marked_section: str) -> str:
    """剥离前置参考与「编号：/内容：」装饰，得到纯正文（与解析共用同一规则）。"""
    return _strip_reference_preamble(marked_section)


def _trim_reasons_section(reasons_section: str) -> str:
    trimmed = re.split(r"\n---\n|\n##\s*📋", reasons_section)[0]
    return re.split(r"\n###\s", trimmed)[0].rstrip()


def parse_reason_entries(reasons_section: str | None) -> list[tuple[int, str]]:
    """解析修改原因段为 [(编号, 原因)]，保留重复与区间展开，供一一对应检查。

    区间（1-2 / ①-③）按每个编号各产生一条；重复编号不会被合并，调用方据此判重。
    """
    if not reasons_section:
        return []
    reasons_section = _trim_reasons_section(reasons_section.replace("\r\n", "\n").replace("\r", "\n"))
    entries: list[tuple[int, str]] = []
    # 两类编号各自独立解析；同时出现时合并，交由调用方统一判重/查孤立。
    # 不允许「出现圈号就整段只按圈号解析」，否则阿拉伯数字条目被静默丢弃。
    circled_present = bool(re.search(r"(?:^|\n)[ \t]*[①-⑳]", reasons_section))
    ascii_present = bool(re.search(
        r"(?:^|\n)[ \t]*\d+(?:\s*[-–]\s*\d+)?[ \t]*[\.\)、]", reasons_section))
    if circled_present:
        for rm in _REASON_CIRCLED_RE.finditer(reasons_section):
            sn = _circle_to_int(rm.group(1)[0])
            en = _circle_to_int(rm.group(2)) if rm.group(2) else sn
            rt = rm.group(3).strip()
            if sn is None or not rt:
                continue
            lo, hi = sorted((sn, en if en is not None else sn))
            entries.extend((n, rt) for n in range(lo, hi + 1))
    if ascii_present:
        for rm in _REASON_ASCII_RE.finditer(reasons_section):
            sn = int(rm.group(1))
            en = int(rm.group(2)) if rm.group(2) else sn
            rt = rm.group(3).strip()
            if not rt:
                continue
            lo, hi = sorted((sn, en))
            entries.extend((n, rt) for n in range(lo, hi + 1))
    return entries


def parse_reasons(reasons_section: str | None) -> dict[int, str]:
    """解析修改原因段为 {编号: 原因}，支持 1-2 / ①-③ 区间写法（重复取最后一条）。"""
    reasons: dict[int, str] = {}
    for n, rt in parse_reason_entries(reasons_section):
        reasons[n] = rt
    return reasons


def marker_numbers(marked_section: str) -> list[int]:
    """按出现顺序返回标记编号（含重复，供重号检查）。"""
    return [int(m.group(1)) for m in INLINE_MARKER_CAPTURE_RE.finditer(marked_section)]


def _parse_inline_format(text: str, summary: str) -> dict | None:
    head, marked_section, reasons_section = split_sections(text)
    if reasons_section is None:
        return None
    marked_section = _strip_reference_preamble(marked_section or "")
    reasons = parse_reasons(reasons_section)

    corrections = []
    seen_nums = set()

    def _extract(marker):
        num = _parse_marker_num(marker.group(1))
        orig = marker.group(2)
        corr = marker.group(3).strip() if marker.group(3) else ""
        if num not in seen_nums:
            seen_nums.add(num)
            corrections.append({
                "num": num,
                "type": "text",
                "original": orig,
                "correction": corr,
                "reason": reasons.get(num, ""),
            })
        return ""

    _clean_marked = INLINE_MARKER_CAPTURE_RE.sub(_extract, marked_section)
    corrections.sort(key=lambda x: x.get("num", 0))

    if not summary and not corrections:
        return None
    return {
        "corrections": corrections,
        "summary": summary,
        "marked_text": marked_section.replace("\n", "\\n"),
    }


def _parse_old_format(text: str, summary: str) -> dict | None:
    blocks = re.split(r"\n?(?:###+\s*修改\s*\d+)\s*\n", text)
    corrections = []
    for block in blocks[1:]:
        corr = {}
        cur_field = None
        cur_val = []
        for line in block.strip().split("\n"):
            s = line.strip()
            matched = False
            for prefix, field in [("- **类型**:", "type"), ("- **原文**:", "original"),
                                   ("- **改为**:", "correction"), ("- **原因**:", "reason"),
                                   ("- **位置**:", "location")]:
                if s.startswith(prefix):
                    if cur_field and cur_val:
                        v = "\n".join(cur_val)
                        if cur_field in ("original", "correction", "location"):
                            m = re.search(r"``(.+?)``", v) or re.search(r"`([^`]+)`", v)
                            corr[cur_field] = m.group(1) if m else v
                        else:
                            corr[cur_field] = v
                    cur_field = field
                    cur_val = [s.split(":", 1)[1].strip() if ":" in s else ""]
                    matched = True
                    break
            if not matched and cur_field:
                cur_val.append(s)
        if cur_field and cur_val:
            v = "\n".join(cur_val)
            if cur_field in ("original", "correction", "location"):
                m = re.search(r"``(.+?)``", v) or re.search(r"`([^`]+)`", v)
                corr[cur_field] = m.group(1) if m else v
            else:
                corr[cur_field] = v
        if corr.get("original") or corr.get("location"):
            corr.setdefault("type", "text")
            corr.setdefault("correction", "")
            corr.setdefault("reason", "")
            corrections.append(corr)
    if not summary and not corrections:
        return None
    return {"corrections": corrections, "summary": summary}


def parse_proofread_md(text: str):
    """解析校对报告为 {corrections, summary, marked_text}；无法解析返回 None。"""
    if not text or not text.strip():
        return None
    text = text.strip().replace("\r\n", "\n").replace("\r", "\n")
    declared = _extract_summary(text)

    has_markers = bool(INLINE_MARKER_DETECT_RE.search(text))
    has_reasons = bool(re.search(r"###\s*修改原因", text))
    if declared == "无问题" and not has_markers and not has_reasons:
        return {"corrections": [], "summary": "无问题", "marked_text": ""}

    result = None
    if has_markers and ("### 标记原文" in text or has_reasons):
        result = _parse_inline_format(text, declared)
    if result is None:
        result = _parse_old_format(text, declared)
    if result is None:
        return None

    if not result["summary"]:
        log("   ⚠️ 校对报告未声明严重度（头部无总结行），"
            f"_校对数据.json 的 summary 记为「{UNSTATED}」")
        result["summary"] = UNSTATED
    elif result["summary"] == "无问题" and result["corrections"]:
        log(f"   ⚠️ 校对报告声明「无问题」却含 {len(result['corrections'])} 条修正标记，"
            f"自相矛盾，_校对数据.json 的 summary 记为「{UNSTATED}」")
        result["summary"] = UNSTATED
    return result


def extract_json(text: str):
    return parse_proofread_md(text)


def save_proofread_json(res: str, q_dir: str, tool_calls: list | None = None) -> bool:
    """把报告解析结果落盘为 <q_dir>/_校对数据.json。"""
    json_path = ensure_inside(os.path.join(q_dir, "_校对数据.json"))
    data = extract_json(res)
    if data is None:
        return False
    if tool_calls:
        data["tool_calls"] = tool_calls
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        log(f"   ⚠️ 保存 _校对数据.json 失败 ({json_path}):\n{traceback.format_exc()}")
        return False

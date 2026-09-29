"""校对报告 → Word 批注版（docx）生成器。

将试卷/讲义目录下各题（单元N/第N题/板块N）的 `_校对报告.md` 合并为单个 docx：
- `【N|原|改】` 标记 → Word 批注（改后文字 + 修改原因）
- 图片合并（重命名防冲突）并嵌入；外链/缺失引用转为文字说明
- 每题一级标题 + 分页符；「无问题」单元同样列入报告并标注
- 含批注标记但缺分段的单元（批注可能丢失）跳过并警示

依赖 pandoc（`-f markdown-implicit_figures` 防止图片题注污染）。
"""
from __future__ import annotations

import itertools
import os
from collections import Counter
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import UTC
from pathlib import Path
from xml.sax.saxutils import escape

from dataclasses import dataclass, field

from .log import log
from .markers import (INLINE_MARKER_CAPTURE_RE, MARKER_NOOP,
                      MARKER_RESTORE_NEW, audit_markers)
from .markers import scan_math_spans as _scan_math_spans
from .report_parse import parse_reasons

# \| 是 LaTeX 转义竖线（\left\|…\right\|），整体属于原文字段，不得当分隔符
_PAT = INLINE_MARKER_CAPTURE_RE
_PAGE_BREAK = '```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```'

_MARKER_SLOT_RE = re.compile(r"【MARKSLOT(\d+)Z】")
"""标记占位符：正文 LaTeX 预处理期间代替整个内联标记（不含 $ 与反斜杠）。"""

_NS = ('xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
       'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
       'xmlns:o="urn:schemas-microsoft-com:office:office" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
       'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
       'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
       'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
       'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
       'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
       'mc:Ignorable="w14"')


def find_pandoc() -> str | None:
    """定位 pandoc：优先 jiaodui.convert，其次 JIAODUI_PANDOC / PATH / 常见路径。

    返回可执行文件的真实路径；找不到返回 None（调用方据此跳过并给出环境提示）。
    本函数是旧仓 core/pandoc_utils.find_pandoc 在新仓的确定性替身，最终以
    jiaodui.convert 的实现为准；该模块尚未提供时用本地探测兜底。
    """
    candidates: list[str] = []
    env = os.environ.get("JIAODUI_PANDOC")
    if env:
        candidates.append(env)
    try:
        from .convert import find_pandoc as _convert_find_pandoc  # type: ignore
        found = _convert_find_pandoc()
        if found:
            candidates.append(found)
    except Exception:
        pass
    which = shutil.which("pandoc")
    if which:
        candidates.append(which)
    candidates.extend(["/usr/local/bin/pandoc", "/opt/homebrew/bin/pandoc", "/usr/bin/pandoc"])
    for cand in candidates:
        if not cand:
            continue
        if os.path.isfile(cand):
            return cand
        resolved = shutil.which(cand)
        if resolved:
            return resolved
    return None


def latex_to_png(latex_body, out_path, fontsize: float = 14, dpi: int = 200) -> bool:
    """惰性转发到 jiaodui.formula_render（matplotlib 缺失时返回 False）。"""
    from .formula_render import latex_to_png as _render
    return _render(latex_body, out_path, fontsize, dpi)


@dataclass
class DocxBuildResult:
    """build_docx 的确定性复核结果（PRD §5.1 / §6.4 硬门槛）。

    - marker_count：报告中【…】错误标记总数
    - anchor_count：生成 docx 内实际 commentRangeStart 锚点数（不含标题批注）
    - formula_fallback_count：公式内标记的可见高亮+修改意见兜底数
    - missing_count：marker_count - anchor_count - formula_fallback_count
    - heading_comment_count：无问题单元的标题批注数（单列，不参与缺失计算）
    - units：每单元 {unit, markers, anchors, fallbacks, missing, heading_comment}
    """

    out_path: str | None
    marker_count: int = 0
    anchor_count: int = 0
    formula_fallback_count: int = 0
    missing_count: int = 0
    heading_comment_count: int = 0
    units: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    excluded_units: list[dict] = field(default_factory=list)
    """未通过 verify-report、被排除出 Word 交付的单元（{unit, reason}）。"""
    anchor_structure_ok: bool = False
    """生成后复核：commentRangeStart/End/Reference 与 comments.xml 数量是否一致。"""

    @property
    def ok(self) -> bool:
        """缺失为 0、产物存在、锚点结构完整、且没有单元被排除，才算通过。"""
        return (self.missing_count == 0 and bool(self.out_path)
                and os.path.exists(self.out_path)
                and self.anchor_structure_ok
                and not self.excluded_units)


def _report_marker_counts(questions) -> dict:
    """按单元统计报告「标记原文」段里的内联标记总数（jiaodui.markers 单一源）。"""
    counts = {}
    for qid, part in questions:
        marker_idx = part.find("### 标记原文")
        reason_idx = part.find("### 修改原因")
        has_sections = marker_idx != -1 and reason_idx != -1 and reason_idx >= marker_idx
        mark_seg = part[marker_idx:reason_idx] if has_sections else part
        counts[qid] = len(_PAT.findall(mark_seg))
    return counts


def _is_included_unit(part: str) -> bool:
    """与 generate_combined_docx 同口径：含标记但缺分段的单元被跳过。"""
    marker_idx = part.find("### 标记原文")
    reason_idx = part.find("### 修改原因")
    has_sections = marker_idx != -1 and reason_idx != -1 and reason_idx >= marker_idx
    mark_seg = part[marker_idx:reason_idx] if has_sections else part
    if _PAT.search(mark_seg) and not has_sections:
        return False
    return True


def _split_unit_sections(doc_xml: str) -> list[str]:
    """按 Heading1 段落把 document.xml 切成各单元正文段（不含文首前导）。"""
    chunks = re.split(r'(?=<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1")', doc_xml)
    return chunks[1:] if chunks else []


def _audit_generated_docx(out_path: str | None, included: list[str],
                          sections: list[str]) -> tuple[dict, set, list[str]]:
    """生成后复核：解析 comments.xml 与正文 commentRangeStart，统计实际锚点。

    Returns:
        (每单元实际计数, 实际保留的批注 id 集合, 告警列表)。
    """
    warnings: list[str] = []
    comment_ids: set[str] = set()
    if out_path and os.path.exists(out_path):
        try:
            with zipfile.ZipFile(out_path) as z:
                if "word/comments.xml" in z.namelist():
                    comments_xml = z.read("word/comments.xml").decode("utf-8")
                    comment_ids = set(re.findall(r'<w:comment w:id="(\d+)"', comments_xml))
        except Exception as e:
            warnings.append(f"复核 docx 失败: {e}")

    if len(sections) != len(included):
        warnings.append(
            f"docx 单元分段数({len(sections)})与应生成单元数({len(included)})不一致，"
            "缺失判定可能偏保守")

    actual: dict[str, dict] = {}
    for idx, qid in enumerate(included):
        sec = sections[idx] if idx < len(sections) else ""
        heading_end = sec.find("</w:p>")
        heading_part = sec[:heading_end + 6] if heading_end != -1 else ""
        heading_starts = set(re.findall(r'<w:commentRangeStart w:id="(\d+)"', heading_part))
        sec_starts = set(re.findall(r'<w:commentRangeStart w:id="(\d+)"', sec))
        actual_heading = 1 if (heading_starts & comment_ids) else 0
        marker_ids = {gid for gid in sec_starts if gid in comment_ids}
        marker_ids -= heading_starts
        actual[qid] = {
            "anchors": len(marker_ids),
            "fallbacks": sec.count("（修改意见："),
            "heading_comment": actual_heading,
        }
    return actual, comment_ids, warnings


def _check_anchor_pairing(doc_xml: str, comment_ids: set[str]) -> tuple[bool, list[str]]:
    """逐 id 校验批注锚点三段与 comments.xml 是否一一配对。

    数量一致只是附加检查：本函数要求每个 comment id 恰好有 1 个
    commentRangeStart / commentRangeEnd / commentReference，且三段顺序正确、
    无重复、与 comments.xml 的 id 集合完全一致。
    """
    problems: list[str] = []

    def _ids(pattern: str) -> list[str]:
        return re.findall(pattern, doc_xml)

    starts = _ids(r'<w:commentRangeStart w:id="(\d+)"')
    ends = _ids(r'<w:commentRangeEnd w:id="(\d+)"')
    refs = _ids(r'<w:commentReference w:id="(\d+)"')
    c_starts, c_ends, c_refs = Counter(starts), Counter(ends), Counter(refs)

    for label, counter in (("commentRangeStart", c_starts), ("commentRangeEnd", c_ends),
                           ("commentReference", c_refs)):
        dup = sorted(k for k, v in counter.items() if v > 1)
        if dup:
            problems.append(f"{label} 出现重复 id：{dup}")
        miss = sorted(comment_ids - set(counter))
        if miss:
            problems.append(f"{label} 缺少 id：{miss}")
        extra = sorted(set(counter) - comment_ids)
        if extra:
            problems.append(f"{label} 出现没有对应批注的额外 id：{extra}")
    for cid in sorted(comment_ids):
        if c_starts.get(cid, 0) == 1 and c_ends.get(cid, 0) == 1 and c_refs.get(cid, 0) == 1:
            ps = doc_xml.find(f'<w:commentRangeStart w:id="{cid}"')
            pe = doc_xml.find(f'<w:commentRangeEnd w:id="{cid}"')
            pr = doc_xml.find(f'<w:commentReference w:id="{cid}"')
            if not (0 <= ps < pe < pr):
                problems.append(f"批注 {cid} 的 start/end/reference 顺序错误")
    return (not problems), problems


def build_docx(paper_dir: str, out_dir: str | None = None) -> DocxBuildResult:
    """生成 Word 批注版，并在生成后解压复核「实际锚点」是否与错误标记对账。

    对账口径（PRD §5.1 / §6.4）：
    - marker_count：各单元 _校对报告.md 的「标记原文」段内联标记总数；
    - anchor_count：docx 内实际三段齐全且落进 comments.xml 的批注锚点数
      （不含无问题单元的标题批注）；
    - formula_fallback_count：公式内部标记跳过批注后，在正文里以黄色高亮 +
      「修改意见」呈现的兜底数；
    - missing_count = marker_count - anchor_count - formula_fallback_count；
      missing_count != 0 时 ok=False（产物保留，由上层决定是否交付）。
    """
    result = DocxBuildResult(out_path=None)
    paper_path = Path(paper_dir)
    if not paper_path.is_dir():
        log(f"❌ Word 报告：目录不存在 {paper_dir}")
        result.warnings.append(f"目录不存在: {paper_dir}")
        return result

    from .verify import verify_unit  # 局部导入，避免潜在循环依赖

    questions_all = _collect_reports(paper_path)
    # 硬约束：下游不得消费未通过 verify-report 的报告。先校验，再排除不合格正文。
    questions = []
    for qid, part in questions_all:
        verdict = verify_unit(paper_path / qid)
        if verdict.ok:
            questions.append((qid, part))
            continue
        reason = "；".join(i.message for i in verdict.errors[:2]) or "verify-report 未通过"
        result.excluded_units.append({"unit": qid, "reason": reason})
        result.warnings.append(f"{qid}: 未通过 verify-report，已排除出 Word 交付（{reason}）")
        log(f"⛔ {qid}: 未通过 verify-report，排除出 Word 交付")
    markers_by_unit = _report_marker_counts(questions)
    included = [qid for qid, part in questions if _is_included_unit(part)]

    if not find_pandoc():
        log("❌ Word 报告：Pandoc 未安装，无法生成")
        result.warnings.append("pandoc 未安装，无法生成 docx")
        for qid, _ in questions:
            result.units.append({
                "unit": qid, "markers": markers_by_unit.get(qid, 0),
                "anchors": 0, "fallbacks": 0,
                "missing": markers_by_unit.get(qid, 0), "heading_comment": 0,
            })
        result.marker_count = sum(markers_by_unit.values())
        result.missing_count = result.marker_count
        return result

    out_path = generate_combined_docx(paper_dir, out_dir,
                                      only_units={qid for qid, _ in questions})
    result.out_path = out_path
    if out_path is None:
        result.warnings.append("docx 生成失败：无可处理单元或 pandoc 转换失败")

    doc_xml = ""
    if out_path and os.path.exists(out_path):
        try:
            with zipfile.ZipFile(out_path) as z:
                if "word/document.xml" in z.namelist():
                    doc_xml = z.read("word/document.xml").decode("utf-8")
        except Exception as e:
            result.warnings.append(f"复核读取 document.xml 失败: {e}")

    sections = _split_unit_sections(doc_xml)
    actual, comment_ids, audit_warnings = _audit_generated_docx(out_path, included, sections)
    result.warnings.extend(audit_warnings)

    for qid, _ in questions:
        markers = markers_by_unit.get(qid, 0)
        unit_actual = actual.get(qid)
        anchors = unit_actual["anchors"] if unit_actual else 0
        fallbacks = unit_actual["fallbacks"] if unit_actual else 0
        heading_comment = unit_actual["heading_comment"] if unit_actual else 0
        missing = markers - anchors - fallbacks
        if missing > 0:
            result.warnings.append(
                f"{qid}: {missing} 条错误标记既无 Word 批注锚点也无公式可见兜底")
        result.units.append({
            "unit": qid, "markers": markers, "anchors": anchors,
            "fallbacks": fallbacks, "missing": missing,
            "heading_comment": heading_comment,
        })

    result.marker_count = sum(u["markers"] for u in result.units)
    result.anchor_count = sum(u["anchors"] for u in result.units)
    result.formula_fallback_count = sum(u["fallbacks"] for u in result.units)
    result.heading_comment_count = sum(u["heading_comment"] for u in result.units)
    result.missing_count = (result.marker_count - result.anchor_count
                            - result.formula_fallback_count)

    # 全局硬门槛交叉复核：正文三段锚点数量、comments.xml 批注数必须相等，
    # 且等于「marker 锚点 + 无问题标题批注」。
    expected_ids = result.anchor_count + result.heading_comment_count
    pairing_ok, pairing_problems = _check_anchor_pairing(doc_xml, comment_ids)
    count_ok = (len(comment_ids) == expected_ids)
    result.anchor_structure_ok = bool(out_path) and pairing_ok and count_ok
    for problem in pairing_problems:
        result.warnings.append(f"锚点配对不一致：{problem}（不交付）")
    if out_path and not count_ok:
        result.warnings.append(
            f"锚点批注数 {len(comment_ids)} 与期望 {expected_ids} 不一致（不交付）")
    if comment_ids and not (result.marker_count or result.heading_comment_count):
        result.warnings.append(f"docx 含 {len(comment_ids)} 条批注锚点，但报告未解析出任何标记")
    log(f"🔎 Word 报告复核：标记 {result.marker_count} = 锚点 {result.anchor_count} + "
        f"公式兜底 {result.formula_fallback_count}，缺失 {result.missing_count}，"
        f"无问题标题批注 {result.heading_comment_count}")
    return result


def generate_combined_docx(paper_dir: str, out_dir: str | None = None,
                           only_units: set[str] | None = None) -> str | None:
    """扫描试卷/讲义目录，生成一份带批注的合并 Word 报告。

    Args:
        paper_dir: 拆分结果目录（含 单元N/第N题 子目录 + _校对报告.md + images/）
        out_dir: 输出目录，默认 paper_dir 同级 校对Word/

    Returns:
        docx 路径，失败返回 None
    """
    paper_path = Path(paper_dir)
    if not paper_path.is_dir():
        log(f"❌ Word 报告：目录不存在 {paper_dir}")
        return None

    if not find_pandoc():
        log("❌ Word 报告：Pandoc 未安装，无法生成")
        return None

    questions = _collect_reports(paper_path)
    if only_units is not None:
        questions = [(qid, part) for qid, part in questions if qid in only_units]
    if not questions:
        log(f"⚠️ Word 报告：{paper_dir} 下未找到任何可交付的 _校对报告.md")
        return None

    out_root = Path(out_dir) if out_dir else paper_path.parent / "校对Word"
    # 必须绝对化：pandoc 以临时目录为 cwd，相对 out_dir 会把 docx 写进临时目录，
    # 后续 _inject_comments 按调用方 cwd 打开相对路径必然 FileNotFoundError
    out_root = out_root.resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in paper_path.name if c not in r'\/:*?"<>|')
    out_path = out_root / f"{safe_name}_校对批注版.docx"

    work = Path(tempfile.mkdtemp(prefix="_docx_report_"))
    img_root = work / "images"
    img_root.mkdir(exist_ok=True)

    try:
        comments = {}
        gid_iter = itertools.count(1)
        used_ids = set()
        skipped_anchors = {}
        skip_anchor_iter = itertools.count(1)
        heading_anchors = {}
        all_bodies = []
        skipped_clean = 0
        skipped_broken = 0

        for qid, part in questions:
            marker_idx = part.find("### 标记原文")
            reason_idx = part.find("### 修改原因")
            has_sections = marker_idx != -1 and reason_idx != -1 and reason_idx >= marker_idx

            # 无标记（【N|原|改】）即视为「无问题」单元：
            # - 无分段形态：LLM 判定无问题时只输出「无问题 + 工具日志 + 思考过程」；
            # - 有分段形态：LLM 按完整分段输出（标记原文 = 无标记全文，修改原因 = 无）。
            # 两种形态都插入单元原文 + 「无问题」批注（锚定标题）。
            # 含标记却缺分段才可疑（批注可能丢失），单独警示。
            mark_seg = part[marker_idx:reason_idx] if has_sections else part
            if _PAT.search(mark_seg):
                if not has_sections:
                    skipped_broken += 1
                    log(f"   ⚠️ Word 报告：{qid} 含批注标记但缺少「标记原文/修改原因」分段，跳过（批注无法生成）")
                    continue
            else:
                skipped_clean += 1
                log(f"   ℹ️ Word 报告：{qid} 无批注，插入单元原文 + 「无问题」批注（锚定标题）")
                unit_md = paper_path / qid / f"{qid}.md"
                if unit_md.exists():
                    content = unit_md.read_text(encoding="utf-8").strip()
                    content = _rewrite_images(content, paper_path / qid, img_root)
                    content = _preprocess_latex(content)
                    gid = next(gid_iter)
                    if gid in used_ids:
                        gid = max(used_ids) + 1
                    used_ids.add(gid)
                    comments[gid] = ("无问题", None)
                    # 锚点后处理落在标题「qid」文本上（Heading1 段落内）
                    heading_anchors[gid] = qid
                    all_bodies.append(f"# {qid}\n\n{content}\n\n{_PAGE_BREAK}")
                else:
                    all_bodies.append(f"# {qid}\n\n无问题\n\n{_PAGE_BREAK}")
                continue
            reasons = parse_reasons(part[reason_idx:])
            body = part[marker_idx:reason_idx]
            body = "\n".join(
                l for l in body.splitlines()
                if not (l.strip().startswith("### 标记原文")
                        or l.strip().startswith("编号：")
                        or l.strip().startswith("内容："))
            ).strip()
            body = _strip_wrapping_fence(body)
            # 标记真实性审计必须在重写图片引用与 LaTeX 预处理之前做：
            # 审计要把「重建正文」与单元源文逐字比对，而这两步都会改写正文字面
            audits = audit_markers(body, _read_unit_source(paper_path, qid))
            body = _rewrite_images(body, paper_path / qid, img_root)
            body = _convert_multiline_tables(body)
            # 标记字段先摘出再预处理正文：字段里的 \[ 多为待修改的转义错误，
            # 套用正文的「\[…\] → $…$」还原会打乱字段内 $ 配对（见 _mask_markers）
            body, marker_fields = _mask_markers(body)
            body = _preprocess_latex(body)

            # 行内公式区间（$...$ 配对），锚点落在公式内部的标记跳过——
            # 上游数据把公式内部文本当锚点时，插入 openxml 会撕裂公式导致乱码
            math_spans = _scan_math_spans(body)

            def _anchor_markup(m, _reasons=reasons, _fields=marker_fields,
                               _audit_by_num={a.num: a for a in audits}):
                # group(1) 是掩码槽位下标（0 起），字段里第一个才是标记编号；
                # 按编号取审计结果，避免槽位顺序与审计顺序耦合
                cid, raw_orig, raw_new = _fields[int(m.group(1))]
                audit = _audit_by_num.get(cid)
                orig = _preprocess_marker_field(raw_orig)
                new = _preprocess_marker_field(raw_new)
                if audit is not None and audit.render_new:
                    # 原文字段在源文对不上、改为字段对得上：按原文渲染会把原文里
                    # 不存在的错误写进 Word 正文，改按「改为」还原，批注保留
                    log(f"   ⚠️ Word 报告：{qid} 标记 {cid} 的原文字段在源文定位不到"
                        f"（源文此处即「{raw_new}」），正文按改为还原并保留批注")
                    orig = new
                if audit is not None and not audit.keep_comment:
                    if audit.verdict == MARKER_NOOP:
                        log(f"   ⚠️ Word 报告：{qid} 标记 {cid} 是空操作"
                            f"（原文与改为同为「{raw_orig}」），不生成批注")
                    else:
                        log(f"   ⚠️ Word 报告：{qid} 标记 {cid} 原文字段为空，不生成批注")
                    return orig
                if any(s <= m.start() < e for s, e in math_spans):
                    # 唯一占位符代替还原文本：pandoc 转换后据此精确定位公式高亮，
                    # 避免还原文本（如常见变量 v）误匹配其他公式。
                    # 记录 (原文, 修改意见)，高亮处一并显示修改建议。
                    log(f"   ⚠️ Word 报告：{qid} 批注锚点位于公式内部，跳过该条（标记原文被还原）")
                    n = next(skip_anchor_iter)
                    skipped_anchors[n] = (orig.strip("$"), new.strip("$"))
                    return f"SKIPANCH{n}Z"
                gid = next(gid_iter)
                used_ids.add(gid)
                if orig.endswith("\\") and not orig.endswith("\\\\"):
                    orig = orig + "\\"
                # 字段内 $ 不能自洽配对时整段转义：否则会与后文（越过 openxml
                # raw）的 $ 错配，把 raw 吞进公式导致批注锚点丢失。
                if not _math_safe(orig):
                    orig = orig.replace("$", "\\$")
                comments[gid] = (new, _reasons.get(cid))
                start = f'`<w:commentRangeStart w:id="{gid}"/>`{{=openxml}}'
                end = (f'`<w:commentRangeEnd w:id="{gid}"/>'
                       f'<w:r><w:commentReference w:id="{gid}"/></w:r>`{{=openxml}}')
                return start + orig + end

            unit_body = _MARKER_SLOT_RE.sub(_anchor_markup, body)
            unit_body = _textify_skipped_formulas(unit_body, skipped_anchors)
            all_bodies.append(f"# {qid}\n\n{unit_body}\n\n{_PAGE_BREAK}")

        if not all_bodies:
            log(f"⚠️ Word 报告：{paper_dir} 无任何可处理的单元")
            return None

        full_md = "\n\n".join(all_bodies)
        md_tmp = work / "_报告_带锚.md"
        md_tmp.write_text(full_md, encoding="utf-8")

        r = subprocess.run(
            [find_pandoc(), "-f", "markdown-implicit_figures+hard_line_breaks+mark",
             str(md_tmp), "-o", str(out_path)],
            capture_output=True, text=True, cwd=str(work),
            **(dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else {}))
        if r.returncode != 0:
            log(f"❌ Word 报告：pandoc 转换失败: {(r.stderr or '')[:300]}")
            return None
        # stderr 正常必为 str；打包 exe 实测现场出现过 None，判空防崩
        if r.stderr and r.stderr.strip():
            fetch_warns = [l for l in r.stderr.splitlines() if 'fetch' in l]
            if fetch_warns:
                log(f"   ⚠️ Word 报告：{len(fetch_warns)} 张图片未找到（将显示替换文字）")

        _inject_comments(out_path, comments, heading_anchors)
        summary = f"（{len(comments)} 条批注"
        if skipped_clean:
            summary += f"，{skipped_clean} 个单元无批注"
        if skipped_broken:
            summary += f"，{skipped_broken} 个单元含标记但缺分段跳过"
        log(f"✅ Word 批注报告已生成：{out_path}{summary}）")
        return str(out_path)
    except Exception as e:
        import traceback
        log(f"❌ Word 报告生成异常: {e}\n{traceback.format_exc()}")
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _collect_reports(paper_path: Path):
    """收集子目录（单元N/第N题/板块N）的 _校对报告.md，按数字排序。"""
    reports = []
    for sub in paper_path.iterdir():
        if not sub.is_dir():
            continue
        rep = sub / "_校对报告.md"
        if rep.exists():
            try:
                reports.append((sub.name, rep.read_text(encoding="utf-8")))
            except OSError:
                continue

    def _sort_key(item):
        m = re.findall(r"\d+", item[0])
        return (int(m[0]) if m else 9999, item[0])

    return sorted(reports, key=_sort_key)


def _read_unit_source(paper_path: Path, qid: str) -> str | None:
    """读取单元源文（`单元N/单元N.md`），用于标记真实性审计。

    非本目录布局（源文缺失）时返回 None：审计随即不做源文比对、不猜测。
    """
    unit_md = paper_path / qid / f"{qid}.md"
    if not unit_md.exists():
        return None
    try:
        return unit_md.read_text(encoding="utf-8")
    except OSError:
        return None


def _rewrite_images(body: str, q_dir: Path, img_root: Path) -> str:
    """图片引用重写：./images/xxx → ./images/{题名}_xxx，复制到合并目录防编号冲突。

    外链 https:// 引用是 LLM 幻觉（搜索结果拷贝），转为文字说明，
    避免 pandoc 尝试下载失败产生 fetch 警告。
    """
    q_img_dir = q_dir / "images"

    def _repl(m):
        ref = m.group(2)
        if ref.startswith(("http://", "https://")):
            return "（配图缺失：外链图片无法嵌入）"
        name = Path(ref).name
        new_name = f"{q_dir.name}_{name}"
        src_img = q_img_dir / name
        if src_img.exists():
            try:
                shutil.copy2(src_img, img_root / new_name)
            except OSError:
                pass
        alt = m.group(1)
        if alt.startswith("@@@"):
            alt = "配图"
        return f"![{alt}](./images/{new_name})"

    return re.sub(r"!\[([^]]*)\]\(([^)]+)\)", _repl, body)


def _convert_multiline_tables(text: str) -> str:
    """多行表格（长 --- 线包裹，pandoc multiline table）→ grid table。

    pandoc 的 multiline table 单元格会丢弃 openxml raw；grid table 正常。
    短 --- 是 markdown 分隔线，不动。
    """
    lines = text.split("\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        # 仅「整行全部由 - 组成」的长线才是 multiline table 边框；- 开头的列表项不算
        if set(stripped) == {"-"} and len(stripped) >= 10:
            j = i + 1
            end = -1
            while j < n:
                s = lines[j].strip()
                if set(s) == {"-"} and len(s) >= 10:
                    end = j
                    break
                j += 1
            if end != -1:
                rows = []
                for k in range(i + 1, end):
                    s = lines[k].strip()
                    if not s:
                        continue
                    if set(s.replace(" ", "")) <= {"-"}:
                        continue
                    cells = [c.strip() for c in re.split(r" {2,}", s)]
                    rows.append(cells)
                if rows:
                    ncols = max(len(r) for r in rows)
                    rows = [r + [""] * (ncols - len(r)) for r in rows]
                    widths = [0] * ncols
                    for r in rows:
                        for ci, c in enumerate(r):
                            widths[ci] = max(widths[ci], len(c))

                    def border(ch):
                        return "+" + "+".join(ch * (w + 2) for w in widths) + "+"

                    out.append(border("-"))
                    out.append("| " + " | ".join(
                        c.ljust(widths[ci]) for ci, c in enumerate(rows[0])) + " |")
                    out.append(border("="))
                    for r in rows[1:]:
                        out.append("| " + " | ".join(
                            c.ljust(widths[ci]) for ci, c in enumerate(r)) + " |")
                        out.append(border("-"))
                    i = end + 1
                    continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _strip_wrapping_fence(text: str) -> str:
    """剥除包裹整段标记原文的首尾代码围栏（``` / ~~~ 行）。

    LLM 为「逐字抄写」的原文本能习惯用围栏包住原文（提示词已禁止，
    但模型不稳定）。围栏会让 pandoc 按代码块渲染：$...$ 不转微软公式、
    图片引用与批注锚点全部变字面文本。只剥首尾的孤立围栏行，正文中间
    的围栏不动（处理 ` ```markdown` 这类带语言标签的围栏）。
    """
    fence = re.compile(r'^\s*(```|~~~)[A-Za-z0-9_\-]*\s*$')
    lines = text.splitlines()
    if lines and fence.match(lines[0]):
        lines = lines[1:]
    if lines and fence.match(lines[-1]):
        lines = lines[:-1]
    return "\n".join(lines)


def _mask_markers(body: str) -> tuple[str, list[tuple[int, str, str]]]:
    """把内联标记整段摘成占位符，返回 (掩码文本, [(编号, 原文, 改为), ...])。

    标记字段必须与正文的 LaTeX 预处理隔离：字段里的 `\\[`、`\\]` 多半是待修改的
    转义错误（如 `$…=\\[…\\]…$`），按正文规则还原成行间公式定界符会把字段内的 `$`
    数量与配对改乱，pandoc 随即用多余的 `$` 开出跨行行内公式，把紧随其后的
    openxml raw 吞进公式——批注只剩 RangeStart，正文残留字面 XML。
    字段自身改由 _preprocess_marker_field 处理。
    """
    fields: list[tuple[int, str, str]] = []

    def _sub(m):
        fields.append((int(m.group(1)), m.group(2), m.group(3)))
        return f"【MARKSLOT{len(fields) - 1}Z】"

    return _PAT.sub(_sub, body), fields


def _preprocess_latex(body: str) -> str:
    """LaTeX 定界符还原：\\[...\\] / \\\\[...\\\\] → 美元行内公式；转义美元还原；公式内部双反斜杠命令还原。"""
    body = re.sub(r"\\\\\[(.*?)\\\\]",
                  lambda m: "$" + m.group(1).replace("\\\\", "\\") + "$",
                  body, flags=re.DOTALL)
    body = re.sub(r"\\\[(.*?)\\\]", lambda m: "$" + m.group(1) + "$",
                  body, flags=re.DOTALL)
    return _normalize_math_dollars(_preprocess_latex_tail(body))


def _preprocess_latex_tail(text: str) -> str:
    """正文与标记字段共用的 LaTeX 预处理尾部（转义美元 / 公式内双反斜杠 / \\rm）。

    不含 `$` 配对规范化：标记字段的配对安全由 _math_safe 按 pandoc 规则显式判定，
    在字段内按行奇偶补转义只会污染字段文本（如把片段 `aaa$` 改成 `aaa\\$`）。
    """
    text = text.replace("\\$", "$")
    text = re.sub(r"\$(.+?)\$",
                  lambda m: "$" + m.group(1).replace("\\\\", "\\") + "$",
                  text, flags=re.DOTALL)
    # texmath 不支持 \rm 切换命令（{\rm m} / \rm{A} 报 unexpected control
    # sequence），pandoc 放弃转换、公式以 TeX 文本显示；统一改写成 \mathrm{X}
    text = re.sub(r"\\rm\s*\{([A-Za-z/]+)\}", r"\\mathrm{\1}", text)
    text = re.sub(r"\{\\rm\s*([A-Za-z/]+)\}", r"\\mathrm{\1}", text)
    return text


_FIELD_DISPLAY_MATH_RE = re.compile(r"^\\\\\[(.*?)\\\\\]$", re.DOTALL)
"""整字段就是 \\\\[…\\\\] 行间公式定界符。"""

_FIELD_ESCAPED_MATH_RE = re.compile(r"^\\\[(.*?)\\\]$", re.DOTALL)
"""整字段就是 \\[…\\] 行间公式定界符。"""


def _preprocess_marker_field(field: str) -> str:
    """标记字段（原文 / 改为）的 LaTeX 预处理——正文规则的字段局部版。

    与正文的唯一区别：`\\[…\\] → $…$` 只在该字段**整体**就是一个行间公式时套用
    （与正文同样区分 `\\[…\\]` 与 `\\[…\\]` 两种转义形态）。字段内部的 `\\[`
    （如 `$…\\[…\\]…$`）是待修改的转义错误，按定界符改写会打乱 `$` 配对、
    吞掉批注 openxml raw，故原样保留。
    """
    for pat, unescape in ((_FIELD_DISPLAY_MATH_RE, True), (_FIELD_ESCAPED_MATH_RE, False)):
        m = pat.match(field)
        if m:
            inner = m.group(1).replace("\\\\", "\\") if unescape else m.group(1)
            return _preprocess_latex_tail("$" + inner + "$")
    return _preprocess_latex_tail(field)


def _math_safe(text: str) -> bool:
    """检查字段内 `$…$` 能否被 pandoc 完整配对（不留裸 `$`）。

    规则与 pandoc tex_math_dollars 实测行为一致：左起遇到 `$` 就尝试配成数学——
    开 `$` 右侧必须非空白、两者之间不得再出现 `$`、闭 `$` 左侧必须非空白且右侧
    不能是数字；配不成则该 `$` 退化为字面字符、从下一个字符继续。字段里只要还剩
    没配对的 `$`，它就会越过 openxml raw 与后文的 `$` 配对，把 raw 吞进公式。
    """
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "$" or (i > 0 and text[i - 1] == "\\"):
            i += 1
            continue
        i += 1
        if i >= n or text[i].isspace() or text[i] == "$":
            return False
        while i < n and text[i] != "$":
            i += 1
        if i >= n or text[i - 1].isspace() or (i + 1 < n and text[i + 1].isdigit()):
            return False
        i += 1
    return True


def _normalize_math_dollars(text: str) -> str:
    """规范化数学定界符，防止 pandoc 错配吞掉 openxml raw。

    `$200\\Omega $`（$ 内尾随空格）不闭合时，pandoc 会把后续文本中的下一个
    `$` 与它配对成数学，中间的 openxml raw 被吞进公式导致批注锚点丢失。
    """
    text = re.sub(r"\$([^$\n]*?)[ \t]+\$", lambda m: "$" + m.group(1) + "$", text)
    text = re.sub(r"\$[ \t]+([^$\n]*?)\$", lambda m: "$" + m.group(1) + "$", text)
    lines = []
    for line in text.split("\n"):
        if line.count("$") % 2 == 1:
            idx = line.rfind("$")
            line = line[:idx] + "\\$" + line[idx + 1:]
        lines.append(line)
    return "\n".join(lines)


def _inject_comments(docx_path: Path, comments: dict, heading_anchors: dict | None = None):
    """填充 comments.xml、清理无锚点引用、替换图片替换文字。

    批注内 `$...$` 公式渲染为 PNG 图片注入（shared/formula_render），
    渲染失败（含中文/矩阵等）的公式段降级为原 LaTeX 文本。
    heading_anchors：{gid: 标题文本}，批注锚点后处理落在 Heading1 段落
    的标题文本 run 上（pandoc 会忽略标题内的 raw 标记，只能转换后注入）。
    """
    # 先读 document.xml 计算保留的批注 id（zipfile 部件顺序不保证 document.xml 在前）
    kept_ids = set()
    with zipfile.ZipFile(docx_path, "r") as zin:
        doc_xml = zin.read("word/document.xml").decode("utf-8")
    doc_xml = re.sub(r'descr="@@@[^"]*"', 'descr="配图"', doc_xml)
    if heading_anchors:
        doc_xml = _anchor_heading_comments(doc_xml, heading_anchors)
    doc_xml, kept_ids, dropped_ids = _strip_unanchored_comments(doc_xml)
    doc_xml, leaked_ids = _strip_leaked_openxml(doc_xml)
    if dropped_ids:
        log(f"   ⚠️ Word 报告：批注 {', '.join(dropped_ids)} 锚点不完整"
            f"（缺 commentRangeStart/End/Reference），已移除残引用并从批注部件剔除")
    if leaked_ids:
        log(f"   ⚠️ Word 报告：批注 {', '.join(leaked_ids)} 的 openxml raw 被 pandoc 当文本输出，"
            "已清理正文残留标记（该锚点内容未生效）")

    work_dir = Path(tempfile.mkdtemp(prefix="_cmt_img_", dir=str(docx_path.parent)))
    try:
        comments_xml, images = _build_comments_xml(comments, kept_ids, work_dir)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    tmp_path = docx_path.with_name("_tmp.docx")
    with zipfile.ZipFile(docx_path, "r") as zin, \
            zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = doc_xml.encode("utf-8")
            elif item.filename == "word/comments.xml":
                data = comments_xml.encode("utf-8")
            elif item.filename == "[Content_Types].xml" and images:
                data = _ensure_png_content_type(data)
            zout.writestr(item, data)
        if images:
            # 批注公式图片 part + 关系（新建 comments.xml.rels）
            for media_name, png_bytes, r_id in images:
                zout.writestr(f"word/media/{media_name}", png_bytes)
            rels_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                        + "".join(
                            f'<Relationship Id="{r_id}" '
                            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                            f'Target="media/{media_name}"/>'
                            for media_name, _, r_id in images)
                        + "</Relationships>")
            zout.writestr("word/_rels/comments.xml.rels", rels_xml.encode("utf-8"))
    tmp_path.replace(docx_path)


def _ensure_png_content_type(ct_xml: bytes) -> bytes:
    """确保 [Content_Types].xml 含 png Default 声明（批注公式图片需要）。"""
    text = ct_xml.decode("utf-8")
    if 'Extension="png"' in text:
        return ct_xml
    return text.replace(
        '<Default Extension="rels"',
        '<Default Extension="png" ContentType="image/png" />\n<Default Extension="rels"',
    ).encode("utf-8")


_SKIP_ANCHOR_RE = re.compile(r"SKIPANCH(\d+)Z")


def _textify_skipped_formulas(text: str, skipped_anchors: dict) -> str:
    """把含被跳过标记的公式改为转义文本并用 ==...== 高亮，不转微软公式。

    公式内标记被跳过（批注无法生成）时，正文对应公式以 LaTeX 文本原样显示
    并黄色高亮，提示读者该处有问题。`\\`、`$` 与 `^` 转义避免 pandoc 数学
    解析、markdown 转义吞字符与 `^...^` 上标误判；SKIPANCH{n}Z 占位符还原
    为标记原文，并在高亮内附修改意见（原文→改后）。
    """
    if not skipped_anchors:
        return text
    spans = _scan_math_spans(text)
    out = text
    for s, e in reversed(spans):
        seg = out[s:e]
        if "SKIPANCH" not in seg:
            continue
        seg = seg.replace("\\", "\\\\").replace("$", "\\$").replace("^", "\\^")

        def _esc(t):
            return t.replace("\\", "\\\\").replace("$", "\\$").replace("^", "\\^")

        # 先收集修改意见（转义不影响占位符），再还原原文，意见追加在公式文本之后
        notes = "".join(
            f"（修改意见：{_esc(orig)}→{_esc(new)}）" if new else ""
            for m in _SKIP_ANCHOR_RE.finditer(seg)
            for orig, new in [skipped_anchors[int(m.group(1))]])
        seg = _SKIP_ANCHOR_RE.sub(
            lambda m: _esc(skipped_anchors[int(m.group(1))][0]), seg)
        out = out[:s] + "==" + seg + notes + "==" + out[e:]
    return out


def _anchor_heading_comments(doc_xml: str, heading_anchors: dict) -> str:
    """在 Heading1 段落的标题文本 run 上插入批注锚点。

    pandoc 忽略标题（ATX heading）内的 raw 标记，无问题单元的「无问题」
    批注锚点只能在此转换后处理：匹配 pStyle=Heading1 段落中 w:t 文本等于
    标题文本的 run，在 run 前后插入 commentRangeStart/End + commentReference。
    """
    for gid, title in heading_anchors.items():
        # rangeStart 在 run 前、rangeEnd+reference 在 run 后（与 pandoc 正常锚点同构）。
        # rPr 用「自闭合元素序列」匹配（pandoc rPr 子元素均为自闭合），
        # 避免 .*? 回溯跨段匹配到远处标题段。
        pat = re.compile(
            r'(<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1"[^>]*/>\s*</w:pPr>\s*)'
            r'(<w:r>\s*<w:rPr>\s*(?:<w:[^>]*/>\s*)*</w:rPr>\s*<w:t[^>]*>)('
            + re.escape(escape(title)) + r')(</w:t>\s*</w:r>)(\s*</w:p>)', re.DOTALL)

        def _repl(m, _gid=gid):
            return (m.group(1)
                    + f'<w:commentRangeStart w:id="{_gid}"/>'
                    + m.group(2) + m.group(3) + m.group(4)
                    + f'<w:commentRangeEnd w:id="{_gid}"/>'
                    + f'<w:r><w:commentReference w:id="{_gid}"/></w:r>'
                    + m.group(5))

        doc_xml, count = pat.subn(_repl, doc_xml)
        if count == 0:
            log(f"   ⚠️ Word 报告：标题「{title}」未在 Heading1 段落匹配，无问题批注锚点丢失")
        elif count > 1:
            log(f"   ⚠️ Word 报告：标题「{title}」匹配到 {count} 处，存在同名标题重复注入")
    return doc_xml


def _strip_unanchored_comments(doc_xml: str):
    """清理锚点不完整的批注引用（双向）。

    源数据损坏（如标记被插进图片引用/公式内部）时 pandoc 会把 openxml raw 当
    普通文本输出，锚点随之残缺：可能只剩 commentRangeStart，也可能只剩
    commentRangeEnd + commentReference。两种残缺都会让 Word 里批注错位或
    显示不出来，这里一律移除，并返回被清理的批注编号供调用方告警。

    Returns:
        (doc_xml, kept_ids, dropped_ids)：kept_ids 为三段引用齐全的批注编号。
    """
    starts = set(re.findall(r'<w:commentRangeStart w:id="(\d+)"', doc_xml))
    ends = set(re.findall(r'<w:commentRangeEnd w:id="(\d+)"', doc_xml))
    refs = set(re.findall(r'<w:commentReference w:id="(\d+)"', doc_xml))
    kept_ids = starts & ends & refs
    dropped_ids = sorted((starts | ends | refs) - kept_ids, key=int)
    for cid in dropped_ids:
        doc_xml = re.sub(rf'<w:commentRangeStart w:id="{cid}"\s*/>', '', doc_xml)
        doc_xml = re.sub(rf'<w:commentRangeEnd w:id="{cid}"\s*/>', '', doc_xml)
        doc_xml = re.sub(rf'<w:r><w:commentReference w:id="{cid}"\s*/></w:r>', '', doc_xml)
    return doc_xml, kept_ids, dropped_ids


_LEAKED_OPENXML_RE = re.compile(r'`&lt;w:commentRange(?:Start|End)[^<]*?`\{=openxml\}')
"""被 pandoc 当普通文本输出的 openxml raw（转义后的字面标记）。"""


def _strip_leaked_openxml(doc_xml: str):
    """删除正文里残留的字面 openxml 标记（被 pandoc 吞进公式后当文本输出）。

    只匹配同一个 w:t 文本节点内的 `\\`…``{=openxml}`（`[^<]` 不允许跨越真实
    XML 标签，因此不会误删正文结构），返回涉及的批注编号。
    """
    leaked: list[str] = []

    def _sub(m):
        leaked.extend(re.findall(r"w:id=&quot;(\d+)&quot;", m.group(0)))
        return ""

    doc_xml = _LEAKED_OPENXML_RE.sub(_sub, doc_xml)
    return doc_xml, sorted(set(leaked), key=int)


def _build_comments_xml(comments: dict, kept_ids: set, work_dir: Path) -> tuple[str, list]:
    """构建 comments.xml，批注内 `$...$` 公式渲染为 PNG 图片。

    Args:
        comments: gid → (改后文字, 修改原因)
        kept_ids: 保留的批注 id
        work_dir: 公式 PNG 渲染临时目录

    Returns:
        (comments_xml, images)：images 为 [(media文件名, png字节, rId), ...]
    """
    items = []
    images = []
    pic_id = itertools.count(1)

    def _escape_run(text: str) -> str:
        return f'<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'

    def _para_with_formulas(text: str) -> str:
        """文本按 $...$ 切分：公式段渲染图片（失败降级为文本），其余保留文本。"""
        parts = re.split(r'(\$[^$]+\$)', text)
        runs = []
        for part in parts:
            if not part:
                continue
            if part.startswith("$") and part.endswith("$") and len(part) > 2:
                body = part[1:-1]
                num = next(pic_id)
                media_name = f"comment_pic{num}.png"
                if latex_to_png(body, work_dir / media_name):
                    png_bytes = (work_dir / media_name).read_bytes()
                    r_id = f"rIdPic{len(images) + 1}"
                    images.append((media_name, png_bytes, r_id))
                    runs.append(_inline_image_xml(num, media_name, r_id, png_bytes))
                    continue
            runs.append(_escape_run(part))
        return "".join(runs)

    for gid in sorted(comments):
        if str(gid) not in kept_ids:
            continue
        new, reason = comments[gid]
        center = '<w:pPr><w:jc w:val="center"/></w:pPr>'
        paras = [f"<w:p>{center}{_para_with_formulas(new)}</w:p>"]
        if reason:
            paras.append(f"<w:p>{center}{_escape_run('修改原因：')}{_para_with_formulas(reason)}</w:p>")
        items.append(
            f'<w:comment w:id="{gid}" w:author="校对助手" '
            f'w:date="{_comment_timestamp()}">' + "".join(paras) + '</w:comment>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:comments {_NS}>' + "".join(items) + "</w:comments>"), images


def _inline_image_xml(num: int, media_name: str, r_id: str, png_bytes: bytes) -> str:
    """构造批注内联图片 run 的 XML（EMU 尺寸按 200dpi 渲染物理尺寸换算）。

    图片垂直位置保持 Word 默认（底边对齐基线），不做 w:position 偏移。
    """
    import io

    from PIL import Image
    with Image.open(io.BytesIO(png_bytes)) as im:
        w_px, h_px = im.size
    emu_w = round(w_px * 914400 / 200)
    emu_h = round(h_px * 914400 / 200)
    return (
        '<w:r><w:drawing>'
        '<wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{emu_w}" cy="{emu_h}"/>'
        f'<wp:docPr id="{num}" name="{escape(media_name)}" descr="公式"/>'
        '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic>'
        f'<pic:nvPicPr><pic:cNvPr id="{num}" name="{escape(media_name)}"/><pic:cNvPicPr/></pic:nvPicPr>'
        '<pic:blipFill>'
        f'<a:blip r:embed="{r_id}"/><a:stretch><a:fillRect/></a:stretch>'
        '</pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/>'
        f'<a:ext cx="{emu_w}" cy="{emu_h}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        '</pic:pic></a:graphicData></a:graphic>'
        '</wp:inline></w:drawing></w:r>'
    )


def _comment_timestamp() -> str:
    """生成 OOXML ST_DateTime 格式的当前 UTC 时间戳（ISO 8601 Z 形式）。"""
    from datetime import datetime
    return datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
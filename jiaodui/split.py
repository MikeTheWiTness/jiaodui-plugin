"""规则拆分、边界切片、拆分预检与导航标记（单一源）。

移植自旧仓 core/defaults.py（HEAD 1c45243）的 default_split_lecture /
default_split_exam 一系函数、core/manual_split.py 的单元标记解析器，以及
shared/split_post_utils.py 的导航标记逻辑，按新契约改写：

- 拆分入口只产出契约名 `第N题.md` / `单元N.md` 与 `images/`；不再产出
  `_clean.md`（旧仓为前置搜索复制）。
- 重跑只补齐源文与图片，绝不覆盖/删除单元目录内已有的 `_校对报告.md`、
  `_校对数据.json`、`_校对失败.md`。
- 图片源目录沿用 `{raw_md 所在目录}/{base_name}_images/media`。
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from .config import (get_compiled_title_patterns, get_exam_question_pattern,
                     get_lecture_split_mode, get_nav_patterns, get_section_pattern,
                     normalize_subject_config)
from .decor_utils import strip_decor_images
from .errors import ContractError
from .image_utils import ImageCopyResult, copy_md_images
from .log import log
from .paths import IMAGES_DIR, SKIP_MARKER_FILE, find_source_md
from .units import scan_unit_dirs


def prepare_lecture_content(content: str, problem_markers=None) -> str:
    """讲义导入清理（移植旧仓导入阶段，默认开启）。

    旧仓讲义流程在拆分前固定按以下顺序执行六步（导入阶段五步，见旧仓
    ui/default_app.py::_conversion_thread_run；再在 default_split_lecture 开头清装饰图）。
    新仓此前只移植了函数、从未调用，导致 pandoc 渲染成网格表的讲义
    （``| **例1**（多选） |``）拆不开：

    1. ``fix_latex_escapes_text``：修复 pandoc 过度转义，使公式定界符可被识别；
    2. ``comprehensive_clean``：去表格竖线、丢表框线、保护公式、规整空行；
    3. ``clean_intent_markers``：删除【出题意图】段，保留其后题目编号；
    4. ``fix_floating_images_text``：把浮进选项 A 的题图挪回独立图片行；
    5. ``normalize_option_spacing_text``：把 4 个以上连续空格压成 2 个；
    6. ``strip_decor_images``：清除板块标题行的小装饰图标。

    顺序与旧仓一致：先还原转义与表格，再清意图/挪图/压空格，最后清装饰图。
    清理后 ``**例1**`` 等例题标题回到行首，``section_pattern`` 才能命中。

    Args:
        content: Markdown 正文。
        problem_markers: 【出题意图】清理的题目编号正则列表；None 时用通用常量。
            学科独有的标志由调用方经 ``convert.get_intent_problem_markers``
            合并后传入。

    幂等：已清理过的正文再跑一次结果不变。
    """
    from .convert import (clean_intent_markers, comprehensive_clean,
                          fix_floating_images_text, fix_latex_escapes_text,
                          normalize_option_spacing_text)

    content = fix_latex_escapes_text(content)
    content = comprehensive_clean(content)
    content = clean_intent_markers(content, problem_markers=problem_markers)
    content = fix_floating_images_text(content)
    content = normalize_option_spacing_text(content)
    return strip_decor_images(content)

# ─── 统一的单元标记（ADR-0017 决策5） ──────────────────────────

UNIT_START_MARKER = r"(\\?#){6}\s*单元开始\s*(\\?#){6}"
UNIT_END_MARKER = r"(\\?#){6}\s*单元结束\s*(\\?#){6}"

OVERLONG_THRESHOLD = 20000
"""precheck_split 判定超长单元的默认字符数阈值（可配置）。"""


class UnitMarkerError(ContractError, ValueError):
    """统一的单元标记错误。

    同时继承 ContractError 与 ValueError：新契约按契约错误处理，旧调用方可继续
    用 `except ValueError` 捕获。
    """


@dataclass
class SplitResult:
    """一次拆分的确定性结果。"""
    unit_dirs: list[str] = field(default_factory=list)
    units: list[dict] = field(default_factory=list)
    copied: int = 0
    missing: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class PrecheckResult:
    """拆分预检摘要（供主 agent 抽查）。

    empty_units / overlong_units 保存命中的单元目录名；对应数量用 len() 取。
    units 每项含 name、path、first_line、chars、empty、overlong。
    """
    unit_count: int = 0
    empty_units: list[str] = field(default_factory=list)
    overlong_units: list[str] = field(default_factory=list)
    length_min: int = 0
    length_median: float = 0.0
    length_max: int = 0
    units: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ─── 单元标记解析器（移植自 core/manual_split.py） ─────────────

def parse_unit_markers(text: str) -> list[dict]:
    """解析 ###### 单元开始/结束 ###### 标记，返回单元列表。

    容忍 pandoc 转义的 \\# 前缀。

    Returns:
        [{"content": "单元正文"}, ...]

    Raises:
        UnitMarkerError: 标记缺失或不配对。
    """
    lines = text.splitlines()
    units: list[dict] = []
    current_content: list[str] = []
    in_unit = False
    start_count = 0
    end_count = 0

    start_pattern = f"^{UNIT_START_MARKER}$"
    end_pattern = f"^{UNIT_END_MARKER}$"

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        is_start = bool(re.match(start_pattern, stripped))
        is_end = bool(re.match(end_pattern, stripped))

        if is_start:
            start_count += 1
            if in_unit:
                raise UnitMarkerError(
                    f"第 {i} 行：发现未闭合的单元开始标记，标记不配对"
                )
            in_unit = True
            current_content = []
        elif is_end:
            end_count += 1
            if not in_unit:
                raise UnitMarkerError(
                    f"第 {i} 行：发现没有对应开始标记的单元结束标记，标记不配对"
                )
            units.append({"content": "\n".join(current_content)})
            in_unit = False
        else:
            if in_unit:
                current_content.append(line)

    if start_count == 0 and end_count == 0:
        raise UnitMarkerError(
            "未找到任何单元标记（###### 单元开始 ###### / ###### 单元结束 ######），"
            "请在文档中添加成对标记"
        )

    if in_unit:
        raise UnitMarkerError(
            f"标记不配对：找到 {start_count} 个开始标记，{end_count} 个结束标记，"
            f"最后一个单元缺少结束标记"
        )

    if start_count != end_count:
        raise UnitMarkerError(
            f"标记不配对：找到 {start_count} 个开始标记，{end_count} 个结束标记"
        )

    return units


# ─── 输入与写盘 ────────────────────────────────────────────

def _ensure_normalized(config: dict | None) -> dict:
    """保证拿到标准化配置；额外键（如图片目录覆盖）原样保留。"""
    if not isinstance(config, dict):
        return normalize_subject_config({})
    merged = dict(config)
    merged.update(normalize_subject_config(config))
    return merged


def _load_raw(raw_md, base_name: str, config: dict | None = None):
    """解析输入：既接受 raw_md 文件路径，也接受 Markdown 正文。

    Returns:
        (content, 图片源目录或 None)。图片源目录约定为
        `{raw_md 所在目录}/{base_name}_images/media`；配置里的
        source_images_dir / images_source_dir 可显式覆盖。
    """
    config = config or {}
    override = (config.get("source_images_dir") or config.get("images_source_dir")
                or config.get("images_source"))
    src_media = Path(override) if override else None
    if src_media is not None and (src_media / "media").is_dir():
        # 兼容 `convert --json` 返回的 images_dir：那是 `{base}_images` 根目录，
        # 图片实际在它的 media/ 子目录，直接传进来曾经一张都复制不到。
        src_media = src_media / "media"

    looks_path = isinstance(raw_md, Path) or (
        isinstance(raw_md, str)
        and bool(raw_md)
        and "\n" not in raw_md
        and "\r" not in raw_md
    )
    if looks_path:
        try:
            candidate = Path(raw_md)
            is_file = candidate.is_file()
        except (OSError, ValueError):
            is_file = False
        if is_file:
            content = candidate.read_text(encoding="utf-8")
            if src_media is None:
                src_media = candidate.parent / f"{base_name}_images" / "media"
            return content, src_media
    return str(raw_md), src_media


def _write_unit(target_root: Path, unit_name: str, content: str,
                src_media: Path | None):
    """写单个单元目录：只落源文与图片，绝不触碰 _ 前缀的校对产物。"""
    unit_dir = target_root / unit_name
    unit_dir.mkdir(parents=True, exist_ok=True)
    img_dir = unit_dir / IMAGES_DIR
    img_dir.mkdir(parents=True, exist_ok=True)
    if src_media is not None:
        img_result = copy_md_images(content, [src_media], img_dir)
    else:
        img_result = ImageCopyResult(content=content)
    md_path = unit_dir / f"{unit_name}.md"
    md_path.write_text(img_result.content, encoding="utf-8")
    return unit_dir, md_path, img_result


def _record(result: SplitResult, unit_dir: Path, md_path: Path,
            title: str, img_result: ImageCopyResult) -> None:
    """登记单元结果（字符数与首行以实际写入内容为准）。"""
    text = img_result.content
    text_lines = text.splitlines()
    result.unit_dirs.append(str(unit_dir))
    result.copied += img_result.copied
    result.missing += img_result.missing
    result.units.append({
        "name": unit_dir.name,
        "title": title,
        "path": str(unit_dir),
        "file": str(md_path),
        "first_line": text_lines[0].strip() if text_lines else "",
        "chars": len(text),
    })


# ─── 试卷模式 ──────────────────────────────────────────────

def _collect_blocks(lines: list[str], qs: re.Pattern) -> list[list[str]]:
    """按题目起始行切块；加粗行（`**...**`）不算题号。"""
    blocks: list[list[str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if qs.match(line) and not line.startswith("**"):
            start = i
            j = i + 1
            while j < len(lines):
                nxt = lines[j].strip()
                if qs.match(nxt) and not nxt.startswith("**"):
                    break
                j += 1
            blocks.append(lines[start:j])
            i = j
        else:
            i += 1
    return blocks


def _assemble_exam_unit(block: list[str], idx: int, answer_mode: str,
                        end_answers: dict | None) -> list[str]:
    """按答案模式组装单题正文（去掉题号加粗壳行）。"""
    def is_title(l: str) -> bool:
        return bool(re.match(r'^\*\*.*\*\*$', l.strip()))

    if answer_mode == "inline":
        start_ans = start_exp = None
        for k, ln in enumerate(block):
            if ln.strip() == "【答案】":
                start_ans = k
            if ln.strip() == "【详解】":
                start_exp = k
        if start_ans is not None:
            stem = block[:start_ans]
            ans = block[start_ans:start_exp] if start_exp is not None else block[start_ans:]
            exp = block[start_exp:] if start_exp is not None else []
        else:
            stem, ans, exp = block, [], []
        stem = [l for l in stem if not is_title(l)]
        return stem + ans + exp

    stem = [l for l in block if not is_title(l)]
    if end_answers and idx in end_answers:
        return stem + end_answers[idx]["explanation"]
    return stem


def find_answer_section(lines: list[str]):
    """定位末尾「参考答案」区，返回 (起始行号, 从该行起的行列表)。"""
    ref_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("**") and "参考答案" in stripped:
            ref_idx = i
            break
        if "参考答案" in stripped and ("《" in stripped or not stripped.startswith("**")):
            ref_idx = i
            break
    if ref_idx is None:
        return None, []
    return ref_idx, lines[ref_idx:]


def detect_answer_mode(lines: list[str]) -> str:
    """判定答案模式：inline（随题）/ end（末尾）。"""
    qs = re.compile(r"^(\d+)．")
    ref_idx, _ = find_answer_section(lines)
    search = lines[:ref_idx] if ref_idx is not None else lines
    blocks: list[list[str]] = []
    i = 0
    while i < len(search):
        line = search[i].strip()
        if qs.match(line) and not line.startswith("**"):
            start = i
            j = i + 1
            while j < len(search):
                nxt = search[j].strip()
                if qs.match(nxt) and not nxt.startswith("**"):
                    break
                j += 1
            blocks.append(search[start:j])
            i = j
        else:
            i += 1
    if not blocks:
        return "end"
    inline_count = sum(1 for blk in blocks if any("【答案】" in l for l in blk))
    return "inline" if inline_count > len(blocks) / 2 else "end"


def parse_end_answers(answer_lines: list[str]) -> dict[int, dict]:
    """解析末尾参考答案区：题号 → {"answer": 答案, "explanation": 详解行}。"""
    if not answer_lines:
        return {}
    qa = re.compile(r'^(\d+)[.．]\s*(.*)')
    start = 0
    while start < len(answer_lines) and not qa.match(answer_lines[start].strip()):
        start += 1
    if start >= len(answer_lines):
        return {}
    result: dict[int, dict] = {}
    i = start
    while i < len(answer_lines):
        m = qa.match(answer_lines[i].strip())
        if not m:
            i += 1
            continue
        qnum = int(m.group(1))
        ans = m.group(2).strip()
        i += 1
        exp_lines = []
        while i < len(answer_lines):
            if qa.match(answer_lines[i].strip()):
                break
            exp_lines.append(answer_lines[i])
            i += 1
        if not any("【答案】" in l for l in exp_lines):
            exp_lines.insert(0, f"【答案】{ans}")
        result[qnum] = {"answer": ans, "explanation": exp_lines}
    return result


def split_exam(raw_md: str, output_root: str, base_name: str, config: dict) -> SplitResult:
    """试卷模式：按题目起始行切成 `第N题/第N题.md`，附 `images/`。

    答案两模式自动判定：inline（题干块内已有 【答案】/【详解】）原样保留；
    end（末尾「参考答案」区）按题号回填到对应题目。

    Args:
        raw_md: 源 Markdown 文件路径（也接受正文，此时不复制图片）。
        output_root: 输出根目录，单元写入 `output_root/base_name/`。
        base_name: 卷名（同时决定图片源目录前缀）。
        config: 学科配置（标准化前后的 dict 均可）。

    Returns:
        SplitResult。
    """
    base_name = (base_name or "").strip()
    raw_config = config if isinstance(config, dict) else {}
    config = _ensure_normalized(config)
    content, src_media = _load_raw(raw_md, base_name, raw_config)
    result = SplitResult()
    if not content.strip():
        result.warnings.append("源文为空，未识别到任何题目")
        return result

    qs = get_exam_question_pattern(config)
    answer_mode = detect_answer_mode(content.splitlines())
    log(f"   📋 答案模式: {'随题' if answer_mode == 'inline' else '末尾'}")
    ans_start, ans_lines = find_answer_section(content.splitlines())
    main_lines = content.splitlines()[:ans_start] if ans_start is not None else content.splitlines()
    blocks = _collect_blocks(main_lines, qs)
    if not blocks:
        result.warnings.append("未识别到任何题目")
        return result

    end_answers = parse_end_answers(ans_lines) if answer_mode == "end" else None
    target_root = Path(output_root) / base_name
    target_root.mkdir(parents=True, exist_ok=True)
    if src_media is not None and not src_media.exists():
        log(f"   🔍 图片源目录不存在: {src_media}")

    for idx, block in enumerate(blocks, start=1):
        final_lines = _assemble_exam_unit(block, idx, answer_mode, end_answers)
        unit_name = f"第{idx}题"
        unit_dir, md_path, img_result = _write_unit(
            target_root, unit_name, "\n".join(final_lines), src_media)
        _record(result, unit_dir, md_path, unit_name, img_result)
        if answer_mode == "end" and end_answers and idx not in end_answers:
            result.warnings.append(f"{unit_name} 在末尾参考答案中无对应条目")

    if result.missing:
        result.warnings.append(f"有 {result.missing} 张图片未找到")
    log(f"   📂 拆分完成: {len(result.units)} 题, 图片 {result.copied} 张")
    return result


# ─── 讲义模式（移植自 core/defaults.py） ─────────────────────

def _split_by_section_pattern(lines: list[str], section_pat: re.Pattern):
    """按 section_pattern 切分，返回 [(标题, 内容), ...]。

    第一个匹配前的内容标题为「引言」。
    """
    sections = []
    current_title = "引言"
    current_content: list[str] = []
    for line in lines:
        stripped = line.strip()
        if section_pat.match(stripped):
            if current_content:
                sections.append((current_title, "\n".join(current_content)))
            current_title = stripped
            current_content = [line]
        else:
            current_content.append(line)
    if current_content:
        sections.append((current_title, "\n".join(current_content)))
    return sections


def _split_by_title_pattern(lines: list[str], config: dict):
    """title 模式（向后兼容旧学科配置）。"""
    title_compiled = get_compiled_title_patterns(config)
    questions = []
    current_title = None
    current_content: list[str] = []
    in_question = False
    for line in lines:
        stripped = line.strip()
        is_title = any(p.match(stripped) for p in title_compiled)
        is_section = stripped.startswith("#") and not stripped.startswith("**")
        if is_title:
            if current_title is not None:
                questions.append((current_title, "\n".join(current_content)))
            current_title = stripped
            current_content = [line]
            in_question = True
        elif is_section and in_question:
            questions.append((current_title, "\n".join(current_content)))
            current_title = None
            current_content = []
            in_question = False
        else:
            if in_question:
                current_content.append(line)
    if current_title is not None:
        questions.append((current_title, "\n".join(current_content)))
    return questions


def _extract_problems_from_section(section_title: str, section_content: str,
                                   problem_pats: list[re.Pattern]):
    """从板块中提取例题为独立单元。

    匹配 problem_pats 的行作为例题边界，例题之间的内容作为知识单元。
    无标记的内联题留在知识单元中。
    """
    lines = section_content.split("\n")
    units = []
    knowledge_lines: list[str] = []
    current_problem_lines: list[str] = []
    current_problem_title = ""
    in_problem = False

    for line in lines:
        stripped = line.strip()
        is_problem = any(p.match(stripped) for p in problem_pats)
        if is_problem:
            if knowledge_lines:
                knowledge_text = "\n".join(knowledge_lines).strip()
                if knowledge_text:
                    units.append((section_title, knowledge_text))
                knowledge_lines = []
            if in_problem and current_problem_lines:
                units.append((current_problem_title, "\n".join(current_problem_lines)))
            current_problem_title = stripped
            current_problem_lines = [line]
            in_problem = True
        else:
            if in_problem:
                current_problem_lines.append(line)
            else:
                knowledge_lines.append(line)

    if knowledge_lines:
        knowledge_text = "\n".join(knowledge_lines).strip()
        if knowledge_text:
            units.append((section_title, knowledge_text))
    if in_problem and current_problem_lines:
        units.append((current_problem_title, "\n".join(current_problem_lines)))

    if not units:
        units.append((section_title, section_content))
    return units


def _merge_consecutive_headers(units, section_pat):
    """合并 ## 模块级标题到下一个单元。

    ## 模块一、## 模块二等标题只是组织结构壳，固定合并到下一个 ### 或 #### 标题单元中。
    """
    if not units:
        return units

    merged = []
    i = 0
    while i < len(units):
        title, content = units[i]
        if title.startswith("## ") and i + 1 < len(units):
            next_title, next_content = units[i + 1]
            merged_content = content + "\n" + next_content
            merged.append((next_title, merged_content))
            i += 2
        else:
            merged.append((title, content))
            i += 1

    return merged


def _drop_title_only_units(units):
    """丢弃只有标题行、无任何正文内容的空壳单元。

    判定规则：内容剥掉标题行（# 开头 / 纯 **加粗** 行）与空行后无剩余 → 丢弃。
    """
    kept = []
    for title, content in units:
        body_exists = any(
            ln.strip() and not ln.strip().startswith("#")
            and not re.fullmatch(r"\*\*[^*]+\*\*", ln.strip())
            for ln in content.splitlines()
        )
        if body_exists:
            kept.append((title, content))
    return kept


def split_lecture(raw_md: str, output_root: str, base_name: str, config: dict,
                  *, clean: bool = True) -> SplitResult:
    """讲义模式：按 section/title 规则切成 `单元N/单元N.md`，附 `images/`。

    行为契约（移植自 default_split_lecture）：
    - section 模式：section_pattern 切大板块，板块内再按例题标题提取独立单元；
    - 连续 `## ` 标题合并到下一个单元；纯标题空壳丢弃；
    - 图片源目录：`{raw_md 所在目录}/{base_name}_images/media`。

    Args:
        raw_md: 源 Markdown 文件路径（也接受正文，此时不复制图片）。
        output_root: 输出根目录，单元写入 `output_root/base_name/`。
        base_name: 文档基础名。
        config: 学科配置（标准化前后的 dict 均可）。

    Returns:
        SplitResult。
    """
    base_name = (base_name or "").strip()
    raw_config = config if isinstance(config, dict) else {}
    config = _ensure_normalized(config)
    content, src_media = _load_raw(raw_md, base_name, raw_config)
    if clean:
        from .convert import get_intent_problem_markers

        content = prepare_lecture_content(
            content, problem_markers=get_intent_problem_markers(config))
    result = SplitResult()
    if not content.strip():
        result.warnings.append("源文为空，未识别到任何单元")
        return result

    split_mode = get_lecture_split_mode(config)
    section_pat = get_section_pattern(config)
    problem_pats = get_compiled_title_patterns(config)
    lines = content.splitlines()

    if split_mode == "section" and section_pat:
        raw_sections = _split_by_section_pattern(lines, section_pat)
    else:
        raw_sections = _split_by_title_pattern(lines, config)

    if not raw_sections:
        result.warnings.append("未识别到任何单元")
        return result

    all_units = []
    for sec_title, sec_content in raw_sections:
        if problem_pats and split_mode == "section":
            all_units.extend(_extract_problems_from_section(sec_title, sec_content, problem_pats))
        else:
            all_units.append((sec_title, sec_content))

    all_units = _merge_consecutive_headers(all_units, section_pat)
    all_units = _drop_title_only_units(all_units)

    if not all_units:
        result.warnings.append("未识别到任何单元（内容可能全是纯标题壳）")
        return result

    target_root = Path(output_root) / base_name
    target_root.mkdir(parents=True, exist_ok=True)
    if src_media is not None and not src_media.exists():
        log(f"   🔍 图片源目录不存在: {src_media}")

    for idx, (title, unit_content) in enumerate(all_units, start=1):
        unit_name = f"单元{idx}"
        unit_dir, md_path, img_result = _write_unit(
            target_root, unit_name, unit_content, src_media)
        _record(result, unit_dir, md_path, title, img_result)

    if result.missing:
        result.warnings.append(f"有 {result.missing} 张图片未找到")
    log(f"   📂 拆分完成: {len(result.units)} 个单元, 图片 {result.copied} 张")
    return result


# ─── 边界切片（智能拆分用） ─────────────────────────────────

_CONTRACT_UNIT_NAME_RE = re.compile(r"^(第\d+题|板块\d+|单元\d+)$")


def _boundary_unit_name(name: str, idx: int, mode: str) -> str:
    """边界单元名：本身是契约名则沿用，否则按模式兜底命名。"""
    if name and _CONTRACT_UNIT_NAME_RE.match(name):
        return name
    return f"单元{idx}" if str(mode).lower() == "lecture" else f"第{idx}题"


def _slice_lines(lines: list[str], start_line, end_line) -> str:
    """按 1 基、含端点的行号切片；越界自动收敛，非法输入回退全篇。"""
    total = len(lines)
    if total == 0:
        return ""
    try:
        start = int(start_line) if start_line is not None else 1
    except (TypeError, ValueError):
        start = 1
    try:
        end = int(end_line) if end_line is not None else total
    except (TypeError, ValueError):
        end = total
    start = max(1, start)
    end = min(total, end)
    if start > total or end < start:
        return ""
    return "\n".join(lines[start - 1:end])


def slice_by_boundaries(raw_md: str, boundaries: list[dict], output_root: str,
                        base_name: str, mode: str = "exam",
                        *, clean: bool = True) -> SplitResult:
    """按边界清单确定性切片（智能拆分用）。

    boundaries 兼容两种写法：
    - {"name": "第1题", "start_line": 1, "end_line": 20}（1 基、含端点）
    - {"name": "第1题", "text": "..."}

    mode 决定兜底命名：`exam` → 第N题，`lecture` → 单元N；边界名本身已是契约名
    时沿用边界名。写盘纪律与 split_exam / split_lecture 完全一致。
    """
    base_name = (base_name or "").strip()
    content, src_media = _load_raw(raw_md, base_name, {})
    if clean and str(mode).lower() == "lecture":
        # 讲义边界清单必须是在同一清理后的正文上定出的行号，
        # 否则切片结果与规则拆分的单元正文不一致（切片入口没有学科配置，
        # 【出题意图】清理只能用通用标志，学科独有标志由 split 路径覆盖）。
        content = prepare_lecture_content(content)
    lines = content.splitlines()
    result = SplitResult()
    if not boundaries:
        result.warnings.append("边界清单为空")
        return result

    target_root = Path(output_root) / base_name
    target_root.mkdir(parents=True, exist_ok=True)

    for idx, boundary in enumerate(boundaries, start=1):
        if not isinstance(boundary, dict):
            result.warnings.append(f"第 {idx} 条边界不是对象，已跳过")
            continue
        name = str(boundary.get("name") or "").strip()
        if boundary.get("text") is not None:
            unit_content = str(boundary["text"])
        else:
            unit_content = _slice_lines(lines, boundary.get("start_line"),
                                        boundary.get("end_line"))
        unit_name = _boundary_unit_name(name, idx, mode)
        unit_dir, md_path, img_result = _write_unit(
            target_root, unit_name, unit_content, src_media)
        _record(result, unit_dir, md_path, name or unit_name, img_result)

    if result.missing:
        result.warnings.append(f"有 {result.missing} 张图片未找到")
    return result


# ─── 拆分预检 ──────────────────────────────────────────────

def precheck_split(paper_dir: str, *, overlong_threshold: int | None = None) -> PrecheckResult:
    """扫描卷目录，输出单元数、首行/字符数分布、空单元与超长单元。

    Args:
        paper_dir: 卷目录或输出根目录（自动兼容一层 base_name 目录）。
        overlong_threshold: 超长阈值（字符数），默认 `OVERLONG_THRESHOLD`。

    Returns:
        PrecheckResult。
    """
    root = Path(paper_dir)
    threshold = OVERLONG_THRESHOLD if overlong_threshold is None else int(overlong_threshold)
    result = PrecheckResult()
    unit_dirs = scan_unit_dirs(root)
    if not unit_dirs:
        result.warnings.append(f"未找到任何单元目录: {root}")
        return result

    lengths: list[int] = []
    for unit_dir in unit_dirs:
        src = find_source_md(unit_dir)
        text = ""
        if src is not None:
            try:
                text = src.read_text(encoding="utf-8")
            except OSError as exc:
                result.warnings.append(f"{unit_dir.name}：源文读取失败 {exc}")
        chars = len(text)
        text_lines = text.splitlines()
        empty = not text.strip()
        overlong = chars > threshold
        result.units.append({
            "name": unit_dir.name,
            "path": str(unit_dir),
            "first_line": text_lines[0].strip() if text_lines else "",
            "chars": chars,
            "empty": empty,
            "overlong": overlong,
        })
        lengths.append(chars)
        if empty:
            result.empty_units.append(unit_dir.name)
        if overlong:
            result.overlong_units.append(unit_dir.name)

    result.unit_count = len(result.units)
    if lengths:
        result.length_min = min(lengths)
        result.length_max = max(lengths)
        result.length_median = statistics.median(lengths)
    if result.empty_units:
        result.warnings.append(
            f"{len(result.empty_units)} 个空单元: {', '.join(result.empty_units)}")
    if result.overlong_units:
        result.warnings.append(
            f"{len(result.overlong_units)} 个超长单元（>{threshold} 字符）: "
            f"{', '.join(result.overlong_units)}")
    return result


# ─── 导航/封面标记（移植自 shared/split_post_utils.py） ──────

def mark_navigation_units(output_root: str, base_name: str,
                          patterns: list[str] | None = None) -> int:
    """给匹配导航/封面模式的单元目录创建 .skip_proofread（保留目录不删除）。

    首行部分匹配即命中；只读不以 `_` 开头的 md，避免误读 `_校对报告.md`。

    Returns:
        标记的单元数量。
    """
    if patterns is None:
        patterns = get_nav_patterns(None)
    nav_re = re.compile("|".join(patterns))
    target_dir = Path(output_root) / base_name
    if not target_dir.exists():
        return 0

    marked = 0
    for sub_dir in sorted(target_dir.iterdir()):
        if not sub_dir.is_dir():
            continue
        md_files = sorted(p for p in sub_dir.glob("*.md") if not p.name.startswith("_"))
        if not md_files:
            continue
        try:
            first_line = md_files[0].read_text(encoding="utf-8").split("\n")[0].strip()
        except OSError:
            continue
        if nav_re.search(first_line):
            (sub_dir / SKIP_MARKER_FILE).touch()
            marked += 1
    return marked


def is_skip_unit(unit_dir) -> bool:
    """检查单元目录是否标记为跳过校对。"""
    return (Path(unit_dir) / SKIP_MARKER_FILE).exists()

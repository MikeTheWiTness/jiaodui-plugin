"""源文件转换链：docx / md / idml → 规范命名的 _raw.md。

移植自旧仓 core/pandoc_utils.py、core/idml_extractor.py、
core/defaults.py（default_convert_file_to_md 与 md 清理/后处理系列）
以及 shared/decor_utils.py。去掉 PyInstaller 打包分支与所有 LLM/网络依赖，
行为契约逐字保留（正则与措辞不做「优化」）。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .decor_utils import strip_decor_images, strip_decor_images_from_file
from .errors import EnvError, NotFoundError, UnsupportedError
from .log import log

__all__ = [
    "ConvertResult",
    "convert_to_raw",
    "find_pandoc",
    "check_pandoc",
    "pandoc_to_docx",
    "convert_with_pandoc",
    "enhance_docx_conversion",
    "comprehensive_clean",
    "clean_md_text",
    "clean_md_file",
    "DEFAULT_INTENT_PROBLEM_MARKERS",
    "get_intent_problem_markers",
    "clean_intent_markers",
    "clean_intent_md_file",
    "fix_latex_escapes",
    "fix_latex_escapes_text",
    "normalize_caret_tilde",
    "convert_display_to_inline",
    "fix_pandoc_comment_anomaly",
    "post_process_md",
    "fix_floating_images",
    "fix_floating_images_text",
    "normalize_option_spacing",
    "normalize_option_spacing_text",
    "strip_decor_images",
    "strip_decor_images_from_file",
    "extract_idml_to_markdown",
]


# ============================================================
# 转换结果
# ============================================================


@dataclass
class ConvertResult:
    """一次源文件转换的确定性结果。

    source_kind 取值：docx / md / idml。
    """

    raw_md: str
    images_dir: str
    copied: int
    missing: int
    warnings: list[str] = field(default_factory=list)
    source_kind: str = ""


# ============================================================
# pandoc 定位与调用
# ============================================================

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _creation_flags() -> dict:
    """Windows 下隐藏子进程窗口；其余平台返回空 dict。"""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def find_pandoc() -> str | None:
    """定位 pandoc 可执行文件。

    优先环境变量 JIAODUI_PANDOC（可为命令名或绝对路径），其次 PATH，最后
    常见安装位置（GUI/agent 宿主进程的 PATH 常常不含 /usr/local/bin）。
    已去掉旧仓的 PyInstaller 打包分支。
    """
    override = os.environ.get("JIAODUI_PANDOC")
    if override:
        resolved = shutil.which(override)
        if resolved:
            return resolved
        if os.path.isfile(override):
            return override
        log(f"❌ JIAODUI_PANDOC 指向的 pandoc 不存在: {override}")
        return None
    found = shutil.which("pandoc")
    if found:
        return found
    for cand in ("/usr/local/bin/pandoc", "/opt/homebrew/bin/pandoc", "/usr/bin/pandoc"):
        if os.path.isfile(cand):
            return cand
    return None


def check_pandoc() -> bool:
    """检查 pandoc 是否可用，可用时打印版本首行。"""
    pandoc = find_pandoc()
    if not pandoc:
        log("❌ Pandoc 未安装")
        return False
    try:
        r = subprocess.run(
            [pandoc, "--version"], capture_output=True, text=True, **_creation_flags()
        )
    except (FileNotFoundError, OSError):
        log("❌ Pandoc 未安装")
        return False
    if r.returncode == 0:
        lines = (r.stdout or "").splitlines()
        if lines:
            log(f"✅ Pandoc: {lines[0]}")
        return True
    return False


def convert_with_pandoc(input_path, output_md, img_dir, use_mathjax=False):
    """docx → markdown（保留旧仓命令与参数顺序）。

    -t markdown-smart 禁用 pandoc 的「智能引号」扩展，
    防止中文弯引号被转换为英文直引号。
    """
    pandoc = find_pandoc()
    cmd = [
        pandoc, "-f", "docx", "-t", "markdown-smart",
        "--extract-media", img_dir, "--wrap", "none",
        "--markdown-headings", "atx",
    ]
    if use_mathjax:
        cmd.insert(3, "--mathjax")
    cmd.extend([input_path, "-o", output_md])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, **_creation_flags())
        return r.returncode == 0
    except Exception as e:
        log(f"   Pandoc 异常: {e}")
        return False


def pandoc_to_docx(md_path: str, docx_path: str) -> bool:
    """markdown → docx（供 docx 生成模块使用）。"""
    pandoc = find_pandoc()
    if not pandoc:
        log("❌ Pandoc 未安装，无法生成 Word")
        return False
    cmd = [pandoc, "-f", "markdown", "-t", "docx", str(md_path), "-o", str(docx_path)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, **_creation_flags())
    except (FileNotFoundError, OSError) as e:
        log(f"❌ Pandoc 生成 Word 异常: {e}")
        return False
    if r.returncode != 0:
        log(f"❌ Pandoc 生成 Word 失败: {(r.stderr or '').strip()}")
        return False
    return True


# ============================================================
# Word 格式增强（python-docx 注入着重号等标记）
# ============================================================

_FMT_MARKERS = {
    "emphasis_dot": ("<着重>", "</着重>"),
    "underline": ("<下划线>", "</下划线>"),
    "underline_wavy": ("<波浪线>", "</波浪线>"),
    "strike": ("<删除线>", "</删除线>"),
    "double_strike": ("<双删除线>", "</双删除线>"),
    "subscript": ("<下标>", "</下标>"),
    "superscript": ("<上标>", "</上标>"),
}


def _extract_special_formats(docx_path):
    """提取 Word 文档中的特殊格式位置（python-docx 缺失时返回空列表）。"""
    try:
        from docx import Document
    except (ImportError, AttributeError):
        log("⚠️ python-docx 未安装或版本不兼容，无法提取特殊格式")
        return []

    formats = []
    try:
        doc = Document(docx_path)
    except Exception as e:
        log(f"⚠️ 读取 Word 文档失败: {e}")
        return []

    for para_idx, para in enumerate(doc.paragraphs):
        pos = 0
        for run in para.runs:
            text = run.text
            if not text:
                pos += len(text)
                continue

            fmt_type = None

            # 着重号（文字下方的点）- 通过 XML 访问
            rPr = run._element.find(f".//{{{_W_NS}}}rPr")
            if rPr is not None:
                emph = rPr.find(f"{{{_W_NS}}}emph")
                if emph is not None:
                    val = emph.get(f"{{{_W_NS}}}val")
                    if val and val.lower() != "none":
                        fmt_type = "emphasis_dot"

            # 下划线 - 通过 XML 准确判断类型
            if rPr is not None:
                u = rPr.find(f"{{{_W_NS}}}u")
                if u is not None:
                    val = u.get(f"{{{_W_NS}}}val")
                    if val and val.lower() != "none":
                        if "wave" in val.lower():
                            fmt_type = "underline_wavy"
                        else:
                            fmt_type = "underline"

            # 删除线
            try:
                if run.font.strike:
                    fmt_type = "strike"
            except Exception:
                pass

            # 双删除线
            try:
                if run.font.double_strike:
                    fmt_type = "double_strike"
            except Exception:
                pass

            # 下标
            try:
                if run.font.subscript:
                    fmt_type = "subscript"
            except Exception:
                pass

            # 上标
            try:
                if run.font.superscript:
                    fmt_type = "superscript"
            except Exception:
                pass

            if fmt_type:
                formats.append({
                    "text": text,
                    "type": fmt_type,
                    "paragraph_index": para_idx,
                    "start_pos": pos,
                })

            pos += len(text)

    return formats


def _inject_format_markers(md_text, docx_path):
    """把特殊格式标记注入 Markdown（旧仓 shared/docx_format_enhancer 逻辑）。"""
    formats = _extract_special_formats(docx_path)
    if not formats:
        return md_text

    by_type = {}
    for fmt in formats:
        t = fmt["type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(fmt)

    result = md_text
    for fmt_type, fmt_list in by_type.items():
        if fmt_type not in _FMT_MARKERS:
            continue
        # ADR-0020: pandoc 已用 ^x^ / ~x~ 处理上下标，normalize_caret_tilde
        # 统一转为 <上标>/<下标>，enhancer 不再注入上下标。
        if fmt_type in ("subscript", "superscript"):
            continue
        open_marker, close_marker = _FMT_MARKERS[fmt_type]

        for fmt in fmt_list:
            text = fmt["text"].strip()
            if not text or len(text) < 1:
                continue
            if len(text) < 2 and not re.search(r'[\u4e00-\u9fff]', text):
                continue

            pattern = re.escape(text)
            matches = list(re.finditer(pattern, result))

            for m in matches:
                start = m.start()
                end = m.end()
                before = result[:start]
                after = result[end:]

                last_open = before.rfind(open_marker)
                last_close = before.rfind(close_marker)
                if last_open > last_close:
                    continue

                in_other = False
                for other_type, (other_open, other_close) in _FMT_MARKERS.items():
                    if other_type == fmt_type:
                        continue
                    o = before.rfind(other_open)
                    c = before.rfind(other_close)
                    if o > c:
                        in_other = True
                        break
                if in_other:
                    continue

                result = before + open_marker + text + close_marker + after
                break

    log(f"📝 已注入 {len(formats)} 个格式标记")
    return result


def enhance_docx_conversion(docx_path, output_md) -> bool:
    """用 python-docx 补充 pandoc 丢失的格式标记，成功返回 True。"""
    try:
        with open(output_md, encoding="utf-8") as f:
            md_text = f.read()
        enhanced = _inject_format_markers(md_text, docx_path)
        with open(output_md, "w", encoding="utf-8") as f:
            f.write(enhanced)
        return True
    except Exception as e:
        log(f"⚠️ 格式增强失败: {e}")
        return False


# ============================================================
# Markdown 清理纯函数（逐字移植 core/defaults.py）
# ============================================================


# 题目识别标志（用于【出题意图】清理等场景）。后期只需增删此列表，
# 所有引用处自动更新。格式说明：标志会在粗体包裹下匹配（即 **标志**），
# 因此只需写标志内容的正则，无需包含 ** 包裹符。
DEFAULT_INTENT_PROBLEM_MARKERS = [
    # 题目编号
    r'小试牛刀\d+',
    r'例\d+',
    r'练\d+',
    r'变式\d+',
    r'变式\d+_例\d+',
    # 分层/班型标签（含数字后缀）
    r'一本班\d+',
    r'双一流班\d+',
    r'清北班\d+',
    r'A班\d+',
    r'A\+班\d+',
    r'S班\d+',
    # 分层/班型标签（无数字后缀）
    r'一本班',
    r'一本班例题',
    r'一本班备用',
    r'双一流班',
    r'双一流班例题',
    r'双一流班备用',
    r'清北班',
    r'清北班例题',
    r'清北班备用',
    r'A班',
    r'A\+班',
    r'S班',
    # 教师版
    r'教师版',
    r'一本班教师版',
    r'双一流班教师版',
    r'清北班教师版',
]


def get_intent_problem_markers(config=None):
    """获取完整的题目识别标志列表：通用常量 + 学科 config 覆盖。

    合并策略：以 :data:`DEFAULT_INTENT_PROBLEM_MARKERS` 为基础，追加 config 中
    独有的标志（去重）。兼容新仓 `wrapped_patterns` 与旧仓
    `lecture_wrapped_patterns` 两种键名。

    Args:
        config: 学科配置 dict（可选）

    Returns:
        list[str]: 去重后的正则模式列表
    """
    markers = list(DEFAULT_INTENT_PROBLEM_MARKERS)
    if config:
        wrapped = config.get("wrapped_patterns")
        if wrapped is None:
            wrapped = config.get("lecture_wrapped_patterns")
        for pat in wrapped or []:
            if pat not in markers:
                markers.append(pat)
    return markers


def comprehensive_clean(md_content):
    """清理表格管道符与边框行，保护数学公式不被破坏。"""
    # Step 0: 保护数学公式中的 | 字符（绝对值、集合、mid 等），避免被表格清理误删
    math_blocks = []

    def _save_math(m):
        math_blocks.append(m.group(0))
        return f'\x00MATH{len(math_blocks) - 1}\x00'

    # 先保护 $...$（单行），再保护 $$...$$（多行）
    # 顺序很重要：$ 更细粒度，先匹配可以避免 $$ 误吞相邻的 $...$（如 $$=\!$ 碎片化公式）
    content = re.sub(r'\$[^$\n]+?\$', _save_math, md_content)
    content = re.sub(r'\$\$.*?\$\$', _save_math, content, flags=re.DOTALL)

    lines = content.splitlines()
    cleaned = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # 去除可能的序号前缀（如 Pandoc 转义的 "1\." 或普通 "1."）
        # 也处理嵌套表格中的前缀：| | 1\.  | +---+
        core = re.sub(r'^[\|\s]*\d+\\?\.\s*[\|\s]*', '', stripped)
        # 纯表格字符行（包含 |+-=:. 和空白），长度大于2
        if re.match(r'^[\|\+\-=\:\.\s\t]*$', core) and len(core) > 2:
            # 排除纯省略号行（只有 . 和空白），其余全部跳过
            if not re.match(r'^[\.\s]+$', core):
                i += 1
                continue
        line = re.sub(r'\|', '', line)
        if '答案:' in line:
            line = re.sub(r'[-=]+', '', line)
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if re.match(r'^[A-Z\s]+$', nxt):
                    line = line.rstrip() + ' ' + nxt
                    i += 1
        cleaned.append(line)
        i += 1
    text = '\n'.join(cleaned)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = '\n'.join(l.strip() for l in text.split('\n'))

    # Step N: 恢复数学公式
    for j, block in enumerate(math_blocks):
        text = text.replace(f'\x00MATH{j}\x00', block)
    return text.strip()


def clean_md_text(content: str) -> str:
    """文本级清理入口（comprehensive_clean 的纯函数别名）。"""
    return comprehensive_clean(content)


def fix_floating_images_text(content: str) -> str:
    """把浮到选项文字里的题图挪回独立图片行（文本级，逐字移植旧仓）。

    旧仓实现直接读写文件；新仓的讲义导入清理在正文（字符串）上进行，故抽出
    文本级核心。无命中时原样返回。
    """
    lines = content.split("\n")
    fixed = False

    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^A\.\s*!\[test\]\(([^)]+)\)\s*(\{[^}]*\})?\s*(.*)", line)
        if not m:
            i += 1
            continue

        img_path = m.group(1)
        img_attrs = m.group(2) or ""
        option_text = m.group(3)

        has_img_in_options = False
        for j in range(i, min(i + 10, len(lines))):
            if re.match(r"^[B-D]\.\s*!\[", lines[j]):
                has_img_in_options = True
                break

        if has_img_in_options:
            i += 1
            continue

        img_line = f"![]({img_path}){img_attrs}"
        if option_text:
            lines[i] = f"A.                                  {option_text}"
        else:
            lines[i] = "A.                                  "
        lines.insert(i, img_line)
        i += 2
        fixed = True

    if not fixed:
        return content
    return "\n".join(lines)


def fix_floating_images(md_file) -> bool:
    """把浮到选项文字里的题图挪回独立图片行，返回是否修改（文件包装）。"""
    with open(md_file, encoding="utf-8") as f:
        content = f.read()
    new_content = fix_floating_images_text(content)
    if new_content != content:
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    return False


def normalize_option_spacing_text(content: str) -> str:
    """把 4 个以上连续空格压缩为 2 个（文本级，逐字移植旧仓）。"""
    return re.sub(r" {4,}", "  ", content)


def normalize_option_spacing(md_file) -> bool:
    """把 4 个以上连续空格压缩为 2 个，返回是否修改（文件包装）。"""
    with open(md_file, encoding="utf-8") as f:
        content = f.read()
    new_content = normalize_option_spacing_text(content)
    if new_content != content:
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    return False


def clean_md_file(md_file) -> bool:
    """读文件 → comprehensive_clean → 写回，返回是否成功。"""
    try:
        with open(md_file, encoding="utf-8") as f:
            content = f.read()
        cleaned = clean_md_text(content)
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(cleaned)
        return True
    except Exception as e:
        log(f"   清洗失败: {e}")
        return False


def clean_intent_markers(md_content, problem_markers=None):
    """清理【出题意图】段落（逐字移植旧仓 clean_intent_markers）。

    删除【出题意图】到下一个题目编号之间的内容，包括【出题意图】本身，
    保留题目编号及其后的内容。

    Args:
        md_content: Markdown 文本
        problem_markers: 题目编号正则列表（不含 ** 包裹符），
                         默认使用 :data:`DEFAULT_INTENT_PROBLEM_MARKERS`。

    Returns:
        清理后的文本（会 strip 首尾空白）。
    """
    if problem_markers is None:
        problem_markers = DEFAULT_INTENT_PROBLEM_MARKERS

    # 构建题目编号正则：**标志1**|**标志2**|...
    # 标签不要求前导 \n 或 ^，直接在 ** 处匹配即可；
    # 标签后可跟任意内容（如来源信息 "（2026·山东青岛模拟）"），
    # 对齐 lecture_wrapped_patterns 的 ^\*\*{pattern}\*\*.*$ 规则。
    marker_union = '|'.join(problem_markers)
    pattern = r'^【出题意图】.*?(?=\*\*(?:' + marker_union + r')\*\*)'
    cleaned = re.sub(pattern, '', md_content, flags=re.DOTALL | re.MULTILINE)
    # 清理可能产生的多余空行
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def clean_intent_md_file(md_file, problem_markers=None) -> bool:
    """对 md 文件执行出题意图清理，返回是否成功（旧仓同名包装）。"""
    try:
        with open(md_file, encoding="utf-8") as f:
            content = f.read()
        cleaned = clean_intent_markers(content, problem_markers=problem_markers)
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(cleaned)
        return True
    except Exception as e:
        log(f"   出题意图清理失败: {e}")
        return False


def fix_latex_escapes_text(content: str) -> str:
    """修复 pandoc 的过度转义（文本级，逐字移植旧仓 fix_latex_escapes 五阶段）。

    分三阶段：
    1. 全局反斜杠规约（pandoc 的 \\\\ → \\，必须全局生效）
    2. 保护 $...$ / $$...$$ 数学块，避免内部 LaTeX 命令被破坏
    3. 字面替换仅作用于非数学文本；数学内部仅做安全的还原（下标、上标、分组）
    """
    # ===== Phase 1: 全局反斜杠规约（lines 33-35，安全，数学内外均需） =====
    special_chars = r'[\[\]\(\)\$_<>{}$]'
    content = re.sub(r'\\{2,}(?=' + special_chars + r')', r'\\', content)
    content = re.sub(r'\\{2,}([a-zA-Z]+)', r'\\\1', content)
    content = re.sub(r'\\{2,}([^a-zA-Z0-9])', r'\\\1', content)

    # ===== Phase 2a: 还原数学定界符 \$ → $（必须在保护数学块之前） =====
    # pandoc 把 $...$ 输出为 \$...\$，先还原定界符才能正确识别数学块
    content = content.replace(r'\$', r'$')

    # ===== Phase 2b: 保护数学块（先 $...$ 再 $$...$$，与 comprehensive_clean 一致） =====
    math_blocks = []

    def _save_math(m):
        math_blocks.append(m.group(0))
        return f'\x01MATH{len(math_blocks) - 1}\x01'

    # 先保护 $...$（单行），再保护 $$...$$（多行）
    content = re.sub(r'\$[^$\n]+?\$', _save_math, content)
    content = re.sub(r'\$\$.*?\$\$', _save_math, content, flags=re.DOTALL)

    # ===== Phase 3: 字面替换（仅影响非数学文本） =====
    content = content.replace(r'\_', '_')
    content = content.replace(r'\<', '<')
    content = content.replace(r'\>', '>')
    content = content.replace(r'\{', '{')
    content = content.replace(r'\}', '}')
    content = content.replace(r'\left\(', r'\left(')
    content = content.replace(r'\right\)', r'\right)')
    content = content.replace(r'\left\[', r'\left[')
    content = content.replace(r'\right\]', r'\right]')

    def _fix_escaped_brackets(content):
        def _repl(m):
            inner = m.group(1)
            if re.search(r'[\$\\\^_]', inner):
                return m.group(0)
            return '[' + inner + ']'
        return re.sub(r'\\\[([^\]]*?)\\\]', _repl, content)
    content = _fix_escaped_brackets(content)

    for esc, orig in [(r'\^', '^'), (r'\#', '#'), (r'\~', '~'), (r'\&', '&'),
                       (r'\%', '%'), (r'\*', '*'), (r'\+', '+'), (r'\-', '-'),
                       (r'\=', '='), (r'\|', '|'), (r'\!', '!'), (r"\'", "'")]:
        content = content.replace(esc, orig)

    # ===== Phase 4: 数学块内部的安全还原 =====
    # 只还原数学模式必需的命令（下标、上标、分组），其余 LaTeX 命令保持不动
    for i, block in enumerate(math_blocks):
        block = block.replace(r'\_', '_')   # 下标 a_1
        block = block.replace(r'\^', '^')   # 上标 x^2
        block = block.replace(r'\{', '{')   # 分组 {…}
        block = block.replace(r'\}', '}')   # 分组 {…}
        math_blocks[i] = block

    # ===== Phase 5: 还原数学块 =====
    for i, block in enumerate(math_blocks):
        content = content.replace(f'\x01MATH{i}\x01', block)

    return content


def fix_latex_escapes(md_file) -> bool:
    """读文件 → fix_latex_escapes_text → 写回，返回是否成功（与旧仓同名包装）。"""
    try:
        with open(md_file, encoding="utf-8") as f:
            content = f.read()
        fixed = fix_latex_escapes_text(content)
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(fixed)
        return True
    except Exception as e:
        log(f"   LaTeX 转义修复失败: {e}")
        return False


def fix_pandoc_comment_anomaly(content):
    """删除 pandoc 生成的空 HTML 注释残留（反引号包裹的 html 注释）。"""
    return content.replace('\x60<!-- -->\x60{=html}', '')


def normalize_caret_tilde(content):
    """将 pandoc 的 ^x^ / ~x~ 记法统一转为 <上标> / <下标> XML 标记。

    按以下顺序处理，确保 lookbehind 正确跳过 pandoc 转义号：
    1. ~x~ → <下标>x</下标>
    2. ^x^ → <上标>x</上标>
    3. 反斜杠波浪号 → 字面波浪号（还原 pandoc 转义）
    4. 反斜杠脱字号 → 字面脱字号（还原 pandoc 转义）

    顺序是关键设计：先转 ^x^，再还原转义号，避免还原后的 ^ 被误当上标语法。
    """
    # Step 1: ~x~ → <下标>x</下标>（跳过 pandoc 转义的波浪号）
    content = re.sub(
        r'(?<!\\)~([^~\s]+?)~',
        lambda m: '<下标>' + m.group(1) + '</下标>',
        content,
    )
    # Step 2: ^x^ → <上标>x</上标>（跳过 pandoc 转义的脱字号）
    content = re.sub(
        r'(?<!\\)\^([^\^\s]+?)\^',
        lambda m: '<上标>' + m.group(1) + '</上标>',
        content,
    )
    # Step 3: 还原字面波浪号
    content = content.replace(r'\~', '~')
    # Step 4: 还原字面脱字号
    content = content.replace(r'\^', '^')
    return content


def convert_display_to_inline(content):
    """把单行显示公式 $$...$$ 压成内联 $...$；跨行公式保持原样。"""

    def repl(m):
        formula = m.group(1)
        if '\n' in formula:
            return m.group(0)
        return '$' + formula + '$'

    return re.sub(r'\$\$(.+?)\$\$', repl, content, flags=re.DOTALL)


def post_process_md(md_path) -> bool:
    """对 raw.md 做通用后处理：注释残留 → 上下标 → 显示公式内联化。

    顺序固定为 fix_pandoc_comment_anomaly → normalize_caret_tilde →
    convert_display_to_inline。返回是否发生写入（内容未变化时不写回，
    避免刷新文件时间戳）。
    """
    try:
        with open(md_path, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        log(f"   ❌ 后处理读取失败: {e}")
        return False
    original = content
    content = fix_pandoc_comment_anomaly(content)
    content = normalize_caret_tilde(content)
    content = convert_display_to_inline(content)
    if content != original:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
        log("   ✅ 后处理完成")
        return True
    return False


# ============================================================
# IDML 提取（逐字移植 core/idml_extractor.py）
# ============================================================


def _get_tag(elem):
    return elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag


def _iter_all(elem):
    yield elem
    for child in elem:
        yield from _iter_all(child)


def _parse_transform(transform_str):
    parts = transform_str.split()
    if len(parts) == 6:
        return float(parts[4]), float(parts[5])
    return 0, 0


def _parse_bounds(bounds_str):
    parts = bounds_str.split()
    if len(parts) == 4:
        return [float(p) for p in parts]
    return [0, 0, 0, 0]


def _extract_stories(z):
    """提取所有 story 的段落内容和样式。"""
    story_files = [n for n in z.namelist()
                   if n.startswith('Stories/Story_') and n.endswith('.xml')]
    story_data = {}

    for sf in story_files:
        story_id = sf.replace('Stories/Story_', '').replace('.xml', '')
        story_xml = z.read(sf)
        story_root = ET.fromstring(story_xml)

        paragraphs = []
        current_chars = []
        current_style = None

        def flush():
            nonlocal current_chars, current_style
            text = ''.join(current_chars).strip()
            if text:
                paragraphs.append({
                    'text': text,
                    'style': current_style
                })
            current_chars = []

        for elem in _iter_all(story_root):
            tag = _get_tag(elem)
            if tag == 'ParagraphStyleRange':
                flush()
                style = elem.get('AppliedParagraphStyle', '')
                current_style = style.split('/')[-1] if '/' in style else style
            elif tag == 'Br':
                current_chars.append('\n')
            elif tag == 'Content' and elem.text:
                current_chars.append(elem.text)

        flush()

        if paragraphs:
            story_data[story_id] = paragraphs

    return story_data


def _get_spread_order(z):
    """从 designmap 获取 spread 顺序。"""
    dm_xml = z.read('designmap.xml')
    dm_root = ET.fromstring(dm_xml)

    spread_files = []
    for elem in _iter_all(dm_root):
        if _get_tag(elem) == 'Spread':
            src = elem.get('src', '')
            if src:
                spread_files.append(src)
    return spread_files


def _get_story_positions(z, spread_files, story_data):
    """获取每个 story 的起始位置（页码和坐标）。"""
    all_tfs = []

    def _iter_with_parent_transform(elem, parent_tx=0.0, parent_ty=0.0):
        """递归遍历元素，累加父元素的变换。"""
        tag = _get_tag(elem)

        tx, ty = _parse_transform(elem.get('ItemTransform', ''))
        abs_tx = parent_tx + tx
        abs_ty = parent_ty + ty

        if tag == 'TextFrame':
            story_id = elem.get('ParentStory', '')
            if story_id and story_id in story_data:
                tf_self = elem.get('Self', '')
                prev_tf = elem.get('PreviousTextFrame', '')
                next_tf = elem.get('NextTextFrame', '')
                yield {
                    'tf_self': tf_self,
                    'story_id': story_id,
                    'prev_tf': prev_tf,
                    'next_tf': next_tf,
                    'x': abs_tx,
                    'y': abs_ty,
                }

        for child in elem:
            if isinstance(child.tag, str):
                yield from _iter_with_parent_transform(child, abs_tx, abs_ty)

    for sf in spread_files:
        sp_xml = z.read(sf)
        sp_root = ET.fromstring(sp_xml)

        pages = []
        for elem in _iter_all(sp_root):
            if _get_tag(elem) == 'Page':
                bounds = _parse_bounds(elem.get('GeometricBounds', ''))
                tx, ty = _parse_transform(elem.get('ItemTransform', ''))
                pages.append({
                    'name': elem.get('Name'),
                    'self': elem.get('Self'),
                    'x': tx,
                    'y': ty,
                    'w': bounds[3] - bounds[1],
                    'h': bounds[2] - bounds[0],
                })

        pages.sort(key=lambda p: p['x'])

        for tf_info in _iter_with_parent_transform(sp_root):
            tx = tf_info['x']
            ty = tf_info['y']

            page_name = None
            for page in pages:
                if (page['x'] <= tx < page['x'] + page['w'] and
                        page['y'] <= ty < page['y'] + page['h']):
                    page_name = page['name']
                    break

            if page_name is None and len(pages) >= 2:
                mid_x = pages[0]['x'] + pages[0]['w']
                page_name = pages[0]['name'] if tx < mid_x else pages[1]['name']

            if page_name:
                tf_info['page_name'] = page_name
                all_tfs.append(tf_info)

    return all_tfs


def _get_story_start_info(all_tfs):
    """找出每个 story 的第一个 TextFrame（起始位置）。"""
    tf_map = {tf['tf_self']: tf for tf in all_tfs}
    story_start = {}

    for tf in all_tfs:
        story_id = tf['story_id']
        prev = tf['prev_tf']
        if prev == 'n' or prev not in tf_map:
            if story_id not in story_start:
                story_start[story_id] = {
                    'page_name': tf['page_name'],
                    'y': tf['y'],
                    'x': tf['x']
                }

    return story_start


def _page_sort_key(page_name):
    """页面排序键值。有前导零的正文在前，没有的在后。"""
    name = str(page_name)
    m = re.search(r'(\d+)', name)
    if not m:
        return (9999, 9999)

    num = int(m.group(1))
    has_leading_zero = name.strip().startswith('0') or (len(m.group(1)) >= 3)

    if has_leading_zero:
        return (0, num)
    else:
        return (1, num)


def _is_annotation_style(style):
    """判断是否是批注/旁注类样式。"""
    if not style:
        return False
    annotation_keywords = ['旁注', '小贴士', '贴士', '批注', '注释：']
    return any(k in style for k in annotation_keywords)


def _annotation_sort_priority(story_id, story_data):
    """排序优先级：正文 0，批注 1。同一行内正文在前，批注在后。"""
    paras = story_data.get(story_id, [])
    if paras and _is_annotation_style(paras[0]['style']):
        return 1
    return 0


def _sort_stories(story_start, story_data, y_bin_size=60.0):
    """对 story 进行智能排序：按页 → 按 y 分箱 → 正文在前批注在后 → 按 x。

    Args:
        story_start: 每个 story 的起始位置信息
        story_data: 每个 story 的段落数据
        y_bin_size: y 坐标分箱大小（像素），同一行内的内容放在一起

    Returns:
        排序后的 (story_id, start_info) 列表
    """
    items = list(story_start.items())

    # 先按页分组
    pages = {}
    for story_id, info in items:
        page = info['page_name']
        if page not in pages:
            pages[page] = []
        pages[page].append((story_id, info))

    result = []
    # 按页排序
    for page_name in sorted(pages.keys(), key=_page_sort_key):
        page_items = pages[page_name]

        # 找出 y 范围
        y_values = [info['y'] for _, info in page_items]
        if not y_values:
            continue
        y_min = min(y_values)
        max(y_values)

        # 按 y 分箱
        bins = {}
        for story_id, info in page_items:
            bin_key = int((info['y'] - y_min) / y_bin_size)
            if bin_key not in bins:
                bins[bin_key] = []
            bins[bin_key].append((story_id, info))

        # 每个分箱内：正文在前，批注在后；同类型按 x 排序
        for bin_key in sorted(bins.keys()):
            bin_items = bins[bin_key]
            # 按 (是否批注, x) 排序
            bin_items.sort(key=lambda item: (
                _annotation_sort_priority(item[0], story_data),
                item[1]['x']
            ))
            result.extend(bin_items)

    return result


def _classify_heading(text, style):
    """根据样式和内容判断标题级别。

    返回 None 表示不是标题，返回 1-6 表示标题级别。
    """
    if not style:
        return None

    if _is_annotation_style(style):
        return None

    style.lower()

    if style in ('第一讲', '讲内容'):
        return 1
    if style.startswith('（一）') or style.startswith('(一)'):
        return 2
    if '例文' in style and '标题' in style:
        return 3
    if '标题' in style:
        return 3

    return None


def _is_useless(text, style, prev_text=None, next_text=None):
    """判断是否是无用内容。

    纯数字短行（题号/分值如 "12" 或独立页码）需结合上下文：
    仅当前段不是题干续行（前段以句末标点结尾）且后段不是编号列表项时
    才当作独立页码过滤，避免误丢题号。
    """
    stripped = text.strip()
    if not stripped:
        return True

    if len(stripped) <= 3 and re.match(r'^\d+$', stripped):
        prev_s = (prev_text or "").strip()
        next_s = (next_text or "").strip()
        # 前段以句末标点结尾 → 数字可能是下一句的题号/分值，保留
        if prev_s and re.search(r'[。．！？!?]$', prev_s):
            return False
        # 后段以编号开头 → 当前数字是编号列表项（如 "12．下列…" 被拆段），保留
        if next_s and re.match(r'^\d+[.．、]', next_s):
            return False
        return True

    if style == 'NormalParagraphStyle' and stripped in (
        '600字', '800字', '500字', '400字', '300字', '200字'
    ):
        return True

    if len(stripped) <= 2 and re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩]+$', stripped):
        return True

    if style and '标题' in style and len(stripped) <= 2:
        if re.match(r'^[①②③④⑤⑥⑦⑧⑨⑩]+$', stripped):
            return True

    return False


def _format_paragraph(text, style):
    """将段落格式化为 Markdown。"""
    if not style:
        return text

    heading_level = _classify_heading(text, style)
    if heading_level:
        prefix = '#' * (heading_level + 1)
        return f'{prefix} {text}'

    if _is_annotation_style(style):
        lines = text.split('\n')
        non_empty = [line.strip() for line in lines if line.strip()]
        if not non_empty:
            return text
        formatted = []
        for i, line in enumerate(non_empty):
            if i == 0:
                formatted.append(f'> 💡 {line}')
            else:
                formatted.append(f'>    {line}')
        return '\n'.join(formatted)

    if style in ('注释内容', '出处'):
        lines = text.split('\n')
        return '\n'.join('> ' + line for line in lines)

    if '表格' in style and ('宋' in style or '楷' in style or '加粗' in style):
        return f'\x60{text}\x60'

    return text


def extract_idml_to_markdown(idml_path, output_md_path=None):
    """从 IDML 文件提取文本并生成 Markdown。

    Args:
        idml_path: IDML 文件路径
        output_md_path: 输出 Markdown 文件路径（可选）

    Returns:
        dict: 包含 markdown 文本、页数、段落数等信息
    """
    idml_path = str(idml_path)
    if not os.path.exists(idml_path):
        raise FileNotFoundError(f"IDML 文件不存在: {idml_path}")

    with zipfile.ZipFile(idml_path) as z:
        story_data = _extract_stories(z)
        spread_files = _get_spread_order(z)
        all_tfs = _get_story_positions(z, spread_files, story_data)
        story_start = _get_story_start_info(all_tfs)

    sorted_stories = _sort_stories(story_start, story_data, y_bin_size=60.0)

    md_lines = []
    base_name = Path(idml_path).stem
    md_lines.append(f"# {base_name}")
    md_lines.append("")

    total_paras = 0
    pages_with_content = set()

    for story_id, start_info in sorted_stories:
        paras = story_data.get(story_id, [])
        page = start_info['page_name']
        pages_with_content.add(page)

        for idx, para in enumerate(paras):
            text = para['text']
            style = para['style']

            # 取前一个非空段与后一段文本，供 _is_useless 上下文判定（题号 vs 页码）
            prev_text = ""
            for p in reversed(paras[:idx]):
                if p['text'].strip():
                    prev_text = p['text']
                    break
            next_text = ""
            for p in paras[idx + 1:]:
                if p['text'].strip():
                    next_text = p['text']
                    break

            if _is_useless(text, style, prev_text, next_text):
                continue

            md_text = _format_paragraph(text, style)
            md_lines.append(md_text)
            md_lines.append("")
            total_paras += 1

    if output_md_path:
        output_md_path = str(output_md_path)
        os.makedirs(os.path.dirname(output_md_path), exist_ok=True)
        with open(output_md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))

    return {
        'markdown': '\n'.join(md_lines),
        'page_count': len(pages_with_content),
        'paragraph_count': total_paras,
        'story_count': len(story_data),
    }


# ============================================================
# 图片归置与转换主流程
# ============================================================

_IMG_RE = re.compile(r'!\[(.*?)\]\((.*?)\)')


def _organize_images(content, source_dirs, images_dir, base, warnings):
    """把 Markdown 引用的本地图片归置到 {base}_images/media 并重写相对路径。

    返回 (新内容, copied, missing)。找不到或复制失败时保留原引用并写入 warnings。
    """
    media_dir = Path(images_dir) / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing = 0
    search_dirs = [Path(d) for d in source_dirs]

    def repl(m):
        nonlocal copied, missing
        alt = m.group(1)
        src = m.group(2).strip()
        if not src or src.lower().startswith(("http://", "https://", "data:")):
            return m.group(0)
        name = Path(src).name
        if not name:
            missing += 1
            return m.group(0)

        found = None
        if Path(src).is_absolute() and Path(src).is_file():
            found = Path(src)

        if found is None:
            for sd in search_dirs:
                try:
                    cand = sd / name
                    if cand.is_file():
                        found = cand
                        break
                    if not src.startswith(("/", "\\")):
                        cand = sd / src
                        if cand.is_file():
                            found = cand
                            break
                except OSError:
                    continue

        if found is None:
            missing += 1
            warnings.append(f"图片未找到，保留原引用：{src}")
            return m.group(0)

        dest = media_dir / name
        try:
            if not dest.exists():
                shutil.copy2(found, dest)
            elif dest.resolve() != found.resolve():
                warnings.append(f"图片重名，沿用已存在文件：{name}")
        except (OSError, shutil.Error) as e:
            missing += 1
            warnings.append(f"图片复制失败，保留原引用：{src}（{e}）")
            return m.group(0)

        copied += 1
        return f"![{alt}](./{base}_images/media/{name})"

    return _IMG_RE.sub(repl, content), copied, missing


def _convert_docx_to_raw(src, raw_md, images_dir, base, use_mathjax, warnings):
    """docx 分支：pandoc → normalize_caret_tilde → 格式增强 → 图片归置 → 后处理。"""
    if not check_pandoc():
        raise EnvError("Pandoc 未安装，无法转换 Word 文档", details={"path": str(src)})
    images_dir.mkdir(parents=True, exist_ok=True)
    ok = convert_with_pandoc(str(src), str(raw_md), str(images_dir), use_mathjax=use_mathjax)
    if not ok:
        raise EnvError("pandoc docx→markdown 转换失败", details={"path": str(src)})

    # normalize_caret_tilde 必须在 enhance 之前执行：
    # 先将 pandoc 的 ^x^/~x~ 转为 <上标>/<下标>，
    # 之后 enhancer 的 avoidance 逻辑会跳过已标记的上下标区域。
    try:
        with open(raw_md, encoding="utf-8") as f:
            content = f.read()
        content = normalize_caret_tilde(content)
        with open(raw_md, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        log(f"   ⚠️ normalize_caret_tilde 失败: {e}")

    enhance_docx_conversion(str(src), str(raw_md))

    with open(raw_md, encoding="utf-8") as f:
        content = f.read()
    content, copied, missing = _organize_images(
        content, [images_dir, raw_md.parent], images_dir, base, warnings
    )
    with open(raw_md, "w", encoding="utf-8") as f:
        f.write(content)
    post_process_md(str(raw_md))
    return copied, missing


def _convert_md_to_raw(src, raw_md, images_dir, base, warnings):
    """md 分支：复制/规范化到规范名，图片搬到 {base}_images/media 或保留报告。"""
    try:
        content = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = src.read_text(encoding="utf-8", errors="replace")
        warnings.append("源 Markdown 非 UTF-8，已按替换字符读取")

    source_dirs = [
        src.parent,
        src.parent / "images",
        src.parent / "media",
        src.parent / f"{src.stem}_images" / "media",
        images_dir,
        images_dir / "media",
        raw_md.parent,
    ]
    content, copied, missing = _organize_images(content, source_dirs, images_dir, base, warnings)
    raw_md.write_text(content, encoding="utf-8")
    post_process_md(str(raw_md))
    return copied, missing


def _convert_idml_to_raw(src, raw_md, images_dir, base, warnings):
    """idml 分支：idml_extractor 转 markdown 后走同一套 md 后处理。"""
    data = extract_idml_to_markdown(str(src), str(raw_md))
    content = data["markdown"]
    source_dirs = [src.parent, images_dir, images_dir / "media", raw_md.parent]
    content, copied, missing = _organize_images(content, source_dirs, images_dir, base, warnings)
    raw_md.write_text(content, encoding="utf-8")
    post_process_md(str(raw_md))
    return copied, missing


def convert_to_raw(src_path: str, out_dir: str, base_name: str, use_mathjax: bool = False) -> ConvertResult:
    """把源文件转换为 out_dir/{base_name}_raw.md，并归置图片。

    - docx：pandoc docx→md（图片解包到 {base}_images/media）→ normalize_caret_tilde
      → python-docx 格式增强 → 图片归置 → 通用后处理。
    - md：复制/规范化为规范名，图片搬到 {base}_images/media（搬不动则保留原引用并报告）。
    - idml：idml_extractor 转 markdown 后走同一套 md 后处理。
    - 未识别扩展名抛 UnsupportedError（结构化）。

    目标已存在时不生成 attempt 副本，直接覆盖规范名并在 warnings 中说明。
    """
    src = Path(src_path)
    if not src.is_file():
        raise NotFoundError(f"源文件不存在: {src_path}", details={"path": str(src_path)})

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    base = (base_name or src.stem).strip() or src.stem

    raw_md = out / f"{base}_raw.md"
    images_dir = out / f"{base}_images"
    warnings: list[str] = []
    if raw_md.exists():
        warnings.append(f"目标已存在，按规范名覆盖写入：{raw_md.name}")

    ext = src.suffix.lower()
    if ext in (".docx", ".doc"):
        copied, missing = _convert_docx_to_raw(src, raw_md, images_dir, base, use_mathjax, warnings)
        source_kind = "docx"
    elif ext in (".md", ".markdown"):
        copied, missing = _convert_md_to_raw(src, raw_md, images_dir, base, warnings)
        source_kind = "md"
    elif ext == ".idml":
        copied, missing = _convert_idml_to_raw(src, raw_md, images_dir, base, warnings)
        source_kind = "idml"
    else:
        raise UnsupportedError(f"不支持的文件格式: {ext}", details={"ext": ext, "path": str(src)})

    return ConvertResult(
        raw_md=str(raw_md),
        images_dir=str(images_dir),
        copied=copied,
        missing=missing,
        warnings=warnings,
        source_kind=source_kind,
    )

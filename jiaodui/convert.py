"""源文件转换链：docx / md / idml → 规范命名的 _raw.md。

移植自旧仓 core/pandoc_utils.py、core/idml_extractor.py、
core/defaults.py（default_convert_file_to_md 与 md 清理/后处理系列）
以及 shared/decor_utils.py。去掉 PyInstaller 打包分支与所有 LLM/网络依赖，
行为契约逐字保留（正则与措辞不做「优化」）。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .decor_utils import strip_decor_images, strip_decor_images_from_file
from .errors import BusinessError, EnvError, NotFoundError, UnsupportedError
from .log import log
from .paths import safe_name
from .workdir import ensure_inside, ensure_tree, input_path

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
    mode: str | None = None
    engine: str = ""
    """实际使用的转换引擎：docx（原生读取）/ pandoc / md / idml。"""
    blocks: list[dict] = field(default_factory=list)
    """原生读取的块计划（行号基于 raw.md）；供结构拆分复用。"""


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


PANDOC_TIMEOUT_SECONDS = 120
"""pandoc 子进程超时。

旧实现三处调用都没有 timeout：卡住的 pandoc 会让整条 CLI 永久挂起——没有退出码、
没有失败留痕，宿主 agent 的轮次就死在那里。同仓 check-env 早就对同一个二进制设了 10s。
"""


def _run_pandoc(cmd: list[str], timeout: int = PANDOC_TIMEOUT_SECONDS):
    """统一的 pandoc 子进程调用：固定 UTF-8 编码 + 超时。

    text=True 不固定编码时，非 UTF-8 locale 下中文诊断会变乱码，ASCII locale 下
    甚至直接抛 UnicodeDecodeError。
    """
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, **_creation_flags())


def check_pandoc() -> bool:
    """检查 pandoc 是否可用，可用时打印版本首行。"""
    pandoc = find_pandoc()
    if not pandoc:
        log("❌ Pandoc 未安装")
        return False
    try:
        r = _run_pandoc([pandoc, "--version"], timeout=10)
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
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
    output_md = str(ensure_inside(output_md))
    img_dir = str(ensure_tree(img_dir))
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
        r = _run_pandoc(cmd)
    except subprocess.TimeoutExpired:
        log(f"   Pandoc 转换超时（{PANDOC_TIMEOUT_SECONDS}s），已中止")
        return False
    except (OSError, subprocess.SubprocessError) as e:
        log(f"   Pandoc 异常: {e}")
        return False
    if r.returncode != 0:
        return False
    # 只看 returncode 不够：包装脚本/磁盘满/进程被杀都可能 exit 0 却不产文件，
    # 下游 open() 会抛裸 FileNotFoundError。
    if not Path(output_md).is_file():
        log(f"   Pandoc 报告成功但没有产出文件：{output_md}")
        return False
    return True


def pandoc_to_docx(md_path: str, docx_path: str) -> bool:
    """markdown → docx（供 docx 生成模块使用）。"""
    docx_path = str(ensure_inside(docx_path))
    pandoc = find_pandoc()
    if not pandoc:
        log("❌ Pandoc 未安装，无法生成 Word")
        return False
    cmd = [pandoc, "-f", "markdown", "-t", "docx", str(md_path), "-o", str(docx_path)]
    try:
        r = _run_pandoc(cmd)
    except subprocess.TimeoutExpired:
        log(f"❌ Pandoc 生成 Word 超时（{PANDOC_TIMEOUT_SECONDS}s），已中止")
        return False
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as e:
        log(f"❌ Pandoc 生成 Word 异常: {e}")
        return False
    if r.returncode != 0:
        log(f"❌ Pandoc 生成 Word 失败: {(r.stderr or '').strip()}")
        return False
    if not Path(docx_path).is_file():
        log(f"❌ Pandoc 报告成功但没有产出 Word：{docx_path}")
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
            # 惰性遍历：命中第一条可插入的就 break，旧实现先 list() 物化全部匹配，
            # 在文本重复出现很多次时是纯浪费（O(匹配数) 内存与时间）。
            for m in re.finditer(pattern, result):
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
            if pat in markers:
                continue
            try:
                re.compile(pat)
            except re.error:
                # 学科配置写坏一条正则不该崩掉整条讲义清理链；
                # 与 config.get_lecture_patterns 的降级口径保持一致。
                log(f"   ⚠️ 无效的题目标志正则，已跳过：{pat!r}")
                continue
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

    # Step N: 恢复数学公式。逐块 str.replace 是 O(公式数 × 全文长度)，
    # 改为单遍正则回填（行为等价）。
    if math_blocks:
        text = re.sub(r'\x00MATH(\d+)\x00',
                      lambda m: math_blocks[int(m.group(1))], text)
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
    try:
        marker_re = re.compile(r'\*\*(?:' + marker_union + r')\*\*')
    except re.error as exc:
        log(f"   ⚠️ 题目标志正则无效（{exc}），跳过出题意图清理")
        return md_content.strip()

    # 旧实现用 ^【出题意图】.*?(?=标记) 的惰性回溯：每个起点都要向后扫到某个标记
    # （没有标记时就扫到文末），k 个起点 × n 长度 = O(n²)。这里改成两次线性扫描
    # （起点、标记各一遍）+ 区间合并，语义等价。
    starts = [m.start() for m in re.finditer(r'^【出题意图】', md_content, flags=re.MULTILINE)]
    marks = [m.start() for m in marker_re.finditer(md_content)]
    spans: list[tuple[int, int]] = []
    cursor = 0
    for start in starts:
        while cursor < len(marks) and marks[cursor] <= start:
            cursor += 1
        if cursor >= len(marks):
            break  # 后面没有标记：原正则不匹配，不删
        spans.append((start, marks[cursor]))
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    pieces: list[str] = []
    last = 0
    for start, end in merged:
        pieces.append(md_content[last:start])
        last = end
    pieces.append(md_content[last:])
    cleaned = ''.join(pieces)
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
    # 同 comprehensive_clean：单遍回填代替逐块 replace。
    if math_blocks:
        content = re.sub(r'\x01MATH(\d+)\x01',
                         lambda m: math_blocks[int(m.group(1))], content)

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


IDML_MAX_ENTRY_BYTES = 32 * 1024 * 1024
"""单个 IDML 成员解压上限：261KB 的 zip 炸弹可解出 256MB（实测峰值 RSS 1GB），必须有闸门。"""
IDML_MAX_TOTAL_BYTES = 128 * 1024 * 1024
IDML_MAX_ENTRIES = 8192


def _idml_read_xml(z, name):
    """读取并解析 IDML 内的 XML 成员，畸形输入统一转成结构化契约错误。

    旧实现直接 z.read + ET.fromstring：缺成员抛 KeyError、非 XML 抛 ParseError、
    深嵌套抛 RecursionError，全部绕过「稳定退出码 + 一行结构化 JSON」的契约。
    """
    infos = z.infolist()
    if len(infos) > IDML_MAX_ENTRIES:
        raise BusinessError(f"IDML 成员数过多（{len(infos)}）", code="invalid-source",
                            details={"entries": len(infos)})
    total = sum(info.file_size for info in infos)
    if total > IDML_MAX_TOTAL_BYTES:
        raise BusinessError(
            f"IDML 解压总量过大（{total} 字节 > {IDML_MAX_TOTAL_BYTES}），拒绝处理",
            code="invalid-source", details={"total_bytes": total})
    if name not in z.namelist():
        raise BusinessError(f"IDML 缺少必需成员：{name}", code="invalid-source",
                            details={"member": name})
    info = z.getinfo(name)
    if info.file_size > IDML_MAX_ENTRY_BYTES:
        raise BusinessError(
            f"IDML 成员过大（{info.file_size} 字节 > {IDML_MAX_ENTRY_BYTES}），拒绝解压",
            code="invalid-source", details={"member": name, "size": info.file_size})
    try:
        raw = z.read(name)
    except (KeyError, zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise BusinessError(f"IDML 成员读取失败：{name}（{exc}）",
                            code="invalid-source") from exc
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise BusinessError(f"IDML 成员不是合法 XML：{name}（{exc}）",
                            code="invalid-source") from exc


def _iter_all(elem):
    """前序遍历（显式栈，不递归）：深嵌套畸形 XML 不再触发 RecursionError。"""
    stack = [elem]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(list(node)))


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
        story_root = _idml_read_xml(z, sf)

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
    dm_root = _idml_read_xml(z, 'designmap.xml')

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
        """前序遍历并累加父元素变换（显式栈，不递归）。"""
        stack = [(elem, parent_tx, parent_ty)]
        while stack:
            node, base_tx, base_ty = stack.pop()
            tag = _get_tag(node)

            tx, ty = _parse_transform(node.get('ItemTransform', ''))
            abs_tx = base_tx + tx
            abs_ty = base_ty + ty

            if tag == 'TextFrame':
                story_id = node.get('ParentStory', '')
                if story_id and story_id in story_data:
                    yield {
                        'tf_self': node.get('Self', ''),
                        'story_id': story_id,
                        'prev_tf': node.get('PreviousTextFrame', ''),
                        'next_tf': node.get('NextTextFrame', ''),
                        'x': abs_tx,
                        'y': abs_ty,
                    }

            for child in reversed(list(node)):
                if isinstance(child.tag, str):
                    stack.append((child, abs_tx, abs_ty))

    for sf in spread_files:
        sp_root = _idml_read_xml(z, sf)

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
        # 无目录部分（如 "only_name.md"）时 os.path.dirname 返回空串，
        # os.makedirs('') 会抛 FileNotFoundError；写盘也要过工作区边界。
        output_md_path = ensure_inside(output_md_path)
        output_md_path.parent.mkdir(parents=True, exist_ok=True)
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

_IMG_RE = re.compile(r'!\[([^\]\n]*)\]\(\s*([^()\n]*(?:\([^()\n]*\)[^()\n]*)*)\s*\)')
"""图片引用；目标字段允许一层括号。

pandoc 在路径含空格/括号时会写出**未用 <> 包裹**的绝对路径
（如 /private/tmp/x (v2)/a.png），非贪婪的 (.*?) 会在第一个 ) 处截断，
导致图片既没复制、宿主机绝对路径又留在产物里。
"""

_TITLE_RE = re.compile(r'''\s+(?:"[^"]*"|'[^']*')$''')
# 讲义占位图删除时连同 Pandoc 属性块处理；正常图片仍原样保留属性。
_PANDOC_IMAGE_RE = re.compile(_IMG_RE.pattern + r'(?P<attributes>\{[^{}]*\})?')


def image_destination(raw: str) -> str | None:
    """从图片引用的目标字段取出纯路径。

    支持 <...> 包裹（路径含空格时的合法写法）与引号标题；**不做空白切分**，
    否则 pandoc 写出的 /tmp/x (v2)/a.png 会被截断成 /tmp/x。
    """
    value = (raw or "").strip()
    if not value:
        return None
    if value.startswith("<"):
        end = value.find(">")
        if end <= 1:
            return None
        return value[1:end].strip() or None
    value = _TITLE_RE.sub("", value).strip()
    return value or None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# 第 6 讲样例中破图占位图的规范化 RGBA 像素指纹；只自动忽略精确匹配。
_BROKEN_IMAGE_PLACEHOLDER_SHA256 = "efc464a2d61fea8d111cd125e0365c3cfa42f359c03378f54c0a628ead16c643"


def _is_broken_image_placeholder(path: Path) -> bool:
    """匹配已确认的 Word 缺图占位图像素，不依赖文件元数据或显示尺寸。"""
    try:
        from PIL import Image

        with Image.open(path) as image:
            if image.size != (88, 106):
                return False
            rgba = image.convert("RGBA")
            fingerprint = hashlib.sha256(rgba.tobytes()).hexdigest()
            return fingerprint == _BROKEN_IMAGE_PLACEHOLDER_SHA256
    except Exception:
        return False


def _organize_images(content, source_dirs, images_dir, base, warnings, *,
                     ignore_broken_placeholders: bool = False):
    """把 Markdown 引用的本地图片归置到 {base}_images/media 并重写相对路径。

    返回 (新内容, copied, missing)。找不到或复制失败时保留原引用并写入 warnings。
    """
    media_dir = ensure_tree(Path(images_dir) / "media")
    media_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    missing = 0
    search_dirs = [Path(d) for d in source_dirs]
    assigned: dict[str, str] = {}
    """本次转换内已占用的目标名 → 内容摘要，用于识别同名不同图。"""
    search_roots: list[Path] = []
    for directory in search_dirs:
        try:
            search_roots.append(directory.resolve())
        except OSError:
            continue

    def _inside_search_dirs(path: Path) -> bool:
        """只接受允许的源目录内的图片。

        否则一份构造的 md 可以用绝对路径或 ../../ 把宿主机任意可读文件吸进材料。
        docx 分支不受影响：pandoc 的 --extract-media 目录本身就是 search_dir。
        """
        try:
            resolved = path.resolve()
        except OSError:
            return False
        return any(resolved.is_relative_to(root) for root in search_roots)

    def _digest_or_none(path: Path) -> str | None:
        try:
            return _file_sha256(path)
        except OSError:
            return None

    def repl(m):
        nonlocal copied, missing
        alt = m.group(1)
        src = image_destination(m.group(2))
        attributes = (m.group("attributes") or "") if ignore_broken_placeholders else ""
        if not src or src.lower().startswith(("http://", "https://", "data:")):
            return m.group(0)
        name = Path(src).name
        if not name:
            missing += 1
            return m.group(0)

        found = None
        if Path(src).is_absolute():
            candidate = Path(src)
            if candidate.is_file() and _inside_search_dirs(candidate):
                found = candidate

        if found is None and not src.startswith(("/", "\\")):
            # 首个目录是正文的资源基目录；裸文件名在其他目录中属于 basename 回退。
            # 带层级的引用先在所有源目录中精确查找，避免被前一个目录的同名图抢占。
            exact_dirs = search_dirs[:1] if len(Path(src).parts) == 1 else search_dirs
            for sd in exact_dirs:
                try:
                    cand = sd / src
                    if cand.is_file() and _inside_search_dirs(cand):
                        found = cand
                        break
                except OSError:
                    continue

        if found is None:
            candidates = []
            for sd in search_dirs:
                try:
                    cand = sd / name
                    if cand.is_file() and _inside_search_dirs(cand):
                        candidates.append(cand)
                except OSError:
                    continue
            if candidates:
                # basename 只作兼容回退；不同内容的候选不能任取一个冒充源图。
                digests = {_digest_or_none(cand) for cand in candidates}
                if None in digests:
                    missing += 1
                    warnings.append(f"图片候选读取失败，保留原引用：{src}")
                    return m.group(0)
                if len(digests) > 1:
                    missing += 1
                    warnings.append(f"同名图片候选内容冲突，保留原引用：{src}")
                    return m.group(0)
                found = candidates[0]

        if found is None:
            missing += 1
            if Path(src).is_absolute() and Path(src).is_file():
                warnings.append(f"图片在允许的源目录之外，未复制：{src}")
            else:
                warnings.append(f"图片未找到，保留原引用：{src}")
            return m.group(0)

        digest = _digest_or_none(found)
        if digest is None:
            missing += 1
            warnings.append(f"图片读取失败，保留原引用：{src}")
            return m.group(0)

        if ignore_broken_placeholders and _is_broken_image_placeholder(found):
            warnings.append(f"已忽略讲义 DOCX 缺图占位图：{src}")
            return ""

        # 同名不同图必须各自保留：**只对本次转换内**的同名冲突加内容哈希后缀。
        # 跨轮同名是同一材料的重转，以源为准覆盖旧图（旧实现两类都直接覆盖，
        # 于是同一次转换里的第二张会静默吃掉第一张，却仍报 copied=2）。
        dest_name = name
        seen = assigned.get(dest_name)
        if seen is not None and seen != digest:
            width = 8
            while True:
                dest_name = f"{Path(name).stem}_{digest[:width]}{Path(name).suffix}"
                current = assigned.get(dest_name)
                if current is None or current == digest:
                    break
                width += 4
        assigned[dest_name] = digest
        dest = ensure_inside(media_dir / dest_name)

        if dest.exists() and _digest_or_none(dest) == digest:
            copied += 1
            return f"![{alt}](./{base}_images/media/{dest_name}){attributes}"
        try:
            shutil.copy2(found, dest)
        except (OSError, shutil.Error) as e:
            missing += 1
            warnings.append(f"图片复制失败，保留原引用：{src}（{e}）")
            return m.group(0)

        copied += 1
        return f"![{alt}](./{base}_images/media/{dest_name}){attributes}"

    # 文本里不可能存在图片引用时直接跳过：未闭合的 "![" 会让正则在 O(n²) 上退化。
    image_pattern = _PANDOC_IMAGE_RE if ignore_broken_placeholders else _IMG_RE
    new_content = image_pattern.sub(repl, content) if '](' in content else content
    # 清理本次转换未再引用的旧图：否则重转后旧图留在材料目录，还会被
    # material.resources 登记进 conversion.resources。被引用的文件（assigned）一律保留。
    stale = [path for path in sorted(media_dir.iterdir())
             if path.is_file() and path.name not in assigned]
    for path in stale:
        try:
            path.unlink()
        except OSError as exc:
            warnings.append(f"旧图片清理失败：{path.name}（{exc}）")
    if stale:
        warnings.append(f"清理未再引用的旧图片 {len(stale)} 张")
    return new_content, copied, missing


def _native_docx_to_raw(src, raw_md, images_dir, base, warnings):
    """原生读取 docx：直接产出规范 md 与图片，返回 (图片数, 块计划)。"""
    from .docx_reader import read_docx

    media_dir = images_dir / "media"
    document = read_docx(str(src), media_dir=media_dir,
                         link_prefix=f"./{base}_images/media")
    if not document.questions:
        from .docx_reader import UnsupportedTemplate

        raise UnsupportedTemplate("未识别到题目表（固定讲义模板要求至少一道题）")
    raw_md.write_text(document.markdown, encoding="utf-8")
    referenced = {item["name"] for item in document.images}
    stale = [path for path in (media_dir.iterdir() if media_dir.is_dir() else [])
             if path.is_file() and path.name not in referenced]
    for path in stale:
        try:
            path.unlink()
        except OSError as exc:
            warnings.append(f"旧图片清理失败：{path.name}（{exc}）")
    warnings.extend(item for item in document.warnings if item not in warnings)
    blocks = [{"kind": block.kind, "level": block.level, "title": block.title,
               "start_line": block.start_line, "end_line": block.end_line}
              for block in document.blocks]
    return len(document.images), blocks


def _convert_docx_to_raw(src, raw_md, images_dir, base, use_mathjax, warnings, *,
                         mode=None, import_engine="auto"):
    """docx 公共转换后仅 exam 走试卷后处理；讲义清理留到拆分时执行。

    import_engine=auto 时优先原生读取固定模板；结构不认识、或显式要求 pandoc 时
    走 pandoc。exam 暂不启用原生读取（题号规则与讲义模板不同）。
    """
    if import_engine not in {"auto", "docx", "pandoc"}:
        from .errors import UsageError
        raise UsageError("import_engine 必须为 auto / docx / pandoc")
    if import_engine != "pandoc" and mode != "exam":
        try:
            copied, blocks = _native_docx_to_raw(src, raw_md, images_dir, base, warnings)
        except Exception as exc:
            from .docx_reader import DocxReadError, UnsupportedTemplate

            if not isinstance(exc, (UnsupportedTemplate, DocxReadError)):
                raise
            if import_engine == "docx":
                raise UnsupportedError(
                    "docx 结构不在原生模板内，无法用原生读取",
                    details={"path": str(src), "reason": str(exc)}) from exc
            warnings.append(f"原生读取不支持（{exc}），已回退 pandoc")
        else:
            return copied, 0, "docx", blocks

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
        content, [images_dir / "media", images_dir, raw_md.parent], images_dir, base, warnings,
        ignore_broken_placeholders=(mode == "lecture"),
    )
    with open(raw_md, "w", encoding="utf-8") as f:
        f.write(content)
    if mode == "exam":
        post_process_md(str(raw_md))
    return copied, missing, "pandoc", []


def _convert_md_to_raw(src, raw_md, images_dir, base, warnings, *, mode=None):
    """md 分支：复制/规范化到规范名，图片搬到 {base}_images/media 或保留报告。"""
    try:
        content = src.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = src.read_text(encoding="utf-8", errors="replace")
        warnings.append("源 Markdown 非 UTF-8，已按替换字符读取")

    # Markdown 资源只从本次输入所在目录解析；source/ 副本作为显式输入时同样适用。
    # 旧 raw 输出不是源目录，不能在原图缺失时无声补齐本次转换。
    source_dirs = [
        src.parent,
        src.parent / "images",
        src.parent / "media",
        src.parent / f"{src.stem}_images" / "media",
    ]
    content, copied, missing = _organize_images(content, source_dirs, images_dir, base, warnings)
    raw_md.write_text(content, encoding="utf-8")
    # 原始 Markdown 已有自己的格式，只归置图片，不套用 Word 后处理。
    return copied, missing


def _convert_idml_to_raw(src, raw_md, images_dir, base, warnings, *, mode=None):
    """idml 分支：提取为 Markdown 并归置图片，不重复执行 Word 后处理。"""
    data = extract_idml_to_markdown(str(src), str(raw_md))
    content = data["markdown"]
    source_dirs = [src.parent, images_dir, images_dir / "media", raw_md.parent]
    content, copied, missing = _organize_images(content, source_dirs, images_dir, base, warnings)
    raw_md.write_text(content, encoding="utf-8")
    # IDML 提取器已完成格式处理，不再套用 Word 专属后处理。
    return copied, missing


def convert_to_raw(src_path: str, out_dir: str | None = None, base_name: str | None = None,
                   use_mathjax: bool | None = None, *, mode: str | None = None,
                   import_engine: str = "auto") -> ConvertResult:
    """把源文件转换为 out_dir/{base_name}_raw.md，并归置图片。

    - docx：pandoc docx→md → normalize_caret_tilde → 格式增强 → 图片归置；
      lecture 默认启用 mathjax，exam 执行试卷后处理，未确定类型只做公共转换。
    - md：复制/规范化为规范名，图片搬到 {base}_images/media（搬不动则保留原引用并报告）。
    - idml：idml_extractor 转 markdown 后归置图片，不套用 Word 后处理。
    - 未识别扩展名抛 UnsupportedError（结构化）。

    目标已存在时不生成 attempt 副本，直接覆盖规范名并在 warnings 中说明。
    """
    if mode is not None and mode not in {"exam", "lecture"}:
        from .errors import UsageError
        raise UsageError("材料类型必须为 exam 或 lecture")
    src = input_path(src_path)
    if not src.is_file():
        raise NotFoundError(f"源文件不存在: {src_path}", details={"path": str(src_path)})

    if out_dir is None:
        from .workflow import convert_material
        return convert_material(src, base_name=base_name, use_mathjax=use_mathjax, mode=mode)
    use_mathjax = mode == "lecture" if use_mathjax is None else use_mathjax
    out = ensure_tree(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # base 会拼进输出文件名：不消毒时 base_name="../逃逸" 可以把产物写到 out_dir 之外
    # （仍在工作区内，所以 ensure_inside 拦不住）。CLI 路径本来就会消毒，这里补公开 API。
    base = safe_name((base_name or src.stem).strip() or src.stem)

    raw_md = ensure_inside(out / f"{base}_raw.md")
    images_dir = ensure_tree(out / f"{base}_images")
    if raw_md == src:
        from .errors import BusinessError
        raise BusinessError("转换输出不能覆盖源文件", code="source-overwrite")
    warnings: list[str] = []
    if raw_md.exists():
        warnings.append(f"目标已存在，按规范名覆盖写入：{raw_md.name}")

    ext = src.suffix.lower()
    if ext == ".doc":
        # 旧版二进制 .doc 不是 OOXML，pandoc 的 -f docx 必然失败。
        # 与其让用户拿到一个含糊的 pandoc 报错，不如在这里说清楚怎么处理。
        raise UnsupportedError(
            "不支持旧版 .doc 格式：请先用 Word / LibreOffice 另存为 .docx 再转换",
            details={"ext": ext, "path": str(src)})
    engine = ""
    blocks: list[dict] = []
    if ext == ".docx":
        copied, missing, engine, blocks = _convert_docx_to_raw(
            src, raw_md, images_dir, base, use_mathjax, warnings, mode=mode,
            import_engine=import_engine)
        source_kind = "docx"
    elif ext in (".md", ".markdown"):
        copied, missing = _convert_md_to_raw(src, raw_md, images_dir, base, warnings, mode=mode)
        source_kind = "md"
        engine = "md"
    elif ext == ".idml":
        copied, missing = _convert_idml_to_raw(src, raw_md, images_dir, base, warnings, mode=mode)
        source_kind = "idml"
        engine = "idml"
    else:
        raise UnsupportedError(f"不支持的文件格式: {ext}", details={"ext": ext, "path": str(src)})

    return ConvertResult(
        raw_md=str(raw_md),
        images_dir=str(images_dir),
        copied=copied,
        missing=missing,
        warnings=warnings,
        source_kind=source_kind,
        mode=mode,
        engine=engine,
        blocks=blocks,
    )

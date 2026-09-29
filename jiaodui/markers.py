"""批注与内联校对标记的正则与真实性审计（单一源）。

移植自旧仓 shared/comment_marker.py（HEAD 1c45243），去掉与 UI / api_client 的
一切耦合。四个使用点共用同一套语法：
1. docx 批注结束令牌 CMTEND{N}Z
2. XML 批注 <批注 id=N><原>…</原><改>…</改></批注>
3. 内联校对标记 【编号|原文|改为】
4. 标记真实性审计 audit_markers（重建正文与单元源文比对）
"""
from __future__ import annotations

import re
from typing import NamedTuple

# ---- 1. Word 批注结束令牌（docx 使用） ----

COMMENT_END_TOKEN_RE = re.compile(r"CMTEND(\d+)Z")
"""匹配 Word 批注占位符 CMTEND{N}Z，用于精确还原批注到原文。"""

# ---- 2. XML 批注标记（docx_report 使用） ----

XML_ANNOTATION_RE = re.compile(r"<批注\s+id=(\d+)><原>(.*?)</原><改>(.*?)</改></批注>")
"""匹配 XML 格式批注标记，含原文字段和修改字段。"""

# ---- 3. 内联校对标记 ----

INLINE_MARKER_CAPTURE_RE = re.compile(r"【(\d+)\|((?:\\\||[^|])*)\|([^】]*?)】", re.DOTALL)
"""提取内联校对标记的三个字段（编号、原文、改为）。

编号为阿拉伯数字；原文字段支持 LaTeX 转义竖线；re.DOTALL 支持跨行标记。
"""

INLINE_MARKER_DETECT_RE = INLINE_MARKER_CAPTURE_RE
"""检测是否存在内联校对标记（与 CAPTURE 同源，带 DOTALL 支持跨行）。"""

_MARKER_MASK_RE = re.compile(r"【\d+\|[^】]*】")
"""屏蔽用：匹配整个内联标记 【N|原文|改为】，扫描公式时替换为等长无 $ 占位。"""

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\u2060\ufeff]")
"""零宽字符：LLM 抄录源文时可能带入，定位比较前必须剥离。"""

MARKER_AUDIT_WINDOW = 12
"""源文比对时取标记两侧各多少字符作上下文（实测 8/12/16 结论一致）。"""

# 标记真实性判定结果
MARKER_OK = "ok"
"""原文字段能在源文定位到：真实标记。"""

MARKER_NOOP = "noop"
"""原文与改为完全相同：空操作，没有实际修正内容。"""

MARKER_EMPTY_ORIG = "empty-orig"
"""原文字段为空。"""

MARKER_RESTORE_NEW = "restore-new"
"""原文字段在源文对不上、改为字段对得上：正文该按「改为」还原。"""

MARKER_UNKNOWN = "unknown"
"""两侧都对不上（多为字段 LaTeX 装饰写法与源文不同）：无法判定，保持原样。"""

MARKER_MANUAL = "manual-review"
"""改为字段与原文无法区分（文本上无法判定）：标记为需人工确认，不拒绝。"""


class MarkerAudit(NamedTuple):
    """单个标记的真实性判定结果。"""

    num: int
    original: str
    correction: str
    verdict: str

    @property
    def render_new(self) -> bool:
        """正文该处是否应渲染「改为」而非「原文」。"""
        return self.verdict == MARKER_RESTORE_NEW

    @property
    def keep_comment(self) -> bool:
        """是否生成批注（空操作与空原文不生成）。"""
        return self.verdict not in (MARKER_NOOP, MARKER_EMPTY_ORIG)


def normalize_marker_field(text: str) -> str:
    """标记字段定位比较前的归一化：剥离零宽字符、转义美元还原为美元。

    等价写法差异（转义美元 / 零宽字符）不应让「字段能否在源文定位」误判。
    """
    return _ZERO_WIDTH_RE.sub("", text).replace("\\$", "$")


def _squeeze(text: str) -> str:
    """归一化并折叠全部空白，避免换行/空格差异破坏源文定位。"""
    return re.sub(r"\s+", "", normalize_marker_field(text))


def split_marked_body(body: str) -> str:
    """把标记插回各自「原文字段」，得到 Word 版默认渲染出的正文形状。

    用于标记审计（定位原文字段）与 verify-report 的原文完整性比对。
    """
    return INLINE_MARKER_CAPTURE_RE.sub(lambda m: m.group(2), body)


def audit_markers(body: str, source_text: str | None = None,
                  win: int = MARKER_AUDIT_WINDOW) -> list[MarkerAudit]:
    """逐个标记判定真实性：是否生成批注、正文该渲染哪一侧字段。

    判定依据是「重建正文」与单元源文的逐字比对。重建正文 = 把每个标记插回各自
    「原文字段」后的文本，也就是 Word 版默认渲染出来的正文形状，于是只有三种落点：

    - 原文字段对得上源文 → 真实标记（正文渲染原文，正常生成批注）
    - 原文字段对不上、改为字段对得上 → 源文此处就是「改为」文字，正文按改为还原
      （典型如模型凭印象写错原文字段：源文是「交于$O$点」却把原文标成「0」，
      按原文字段渲染会把原文里不存在的错误写进 Word 正文）
    - 两侧都对不上 → 无法判定，保持原样（不猜测）

    空原文字段与空操作（原文 == 改为）不依赖源文，源文缺失时依然判定。
    无法判定时不猜测：源文缺失一律返回 MARKER_UNKNOWN。
    """
    matches = list(INLINE_MARKER_CAPTURE_RE.finditer(body))
    if not matches:
        return []

    chunks: list[str] = []
    spans: list[tuple[int, int]] = []
    last = 0
    cursor = 0
    for m in matches:
        chunks.append(body[last:m.start()])
        cursor += m.start() - last
        orig = m.group(2)
        spans.append((cursor, cursor + len(orig)))
        chunks.append(orig)
        cursor += len(orig)
        last = m.end()
    chunks.append(body[last:])
    reconstructed = "".join(chunks)

    source = _squeeze(source_text) if source_text else ""
    audits: list[MarkerAudit] = []
    for m, (start, end) in zip(matches, spans):
        num = int(m.group(1))
        orig = m.group(2)
        new = m.group(3).strip()
        if not orig.strip():
            audits.append(MarkerAudit(num, orig, new, MARKER_EMPTY_ORIG))
            continue
        if orig.strip() == new:
            audits.append(MarkerAudit(num, orig, new, MARKER_NOOP))
            continue
        left = _squeeze(reconstructed[max(0, start - win):start])
        right = _squeeze(reconstructed[end:end + win])

        def _locatable(value: str) -> bool:
            needle = left + _squeeze(value) + right
            return bool(needle) and needle in source

        if not source:
            verdict = MARKER_UNKNOWN
        elif _locatable(orig):
            verdict = MARKER_OK
        elif _locatable(new):
            verdict = MARKER_RESTORE_NEW
        else:
            verdict = MARKER_UNKNOWN
        audits.append(MarkerAudit(num, orig, new, verdict))
    return audits


def scan_math_spans(text: str) -> list[tuple[int, int]]:
    """扫描行内公式 $...$ 的 [start, end) 区间列表（每行内成对配对）。

    返回全文偏移（累计行偏移），与 re.Match.start() 对齐。
    转义美元不参与配对；标记字段内部的美元先屏蔽为等长占位，避免干扰公式配对。
    """
    masked = _MARKER_MASK_RE.sub(lambda m: "【" + "X" * (len(m.group(0)) - 2) + "】", text)

    def _escaped(s: str, i: int) -> bool:
        return i > 0 and s[i - 1] == chr(92)

    def _next_dollar(s: str, start: int) -> int:
        for j in range(start, len(s)):
            if s[j] == "$" and not _escaped(s, j):
                return j
        return -1

    def _next_double(s: str, start: int) -> int:
        for j in range(start, len(s) - 1):
            if s[j] == "$" and s[j + 1] == "$" and not _escaped(s, j):
                return j
        return -1

    # 从左到右扫描：$$…$$ 视为显示公式（可跨行）；单个 $ 为行内公式。
    # 不用正则，避免把相邻的两个行内公式 `$a$$b$` 误判成一个显示公式。
    spans: list[tuple[int, int]] = []
    i, n = 0, len(masked)
    while i < n:
        if masked[i] != "$" or _escaped(masked, i):
            i += 1
            continue
        if i + 1 < n and masked[i + 1] == "$" and not _escaped(masked, i + 1):
            close = _next_double(masked, i + 2)
            if close != -1:
                spans.append((i, close + 2))
                i = close + 2
                continue
        close = _next_dollar(masked, i + 1)
        if close != -1:
            spans.append((i, close + 1))
            i = close + 1
        else:
            i += 1
    return spans

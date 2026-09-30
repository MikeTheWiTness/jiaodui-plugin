"""材料入口的只读检查：统计 Word 结构，按需返回至多 2,000 字节选。

不判断学科或材料类型，不转换、不落盘；判断由宿主按用户指定及入口规则完成。
结构扫描可以遍历 XML，但不将全文送入主 agent 上下文。
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

from .errors import BusinessError, NotFoundError, UnsupportedError, UsageError
from .workdir import input_path

MAX_PREVIEW_CHARS = 2000
_W_NAMESPACES = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}


class _Preview:
    """边扫描边截断，内存中只保留额度内文本及一个越界标志。"""

    def __init__(self, limit: int):
        self.limit = limit
        self.text = ""
        self.truncated = False

    def append(self, text: str) -> None:
        if not self.limit:
            return
        room = self.limit - len(self.text)
        self.text += text[:room]
        self.truncated |= len(text) > room


def _word_structure(source: Path, preview: _Preview) -> dict:
    stats = {"table_count": 0, "top_level_table_count": 0, "nested_table_count": 0,
             "max_table_depth": 0, "top_tables_with_nested": 0,
             "text_chars": 0, "table_text_chars": 0, "nested_table_text_chars": 0}
    in_body = False
    saw_body = False
    depth = 0
    hidden = 0
    top_has_nested = False
    with zipfile.ZipFile(source) as archive, archive.open("word/document.xml") as stream:
        for event, node in etree.iterparse(stream, events=("start", "end"),
                                            resolve_entities=False, no_network=True, load_dtd=False):
            name = etree.QName(node)
            tag = name.localname if name.namespace in _W_NAMESPACES else ""
            if event == "start":
                if tag == "body":
                    in_body = True
                    saw_body = True
                if not in_body:
                    continue
                if tag in {"del", "moveFrom"}:
                    hidden += 1
                if hidden:
                    continue
                if tag == "tbl":
                    depth += 1
                    stats["table_count"] += 1
                    stats["max_table_depth"] = max(depth, stats["max_table_depth"])
                    if depth == 1:
                        top_has_nested = False
                        stats["top_level_table_count"] += 1
                    else:
                        top_has_nested = True
                        stats["nested_table_count"] += 1
                continue
            if in_body and not hidden:
                if tag == "t":
                    text = node.text or ""
                    stats["text_chars"] += len(text)
                    if depth:
                        stats["table_text_chars"] += len(text)
                    if depth >= 2:
                        stats["nested_table_text_chars"] += len(text)
                    preview.append(text)
                elif tag in {"p", "br", "cr"}:
                    preview.append("\n")
                elif tag == "tab":
                    preview.append("\t")
                elif tag == "tbl":
                    if depth == 1 and top_has_nested:
                        stats["top_tables_with_nested"] += 1
                    depth -= 1
            if in_body and tag in {"del", "moveFrom"}:
                hidden -= 1
            if tag == "body":
                in_body = False
            # 只保留当前解析分支，不累积已遍历的正文树。
            node.clear()
            parent = node.getparent()
            if parent is not None:
                while node.getprevious() is not None:
                    del parent[0]
    if not saw_body:
        raise BusinessError("DOCX 缺少 Word 正文结构", code="invalid-source",
                            details={"path": str(source)})
    stats["nested_text_ratio"] = (stats["nested_table_text_chars"] / stats["text_chars"]
                                   if stats["text_chars"] else 0)
    return stats


def inspect_source(file: str | Path, *, preview_chars: int = 0) -> dict:
    """默认仅返回结构；只有显式请求才读出受限正文节选。"""
    if type(preview_chars) is not int or not 0 <= preview_chars <= MAX_PREVIEW_CHARS:
        raise UsageError(f"--preview-chars 必须在 0..{MAX_PREVIEW_CHARS} 之间")
    source = input_path(file)
    if not source.is_file():
        raise NotFoundError(f"源文件不存在：{source}")
    kind = source.suffix.lower().lstrip(".")
    preview = _Preview(preview_chars)
    structure = None
    warnings = []
    try:
        if kind == "docx":
            structure = _word_structure(source, preview)
        elif kind in {"md", "markdown", "txt"}:
            if preview_chars:
                with source.open(encoding="utf-8", errors="replace") as stream:
                    preview.append(stream.read(preview_chars + 1))
        elif kind in {"doc", "idml"}:
            warnings.append("此格式不能直接提供 Word 嵌套结构；不能据此判为试卷。"
                            "可检查已转换 raw 的有限节选，旧版 .doc 建议先另存为 .docx；仍不明确时询问用户。")
        else:
            raise UnsupportedError(f"不支持入口检查的格式：{source.suffix}")
    except (zipfile.BadZipFile, KeyError, etree.XMLSyntaxError, OSError) as exc:
        raise BusinessError("无法检查源文件结构", code="invalid-source",
                            details={"path": str(source), "reason": type(exc).__name__}) from exc
    return {"ok": True, "path": str(source), "source_kind": kind, "structure": structure,
            "preview": preview.text, "preview_chars": len(preview.text),
            "preview_truncated": preview.truncated, "warnings": warnings}

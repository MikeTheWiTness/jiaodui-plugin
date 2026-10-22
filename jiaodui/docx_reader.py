"""DOCX 原生读取：固定讲义模板 → 规范 Markdown（不经 pandoc）。

模板事实（2026-10 实测第 4/5/11/12 讲）：
- 顶层表格只有两类：1 行 1 列的标题表、3~6 行 1 列的题目表；
- 标题层级写在 pStyle（Heading 2/3/4），公式是 $...$ 文本，无 OMML；
- 题目表内部是布局表（题干/选项/答案解析），答案在最后几行的两列表里；
- 题目/知识讲解中可能有真正的数据表（有边框、多列多行、每行多个非空单元格），
  这些要保留成 Markdown 管道表，不能当布局表拍平。

读取结果是**校对源文**：只丢装饰图标、【出题意图】元信息行与表格脚手架，
正文文字逐字保留。识别不了的结构抛 :class:`UnsupportedTemplate`，由 convert
回退 pandoc。
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
EMU_PER_INCH = 914400

__all__ = ["Block", "DocxDocument", "DocxReadError", "UnsupportedTemplate", "read_docx"]
DECOR_INCH = 0.4

_BORDER_SIDES = ("top", "left", "bottom", "right", "insideH", "insideV")
_LAYOUT_LABEL_RE = re.compile(
    r"^(?:[A-H][.．、]?|答案[:：]?|解答[:：]?|解析[:：]?|分析[:：]?|"
    r"点睛[:：]?|方法[:：]?|点拨[:：]?|点评[:：]?|说明[:：]?)$"
)


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


class UnsupportedTemplate(Exception):
    """结构不在固定模板内：调用方应回退 pandoc。"""


class DocxReadError(Exception):
    """docx 包本身无法读取（损坏、缺部件）：调用方可回退 pandoc 由它报错。"""


@dataclass
class Block:
    kind: str                      # heading / question / paragraph
    lines: list[str]
    level: int = 0
    title: str = ""
    payload: dict = field(default_factory=dict)
    start_line: int = 0
    end_line: int = 0

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass
class DocxDocument:
    blocks: list[Block]
    markdown: str
    images: list[dict]
    warnings: list[str]
    stats: dict = field(default_factory=dict)

    @property
    def questions(self) -> list[Block]:
        return [b for b in self.blocks if b.kind == "question"]


class DocxReader:
    def __init__(self, path: str | Path, media_dir: str | Path, link_prefix: str):
        self.path = Path(path)
        self.media_dir = Path(media_dir)
        self.link_prefix = link_prefix.rstrip("/")
        self.warnings: list[str] = []
        self.images: list[dict] = []
        self._by_rel: dict[str, str] = {}
        self._data_tables = 0
        self._floating_md: set[str] = set()
        try:
            with zipfile.ZipFile(self.path) as archive:
                self._document = etree.fromstring(archive.read("word/document.xml"))
                rels = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
                self._rels = {
                    node.get("Id"): node.get("Target")
                    for node in rels.findall(f"{{{PKG}}}Relationship")
                }
                self._media_bytes: dict[str, bytes] = {}
                for name in archive.namelist():
                    if name.startswith("word/media/"):
                        self._media_bytes[name] = archive.read(name)
        except (zipfile.BadZipFile, KeyError, OSError, etree.XMLSyntaxError) as exc:
            raise DocxReadError(f"无法读取 docx 包：{exc}") from exc
        self._styles = self._load_style_levels()

    # ── 结构信息 ─────────────────────────────────────────────
    def _load_style_levels(self) -> dict[str, int]:
        with zipfile.ZipFile(self.path) as archive:
            root = etree.fromstring(archive.read("word/styles.xml"))
        raw: dict[str, tuple[int | None, str | None]] = {}
        for style in root.findall(w("style")):
            sid = style.get(w("styleId")) or ""
            lvl = style.find(f"{w('pPr')}/{w('outlineLvl')}")
            based = style.find(w("basedOn"))
            raw[sid] = (int(lvl.get(w("val"))) if lvl is not None else None,
                        based.get(w("val")) if based is not None else None)
        resolved: dict[str, int] = {}

        def resolve(sid: str, seen: set[str]) -> int | None:
            if sid in resolved:
                return resolved[sid]
            if sid not in raw or sid in seen:
                return None
            level, based = raw[sid]
            if level is not None:
                resolved[sid] = level
                return level
            value = resolve(based, seen | {sid}) if based else None
            if value is not None:
                resolved[sid] = value
            return value

        for sid in raw:
            resolve(sid, set())
        return {sid: lvl + 1 for sid, lvl in resolved.items()}

    def _paragraph_style(self, p) -> str:
        ppr = p.find(w("pPr"))
        if ppr is None:
            return ""
        style = ppr.find(w("pStyle"))
        return style.get(w("val")) if style is not None else ""

    def _heading_level(self, p) -> int:
        ppr = p.find(w("pPr"))
        if ppr is not None:
            direct = ppr.find(w("outlineLvl"))
            if direct is not None:
                return int(direct.get(w("val"))) + 1
        return self._styles.get(self._paragraph_style(p), 0)

    # ── 文本与图片 ───────────────────────────────────────────
    def _text(self, node) -> str:
        """完整文本（不保留粗体），用于标题、标签、判定。"""
        return "".join(seg for seg, _ in self._segments(node))

    def _segments(self, node) -> list[tuple[str, bool]]:
        out: list[tuple[str, bool]] = []

        def add(text: str, bold: bool = False) -> None:
            if not text:
                return
            if out and out[-1][1] == bold:
                out[-1] = (out[-1][0] + text, bold)
            else:
                out.append((text, bold))

        def walk(element, bold: bool = False) -> None:
            tag = etree.QName(element).localname if isinstance(element.tag, str) else ""
            ns = etree.QName(element).namespace if isinstance(element.tag, str) else None
            if ns == M and tag == "oMath":
                raise UnsupportedTemplate("文档含 OMML 公式，暂不支持直接解析")
            if ns == W and tag == "del":
                return
            if ns == W and tag == "r":
                rpr = element.find(w("rPr"))
                run_bold = bold
                if rpr is not None:
                    b = rpr.find(w("b"))
                    if b is not None:
                        run_bold = (b.get(w("val")) or "1").lower() not in {"0", "false", "off"}
                for child in element:
                    child_tag = etree.QName(child).localname
                    if child_tag == "t":
                        add(child.text or "", run_bold)
                    elif child_tag in {"tab"}:
                        add("\t", run_bold)
                    elif child_tag in {"br", "cr"}:
                        add("\n", run_bold)
                    elif child_tag == "drawing":
                        markdown = self._drawing_markdown(child)
                        if markdown:
                            add(markdown, False)
                    elif child_tag == "noBreakHyphen":
                        add("-", run_bold)
                return
            for child in element:
                walk(child, bold)

        walk(node)
        return out

    def _in_heading_table(self, drawing) -> bool:
        """图片是否位于 1 行 1 列、且内含标题段落的版块标题表里。"""
        node = drawing.getparent()
        while node is not None and etree.QName(node).localname != "tbl":
            node = node.getparent()
        if node is None:
            return False
        rows = node.findall(w("tr"))
        if len(rows) != 1:
            return False
        cells = rows[0].findall(w("tc"))
        if len(cells) != 1:
            return False
        def plain(paragraph) -> str:
            return "".join(node.text or "" for node in paragraph.iter(w("t"))).strip()

        return any(plain(p) and self._heading_level(p) > 0
                   for p in cells[0].findall(w("p")))

    def _drawing_markdown(self, drawing) -> str:
        extent = drawing.find(f".//{{{WP}}}extent")
        if extent is not None:
            cx, cy = int(extent.get("cx", "0")), int(extent.get("cy", "0"))
            # 只丢版块标题表里的小图标；正文里的小图可能是真实配图。
            if (cx / EMU_PER_INCH < DECOR_INCH and cy / EMU_PER_INCH < DECOR_INCH
                    and self._in_heading_table(drawing)):
                return ""
        doc_pr = drawing.find(f".//{{{WP}}}docPr")
        alt = (doc_pr.get("descr") or "").strip() if doc_pr is not None else ""
        # Word 的 descr 残留（实测全是 "test"）与校对无关，不进源文。
        if alt.lower() == "test":
            alt = ""
        alt = alt.replace("[", "\\[").replace("]", "\\]")
        floating = drawing.find(f".//{{{WP}}}anchor") is not None
        blip = drawing.find(f".//{{{A}}}blip")
        if blip is None:
            return ""
        rid = blip.get(f"{{{R}}}embed") or blip.get(f"{{{R}}}link")
        if not rid or rid not in self._rels:
            self.warnings.append("图片关系缺失，已跳过一张图")
            return ""
        name = self._materialize(rid)
        if name is None:
            return ""
        markdown = f"![{alt}]({self.link_prefix}/{name})"
        if floating:
            self._floating_md.add(markdown)
        return markdown

    def _materialize(self, rid: str) -> str | None:
        if rid in self._by_rel:
            return self._by_rel[rid]
        target = self._rels[rid]
        if re.match(r"^[a-z]+://", target, re.I):
            self.warnings.append(f"跳过远程图片：{target}")
            return None
        key = "word/" + target.lstrip("/")
        data = self._media_bytes.get(key)
        if data is None:
            key = "word/media/" + Path(target).name
            data = self._media_bytes.get(key)
        if data is None:
            self.warnings.append(f"图片实体缺失：{target}")
            return None
        name = Path(target).name
        self.media_dir.mkdir(parents=True, exist_ok=True)
        destination = self.media_dir / name
        if destination.exists() and destination.read_bytes() != data:
            import hashlib
            stem, suffix = destination.stem, destination.suffix
            name = f"{stem}_{hashlib.sha256(data).hexdigest()[:8]}{suffix}"
            destination = self.media_dir / name
        if not destination.exists():
            destination.write_bytes(data)
        self._by_rel[rid] = name
        self.images.append({"name": name, "rel": rid, "bytes": len(data)})
        return name

    # ── 表格：布局表 vs 数据表 ───────────────────────────────
    @staticmethod
    def _cell_plain_text(cell) -> str:
        """单元格纯文字（不递归嵌套表），用于结构判定。"""
        return "".join(t.text or "" for t in cell.iter(w("t"))).strip()

    @staticmethod
    def _row_width(row) -> int:
        total = 0
        for cell in row.findall(w("tc")):
            tcpr = cell.find(w("tcPr"))
            span = 1
            if tcpr is not None:
                grid = tcpr.find(w("gridSpan"))
                if grid is not None:
                    try:
                        span = max(1, int(grid.get(w("val")) or "1"))
                    except ValueError:
                        span = 1
            total += span
        return total

    def _has_visible_borders(self, table) -> bool:
        tblpr = table.find(w("tblPr"))
        if tblpr is None:
            return False
        style = tblpr.find(w("tblStyle"))
        if style is not None and "grid" in (style.get(w("val")) or "").lower():
            return True
        borders = tblpr.find(w("tblBorders"))
        if borders is None:
            return False
        for side in _BORDER_SIDES:
            edge = borders.find(w(side))
            if edge is not None and (edge.get(w("val")) or "single").lower() not in {"none", "nil"}:
                return True
        return False

    def _is_data_table(self, table) -> bool:
        """数据表判据：有边框；或排除布局标签后每行出现多个非空单元格。"""
        rows = table.findall(w("tr"))
        if len(rows) < 2:
            return False
        widths = [self._row_width(row) for row in rows]
        if not widths or max(widths) < 2:
            return False
        if self._has_visible_borders(table):
            return True
        if all(width == 2 for width in widths):
            labels = []
            for row in rows:
                cells = row.findall(w("tc"))
                if cells:
                    labels.append(self._cell_plain_text(cells[0]))
            named = [text for text in labels if text]
            if named and all(
                    _LAYOUT_LABEL_RE.match(text) or text.endswith((":", "："))
                    for text in named):
                return False
        # 2×2 选项布局表：每个单元格都以 A./B./C./D. 开头，不是数据。
        option_cells = 0
        filled_cells = 0
        for row in rows:
            for cell in row.findall(w("tc")):
                text = self._cell_plain_text(cell)
                if not text:
                    continue
                filled_cells += 1
                if re.match(r"^[A-H]s*[.．、]", text):
                    option_cells += 1
        if filled_cells and option_cells == filled_cells:
            return False
        for row in rows:
            cells = row.findall(w("tc"))
            if sum(1 for cell in cells if self._cell_plain_text(cell)) >= 2:
                return True
        return False

    def _row_cells(self, row) -> list[str]:
        cells: list[str] = []
        for cell in row.findall(w("tc")):
            tcpr = cell.find(w("tcPr"))
            span = 1
            if tcpr is not None:
                grid = tcpr.find(w("gridSpan"))
                if grid is not None:
                    try:
                        span = max(1, int(grid.get(w("val")) or "1"))
                    except ValueError:
                        span = 1
            text = "<br>".join(
                line.strip() for line in self._container_lines(cell) if line.strip())
            cells.append(self._escape_cell(text))
            cells.extend([""] * (span - 1))
        return cells

    @staticmethod
    def _escape_cell(text: str) -> str:
        """表格单元格转义：只转义数学环境外的竖线，避免破坏 |x|。"""
        out: list[str] = []
        in_math = False
        for char in text:
            if char == "$":
                in_math = not in_math
            if char == "|" and not in_math:
                out.append("\\|")
            else:
                out.append(char)
        return "".join(out)

    def _render_data_table(self, table) -> list[str]:
        rows = [self._row_cells(row) for row in table.findall(w("tr"))]
        width = max((len(row) for row in rows), default=0)
        if width < 2:
            return []
        lines = ["| " + " | ".join(row + [""] * (width - len(row))) + " |" for row in rows]
        lines.insert(1, "|" + "|".join([" --- "] * width) + "|")
        return lines

    # ── 段落渲染 ─────────────────────────────────────────────
    def _inline(self, paragraph, *, bold: bool = True) -> str:
        segments = self._segments(paragraph)
        if not bold:
            return "".join(text for text, _ in segments)
        out: list[str] = []
        open_bold = False
        in_math = False
        for text, is_bold in segments:
            for ch in text:
                if ch == "$":
                    in_math = not in_math
                want = is_bold and not in_math
                if want and not open_bold:
                    out.append("**")
                    open_bold = True
                elif not want and open_bold:
                    out.append("**")
                    open_bold = False
                out.append(ch)
        if open_bold:
            out.append("**")
        return "".join(out)

    def _paragraph_lines(self, p, *, bold: bool = True) -> list[str]:
        text = self._inline(p, bold=bold)
        return [line.rstrip() for line in text.split("\n")] if text.strip() else []

    def _container_lines(self, cell) -> list[str]:
        lines: list[str] = []
        for child in cell:
            tag = etree.QName(child).localname
            if tag == "p":
                lines.extend(self._paragraph_lines(child))
            elif tag == "tbl":
                if self._is_data_table(child):
                    rendered = self._render_data_table(child)
                    if rendered:
                        self._data_tables += 1
                        lines.extend(rendered)
                        continue
                for row in child.findall(w("tr")):
                    for inner in row.findall(w("tc")):
                        lines.extend(self._container_lines(inner))
            elif tag == "sdt":
                content = child.find(w("sdtContent"))
                if content is not None:
                    lines.extend(self._container_lines(content))
        return lines

    # ── 块解析 ───────────────────────────────────────────────
    def _heading_block(self, level: int, text: str) -> Block | None:
        text = " ".join(text.split()).strip()
        if not text:
            return None
        level = max(1, min(6, level or 4))
        return Block(kind="heading", lines=[f"{'#' * level} {text}"], level=level, title=text)

    def _parse_heading_table(self, table) -> Block | None:
        row = table.find(w("tr"))
        cell = row.find(w("tc"))
        paragraphs = cell.findall(w("p"))
        text = ""
        level = 0
        for p in paragraphs:
            value = self._text(p).strip()
            if value:
                text = value
                level = self._heading_level(p)
                break
        if not text:
            return None
        if level == 0:
            level = 4
        return self._heading_block(level, text)

    def _row_text(self, row) -> str:
        return " ".join(
            line for cell in row.findall(w("tc"))
            for line in self._container_lines(cell)
        ).strip()

    def _parse_question(self, table) -> Block:
        rows = table.findall(w("tr"))
        # 模板变体：题目行之前可能有【出题意图】等元信息行，不进入校对源文。
        start = 0
        metadata: list[str] = []
        while start < len(rows):
            text = self._row_text(rows[start])
            if text.startswith("【") and not rows[start].findall(f".//{w('tbl')}"):
                metadata.append(text)
                start += 1
                continue
            break
        if start + 2 >= len(rows):
            raise UnsupportedTemplate("题目表格行数不足（至少需要标题/题干/选项）")
        title = self._row_text(rows[start])
        if not title:
            raise UnsupportedTemplate("题目表格缺少标题行")

        stem = self._container_lines(rows[start + 1].find(w("tc")))
        option_lines: list[str] = []
        for cell in rows[start + 2].findall(w("tc")):
            option_lines.extend(self._container_lines(cell))
        options = self._group_options(option_lines)
        figures, options = self._split_floating_figures(options)
        answer = self._parse_answer_rows(rows[start + 3:])

        lines = [title]
        lines.extend(stem)
        # Word 里浮在选项单元格的题图属于题干版面，挪到选项前；
        # 行内图（选项本身是图像）保持原位。
        lines.extend(figures)
        lines.extend(options)
        lines.extend(answer)
        return Block(kind="question", lines=lines, title=title, payload={
            "stem_lines": stem, "option_lines": options, "answer_lines": answer,
            "metadata": metadata,
        })

    @staticmethod
    def _group_options(lines: list[str]) -> list[str]:
        options: list[dict] = []
        current: dict | None = None
        for line in lines:
            match = re.match(r"^([A-H])\s*[.．、]\s*(.*)$", line)
            if match:
                if current is not None:
                    options.append(current)
                current = {"letter": match.group(1), "parts": [match.group(2)] if match.group(2) else []}
            elif current is not None:
                current["parts"].append(line)
        if current is not None:
            options.append(current)
        rendered: list[str] = []
        for option in options:
            body = " ".join(part.strip() for part in option["parts"] if part.strip())
            rendered.append(f"{option['letter']}. {body}".rstrip())
        return rendered

    def _split_floating_figures(self, options: list[str]) -> tuple[list[str], list[str]]:
        """把浮在选项单元格里的题图挪到选项前；行内图保持原位。"""
        figures: list[str] = []
        kept: list[str] = []
        for line in options:
            tokens = re.findall(r"!\[[^\]]*\]\([^)]*\)", line)
            floating = [token for token in tokens if token in self._floating_md]
            if not floating:
                kept.append(line)
                continue
            for token in floating:
                figures.append(token)
                line = line.replace(token, "", 1)
            line = re.sub(r"[ \t]{2,}", " ", line).strip()
            if re.fullmatch(r"[A-H]\.", line):
                continue  # 只剩字母的空选项
            kept.append(line)
        return figures, kept

    def _parse_answer_rows(self, rows) -> list[str]:
        items: list[tuple[str, list[str]]] = []
        for row in rows:
            for cell in row.findall(w("tc")):
                inner = cell.findall(w("tbl"))
                if inner:
                    for itable in inner:
                        if self._is_data_table(itable):
                            rendered = self._render_data_table(itable)
                            if rendered:
                                self._data_tables += 1
                                items.append(("", rendered))
                            continue
                        for irow in itable.findall(w("tr")):
                            cells = irow.findall(w("tc"))
                            label = self._text(cells[0]).strip() if cells else ""
                            content = self._container_lines(cells[1]) if len(cells) > 1 else []
                            if label or content:
                                items.append((label, content))
                else:
                    content = self._container_lines(cell)
                    if content:
                        items.append(("", content))
        rendered: list[str] = []
        for label, content in items:
            content = [line for line in content if line.strip()]
            if not label and not content:
                continue
            if label and len(content) == 1 and len(content[0]) <= 80 and "\n" not in content[0]:
                rendered.append(f"{label} {content[0]}")
            else:
                if label:
                    rendered.append(label)
                rendered.extend(content)
        return rendered

    # ── 主流程 ───────────────────────────────────────────────
    def parse(self) -> DocxDocument:
        body = self._document.find(w("body"))
        if body is None:
            raise UnsupportedTemplate("缺少 Word 正文")
        blocks: list[Block] = []
        for child in body:
            tag = etree.QName(child).localname
            if tag == "p":
                level = self._heading_level(child)
                text = self._text(child)
                if level:
                    block = self._heading_block(level, text)
                else:
                    lines = self._paragraph_lines(child)
                    block = Block(kind="paragraph", lines=lines) if lines else None
            elif tag == "tbl":
                block = self._classify_table(child)
            else:
                continue
            if block is not None:
                blocks.append(block)

        markdown_lines: list[str] = []
        for block in blocks:
            if markdown_lines:
                markdown_lines.append("")
            block.start_line = len(markdown_lines) + 1
            markdown_lines.extend(block.lines)
            block.end_line = len(markdown_lines)
        markdown = "\n".join(markdown_lines).strip() + "\n"
        stats = {
            "blocks": len(blocks),
            "questions": sum(1 for block in blocks if block.kind == "question"),
            "headings": sum(1 for block in blocks if block.kind == "heading"),
            "tables": sum(1 for block in blocks if block.kind == "table"),
            "data_tables": self._data_tables,
            "images": len(self.images),
        }
        return DocxDocument(blocks=blocks, markdown=markdown, images=self.images,
                            warnings=self.warnings, stats=stats)

    def _classify_table(self, table) -> Block | None:
        rows = table.findall(w("tr"))
        cells = [len(row.findall(w("tc"))) for row in rows]
        if len(rows) == 1 and cells == [1]:
            return self._parse_heading_table(table)
        if len(rows) >= 3 and all(count == 1 for count in cells):
            return self._parse_question(table)
        if self._is_data_table(table):
            rendered = self._render_data_table(table)
            if rendered:
                self._data_tables += 1
                return Block(kind="table", lines=rendered)
        raise UnsupportedTemplate(f"未识别的表格结构：{len(rows)} 行 / 每行单元格 {cells}")


def read_docx(path: str | Path, *, media_dir: str | Path,
              link_prefix: str = "") -> DocxDocument:
    """读取 docx 并渲染规范 Markdown。

    Args:
        path: 源 .docx。
        media_dir: 图片落盘目录（通常是 raw/<材料名>_images/media）。
        link_prefix: Markdown 中图片链接前缀，不含尾部斜杠。

    Raises:
        UnsupportedTemplate: 结构不在固定模板内，调用方应回退 pandoc。
    """
    reader = DocxReader(path, media_dir, link_prefix)
    return reader.parse()

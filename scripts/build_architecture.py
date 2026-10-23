"""将架构 Markdown 生成自包含的暖纸风格 HTML 汇报。"""
from __future__ import annotations

import subprocess
from pathlib import Path

from lxml import etree, html


def main() -> None:
    """复用文档与样式源；不依赖外部字体、脚本或网络。"""
    root = Path(__file__).resolve().parent.parent
    docs = root / "docs"
    result = subprocess.run(
        [
            "pandoc", str(docs / "ARCHITECTURE.md"), "--from=markdown",
            "--to=html5", "--standalone", "--embed-resources", "--toc",
            "--toc-depth=2", f"--resource-path={docs}",
            f"--css={docs / 'architecture-assets/report.css'}",
            "--metadata=title:JiaoDuiAgentSkill 项目架构与设计", "--metadata=lang:zh-CN",
        ],
        cwd=root, check=True, capture_output=True, text=True, encoding="utf-8",
    )
    page = html.fromstring(result.stdout)
    body = page.find("body")
    assert body is not None
    masthead = etree.Element("header", {"class": "masthead"})
    meta = html.fragment_fromstring(
        '<div class="meta"><span><span class="meta__mark" aria-hidden="true">✳</span>'
        'JIAODUI · 项目汇报</span><span class="pill">架构与设计</span></div>'
    )
    masthead.append(meta)
    chapter = None
    for child in list(body):
        if child.get("id") in {"title-block-header", "TOC"}:
            continue
        if child.tag == "h1":
            body.insert(body.index(child), masthead)
        if child.tag == "h2":
            chapter = etree.Element("section", {"class": "chapter"})
            body.insert(body.index(child), chapter)
        (chapter if chapter is not None else masthead).append(child)
    masthead.append(etree.Element("hr", {"class": "rule"}))
    for table in page.xpath("//table"):
        parent = table.getparent()
        assert parent is not None
        wrap = etree.Element("div", {"class": "table-wrap", "tabindex": "0",
                                      "role": "region", "aria-label": "可滚动数据表"})
        parent.replace(table, wrap)
        wrap.append(table)
    footer = etree.Element("footer", {"class": "foot"})
    footer.text = "JiaoDuiAgentSkill · 架构与设计 · 2026-10-13"
    body.append(footer)
    (docs / "ARCHITECTURE.html").write_text(
        "<!DOCTYPE html>\n" + html.tostring(page, encoding="unicode", method="html"),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

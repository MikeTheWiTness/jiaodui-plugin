"""标题批注按 OOXML 语义定位，不依赖 Pandoc 的可选 rPr 或标签顺序。"""
from lxml import etree
import pytest

from jiaodui.docx_report import _anchor_heading_comments, _split_unit_sections

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


@pytest.mark.parametrize("paragraph", [
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>单元7</w:t></w:r></w:p>',
    '<w:p w:rsidR="001"><w:pPr><w:keepNext/><w:pStyle w:val="Heading1"/></w:pPr>'
    '<w:r><w:rPr><w:b/></w:rPr><w:t>单元7</w:t></w:r></w:p>',
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:bookmarkStart w:id="0" w:name="标题"/>'
    '<w:r><w:t>单元</w:t></w:r><w:r><w:t>7</w:t></w:r><w:bookmarkEnd w:id="0"/></w:p>',
])
def test_anchor_heading_variants(paragraph):
    text = f'<w:document xmlns:w="{W}"><w:body>{paragraph}<w:p><w:r><w:t>正文</w:t></w:r></w:p></w:body></w:document>'
    anchored = _anchor_heading_comments(text, {3: "单元7"})
    root = etree.fromstring(anchored.encode())
    heading = root.find("w:body/w:p", NS)
    assert heading.find("w:commentRangeStart", NS).get(f"{{{W}}}id") == "3"
    assert heading.find("w:commentRangeEnd", NS).get(f"{{{W}}}id") == "3"
    assert heading.find("w:r/w:commentReference", NS) is not None
    assert heading.xpath("string(.)") == "单元7"
    assert len(_split_unit_sections(anchored)) == 1


def test_body_text_is_not_mistaken_for_heading():
    text = f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>单元7</w:t></w:r></w:p></w:body></w:document>'
    assert _anchor_heading_comments(text, {1: "单元7"}) == text
    assert _split_unit_sections(text) == []


def test_multiple_heading_sections_keep_original_unit_order():
    text = (f'<w:document xmlns:w="{W}"><w:body>'
            '<w:p><w:r><w:t>卷首说明</w:t></w:r></w:p>'
            '<w:p><w:pPr><w:keepNext/><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>第1题</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>第一题正文</w:t></w:r></w:p>'
            '<w:p w:rsidR="002"><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>单元7</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>第二题正文</w:t></w:r></w:p></w:body></w:document>')
    sections = _split_unit_sections(text)
    assert len(sections) == 2
    assert "第一题正文" in sections[0] and "第二题正文" not in sections[0]
    assert "第二题正文" in sections[1] and "卷首说明" not in "".join(sections)


def test_word_without_chinese_font_keeps_formula_visible(tmp_path, monkeypatch):
    import zipfile
    from jiaodui import formula_render
    from jiaodui.docx_report import build_docx, find_pandoc
    if not find_pandoc():
        pytest.skip("需要 Pandoc")
    # 不依赖测试机器是否安装中文字体，明确覆盖 CI 所处的降级路径。
    formula_render.matplotlib_available()
    monkeypatch.setattr(formula_render, "_CJK_FONT", None)
    paper = tmp_path / "卷子"
    unit = paper / "第1题"
    unit.mkdir(parents=True)
    (unit / "第1题.md").write_text("总电动势为E。")
    (unit / "_校对报告.md").write_text(
        "一般问题\n### 标记原文\n总电动势为【1|E|$E_{总}=E_1+E_2$】。\n"
        "### 修改原因\n1. 补充总电动势关系。")
    result = build_docx(str(paper), legacy_layout=True)
    assert result.ok and result.anchor_count == 1
    with zipfile.ZipFile(result.out_path) as archive:
        text = archive.read("word/comments.xml").decode()
    assert "$E_{总}=E_1+E_2$" in text and "补充总电动势关系。" in text
    assert "<w:drawing>" not in text


def test_missing_heading_anchor_cannot_pass_delivery_audit(tmp_path, monkeypatch):
    from jiaodui import docx_report
    if not docx_report.find_pandoc():
        pytest.skip("需要 Pandoc")
    unit = tmp_path / "卷子" / "第1题"
    unit.mkdir(parents=True)
    (unit / "第1题.md").write_text("原文正确。")
    (unit / "_校对报告.md").write_text("无问题\n### 标记原文\n原文正确。\n### 修改原因\n无\n")
    monkeypatch.setattr(docx_report, "_anchor_heading_comments", lambda xml, anchors: xml)
    result = docx_report.build_docx(str(unit.parent), legacy_layout=True)
    assert result.heading_comment_count == 0
    assert not result.ok and not result.anchor_structure_ok
    assert any("无问题标题批注 0 与期望 1" in warning for warning in result.warnings)

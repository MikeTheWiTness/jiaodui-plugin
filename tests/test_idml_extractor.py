"""测试 jiaodui.convert 的 IDML 提取与段落过滤判定。

_is_useless 部分逐字移植自旧仓 tests/test_idml_extractor.py；
另加合成 IDML 压缩包的端到端提取用例。
"""
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jiaodui.convert import _is_useless, extract_idml_to_markdown


class TestIsUseless(unittest.TestCase):
    """回归：≤3 位纯数字行不得无条件当页码丢弃（题号"12"被误删）。"""

    def test_short_number_between_sentences_kept(self):
        """前段以句末标点结尾 → 数字是下一句的题号/分值，保留"""
        self.assertFalse(_is_useless("12", "NormalParagraphStyle",
                                     prev_text="阅读下面的文字，完成下面小题。",
                                     next_text="下列对文中画波浪线部分的断句"))

    def test_short_number_before_numbered_item_kept(self):
        """后段以编号开头 → 当前数字是编号列表项，保留"""
        self.assertFalse(_is_useless("12", "NormalParagraphStyle",
                                     prev_text="非题干续行",
                                     next_text="12．下列对文中加点词"))

    def test_short_number_isolated_is_page_number(self):
        """前后均非句末/编号上下文 → 独立页码，过滤"""
        self.assertTrue(_is_useless("12", "NormalParagraphStyle",
                                    prev_text="正文结束没有句末标点",
                                    next_text="下一段开始"))

    def test_short_number_no_context_filtered(self):
        """无上下文信息时保持原行为（当页码过滤）"""
        self.assertTrue(_is_useless("12", "NormalParagraphStyle"))

    def test_four_digit_year_kept(self):
        """4 位数字（年份）不受影响"""
        self.assertFalse(_is_useless("2026", "NormalParagraphStyle"))

    def test_empty_text(self):
        self.assertTrue(_is_useless("  ", "NormalParagraphStyle"))
        self.assertTrue(_is_useless("", "NormalParagraphStyle"))

    def test_word_count_rules(self):
        """字数要求行（600字等）过滤"""
        self.assertTrue(_is_useless("600字", "NormalParagraphStyle"))
        self.assertTrue(_is_useless("800字", "NormalParagraphStyle"))

    def test_circle_number_rules(self):
        """圆圈序号短行过滤"""
        self.assertTrue(_is_useless("①", "NormalParagraphStyle"))
        self.assertTrue(_is_useless("①②", "NormalParagraphStyle"))

    def test_normal_text_kept(self):
        self.assertFalse(_is_useless("这是一段正常的正文内容。", "NormalParagraphStyle"))


DESIGNMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Document>
  <Spread src="Spreads/Spread_a.xml" />
</Document>
"""

SPREAD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Spread>
  <Page Name="01" Self="p1" GeometricBounds="0 0 600 800" ItemTransform="1 0 0 1 0 0" />
  <TextFrame ParentStory="story1" Self="tf1" PreviousTextFrame="n" NextTextFrame="n" ItemTransform="1 0 0 1 10 10" />
</Spread>
"""

STORY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Story>
  <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/正文">
    <Content>你好世界</Content>
  </ParagraphStyleRange>
  <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/一级标题">
    <Content>第一讲</Content>
  </ParagraphStyleRange>
  <ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/正文">
    <Content>12</Content>
  </ParagraphStyleRange>
</Story>
"""


def _make_idml(path: Path) -> Path:
    """合成一个最小可解析的 IDML 压缩包。"""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("designmap.xml", DESIGNMAP_XML)
        z.writestr("Spreads/Spread_a.xml", SPREAD_XML)
        z.writestr("Stories/Story_story1.xml", STORY_XML)
    return path


class TestExtractIdmlToMarkdown:
    """合成 IDML 的端到端提取（页数/段落数/story 数/标题层级）。"""

    def test_extract_returns_counts(self, tmp_path):
        idml = _make_idml(tmp_path / "讲义.idml")
        data = extract_idml_to_markdown(str(idml))
        assert data["story_count"] == 1
        assert data["page_count"] == 1
        # "12" 在无题号上下文时按页码过滤 → 只保留 2 段
        assert data["paragraph_count"] == 2
        assert "你好世界" in data["markdown"]
        assert "#### 第一讲" in data["markdown"]
        assert data["markdown"].startswith("# 讲义")

    def test_extract_writes_output_file(self, tmp_path):
        idml = _make_idml(tmp_path / "讲义.idml")
        out = tmp_path / "out" / "讲义_raw.md"
        extract_idml_to_markdown(str(idml), str(out))
        assert out.is_file()
        assert "你好世界" in out.read_text(encoding="utf-8")

    def test_missing_file_raises(self, tmp_path):
        try:
            extract_idml_to_markdown(str(tmp_path / "nope.idml"))
        except FileNotFoundError:
            return
        raise AssertionError("缺失 IDML 应抛 FileNotFoundError")


if __name__ == "__main__":
    unittest.main()

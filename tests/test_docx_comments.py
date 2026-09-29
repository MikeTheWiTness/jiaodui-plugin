import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jiaodui.docx_comments import (
    extract_comment_anchors,
    fuzzy_insert_comment,
    inject_comment_placeholders,
    insert_comments_into_md,
    normalize_text,
    parse_comments_xml,
    replace_comment_placeholders,
)


class TestParseCommentsXml(unittest.TestCase):
    def test_single_comment(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0" w:author="张三" w:date="2026-01-01T00:00:00Z" w:initials="">
    <w:p>
      <w:r><w:t>这是第一条批注</w:t></w:r>
    </w:p>
  </w:comment>
</w:comments>'''
        comments = parse_comments_xml(xml)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments["0"], "这是第一条批注")

    def test_multiple_comments(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0" w:author="A">
    <w:p><w:r><w:t>批注一</w:t></w:r></w:p>
  </w:comment>
  <w:comment w:id="1" w:author="B">
    <w:p><w:r><w:t>批注二</w:t></w:r></w:p>
  </w:comment>
  <w:comment w:id="2" w:author="C">
    <w:p><w:r><w:t>批注三</w:t></w:r></w:p>
  </w:comment>
</w:comments>'''
        comments = parse_comments_xml(xml)
        self.assertEqual(len(comments), 3)
        self.assertEqual(comments["0"], "批注一")
        self.assertEqual(comments["1"], "批注二")
        self.assertEqual(comments["2"], "批注三")

    def test_comment_with_multiple_runs(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0" w:author="A">
    <w:p>
      <w:r><w:t>第一段</w:t></w:r>
      <w:r><w:t>第二段</w:t></w:r>
    </w:p>
  </w:comment>
</w:comments>'''
        comments = parse_comments_xml(xml)
        self.assertIn("第一段", comments["0"])
        self.assertIn("第二段", comments["0"])

    def test_empty_comments(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
</w:comments>'''
        comments = parse_comments_xml(xml)
        self.assertEqual(comments, {})


class TestExtractCommentAnchors(unittest.TestCase):
    def test_single_anchor(self):
        doc_xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>前面文字</w:t></w:r>
      <w:commentRangeStart w:id="0"/>
      <w:r><w:t>锚定文本</w:t></w:r>
      <w:commentRangeEnd w:id="0"/>
      <w:r><w:commentReference w:id="0"/></w:r>
      <w:r><w:t>后面文字</w:t></w:r>
    </w:p>
  </w:body>
</w:document>'''
        anchors = extract_comment_anchors(doc_xml)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors[0]["id"], "0")
        self.assertEqual(anchors[0]["text"], "锚定文本")

    def test_multiple_anchors(self):
        doc_xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:commentRangeStart w:id="0"/>
      <w:r><w:t>第一个锚点</w:t></w:r>
      <w:commentRangeEnd w:id="0"/>
      <w:r><w:commentReference w:id="0"/></w:r>
      <w:r><w:t>中间</w:t></w:r>
      <w:commentRangeStart w:id="1"/>
      <w:r><w:t>第二个锚点</w:t></w:r>
      <w:commentRangeEnd w:id="1"/>
      <w:r><w:commentReference w:id="1"/></w:r>
    </w:p>
  </w:body>
</w:document>'''
        anchors = extract_comment_anchors(doc_xml)
        self.assertEqual(len(anchors), 2)
        self.assertEqual(anchors[0]["id"], "0")
        self.assertEqual(anchors[0]["text"], "第一个锚点")
        self.assertEqual(anchors[1]["id"], "1")
        self.assertEqual(anchors[1]["text"], "第二个锚点")

    def test_no_anchors(self):
        doc_xml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>纯文本无批注</w:t></w:r></w:p></w:body>
</w:document>'''
        anchors = extract_comment_anchors(doc_xml)
        self.assertEqual(anchors, [])


class TestInsertCommentsIntoMd(unittest.TestCase):
    def test_single_comment_insertion(self):
        md = "这是一段文字，其中有个错别字。"
        comments = {"0": "应该是'错别宇'吗？不对，应该是'错别字'才对"}
        anchors = [{"id": "0", "text": "错别字"}]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertIn('<批注 id=1>', result)
        self.assertIn("错别字", result)

    def test_multiple_comments(self):
        md = "春天来了，花儿开了，小鸟在树上唱歌。"
        comments = {"0": "是'春天'还是'春季'？", "1": "应该是'鸟儿'吧"}
        anchors = [{"id": "0", "text": "春天"}, {"id": "1", "text": "小鸟"}]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertIn("批注 id=1", result)
        self.assertIn("批注 id=2", result)

    def test_no_comments_returns_original(self):
        md = "纯文本没有批注"
        comments = {}
        anchors = []
        result = insert_comments_into_md(md, comments, anchors)
        self.assertEqual(result, md)

    def test_anchor_not_found_skip(self):
        md = "这段文字里找不到锚点"
        comments = {"0": "这条批注找不到位置"}
        anchors = [{"id": "0", "text": "不存在的文本"}]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertEqual(result, md)


class TestExtractCommentsToMd(unittest.TestCase):
    def test_function_exists(self):
        from jiaodui.docx_comments import extract_comments_to_md
        self.assertTrue(callable(extract_comments_to_md))

    def test_nonexistent_file_returns_false(self):

        from jiaodui.docx_comments import extract_comments_to_md
        result = extract_comments_to_md("/nonexistent/path.docx", "/tmp/out.md")
        self.assertFalse(result)


class TestEdgeCases(unittest.TestCase):
    def test_comment_id_not_in_dict_skipped(self):
        md = "正文内容"
        comments = {"99": "这条批注没有对应锚点"}
        anchors = [{"id": "0", "text": "不存在"}]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertEqual(result, md)

    def test_anchor_with_empty_text_skipped(self):
        md = "正文"
        comments = {"0": "空锚点批注"}
        anchors = [{"id": "0", "text": ""}]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertEqual(result, md)

    def test_multiple_occurrences_only_first(self):
        md = "苹果香蕉苹果橙子苹果"
        comments = {"0": "第一个苹果的批注"}
        anchors = [{"id": "0", "text": "苹果"}]
        result = insert_comments_into_md(md, comments, anchors)
        count = result.count("批注 id=1")
        self.assertEqual(count, 1)

    def test_comment_numbering_sequential(self):
        md = "甲乙丙丁"
        comments = {"0": "批注A", "1": "批注B", "2": "批注C"}
        anchors = [
            {"id": "0", "text": "甲"},
            {"id": "1", "text": "乙"},
            {"id": "2", "text": "丙"},
        ]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertIn("批注 id=1", result)
        self.assertIn("批注 id=2", result)
        self.assertIn("批注 id=3", result)


class TestShortAnchorCollision(unittest.TestCase):
    """短数字锚点不应匹配已插入 <批注 id=N> 标记内部的数字。

    回归 bug：题号批注锚点为单数字 "9"，replace("9",...) 命中已插入
    <批注 id=9> 标记里的 "9"，把新批注插进旧标记开标签，产出
    <批注 id=9<批注 id=38>... 破损嵌套，且批注错位到第1题。
    """

    def test_minimal_digit_anchor_not_nested_into_marker(self):
        # 甲→id=1，锚点 "1" 应命中 body "1"，不命中 <批注 id=1> 里的 "1"
        md = "甲1乙"
        comments = {"a": "批注甲", "b": "批注一"}
        anchors = [
            {"id": "a", "text": "甲", "pos": 0},
            {"id": "b", "text": "1", "pos": 10},
        ]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertNotIn("<批注 id=1<批注", result, "短数字锚点不应嵌进已插入标记")
        self.assertIn("<批注 id=1><原>甲</原>", result)
        self.assertIn("<批注 id=2><原>1</原>", result)
        self.assertEqual(result.count("<批注 id=1><原>甲</原>"), 1)
        self.assertEqual(result.count("<批注 id=2><原>1</原>"), 1)

    def test_realistic_digit9_anchor_after_id9_marker(self):
        # 复刻真实 bug：第9个批注(壬)编号 id=9，后续单数字 "9" 锚点
        md = "甲乙丙丁戊己庚辛壬9题"
        chars = list("甲乙丙丁戊己庚辛壬")
        comments = {str(i): f"批注{c}" for i, c in enumerate(chars)}
        comments["9"] = "题号批注"
        anchors = [{"id": str(i), "text": c, "pos": i} for i, c in enumerate(chars)]
        anchors.append({"id": "9", "text": "9", "pos": 100})
        result = insert_comments_into_md(md, comments, anchors)
        self.assertNotIn("<批注 id=9<批注", result, "锚点 '9' 不应嵌进 <批注 id=9> 标记")
        self.assertIn("<批注 id=9><原>壬</原>", result)   # 第9个批注完整
        self.assertIn("<批注 id=10><原>9</原>", result)   # 题号批注独立、在 body "9" 处

    def test_digit_anchor_absent_from_body_not_misinserted(self):
        # 锚点 "1" 不在 body 里（只在已插入 <批注 id=1> 标记内）→ 不应错插，应跳过
        md = "甲乙"
        comments = {"a": "批注甲", "b": "找不到的批注"}
        anchors = [
            {"id": "a", "text": "甲", "pos": 0},
            {"id": "b", "text": "1", "pos": 10},
        ]
        result = insert_comments_into_md(md, comments, anchors)
        self.assertNotIn("<批注 id=1<批注", result)
        self.assertNotIn("<批注 id=2>", result)  # 锚点缺失，第二条不插入


class TestPlaceholderInsertion(unittest.TestCase):
    """占位符精确插入：pandoc 前注入 CMTEND{N}Z，转换后按 md 顺序替换为批注标记。

    位置由 docx commentRangeEnd 决定，与锚点文本是否重复无关——彻底解决
    短/重复锚点错位与 id 乱序。
    """

    def test_replace_preserves_anchor_text_and_position(self):
        # 罗阳 在 token 前，主簿 在后；标记应落在 token 位置（罗阳之后、主簿之前）
        md = "部属罗阳CMTEND11Z主簿"
        comments = {"11": "洛阳"}
        anchors = [{"id": "11", "text": "罗阳", "pos": 0}]
        result = replace_comment_placeholders(md, comments, anchors)
        self.assertEqual(result,
                         "部属罗阳<批注 id=1><原>罗阳</原><改>洛阳</改></批注>主簿")

    def test_replace_renumber_by_md_order(self):
        # 两个 token，按 md 出现顺序编号 1,2（与 docx cid 大小无关）
        md = "韦凑CMTEND11Z字彦宗CMTEND3Z"
        comments = {"11": "洛阳", "3": "改为昆虫"}
        anchors = [{"id": "11", "text": "罗阳", "pos": 0},
                   {"id": "3", "text": "昆蛟", "pos": 10}]
        result = replace_comment_placeholders(md, comments, anchors)
        self.assertIn("<批注 id=1><原>罗阳</原><改>洛阳</改></批注>", result)
        self.assertIn("<批注 id=2><原>昆蛟</原><改>改为昆虫</改></批注>", result)
        self.assertNotIn("CMTEND", result)

    def test_replace_skip_unknown_id(self):
        # cid 99 不在 anchors（空锚点/无 Range）→ 移除占位符、不插标记、不占编号
        md = "韦凑CMTEND11Z字CMTEND99Z"
        comments = {"11": "洛阳", "99": "内容"}
        anchors = [{"id": "11", "text": "罗阳", "pos": 0}]
        result = replace_comment_placeholders(md, comments, anchors)
        self.assertIn("<批注 id=1><原>罗阳</原>", result)
        self.assertNotIn("CMTEND", result)
        self.assertNotIn("<批注 id=2>", result)

    def test_replace_digit_anchor_not_confused_by_repeated_text(self):
        # 锚点 "9" 在 md 里多次出现：占位符钉位置，不靠文本搜索，不会错位
        md = "长辈9完成9CMTEND46Z题"  # 真正批注位在第二个 9 之后
        comments = {"46": "题号标注9-12题断裂"}
        anchors = [{"id": "46", "text": "9", "pos": 0}]
        result = replace_comment_placeholders(md, comments, anchors)
        self.assertEqual(result,
                         "长辈9完成9<批注 id=1><原>9</原><改>题号标注9-12题断裂</改></批注>题")

    def test_inject_inserts_token_after_comment_range_end(self):
        import tempfile
        import zipfile
        doc_xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   '<w:body><w:p><w:r><w:t>罗阳</w:t></w:r>'
                   '<w:commentRangeEnd w:id="11"/>'
                   '<w:r><w:commentReference w:id="11"/></w:r></w:p></w:body></w:document>')
        fd, docx_path = tempfile.mkstemp(suffix='.docx')
        os.close(fd)
        with zipfile.ZipFile(docx_path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('word/document.xml', doc_xml)
        try:
            temp = inject_comment_placeholders(docx_path)
            self.assertIsNotNone(temp, "有 commentRangeEnd 应生成 temp docx")
            with zipfile.ZipFile(temp) as z:
                new_xml = z.read('word/document.xml').decode('utf-8')
            self.assertIn(
                '<w:commentRangeEnd w:id="11"/><w:r><w:t xml:space="preserve">CMTEND11Z</w:t></w:r>',
                new_xml)
            os.unlink(temp)
        finally:
            os.unlink(docx_path)

    def test_inject_no_comment_range_returns_none(self):
        import tempfile
        import zipfile
        doc_xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   '<w:body><w:p><w:r><w:t>无批注</w:t></w:r></w:p></w:body></w:document>')
        fd, docx_path = tempfile.mkstemp(suffix='.docx')
        os.close(fd)
        with zipfile.ZipFile(docx_path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('word/document.xml', doc_xml)
        try:
            self.assertIsNone(inject_comment_placeholders(docx_path))
        finally:
            os.unlink(docx_path)


class TestNormalizeText(unittest.TestCase):
    def test_remove_all_whitespace(self):
        self.assertEqual(normalize_text("a b  c\n\nd"), "abcd")

    def test_chinese_quotes_to_english(self):
        self.assertEqual(normalize_text("“选非”"), '"选非"')

    def test_mixed_whitespace_and_quotes(self):
        self.assertEqual(normalize_text("“你好   世界”\n"), '"你好世界"')

    def test_empty_string(self):
        self.assertEqual(normalize_text(""), "")

    def test_only_whitespace(self):
        self.assertEqual(normalize_text("   \n\t  "), "")


class TestFuzzyInsertComment(unittest.TestCase):
    def test_exact_match(self):
        md = "这是正文内容"
        result, ok = fuzzy_insert_comment(md, "正文", "批注内容", 1)
        self.assertTrue(ok)
        self.assertIn('<批注 id=1><原>正文</原><改>批注内容</改></批注>', result)

    def test_newline_difference(self):
        md = "这是正\n文内容"
        result, ok = fuzzy_insert_comment(md, "正文", "批注", 1)
        self.assertTrue(ok)
        self.assertIn("批注 id=1", result)

    def test_quote_difference(self):
        md = '一般以"选非"的形式考查'
        result, ok = fuzzy_insert_comment(md, "“选非”", "批注", 1)
        self.assertTrue(ok)
        self.assertIn("批注 id=1", result)

    def test_three_spaces_to_newlines(self):
        md = "参考含义：精神\n\n原因：作者\n\n情感：赞美"
        anchor = "参考含义：精神   原因：作者   情感：赞美"
        result, ok = fuzzy_insert_comment(md, anchor, "批注", 1)
        self.assertTrue(ok)
        self.assertIn("批注 id=1", result)

    def test_paragraph_break_in_answer(self):
        md = "2.【试题答案】B\n\n【试题考点】本题考查\n\n【试题解析】解析内容"
        anchor = "2.【试题答案】B【试题考点】本题考查【试题解析】解析内容"
        result, ok = fuzzy_insert_comment(md, anchor, "批注", 1)
        self.assertTrue(ok)
        self.assertIn("批注 id=1", result)

    def test_no_match_returns_false(self):
        md = "完全不相关的文本"
        result, ok = fuzzy_insert_comment(md, "找不到的锚点", "批注", 1)
        self.assertFalse(ok)
        self.assertEqual(result, md)


if __name__ == "__main__":
    unittest.main()
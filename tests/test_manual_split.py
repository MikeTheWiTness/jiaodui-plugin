"""单元标记解析器的行为契约测试（ADR-0017 决策5）。

移植自旧仓 tests/test_manual_split.py（HEAD 1c45243）的 TestParseUnitMarkers /
TestSplitByUnitMarkers，统一到新仓公开 API parse_unit_markers + UnitMarkerError，
并补充 pandoc 转义与错误边界。
"""
import unittest

from jiaodui.errors import ContractError
from jiaodui.split import UnitMarkerError, parse_unit_markers


class TestParseUnitMarkersNormal(unittest.TestCase):
    """正常解析：单元切分、正文取舍。"""

    def test_single_unit(self):
        text = (
            "###### 单元开始 ######\n"
            "这是第一单元的内容\n"
            "第二行\n"
            "###### 单元结束 ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"].strip(), "这是第一单元的内容\n第二行")

    def test_multiple_units(self):
        text = (
            "###### 单元开始 ######\n"
            "单元1内容\n"
            "###### 单元结束 ######\n"
            "###### 单元开始 ######\n"
            "单元2内容\n"
            "###### 单元结束 ######\n"
            "###### 单元开始 ######\n"
            "单元3内容\n"
            "###### 单元结束 ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 3)
        self.assertIn("单元1", result[0]["content"])
        self.assertIn("单元3", result[2]["content"])

    def test_outside_content_discarded(self):
        text = (
            "开头引言\n"
            "这里是说明文字\n"
            "###### 单元开始 ######\n"
            "单元正文\n"
            "###### 单元结束 ######\n"
            "中间过渡文字\n"
            "###### 单元开始 ######\n"
            "第二单元\n"
            "###### 单元结束 ######\n"
            "结尾总结文字\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 2)
        self.assertNotIn("引言", result[0]["content"])
        self.assertNotIn("过渡", result[1]["content"])
        self.assertNotIn("总结", result[1]["content"])

    def test_empty_unit_content(self):
        text = (
            "###### 单元开始 ######\n"
            "###### 单元结束 ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "")

    def test_extra_spaces_in_marker(self):
        text = (
            "######  单元开始  ######\n"
            "内容\n"
            "######  单元结束  ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)
        self.assertIn("内容", result[0]["content"])

    def test_preserves_whitespace_in_content(self):
        text = (
            "###### 单元开始 ######\n"
            "  缩进的内容\n"
            "\t制表符内容\n"
            "普通内容\n"
            "###### 单元结束 ######\n"
        )
        result = parse_unit_markers(text)
        self.assertIn("  缩进的内容", result[0]["content"])
        self.assertIn("\t制表符内容", result[0]["content"])

    def test_lookalike_not_on_own_line(self):
        """正文中提到的标记形态不在单独一行时不应干扰解析。"""
        text = (
            "###### 单元开始 ######\n"
            "正文里提到了###### 单元开始 ######但不是单独一行\n"
            "###### 单元结束 ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)
        self.assertIn("提到了", result[0]["content"])


class TestParseUnitMarkersErrors(unittest.TestCase):
    """错误边界：缺标记、不配对、空文本。"""

    def test_no_markers_raises(self):
        with self.assertRaises(UnitMarkerError) as ctx:
            parse_unit_markers("没有标记的普通文本")
        self.assertIn("标记", str(ctx.exception))

    def test_empty_text_raises(self):
        with self.assertRaises(UnitMarkerError):
            parse_unit_markers("")

    def test_missing_end_marker_raises(self):
        text = (
            "###### 单元开始 ######\n"
            "内容没有结束标记\n"
        )
        with self.assertRaises(UnitMarkerError) as ctx:
            parse_unit_markers(text)
        self.assertIn("配对", str(ctx.exception))

    def test_end_without_start_raises(self):
        text = (
            "###### 单元结束 ######\n"
            "###### 单元开始 ######\n"
            "内容\n"
            "###### 单元结束 ######\n"
        )
        with self.assertRaises(UnitMarkerError) as ctx:
            parse_unit_markers(text)
        self.assertIn("配对", str(ctx.exception))

    def test_nested_start_raises(self):
        text = (
            "###### 单元开始 ######\n"
            "###### 单元开始 ######\n"
            "内容\n"
        )
        with self.assertRaises(UnitMarkerError):
            parse_unit_markers(text)

    def test_marker_not_alone_line_raises(self):
        """整行不是标记形态时视作无标记 → 报错。"""
        text = (
            "前面文字 ###### 单元开始 ###### 后面文字\n"
            "内容\n"
            "###### 单元结束 ######\n"
        )
        with self.assertRaises(UnitMarkerError):
            parse_unit_markers(text)

    def test_unit_marker_error_types(self):
        self.assertTrue(issubclass(UnitMarkerError, ContractError))
        self.assertTrue(issubclass(UnitMarkerError, ValueError))


class TestParseUnitMarkersPandoc(unittest.TestCase):
    """pandoc 转换会把行首 # 转义成 \\#，标记变成 \\###### 单元开始 \\######。

    正则需容忍转义，否则匹配不到 → 抛错 → 调用方未捕获 → 转换线程静默死亡。
    """

    def test_escaped_first_hash(self):
        text = (
            r"\###### 单元开始 \######" "\n"
            "单元内容\n"
            r"\###### 单元结束 \######" "\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)
        self.assertIn("单元内容", result[0]["content"])

    def test_per_hash_escaped(self):
        text = (
            r"\#\#\#\#\#\# 单元开始 \#\#\#\#\#\#" "\n"
            "单元内容\n"
            r"\#\#\#\#\#\# 单元结束 \#\#\#\#\#\#" "\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 1)
        self.assertIn("单元内容", result[0]["content"])

    def test_mixed_escaped_and_unescaped(self):
        text = (
            r"\###### 单元开始 \######" "\n"
            "第一单元\n"
            r"\###### 单元结束 \######" "\n"
            "###### 单元开始 ######\n"
            "第二单元\n"
            "###### 单元结束 ######\n"
        )
        result = parse_unit_markers(text)
        self.assertEqual(len(result), 2)
        self.assertIn("第一单元", result[0]["content"])
        self.assertIn("第二单元", result[1]["content"])


if __name__ == "__main__":
    unittest.main()

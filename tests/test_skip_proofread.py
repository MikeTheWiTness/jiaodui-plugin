"""导航/封面单元跳过校对的契约测试。

移植自旧仓 tests/test_skip_proofread_contract.py（HEAD 1c45243），导入路径改为
jiaodui.split.mark_navigation_units / is_skip_unit。
"""
import tempfile
import unittest
from pathlib import Path

from jiaodui.paths import SKIP_MARKER_FILE
from jiaodui.split import is_skip_unit, mark_navigation_units


class TestSkipProofreadContract(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_root = self.temp_dir.name
        self.base_name = "test_doc"

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── 辅助方法 ──────────────────────────────────────────────
    def _target_dir(self):
        return Path(self.output_root) / self.base_name

    def _make_unit(self, unit_name, first_line):
        """创建包含一个 .md 文件的板块目录。"""
        unit_dir = self._target_dir() / unit_name
        unit_dir.mkdir(parents=True, exist_ok=True)
        md_file = unit_dir / "content.md"
        md_file.write_text(first_line + "\n\n正文内容……", encoding="utf-8")
        return unit_dir

    def _make_units(self, *specs):
        for name, first_line in specs:
            self._make_unit(name, first_line)

    # ── 测试用例 ──────────────────────────────────────────────
    def test_creates_skip_marker(self):
        self._make_unit("01_直击课堂", "# 直击课堂")
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 1)
        skip_file = self._target_dir() / "01_直击课堂" / SKIP_MARKER_FILE
        self.assertTrue(skip_file.exists())

    def test_marker_placed_in_unit_dir(self):
        self._make_unit("02_本讲导航", "## 本讲导航 - 内容概览")
        mark_navigation_units(self.output_root, self.base_name)
        skip_file = self._target_dir() / "02_本讲导航" / SKIP_MARKER_FILE
        self.assertTrue(skip_file.exists())
        self.assertFalse((self._target_dir() / SKIP_MARKER_FILE).exists())

    def test_multiple_navigation_units(self):
        self._make_units(
            ("01_直击课堂", "# 直击课堂"),
            ("02_知识点", "## 知识点讲解"),
            ("03_本讲导航", "# 本讲导航"),
            ("04_练习", "## 练习"),
        )
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 2)
        self.assertTrue((self._target_dir() / "01_直击课堂" / SKIP_MARKER_FILE).exists())
        self.assertTrue((self._target_dir() / "03_本讲导航" / SKIP_MARKER_FILE).exists())
        self.assertFalse((self._target_dir() / "02_知识点" / SKIP_MARKER_FILE).exists())
        self.assertFalse((self._target_dir() / "04_练习" / SKIP_MARKER_FILE).exists())

    def test_non_matching_units_not_marked(self):
        self._make_units(
            ("01_知识点", "# 知识点一"),
            ("02_例题", "## 例题精讲"),
        )
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 0)
        self.assertFalse((self._target_dir() / "01_知识点" / SKIP_MARKER_FILE).exists())
        self.assertFalse((self._target_dir() / "02_例题" / SKIP_MARKER_FILE).exists())

    def test_missing_target_dir_returns_zero(self):
        marked = mark_navigation_units(self.output_root, "nonexistent_doc")
        self.assertEqual(marked, 0)

    def test_empty_target_dir_returns_zero(self):
        self._target_dir().mkdir(parents=True)
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 0)

    def test_subdir_without_md_files_skipped(self):
        unit_dir = self._target_dir() / "empty_unit"
        unit_dir.mkdir(parents=True)
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 0)
        self.assertFalse((unit_dir / SKIP_MARKER_FILE).exists())

    def test_custom_patterns(self):
        self._make_units(
            ("封面", "# 课程封面"),
            ("目录", "## 目录"),
        )
        marked = mark_navigation_units(
            self.output_root, self.base_name,
            patterns=[r"封面", r"目录"],
        )
        self.assertEqual(marked, 2)
        self.assertTrue((self._target_dir() / "封面" / SKIP_MARKER_FILE).exists())
        self.assertTrue((self._target_dir() / "目录" / SKIP_MARKER_FILE).exists())

    def test_partial_match_in_first_line(self):
        self._make_unit("01_开场", "### 直击课堂 - 今日要点")
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 1)
        self.assertTrue((self._target_dir() / "01_开场" / SKIP_MARKER_FILE).exists())

    def test_return_value_is_int(self):
        self._make_unit("nav", "# 直击课堂")
        result = mark_navigation_units(self.output_root, self.base_name)
        self.assertIsInstance(result, int)

    def test_report_md_is_not_used_as_first_line(self):
        """只读非 _ 前缀的源文，_校对报告.md 不得决定是否跳过。"""
        unit_dir = self._target_dir() / "01_单元"
        unit_dir.mkdir(parents=True)
        (unit_dir / "_校对报告.md").write_text("# 直击课堂\n（这是报告，不是源文）", encoding="utf-8")
        (unit_dir / "单元1.md").write_text("正常正文", encoding="utf-8")
        marked = mark_navigation_units(self.output_root, self.base_name)
        self.assertEqual(marked, 0)
        self.assertFalse((unit_dir / SKIP_MARKER_FILE).exists())

    def test_is_skip_unit(self):
        unit_dir = self._make_unit("nav", "# 直击课堂")
        self.assertFalse(is_skip_unit(unit_dir))
        (unit_dir / SKIP_MARKER_FILE).touch()
        self.assertTrue(is_skip_unit(unit_dir))


if __name__ == "__main__":
    unittest.main()

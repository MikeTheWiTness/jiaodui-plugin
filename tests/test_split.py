"""规则拆分 / 边界切片 / 拆分预检的行为契约测试。

移植并扩展旧仓 tests/test_split_modes.py（HEAD 1c45243）：新契约只产出
第N题.md / 单元N.md 与 images/，不再有 _clean.md；重跑保留已有校对产物。
"""
from pathlib import Path

from jiaodui.split import (SplitResult, precheck_split, slice_by_boundaries,
                           split_exam, split_lecture)


def _md_names(unit_dir: Path):
    return sorted(p.name for p in unit_dir.glob("*.md"))


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ─── 试卷模式 ─────────────────────────────────────────────

class TestSplitExam:
    def test_inline_answer_mode(self, tmp_path):
        raw = ("1．第一题题干\n"
               "【答案】A\n"
               "【详解】解析一\n"
               "2．第二题题干\n"
               "【答案】B\n"
               "【详解】解析二\n")
        result = split_exam(raw, str(tmp_path / "out"), "paper", {})
        assert isinstance(result, SplitResult)
        assert len(result.units) == 2
        assert [Path(p).name for p in result.unit_dirs] == ["第1题", "第2题"]
        text1 = _text(tmp_path / "out" / "paper" / "第1题" / "第1题.md")
        assert "【答案】A" in text1
        assert "【详解】解析一" in text1
        assert _md_names(tmp_path / "out" / "paper" / "第1题") == ["第1题.md"]

    def test_end_answer_mode(self, tmp_path):
        raw = ("1．第一题\n"
               "2．第二题\n"
               "参考答案\n"
               "1. A 解析A\n"
               "2. B 解析B\n")
        result = split_exam(raw, str(tmp_path / "out"), "paper", {})
        assert len(result.units) == 2
        assert "【答案】A 解析A" in _text(tmp_path / "out" / "paper" / "第1题" / "第1题.md")
        assert "【答案】B 解析B" in _text(tmp_path / "out" / "paper" / "第2题" / "第2题.md")

    def test_no_match_warns_and_returns_empty(self, tmp_path):
        result = split_exam("没有任何题号的文本", str(tmp_path / "out"), "paper", {})
        assert result.units == []
        assert result.unit_dirs == []
        assert any("题目" in w for w in result.warnings)

    def test_empty_source_warns(self, tmp_path):
        result = split_exam("   ", str(tmp_path / "out"), "paper", {})
        assert result.units == []
        assert result.warnings

    def test_no_clean_md_produced(self, tmp_path):
        raw = "1．第一题\n2．第二题\n"
        split_exam(raw, str(tmp_path / "out"), "paper", {})
        assert not list((tmp_path / "out").rglob("*_clean.md"))

    def test_only_contract_md_names(self, tmp_path):
        raw = "1．第一题\n2．第二题\n"
        split_exam(raw, str(tmp_path / "out"), "paper", {})
        produced = sorted(p.name for p in (tmp_path / "out").rglob("*.md"))
        assert produced == ["第1题.md", "第2题.md"]

    def test_images_copied_and_path_rewritten(self, tmp_path):
        raw_path = tmp_path / "paper.md"
        raw_path.write_text("1．见下图\n![示意图](./pic.png)\n", encoding="utf-8")
        media = tmp_path / "paper_images" / "media"
        media.mkdir(parents=True)
        (media / "pic.png").write_bytes(b"png")

        result = split_exam(str(raw_path), str(tmp_path / "out"), "paper", {})

        assert result.copied == 1
        assert result.missing == 0
        assert (tmp_path / "out" / "paper" / "第1题" / "images" / "pic.png").exists()
        assert "./images/pic.png" in _text(tmp_path / "out" / "paper" / "第1题" / "第1题.md")

    def test_missing_image_counted_and_warned(self, tmp_path):
        raw_path = tmp_path / "paper.md"
        raw_path.write_text("1．见下图\n![示意图](./nope.png)\n", encoding="utf-8")
        result = split_exam(str(raw_path), str(tmp_path / "out"), "paper", {})
        assert result.missing == 1
        assert any("图片" in w for w in result.warnings)

    def test_rerun_preserves_existing_reports(self, tmp_path):
        raw = "1．第一题\n2．第二题\n"
        out = str(tmp_path / "out")
        split_exam(raw, out, "paper", {})
        unit = tmp_path / "out" / "paper" / "第1题"
        (unit / "_校对报告.md").write_text("稳定报告", encoding="utf-8")
        (unit / "_校对数据.json").write_text("{}", encoding="utf-8")
        (unit / "_校对失败.md").write_text("失败留痕", encoding="utf-8")

        split_exam(raw, out, "paper", {})

        assert _text(unit / "_校对报告.md") == "稳定报告"
        assert _text(unit / "_校对数据.json") == "{}"
        assert _text(unit / "_校对失败.md") == "失败留痕"
        assert (unit / "第1题.md").exists()


# ─── 讲义模式 ─────────────────────────────────────────────

class TestSplitLecture:
    def test_section_split_drops_title_only_units(self, tmp_path):
        """「### 标题 → #### 阶段标题 → **练N**」结构不再产出纯标题空壳单元。"""
        lec = ("# 第 1 讲\n\n"
               "## 知识精讲\n\n"
               "### 电极反应式的书写\n\n"
               "#### 基础演练\n\n"
               "#### 强化训练\n\n"
               "**练1**\n\n"
               "题目一内容\n\n"
               "## 练习册\n\n"
               "### 原电池\n\n"
               "#### 基础演练\n\n"
               "**练2**\n\n"
               "题目二内容\n")
        result = split_lecture(lec, str(tmp_path / "out"), "lec",
                               {"wrapped_patterns": [r"例\d+", r"练\d+"]})
        assert len(result.units) == 2
        unit_dirs = sorted((tmp_path / "out" / "lec").iterdir())
        assert [d.name for d in unit_dirs] == ["单元1", "单元2"]
        for d in unit_dirs:
            assert _md_names(d) == [f"{d.name}.md"]
            first = _text(d / f"{d.name}.md").splitlines()[0]
            assert "**练" in first

    def test_consecutive_headers_merged(self, tmp_path):
        lec = "## 模块一\n\n### 小节\n\n正文内容\n"
        result = split_lecture(lec, str(tmp_path / "out"), "lec", {})
        assert len(result.units) == 1
        text = _text(tmp_path / "out" / "lec" / "单元1" / "单元1.md")
        assert "模块一" in text
        assert "正文内容" in text

    def test_title_mode_splits_by_title_pattern(self, tmp_path):
        lec = "**例1**\n题干一\n**例2**\n题干二\n"
        cfg = {"split_mode": "title", "wrapped_patterns": [r"例\d+"]}
        result = split_lecture(lec, str(tmp_path / "out"), "lec", cfg)
        assert len(result.units) == 2

    def test_empty_source_warns(self, tmp_path):
        result = split_lecture("   ", str(tmp_path / "out"), "lec", {})
        assert result.units == []
        assert result.warnings

    def test_rerun_preserves_reports(self, tmp_path):
        lec = "## 小节\n\n正文\n"
        out = str(tmp_path / "out")
        split_lecture(lec, out, "lec", {})
        unit = tmp_path / "out" / "lec" / "单元1"
        (unit / "_校对报告.md").write_text("报告", encoding="utf-8")
        (unit / "_校对数据.json").write_text("{}", encoding="utf-8")

        split_lecture(lec, out, "lec", {})

        assert _text(unit / "_校对报告.md") == "报告"
        assert _text(unit / "_校对数据.json") == "{}"
        assert _md_names(unit) == ["_校对报告.md", "单元1.md"]

    def test_lecture_images_copied(self, tmp_path):
        raw_path = tmp_path / "lec.md"
        raw_path.write_text("## 小节\n\n![图](./pic.png)\n正文\n", encoding="utf-8")
        media = tmp_path / "lec_images" / "media"
        media.mkdir(parents=True)
        (media / "pic.png").write_bytes(b"png")
        result = split_lecture(str(raw_path), str(tmp_path / "out"), "lec", {})
        assert result.copied == 1
        assert (tmp_path / "out" / "lec" / "单元1" / "images" / "pic.png").exists()


# ─── 边界切片 ─────────────────────────────────────────────

class TestSliceByBoundaries:
    def test_line_based(self, tmp_path):
        raw = "第1题正文\n第二行\n第2题正文"
        boundaries = [
            {"name": "第1题", "start_line": 1, "end_line": 2},
            {"name": "第2题", "start_line": 3, "end_line": 3},
        ]
        result = slice_by_boundaries(raw, boundaries, str(tmp_path / "out"), "sl", "exam")
        assert len(result.units) == 2
        assert _text(tmp_path / "out" / "sl" / "第1题" / "第1题.md") == "第1题正文\n第二行"
        assert _text(tmp_path / "out" / "sl" / "第2题" / "第2题.md") == "第2题正文"

    def test_text_based(self, tmp_path):
        boundaries = [{"name": "单元1", "text": "甲"}, {"name": "单元2", "text": "乙"}]
        result = slice_by_boundaries("忽略", boundaries, str(tmp_path / "out"), "sl", "lecture")
        assert len(result.units) == 2
        assert _text(tmp_path / "out" / "sl" / "单元1" / "单元1.md") == "甲"

    def test_name_fallback_by_mode(self, tmp_path):
        boundaries = [{"name": "开场", "text": "x"}]
        slice_by_boundaries("", boundaries, str(tmp_path / "out"), "sl", "exam")
        assert (tmp_path / "out" / "sl" / "第1题" / "第1题.md").exists()
        slice_by_boundaries("", boundaries, str(tmp_path / "out2"), "sl", "lecture")
        assert (tmp_path / "out2" / "sl" / "单元1" / "单元1.md").exists()

    def test_empty_boundaries_warns(self, tmp_path):
        result = slice_by_boundaries("x", [], str(tmp_path / "out"), "sl", "exam")
        assert result.units == []
        assert result.warnings

    def test_start_line_out_of_range_gives_empty_unit(self, tmp_path):
        boundaries = [{"name": "第1题", "start_line": 99, "end_line": 120}]
        slice_by_boundaries("a\nb", boundaries, str(tmp_path / "out"), "sl", "exam")
        assert _text(tmp_path / "out" / "sl" / "第1题" / "第1题.md") == ""

    def test_no_clean_md_produced(self, tmp_path):
        boundaries = [{"name": "第1题", "text": "x"}]
        slice_by_boundaries("ignored", boundaries, str(tmp_path / "out"), "sl", "exam")
        assert not list((tmp_path / "out").rglob("*_clean.md"))


# ─── 拆分预检 ─────────────────────────────────────────────

class TestPrecheckSplit:
    def _make_unit(self, base: Path, name: str, text: str):
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.md").write_text(text, encoding="utf-8")
        return d

    def test_reports_empty_and_overlong(self, tmp_path):
        base = tmp_path / "paper"
        self._make_unit(base, "单元1", "")
        normal = "标题\n" + "x" * 50
        self._make_unit(base, "单元2", normal)
        self._make_unit(base, "单元3", "标题\n" + "y" * 200)

        result = precheck_split(str(base), overlong_threshold=100)

        assert result.unit_count == 3
        assert result.empty_units == ["单元1"]
        assert result.overlong_units == ["单元3"]
        assert result.length_min == 0
        assert result.length_max > 200
        assert result.length_median == len(normal)
        assert result.units[0]["first_line"] == ""
        assert result.units[1]["first_line"] == "标题"
        assert result.units[1]["chars"] == len(normal)
        assert result.warnings

    def test_default_threshold_is_20000(self, tmp_path):
        base = tmp_path / "paper"
        self._make_unit(base, "单元1", "a" * 19999)
        self._make_unit(base, "单元2", "a" * 20001)
        result = precheck_split(str(base))
        assert result.overlong_units == ["单元2"]

    def test_empty_dir_warns(self, tmp_path):
        result = precheck_split(str(tmp_path))
        assert result.unit_count == 0
        assert result.warnings

    def test_scans_output_root_with_base_name_layer(self, tmp_path):
        base = tmp_path / "out" / "paper"
        self._make_unit(base, "单元1", "内容")
        result = precheck_split(str(tmp_path / "out"))
        assert result.unit_count == 1
        assert result.units[0]["name"] == "单元1"

    def test_reads_reports_do_not_affect_chars(self, tmp_path):
        """预检只读源文；_ 前缀的校对产物不计入字符数。"""
        base = tmp_path / "paper"
        d = self._make_unit(base, "单元1", "短")
        (d / "_校对报告.md").write_text("x" * 5000, encoding="utf-8")
        result = precheck_split(str(base))
        assert result.units[0]["chars"] == 1

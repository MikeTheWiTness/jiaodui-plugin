"""规则拆分 / 边界切片 / 拆分预检的行为契约测试。

移植并扩展旧仓 tests/test_split_modes.py（HEAD 1c45243）：新契约只产出
第N题.md / 单元N.md 与 images/，不再有 _clean.md；重跑保留已有校对产物。
"""
from pathlib import Path

from jiaodui.split import (SplitResult, lecture_cleaned_text, precheck_split,
                           slice_by_boundaries, split_exam, split_lecture)


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

    def test_section_mode_cleans_grid_tables_before_split(self, tmp_path):
        """讲义导入清理：pandoc 网格表包裹的 **例N** 必须先清表格再按 section 拆分。

        真实讲义（第 6 讲校对测试.docx）经 pandoc 转成网格表后，「**例1**（多选）」
        落在表格行里（行首是竖线）；旧仓导入阶段默认执行 comprehensive_clean
        （去竖线、丢表框线），例题标题回到行首后才被 section_pattern 命中。
        新仓若不做这一步，整篇会塌成一个超长单元。
        """
        lec = ("## 模块一 模型：起振问题\n\n"
               "+--------------------------------+\n"
               "| 模型大招                        |\n"
               "+================================+\n"
               "| **例1**（多选）                  |\n"
               "+================================+\n"
               "| 题干一                          |\n"
               "+--------------------------------+\n"
               "| **例2**（多选）                  |\n"
               "+================================+\n"
               "| 题干二                          |\n"
               "+--------------------------------+\n")
        raw_path = tmp_path / "lec.md"
        raw_path.write_text(lec, encoding="utf-8")
        result = split_lecture(str(raw_path), str(tmp_path / "out"), "lec", {})
        assert len(result.units) >= 3
        firsts = [u["first_line"] for u in result.units]
        assert any(f.startswith("**例1**") for f in firsts)
        for u in result.units:
            text = _text(Path(u["file"]))
            assert "|" not in text, "网格表竖线应被清理"

    def test_images_dir_override_accepts_convert_output_root(self, tmp_path):
        """--images-dir 传 convert --json 的 images_dir（{base}_images 根目录）也能复制。"""
        raw_path = tmp_path / "lec.md"
        raw_path.write_text("## 小节\n\n![图](./pic.png)\n正文\n", encoding="utf-8")
        images_root = tmp_path / "lec_images"
        media = images_root / "media"
        media.mkdir(parents=True)
        (media / "pic.png").write_bytes(b"png")
        result = split_lecture(str(raw_path), str(tmp_path / "out"), "lec",
                               {"images_source": str(images_root)})
        assert result.copied == 1
        assert result.missing == 0

    def test_no_clean_keeps_table_wrapping(self, tmp_path):
        """--no-clean：保留原始网格表包裹，例题标题不在行首，只能拆出更少的单元。"""
        lec = ("## 模块一\n\n"
               "+------------------+\n"
               "| **例1**（多选）    |\n"
               "+------------------+\n"
               "| 题干一            |\n"
               "+------------------+\n")
        raw_path = tmp_path / "lec.md"
        raw_path.write_text(lec, encoding="utf-8")
        result = split_lecture(str(raw_path), str(tmp_path / "out"), "lec", {},
                               clean=False)
        assert len(result.units) == 1
        assert "|" in _text(Path(result.units[0]["file"]))

    def test_import_cleanup_applies_intent_floating_and_spacing(self, tmp_path):
        """讲义导入清理接线：清【出题意图】、挪浮图、压选项空格。"""
        lec = ("## 模块一\n\n"
               "【出题意图】本题想考波动图像。\n"
               "**例1**（多选）\n"
               "题干一\n\n"
               "A. ![test](./pic.png){width=\"1in\"}   选项甲\n"
               "B. 选项乙\n")
        media = tmp_path / "lec_images" / "media"
        media.mkdir(parents=True)
        (media / "pic.png").write_bytes(b"png")
        raw_path = tmp_path / "lec.md"
        raw_path.write_text(lec, encoding="utf-8")
        result = split_lecture(str(raw_path), str(tmp_path / "out"), "lec",
                               {"wrapped_patterns": [r"例\d+"]})
        text = _text(Path(result.units[-1]["file"]))
        assert "【出题意图】" not in text
        assert "**例1**" in text
        # 题图挪到独立行，且排在 A. 选项之前
        assert "![](./images/pic.png)" in text
        assert text.index("![](./images/pic.png)") < text.index("A.  选项甲")
        # 4 个以上连续空格被压成 2 个
        assert "    " not in text

    def test_config_markers_enable_subject_specific_intent_clean(self, tmp_path):
        """学科独有标志（真题）经 config 合并后才会被【出题意图】清理。"""
        lec = ("## 模块一\n\n"
               "【出题意图】说明。\n"
               "**真题1**\n"
               "题干\n")
        raw_path = tmp_path / "lec.md"
        raw_path.write_text(lec, encoding="utf-8")

        r1 = split_lecture(str(raw_path), str(tmp_path / "o1"), "lec",
                           {"wrapped_patterns": [r"例\d+"]})
        assert "【出题意图】" in _text(Path(r1.units[0]["file"]))

        r2 = split_lecture(str(raw_path), str(tmp_path / "o2"), "lec",
                           {"wrapped_patterns": [r"例\d+", r"真题\d+"]})
        assert "【出题意图】" not in _text(Path(r2.units[0]["file"]))

    def test_no_clean_skips_intent_and_floating_image_cleanup(self, tmp_path):
        """clean=False（--no-clean）时三项导入清理都不执行。"""
        lec = ("## 模块一\n\n"
               "【出题意图】说明。\n"
               "**例1**\n"
               "A. ![test](./pic.png)   选项\n")
        raw_path = tmp_path / "lec.md"
        raw_path.write_text(lec, encoding="utf-8")
        result = split_lecture(str(raw_path), str(tmp_path / "out"), "lec", {},
                               clean=False)
        text = _text(Path(result.units[0]["file"]))
        assert "【出题意图】" in text
        assert "A. ![test](./pic.png)   选项" in text


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

    def test_lecture_boundaries_must_follow_cleaned_text(self, tmp_path):
        """智能拆分行号必须基于清理后正文（否则第一单元混题、第二单元为空）。"""
        raw = ("## 模块一\n\n"
               "+------------------+\n"
               "| **例1**（多选）    |\n"
               "+------------------+\n"
               "| 题干一            |\n"
               "+------------------+\n"
               "| **例2**（多选）    |\n"
               "+------------------+\n"
               "| 题干二            |\n"
               "+------------------+\n")
        raw_path = tmp_path / "lec.md"
        raw_path.write_text(raw, encoding="utf-8")

        cleaned = lecture_cleaned_text(str(raw_path), "lec")
        lines = cleaned.splitlines()
        i1 = lines.index("**例1**（多选）")
        i2 = lines.index("**例2**（多选）")
        assert "|" not in cleaned
        boundaries = [
            {"name": "单元1", "start_line": i1 + 1, "end_line": i2},
            {"name": "单元2", "start_line": i2 + 1, "end_line": len(lines)},
        ]
        result = slice_by_boundaries(str(raw_path), boundaries,
                                     str(tmp_path / "out"), "lec", "lecture")
        assert len(result.units) == 2
        t1 = _text(tmp_path / "out" / "lec" / "单元1" / "单元1.md")
        t2 = _text(tmp_path / "out" / "lec" / "单元2" / "单元2.md")
        assert "**例1**" in t1 and "题干一" in t1 and "**例2**" not in t1
        assert "**例2**" in t2 and "题干二" in t2

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

import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from jiaodui.docx_report import (DocxBuildResult, build_docx, find_pandoc,
                                 generate_combined_docx)
from jiaodui.formula_render import matplotlib_available

PANDOC = find_pandoc()
# 真实 import 判定：find_spec 会把「装了但 dlopen 失败（macOS 代码签名）」
# 误判为可用，导致公式图片断言失败。
HAS_MPL = matplotlib_available()
PANDOC_REQUIRED = pytest.mark.skipif(PANDOC is None, reason="pandoc 不可用")

_1PX_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

REPORT_WITH_MARKS = """# 第1题 校对报告

轻微问题

### 标记原文
编号：第1题
内容：
1．下列关于物理量的说法正确的是（　　）

【1|电荷量很小的电荷就是元电荷|元电荷是最小的电荷量，并非电荷量很小的电荷】

【2|电量|电荷量】是电荷的多少

![@@@testuuid00000000000000000000000001](./images/img1.png){width="1.0in" height="0.8in"}

### 修改原因
1. 元电荷是最小的电荷量，表述不严谨。
2. "电量"为口语化表述，应规范为"电荷量"。
"""

REPORT_NO_MARKS = """# 第2题 校对报告

无问题

### 标记原文
编号：第2题
内容：
2．下列说法正确的是（　　）

A．正确

B．错误

### 修改原因
无
"""


@PANDOC_REQUIRED
class TestGenerateCombinedDocx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_report_test_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        os.makedirs(os.path.join(self.paper, "第1题", "images"))
        os.makedirs(os.path.join(self.paper, "第2题"))
        with open(os.path.join(self.paper, "第1题", "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(REPORT_WITH_MARKS)
        with open(os.path.join(self.paper, "第2题", "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(REPORT_NO_MARKS)
        with open(os.path.join(self.paper, "第1题", "images", "img1.png"), "wb") as f:
            f.write(_1PX_PNG)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generate_combined_docx(self):
        out_dir = os.path.join(self.tmp, "out")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        self.assertTrue(os.path.exists(docx_path))

        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        ET.fromstring(doc)
        ET.fromstring(cmt)

        n_cmt = len(self._findall(cmt, "<w:comment w:id="))
        n_start = len(self._findall(doc, "<w:commentRangeStart"))
        n_end = len(self._findall(doc, "<w:commentRangeEnd"))
        n_ref = len(self._findall(doc, "<w:commentReference"))
        self.assertEqual(n_cmt, 2)
        self.assertEqual(n_start, n_end)
        self.assertEqual(n_end, n_ref)
        self.assertEqual(n_ref, n_cmt)

    def test_no_caption_and_no_uuid(self):
        out_dir = os.path.join(self.tmp, "out2")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertNotIn("CaptionedFigure", doc)
        self.assertNotIn("@@@", doc)

    def test_image_embedded_and_renamed(self):
        out_dir = os.path.join(self.tmp, "out3")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertGreaterEqual(doc.count("<w:drawing>"), 1)
        media = [n for n in z.namelist() if n.startswith("word/media/")]
        self.assertTrue(media)

    def test_headings_and_page_breaks(self):
        out_dir = os.path.join(self.tmp, "out4")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertEqual(len(self._findall(doc, 'w:val="Heading1"')), 2)
        self.assertGreaterEqual(len(self._findall(doc, 'w:type="page"')), 1)

    def test_empty_dir_returns_none(self):
        empty = os.path.join(self.tmp, "空目录")
        os.makedirs(empty)
        self.assertIsNone(generate_combined_docx(empty, self.tmp))

    def test_relative_out_dir_resolved_to_absolute(self):
        """回归：相对 out_dir 时 docx 必须落到调用方 cwd 下且返回绝对路径。

        修复前：pandoc 以临时工作目录为 cwd，相对 out_dir 把 docx 写进临时目录
        （finally 即删），_inject_comments 按调用方 cwd 打开相对路径抛
        FileNotFoundError，generate_combined_docx 捕获后返回 None。
        """
        old_cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            docx_path = generate_combined_docx(self.paper, "output/校对Word")
            self.assertIsNotNone(docx_path)
            self.assertTrue(os.path.isabs(docx_path))
            self.assertTrue(os.path.exists(docx_path))
            # 文件必须真实落在 out_dir 对应的相对位置，而非漂移到 pandoc 临时目录
            rel = os.path.join("output", "校对Word", os.path.basename(docx_path))
            self.assertTrue(os.path.exists(rel))
            z = zipfile.ZipFile(docx_path)
            cmt = z.read("word/comments.xml").decode("utf-8")
            self.assertEqual(len(self._findall(cmt, "<w:comment w:id=")), 2)
        finally:
            os.chdir(old_cwd)

    @staticmethod
    def _findall(text, needle):
        return [m for m in range(len(text)) if text.startswith(needle, m)]


@PANDOC_REQUIRED
class TestStderrNoneResilience(unittest.TestCase):
    """回归：pandoc 转换成功但 CompletedProcess.stderr 为 None 时报告仍须生成。

    修复前：成功路径的 fetch 告警检查 r.stderr.strip() 在 None 上抛
    AttributeError，被外层 except 吞掉返回 None——此时 pandoc 已转换成功、
    批注注入尚未执行，整份 Word 报告失败（Windows 打包 exe 实测现场，
    capture_output=True 下 stderr 仍为 None，机制未复现，判空兜底）。
    """

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_stderr_none_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        q = os.path.join(self.paper, "第1题")
        os.makedirs(os.path.join(q, "images"))
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(REPORT_WITH_MARKS)
        with open(os.path.join(q, "images", "img1.png"), "wb") as f:
            f.write(_1PX_PNG)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_stderr_none_does_not_abort_report(self):
        from jiaodui import docx_report
        real_run = docx_report.subprocess.run

        def _run_stderr_none(*args, **kwargs):
            r = real_run(*args, **kwargs)
            r.stderr = None
            return r

        with mock.patch.object(docx_report.subprocess, "run",
                               side_effect=_run_stderr_none):
            docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        self.assertTrue(os.path.exists(docx_path))
        z = zipfile.ZipFile(docx_path)
        cmt = z.read("word/comments.xml").decode("utf-8")
        self.assertEqual(cmt.count("<w:comment w:id="), 2)


@PANDOC_REQUIRED
class TestSkippedUnitsDiagnostics(unittest.TestCase):
    """回归：无分段跳过必须区分「无批注（正常）」与「含标记但缺分段（可疑）」。

    修复前：LLM 判定「无问题」的报告（只有 无问题+工具日志+思考过程，
    无 ### 标记原文/### 修改原因 分段）被统一记 ⚠️「分段异常，跳过」，
    正常业务形态被误标为异常，误导排查。
    """

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_skip_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_paper(self, units):
        """units: {目录名: 报告内容}，另加一个带批注的基准单元保证 docx 生成。"""
        paper = os.path.join(self.tmp, "测试试卷")
        for name, content in units.items():
            d = os.path.join(paper, name)
            os.makedirs(d)
            with open(os.path.join(d, "_校对报告.md"), "w", encoding="utf-8") as f:
                f.write(content)
        return paper

    NO_ISSUE_REPORT = """无问题

---

## 📋 工具调用日志

共调用 1 次

## 📋 模型思考过程（仅核查用，不出现在 PDF 中）

题目与解答均无错误。
"""

    WITH_SECTIONS_NO_MARKS = """单元N 校对报告

**总结行：无问题**（题干严谨、解析推导与实算一致、答案正确）

### 标记原文
**教师版**（2022·模拟）（多选）
如图所示，金属棒从$h$高处释放，不计空气阻力。

### 修改原因

无

---

## 📋 工具调用日志

共调用 11 次

## 📊 Token 用量统计
"""

    def test_with_sections_zero_marks_gets_no_issue_comment(self):
        """回归：带完整分段但零标记的报告（总结行=无问题）必须生成「无问题」批注。

        修复前：LLM 按完整分段格式输出时走批注解析分支，零标记 → 零批注，
        「无问题」单元在 Word 报告里没有任何标注。与无分段形态同等对待。
        """
        from jiaodui import docx_report
        paper = self._make_paper({
            "第1题": REPORT_WITH_MARKS,
            "单元7": self.WITH_SECTIONS_NO_MARKS,
        })
        with open(os.path.join(paper, "单元7", "单元7.md"), "w", encoding="utf-8") as f:
            f.write("**教师版**（2022·模拟）（多选）\n如图所示，金属棒从$h$高处释放，不计空气阻力。\n")
        with mock.patch.object(docx_report, "log") as mlog:
            docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out_seg"))
        self.assertIsNotNone(docx_path)
        messages = [c.args[0] for c in mlog.call_args_list]
        self.assertTrue(any("单元7 无批注" in m for m in messages))
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 单元原文正文已插入（锚点落在标题，正文保持完整）
        self.assertIn("2022·模拟", doc)
        # 第1题 2 条批注 + 单元7「无问题」批注
        self.assertEqual(cmt.count("<w:comment w:id="), 3)
        self.assertIn("无问题", cmt)
        self.assertEqual(cmt.count("无问题"), 1)
        # 「无问题」批注锚定在 Heading1 标题段内（gid 3 = 第1题 1、2 之后的第一个空闲号）
        heading_pat = re.compile(
            r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1"[^>]*/>\s*</w:pPr>'
            r'\s*<w:commentRangeStart w:id="3"/>', re.DOTALL)
        self.assertIsNotNone(heading_pat.search(doc))

    def test_no_issue_unit_listed_as_no_issue(self):
        """「无问题」报告（无分段、无批注标记）必须列入报告并标注，不得记 ⚠️ 异常"""
        from jiaodui import docx_report
        paper = self._make_paper({
            "第1题": REPORT_WITH_MARKS,
            "单元7": self.NO_ISSUE_REPORT,
        })
        with mock.patch.object(docx_report, "log") as mlog:
            docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        messages = [c.args[0] for c in mlog.call_args_list]
        self.assertTrue(any("单元7 无批注" in m for m in messages))
        self.assertFalse(any("分段异常" in m or "含批注标记" in m for m in messages))
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 无批注单元出现在报告里（独立标题 + 无问题标注），不产生批注
        self.assertEqual(len(self._findall(doc, 'w:val="Heading1"')), 2)
        self.assertIn("无问题", doc)
        self.assertEqual(cmt.count("<w:comment w:id="), 2)

    def test_no_issue_unit_with_md_inserts_original_and_comment(self):
        """无问题单元存在单元 md 时：插入原文正文，并在正文开头生成「无问题」批注"""
        paper = self._make_paper({
            "第1题": REPORT_WITH_MARKS,
            "单元7": self.NO_ISSUE_REPORT,
        })
        with open(os.path.join(paper, "单元7", "单元7.md"), "w", encoding="utf-8") as f:
            f.write("**教师版**（2022·模拟）（多选）\n如图所示，金属棒从$h$高处释放。\n")
        docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out2"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 单元原文正文已插入（粗体「教师版」被锚点拆为两个 run，分别断言）
        self.assertIn("教", doc)
        self.assertIn("师版", doc)
        self.assertIn("2022·模拟", doc)
        self.assertIn("<m:oMath>", doc)
        # 生成「无问题」批注（锚点在 Heading1 标题段内，非正文）
        self.assertEqual(cmt.count("<w:comment w:id="), 3)
        self.assertIn("无问题", cmt)
        self.assertEqual(cmt.count("无问题"), 1)
        heading_pat = re.compile(
            r'<w:p>\s*<w:pPr>\s*<w:pStyle w:val="Heading1"[^>]*/>\s*</w:pPr>'
            r'\s*<w:commentRangeStart w:id="3"/>', re.DOTALL)
        self.assertIsNotNone(heading_pat.search(doc))

    def test_all_no_issue_units_still_generate_report(self):
        """整份试卷全部无问题也必须生成报告（标注无问题），不得返回 None"""
        paper = self._make_paper({
            "单元7": self.NO_ISSUE_REPORT,
            "单元9": self.NO_ISSUE_REPORT,
        })
        docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out_noissue"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertEqual(len(self._findall(doc, 'w:val="Heading1"')), 2)
        self.assertEqual(doc.count("无问题"), 2)

    def test_url_image_ref_replaced_with_text(self):
        """外链 https:// 图片引用（LLM 幻觉）转为文字说明，不得重写成垃圾本地路径"""
        from jiaodui import docx_report
        url_report = REPORT_WITH_MARKS.replace(
            "![@@@testuuid00000000000000000000000001](./images/img1.png)",
            "![外链图](https://p3-hippo-sign.example.com/x/y.png?lk3s=19ff00fe&x-expires=2067)")
        paper = self._make_paper({"第1题": url_report})
        with mock.patch.object(docx_report, "log") as mlog:
            docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out_url"))
        self.assertIsNotNone(docx_path)
        messages = [c.args[0] for c in mlog.call_args_list]
        self.assertFalse(any("图片未找到" in m for m in messages))
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        self.assertIn("外链图片无法嵌入", doc)
        self.assertNotIn("p3-hippo-sign", doc)
        self.assertNotIn("lk3s=", doc)

    @staticmethod
    def _findall(text, needle):
        return [m for m in range(len(text)) if text.startswith(needle, m)]

    def test_marked_without_sections_warns_and_skips(self):
        """含 【N|原|改】 标记但缺分段 → ⚠️ 警告（批注可能丢失）且该单元跳过"""
        from jiaodui import docx_report
        paper = self._make_paper({
            "第1题": REPORT_WITH_MARKS,
            "单元9": "有批注标记但缺分段：【1|原句|改为句】\n",
        })
        with mock.patch.object(docx_report, "log") as mlog:
            docx_path = generate_combined_docx(paper, os.path.join(self.tmp, "out2"))
        self.assertIsNotNone(docx_path)
        messages = [c.args[0] for c in mlog.call_args_list]
        self.assertTrue(any("单元9 含批注标记但缺少" in m for m in messages))
        # 该单元被跳过：批注仍只来自第1题
        z = zipfile.ZipFile(docx_path)
        cmt = z.read("word/comments.xml").decode("utf-8")
        self.assertEqual(cmt.count("<w:comment w:id="), 2)


@PANDOC_REQUIRED
class TestEscapedPipeInMarkers(unittest.TestCase):
    """回归：原文字段中的 LaTeX 转义竖线 \\| 不得被当作字段分隔符。

    修复前：_PAT 按 [^|] 分割，【N|$\\left\\|…\right\\|$|改】 的 original 在
    \\| 处截断，后半截拼进 correction 还带 |，批注内容损坏。
    """

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_pipe_test_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        q = os.path.join(self.paper, "第1题")
        os.makedirs(q)
        report = (
            "# 第1题 校对报告\n\n一般问题\n\n"
            "### 标记原文\n编号：第1题\n内容：\n"
            "总电动势【1|${E}_{总}=\\left\\|{E}_{1}-{E}_{2}\\right\\|$|"
            "${E}_{总}=\\left|{E}_{1}-{E}_{2}\\right|$】，方向与【2|大者|数值较大的电动势】一致。\n\n"
            "### 修改原因\n1. 双竖线改单竖线。\n2. 表述严谨。\n"
        )
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_latex_pipe_not_split(self):
        r"""\| 转义竖线整体保留在 original，批注数正确"""
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        self.assertEqual(cmt.count("<w:comment w:id="), 2)
        # 原文公式（含 \| 双竖线）作为整体被锚定：批注范围完整包住 oMath 对象
        self.assertIn('<w:commentRangeStart w:id="1"/><m:oMath>', doc)
        self.assertIn('</m:oMath><w:commentRangeEnd w:id="1"/>', doc)
        # 双竖线符号 ∥（pandoc 将 \left\| 转为 OMML 的 begChr/endChr）保留在锚点内
        self.assertIn("∥", doc)
        # 改后（单竖线公式）写入批注内容：matplotlib 可用时渲染为公式图片、
        # 不再以 LaTeX 文本出现；缺失时按契约降级为原文文本（此处不强求图片）
        if HAS_MPL:
            self.assertIn("<w:drawing>", cmt)
            self.assertNotIn(r"\left|{E}_{1}-{E}_{2}\right|", cmt)


class TestConvertMultilineTables(unittest.TestCase):
    """回归：_convert_multiline_tables 不得把普通 bullet 列表误判为表格。

    修复前：判定条件 startswith("-") and len>=10 把任意 10 字以上列表项
    当作 multiline table 边框，正文被按 2+ 空格切分成网格表格静默改写。
    修复后：只有「整行全部由 - 组成」的长线才是表格边框。
    """

    def setUp(self):
        from jiaodui.docx_report import _convert_multiline_tables
        self._convert = _convert_multiline_tables

    def test_bullet_list_not_treated_as_table(self):
        """两条以上 bullet 列表项必须原样保留，不得转成网格表格"""
        text = (
            "### 标记原文\n\n"
            "- 首先我们先看这道题目的已知条件是什么\n"
            "- 其次要注意单位换算关系\n"
            "- 最后检查计算过程是否合理"
        )
        out = self._convert(text)
        self.assertNotIn("|", out)
        self.assertIn("- 首先我们先看这道题目的已知条件是什么", out)
        self.assertIn("- 其次要注意单位换算关系", out)
        self.assertIn("- 最后检查计算过程是否合理", out)

    def test_single_bullet_not_treated_as_table(self):
        """单条 bullet（无配对边界）也不受影响"""
        text = "- 这是一条超过十个字符的普通列表项内容"
        out = self._convert(text)
        self.assertEqual(out, text)

    def test_real_multiline_table_still_converted(self):
        """真实 multiline table（--- 边框）仍应转为 grid table"""
        text = (
            "前文\n\n"
            "---------------\n"
            "列一  列二  列三\n"
            "甲    乙    丙\n"
            "---------------\n\n"
            "后文"
        )
        out = self._convert(text)
        self.assertIn("| 列一", out)
        self.assertIn("| 甲", out)
        self.assertIn("前文", out)
        self.assertIn("后文", out)

    def test_short_separator_untouched(self):
        """短 --- markdown 分隔线保持原样"""
        text = "正文\n\n---\n\n后续"
        out = self._convert(text)
        self.assertEqual(out, text)

    def test_empty_and_plain_text(self):
        self.assertEqual(self._convert(""), "")
        plain = "没有任何表格的普通段落。\n第二行。"
        self.assertEqual(self._convert(plain), plain)


REPORT_WITH_FORMULA_MARKS = """# 第1题 校对报告

轻微问题

### 标记原文
编号：第1题
内容：
【1|$v_{1}=1m/s$|$v_{1}=1\\,\\mathrm{m/s}$】

【2|$x$|$s$】

【3|$Q_{电热}$|$Q_2$】

【4|$E=BLv$|$E_1=BLv_1$】

【5|$A$|$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$】

### 修改原因
1. 公式 $E=BLv$ 符号不统一。
2. 矩阵公式 $\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$ 应降级为文本。
"""


@PANDOC_REQUIRED
@pytest.mark.skipif(not HAS_MPL, reason="matplotlib 不可用")
class TestCommentFormulaImages(unittest.TestCase):
    """批注内 `$...$` 公式渲染为 PNG 图片注入。"""

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("matplotlib 不可用，跳过公式图片测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_formula_test_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        os.makedirs(os.path.join(self.paper, "第1题"))
        with open(os.path.join(self.paper, "第1题", "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(REPORT_WITH_FORMULA_MARKS)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _generate(self):
        out_dir = os.path.join(self.tmp, "out")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        return z, {
            n: z.read(n).decode("utf-8")
            for n in z.namelist()
            if n in ("word/comments.xml", "word/_rels/comments.xml.rels", "[Content_Types].xml")
        }

    def test_formula_rendered_as_image(self):
        z, parts = self._generate()
        cmt = parts["word/comments.xml"]
        ET.fromstring(cmt)
        # 可渲染公式 → drawing 图片
        drawings = len(self._findall(cmt, "<w:drawing>"))
        self.assertGreaterEqual(drawings, 3)
        # 批注图片 part 写入
        media_files = [n for n in z.namelist() if "comment_pic" in n]
        self.assertEqual(len(media_files), drawings)
        # rels 注册齐全
        rels = parts["word/_rels/comments.xml.rels"]
        ET.fromstring(rels)
        self.assertEqual(len(self._findall(rels, "<Relationship ")), drawings)
        for mf in media_files:
            self.assertIn(mf.replace("word/media/", "media/"), rels)
        # png Content-Type 声明
        self.assertIn('Extension="png"', parts["[Content_Types].xml"])

    def test_unsupported_formula_degrades_to_text(self):
        _, parts = self._generate()
        cmt = parts["word/comments.xml"]
        # 矩阵公式渲染失败 → 保留原 LaTeX 文本（\\ 还原为单反斜杠、& 转义）
        self.assertIn("$\\begin{pmatrix} a &amp; b \\ c &amp; d \\end{pmatrix}$", cmt)
        # 可渲染的公式不应以 $...$ 文本残留
        self.assertNotIn("$E=BLv$", cmt)
        self.assertNotIn("$E_1=BLv_1$", cmt)
        self.assertNotIn("$v_{1}=1\\,\\mathrm{m/s}$", cmt)
        self.assertNotIn("$s$", cmt)
        self.assertNotIn("$Q_2$", cmt)

    def _findall(self, text, sub):
        return [m for m in re.finditer(re.escape(sub), text)]


@PANDOC_REQUIRED
class TestAnchorInsideFormula(unittest.TestCase):
    """锚点位于公式内部的标记：跳过批注、还原标记原文，防止撕裂公式。"""

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_formula_anchor_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        q = os.path.join(self.paper, "第1题")
        os.makedirs(q)
        report = (
            "# 第1题 校对报告\n\n一般问题\n\n"
            "### 标记原文\n编号：第1题\n内容：\n"
            "安培力做功大小为$\\frac{{B}^{2}{L}^{2}【1|$v$|$v_0$】x}{R+r}$\n\n"
            "正常标记【2|导体棒|金属棒】后续文本\n\n"
            "### 修改原因\n1. 公式内锚点。\n2. 正常标记。\n"
        )
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_formula_anchor_skipped_and_text_restored(self):
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 公式内标记被跳过：只生成公式外那条批注
        self.assertEqual(cmt.count("<w:comment w:id="), 1)
        # 公式不转微软公式（保留为 LaTeX 文本），oMath 不包含被跳过公式
        self.assertNotIn("<m:oMath>", doc)
        # 公式以文本形式显示，并被黄色高亮（mark ==...== → w:highlight）
        self.assertIn("frac", doc)
        self.assertIn('<w:highlight w:val="yellow" />', doc)
        # 占位符已还原，无残留
        self.assertNotIn("SKIPANCH", doc)
        # 正常标记的批注仍生成
        self.assertIn("金属棒", cmt)


@PANDOC_REQUIRED
class TestSkipAnchorRobustness(unittest.TestCase):
    """稳健性：多个相同公式/文本时，占位符必须精确定位目标公式。"""

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_skip_robust_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        q = os.path.join(self.paper, "第1题")
        os.makedirs(q)
        report = (
            "# 第1题 校对报告\n\n一般问题\n\n"
            "### 标记原文\n编号：第1题\n内容：\n"
            "甲式：$\\frac{{B}^{2}{L}^{2}【1|$v$|$v_0$】x}{R+r}$\n\n"
            "乙式：$\\frac{{B}^{2}{L}^{2}vx}{R+r}$（与甲式完全相同）\n\n"
            "丙式：$\\frac{{B}^{2}{L}^{2}vx}{R+r}$\n\n"
            "### 修改原因\n1. 符号统一。\n"
        )
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_identical_formulas_only_target_highlighted(self):
        """三个相同公式：仅含标记的甲式被文本化高亮，乙丙两式保持 oMath。"""
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 仅甲式被跳过（无批注），乙丙两式无标记不受影响
        self.assertEqual(cmt.count("<w:comment w:id="), 0)
        # 乙丙两式保持微软公式（2 个 oMath），甲式文本化不高亮误伤
        self.assertEqual(doc.count("<m:oMath>"), 2)
        self.assertIn('<w:highlight w:val="yellow" />', doc)
        # 高亮内容含甲式的 LaTeX 文本（frac），且不含 SKIPANCH 残留
        self.assertIn("frac", doc)
        self.assertNotIn("SKIPANCH", doc)

    def test_identical_text_marker_untouched(self):
        """相同文本多次出现但标记在公式外时，正常批注不受影响。"""
        q = os.path.join(self.paper, "第2题")
        os.makedirs(q)
        report = (
            "# 第2题 校对报告\n\n一般问题\n\n"
            "### 标记原文\n编号：第2题\n内容：\n"
            "导体棒运动，导体棒【1|导体棒|金属棒】运动，导体棒停止。\n\n"
            "### 修改原因\n1. 术语统一。\n"
        )
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out2"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 三个「导体棒」中仅第二个被锚定批注，批注内容正确
        self.assertEqual(cmt.count("<w:comment w:id="), 1)
        self.assertIn("金属棒", cmt)
        self.assertIn("导体棒", doc)
        self.assertNotIn("SKIPANCH", doc)


@PANDOC_REQUIRED
class TestExtremeFormulaAnchors(unittest.TestCase):
    """极端情况：标记字段内含 $、多标记同公式、空原文、公式外标记含 $。"""

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_extreme_")
        self.paper = os.path.join(self.tmp, "测试试卷")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, qname, content):
        q = os.path.join(self.paper, qname)
        os.makedirs(q)
        report = (
            f"# {qname} 校对报告\n\n一般问题\n\n"
            "### 标记原文\n编号：第1题\n内容：\n"
            f"{content}\n\n### 修改原因\n1. 修正。\n"
        )
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        return z.read("word/document.xml").decode("utf-8"), \
            z.read("word/comments.xml").decode("utf-8")

    def test_marker_field_with_dollar_inside_formula(self):
        """标记字段内含 $（【1|aaa$|bbb$】）位于公式内：识别为公式内并文本化。"""
        doc, cmt = self._make("第1题", "安培力做功大小为$\\frac{【1|aaa$|bbb$】x}{R+r}$")
        # 无批注（跳过）、公式文本化 + 高亮 + 修改意见（$ 剥离后）
        self.assertEqual(cmt.count("<w:comment w:id="), 0)
        self.assertIn('<w:highlight w:val="yellow" />', doc)
        self.assertIn("修改意见：aaa→bbb", doc)
        self.assertNotIn("SKIPANCH", doc)
        self.assertNotIn("superscript", doc)

    def test_multiple_anchors_same_formula(self):
        """同一公式内多个标记：全部还原并展示各自修改意见。"""
        doc, cmt = self._make(
            "第1题", "总功为$\\frac{【1|a|b】c【2|d|e】}{R}$")
        self.assertEqual(cmt.count("<w:comment w:id="), 0)
        self.assertIn("修改意见：a→b", doc)
        self.assertIn("修改意见：d→e", doc)
        self.assertNotIn("SKIPANCH", doc)

    def test_marker_with_dollar_outside_formula_normal_comment(self):
        """标记在公式外但字段内含 $：不误判公式内，正常生成批注。"""
        doc, cmt = self._make("第1题", "电阻【1|aaa$|bbb$】阻值，由$E=BLv$得")
        self.assertEqual(cmt.count("<w:comment w:id="), 1)
        self.assertIn("bbb", cmt)
        self.assertIn("<m:oMath>", doc)  # $E=BLv$ 正常转公式
        self.assertNotIn("修改意见", doc)

    def test_empty_orig_inside_formula(self):
        """原文字段为空的标记不生成批注，也不撕裂公式（Issue 056 新契约）。

        空原文字段零信息，旧行为会在公式里插入高亮与「修改意见：→bbb」文本；
        现由程序初筛在源头拦下，Word 侧只记录告警、不生成批注，公式保持原样。
        """
        doc, cmt = self._make("第1题", "结果为$\\frac{【1||bbb】x}{R}$")
        self.assertEqual(cmt.count("<w:comment w:id="), 0)
        self.assertNotIn("SKIPANCH", doc)
        self.assertNotIn("&lt;w:commentRange", doc)
        self.assertIn("<m:oMath>", doc)
        self.assertIn("<m:t>x</m:t>", doc)
        self.assertIn("<m:t>R</m:t>", doc)

    def test_escaped_bracket_field_keeps_anchor(self):
        """回归（第8讲 单元9）：字段内含 \\[..\\] 且后文有 $ 时，锚点不得被吞。

        修复前：正文的「\\[…\\] → $…$」还原把字段内的转义方括号改写成 $，
        字段 $ 配对错乱，pandoc 用多余的 $ 开出跨行公式，把 commentRangeEnd
        /commentReference 当普通文本输出——批注丢失、正文残留字面 XML。
        """
        doc, cmt = self._make(
            "第1题",
            "体积【1|$V_{A2}=l_{A}S=\\[l_{1}-(h_{B}-H)\\]S=\\left\\[13.5-\\left(2-H\\right)\\right\\]S$"
            "|$V_{A2}=l_{A}S=[l_{1}-(h_{B}-H)]S$】，其中$H$为高度\n"
            "对$A$管内气体，由玻意耳定律得$p_{A1}V_{A1}=p_{A2}V_{A2}$")
        self.assertEqual(cmt.count("<w:comment w:id="), 1)
        self.assertEqual(doc.count("<w:commentRangeStart"), 1)
        self.assertEqual(doc.count("<w:commentRangeEnd"), 1)
        self.assertEqual(doc.count("<w:commentReference"), 1)
        self.assertNotIn("&lt;w:commentRange", doc)

    def test_whole_field_display_math_converted(self):
        """字段整体是 \\[…\\] 行间公式时仍还原为 $…$（单元22 场景不回归）。"""
        doc, cmt = self._make(
            "第1题",
            "省力的大小为【1|\\[1-(\\frac{{V}_{0}}{{V}_{0}+{V}_{1}})^{n}\\]"
            "|$\\left[1-(\\frac{{V}_{0}}{{V}_{0}+{V}_{1}})^{n}\\right]$】$p_{0}S$")
        self.assertEqual(cmt.count("<w:comment w:id="), 1)
        self.assertEqual(doc.count("<w:commentRangeEnd"), 1)
        self.assertEqual(doc.count("<w:commentReference"), 1)
        self.assertIn("<m:oMath", doc)
        self.assertNotIn("\\[1-", doc)

    def test_broken_anchor_cleaned_and_logged(self):
        """兜底：字段配对仍不自洽（模拟上游再次引入）——清理残引用并告警。"""
        from jiaodui import docx_report
        with mock.patch.object(docx_report, "_math_safe", return_value=True):
            with mock.patch.object(docx_report, "log") as mlog:
                doc, cmt = self._make(
                    "第1题",
                    "体积【1|$V_{A2}=l_{A}S=$l_{1}-(h_{B}-H)$S=\\left$13.5-\\right$S$"
                    "|$V_{A2}=l_{A}S=l_{1}S$】\n对$A$管内气体得$p_{A1}V_{A1}=p_{A2}V_{A2}$")
        self.assertEqual(doc.count("<w:commentRangeStart"), 0)
        self.assertEqual(doc.count("<w:commentRangeEnd"), 0)
        self.assertEqual(doc.count("<w:commentReference"), 0)
        self.assertEqual(cmt.count("<w:comment w:id="), 0)
        self.assertNotIn("&lt;w:commentRange", doc)
        self.assertTrue(any("锚点不完整" in c.args[0] for c in mlog.call_args_list))


class TestMarkerFieldMathSafety(unittest.TestCase):
    """标记字段的 LaTeX 处理：字段内部 \\[ 不被当定界符；插入前做真实配对校验。"""

    def test_field_keeps_inner_escaped_brackets(self):
        from jiaodui.docx_report import _preprocess_marker_field
        field = "$V_{A2}=l_{A}S=\\[l_{1}-(h_{B}-H)\\]S$"
        self.assertEqual(_preprocess_marker_field(field), field)

    def test_whole_field_display_math_converted(self):
        from jiaodui.docx_report import _preprocess_marker_field
        self.assertEqual(_preprocess_marker_field("\\[a=b\\]"), "$a=b$")
        self.assertEqual(_preprocess_marker_field("\\\\[a=b\\\\]"), "$a=b$")

    def test_rm_normalized_inside_field(self):
        from jiaodui.docx_report import _preprocess_marker_field
        self.assertEqual(_preprocess_marker_field("$d=0.2{\\rm m}$"), "$d=0.2\\mathrm{m}$")

    def test_math_safe_balanced(self):
        from jiaodui.docx_report import _math_safe
        self.assertTrue(_math_safe("$a=b$"))
        self.assertTrue(_math_safe("体积$V_{A2}=l_{A}S=\\[l_{1}-(h_{B}-H)\\]S$"))
        self.assertTrue(_math_safe("无公式"))
        self.assertTrue(_math_safe("$a$$b$"))

    def test_math_safe_detects_mispairing(self):
        from jiaodui.docx_report import _math_safe
        # 闭 $ 右侧是数字 → pandoc 不认，该 $ 退化为字面量，剩余的 $ 会吞掉后文 raw
        self.assertFalse(_math_safe("$V_{A2}=l_{A}S=$l_{1}-(h_{B}-H)$S=\\left$13.5-\\right$S$"))
        self.assertFalse(_math_safe("$a=$1.5$"))
        # 开 $ 右侧空白 / 空公式 / 悬空 $
        self.assertFalse(_math_safe("$ a$"))
        self.assertFalse(_math_safe("$$"))
        self.assertFalse(_math_safe("abc$"))
        self.assertFalse(_math_safe("a$b$c$"))

    @pytest.mark.skipif(PANDOC is None, reason="pandoc 不可用")
    def test_math_safe_matches_pandoc_pairing(self):
        """用 pandoc 实际配对结果锁定 _math_safe 的判据（独立来源）。"""
        from jiaodui.docx_report import _math_safe
        cases = ["$a=b$", "$a$$b$", "$V=lS=$x$y=\\left$13.5-\\right$S$", "abc$"]
        for field in cases:
            with self.subTest(field=field):
                raw = (f"体积`<w:commentRangeStart w:id=\"1\"/>`{{=openxml}}{field}"
                       f"`<w:commentRangeEnd w:id=\"1\"/>`{{=openxml}}\n对$A$管内气体")
                r = subprocess.run(
                    [find_pandoc(), "-f", "markdown-implicit_figures+hard_line_breaks+mark",
                     "-t", "native", "-"],
                    input=raw, capture_output=True, text=True)
                parsed_raw = 'RawInline\n        (Format "openxml") "<w:commentRangeEnd' in r.stdout
                self.assertEqual(_math_safe(field), parsed_raw)


@PANDOC_REQUIRED
class TestMarkerIntegrityDocx(unittest.TestCase):
    """标记真实性：空操作不生成批注、虚构标记不污染正文（Issue 056，跑通 pandoc）。"""

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_integrity_")
        self.paper = os.path.join(self.tmp, "测试试卷")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make(self, qname, content, source=None):
        q = os.path.join(self.paper, qname)
        os.makedirs(q)
        report = (f"# {qname} 校对报告\n\n轻微问题\n\n### 标记原文\n"
                  f"{content}\n\n### 修改原因\n1. 修正。\n")
        with open(os.path.join(q, "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(report)
        if source is not None:
            with open(os.path.join(q, f"{qname}.md"), "w", encoding="utf-8") as f:
                f.write(source)
        docx_path = generate_combined_docx(self.paper, os.path.join(self.tmp, "out"))
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        return (z.read("word/document.xml").decode("utf-8"),
                z.read("word/comments.xml").decode("utf-8"))

    def test_noop_marker_generates_no_comment(self):
        """原文与改为完全相同（单元6「第四枚→第四枚」）：不生成批注，正文照旧。"""
        doc, cmt = self._make("第1题", "$(选填“需要”或“不需要”)$【1|第四枚|第四枚】大头针；")
        self.assertEqual(cmt.count("<w:comment w:id="), 0)
        self.assertEqual(doc.count("<w:commentRangeStart"), 0)
        self.assertIn("第四枚", doc)

    def test_phantom_marker_body_restored_from_correction(self):
        """虚构标记（单元6「0 → $O$」）：正文按改为还原，源文不再被写成「交于0点」。

        批注保留 —— 程序无法区分「源文此处本就正确」与「源文确有错字但原文字段
        与左邻文本重叠」（第 8 讲单元8 实测），丢批注会静默漏掉真实校对结论。
        """
        content = "①在白纸上画一条直线$ab$，并画出其垂线$cd$，交于【1|0|$O$】点；"
        source = "①在白纸上画一条直线$ab$，并画出其垂线$cd$，交于$O$点；\n②确定位置。"
        doc, cmt = self._make("第1题", content, source=source)
        self.assertEqual(cmt.count("<w:comment w:id="), 1)
        self.assertEqual(doc.count("<w:commentRangeStart"), 1)
        self.assertEqual(doc.count("<w:commentRangeEnd"), 1)
        self.assertEqual(doc.count("<w:commentReference"), 1)
        self.assertNotIn("0</w:t>", doc)
        self.assertNotIn("交于0点", doc)
        self.assertIn("<m:t>O</m:t>", doc)

    def test_source_missing_keeps_original_rendering(self):
        """源文缺失（非本目录布局）：不做猜测，正文仍按原文字段渲染并保留批注。"""
        doc, cmt = self._make("第1题", "交于【1|0|$O$】点；")
        self.assertEqual(cmt.count("<w:comment w:id="), 1)
        self.assertIn("0", doc)


class TestStripUnanchoredComments(unittest.TestCase):
    """兜底清理：锚点残缺引用与残留字面 openxml 文本（纯 XML，不依赖 pandoc）。"""

    def test_start_without_end_dropped(self):
        from jiaodui.docx_report import _strip_unanchored_comments
        doc = ('<w:body><w:p><w:commentRangeStart w:id="3"/>'
               '<w:r><w:t>x</w:t></w:r></w:p></w:body>')
        out, kept, dropped = _strip_unanchored_comments(doc)
        self.assertEqual(kept, set())
        self.assertEqual(dropped, ["3"])
        self.assertNotIn("commentRangeStart", out)

    def test_end_without_start_dropped(self):
        from jiaodui.docx_report import _strip_unanchored_comments
        doc = ('<w:body><w:p><w:commentRangeEnd w:id="3"/>'
               '<w:r><w:commentReference w:id="3"/></w:r></w:p></w:body>')
        out, kept, dropped = _strip_unanchored_comments(doc)
        self.assertEqual(kept, set())
        self.assertEqual(dropped, ["3"])
        self.assertNotIn("commentRangeEnd", out)
        self.assertNotIn("commentReference", out)

    def test_complete_anchor_kept(self):
        from jiaodui.docx_report import _strip_unanchored_comments
        doc = ('<w:p><w:commentRangeStart w:id="1"/><w:r><w:t>x</w:t></w:r>'
               '<w:commentRangeEnd w:id="1"/>'
               '<w:r><w:commentReference w:id="1"/></w:r></w:p>')
        out, kept, dropped = _strip_unanchored_comments(doc)
        self.assertEqual(kept, {"1"})
        self.assertEqual(dropped, [])
        self.assertIn("commentRangeStart", out)

    def test_leaked_openxml_text_removed(self):
        from jiaodui.docx_report import _strip_leaked_openxml
        doc = ('<w:p><w:r><w:t xml:space="preserve">$`&lt;w:commentRangeEnd w:id=&quot;3&quot;/&gt;'
               '&lt;w:r&gt;&lt;w:commentReference w:id=&quot;3&quot;/&gt;&lt;/w:r&gt;'
               '`{=openxml}</w:t></w:r></w:p>')
        out, leaked = _strip_leaked_openxml(doc)
        self.assertEqual(leaked, ["3"])
        self.assertNotIn("commentRangeEnd", out)
        self.assertNotIn("{=openxml}", out)

    def test_leaked_cleanup_does_not_cross_xml_tags(self):
        """字面标记跨真实 XML 标签时不误删正文结构。"""
        from jiaodui.docx_report import _strip_leaked_openxml
        doc = ('<w:p><w:r><w:t>`&lt;w:commentRangeStart w:id=&quot;5&quot;/&gt;</w:t></w:r>'
               '<w:r><w:t>{=openxml}</w:t></w:r></w:p>')
        out, leaked = _strip_leaked_openxml(doc)
        self.assertEqual(leaked, [])
        self.assertEqual(out, doc)


class TestAnchorHeadingComments(unittest.TestCase):
    """B2：Heading1 标题锚点注入的 XML 转义与告警。"""

    @staticmethod
    def _heading_xml(w_t_text):
        return (
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            f'<w:r><w:rPr><w:b/></w:rPr><w:t>{w_t_text}</w:t></w:r></w:p>'
        )

    def test_title_with_amp_anchored(self):
        """标题含 & 时用 XML 转义后匹配 w:t 内的 &amp;。"""
        from jiaodui.docx_report import _anchor_heading_comments
        doc_xml = self._heading_xml("A&amp;B")
        result = _anchor_heading_comments(doc_xml, {1: "A&B"})
        self.assertIn('commentRangeStart w:id="1"', result)
        self.assertIn('commentReference w:id="1"', result)

    def test_title_with_lt_anchored(self):
        """标题含 < 时用 XML 转义后匹配 w:t 内的 &lt;。"""
        from jiaodui.docx_report import _anchor_heading_comments
        doc_xml = self._heading_xml("A&lt;B")
        result = _anchor_heading_comments(doc_xml, {1: "A<B"})
        self.assertIn('commentRangeStart w:id="1"', result)

    def test_unmatched_title_logs_warning(self):
        """标题匹配不到时记录告警（不再静默清掉批注）。"""
        from jiaodui import docx_report
        from jiaodui.docx_report import _anchor_heading_comments
        doc_xml = self._heading_xml("第1题")
        with mock.patch.object(docx_report, "log") as mlog:
            _anchor_heading_comments(doc_xml, {1: "不存在"})
        self.assertTrue(any("未在 Heading1 段落匹配" in c.args[0] for c in mlog.call_args_list))


REPORT_FENCED_MARKER_SECTION = """# 第1题 校对报告

轻微问题

### 标记原文

```
编号：第1题
内容：
1．导体棒以速度【1|速度|速率】运动，感应电动势为 $E=BLv$，间距$d=0.2{\\rm m}$。

![@@@testuuid00000000000000000000000001](./images/img1.png){width="1.0in" height="0.8in"}
```

### 修改原因
1. "速度"应改为"速率"，速度有方向。
"""


@PANDOC_REQUIRED
class TestFencedMarkerSection(unittest.TestCase):
    """回归：LLM 用 ``` 围栏包住标记原文 → 生成器应剥除围栏。

    修复前：围栏使 pandoc 按代码块渲染，公式不转 OMML、图片与批注锚点
    全部变成字面文本。
    """

    @classmethod
    def setUpClass(cls):
        if not find_pandoc():
            raise unittest.SkipTest("pandoc 不可用，跳过 docx 报告测试")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="_docx_fence_test_")
        self.paper = os.path.join(self.tmp, "测试试卷")
        os.makedirs(os.path.join(self.paper, "第1题", "images"))
        with open(os.path.join(self.paper, "第1题", "_校对报告.md"), "w", encoding="utf-8") as f:
            f.write(REPORT_FENCED_MARKER_SECTION)
        with open(os.path.join(self.paper, "第1题", "images", "img1.png"), "wb") as f:
            f.write(_1PX_PNG)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_fence_stripped_math_converted(self):
        out_dir = os.path.join(self.tmp, "out")
        docx_path = generate_combined_docx(self.paper, out_dir)
        self.assertIsNotNone(docx_path)
        z = zipfile.ZipFile(docx_path)
        doc = z.read("word/document.xml").decode("utf-8")
        cmt = z.read("word/comments.xml").decode("utf-8")
        # 公式转为 OMML，不残留字面 $...$（含 {{\\rm}} 形态）
        self.assertIn("<m:oMath", doc)
        self.assertNotIn("$E=BLv$", doc)
        self.assertNotIn("$d=0.2", doc)
        # 图片真实嵌入（不再是字面 ![](...) 文本）
        self.assertIn("<w:drawing>", doc)
        # 批注锚点完整：start/end/reference/comment 数量一致
        self.assertEqual(doc.count("<w:commentRangeStart"), 1)
        self.assertEqual(doc.count("<w:commentRangeEnd"), 1)
        self.assertEqual(doc.count("<w:commentReference"), 1)
        self.assertEqual(cmt.count("<w:comment w:id="), 1)


class TestPreprocessLatexRm(unittest.TestCase):
    """_preprocess_latex：{\\rm X} / \\rm{X} 归一化为 \\mathrm{X}。

    texmath 不支持 \\rm 切换命令，不定式时 pandoc 放弃转换、公式以 TeX
    文本原样显示。
    """

    def test_brace_rm_converted(self):
        from jiaodui.docx_report import _preprocess_latex
        self.assertEqual(_preprocess_latex("间距$d=0.2{\\rm m}$"),
                         "间距$d=0.2\\mathrm{m}$")

    def test_rm_brace_converted(self):
        from jiaodui.docx_report import _preprocess_latex
        self.assertEqual(_preprocess_latex("故$\\rm{A}$正确"),
                         "故$\\mathrm{A}$正确")

    def test_rm_slash_unit_converted(self):
        from jiaodui.docx_report import _preprocess_latex
        self.assertEqual(_preprocess_latex("初速度$v_{0}=0.2{\\rm m/s}$"),
                         "初速度$v_{0}=0.2\\mathrm{m/s}$")

    def test_mathrm_untouched(self):
        from jiaodui.docx_report import _preprocess_latex
        text = "电压为$4.0\\times {10}^{-2}\\mathrm{V}$"
        self.assertEqual(_preprocess_latex(text), text)

    def test_prose_untouched(self):
        from jiaodui.docx_report import _preprocess_latex
        plain = "**例1**（2024·月考）（多选）"
        self.assertEqual(_preprocess_latex(plain), plain)


class TestStripWrappingFence(unittest.TestCase):
    """_strip_wrapping_fence：只剥首尾孤立围栏行，正文中间与普通文本不动。"""

    def test_strips_wrapping_fence(self):
        from jiaodui.docx_report import _strip_wrapping_fence
        self.assertEqual(_strip_wrapping_fence("```\nabc\n```"), "abc")
        self.assertEqual(_strip_wrapping_fence("~~~\nabc\n~~~"), "abc")

    def test_strips_fence_with_language_tag(self):
        from jiaodui.docx_report import _strip_wrapping_fence
        self.assertEqual(_strip_wrapping_fence("```markdown\nabc\n```"), "abc")

    def test_keeps_inner_fence(self):
        from jiaodui.docx_report import _strip_wrapping_fence
        self.assertEqual(_strip_wrapping_fence("a\n```\nb```"), "a\n```\nb```")

    def test_plain_text_unchanged(self):
        from jiaodui.docx_report import _strip_wrapping_fence
        plain = "**例1** 公式$v$与图片引用"
        self.assertEqual(_strip_wrapping_fence(plain), plain)


# ---------------- build_docx：生成后复核实际锚点（PRD §5.1 / §6.4 硬门槛） ----------------

FORMULA_FALLBACK_REPORT = """# 第1题 校对报告

一般问题

### 标记原文
编号：第1题
内容：
安培力做功大小为$\\frac{{B}^{2}{L}^{2}【1|$v$|$v_0$】x}{R+r}$

正常标记【2|导体棒|金属棒】后续文本

### 修改原因
1. 公式内锚点。
2. 正常标记。
"""

NOOP_REPORT = """# 第1题 校对报告

轻微问题

### 标记原文
编号：第1题
内容：
正常【1|甲|乙】；空操作【2|增大|增大】。

### 修改原因
1. 改。
"""

NO_ISSUE_SHORT = """无问题

---

## 📋 工具调用日志

共调用 1 次
"""


def _source_from_report(text):
    """从报告反推「重建正文」作为单元源文，使报告能通过 verify-report 闸门。

    仅用于 build_docx 测试的 fixture 搭建；闸门本身的行为由 test_verify_contract 锁定。
    """
    from jiaodui.markers import split_marked_body
    from jiaodui.report_parse import split_sections, strip_reference_preamble

    _head, marked, _reasons = split_sections(text)
    return split_marked_body(strip_reference_preamble(marked or ""))


def _write_unit_report(paper, unit, text):
    d = paper / unit
    d.mkdir(parents=True, exist_ok=True)
    (d / "_校对报告.md").write_text(text, encoding="utf-8")
    src = d / f"{unit}.md"
    if not src.exists():
        src.write_text(_source_from_report(text), encoding="utf-8")
    return d


def _make_illustrated_paper(tmp_path, units):
    paper = tmp_path / "测试试卷"
    for unit, text in units.items():
        _write_unit_report(paper, unit, text)
    (paper / "第1题" / "images").mkdir(parents=True, exist_ok=True)
    (paper / "第1题" / "images" / "img1.png").write_bytes(_1PX_PNG)
    return paper


@PANDOC_REQUIRED
class TestBuildDocxAudit:
    """build_docx 生成后解压复核：错误标记 = 锚点 + 公式可见兜底，缺失为 0。"""

    def test_counts_match_actual_anchors(self, tmp_path):
        paper = _make_illustrated_paper(
            tmp_path, {"第1题": REPORT_WITH_MARKS, "第2题": REPORT_NO_MARKS})
        res = build_docx(str(paper), str(tmp_path / "out"))
        assert isinstance(res, DocxBuildResult)
        assert res.marker_count == 2
        assert res.anchor_count == 2
        assert res.formula_fallback_count == 0
        assert res.missing_count == 0
        # 第2题为无问题单元，按契约单列一条标题批注
        assert res.heading_comment_count == 1
        assert res.ok is True
        assert [u["unit"] for u in res.units] == ["第1题", "第2题"]
        assert all(u["missing"] == 0 for u in res.units)
        assert res.out_path and os.path.exists(res.out_path)
        z = zipfile.ZipFile(res.out_path)
        doc = z.read("word/document.xml").decode("utf-8")
        assert doc.count("<w:commentRangeStart") == doc.count("<w:commentRangeEnd")
        assert doc.count("<w:commentRangeEnd") == doc.count("<w:commentReference")

    def test_formula_fallback_counts_as_covered(self, tmp_path):
        paper = _make_illustrated_paper(tmp_path, {"第1题": FORMULA_FALLBACK_REPORT})
        res = build_docx(str(paper), str(tmp_path / "out"))
        assert res.marker_count == 2
        assert res.anchor_count == 1
        assert res.formula_fallback_count == 1
        assert res.missing_count == 0
        assert res.ok is True
        z = zipfile.ZipFile(res.out_path)
        doc = z.read("word/document.xml").decode("utf-8")
        assert '<w:highlight w:val="yellow" />' in doc
        assert "（修改意见：" in doc
        assert "SKIPANCH" not in doc

    def test_no_issue_heading_comment_listed_separately(self, tmp_path):
        src7 = "**教师版** 金属棒从$h$高处释放。"
        no_issue_valid = "无问题\n\n### 标记原文\n" + src7 + "\n\n### 修改原因\n无\n"
        paper = _make_illustrated_paper(
            tmp_path, {"第1题": REPORT_WITH_MARKS, "单元7": no_issue_valid})
        res = build_docx(str(paper), str(tmp_path / "out"))
        assert res.marker_count == 2
        assert res.anchor_count == 2
        assert res.heading_comment_count == 1
        assert res.missing_count == 0
        assert res.ok is True
        unit7 = [u for u in res.units if u["unit"] == "单元7"][0]
        assert unit7["markers"] == 0
        assert unit7["heading_comment"] == 1

    def test_noop_marker_unit_excluded(self, tmp_path):
        """空操作报告未通过 verify-report，必须排除出 Word 交付。"""
        paper = _make_illustrated_paper(tmp_path, {"第1题": NOOP_REPORT})
        res = build_docx(str(paper), str(tmp_path / "out"))
        assert res.marker_count == 0, "不合格报告不得计入"
        assert [e["unit"] for e in res.excluded_units] == ["第1题"]
        assert "空操作" in res.excluded_units[0]["reason"]
        assert res.ok is False

    def test_broken_unit_excluded_not_counted(self, tmp_path):
        """含标记但缺分段的单元未过闸门，排除且不计入标记数。"""
        paper = _make_illustrated_paper(tmp_path, {
            "第1题": REPORT_WITH_MARKS,
            "单元9": "有批注标记但缺分段：【1|原句|改为句】\n",
        })
        res = build_docx(str(paper), str(tmp_path / "out"))
        assert res.marker_count == 2, "只统计合格单元"
        assert [e["unit"] for e in res.excluded_units] == ["单元9"]
        assert res.ok is False

    def test_empty_dir_not_ok(self, tmp_path):
        empty = tmp_path / "空目录"
        empty.mkdir()
        res = build_docx(str(empty), str(tmp_path / "out"))
        assert res.out_path is None
        assert res.ok is False
        assert res.warnings

    def test_relative_out_dir_resolved_absolute(self, tmp_path):
        paper = _make_illustrated_paper(tmp_path, {"第1题": REPORT_WITH_MARKS})
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            res = build_docx(str(paper), "output/校对Word")
        finally:
            os.chdir(old_cwd)
        assert res.ok is True
        assert res.out_path and os.path.isabs(res.out_path)
        assert os.path.exists(res.out_path)

    def test_generate_combined_docx_compat_wrapper(self, tmp_path):
        paper = _make_illustrated_paper(tmp_path, {"第1题": REPORT_WITH_MARKS})
        path = generate_combined_docx(str(paper), str(tmp_path / "out"))
        assert isinstance(path, str)
        assert os.path.exists(path)
        z = zipfile.ZipFile(path)
        cmt = z.read("word/comments.xml").decode("utf-8")
        assert cmt.count("<w:comment w:id=") == 2



if __name__ == "__main__":
    unittest.main()

def test_anchor_pairing_ok():
    from jiaodui.docx_report import _check_anchor_pairing
    doc = ('<w:commentRangeStart w:id="1"/><w:p/><w:commentRangeEnd w:id="1"/>'
           '<w:r><w:commentReference w:id="1"/></w:r>')
    ok, problems = _check_anchor_pairing(doc, {"1"})
    assert ok and not problems


def test_anchor_pairing_detects_id_mismatch():
    from jiaodui.docx_report import _check_anchor_pairing
    doc = ('<w:commentRangeStart w:id="1"/><w:commentRangeEnd w:id="999"/>'
           '<w:commentReference w:id="999"/>')
    ok, problems = _check_anchor_pairing(doc, {"1"})
    assert not ok
    assert any(("不一致" in p) or ("缺少" in p) for p in problems)


def test_anchor_pairing_detects_duplicate_and_order():
    from jiaodui.docx_report import _check_anchor_pairing
    dup = ('<w:commentRangeStart w:id="1"/><w:commentRangeStart w:id="1"/>'
           '<w:commentRangeEnd w:id="1"/><w:commentReference w:id="1"/>')
    ok, problems = _check_anchor_pairing(dup, {"1"})
    assert not ok and any("重复" in p for p in problems)
    bad_order = ('<w:commentRangeStart w:id="1"/><w:commentReference w:id="1"/>'
                 '<w:commentRangeEnd w:id="1"/>')
    ok2, problems2 = _check_anchor_pairing(bad_order, {"1"})
    assert not ok2 and any("顺序" in p for p in problems2)



def test_anchor_pairing_detects_extra_end_and_reference():
    from jiaodui.docx_report import _check_anchor_pairing
    doc = ('<w:commentRangeStart w:id="1"/><w:commentRangeEnd w:id="1"/>'
           '<w:r><w:commentReference w:id="1"/></w:r>'
           '<w:commentRangeEnd w:id="999"/><w:r><w:commentReference w:id="999"/></w:r>')
    ok, problems = _check_anchor_pairing(doc, {"1"})
    assert not ok
    assert any("999" in p for p in problems)


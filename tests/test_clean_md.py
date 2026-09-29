"""测试 jiaodui.convert 的 comprehensive_clean 与 md 后处理契约。

comprehensive_clean 部分逐字移植自旧仓 tests/test_comprehensive_clean.py
（去掉出题意图清理一节，该功能不在本次移植范围）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jiaodui.convert import (
    clean_md_file,
    clean_md_text,
    comprehensive_clean,
    normalize_caret_tilde,
    post_process_md,
)
from jiaodui.decor_utils import (
    DECOR_MAX_H,
    DECOR_MAX_W,
    strip_decor_images,
    strip_decor_images_from_file,
)


# ============================================================
# 基础功能
# ============================================================

class TestBasicMathProtection:
    """基础数学公式保护与恢复"""

    def test_inline_math_preserved(self):
        """内联公式 $...$ 不应被破坏"""
        assert comprehensive_clean(r"$a+b$") == r"$a+b$"

    def test_display_math_preserved(self):
        """显示公式 $$...$$ 不应被破坏"""
        assert comprehensive_clean(r"$$x^2+y^2=z^2$$") == r"$$x^2+y^2=z^2$$"

    def test_multiline_display_math(self):
        """多行显示公式应保留"""
        assert comprehensive_clean("$$\na + b = c\n$$") == "$$\na + b = c\n$$"

    def test_math_with_special_chars(self):
        r"""公式中的特殊字符（^、_、{、}、\）应保留"""
        assert comprehensive_clean(r"$x^{2} + y_{1} = z$") == r"$x^{2} + y_{1} = z$"

    def test_multiple_inline_math(self):
        """同一行多个内联公式"""
        assert comprehensive_clean(r"$a$ 和 $b$ 和 $c$") == r"$a$ 和 $b$ 和 $c$"

    def test_empty_input(self):
        """空输入"""
        assert comprehensive_clean("") == ""

    def test_no_math(self):
        """不含数学公式的纯文本"""
        assert comprehensive_clean("这是纯文本，没有公式。") == "这是纯文本，没有公式。"


# ============================================================
# 核心回归测试：碎片化公式（本次修复的目标 bug）
# ============================================================

class TestFragmentedMathRegression:
    """碎片化 $...$ 相邻 $$ 场景 —— 不应产生 MATH 占位符残留"""

    def test_chemistry_fragmented_C_option(self):
        r"""高中化学 C 选项碎片化公式：$\mathrm{C}$...$$=\!$$=\!$$=..."""
        # 这是本次 bug 的精确复现
        input_text = (
            r'$\mathrm{C}$．由反应'
            r'$\mathrm{S}{\mathrm{O}}_{3}^{2-}+{\mathrm{I}}_{2}+{\mathrm{H}}_{2}\mathrm{O}$'
            r'$$=\!$$=\!$$=\mathrm{S}{\mathrm{O}}_{4}^{2-}+2{\mathrm{I}}^{-}+2{\mathrm{H}}^{+}$'
            r'可知'
        )
        result = comprehensive_clean(input_text)
        # 绝不能包含 MATH 占位符残留
        assert 'MATH' not in result, f"残留 MATH 占位符: {result}"
        # 也不能包含 \x00 空字节
        assert '\x00' not in result, "残留空字节"
        # 所有原始 $ 符号应存在（10 对 = 20 个 $）
        assert result.count('$') == input_text.count('$'), \
            f"$ 数量不匹配: 期望 {input_text.count('$')}, 实际 {result.count('$')}"
        # 关键内容应完整
        assert r'\mathrm{C}' in result
        assert r'\mathrm{S}{\mathrm{O}}_{3}^{2-}' in result
        assert r'\mathrm{S}{\mathrm{O}}_{4}^{2-}' in result

    def test_chemistry_fragmented_D_option(self):
        r"""高中化学 D 选项碎片化公式：$\mathrm{D}$...$$=\!$$=\!$$=..."""
        input_text = (
            r'$\mathrm{D}$．由反应'
            r'$\mathrm{S}{\mathrm{O}}_{3}^{2-}+2{\mathrm{S}}^{2-}+6{\mathrm{H}}^{+}$'
            r'$$=\!$$=\!$$=3\mathrm{S}\downarrow +3{\mathrm{H}}_{2}\mathrm{O}$'
            r'可知'
        )
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert r'\mathrm{D}' in result
        assert r'\downarrow' in result

    def test_three_consecutive_fragments(self):
        """三个连续的 $...$ 碎片与相邻 $$"""
        input_text = r'$A$$$B$$$C$$$D$'
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert result == r'$A$$$B$$$C$$$D$'

    def test_fragment_with_pipe_protection(self):
        """碎片化公式 + 管道符混合场景"""
        input_text = r'$|x|$$$=|y|$$'
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result


# ============================================================
# 连公式场景（原始用例，确保不回归）
# ============================================================

class TestConsecutiveMath:
    """连公式场景：$x=$$a+b$ 等"""

    def test_consecutive_inline(self):
        """两个内联公式相邻 $x=$$a+b$"""
        assert comprehensive_clean(r"$x=$$a+b$") == r"$x=$$a+b$"

    def test_three_consecutive_inline(self):
        """三个内联公式相邻"""
        assert comprehensive_clean(r"$a$$b$$c$") == r"$a$$b$$c$"

    def test_consecutive_mixed_with_text(self):
        """连公式中间夹文本"""
        assert comprehensive_clean(r"由$x=$$a+b$可知") == r"由$x=$$a+b$可知"

    def test_consecutive_with_subscripts(self):
        """连公式含上下标"""
        assert comprehensive_clean(r"$x^{2}$$=y_{1}$") == r"$x^{2}$$=y_{1}$"

    def test_consecutive_with_mathrm(self):
        r"""连公式含 \mathrm"""
        assert comprehensive_clean(r"$\mathrm{A}$$\mathrm{B}$") == r"$\mathrm{A}$$\mathrm{B}$"


# ============================================================
# 嵌套/内嵌场景
# ============================================================

class TestNestedMath:
    """嵌套数学块保护"""

    def test_display_math_containing_inline(self):
        """$$...$...$...$$ 显示公式内嵌内联公式"""
        input_text = r"$$x = $a+b$ + y$$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert result == input_text

    def test_display_math_containing_multiple_inline(self):
        """$$ 包含多个 $...$ 块"""
        input_text = r"$$f(x) = $a$ + $b$ \cdot x$$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result

    def test_inline_containing_dollar_text(self):
        r"""$...$ 中的 \$ 转义（边界情况，验证不会崩溃）"""
        input_text = r"$\$5.00$"
        result = comprehensive_clean(input_text)
        # 不崩溃即可，不严格要求 \$ 处理
        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================
# 表格管道符清理
# ============================================================

class TestTablePipeCleanup:
    """表格 | 字符清理"""

    def test_pipe_removed_outside_math(self):
        """公式外的 | 应被移除"""
        result = comprehensive_clean(r"| 文本 | $a+b$ |")
        assert '|' not in result
        assert r"$a+b$" in result

    def test_pipe_preserved_inside_math(self):
        """公式内的 |（绝对值、集合）应保留"""
        # 绝对值
        result = comprehensive_clean(r"$|x|$ 和 $|y|$")
        assert r"$|x|$" in result
        assert r"$|y|$" in result

    def test_table_line_removed(self):
        """表格分隔行应被移除"""
        result = comprehensive_clean("| --- | --- |\n| a | b |")
        assert '---' not in result

    def test_table_with_math_and_pipes(self):
        """表格中有公式也有管道"""
        input_text = "| $\\alpha$ | $\\beta$ |\n| --- | --- |\n| $x$ | $y$ |"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result

    def test_答案_line_merge(self):
        """'答案:' 行应与下一行合并"""
        input_text = "答案:\nB"
        result = comprehensive_clean(input_text)
        assert "答案: B" in result

    # ---- 表格边框行清理（带序号前缀） ----

    def test_table_border_with_pandoc_ordered_list_prefix(self):
        """Pandoc 转义序号前缀的表格边框行应被移除：1\\.  +---+"""
        input_text = (
            "1\\.  +----------------------------------+"
            "--------------------------------------------------------------------"
            "---------------------------------------------------------------+\n"
            "答案：  B\n"
            "解答：  这是解答内容。\n"
            "2\\.  +----------------------------------+"
            "--------------------------------------------------------------------"
            "---------------------------------------------------------------+\n"
            "解答：  第二题解答。"
        )
        result = comprehensive_clean(input_text)
        # 边框行应被移除
        assert '+---' not in result, f"残留表格边框: {result}"
        assert '答案：  B' in result
        assert '解答：  这是解答内容' in result
        assert '解答：  第二题解答' in result

    def test_table_border_with_plain_ordered_list_prefix(self):
        """普通序号前缀的表格边框行应被移除：1. +---+"""
        input_text = (
            "1. +-------+--------+\n"
            "答案：  A\n"
            "解答：  内容。"
        )
        result = comprehensive_clean(input_text)
        assert '+---' not in result, f"残留表格边框: {result}"
        assert '答案：  A' in result

    def test_table_border_with_multi_digit_prefix(self):
        """多位序号前缀的表格边框行应被移除：12\\.  +---+"""
        input_text = (
            "12\\.  +-----+-----+\n"
            "内容行"
        )
        result = comprehensive_clean(input_text)
        assert '+---' not in result, f"残留表格边框: {result}"
        assert '内容行' in result

    def test_table_border_line_only_removed_not_content(self):
        """仅移除表格边框行，保留前面的内容行"""
        input_text = (
            "1\\.  +-----------+\n"
            "这是一条正常内容。\n"
            "2\\.  +-----------+\n"
            "这也是正常内容。"
        )
        result = comprehensive_clean(input_text)
        assert '+---' not in result, f"残留表格边框: {result}"
        assert '这是一条正常内容' in result
        assert '这也是正常内容' in result

    def test_nested_table_border_with_prefix(self):
        """嵌套表格中的边框行：| | 1\\.  | +---+ → 应被跳过"""
        input_text = (
            "| 前面内容 | 列2 |\n"
            "| | 1\\.                               | +----------------------------------+------------------------+\n"
            "| | 选项A                             | 内容A                            |\n"
        )
        result = comprehensive_clean(input_text)
        assert '+---' not in result, f"残留嵌套表格边框: {result}"
        assert '选项A' in result
        assert '内容A' in result

    def test_nested_table_border_multi_prefix(self):
        """嵌套表格中多个序号边框行均被跳过"""
        input_text = (
            "| | 1\\.  | +-----+-----+\n"
            "| | 选项 | 内容 |\n"
            "| | 2\\.  | +-----+-----+\n"
            "| | 答案 | 结果 |\n"
        )
        result = comprehensive_clean(input_text)
        assert '+---' not in result, f"残留边框: {result}"

    # ---- 纯 - 分隔线清理（无 + 或 |） ----

    def test_pure_dash_separator_removed(self):
        """纯 - 分隔线（无 + 或 |）应被移除"""
        input_text = (
            "前面内容。\n"
            "-----------------------------------------------------------------------\n"
            "后面内容。"
        )
        result = comprehensive_clean(input_text)
        assert '---' not in result, f"残留分隔线: {result}"
        assert '前面内容' in result
        assert '后面内容' in result

    def test_dash_space_mixed_separator_removed(self):
        """- 和空格混合的分隔线应被移除（如 Pandoc 表格残留）"""
        input_text = (
            "前面。\n"
            "----------------- ---------------------------------------- -----------------\n"
            "后面。"
        )
        result = comprehensive_clean(input_text)
        assert '---' not in result, f"残留分隔线: {result}"
        assert '前面' in result
        assert '后面' in result

    def test_long_dash_separator_removed(self):
        """超长纯 - 分隔线应被移除"""
        input_text = (
            "开头。\n"
            + "-" * 120 + "\n"
            "结尾。"
        )
        result = comprehensive_clean(input_text)
        assert '---' not in result, f"残留分隔线: {result}"
        assert '开头' in result
        assert '结尾' in result

    def test_ellipsis_preserved(self):
        """纯省略号行（...）应保留不被误删"""
        input_text = (
            "前面内容。\n"
            "...\n"
            "后面内容。"
        )
        result = comprehensive_clean(input_text)
        assert '...' in result, f"省略号被误删: {result}"

    def test_multiple_ellipsis_preserved(self):
        """长省略号行（......）应保留"""
        input_text = "前面。\n..........\n后面。"
        result = comprehensive_clean(input_text)
        assert '....' in result, f"省略号被误删: {result}"


# ============================================================
# 复杂综合场景
# ============================================================

class TestComplexScenarios:
    """复杂的综合场景"""

    def test_full_chemistry_answer_section(self):
        """完整的化学解答区域（含 A/B/C/D 四个选项的解答）"""
        input_text = (
            r'$\mathrm{A}$．由反应${\mathrm{S}}^{2-}+{\mathrm{I}}_{2}=\!=\!='
            r'\mathrm{S}\downarrow +2{\mathrm{I}}^{-}$可知，'
            r'还原剂${\mathrm{S}}^{2-}$的还原性大于还原产物${\mathrm{I}}^{-}$的还原性，'
            r'符合题意，可以发生，故$\mathrm{A}$不选；'
        )
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert r'\mathrm{A}' in result
        assert r'\downarrow' in result

    def test_latex_with_curly_braces(self):
        """多层花括号嵌套的 LaTeX"""
        input_text = r"${\mathrm{Fe(OH)}}_{3}$ 和 ${\mathrm{CaCO}}_{3}$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert result == input_text

    def test_ion_charges(self):
        r"""离子电荷表示：${\mathrm{Fe}}^{2+}$、${\mathrm{SO}}_{4}^{2-}$"""
        input_text = r"${\mathrm{Fe}}^{2+}$ 和 ${\mathrm{SO}}_{4}^{2-}$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert result == input_text

    def test_chemical_equation_with_conditions(self):
        """含反应条件的化学方程式"""
        input_text = (
            r'$2{\mathrm{H}}_{2}+{\mathrm{O}}_{2}'
            r'\xlongequal{\mathrm{点燃}}'
            r'2{\mathrm{H}}_{2}\mathrm{O}$'
        )
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result

    def test_mixed_display_and_inline(self):
        """混合显示公式和内联公式"""
        input_text = (
            r'由$$E=mc^{2}$$可得$E$与$m$成正比。'
            r'又$$F=ma$$因此$a=F/m$。'
        )
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert r'$$E=mc^{2}$$' in result
        assert r'$$F=ma$$' in result
        assert r'$a=F/m$' in result

    def test_long_text_with_many_math_blocks(self):
        """长文本中散布大量数学块"""
        input_text = (
            r'已知$a>0$，$b>0$，且$a+b=1$，'
            r'求$\frac{1}{a}+\frac{1}{b}$的最小值。'
            r'由基本不等式$$x+y\geq 2\sqrt{xy}$$可得'
            r'$\frac{1}{a}+\frac{1}{b}\geq\frac{4}{a+b}=4$，'
            r'当且仅当$a=b=\frac{1}{2}$时取等。'
        )
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        # 关键内容完整
        assert r'$$x+y\geq 2\sqrt{xy}$$' in result
        assert r'\frac{1}{a}' in result

    def test_quadruple_dollar(self):
        """四个连续的 $：$$$$"""
        input_text = r"$$$$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result

    def test_double_dollar_adjacent_to_single(self):
        """$$ 后面紧跟 $"""
        input_text = r"$$x$$$y$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result


# ============================================================
# 边界情况
# ============================================================

class TestEdgeCases:
    """边界情况"""

    def test_unbalanced_math_is_untouched(self):
        """不配对的 $ 应保持原样（不崩溃）"""
        input_text = r"$a+b 没有闭合"
        result = comprehensive_clean(input_text)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_only_dollar_signs(self):
        """纯 $ 符号"""
        result = comprehensive_clean("$$$")
        assert isinstance(result, str)

    def test_math_at_line_start(self):
        """行首的公式"""
        assert comprehensive_clean(r"$x$ 开头") == r"$x$ 开头"

    def test_math_at_line_end(self):
        """行尾的公式"""
        assert comprehensive_clean(r"结尾 $x$") == r"结尾 $x$"

    def test_single_dollar(self):
        """单个 $ 符号"""
        result = comprehensive_clean(r"价格 $5")
        assert isinstance(result, str)
        assert '$' in result or '5' in result  # 至少不崩溃

    def test_newlines_inside_math(self):
        """公式跨行（$...$ 内部不应跨行，但 $$ 可以）"""
        input_text = "$$\na\nb\n$$"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result

    def test_chinese_and_math_mixed(self):
        """中文和数学公式混排"""
        input_text = r"根据公式$F=ma$，当$m=2\mathrm{kg}$时，$a=3\mathrm{m/s^{2}}$。"
        result = comprehensive_clean(input_text)
        assert 'MATH' not in result
        assert '\x00' not in result
        assert result == input_text



# ============================================================
# 文本清理入口与文件级清理
# ============================================================


class TestCleanMdText:
    """clean_md_text 是 comprehensive_clean 的纯函数入口。"""

    def test_clean_md_text_alias(self):
        raw = "| a | b |\n| --- | --- |\n正文"
        assert clean_md_text(raw) == comprehensive_clean(raw)

    def test_clean_md_text_preserves_math(self):
        assert clean_md_text(r"$|x|$") == r"$|x|$"


class TestCleanMdFile:
    """clean_md_file 读文件 → 清理 → 写回。"""

    def test_clean_md_file_removes_table_pipes(self, tmp_path):
        f = tmp_path / "a.md"
        f.write_text("| a | b |\n正文", encoding="utf-8")
        assert clean_md_file(str(f)) is True
        assert "|" not in f.read_text(encoding="utf-8")
        assert "正文" in f.read_text(encoding="utf-8")

    def test_clean_md_file_missing_returns_false(self, tmp_path):
        assert clean_md_file(str(tmp_path / "nope.md")) is False


# ============================================================
# post_process_md（文件 I/O，契约移植自 test_normalize_caret_tilde.py）
# ============================================================


class TestPostProcessMd:
    """fix_pandoc_comment_anomaly → normalize_caret_tilde → convert_display_to_inline。"""

    def test_writes_normalized_content(self, tmp_path):
        f = tmp_path / "raw.md"
        f.write_text("速度v^2^和时间t~0~\n", encoding="utf-8")
        assert post_process_md(str(f)) is True
        result = f.read_text(encoding="utf-8")
        assert "v<上标>2</上标>" in result
        assert "t<下标>0</下标>" in result

    def test_unchanged_content_not_rewritten(self, tmp_path):
        f = tmp_path / "raw.md"
        content = "v<上标>2</上标> 已处理"
        f.write_text(content, encoding="utf-8")
        import time
        mtime_before = f.stat().st_mtime
        time.sleep(0.01)
        assert post_process_md(str(f)) is False
        assert f.stat().st_mtime == mtime_before
        assert f.read_text(encoding="utf-8") == content

    def test_fixes_pandoc_comment_anomaly(self, tmp_path):
        f = tmp_path / "raw.md"
        f.write_text("前\x60<!-- -->\x60{=html}后", encoding="utf-8")
        assert post_process_md(str(f)) is True
        assert f.read_text(encoding="utf-8") == "前后"

    def test_collapses_single_line_display_math(self, tmp_path):
        f = tmp_path / "raw.md"
        f.write_text("由$$E=mc^2$$可得", encoding="utf-8")
        assert post_process_md(str(f)) is True
        assert f.read_text(encoding="utf-8") == "由$E=mc^2$可得"

    def test_multiline_display_math_kept(self, tmp_path):
        f = tmp_path / "raw.md"
        content = "$$\na+b\n$$"
        f.write_text(content, encoding="utf-8")
        assert post_process_md(str(f)) is False
        assert f.read_text(encoding="utf-8") == content

    def test_missing_file_returns_false(self, tmp_path):
        assert post_process_md(str(tmp_path / "nope.md")) is False


# ============================================================
# 装饰图片清除（移植自 tests/test_decor_utils.py）
# ============================================================


class TestStripDecorImages:
    """验证 strip_decor_images 核心行为。"""

    def test_threshold_is_04_inch(self):
        assert DECOR_MAX_W == 0.4
        assert DECOR_MAX_H == 0.4

    def test_title_icon_test_alt_deleted(self):
        md = '### 模型大招![test](media/image1.png){width="0.194in" height="0.194in"}'
        assert strip_decor_images(md) == "### 模型大招"

    def test_title_icon_empty_alt_deleted(self):
        md = '### 必备知识![](media/image17.png){width="0.194in" height="0.194in"}'
        assert strip_decor_images(md) == "### 必备知识"

    def test_problem_image_kept(self):
        md = '![test](media/image16.png){width="0.875in" height="0.78125in"}'
        assert strip_decor_images(md) == md

    def test_smallest_real_image_kept(self):
        md = '![test](media/image81.png){width="0.479in" height="0.667in"}'
        assert strip_decor_images(md) == md

    def test_stretched_table_icon_kept(self):
        md = '![test](media/image2.png){width="1.222in" height="1.472in"}'
        assert strip_decor_images(md) == md

    def test_boundary_exact_04_kept(self):
        md = '![test](media/x.png){width="0.4in" height="0.4in"}'
        assert strip_decor_images(md) == md

    def test_boundary_just_below_deleted(self):
        md = '![test](media/x.png){width="0.399in" height="0.399in"}'
        assert strip_decor_images(md) == ""

    def test_width_only_not_matched(self):
        md = '![test](media/x.png){width="0.194in"}'
        assert strip_decor_images(md) == md

    def test_non_test_alt_kept(self):
        md = '![IMG_256](media/image256.png){width="0.208in" height="0.146in"}'
        assert strip_decor_images(md) == md

    def test_mixed_content(self):
        md = (
            '### 模型大招![test](media/i1.png){width="0.194in" height="0.194in"}\n'
            '![test](media/i16.png){width="0.875in" height="0.78125in"}\n'
            '![IMG_1](media/i3.png){width="0.2in" height="0.2in"}'
        )
        assert strip_decor_images(md) == (
            '### 模型大招\n'
            '![test](media/i16.png){width="0.875in" height="0.78125in"}\n'
            '![IMG_1](media/i3.png){width="0.2in" height="0.2in"}'
        )


class TestStripDecorImagesFromFile:
    """验证 strip_decor_images_from_file 文件写回行为。"""

    def test_file_modified_when_decor_found(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text('### 必备知识![test](media/i.png){width="0.194in" height="0.194in"}', encoding="utf-8")
        assert strip_decor_images_from_file(str(f)) is True
        assert f.read_text(encoding="utf-8") == "### 必备知识"

    def test_file_untouched_when_no_decor(self, tmp_path):
        f = tmp_path / "doc.md"
        original = '![test](media/i16.png){width="0.875in" height="0.78125in"}'
        f.write_text(original, encoding="utf-8")
        assert strip_decor_images_from_file(str(f)) is False
        assert f.read_text(encoding="utf-8") == original


# ============================================================
# normalize_caret_tilde 纯函数契约（移植自 tests/test_normalize_caret_tilde.py）
# ============================================================


class TestNormalizeCaretTildeBasic:
    """基本上下标转换"""

    def test_superscript_single_char(self):
        assert normalize_caret_tilde("x^2^") == "x<上标>2</上标>"

    def test_superscript_multi_char(self):
        assert normalize_caret_tilde("a^10^") == "a<上标>10</上标>"

    def test_subscript_single_char(self):
        assert normalize_caret_tilde("H~2~O") == "H<下标>2</下标>O"

    def test_subscript_multi_char(self):
        assert normalize_caret_tilde("v~max~") == "v<下标>max</下标>"

    def test_mixed_sup_and_sub(self):
        result = normalize_caret_tilde("v^2^ + a~0~")
        assert result == "v<上标>2</上标> + a<下标>0</下标>"

    def test_multiple_superscripts(self):
        result = normalize_caret_tilde("x^2^ + y^3^")
        assert result == "x<上标>2</上标> + y<上标>3</上标>"

    def test_superscript_in_italic(self):
        """斜体标记 *...* 保持不动，仅内部 ^x^ 转换"""
        result = normalize_caret_tilde("*v^2^*")
        assert result == "*v<上标>2</上标>*"

    def test_subscript_in_italic(self):
        result = normalize_caret_tilde("*v~0~*")
        assert result == "*v<下标>0</下标>*"


class TestNormalizeCaretTildeEscapes:
    """转义号还原（步骤 3、4）"""

    def test_escaped_tilde_restored(self):
        """\\~ → ~"""
        assert normalize_caret_tilde(r"from 0\~2s") == "from 0~2s"

    def test_escaped_caret_restored(self):
        r"""\^ → ^"""
        assert normalize_caret_tilde(r"use \^ for power") == "use ^ for power"

    def test_escaped_caret_not_confused_with_superscript(self):
        r"""\^2^ — 字面 ^ + superscript 结束符，不应转为 <上标>"""
        result = normalize_caret_tilde(r"\^2^")
        # lookbehind 跳过 \^ → step 2 不匹配 → step 4 还原
        assert result == "^2^"
        assert "<上标>" not in result

    def test_escaped_then_superscript(self):
        r"""\^a^ — 字面 ^ 后恰好有 ^a^ 上标模式。

        实际行为：step 2 先运行，此时 \^ 处 lookbehind 跳过，末位 ^ 后无内容无法形成匹配。
        step 4 还原 \^ → ^，结果为 ^a^（未转为 <上标>）。

        这是正确行为——\^ 是 pandoc 对字面脱字号的转义，不应触发上标转换。
        """
        result = normalize_caret_tilde(r"\^a^")
        # step 2: \^ lookbehind 跳过 → 末位 ^ 无后继字符 → 不匹配
        # step 4: \^ → ^
        assert result == "^a^"


class TestNormalizeCaretTildeOrder:
    """验证四步执行顺序的正确性"""

    def test_order_caret_before_restore(self):
        r"""先处理 ^x^ 再还原 \^ — 确保还原后的 ^ 不会被误转为 <上标>"""
        # 模拟：pandoc 输出中有字面 \^ 也有上标 ^2^
        result = normalize_caret_tilde(r"literal \^ and superscript ^2^")
        # step 2: ^2^ → <上标>2</上标>（\^ 处 lookbehind 跳过）
        # step 4: \^ → ^
        assert result == "literal ^ and superscript <上标>2</上标>"

    def test_then_both_superscript_after_restore_not_matched(self):
        """还原后的 ^ 不应再被 step 2 处理（因为 step 2 已经执行完毕）"""
        # 如果顺序错（先还原 \^ 再处理 ^x^），\^ → ^ 后 ^x^ 会被误转
        # 正确顺序：先 ^x^→<上标> 再 \^→^
        result = normalize_caret_tilde(r"\^x^")
        assert result == "^x^"  # 不是 <上标>x</上标>


class TestNormalizeCaretTildeBoundary:
    """边界和不应匹配的情况"""

    def test_inline_math_not_matched(self):
        """$x^2$ — 数学模式内 ^ 后没有关闭的 ^，不匹配"""
        result = normalize_caret_tilde("$x^2 + y^2$")
        assert result == "$x^2 + y^2$"
        assert "<上标>" not in result

    def test_display_math_not_matched(self):
        """$$E=mc^2$$ — 同上"""
        result = normalize_caret_tilde("$$E=mc^2$$")
        assert result == "$$E=mc^2$$"

    def test_single_caret_ignored(self):
        """孤立的 ^ 不形成 ^x^ 模式，不处理"""
        assert normalize_caret_tilde("a^b") == "a^b"

    def test_caret_with_whitespace_ignored(self):
        """^ 后跟空格不形成上标"""
        assert normalize_caret_tilde("a^ b") == "a^ b"

    def test_single_tilde_ignored(self):
        """孤立的 ~"""
        assert normalize_caret_tilde("30~40") == "30~40"

    def test_noop_on_plain_text(self):
        """纯文本原样返回"""
        plain = "这是一段没有任何标记的普通文本。"
        assert normalize_caret_tilde(plain) == plain

    def test_already_converted_markers_unchanged(self):
        """已转换的 <上标> 标记不会被二次处理"""
        already = "v<上标>2</上标>"
        assert normalize_caret_tilde(already) == already


class TestNormalizeCaretTildeRobustness:
    """极端输入、畸形模式、特殊字符"""

    def test_empty_string(self):
        assert normalize_caret_tilde("") == ""

    def test_only_caret_no_content(self):
        """孤立的 ^ 字符"""
        assert normalize_caret_tilde("^") == "^"

    def test_only_tilde_no_content(self):
        """孤立的 ~ 字符"""
        assert normalize_caret_tilde("~") == "~"

    def test_empty_superscript(self):
        """^^ — 空上标，不应匹配（内层需 ≥1 字符）"""
        assert normalize_caret_tilde("a^^b") == "a^^b"

    def test_empty_subscript(self):
        """~~ — 空下标"""
        assert normalize_caret_tilde("a~~b") == "a~~b"

    def test_consecutive_superscripts(self):
        """^a^^b^ — 两个连续上标"""
        result = normalize_caret_tilde("^a^^b^")
        assert result == "<上标>a</上标><上标>b</上标>"

    def test_caret_then_tilde_sequence(self):
        """^2^~0~ 连续出现"""
        result = normalize_caret_tilde("x^2^~0~")
        assert result == "x<上标>2</上标><下标>0</下标>"

    def test_only_escaped_chars(self):
        r"""只有 \^ 和 \~"""
        result = normalize_caret_tilde(r"\^\~")
        # step 1-2: lookbehind 跳过 → 不匹配
        # step 3: \~ → ~
        # step 4: \^ → ^
        assert result == "^~"

    def test_multiple_escaped_mixed(self):
        r"""混合转义和真实上下标"""
        result = normalize_caret_tilde(r"literal \^ and \~ with ^2^ and ~0~")
        assert result == "literal ^ and ~ with <上标>2</上标> and <下标>0</下标>"

    def test_unicode_in_superscript(self):
        """上标含中文"""
        result = normalize_caret_tilde("a^中文^")
        assert result == "a<上标>中文</上标>"

    def test_special_regex_chars_in_superscript(self):
        r"""上标含正则特殊字符 .*+?()[]{}"""
        result = normalize_caret_tilde(r"x^.*+?^")
        # 注意：.*+? 中的正则字符在字符类 [^\^\s] 中都是字面字符
        assert result == r"x<上标>.*+?</上标>"

    def test_superscript_with_parentheses(self):
        """上标含括号"""
        result = normalize_caret_tilde("x^(a)^")
        assert result == "x<上标>(a)</上标>"

    def test_unclosed_superscript(self):
        """^a — 缺少闭合 ^"""
        assert normalize_caret_tilde("x^a y") == "x^a y"

    def test_unclosed_subscript(self):
        """~a — 缺少闭合 ~"""
        assert normalize_caret_tilde("x~a y") == "x~a y"

    def test_tilde_at_line_start(self):
        """行首 ~x~"""
        result = normalize_caret_tilde("~start~ of line")
        assert result == "<下标>start</下标> of line"

    def test_caret_at_line_end(self):
        """行尾 ^x^"""
        result = normalize_caret_tilde("end of line ^x^")
        assert result == "end of line <上标>x</上标>"

    def test_newline_between_delimiters(self):
        r"""^x^ 跨行 — \s 阻止匹配"""
        result = normalize_caret_tilde("a^\nb^")
        # \n 是 \s → [^\^\s] 不匹配 → 不转换
        assert result == "a^\nb^"

    def test_code_span_with_caret(self):
        """`code with ^2^` — 反引号内的 ^x^ 也被转换（无保护）"""
        # 当前实现不保护反引号内的内容，如实记录这一行为
        result = normalize_caret_tilde("`code with ^2^`")
        assert result == "`code with <上标>2</上标>`"

    def test_bold_with_superscript(self):
        """**v^2^** — 粗体包裹上标，标记保持不动"""
        result = normalize_caret_tilde("**v^2^**")
        assert result == "**v<上标>2</上标>**"

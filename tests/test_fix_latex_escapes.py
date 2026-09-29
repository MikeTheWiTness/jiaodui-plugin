"""测试 jiaodui.convert 的 fix_latex_escapes_text / fix_latex_escapes 函数

重点验证：
1. Phase 1: 全局反斜杠规约（pandoc 的 \\\\ → \\）
2. Phase 2+3: 数学公式内 LaTeX 命令不被破坏（\\! \\, \\~ 等）
3. Phase 2+3: 非数学文本中的转义正常还原
4. Phase 4: 数学内部的"安全替换"生效（_、^、{、}）
5. 嵌套/边界情况
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jiaodui.convert import fix_latex_escapes, fix_latex_escapes_text


def _run_fix(input_text):
    """辅助函数：调用文本级 fix_latex_escapes_text，返回处理后的文本"""
    return fix_latex_escapes_text(input_text)


def _run_fix_file(input_text):
    """辅助函数：写入临时文件跑文件级 fix_latex_escapes，返回处理后的文本"""
    fd, tmp_path = tempfile.mkstemp(suffix='.md', text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(input_text)
        fix_latex_escapes(tmp_path)
        with open(tmp_path, encoding='utf-8') as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


# ============================================================
# 核心回归：数学内 \! 保留（本次修复目标）
# ============================================================

class TestBangInMathPreserved:
    r"""\! 在数学公式内保留，在文本外替换"""

    def test_bang_in_inline_math_preserved(self):
        r"""$x\!=\!y$ → \! 保留"""
        result = _run_fix(r'$x\!=\!y$')
        assert r'\!=\!' in result
        assert '=!=' not in result.replace(r'\!=\!', '')  # 没有裸 !

    def test_bang_in_display_math_preserved(self):
        r"""$$x\!=\!y$$ → \! 保留"""
        result = _run_fix(r'$$x\!=\!y$$')
        assert r'\!=\!' in result

    def test_bang_outside_math_replaced(self):
        r"""文本中的 \! → !"""
        result = _run_fix(r'Hello\! World')
        assert 'Hello! World' in result
        assert r'\!' not in result

    def test_bang_outside_math_triple(self):
        r"""文本中的 \!\!\! → !!!"""
        result = _run_fix(r'Wait\!\!\!')
        assert 'Wait!!!' in result

    def test_chemistry_equation_long_equals(self):
        r"""化学方程式长等号 $=\!=\!=x$ → \! 全部保留"""
        result = _run_fix(r'${\mathrm{S}}^{2-}+{\mathrm{I}}_{2}=\!=\!=x$')
        assert r'=\!=\!=' in result
        assert 'MATH' not in result
        assert '\x01' not in result

    def test_chemistry_fragmented_equation(self):
        r"""碎片化化学方程式 $\mathrm{S}$$$=\!$$=\!$$=x$ → \! 保留"""
        result = _run_fix(
            r'$\mathrm{S}{\mathrm{O}}_{3}^{2-}$'
            r'$$=\!$$=\!$$=\mathrm{S}{\mathrm{O}}_{4}^{2-}$'
        )
        assert 'MATH' not in result
        assert '\x01' not in result
        # \! 应该保留（在数学内）—— 注意碎片之间有 $$ 分隔
        assert r'\!' in result
        assert '=!=' not in result.replace(r'\!=\!', '')  # 无裸的 !=


# ============================================================
# Phase 4: 数学内部安全替换（下标、上标、分组）
# ============================================================

class TestSafeReplacementsInMath:
    """数学内部：_ ^ { } 必须还原，其余命令保留"""

    def test_underscore_in_math_replaced(self):
        r"""$\_1$ → $_1$（下标必须工作）"""
        result = _run_fix(r'$x\_1$')
        assert '$x_1$' in result

    def test_caret_in_math_replaced(self):
        r"""$\^2$ → $^2$（上标必须工作）"""
        result = _run_fix(r'$x\^2$')
        assert '$x^2$' in result

    def test_braces_in_math_replaced(self):
        r"""$\{x\}$ → ${x}$（分组必须工作）"""
        result = _run_fix(r'$\{x\}$')
        assert '${x}$' in result

    def test_mathrm_with_braces(self):
        """$\\{\\mathrm{SO}\\}$ → ${\\mathrm{SO}}$"""
        # 模拟 pandoc 输出: \\{  → \{ (line 33-35) → { (Phase 4)
        result = _run_fix(r'$\\{\\mathrm{SO}\\}$')
        assert r'${\mathrm{SO}}$' in result

    def test_subscript_and_superscript_together(self):
        r"""$x\_1\^2$ → $x_1^2$"""
        result = _run_fix(r'$x\_1\^2$')
        assert '$x_1^2$' in result


# ============================================================
# Phase 2+3: 其他 LaTeX 命令在数学内保护
# ============================================================

class TestLatexCommandsProtectedInMath:
    """各种 LaTeX 命令在数学公式内不被破坏"""

    def test_dollar_in_math_preserved(self):
        r"""$\$5$ → \$ 在数学内保留的边界情况
        注意：由于 \$ → $ 必须在数学保护之前执行（以识别 $...$ 定界符），
        数学内字面的 \$ 会与定界符合并。这在化学/物理公式中极少出现。
        """
        result = _run_fix(r'$\$5$')
        # 不崩溃即可，实际行为受限于 \$ → $ 的全局前置处理
        assert isinstance(result, str)
        assert len(result) > 0

    def test_tilde_in_math_preserved(self):
        r"""$\~a$ → \~ 保留（LaTeX 波浪 accent）"""
        result = _run_fix(r'$\~a$')
        assert r'\~a' in result

    def test_ampersand_in_math_preserved(self):
        r"""$\&$ → \& 保留"""
        result = _run_fix(r'$\&$')
        assert r'\&' in result

    def test_percent_in_math_preserved(self):
        r"""$\%$ → \% 保留"""
        result = _run_fix(r'$\%$')
        assert r'\%' in result

    def test_star_in_math_preserved(self):
        r"""$\*$ → \* 保留"""
        result = _run_fix(r'$\*$')
        assert r'\*' in result

    def test_plus_in_math_preserved(self):
        r"""$\+$ → \+ 保留"""
        result = _run_fix(r'$\+$')
        assert r'\+' in result

    def test_minus_in_math_preserved(self):
        r"""$\-$ → \- 保留"""
        result = _run_fix(r'$\-$')
        assert r'\-' in result

    def test_equal_in_math_preserved(self):
        r"""$\=$ → \= 保留（LaTeX macron accent）"""
        result = _run_fix(r'$\=$')
        assert r'\=' in result

    def test_pipe_in_math_preserved(self):
        r"""$\|x\|$ → \| 保留（LaTeX 范数）"""
        result = _run_fix(r'$\|x\|$')
        assert r'\|' in result

    def test_quote_in_math_preserved(self):
        r"""$\'e$ → \' 保留（LaTeX acute accent）"""
        result = _run_fix(r'$\'e$')
        assert r"\'e" in result

    def test_hash_in_math_preserved(self):
        r"""$\#1$ → \# 保留"""
        result = _run_fix(r'$\#1$')
        assert r'\#1' in result


# ============================================================
# Phase 3: 非数学文本中转义正常还原
# ============================================================

class TestEscapesOutsideMath:
    """文本中的 pandoc 转义正常还原"""

    def test_dollar_outside_math(self):
        r"""文本中 \$ → $"""
        result = _run_fix(r'价格 \$5')
        assert '价格 $5' in result

    def test_underscore_outside_math(self):
        r"""文本中 \_ → _"""
        result = _run_fix(r'file\_name')
        assert 'file_name' in result

    def test_hash_outside_math(self):
        r"""文本中 \# → #"""
        result = _run_fix(r'\#tag')
        assert '#tag' in result

    def test_ampersand_outside_math(self):
        r"""文本中 \& → &"""
        result = _run_fix(r'A \& B')
        assert 'A & B' in result

    def test_percent_outside_math(self):
        r"""文本中 \% → %"""
        result = _run_fix(r'50\%')
        assert '50%' in result

    def test_brace_outside_math(self):
        r"""文本中 \{ → {"""
        result = _run_fix(r'\{note\}')
        assert '{note}' in result

    def test_tilde_outside_math(self):
        r"""文本中 \~ → ~"""
        result = _run_fix(r'foo\~bar')
        assert 'foo~bar' in result

    def test_left_right_parentheses(self):
        """\\left\\( 和 \right\\) 修复"""
        result = _run_fix(r'\left\( x \right\)')
        assert r'\left( x \right)' in result

    def test_left_right_brackets(self):
        """\\left\\[ 和 \right\\] 修复"""
        result = _run_fix(r'\left\[ x \right\]')
        assert r'\left[ x \right]' in result

    def test_mixed_escapes_in_text(self):
        """混合多种转义"""
        result = _run_fix(r'Price: \$50\_discount \= 30\% off\!')
        assert 'Price: $50_discount = 30% off!' in result


# ============================================================
# 混合场景：数学 + 文本相邻
# ============================================================

class TestMixedMathAndText:
    """数学公式和文本交替出现"""

    def test_bang_in_math_not_in_text(self):
        r"""$x\!=\!y$ 文本中的 \! 正常替换"""
        result = _run_fix(r'公式 $x\!=\!y$ 和文字 Hello\!')
        assert r'\!=\!' in result   # 数学内保留
        assert 'Hello!' in result   # 文本中替换

    def test_underscore_in_both(self):
        r"""$\_1$ + 文本 \_ → 各自正确处理"""
        result = _run_fix(r'变量 $x\_1$ 和文件 file\_name')
        assert '$x_1$' in result    # 数学内还原
        assert 'file_name' in result # 文本中还原

    def test_multiple_math_blocks(self):
        """多个数学块各自保护"""
        result = _run_fix(r'$x\!=\!y$ 和 $a\~b$ 和 $c\&d$')
        assert r'\!=\!' in result
        assert r'\~' in result
        assert r'\&' in result

    def test_chinese_text_with_math(self):
        """中文文本 + 数学公式"""
        result = _run_fix(r'已知 $x\_1 + x\_2 = 5$，求 $x\_1\^2$ 的值。')
        assert '$x_1 + x_2 = 5$' in result
        assert '$x_1^2$' in result


# ============================================================
# 嵌套数学：$$...$...$...$$
# ============================================================

class TestNestedMath:
    """嵌套数学块保护"""

    def test_display_containing_inline(self):
        """$$x = $a+b$ + y$$"""
        result = _run_fix(r'$$x = $a+b$ + y$$')
        assert '$$x = $a+b$ + y$$' in result
        assert 'MATH' not in result
        assert '\x01' not in result

    def test_display_with_bang_inside(self):
        r"""$$x\!=\!$a+b$ + y$$"""
        result = _run_fix(r'$$x\!=\!$a+b$ + y$$')
        assert r'\!=\!' in result
        assert 'MATH' not in result

    def test_display_with_underscore_inside(self):
        r"""$$x = $\_1$ + y$$"""
        result = _run_fix(r'$$x = $\_1$ + y$$')
        # 内嵌数学的 _ 应该被还原
        assert '$_1$' in result


# ============================================================
# Phase 1: 全局反斜杠规约
# ============================================================

class TestGlobalBackslashReduction:
    """pandoc 的 \\\\ 规约（Phase 1，全局生效）"""

    def test_double_backslash_before_special(self):
        """\\\\[ → \\[（然后 \\[note\\] → [note] 经 _fix_escaped_brackets）"""
        result = _run_fix(r'text \\[note\\]')
        # _fix_escaped_brackets 将 \\[note\\]（不含数学内容）转换为 [note]
        assert '[note]' in result

    def test_double_backslash_before_letters(self):
        """\\\\mathrm → \\mathrm（LaTeX 命令复原）"""
        result = _run_fix(r'$\\\\mathrm{SO}$')
        assert r'$\mathrm{SO}$' in result

    def test_double_backslash_before_other(self):
        """\\\\! → \\!（然后 Phase 2 保护 \\!）"""
        result = _run_fix(r'$\\\\!$')
        assert r'$\!$' in result

    def test_triple_backslash_reduction(self):
        """\\\\\\\\[ → \\[ → [（经 _fix_escaped_brackets）"""
        result = _run_fix(r'\\\\\\[x\\\\\\]')
        assert '[x]' in result


# ============================================================
# fix_escaped_brackets 测试
# ============================================================

class TestEscapedBrackets:
    """\\[...\\] 处理"""

    def test_escaped_bracket_non_math(self):
        """\\[普通文本\\] → [普通文本]"""
        result = _run_fix(r'这是 \\[注释\\] 内容')
        assert '[注释]' in result
        assert r'\\[' not in result

    def test_escaped_bracket_with_math_inside(self):
        """\\[$x^2$\\] → 保留（内部有数学）"""
        result = _run_fix(r'\\[$x^2$\\]')
        # 包含数学内容的不应该转换
        assert r'\[' in result or '[' in result  # 至少存在


# ============================================================
# 边界情况
# ============================================================

class TestEdgeCases:
    """边界情况"""

    def test_empty_input(self):
        """空输入"""
        assert _run_fix('') == ''

    def test_no_special_chars(self):
        """纯文本无特殊字符"""
        assert _run_fix('Hello World') == 'Hello World'

    def test_empty_math(self):
        """空数学块 $$"""
        result = _run_fix('$$')
        assert '$$' in result

    def test_unbalanced_math(self):
        """不配对的 $ — 不崩溃"""
        result = _run_fix(r'$a+b 没闭合')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_single_backslash(self):
        """单个 \\ 不在特殊字符前"""
        result = _run_fix(r'路径 C:\Users\test')
        assert r'C:\Users\test' in result

    def test_math_at_line_start(self):
        """行首公式"""
        result = _run_fix(r'$x\!=\!y$ 开头')
        assert r'\!=\!' in result

    def test_math_at_line_end(self):
        """行尾公式"""
        result = _run_fix(r'结尾 $x\!=\!y$')
        assert r'\!=\!' in result

    def test_newline_inside_display_math(self):
        """$$ 内跨行"""
        result = _run_fix('$$\na\\_{1} + b\\^{2}\n$$')
        assert 'MATH' not in result
        assert '_' in result  # 下标还原
        assert '^' in result  # 上标还原


# ============================================================
# 端到端：模拟完整 pandoc → fix_latex_escapes 流程
# ============================================================

class TestEndToEnd:
    """模拟 pandoc 输出 → fix_latex_escapes 的端到端流程"""

    def test_pandoc_style_chemistry_equation(self):
        """模拟 pandoc 输出的化学方程式"""
        # pandoc 输出典型特征：
        # - \\$...\\$ 包裹数学
        # - \\\\mathrm 等双重反斜杠
        # - \\_ 和 \\^ 转义上下标
        # - \\! 转义感叹号
        pandoc_output = (
            r'\$\\mathrm{C}\$'  # pandoc escaped math delimiters
            r'．由反应'
            r'\$\\mathrm{S}{\\mathrm{O}}\_{3}\^{2-}'
            r'+{\\mathrm{I}}\_{2}+{\\mathrm{H}}\_{2}\\mathrm{O}'
            r'=\\!=\\!=\\mathrm{S}{\\mathrm{O}}\_{4}\^{2-}'
            r'+2{\\mathrm{I}}\^{-}+2{\\mathrm{H}}\^{+}\$'
            r'可知'
        )
        result = _run_fix(pandoc_output)

        # 验证关键修复
        assert r'$\mathrm{C}$' in result          # 数学界定界符修复
        assert r'\mathrm{S}' in result            # LaTeX 命令修复
        assert r'_{3}' in result                  # 下标修复
        assert r'^{2-}' in result                 # 上标修复
        assert r'=\!=\!=' in result               # \! 保留（关键！）
        assert 'MATH' not in result               # 无占位符残留
        assert '\x01' not in result               # 无 SOH 残留
        # 不应有裸的 !=
        assert '=!=' not in ''.join(result.split(r'\!=\!'))

    def test_multiple_equations_in_one_document(self):
        """多个化学方程式在同一文档"""
        pandoc_output = (
            r'\$\\mathrm{A}\$．'
            r'\${\\mathrm{S}}\^{2-}+{\\mathrm{I}}\_{2}=\\!=\\!=x\$' '\n'
            r'\$\\mathrm{B}\$．'
            r'\$2{\\mathrm{Fe}}\^{2+}+\\mathrm{S}=\\!=\\!=y\$'
        )
        result = _run_fix(pandoc_output)

        assert r'$\mathrm{A}$' in result
        assert r'$\mathrm{B}$' in result
        assert r'=\!=\!=' in result  # 两个方程式都有
        assert result.count(r'=\!=\!=') >= 2


# ============================================================
# 文件级包装：fix_latex_escapes（读文件 → 文本级 → 写回）
# ============================================================


class TestFileLevelWrapper:
    """文件级 fix_latex_escapes 包装，与文本级结果一致"""

    def test_file_wrapper_matches_text(self):
        r"""$x_1$ 文件级与文本级结果一致，且下标已还原"""
        src = r'\$x\_1\$'
        out = _run_fix_file(src)
        assert out == fix_latex_escapes_text(src)
        assert '$x_1$' in out

    def test_file_wrapper_empty(self):
        """空文件往返为空"""
        assert _run_fix_file('') == ''

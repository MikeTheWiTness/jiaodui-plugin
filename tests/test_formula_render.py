"""jiaodui/formula_render.py 单元测试。

锁定 latex_to_png 的渲染成功/降级边界（CJK 拒绝、异常降级、空串），
以及 matplotlib 缺失时的优雅降级（返回 False 且不残留文件）。
"""
import importlib.util

import pytest

from jiaodui.formula_render import _CJK_FONT, latex_to_png

HAS_MPL = importlib.util.find_spec("matplotlib") is not None


@pytest.mark.skipif(HAS_MPL, reason="matplotlib 可用时该退化用例不适用")
def test_missing_matplotlib_returns_false_without_file(tmp_path):
    out = tmp_path / "f.png"
    assert latex_to_png(r"v = at", out) is False
    assert not out.exists()


@pytest.mark.skipif(HAS_MPL, reason="matplotlib 可用时该退化用例不适用")
def test_missing_matplotlib_failed_render_leaves_no_file(tmp_path):
    out = tmp_path / "f.png"
    out.write_bytes(b"stale")
    assert latex_to_png(r"v = at", out) is False
    assert not out.exists()


@pytest.mark.skipif(not HAS_MPL, reason="matplotlib 不可用")
class TestLatexToPng:
    def test_simple_formula_renders(self, tmp_path):
        out = tmp_path / "f.png"
        assert latex_to_png(r"v = at", out) is True
        assert out.exists()
        assert out.read_bytes()[:8].startswith(b"\x89PNG")

    def test_frac_and_greek_renders(self, tmp_path):
        out = tmp_path / "f.png"
        assert latex_to_png(r"E = n\frac{\Delta\Phi}{\Delta t}", out) is True

    def test_mathrm_with_space_renders(self, tmp_path):
        out = tmp_path / "f.png"
        assert latex_to_png(r"\mathrm {B}", out) is True

    def test_chinese_renders_with_cjk_font_or_rejects(self, tmp_path):
        """有系统 CJK 字体时中文公式渲染成功；无字体时拒绝。"""
        out = tmp_path / "f.png"
        ok = latex_to_png(r"Q_{电热}", out)
        if _CJK_FONT:
            assert ok is True
            assert out.exists()
        else:
            assert ok is False
            assert not out.exists()

    def test_chinese_text_cmd_renders_with_cjk_font_or_rejects(self, tmp_path):
        out = tmp_path / "f.png"
        ok = latex_to_png(r"\text{线圈}A", out)
        if _CJK_FONT:
            assert ok is True
        else:
            assert ok is False
            assert not out.exists()

    def test_matrix_rejected(self, tmp_path):
        out = tmp_path / "f.png"
        assert latex_to_png(r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}", out) is False
        assert not out.exists()

    def test_empty_rejected(self, tmp_path):
        out = tmp_path / "f.png"
        assert latex_to_png("", out) is False
        assert latex_to_png("   ", out) is False

    def test_failed_render_leaves_no_file(self, tmp_path):
        # 渲染失败后不应残留上次成功的文件
        out = tmp_path / "f.png"
        assert latex_to_png(r"v=at", out) is True
        assert latex_to_png(r"\begin{cases} a & b \end{cases}", out) is False
        assert not out.exists()

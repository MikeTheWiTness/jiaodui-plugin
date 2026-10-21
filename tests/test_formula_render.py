"""jiaodui/formula_render.py 单元测试。

锁定 latex_to_png 的渲染成功/降级边界（CJK 拒绝、异常降级、空串），
以及 matplotlib 缺失时的优雅降级（返回 False 且不残留文件）。
"""
import pytest

from jiaodui.formula_render import _CJK_FONT, latex_to_png, matplotlib_available, normalize_latex

# 用真实 import 判定可用性，而非 find_spec：pip 装的 matplotlib 在本机可能被
# macOS 代码签名拒绝（dlopen 报 Team ID 不一致），find_spec 会误判为可用。
HAS_MPL = matplotlib_available()


def test_missing_matplotlib_returns_false_without_file(tmp_path, monkeypatch):
    monkeypatch.setattr("jiaodui.formula_render._ensure_matplotlib", lambda: False)
    out = tmp_path / "f.png"
    assert latex_to_png(r"v = at", out) is False
    assert not out.exists()


def test_missing_matplotlib_failed_render_leaves_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("jiaodui.formula_render._ensure_matplotlib", lambda: False)
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

    @pytest.mark.parametrize("body", [
        r"U_{CB}q_{1} \gt U_{DC}q_{3}",
        r"qE\lt \frac{mv^{2}}{r}",
        r"U_{BC}q_{1} \gt \|U_{CD}q_{3}\|",
        r"a \ge b",
        r"a \le b",
        r"\mathrm{\,}",
        r"\text{abc}",
        r"\mbox{abc}",
        r"\hspace{1em}a",
        r"\left\| x \right\|",
    ])
    def test_pandoc_commands_are_normalized_before_rendering(self, tmp_path, body):
        r"""pandoc 转写的命令（\gt / \lt / \| / \ge / \le 等）必须能渲染。

        这些不是缺失可选依赖，而是 mathtext 语法差异；归一化后仍失败才允许降级。
        """
        out = tmp_path / "f.png"
        assert latex_to_png(body, out) is True
        assert out.exists()


def test_normalize_latex_maps_pandoc_commands():
    assert normalize_latex(r"a \gt b") == "a > b"
    assert normalize_latex(r"a \lt b") == "a < b"
    assert normalize_latex(r"a \ge b") == r"a \geq b"
    assert normalize_latex(r"a \le b") == r"a \leq b"
    assert normalize_latex(r"\|x\|") == r"{\Vert}x{\Vert}"
    assert normalize_latex(r"\left\|x\right\|") == r"\left\Vertx\right\Vert"
    assert normalize_latex(r"\text{中文}") == r"\mathrm{中文}"
    assert normalize_latex(r"\mathrm{\,}") == r"\mathrm{}"


def test_diagnostics_distinguish_dependency_from_syntax(tmp_path, monkeypatch):
    dependency: dict = {}
    monkeypatch.setattr("jiaodui.formula_render._ensure_matplotlib", lambda: False)
    assert latex_to_png(r"v=at", tmp_path / "f.png", diagnostics=dependency) is False
    assert dependency["reason"] == "dependency_missing"

    monkeypatch.undo()
    if not HAS_MPL:
        pytest.skip("matplotlib 不可用")
    syntax: dict = {}
    assert latex_to_png(r"\begin{pmatrix} a & b \end{pmatrix}",
                        tmp_path / "g.png", diagnostics=syntax) is False
    assert syntax["reason"] == "syntax_unsupported"
    assert "Unknown symbol" in syntax["detail"] or "ParseFatal" in syntax["detail"]


def test_empty_formula_reports_empty_reason(tmp_path):
    diagnostics: dict = {}
    assert latex_to_png("", tmp_path / "f.png", diagnostics=diagnostics) is False
    assert diagnostics["reason"] == "empty"

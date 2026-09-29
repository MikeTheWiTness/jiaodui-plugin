r"""LaTeX 公式 → PNG 渲染（matplotlib mathtext，Word 批注插图用）。

字体策略（动态切换）：
- 无中文字符的公式 → 纯 STIX fontset：变量斜体衬线（Times 风格）
- 含中文字符的公式 → custom fontset：
  - 裸中文字符预处理包进 \mathrm{...} → rm 字体（系统 CJK 宋体）渲染
  - 拉丁变量走 it 字体（STIXGeneral 斜体）——中文公式里变量保持斜体
  - STIX fallback 兜底数学符号
- 无系统 CJK 字体且公式含中文 → 拒绝渲染（调用方降级为纯文本）
- 矩阵/多行公式等 mathtext 不支持的结构抛异常，同样拒绝

matplotlib 是可选依赖：模块导入不触发 matplotlib，latex_to_png 首次调用时才
惰性加载（模块级 __getattr__ 让 _CJK_FONT 等属性被 import 时也能惰性解析）；
缺失时 latex_to_png 返回 False 并确保不残留输出文件，调用方降级为纯文本。
"""
from __future__ import annotations

import os
import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")

# 中文字体候选：衬线（宋体）优先，黑体兜底
_CJK_CANDIDATES = [
    "STSong", "Songti SC", "SimSun", "NSimSun",
    "Noto Serif CJK SC", "Source Han Serif SC",
    "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC",
    "Source Han Sans SC", "WenQuanYi Zen Hei",
]

# 纯 STIX 配置（普通公式：斜体衬线）
_STIX_RC = {
    "mathtext.fontset": "stix",
    "font.family": "STIXGeneral",
}

# 含中文公式配置：rm=系统 CJK 字体（\mathrm/文本），it=STIX 斜体（变量）
# 注意：mathtext custom 走 UnicodeFonts，findfont 不带 style，必须用
# "字体名:italic" 语法显式指定斜体变体，否则变量渲染为正体
_CJK_RC = {
    "mathtext.fontset": "custom",
    "mathtext.rm": None,
    "mathtext.it": "STIXGeneral:italic",
    "mathtext.bf": "STIXGeneral:weight=bold",
    "mathtext.cal": "STIXGeneral",
    "mathtext.tt": "STIXGeneral",
    "mathtext.fallback": "stix",
    "font.family": ["STIXGeneral", None],
}

# 惰性加载状态：导入本模块不会 import matplotlib
plt = None
font_manager = None
_MATPLOTLIB_AVAILABLE = False
_MPL_CHECKED = False


def _find_cjk_font() -> str | None:
    """在系统已装字体里挑选可用的中文字体；无则返回 None。"""
    if font_manager is None:
        return None
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in _CJK_CANDIDATES:
        if cand in names:
            return cand
    return None


def _ensure_matplotlib() -> bool:
    """首次调用时惰性 import matplotlib 并解析 CJK 字体；缺失返回 False。"""
    global _MPL_CHECKED, _MATPLOTLIB_AVAILABLE, plt, font_manager, _CJK_FONT
    if _MPL_CHECKED:
        return _MATPLOTLIB_AVAILABLE
    _MPL_CHECKED = True
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as _plt
        from matplotlib import font_manager as _fm
    except Exception:
        plt = None
        font_manager = None
        _MATPLOTLIB_AVAILABLE = False
        _CJK_FONT = None
        return False
    plt = _plt
    font_manager = _fm
    _MATPLOTLIB_AVAILABLE = True
    _CJK_FONT = _find_cjk_font()
    if _CJK_FONT:
        _CJK_RC["mathtext.rm"] = _CJK_FONT
        _CJK_RC["font.family"] = ["STIXGeneral", _CJK_FONT]
    return True


def matplotlib_available() -> bool:
    """matplotlib 是否真正可加载（而非仅装了个包）。

    调用 :func:`_ensure_matplotlib` 做一次真实 import：pip 装的 C 扩展若被
    macOS 代码签名拒绝（Team ID 不一致）会在此返回 False，供 check-env 与测试
    统一定位「已安装但无法加载」的退化，而不是用 find_spec 误判为可用。
    """
    return _ensure_matplotlib()


def __getattr__(name: str):
    """惰性属性：from .formula_render import _CJK_FONT 时才触发 matplotlib 解析。"""
    if name == "_CJK_FONT":
        _ensure_matplotlib()
        return globals().get("_CJK_FONT")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _remove_quietly(path) -> None:
    """删除可能残留的输出文件，忽略删除失败。"""
    try:
        os.remove(path)
    except OSError:
        pass


def _wrap_bare_cjk(latex_body: str) -> str:
    r"""把公式中裸中文字符包进 \mathrm{...}（rm 字体渲染）。

    已在 \text{...} / \mathrm{...} 内的中文保持不动，避免嵌套。
    """
    placeholders = {}

    def _protect(m):
        key = f"\x00{len(placeholders)}\x00"
        placeholders[key] = m.group(0)
        return key

    body = re.sub(r"\\text\{[^}]*\}|\\mathrm\{[^}]*\}", _protect, latex_body)
    body = _CJK_RUN_RE.sub(lambda m: r"\mathrm{" + m.group(0) + "}", body)
    for key, value in placeholders.items():
        body = body.replace(key, value)
    return body


def latex_to_png(latex_body: str, out_path, fontsize: float = 14, dpi: int = 200) -> bool:
    """渲染 LaTeX 公式体（不含 $ 包裹）为透明 PNG，成功返回 True。

    无系统 CJK 字体且公式含中文字符时返回 False；matplotlib 不可用或渲染抛异常时
    返回 False 并清理可能残留的输出文件（调用方降级为文本）。
    """
    if not latex_body:
        return False
    if not _ensure_matplotlib():
        _remove_quietly(out_path)
        return False
    has_cjk = bool(_CJK_RE.search(latex_body))
    if _CJK_FONT is None and has_cjk:
        return False
    if has_cjk:
        latex_body = _wrap_bare_cjk(latex_body)
    rc = _CJK_RC if has_cjk else _STIX_RC
    try:
        with plt.rc_context(rc):
            fig = plt.figure(figsize=(0.1, 0.1))
            fig.text(0, 0, "$" + latex_body + "$", fontsize=fontsize)
            fig.savefig(out_path, dpi=dpi, transparent=True,
                        bbox_inches="tight", pad_inches=0.02)
            plt.close(fig)
        return True
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        _remove_quietly(out_path)
        return False

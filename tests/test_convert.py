"""测试 jiaodui.convert 的公开转换 API（pandoc 定位 + docx/md/idml 分支）。

锁定：
- find_pandoc / check_pandoc / pandoc_to_docx / convert_with_pandoc 的定位与命令构造
- docx 转换顺序：先 normalize_caret_tilde 后 enhance（旧仓 test_convert_default 契约）
- md 分支：规范命名、图片搬到 {base}_images/media、丢失图片保留并报告
- 已有目标：覆盖规范名，不生成 attempt 副本，warnings 说明
- 未识别扩展名：抛 UnsupportedError；源文件缺失：抛 NotFoundError
"""
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jiaodui import convert
from jiaodui.convert import (
    ConvertResult,
    check_pandoc,
    convert_display_to_inline,
    convert_to_raw,
    find_pandoc,
    normalize_caret_tilde,
    pandoc_to_docx,
)
from jiaodui.errors import EnvError, NotFoundError, UnsupportedError


# ============================================================
# pandoc 定位与命令构造
# ============================================================


def test_find_pandoc_uses_env_path_override(monkeypatch):
    monkeypatch.setenv("JIAODUI_PANDOC", "/opt/pandoc/bin/pandoc")
    monkeypatch.setattr(convert.os.path, "isfile", lambda p: p == "/opt/pandoc/bin/pandoc")
    monkeypatch.setattr(convert.shutil, "which", lambda name: None)
    assert find_pandoc() == "/opt/pandoc/bin/pandoc"


def test_find_pandoc_env_command_resolved_by_which(monkeypatch):
    monkeypatch.setenv("JIAODUI_PANDOC", "pandoc-custom")
    monkeypatch.setattr(
        convert.shutil, "which",
        lambda name: "/usr/local/bin/pandoc" if name == "pandoc-custom" else None,
    )
    assert find_pandoc() == "/usr/local/bin/pandoc"


def test_find_pandoc_env_missing_returns_none(monkeypatch):
    monkeypatch.setenv("JIAODUI_PANDOC", "/nope/pandoc")
    monkeypatch.setattr(convert.os.path, "isfile", lambda p: False)
    monkeypatch.setattr(convert.shutil, "which", lambda name: None)
    assert find_pandoc() is None


def test_find_pandoc_falls_back_to_which(monkeypatch):
    monkeypatch.delenv("JIAODUI_PANDOC", raising=False)
    monkeypatch.setattr(
        convert.shutil, "which",
        lambda name: "/usr/bin/pandoc" if name == "pandoc" else None,
    )
    assert find_pandoc() == "/usr/bin/pandoc"


def test_check_pandoc_false_without_binary(monkeypatch):
    monkeypatch.setattr(convert, "find_pandoc", lambda: None)
    assert check_pandoc() is False


def test_check_pandoc_true(monkeypatch):
    monkeypatch.setattr(convert, "find_pandoc", lambda: "/fake/pandoc")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="pandoc 3.1\n", stderr="")

    monkeypatch.setattr(convert.subprocess, "run", fake_run)
    assert check_pandoc() is True
    assert calls == [["/fake/pandoc", "--version"]]


def test_pandoc_to_docx_command(monkeypatch, tmp_path):
    monkeypatch.setattr(convert, "find_pandoc", lambda: "/fake/pandoc")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(convert.subprocess, "run", fake_run)
    assert pandoc_to_docx("in.md", "out.docx") is True
    assert seen["cmd"] == [
        "/fake/pandoc", "-f", "markdown", "-t", "docx", "in.md", "-o", str(tmp_path / "out.docx"),
    ]


def test_pandoc_to_docx_failure(monkeypatch):
    monkeypatch.setattr(convert, "find_pandoc", lambda: "/fake/pandoc")
    monkeypatch.setattr(
        convert.subprocess, "run",
        lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="boom"),
    )
    assert pandoc_to_docx("in.md", "out.docx") is False


def test_pandoc_to_docx_without_pandoc(monkeypatch):
    monkeypatch.setattr(convert, "find_pandoc", lambda: None)
    assert pandoc_to_docx("in.md", "out.docx") is False


def test_convert_with_pandoc_command_and_mathjax(monkeypatch, tmp_path):
    monkeypatch.setattr(convert, "find_pandoc", lambda: "/fake/pandoc")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(convert.subprocess, "run", fake_run)

    assert convert.convert_with_pandoc("a.docx", "o.md", "imgs", use_mathjax=False) is True
    assert seen["cmd"] == [
        "/fake/pandoc", "-f", "docx", "-t", "markdown-smart",
        "--extract-media", str(tmp_path / "imgs"), "--wrap", "none",
        "--markdown-headings", "atx", "a.docx", "-o", str(tmp_path / "o.md"),
    ]

    convert.convert_with_pandoc("a.docx", "o.md", "imgs", use_mathjax=True)
    assert seen["cmd"][3] == "--mathjax"


# ============================================================
# ConvertResult 与纯函数契约
# ============================================================


def test_convert_result_fields():
    r = ConvertResult(raw_md="x", images_dir="y", copied=1, missing=2, source_kind="md")
    assert r.warnings == []
    assert (r.raw_md, r.images_dir, r.copied, r.missing, r.source_kind) == ("x", "y", 1, 2, "md")


def test_normalize_caret_tilde_contract():
    assert normalize_caret_tilde("x^2^") == "x<上标>2</上标>"
    assert normalize_caret_tilde("H~2~O") == "H<下标>2</下标>O"
    assert normalize_caret_tilde(r"\^2^") == "^2^"


def test_convert_display_to_inline_contract():
    assert convert_display_to_inline("$$a+b$$") == "$a+b$"
    assert convert_display_to_inline("$$\na\n$$") == "$$\na\n$$"


def test_fix_floating_images(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("A. ![test](m/1.png) 选项文字", encoding="utf-8")
    assert convert.fix_floating_images(str(f)) is True
    assert f.read_text(encoding="utf-8").startswith("![](m/1.png)\nA.")


def test_normalize_option_spacing(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("A.    选项", encoding="utf-8")
    assert convert.normalize_option_spacing(str(f)) is True
    assert f.read_text(encoding="utf-8") == "A.  选项"


def test_fix_floating_images_text_moves_image_before_option():
    text = "A. ![test](m/1.png){width=\"1in\"} 选项文字"
    fixed = convert.fix_floating_images_text(text)
    assert fixed.startswith("![](m/1.png){width=\"1in\"}\nA.")
    assert "选项文字" in fixed


def test_fix_floating_images_text_keeps_image_when_other_options_have_images():
    """B-D 也是图片选项时不挪动（避免破坏并排选项）。"""
    text = "A. ![test](m/1.png) 甲\nB. ![test](m/2.png) 乙"
    assert convert.fix_floating_images_text(text) == text


def test_fix_floating_images_text_noop_returns_original():
    text = "![](m/1.png)\nA. 甲"
    assert convert.fix_floating_images_text(text) == text


def test_normalize_option_spacing_text_contract():
    assert convert.normalize_option_spacing_text("A.    选项") == "A.  选项"
    assert convert.normalize_option_spacing_text("A.  选项") == "A.  选项"


# ============================================================
# docx 分支
# ============================================================


def test_docx_conversion_normalizes_before_enhance(tmp_path, monkeypatch):
    src = tmp_path / "讲义.docx"
    src.write_bytes(b"fake docx")
    out_dir = tmp_path / "out"

    monkeypatch.setattr(convert, "check_pandoc", lambda: True)

    def fake_convert(input_path, out_md, img_dir, use_mathjax=False):
        Path(out_md).write_text("v^2^ + H~2~O", encoding="utf-8")
        return True

    enhance_seen = []

    def fake_enhance(docx_path, md_path):
        enhance_seen.append(Path(md_path).read_text(encoding="utf-8"))
        return True

    monkeypatch.setattr(convert, "convert_with_pandoc", fake_convert)
    monkeypatch.setattr(convert, "enhance_docx_conversion", fake_enhance)

    result = convert_to_raw(str(src), str(out_dir), "讲义")

    assert result.source_kind == "docx"
    assert result.raw_md == str(out_dir / "讲义_raw.md")
    assert result.images_dir == str(out_dir / "讲义_images")
    assert enhance_seen == ["v<上标>2</上标> + H<下标>2</下标>O"], "默认转换应只增强一次且已归一上下标"
    text = Path(result.raw_md).read_text(encoding="utf-8")
    assert "v<上标>2</上标> + H<下标>2</下标>O" in text


def test_docx_without_pandoc_raises_env_error(tmp_path, monkeypatch):
    src = tmp_path / "a.docx"
    src.write_bytes(b"x")
    monkeypatch.setattr(convert, "check_pandoc", lambda: False)
    with pytest.raises(EnvError):
        convert_to_raw(str(src), str(tmp_path / "out"), "a")


# ============================================================
# md 分支
# ============================================================


def test_md_branch_copies_to_canonical_and_moves_images(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "pic.png").write_bytes(b"\x89PNG")
    src = src_dir / "讲义.md"
    src.write_text("正文\n\n![图](pic.png)\n", encoding="utf-8")
    out_dir = tmp_path / "out"

    result = convert_to_raw(str(src), str(out_dir), "讲义")

    assert result.source_kind == "md"
    assert result.copied == 1
    assert result.missing == 0
    raw = Path(result.raw_md)
    assert raw.name == "讲义_raw.md"
    assert (out_dir / "讲义_images" / "media" / "pic.png").read_bytes() == b"\x89PNG"
    assert "![图](./讲义_images/media/pic.png)" in raw.read_text(encoding="utf-8")


def test_md_branch_missing_image_kept_and_reported(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("![图](missing.png)", encoding="utf-8")

    result = convert_to_raw(str(src), str(tmp_path / "out"), "a")

    assert result.missing == 1
    assert result.warnings
    assert "![图](missing.png)" in Path(result.raw_md).read_text(encoding="utf-8")


def test_existing_target_overwritten_in_place_without_attempt_copy(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("新内容", encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    target = out_dir / "a_raw.md"
    target.write_text("旧内容", encoding="utf-8")

    result = convert_to_raw(str(src), str(out_dir), "a")

    assert result.warnings and "覆盖" in result.warnings[0]
    assert target.read_text(encoding="utf-8") == "新内容"
    # 不得出现 attempt / 副本文件，只保留规范名
    assert sorted(p.name for p in out_dir.glob("*.md")) == ["a_raw.md"]


def test_md_branch_preserves_original_formatting(tmp_path):
    src = tmp_path / "a.md"
    src.write_text("速度v^2^", encoding="utf-8")
    result = convert_to_raw(str(src), str(tmp_path / "out"), "a")
    assert Path(result.raw_md).read_text(encoding="utf-8") == "速度v^2^"


# ============================================================
# idml 分支与错误
# ============================================================


def _minimal_idml(path: Path) -> Path:
    designmap = '<?xml version="1.0"?><Document><Spread src="Spreads/S.xml"/></Document>'
    spread = (
        '<?xml version="1.0"?><Spread>'
        '<Page Name="01" Self="p" GeometricBounds="0 0 600 800" ItemTransform="1 0 0 1 0 0"/>'
        '<TextFrame ParentStory="s" Self="t" PreviousTextFrame="n" NextTextFrame="n" '
        'ItemTransform="1 0 0 1 10 10"/>'
        '</Spread>'
    )
    story = (
        '<?xml version="1.0"?><Story>'
        '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/正文">'
        '<Content>正文内容</Content></ParagraphStyleRange>'
        '</Story>'
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("designmap.xml", designmap)
        z.writestr("Spreads/S.xml", spread)
        z.writestr("Stories/Story_s.xml", story)
    return path


def test_idml_branch(tmp_path):
    idml = _minimal_idml(tmp_path / "a.idml")
    result = convert_to_raw(str(idml), str(tmp_path / "out"), "a")
    assert result.source_kind == "idml"
    assert "正文内容" in Path(result.raw_md).read_text(encoding="utf-8")


def test_unsupported_extension_raises(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    with pytest.raises(UnsupportedError) as ei:
        convert_to_raw(str(src), str(tmp_path / "out"), "a")
    assert ei.value.code == "unsupported"
    assert ei.value.exit_code == 7


def test_missing_source_raises_not_found(tmp_path):
    with pytest.raises(NotFoundError):
        convert_to_raw(str(tmp_path / "nope.docx"), str(tmp_path / "out"), "nope")

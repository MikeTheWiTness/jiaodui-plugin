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
    extract_idml_to_markdown,
    find_pandoc,
    normalize_caret_tilde,
    pandoc_to_docx,
)
from jiaodui.errors import BusinessError, EnvError, NotFoundError, UnsupportedError


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
        # 成功必须同时产出文件：现在会校验产物，假 pandoc 也要写一个
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"x")
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


def test_pandoc_success_without_output_is_rejected(monkeypatch, tmp_path):
    """pandoc exit 0 但不产文件时必须判失败：下游 open() 会抛裸 FileNotFoundError。"""
    monkeypatch.setattr(convert, "find_pandoc", lambda: "/fake/pandoc")
    monkeypatch.setattr(convert.subprocess, "run",
                        lambda cmd, **kw: SimpleNamespace(returncode=0, stdout="", stderr=""))
    assert pandoc_to_docx("in.md", "out.docx") is False
    assert convert.convert_with_pandoc("a.docx", "o.md", "imgs") is False


def test_pandoc_timeout_is_reported(monkeypatch):
    """pandoc 卡住必须超时返回，而不是永久挂起。"""
    import subprocess as sp

    monkeypatch.setattr(convert, "find_pandoc", lambda: "/fake/pandoc")

    def fake_run(cmd, **kw):
        raise sp.TimeoutExpired(cmd, kw.get("timeout", 0))

    monkeypatch.setattr(convert.subprocess, "run", fake_run)
    assert pandoc_to_docx("in.md", "out.docx") is False
    assert convert.convert_with_pandoc("a.docx", "o.md", "imgs") is False


def test_pandoc_to_docx_without_pandoc(monkeypatch):
    monkeypatch.setattr(convert, "find_pandoc", lambda: None)
    assert pandoc_to_docx("in.md", "out.docx") is False


def test_convert_with_pandoc_command_and_mathjax(monkeypatch, tmp_path):
    monkeypatch.setattr(convert, "find_pandoc", lambda: "/fake/pandoc")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        # 成功必须同时产出文件：现在会校验产物，假 pandoc 也要写一个
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"x")
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


def _idml_zip(path: Path, members: dict) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return path


def test_doc_legacy_format_is_rejected_with_hint(tmp_path):
    """旧版 .doc 不是 OOXML：应当明确拒绝并提示另存，而不是让 pandoc 失败。"""
    src = tmp_path / "old.doc"
    src.write_bytes(b"\xd0\xcf\x11\xe0legacy")
    with pytest.raises(UnsupportedError) as ei:
        convert_to_raw(str(src), str(tmp_path / "out"), "old")
    assert ei.value.exit_code == 7
    assert "docx" in ei.value.message


def test_invalid_config_pattern_does_not_break_intent_cleaning():
    """学科配置里一条坏正则不该崩掉整条讲义清理链。"""
    markers = convert.get_intent_problem_markers(
        {"wrapped_patterns": [r"例(1", r"变式\d+"]})
    assert r"例(1" not in markers
    assert r"变式\d+" in markers

    # 直接传入坏正则同样只降级、不抛
    text = "【出题意图】\n应被清掉\n**例1** 题干"
    assert convert.clean_intent_markers(text, problem_markers=["例(1"]) == text.strip()


def test_base_name_cannot_escape_out_dir(tmp_path):
    """base_name 会拼进输出文件名：公开 API 也必须消毒，不能写到 out_dir 之外。"""
    src = tmp_path / "a.md"
    src.write_text("内容", encoding="utf-8")
    out = tmp_path / "out"
    result = convert_to_raw(str(src), str(out), "../逃逸")
    produced = Path(result.raw_md)
    assert produced.parent == out.resolve()
    assert not (tmp_path / "逃逸_raw.md").exists()


def test_idml_missing_designmap_is_structured_error(tmp_path):
    """缺 designmap.xml：结构化契约错误，不是裸 KeyError（旧实现直接崩）。"""
    idml = _idml_zip(tmp_path / "bad.idml", {"Stories/Story_s.xml": "<Story/>"})
    with pytest.raises(BusinessError) as ei:
        extract_idml_to_markdown(str(idml))
    assert ei.value.code == "invalid-source"
    assert "designmap.xml" in ei.value.message


def test_idml_bad_xml_is_structured_error(tmp_path):
    """成员不是 XML：结构化契约错误，不是裸 ParseError。"""
    idml = _idml_zip(tmp_path / "bad.idml", {"designmap.xml": "not xml <<<"})
    with pytest.raises(BusinessError) as ei:
        extract_idml_to_markdown(str(idml))
    assert ei.value.code == "invalid-source"
    assert "XML" in ei.value.message


def test_idml_oversized_member_is_rejected(tmp_path, monkeypatch):
    """解压上限：单成员超限直接拒绝（zip 炸弹闸门）。"""
    monkeypatch.setattr(convert, "IDML_MAX_ENTRY_BYTES", 10)
    idml = _minimal_idml(tmp_path / "big.idml")
    with pytest.raises(BusinessError) as ei:
        extract_idml_to_markdown(str(idml))
    assert ei.value.code == "invalid-source"
    assert "过大" in ei.value.message


def test_idml_deep_nesting_does_not_recurse(tmp_path):
    """深嵌套 XML 不再 RecursionError：遍历改为显式栈。"""
    depth = 3000
    story = ("<Story>" + "<A>" * depth
             + '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/正文">'
             + "<Content>深嵌套正文</Content></ParagraphStyleRange>"
             + "</A>" * depth + "</Story>")
    idml = _idml_zip(tmp_path / "deep.idml", {
        "designmap.xml": '<Document><Spread src="Spreads/S.xml"/></Document>',
        "Spreads/S.xml": ('<Spread><Page Name="01" Self="p" '
                          'GeometricBounds="0 0 600 800" ItemTransform="1 0 0 1 0 0"/>'
                          '<TextFrame ParentStory="s" Self="t" '
                          'ItemTransform="1 0 0 1 10 10"/></Spread>'),
        "Stories/Story_s.xml": story,
    })
    result = extract_idml_to_markdown(str(idml))
    assert "深嵌套正文" in result["markdown"]


def test_idml_output_without_directory(tmp_path):
    """输出只给文件名（无目录部分）时不得崩在 os.makedirs('')。"""
    idml = _minimal_idml(tmp_path / "a.idml")
    out = tmp_path / "plain.md"
    result = extract_idml_to_markdown(str(idml), str(out))
    assert out.is_file() and "正文内容" in result["markdown"]


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


# ============================================================
# 图片归置：路径形态与同名不同图（R-C01 / R-C02）
# ============================================================


def test_image_destination_keeps_parens_and_spaces():
    """pandoc 会写出未用 <> 包裹、含空格与括号的绝对路径，不能被空白切分截断。"""
    assert convert.image_destination("/private/tmp/x (v2)/a.png") == "/private/tmp/x (v2)/a.png"
    assert convert.image_destination("<./a b.png>") == "./a b.png"
    assert convert.image_destination('a.png "标题"') == "a.png"
    assert convert.image_destination("./a.png") == "./a.png"
    assert convert.image_destination("   ") is None


def test_organize_images_rewrites_paren_path_without_leaking_absolute(tmp_path):
    """路径含空格/括号的引用：必须复制成功、重写成相对路径，不得把绝对路径留在产物里。"""
    source_dir = tmp_path / "src"
    weird = source_dir / "space probe (v2)"
    weird.mkdir(parents=True)
    image = weird / "pic.png"
    image.write_bytes(b"png-bytes")
    images_dir = tmp_path / "out" / "材料_images"
    media = images_dir / "media"

    content = f"![图]({image})"
    warnings: list[str] = []
    new_content, copied, missing = convert._organize_images(
        content, [source_dir], images_dir, "材料", warnings)

    assert (copied, missing) == (1, 0), warnings
    assert new_content == "![图](./材料_images/media/pic.png)"
    assert str(image) not in new_content
    assert (media / "pic.png").read_bytes() == b"png-bytes"


def test_md_absolute_image_path_is_normalized_and_deterministic(tmp_path, monkeypatch):
    """同一材料从不同工作区转换必须产出相同 _raw.md：产物不得写进宿主机绝对路径。

    路径含括号时旧正则会在第一个 ) 处截断，产物里保留绝对路径 → 同一输入产出不同字节。
    """
    outputs = []
    for index in ("one", "two"):
        work = tmp_path / f"work {index}"
        work.mkdir()
        monkeypatch.setenv("JIAODUI_WORK_ROOT", str(work))
        assets = work / "assets (v2)"
        assets.mkdir()
        image = assets / "pic.png"
        image.write_bytes(b"PNG-" + index.encode())
        md = tmp_path / f"材料 {index}.md"
        md.write_text(f"1．题干 ![图]({image})。\n", encoding="utf-8")

        result = convert_to_raw(str(md), str(work / "raw"), "材料")
        text = Path(result.raw_md).read_text(encoding="utf-8")
        assert str(image) not in text, "产物不得含宿主机绝对路径"
        outputs.append((text, result.copied, result.missing))

    assert outputs[0][1:] == outputs[1][1:] == (1, 0)
    assert outputs[0][0] == outputs[1][0], "同一材料必须产出相同字节的 _raw.md"
    assert "![图](./材料_images/media/pic.png)" in outputs[0][0]


def test_clean_intent_markers_semantics():
    """出题意图清理：改成线性实现后语义必须与旧惰性回溯一致。"""
    clean = convert.clean_intent_markers
    assert clean("【出题意图】\n说明\n**例1** 题干") == "**例1** 题干"
    # 后面没有标记：旧正则的 lookahead 不匹配，整段保留
    assert clean("【出题意图】\n说明") == "【出题意图】\n说明"
    # 多个起点共用同一个标记：整体删除
    assert clean("【出题意图】\nA\n【出题意图】\nB\n**例1** 题干") == "**例1** 题干"
    # 标记在起点之前：不删
    assert clean("**例1** 题干\n【出题意图】\nA") == "**例1** 题干\n【出题意图】\nA"
    # 只认行首的【出题意图】
    assert clean("前缀【出题意图】\nA\n**例1** x") == "前缀【出题意图】\nA\n**例1** x"


def test_math_block_restore_is_lossless():
    """数学块还原改成单遍回填后必须无损：含 | 的公式、多块、下标分组都要原样。"""
    assert convert.comprehensive_clean("$a|b$ 和 $c|d$") == "$a|b$ 和 $c|d$"
    assert convert.comprehensive_clean("$x$ $y$ $z$") == "$x$ $y$ $z$"
    assert convert.fix_latex_escapes_text("$a_1$ 与 $b_2$") == "$a_1$ 与 $b_2$"
    assert convert.fix_latex_escapes_text("$" + "{x}" + "$") == "$" + "{x}" + "$"


def test_organize_images_skips_regex_without_image_syntax(tmp_path, monkeypatch):
    """没有 "](" 时不得调用图片正则：未闭合的 "![" 会让它退化成 O(n²)。"""
    calls: list[str] = []

    class _Spy:
        def sub(self, repl, content):
            calls.append(content)
            return content

    monkeypatch.setattr(convert, "_IMG_RE", _Spy())
    images_dir = tmp_path / "out" / "材料_images"
    convert._organize_images("纯文本，没有图片", [], images_dir, "材料", [])
    assert calls == []
    convert._organize_images("![a](missing.png)", [], images_dir, "材料", [])
    assert len(calls) == 1


def test_organize_images_prunes_stale_media(tmp_path):
    """重转后不再被引用的旧图必须清掉，否则会留在材料目录并被登记进资源摘要。"""
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "keep.png").write_bytes(b"KEEP")
    images_dir = tmp_path / "out" / "材料_images"
    media = images_dir / "media"
    media.mkdir(parents=True)
    (media / "stale.png").write_bytes(b"STALE")

    warnings: list[str] = []
    _, copied, missing = convert._organize_images(
        "![k](./keep.png)", [source_dir], images_dir, "材料", warnings)

    assert (copied, missing) == (1, 0)
    assert sorted(p.name for p in media.iterdir()) == ["keep.png"]
    assert any("旧图片" in w for w in warnings)


def test_organize_images_same_basename_keeps_both(tmp_path):
    """同名不同图必须各自保留：旧实现后者静默吃掉前者，却仍报 copied=2。"""
    import re

    first_dir = tmp_path / "a"
    second_dir = tmp_path / "b"
    first_dir.mkdir()
    second_dir.mkdir()
    (first_dir / "pic.png").write_bytes(b"FIRST")
    (second_dir / "pic.png").write_bytes(b"SECOND")
    images_dir = tmp_path / "out" / "材料_images"
    media = images_dir / "media"

    content = f"![一]({first_dir / 'pic.png'})\n![二]({second_dir / 'pic.png'})"
    warnings: list[str] = []
    new_content, copied, missing = convert._organize_images(
        content, [first_dir, second_dir], images_dir, "材料", warnings)

    assert (copied, missing) == (2, 0), warnings
    refs = re.findall(r"\]\(\./材料_images/media/([^)]+)\)", new_content)
    assert len(refs) == 2
    assert len(set(refs)) == 2, "同名不同图必须落到不同文件"
    assert {(media / name).read_bytes() for name in refs} == {b"FIRST", b"SECOND"}


@pytest.mark.parametrize("attributes", [
    "",
    '{width="1.222222in" height="1.472222in"}',
    '{width="1.222222in"\nheight="1.472222in"}',
])
def test_lecture_organize_images_ignores_only_confirmed_placeholder(tmp_path, monkeypatch, attributes):
    """讲义 DOCX 忽略已确认占位图，保留有效图；默认导入不启用忽略。"""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    broken = source_dir / "placeholder.png"
    valid = source_dir / "graph.png"
    broken.write_bytes(b"placeholder")
    valid.write_bytes(b"valid graph")
    monkeypatch.setattr(convert, "_is_broken_image_placeholder", lambda path: path == broken)
    images_dir = tmp_path / "out" / "材料_images"
    warnings: list[str] = []
    source = (f"![缺图](placeholder.png){attributes}\n"
              '![波形图](graph.png){width="2in" height="3in"}')

    text, copied, missing = convert._organize_images(
        source, [source_dir], images_dir, "材料", warnings,
        ignore_broken_placeholders=True)

    assert text == '\n![波形图](./材料_images/media/graph.png){width="2in" height="3in"}'
    assert (copied, missing) == (1, 0)
    assert (images_dir / "media" / "graph.png").read_bytes() == b"valid graph"
    assert warnings == ["已忽略讲义 DOCX 缺图占位图：placeholder.png"]

    untouched, copied, missing = convert._organize_images(
        f"![缺图](placeholder.png){attributes}", [source_dir], tmp_path / "default", "材料", [])
    assert untouched == f"![缺图](./材料_images/media/placeholder.png){attributes}"
    assert (copied, missing) == (1, 0)

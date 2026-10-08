"""正文顺序图片清单与白底准备测试。"""
from pathlib import Path

from PIL import Image

from jiaodui.inspect_images import inspect_unit_images, prepare_white_backgrounds


def _png(path: Path, color, *, alpha=255):
    image = Image.new("RGBA", (4, 3), (*color, alpha))
    image.save(path, "PNG")


def _unit(tmp_path: Path, text: str) -> Path:
    unit = tmp_path / "第1题"
    (unit / "images").mkdir(parents=True)
    (unit / "第1题.md").write_text(text, encoding="utf-8")
    return unit


def test_inspect_images_keeps_body_order_positions_and_duplicates(tmp_path):
    unit = _unit(tmp_path, "题干 ![十](./images/image10.png) ![二](./images/image2.png)\n重复 ![十](./images/image10.png)\n")
    _png(unit / "images/image10.png", (255, 0, 0))
    _png(unit / "images/image2.png", (0, 255, 0))

    result = inspect_unit_images(unit)

    assert result["ok"] is True
    refs = result["references"]
    assert [r["original_reference_path"] for r in refs] == [
        "./images/image10.png", "./images/image2.png", "./images/image10.png"
    ]
    assert [r["reference_index"] for r in refs] == [1, 2, 3]
    assert refs[0]["line"] == refs[1]["line"] == 1
    assert refs[0]["column"] < refs[1]["column"]
    assert refs[2]["line"] == 2
    assert refs[2]["duplicate_of"] == 1


def test_inspect_images_reports_missing_remote_and_extra(tmp_path):
    unit = _unit(tmp_path, "![缺](./images/missing.png)\n![远程](https://example.test/a.png)\n![FTP](ftp://example.test/b.png)\n")
    _png(unit / "images/extra.png", (0, 0, 255))

    result = inspect_unit_images(unit)

    assert result["ok"] is False
    assert [r["file_status"] for r in result["references"]] == ["missing", "remote_unsupported", "remote_unsupported"]
    assert {e["code"] for e in result["errors"]} == {"missing", "remote_unsupported"}
    assert [Path(x["path"]).name for x in result["extra_images"]] == ["extra.png"]
    assert result["warnings"][0]["code"] == "extra_images"


def test_transparent_image_has_explicit_white_background_binding(tmp_path):
    unit = _unit(tmp_path, "![透明](./images/transparent.png)\n")
    original = unit / "images/transparent.png"
    _png(original, (255, 0, 0), alpha=80)

    prepared = prepare_white_backgrounds(unit / "images")
    result = inspect_unit_images(unit)

    assert len(prepared) == 1
    assert original.is_file()
    ref = result["references"][0]
    assert result["ok"] is True
    assert ref["resolved_original_path"] == str(original.resolve())
    assert ref["actual_read_path"] == prepared[0]["white_background"]
    assert Path(ref["actual_read_path"]).is_file()
    with Image.open(ref["actual_read_path"]) as image:
        assert image.mode == "RGB"
        assert image.getpixel((0, 0)) != (255, 0, 0)


def test_unsupported_html_image_is_reported(tmp_path):
    unit = _unit(tmp_path, '<img src="./images/p.png">\n')
    result = inspect_unit_images(unit)
    assert result["ok"] is False
    assert any(error["code"] == "unsupported_syntax" for error in result["errors"])


def test_corrupt_white_background_is_rejected(tmp_path):
    unit = _unit(tmp_path, "![透明](./images/transparent.png)\n")
    original = unit / "images/transparent.png"
    _png(original, (255, 0, 0), alpha=80)
    prepared = prepare_white_backgrounds(unit / "images")
    Path(prepared[0]["white_background"]).write_bytes(b"not-an-image")

    result = inspect_unit_images(unit)

    assert result["ok"] is False
    assert result["references"][0]["file_status"] == "white_background_unreadable"
    assert any(error["code"] == "white_background_unreadable" for error in result["errors"])


def test_inline_code_image_text_is_not_a_reference(tmp_path):
    unit = _unit(tmp_path, "示例 `![图](missing.png)`\n```md\n![代码](also-missing.png)\n```\n")
    result = inspect_unit_images(unit)
    assert result["ok"] is True
    assert result["references"] == []


def test_reference_style_is_rejected_as_unsupported_syntax(tmp_path):
    unit = _unit(tmp_path, "![图][p]\n\n[p]: <./images/p.png>\n")
    _png(unit / "images/p.png", (20, 30, 40))
    result = inspect_unit_images(unit)
    assert result["ok"] is False
    assert result["references"] == []
    assert any(error["code"] == "unsupported_syntax" for error in result["errors"])

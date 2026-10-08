from pathlib import Path

from PIL import Image

from jiaodui.verify import verify_unit


def _make_unit(tmp_path: Path, source: str) -> Path:
    unit = tmp_path / "第1题"
    (unit / "images").mkdir(parents=True)
    (unit / "第1题.md").write_text(source, encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n",
        encoding="utf-8",
    )
    return unit


def test_verify_report_rejects_missing_image_reference(tmp_path):
    result = verify_unit(_make_unit(tmp_path, "题干 ![](./images/missing.png)"))
    assert not result.ok
    assert any(issue.code == "images.missing" for issue in result.errors)


def test_verify_report_rejects_remote_image_reference(tmp_path):
    result = verify_unit(_make_unit(tmp_path, "题干 ![](https://example.test/x.png)"))
    assert not result.ok
    assert any(issue.code == "images.remote_unsupported" for issue in result.errors)


def test_verify_report_warns_about_extra_image_without_read_task(tmp_path):
    unit = _make_unit(tmp_path, "题干")
    image = unit / "images" / "extra.png"
    Image.new("RGB", (2, 2), "white").save(image)
    result = verify_unit(unit)
    assert result.ok
    assert any(issue.code == "images.extra_images" for issue in result.warnings)
    assert result.stats["images"]["extra_count"] == 1


def test_verify_images_uses_explicit_source_path(tmp_path):
    unit = tmp_path / "第1题"
    (unit / "images").mkdir(parents=True)
    (unit / "第1题.md").write_text("默认源文无图", encoding="utf-8")
    explicit = tmp_path / "外部源.md"
    explicit.write_text("显式源文 ![](./missing.png)", encoding="utf-8")
    (unit / "_校对报告.md").write_text("无问题\n### 标记原文\n显式源文 ![](./missing.png)\n### 修改原因\n无\n", encoding="utf-8")

    result = verify_unit(unit, source_path=explicit)

    assert not result.ok
    assert any(issue.code == "images.missing" for issue in result.errors)


def test_verify_ignores_image_syntax_inside_markdown_code(tmp_path):
    source = "示例 " + chr(96) + "![图](missing.png)" + chr(96) + "\n```md\n![代码](also-missing.png)\n```\n"
    result = verify_unit(_make_unit(tmp_path, source))
    assert result.ok
    assert result.stats["images"]["reference_count"] == 0

"""图片资源是闸门项：下游命令必须与 verify-report 同口径拒绝。

契约出处：PRD §5.2（检查项含图片资源）+ AGENTS.md「build-report / parse-report /
build-docx 必须复核当前状态，拒绝消费未通过的报告」。此前下游只复核文本，
缺图单元能被登记、拼进整卷并进入 Word 交付。
"""
from pathlib import Path

import pytest

from jiaodui.errors import JiaoduiError


def _deliver(unit: Path) -> None:
    from jiaodui.workflow import parse_unit
    from jiaodui.verify import verify_unit
    from v2_helpers import deliver_v2

    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n", encoding="utf-8")
    if not verify_unit(unit).ok:
        # 显式人工兼容仍必须经过图片闸门，不能借新布局默认拒绝掩盖缺图错误。
        parse_unit(unit, manual_legacy=True)
    else:
        deliver_v2(unit)


def _material_with_one_broken_image(tmp_path, monkeypatch):
    from jiaodui.workflow import convert_material, split_material

    workspace = tmp_path / "W"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "卷.md"
    source.write_text("1．题干 ![](missing.png)。\n\n2．第二题。\n", encoding="utf-8")
    converted = convert_material(source)
    result = split_material(converted.raw_md, subject="高中物理", mode="exam")
    units = sorted(Path(p) for p in result.unit_dirs)
    bad = next(p for p in units if "missing.png" in (p / f"{p.name}.md").read_text(encoding="utf-8"))
    good = next(p for p in units if p != bad)
    return bad, good


def test_unverified_image_blocks_registration_and_whole_report(tmp_path, monkeypatch):
    from jiaodui.report import build_report
    from jiaodui.verify import verify_unit

    bad, good = _material_with_one_broken_image(tmp_path, monkeypatch)

    assert not verify_unit(bad).ok
    with pytest.raises(JiaoduiError) as refused:
        _deliver(bad)
    assert refused.value.code == "contract"
    assert refused.value.details.get("errors"), "必须由完整 verify 闸门拒绝，而不是因未指定人工兼容参数被拒"

    _deliver(good)
    result = build_report(bad.parent)
    assert [u["unit"] for u in result.included] == [good.name]
    assert [u["unit"] for u in result.failed] == [bad.name]


def test_corrupt_white_background_blocks_delivery(tmp_path, monkeypatch):
    """白底图是宿主实际读的那一份，坏了必须拒绝，而不是照原图放行。"""
    from PIL import Image

    from jiaodui.inspect_images import white_background_path
    from jiaodui.verify import verify_unit

    bad, _ = _material_with_one_broken_image(tmp_path, monkeypatch)
    source = (bad / f"{bad.name}.md").read_text(encoding="utf-8")
    transparent = bad / "images" / "透明.png"
    Image.new("RGBA", (4, 3), (255, 0, 0, 80)).save(transparent, "PNG")
    (bad / f"{bad.name}.md").write_text("题干 ![](./images/透明.png)\n", encoding="utf-8")
    (bad / "_校对报告.md").write_text(
        "无问题\n### 标记原文\n题干 ![](./images/透明.png)\n### 修改原因\n无\n", encoding="utf-8")

    from jiaodui.inspect_images import prepare_white_backgrounds

    prepared = prepare_white_backgrounds(bad / "images")
    assert prepared and prepared[0]["white_background"]
    Path(prepared[0]["white_background"]).write_bytes(b"not-an-image")
    assert white_background_path(transparent).is_file()

    result = verify_unit(bad)
    assert not result.ok
    assert any(issue.code == "images.white_background_unreadable" for issue in result.errors)
    assert source  # 源文读取一次即可，断言仅为说明 fixture 已建好

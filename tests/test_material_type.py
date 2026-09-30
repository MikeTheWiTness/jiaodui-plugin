"""讲义/试卷入口类型、转换差异与拆分同一 mode 的契约。"""
import json
from pathlib import Path

import pytest

from jiaodui.errors import JiaoduiError
from jiaodui.workflow import convert_material, slice_material, split_material


def source(tmp_path):
    path = tmp_path / "材料.md"
    path.write_text("**例1**\n\n1．题干。\n\n**例2**\n\n2．题干二。\n", encoding="utf-8")
    return path


def test_explicit_mode_skips_inspection_and_persists(tmp_path, monkeypatch):
    from jiaodui import inspect_source
    def forbidden(*args, **kwargs):
        pytest.fail("用户指定类型不得再次识别")
    monkeypatch.setattr(inspect_source, "inspect_source", forbidden)
    converted = convert_material(source(tmp_path), mode="lecture")
    result = split_material(converted.raw_md, subject="高中物理")
    assert [Path(d).name for d in result.unit_dirs] == ["单元1", "单元2"]
    data = json.loads((tmp_path / "校对/材料/_校对记录.json").read_text())
    assert data["material_type"] == {"mode": "lecture", "origin": "user", "reason": ""}
    assert data["params"]["mode"] == "lecture"
    assert data["conversion"]["mathjax"] is True


def test_unknown_type_cannot_silently_default_exam(tmp_path):
    converted = convert_material(source(tmp_path))
    with pytest.raises(JiaoduiError) as err:
        split_material(converted.raw_md, subject="高中物理")
    assert err.value.code == "mode-required"


def test_mode_origin_is_recorded_without_affecting_unit_input(tmp_path):
    converted = convert_material(source(tmp_path), mode="lecture", mode_origin="structure",
                                 mode_reason="主体内容反复置于嵌套表格")
    split_material(converted.raw_md, subject="高中物理")
    data = json.loads((tmp_path / "校对/材料/_校对记录.json").read_text())
    assert data["material_type"]["origin"] == "structure"
    assert data["material_type"]["reason"] == "主体内容反复置于嵌套表格"


def test_slice_preview_and_write_share_saved_mode(tmp_path):
    converted = convert_material(source(tmp_path), mode="lecture")
    preview = slice_material(None, raw=converted.raw_md, preview=True, subject="高中物理")
    assert preview["mode"] == "lecture"
    boundaries = tmp_path / "边界.json"
    boundaries.write_text(json.dumps({"raw": converted.raw_md, "subject": "高中物理",
                                     "boundaries": [{"start_line": 1, "end_line": 3}]}))
    result = slice_material(boundaries)
    assert Path(result.unit_dirs[0]).name == "单元1"


def test_slice_conflicting_explicit_and_boundary_modes_rejected(tmp_path):
    converted = convert_material(source(tmp_path), mode="lecture")
    boundaries = tmp_path / "边界.json"
    boundaries.write_text(json.dumps({"raw": converted.raw_md, "mode": "lecture",
                                     "boundaries": [{"start_line": 1, "end_line": 3}]}))
    with pytest.raises(JiaoduiError) as err:
        slice_material(boundaries, mode="exam")
    assert err.value.code == "mode-conflict"


@pytest.mark.parametrize("mode,prefix", [("lecture", "单元"), ("exam", "第")])
def test_manual_and_whole_document_strategies(tmp_path, mode, prefix):
    path = tmp_path / "材料.md"
    path.write_text("###### 单元开始 ######\n甲\n###### 单元结束 ######\n"
                    "###### 单元开始 ######\n乙\n###### 单元结束 ######\n")
    converted = convert_material(path, mode=mode)
    result = split_material(converted.raw_md, subject="高中物理", strategy="manual")
    assert len(result.unit_dirs) == 2 and all(Path(d).name.startswith(prefix) for d in result.unit_dirs)
    # 整篇策略使用独立材料，避免把双向集合冲突混入策略测试。
    converted = convert_material(path, mode=mode, material_name="整篇")
    result = split_material(converted.raw_md, subject="高中物理", strategy="none")
    assert len(result.unit_dirs) == 1
    assert "甲" in (Path(result.unit_dirs[0]) / (Path(result.unit_dirs[0]).name + ".md")).read_text()


@pytest.mark.parametrize("mode", ["lecture", "exam"])
def test_explicit_markdown_import_preserves_math_and_formatting(tmp_path, mode):
    path = tmp_path / "公式.md"
    path.write_text("$$x=1$$\n\nv^2^", encoding="utf-8")
    converted = convert_material(path, mode=mode)
    assert Path(converted.raw_md).read_text() == "$$x=1$$\n\nv^2^"


@pytest.mark.parametrize("mode,mathjax,expected", [
    ("lecture", True, "$$x=1$$"), ("exam", False, "$x=1$"), (None, False, "$$x=1$$"),
])
def test_word_import_uses_mode_specific_postprocessing(tmp_path, monkeypatch, mode, mathjax, expected):
    from jiaodui import convert
    path = tmp_path / "材料.docx"
    path.write_bytes(b"fixture")
    seen = []
    def fake_pandoc(src, raw, images, use_mathjax=False):
        seen.append(use_mathjax)
        Path(raw).write_text("$$x=1$$")
        return True
    monkeypatch.setattr(convert, "check_pandoc", lambda: True)
    monkeypatch.setattr(convert, "convert_with_pandoc", fake_pandoc)
    monkeypatch.setattr(convert, "enhance_docx_conversion", lambda *args: True)
    result = convert_material(path, mode=mode)
    assert seen == [mathjax]
    assert Path(result.raw_md).read_text() == expected


def test_untyped_slice_requires_mode_before_reading_full_preview(tmp_path):
    converted = convert_material(source(tmp_path))
    with pytest.raises(JiaoduiError) as err:
        slice_material(None, raw=converted.raw_md, preview=True)
    assert err.value.code == "mode-required"


def test_changing_import_type_invalidates_previous_delivery(tmp_path):
    from jiaodui.workflow import parse_unit
    from jiaodui.status import scan_status
    path = tmp_path / "材料.md"
    path.write_text("1．题干。")
    converted = convert_material(path, mode="exam")
    result = split_material(converted.raw_md, subject="高中物理")
    unit = Path(result.unit_dirs[0])
    text = (unit / "第1题.md").read_text()
    (unit / "_校对报告.md").write_text(f"无问题\n### 标记原文\n{text}\n### 修改原因\n无\n")
    parse_unit(unit)
    assert scan_status(unit.parent).counts()["已完成"] == 1
    convert_material(path, mode="lecture")
    assert scan_status(unit.parent).counts()["已完成"] == 0
    with pytest.raises(JiaoduiError) as err:
        split_material(converted.raw_md, subject="高中物理", mode="exam")
    assert err.value.code == "mode-conflict"


def test_manual_strategy_copies_referenced_images(tmp_path):
    path = tmp_path / "材料.md"
    (tmp_path / "图.png").write_bytes(b"known-image")
    path.write_text("###### 单元开始 ######\n题干 ![](图.png)\n###### 单元结束 ######\n")
    converted = convert_material(path, mode="exam")
    split = split_material(converted.raw_md, subject="高中物理", strategy="manual")
    assert split.copied == 1 and split.missing == 0
    assert (Path(split.unit_dirs[0]) / "images/图.png").read_bytes() == b"known-image"


def test_real_lecture_import_split_and_existing_gate(tmp_path):
    from jiaodui.verify import verify_unit
    import shutil
    repo = Path(__file__).resolve().parents[1]
    fixture = repo / "evaluation/m1"
    from jiaodui.convert import find_pandoc
    if not find_pandoc():
        pytest.skip("需要 Pandoc")
    result = convert_material(fixture / "source/第 6 讲校对测试.docx", mode="lecture")
    assert result.copied == 8 and result.missing == 0
    split = split_material(result.raw_md, subject="高中物理")
    assert len(split.unit_dirs) == 5 and split.missing == 0
    assert split.copied == 7
    for directory in map(Path, split.unit_dirs):
        shutil.copy2(fixture / "units/第 6 讲校对测试" / directory.name / "_校对报告.md",
                     directory / "_校对报告.md")
        assert verify_unit(directory).ok


def test_cli_explicit_type_then_inherited_split(tmp_path):
    import subprocess
    import sys
    src = source(tmp_path)
    convert = subprocess.run([sys.executable, "-m", "jiaodui", "convert", str(src),
                              "--mode", "lecture", "--mode-origin", "user", "--json"],
                             capture_output=True, text=True)
    assert convert.returncode == 0, convert.stderr
    payload = json.loads(convert.stdout)
    assert payload["mode"] == "lecture"
    split = subprocess.run([sys.executable, "-m", "jiaodui", "split", payload["raw_md"],
                            "--subject", "高中物理", "--json"], capture_output=True, text=True)
    assert split.returncode == 0, split.stderr
    assert [Path(p).name for p in json.loads(split.stdout)["unit_dirs"]] == ["单元1", "单元2"]

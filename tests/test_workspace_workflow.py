"""工作区与材料契约：预期来自 ADR 0002，不重算实现逻辑。"""
import json
import shutil
from pathlib import Path

import pytest

from jiaodui.errors import JiaoduiError


def test_write_requires_workspace(tmp_path, monkeypatch):
    from jiaodui.convert import convert_to_raw
    monkeypatch.delenv("JIAODUI_WORK_ROOT", raising=False)
    src = tmp_path / "外部.md"
    src.write_text("1．题干。", encoding="utf-8")
    with pytest.raises(JiaoduiError) as err:
        convert_to_raw(str(src), str(tmp_path / "raw"), "外部")
    assert err.value.code == "workspace-required"


def test_symlink_destination_refused(tmp_path, monkeypatch):
    from jiaodui.convert import convert_to_raw
    workspace = tmp_path / "W"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "raw").symlink_to(outside, target_is_directory=True)
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    src = tmp_path / "材料.md"
    src.write_text("1．题干。", encoding="utf-8")
    with pytest.raises(JiaoduiError) as err:
        convert_to_raw(str(src), str(workspace / "raw"), "材料")
    assert err.value.code == "outside-workspace"
    assert list(outside.iterdir()) == []


def _prepare(tmp_path, monkeypatch, name="A"):
    from jiaodui.workflow import convert_material, split_material
    workspace = tmp_path / name
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    src = tmp_path / "材料.md"
    src.write_text("1．设a为O点。\n\n2．第二题。\n", encoding="utf-8")
    converted = convert_material(src)
    result = split_material(converted.raw_md, subject="高中物理", mode="exam")
    return workspace, src, converted, result


def _deliver(unit):
    from jiaodui.workflow import parse_unit
    source = (unit / f"{unit.name}.md").read_text(encoding="utf-8")
    (unit / "_校对报告.md").write_text(
        f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n", encoding="utf-8")
    parse_unit(unit)


def test_layout_resume_rerun_and_move(tmp_path, monkeypatch):
    from jiaodui.workflow import split_material
    from jiaodui.status import scan_status
    from jiaodui.report import build_report
    workspace, src, converted, split = _prepare(tmp_path, monkeypatch)
    material = workspace / "校对" / "材料"
    assert Path(converted.raw_md) == material / "raw" / "材料_raw.md"
    assert (material / "source" / "材料.md").read_bytes() == src.read_bytes()
    assert len(split.unit_dirs) == 2
    paper = material / "units" / "材料"
    for unit in map(Path, split.unit_dirs):
        _deliver(unit)
    before = (paper / "第1题" / "_校对报告.md").read_bytes()
    split_material(converted.raw_md, subject="高中物理", mode="exam")
    assert scan_status(paper).counts()["已完成"] == 2
    assert (paper / "第1题" / "_校对报告.md").read_bytes() == before
    assert Path(build_report(paper).out_path).parent == material / "校对报告"
    split_material(converted.raw_md, subject="高中物理", mode="exam", rerun=True)
    assert scan_status(paper).counts().get("本轮未完成", 0) == 2
    assert not build_report(paper).included
    for unit in map(Path, split.unit_dirs):
        _deliver(unit)
    moved = tmp_path / "B" / "校对" / "材料"
    moved.parent.mkdir(parents=True)
    shutil.move(material, moved)
    monkeypatch.delenv("JIAODUI_WORK_ROOT", raising=False)
    assert scan_status(moved / "units" / "材料").counts()["已完成"] == 2
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(tmp_path / "B"))
    assert Path(build_report(moved / "units" / "材料").out_path).parent == moved / "校对报告"


def test_conflict_keeps_existing_bytes(tmp_path, monkeypatch):
    from jiaodui.workflow import convert_material
    workspace, src, converted, _ = _prepare(tmp_path, monkeypatch)
    manifest = workspace / "校对" / "材料" / "_校对记录.json"
    before = manifest.read_bytes(), Path(converted.raw_md).read_bytes()
    src.write_text("源文已改变", encoding="utf-8")
    with pytest.raises(JiaoduiError) as err:
        convert_material(src)
    assert err.value.code == "material-conflict"
    assert (manifest.read_bytes(), Path(converted.raw_md).read_bytes()) == before


@pytest.mark.parametrize("kind", ["extra", "missing"])
def test_unit_set_checked_both_ways(tmp_path, monkeypatch, kind):
    from jiaodui.status import scan_status
    workspace, _, _, _ = _prepare(tmp_path, monkeypatch)
    paper = workspace / "校对" / "材料" / "units" / "材料"
    if kind == "extra":
        (paper / "第3题").mkdir()
    else:
        shutil.rmtree(paper / "第2题")
    with pytest.raises(JiaoduiError) as err:
        scan_status(paper)
    assert err.value.code == "unit-set-mismatch"
    assert err.value.details["extra_units"] == (["第3题"] if kind == "extra" else [])
    assert err.value.details["missing_units"] == (["第2题"] if kind == "missing" else [])


def test_corrupt_manifest_never_legacy_fallback(tmp_path, monkeypatch):
    from jiaodui.status import scan_status
    workspace, _, _, _ = _prepare(tmp_path, monkeypatch)
    material = workspace / "校对" / "材料"
    (material / "_校对记录.json").write_text("{坏JSON", encoding="utf-8")
    with pytest.raises(JiaoduiError) as err:
        scan_status(material / "units" / "材料")
    assert err.value.code == "invalid-manifest"


def test_changed_markdown_image_starts_new_run(tmp_path, monkeypatch):
    from jiaodui.workflow import convert_material, split_material
    from jiaodui.status import scan_status
    workspace = tmp_path / "W"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "卷.md"
    source.write_text("1．题干 ![](pic.png)。\n", encoding="utf-8")
    image = tmp_path / "pic.png"
    image.write_bytes(b"first-image")
    converted = convert_material(source)
    split = split_material(converted.raw_md, subject="高中物理", mode="exam")
    unit = Path(split.unit_dirs[0])
    _deliver(unit)
    paper = unit.parent
    manifest = workspace / "校对" / "卷" / "_校对记录.json"
    before = json.loads(manifest.read_text())["current_run_id"]
    image.write_bytes(b"second-image")
    convert_material(source)
    assert scan_status(paper).counts()["已完成"] == 0
    split_material(converted.raw_md, subject="高中物理", mode="exam")
    assert json.loads(manifest.read_text())["current_run_id"] != before
    assert (unit / "images" / "pic.png").read_bytes() == b"second-image"


def test_adopt_missing_units_is_recorded(tmp_path, monkeypatch):
    from jiaodui.workflow import split_material
    from jiaodui.status import scan_status
    workspace, _, converted, result = _prepare(tmp_path, monkeypatch)
    paper = Path(result.unit_dirs[0]).parent
    shutil.rmtree(paper / "第2题")
    split_material(converted.raw_md, subject="高中物理", mode="exam", adopt_units=True)
    assert scan_status(paper).counts()["total"] == 1
    data = json.loads((workspace / "校对" / "材料" / "_校对记录.json").read_text())
    action = data["runs"][-1]["actions"][-1]
    assert action["before"] == ["第1题", "第2题"]
    assert action["after"] == ["第1题"]


def test_param_change_preserves_report_but_invalidates_registration(tmp_path, monkeypatch):
    from jiaodui.workflow import split_material
    from jiaodui.status import scan_status
    _, _, converted, result = _prepare(tmp_path, monkeypatch)
    unit = Path(result.unit_dirs[0])
    _deliver(unit)
    before = (unit / "_校对报告.md").read_bytes()
    split_material(converted.raw_md, subject="高中物理", mode="exam", clean=False)
    assert (unit / "_校对报告.md").read_bytes() == before
    assert scan_status(unit.parent).counts()["已完成"] == 0


def test_manifest_escape_without_workspace_is_rejected(tmp_path, monkeypatch):
    from jiaodui.status import scan_status
    workspace, _, _, result = _prepare(tmp_path, monkeypatch)
    manifest = workspace / "校对" / "材料" / "_校对记录.json"
    data = json.loads(manifest.read_text())
    data["paths"]["raw"] = "../../outside.md"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.delenv("JIAODUI_WORK_ROOT", raising=False)
    with pytest.raises(JiaoduiError) as err:
        scan_status(Path(result.unit_dirs[0]).parent)
    assert err.value.code == "invalid-manifest"


def test_docx_raw_images_remain_relative_after_move(tmp_path, monkeypatch):
    from docx import Document
    from PIL import Image
    from jiaodui.convert import find_pandoc
    from jiaodui.workflow import convert_material, split_material
    if not find_pandoc():
        pytest.skip("需要 pandoc")
    image = tmp_path / "picture.png"
    Image.new("RGB", (20, 20), "red").save(image)
    source = tmp_path / "图卷.docx"
    document = Document()
    document.add_paragraph("1．看图判断。")
    document.add_picture(str(image))
    document.save(source)
    workspace = tmp_path / "A"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    converted = convert_material(source)
    assert converted.missing == 0 and converted.copied == 1
    text = Path(converted.raw_md).read_text()
    assert "./图卷_images/media/" in text
    moved = tmp_path / "B" / "校对" / "图卷"
    moved.parent.mkdir(parents=True)
    shutil.move(workspace / "校对" / "图卷", moved)
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(tmp_path / "B"))
    split = split_material(moved / "raw" / "图卷_raw.md", subject="高中物理", mode="exam")
    assert split.missing == 0 and split.copied == 1


def test_subprocess_outputs_rejected_before_spawn(tmp_path, monkeypatch):
    from jiaodui import convert
    workspace = tmp_path / "W"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    def forbidden(*args, **kwargs):
        pytest.fail("越界输出不能启动子进程")
    monkeypatch.setattr(convert.subprocess, "run", forbidden)
    with pytest.raises(JiaoduiError) as err:
        convert.convert_with_pandoc("input.docx", str(tmp_path / "outside.md"), str(workspace / "imgs"))
    assert err.value.code == "outside-workspace"


def test_concurrent_registration_keeps_all_units(tmp_path, monkeypatch):
    import subprocess
    import sys
    from jiaodui.status import scan_status
    from jiaodui.workflow import split_material, convert_material
    workspace = tmp_path / "W"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "并发.md"
    source.write_text("\n\n".join(f"{n}．题干。" for n in range(1, 9)), encoding="utf-8")
    converted = convert_material(source)
    split = split_material(converted.raw_md, subject="高中物理", mode="exam")
    for d in map(Path, split.unit_dirs):
        src = (d / f"{d.name}.md").read_text()
        (d / "_校对报告.md").write_text(f"无问题\n### 标记原文\n{src}\n### 修改原因\n无\n")
    jobs = [subprocess.Popen([sys.executable, "-m", "jiaodui", "parse-report", "--unit", d, "--json"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for d in split.unit_dirs]
    for job in jobs:
        stdout, stderr = job.communicate(timeout=20)
        assert job.returncode == 0, stderr
        assert json.loads(stdout)["registered"]
    assert scan_status(Path(split.unit_dirs[0]).parent).counts()["已完成"] == 8


def test_word_rejects_partial_current_run(tmp_path, monkeypatch):
    from jiaodui.docx_report import build_docx, find_pandoc
    if not find_pandoc():
        pytest.skip("需要 pandoc")
    _, _, _, result = _prepare(tmp_path, monkeypatch)
    unit = Path(result.unit_dirs[0])
    _deliver(unit)
    word = build_docx(str(unit.parent))
    assert not word.ok
    assert [u["unit"] for u in word.excluded_units] == ["第2题"]


def test_material_name_keeps_literal_source_stem(tmp_path, monkeypatch):
    from jiaodui.workflow import convert_material
    workspace = tmp_path / "W"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "源_raw.md"
    source.write_text("1．题干。")
    converted = convert_material(source)
    assert Path(converted.raw_md) == workspace / "校对" / "源_raw" / "raw" / "源_raw_raw.md"


def test_failed_conversion_can_resume_same_material(tmp_path, monkeypatch):
    from jiaodui import convert
    from jiaodui.workflow import convert_material
    from jiaodui.errors import EnvError
    workspace = tmp_path / "W"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "失败.md"
    source.write_text("1．题干。")
    original = convert.convert_to_raw
    def fail(*args, **kwargs):
        raise EnvError("模拟转换失败")
    monkeypatch.setattr(convert, "convert_to_raw", fail)
    with pytest.raises(EnvError):
        convert_material(source)
    monkeypatch.setattr(convert, "convert_to_raw", original)
    assert Path(convert_material(source).raw_md).is_file()


def test_registration_refuses_run_changed_during_parse(tmp_path, monkeypatch):
    from jiaodui.workflow import parse_unit, split_material
    from jiaodui import report_parse
    _, _, converted, result = _prepare(tmp_path, monkeypatch)
    unit = Path(result.unit_dirs[0])
    source = (unit / "第1题.md").read_text()
    (unit / "_校对报告.md").write_text(f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n")
    save = report_parse.save_proofread_json
    def new_run_before_register(*args, **kwargs):
        saved = save(*args, **kwargs)
        split_material(converted.raw_md, subject="高中物理", mode="exam", rerun=True)
        return saved
    monkeypatch.setattr(report_parse, "save_proofread_json", new_run_before_register)
    with pytest.raises(JiaoduiError) as err:
        parse_unit(unit)
    assert err.value.code == "run-changed"


def test_crlf_report_registers_its_actual_bytes(tmp_path, monkeypatch):
    from jiaodui.workflow import parse_unit
    from jiaodui.status import scan_status
    _, _, _, result = _prepare(tmp_path, monkeypatch)
    unit = Path(result.unit_dirs[0])
    source = (unit / "第1题.md").read_text()
    report = f"无问题\n### 标记原文\n{source}\n### 修改原因\n无\n".replace("\n", "\r\n")
    (unit / "_校对报告.md").write_bytes(report.encode("utf-8"))
    assert parse_unit(unit)["registered"]
    assert scan_status(unit.parent).counts()["已完成"] == 1

"""确定性端到端流水线：split → verify → status → build-report → build-docx。"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from jiaodui.config import load_subject_config
from jiaodui.report import build_report
from jiaodui.status import COMPLETED, DELIVERED_UNVERIFIED, scan_status
from jiaodui.verify import verify_unit

REPO = Path(__file__).resolve().parent.parent
PANDOC = shutil.which("pandoc") or "/usr/local/bin/pandoc"

RAW = """1．设a为$O$点，求a的值。

2．第二题：$1+1=2$。
"""


def _split(tmp_path: Path):
    from jiaodui.split import split_exam

    config = load_subject_config(REPO / "config" / "subjects" / "高中物理.json")
    return split_exam(RAW, str(tmp_path), "卷子", config)


def _write_report_from_source(unit_dir: Path) -> None:
    """用单元源文构造一份必然通过完整性校验的报告（标记包裹已存在的字符）。"""
    from jiaodui.paths import find_source_md

    src = find_source_md(unit_dir).read_text(encoding="utf-8")
    original = next(ch for ch in src if ch.strip() and ch not in "$\\")
    marked = src.replace(original, f"【1|{original}|{original}改】", 1)
    (unit_dir / "_校对报告.md").write_text(
        f"一般问题\n### 标记原文\n{marked}\n### 修改原因\n1. 参数写错。\n",
        encoding="utf-8",
    )


def test_split_creates_units_and_source(tmp_path):
    res = _split(tmp_path)
    dirs = sorted(Path(p) for p in res.unit_dirs)
    assert len(dirs) == 2
    for d in dirs:
        assert list(d.glob("*.md")), d
        assert (d / "images").is_dir()


def test_split_rerun_keeps_existing_report(tmp_path):
    res = _split(tmp_path)
    unit = sorted(Path(p) for p in res.unit_dirs)[0]
    report = unit / "_校对报告.md"
    report.write_text("占位报告", encoding="utf-8")
    _split(tmp_path)  # 重跑
    assert report.read_text(encoding="utf-8") == "占位报告"


def test_pipeline_verify_status_report(tmp_path):
    res = _split(tmp_path)
    units = sorted(Path(p) for p in res.unit_dirs)
    _write_report_from_source(units[0])
    # 第二个单元写不合规报告
    (units[1] / "_校对报告.md").write_text("这里没有规范段落。", encoding="utf-8")

    assert verify_unit(units[0]).ok
    assert not verify_unit(units[1]).ok

    ps = scan_status(tmp_path)
    assert ps.counts()[COMPLETED] == 1
    assert ps.counts()[DELIVERED_UNVERIFIED] == 1

    out = tmp_path.parent / "out.md"
    br = build_report(tmp_path, out_path=out)
    text = out.read_text(encoding="utf-8")
    assert "【1|" in text and "1改】" in text
    assert "这里没有规范段落" not in text
    assert len(br.included) == 1 and len(br.failed) == 1


def test_split_copies_images_from_convention_dir(tmp_path):
    media = tmp_path / "卷子_images" / "media"
    media.mkdir(parents=True)
    (media / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    raw = tmp_path / "卷子_raw.md"
    raw.write_text("1．看图 ![](./卷子_images/media/pic.png) 求值。\n\n2．第二题。\n",
                   encoding="utf-8")
    from jiaodui.split import split_exam

    config = load_subject_config(REPO / "config" / "subjects" / "高中物理.json")
    res = split_exam(str(raw), str(tmp_path), "卷子", config)
    assert res.copied == 1
    unit = Path(res.unit_dirs[0])
    assert (unit / "images" / "pic.png").is_file()
    assert "./images/pic.png" in (unit / "第1题.md").read_text(encoding="utf-8")


@pytest.mark.skipif(not Path(PANDOC).is_file(), reason="需要 pandoc")
def test_pipeline_build_docx(tmp_path):
    from jiaodui.docx_report import build_docx

    res = _split(tmp_path)
    units = sorted(Path(p) for p in res.unit_dirs)
    for u in units:
        _write_report_from_source(u)
    result = build_docx(str(tmp_path / "卷子"))
    assert result.marker_count == 2
    assert result.missing_count == 0
    assert result.ok, result.warnings

"""M1 验收快照（evaluation/m1/）可从提交独立复现。

覆盖：
1. 5 个单元的报告在随仓源文上通过 verify-report；
2. 批注版 Word 生成 24 条批注且每条都有修改原因（含区间编号 1-3. / 3-6.）。
"""
import re
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "evaluation" / "m1"
UNIT_ROOT = FIXTURE / "units" / "第 6 讲校对测试"
sys.path.insert(0, str(ROOT))

from jiaodui.docx_report import find_pandoc, generate_combined_docx
from jiaodui.verify import verify_unit

PANDOC = find_pandoc()


def test_m1_fixture_units_pass_gate():
    dirs = sorted(p for p in UNIT_ROOT.iterdir() if p.is_dir())
    assert [d.name for d in dirs] == ["单元1", "单元2", "单元3", "单元4", "单元5"]
    for unit in dirs:
        result = verify_unit(str(unit))
        assert result.ok, f"{unit.name}: " + str([e.to_dict() for e in result.errors])


@pytest.mark.skipif(PANDOC is None, reason="pandoc 不可用")
def test_m1_fixture_build_docx_has_all_reasons(tmp_path):
    paper = tmp_path / "第 6 讲校对测试"
    shutil.copytree(UNIT_ROOT, paper)
    docx_path = generate_combined_docx(str(paper), str(tmp_path / "out"))
    assert docx_path and Path(docx_path).is_file()
    z = zipfile.ZipFile(docx_path)
    cmt = z.read("word/comments.xml").decode("utf-8")
    blocks = re.findall(r'<w:comment w:id="(\d+)"[^>]*>(.*?)</w:comment>', cmt, re.S)
    assert len(blocks) == 24
    missing = [cid for cid, body in blocks if "修改原因：" not in body]
    assert missing == [], f"缺少修改原因的批注：{missing}"

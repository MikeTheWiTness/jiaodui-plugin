"""入口检查只提供结构事实和受限节选，不承担材料分类或写盘。"""
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from jiaodui.errors import JiaoduiError

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REPO = Path(__file__).resolve().parents[1]


def docx(path, body):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", f'<w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>')
    return path


def test_counts_actual_table_ancestors_without_duplicating_text(tmp_path, monkeypatch):
    from jiaodui.inspect_source import inspect_source
    source = docx(tmp_path / "样本.docx", '<w:p><w:r><w:t>外</w:t></w:r></w:p>'
                  '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>表</w:t></w:r></w:p>'
                  '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>嵌套</w:t></w:r></w:p>'
                  '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>深层</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
                  '</w:tc></w:tr></w:tbl></w:tc></w:tr></w:tbl>')
    monkeypatch.delenv("JIAODUI_WORK_ROOT", raising=False)
    before = source.read_bytes()
    result = inspect_source(source)
    assert result["structure"] == {
        "table_count": 3, "top_level_table_count": 1, "nested_table_count": 2,
        "max_table_depth": 3, "top_tables_with_nested": 1,
        "text_chars": 6, "table_text_chars": 5, "nested_table_text_chars": 4,
        "nested_text_ratio": pytest.approx(4 / 6),
    }
    assert result["preview"] == ""
    assert "mode" not in result
    assert source.read_bytes() == before and list(tmp_path.iterdir()) == [source]


def test_regular_tables_are_not_nested(tmp_path):
    from jiaodui.inspect_source import inspect_source
    source = docx(tmp_path / "试卷.docx", '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>分数</w:t></w:r></w:p></w:tc></w:tr></w:tbl>' * 12)
    result = inspect_source(source)
    assert result["structure"]["table_count"] == 12
    assert result["structure"]["nested_table_count"] == 0
    assert result["structure"]["nested_text_ratio"] == 0


def test_docx_preview_limit_applies_before_returning_text(tmp_path):
    from jiaodui.inspect_source import inspect_source
    source = docx(tmp_path / "长文.docx", '<w:p><w:r><w:t>' + "甲" * 2500 + '不要输出尾部' + '</w:t></w:r></w:p>')
    result = inspect_source(source, preview_chars=20)
    assert result["preview"] == "甲" * 20
    assert result["preview_truncated"]
    assert "不要输出尾部" not in json.dumps(result, ensure_ascii=False)
    with pytest.raises(JiaoduiError) as err:
        inspect_source(source, preview_chars=2001)
    assert err.value.exit_code == 2


def test_markdown_preview_only_reads_bounded_prefix(tmp_path, monkeypatch):
    from jiaodui.inspect_source import inspect_source
    source = tmp_path / "材料.md"
    source.write_text("标题\n" + "正文" * 2000)
    def forbidden(*args, **kwargs):
        pytest.fail("Markdown 预览不可先 read_text 全文再截取")
    monkeypatch.setattr(Path, "read_text", forbidden)
    result = inspect_source(source, preview_chars=5)
    assert result["preview"] == "标题\n正文"
    assert result["structure"] is None and result["preview_truncated"]


def test_confirmed_m1_lecture_structure():
    from jiaodui.inspect_source import inspect_source
    result = inspect_source(REPO / "evaluation/m1/source/第 6 讲校对测试.docx")
    stats = result["structure"]
    assert stats["table_count"] == 42 and stats["nested_table_count"] == 32
    assert stats["max_table_depth"] == 3 and stats["top_tables_with_nested"] == 4
    assert stats["text_chars"] == 3838 and stats["nested_table_text_chars"] == 3104
    assert result["preview"] == ""


def test_unavailable_structure_does_not_mean_exam(tmp_path):
    from jiaodui.inspect_source import inspect_source
    source = tmp_path / "旧格式.doc"
    source.write_bytes(b"old binary word")
    result = inspect_source(source)
    assert result["structure"] is None and result["warnings"]
    assert "mode" not in result


def test_corrupt_docx_is_structured_error(tmp_path):
    from jiaodui.inspect_source import inspect_source
    source = tmp_path / "损坏.docx"
    source.write_bytes(b"not-a-zip")
    with pytest.raises(JiaoduiError) as err:
        inspect_source(source)
    assert err.value.code == "invalid-source"


def test_cli_inspection_is_available_without_workspace(tmp_path, monkeypatch):
    monkeypatch.delenv("JIAODUI_WORK_ROOT", raising=False)
    source = docx(tmp_path / "材料.docx", '<w:p><w:r><w:t>标题</w:t></w:r></w:p>')
    result = subprocess.run([sys.executable, "-m", "jiaodui", "inspect-source", str(source),
                             "--preview-chars", "2", "--json"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["preview"] == "标题"

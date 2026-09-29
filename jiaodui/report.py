"""整卷报告拼接（PRD §5.1）：只拼入通过校验的正文，失败单元写占位，无 LLM 参与。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .log import log
from .units import scan_unit_dirs
from .verify import verify_unit


@dataclass
class BuildReportResult:
    out_path: str | None
    included: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "out_path": self.out_path,
            "included": self.included,
            "failed": self.failed,
            "skipped": self.skipped,
            "warnings": self.warnings,
        }


def _base_name(paper_dir: Path) -> str:
    return paper_dir.name


def build_report(paper_dir: str | Path, out_path: str | Path | None = None) -> BuildReportResult:
    """按单元顺序拼接整卷报告。

    - 通过 verify-report 的单元：拼入正文（标记原文段 + 修改原因段），加 ## 单元名 标题。
    - 未通过/未开始的单元：写明显占位与原因，不拼入未校验正文。
    - .skip_proofread 单元跳过，单独计数。
    """
    paper_dir = Path(paper_dir)
    result = BuildReportResult(out_path=None)
    dirs = scan_unit_dirs(paper_dir)
    if not dirs:
        result.warnings.append("未发现任何单元目录")
        return result

    sections: list[str] = [f"# {_base_name(paper_dir)} 整卷校对报告", ""]
    for d in dirs:
        name = d.name
        report = paths.report_path(d)
        if paths.is_skip_unit(d):
            result.skipped.append({"unit": name, "reason": "跳过校对"})
            continue
        if not report.is_file():
            result.failed.append({"unit": name, "reason": "无校对报告"})
            sections.append(f"## {name}")
            sections.append("")
            sections.append("> ⚠️ 该单元未产生校对报告，未通过交付校验。")
            sections.append("")
            continue
        vr = verify_unit(d)
        if not vr.ok:
            reason = "；".join(i.message for i in vr.errors[:3]) or "校验未通过"
            result.failed.append({"unit": name, "reason": reason})
            sections.append(f"## {name}")
            sections.append("")
            sections.append(f"> ⚠️ 该单元报告未通过交付校验，正文未拼入。原因：{reason}")
            sections.append("")
            continue
        body = report.read_text(encoding="utf-8").strip()
        result.included.append({"unit": name, "markers": vr.marker_count})
        sections.append(f"## {name}")
        sections.append("")
        sections.append(body)
        sections.append("")

    if out_path is None:
        out_dir = paper_dir.parent / paths.WHOLE_REPORT_DIR
        out_path = out_dir / f"{paths.safe_name(_base_name(paper_dir))}_整卷报告.md"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    result.out_path = str(out_path)
    log(f"   📄 整卷报告：{out_path}（拼入 {len(result.included)}，失败 {len(result.failed)}，跳过 {len(result.skipped)}）")
    return result

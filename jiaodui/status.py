"""状态机：状态只由磁盘产物推导（PRD §5.3）。

优先级：先校验现有报告；通过则为「已完成」，即使保留旧 _校对失败.md 也不回退。
未通过且有失败记录才为「失败」；未通过且无失败记录为「已交付未过校验」。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .units import scan_unit_dirs
from .verify import verify_unit

NOT_STARTED = "未开始"
DELIVERED_UNVERIFIED = "已交付未过校验"
COMPLETED = "已完成"
FAILED = "失败"
SKIPPED = "跳过"

STATE_ORDER = [NOT_STARTED, DELIVERED_UNVERIFIED, COMPLETED, FAILED, SKIPPED]


@dataclass
class UnitStatus:
    unit: str
    dir: str
    state: str
    source: str | None = None
    report: str | None = None
    reason: str | None = None
    error_count: int = 0
    warning_count: int = 0
    marker_count: int = 0

    def to_dict(self) -> dict:
        return {
            "unit": self.unit,
            "dir": self.dir,
            "state": self.state,
            "source": self.source,
            "report": self.report,
            "reason": self.reason,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "marker_count": self.marker_count,
        }


@dataclass
class PaperStatus:
    paper_dir: str
    units: list[UnitStatus] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def counts(self) -> dict:
        counts = {s: 0 for s in STATE_ORDER}
        for u in self.units:
            counts[u.state] = counts.get(u.state, 0) + 1
        counts["total"] = len(self.units)
        return counts

    def to_dict(self) -> dict:
        return {"paper_dir": self.paper_dir, "counts": self.counts(),
                "units": [u.to_dict() for u in self.units], "warnings": self.warnings}


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def status_of_unit(unit_dir: str | Path) -> UnitStatus:
    """推导单个单元的状态。"""
    unit_dir = Path(unit_dir)
    name = unit_dir.name
    src = paths.find_source_md(unit_dir)
    report = paths.report_path(unit_dir)
    fail = paths.fail_path(unit_dir)

    if paths.is_skip_unit(unit_dir):
        return UnitStatus(name, str(unit_dir), SKIPPED,
                          source=str(src) if src else None)

    if not report.is_file():
        if src is not None:
            return UnitStatus(name, str(unit_dir), NOT_STARTED, source=str(src))
        return UnitStatus(name, str(unit_dir), NOT_STARTED, reason="源文缺失")

    result = verify_unit(unit_dir)
    if result.ok:
        return UnitStatus(name, str(unit_dir), COMPLETED, source=str(src) if src else None,
                          report=str(report), error_count=len(result.errors),
                          warning_count=len(result.warnings), marker_count=result.marker_count)

    reason = "；".join(i.message for i in result.errors[:3]) or "校验未通过"
    if fail.is_file():
        try:
            reason = _first_line(fail.read_text(encoding="utf-8")) or reason
        except OSError:
            pass
        return UnitStatus(name, str(unit_dir), FAILED, source=str(src) if src else None,
                          report=str(report), reason=reason, error_count=len(result.errors),
                          warning_count=len(result.warnings), marker_count=result.marker_count)
    return UnitStatus(name, str(unit_dir), DELIVERED_UNVERIFIED, source=str(src) if src else None,
                      report=str(report), reason=reason, error_count=len(result.errors),
                      warning_count=len(result.warnings), marker_count=result.marker_count)


def scan_status(paper_dir: str | Path) -> PaperStatus:
    """扫描 paper_dir 下所有单元的状态。"""
    paper_dir = Path(paper_dir)
    result = PaperStatus(paper_dir=str(paper_dir))
    if not paper_dir.is_dir():
        result.warnings.append(f"目录不存在：{paper_dir}")
        return result
    dirs = scan_unit_dirs(paper_dir)
    if not dirs:
        result.warnings.append("未发现任何单元目录（第N题 / 板块N / 单元N）")
    for d in dirs:
        result.units.append(status_of_unit(d))
    return result

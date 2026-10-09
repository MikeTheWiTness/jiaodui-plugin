"""绑定材料快照的单元报告预览与事务提交。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from . import material
from .errors import BusinessError, NotFoundError
from .paths import data_path, find_source_md, report_path
from .report_parse import parse_proofread_md, split_sections
from .report_suggestions import ReportCandidate, extract_body, render_suggestions
from .verify import verify_report_text, verify_unit
from .workdir import ensure_inside


def _canonical_hash(value: dict) -> str:
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _current(root: Path, unit: Path) -> tuple[dict, Path, str]:
    root = ensure_inside(root)
    unit = ensure_inside(unit)
    data = material.load(root)
    paper = material.check_units(root, data)
    if unit.parent != paper or unit.name not in data["unit_set"]:
        raise BusinessError("单元不属于当前材料单元集", code="unit-path-mismatch")
    if data.get("task_id") is None or unit.name not in data.get("unit_ids", {}):
        raise BusinessError("材料尚无task/unit身份，请重新拆分后再提交", code="identity-missing")
    if data["runs"][-1].get("execution_policy") is None:
        raise BusinessError("当前轮次尚未确认执行模式", code="execution-policy-required")
    source = find_source_md(unit)
    if source is None or not source.is_file():
        raise NotFoundError("找不到单元源文", details={"unit": str(unit)})
    return data, source, source.read_bytes().decode("utf-8")


def _snapshot(root: Path, unit: Path) -> dict:
    data, source, source_text = _current(root, unit)
    inputs = material.unit_inputs(root, unit)
    if inputs != data["unit_inputs"].get(unit.name):
        raise BusinessError("源文或图片已改变，当前单元快照失效", code="unit-input-mismatch")
    report = report_path(unit)
    data_file = data_path(unit)
    value = {
        "task_id": data["task_id"],
        "unit_id": data["unit_ids"][unit.name],
        "unit": unit.name,
        "run_id": data["current_run_id"],
        "inputs": inputs,
        "input_digest": _canonical_hash(inputs),
        "source_sha256": material.sha256(source),
        "body_sha256": hashlib.sha256(extract_body(source_text).encode("utf-8")).hexdigest(),
        "report_sha256": material.sha256(report) if report.is_file() else None,
        "data_sha256": material.sha256(data_file) if data_file.is_file() else None,
    }
    value["snapshot_sha256"] = _canonical_hash(value)
    return value


def read_unit_snapshot(task_id: str, unit_id: str) -> dict:
    root, unit = material.find_unit_by_id(task_id, unit_id)
    snapshot = _snapshot(root, unit)
    if snapshot["task_id"] != task_id or snapshot["unit_id"] != unit_id:
        raise BusinessError("task/unit身份不匹配", code="identity-mismatch")
    return snapshot


def _candidate(root: Path, unit: Path, snapshot: dict, proposal: dict) -> tuple[ReportCandidate, dict]:
    if _snapshot(root, unit)["snapshot_sha256"] != snapshot["snapshot_sha256"]:
        raise BusinessError("读取期间单元输入或交付版本已改变", code="snapshot-stale")
    data, source_path, source_text = _current(root, unit)
    if (data["task_id"] != snapshot["task_id"] or data["unit_ids"].get(unit.name) != snapshot["unit_id"]
            or data["current_run_id"] != snapshot["run_id"]):
        raise BusinessError("task/unit/run身份已改变", code="snapshot-stale")
    try:
        candidate = render_suggestions(source_text, proposal,
                                       expected_task_id=snapshot["task_id"],
                                       expected_unit_id=snapshot["unit_id"],
                                       expected_run_id=snapshot["run_id"],
                                       calc_calls=data["runs"][-1].get("calc_calls", []),
                                       expected_source_sha256=snapshot["source_sha256"])
    except ValueError as exc:
        raise BusinessError(str(exc), code=getattr(exc, "code", "proposal-invalid")) from exc
    verdict = verify_report_text(candidate.text, source_text)
    if not verdict.ok:
        raise BusinessError("生成报告未通过文本闸门", code="contract",
                            details={"errors": [item.to_dict() for item in verdict.errors]})
    _, marked_body, _ = split_sections(candidate.text)
    from .markers import split_marked_body
    if (marked_body is None
            or split_marked_body(marked_body, escaped=True) != source_text):
        raise BusinessError("生成报告无法逐字恢复源文", code="report-restore-mismatch")
    parsed = parse_proofread_md(candidate.text)
    if parsed is None:
        raise BusinessError("生成报告无法被现有解析器读取", code="parse-failed")
    from .inspect_images import inspect_unit_images
    images = inspect_unit_images(unit, source_path=source_path, allow_legacy_transparent=False)
    if not images["ok"]:
        raise BusinessError("单元图片资源未通过闸门", code="images-invalid",
                            details={"errors": images["errors"]})
    return candidate, {"parsed": parsed, "images": images}


def preview_unit_submission(task_id: str, unit_id: str, proposal: dict,
                            expected_snapshot_sha256: str) -> dict:
    root, unit = material.find_unit_by_id(task_id, unit_id)
    snapshot = _snapshot(root, unit)
    if snapshot["snapshot_sha256"] != expected_snapshot_sha256:
        raise BusinessError("预览使用的单元版本已改变", code="snapshot-stale",
                            details={"current_snapshot_sha256": snapshot["snapshot_sha256"]})
    candidate, checked = _candidate(root, unit, snapshot, proposal)
    return {"ok": True, "preview": True, "snapshot": snapshot,
            "report_sha256": hashlib.sha256(candidate.text.encode("utf-8")).hexdigest(),
            "proposal_sha256": candidate.proposal_sha256,
            "summary": candidate.summary, "marker_count": len(candidate.corrections),
            "image_result": checked["images"]}


def _atomic_write(path: Path, content: bytes) -> None:
    ensure_inside(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _restore(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
    else:
        _atomic_write(path, previous)


def commit_unit_submission(task_id: str, unit_id: str, proposal: dict,
                           expected_snapshot_sha256: str) -> dict:
    """在材料锁内以CAS提交报告/数据，并将清单登记作为最后提交标志。"""
    root, unit = material.find_unit_by_id(task_id, unit_id)
    report = report_path(unit)
    data_file = data_path(unit)
    manifest = root / material.MANIFEST
    with material.locked(root):
        snapshot = _snapshot(root, unit)
        if snapshot["snapshot_sha256"] != expected_snapshot_sha256:
            raise BusinessError("提交使用的单元版本已改变，拒绝覆盖", code="snapshot-stale",
                                details={"current_snapshot_sha256": snapshot["snapshot_sha256"]})
        candidate, checked = _candidate(root, unit, snapshot, proposal)
        if data_file.is_file():
            try:
                previous_data = json.loads(data_file.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise BusinessError("当前数据损坏，不能静默覆盖", code="data-invalid") from exc
            if not isinstance(previous_data, dict):
                raise BusinessError("当前数据结构无效，不能静默覆盖", code="data-invalid")
            if (previous_data.get("schema_version") == 2
                    and proposal["proposal_revision"] != previous_data.get("proposal_revision", 0) + 1):
                raise BusinessError("新建议revision必须在当前版本基础上增加1", code="proposal-revision-stale")
        report_bytes = candidate.text.encode("utf-8")
        parsed: dict[str, Any] = dict(checked["parsed"])
        parsed.update({
            "schema_version": 2,
            "proposal": proposal,
            "proposal_revision": proposal["proposal_revision"],
            "proposal_sha256": candidate.proposal_sha256,
            "source_sha256": candidate.source_sha256,
            "body_sha256": snapshot["body_sha256"],
            "input_digest": snapshot["input_digest"],
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "run_id": snapshot["run_id"],
        })
        data_bytes = (json.dumps(parsed, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        before = {
            report: report.read_bytes() if report.is_file() else None,
            data_file: data_file.read_bytes() if data_file.is_file() else None,
            manifest: manifest.read_bytes(),
        }
        try:
            _atomic_write(report, report_bytes)
            _atomic_write(data_file, data_bytes)
            verdict = verify_unit(unit)
            if not verdict.ok:
                raise BusinessError("落盘后的单元未通过完整verify闸门", code="contract",
                                    details={"errors": [item.to_dict() for item in verdict.errors]})
            material.register_locked(root, unit, candidate.text, snapshot["run_id"])
        except Exception:
            for path, content in before.items():
                _restore(path, content)
            raise
        return {"ok": True, "registered": True, "verified": True,
                "task_id": task_id, "unit_id": unit_id, "run_id": snapshot["run_id"],
                "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
                "data_sha256": hashlib.sha256(data_bytes).hexdigest(),
                "proposal_sha256": candidate.proposal_sha256,
                "summary": candidate.summary, "marker_count": len(candidate.corrections),
                "image_result": checked["images"]}

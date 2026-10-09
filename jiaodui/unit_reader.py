"""通过持久身份只读获取单元源文分段和图片清单。"""
from __future__ import annotations

from . import material
from .errors import BusinessError, NotFoundError
from .paths import find_source_md
from .workdir import ensure_inside

MAX_LINES = 2000


def read_unit_source(task_id: str, unit_id: str, *, start_line: int = 1,
                     max_lines: int = MAX_LINES) -> dict:
    """在当前工作区按ID读取源文页，不接受任意路径或写操作。"""
    if type(start_line) is not int or start_line < 1:
        raise BusinessError("start_line必须为正整数", code="unit-read-range")
    if type(max_lines) is not int or not 1 <= max_lines <= MAX_LINES:
        raise BusinessError(f"max_lines必须在1..{MAX_LINES}范围内", code="unit-read-range")
    root, unit = material.find_unit_by_id(task_id, unit_id)
    ensure_inside(unit)
    data = material.load(root)
    paper = material.check_units(root, data)
    if unit.parent != paper or data.get("unit_ids", {}).get(unit.name) != unit_id:
        raise BusinessError("task/unit身份与当前材料不一致", code="identity-mismatch")
    source = find_source_md(unit)
    if source is None or not source.is_file():
        raise NotFoundError("找不到登记单元源文", details={"unit_id": unit_id})
    raw = source.read_bytes()
    digest = material.sha256(source)
    if material.unit_inputs(root, unit) != data["unit_inputs"].get(unit.name):
        raise BusinessError("源文或图片与当前轮次摘要不一致", code="unit-input-mismatch")
    text = raw.decode("utf-8")
    lines = text.splitlines(keepends=True)
    if text and not lines:
        lines = [text]
    start = start_line - 1
    selected = lines[start:start + max_lines]
    end_line = start + len(selected)
    from .inspect_images import inspect_unit_images
    images = inspect_unit_images(unit, source_path=source, allow_legacy_transparent=False)
    return {
        "ok": True,
        "task_id": task_id,
        "unit_id": unit_id,
        "unit": unit.name,
        "run_id": data["current_run_id"],
        "source_sha256": digest,
        "body_sha256": digest,
        "line_start": start_line if selected else None,
        "line_end": end_line if selected else None,
        "line_count": len(lines),
        "next_line": end_line + 1 if end_line < len(lines) else None,
        "content": "".join(selected),
        "images": images,
    }

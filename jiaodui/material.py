"""材料清单、轮次与交付登记；清单描述产物，不授予写入权限。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .errors import BusinessError
from .paths import find_source_md, is_skip_unit, report_path, safe_name
from .units import is_unit_dir, scan_unit_dirs
from .workdir import ensure_inside, input_path

MANIFEST = "_校对记录.json"


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _invalid(message: str, root: Path):
    raise BusinessError(message, code="invalid-manifest", details={"material_dir": str(root)})


def relative_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        _invalid("清单内部路径必须为非空相对路径", root)
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        _invalid("清单内部路径越出材料目录", root)
    return path


def validate(root: Path, data: dict) -> dict:
    """缺失、损坏或不支持的清单一律拒绝，不作历史回退。"""
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        _invalid("不支持的材料清单结构或 schema_version", root)
    for key in ("material_name", "source_path", "source_sha256", "created_at", "current_run_id"):
        if not isinstance(data.get(key), str) or not data[key]:
            _invalid(f"清单缺少有效字段：{key}", root)
    name = data["material_name"]
    if safe_name(name) != name or name in {".", ".."}:
        _invalid("清单材料名无效", root)
    if not Path(data["source_path"]).is_absolute() or not re.fullmatch(r"[0-9a-f]{64}", data["source_sha256"]):
        _invalid("清单源文件溯源字段无效", root)
    if not isinstance(data.get("paths"), dict) or set(data["paths"]) != {"source", "raw", "images", "paper"}:
        _invalid("清单缺少内部路径", root)
    for value in data["paths"].values():
        relative_path(root, value)
    if (data["paths"]["raw"] != f"raw/{name}_raw.md"
            or data["paths"]["images"] != f"raw/{name}_images"
            or data["paths"]["paper"] != f"units/{name}"
            or Path(data["paths"]["source"]).parts[0] != "source"):
        _invalid("清单内部路径不符合材料布局", root)
    if not isinstance(data.get("params"), dict) or not isinstance(data.get("unit_inputs"), dict):
        _invalid("清单参数或单元输入摘要无效", root)
    if "material_type" in data:
        from .material_type import validate_selection
        validate_selection(data["material_type"])
    for key in ("unit_set", "resources", "runs", "unit_records"):
        if not isinstance(data.get(key), list):
            _invalid(f"清单字段必须为数组：{key}", root)
    names = data["unit_set"]
    if (any(not isinstance(n, str) or not re.fullmatch(r"(?:第\d+题|单元\d+|板块\d+)", n)
            for n in names) or len(set(names)) != len(names)):
        _invalid("清单单元集合无效", root)
    if set(data["unit_inputs"]) != set(names):
        _invalid("单元集合与输入摘要不一致", root)
    def resource(entry):
        if not isinstance(entry, dict) or set(entry) != {"rel", "sha256"}:
            _invalid("关联资源结构无效", root)
        relative_path(root, entry["rel"])
        if not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            _invalid("关联资源摘要无效", root)
    for r in data["resources"]:
        resource(r)
    def input_record(entry):
        if (not isinstance(entry, dict) or not isinstance(entry.get("source_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", entry["source_sha256"])
                or not isinstance(entry.get("images"), list)):
            _invalid("单元输入摘要无效或源文缺失", root)
        for r in entry["images"]:
            resource(r)
    for entry in data["unit_inputs"].values():
        input_record(entry)
    ids = []
    for run in data["runs"]:
        if (not isinstance(run, dict) or not isinstance(run.get("run_id"), str) or not run["run_id"]
                or not isinstance(run.get("started_at"), str) or not isinstance(run.get("actions"), list)
                or not isinstance(run.get("params"), dict) or not isinstance(run.get("resources"), list)
                or not isinstance(run.get("status"), str)
                or run["status"] not in {"in_progress", "completed", "superseded"}):
            _invalid("轮次记录无效", root)
        ids.append(run["run_id"])
        for r in run["resources"]:
            resource(r)
    if len(set(ids)) != len(ids) or not ids or data["current_run_id"] != ids[-1]:
        _invalid("当前轮次不存在或轮次重复", root)
    for record in data["unit_records"]:
        if (not isinstance(record, dict) or record.get("run_id") not in ids
                or not isinstance(record.get("unit"), str) or not isinstance(record.get("recorded_at"), str)
                or not isinstance(record.get("report_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["report_sha256"])
                or not isinstance(record.get("inputs"), dict)):
            _invalid("单元交付登记无效", root)
        input_record(record["inputs"])
    conversion = data.get("conversion")
    if conversion is not None:
        if (not isinstance(conversion, dict) or not isinstance(conversion.get("raw_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", conversion["raw_sha256"])
                or type(conversion.get("mathjax")) is not bool
                or not isinstance(conversion.get("resources"), list)
                or not isinstance(conversion.get("source_resources"), list)):
            _invalid("转换摘要无效", root)
        if conversion.get("mode") is not None and (not isinstance(conversion["mode"], str)
                                                   or conversion["mode"] not in {"lecture", "exam"}):
            _invalid("转换类型无效", root)
        for r in conversion["resources"] + conversion["source_resources"]:
            resource(r)
    return data


def load(root: Path) -> dict:
    try:
        path = relative_path(root, MANIFEST)
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        _invalid(f"无法读取材料清单：{exc}", root)
    return validate(root, data)


def find_material(path: str | Path) -> Path | None:
    """只查调用目录及三层祖先，禁止用目录名字猜材料身份。"""
    path = input_path(path)
    current = path if path.is_dir() else path.parent
    for _ in range(4):
        marker = current / MANIFEST
        if marker.exists() or marker.is_symlink():
            load(current)
            return current
        if current.parent == current:
            break
        current = current.parent
    return None


def write(root: Path, data: dict) -> None:
    """同目录临时文件原子替换；临时文件不作为运行产物保留。"""
    path = ensure_inside(root / MANIFEST)
    validate(root, data)
    fd, temporary = tempfile.mkstemp(prefix=".jiaodui-manifest-", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(root: Path):
    """锁定材料目录 inode，原子替换清单不会改变锁对象。"""
    import fcntl
    root = ensure_inside(root)
    fd = os.open(root, os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def resources(root: Path, directory: Path) -> list[dict]:
    entries = []
    if directory.is_dir():
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                relative_path(root, str(path.relative_to(root)))
                entries.append({"rel": path.relative_to(root).as_posix(), "sha256": sha256(path)})
    return entries


def unit_inputs(root: Path, unit: Path) -> dict:
    source = find_source_md(unit)
    return {"source_sha256": sha256(source) if source else "",
            "images": resources(root, unit / "images")}


def new_run(data: dict, params: dict, associated: list[dict]) -> str:
    for previous in data["runs"]:
        if previous["run_id"] == data.get("current_run_id") and previous["status"] == "in_progress":
            previous["status"] = "superseded"
    run_id = uuid.uuid4().hex
    data["current_run_id"] = run_id
    data["params"] = params
    data["resources"] = associated
    data["runs"].append({"run_id": run_id, "started_at": now(), "status": "in_progress",
                         "params": params, "resources": associated, "actions": []})
    return run_id


def check_units(root: Path, data: dict) -> Path:
    paper = relative_path(root, data["paths"]["paper"])
    dirs = sorted((p for p in paper.iterdir() if p.is_dir() and is_unit_dir(p.name)),
                  key=lambda p: p.name) if paper.is_dir() else []
    for directory in dirs:
        relative_path(root, directory.relative_to(root).as_posix())
    actual = {p.name for p in dirs}
    expected = set(data["unit_set"])
    if actual != expected:
        from .status import status_of_unit
        scannable = []
        for d in dirs:
            s = status_of_unit(d).to_dict()
            s["report_sha256"] = sha256(report_path(d)) if report_path(d).is_file() else None
            scannable.append(s)
        raise BusinessError("材料单元集合与磁盘不一致", code="unit-set-mismatch",
                            details={"material_dir": str(root), "run_id": data["current_run_id"],
                                     "extra_units": sorted(actual - expected),
                                     "missing_units": sorted(expected - actual), "scannable": scannable})
    return paper


def registered(root: Path, data: dict, unit: Path) -> bool:
    report = report_path(unit)
    if not report.is_file() or unit_inputs(root, unit) != data["unit_inputs"].get(unit.name):
        return False
    digest = sha256(report)
    return any(r["unit"] == unit.name and r["run_id"] == data["current_run_id"]
               and r["report_sha256"] == digest and r["inputs"] == data["unit_inputs"][unit.name]
               for r in data["unit_records"])


def register(root: Path, unit: Path, text: str, expected_run_id: str) -> None:
    with locked(root):
        data = load(root)
        if data["current_run_id"] != expected_run_id:
            raise BusinessError("交付登记期间轮次已改变，请重新校对当前轮次", code="run-changed")
        paper = check_units(root, data)
        if unit.parent != paper or unit_inputs(root, unit) != data["unit_inputs"].get(unit.name):
            raise BusinessError("单元输入已改变，需重新拆分后交付", code="unit-input-mismatch")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if sha256(report_path(unit)) != digest:
            raise BusinessError("登记前报告已改变，请重新校验", code="report-changed")
        data["unit_records"] = [r for r in data["unit_records"]
                                if not (r["unit"] == unit.name and r["run_id"] == data["current_run_id"])]
        data["unit_records"].append({"unit": unit.name, "run_id": data["current_run_id"],
                                     "report_sha256": digest, "recorded_at": now(),
                                     "inputs": data["unit_inputs"][unit.name]})
        from .verify import verify_unit
        complete = all(is_skip_unit(paper / n) or (registered(root, data, paper / n) and verify_unit(paper / n).ok)
                       for n in data["unit_set"])
        data["runs"][-1]["status"] = "completed" if complete else "in_progress"
        write(root, data)


def downstream(paper: str | Path, *, legacy_layout: bool = False) -> tuple[Path, dict | None]:
    paper = input_path(paper)
    root = find_material(paper)
    if root is None:
        if not legacy_layout:
            raise BusinessError("未找到材料清单；历史写入需 --legacy-layout", code="manifest-required")
        ensure_inside(paper)
        return paper.parent, None
    ensure_inside(root)
    data = load(root)
    expected = check_units(root, data)
    if paper != expected:
        raise BusinessError("请使用清单中的单元根目录", code="paper-path-mismatch",
                            details={"paper_dir": str(expected)})
    return root, data

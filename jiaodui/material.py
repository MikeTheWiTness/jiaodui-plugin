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

from .errors import BusinessError, NotFoundError
from .paths import data_path, find_source_md, is_skip_unit, report_path, safe_name
from .units import is_unit_dir, scan_unit_dirs
from .workdir import ensure_inside, input_path, workspace_root

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
    if "task_id" in data or "unit_ids" in data:
        task_id = data.get("task_id")
        unit_ids = data.get("unit_ids")
        if (not isinstance(task_id, str) or not re.fullmatch(r"[0-9a-f]{32}", task_id)
                or not isinstance(unit_ids, dict) or set(unit_ids) != set(names)
                or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value)
                       for value in unit_ids.values())
                or len(set(unit_ids.values())) != len(unit_ids)):
            _invalid("task/unit身份映射无效", root)
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
        policy = run.get("execution_policy")
        if policy is not None:
            _validate_execution_policy(policy, run["run_id"], root)
        for r in run["resources"]:
            resource(r)
    if len(set(ids)) != len(ids) or not ids or data["current_run_id"] != ids[-1]:
        _invalid("当前轮次不存在或轮次重复", root)
    for record in data["unit_records"]:
        if (not isinstance(record, dict) or record.get("run_id") not in ids
                or not isinstance(record.get("unit"), str) or not isinstance(record.get("recorded_at"), str)
                or not isinstance(record.get("report_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", record["report_sha256"])
                # data_sha256 可缺省（升级前的旧记录），给了就必须是合法摘要
                or ("data_sha256" in record and (
                    not isinstance(record["data_sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", record["data_sha256"])))
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


def _validate_execution_policy(policy: dict, run_id: str, root: Path) -> None:
    """校验绑定当前材料轮次的一次性执行授权。"""
    expected = {
        "call_correction": 2,
        "calc_representation": 2,
        "report_repair": 3,
        "targeted_review": 2,
        "technical_redispatch": 1,
        "image_schema_fix": 2,
    }
    if (not isinstance(policy, dict)
            or policy.get("mode") not in {"automatic", "interactive"}
            or policy.get("origin") not in {"user", "confirmed"}
            or policy.get("run_id") != run_id
            or not isinstance(policy.get("confirmed_at"), str)
            or policy.get("budgets") != expected):
        _invalid("执行模式授权无效或不属于当前轮次", root)


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


def new_task_id() -> str:
    """生成持久材料身份，不携带绝对路径或用户信息。"""
    return uuid.uuid4().hex


def ensure_unit_ids(data: dict, unit_names: list[str]) -> dict:
    """为当前单元集合分配持久ID；集合变化时只保留当前单元映射。"""
    data.setdefault("task_id", uuid.uuid4().hex)
    existing = data.get("unit_ids", {})
    data["unit_ids"] = {name: existing.get(name, uuid.uuid4().hex) for name in unit_names}
    return {"task_id": data["task_id"], "unit_ids": dict(data["unit_ids"])}


def find_unit_by_id(task_id: str, unit_id: str) -> tuple[Path, Path]:
    """只在当前工作区材料清单中解析已登记的task/unit ID。"""
    materials = workspace_root() / "校对"
    if materials.is_dir():
        for root in materials.iterdir():
            if not root.is_dir() or not (root / MANIFEST).is_file():
                continue
            ensure_inside(root)
            data = load(root)
            if data.get("task_id") != task_id:
                continue
            unit_name = next((name for name, identity in data.get("unit_ids", {}).items()
                              if identity == unit_id), None)
            if unit_name is None:
                raise NotFoundError("当前材料中不存在此unit_id", details={"task_id": task_id})
            unit = relative_path(root, data["paths"]["paper"]) / unit_name
            if not unit.is_dir():
                raise NotFoundError("登记的单元目录不存在", details={"unit_id": unit_id})
            return root, unit
    raise NotFoundError("当前工作区中不存在此task_id", details={"task_id": task_id})


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


def set_execution_policy(root: Path, mode: str, origin: str = "user") -> dict:
    """为当前轮次记录一次自动/交互执行授权和固定恢复预算。"""
    if mode not in {"automatic", "interactive"}:
        raise BusinessError("执行模式必须为 automatic 或 interactive", code="invalid-execution-mode")
    if origin not in {"user", "confirmed"}:
        raise BusinessError("执行模式来源必须为 user 或 confirmed", code="invalid-execution-origin")
    budgets = {
        "call_correction": 2,
        "calc_representation": 2,
        "report_repair": 3,
        "targeted_review": 2,
        "technical_redispatch": 1,
        "image_schema_fix": 2,
    }
    with locked(root):
        data = load(root)
        run = data["runs"][-1]
        existing = run.get("execution_policy")
        if existing is not None:
            if existing["mode"] == mode and existing["origin"] == origin:
                return existing
            raise BusinessError("本轮执行模式已确认；如需改变策略，请显式开启新轮次", code="execution-policy-locked")
        policy = {"mode": mode, "origin": origin, "confirmed_at": now(),
                  "budgets": budgets, "run_id": run["run_id"]}
        run["execution_policy"] = policy
        run["actions"].append({"command": "execution-policy", "at": policy["confirmed_at"],
                               "mode": mode, "origin": origin})
        write(root, data)
        return policy


def record_recovery_attempt(task_id: str, unit_id: str, category: str, fingerprint: str) -> dict:
    """在当前轮次消费一个分类预算，并按失败指纹留痕。"""
    allowed_categories = {"call_correction", "calc_representation", "report_repair",
                          "targeted_review", "technical_redispatch", "image_schema_fix"}
    if (category not in allowed_categories or not isinstance(fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)):
        raise BusinessError("恢复类别或SHA-256失败指纹无效", code="recovery-invalid")
    root, _ = find_unit_by_id(task_id, unit_id)
    with locked(root):
        data = load(root)
        run = data["runs"][-1]
        policy = run.get("execution_policy")
        if policy is None:
            raise BusinessError("当前轮次尚未确认执行模式", code="execution-policy-required")
        if run["run_id"] != data["current_run_id"]:
            raise BusinessError("恢复预算只能记入当前轮次", code="run-changed")
        budget = policy["budgets"][category]
        unit_state = run.setdefault("recovery", {}).setdefault(unit_id, {})
        state = unit_state.setdefault(category, {"used": 0, "fingerprints": {}})
        if state["used"] >= budget:
            result = {"allowed": False, "retryable": False, "category": category,
                      "used": state["used"], "budget": budget, "remaining": 0,
                      "fingerprint_attempts": state["fingerprints"].get(fingerprint, 0)}
        else:
            state["used"] += 1
            state["fingerprints"][fingerprint] = state["fingerprints"].get(fingerprint, 0) + 1
            result = {"allowed": True, "retryable": True, "category": category,
                      "used": state["used"], "budget": budget, "remaining": budget - state["used"],
                      "fingerprint_attempts": state["fingerprints"][fingerprint]}
        run.setdefault("recovery_events", []).append({
            "at": now(), "unit_id": unit_id, "category": category,
            "fingerprint": fingerprint, "allowed": result["allowed"],
            "used": result["used"], "budget": budget,
        })
        write(root, data)
        return result


def record_unit_event(task_id: str, unit_id: str, *, phase: str, attempt_id: str,
                      agent_id: str | None = None, cancel_initiator: str | None = None,
                      cancel_reason: str | None = None) -> dict:
    """记录可恢复阶段事件与明确来源的取消，不从错误文本猜测。"""
    phases = {"prepared", "read", "images", "calculated", "proposed", "self_checked",
              "verified", "registered", "parent_reviewed", "deliverable"}
    if phase not in phases or not isinstance(attempt_id, str) or not attempt_id:
        raise BusinessError("阶段或attempt_id无效", code="event-invalid")
    if (cancel_initiator is None) != (cancel_reason is None):
        raise BusinessError("取消发起者与原因必须同时提供", code="cancel-invalid")
    if cancel_initiator is not None:
        allowed = {"user": {"user_cancel"},
                   "parent": {"technical_timeout", "superseded"},
                   "host": {"technical_timeout", "superseded"}}
        if cancel_initiator not in allowed or cancel_reason not in allowed[cancel_initiator]:
            raise BusinessError("取消来源与原因不匹配", code="cancel-invalid")
    root, _ = find_unit_by_id(task_id, unit_id)
    with locked(root):
        data = load(root)
        run = data["runs"][-1]
        event = {"at": now(), "unit_id": unit_id, "phase": phase,
                 "attempt_id": attempt_id, "agent_id": agent_id}
        run.setdefault("unit_events", {}).setdefault(unit_id, []).append(event)
        run.setdefault("unit_state", {})[unit_id] = {"phase": phase, "attempt_id": attempt_id,
                                                     "agent_id": agent_id, "last_event_at": event["at"]}
        if cancel_initiator is not None:
            run.setdefault("cancellations", []).append({
                **event, "initiator": cancel_initiator, "reason": cancel_reason,
            })
        write(root, data)
        return event


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
                                     "missing_units": sorted(expected - actual), "scannable": scannable,
                                     "hint": "如需变更单元集，请用 split / slice --replace-units："
                                             "陈旧单元会归档到单元根目录的 .superseded/<run_id>/，只移动不删除"})
    return paper


def registered(root: Path, data: dict, unit: Path) -> bool:
    report = report_path(unit)
    if not report.is_file() or unit_inputs(root, unit) != data["unit_inputs"].get(unit.name):
        return False
    # R-D06：_校对数据.json 是交付的一部分。删掉或改动它都不能再算「本轮完成」，
    # 否则下游（build-report / build-docx）会消费一份与报告不再对应的结构化结果。
    data_file = data_path(unit)
    if not data_file.is_file():
        return False
    digest = sha256(report)
    data_digest = sha256(data_file)
    for record in data["unit_records"]:
        if (record["unit"] != unit.name or record["run_id"] != data["current_run_id"]
                or record["report_sha256"] != digest
                or record["inputs"] != data["unit_inputs"][unit.name]):
            continue
        # 升级前写入的旧记录没有该字段：退化为「存在性」；新记录要求逐字节一致
        recorded = record.get("data_sha256")
        if recorded is None or recorded == data_digest:
            return True
    return False


def register_locked(root: Path, unit: Path, text: str, expected_run_id: str) -> None:
    """调用方持有材料锁时登记；不重新获取目录锁。"""
    data = load(root)
    if data["current_run_id"] != expected_run_id:
        raise BusinessError("交付登记期间轮次已改变，请重新校对当前轮次", code="run-changed")
    paper = check_units(root, data)
    if unit.parent != paper or unit_inputs(root, unit) != data["unit_inputs"].get(unit.name):
        raise BusinessError("单元输入已改变，需重新拆分后交付", code="unit-input-mismatch")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if sha256(report_path(unit)) != digest:
        raise BusinessError("登记前报告已改变，请重新校验", code="report-changed")
    data_file = data_path(unit)
    if not data_file.is_file():
        raise BusinessError("登记前缺少 _校对数据.json，请重新运行 parse-report",
                            code="data-missing")
    data_digest = sha256(data_file)
    data["unit_records"] = [r for r in data["unit_records"]
                            if not (r["unit"] == unit.name and r["run_id"] == data["current_run_id"])]
    data["unit_records"].append({"unit": unit.name, "run_id": data["current_run_id"],
                                 "report_sha256": digest, "data_sha256": data_digest,
                                 "recorded_at": now(), "inputs": data["unit_inputs"][unit.name]})
    from .verify import verify_unit
    complete = all(is_skip_unit(paper / name)
                   or (registered(root, data, paper / name) and verify_unit(paper / name).ok)
                   for name in data["unit_set"])
    data["runs"][-1]["status"] = "completed" if complete else "in_progress"
    write(root, data)


def register(root: Path, unit: Path, text: str, expected_run_id: str) -> None:
    with locked(root):
        register_locked(root, unit, text, expected_run_id)


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

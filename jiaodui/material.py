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

from .error_classification import RECOVERY_CATEGORIES, classify_error
from .execution_policy import (attempt_decision, charge, is_current_policy,
                               is_readable_policy, migrate_legacy_spent, new_policy,
                               validate_attempt)
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
    reviews = data.get("unit_reviews", [])
    if not isinstance(reviews, list):
        _invalid("父复核记录必须为数组", root)
    for review in reviews:
        if (not isinstance(review, dict)
                or not isinstance(review.get("unit_id"), str)
                or not re.fullmatch(r"[0-9a-f]{32}", review["unit_id"])
                or review.get("run_id") not in ids
                or review.get("decision") not in {"accepted", "needs_revision"}
                or not isinstance(review.get("reviewer_id"), str)
                or not isinstance(review.get("recorded_at"), str)
                or not isinstance(review.get("inputs"), dict)
                or not isinstance(review.get("report_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", review["report_sha256"])
                or not isinstance(review.get("proposal_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", review["proposal_sha256"])
                or not isinstance(review.get("self_check_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", review["self_check_sha256"])):
            _invalid("父复核记录无效", root)
        input_record(review["inputs"])
    return data


def _validate_execution_policy(policy: dict, run_id: str, root: Path) -> None:
    """读盘门：只判「能否安全读入」，不判授权。

    旧聚合形态（main 时期）必须可读——否则升级时连清单都打不开；它当然不授权本轮
    工作，授权由 `require_current_policy` 判定。
    """
    if not is_readable_policy(policy):
        _invalid("执行模式授权无效或不属于当前轮次", root)


def require_current_policy(run: dict, data: dict) -> dict:
    """需要授权才能干活的入口共用：无策略、旧策略、非本轮策略一律拒绝。"""
    policy = run.get("execution_policy")
    if not is_current_policy(policy, run.get("run_id")):
        raise BusinessError("当前轮次尚未确认执行模式", code="execution-policy-required")
    return policy


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


TERMINAL_PHASES: frozenset[str] = frozenset({"registered", "parent_reviewed", "deliverable"})
"""到达这些阶段即为终态：不再是在途单元，也不会被判超时。"""


def _material_by_task(task_id: str) -> Path:
    """只读解析task_id对应的材料目录，找不到就报 not_found。"""
    materials = workspace_root() / "校对"
    if materials.is_dir():
        for root in sorted(materials.iterdir()):
            if not root.is_dir() or not (root / MANIFEST).is_file():
                continue
            ensure_inside(root)
            if load(root).get("task_id") == task_id:
                return root
    raise NotFoundError("当前工作区中不存在此task_id", details={"task_id": task_id})


def unit_progress(task_id: str, *, unit_id: str | None = None,
                  stale_after_seconds: int = 900) -> dict:
    """只读汇总当前轮次的单元心跳：阶段、attempt、最后事件时间与在途/超时判定。

    父代理据此判超时，不再靠「沉默多久没消息」猜崩溃；本函数不取锁、不写盘。
    - `in_flight`：有事件、最后阶段不是终态、且未被取消；
    - `stale`：在途且最后事件距今超过 `stale_after_seconds`；
    - `cancelled`：最后一次显式取消的发起者与原因（parent 技术取消不得记作 user）。
    """
    if type(stale_after_seconds) is not int or stale_after_seconds < 0:
        raise BusinessError("stale_after_seconds 必须为非负整数", code="progress-invalid")
    root = _material_by_task(task_id)
    data = load(root)
    run = data["runs"][-1]
    state_map = run.get("unit_state", {}) or {}
    events_map = run.get("unit_events", {}) or {}
    cancellations = run.get("cancellations", []) or []
    identities = data.get("unit_ids", {}) or {}
    selected = [(name, identity) for name, identity in identities.items()
                if unit_id is None or identity == unit_id]
    if unit_id is not None and not selected:
        raise NotFoundError("当前材料中不存在此unit_id", details={"task_id": task_id})
    current = datetime.now(timezone.utc)
    units: list[dict] = []
    for name, identity in selected:
        state = state_map.get(identity) or {}
        last_event_at = state.get("last_event_at")
        cancel = next((item for item in reversed(cancellations)
                       if item.get("unit_id") == identity), None)
        in_flight = bool(state) and state.get("phase") not in TERMINAL_PHASES and cancel is None
        age: int | None = None
        if isinstance(last_event_at, str):
            try:
                age = max(0, int((current - datetime.fromisoformat(last_event_at)).total_seconds()))
            except ValueError:
                age = None
        units.append({
            "unit": name,
            "unit_id": identity,
            "phase": state.get("phase"),
            "attempt_id": state.get("attempt_id"),
            "agent_id": state.get("agent_id"),
            "last_event_at": last_event_at,
            "age_seconds": age,
            "event_count": len(events_map.get(identity, []) or []),
            "in_flight": in_flight,
            "stale": bool(in_flight and age is not None and age > stale_after_seconds),
            "cancelled": ({"initiator": cancel.get("initiator"), "reason": cancel.get("reason"),
                           "at": cancel.get("at")} if cancel else None),
        })
    return {"ok": True, "task_id": task_id, "run_id": run.get("run_id"),
            "material_dir": str(root), "stale_after_seconds": stale_after_seconds,
            "units": units}


def dispatch_plan(task_id: str, *, window: int = 8) -> dict:
    """按滑动窗口给出下一批可派发单元；只读，不派发、不占预算。

    - 在途单元占用窗口（`unit_progress` 的 `in_flight`），所以同一单元不会被重复派发；
    - 候选只取「未开始 / 已交付未过校验 / 本轮未完成」，已完成与跳过不再派；
    - 任一单元被显式取消（user / parent / host）即 `stop=True`：停止补位交人裁定，
      不为「凑满窗口」继续派发；父代理技术取消同样按停止处理，但不冒称用户取消。
    """
    if type(window) is not int or window < 1:
        raise BusinessError("window 必须为正整数", code="policy-invalid")
    from .status import CURRENT_PENDING, DELIVERED_UNVERIFIED, NOT_STARTED, scan_status

    root = _material_by_task(task_id)
    data = load(root)
    paper = relative_path(root, data["paths"]["paper"])
    progress = unit_progress(task_id)
    in_flight = [item["unit"] for item in progress["units"] if item["in_flight"]]
    cancelled = [{"unit": item["unit"], **(item["cancelled"] or {})}
                 for item in progress["units"] if item["cancelled"]]
    report = scan_status(paper)
    dispatchable = [item.unit for item in report.units
                    if item.state in {NOT_STARTED, DELIVERED_UNVERIFIED, CURRENT_PENDING}
                    and item.unit not in in_flight]
    free = max(0, window - len(in_flight))
    stopped = bool(cancelled)
    return {"ok": True, "task_id": task_id, "run_id": progress["run_id"],
            "window": window, "in_flight": in_flight, "free_slots": free,
            "dispatch": [] if stopped else dispatchable[:free],
            "waiting": dispatchable if stopped else dispatchable[free:],
            "stop": stopped, "cancelled": cancelled,
            "states": {item.unit: item.state for item in report.units}}


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
    with locked(root):
        data = load(root)
        run = data["runs"][-1]
        existing = run.get("execution_policy")
        if existing is not None and is_current_policy(existing, run["run_id"]):
            if existing["mode"] == mode and existing["origin"] == origin:
                return existing
            raise BusinessError("本轮执行模式已确认；如需改变策略，请显式开启新轮次", code="execution-policy-locked")
        # 无策略、旧聚合策略或非本轮策略：重授权，并把旧聚合计数按单元保守迁移，
        # **不重置已花额度**（旧计数无法归因到单元，故每个单元同样迁移、取 min）。
        migrated = migrate_legacy_spent(existing) if isinstance(existing, dict) else {}
        if migrated:
            ledger = run.setdefault("recovery", {})
            for identity in (data.get("unit_ids") or {}).values():
                state = ledger.setdefault(identity, {})
                for category, used in migrated.items():
                    state.setdefault(category, {"used": used, "fingerprints": {}})
        policy = new_policy(mode, origin, now(), run["run_id"])
        run["execution_policy"] = policy
        action = {"command": "execution-policy", "at": policy["confirmed_at"],
                  "mode": mode, "origin": origin}
        if migrated:
            action["migrated_legacy_spent"] = sorted(migrated)
        run["actions"].append(action)
        write(root, data)
        return policy


def record_recovery_attempt(task_id: str, unit_id: str, category: str | None, fingerprint: str,
                            *, attempt_id: str, error_code: str | None = None,
                            expected_run_id: str | None = None) -> dict:
    """在当前轮次消费一个分类预算，并按失败指纹留痕。

    类别由错误码确定性决定（PLAN-rework-continuation P5 / `error_classification`）：
    - 给了 `error_code`：类别取映射结果；同时给了 `category` 时必须与映射一致；
    - 只给 `category`：仅允许父代理判断类的 `targeted_review`，其余必须给错误码；
    - 未分类码、用户取消、权限拒绝一律拒绝，且不消耗任何预算。

    `attempt_id` 是幂等键（UNIFY-PLAN B3，采纳 main 的 `attempt_id` 语义）：
    同一 attempt 重放不再扣费并返回原结果（`idempotent=true`）；同一 attempt 换了指纹
    或换了类别 → `attempt-id-conflict`。指纹只标识「同一失败」，不承担幂等。
    `expected_run_id` 是 CAS 防护：与当前轮次不一致即 `run-changed`。
    """
    attempt_id, fingerprint = validate_attempt(attempt_id, fingerprint)
    if category is not None and category not in RECOVERY_CATEGORIES:
        raise BusinessError(f"未知恢复类别：{category!r}", code="recovery-invalid")
    if error_code is None:
        if category != "targeted_review":
            raise BusinessError(
                "错误驱动的恢复必须给出 --error-code，不能自选类别；"
                "只有父代理判断类的 targeted_review 可以只给类别",
                code="recovery-error-code-required")
    else:
        classified = classify_error(error_code)
        if not classified["recoverable"]:
            hint = classified.get("suggestion") or []
            raise BusinessError(
                f"错误码 {error_code!r} 不可用于恢复：{classified['reason']}"
                + (f"；相近的已知码：{'、'.join(hint)}" if hint else ""),
                code="recovery-forbidden" if classified["forbidden"] else "unclassified-error-code")
        if category is not None and category != classified["category"]:
            raise BusinessError(
                f"类别与错误码不一致：{error_code!r} 属于 {classified['category']}，"
                f"不能记为 {category}",
                code="recovery-category-mismatch")
        category = classified["category"]
    root, _ = find_unit_by_id(task_id, unit_id)
    with locked(root):
        data = load(root)
        run = data["runs"][-1]
        require_current_policy(run, data)
        if run["run_id"] != data["current_run_id"]:
            raise BusinessError("恢复预算只能记入当前轮次", code="run-changed")
        if expected_run_id is not None and expected_run_id != run["run_id"]:
            raise BusinessError("恢复只能记入调用方预期的轮次", code="run-changed",
                                details={"expected_run_id": expected_run_id,
                                         "run_id": run["run_id"]})
        attempts = run.setdefault("recovery_attempts", {}).setdefault(unit_id, {})
        decision = attempt_decision(attempts.get(attempt_id), attempt_id=attempt_id,
                                    fingerprint=fingerprint, category=category)
        event = {"at": now(), "unit_id": unit_id, "category": category,
                 "error_code": error_code, "attempt_id": attempt_id,
                 "fingerprint": fingerprint}
        if decision["replay"]:
            # 真·无操作：不追加事件、不写盘（采纳 main 的语义）。否则被反复重试的同
            # 一 attempt 会让清单无界增长；审计需求由 attempt 索引与 idempotent=true 满足。
            return {**(decision["result"] or {}), "idempotent": True}
        unit_state = run.setdefault("recovery", {}).setdefault(unit_id, {})
        result = charge(unit_state, category, fingerprint)
        attempts[attempt_id] = {"fingerprint": fingerprint, "category": category,
                                "at": event["at"], "result": result}
        event.update({"charged": result["charged"],
                      "blocked_category": result.get("blocked_category"),
                      "allowed": result["allowed"], "used": result["used"],
                      "budget": result["budget"]})
        run.setdefault("recovery_events", []).append(event)
        write(root, data)
        return result


def record_unit_event(task_id: str, unit_id: str, *, phase: str, attempt_id: str,
                      agent_id: str | None = None, cancel_initiator: str | None = None,
                      cancel_reason: str | None = None,
                      expected_run_id: str | None = None) -> dict:
    """记录可恢复阶段事件与明确来源的取消，不从错误文本猜测。

    `expected_run_id` 是 CAS 防护（采纳 main）：与当前轮次不一致即 `run-changed`，
    避免迟到的阶段事件被写进新轮次。
    """
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
        if expected_run_id is not None and expected_run_id != run["run_id"]:
            raise BusinessError("阶段事件只能记入调用方预期的轮次", code="run-changed",
                                details={"expected_run_id": expected_run_id,
                                         "run_id": run["run_id"]})
        # 采纳 main：没有当前执行授权就不该留下工作痕迹（顺序同 main，先判轮次再判授权）
        require_current_policy(run, data)
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


def record_calc_call(task_id: str, unit_id: str, operation: str, params: dict, result: dict) -> str:
    """记录与当前单元输入绑定的确定性计算结果，返回供建议引用的call_id。"""
    if not isinstance(operation, str) or not operation or not isinstance(params, dict):
        raise BusinessError("calc调用信息无效", code="calc-evidence-invalid")
    root, unit = find_unit_by_id(task_id, unit_id)
    with locked(root):
        data = load(root)
        run = data["runs"][-1]
        require_current_policy(run, data)
        inputs = unit_inputs(root, unit)
        if inputs != data["unit_inputs"].get(unit.name):
            raise BusinessError("calc调用时单元输入已改变", code="unit-input-mismatch")
        call_id = uuid.uuid4().hex
        entry = {
            "call_id": call_id,
            "task_id": task_id,
            "unit_id": unit_id,
            "run_id": run["run_id"],
            "source_sha256": inputs["source_sha256"],
            "input_digest": hashlib.sha256(
                json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "operation": operation,
            "params": params,
            "success": bool(result.get("success")),
            "result": {key: value for key, value in result.items() if key != "code"},
            "recorded_at": now(),
        }
        run.setdefault("calc_calls", []).append(entry)
        write(root, data)
        return call_id


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
    previous = [record for record in data["unit_records"]
                if record["unit"] == unit.name and record["run_id"] == expected_run_id]
    data["runs"][-1]["actions"].append({
        "command": "register-unit", "at": now(), "unit": unit.name,
        "previous_records": previous, "report_sha256": digest, "data_sha256": data_digest,
    })
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

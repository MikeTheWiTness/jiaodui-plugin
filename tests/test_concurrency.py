"""M5 调度闭环：并发登记原子性（PLAN-rework-continuation P5 第 4 项）。

8 个单元同时登记时，材料清单里的条目不得丢失或互相覆盖。这里用线程与独立进程
两条路径压 `material.locked`：线程验证同进程互斥，进程验证真实场景（8 个子 agent
各自一条 CLI 进程）；另验证持锁进程意外退出后锁可恢复。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from jiaodui import material  # noqa: E402
from jiaodui.errors import BusinessError, ExitCode  # noqa: E402
from jiaodui.unit_delivery import commit_unit_submission, read_unit_snapshot  # noqa: E402
from jiaodui.workflow import convert_material, split_material  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UNITS = 8


def test_material_lock_file_persists_and_can_be_reacquired(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    root = workspace / "校对" / "锁测试"
    root.mkdir(parents=True)
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    lock_file = root / ".jiaodui.lock"

    with pytest.raises(RuntimeError):
        with material.locked(root):
            assert lock_file.is_file()
            raise RuntimeError("验证异常退出清理")

    assert lock_file.is_file(), "锁文件必须保留，避免不同进程锁住不同文件对象"
    with material.locked(root):
        assert lock_file.is_file()


def test_material_lock_wait_has_a_bounded_timeout(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    root = workspace / "校对" / "锁超时测试"
    root.mkdir(parents=True)
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    monkeypatch.setattr(material, "MATERIAL_LOCK_TIMEOUT_SECONDS", 0.05)

    def acquire_again():
        with material.locked(root):
            return True

    with material.locked(root):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(acquire_again)
            with pytest.raises(BusinessError) as caught:
                future.result(timeout=1)

    assert caught.value.code == "lock-timeout"
    assert caught.value.exit_code == ExitCode.ENV


def test_material_lock_is_released_when_process_is_terminated(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    root = workspace / "校对" / "锁进程测试"
    root.mkdir(parents=True)
    ready = tmp_path / "lock-ready"
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    monkeypatch.setattr(material, "MATERIAL_LOCK_TIMEOUT_SECONDS", 1.0, raising=False)
    script = (
        "from pathlib import Path\n"
        "import sys, time\n"
        "from jiaodui import material\n"
        "material.MATERIAL_LOCK_TIMEOUT_SECONDS = 1.0\n"
        "root, ready = map(Path, sys.argv[1:])\n"
        "with material.locked(root):\n"
        "    ready.write_text('ready', encoding='ascii')\n"
        "    time.sleep(30)\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(root), str(ready)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8")
    deadline = time.monotonic() + 10
    try:
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.is_file(), process.stderr.read() if process.poll() is not None else "子进程未取得锁"
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)

    with material.locked(root):
        assert (root / ".jiaodui.lock").is_file()


def _eight_units(tmp_path, monkeypatch):
    """拆出 1 个单元后补齐到 8 个，再用 adopt-units 让清单正式接纳它们。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("第一节\n正文。\n", encoding="utf-8")
    converted = convert_material(source, material_name="并发测试", mode="lecture")
    split = split_material(converted.raw_md, subject="高中物理", mode="lecture", strategy="none")
    template = Path(split.unit_dirs[0])
    paper = template.parent
    for index in range(2, UNITS + 1):
        target = paper / f"单元{index}"
        target.mkdir()
        (target / f"单元{index}.md").write_text(
            (template / "单元1.md").read_text(encoding="utf-8"), encoding="utf-8")
    split_material(converted.raw_md, subject="高中物理", mode="lecture", adopt_units=True)
    root = workspace / "校对" / "并发测试"
    material.set_execution_policy(root, "automatic")
    data = material.load(root)
    assert len(data["unit_set"]) == UNITS
    return root, data


def _no_issue_proposal(data, unit_id, source_text):
    return {
        "schema_version": 2,
        "task_id": data["task_id"],
        "unit_id": unit_id,
        "run_id": data["current_run_id"],
        "source_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
        "body_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
        "proposal_revision": 1,
        "summary": "无问题",
        "corrections": [],
        "evidence": {
            "assumptions": [{"id": "e1", "text": "已逐字核对。", "source_locations": []}],
            "symbols": [],
            "images": {"status": "not_applicable", "reason": "合成材料无图"},
            "calculations": {"status": "not_applicable", "reason": "无数值或公式核验"},
        },
        "self_check": {"status": "passed", "checks": ["no_issue_review"], "unresolved": []},
    }


def test_concurrent_unit_events_from_threads_keep_every_entry(tmp_path, monkeypatch):
    root, data = _eight_units(tmp_path, monkeypatch)
    task_id, ids = data["task_id"], data["unit_ids"]

    def hammer(item):
        name, unit_id = item
        for index in range(5):
            material.record_unit_event(task_id, unit_id, phase="read",
                                       attempt_id=f"a{index}", agent_id=f"ag-{name}")

    with ThreadPoolExecutor(max_workers=UNITS) as pool:
        list(pool.map(hammer, list(ids.items())))

    run = material.load(root)["runs"][-1]
    for name, unit_id in ids.items():
        assert len(run["unit_events"][unit_id]) == 5, name
        assert run["unit_state"][unit_id]["phase"] == "read"
    assert sum(len(events) for events in run["unit_events"].values()) == UNITS * 5


def test_concurrent_unit_events_from_processes_keep_every_entry(tmp_path, monkeypatch):
    root, data = _eight_units(tmp_path, monkeypatch)
    task_id, ids = data["task_id"], data["unit_ids"]
    env = {**os.environ, "JIAODUI_WORK_ROOT": str(root.parent.parent)}

    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "jiaodui", "--json", "unit-event",
             "--task-id", task_id, "--unit-id", unit_id,
             "--phase", "read", "--attempt-id", f"p-{name}"],
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for name, unit_id in ids.items()
    ]
    for process in processes:
        _, stderr = process.communicate(timeout=60)
        assert process.returncode == 0, stderr

    run = material.load(root)["runs"][-1]
    for name, unit_id in ids.items():
        events = run["unit_events"][unit_id]
        assert len(events) == 1, name
        assert events[0]["attempt_id"] == f"p-{name}"
    assert run.get("recovery_events", []) == []


def test_concurrent_recovery_attempts_stop_at_budget(tmp_path, monkeypatch):
    root, data = _eight_units(tmp_path, monkeypatch)
    task_id = data["task_id"]
    unit_id = list(data["unit_ids"].values())[0]

    def attempt(index):
        return material.record_recovery_attempt(
            task_id, unit_id, None,
            hashlib.sha256(f"fp-{index}".encode()).hexdigest(),
            attempt_id=f"thread-{index}", error_code="usage")

    with ThreadPoolExecutor(max_workers=UNITS) as pool:
        results = list(pool.map(attempt, range(UNITS)))

    allowed = [item for item in results if item["allowed"]]
    assert len(allowed) == 2, "call_correction 预算为 2，超出的并发请求必须被拒"
    assert all(not item["retryable"] for item in results if not item["allowed"])
    state = material.load(root)["runs"][-1]["recovery"][unit_id]["call_correction"]
    assert state["used"] == 2
    assert sum(state["fingerprints"].values()) == 2


def test_concurrent_submissions_register_every_unit(tmp_path, monkeypatch):
    root, data = _eight_units(tmp_path, monkeypatch)
    task_id, ids = data["task_id"], data["unit_ids"]

    def submit(item):
        name, unit_id = item
        snapshot = read_unit_snapshot(task_id, unit_id)
        source = (root / data["paths"]["paper"] / name / f"{name}.md").read_text(encoding="utf-8")
        proposal = _no_issue_proposal(data, unit_id, source)
        return commit_unit_submission(task_id, unit_id, proposal, snapshot["snapshot_sha256"])

    with ThreadPoolExecutor(max_workers=UNITS) as pool:
        results = list(pool.map(submit, list(ids.items())))

    assert all(item["ok"] and item["registered"] for item in results)
    records = material.load(root)["unit_records"]
    assert {record["unit"] for record in records} == set(data["unit_set"])
    assert len(records) == UNITS

"""M5 调度闭环：并发登记原子性（PLAN-rework-continuation P5 第 4 项）。

8 个单元同时登记时，材料清单里的条目不得丢失或互相覆盖。锁在
`material.locked`（`fcntl.flock` 锁材料目录 inode，原子替换清单不会换锁对象），
这里用线程与独立进程两条路径压它：线程验证同进程内的互斥，进程验证真实场景
（8 个子 agent 各自一条 CLI 进程）。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

fcntl = pytest.importorskip("fcntl", reason="材料锁依赖 POSIX flock")

from jiaodui import material  # noqa: E402
from jiaodui.unit_delivery import commit_unit_submission, read_unit_snapshot  # noqa: E402
from jiaodui.workflow import convert_material, split_material  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UNITS = 8


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
            hashlib.sha256(f"fp-{index}".encode()).hexdigest(), error_code="usage")

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

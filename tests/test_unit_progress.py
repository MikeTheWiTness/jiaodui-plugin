"""M5 调度闭环：`unit-progress` 心跳与超时判据（PLAN-rework-continuation P5 第 2 项）。

父代理据此判超时，不再靠「沉默多久没消息」猜崩溃：只看单元是否在途、最后一次
事件是什么、距今多久，以及是否已被显式取消。全程只读，不改材料记录。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from jiaodui import material
from jiaodui.errors import BusinessError, NotFoundError
from jiaodui.workflow import convert_material, split_material


def _unit(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("JIAODUI_WORK_ROOT", str(workspace))
    source = tmp_path / "lesson.md"
    source.write_text("第一节\n正文。\n", encoding="utf-8")
    converted = convert_material(source, material_name="进度测试", mode="lecture")
    split = split_material(converted.raw_md, subject="高中物理", mode="lecture", strategy="none")
    root = workspace / "校对" / "进度测试"
    material.set_execution_policy(root, "automatic")
    data = material.load(root)
    return root, data["task_id"], data["unit_ids"][data["unit_set"][0]]


def _age_last_event(root, unit_id, seconds):
    """把最后一次事件的时间改成过去，用于构造「沉默过久」的现场。"""
    from datetime import datetime, timedelta, timezone

    with material.locked(root):
        data = material.load(root)
        run = data["runs"][-1]
        old = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
        for event in run["unit_events"][unit_id]:
            event["at"] = old
        run["unit_state"][unit_id]["last_event_at"] = old
        material.write(root, data)


def test_no_events_means_not_in_flight(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    progress = material.unit_progress(task_id)
    entry = next(item for item in progress["units"] if item["unit_id"] == unit_id)
    assert entry["phase"] is None
    assert entry["in_flight"] is False
    assert entry["stale"] is False
    assert entry["event_count"] == 0


def test_in_flight_unit_exposes_phase_attempt_and_last_event(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1", agent_id="ag1")
    progress = material.unit_progress(task_id, unit_id=unit_id)
    entry = progress["units"][0]
    assert entry["phase"] == "read"
    assert entry["attempt_id"] == "a1"
    assert entry["agent_id"] == "ag1"
    assert entry["last_event_at"]
    assert entry["in_flight"] is True
    assert entry["stale"] is False


def test_terminal_phase_is_not_in_flight_even_when_old(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    material.record_unit_event(task_id, unit_id, phase="registered", attempt_id="a1")
    _age_last_event(root, unit_id, 10_000)
    entry = material.unit_progress(task_id, unit_id=unit_id)["units"][0]
    assert entry["in_flight"] is False
    assert entry["stale"] is False, "已完成的单元不该被判为超时"


def test_silent_in_flight_unit_becomes_stale(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1")
    _age_last_event(root, unit_id, 10_000)
    fresh = material.unit_progress(task_id, unit_id=unit_id, stale_after_seconds=60)["units"][0]
    assert fresh["in_flight"] is True and fresh["stale"] is True
    relaxed = material.unit_progress(task_id, unit_id=unit_id, stale_after_seconds=999_999)["units"][0]
    assert relaxed["stale"] is False


def test_cancelled_unit_is_not_in_flight_and_reports_origin(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1")
    material.record_unit_cancel(task_id, unit_id, attempt_id="a1",
                                initiator="parent", reason="technical_timeout")
    _age_last_event(root, unit_id, 10_000)
    entry = material.unit_progress(task_id, unit_id=unit_id, stale_after_seconds=60)["units"][0]
    assert entry["in_flight"] is False, "已取消的单元不得再被判为在途或超时"
    assert entry["cancelled"]["initiator"] == "parent"
    assert entry["cancelled"]["reason"] == "technical_timeout"


def test_unit_event_has_no_cancellation_parameters():
    """取消不再挂在 unit-event 上：该工具只记阶段心跳。

    第 12 讲实测：取消作为两个没有说明的可选 enum 暴露时，单元子代理在正常的
    `prepared` 心跳里顺手填了 `user` + `user_cancel`，在 8 个单元上伪造出约 29 条
    「用户取消」；`dispatch-plan` 只要有取消记录就永久 `stop=true`，父代理只能靠
    `--rerun` 逃出，又引发 `run-changed` 连锁并让整轮无交付。
    """
    import inspect

    params = inspect.signature(material.record_unit_event).parameters
    assert "cancel_initiator" not in params
    assert "cancel_reason" not in params


def test_cancel_reports_actor_and_revoke_releases_dispatch_stop(tmp_path, monkeypatch):
    """技术性取消可撤销，但已停止的旧 attempt 仍保持终态并释放窗口。"""
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1", agent_id="worker")
    material.record_unit_cancel(task_id, unit_id, attempt_id="a1", agent_id="parent",
                                initiator="parent", reason="technical_timeout")
    stopped = material.dispatch_plan(task_id, window=8)
    assert stopped["stop"] is True
    assert stopped["dispatch"] == []
    assert stopped["cancelled"][0]["attempt_id"] == "a1"
    assert stopped["cancelled"][0]["agent_id"] == "parent"

    material.record_unit_cancel(task_id, unit_id, attempt_id="a1-revoke", agent_id="parent",
                                initiator="parent", reason="technical_timeout", revoke=True)
    released = material.dispatch_plan(task_id, window=8)
    assert released["stop"] is False
    assert released["dispatch"] == ["单元1"], "撤销后需重派，但不能复活已停止的旧 attempt"
    progress = material.unit_progress(task_id, unit_id=unit_id)["units"][0]
    assert progress["cancelled"] is None
    assert progress["phase"] == "cancelled"
    assert progress["in_flight"] is False
    with pytest.raises(BusinessError) as late:
        material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1", agent_id="worker")
    assert late.value.code == "attempt-terminated"
    assert material.unit_progress(task_id, unit_id=unit_id)["units"][0]["in_flight"] is False


def test_user_cancel_cannot_be_revoked_by_parent(tmp_path, monkeypatch):
    """用户取消是人的决定，父代理不得代撤销。"""
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    material.record_unit_cancel(task_id, unit_id, attempt_id="a1",
                                initiator="user", reason="user_cancel")
    with pytest.raises(BusinessError) as error:
        material.record_unit_cancel(task_id, unit_id, attempt_id="a1-revoke",
                                    initiator="parent", reason="technical_timeout", revoke=True)
    assert error.value.code == "cancel-invalid"
    assert material.dispatch_plan(task_id, window=8)["stop"] is True, "被拒后原取消必须仍然生效"


def test_user_cancel_survives_later_technical_cancel_and_revoke(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    material.record_unit_cancel(task_id, unit_id, attempt_id="user-1",
                                initiator="user", reason="user_cancel")
    material.record_unit_cancel(task_id, unit_id, attempt_id="timeout-1",
                                initiator="parent", reason="technical_timeout")
    material.record_unit_cancel(task_id, unit_id, attempt_id="revoke-1",
                                initiator="parent", reason="technical_timeout", revoke=True)

    plan = material.dispatch_plan(task_id, window=8)
    assert plan["stop"] is True
    assert plan["dispatch"] == []
    assert plan["cancelled"][0]["initiator"] == "user"
    assert plan["cancelled"][0]["reason"] == "user_cancel"
    assert len(material.load(root)["runs"][-1]["cancellations"]) == 3


def test_revoke_without_standing_cancel_is_rejected(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    with pytest.raises(BusinessError) as error:
        material.record_unit_cancel(task_id, unit_id, attempt_id="a1",
                                    initiator="parent", reason="superseded", revoke=True)
    assert error.value.code == "cancel-invalid"


def test_progress_is_read_only(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1")
    manifest = root / material.MANIFEST
    before = hashlib.sha256(manifest.read_bytes()).hexdigest()
    material.unit_progress(task_id, stale_after_seconds=60)
    material.unit_progress(task_id, unit_id=unit_id)
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == before


def test_unknown_task_or_unit_is_rejected(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    with pytest.raises(NotFoundError) as unknown_task:
        material.unit_progress("f" * 32)
    assert unknown_task.value.code == "not_found"
    with pytest.raises(NotFoundError) as unknown_unit:
        material.unit_progress(task_id, unit_id="f" * 32)
    assert unknown_unit.value.code == "not_found"


def test_unrelated_broken_manifest_does_not_block_queries(tmp_path, monkeypatch):
    """回归（P2）：无关材料的损坏清单不得阻断目标材料的只读查询。

    修复前 `_material_by_task` / `find_unit_by_id` 逐份 load，任何一份坏 JSON 都会
    让正常 task 的 unit-progress 报那个无关目录的 invalid-manifest。损坏材料仍要
    留痕：查不到的 task 会把不可读清单列进 details。
    """
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    broken = root.parent / "000无关"
    broken.mkdir()
    (broken / material.MANIFEST).write_text("{ 坏掉的 JSON", encoding="utf-8")

    assert material.unit_progress(task_id)["task_id"] == task_id
    assert material.find_unit_by_id(task_id, unit_id)[1].name == "单元1"
    assert material.dispatch_plan(task_id)["ok"] is True

    with pytest.raises(NotFoundError) as unknown_task:
        material.unit_progress("f" * 32)
    unreadable = unknown_task.value.details["unreadable_materials"]
    assert [item["material_dir"] for item in unreadable] == [str(broken)]
    assert unreadable[0]["code"] == "invalid-manifest"


# ---- 滑动窗口判据（P5 第 3 项中可由 core 判定的部分） ----

def test_dispatch_plan_fills_empty_slots_without_duplicating_in_flight(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    plan = material.dispatch_plan(task_id, window=1)
    assert plan["in_flight"] == []
    assert plan["dispatch"] == ["单元1"], "空窗口应补位"
    assert plan["stop"] is False

    material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1")
    busy = material.dispatch_plan(task_id, window=1)
    assert busy["in_flight"] == ["单元1"]
    assert busy["free_slots"] == 0
    assert busy["dispatch"] == [], "在途单元不得被重复派发"


def test_dispatch_plan_stops_after_explicit_cancellation(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1")
    material.record_unit_cancel(task_id, unit_id, attempt_id="a1",
                                initiator="parent", reason="technical_timeout")
    plan = material.dispatch_plan(task_id, window=8)
    assert plan["stop"] is True
    assert plan["dispatch"] == []
    assert plan["waiting"], "停止补位后候选应留在 waiting，不是消失"
    assert plan["cancelled"][0]["initiator"] == "parent"
    assert plan["cancelled"][0]["reason"] == "technical_timeout"


def test_dispatch_plan_rejects_bad_window_and_is_read_only(tmp_path, monkeypatch):
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    with pytest.raises(BusinessError) as error:
        material.dispatch_plan(task_id, window=0)
    assert error.value.code == "policy-invalid"
    manifest = root / material.MANIFEST
    before = hashlib.sha256(manifest.read_bytes()).hexdigest()
    material.dispatch_plan(task_id, window=8)
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == before


# ---- Phase 2 合并：采纳 main 的两条更优语义 ----

def test_build_report_payload_exposes_ok_independently_of_complete(tmp_path, monkeypatch):
    """`ok` = 诊断文件已生成；`complete` = 所有必需单元通过或显式跳过（两者独立）。

    main 的 `BuildReportResult.to_dict()` 有 `ok`，分支只有 CLI 补；契约（AGENTS）把
    `ok` 定义为对外字段，所以补进 dataclass，同时保留分支更严谨的 complete 规则
    （考虑 unreviewed；main 的 `not failed` 是粗近似）。
    """
    from jiaodui.report import build_report

    paper = tmp_path / "卷子"
    unit = paper / "第1题"
    unit.mkdir(parents=True)
    (unit / "第1题.md").write_text("设a为$O$点。", encoding="utf-8")
    (unit / "_校对报告.md").write_text("不合规报告", encoding="utf-8")

    result = build_report(paper, out_path=tmp_path / "out.md", legacy_layout=True)
    payload = result.to_dict()

    assert payload["ok"] is True, "诊断文件已生成"
    assert payload["complete"] is False, "单元未通过校验"


def test_unit_event_rejects_late_event_from_previous_run(tmp_path, monkeypatch):
    """迟到的阶段事件不得写进新轮次（采纳 main 的 expected_run_id CAS）。"""
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    manifest = material.load(root)
    stale_run = manifest["current_run_id"]

    with material.locked(root):
        data = material.load(root)
        material.new_run(data, data["params"], data["resources"])
        material.write(root, data)

    material.set_execution_policy(root, "automatic")
    with pytest.raises(BusinessError) as error:
        material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1",
                                   expected_run_id=stale_run)
    assert error.value.code == "run-changed"
    assert material.load(root)["runs"][-1].get("unit_events", {}) == {}, "迟到事件不得落盘"

    fresh = material.load(root)["current_run_id"]
    event = material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1",
                                       expected_run_id=fresh)
    assert event["phase"] == "read"


def test_unit_event_requires_execution_policy(tmp_path, monkeypatch):
    """没有执行授权就不该留下工作痕迹（采纳 main：unit-event 也要求当前策略）。"""
    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    with material.locked(root):
        data = material.load(root)
        data["runs"][-1].pop("execution_policy", None)
        material.write(root, data)
    before = (root / material.MANIFEST).read_bytes()

    with pytest.raises(BusinessError) as error:
        material.record_unit_event(task_id, unit_id, phase="read", attempt_id="a1")

    assert error.value.code == "execution-policy-required"
    assert (root / material.MANIFEST).read_bytes() == before, "未授权时不得落盘"


def test_cli_unit_event_accepts_and_forwards_expected_run_id(tmp_path, monkeypatch):
    """端到端：CLI 必须真的接受并传递 `--expected-run-id`。

    教训：Node 行为测试只验插件拼的 argv、Python 测试直接用 core API，两者都验不到
    「CLI 解析器是否接受这个参数」，导致一次漏改无声通过。这条用真子进程兜住。
    """
    import json
    import os
    import subprocess
    import sys

    root, task_id, unit_id = _unit(tmp_path, monkeypatch)
    fresh = material.load(root)["current_run_id"]

    def run(*extra):
        return subprocess.run(
            [sys.executable, "-m", "jiaodui", "unit-event", "--task-id", task_id,
             "--unit-id", unit_id, "--phase", "read", "--attempt-id", "cli-1",
             *extra, "--json"],
            capture_output=True, text=True, env=os.environ.copy(),
            cwd=str(Path(__file__).resolve().parents[1]))

    stale = run("--expected-run-id", "0" * 32)
    assert stale.returncode == 6, stale.stderr
    assert json.loads(stale.stdout or stale.stderr)["error"]["code"] == "run-changed"

    ok = run("--expected-run-id", fresh)
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["event"]["phase"] == "read"


def test_cli_unit_cancel_records_and_revokes_end_to_end(tmp_path, monkeypatch):
    """端到端：`unit-event` 不再接受取消参数，取消走独立的 `unit-cancel`。

    同一条教训：Node 行为测试只验插件拼的 argv、Python 测试直接用 core API，
    两者都验不到「CLI 解析器是否真的接受/拒绝这些参数」。这里用真子进程兜住。
    """
    import json
    import os
    import subprocess
    import sys

    root, task_id, unit_id = _unit(tmp_path, monkeypatch)

    def run(*argv):
        return subprocess.run(
            [sys.executable, "-m", "jiaodui", *argv, "--json"],
            capture_output=True, text=True, env=os.environ.copy(),
            cwd=str(Path(__file__).resolve().parents[1]))

    # 心跳不再携带取消：旧写法必须被解析器拒绝，而不是静默记成一次取消
    legacy = run("unit-event", "--task-id", task_id, "--unit-id", unit_id,
                 "--phase", "prepared", "--attempt-id", "cli-1",
                 "--cancel-initiator", "user", "--cancel-reason", "user_cancel")
    assert legacy.returncode == 2, legacy.stderr
    assert material.dispatch_plan(task_id, window=8)["stop"] is False, "旧写法不得伪造取消"

    bad = run("unit-cancel", "--task-id", task_id, "--unit-id", unit_id,
              "--attempt-id", "cli-1", "--initiator", "user", "--reason", "superseded")
    assert bad.returncode == 6, bad.stderr
    assert json.loads(bad.stdout or bad.stderr)["error"]["code"] == "cancel-invalid"

    recorded = run("unit-cancel", "--task-id", task_id, "--unit-id", unit_id,
                   "--attempt-id", "cli-1", "--initiator", "parent",
                   "--reason", "technical_timeout")
    assert recorded.returncode == 0, recorded.stderr
    assert json.loads(recorded.stdout)["cancellation"]["initiator"] == "parent"
    assert material.dispatch_plan(task_id, window=8)["stop"] is True

    revoked = run("unit-cancel", "--task-id", task_id, "--unit-id", unit_id,
                  "--attempt-id", "cli-2", "--initiator", "parent",
                  "--reason", "technical_timeout", "--revoke")
    assert revoked.returncode == 0, revoked.stderr
    assert json.loads(revoked.stdout)["cancellation"]["revoked"] is True
    assert material.dispatch_plan(task_id, window=8)["stop"] is False

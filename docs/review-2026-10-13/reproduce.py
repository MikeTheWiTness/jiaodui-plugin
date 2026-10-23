"""使用临时合成材料复现审查问题；不读取或改写真实校对材料。

R2 的迟到技术取消在当前代码中应被拒绝。脚本记录该预期拒绝后继续运行，
以免一个已修复项遮蔽 R1 / R3 的观测结果。
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import tempfile
from pathlib import Path

from jiaodui import material
from jiaodui.calc.operations import run_operation
from jiaodui.errors import BusinessError
from jiaodui.workflow import convert_material, split_material


def projected(result: dict) -> dict:
    """保留计算结果，避免在证据中重复生成代码。"""
    return {key: value for key, value in result.items() if key != "code"}


def main() -> None:
    results: dict = {}
    with tempfile.TemporaryDirectory(prefix="jiaodui-review-") as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        workspace.mkdir()
        old_workspace = os.environ.get("JIAODUI_WORK_ROOT")
        os.environ["JIAODUI_WORK_ROOT"] = str(workspace)
        try:
            # 只创建临时目录中的空标记，证明表达式可以跨出授权工作区写文件。
            marker = root / "sandbox-escape.txt"
            expression = (
                "sqrt.__globals__['__buil'+'tins__']['__im'+'port__']"
                "('path'+'lib').Path(" + repr(str(marker)) + ").touch()"
            )
            result = run_operation("evaluate", expression=expression)
            results["R1"] = {
                "operation": "evaluate", "expression": expression,
                "result": projected(result), "marker_exists": marker.exists(),
                "marker_inside_work_root": marker.is_relative_to(workspace),
                "expected": "拒绝非数学属性访问与导入，且不创建文件",
            }

            # A 被技术取消并撤销后，B 开始；A 的迟到超时取消应被拒绝，不得影响 B。
            source = root / "synthetic.md"
            source.write_text("合成材料正文。\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                converted = convert_material(source, material_name="审查临时材料", mode="lecture")
                split_material(converted.raw_md, subject="高中物理", strategy="none")
            scene = workspace / "校对" / "审查临时材料"
            material.set_execution_policy(scene, "automatic")
            data = material.load(scene)
            task_id = data["task_id"]
            unit_id = data["unit_ids"][data["unit_set"][0]]
            run_id = data["current_run_id"]
            material.record_unit_event(task_id, unit_id, phase="read", attempt_id="attempt-A",
                                       agent_id="agent-A", expected_run_id=run_id)
            material.record_unit_cancel(task_id, unit_id, attempt_id="attempt-A", initiator="parent",
                                        reason="technical_timeout", expected_run_id=run_id)
            material.record_unit_cancel(task_id, unit_id, attempt_id="revoke-A", initiator="parent",
                                        reason="technical_timeout", revoke=True, expected_run_id=run_id)
            material.record_unit_event(task_id, unit_id, phase="read", attempt_id="attempt-B",
                                       agent_id="agent-B", expected_run_id=run_id)
            before = material.unit_progress(task_id)["units"][0]
            try:
                late = material.record_unit_cancel(task_id, unit_id, attempt_id="attempt-A",
                                                   initiator="parent", reason="technical_timeout",
                                                   expected_run_id=run_id)
            except BusinessError as exc:
                late_cancel = {"rejected": True, **exc.to_dict()["error"]}
            else:
                late_cancel = {"rejected": False, "entry": late}
            results["R2"] = {
                "before": before, "late_cancel": late_cancel,
                "after": material.unit_progress(task_id)["units"][0],
                "terminated_attempts": material.load(scene)["runs"][-1]["terminated_attempts"],
                "dispatch_stop": material.dispatch_plan(task_id)["stop"],
                "expected": "旧 attempt-A 的迟到技术取消应被 attempt-terminated 拒绝，"
                            "attempt-B 保持在途且调度不停止",
            }

            # 期望值独立取自标准库 math.pi，不复用项目序列化逻辑。
            expected = math.pi * 1e-12
            result = run_operation("evaluate", expression="pi*1e-12")
            results["R3"] = {
                "expression": "pi*1e-12", "result": projected(result), "expected": expected,
                "relative_error": abs(result["result"] - expected) / expected,
            }
        finally:
            if old_workspace is None:
                os.environ.pop("JIAODUI_WORK_ROOT", None)
            else:
                os.environ["JIAODUI_WORK_ROOT"] = old_workspace
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

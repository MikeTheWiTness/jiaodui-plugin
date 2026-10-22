"""jiaodui 命令行入口：入口检查与确定性校对命令。

契约：所有命令支持 --json；失败向 stderr 输出一行结构化 JSON 并返回稳定退出码；
进度与诊断走 stderr，机器可读结果走 stdout。核心逻辑只有一份，CLI 只做参数解析。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .errors import (BusinessError, ContractError, ExitCode, JiaoduiError,
                     NotFoundError, UnsupportedError, UsageError, VerifyFailedError,
                     emit_error)
from .log import log, set_quiet


def _json_out(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _resolve_config_dir() -> Path:
    """配置解析委托确定性核心。"""
    from .workflow import resolve_config_dir
    return resolve_config_dir()


def _resolve_subject_config(subject: str) -> dict:
    from .workflow import subject_config
    return subject_config(subject)


# ---------------------------------------------------------------- commands

def cmd_inspect_source(args: argparse.Namespace) -> int:
    from .inspect_source import inspect_source
    payload = inspect_source(args.file, preview_chars=args.preview_chars)
    _json_out(payload)
    return ExitCode.OK


def cmd_inspect_images(args: argparse.Namespace) -> int:
    from .inspect_images import inspect_unit_images
    payload = inspect_unit_images(args.unit)
    _json_out(payload)
    if not payload["ok"]:
        raise VerifyFailedError(
            "图片引用清单未通过：存在缺图、无效引用或不支持的远程引用",
            details={"unit": str(args.unit), "errors": payload["errors"]},
        )
    return ExitCode.OK


def cmd_check_env(args: argparse.Namespace) -> int:
    from .checkenv import check_env

    report = check_env(expect_schema_version=args.expect_schema_version,
                       expect_bundle_version=args.expect_bundle_version,
                       expect_schema_file=args.expect_schema_file)
    if args.json:
        _json_out(report.to_dict())
    else:
        for item in report.items:
            mark = "✅" if item.ok else ("⚠️" if not item.required else "❌")
            log(f" {mark} {item.name}: {item.detail}")
        log(" 宿主侧必须另行实测（CLI 无法证明）：")
        for h in report.host_checks_required:
            log(f"   - {h}")
        print(json.dumps({"ok": report.ok}, ensure_ascii=False))
    if not report.ok:
        failed = [i.name for i in report.items if i.required and not i.ok]
        raise BusinessError(f"环境预检未通过：{failed}", code="env",
                            exit_code=ExitCode.ENV, details={"failed": failed})
    return ExitCode.OK


def cmd_convert(args: argparse.Namespace) -> int:
    from .workflow import convert_material
    result = convert_material(args.file, args.out_dir, args.base_name,
                              material_name=args.material_name, use_mathjax=args.mathjax,
                              legacy_layout=args.legacy_layout, mode=args.mode,
                              mode_origin=args.mode_origin, mode_reason=args.mode_reason,
                              import_engine=args.import_engine)
    payload = {"ok": True, "raw_md": result.raw_md, "images_dir": result.images_dir,
               "copied": result.copied, "missing": result.missing,
               "warnings": result.warnings, "source_kind": result.source_kind,
               "mode": result.mode, "engine": result.engine}
    if args.json:
        _json_out(payload)
    else:
        log(f" ✅ 转换完成（{result.source_kind}）：{result.raw_md}")
        print(json.dumps(payload, ensure_ascii=False))
    return ExitCode.OK


def cmd_import(args: argparse.Namespace) -> int:
    from .workflow import import_material
    payload = import_material(args.file, subject=args.subject, mode=args.mode,
                              material_name=args.material_name,
                              import_engine=args.import_engine,
                              rerun=args.rerun, replace_units=args.replace_units)
    if args.json:
        _json_out(payload)
    else:
        log(f" ✅ 导入完成（{payload['engine']}）：{payload['units']} 个单元"
            f"（题目 {payload['question_units']} / 知识 {payload['knowledge_units']}）")
        print(json.dumps(payload, ensure_ascii=False))
    return ExitCode.OK


def _split(args: argparse.Namespace) -> int:
    from .workflow import split_material
    result = split_material(args.raw_md, subject=args.subject, mode=args.mode,
                            out_root=args.out_root, base_name=args.base_name,
                            material_name=args.material_name, images_dir=args.images_dir,
                            clean=not args.no_clean, rerun=args.rerun,
                            adopt_units=args.adopt_units, replace_units=args.replace_units,
                            legacy_layout=args.legacy_layout,
                            mode_origin=args.mode_origin, mode_reason=args.mode_reason,
                            strategy=args.strategy)
    payload = {"ok": True, "units": result.units, "unit_dirs": result.unit_dirs,
               "copied": result.copied, "missing": result.missing, "warnings": result.warnings,
               "coverage": result.coverage}
    if result.unit_dirs:
        from .material import find_material, load
        root = find_material(result.unit_dirs[0])
        if root is not None:
            identity = load(root)
            payload["task_id"] = identity.get("task_id")
            payload["unit_ids"] = identity.get("unit_ids", {})
    if args.json:
        _json_out(payload)
    else:
        log(f" ✅ 拆分完成：{len(result.unit_dirs)} 个单元，图片 {result.copied} 张")
        print(json.dumps(payload, ensure_ascii=False))
    return ExitCode.OK


def cmd_slice(args: argparse.Namespace) -> int:
    from .workflow import slice_material
    result = slice_material(args.boundaries, raw=args.raw, subject=args.subject, mode=args.mode,
                            out_root=args.out_root, base_name=args.base_name, material_name=args.material_name,
                            clean=not args.no_clean, rerun=args.rerun,
                            replace_units=args.replace_units,
                            legacy_layout=args.legacy_layout, preview=args.preview,
                             scope=args.scope, scope_reason=args.scope_reason,
                            mode_origin=args.mode_origin, mode_reason=args.mode_reason)
    if args.preview:
        if args.json:
            _json_out(result)
        else:
            print(result["cleaned"])
        return ExitCode.OK
    payload = {"ok": True, "unit_dirs": result.unit_dirs, "units": result.units,
               "copied": result.copied, "missing": result.missing, "warnings": result.warnings,
               "coverage": result.coverage}
    if result.unit_dirs:
        from .material import find_material, load
        root = find_material(result.unit_dirs[0])
        if root is not None:
            identity = load(root)
            payload["task_id"] = identity.get("task_id")
            payload["unit_ids"] = identity.get("unit_ids", {})
    if args.json:
        _json_out(payload)
    else:
        log(f" ✅ 切片完成：{len(result.unit_dirs)} 个单元")
        print(json.dumps(payload, ensure_ascii=False))
    return ExitCode.OK


def cmd_precheck_split(args: argparse.Namespace) -> int:
    from .split import precheck_split

    result = precheck_split(args.dir)
    payload = result.__dict__ if hasattr(result, "__dict__") else result
    if args.json:
        _json_out(payload)
    else:
        counts = getattr(result, "unit_count", None)
        empty = getattr(result, "empty_units", [])
        overlong = getattr(result, "overlong_units", [])
        log(f" 单元数 {counts}；空单元 {len(empty)}；超长单元 {len(overlong)}")
        print(json.dumps(payload, ensure_ascii=False, default=str))
    return ExitCode.OK


def cmd_status(args: argparse.Namespace) -> int:
    from .status import scan_status

    result = scan_status(args.paper_dir)
    if args.json:
        _json_out(result.to_dict())
    else:
        for u in result.units:
            log(f" {u.state:<8} {u.unit}" + (f" — {u.reason}" if u.reason and u.state != "已完成" else ""))
        for warning in result.warnings:
            log(f" ⚠️ {warning}")
        print(json.dumps(result.counts(), ensure_ascii=False))
    return ExitCode.OK


def cmd_execution_policy(args: argparse.Namespace) -> int:
    from .material import set_execution_policy
    from .workdir import input_path

    root = input_path(args.material_dir)
    policy = set_execution_policy(root, args.mode, args.origin)
    payload = {"ok": True, "material_dir": str(root), "execution_policy": policy}
    if args.json:
        _json_out(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False))
    return ExitCode.OK


def cmd_unit_locate(args: argparse.Namespace) -> int:
    from .material import find_unit_by_id, sha256
    from .paths import find_source_md
    from .source_index import LocationError, query_locations

    root, unit = find_unit_by_id(args.task_id, args.unit_id)
    source = find_source_md(unit)
    if source is None or not source.is_file():
        raise NotFoundError("找不到登记单元的源文", details={"unit_id": args.unit_id})
    text = source.read_bytes().decode("utf-8")
    digest = sha256(source)
    try:
        locations = query_locations(text, digest, args.phrase)
    except LocationError as exc:
        raise BusinessError(str(exc), code=exc.code) from exc
    payload = {"ok": True, "task_id": args.task_id, "unit_id": args.unit_id,
               "source_sha256": digest, "body_sha256": digest, "index_version": 1,
               "material_dir": str(root), "unit": unit.name, "locations": locations}
    _json_out(payload)
    return ExitCode.OK


def cmd_unit_read(args: argparse.Namespace) -> int:
    from .unit_reader import read_unit_source

    _json_out(read_unit_source(args.task_id, args.unit_id,
                               start_line=args.start_line, max_lines=args.max_lines))
    return ExitCode.OK


def cmd_unit_snapshot(args: argparse.Namespace) -> int:
    from .unit_delivery import read_unit_snapshot

    _json_out({"ok": True, "snapshot": read_unit_snapshot(args.task_id, args.unit_id,
                                                         with_proposal=args.with_proposal)})
    return ExitCode.OK


def cmd_unit_submit(args: argparse.Namespace) -> int:
    from .unit_delivery import commit_unit_submission, preview_unit_submission

    try:
        if args.proposal_json_file is not None:
            proposal_text = Path(args.proposal_json_file).read_text(encoding="utf-8")
        else:
            proposal_text = args.proposal_json
        proposal = json.loads(proposal_text)
    except OSError as exc:
        raise NotFoundError(f"proposal-json文件不存在或不可读：{args.proposal_json_file}") from exc
    except json.JSONDecodeError as exc:
        raise BusinessError("proposal-json不是有效JSON", code="proposal-json-invalid") from exc
    if args.preview:
        payload = preview_unit_submission(args.task_id, args.unit_id, proposal,
                                          args.expected_snapshot_sha256, bind_current=args.bind_current)
    else:
        payload = commit_unit_submission(args.task_id, args.unit_id, proposal,
                                         args.expected_snapshot_sha256, bind_current=args.bind_current)
    _json_out(payload)
    return ExitCode.OK


def cmd_unit_recovery(args: argparse.Namespace) -> int:
    from .material import record_recovery_attempt

    failure = None
    if args.failure_json is not None:
        try:
            failure = json.loads(args.failure_json)
        except json.JSONDecodeError as exc:
            raise BusinessError("failure-json不是有效JSON", code="attempt-failure-json-invalid") from exc
    _json_out(record_recovery_attempt(args.task_id, args.unit_id, args.category,
                                      args.fingerprint, attempt_id=args.attempt_id,
                                      error_code=args.error_code, failure=failure,
                                      expected_run_id=args.expected_run_id))
    return ExitCode.OK


def cmd_unit_progress(args: argparse.Namespace) -> int:
    from .material import unit_progress

    _json_out(unit_progress(args.task_id, unit_id=args.unit_id,
                            stale_after_seconds=args.stale_after_seconds))
    return ExitCode.OK


def cmd_dispatch_plan(args: argparse.Namespace) -> int:
    from .material import dispatch_plan

    _json_out(dispatch_plan(args.task_id, window=args.window))
    return ExitCode.OK


def cmd_unit_event(args: argparse.Namespace) -> int:
    from .material import record_unit_event

    payload = record_unit_event(args.task_id, args.unit_id, phase=args.phase,
                                attempt_id=args.attempt_id, agent_id=args.agent_id,
                                expected_run_id=args.expected_run_id)
    _json_out({"ok": True, "event": payload})
    return ExitCode.OK


def cmd_unit_cancel(args: argparse.Namespace) -> int:
    from .material import record_unit_cancel

    payload = record_unit_cancel(args.task_id, args.unit_id, attempt_id=args.attempt_id,
                                 initiator=args.initiator, reason=args.reason,
                                 agent_id=args.agent_id,
                                 expected_run_id=args.expected_run_id, revoke=args.revoke)
    _json_out({"ok": True, "cancellation": payload})
    return ExitCode.OK


def cmd_unit_schema(args: argparse.Namespace) -> int:
    from .report_suggestions import proposal_json_schema

    _json_out({"schema": proposal_json_schema(bind_current=args.bind_current, schema_version=args.schema_version)})
    return ExitCode.OK


def cmd_unit_review(args: argparse.Namespace) -> int:
    from .review import record_parent_review

    payload = record_parent_review(args.task_id, args.unit_id,
                                   expected_snapshot_sha256=args.expected_snapshot_sha256,
                                   decision=args.decision, reviewer_id=args.reviewer_id,
                                   issue=args.issue or "")
    _json_out(payload)
    return ExitCode.OK


def cmd_verify_report(args: argparse.Namespace) -> int:
    from .verify import verify_unit
    from .workdir import input_path

    result = verify_unit(args.unit, source_path=args.source)
    payload = result.to_dict()
    payload["unit"] = str(input_path(args.unit))
    if args.json:
        _json_out(payload)
    else:
        status = "通过" if result.ok else "未通过"
        log(f" 校验{status}：{result.summary or '（无严重度）'}，标记 {result.marker_count} 个，"
            f"错误 {len(result.errors)}，警告 {len(result.warnings)}，需人工 {len(result.manual)}")
        for i in result.errors:
            log(f"   ❌ [{i.code}] {i.message}")
        for i in result.warnings:
            log(f"   ⚠️ [{i.code}] {i.message}")
        for i in result.manual:
            log(f"   🔎 [{i.code}] {i.message}")
        print(json.dumps(payload, ensure_ascii=False))
    if result.ok:
        return ExitCode.OK
    # 业务失败同样遵守「失败向 stderr 输出一行结构化 JSON」的契约
    emit_error(VerifyFailedError(
        f"报告未通过交付校验：{result.summary or '（无严重度）'}，错误 {len(result.errors)} 条",
        details={"unit": str(args.unit),
                 "errors": [i.to_dict() for i in result.errors]}))
    return ExitCode.VERIFY_FAILED


def cmd_parse_report(args: argparse.Namespace) -> int:
    from .workflow import parse_unit
    payload = parse_unit(args.unit, source=args.source, legacy=args.legacy,
                         legacy_layout=args.legacy_layout, manual_legacy=args.manual_legacy)
    if args.json:
        _json_out(payload)
    else:
        log(f" ✅ _校对数据.json：{payload['data']}")
        print(json.dumps(payload, ensure_ascii=False))
    return ExitCode.OK


def cmd_repair_report(args: argparse.Namespace) -> int:
    from .report_repair import repair_unit_report
    from .workdir import input_path

    result = repair_unit_report(
        args.unit,
        source_path=args.source,
        apply=args.apply,
        manual_legacy=args.manual_legacy,
        work_root=getattr(args, "work_root", None),
    )
    payload = result.to_dict()
    payload.update({
        "unit": str(input_path(args.unit)),
        "applied": result.verified,
        "mode": "apply" if args.apply else "preview",
    })
    if args.json:
        _json_out(payload)
    else:
        print(json.dumps(payload, ensure_ascii=False))
    if result.ok:
        return ExitCode.OK
    emit_error(VerifyFailedError(
        "报告修复候选未通过严格条件，未写入报告",
        details={"unit": str(args.unit), "diagnostics": result.diagnostics},
    ))
    return ExitCode.VERIFY_FAILED


def _parse_kv(values: list[str]) -> dict:
    params: dict[str, Any] = {}
    for item in values or []:
        if "=" not in item:
            raise JiaoduiError(f"--param 需要 NAME=VALUE 形式：{item!r}")
        k, v = item.split("=", 1)
        try:
            params[k] = json.loads(v)
        except json.JSONDecodeError:
            params[k] = v
    return params


# PRD §5.4 的用户可见子命令 → 内部 operation 名
CALC_ALIASES = {
    "dimension": "dimensional",
    "vector": "vector_ops",
    "circle": "circle_from_two_points",
}
CALC_REQUIRED_OPS = ["evaluate", "solve", "formula", "dimension", "vector", "circle", "equality"]


def cmd_calc_schema(args: argparse.Namespace) -> int:
    from .calc.schema import all_json_schemas, json_schema_for
    from .calc import OPERATIONS

    if args.operation:
        payload = {"operation": args.operation, "description": OPERATIONS[args.operation]["summary"],
                   "parameters": json_schema_for(args.operation)}
    else:
        payload = {"operations": all_json_schemas()}
    _json_out(payload)
    return ExitCode.OK


def cmd_calc(args: argparse.Namespace) -> int:
    from .calc import OPERATIONS, run_operation

    op = args.op
    internal = CALC_ALIASES.get(op, op)
    if internal not in OPERATIONS:
        visible = sorted(set(CALC_REQUIRED_OPS) | set(OPERATIONS))
        raise UnsupportedError(f"未知 calc 子命令：{op}", details={"available": visible})
    params = _parse_kv(args.param)
    if getattr(args, "subject", None):
        from .workflow import require_subject_tool
        config = require_subject_tool(args.subject, "calc")
        # 学科物理量表只服务于 dimensional（给 quantity 声明做量纲交叉校验，
        # ADR 0005）；显式传入优先，其他 op 不接受该参数。
        if internal == "dimensional":
            params.setdefault("quantities", config.get("quantities") or {})
    result = run_operation(internal, **params)
    call_id = None
    if bool(getattr(args, "task_id", None)) != bool(getattr(args, "unit_id", None)):
        raise UsageError("calc记录证据时必须同时提供--task-id和--unit-id")
    if getattr(args, "task_id", None):
        from .material import record_calc_call
        call_id = record_calc_call(args.task_id, args.unit_id, internal, params, result)
    if not result.get("code") or not args.show_code:
        result = {k: v for k, v in result.items() if k != "code"}
    # 回显实际参与记账的参数：多参数调用（formula 的 formula+solve_for、
    # equality 的 expression_a+expression_b）必须能逐字复制，不能凭记忆重写。
    payload = {"ok": bool(result.get("success")), "op": op, "params": params,
               "result": result}
    if call_id is not None:
        payload["call_id"] = call_id
    if args.json:
        _json_out(payload)
    else:
        print(json.dumps(result, ensure_ascii=False, default=str))
    if not result.get("success"):
        raise BusinessError(str(result.get("error") or "calc 执行失败"), code="calc_failed",
                            details={"op": op})
    return ExitCode.OK


def cmd_quantities(args: argparse.Namespace) -> int:
    from .workflow import list_quantities

    payload = {"ok": True, **list_quantities(args.subject, args.search)}
    if args.json:
        _json_out(payload)
    else:
        for name, unit in payload["quantities"].items():
            log(f" {name}: {unit}")
        log(f" 共 {payload['count']} 条（{payload['subject']}）")
        print(json.dumps({"ok": True, "count": payload["count"]}, ensure_ascii=False))
    return ExitCode.OK


def cmd_build_report(args: argparse.Namespace) -> int:
    from .report import build_report

    result = build_report(args.paper_dir, out_path=args.out, legacy_layout=args.legacy_layout)
    payload = result.to_dict()
    payload["ok"] = result.out_path is not None
    payload["deliverable"] = result.complete
    if args.json:
        _json_out(payload)
    else:
        log(f" 拼入 {len(result.included)}，失败 {len(result.failed)}，跳过 {len(result.skipped)}")
        print(json.dumps(payload, ensure_ascii=False))
    if not result.out_path:
        raise BusinessError("整卷报告未生成：没有可处理的单元",
                            code="build_report_failed", details={"warnings": result.warnings})
    return ExitCode.OK


def cmd_build_docx(args: argparse.Namespace) -> int:
    from .docx_report import build_docx

    result = build_docx(args.paper_dir, out_dir=args.out_dir, legacy_layout=args.legacy_layout)
    payload = result.__dict__ if hasattr(result, "__dict__") else dict(result)
    payload["ok"] = bool(getattr(result, "ok", False))
    if args.json:
        _json_out(payload)
    else:
        anomaly = f"，记账异常 {result.over_count}" if result.over_count else ""
        if result.image_missing_count:
            anomaly += f"，图片未嵌入 {result.image_missing_count}"
        if result.comment_formula_fallback_count:
            anomaly += (f"，公式降级 {result.comment_formula_fallback_count}"
                        f"（依赖 {result.comment_formula_dependency_missing_count}"
                        f" / 语法 {result.comment_formula_syntax_unsupported_count}）")
        log(f" 标记 {result.marker_count} = 锚点 {result.anchor_count} + 公式兜底 "
            f"{result.formula_fallback_count}，缺失 {result.missing_count}，"
            f"标题批注 {result.heading_comment_count}{anomaly}")
        print(json.dumps(payload, ensure_ascii=False, default=str))
    if not payload["ok"]:
        raise BusinessError(
            "Word 交付未通过复核（缺失/记账异常/被排除/锚点结构不一致）",
            code="docx_incomplete",
            details={"missing_count": result.missing_count,
                     "over_count": result.over_count,
                     "excluded_units": result.excluded_units,
                     "anchor_structure_ok": result.anchor_structure_ok,
                     "warnings": result.warnings})
    return ExitCode.OK


# ---------------------------------------------------------------- parser

class _Parser(argparse.ArgumentParser):
    """参数错误也走统一的结构化错误出口（stderr JSON + 退出码 2）。"""

    def __init__(self, *args, **kwargs):
        kwargs["allow_abbrev"] = False
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> None:  # type: ignore[override]
        raise UsageError(message, details={"usage": self.format_usage().strip()})


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="jiaodui", description="K-12 校对确定性工具核心")
    p.add_argument("--version", action="version", version=f"jiaodui {__version__}")
    p.add_argument("--quiet", action="store_true", help="静默进度输出")
    p.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    p.add_argument("--work-root", help="当前工作区绝对路径（也可由宿主注入 JIAODUI_WORK_ROOT）")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("check-env", help="环境预检（无凭证项，含插件↔CLI契约探针）")
    sp.add_argument("--expect-schema-version", type=int,
                    help="插件期望的提案 schema 版本；与核心能力不一致即预检失败")
    sp.add_argument("--expect-bundle-version",
                    help="插件 bundle 版本；与核心版本不一致即预检失败")
    sp.add_argument("--expect-schema-file",
                    help="插件随包的提案 schema 文件；与核心导出逐字段比对")
    sp.set_defaults(func=cmd_check_env)

    sp = sub.add_parser("inspect-source", help="只读检查 Word 嵌套表格与有限正文节选")
    sp.add_argument("file")
    sp.add_argument("--preview-chars", type=int, default=0, help="节选字符数 0..2000；默认不返回正文")
    sp.set_defaults(func=cmd_inspect_source)

    sp = sub.add_parser("inspect-images", help="按正文顺序列出单元图片引用与实际读取路径")
    sp.add_argument("--unit", required=True)
    sp.set_defaults(func=cmd_inspect_images)

    sp = sub.add_parser("convert", help="docx / idml / md → _raw.md")
    sp.add_argument("file")
    sp.add_argument("--out-dir")
    sp.add_argument("--base-name")
    sp.add_argument("--mathjax", action="store_true", default=None)
    sp.add_argument("--mode", choices=["exam", "lecture"], help="材料类型，讲义自动启用其专用转换参数")
    sp.add_argument("--import-engine", choices=["auto", "docx", "pandoc"], default="auto",
                    help="docx 导入引擎：原生读取固定模板 / 强制 pandoc / 自动（默认）")
    sp.set_defaults(func=cmd_convert)

    sp = sub.add_parser("import", help="一次完成转换、结构拆分与预检，返回紧凑摘要")
    sp.add_argument("file")
    sp.add_argument("--subject", required=True)
    sp.add_argument("--mode", choices=["exam", "lecture"],
                    help="材料类型；省略时仅固定 docx 模板可按结构判定")
    sp.add_argument("--material-name")
    sp.add_argument("--import-engine", choices=["auto", "docx", "pandoc"], default="auto")
    sp.add_argument("--rerun", action="store_true")
    sp.add_argument("--replace-units", action="store_true")
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("split", help="规则拆分：源文 → 单元目录")
    sp.add_argument("raw_md")
    sp.add_argument("--subject", required=True)
    sp.add_argument("--mode", choices=["exam", "lecture"], help="材料类型；省略时沿用材料清单，未知则拒绝")
    sp.add_argument("--strategy", choices=["rule", "manual", "none"], default="rule",
                    help="规则拆分 / 人工单元标记 / 整篇单元；智能拆分使用 slice")
    sp.add_argument("--out-root")
    sp.add_argument("--base-name")
    sp.add_argument("--images-dir")
    sp.add_argument("--no-clean", action="store_true",
                    help="讲义模式跳过导入清理（保留原始表格包裹）")
    sp.set_defaults(func=_split)

    sp = sub.add_parser("slice", help="按边界清单确定性切片")
    sp.add_argument("--boundaries")
    sp.add_argument("--raw")
    sp.add_argument("--out-root")
    sp.add_argument("--base-name")
    sp.add_argument("--mode", choices=["exam", "lecture"])
    sp.add_argument("--subject", help="学科配置（与 split 一致，影响讲义出题意图清理）")
    sp.add_argument("--no-clean", action="store_true",
                    help="讲义模式跳过导入清理（边界行号须与清理后正文一致）")
    sp.add_argument("--scope", choices=["full", "excerpt"],
                    help="切片范围：默认 full 核对全部非空正文；明确节选用 excerpt")
    sp.add_argument("--scope-reason", help="明确节选的原因，excerpt 必填")
    sp.add_argument("--preview", action="store_true",
                    help="只打印讲义清理后的正文（供智能拆分定边界行号），不写盘")
    sp.set_defaults(func=cmd_slice)

    sp = sub.add_parser("precheck-split", help="拆分预检")
    sp.add_argument("dir")
    sp.set_defaults(func=cmd_precheck_split)

    sp = sub.add_parser("status", help="扫描单元状态")
    sp.add_argument("paper_dir")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("execution-policy", help="为当前材料轮次确认自动/交互执行模式")
    sp.add_argument("material_dir")
    sp.add_argument("--mode", choices=["automatic", "interactive"], required=True)
    sp.add_argument("--origin", choices=["user", "confirmed"], default="user")
    sp.set_defaults(func=cmd_execution_policy)

    sp = sub.add_parser("unit-locate", help="按task/unit身份查询原文位置")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--unit-id", required=True)
    sp.add_argument("--phrase", required=True)
    sp.set_defaults(func=cmd_unit_locate)

    sp = sub.add_parser("unit-read", help="按task/unit身份分页只读源文和图片清单")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--unit-id", required=True)
    sp.add_argument("--start-line", type=int, default=1)
    sp.add_argument("--max-lines", type=int, default=2000)
    sp.set_defaults(func=cmd_unit_read)

    sp = sub.add_parser("unit-snapshot", help="读取提交前的单元版本快照")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--unit-id", required=True)
    sp.add_argument("--with-proposal", action="store_true", help="附带当前修订的精简列表供返修引用")
    sp.set_defaults(func=cmd_unit_snapshot)

    sp = sub.add_parser("unit-submit", help="从结构化建议生成并提交完整报告")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--unit-id", required=True)
    proposal_input = sp.add_mutually_exclusive_group(required=True)
    proposal_input.add_argument("--proposal-json", help="结构化建议 JSON（兼容小提案）")
    proposal_input.add_argument("--proposal-json-file", help="UTF-8 编码的结构化建议 JSON 文件")
    sp.add_argument("--expected-snapshot-sha256", required=True)
    sp.add_argument("--bind-current", action="store_true", help="由 core 在锁内绑定当前身份与提案版本")
    sp.add_argument("--preview", action="store_true", help="只预览，不写入报告或数据")
    sp.set_defaults(func=cmd_unit_submit)

    sp = sub.add_parser("unit-recovery", help="消费当前轮次某类恢复预算并留痕")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--unit-id", required=True)
    from .error_classification import RECOVERY_CATEGORIES
    sp.add_argument("--category", choices=list(RECOVERY_CATEGORIES),
                    help="父代理判断类恢复（目前仅 targeted_review）；错误驱动的恢复改用 --error-code")
    sp.add_argument("--error-code",
                    help="失败的工具/宿主错误码；恢复类别由它确定性决定，未分类码会被拒绝")
    sp.add_argument("--attempt-id", required=True,
                    help="本次尝试的幂等键（须与该单元 unit-event 登记的 attempt_id 一致）")
    failure_input = sp.add_mutually_exclusive_group(required=True)
    failure_input.add_argument("--fingerprint", help="兼容旧调用；优先改用 --failure-json，由core派生")
    failure_input.add_argument("--failure-json", help="稳定失败载荷JSON（message/details）；忽略call_id与时间戳并由core派生指纹")
    sp.add_argument("--expected-run-id",
                    help="CAS 防护：与当前轮次不一致即 run-changed")
    sp.set_defaults(func=cmd_unit_recovery)

    sp = sub.add_parser("unit-progress", help="只读汇总单元心跳与在途/超时判定")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--unit-id", help="省略时汇总该材料当前轮次的全部单元")
    sp.add_argument("--stale-after-seconds", type=int, default=900,
                    help="最后一次事件距今超过该秒数且仍在途 → stale=true（默认 900）")
    sp.set_defaults(func=cmd_unit_progress)

    sp = sub.add_parser("dispatch-plan", help="按滑动窗口给出下一批可派发单元（只读）")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--window", type=int, default=8, help="滑动窗口上限，默认 8")
    sp.set_defaults(func=cmd_dispatch_plan)

    sp = sub.add_parser("unit-event", help="记录单元阶段心跳（不含取消；取消用 unit-cancel）")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--unit-id", required=True)
    sp.add_argument("--phase", choices=["prepared", "read", "images", "calculated", "proposed",
                                        "self_checked", "verified", "registered", "parent_reviewed",
                                        "deliverable"], required=True)
    sp.add_argument("--attempt-id", required=True)
    sp.add_argument("--agent-id")
    sp.add_argument("--expected-run-id", help="CAS 防护：与当前轮次不一致即 run-changed")
    sp.set_defaults(func=cmd_unit_event)

    sp = sub.add_parser("unit-cancel", help="记录或撤销一次显式取消（只应由父代理/宿主调用）")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--unit-id", required=True)
    sp.add_argument("--attempt-id", required=True)
    sp.add_argument("--initiator", choices=["user", "parent", "host"], required=True)
    sp.add_argument("--reason", choices=["user_cancel", "technical_timeout", "superseded"],
                    required=True)
    sp.add_argument("--agent-id")
    sp.add_argument("--revoke", action="store_true",
                    help="撤销该单元当前生效的取消（用户取消不可撤销）")
    sp.add_argument("--expected-run-id", help="CAS 防护：与当前轮次不一致即 run-changed")
    sp.set_defaults(func=cmd_unit_cancel)

    sp = sub.add_parser("unit-schema", help="输出结构化建议 schema v2/v3")
    sp.add_argument("--schema-version", type=int, choices=(2, 3), default=2)
    sp.add_argument("--bind-current", action="store_true", help="导出允许 core 绑定六项身份版本字段的 schema")
    sp.set_defaults(func=cmd_unit_schema)

    sp = sub.add_parser("unit-review", help="按snapshot接受或退回当前结构化建议")
    sp.add_argument("--task-id", required=True)
    sp.add_argument("--unit-id", required=True)
    sp.add_argument("--expected-snapshot-sha256", required=True)
    sp.add_argument("--decision", choices=["accepted", "needs_revision"], required=True)
    sp.add_argument("--reviewer-id", required=True)
    sp.add_argument("--issue")
    sp.set_defaults(func=cmd_unit_review)

    sp = sub.add_parser("verify-report", help="交付即校验")
    sp.add_argument("--unit", required=True)
    sp.add_argument("--source")
    sp.set_defaults(func=cmd_verify_report)

    sp = sub.add_parser("parse-report", help="报告 → _校对数据.json")
    sp.add_argument("--unit", required=True)
    sp.add_argument("--source")
    sp.add_argument("--legacy", action="store_true", help="允许解析未通过校验的历史报告")
    sp.add_argument("--manual-legacy", action="store_true", help="人工兼容解析 v1，仅写数据，不登记本轮完成")
    sp.set_defaults(func=cmd_parse_report)

    sp = sub.add_parser("repair-report", help="预览或显式应用报告正文完整性修复")
    sp.add_argument("--unit", required=True)
    sp.add_argument("--source")
    sp.add_argument("--apply", action="store_true", help="原子替换报告并运行完整 verify-unit 复验")
    sp.add_argument("--manual-legacy", action="store_true", help="人工兼容修复 v1，不登记本轮完成")
    sp.set_defaults(func=cmd_repair_report)

    sp = sub.add_parser("calc-schema", help="导出计算operation参数schema")
    sp.add_argument("--operation", choices=sorted(__import__("jiaodui.calc", fromlist=["OPERATIONS"]).OPERATIONS))
    sp.set_defaults(func=cmd_calc_schema)

    sp = sub.add_parser("calc", help="符号计算沙箱（evaluate/solve/formula/dimension/vector/circle/equality）")
    sp.add_argument("op")
    sp.add_argument("--param", action="append", default=[], metavar="NAME=VALUE")
    sp.add_argument("--show-code", action="store_true", help="回显生成的代码（默认不回显）")
    sp.add_argument("--subject", help="学科；提供后按学科配置的工具集白名单校验 calc 是否可用")
    sp.add_argument("--task-id", help="记录calc证据时的材料task_id")
    sp.add_argument("--unit-id", help="记录calc证据时的单元unit_id")
    sp.set_defaults(func=cmd_calc)

    sp = sub.add_parser("quantities", help="列出学科物理量表（只读，供量纲声明核对用词）")
    sp.add_argument("--subject", required=True)
    sp.add_argument("--search", help="按关键词过滤物理量名或单位表达式")
    sp.set_defaults(func=cmd_quantities)

    sp = sub.add_parser("build-report", help="拼接整卷报告")
    sp.add_argument("paper_dir")
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_build_report)

    sp = sub.add_parser("build-docx", help="生成 Word 批注版")
    sp.add_argument("paper_dir")
    sp.add_argument("--out-dir")
    sp.set_defaults(func=cmd_build_docx)

    # 每个子命令都接受 --json / --quiet（默认 SUPPRESS，保留顶层取值）
    for sp in sub.choices.values():
        sp.add_argument("--work-root", default=argparse.SUPPRESS, help="当前工作区绝对路径")
        sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="机器可读 JSON 输出")
        sp.add_argument("--quiet", action="store_true", default=argparse.SUPPRESS,
                        help="静默进度输出")
    for name in ("convert", "split", "slice", "parse-report", "build-report", "build-docx"):
        sub.choices[name].add_argument("--legacy-layout", action="store_true", help="显式使用历史布局，仍受工作区边界限制")
    for name in ("convert", "split", "slice"):
        sub.choices[name].add_argument("--material-name", help="材料目录名称")
        sub.choices[name].add_argument("--mode-origin", choices=["user", "structure", "preview", "confirmed"],
                                       help="类型来源：用户指定 / 结构 / 有限预览 / 询问确认")
        sub.choices[name].add_argument("--mode-reason", help="类型判断的简短依据（不超过 500 字符）")
    for name in ("split", "slice"):
        sub.choices[name].add_argument("--rerun", action="store_true", help="开启新轮次，旧报告不计为本轮完成")
        sub.choices[name].add_argument(
            "--replace-units", action="store_true",
            help="单元集变化时把陈旧单元归档到 .superseded/<run_id>/（只移动不删除），并更新本轮单元集")
    sub.choices["split"].add_argument("--adopt-units", action="store_true", help="显式接纳当前磁盘单元集，留痕且不删除产物")
    return p


def _configure_stdio_utf8() -> None:
    """CLI 机器接口固定 UTF-8，避免 Windows OEM code page 改写 JSON 和中文诊断。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main(argv: list[str] | None = None) -> int:
    _configure_stdio_utf8()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except JiaoduiError as exc:
        return emit_error(exc)
    set_quiet(bool(getattr(args, "quiet", False)))
    try:
        from .workdir import workspace_scope
        with workspace_scope(args.work_root):
            return int(args.func(args))
    except JiaoduiError as exc:
        return emit_error(exc)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc(file=sys.stderr)
        return emit_error(exc)


if __name__ == "__main__":
    raise SystemExit(main())

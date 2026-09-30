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

def cmd_check_env(args: argparse.Namespace) -> int:
    from .checkenv import check_env

    report = check_env()
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
                              mode_origin=args.mode_origin, mode_reason=args.mode_reason)
    payload = {"ok": True, "raw_md": result.raw_md, "images_dir": result.images_dir,
               "copied": result.copied, "missing": result.missing,
               "warnings": result.warnings, "source_kind": result.source_kind, "mode": result.mode}
    if args.json:
        _json_out(payload)
    else:
        log(f" ✅ 转换完成（{result.source_kind}）：{result.raw_md}")
        print(json.dumps(payload, ensure_ascii=False))
    return ExitCode.OK


def _split(args: argparse.Namespace) -> int:
    from .workflow import split_material
    result = split_material(args.raw_md, subject=args.subject, mode=args.mode,
                            out_root=args.out_root, base_name=args.base_name,
                            material_name=args.material_name, images_dir=args.images_dir,
                            clean=not args.no_clean, rerun=args.rerun,
                            adopt_units=args.adopt_units, legacy_layout=args.legacy_layout,
                            mode_origin=args.mode_origin, mode_reason=args.mode_reason,
                            strategy=args.strategy)
    payload = {"ok": True, "units": result.units, "unit_dirs": result.unit_dirs,
               "copied": result.copied, "missing": result.missing, "warnings": result.warnings}
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
                            legacy_layout=args.legacy_layout, preview=args.preview,
                            mode_origin=args.mode_origin, mode_reason=args.mode_reason)
    if args.preview:
        if args.json:
            _json_out(result)
        else:
            print(result["cleaned"])
        return ExitCode.OK
    payload = {"ok": True, "unit_dirs": result.unit_dirs, "units": result.units,
               "copied": result.copied, "missing": result.missing, "warnings": result.warnings}
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
        print(json.dumps(result.counts(), ensure_ascii=False))
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
    payload = parse_unit(args.unit, source=args.source, legacy=args.legacy, legacy_layout=args.legacy_layout)
    if args.json:
        _json_out(payload)
    else:
        log(f" ✅ _校对数据.json：{payload['data']}")
        print(json.dumps(payload, ensure_ascii=False))
    return ExitCode.OK


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


def cmd_calc(args: argparse.Namespace) -> int:
    from .calc import OPERATIONS, run_operation

    op = args.op
    internal = CALC_ALIASES.get(op, op)
    if internal not in OPERATIONS:
        visible = sorted(set(CALC_REQUIRED_OPS) | set(OPERATIONS))
        raise UnsupportedError(f"未知 calc 子命令：{op}", details={"available": visible})
    params = _parse_kv(args.param)
    result = run_operation(internal, **params)
    if not result.get("code") or not args.show_code:
        result = {k: v for k, v in result.items() if k != "code"}
    payload = {"ok": bool(result.get("success")), "op": op, "result": result}
    if args.json:
        _json_out(payload)
    else:
        print(json.dumps(result, ensure_ascii=False, default=str))
    if not result.get("success"):
        raise BusinessError(str(result.get("error") or "calc 执行失败"), code="calc_failed",
                            details={"op": op})
    return ExitCode.OK


def cmd_build_report(args: argparse.Namespace) -> int:
    from .report import build_report

    result = build_report(args.paper_dir, out_path=args.out, legacy_layout=args.legacy_layout)
    payload = result.to_dict()
    payload["ok"] = result.out_path is not None
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
        log(f" 标记 {result.marker_count} = 锚点 {result.anchor_count} + 公式兜底 "
            f"{result.formula_fallback_count}，缺失 {result.missing_count}，"
            f"标题批注 {result.heading_comment_count}")
        print(json.dumps(payload, ensure_ascii=False, default=str))
    if not payload["ok"]:
        raise BusinessError(
            "Word 交付未通过复核（缺失/被排除/锚点结构不一致）",
            code="docx_incomplete",
            details={"missing_count": result.missing_count,
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

    sp = sub.add_parser("check-env", help="环境预检（无凭证项）")
    sp.set_defaults(func=cmd_check_env)

    sp = sub.add_parser("inspect-source", help="只读检查 Word 嵌套表格与有限正文节选")
    sp.add_argument("file")
    sp.add_argument("--preview-chars", type=int, default=0, help="节选字符数 0..2000；默认不返回正文")
    sp.set_defaults(func=cmd_inspect_source)

    sp = sub.add_parser("convert", help="docx / idml / md → _raw.md")
    sp.add_argument("file")
    sp.add_argument("--out-dir")
    sp.add_argument("--base-name")
    sp.add_argument("--mathjax", action="store_true", default=None)
    sp.add_argument("--mode", choices=["exam", "lecture"], help="材料类型，讲义自动启用其专用转换参数")
    sp.set_defaults(func=cmd_convert)

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
    sp.add_argument("--preview", action="store_true",
                    help="只打印讲义清理后的正文（供智能拆分定边界行号），不写盘")
    sp.set_defaults(func=cmd_slice)

    sp = sub.add_parser("precheck-split", help="拆分预检")
    sp.add_argument("dir")
    sp.set_defaults(func=cmd_precheck_split)

    sp = sub.add_parser("status", help="扫描单元状态")
    sp.add_argument("paper_dir")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("verify-report", help="交付即校验")
    sp.add_argument("--unit", required=True)
    sp.add_argument("--source")
    sp.set_defaults(func=cmd_verify_report)

    sp = sub.add_parser("parse-report", help="报告 → _校对数据.json")
    sp.add_argument("--unit", required=True)
    sp.add_argument("--source")
    sp.add_argument("--legacy", action="store_true", help="允许解析未通过校验的历史报告")
    sp.set_defaults(func=cmd_parse_report)

    sp = sub.add_parser("calc", help="符号计算沙箱（evaluate/solve/formula/dimension/vector/circle/equality）")
    sp.add_argument("op")
    sp.add_argument("--param", action="append", default=[], metavar="NAME=VALUE")
    sp.add_argument("--show-code", action="store_true", help="回显生成的代码（默认不回显）")
    sp.set_defaults(func=cmd_calc)

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
    sub.choices["split"].add_argument("--adopt-units", action="store_true", help="显式接纳当前磁盘单元集，留痕且不删除产物")
    return p


def main(argv: list[str] | None = None) -> int:
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

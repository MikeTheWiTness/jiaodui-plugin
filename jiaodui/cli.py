"""jiaodui 命令行入口：11 个 v1 命令。

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
    """定位学科配置目录：env → cwd/config → 仓库 config → 包内 data（发行版）。"""
    env = os.environ.get("JIAODUI_CONFIG_DIR")
    if env:
        return Path(env)
    pkg = Path(__file__).resolve().parent
    candidates = [Path.cwd() / "config", pkg.parent / "config", pkg / "data"]
    for c in candidates:
        if (c / "subjects").is_dir():
            return c
    return candidates[-1]


def _resolve_subject_config(subject: str) -> dict:
    from .config import load_subject_config

    config_dir = _resolve_config_dir() / "subjects"
    path = config_dir / f"{subject}.json"
    if not path.is_file():
        raise NotFoundError(f"找不到学科配置：{path}", details={"subject": subject,
                                                              "config_dir": str(config_dir)})
    return load_subject_config(path)


# ---------------------------------------------------------------- commands

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
    from .convert import convert_to_raw

    src = Path(args.file)
    if not src.is_file():
        raise NotFoundError(f"源文件不存在：{src}")
    src_dir = src.parent
    base_name = args.base_name or src.stem
    out_dir = Path(args.out_dir) if args.out_dir else src_dir
    result = convert_to_raw(str(src), str(out_dir), base_name, use_mathjax=args.mathjax)
    payload = {"ok": True, "raw_md": result.raw_md, "images_dir": result.images_dir,
               "copied": result.copied, "missing": result.missing,
               "warnings": result.warnings, "source_kind": result.source_kind}
    if args.json:
        _json_out(payload)
    else:
        log(f" ✅ 转换完成（{result.source_kind}）：{result.raw_md}")
        print(json.dumps(payload, ensure_ascii=False))
    return ExitCode.OK


def _split(args: argparse.Namespace) -> int:
    from .split import split_exam, split_lecture

    raw_path = Path(args.raw_md)
    if not raw_path.is_file():
        raise NotFoundError(f"raw md 不存在：{raw_path}")
    config = _resolve_subject_config(args.subject)
    base_name = args.base_name or raw_path.stem.replace("_raw", "")
    out_root = Path(args.out_root) if args.out_root else raw_path.parent
    if args.images_dir:
        config["images_source"] = args.images_dir
    # 传路径而非正文：split 会据此推导图片源目录 {raw_md 所在目录}/{base_name}_images/media
    if args.mode == "exam":
        result = split_exam(str(raw_path), str(out_root), base_name, config)
    else:
        # 讲义默认执行导入清理（表格清理 + 装饰图清除），与旧仓 clean_enabled 默认一致；
        # --no-clean 保留原始表格包裹，供排查/对照使用。
        result = split_lecture(str(raw_path), str(out_root), base_name, config,
                               clean=not args.no_clean)
    payload = {"ok": True, "units": result.units, "unit_dirs": result.unit_dirs,
               "copied": result.copied, "missing": result.missing, "warnings": result.warnings}
    if args.json:
        _json_out(payload)
    else:
        log(f" ✅ 拆分完成：{len(result.unit_dirs)} 个单元，图片 {result.copied} 张")
        print(json.dumps(payload, ensure_ascii=False))
    return ExitCode.OK


def cmd_slice(args: argparse.Namespace) -> int:
    from .split import slice_by_boundaries

    bpath = Path(args.boundaries)
    if not bpath.is_file():
        raise NotFoundError(f"边界清单不存在：{bpath}")
    data = json.loads(bpath.read_text(encoding="utf-8"))
    raw_path = args.raw or data.get("raw") or data.get("source")
    if not raw_path:
        raise JiaoduiError("边界清单缺少 raw/source 字段，且未提供 --raw")
    raw_path = Path(raw_path)
    if not raw_path.is_absolute() and not raw_path.is_file():
        raw_path = bpath.parent / raw_path
    if not raw_path.is_file():
        raise NotFoundError(f"raw md 不存在：{raw_path}")
    boundaries = data.get("boundaries", data if isinstance(data, list) else None)
    if not boundaries:
        raise JiaoduiError("边界清单缺少 boundaries 数组")
    mode = args.mode or data.get("mode", "exam")
    base_name = args.base_name or data.get("base_name") or raw_path.stem.replace("_raw", "")
    out_root = Path(args.out_root) if args.out_root else (Path(data["out_root"]) if data.get("out_root") else raw_path.parent)
    result = slice_by_boundaries(str(raw_path), boundaries, str(out_root), base_name, mode,
                                 clean=not args.no_clean)
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

    result = verify_unit(args.unit, source_path=args.source)
    payload = result.to_dict()
    payload["unit"] = str(args.unit)
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
    from .paths import data_path, report_path
    from .report_parse import save_proofread_json
    from .verify import verify_unit

    unit = Path(args.unit)
    report = report_path(unit)
    if not report.is_file():
        raise NotFoundError(f"找不到报告：{report}")
    result = verify_unit(unit, source_path=args.source)
    if not result.ok and not args.legacy:
        raise ContractError(
            "报告未通过 verify-report，拒绝解析（历史产物兼容请显式加 --legacy）",
            details={"errors": [i.message for i in result.errors]})
    text = report.read_text(encoding="utf-8")
    ok = save_proofread_json(text, str(unit))
    payload = {"ok": ok, "data": str(data_path(unit)),
               "verified": result.ok, "legacy": bool(args.legacy and not result.ok)}
    if args.json:
        _json_out(payload)
    else:
        log(f" {'✅' if ok else '❌'} _校对数据.json：{data_path(unit)}")
        print(json.dumps(payload, ensure_ascii=False))
    if not ok:
        raise BusinessError(f"报告无法解析为 _校对数据.json：{unit}", code="parse_failed",
                            details={"unit": str(unit)})
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

    result = build_report(args.paper_dir, out_path=args.out)
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

    result = build_docx(args.paper_dir, out_dir=args.out_dir)
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

    def error(self, message: str) -> None:  # type: ignore[override]
        raise UsageError(message, details={"usage": self.format_usage().strip()})


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="jiaodui", description="K-12 校对确定性工具核心")
    p.add_argument("--version", action="version", version=f"jiaodui {__version__}")
    p.add_argument("--quiet", action="store_true", help="静默进度输出")
    p.add_argument("--json", action="store_true", help="机器可读 JSON 输出")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("check-env", help="环境预检（无凭证项）")
    sp.set_defaults(func=cmd_check_env)

    sp = sub.add_parser("convert", help="docx / idml / md → _raw.md")
    sp.add_argument("file")
    sp.add_argument("--out-dir")
    sp.add_argument("--base-name")
    sp.add_argument("--mathjax", action="store_true")
    sp.set_defaults(func=cmd_convert)

    sp = sub.add_parser("split", help="规则拆分：源文 → 单元目录")
    sp.add_argument("raw_md")
    sp.add_argument("--subject", required=True)
    sp.add_argument("--mode", choices=["exam", "lecture"], required=True)
    sp.add_argument("--out-root")
    sp.add_argument("--base-name")
    sp.add_argument("--images-dir")
    sp.add_argument("--no-clean", action="store_true",
                    help="讲义模式跳过导入清理（保留原始表格包裹）")
    sp.set_defaults(func=_split)

    sp = sub.add_parser("slice", help="按边界清单确定性切片")
    sp.add_argument("--boundaries", required=True)
    sp.add_argument("--raw")
    sp.add_argument("--out-root")
    sp.add_argument("--base-name")
    sp.add_argument("--mode", choices=["exam", "lecture"])
    sp.add_argument("--no-clean", action="store_true",
                    help="讲义模式跳过导入清理（边界行号须与清理后正文一致）")
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
        sp.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="机器可读 JSON 输出")
        sp.add_argument("--quiet", action="store_true", default=argparse.SUPPRESS,
                        help="静默进度输出")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except JiaoduiError as exc:
        return emit_error(exc)
    set_quiet(bool(getattr(args, "quiet", False)))
    try:
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

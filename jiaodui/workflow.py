"""工作区内的确定性材料流程；CLI 与宿主只透传参数。"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from . import __version__, material
from .config import load_subject_config, resolve_config_dir
from .errors import BusinessError, NotFoundError, UnsupportedError, UsageError
from .paths import data_path, safe_name
from .log import log
from .material_type import resolve_selection
from .workdir import ensure_inside, ensure_tree, input_path, workspace_root





def subject_config(subject: str) -> dict:
    path = resolve_config_dir() / "subjects" / f"{subject}.json"
    if not path.is_file():
        raise NotFoundError(f"找不到学科配置：{path}")
    return load_subject_config(path)


ARCHIVE_DIR = ".superseded"
"""陈旧单元归档目录名：位于单元根目录内，不被单元扫描识别。"""


def list_quantities(subject: str, search: str | None = None) -> dict:
    """列出学科物理量表，可按关键词过滤；只读，供 agent 核对声明用词。

    量表本身不进 agent 上下文（它是 Python 侧数据），需要时按需查这一条命令。
    """
    config = require_subject_tool(subject, "calc")
    table = config.get("quantities") or {}
    if search and search.strip():
        needle = search.strip()
        table = {name: unit for name, unit in table.items()
                 if needle in name or needle in unit}
    return {"subject": subject, "count": len(table), "quantities": table}


def _archive_stale_units(paper: Path, keep: list[str], run_id: str) -> list[dict]:
    """把不再属于当前单元集的单元目录移动到 <paper>/.superseded/<run_id>/。

    只移动、不删除：旧报告与图片仍留在材料目录内可追溯。归档目录名不是契约
    单元名，`scan_unit_dirs` / `check_units` 都不会把它当成单元。
    """
    from .units import scan_unit_dirs

    keep_set = set(keep)
    stale = [path for path in scan_unit_dirs(paper) if path.name not in keep_set]
    moved: list[dict] = []
    for path in stale:
        destination = ensure_tree(paper / ARCHIVE_DIR / run_id / path.name)
        if destination.exists():
            raise BusinessError(
                f"归档目标已存在，拒绝覆盖：{destination}",
                code="archive-conflict",
                details={"unit": path.name, "destination": str(destination)},
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))
        moved.append({
            "unit": path.name,
            "from": path.relative_to(paper.parent).as_posix(),
            "to": destination.relative_to(paper.parent).as_posix(),
        })
    return moved


def require_subject_tool(subject: str, family: str) -> dict:
    """校验学科配置的工具集白名单包含某工具族，返回该学科配置。

    白名单只是「这门学科能不能用这类工具」，不细分 operation：operations 的
    取舍仍由学科 references 决定。
    """
    config = subject_config(subject)
    allowed = config.get("tools") or []
    if family not in allowed:
        raise UnsupportedError(
            f"学科「{subject}」未声明 {family} 工具",
            details={"subject": subject, "requested": family, "allowed_tools": allowed},
        )
    return config


def _name(name: str) -> str:
    value = safe_name(name)
    if value in {".", ".."}:
        raise BusinessError("材料名不能为 . 或 ..", code="invalid-material-name")
    return value


def _saved_type(data: dict | None) -> dict | None:
    """兼容新增类型来源字段之前已落盘的明确拆分类型。"""
    if not data:
        return None
    if data.get("material_type") is not None:
        return data["material_type"]
    mode = data.get("params", {}).get("mode")
    if mode in {"lecture", "exam"}:
        return {"mode": mode, "origin": "confirmed", "reason": "沿用既有材料记录中的拆分类型"}
    return None


def convert_material(file: str | Path, out_dir: str | Path | None = None,
                     base_name: str | None = None, *, material_name: str | None = None,
                     use_mathjax: bool | None = None, legacy_layout: bool = False,
                     mode: str | None = None, mode_origin: str | None = None,
                     mode_reason: str | None = None):
    from .convert import _IMG_RE, convert_to_raw, image_destination
    src = input_path(file)
    if not src.is_file():
        raise NotFoundError(f"源文件不存在：{src}")
    if src.suffix.lower() not in {".docx", ".doc", ".md", ".markdown", ".idml"}:
        raise UnsupportedError(f"不支持的文件格式：{src.suffix}")
    if src.suffix.lower() == ".doc":
        # 在创建材料目录之前拒绝，避免留下空材料
        raise UnsupportedError(
            "不支持旧版 .doc 格式：请先用 Word / LibreOffice 另存为 .docx 再转换",
            details={"path": str(src)})
    root = workspace_root()
    name = _name(material_name or base_name or src.stem)
    selection = resolve_selection(mode, origin=mode_origin, reason=mode_reason, required=False)
    if legacy_layout:
        if out_dir is None:
            raise BusinessError("历史转换需显式 --out-dir", code="output-required")
        return convert_to_raw(str(src), str(ensure_inside(out_dir)), name, use_mathjax, mode=mode)
    directory = ensure_tree(root / "校对" / name)
    raw_dir = ensure_tree(out_dir if out_dir is not None else directory / "raw")
    if raw_dir != directory / "raw":
        raise BusinessError("新布局转换输出必须为材料 raw/；历史布局请显式指定", code="layout-conflict")
    digest = material.sha256(src)
    if directory.exists() and not (directory / material.MANIFEST).exists() and any(directory.iterdir()):
        raise BusinessError("已有非空材料目录缺少清单，拒绝覆盖", code="manifest-required")
    directory.mkdir(parents=True, exist_ok=True)
    with material.locked(directory):
        marker = directory / material.MANIFEST
        data = material.load(directory) if marker.exists() or marker.is_symlink() else None
        selection = resolve_selection(mode, _saved_type(data), origin=mode_origin, reason=mode_reason, required=False)
        effective_mode = selection["mode"] if selection else None
        effective_mathjax = effective_mode == "lecture" if use_mathjax is None else use_mathjax
        if data is not None and data["source_sha256"] != digest:
            raise BusinessError("同名材料源文件已改变；请指定 --material-name 或移走旧目录",
                                code="material-conflict", details={"material_dir": str(directory)})
        if data is not None and data["material_name"] != name:
            raise BusinessError("材料目录名称与清单不一致", code="invalid-manifest")
        for part in ("source", "raw", "units", "校对报告", "校对Word"):
            ensure_inside(directory / part).mkdir(parents=True, exist_ok=True)
        source_copy = ensure_inside(directory / "source" / src.name)
        if source_copy != src:
            shutil.copy2(src, source_copy)
        # Markdown 仍保留原文件字节；安全相对引用的资源复制到同样的目录结构。
        if src.suffix.lower() in {".md", ".markdown"}:
            md_text = src.read_text(encoding="utf-8")
            # 没有 "](" 就不可能有图片引用：未闭合的 "![" 会让 _IMG_RE 退化成 O(n²)。
            for _, raw_link in (_IMG_RE.findall(md_text) if '](' in md_text else []):
                link = image_destination(raw_link)
                if not link or link.startswith(("http://", "https://", "data:")):
                    continue
                image = (src.parent / link).resolve()
                # 只允许引用源文件目录内的资源：否则一份构造的 md 可以把宿主机
                # 任意可读文件（如 /etc/passwd）吸进材料 source/。
                if not image.is_relative_to(src.parent.resolve()) or not image.is_file():
                    log(f"   ⚠️ 跳过源目录之外的图片引用：{link}")
                    continue
                target = directory / "source" / link
                if Path(link).is_absolute() or not target.resolve().is_relative_to(directory / "source"):
                    target = directory / "source" / "images" / f"{material.sha256(image)[:12]}_{image.name}"
                target = ensure_inside(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                if image != target:
                    shutil.copy2(image, target)
        if data is None:
            data = {"schema_version": 1, "material_name": name, "source_path": str(src),
                    "source_sha256": digest, "created_at": material.now(), "tool_version": __version__,
                     "task_id": material.new_task_id(), "unit_ids": {},
                    "paths": {"source": source_copy.relative_to(directory).as_posix(),
                              "raw": f"raw/{name}_raw.md",
                              "images": f"raw/{name}_images",
                              "paper": f"units/{name}"},
                    "params": {}, "resources": [], "unit_set": [], "unit_inputs": {},
                    "unit_records": [], "runs": []}
            material.new_run(data, {}, [])
        snapshot = material.resources(directory, directory / "source")
        previous = data.get("conversion")
        run_changed = previous is not None and (previous["source_resources"] != snapshot
                                                or previous["mathjax"] != effective_mathjax
                                                or previous.get("mode") != effective_mode)
        if run_changed:
            material.new_run(data, data["params"], data["resources"])
        if selection is not None:
            data["material_type"] = selection
        action = {"at": material.now(), "command": "convert", "status": "running",
                  "args": {"file": str(src), "out_dir": str(raw_dir),
                           "material_name": name, "mathjax": effective_mathjax,
                           "material_type": selection}, "tool_version": __version__}
        data["runs"][-1]["actions"].append(action)
        material.write(directory, data)
        try:
            result = convert_to_raw(str(src), str(raw_dir), name, effective_mathjax, mode=effective_mode)
        except Exception as exc:
            action.update(status="failed", error=str(exc), finished_at=material.now())
            material.write(directory, data)
            raise
        conversion = {"raw_sha256": material.sha256(result.raw_md), "mathjax": effective_mathjax,
                      "mode": effective_mode,
                      "resources": material.resources(directory, Path(result.images_dir)),
                      "source_resources": snapshot}
        action.update(status="completed", finished_at=material.now(), missing=result.missing,
                      copied=result.copied, warnings=result.warnings)
        if previous is not None and previous != conversion and not run_changed:
            material.new_run(data, data["params"], conversion["resources"])
            data["runs"][-1]["actions"].append(action)
        data["conversion"] = conversion
        material.write(directory, data)
        return result


def split_material(raw_md: str | Path, *, subject: str | None = None, mode: str | None = None,
                   out_root: str | Path | None = None, base_name: str | None = None,
                   material_name: str | None = None, images_dir: str | Path | None = None,
                   clean: bool = True, boundaries: list[dict] | None = None,
                   boundaries_sha256: str | None = None, rerun: bool = False,
                   adopt_units: bool = False, replace_units: bool = False,
                   legacy_layout: bool = False,
                   mode_origin: str | None = None, mode_reason: str | None = None,
                   strategy: str = "rule"):
    from .split import SplitResult, slice_by_boundaries, split_exam, split_lecture, split_by_strategy
    raw = input_path(raw_md)
    if not raw.is_file():
        raise NotFoundError(f"raw md 不存在：{raw}")
    if strategy not in {"rule", "manual", "none"}:
        raise UsageError("拆分 strategy 必须为 rule / manual / none；智能拆分使用宿主判断加 slice")
    if boundaries is not None and strategy != "rule":
        raise UsageError("边界切片不能同时指定其他拆分策略")
    workspace_root()
    config = subject_config(subject) if subject else {}
    name = _name(material_name or base_name or raw.stem.removesuffix("_raw"))
    directory = material.find_material(raw)
    data = material.load(directory) if directory is not None else None
    selection = resolve_selection(mode or ("exam" if legacy_layout else None), _saved_type(data),
                                  origin=mode_origin, reason=mode_reason)
    mode = selection["mode"]
    if legacy_layout:
        target = ensure_inside(out_root if out_root is not None else raw.parent)
    else:
        if directory is None:
            converted = convert_material(raw, material_name=name, mode=mode,
                                         mode_origin=selection["origin"], mode_reason=selection["reason"])
            raw = Path(converted.raw_md)
            directory = material.find_material(raw)
        data = material.load(directory)
        converted_mode = data.get("conversion", {}).get("mode")
        if converted_mode is None:
            # 入口可能为有限预览先做公共转换；确定类型后完成对应导入，再拆分。
            if boundaries is not None:
                raise BusinessError("边界切片前需先按已确定 --mode 转换并重新预览，避免行号错位",
                                    code="mode-required")
            snapshot = material.relative_path(directory, data["paths"]["source"])
            converted = convert_material(snapshot, material_name=data["material_name"], mode=mode,
                                         mode_origin=selection["origin"], mode_reason=selection["reason"])
            raw = Path(converted.raw_md)
            data = material.load(directory)
        if converted_mode is not None and converted_mode != mode:
            raise BusinessError("拆分类型与导入类型不同；请先用源文件副本按新 --mode 重新 convert",
                                code="mode-conflict", details={"import_mode": converted_mode,
                                                               "requested_mode": mode,
                                                               "source": str(material.relative_path(directory, data["paths"]["source"]))})
        name = data["material_name"]
        target = ensure_tree(out_root if out_root is not None else directory / "units")
        if target / name != material.relative_path(directory, data["paths"]["paper"]):
            raise BusinessError("拆分输出与材料清单不一致", code="layout-conflict")
    if images_dir:
        config["images_source"] = str(input_path(images_dir))
    def split(before_write=None):
        if boundaries is not None:
            return slice_by_boundaries(str(raw), boundaries, str(target), name, mode,
                                       clean=clean, config=config, before_write=before_write)
        if strategy != "rule":
            return split_by_strategy(str(raw), str(target), name, config, mode=mode,
                                     strategy=strategy, clean=clean, before_write=before_write)
        if mode == "exam":
            return split_exam(str(raw), str(target), name, config, before_write=before_write)
        return split_lecture(str(raw), str(target), name, config, clean=clean,
                             before_write=before_write)
    if legacy_layout:
        if adopt_units or replace_units or rerun:
            raise BusinessError("轮次与集合变更需要新布局材料清单", code="manifest-required")
        return split()
    with material.locked(directory):
        data = material.load(directory)
        paper = ensure_tree(material.relative_path(directory, data["paths"]["paper"]))
        from .units import scan_unit_dirs
        if adopt_units and replace_units:
            raise UsageError("--adopt-units 与 --replace-units 不能同时使用")
        if adopt_units:
            before = list(data["unit_set"])
            dirs = scan_unit_dirs(paper)
            data["unit_set"] = [p.name for p in dirs]
            material.ensure_unit_ids(data, data["unit_set"])
            data["unit_inputs"] = {p.name: material.unit_inputs(directory, p) for p in dirs}
            material.new_run(data, data["params"], data["resources"])
            data["runs"][-1]["actions"].append({"command": "split --adopt-units", "at": material.now(),
                                                "before": before, "after": data["unit_set"]})
            material.write(directory, data)
            return SplitResult(unit_dirs=[str(p) for p in dirs])
        # --replace-units 的语义就是「集合会变」，不能拿旧集合先卡住自己。
        if data["unit_set"] and not replace_units:
            material.check_units(directory, data)
        before_names = {path.name for path in scan_unit_dirs(paper)}

        def check_unit_set(names: list[str]) -> None:
            # 保留既有增补语义；淘汰旧单元必须显式 --replace-units。
            # 在写盘前拒绝，不需要备份或回滚源文、图片与校对产物。
            stale = before_names - set(names)
            if stale and not replace_units:
                raise BusinessError(
                    "拆分结果与当前单元集不一致，未写入单元或清单",
                    code="unit-set-mismatch",
                    details={"extra_units": sorted(stale), "missing_units": [],
                             "hint": "如需变更单元集，请用 split / slice --replace-units："
                                     "陈旧单元会归档到单元根目录的 .superseded/<run_id>/，只移动不删除"})

        params = {"subject": subject, "mode": mode, "clean": clean,
                  "strategy": "boundaries" if boundaries is not None else strategy,
                  "boundaries_sha256": boundaries_sha256,
                  "raw_sha256": material.sha256(raw),
                  "config_sha256": hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
        result = split(before_write=check_unit_set)
        data["material_type"] = selection
        dirs = [Path(p) for p in result.unit_dirs]
        names = [p.name for p in dirs]
        material.ensure_unit_ids(data, names)
        archived = _archive_stale_units(paper, names, data["current_run_id"]) if replace_units else []
        inputs = {p.name: material.unit_inputs(directory, p) for p in dirs}
        associated = material.resources(directory, material.relative_path(directory, data["paths"]["images"]))
        opens_new_run = (rerun or data["params"] != params or data["resources"] != associated
                         or data["unit_inputs"] != inputs)
        if opens_new_run:
            material.new_run(data, params, associated)
            # 执行模式授权绑定轮次：这里一开新轮，上一轮授权立即失效。当场告知调用方，
            # 避免子代理派出去之后在第 1 步被 execution-policy-required 集体拒绝
            # （第 11 讲实测：split 后 8 个并发子代理首次调用全部被拒）。
            result.warnings.append(
                "本次拆分开启了新轮次，上一轮的执行模式授权已失效；"
                "派发单元前必须重新登记：`jiaodui execution-policy <材料目录> "
                "--mode automatic|interactive --origin user|confirmed --work-root <W> --json`")
        data["unit_set"] = names
        data["unit_inputs"] = inputs
        data["runs"][-1]["actions"].append({"command": "slice" if boundaries is not None else "split",
                                            "at": material.now(), "args": {"raw": str(raw), **params,
                                                                            "rerun": rerun,
                                                                            "replace_units": archived,
                                                                            "material_type": selection}, "tool_version": __version__})
        material.write(directory, data)
        material.check_units(directory, data)
        return result


def slice_material(boundaries_file: str | Path | None, *, raw: str | Path | None = None,
                   subject: str | None = None, mode: str | None = None,
                   out_root: str | Path | None = None, base_name: str | None = None,
                   material_name: str | None = None, clean: bool = True,
                   rerun: bool = False, replace_units: bool = False,
                   legacy_layout: bool = False, preview: bool = False,
                   mode_origin: str | None = None, mode_reason: str | None = None):
    if preview:
        from .split import lecture_cleaned_text
        if raw is None:
            raise UsageError("--preview 需要 --raw <raw_md>")
        path = input_path(raw)
        if not path.is_file():
            raise NotFoundError(f"raw md 不存在：{path}")
        root = material.find_material(path)
        data = material.load(root) if root is not None else None
        selection = resolve_selection(mode or ("lecture" if legacy_layout else None), _saved_type(data),
                                      origin=mode_origin, reason=mode_reason)
        effective_mode = selection["mode"]
        if data is not None and not legacy_layout and data.get("conversion", {}).get("mode") != effective_mode:
            raise BusinessError("请先按已确定 --mode 转换材料，再生成同一类型的切片预览", code="mode-conflict")
        config = subject_config(subject) if subject else {}
        cleaned = (lecture_cleaned_text(str(path), base_name or path.stem.removesuffix("_raw"), config)
                   if clean and effective_mode == "lecture" else path.read_text(encoding="utf-8"))
        return {"ok": True, "mode": effective_mode, "cleaned": cleaned}
    if boundaries_file is None:
        raise UsageError("slice 需要 --boundaries <清单.json>，或用 --preview")
    file = input_path(boundaries_file)
    if not file.is_file():
        raise NotFoundError(f"边界清单不存在：{file}")
    data = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(data, (dict, list)):
        raise BusinessError("边界清单必须为对象或数组", code="invalid-boundaries")
    metadata = data if isinstance(data, dict) else {}
    if mode is not None and metadata.get("mode") is not None and mode != metadata["mode"]:
        raise BusinessError("命令类型与边界清单不一致，请使用预览时的同一类型", code="mode-conflict")
    raw = raw or metadata.get("raw") or metadata.get("source")
    if not raw:
        raise BusinessError("边界清单缺少 raw/source", code="invalid-boundaries")
    boundaries = metadata.get("boundaries") if isinstance(data, dict) else data
    if not isinstance(boundaries, list) or not boundaries:
        raise BusinessError("边界清单缺少非空 boundaries 数组", code="invalid-boundaries")
    return split_material(raw, subject=subject or metadata.get("subject"),
                          mode=mode or metadata.get("mode"),
                          out_root=out_root or metadata.get("out_root"),
                          base_name=base_name or metadata.get("base_name"), material_name=material_name,
                          clean=clean, boundaries=boundaries,
                          boundaries_sha256=material.sha256(file), rerun=rerun,
                          replace_units=replace_units, legacy_layout=legacy_layout,
                          mode_origin=mode_origin, mode_reason=mode_reason)


def parse_unit(unit: str | Path, *, source: str | Path | None = None,
               legacy: bool = False, legacy_layout: bool = False) -> dict:
    from .report_parse import save_proofread_json
    from .verify import verify_unit
    from .paths import find_source_md, report_path
    unit = input_path(unit)
    ensure_tree(unit)
    root = material.find_material(unit)
    if root is None and not legacy_layout:
        raise BusinessError("历史报告写入需 --legacy-layout", code="manifest-required")
    if root is not None:
        ensure_tree(root)
        data = material.load(root)
        paper = material.check_units(root, data)
        if unit.parent != paper:
            raise BusinessError("单元不属于当前材料", code="unit-path-mismatch")
    report = report_path(unit)
    if not report.is_file():
        raise NotFoundError(f"找不到报告：{report}")
    text = report.read_bytes().decode("utf-8")
    if text.startswith("<!-- jiaodui-report-v2 -->"):
        raise BusinessError("v2报告须通过unit-submit生成登记，禁止旧parse覆盖建议及证据", code="parse-v2-requires-submit")
    source_file = input_path(source) if source else find_source_md(unit)
    # 走完整闸门：parse-report 是交付登记入口，只查文本会让缺图单元照样登记。
    verdict = verify_unit(unit, source_path=source_file)
    if not verdict.ok and not legacy:
        raise BusinessError("报告未通过 verify-report，拒绝解析", code="contract",
                            details={"errors": [i.message for i in verdict.errors]})
    if root is not None and (source is not None or not verdict.ok):
        raise BusinessError("新材料登记必须校验本单元源文且通过闸门", code="contract")
    ok = save_proofread_json(text, str(unit))
    if not ok:
        raise BusinessError("报告无法解析", code="parse_failed")
    if root is not None:
        material.register(root, unit, text, data["current_run_id"])
    return {"ok": True, "data": str(data_path(unit)), "verified": verdict.ok,
            "legacy": bool(legacy and not verdict.ok), "registered": root is not None}

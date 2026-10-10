"""按 Markdown 正文顺序检查单元图片引用，并准备透明图白底读图副本。"""
from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .image_utils import inline_image_matches
from .paths import find_source_md

_SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
_WHITE_BG_RE = re.compile(r"^__jiaodui-whitebg-[0-9a-f]{16}\.png$")
_HTML_IMAGE_RE = re.compile(r"<img\b[^>]*\bsrc\s*=", re.IGNORECASE)
_FENCE_OPEN_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


def _fenced_regions(text: str) -> list[tuple[int, int]]:
    """围栏代码块的 [start, end) 区间（含首尾围栏行）。

    按行扫描而不是用正则配平，才能正确处理「围栏长度不等」（``` 开、```` 闭）
    与未闭合围栏（一直延伸到文末）。
    """
    regions: list[tuple[int, int]] = []
    offset = 0
    opened: tuple[str, int, int] | None = None  # (围栏字符, 长度, 起始偏移)
    for line in text.split("\n"):
        start = offset
        offset += len(line) + 1
        match = _FENCE_OPEN_RE.match(line)
        if opened is None:
            if match:
                opened = (match.group(1)[0], len(match.group(1)), start)
            continue
        if (match and match.group(1)[0] == opened[0] and len(match.group(1)) >= opened[1]
                and not line[match.end():].strip()):
            regions.append((opened[2], start + len(line)))
            opened = None
    if opened is not None:
        regions.append((opened[2], len(text)))
    return regions


def _mask_code(text: str) -> str:
    """把围栏代码块与行内代码替换为等长空白，保持偏移与行号不变。

    正文里的代码示例（如 `![图](x.png)`）不是真实图片引用，不能参与引用清单、
    缺图判定或 HTML 图片语法检查；等长替换是为了让报错行号仍指向原文位置。
    """
    buf = list(text)

    def blank(start: int, end: int) -> None:
        for index in range(start, end):
            if buf[index] != "\n":
                buf[index] = " "

    for start, end in _fenced_regions(text):
        blank(start, end)

    index, total = 0, len(buf)
    while index < total:
        if buf[index] != "`":
            index += 1
            continue
        run_end = index
        while run_end < total and buf[run_end] == "`":
            run_end += 1
        width = run_end - index
        cursor, close = run_end, -1
        while cursor < total:
            if buf[cursor] == "`":
                end = cursor
                while end < total and buf[end] == "`":
                    end += 1
                if end - cursor == width:
                    close = cursor
                    break
                cursor = end
            else:
                cursor += 1
        if close == -1:
            index = run_end
            continue
        blank(index, close + width)
        index = close + width
    return "".join(buf)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def white_background_path(path: str | Path) -> Path:
    """返回与原图内容绑定的确定性白底路径，不修改原图。"""
    source = Path(path)
    return source.parent / f"__jiaodui-whitebg-{_sha256(source)[:16]}.png"


def _image_summary(path: Path) -> dict:
    """读取图片元数据；不能解码时保留完整失败原因。"""
    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - 环境检查会覆盖依赖缺失
        return {"readable": False, "error": f"Pillow 不可用：{exc}"}
    try:
        with Image.open(path) as image:
            image.load()
            has_alpha = "A" in image.getbands() or "transparency" in image.info
            transparent = False
            if has_alpha:
                if "A" in image.getbands():
                    transparent = image.getchannel("A").getextrema()[0] < 255
                else:
                    transparent = True
            return {
                "readable": True,
                "format": image.format,
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "has_alpha": has_alpha,
                "transparent": transparent,
                "sha256": _sha256(path),
            }
    except Exception as exc:
        return {"readable": False, "error": f"图片无法读取：{exc}", "sha256": _sha256(path)}


def prepare_white_backgrounds(images_dir: str | Path) -> list[dict]:
    """在拆分完成、输入摘要登记前，为透明图片生成白底 PNG。"""
    directory = Path(images_dir)
    if not directory.is_dir():
        return []
    try:
        from PIL import Image
    except Exception:
        return []
    prepared: list[dict] = []
    # 不删除任何文件；旧白底副本由清单忽略，原图始终保留。
    for source in sorted(directory.rglob("*"), key=lambda p: p.as_posix()):
        if not source.is_file() or source.name.startswith("__jiaodui-whitebg-"):
            continue
        if source.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        summary = _image_summary(source)
        if not summary.get("readable") or not summary.get("transparent"):
            continue
        target = white_background_path(source)
        temporary = None
        try:
            with Image.open(source) as image:
                image.load()
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                composited = Image.alpha_composite(background, rgba).convert("RGB")
                with tempfile.NamedTemporaryFile(
                    dir=target.parent, prefix=target.name + ".", suffix=".tmp", delete=False
                ) as handle:
                    temporary = Path(handle.name)
                composited.save(temporary, "PNG")
                check = _image_summary(temporary)
                if (not check.get("readable") or check.get("mode") != "RGB"
                        or check.get("width") != image.width or check.get("height") != image.height):
                    raise ValueError("生成的白底图片校验失败")
                temporary.replace(target)
            prepared.append({"original": str(source.resolve()), "white_background": str(target.resolve())})
        except Exception as exc:
            prepared.append({"original": str(source.resolve()), "white_background": None, "error": str(exc)})
        finally:
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
    return prepared


def _location(text: str, start: int, end: int) -> tuple[int, int, int, int]:
    line = text.count("\n", 0, start) + 1
    line_start = text.rfind("\n", 0, start) + 1
    column = start - line_start + 1
    return line, column, start, end


def _source_summary(text: str, start: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start)
    if line_end < 0:
        line_end = len(text)
    return text[line_start:line_end].strip()[:200]


def _is_remote(path: str) -> bool:
    parsed = urlsplit(path)
    return bool(parsed.scheme) or path.startswith("//")


def _ref_record(text: str, start: int, end: int, alt: str, path: str | None, syntax: str) -> dict:
    line, column, char_start, char_end = _location(text, start, end)
    return {
        "reference_index": 0,
        "sequence": 0,
        "raw_reference": text[start:end],
        "position": {"line": line, "column": column, "char_start": char_start, "char_end": char_end},
        "source_summary": _source_summary(text, start),
        "line": line,
        "column": column,
        "char_start": char_start,
        "char_end": char_end,
        "original_reference_path": path,
        "resolved_original_path": None,
        "original_path": None,
        "actual_read_path": None,
        "read_path": None,
        "file_status": "unresolved" if path is None else "pending",
        "status": "unresolved" if path is None else "pending",
        "image_summary": None,
        "summary": None,
        "alt_text": alt,
        "syntax": syntax,
    }


def _finalize_record(record: dict) -> dict:
    """补齐给宿主使用的稳定别名，避免调用方猜测字段语义。"""
    record["sequence"] = record["reference_index"]
    record["original_path"] = record["resolved_original_path"]
    record["read_path"] = record["actual_read_path"]
    record["status"] = record["file_status"]
    record["summary"] = record["image_summary"]
    return record


def _read_paths(references: list[dict]) -> list[str]:
    """按正文顺序去重的实际读取路径清单，供子 agent 逐字复制调用读图工具。

    路径由拆分阶段决定；子 agent 自行拼接目录层级会指向不存在的文件
    （回放实测：漏掉 `units/<材料名>/` 一层导致 read_image not found）。
    同一文件被多处引用时只列一次，避免宿主重复读同一张图。
    """
    paths: list[str] = []
    for record in references:
        path = record.get("actual_read_path")
        if isinstance(path, str) and path and path not in paths:
            paths.append(path)
    return paths


def inspect_unit_images(unit_dir: str | Path, *, source_path: str | Path | None = None,
                        allow_legacy_transparent: bool = False) -> dict:
    """返回单元图片清单；引用按正文出现位置排序，重复引用不去重。

    `source_path` 显式指定待检查的源文（verify-report --source，闸门复用同一次
    校验的源文）；缺省时才按单元目录约定名回退。两种情况都必须扫同一份源文，
    否则闸门会对着另一份文本放行。
    """
    unit = Path(unit_dir).resolve()
    source = Path(source_path).resolve() if source_path is not None else find_source_md(unit)
    result = {"ok": True, "unit": str(unit), "source": str(source.resolve()) if source else None,
              "references": [], "read_paths": [], "extra_images": [], "errors": [], "warnings": [],
              "supported_syntax": ["![alt](path)"]}
    if source is None or not source.is_file():
        result["ok"] = False
        result["errors"].append({"code": "source_missing", "message": f"找不到单元源文：{unit}"})
        return result
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        result["ok"] = False
        result["errors"].append({"code": "source_unreadable", "message": f"源文读取失败：{exc}"})
        return result

    # 全部扫描都基于屏蔽掉代码跨度后的文本：代码示例里的图片语法不是引用，
    # 既不该进清单，也不该触发「无法解析」或「HTML img」报错。
    from .convert import image_destination

    matches: list[tuple[int, int, str, str, str | None]] = []
    covered: list[tuple[int, int]] = []
    for match in inline_image_matches(text):
        path = image_destination(match.group(2))
        matches.append((match.start(), match.end(), match.group(1), "inline", path))
        covered.append((match.start(), match.end()))
    scan_text = _mask_code(text)

    for marker in re.finditer(r"!\[", scan_text):
        if not any(start <= marker.start() < end for start, end in covered):
            line, column, _, _ = _location(text, marker.start(), marker.start() + 2)
            result["ok"] = False
            result["errors"].append({"code": "unsupported_syntax", "message": "无法解析的 Markdown 图片引用",
                                     "line": line, "column": column})
    for marker in _HTML_IMAGE_RE.finditer(scan_text):
        line, column, _, _ = _location(text, marker.start(), marker.end())
        result["ok"] = False
        result["errors"].append({"code": "unsupported_syntax", "message": "不支持 HTML img 图片语法，请改用 Markdown 图片引用",
                                 "line": line, "column": column})

    seen: dict[str, int] = {}
    for index, (start, end, alt, syntax, raw_path) in enumerate(matches, start=1):
        record = _ref_record(text, start, end, alt, raw_path, syntax)
        record["reference_index"] = index
        record["sequence"] = index
        if raw_path is None:
            record["file_status"] = "invalid_reference"
            result["ok"] = False
            result["errors"].append({"code": "invalid_reference", "message": "图片引用缺少可解析路径",
                                     "reference_index": index, "line": record["line"]})
            result["references"].append(_finalize_record(record))
            continue
        if _is_remote(raw_path):
            record["file_status"] = "remote_unsupported"
            result["ok"] = False
            result["errors"].append({"code": "remote_unsupported", "message": f"不支持远程图片引用：{raw_path}",
                                     "reference_index": index, "line": record["line"]})
            result["references"].append(_finalize_record(record))
            continue
        decoded = unquote(raw_path)
        resolved = (source.parent / decoded).resolve() if not Path(decoded).is_absolute() else Path(decoded).resolve()
        record["resolved_original_path"] = str(resolved)
        record["original_path"] = str(resolved)
        key = str(resolved)
        if key in seen:
            record["duplicate_of"] = seen[key]
        else:
            seen[key] = index
        if not resolved.is_file():
            record["file_status"] = "missing"
            result["ok"] = False
            result["errors"].append({"code": "missing", "message": f"图片文件不存在：{resolved}",
                                     "reference_index": index, "line": record["line"]})
            result["references"].append(_finalize_record(record))
            continue
        if resolved.suffix.lower() not in _SUPPORTED_SUFFIXES:
            record["file_status"] = "unsupported_format"
            result["ok"] = False
            result["errors"].append({"code": "unsupported_format", "message": f"不支持的图片格式：{resolved.suffix}",
                                     "reference_index": index, "line": record["line"]})
            result["references"].append(_finalize_record(record))
            continue
        summary = _image_summary(resolved)
        record["image_summary"] = summary
        record["summary"] = summary
        if not summary.get("readable"):
            record["file_status"] = "unreadable"
            result["ok"] = False
            result["errors"].append({"code": "unreadable", "message": summary.get("error", "图片无法读取"),
                                     "reference_index": index, "line": record["line"]})
            result["references"].append(_finalize_record(record))
            continue
        actual = resolved
        if summary.get("transparent"):
            white = white_background_path(resolved)
            if white.is_file():
                white_summary = _image_summary(white)
                # 白底图才是宿主实际读的那一份，必须独立校验：它坏了等于交给宿主
                # 一张读不开的图，只看原图完好会漏检。
                broken = (not white_summary.get("readable")
                          or white_summary.get("mode") != "RGB"
                          or white_summary.get("width") != summary.get("width")
                          or white_summary.get("height") != summary.get("height"))
                if broken:
                    record["file_status"] = "white_background_unreadable"
                    record["white_background_summary"] = white_summary
                    result["ok"] = False
                    result["errors"].append({
                        "code": "white_background_unreadable",
                        "message": f"白底图无法读取或与原图不一致：{white}",
                        "reference_index": index,
                        "line": record["line"],
                    })
                    result["references"].append(_finalize_record(record))
                    continue
                actual = white
            elif allow_legacy_transparent:
                actual = resolved
                record["file_status"] = "ok_legacy_transparent"
                result["warnings"].append({
                    "code": "white_background_missing",
                    "message": "历史布局透明图片没有白底副本，回退读取原图",
                    "reference_index": index,
                    "line": record["line"],
                })
            else:
                record["file_status"] = "white_background_missing"
                result["ok"] = False
                result["errors"].append({"code": "white_background_missing", "message": "透明图片缺少拆分阶段生成的白底图",
                                         "reference_index": index, "line": record["line"]})
                result["references"].append(_finalize_record(record))
                continue
        record["actual_read_path"] = str(actual.resolve())
        record["read_path"] = str(actual.resolve())
        if record["file_status"] == "pending":
            record["file_status"] = "ok"
        record["status"] = record["file_status"]
        result["references"].append(record)

    image_dir = unit / "images"
    referenced = {r["resolved_original_path"] for r in result["references"] if r.get("resolved_original_path")}
    if image_dir.is_dir():
        for image in sorted(image_dir.rglob("*"), key=lambda p: p.as_posix()):
            if not image.is_file() or _WHITE_BG_RE.match(image.name):
                continue
            if image.suffix.lower() not in _SUPPORTED_SUFFIXES:
                continue
            if str(image.resolve()) not in referenced:
                result["extra_images"].append({"path": str(image.resolve()), "sha256": _sha256(image)})
        if result["extra_images"]:
            result["warnings"].append({"code": "extra_images", "message": "images/ 中存在未被正文引用的图片，未加入读图任务",
                                        "paths": [x["path"] for x in result["extra_images"]]})
    result["read_paths"] = _read_paths(result["references"])
    return result


# CLI 使用 inspect_unit_images；保留简短别名供核心调用方复用。
inspect_images = inspect_unit_images

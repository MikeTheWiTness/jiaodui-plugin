#!/usr/bin/env python3
"""冻结独立标注的候选样本；只做哈希，不生成或改写预期值。"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "revise_ab"
SAMPLE_IDS = [f"physics/S{i}" for i in range(1, 10)] + [f"chemistry/C{i}" for i in range(1, 4)]


def inventory(root: Path) -> dict[str, str]:
    """记录全部载荷，避免漏掉预期、图片或干预描述。"""
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"不允许符号链接：{path.relative_to(root)}")
        if path.is_file() and path != root / "manifest.json":
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def freeze(root: Path) -> None:
    """首次冻结；已有清单时拒绝重写，绝不导入 jiaodui。"""
    manifest = root / "manifest.json"
    if manifest.exists():
        raise ValueError("manifest.json 已存在，拒绝重写冻结清单")
    observed = sorted(p.parent.relative_to(root).as_posix() for p in root.rglob("expected.json"))
    if observed != sorted(SAMPLE_IDS):
        raise ValueError("必须独立提供9个物理及3个化学 expected.json")
    for sample in SAMPLE_IDS:
        folder = root / sample
        if not (folder / "source.md").is_file():
            raise ValueError(f"缺少源文：{sample}/source.md")
        expected = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
        if expected.get("sample_id") != sample:
            raise ValueError(f"标注身份不匹配：{sample}")
    payload = {"schema_version": 1, "status": "frozen-candidate", "samples": SAMPLE_IDS,
               "algorithm": "sha256", "files": inventory(root)}
    # x 模式防止并发冻结覆盖；唯一允许创建的标注相关文件是清单。
    with manifest.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def check(root: Path) -> None:
    """只读比较文件集和每个文件的SHA-256；不自动修正清单。"""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("schema_version") != 1 or manifest.get("algorithm") != "sha256"
            or manifest.get("status") != "frozen-candidate" or manifest.get("samples") != SAMPLE_IDS):
        raise ValueError("冻结清单元数据不符合候选样本契约")
    frozen = manifest["files"]
    current = inventory(root)
    errors = [f"缺少文件：{p}" for p in sorted(frozen.keys() - current.keys())]
    errors += [f"新增未冻结文件：{p}" for p in sorted(current.keys() - frozen.keys())]
    errors += [f"SHA-256不匹配：{p}" for p in sorted(frozen.keys() & current.keys())
               if frozen[p] != current[p]]
    if errors:
        raise ValueError("\n".join(errors))


def synthetic_png(segments: list[tuple[int, int, int, int]]) -> bytes:
    """纯整数线段绘制的白底示意图，不依赖字体、渲染器或真实实验材料。"""
    width, height = 240, 180
    pixels = bytearray(b"\xff" * (width * height * 3))
    for x0, y0, x1, y1 in segments:
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = 1 if x0 < x1 else -1, 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            for y in range(max(0, y0 - 2), min(height, y0 + 3)):
                for x in range(max(0, x0 - 2), min(width, x0 + 3)):
                    index = (y * width + x) * 3
                    pixels[index:index + 3] = b"\x00\x00\x00"
            if x0 == x1 and y0 == y1:
                break
            twice = 2 * err
            if twice >= dy:
                err += dy
                x0 += sx
            if twice <= dx:
                err += dx
                y0 += sy
    scanlines = b"".join(b"\x00" + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(scanlines, level=0)) + chunk(b"IEND", b""))


def write_images(root: Path) -> None:
    """冻结前的一次性图片制备入口，拒绝覆盖已有文件。"""
    drawings = {
        "physics/S5/images/a.png": [(30, 125, 45, 85), (45, 85, 60, 125), (36, 110, 54, 110),
                                     (85, 90, 205, 90), (205, 90, 175, 65), (205, 90, 175, 115)],
        "physics/S5/images/b.png": [(25, 70, 25, 115), (25, 70, 48, 70), (48, 70, 58, 82),
                                     (58, 82, 48, 92), (25, 92, 48, 92), (48, 92, 58, 104),
                                     (58, 104, 48, 115), (25, 115, 48, 115),
                                     (155, 145, 155, 35), (155, 35, 130, 65), (155, 35, 180, 65)],
        "chemistry/C2/images/container.png": [(65, 40, 65, 145), (65, 145, 175, 145),
                                                (175, 145, 175, 40), (100, 75, 140, 115),
                                                (100, 115, 140, 75)],
    }
    if (root / "manifest.json").exists():
        raise ValueError("已冻结，拒绝生成图片")
    if any((root / name).exists() for name in drawings):
        raise ValueError("图片已存在，拒绝覆盖")
    for name, segments in drawings.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(synthetic_png(segments))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--freeze", action="store_true", help="首次冻结已有原文、预期、说明与图片")
    mode.add_argument("--check", action="store_true", help="只读校验（默认）")
    mode.add_argument("--write-synthetic-images", action="store_true", help="冻结前生成3张确定性合成示意图")
    args = parser.parse_args()
    try:
        if args.freeze:
            freeze(args.root)
        elif args.write_synthetic_images:
            write_images(args.root)
        else:
            check(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("合成图片已生成" if args.write_synthetic_images else "冻结候选样本通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

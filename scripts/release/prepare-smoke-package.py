from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

# 已落地的学科插件包：一次发布同时带全部包，目标机只装其中需要的一个。
BUNDLE_PACKAGES = ("dsh-jiaodui", "dsh-jiaodui-chemistry")


def _versions(root: Path) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    for package in BUNDLE_PACKAGES:
        bundle = json.loads(
            (root / "packages" / package / "package.json").read_text(encoding="utf-8")
        )
        if project["version"] != bundle["version"]:
            raise SystemExit(
                f"Python CLI 与 DSH bundle 版本不一致：{project['version']} / "
                f"{package} {bundle['version']}"
            )
    return project["version"]


def _tracked_bundle_files(root: Path, package: str) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", f"packages/{package}"],
        check=True,
        capture_output=True,
    )
    return [Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]


def prepare(root: Path, wheel: Path, output: Path) -> Path:
    version = _versions(root)
    expected_wheel = f"jiaodui-{version}-py3-none-any.whl"
    if wheel.name != expected_wheel or not wheel.is_file():
        raise SystemExit(f"wheel 名称/文件不匹配，期望 {expected_wheel}：{wheel}")
    if output.exists():
        raise SystemExit(f"冒烟发布目录已存在，拒绝覆盖：{output}")

    output.mkdir(parents=True)
    for package in BUNDLE_PACKAGES:
        for relative in _tracked_bundle_files(root, package):
            source = root / relative
            if not source.is_file():
                raise SystemExit(f"bundle 跟踪文件缺失：{source}")
            destination = output / package / relative.relative_to(f"packages/{package}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

    release_scripts = root / "scripts" / "release"
    for filename in (
        expected_wheel,
        "runtime-constraints.txt",
        "install-macos.sh",
        "install-windows.ps1",
        "README.md",
    ):
        source = wheel if filename == expected_wheel else release_scripts / filename
        if not source.is_file():
            raise SystemExit(f"发布冒烟输入缺失：{source}")
        shutil.copyfile(source, output / filename)

    manifest = []
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.append(f"{digest}  {path.relative_to(output).as_posix()}\n")
    (output / "SHA256SUMS").write_text("".join(manifest), encoding="utf-8", newline="\n")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="准备当前平台的最终 CLI 安装冒烟目录")
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    default_output = Path(os.environ.get("RUNNER_TEMP", sys_temp_dir())) / "jiaodui-release-smoke"
    output = (args.output or default_output).resolve()
    repository = args.repository.resolve()
    wheel = args.wheel.resolve() if args.wheel else None
    if wheel is None:
        version = _versions(repository)
        candidates = list((repository / "dist").glob(f"jiaodui-{version}-py3-none-any.whl"))
        if len(candidates) != 1:
            raise SystemExit(f"dist 中期望唯一的 jiaodui-{version}-py3-none-any.whl，找到 {len(candidates)} 个")
        wheel = candidates[0]
    prepare(repository, wheel, output)
    print(output)
    return 0


def sys_temp_dir() -> str:
    import tempfile

    return tempfile.gettempdir()


if __name__ == "__main__":
    raise SystemExit(main())

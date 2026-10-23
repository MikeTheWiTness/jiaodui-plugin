"""release 构建脚本的解释器选择与失败路径。"""
from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "release" / "build-release.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="需要 bash")


def _version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_build_release_script_has_valid_syntax():
    result = subprocess.run([BASH, "-n", str(SCRIPT)], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_build_release_rejects_explicit_python_without_build(tmp_path):
    """显式 PYTHON 不满足 build/pip 时必须在构建前失败，而不是抛 No module named build。"""
    env = {**os.environ, "PYTHON": str(tmp_path / "missing-python")}
    result = subprocess.run([BASH, str(SCRIPT)], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 3
    assert "不可用于构建" in result.stderr
    assert "build 与 pip" in result.stderr


def test_build_release_auto_selects_build_capable_python(tmp_path):
    """不设 PYTHON 时也必须选中带 build 的解释器；用已存在归档让脚本在构建前停下。"""
    release = tmp_path / "release"
    release.mkdir()
    (release / f"dsh-jiaodui-{_version()}.tar.gz").write_bytes(b"placeholder")
    env = {**os.environ, "JIAODUI_RELEASE_DIR": str(release)}
    env.pop("PYTHON", None)
    result = subprocess.run([BASH, str(SCRIPT)], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=30)
    assert "使用构建解释器" in result.stderr
    assert result.returncode == 2
    assert "发布文件已存在" in result.stderr

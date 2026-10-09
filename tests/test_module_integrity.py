"""工作树完整性：本包内的相对导入必须指向本包内真实存在的模块。

背景（2026-10-09 P5 实测）：`.venv` 的 editable 安装指向根仓 main，于是**只有 main
才有的模块**（如 `jiaodui.execution_policy`）在实验 worktree 里也能 import 成功 —
报错路径指向根仓文件，把排查方向带偏；更糟的是会静默读到另一条线的代码。

这条守卫把「本包不得依赖自己目录里没有的模块」钉死，避免两条线共用同一 venv 时混用。
相对导入按**声明它的文件所在目录**解析，因此 `jiaodui/calc/*.py` 里的 `from .sandbox`
算同目录模块，不会被误判。
"""
from __future__ import annotations

import re
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "jiaodui"


def test_relative_imports_resolve_inside_the_package():
    missing: dict[str, list[str]] = {}
    for source_file in PKG.rglob("*.py"):
        directory = source_file.parent
        siblings = {path.stem for path in directory.glob("*.py")}
        subpackages = {path.name for path in directory.iterdir()
                       if path.is_dir() and (path / "__init__.py").is_file()}
        text = source_file.read_text(encoding="utf-8")
        referenced = set(re.findall(r"from \.(\w+) import", text))
        referenced |= set(re.findall(r"from \.(\w+)\.", text))
        unknown = sorted(referenced - siblings - subpackages - {"__init__"})
        if unknown:
            missing[str(source_file.relative_to(PKG))] = unknown
    assert not missing, f"相对导入了本包不存在的模块：{missing}"

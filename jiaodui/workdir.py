"""工作区授权与真实路径边界；会话工作区由宿主显式注入。"""
from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .errors import BusinessError

_workspace: ContextVar[Path | None] = ContextVar("jiaodui_workspace", default=None)


def workspace_root(required: bool = True) -> Path | None:
    root = _workspace.get()
    value = os.environ.get("JIAODUI_WORK_ROOT")
    if root is None and value:
        root = Path(value).expanduser()
    if root is None:
        if not required:
            return None
        raise BusinessError("写入需要当前会话工作区或 --work-root", code="workspace-required")
    if not root.is_absolute():
        raise BusinessError("工作区根必须是绝对路径", code="workspace-required")
    return root.resolve()


@contextmanager
def workspace_scope(root: str | Path | None):
    """CLI 只透传工作区；ContextVar 隔离同进程并发调用。"""
    token = _workspace.set(Path(root).expanduser() if root else None)
    try:
        yield
    finally:
        _workspace.reset(token)


def input_path(path: str | Path) -> Path:
    """相对输入按显式工作区解析；独立只读调用仍可使用当前目录。"""
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = (workspace_root(required=False) or Path.cwd()) / path
    return path.resolve()


def ensure_inside(path: str | Path) -> Path:
    """校验实际待写路径，不允许通过符号链接逃出工作区。"""
    root = workspace_root()
    path = Path(path).expanduser()
    resolved = (path if path.is_absolute() else root / path).resolve()
    if not resolved.is_relative_to(root):
        raise BusinessError("校对产物不能写入当前工作区之外", code="outside-workspace",
                            details={"resolved_path": str(resolved), "work_root": str(root)})
    return resolved


def ensure_tree(path: str | Path) -> Path:
    """子进程可能写目录中的现存文件；提交前检查其全部目的地。"""
    path = ensure_inside(path)
    if path.is_dir():
        for child in path.rglob("*"):
            ensure_inside(child)
    return path

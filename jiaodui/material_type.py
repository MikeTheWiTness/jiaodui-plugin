"""解析宿主给出的材料类型及来源；不在 Python 中做语义分类。"""
from __future__ import annotations

from .errors import BusinessError, UsageError

MODES = {"lecture", "exam"}
ORIGINS = {"user", "structure", "preview", "confirmed"}


def validate_selection(selection: dict) -> None:
    if (not isinstance(selection, dict) or set(selection) != {"mode", "origin", "reason"}
            or not isinstance(selection["mode"], str) or selection["mode"] not in MODES
            or not isinstance(selection["origin"], str) or selection["origin"] not in ORIGINS
            or not isinstance(selection["reason"], str) or len(selection["reason"]) > 500):
        raise BusinessError("材料类型记录无效", code="invalid-manifest")


def resolve_selection(mode: str | None, saved: dict | None = None, *,
                      origin: str | None = None, reason: str | None = None,
                      required: bool = True) -> dict | None:
    """显式类型优先；缺失时复用材料记录；新布局禁止猜默认类型。"""
    if saved is not None:
        validate_selection(saved)
    if mode is not None and (not isinstance(mode, str) or mode not in MODES):
        raise UsageError("材料类型必须为 exam 或 lecture")
    if origin is not None and (not isinstance(origin, str) or origin not in ORIGINS):
        raise UsageError("类型来源必须为 user / structure / preview / confirmed")
    if reason is not None and (not isinstance(reason, str) or len(reason) > 500):
        raise UsageError("类型判断理由不能超过 500 字符")
    if mode is None and (origin is not None or reason is not None):
        raise UsageError("--mode-origin / --mode-reason 需要显式 --mode")
    if mode is not None:
        # 重复传相同 mode 不抹掉最初的判断来源；显式给来源则记录新的用户决定。
        if saved is not None and mode == saved["mode"] and origin is None and reason is None:
            return dict(saved)
        return {"mode": mode, "origin": origin or "user", "reason": reason or ""}
    if saved is not None:
        return dict(saved)
    if required:
        raise BusinessError("材料类型尚未确定：请按用户指定，或先 inspect-source；不确定时询问用户，再传 --mode exam|lecture",
                            code="mode-required")
    return None

"""结构化错误与稳定退出码。

契约：任何命令失败时，都向 stderr 输出一行 JSON：
    {"ok": false, "error": {"code": "...", "message": "...", "details": {...}}}
人类可读说明在前，机器可读细节在 details；调用方据 code 与退出码判断类别。
"""
from __future__ import annotations

import json
import sys
from typing import Any


class ExitCode:
    """稳定的进程退出码（脚本可依赖）。"""

    OK = 0
    UNEXPECTED = 1
    USAGE = 2
    ENV = 3
    VERIFY_FAILED = 4
    NOT_FOUND = 5
    CONTRACT = 6
    UNSUPPORTED = 7


class JiaoduiError(Exception):
    """所有预期内失败的基类：携带机器可读 code 与退出码。"""

    code = "error"
    exit_code = ExitCode.UNEXPECTED

    def __init__(self, message: str, *, details: dict[str, Any] | None = None,
                 location: str | None = None):
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}
        self.location = location

    def to_dict(self) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.location:
            err["location"] = self.location
        if self.details:
            err["details"] = self.details
        return {"ok": False, "error": err}


class UsageError(JiaoduiError):
    code = "usage"
    exit_code = ExitCode.USAGE


class EnvError(JiaoduiError):
    code = "env"
    exit_code = ExitCode.ENV


class NotFoundError(JiaoduiError):
    code = "not_found"
    exit_code = ExitCode.NOT_FOUND


class ContractError(JiaoduiError):
    """产物不满足契约（解析/状态层面），与 verify-report 的校验失败区分。"""

    code = "contract"
    exit_code = ExitCode.CONTRACT


class UnsupportedError(JiaoduiError):
    code = "unsupported"
    exit_code = ExitCode.UNSUPPORTED


class VerifyFailedError(JiaoduiError):
    """verify-report 判定的业务失败（退出码 4）。"""

    code = "verify_failed"
    exit_code = ExitCode.VERIFY_FAILED


class BusinessError(JiaoduiError):
    """通用业务失败：调用方指定 code 与退出码，统一走 stderr JSON 出口。"""

    def __init__(self, message: str, *, code: str = "contract",
                 exit_code: int = ExitCode.CONTRACT,
                 details: dict[str, Any] | None = None, location: str | None = None):
        super().__init__(message, details=details, location=location)
        self.code = code
        self.exit_code = exit_code


def emit_error(exc: BaseException) -> int:
    """把异常输出为一行 JSON 到 stderr，返回退出码。"""
    if isinstance(exc, JiaoduiError):
        payload = exc.to_dict()
        code = exc.exit_code
    else:
        payload = {"ok": False, "error": {"code": "unexpected", "message": str(exc)}}
        code = ExitCode.UNEXPECTED
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr, flush=True)
    return code

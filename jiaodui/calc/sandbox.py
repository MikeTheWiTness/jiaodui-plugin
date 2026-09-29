"""SymPy 代码执行沙箱。

移植自旧仓 shared/sympy_tools/sandbox.py，去掉 PyInstaller 打包分支：
旧仓在 GUI exe 下回退为进程内执行，新仓只保留「隔离子进程 + 超时 kill」这一条路径。

安全双保险：
- 静态：check_dangerous() 在生成代码进入子进程前拦截危险模式；
- 动态：子进程以受限 builtins 执行（去掉 exec/eval/compile/open/input 等）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from .safety import check_dangerous


def _run_in_subprocess(code: str, timeout: int) -> dict:
    """在隔离子进程中执行 SymPy 代码（stdin 传码，避免命令行长度限制）。"""
    start = time.monotonic()
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        restricted_code = (
            "import builtins, sys\n"
            "_allowed = {k:v for k,v in builtins.__dict__.items() "
            "if k not in ('exec','eval','compile','open','input','breakpoint','memoryview')}\n"
            "_allowed['__build_class__'] = __build_class__\n"
            "exec(sys.stdin.read(), {'__builtins__': _allowed, '__name__': '__main__'})\n"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", restricted_code],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True, encoding="utf-8", errors="replace",
        )
        try:
            stdout, stderr = proc.communicate(input=code, timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            elapsed = int((time.monotonic() - start) * 1000)
            return {
                "success": False, "result": None,
                "error": f"Execution timed out ({timeout}s)",
                "code": code, "elapsed_ms": elapsed,
            }

        elapsed = int((time.monotonic() - start) * 1000)

        if proc.returncode != 0:
            return {
                "success": False, "result": None,
                "error": stderr.strip() or "Unknown subprocess error",
                "code": code, "elapsed_ms": elapsed,
            }

        result = json.loads(stdout.strip())
        return {
            "success": True, "result": result,
            "error": None, "code": code, "elapsed_ms": elapsed,
        }
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return {
            "success": False, "result": None,
            "error": str(e), "code": code, "elapsed_ms": elapsed,
        }


def execute_code(code: str, timeout: int = 30) -> dict:
    """在隔离环境中执行 SymPy 代码，返回结构化结果。

    返回体固定为 {"success", "result", "error", "code", "elapsed_ms"}。
    code 字段必须原样保留（issue 058）：上层「投影」时按需裁剪，沙箱内不裁剪。
    """
    danger = check_dangerous(code)
    if danger:
        return {
            "success": False, "result": None,
            "error": danger, "code": code, "elapsed_ms": 0,
        }

    return _run_in_subprocess(code, timeout)

"""jiaodui.calc —— 符号计算沙箱子包（移植自旧仓 shared/sympy_tools）。

去掉 langchain_core / pydantic / LLM 依赖，只保留：
- safety.check_dangerous  ：危险代码静态拦截
- sandbox.execute_code    ：隔离子进程执行 + 超时 kill
- templates.build_code    ：14 种 operation 的代码生成
- chemistry               ：摩尔质量数据库 + 化学式解析（单一源）
- operations.OPERATIONS / run_operation：替代旧仓 BaseTool 的统一入口

公开 API：
    OPERATIONS: dict[str, dict]
    run_operation(operation: str, **params) -> dict
"""
from __future__ import annotations

from .chemistry import _MOLAR_MASSES, parse_chemical_formula
from .operations import OPERATIONS, run_operation
from .sandbox import execute_code
from .safety import check_dangerous
from .templates import build_code, json_repr

__all__ = [
    "OPERATIONS",
    "run_operation",
    "execute_code",
    "build_code",
    "json_repr",
    "check_dangerous",
    "_MOLAR_MASSES",
    "parse_chemical_formula",
]

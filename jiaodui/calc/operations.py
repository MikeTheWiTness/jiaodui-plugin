"""符号计算操作注册表与统一执行入口。

替代旧仓 shared/sympy_tools/tools.py 中的 langchain BaseTool 包装（去掉
langchain_core / pydantic 依赖）：旧仓每个工具对应这里 OPERATIONS 中的一条
operation 元数据，run_operation 直接返回沙箱的结构化 dict。

公开契约：
- OPERATIONS: dict[str, dict]  —— 每个 operation 的元数据（params/summary）
- run_operation(operation, **params) -> dict
  返回体逐字保留旧仓沙箱形态：{"success", "result", "error", "code", "elapsed_ms"}。
  code 字段必须保留（issue 058），由上层「投影」裁剪，calc 内不裁剪。
"""
from __future__ import annotations

import re as _re
from typing import Any, Callable

from .chemistry import _MOLAR_MASSES
from .sandbox import execute_code
from .templates import build_code

__all__ = ["OPERATIONS", "run_operation"]


def _p(name: str, required: bool, type_: str, default: Any, help_: str) -> dict[str, Any]:
    """构造一个参数元数据条目（name/required/type/default/help）。"""
    return {
        "name": name,
        "required": required,
        "type": type_,
        "default": default,
        "help": help_,
    }


# ---- 14 种 operation（operation 名与旧仓完全一致） ----

OPERATIONS: dict[str, dict] = {
    "evaluate": {
        "summary": "求值一个符号数学表达式，可选代入变量后进行数值计算。",
        "params": [
            _p("expression", True, "str", None,
               "待求值的数学表达式，如 '2*x + 3*y' 或 'sqrt(u**2 + 2*a*s)'"),
            _p("substitutions", False, "dict", {},
               "变量替换映射，如 {'x': 2, 'y': 'pi/2'}；字符串值先经 sympify 解析"),
        ],
    },
    "simplify": {
        "summary": "对表达式化简、展开、因式分解或三角化简。",
        "params": [
            _p("expression", True, "str", None,
               "待化简/展开的表达式，如 '(x+1)**2' 或 'sin(x)**2 + cos(x)**2'"),
            _p("method", False, "str", "simplify",
               "操作类型：simplify / expand / factor / trigsimp"),
        ],
    },
    "solve": {
        "summary": "求解一个或多个方程（等号形式或设为 0 的表达式）。",
        "params": [
            _p("equations", True, "list[str]", None,
               "方程列表，如 ['x**2 - 4 = 0'] 或 ['x + y - 5']"),
            _p("variables", True, "list[str]", None,
               "求解的变量列表，如 ['x'] 或 ['x', 'y']"),
            _p("domain", False, "str", "real",
               "求解域：'real'（默认，剔除复数根）或 'complex'"),
        ],
    },
    "equality": {
        "summary": "检查两个数学表达式是否等价（simplify(a-b)==0 加浮点容差）。",
        "params": [
            _p("expression_a", True, "str", None,
               "第一个表达式，如 'sin(x)**2 + cos(x)**2'"),
            _p("expression_b", True, "str", None,
               "第二个表达式，如 '1'"),
        ],
    },
    "differentiate": {
        "summary": "对表达式求（高阶）导数。",
        "params": [
            _p("expression", True, "str", None,
               "被求导的表达式，如 'x**3 + 2*x'"),
            _p("variable", False, "str", "x", "求导变量名，如 'x'"),
            _p("order", False, "int", 1, "求导阶数（正整数）"),
            _p("substitutions", False, "dict", {},
               "求导后代入的变量映射（模板契约保留；旧仓未在求导前展开）"),
        ],
    },
    "integrate": {
        "summary": "对表达式求不定积分或定积分。",
        "params": [
            _p("expression", True, "str", None,
               "被积表达式，如 'x**2'"),
            _p("variable", False, "str", "x", "积分变量名，如 'x'"),
            _p("lower_limit", False, "str", None,
               "定积分下限表达式（与 upper_limit 同时给出时才做定积分），如 '0'"),
            _p("upper_limit", False, "str", None,
               "定积分上限表达式，如 'pi/2'"),
        ],
    },
    "formula": {
        "summary": "从物理公式中解出目标变量，可选代入已知数值。",
        "params": [
            _p("formula", True, "str", None,
               "物理公式（等号形式），如 'v = u + a*t' 或 'E = 1/2 * m * v**2'"),
            _p("solve_for", True, "str", None, "要解出的目标变量名，如 'a' 或 'v'"),
            _p("substitutions", False, "dict", {},
               "已知量数值映射，如 {'v': 20, 'u': 0, 't': 5}"),
        ],
    },
    "dimensional": {
        "summary": "量纲分析：等号两侧一致性 / 提取量纲 / 单位换算。",
        "params": [
            _p("expression", True, "str", None,
               "物理表达式，如 'F = m * a' 或 'F = B**2*L**2*v/(R+r)'"),
            _p("dim_operation", False, "str", "check_consistency",
               "操作：check_consistency / get_dimensions / convert"),
            _p("unit_definitions", True, "dict", None,
               "表达式里每个符号的单位声明，如 {'F': 'newton', 'L': 'meter'}；"
               "无量纲量声明为 'dimensionless'；歧义符号用候选列表 "
               "{'V': ['meter/second', 'meter**3']}"),
            _p("target_units", False, "str", "",
               "目标单位表达式，仅 dim_operation='convert' 时使用，如 'kilometer / hour'"),
        ],
    },
    "limit": {
        "summary": "计算表达式的极限（双侧或单侧）。",
        "params": [
            _p("expression", True, "str", None, "求极限的表达式，如 'sin(x)/x'"),
            _p("variable", True, "str", None, "趋近变量，如 'x'"),
            _p("approach", True, "str", None, "趋近值，如 '0' 或 'oo'"),
            _p("direction", False, "str", "+-", "方向：'+' 右极限，'-' 左极限，'+-' 双侧"),
        ],
    },
    "geometry": {
        "summary": "几何构造与测量（点、线、圆、垂线、中点、距离、夹角、交点）。",
        "params": [
            _p("expression", True, "str", None,
               "几何表达式，可链式调用，如 "
               "'Point(0,0).distance(Point(3*h,4*h))' 或 "
               "'Circle(Point(0,0), 5).intersection(Line(Point(-10,3), Point(10,3)))'"),
        ],
    },
    "vector_ops": {
        "summary": "向量运算：点积、叉积（2D/3D）、夹角、投影。",
        "params": [
            _p("vector_operation", True, "str", None,
               "向量操作：'dot' / 'cross' / 'angle' / 'projection'"),
            _p("vec_a", True, "list[float]", None, "向量 A 的坐标，如 [1, 2, 3]"),
            _p("vec_b", True, "list[float]", None, "向量 B 的坐标，如 [4, 5, 6]"),
        ],
    },
    "circle_from_two_points": {
        "summary": "由两点及其方向/法向量求解圆的圆心与半径。",
        "params": [
            _p("entry_point", True, "list[str]", None,
               "第一个点的坐标，如 ['1.5*h', 'h']（支持符号表达式）"),
            _p("velocity_direction", True, "list[float]", None,
               "第一个点处的方向向量（切线方向），如 [3, 4]（无需归一化）"),
            _p("impact_point", True, "list[str]", None,
               "第二个点的坐标，如 ['0', '-1.5*h']"),
            _p("impact_normal", True, "list[float]", None,
               "第二个点处的法向量，如 [0, 1]"),
        ],
    },
    "chemistry_balance": {
        "summary": "配平化学方程式（原子守恒矩阵求零空间）。",
        "params": [
            _p("equation", True, "str", None,
               "待配平的化学方程式，用 -> 分隔，如 'Fe + O2 -> Fe2O3'"),
        ],
    },
    "stoichiometry": {
        "summary": "由已配平方程式与一种物质质量计算另一种物质的质量。",
        "params": [
            _p("balanced_equation", True, "str", None,
               "已配平的化学方程式，如 '2H2 + O2 -> 2H2O'"),
            _p("known_substance", True, "str", None, "已知质量的物质化学式，如 'H2'"),
            _p("known_mass", True, "float", None, "已知物质的质量，单位克(g)，如 4.0"),
            _p("target_substance", True, "str", None, "待求质量的物质化学式，如 'H2O'"),
        ],
    },
}


# ---- 参数类型校验 ----

_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "str": lambda v: isinstance(v, str),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "dict": lambda v: isinstance(v, dict),
    "list[str]": lambda v: isinstance(v, list) and all(isinstance(x, str) for x in v),
    "list[float]": lambda v: (
        isinstance(v, list)
        and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)
    ),
}


def _fail(message: str) -> dict:
    """构造与沙箱一致的五键失败返回体（校验阶段失败，code 为空）。"""
    return {
        "success": False, "result": None,
        "error": message, "code": "", "elapsed_ms": 0,
    }


def _validate_params(operation: str, meta: dict, params: dict) -> str | None:
    """校验必填与类型，返回可读错误信息；通过则返回 None。"""
    for spec in meta["params"]:
        name = spec["name"]
        if name not in params or params[name] is None:
            if spec["required"]:
                return f"operation '{operation}' 缺少必填参数 '{name}'"
            continue
        check = _TYPE_CHECKS.get(spec["type"])
        if check is not None and not check(params[name]):
            actual = type(params[name]).__name__
            return (
                f"operation '{operation}' 参数 '{name}' 类型错误："
                f"期望 {spec['type']}，实际 {actual}"
            )
    return None


def _effective_params(meta: dict, params: dict) -> dict:
    """按元数据补齐默认值，只保留已声明的参数。"""
    return {spec["name"]: params.get(spec["name"], spec["default"]) for spec in meta["params"]}


# ---- stoichiometry 专用：先解析方程式再生成沙箱代码 ----

_COEFF_PAT = _re.compile(r"^\s*(\d*)\s*([A-Za-z0-9()]+)\s*$")


def _parse_side(side: str) -> list[tuple[int, str]]:
    """解析方程式一侧，返回 [(系数, 化学式), ...]。"""
    out: list[tuple[int, str]] = []
    for part in side.split("+"):
        part = part.strip()
        m = _COEFF_PAT.match(part)
        if m:
            coeff = int(m.group(1)) if m.group(1) else 1
            out.append((coeff, m.group(2)))
    return out


def _build_stoichiometry(eff: dict) -> dict:
    """旧仓 StoichiometryCalcTool._run 的纯函数版：返回五键返回体。"""
    balanced_equation = eff["balanced_equation"]
    sides = balanced_equation.split("->")
    if len(sides) != 2:
        return _fail("方程式格式错误，需要用 -> 分隔")

    reactants = _parse_side(sides[0])
    products = _parse_side(sides[1])
    reactant_coeffs = [c for c, _ in reactants]
    product_coeffs = [c for c, _ in products]
    reactant_formulas = [f for _, f in reactants]
    product_formulas = [f for _, f in products]
    all_formulas = reactant_formulas + product_formulas
    missing = [f for f in all_formulas if f not in _MOLAR_MASSES]
    if missing:
        return _fail(
            f"以下物质的摩尔质量不在内置数据库中: {', '.join(missing)}。暂不支持此计算。"
        )

    code = build_code(
        "stoichiometry",
        known_substance=eff["known_substance"],
        target_substance=eff["target_substance"],
        known_mass=eff["known_mass"],
        reactants=reactant_formulas,
        products=product_formulas,
        reactant_coeffs=reactant_coeffs,
        product_coeffs=product_coeffs,
        molar_masses={f: _MOLAR_MASSES[f] for f in all_formulas},
    )
    return execute_code(code)


# ---- 统一执行入口 ----


def run_operation(operation: str, **params) -> dict:
    """执行一个 operation，返回旧仓沙箱形态的结构化 dict。

    返回体固定包含 success/result/error/code/elapsed_ms 五个字段；其中 code
    原样保留生成/执行的代码（issue 058），裁剪交由上层「投影」完成。

    校验失败（未知 operation、缺必填参数、类型错误、参数自带业务错误）统一返回
    success=False 且 error 为可读中文/英文说明，绝不抛裸异常给调用方。
    """
    meta = OPERATIONS.get(operation)
    if meta is None:
        return _fail(f"Unknown operation type: {operation}")

    error = _validate_params(operation, meta, params)
    if error is not None:
        return _fail(error)

    eff = _effective_params(meta, params)

    try:
        if operation == "stoichiometry":
            return _build_stoichiometry(eff)
        code = build_code(operation, **eff)
    except Exception as e:  # build_code 抛出（如未知 operation 内部子操作）也结构化返回
        return _fail(str(e))

    return execute_code(code)

import json
from string import Template

_SAFE_IMPORTS = """\
import json
from sympy import Symbol, symbols, expand, simplify, sqrt, pi, oo, I
from sympy import sin, cos, tan, log, exp, factorial, Rational
from sympy import Matrix, Piecewise, solveset, solve, Eq, limit, diff, integrate
from sympy import factor, trigsimp, together, apart, S
from sympy import Float, Integer, Max, Min, asin, acos, atan, cot, sinh, cosh, tanh, Abs, floor, ceiling
from sympy.geometry import Point, Line, Circle, intersection
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication
import sympy as _sp
E = Symbol('E')
_LOCALS = dict(locals())
# local 语境优先于白名单，剔除会劫持物理符号的全局名（I 虚数单位、S 单例注册器）
for _bad in ('I', 'S'):
    _LOCALS.pop(_bad, None)
_transforms = standard_transformations + (implicit_multiplication,)

# 数学语境白名单：仅数学函数/常量可解析，防止 sympy 全局名（I 虚数单位、S、O、beta、gamma 等）劫持物理符号
_MATH_GLOBALS = {n: v for n, v in globals().items() if n in (
    'pi', 'oo', 'Rational', 'Float', 'Integer', 'Max', 'Min', 'sin', 'cos', 'tan', 'cot',
    'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh', 'log', 'exp', 'sqrt', 'Abs', 'floor',
    'ceiling', 'factorial', 'E', 'Symbol', 'symbols', 'Matrix', 'Piecewise', 'Point', 'Line',
    'Circle', 'intersection')}

def _safe_sympify(expr_str, local_dict=None):
    return parse_expr(expr_str, local_dict=local_dict, global_dict=_MATH_GLOBALS, transformations=_transforms)
"""

_SERIALIZER = """
def _serialize(obj):
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        # 消除 IEEE 754 噪声：将浮点数舍入到 12 位有效数字
        # 如 0.25600000000000006 → 0.256
        if abs(obj) >= 1e-12:
            rounded = round(obj, 12)
            # 仅当舍入前后差异在容差内才取舍入值（避免对真正的无理数产生误差）
            if abs(obj - rounded) < 1e-10 * max(1, abs(obj)):
                return rounded
        return obj
    if isinstance(obj, int):
        return obj
    if obj is _sp.S.true:
        return True
    if obj is _sp.S.false:
        return False
    if obj is _sp.S.NaN or obj is None:
        return None
    if hasattr(obj, 'is_number') and obj.is_number and obj is not _sp.oo and obj is not -_sp.oo:
        try:
            val = float(obj)
            # 消除 IEEE 754 噪声
            if abs(val) >= 1e-12:
                rounded = round(val, 12)
                if abs(val - rounded) < 1e-10 * max(1, abs(val)):
                    return rounded
            return val
        except (TypeError, ValueError, OverflowError) as _e:
            # 无穷（zoo/oo）与虚数结果不能静默降级为普通字符串（"zoo"/"I" 会让模型误读）
            if obj.is_infinite:
                return f"未定义（无穷大：{obj}）"
            if hasattr(obj, 'has') and obj.has(_sp.I):
                try:
                    _c = complex(obj)
                    if abs(_c.imag) > 1e-12:
                        _sign = '+' if _c.imag >= 0 else '-'
                        return f"{_c.real:g}{_sign}{abs(_c.imag):g}i"
                except Exception:
                    pass
            return str(obj)
    if isinstance(obj, _sp.MatrixBase):
        return [[_serialize(obj[i, j]) for j in range(obj.cols)] for i in range(obj.rows)]
    if isinstance(obj, _sp.Piecewise):
        return [{"expr": _serialize(e), "cond": _serialize(c)} for e, c in obj.args]
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    return str(obj)

output = _serialize(result)
print(json.dumps(output, ensure_ascii=False))
"""

_DIM_BODY = (
    _SAFE_IMPORTS
    + "from sympy.physics.units import *\n"
    + "from sympy.physics.units import convert_to\n"
    + "from sympy.physics.units.quantities import Quantity, PhysicalConstant\n"
    + "from sympy.physics.units.systems.si import dimsys_SI\n"
    + "from sympy.physics.units.systems.si import dimsys_SI\n"
    + "from itertools import product\n"
    + "\n"
    + "# 单位语境只用于解析单位字符串（单位名/缩写），绝不注入数学表达式\n"
    + "units_ctx = {n: v for n, v in globals().items() if isinstance(v, (Quantity, PhysicalConstant))}\n"
    + "\n"
    + "def _unit_vec(q):\n"
    + "    deps = dimsys_SI.get_dimensional_dependencies(q.dimension)\n"
    + "    return {str(getattr(k, 'name', str(k))): int(v) for k, v in deps.items()}\n"
    + "\n"
    + "def _parse_unit(s):\n"
    + "    e = parse_expr(s, local_dict=units_ctx, global_dict=_MATH_GLOBALS, transformations=_transforms)\n"
    + "    bad = sorted(str(x) for x in e.free_symbols)\n"
    + "    if bad:\n"
    + "        raise ValueError('单位表达式 \"' + s + '\" 含未识别符号 ' + repr(bad) + '，请使用 sympy 单位名（如 meter、second、kilogram、ohm、tesla）')\n"
    + "    return e\n"
    + "\n"
    + "def _vec_equal(a, b):\n"
    + "    keys = set(a) | set(b)\n"
    + "    return all(abs(a.get(k, 0.0) - b.get(k, 0.0)) <= 1e-6 for k in keys)\n"
    + "\n"
    + "def _vec_norm(v):\n"
    + "    return {k: round(x, 6) for k, x in v.items() if abs(x) > 1e-9}\n"
    + "\n"
    + "_SUP_TABLE = {'0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹', '-': '⁻', '.': '·'}\n"
    + "\n"
    + "def _vec_str(v):\n"
    + "    order = [('mass', 'M'), ('length', 'L'), ('time', 'T'), ('current', 'I'), ('temperature', 'Θ'), ('amount_of_substance', 'N'), ('luminous_intensity', 'J')]\n"
    + "    parts = []\n"
    + "    for k, sym in order:\n"
    + "        p = v.get(k)\n"
    + "        if not p or abs(p) < 1e-9:\n"
    + "            continue\n"
    + "        p = round(p, 4)\n"
    + "        if abs(p - round(p)) < 1e-9:\n"
    + "            p = int(round(p))\n"
    + "        sup = str(p).translate(str.maketrans(_SUP_TABLE))\n"
    + "        parts.append(sym if p == 1 else sym + sup)\n"
    + "    return '·'.join(parts) if parts else 'dimensionless'\n"
    + "\n"
    + "def _vec(e, sym_vec):\n"
    + "    if isinstance(e, (Quantity, PhysicalConstant)):\n"
    + "        return _unit_vec(e)\n"
    + "    if e.is_Number or e.is_NumberSymbol:\n"
    + "        return {}\n"
    + "    if e.is_Symbol:\n"
    + "        name = str(e)\n"
    + "        if name not in sym_vec:\n"
    + "            raise ValueError('符号 ' + name + ' 未声明单位')\n"
    + "        return dict(sym_vec[name])\n"
    + "    if e.is_Pow:\n"
    + "        exp = e.exp\n"
    + "        if not exp.is_Number:\n"
    + "            raise ValueError('量纲指数必须为数值，得到: ' + str(exp))\n"
    + "        f = float(exp)\n"
    + "        bv = _vec(e.base, sym_vec)\n"
    + "        return {k: x * f for k, x in bv.items()}\n"
    + "    if e.is_Mul:\n"
    + "        r = {}\n"
    + "        for a in e.args:\n"
    + "            for k, x in _vec(a, sym_vec).items():\n"
    + "                r[k] = r.get(k, 0.0) + x\n"
    + "        return r\n"
    + "    if e.is_Add:\n"
    + "        vs = [_vec(a, sym_vec) for a in e.args]\n"
    + "        for v in vs[1:]:\n"
    + "            if not _vec_equal(vs[0], v):\n"
    + "                raise ValueError('加法项量纲不一致，无法合并')\n"
    + "        return dict(vs[0])\n"
    + "    if e.is_Function:\n"
    + "        for a in e.args:\n"
    + "            if not _vec_equal(_vec(a, sym_vec), {}):\n"
    + "                raise ValueError('数学函数（如 sin/cos/exp）的参数必须无量纲')\n"
    + "        return {}\n"
    + "    raise ValueError('不支持的量纲表达式节点: ' + type(e).__name__ + '(' + str(e) + ')')\n"
    + "\n"
    + "def _decl_vec(u):\n"
    + "    if str(u).strip().lower() == 'dimensionless':\n"
    + "        return {}\n"
    + "    return _vec(_parse_unit(str(u)), {})\n"
    + "\n"
    + "def _parse_symbol_defs(unit_defs):\n"
    + "    return {s: (list(v) if isinstance(v, list) else [v]) for s, v in unit_defs.items()}\n"
)

_TEMPLATES: dict[str, Template] = {
    "evaluate": Template(
        _SAFE_IMPORTS
        + "\n$var_declarations\n"
        + "result = _safe_sympify($expression, local_dict=_LOCALS)\n"
        + "$subs_call\n"
        + _SERIALIZER
    ),
    "simplify": Template(
        _SAFE_IMPORTS
        + "\n$var_declarations\n"
        + "result = _safe_sympify($expression, local_dict=_LOCALS)\n"
        + "$subs_call\n"
        + "result = $method(result)\n"
        + _SERIALIZER
    ),
    "solve": Template(
        _SAFE_IMPORTS
        + "\neqs = []\n"
        + "for _e in $equations:\n"
        + "    if '=' in _e:\n"
        + "        _parts = _e.rsplit('=', 1)\n"
        + "        eqs.append(Eq(_safe_sympify(_parts[0], local_dict=_LOCALS), _safe_sympify(_parts[1], local_dict=_LOCALS)))\n"
        + "    else:\n"
        + "        eqs.append(_safe_sympify(_e, local_dict=_LOCALS))\n"
        + "vars = symbols($var_names)\n"
        + "result = solve(eqs, vars, dict=True)\n"
        + "$domain_filter_code\n"
        + _SERIALIZER
    ),
    "equality": Template(
        _SAFE_IMPORTS
        + "\na = _safe_sympify($expression_a)\n"
        + "b = _safe_sympify($expression_b)\n"
        + "diff = simplify(a - b)\n"
        + "result = diff == 0\n"
        + "if not result:\n"
        + "    try:\n"
        + "        result = bool(a.equals(b))\n"
        + "    except Exception:\n"
        + "        pass\n"
        + "if not result:\n"
        + "    try:\n"
        + "        result = abs(float(diff)) <= 1e-12\n"
        + "    except Exception:\n"
        + "        pass\n"
        + _SERIALIZER
    ),
    "differentiate": Template(
        _SAFE_IMPORTS
        + "\n$substitutions\n"
        + "expr = _safe_sympify($expression)\n"
        + "var = Symbol($variable)\n"
        + "result = diff(expr, var, $order)\n"
        + _SERIALIZER
    ),
    "integrate": Template(
        _SAFE_IMPORTS
        + "\n$substitutions\n"
        + "expr = _safe_sympify($expression)\n"
        + "var = Symbol($variable)\n"
        + "$limit_code\n"
        + _SERIALIZER
    ),
    "formula": Template(
        _SAFE_IMPORTS
        + "\n_parts = $formula_str.rsplit('=', 1)\n"
        + "_lhs = _safe_sympify(_parts[0].strip(), local_dict=_LOCALS)\n"
        + "_rhs = _safe_sympify(_parts[1].strip(), local_dict=_LOCALS)\n"
        + "_eq = Eq(_lhs, _rhs)\n"
        + "_tgt = Symbol($solve_for)\n"
        + "_sol = solve(_eq, _tgt, dict=True)\n"
        + "result = _sol[0][_tgt] if _sol else None\n"
        + "$subs_call\n"
        + _SERIALIZER
    ),
    "dimensional": Template(
        _DIM_BODY
        + "$operation_code\n"
        + _SERIALIZER
    ),
    "limit": Template(
        _SAFE_IMPORTS
        + "\n_expr = _safe_sympify($expression, local_dict=_LOCALS)\n"
        + "_var = Symbol($variable)\n"
        + "_approach = _safe_sympify($approach, local_dict=_LOCALS)\n"
        + "_dir = $direction\n"
        + "result = limit(_expr, _var, _approach, dir=_dir)\n"
        + _SERIALIZER
    ),
    "geometry": Template(
        _SAFE_IMPORTS
        + "from sympy.geometry import Point, Line, Circle, intersection\n"
        + "\nresult = _safe_sympify($expression, local_dict=_LOCALS)\n"
        + _SERIALIZER
    ),
    "vector_ops": Template(
        _SAFE_IMPORTS
        + "from sympy import Matrix\n"
        + "\n_a = Matrix($vec_a)\n"
        + "_b = Matrix($vec_b)\n"
        + "$op_code\n"
        + _SERIALIZER
    ),
    "circle_from_two_points": Template(
        _SAFE_IMPORTS
        + "from sympy.geometry import Point, Line, Circle, intersection\n"
        + "\n$setup_code\n"
        + "$solve_code\n"
        + _SERIALIZER
    ),
    "chemistry_balance": Template(
        _SAFE_IMPORTS
        + "\n"
        + "_eq = $equation_str\n"
        + "_sides = _eq.split('->')\n"
        + "_reactants = [s.strip() for s in _sides[0].split('+')]\n"
        + "_products = [s.strip() for s in _sides[1].split('+')]\n"
        + "_all_species = _reactants + _products\n"
        + "_n_react = len(_reactants)\n"
        + "\n"
        + "def _parse_formula(f):\n"
        + "    _counts = {}\n"
        + "    _i = 0\n"
        + "    _n = len(f)\n"
        + "    def _parse_group():\n"
        + "        nonlocal _i\n"
        + "        _gc = {}\n"
        + "        while _i < _n and f[_i] != ')':\n"
        + "            if f[_i] == '(':\n"
        + "                _i += 1\n"
        + "                _inner = _parse_group()\n"
        + "                if _i < _n and f[_i] == ')':\n"
        + "                    _i += 1\n"
        + "                _num_start = _i\n"
        + "                while _i < _n and f[_i].isdigit():\n"
        + "                    _i += 1\n"
        + "                _mult = int(f[_num_start:_i]) if _i > _num_start else 1\n"
        + "                for _el, _cnt in _inner.items():\n"
        + "                    _gc[_el] = _gc.get(_el, 0) + _cnt * _mult\n"
        + "            elif f[_i].isupper():\n"
        + "                _el_start = _i\n"
        + "                _i += 1\n"
        + "                while _i < _n and f[_i].islower():\n"
        + "                    _i += 1\n"
        + "                _el = f[_el_start:_i]\n"
        + "                _num_start = _i\n"
        + "                while _i < _n and f[_i].isdigit():\n"
        + "                    _i += 1\n"
        + "                _cnt = int(f[_num_start:_i]) if _i > _num_start else 1\n"
        + "                _gc[_el] = _gc.get(_el, 0) + _cnt\n"
        + "            else:\n"
        + "                _i += 1\n"
        + "        return _gc\n"
        + "    _counts = _parse_group()\n"
        + "    return _counts\n"
        + "\n"
        + "_elements = set()\n"
        + "for _s in _all_species:\n"
        + "    _elements.update(_parse_formula(_s).keys())\n"
        + "_elements = sorted(_elements)\n"
        + "\n"
        + "_A = []\n"
        + "for _el in _elements:\n"
        + "    _row = []\n"
        + "    for _i, _s in enumerate(_all_species):\n"
        + "        _cnt = _parse_formula(_s).get(_el, 0)\n"
        + "        if _i >= _n_react:\n"
        + "            _cnt = -_cnt\n"
        + "        _row.append(_cnt)\n"
        + "    _A.append(_row)\n"
        + "\n"
        + "_M = Matrix(_A)\n"
        + "_null = _M.nullspace()\n"
        + "if not _null:\n"
        + "    result = {'error': '无法配平（可能方程式有误）'}\n"
        + "else:\n"
        + "    _vec = _null[0]\n"
        + "    _denoms = [Rational(v).q for v in _vec]\n"
        + "    import math as _math\n"
        + "    _lcm = _denoms[0]\n"
        + "    for _d in _denoms[1:]:\n"
        + "        _lcm = _lcm * _d // _math.gcd(_lcm, _d)\n"
        + "    _coeffs = [abs(int(Rational(v) * _lcm)) for v in _vec]\n"
        + "    _parts = []\n"
        + "    for _i, _s in enumerate(_all_species):\n"
        + "        _co = _coeffs[_i]\n"
        + "        _prefix = str(_co) if _co != 1 else ''\n"
        + "        _parts.append(_prefix + _s)\n"
        + "        if _i == _n_react - 1:\n"
        + "            _parts.append(' -> ')\n"
        + "        elif _i < len(_all_species) - 1:\n"
        + "            _parts.append(' + ')\n"
        + "    result = {'coefficients': _coeffs, "
        + "'reactant_coeffs': _coeffs[:_n_react], "
        + "'product_coeffs': _coeffs[_n_react:], "
        + "'balanced_equation': ''.join(_parts), "
        + "'species': _all_species}\n"
        + _SERIALIZER
    ),
    "stoichiometry": Template(
        _SAFE_IMPORTS
        + "\n"
        + "$molar_masses\n"
        + "_known = $known_substance_str\n"
        + "_target = $target_substance_str\n"
        + "_known_mass = float($known_mass_val)\n"
        + "\n"
        + "_rco = $reactant_coeffs\n"
        + "_pco = $product_coeffs\n"
        + "_react = $reactants_str\n"
        + "_prod = $products_str\n"
        + "\n"
        + "_all = _react + _prod\n"
        + "_coeffs = _rco + _pco\n"
        + "\n"
        + "if _known not in _all or _target not in _all:\n"
        + "    result = {'error': '物质不在方程式中'}\n"
        + "else:\n"
        + "    _ki = _all.index(_known)\n"
        + "    _ti = _all.index(_target)\n"
        + "    _known_mol = _known_mass / _MOLAR[_known]\n"
        + "    _target_mol = _known_mol * (_coeffs[_ti] / _coeffs[_ki])\n"
        + "    _target_mass = _target_mol * _MOLAR[_target]\n"
        + "    result = {\n"
        + "        'known_mass_g': _known_mass,\n"
        + "        'known_mol': float(_known_mol),\n"
        + "        'target_mol': float(_target_mol),\n"
        + "        'target_mass_g': float(_target_mass),\n"
        + "        'mole_ratio': f'{_coeffs[_ti]}:{_coeffs[_ki]}',\n"
        + "    }\n"
        + _SERIALIZER
    ),
}


def build_code(operation: str, **params) -> str:
    """根据操作类型和参数生成可在子进程中执行的 SymPy Python 代码。"""
    template = _TEMPLATES.get(operation)
    if template is None:
        raise ValueError(f"Unknown operation type: {operation}")

    substitutions = params.get("substitutions", {}) or {}

    # 生成变量声明：将 substitution 中的每个变量名注册为 Symbol，
    # 避免变量名（如 E1, d0）与 SymPy 全局命名空间冲突导致解析失败。
    var_declarations = ""
    if substitutions:
        var_lines = []
        for var_name in substitutions:
            var_lines.append(f'_LOCALS[{var_name!r}] = Symbol({var_name!r})')
        var_declarations = "\n".join(var_lines)

    if substitutions:
        subs_pairs = []
        for var_name, var_value in substitutions.items():
            if isinstance(var_value, str):
                subs_pairs.append(f'Symbol({var_name!r}): _safe_sympify({var_value!r})')
            else:
                subs_pairs.append(f'Symbol({var_name!r}): {var_value!r}')
        subs_call = "result = result.subs({" + ", ".join(subs_pairs) + "})"
    else:
        subs_call = ""

    var_names = " ".join(params.get("variables", ["x"]))

    limit_code = ""
    lower = params.get("lower_limit")
    upper = params.get("upper_limit")
    if lower is not None and upper is not None:
        limit_code = f"result = integrate(expr, (var, _safe_sympify({lower!r}), _safe_sympify({upper!r})))"
    else:
        limit_code = "result = integrate(expr, var)"

    # Formula-specific params
    formula_str = json_repr(params.get("formula", ""))
    solve_for = json_repr(params.get("solve_for", "x"))

    # Dimensional-analysis params
    operation = params.get("dim_operation", params.get("operation", "check_consistency"))
    target_units = params.get("target_units", "")
    unit_defs = params.get("unit_definitions", {}) or {}
    unit_defs_json = json_repr(unit_defs)

    expression_str = params.get("expression", "")
    # get_dimensions / convert 只取等号右端（左端为目标量，量纲来源在右侧）
    dim_expr_str = expression_str.rsplit("=", 1)[-1].strip() if "=" in expression_str else expression_str
    
    if operation == "check_consistency":
        operation_code = (
            "_unit_defs = $unit_defs_json\n"
            "_cands = _parse_symbol_defs(_unit_defs)\n"
            "_lr = $expression_str.rsplit('=', 1)\n"
            "_left = _safe_sympify(_lr[0].strip(), local_dict=_LOCALS)\n"
            "_right = _safe_sympify(_lr[1].strip(), local_dict=_LOCALS) if len(_lr) > 1 else None\n"
            "_syms = set(str(s) for s in _left.free_symbols)\n"
            "if _right is not None:\n"
            "    _syms |= set(str(s) for s in _right.free_symbols)\n"
            "_missing = sorted(s for s in _syms if s not in _unit_defs)\n"
            "if _missing:\n"
            "    raise ValueError('以下符号未声明单位，请在 unit_definitions 中补齐: ' + repr(_missing) + '（纯数学量请声明为 dimensionless）')\n"
            "_keys = sorted(_cands.keys())\n"
            "_n = 1\n"
            "for s in _keys:\n"
            "    _n *= len(_cands[s])\n"
            "if _n > 128:\n"
            "    raise ValueError('歧义候选组合过多 (' + str(_n) + ' > 128)，请减少候选单位')\n"
            "_matched = None\n"
            "_lv = _rv = None\n"
            "_tried = 0\n"
            "for _combo in product(*[_cands[s] for s in _keys]):\n"
            "    _tried += 1\n"
            "    _sym_vec = {}\n"
            "    for s, u in zip(_keys, _combo):\n"
            "        _sym_vec[s] = _decl_vec(u)\n"
            "    _lv = _vec_norm(_vec(_left, _sym_vec))\n"
            "    _rv = _vec_norm(_vec(_right, _sym_vec)) if _right is not None else {}\n"
            "    if _vec_equal(_lv, _rv):\n"
            "        _matched = {s: u for s, u in zip(_keys, _combo)}\n"
            "        break\n"
            "if _matched is not None:\n"
            "    result = {'consistent': True, 'left_dimensions': _vec_str(_lv), 'right_dimensions': _vec_str(_rv), 'matched_combination': _matched, 'tried_combinations': _tried}\n"
            "else:\n"
            "    result = {'consistent': False, 'left_dimensions': _vec_str(_lv) if _lv is not None else '', 'right_dimensions': _vec_str(_rv) if _rv is not None else '', 'matched_combination': None, 'tried_combinations': _tried}\n"
        )
    elif operation == "get_dimensions":
        operation_code = (
            "_unit_defs = $unit_defs_json\n"
            "_cands = _parse_symbol_defs(_unit_defs)\n"
            "_lr = $expression_str.rsplit('=', 1)\n"
            "_left_syms = []\n"
            "if len(_lr) > 1:\n"
            "    _le = _safe_sympify(_lr[0].strip(), local_dict=_LOCALS)\n"
            "    _left_syms = sorted(str(s) for s in _le.free_symbols)\n"
            "_expr = _safe_sympify(_lr[-1].strip(), local_dict=_LOCALS)\n"
            "_syms = sorted(set(str(s) for s in _expr.free_symbols) | set(_left_syms))\n"
            "_missing = [s for s in _syms if s not in _unit_defs]\n"
            "if _missing:\n"
            "    raise ValueError('以下符号未声明单位，请在 unit_definitions 中补齐: ' + repr(_missing) + '（纯数学量请声明为 dimensionless）')\n"
            "_out = {}\n"
            "_c = {}\n"
            "for s in _syms:\n"
            "    if s in _left_syms and s not in _expr.free_symbols:\n"
            "        continue\n"
            "    _vecs = [_vec_str(_vec_norm(_decl_vec(u))) for u in _cands[s]]\n"
            "    _out[s] = _vecs if len(_vecs) > 1 else _vecs[0]\n"
            "    _c[s] = _decl_vec(_cands[s][0])\n"
            "_overall = _vec_str(_vec_norm(_vec(_expr, _c)))\n"
            "for s in _left_syms:\n"
            "    _out[s] = _overall\n"
            "result = {'dimensions': _out, 'expression': _overall}\n"
        )
    elif operation == "convert":
        operation_code = (
            "_unit_defs = $unit_defs_json\n"
            "_expr = parse_expr($dim_expression_str, local_dict=units_ctx, transformations=_transforms)\n"
            "_bad = sorted(str(x) for x in _expr.free_symbols)\n"
            "if _bad:\n"
            "    _missing = [s for s in _bad if s not in _unit_defs]\n"
            "    if _missing:\n"
            "        raise ValueError('以下符号未声明单位，请在 unit_definitions 中补齐: ' + repr(_missing))\n"
            "    _src = {}\n"
            "    for s in _bad:\n"
            "        u = _unit_defs[s]\n"
            "        u = u[0] if isinstance(u, list) else u\n"
            "        _src[Symbol(s)] = _parse_unit(str(u))\n"
            "    _expr = _expr.subs(_src)\n"
            "_target = parse_expr($target_units, local_dict=units_ctx, transformations=_transforms)\n"
            "_tb = sorted(str(x) for x in _target.free_symbols)\n"
            "if _tb:\n"
            "    raise ValueError('目标单位含未识别符号: ' + repr(_tb))\n"
            "_converted = convert_to(_expr, _target)\n"
            "result = float((_converted / _target).evalf())\n"
        )
    else:
        operation_code = "\nresult = 'unsupported operation'\n"

    # SolveEquationTool domain 过滤：real 域剔除复数根
    domain = str(params.get("domain", "real")).lower()
    if domain == "real":
        domain_filter_code = (
            "result = [sol for sol in result "
            "if all(v.is_real is not False for v in sol.values())]"
        )
    else:
        domain_filter_code = ""

    # Vector ops params
    vec_a = params.get("vec_a", [0, 0])
    vec_b = params.get("vec_b", [0, 0])
    op = params.get("vector_operation", params.get("operation", "dot"))
    if op == "dot":
        op_code = "result = float(_a.dot(_b))"
    elif op == "cross":
        op_code = (
            "if len(_a) == 2:\n"
            "    result = float(_a[0]*_b[1] - _a[1]*_b[0])\n"
            "else:\n"
            "    _c = _a.cross(_b)\n"
            "    result = [float(_c[i]) for i in range(len(_c))]"
        )
    elif op == "angle":
        op_code = (
            "if _a.is_zero_matrix or _b.is_zero_matrix:\n"
            "    raise ValueError('存在零向量，无法计算夹角')\n"
            "from sympy import acos\n"
            "result = float(acos(_a.dot(_b) / (sqrt(_a.dot(_a)) * sqrt(_b.dot(_b)))).evalf())"
        )
    elif op == "projection":
        op_code = (
            "if _b.is_zero_matrix:\n"
            "    raise ValueError('投影方向向量 B 为零向量，无法计算')\n"
            "result = [float(x) for x in (_a.dot(_b) / _b.dot(_b)) * _b]"
        )
    else:
        op_code = "result = 'unsupported'"

    # Circle from two points params
    entry_point = params.get("entry_point", ["0", "0"])
    velocity_direction = params.get("velocity_direction", [1, 0])
    impact_point = params.get("impact_point", ["0", "0"])
    impact_normal = params.get("impact_normal", [0, 1])

    setup_code = (
        f"_px, _py = _safe_sympify({entry_point[0]!r}, local_dict=_LOCALS), _safe_sympify({entry_point[1]!r}, local_dict=_LOCALS)\n"
        f"_ix, _iy = _safe_sympify({impact_point[0]!r}, local_dict=_LOCALS), _safe_sympify({impact_point[1]!r}, local_dict=_LOCALS)\n"
        f"_P = Point(_px, _py)\n"
        f"_v = Matrix([{velocity_direction[0]}, {velocity_direction[1]}])\n"
        f"_I = Point(_ix, _iy)\n"
        f"_n = Matrix([{impact_normal[0]}, {impact_normal[1]}])\n"
        "if _v.is_zero_matrix:\n"
        "    raise ValueError('入射点速度方向向量为零，无法确定切线')\n"
        "if _n.is_zero_matrix:\n"
        "    raise ValueError('撞击点法向量为零，无法确定约束')\n"
        "if (_ix - _px)**2 + (_iy - _py)**2 <= 1e-12:\n"
        "    raise ValueError('两个点重合，无法确定圆')\n"
    )
    solve_code = (
        "Cx, Cy = symbols('Cx Cy')\n"
        "_eq1 = Eq((Cx - _P.x)*_v[0] + (Cy - _P.y)*_v[1], 0)\n"
        "_eq2 = Eq((Cx - _I.x)*_n[0] + (Cy - _I.y)*_n[1], 0)\n"
        "_sol = solve([_eq1, _eq2], (Cx, Cy), dict=True)\n"
        "if _sol:\n"
        "    _C = Point(_sol[0][Cx], _sol[0][Cy])\n"
        "    _R = simplify(_C.distance(_P))\n"
        "    result = {'center': [str(_C.x), str(_C.y)], 'radius': str(_R)}\n"
        "else:\n"
        "    result = {'error': 'no_solution'}\n"
    )

    # Chemistry params
    equation_str = json_repr(params.get("equation", ""))
    known_substance_str = json_repr(params.get("known_substance", ""))
    target_substance_str = json_repr(params.get("target_substance", ""))
    known_mass_val = json_repr(params.get("known_mass", 0))
    reactant_coeffs = json_repr(params.get("reactant_coeffs", []))
    product_coeffs = json_repr(params.get("product_coeffs", []))
    reactants_str = json_repr(params.get("reactants", []))
    products_str = json_repr(params.get("products", []))

    # Build molar masses dict
    molar_masses = params.get("molar_masses", {}) or {}
    molar_lines = ["_MOLAR = {"]
    for formula, mass in molar_masses.items():
        molar_lines.append(f"    {json_repr(formula)}: {mass},")
    molar_lines.append("}")
    molar_masses_code = "\n".join(molar_lines)

    return template.safe_substitute(
        var_declarations=var_declarations,
        subs_call=subs_call,
        substitutions="",
        expression=json_repr(params.get("expression", "")),
        expression_str=json_repr(params.get("expression", "")),
        expression_a=json_repr(params.get("expression_a", "")),
        expression_b=json_repr(params.get("expression_b", "")),
        equations=json_repr(params.get("equations", [])),
        var_names=json_repr(var_names),
        variables=json_repr(params.get("variables", [])),
        domain_filter_code=domain_filter_code,
        variable=json_repr(params.get("variable", "x")),
        order=str(params.get("order", 1)),
        method=params.get("method", "simplify"),
        limit_code=limit_code,
        approach=json_repr(params.get("approach", "0")),
        direction=json_repr(params.get("direction", "+-")),
        formula_str=formula_str,
        solve_for=solve_for,
        unit_defs_json=unit_defs_json,
        operation_code=operation_code,
        target_units=json_repr(target_units),
        vec_a=json_repr(vec_a),
        vec_b=json_repr(vec_b),
        op_code=op_code,
        setup_code=setup_code,
        solve_code=solve_code,
        equation_str=equation_str,
        known_substance_str=known_substance_str,
        target_substance_str=target_substance_str,
        known_mass_val=known_mass_val,
        reactant_coeffs=reactant_coeffs,
        product_coeffs=product_coeffs,
        reactants_str=reactants_str,
        products_str=products_str,
        molar_masses=molar_masses_code,
    ).replace(
        # safe_substitute 不递归处理替换值内的占位符，这里二次替换 dimensional 分支的嵌入值
        "$unit_defs_json", unit_defs_json,
    ).replace(
        "$expression_str", json_repr(params.get("expression", "")),
    ).replace(
        "$dim_expression_str", json_repr(dim_expr_str),
    ).replace(
        "$target_units", json_repr(target_units),
    )


def json_repr(obj) -> str:
    """将 Python 对象转为 JSON 字符串，用于嵌入生成的代码中。"""
    return json.dumps(obj, ensure_ascii=False)

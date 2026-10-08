"""量纲声明的归一化与沙箱生成代码片段（单一源）。

三种声明形态（ADR 0005）：

- "kilogram" / "meter/second**2"：sympy 单位表达式，通用兜底，覆盖题目自定义量
- "dim:M*L*T**-2"：显式量纲，只允许 M/L/T/I/Θ/N/J，**绝不走 sympy 单位命名空间**
  （实测 L=liter、T=tesla、N=newton、J=joule 等 14 个单字母是活单位名）
- {"quantity": "质量", "unit": "kilogram"}：物理量名 + 单位，名字只用于交叉校验

量纲真值只来自 unit / dim:，**绝不来自物理量名**：只给名字不给单位直接拒绝，
题目自定义量按题面定义写成单位表达式即可，表不全永远不阻塞任何一道题。
"""
from __future__ import annotations

import re

# 量纲字母 → sympy dimsys_SI 的规范维度名（与沙箱 _unit_vec 的键一致）
DIM_ALIASES = {
    "M": "mass",
    "L": "length",
    "T": "time",
    "I": "current",
    "Θ": "temperature",
    "K": "temperature",
    "N": "amount_of_substance",
    "J": "luminous_intensity",
}
_DIM_TERM_RE = re.compile(r"^([MLTIΘKNJ])(?:\s*(?:\*\*|\^)\s*(-?\d+(?:\.\d+)?))?$")
_DIMENSIONLESS = {"", "1", "dimensionless"}


def parse_dim_spec(spec: str) -> dict:
    """解析 dim: 后面的量纲表达式，返回 {规范维度名: 指数}。"""
    text = spec.strip()
    if text.lower() in _DIMENSIONLESS:
        return {}
    # 先把 ** 统一成 ^，否则按 * 切分时 T**-2 会被切成 T / '' / -2
    text = text.replace("**", "^")
    # 只支持一个 /：左边分子、右边分母；分母里的每一项取负号。
    numerator, _, denominator = text.partition("/")
    out: dict[str, float] = {}
    for part_text, sign in ((numerator, 1.0), (denominator, -1.0)):
        for term in re.split(r"[*·×]", part_text):
            term = term.strip()
            if not term or term == "1":
                # 允许 1/T 这类写法：裸 1 是无量纲因子
                continue
            match = _DIM_TERM_RE.match(term)
            if not match:
                raise ValueError(
                    "非法量纲项 " + repr(term)
                    + "：dim: 只允许 M/L/T/I/Θ/N/J，例如 dim:M*L*T**-2")
            key = DIM_ALIASES[match.group(1)]
            exponent = float(match.group(2)) if match.group(2) else 1.0
            out[key] = out.get(key, 0.0) + sign * exponent
    return {k: v for k, v in out.items() if abs(v) > 1e-9}


def _normalize_reading(symbol: str, value) -> dict:
    """把一种声明形态归一成读数：{unit|dimvec, quantity?, label}。"""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("符号 " + symbol + " 的单位声明为空")
        if text.startswith("dim:"):
            spec = text[4:].strip()
            return {"dimvec": parse_dim_spec(spec), "dim_source": "dim:" + spec,
                    "label": "dim:" + spec}
        return {"unit": text, "label": text}
    if isinstance(value, dict):
        unknown = sorted(set(value) - {"quantity", "unit", "dim"})
        if unknown:
            raise ValueError("符号 " + symbol + " 的声明含未知字段：" + repr(unknown))
        quantity = value.get("quantity")
        if quantity is not None and (not isinstance(quantity, str) or not quantity.strip()):
            raise ValueError("符号 " + symbol + " 的 quantity 必须是非空字符串")
        unit = value.get("unit")
        dim = value.get("dim")
        if unit and dim:
            raise ValueError("符号 " + symbol + " 同时给了 unit 与 dim，只能取其一")
        if not unit and not dim:
            raise ValueError(
                "符号 " + symbol + " 只声明了物理量名，缺少 unit 或 dim——"
                "量纲真值只来自单位/量纲，不按名字猜；题目自定义量请按定义写成单位表达式")
        reading: dict = {}
        if unit:
            reading["unit"] = str(unit)
            source = str(unit)
        else:
            spec = str(dim)
            if spec.startswith("dim:"):
                spec = spec[4:].strip()
            reading["dimvec"] = parse_dim_spec(spec)
            reading["dim_source"] = "dim:" + spec
            source = "dim:" + spec
        if quantity:
            reading["quantity"] = quantity.strip()
            reading["label"] = reading["quantity"] + "=" + source
        else:
            reading["label"] = source
        return reading
    raise ValueError("符号 " + symbol + " 的声明类型非法：" + type(value).__name__)


def normalize_unit_definitions(unit_defs) -> dict:
    """把三种声明形态归一为 {符号: [读数, ...]}。

    列表表示调用方显式列出的**全部候选读数**，由沙箱枚举所有组合并回报全部自洽解，
    不再由工具静默取第一个。
    """
    if unit_defs is None:
        return {}
    if not isinstance(unit_defs, dict):
        raise ValueError("unit_definitions 必须是对象")
    normalized: dict[str, list[dict]] = {}
    for symbol, value in unit_defs.items():
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("unit_definitions 的符号名必须是非空字符串")
        values = value if isinstance(value, list) else [value]
        if not values:
            raise ValueError("符号 " + symbol + " 的候选列表为空")
        normalized[symbol.strip()] = [_normalize_reading(symbol, item) for item in values]
    return normalized


READING_HELPERS = r"""
def _reading_vec(u):
    if 'dimvec' in u:
        return {k: float(v) for k, v in u['dimvec'].items()}
    if u.get('unit'):
        return _decl_vec(u['unit'])
    raise ValueError('读数既没有单位也没有量纲')


def _reading_label(u):
    return u.get('label') or u.get('unit') or u.get('quantity') or ''
"""

QUANTITY_CHECK = r"""_quantity_table = $quantities_json
_unknown_q = []
for _s in sorted(_unit_defs):
    for _u in _unit_defs[_s]:
        _q = _u.get('quantity')
        if not _q:
            continue
        if _q not in _quantity_table:
            _unknown_q.append(_q)
            continue
        if not _vec_equal(_reading_vec(_u), _decl_vec(_quantity_table[_q])):
            raise ValueError('符号 ' + _s + ' 声明的物理量「' + _q + '」与单位/量纲不一致：' + _reading_label(_u))
"""

CHECK_CONSISTENCY = r"""_unit_defs = $unit_defs_json
_cands = _unit_defs
_lr = $expression_str.rsplit('=', 1)
_left = _safe_sympify(_lr[0].strip(), local_dict=_LOCALS)
_right = _safe_sympify(_lr[1].strip(), local_dict=_LOCALS) if len(_lr) > 1 else None
_syms = set(str(s) for s in _left.free_symbols)
if _right is not None:
    _syms |= set(str(s) for s in _right.free_symbols)
_missing = sorted(s for s in _syms if s not in _unit_defs)
if _missing:
    raise ValueError('以下符号未声明单位，请在 unit_definitions 中补齐: ' + repr(_missing) + '（纯数学量请声明为 dimensionless）')
$quantity_check_code
_keys = sorted(_cands.keys())
_n = 1
for s in _keys:
    _n *= len(_cands[s])
if _n > 128:
    raise ValueError('歧义候选组合过多 (' + str(_n) + ' > 128)，请减少候选单位')
_matches = []
_tried = 0
_lv = _rv = None
_last_lv = _last_rv = None
_first_lv = _first_rv = None
for _combo in product(*[_cands[s] for s in _keys]):
    _tried += 1
    _sym_vec = {s: _reading_vec(u) for s, u in zip(_keys, _combo)}
    try:
        _lv = _vec_norm(_vec(_left, _sym_vec))
        _rv = _vec_norm(_vec(_right, _sym_vec)) if _right is not None else {}
    except _DimensionMismatch:
        if _n == 1:
            raise
        continue
    _last_lv, _last_rv = _lv, _rv
    if _vec_equal(_lv, _rv):
        _matches.append({s: _reading_label(u) for s, u in zip(_keys, _combo)})
        if len(_matches) == 1:
            _first_lv, _first_rv = _lv, _rv
if _matches:
    _dl, _dr = _first_lv, _first_rv
else:
    _dl, _dr = _last_lv, _last_rv
result = {'consistent': bool(_matches),
          'ambiguous': len(_matches) > 1,
          'candidates': _matches,
          'left_dimensions': _vec_str(_dl) if _dl is not None else '',
          'right_dimensions': _vec_str(_dr) if _dr is not None else '',
          'tried_combinations': _tried}
if len(_matches) == 1:
    result['matched_combination'] = _matches[0]
elif not _matches:
    result['matched_combination'] = None
if _unknown_q:
    result['quantity_unknown'] = sorted(set(_unknown_q))
"""

GET_DIMENSIONS = r"""_unit_defs = $unit_defs_json
_cands = _unit_defs
$quantity_check_code
_multi = sorted(s for s in _cands if len(_cands[s]) > 1)
if _multi:
    raise ValueError('以下符号声明了多个读数，get_dimensions 需要单一读数，请先收敛：' + repr(_multi))
_lr = $expression_str.rsplit('=', 1)
_left_syms = []
if len(_lr) > 1:
    _le = _safe_sympify(_lr[0].strip(), local_dict=_LOCALS)
    _left_syms = sorted(str(s) for s in _le.free_symbols)
_expr = _safe_sympify(_lr[-1].strip(), local_dict=_LOCALS)
_right_syms = sorted(str(s) for s in _expr.free_symbols)
_syms = sorted(set(_right_syms) | set(_left_syms))
_missing = [s for s in _syms if s not in _unit_defs]
if _missing:
    raise ValueError('以下符号未声明单位，请在 unit_definitions 中补齐: ' + repr(_missing) + '（纯数学量请声明为 dimensionless）')
_out = {}
_c = {}
for s in _syms:
    # 只在等号右侧出现的符号参与整体量纲计算；左侧独有符号由整体结果回填。
    # 旧实现拿 str 与 Symbol 集合比较（恒为真），x = x 这类左右同符号会漏算。
    if s in _left_syms and s not in _right_syms:
        continue
    _u0 = _cands[s][0]
    _out[s] = _vec_str(_vec_norm(_reading_vec(_u0)))
    _c[s] = _reading_vec(_u0)
_overall = _vec_str(_vec_norm(_vec(_expr, _c)))
for s in _left_syms:
    _out[s] = _overall
result = {'dimensions': _out, 'expression': _overall}
"""

CONVERT = r"""_unit_defs = $unit_defs_json
_cands = _unit_defs
$quantity_check_code
_multi = sorted(s for s in _cands if len(_cands[s]) > 1)
if _multi:
    raise ValueError('以下符号声明了多个读数，convert 需要单一读数，请先收敛：' + repr(_multi))
_dim_locals = dict(units_ctx)
for _name in _unit_defs:
    _dim_locals[_name] = Symbol(_name)
_expr = _safe_sympify($dim_expression_str, local_dict=_dim_locals, global_dict=dict(_MATH_GLOBALS, **units_ctx))
_bad = sorted(str(x) for x in _expr.free_symbols)
if _bad:
    _missing = [s for s in _bad if s not in _unit_defs]
    if _missing:
        raise ValueError('以下符号未声明单位，请在 unit_definitions 中补齐: ' + repr(_missing))
    _src = {}
    for s in _bad:
        _u0 = _cands[s][0]
        if not _u0.get('unit'):
            raise ValueError('convert 需要单位声明，符号 ' + s + ' 用了 dim: 形式，无法换算')
        _src[Symbol(s)] = _parse_unit(_u0['unit'])
    _expr = _expr.subs(_src)
_target = parse_expr($target_units, local_dict=units_ctx, transformations=_transforms)
_tb = sorted(str(x) for x in _target.free_symbols)
if _tb:
    raise ValueError('目标单位含未识别符号: ' + repr(_tb))
_converted = convert_to(_expr, _target)
result = float((_converted / _target).evalf())
"""

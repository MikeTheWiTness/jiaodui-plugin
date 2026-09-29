"""dimensional operation 行为测试（移植自旧仓 tests/test_dimensional_analysis.py）。

背景：旧实现把单位命名空间注入表达式解析环境，F/L/v/R 等单字母符号会被劫持为
sympy 单位（farad/liter/volt/molar_gas_constant），合法公式误报「量纲不一致」。
这些测试锁定：未声明单位拒绝执行、歧义候选任一通过即通过、量纲向量显示格式。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jiaodui.calc import run_operation


def run_dim(expression, operation="check_consistency", unit_definitions=None, target_units=""):
    """实调 dimensional operation（走 sandbox 子进程），返回解析后的 dict。"""
    return run_operation(
        "dimensional",
        expression=expression,
        dim_operation=operation,
        unit_definitions=unit_definitions or {},
        target_units=target_units,
    )


# ---- 撞名回归：旧 bug 的用例，声明完整时不再被单位名劫持 ----


def test_collision_regression_F_B_L_v_R():
    """F = B**2*L**2*v/(R+r) ——旧实现对它有量纲不一致的误报，现在应一致。"""
    r = run_dim(
        "F = B**2 * L**2 * v / (R + r)",
        unit_definitions={
            "F": "newton", "B": "tesla", "L": "meter",
            "v": "meter/second", "R": "ohm", "r": "ohm",
        },
    )
    assert r["success"] is True
    result = r["result"]
    assert result["consistent"] is True
    assert result["left_dimensions"] == "M·L·T⁻²"
    assert result["right_dimensions"] == "M·L·T⁻²"
    assert result["matched_combination"]["F"] == "newton"
    assert result["matched_combination"]["B"] == "tesla"
    assert result["matched_combination"]["R"] == "ohm"


def test_trivial_consistency_F_ma():
    """F = m*a 标准公式：一致。"""
    r = run_dim(
        "F = m * a",
        unit_definitions={"F": "newton", "m": "kilogram", "a": "meter/second**2"},
    )
    assert r["success"] is True
    assert r["result"]["consistent"] is True
    assert r["result"]["left_dimensions"] == "M·L·T⁻²"


# ---- 未声明符号拒绝执行 ----


def test_undeclared_symbols_rejected():
    """缺声明符号 → 报错并列出缺失符号，而不是静默猜测。"""
    r = run_dim(
        "F = B**2 * L**2 * v / (R + r)",
        unit_definitions={"F": "newton"},
    )
    assert r["success"] is False
    assert "B" in r["error"] and "R" in r["error"] and "v" in r["error"]


def test_empty_unit_definitions_rejected():
    """完全不带 unit_definitions → 同样拒绝。"""
    r = run_dim("F = m * a", unit_definitions={})
    assert r["success"] is False


# ---- 歧义候选：任一组合通过即通过 ----


def test_ambiguous_candidate_hit():
    """V 声明 [速度, 体积]，速度解释成立 → consistent True 且 matched 指明 V=meter/second。"""
    r = run_dim(
        "K = 0.5 * m * V**2",
        unit_definitions={"K": "joule", "m": "kilogram", "V": ["meter/second", "meter**3"]},
    )
    assert r["success"] is True
    result = r["result"]
    assert result["consistent"] is True
    assert result["matched_combination"]["V"] == "meter/second"
    assert result["left_dimensions"] == "M·L²·T⁻²"


def test_ambiguous_candidate_all_miss():
    """V 候选 [体积, 电流] 都对不上 → consistent False 且尝试了全部 2 组。"""
    r = run_dim(
        "K = 0.5 * m * V**2",
        unit_definitions={"K": "joule", "m": "kilogram", "V": ["meter**3", "ampere"]},
    )
    assert r["success"] is True
    result = r["result"]
    assert result["consistent"] is False
    assert result["matched_combination"] is None
    assert result["tried_combinations"] == 2


def test_combination_limit_exceeded():
    """候选组合数超上限（5 符号 × 3 候选 = 243 > 128）→ 报错减少候选。"""
    defs = {s: ["meter", "second", "kilogram"] for s in "abcde"}
    defs["x"] = "newton"
    r = run_dim("x = a*b*c*d*e", unit_definitions=defs)
    assert r["success"] is False
    assert "128" in r["error"]


# ---- dimensionless 与纯数学量 ----


def test_dimensionless_symbols():
    """无量纲量声明为 dimensionless → 两侧一致（且 beta 不被 sympy 全局函数劫持）。"""
    r = run_dim(
        "theta = alpha * beta",
        unit_definitions={"theta": "dimensionless", "alpha": "dimensionless", "beta": "dimensionless"},
    )
    assert r["success"] is True
    assert r["result"]["consistent"] is True
    assert r["result"]["left_dimensions"] == "dimensionless"


# ---- 非法/不支持输入 ----


def test_invalid_unit_string():
    """单位字符串含不可识别符号 → 报错。"""
    r = run_dim(
        "F = m*a",
        unit_definitions={"F": "newton", "m": "kilogram", "a": "meter/flatulence"},
    )
    assert r["success"] is False
    assert "flatulence" in r["error"]


def test_add_dimension_mismatch():
    """加法两侧量纲不一致 → 报错（长度 + 时间不能相加）。"""
    r = run_dim(
        "x = a + b",
        unit_definitions={"x": "meter", "a": "meter", "b": "second"},
    )
    assert r["success"] is False


# ---- get_dimensions / convert ----


def test_get_dimensions_with_equation():
    """get_dimensions：F = m*a 输出各符号量纲（含等号左侧），表达式整体 M·L·T⁻²。"""
    r = run_dim(
        "F = m * a",
        operation="get_dimensions",
        unit_definitions={"F": "newton", "m": "kilogram", "a": "meter/second**2"},
    )
    assert r["success"] is True
    result = r["result"]
    assert result["dimensions"]["F"] == "M·L·T⁻²"
    assert result["dimensions"]["m"] == "M"
    assert result["dimensions"]["a"] == "L·T⁻²"
    assert result["expression"] == "M·L·T⁻²"


def test_convert_m_per_s_to_km_per_h():
    """convert：5 m/s = 18 km/h。"""
    r = run_dim(
        "5*m/s",
        operation="convert",
        unit_definitions={"m": "meter", "s": "second"},
        target_units="kilometer/hour",
    )
    assert r["success"] is True
    assert r["result"] == 18.0


def test_vector_str_locked():
    """向量显示格式锁定：力 = M·L·T⁻²。"""
    r = run_dim(
        "F = 1 * L * L * M / T**2",
        unit_definitions={"F": "newton", "L": "meter", "M": "kilogram", "T": "second"},
    )
    assert r["success"] is True
    assert r["result"]["right_dimensions"] == "M·L²·T⁻²"

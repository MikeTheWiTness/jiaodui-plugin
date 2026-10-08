"""dimensional operation 行为测试（移植自旧仓 tests/test_dimensional_analysis.py）。

背景：旧实现把单位命名空间注入表达式解析环境，F/L/v/R 等单字母符号会被劫持为
sympy 单位（farad/liter/volt/molar_gas_constant），合法公式误报「量纲不一致」。
契约（ADR 0005）：未声明单位拒绝执行；声明形态有单位 / dim: / 物理量名+单位三种；
候选列表表示调用方显式列出的全部候选读数，工具**枚举全部组合并回报全部自洽解**
（≥2 组自洽即 ambiguous，不再返回单一 matched_combination 充当结论）；量纲向量显示格式锁定。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jiaodui.calc import run_operation


def run_dim(expression, operation="check_consistency", unit_definitions=None,
            target_units="", quantities=None):
    """实调 dimensional operation（走 sandbox 子进程），返回解析后的 dict。"""
    kwargs = dict(
        expression=expression,
        dim_operation=operation,
        unit_definitions=unit_definitions or {},
        target_units=target_units,
    )
    if quantities is not None:
        kwargs["quantities"] = quantities
    return run_operation("dimensional", **kwargs)


QUANTITY_TABLE = {"力": "newton", "质量": "kilogram", "加速度": "meter/second**2"}


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


def test_lambda_symbol_in_dimensional_expression_is_not_python_keyword():
    r = run_dim(
        "y = lambda * x",
        unit_definitions={"y": "meter", "lambda": "second", "x": "meter/second"},
    )
    assert r["success"] is True
    assert r["result"]["consistent"] is True


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


def test_inconsistent_add_candidate_is_skipped_in_either_order():
    """多候选中的加法量纲冲突应只排除该组合，不吞掉其他自洽解。"""
    for candidates in (["meter", "second"], ["second", "meter"]):
        r = run_dim(
            "x = a + b",
            unit_definitions={"x": "meter", "a": "meter", "b": candidates},
        )
        assert r["success"] is True, r.get("error")
        assert r["result"]["consistent"] is True
        assert r["result"]["ambiguous"] is False
        assert r["result"]["tried_combinations"] == 2
        assert r["result"]["matched_combination"]["b"] == "meter"


def test_multiple_self_consistent_add_combinations_are_all_reported():
    r = run_dim(
        "x = a + b",
        unit_definitions={
            "x": ["meter", "second"],
            "a": ["meter", "second"],
            "b": ["meter", "second"],
        },
    )
    assert r["success"] is True, r.get("error")
    assert r["result"]["consistent"] is True
    assert r["result"]["ambiguous"] is True
    assert len(r["result"]["candidates"]) == 2
    assert {tuple(candidate[s] for s in ("x", "a", "b"))
            for candidate in r["result"]["candidates"]} == {
        ("meter", "meter", "meter"), ("second", "second", "second"),
    }
    assert r["result"]["tried_combinations"] == 8


def test_all_inconsistent_add_combinations_report_no_solution():
    r = run_dim(
        "x = a + b",
        unit_definitions={"x": "meter", "a": "meter", "b": ["second", "kilogram"]},
    )
    assert r["success"] is True, r.get("error")
    assert r["result"]["consistent"] is False
    assert r["result"]["ambiguous"] is False
    assert r["result"]["candidates"] == []
    assert r["result"]["matched_combination"] is None
    assert r["result"]["left_dimensions"] == ""
    assert r["result"]["right_dimensions"] == ""
    assert r["result"]["tried_combinations"] == 2


def test_single_inconsistent_add_keeps_error_semantics():
    """没有候选歧义时，既有的加法量纲错误仍作为执行错误返回。"""
    r = run_dim(
        "x = a + b",
        unit_definitions={"x": "meter", "a": "meter", "b": "second"},
    )
    assert r["success"] is False
    assert "加法项量纲不一致" in r["error"]


def test_function_argument_dimension_mismatch_skips_only_that_candidate():
    """有量纲的函数参数只是该候选不自洽，仍保留无量纲候选。"""
    r = run_dim(
        "x = sin(a)",
        unit_definitions={"x": "dimensionless", "a": ["meter", "dimensionless"]},
    )
    assert r["success"] is True, r.get("error")
    assert r["result"]["consistent"] is True
    assert r["result"]["matched_combination"]["a"] == "dimensionless"
    assert r["result"]["tried_combinations"] == 2


def test_other_expression_errors_still_fail_during_candidate_enumeration():
    """符号指数是工具不支持的表达式，不能当作候选不匹配吞掉。"""
    r = run_dim(
        "x = a**b",
        unit_definitions={"x": "meter", "a": "meter", "b": ["dimensionless", "dimensionless"]},
    )
    assert r["success"] is False
    assert "量纲指数必须为数值" in r["error"]


def test_invalid_unit_candidate_still_fails_after_a_valid_combination():
    """声明错误即使排在合法解之后，整次执行仍必须报错。"""
    r = run_dim(
        "x = a + b",
        unit_definitions={"x": "meter", "a": "meter", "b": ["meter", "not_a_unit"]},
    )
    assert r["success"] is False
    assert "未识别符号" in r["error"]


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


# ---- dim: 显式量纲（ADR 0005） ----


def test_dim_form_is_length_not_liter():
    """dim:L 必须是长度：单位值上下文里 L 是 liter，直接交给单位解析器会读成体积。"""
    r = run_dim("x = y", unit_definitions={"x": "dim:L", "y": "meter"})
    assert r["success"] is True
    assert r["result"]["consistent"] is True
    assert r["result"]["left_dimensions"] == "L"


def test_dim_form_accepts_slash_and_rejects_illegal_letter():
    ok = run_dim("F = m*a", unit_definitions={
        "F": "dim:M*L/T^2", "m": "dim:M", "a": "dim:L/T^2"})
    assert ok["success"] is True and ok["result"]["consistent"] is True
    bad = run_dim("x = y", unit_definitions={"x": "dim:Q", "y": "meter"})
    assert bad["success"] is False
    assert "dim:" in bad["error"]


# ---- 物理量名 + 交叉校验（ADR 0005） ----


def test_quantity_cross_check_is_shared_by_all_operations():
    bad_mass = {"y": {"quantity": "质量", "unit": "meter"}}
    for operation, expression, options in (
        ("check_consistency", "x = y", {}),
        ("get_dimensions", "x = y", {}),
        ("convert", "y", {"target_units": "centimeter"}),
    ):
        result = run_dim(expression, operation=operation,
                         unit_definitions={"x": "meter", **bad_mass},
                         quantities={"质量": "kilogram"}, **options)
        assert result["success"] is False, (operation, result)
        assert "质量" in result["error"]
        assert "不一致" in result["error"]


def test_quantity_cross_check_accepts_matching_declaration_across_operations():
    for operation, expression, options in (
        ("check_consistency", "x = y", {}),
        ("get_dimensions", "x = y", {}),
        ("convert", "y", {"target_units": "gram"}),
    ):
        result = run_dim(expression, operation=operation,
                         unit_definitions={"x": "kilogram",
                                           "y": {"quantity": "质量", "unit": "kilogram"}},
                         quantities={"质量": "kilogram"}, **options)
        assert result["success"] is True, (operation, result)


def test_quantity_name_cross_check_against_unit():
    good = run_dim("F = m*a", unit_definitions={
        "F": {"quantity": "力", "unit": "newton"},
        "m": {"quantity": "质量", "unit": "kilogram"},
        "a": {"quantity": "加速度", "unit": "meter/second**2"}},
        quantities=QUANTITY_TABLE)
    assert good["success"] is True and good["result"]["consistent"] is True
    assert good["result"]["matched_combination"]["m"] == "质量=kilogram"

    bad = run_dim("F = m*a", unit_definitions={
        "F": {"quantity": "力", "unit": "newton"},
        "m": {"quantity": "质量", "unit": "meter"},
        "a": {"quantity": "加速度", "unit": "meter/second**2"}},
        quantities=QUANTITY_TABLE)
    assert bad["success"] is False
    assert "不一致" in bad["error"]


def test_quantity_unknown_only_warns():
    """题目自定义量不在表里：告警放行，量纲仍来自单位。"""
    r = run_dim("F = m*a", unit_definitions={
        "F": {"quantity": "题目自定义量X", "unit": "newton"},
        "m": "kilogram", "a": "meter/second**2"}, quantities=QUANTITY_TABLE)
    assert r["success"] is True
    assert r["result"]["consistent"] is True
    assert r["result"]["quantity_unknown"] == ["题目自定义量X"]


def test_quantity_without_unit_is_rejected():
    """只给物理量名不给单位：拒绝，工具绝不按名字猜量纲。"""
    r = run_dim("F = m*a", unit_definitions={
        "F": {"quantity": "力"}, "m": "kilogram", "a": "meter/second**2"},
        quantities=QUANTITY_TABLE)
    assert r["success"] is False
    assert "只声明了物理量名" in r["error"]


# ---- 真判别：枚举全部组合，返回全部自洽解（ADR 0005） ----


def test_true_ambiguity_reports_all_consistent_readings():
    r = run_dim("x = y", unit_definitions={"x": ["meter", "second"], "y": ["meter", "second"]})
    result = r["result"]
    assert result["consistent"] is True
    assert result["ambiguous"] is True
    assert len(result["candidates"]) == 2
    assert "matched_combination" not in result, "多解时不得给出单一结论"
    assert result["tried_combinations"] == 4


def test_single_reading_keeps_matched_combination():
    r = run_dim("p = m*v", unit_definitions={
        "p": ["joule", "watt", "kilogram*meter/second"],
        "m": "kilogram", "v": "meter/second"})
    result = r["result"]
    assert result["ambiguous"] is False
    assert result["matched_combination"]["p"] == "kilogram*meter/second"
    assert result["tried_combinations"] == 3


def test_get_dimensions_handles_left_symbol_appearing_on_both_sides():
    """旧实现拿 str 与 Symbol 集合比较（恒为真），x = x 这类会漏算整体量纲。"""
    cases = (("x = x", {"x": "meter"}, "L"),
             ("F = F + m*a", {"F": "newton", "m": "kilogram", "a": "meter/second**2"},
              "M·L·T⁻²"))
    for expr, defs, expected in cases:
        r = run_dim(expr, operation="get_dimensions", unit_definitions=defs)
        assert r["success"] is True, r.get("error")
        assert r["result"]["expression"] == expected


def test_multi_reading_is_rejected_for_get_dimensions_and_convert():
    dims = run_dim("V = m/rho", operation="get_dimensions", unit_definitions={
        "V": ["meter/second", "meter**3"], "m": "kilogram", "rho": "kilogram/meter**3"})
    assert dims["success"] is False
    assert "多个读数" in dims["error"]

    conv = run_dim("x", operation="convert", target_units="kilometer",
                   unit_definitions={"x": ["meter", "second"]})
    assert conv["success"] is False
    assert "多个读数" in conv["error"]

    single = run_dim("x", operation="convert", target_units="centimeter",
                     unit_definitions={"x": "meter"})
    assert single["success"] is True and single["result"] == 100.0

    dim_convert = run_dim("x", operation="convert", target_units="kilometer",
                          unit_definitions={"x": "dim:L"})
    assert dim_convert["success"] is False
    assert "单位声明" in dim_convert["error"]

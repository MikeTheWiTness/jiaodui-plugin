"""化学式解析与方程式配平测试（移植自旧仓 tests/test_chemistry_balance.py）。

覆盖：基础化学式、含括号化学式（本次修复的核心目标）、复杂多原子离子基团、
配平结果正确性、化学计量计算。
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jiaodui.calc import run_operation
from jiaodui.calc.chemistry import parse_chemical_formula


# ============================================================
# parse_chemical_formula：简单化学式（不应退化）
# ============================================================


@pytest.mark.parametrize("formula,expected", [
    ("H2O", {"H": 2, "O": 1}),
    ("CO2", {"C": 1, "O": 2}),
    ("NaCl", {"Na": 1, "Cl": 1}),
    ("H2SO4", {"H": 2, "S": 1, "O": 4}),
    ("Fe2O3", {"Fe": 2, "O": 3}),
    ("KMnO4", {"K": 1, "Mn": 1, "O": 4}),
    ("NaHCO3", {"Na": 1, "H": 1, "C": 1, "O": 3}),
    ("O2", {"O": 2}),
])
def test_parse_simple(formula, expected):
    assert parse_chemical_formula(formula) == expected


# ============================================================
# parse_chemical_formula：含括号化学式（核心目标）
# ============================================================


@pytest.mark.parametrize("formula,expected", [
    ("Ca(OH)2", {"Ca": 1, "O": 2, "H": 2}),
    ("Fe2(SO4)3", {"Fe": 2, "S": 3, "O": 12}),
    ("Al(OH)3", {"Al": 1, "O": 3, "H": 3}),
    ("Mg(OH)2", {"Mg": 1, "O": 2, "H": 2}),
    ("Ca3(PO4)2", {"Ca": 3, "P": 2, "O": 8}),
    ("(NH4)2SO4", {"N": 2, "H": 8, "S": 1, "O": 4}),
    ("Fe(OH)3", {"Fe": 1, "O": 3, "H": 3}),
    ("Ba(OH)2", {"Ba": 1, "O": 2, "H": 2}),
    ("Cu(OH)2", {"Cu": 1, "O": 2, "H": 2}),
])
def test_parse_parenthesized(formula, expected):
    assert parse_chemical_formula(formula) == expected


def test_parse_empty_string():
    """空字符串。"""
    assert parse_chemical_formula("") == {}


# ============================================================
# 集成：通过 chemistry_balance operation 验证配平结果
# ============================================================


def _balance(equation):
    """调用配平 operation，断言成功并返回 result dict。"""
    r = run_operation("chemistry_balance", equation=equation)
    assert r["success"] is True, f"配平失败（静默错误）: {r.get('error')}"
    return r["result"]


@pytest.mark.parametrize("equation,needles", [
    ("CH4 + O2 -> CO2 + H2O", ["CH4", "2O2", "CO2", "2H2O"]),
    ("Fe + O2 -> Fe2O3", ["4Fe", "3O2", "2Fe2O3"]),
    ("Ca(OH)2 + HCl -> CaCl2 + H2O", ["Ca(OH)2", "2HCl", "CaCl2", "2H2O"]),
    ("Al(OH)3 + HCl -> AlCl3 + H2O", ["Al(OH)3", "3HCl", "AlCl3", "3H2O"]),
    ("Fe(OH)3 -> Fe2O3 + H2O", ["2Fe(OH)3", "Fe2O3", "3H2O"]),
    ("Ba(OH)2 + H2SO4 -> BaSO4 + H2O", ["Ba(OH)2", "H2SO4", "BaSO4", "2H2O"]),
    ("Ca3(PO4)2 + H2SO4 -> CaSO4 + H3PO4", ["Ca3(PO4)2", "3H2SO4"]),
    ("Fe2(SO4)3 + NaOH -> Fe(OH)3 + Na2SO4", ["Fe2(SO4)3", "6NaOH", "2Fe(OH)3", "3Na2SO4"]),
    ("(NH4)2SO4 + Ca(OH)2 -> CaSO4 + NH3 + H2O", ["(NH4)2SO4", "Ca(OH)2", "CaSO4", "2NH3", "2H2O"]),
    ("Cu(OH)2 -> CuO + H2O", ["Cu(OH)2", "CuO", "H2O"]),
])
def test_balance_equations(equation, needles):
    r = _balance(equation)
    eq = r["balanced_equation"]
    for needle in needles:
        assert needle in eq, (equation, eq)


def test_balance_CaOH2_coefficients_locked():
    """含括号输入：配平失败时绝不能静默通过——先断言成功再断言系数。"""
    r = _balance("Ca(OH)2 + HCl -> CaCl2 + H2O")
    assert r["coefficients"] == [1, 2, 1, 2]


def test_balance_Ca3PO42_coeff_count():
    r = _balance("Ca3(PO4)2 + H2SO4 -> CaSO4 + H3PO4")
    assert len(r["coefficients"]) == 4


def test_impossible_equation_handled():
    """不可能发生的反应应返回错误标记或可读结果，不崩溃。"""
    r = run_operation("chemistry_balance", equation="Na + H -> NaH2")
    assert r["success"] is True
    result = r["result"]
    assert result.get("error") is not None or result.get("balanced_equation") is not None


# ============================================================
# 化学计量：由已配平方程式与已知质量求目标质量
# ============================================================


def test_stoichiometry_h2_to_water():
    r = run_operation(
        "stoichiometry", balanced_equation="2H2 + O2 -> 2H2O",
        known_substance="H2", known_mass=4.0, target_substance="H2O",
    )
    assert r["success"] is True
    result = r["result"]
    assert result["mole_ratio"] == "2:2"
    assert abs(result["target_mass_g"] - 35.744) < 0.01


def test_stoichiometry_substance_not_in_equation():
    """已知物质不在方程式中 → 沙箱内返回业务错误（旧仓行为：success True + result.error）。"""
    r = run_operation(
        "stoichiometry", balanced_equation="2H2 + O2 -> 2H2O",
        known_substance="Xe", known_mass=1.0, target_substance="H2O",
    )
    assert r["success"] is True
    assert r["result"]["error"] == "物质不在方程式中"


def test_stoichiometry_missing_molar_mass_rejected():
    """方程式含数据库外物质 → 前置拒绝，不进入沙箱（旧仓 StoichiometryCalcTool 行为）。"""
    r = run_operation(
        "stoichiometry", balanced_equation="Xe + O2 -> XeO2",
        known_substance="Xe", known_mass=1.0, target_substance="XeO2",
    )
    assert r["success"] is False
    assert "Xe" in r["error"]

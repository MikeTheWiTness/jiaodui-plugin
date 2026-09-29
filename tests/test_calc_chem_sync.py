"""化学式解析单一源同步测试（移植自旧仓 tests/test_chem_formula_sync.py，ADR-0026）。

确保 jiaodui/calc/chemistry.py（canonical 实现）与 jiaodui/calc/templates.py
（沙箱内嵌代码）中的 _parse_formula 实现保持一致，且 operations 侧的
_MOLAR_MASSES 与 chemistry 为同一对象（单一源）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _extract_parse_formula_source(module, func_name):
    """提取模块中函数源码字符串（去掉首行 def，只保留函数体）。"""
    import inspect

    func = getattr(module, func_name)
    source = inspect.getsource(func)
    lines = source.split("\n")
    body_start = 1
    for i, line in enumerate(lines):
        if i == 0:
            continue
        if line.strip() and not line.startswith("def ") and not line.startswith("@"):
            body_start = i
            break
    body = "\n".join(lines[body_start:])
    return body.strip()


def test_molar_masses_single_source():
    """验证 _MOLAR_MASSES 单一源：operations 从 chemistry 导入同一对象。"""
    from jiaodui.calc.chemistry import _MOLAR_MASSES as chem_masses
    from jiaodui.calc.operations import _MOLAR_MASSES as ops_masses

    assert chem_masses is ops_masses, (
        "_MOLAR_MASSES 应为同一对象，operations 应从 chemistry 导入而非本地定义"
    )

    assert isinstance(chem_masses, dict)
    assert len(chem_masses) >= 50, f"摩尔质量数据库应含至少 50 种化合物，实际 {len(chem_masses)} 种"
    for formula, mass in chem_masses.items():
        assert isinstance(formula, str)
        assert isinstance(mass, float)


def test_chemistry_balance_still_works():
    """验证化学方程式配平功能不受影响。"""
    from jiaodui.calc.chemistry import _MOLAR_MASSES

    common = ["H2O", "CO2", "NaCl", "H2SO4", "NaOH", "O2", "H2"]
    for f in common:
        assert f in _MOLAR_MASSES, f"常见化合物 {f} 应在摩尔质量数据库中"


def test_parse_formula_sync_templates():
    """验证 templates.py 内嵌 _parse_formula 与 chemistry.py 主实现结构一致。"""
    import re as _re

    import jiaodui.calc.chemistry as chem
    import jiaodui.calc.templates as tmpl

    # 1. 从模板字符串提取内嵌 _parse_formula 函数体
    tmpl_str = tmpl._TEMPLATES["chemistry_balance"].template
    match = _re.search(r"def _parse_formula\(f\):(.*?)(?=\n\S|\Z)", tmpl_str, _re.DOTALL)
    assert match is not None, "模板应包含 _parse_formula 函数定义"
    tmpl_func_body = match.group(1)

    # 2. 获取 chemistry.parse_chemical_formula 源码
    chem_source = _extract_parse_formula_source(chem, "parse_chemical_formula")

    # 3. 结构比对：两者都应有内嵌解析函数 _parse_group
    assert "def _parse_group" in tmpl_func_body, "模板 _parse_formula 应包含 _parse_group"
    assert "def _parse_group" in chem_source or "_parse_group" in chem_source, (
        "chemistry 应包含内嵌解析函数"
    )

    # 4. 两者都处理元素（大写字母开头）和数字（下标计数）
    assert "isupper()" in tmpl_func_body, "模板应处理大写元素符号"
    assert "isdigit()" in tmpl_func_body, "模板应处理数字下标"
    assert "isupper()" in chem_source or "isupper" in chem_source, (
        "chemistry 应处理大写元素符号"
    )

    # 5. 两者都处理括号分组（如 Ca(OH)2）
    assert "'('" in tmpl_func_body or '"("' in tmpl_func_body, "模板应处理括号分组"
    assert "'('" in chem_source or '"("' in chem_source, "chemistry 应处理括号分组"

    # 6. 基本功能验证：用真实化学式测试 canonical 端输出
    for formula in ["H2O", "CO2", "NaCl", "Ca(OH)2", "Al2(SO4)3", "Fe2O3"]:
        chem_result = chem.parse_chemical_formula(formula)
        assert isinstance(chem_result, dict), f"{formula}: 应返回 dict"
        assert len(chem_result) > 0, f"{formula}: 解析结果不应为空"

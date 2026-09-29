"""化学计算纯模块：摩尔质量数据库 + 化学式解析（单一源）。

移植自旧仓 shared/chemistry_tools.py 中的 _MOLAR_MASSES 与 parse_chemical_formula；
旧仓该模块其余部分依赖 langchain/pydantic 与 LLM 调用，未移植。

parse_chemical_formula 是 canonical 实现；jiaodui/calc/templates.py 的
chemistry_balance 模板内联了同逻辑的 _parse_formula（隔离 exec 环境无法 import），
两端须保持同步（见 tests/test_calc_chem_sync.py）。
"""
from __future__ import annotations

_MOLAR_MASSES: dict[str, float] = {
    "H2O": 18.015, "CO2": 44.01, "CO": 28.01, "CH4": 16.04,
    "C2H5OH": 46.07, "C2H4": 28.05, "C2H2": 26.04, "C6H12O6": 180.16,
    "C6H6": 78.11, "C2H6": 30.07,
    "NaCl": 58.44, "NaOH": 40.00, "Na2CO3": 105.99, "NaHCO3": 84.01,
    "Na2O": 61.98, "Na2O2": 77.98, "Na2SO4": 142.04,
    "HCl": 36.46, "H2SO4": 98.08, "HNO3": 63.01, "H3PO4": 98.00,
    "H2O2": 34.01,
    "NH3": 17.03, "NH4Cl": 53.49, "NH4NO3": 80.04, "NO": 30.01, "NO2": 46.01,
    "CaCO3": 100.09, "CaO": 56.08, "Ca(OH)2": 74.09, "CaCl2": 110.98,
    "CaSO4": 136.14, "Ca3(PO4)2": 310.18,
    "Fe": 55.85, "Fe2O3": 159.69, "Fe3O4": 231.53, "FeCl3": 162.20,
    "Fe(OH)2": 89.86, "Fe(OH)3": 106.87, "FeSO4": 151.91,
    "Al": 26.98, "Al2O3": 101.96, "Al(OH)3": 78.00, "AlCl3": 133.34,
    "Al2(SO4)3": 342.15,
    "Cu": 63.55, "CuO": 79.55, "CuSO4": 159.61, "Cu(OH)2": 97.56,
    "Cu2O": 143.09,
    "Zn": 65.38, "ZnO": 81.38, "ZnSO4": 161.44,
    "Ag": 107.87, "AgNO3": 169.87, "AgCl": 143.32,
    "KMnO4": 158.03, "K2Cr2O7": 294.18, "KCl": 74.55, "KOH": 56.11,
    "K2SO4": 174.26,
    "MnO2": 86.94, "SO2": 64.06, "SO3": 80.06,
    "P2O5": 141.94, "SiO2": 60.08,
    "O2": 32.00, "H2": 2.016, "N2": 28.01, "Cl2": 70.90,
    "BaCl2": 208.23, "BaSO4": 233.39, "Ba(OH)2": 171.34,
    "Mg": 24.31, "MgO": 40.30, "Mg(OH)2": 58.32, "MgCl2": 95.21,
}

def parse_chemical_formula(formula: str) -> dict[str, int]:
    """解析化学式字符串，返回元素 → 计数映射。支持括号嵌套，如 Ca(OH)2 → {"Ca": 1, "O": 2, "H": 2}。

    此函数为 canonical 实现。sympy_tools/templates.py 中的 chemistry_balance 模板
    内联了同逻辑的 `_parse_formula`（由于模板在隔离 exec 环境中运行，无法 import），
    两端须保持同步。
    """
    i = 0
    n = len(formula)

    def _parse_group() -> dict[str, int]:
        nonlocal i
        gc: dict[str, int] = {}
        while i < n and formula[i] != ')':
            if formula[i] == '(':
                i += 1  # skip '('
                inner = _parse_group()
                if i < n and formula[i] == ')':
                    i += 1
                num_start = i
                while i < n and formula[i].isdigit():
                    i += 1
                mult = int(formula[num_start:i]) if i > num_start else 1
                for el, cnt in inner.items():
                    gc[el] = gc.get(el, 0) + cnt * mult
            elif formula[i].isupper():
                el_start = i
                i += 1
                while i < n and formula[i].islower():
                    i += 1
                el = formula[el_start:i]
                num_start = i
                while i < n and formula[i].isdigit():
                    i += 1
                cnt = int(formula[num_start:i]) if i > num_start else 1
                gc[el] = gc.get(el, 0) + cnt
            else:
                i += 1
        return gc

    return _parse_group()

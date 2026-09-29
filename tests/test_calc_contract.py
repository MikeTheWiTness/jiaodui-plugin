"""jiaodui.calc 符号计算沙箱行为合约测试（移植自旧仓 tests/test_sympy_tools_contract.py）。

锁定：符号白名单防劫持、浮点容差、退化输入报错、无穷/复数序列化形态、
OPERATIONS 元数据、run_operation 参数校验、code 字段保留（issue 058）。
全部通过 run_operation 实调（走 sandbox 子进程）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jiaodui.calc import OPERATIONS, execute_code, run_operation


# ---- P1：白名单符号防劫持 ----

def test_symbols_not_hijacked_by_sympy_global():
    assert run_operation("evaluate", expression="alpha*beta")["result"] == "alpha*beta"
    assert run_operation("evaluate", expression="S*3")["result"] == "3*S"
    assert run_operation("evaluate", expression="I**2")["result"] == "I**2"  # Symbol 而非 -1


def test_pi_still_constant():
    r = run_operation("evaluate", expression="2*pi")
    assert r["success"] is True
    assert abs(r["result"] - 6.28318530718) < 1e-9


def test_formula_solve_current_I():
    r = run_operation("formula", formula="I = B*L*v/(R+r)", solve_for="I")
    assert r["success"] is True
    assert r["result"] is not None
    assert "B" in r["result"] and "v" in r["result"]


def test_formula_solve_F_with_values():
    r = run_operation(
        "formula", formula="F = B*I*L", solve_for="F",
        substitutions={"B": 1, "I": 2.5, "L": 1},
    )
    assert r["success"] is True
    assert r["result"] == 2.5


def test_geometry_still_works():
    r = run_operation(
        "geometry",
        expression="Line(Point(0,0), Point(1,1)).angle_between(Line(Point(0,0), Point(1,0)))",
    )
    assert r["success"] is True
    assert abs(r["result"] - 0.785398163397) < 1e-6


# ---- P2：浮点容差 ----

def test_equality_float_tolerance():
    r = run_operation("equality", expression_a="0.1+0.2", expression_b="0.3")
    assert r["success"] is True
    assert r["result"] is True


def test_equality_still_detects_inequality():
    r = run_operation("equality", expression_a="0.3", expression_b="0.4")
    assert r["result"] is False


def test_equality_trig_identity():
    r = run_operation("equality", expression_a="sin(x)**2 + cos(x)**2", expression_b="1")
    assert r["result"] is True


# ---- P9：退化输入 ----

def test_angle_zero_vector_rejected():
    r = run_operation("vector_ops", vector_operation="angle", vec_a=[1, 0], vec_b=[0, 0])
    assert r["success"] is False
    assert "零向量" in r["error"]


def test_projection_zero_vector_rejected():
    r = run_operation("vector_ops", vector_operation="projection", vec_a=[1, 0], vec_b=[0, 0])
    assert r["success"] is False


def test_circle_same_points_rejected():
    r = run_operation(
        "circle_from_two_points",
        entry_point=["0", "0"], velocity_direction=[1, 0],
        impact_point=["0", "0"], impact_normal=[0, 1],
    )
    assert r["success"] is False
    assert "重合" in r["error"]


def test_circle_zero_direction_rejected():
    r = run_operation(
        "circle_from_two_points",
        entry_point=["0", "0"], velocity_direction=[0, 0],
        impact_point=["0", "2"], impact_normal=[0, 1],
    )
    assert r["success"] is False


# ---- P10：序列化分支 ----

def test_division_by_zero_marked():
    r = run_operation("evaluate", expression="1/0")
    assert r["success"] is True
    assert "未定义" in r["result"]


def test_sqrt_negative_one_complex_form():
    r = run_operation("evaluate", expression="sqrt(-1)")
    assert r["success"] is True
    assert r["result"] == "0+1i"


# ---- OPERATIONS 元数据（operation 名与旧仓一致） ----

_EXPECTED_OPS = {
    "evaluate", "simplify", "solve", "equality", "differentiate", "integrate",
    "formula", "dimensional", "limit", "geometry", "vector_ops",
    "circle_from_two_points", "chemistry_balance", "stoichiometry",
}


def test_operations_registry_shape():
    assert set(OPERATIONS) == _EXPECTED_OPS
    for name, meta in OPERATIONS.items():
        assert meta["summary"], name
        assert isinstance(meta["params"], list)
        for spec in meta["params"]:
            assert set(spec) == {"name", "required", "type", "default", "help"}, (name, spec)
            assert isinstance(spec["required"], bool)


def test_dimensional_subop_param_present():
    names = {p["name"] for p in OPERATIONS["dimensional"]["params"]}
    assert "dim_operation" in names


def test_vector_subop_param_present():
    names = {p["name"] for p in OPERATIONS["vector_ops"]["params"]}
    assert "vector_operation" in names


# ---- 参数校验 ----

def test_unknown_operation_returns_structured_error():
    r = run_operation("does_not_exist")
    assert r["success"] is False
    assert "Unknown operation" in r["error"]
    assert r["result"] is None


def test_missing_required_param_rejected():
    r = run_operation("limit", expression="sin(x)/x", variable="x")
    assert r["success"] is False
    assert "缺少必填参数" in r["error"]
    assert "approach" in r["error"]


def test_type_error_is_readable():
    r = run_operation("evaluate", expression=123)
    assert r["success"] is False
    assert "类型错误" in r["error"]
    assert "expression" in r["error"]


def test_list_element_type_error_is_readable():
    r = run_operation("vector_ops", vector_operation="dot", vec_a=[1, "x"], vec_b=[1, 0])
    assert r["success"] is False
    assert "类型错误" in r["error"]


# ---- issue 058：code 字段必须保留（由上层投影裁剪） ----

def test_success_body_has_five_keys_and_code_preserved():
    r = run_operation("evaluate", expression="1+1")
    assert set(r) == {"success", "result", "error", "code", "elapsed_ms"}
    assert r["success"] is True
    assert r["result"] == 2
    assert isinstance(r["code"], str) and "1+1" in r["code"]


def test_failure_body_has_same_five_keys():
    r = run_operation("nope")
    assert set(r) == {"success", "result", "error", "code", "elapsed_ms"}


def test_dangerous_code_blocked_by_safety():
    r = execute_code("import os\nprint(os.getcwd())")
    assert r["success"] is False
    assert "Dangerous operation blocked" in r["error"]
    assert r["code"]

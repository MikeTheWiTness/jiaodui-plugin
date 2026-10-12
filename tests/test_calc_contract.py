"""jiaodui.calc 符号计算沙箱行为合约测试（移植自旧仓 tests/test_sympy_tools_contract.py）。

锁定：符号白名单防劫持、浮点容差、退化输入报错、无穷/复数序列化形态、
OPERATIONS 元数据、run_operation 参数校验、code 字段保留（issue 058）。
全部通过 run_operation 实调（走 sandbox 子进程）。
"""

import os
import sys

import pytest

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


def test_lambda_is_a_symbol_in_expression_and_substitution():
    r = run_operation(
        "evaluate", expression="lambda*x + lambda2", substitutions={"lambda": 3, "x": 4, "lambda2": 5}
    )
    assert r["success"] is True
    assert r["result"] == 17


def test_lambda_symbol_works_in_solve_and_formula_target():
    solved = run_operation("solve", equations=["lambda + x - 5"], variables=["lambda"])
    assert solved["success"] is True
    assert solved["result"] == [{"lambda": "5 - x"}]

    formula = run_operation("formula", formula="y = lambda*x", solve_for="lambda", substitutions={"y": 6, "x": 2})
    assert formula["success"] is True
    assert formula["result"] == 3


def test_evaluate_rejects_top_level_equation_with_actionable_message():
    r = run_operation("evaluate", expression="x = 1")
    assert r["success"] is False
    assert "evaluate 不接受顶层等式" in r["error"]
    assert "solve" in r["error"] and "formula" in r["error"] and "equality" in r["error"]


def test_evaluate_rejects_multiple_top_level_equations_without_syntax_error():
    r = run_operation("evaluate", expression="x = y = 1")
    assert r["success"] is False
    assert "evaluate 不接受顶层等式" in r["error"]


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


def test_unknown_parameter_is_rejected_instead_of_silently_dropped():
    r = run_operation("evaluate", expression="1+1", expresion="ignored")
    assert r["success"] is False
    assert "未知参数" in r["error"]
    assert "expresion" in r["error"]


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


@pytest.mark.parametrize("snippet", [
    "import os",
    "from os import getcwd",
    "__import__('os')",
    "os.system('ls')",
    "subprocess.run(['ls'])",
    "open('/etc/passwd')",
    "exec('x = 1')",
    "eval('1+1')",
    "[].__class__.__bases__[0].__subclasses__()",
    "getattr(__builtins__, 'eval')('1')",
    "__builtins__['eval']('1')",
    "chr(101)+chr(118)+chr(97)+chr(108)",
])
def test_dangerous_snippets_blocked(snippet):
    """safety 的 30+ 条模式此前只覆盖 1 条：这里按绕过手法逐类取样。"""
    r = execute_code(snippet)
    assert r["success"] is False, f"应被拦截：{snippet}"
    assert "Dangerous operation blocked" in r["error"]


@pytest.mark.parametrize("expression", [
    "1 + 1",
    "2*3 - 1",
    "3**2 + 1",
    "10 / 4",
])
def test_benign_expressions_allowed(expression):
    """正常表达式不得被安全模式误伤（走公开算符入口，与真实调用同一条安全链）。"""
    r = run_operation("evaluate", expression=expression)
    assert r["success"] is True, r.get("error")
    assert r["error"] is None

# ---- R5：圆几何约束一致性（联立真实约束，拒绝伪圆） ----

def test_circle_returns_circle_through_both_points():
    """独立核算：圆心 (11/2, -2) 到入射点 (1.5, 1) 与撞击点 (0.5, -2) 距离均为 5。"""
    r = run_operation(
        "circle_from_two_points",
        entry_point=["1.5", "1"], velocity_direction=[3, 4],
        impact_point=["0.5", "-2"], impact_normal=[0, 1],
    )
    assert r["success"] is True, r.get("error")
    assert r["result"]["center"] == ["11/2", "-2"]
    assert r["result"]["radius"] == "5"


def test_circle_rejects_non_equidistant_pseudo_circle():
    """审查 R5 复现：旧实现返回不经过撞击点的伪圆，必须改为明确报错。"""
    r = run_operation(
        "circle_from_two_points",
        entry_point=["1.5", "1"], velocity_direction=[3, 4],
        impact_point=["0", "-1.5"], impact_normal=[0, 1],
    )
    assert r["success"] is False
    assert r["result"] is None
    assert "不在同一圆" in r["error"] or "冲突" in r["error"]


def test_circle_rejects_small_scale_non_equidistant_pseudo_circle():
    result = run_operation(
        "circle_from_two_points",
        entry_point=["0.0000165", "0.000011"], velocity_direction=[3, 4],
        impact_point=["0", "-0.0000165"], impact_normal=[0, 1],
    )
    assert result["success"] is False
    assert "冲突" in result["error"] or "不在同一圆" in result["error"]


def test_circle_accepts_consistent_micro_scale_geometry():
    result = run_operation(
        "circle_from_two_points",
        entry_point=["0.0000015", "0.000001"], velocity_direction=[3, 4],
        impact_point=["0.0000005", "-0.000002"], impact_normal=[0, 1],
    )
    assert result["success"] is True, result.get("error")


def test_circle_rejects_normal_pointing_away_from_entry_side():
    """法向量按约定应指向入射点所在侧；反向时不得静默给圆。"""
    r = run_operation(
        "circle_from_two_points",
        entry_point=["1.5", "1"], velocity_direction=[3, 4],
        impact_point=["0.5", "-2"], impact_normal=[0, -1],
    )
    assert r["success"] is False
    assert r["result"] is None
    assert "法向量" in r["error"]


def test_circle_parallel_constraints_rejected():
    """速度方向与撞击面法向量平行时约束退化，无法确定唯一圆心。"""
    r = run_operation(
        "circle_from_two_points",
        entry_point=["0", "0"], velocity_direction=[0, 1],
        impact_point=["0", "2"], impact_normal=[0, 1],
    )
    assert r["success"] is False
    assert r["result"] is None


# ---- R6：formula 多解不静默取首解 ----

def test_formula_multiple_real_roots_reported_as_ambiguous():
    """E=m*v**2/2、E=100、m=2 有 ±10 两个代数根，必须显式报歧义。"""
    r = run_operation("formula", formula="E = m*v**2/2", solve_for="v",
                      substitutions={"E": 100, "m": 2})
    assert r["success"] is True
    result = r["result"]
    assert isinstance(result, dict), result
    assert result.get("ambiguous") is True
    assert sorted(float(v) for v in result["solutions"]) == [-10.0, 10.0]


def test_formula_symbolic_multiple_roots_reported_as_ambiguous():
    r = run_operation("formula", formula="E = m*v**2/2", solve_for="v")
    assert r["success"] is True
    result = r["result"]
    assert isinstance(result, dict) and result.get("ambiguous") is True
    # 独立来源：v² = 2E/m 的两个代数根为 ±sqrt(2)*sqrt(E/m)
    assert set(result["solutions"]) == {"-sqrt(2)*sqrt(E/m)", "sqrt(2)*sqrt(E/m)"}


def test_formula_unique_root_still_returns_scalar():
    r = run_operation("formula", formula="v = u + a*t", solve_for="a",
                      substitutions={"v": 20, "u": 0, "t": 5})
    assert r["success"] is True
    assert r["result"] == 4


# ---- R7：differentiate 执行「求导后代入」 ----

def test_differentiate_applies_substitutions_after_derivative():
    r = run_operation("differentiate", expression="x**2", variable="x",
                      substitutions={"x": 3})
    assert r["success"] is True
    assert r["result"] == 6


def test_differentiate_higher_order_then_substitutes():
    r = run_operation("differentiate", expression="x**3", variable="x", order=2,
                      substitutions={"x": 2})
    assert r["success"] is True
    assert float(r["result"]) == 12


def test_differentiate_without_substitutions_keeps_symbolic_derivative():
    r = run_operation("differentiate", expression="x**3 + 2*x", variable="x")
    assert r["success"] is True
    assert r["result"] == "3*x**2 + 2"


def test_differentiate_symbolic_substitution_value():
    r = run_operation("differentiate", expression="x**2", variable="x",
                      substitutions={"x": "a+1"})
    assert r["success"] is True
    assert r["result"] == "2*a + 2"


# ---- 复核补充：代入后去重、零解、大尺度容差、维度校验、符号语义 ----

def test_formula_distinct_nearby_roots_remain_ambiguous():
    result = run_operation("formula", formula="y = x**2", solve_for="x",
                           substitutions={"y": 1e-20})
    assert result["success"] is True
    assert result["result"]["ambiguous"] is True
    assert len(result["result"]["solutions"]) == 2


def test_circle_direction_vector_scale_does_not_change_validity():
    base = run_operation(
        "circle_from_two_points", entry_point=["1.5", "1"], velocity_direction=[3, 4],
        impact_point=["0.5", "-2"], impact_normal=[0, 1])
    scaled = run_operation(
        "circle_from_two_points", entry_point=["1.5", "1"], velocity_direction=[3e-6, 4e-6],
        impact_point=["0.5", "-2"], impact_normal=[0, 1e-6])
    assert base["success"] is True and scaled["success"] is True
    assert scaled["result"] == base["result"]


def test_formula_roots_collapsing_after_substitution_is_not_ambiguous():
    """E=0 时 ±根代入后都塌缩为 0，是唯一解而非歧义。"""
    r = run_operation("formula", formula="E = m*v**2/2", solve_for="v",
                      substitutions={"E": 0, "m": 2})
    assert r["success"] is True
    assert not isinstance(r["result"], dict), r["result"]
    assert float(r["result"]) == 0.0


def test_formula_target_absent_from_equation_returns_null():
    r = run_operation("formula", formula="a = b", solve_for="c")
    assert r["success"] is True
    assert r["result"] is None


def test_circle_large_scale_consistent_floats_accepted():
    """R=2e6 的自洽浮点圆不应被绝对容差误判为条件冲突。"""
    import math
    import sympy
    radius = 2e6
    a, b = 0.7, 2.1
    r = run_operation(
        "circle_from_two_points",
        entry_point=[repr(radius * math.cos(a)), repr(radius * math.sin(a))],
        velocity_direction=[-math.sin(a), math.cos(a)],
        impact_point=[repr(radius * math.cos(b)), repr(radius * math.sin(b))],
        impact_normal=[math.sin(b), -math.cos(b)],
    )
    assert r["success"] is True, r.get("error")
    got = float(sympy.sympify(r["result"]["radius"]))
    assert abs(got - radius) < 1e-6 * radius


def test_circle_direction_vectors_must_be_two_dimensional():
    for bad_vector in ([1, 0, 99], [1]):
        r = run_operation(
            "circle_from_two_points",
            entry_point=["0", "0"], velocity_direction=bad_vector,
            impact_point=["1", "1"], impact_normal=[0, 1],
        )
        assert r["success"] is False
        assert "必须各含 2" in r["error"]


def test_circle_symbolic_consistent_input_returns_scaled_circle():
    """符号坐标在方向/法向量为精确整数时应得到同一符号圆，而不是报冲突。"""
    r = run_operation(
        "circle_from_two_points",
        entry_point=["1.5*h", "h"], velocity_direction=[3, 4],
        impact_point=["0.5*h", "-2*h"], impact_normal=[0, 1],
    )
    assert r["success"] is True, r.get("error")
    assert r["result"]["center"] == ["11*h/2", "-2*h"]

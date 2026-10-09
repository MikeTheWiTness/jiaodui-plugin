"""材料轮次执行策略与固定预算。"""
from __future__ import annotations

from .errors import BusinessError

BUDGETS = {
    "entry_question": 2,
    "call_correction": 2,
    "report_correction": 3,
    "unit_recovery": 2,
    "technical_retry": 1,
    "calculation_correction": 2,
}


def new_policy(*, mode: str = "automatic", origin: str = "confirmed", confirmed_at: str) -> dict:
    if not isinstance(mode, str) or mode not in {"automatic", "interactive"}:
        raise BusinessError("执行模式必须为 automatic 或 interactive", code="invalid-execution-policy")
    if not isinstance(origin, str) or origin not in {"user", "confirmed"}:
        raise BusinessError("执行策略来源必须为 user 或 confirmed", code="invalid-execution-policy")
    return {"mode": mode, "origin": origin, "confirmed_at": confirmed_at,
            "budgets": dict(BUDGETS), "spent": {key: 0 for key in BUDGETS}}


def validate_policy(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {"mode", "origin", "confirmed_at", "budgets", "spent"}:
        return False
    if not isinstance(value.get("mode"), str) or value["mode"] not in {"automatic", "interactive"}:
        return False
    if not isinstance(value.get("origin"), str) or value["origin"] not in {"user", "confirmed"}:
        return False
    if not isinstance(value.get("confirmed_at"), str) or not value["confirmed_at"]:
        return False
    budgets = value.get("budgets")
    if (not isinstance(budgets, dict) or set(budgets) != set(BUDGETS)
            or any(type(budgets[key]) is not int or budgets[key] != expected
                   for key, expected in BUDGETS.items())):
        return False
    spent = value.get("spent")
    return (isinstance(spent, dict) and set(spent) == set(BUDGETS)
            and all(type(n) is int and 0 <= n <= BUDGETS[key] for key, n in spent.items()))


def spend(policy: dict, category: str) -> None:
    if not isinstance(category, str) or category not in BUDGETS:
        raise BusinessError(f"未知执行预算类别：{category}", code="invalid-budget-category")
    count = policy["spent"][category]
    if count >= BUDGETS[category]:
        raise BusinessError(f"执行预算已耗尽：{category}", code="execution-budget-exhausted",
                            details={"category": category, "budget": BUDGETS[category]})
    policy["spent"][category] = count + 1

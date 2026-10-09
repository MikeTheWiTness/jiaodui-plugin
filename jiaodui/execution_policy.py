"""材料轮次执行策略与按单元固定预算。"""
from __future__ import annotations

import re

from .errors import BusinessError

BUDGETS = {
    "call_correction": 2,
    "calc_representation": 2,
    "report_repair": 3,
    "targeted_review": 2,
    "technical_redispatch": 1,
    "image_schema_fix": 2,
}

_LEGACY_BUDGETS = {
    "entry_question": 2,
    "call_correction": 2,
    "report_correction": 3,
    "unit_recovery": 2,
    "technical_retry": 1,
    "calculation_correction": 2,
}
_UNIT_NAME_RE = re.compile(r"(?:第\d+题|单元\d+|板块\d+)")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def new_policy(*, mode: str, origin: str, confirmed_at: str) -> dict:
    if not isinstance(mode, str) or mode not in {"automatic", "interactive"}:
        raise BusinessError("执行模式必须为 automatic 或 interactive", code="invalid-execution-policy")
    if not isinstance(origin, str) or origin not in {"user", "confirmed"}:
        raise BusinessError("执行策略来源必须为 user 或 confirmed", code="invalid-execution-policy")
    return {"mode": mode, "origin": origin, "confirmed_at": confirmed_at,
            "budgets": dict(BUDGETS), "spent": {}}


def is_current_policy(value: object) -> bool:
    return (isinstance(value, dict) and value.get("budgets") == BUDGETS
            and isinstance(value.get("spent"), dict)
            and all(isinstance(v, dict) for v in value["spent"].values()))


def validate_policy(value: object) -> bool:
    """验证新策略和 transitional 旧字段；旧策略不构成当前轮授权。"""
    if not isinstance(value, dict) or set(value) != {
            "mode", "origin", "confirmed_at", "budgets", "spent"}:
        return False
    if (not isinstance(value.get("mode"), str) or value["mode"] not in {"automatic", "interactive"}
            or not isinstance(value.get("origin"), str) or value["origin"] not in {"user", "confirmed"}
            or not isinstance(value.get("confirmed_at"), str) or not value["confirmed_at"]):
        return False
    budgets, spent = value["budgets"], value["spent"]
    if not isinstance(budgets, dict) or not isinstance(spent, dict):
        return False
    if budgets == _LEGACY_BUDGETS:
        return (set(budgets) == set(_LEGACY_BUDGETS)
                and all(type(budgets[key]) is int and budgets[key] == amount
                        for key, amount in _LEGACY_BUDGETS.items())
                and set(spent) == set(_LEGACY_BUDGETS)
                and all(type(count) is int and 0 <= count <= _LEGACY_BUDGETS[key]
                        for key, count in spent.items()))
    if set(budgets) != set(BUDGETS) or any(
            type(budgets[key]) is not int or budgets[key] != amount
            for key, amount in BUDGETS.items()):
        return False
    return all(
        isinstance(unit, str) and _UNIT_NAME_RE.fullmatch(unit)
        and isinstance(counts, dict) and set(counts) == set(BUDGETS)
        and all(type(count) is int and 0 <= count <= BUDGETS[key]
                for key, count in counts.items())
        for unit, counts in spent.items()
    )


def migrate_legacy_spent(policy: dict, units: list[str]) -> dict:
    """旧轮次的聚合计数无法归因，按每个单元保守迁移，避免重置额度。"""
    old = policy.get("spent") or {}
    mapped = {
        "call_correction": old.get("call_correction", 0),
        "calc_representation": old.get("calculation_correction", 0),
        "report_repair": old.get("report_correction", 0),
        "targeted_review": 0,
        "technical_redispatch": max(old.get("unit_recovery", 0), old.get("technical_retry", 0)),
        # 旧版本将图像 schema 修正记在 call_correction，无法再单独区分。
        "image_schema_fix": old.get("call_correction", 0),
    }
    per_unit = {}
    for unit in units:
        per_unit[unit] = {key: min(value, BUDGETS[key]) for key, value in mapped.items()}
    return per_unit


def _charges(category: str) -> tuple[str, ...]:
    if not isinstance(category, str) or category not in BUDGETS:
        raise BusinessError(f"未知执行预算类别：{category}", code="invalid-budget-category")
    if category == "image_schema_fix":
        return ("image_schema_fix", "call_correction")
    return (category,)


def spend(policy: dict, unit: str, category: str) -> None:
    if not isinstance(unit, str) or not _UNIT_NAME_RE.fullmatch(unit):
        raise BusinessError("预算必须绑定契约单元名", code="unit-path-mismatch")
    charges = _charges(category)
    spent = policy["spent"].setdefault(unit, {key: 0 for key in BUDGETS})
    for key in charges:
        if spent[key] >= BUDGETS[key]:
            raise BusinessError(f"执行预算已耗尽：{unit}/{key}", code="execution-budget-exhausted",
                                details={"unit": unit, "category": key, "budget": BUDGETS[key]})
    for key in charges:
        spent[key] += 1


def validate_attempt(attempt_id: object, fingerprint: object) -> tuple[str, str]:
    if not isinstance(attempt_id, str) or not attempt_id.strip() or len(attempt_id) > 200:
        raise BusinessError("attempt_id 必须是 1..200 字符的非空字符串", code="invalid-attempt-id")
    if not isinstance(fingerprint, str) or not _SHA256_RE.fullmatch(fingerprint):
        raise BusinessError("fingerprint 必须是小写 64 位 SHA256", code="invalid-attempt-fingerprint")
    return attempt_id, fingerprint

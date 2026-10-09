"""执行策略与恢复预算的纯机制（无 IO、无 json）。

模块形状取自 main 的 `execution_policy.py`：策略与落盘分离，机制可单测。
分支侧原先把这些内嵌在 `material.py` 里，B1 把它搬出来，并采纳 main 的两条语义：

- `charges()`：图片格式修复**连带扣** `call_correction`（一次修复同时占调用成本）；
- `charge()`：扣费决策（含"任一被扣类别余额不足即整次拒绝、不部分扣费"）。

存储形态仍是分支的清单形态（`run.execution_policy.budgets` + `run.recovery[unit][类别]`），
不迁移已产出的材料；`material.record_recovery_attempt` 只负责取锁、读盘、记账与落盘。
"""
from __future__ import annotations

import re

from .errors import BusinessError

CATEGORIES: tuple[str, ...] = (
    "call_correction",
    "calc_representation",
    "report_repair",
    "targeted_review",
    "technical_redispatch",
    "image_schema_fix",
)
"""六类恢复预算的类别名（唯一来源；`error_classification` 从这里的类别取值）。"""

BUDGETS: dict[str, int] = {
    "call_correction": 2,
    "calc_representation": 2,
    "report_repair": 3,
    "targeted_review": 2,
    "technical_redispatch": 1,
    "image_schema_fix": 2,
}
"""每单元每轮的固定额度。"""

MODES: tuple[str, ...] = ("automatic", "interactive")
ORIGINS: tuple[str, ...] = ("user", "confirmed")

LEGACY_BUDGETS: dict[str, int] = {
    "entry_question": 2,
    "call_correction": 2,
    "report_correction": 3,
    "unit_recovery": 2,
    "technical_retry": 1,
    "calculation_correction": 2,
}
"""main 时期的材料级聚合预算类别名（用于读旧清单）。"""

_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def charges(category: str) -> tuple[str, ...]:
    """一次恢复要扣的类别。

    图片格式修复本身要占一次调用，所以连带扣 `call_correction`——采纳 main 的
    `_charges` 语义（main 侧有测试锁定）；只扣一类会漏算调用成本。
    """
    if category not in BUDGETS:
        raise BusinessError(f"未知恢复类别：{category!r}", code="recovery-invalid")
    if category == "image_schema_fix":
        return ("image_schema_fix", "call_correction")
    return (category,)


def new_policy(mode: str, origin: str, confirmed_at: str, run_id: str) -> dict:
    """构造绑定当前轮次的执行授权；模式与来源在这里校验。"""
    if mode not in MODES:
        raise BusinessError("执行模式必须为 automatic 或 interactive", code="invalid-execution-mode")
    if origin not in ORIGINS:
        raise BusinessError("执行模式来源必须为 user 或 confirmed", code="invalid-execution-origin")
    return {"mode": mode, "origin": origin, "confirmed_at": confirmed_at,
            "budgets": dict(BUDGETS), "run_id": run_id}


def is_current_policy(policy: object, run_id: str) -> bool:
    """形状与轮次绑定都正确，才算本轮的**有效授权**。"""
    return (isinstance(policy, dict)
            and policy.get("mode") in MODES
            and policy.get("origin") in ORIGINS
            and policy.get("run_id") == run_id
            and isinstance(policy.get("confirmed_at"), str)
            and policy.get("budgets") == dict(BUDGETS))


def is_readable_policy(value: object) -> bool:
    """能否安全读入清单。

    当前形态与**旧聚合形态**都算可读：升级时不能让旧清单连打开都失败。
    可读不等于授权——是否授权由 `is_current_policy` 判定。
    """
    if not isinstance(value, dict):
        return False
    if value.get("mode") not in MODES or value.get("origin") not in ORIGINS:
        return False
    if not isinstance(value.get("confirmed_at"), str):
        return False
    budgets = value.get("budgets")
    if not isinstance(budgets, dict):
        return False
    if set(budgets) == set(BUDGETS):
        return all(type(budgets[key]) is int and budgets[key] == BUDGETS[key] for key in BUDGETS)
    if set(budgets) == set(LEGACY_BUDGETS):
        return all(type(budgets[key]) is int and 0 <= budgets[key] <= LEGACY_BUDGETS[key]
                   for key in budgets)
    return False


def migrate_legacy_spent(policy: dict) -> dict[str, int]:
    """旧聚合 spent → 当前类别计数（每个单元同值，由调用方按单元落账）。

    旧轮次把额度记在材料级、无法归因到单元，按 main 的映射保守迁移：
    `entry_question` 丢弃（它不是恢复额度）、`image_schema_fix` 由旧
    `call_correction` 推（旧版把图像 schema 修正记在 call_correction）、
    `technical_redispatch` 取 `unit_recovery` / `technical_retry` 的较大者；
    最后按当前额度取 `min`，宁可少给不可多给。只返回非零项。
    """
    old = policy.get("spent") if isinstance(policy, dict) else None
    if not isinstance(old, dict):
        return {}

    def count(key: str) -> int:
        value = old.get(key, 0)
        return value if type(value) is int and value > 0 else 0

    mapped = {
        "call_correction": count("call_correction"),
        "calc_representation": count("calculation_correction"),
        "report_repair": count("report_correction"),
        "targeted_review": 0,
        "technical_redispatch": max(count("unit_recovery"), count("technical_retry")),
        "image_schema_fix": count("call_correction"),
    }
    return {key: min(value, BUDGETS[key]) for key, value in mapped.items() if value}


def validate_fingerprint(fingerprint: object) -> str:
    """失败指纹必须是小写 64 位 SHA-256。"""
    if not isinstance(fingerprint, str) or not _SHA256_RE.fullmatch(fingerprint):
        raise BusinessError("SHA-256失败指纹无效", code="recovery-invalid")
    return fingerprint


def charge(recovery: dict, category: str, fingerprint: str) -> dict:
    """从单元的恢复账本扣一次，返回结果字典（只改 `recovery`，不碰其它状态）。

    - 先判 `charges(category)` 的**全部**余额：任一不足即整次拒绝，**不做部分扣费**；
    - 成功时主类别记失败指纹，连带类别只记成本（连带扣是调用成本，不是新的失败）。
    """
    charged = charges(category)
    states = {key: recovery.setdefault(key, {"used": 0, "fingerprints": {}})
              for key in charged}
    blocked = next((key for key in charged if states[key]["used"] >= BUDGETS[key]), None)
    if blocked is not None:
        state = states[blocked]
        return {"allowed": False, "retryable": False, "category": category,
                "charged": list(charged), "blocked_category": blocked,
                "used": state["used"], "budget": BUDGETS[blocked], "remaining": 0,
                "fingerprint_attempts": state["fingerprints"].get(fingerprint, 0)}
    primary = states[category]
    primary["used"] += 1
    primary["fingerprints"][fingerprint] = primary["fingerprints"].get(fingerprint, 0) + 1
    for key in charged:
        if key != category:
            states[key]["used"] += 1
    return {"allowed": True, "retryable": True, "category": category,
            "charged": list(charged), "used": primary["used"], "budget": BUDGETS[category],
            "remaining": BUDGETS[category] - primary["used"],
            "fingerprint_attempts": primary["fingerprints"][fingerprint]}

"""M5 恢复预算的错误码分类（单一源）。

PLAN-rework-continuation P5 第 1 项：core 增一份「错误码 → 恢复类别」映射，
恢复入口只接受已分类的码；未分类码拒绝并给出建议。

为什么要有它：预算与指纹记账已经能防重复，但**类别由模型自选**，于是同一类
故障可能被记进不同预算（第 11/12 讲回放里 `unit_events[].source` 出现了整段
散文就是征兆）。把「这个错误该花哪一类额度」变成确定性映射之后，编排侧只报
错误码，类别的选择不再依赖模型判断。

约定：
- `classify_error` 是纯函数，不读磁盘、不抛错；调用方据 `recoverable` 决定拒绝还是记账。
- 用户取消与权限拒绝**不可恢复**，因此它们没有类别——这正是「用户取消不重派」的
  确定性落点，不靠编排侧自觉。
- 前缀规则按顺序匹配，最具体的写在最前（如 `proposal.calc-*` 先于 `proposal.*`）。
"""
from __future__ import annotations

from .execution_policy import BUDGETS as RECOVERY_BUDGETS
from .execution_policy import CATEGORIES as RECOVERY_CATEGORIES

# 类别与额度只有一份定义（jiaodui/execution_policy.py）；这里重导出，保持既有调用面。
__all__ = ["RECOVERY_BUDGETS", "RECOVERY_CATEGORIES", "classify_error"]

NON_RECOVERABLE_CODES: frozenset[str] = frozenset({
    "user-cancel", "user_cancel",
    "permission-denied", "permission_denied",
})
"""不可恢复：用户取消与权限拒绝只留痕，不消耗预算、不重派。"""

ERROR_CATEGORY_EXACT: dict[str, str] = {
    # 调用形态类：改参数 / 重新取位置或快照后重试
    "usage": "call_correction",
    "not_found": "call_correction",
    "unsupported": "call_correction",
    "host-edit-precondition": "call_correction",
    "host-tool-schema": "call_correction",
    "snapshot-stale": "call_correction",
    "unit-input-mismatch": "call_correction",
    "run-changed": "call_correction",
    "unit-set-mismatch": "call_correction",
    "identity-missing": "call_correction",
    "identity-mismatch": "call_correction",
    "unit-path-mismatch": "call_correction",
    "paper-path-mismatch": "call_correction",
    "manifest-required": "call_correction",
    "invalid-manifest": "call_correction",
    "workspace-required": "call_correction",
    "outside-workspace": "call_correction",
    "invalid-source": "call_correction",
    "invalid-material-name": "call_correction",
    "material-conflict": "call_correction",
    "layout-conflict": "call_correction",
    "invalid-boundaries": "call_correction",
    "mode-required": "call_correction",
    "mode-conflict": "call_correction",
    "invalid-execution-mode": "call_correction",
    "invalid-execution-origin": "call_correction",
    "execution-policy-required": "call_correction",
    "execution-policy-locked": "call_correction",
    "event-invalid": "call_correction",
    "cancel-invalid": "call_correction",
    "recovery-invalid": "call_correction",
    "recovery-error-code-required": "call_correction",
    "self-check-missing": "call_correction",
    "review-invalid": "call_correction",
    "review-stale": "call_correction",
    "review-issue-required": "call_correction",
    "review-legacy-not-supported": "call_correction",
    "parse-failed": "call_correction",
    "parse-v2-requires-submit": "call_correction",
    "data-invalid": "call_correction",
    "data-missing": "call_correction",
    "proposal-json-invalid": "call_correction",
    "proposal-revision-stale": "call_correction",
    "source-overwrite": "call_correction",
    "archive-conflict": "call_correction",
    "output-required": "call_correction",
    # 计算表示类：算式写法 / 参数表示 / 证据绑定
    "calc_failed": "calc_representation",
    "calc-evidence-invalid": "calc_representation",
    "proposal.calc-call-mismatch": "calc_representation",
    # 报告类：闸门、完整性、语法、定位
    "verify_failed": "report_repair",
    "contract": "report_repair",
    "out-of-contract": "report_repair",
    "report-restore-mismatch": "report_repair",
    "report-changed": "report_repair",
    # 图片类：读图参数、资源缺失、白底副本
    "images-invalid": "image_schema_fix",
    # 技术类：环境、宿主超时/崩溃（与单元内容无关）
    "env": "technical_redispatch",
    "host-timeout": "technical_redispatch",
    "host-crash": "technical_redispatch",
    "parent-technical-timeout": "technical_redispatch",
}
"""精确匹配的错误码表。

注意 `contract` 是 `BusinessError` 的默认码，当前 4 处用法都是报告/闸门问题
（`unit_delivery.py:91`/`:195`、`workflow.py:434`/`:437`）；新增 `BusinessError`
必须显式给码，不要依赖默认值，否则会被归进报告预算。
"""

ERROR_CATEGORY_PREFIX: tuple[tuple[str, str], ...] = (
    ("proposal.calc", "calc_representation"),
    ("proposal.", "call_correction"),
    ("location.", "call_correction"),
    ("calc", "calc_representation"),
    ("images.", "image_schema_fix"),
    ("syntax.", "report_repair"),
    ("reason.", "report_repair"),
    ("severity.", "report_repair"),
    ("original.", "report_repair"),
    ("integrity.", "report_repair"),
    ("locate.", "report_repair"),
    ("report.", "report_repair"),
    ("marker.", "report_repair"),
)
"""前缀规则，按顺序匹配；`proposal.` 前必须先把 `proposal.calc` 摘出来。"""


def classify_error(code: str) -> dict:
    """把错误码确定性映射到恢复类别。

    返回 `{"code", "recoverable", "forbidden", "category", "reason", "suggestion"}`：
    - `recoverable=False` 表示不得消耗预算；
    - `forbidden=True` 专指用户取消/权限拒绝（策略禁止），与「未分类码」区分开，
      调用方据此给出不同的错误码；
    - `suggestion` 仅在未分类时给出，列出相近的已知码，避免只说「失败」。
    """
    if not isinstance(code, str) or not code.strip():
        return {"code": code, "recoverable": False, "forbidden": False, "category": None,
                "reason": "错误码不能为空", "suggestion": sorted(ERROR_CATEGORY_EXACT)[:8]}
    normalized = code.strip()
    if normalized in NON_RECOVERABLE_CODES:
        return {"code": normalized, "recoverable": False, "forbidden": True, "category": None,
                "reason": "用户取消与权限拒绝不得恢复或消耗预算", "suggestion": None}
    category = ERROR_CATEGORY_EXACT.get(normalized)
    if category is None:
        for prefix, mapped in ERROR_CATEGORY_PREFIX:
            if normalized.startswith(prefix):
                category = mapped
                break
    if category is None:
        head = normalized.split(".")[0].split("-")[0]
        near = sorted(
            known for known in list(ERROR_CATEGORY_EXACT)
            + [prefix for prefix, _ in ERROR_CATEGORY_PREFIX]
            if head and (head in known or known.startswith(head))
        )[:6]
        return {"code": normalized, "recoverable": False, "forbidden": False, "category": None,
                "reason": "未分类的错误码，不能凭它消费恢复预算",
                "suggestion": near or sorted(ERROR_CATEGORY_EXACT)[:6]}
    return {"code": normalized, "recoverable": True, "forbidden": False, "category": category,
            "reason": "", "suggestion": None}

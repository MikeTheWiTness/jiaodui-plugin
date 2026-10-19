# revise 校对工具升级计划

日期：2026-10-19。状态：**P0 出口验收通过（用户确认）；已在 `integration/revise-p0-baseline` 分层整理前置与P0候选基线，main尚未合入；P0.5原型另在 `exp/revise-ab`，正式36次未执行，A/B未选定**。分层来源、原工作区保护与本次复验见[基线整理记录](<REVISE-P0-BASELINE.md>)。确认范围、样本验收版本与证据来源见[验收结论](<REVISE-P0-ACCEPTANCE-2026-10-19.md>)，自动验证及CLI/core实测见[P0实施与验收记录](<REVISE-P0-VERIFICATION.md>)。原生插件结论来源于用户确认，非本会话独立执行；本文件的 A/B 接口仍是待实验决策后的目标，不代表已经实现。

初稿见 [PLAN-revise-tool-upgrade.v0-draft.md](PLAN-revise-tool-upgrade.v0-draft.md)。本版整合了对初稿的审查、二次审查与第三轮逐条代码核对的结果（第 3 节决策 D1–D14；修正记录见第 13 节）。

---

## 1. 背景与目标

### 1.1 现状

当前子 agent 的正常链为 `unit_snapshot → unit_read / 读图 / calc → unit_locate → unit_submit`，父侧按当前 snapshot 调用 `unit_review`。子 agent 只提交 schema v2 结构化提案，报告由 core 从不可变源文生成，然后经过 verify、落盘和登记。

### 1.2 已证实的痛点

| 痛点 | 证据 | 现状 |
| --- | --- | --- |
| 定位与修改分两步：先取 `location_id`，再逐字填写 `expected_original` | 第 11 讲单元 3：同一子串误用后提交连撞 20 次，最后放弃该条修改改报「无问题」，造成静默漏报（[source_index.py](../jiaodui/source_index.py) `resolve_location` 注释） | 未解决 |
| `proposal_revision` 与身份/hash 手工填写 | 实测有子代理连撞 2 次（[unit_delivery.py](../jiaodui/unit_delivery.py)） | 插件已在 JS 侧按 snapshot 自动绑定（[index.js](../packages/dsh-jiaodui/tools/index.js) `jiaodui_unit_submit`），但这是壳内逻辑，CLI 路径仍需手填 |
| 修改一处要整包重交 corrections 与 evidence | 交互形态决定 | 未解决 |
| 删去的修订留下的依据仍会进报告 | `render_suggestions` 把全局 `evidence` 整包写入「核验说明」（[report_suggestions.py:609](../jiaodui/report_suggestions.py#L609)） | 未解决 |
| 逐条持久化 / 崩溃续做 | **无实测痛点** | 由 P0.5 判定是否值得做 |

### 1.3 目标

1. 子 agent 用「原文 → 建议 + 原因」直接登记修订，程序即时定位并给出可执行的诊断。
2. 撤回或修改某条修订时，不需要重抄整包，也不会留下残余证据。
3. 报告仍由程序从不可变源文生成，继续经过 verify 与父复核，下游格式不变。
4. 用对照实验决定是否需要持久工作日志，不预设答案。

### 1.4 非目标

纯图片替换、零宽插入、自动改写 Word、重构拆分/学科判断/Word 锚点、数据库式迁移、新的报告格式。

### 1.5 不变的硬约束

- 源文不可变；报告由程序生成；`split_marked_body(marked) == source`。
- 新报告必须过 `verify-report`；父代理按当前 snapshot 复核后才算完成。
- 状态只由磁盘推导；Python 侧零凭证。
- CLI/插件壳不含业务逻辑，两学科共用 core。
- 失败留痕走 `_校对失败.md`；退出码 0–7 语义不变。
- 小样本只证明流程可用，不宣称质量统计提升。

---

## 2. 路线总览

```
P0  共同前置（合入 main，两条分支都依赖）
 │
P0.5 对照实验（独立 worktree，原型不合入）
 │
 ├── A 胜出 ──▶ A1 core v3 ─▶ A2 插件/skill ─▶ A3 真机与切换
 │
 └── B 胜出 ──▶ B0 存储与工作模型 ADR ─▶ B1 代次与修订核心 ─▶ B2 判定接线
                 ─▶ B3 finish 提交 ─▶ B4 schema 升级/回滚 ─▶ B5 插件/skill
                 ─▶ B6 真机与切换 ─▶（B7 可选增强）
```

规则：

- P0 出口评审通过前，不进入 P0.5。
- P0.5 判定结果出来前，不写 A/B 的生产代码。
- 每个阶段结束时跑全量测试与 CI 口径。

---

## 3. 决策记录

| # | 决策 | 适用 |
| --- | --- | --- |
| D1 | **T09**：新布局下 `parse-report` / `repair-report --apply` 默认禁止登记 v1 报告。显式 `--manual-legacy` 只允许写 `_校对数据.json` 并标记 `legacy_manual: true`，**不登记、不计入本轮完成**，下游拒绝消费；若已有 schema v2 数据、当前轮 v2 登记或数据损坏，返回 `legacy-overwrite-v2-forbidden`，不覆盖。没有清单的历史布局（`--legacy-layout`）行为不变 | 共同 |
| D2 | **结构切断**：修订入口在 old_text 切断公式或加粗时拒绝，并返回应覆盖的完整原文；`unit_locate` 保持现有的自动扩展行为 | 共同 |
| D3 | **定位类错误不计预算**：`anchor.*` 与 `revise.*` 归为 `interactive`，不能用于 `unit-recovery`，也不扣六类预算 | 共同 |
| D4 | **证据分层**：`unit_evidence` 负责单元级覆盖；继承时全部证据先归 `unit_evidence`，单引用的 assumption/calculation 记内部 `inherited_ref`，仅在无有效引用时修剪，images 永不因撤回修剪；修订局部证据随有效修订渲染；编译后仍输出 v2 四键 `evidence` | 共同 |
| D5 | **身份与版本绑定收回 core**：`unit-submit --bind-current` 由 core 在锁内填写 task/unit/run/hash/proposal_revision；core 另导出 `unit-schema --bind-current`，插件读随包 bind schema，删除 JS 侧的 snapshot 绑定与 schema 改写 | 共同 |
| D6 | **P0.5 判定门槛**：B 必须同时满足拒绝数 ≤ A × 0.7、输出 token ≤ A × 1.15、耗时 ≤ A × 1.2、漏报 ≤ A；否则采用 A。A 相对基线拒绝数不下降，或漏报增加，则两臂都停 | P0.5 |
| D7 | **存储**：按 P0.5 实测决定。8 并发下 revise **端到端延迟 p95（含等锁）** > 50 ms，或单材料清单增量 > 100 KB，则用独立草稿文件；否则放在清单内。方案 2 的 revise 只取单元级锁，finish/abandon 按 material→unit 顺序取锁 | B |
| D8 | **技术重派不继承草稿**：重派 = 父放弃旧代次 + 新实例开新代次；只有父退回后的 reopen 可以从上一份**已提交**提案继承。任何上一代次为 `submitted`（accepted 或 needs_revision）时，child `open` 必须返回 `work-reopen-required` | B |
| D9 | **单一提交点 + 候选摘要预登记**：代次封存与 `register_locked` 合并为同一次清单写入；写文件前在代次头预登记候选 report/data hash（绑定 `draft_sha256`），代次仍 open 时重新 finish 允许当前文件等于 base 或已登记候选；不引入完整 preparing 日志 | B |
| D10 | **子侧语义幂等**：子侧操作不用 operation_id/CAS，靠语义幂等加代次归属判定；父侧操作沿用 `expected_snapshot_sha256` CAS | B |
| D11 | **代次归属**：代次头记录 `owner_attempt_id`，放弃时把它写入现有 `terminated_attempts`。不以 `unit_state.attempt_id` 判定归属，因为任意 `unit-event` 都会覆盖它 | B |
| D12 | **清单懒升级**：材料首次开代次时把 `schema_version` 升为 2，旧代码因此必然拒绝；提供无 open 代次时的 `material-downgrade`。downgrade 归档到 `units/<材料名>/.superseded/<run_id>/work/`；开关关闭后活 owner 可 finish，失联 owner 由父 abandon 后走旧 `unit-submit` | B |
| D13 | **A 定位拒绝硬上限**：只对 `unit-submit` 的定位类拒绝按单元×轮次计数，8 次后返回 `stop`；`revise_check` 只读干跑不计数。计数写当前 run 的 `unit_state`/action，AGENTS「被拒不写盘」限定为恢复记账 | A |
| D14 | **P0.5 响应丢失重放**：新增 S9（工具成功、响应丢失、模型重试同一操作）。B 必须不重复登记；若 B 在 S9 也不占优，D6 不应仅凭逐条反馈选 B | P0.5 |

---

## 4. P0：共同前置

### 4.1 任务清单

| ID | 任务 | 主要文件 | 规模 |
| --- | --- | --- | --- |
| P0-1 | PRD 增量；ADR 0008「锚点匹配、证据分层与交互类错误」；T09 决策写入 TICKETS | `docs/PRD.html`、`docs/adr/0008-*.md`、`docs/TICKETS-full-chain-2026-10-10.md` | S |
| P0-2 | 锚点解析纯函数 | 新增 `jiaodui/anchor.py` | M |
| P0-3 | 证据分层：合并、拆分与继承修剪纯函数 | 新增 `jiaodui/evidence_layers.py` | M |
| P0-4 | 交互类错误码 | `jiaodui/error_classification.py`、`jiaodui/material.py`（`record_recovery_attempt`） | S |
| P0-5 | T09 收口（D1） | `jiaodui/workflow.py`、`jiaodui/report_repair.py`、`jiaodui/status.py`、`jiaodui/cli.py` | S |
| P0-6 | `unit-submit --bind-current`（D5）；core 导出 bind schema；插件删除 JS 绑定与 schema 改写 | `jiaodui/unit_delivery.py`、`jiaodui/report_suggestions.py`、`jiaodui/cli.py`、两包 `tools/index.js`、两包新增 `tools/proposal-schema-bind-current.json` | M |
| P0-7 | skill 入口瘦身，腾出 ≥ 300 码点 | `skills/jiaodui*/SKILL.md`、`references/operation-manual.md` 及随包副本 | S |
| P0-8 | 冻结实验样本与人工标注 | `tests/fixtures/revise_ab/`、`scripts/freeze_revise_samples.py` | M |

### 4.2 P0-2 锚点解析规格

```python
def resolve_anchor(source_text: str, old_text: str, *,
                   context_before: str = "", context_after: str = "",
                   occurrence: int | None = None) -> AnchorMatch
```

返回 `AnchorMatch(start, end, original, line, column, normalized_match: bool)`；失败时抛 `AnchorError(code, message, details)`。

规则，按执行顺序：

1. `old_text` 为空，返回 `anchor.empty`。
2. 严格逐字查找 `context_before + old_text + context_after`，重叠命中也计数。命中位置只取 old_text 段，上下文不进入替换区间。
3. 严格匹配 0 命中时做匹配期归一化：CRLF→LF，去掉 U+200B–U+200D、U+FEFF。归一化后恰好 1 命中时，把区间映射回源文码点，返回 `normalized_match: true`，`original` 取源文中的逐字原文。不做 NFC、空白折叠或 LaTeX 归一化。
4. 给了 `occurrence` 时，它是对 `context_before + old_text + context_after` 整个匹配串的 1 起命中序号（上下文为空时即 `old_text`；与现有 `query_locations` 的 `match_index` 同义）。归一化命中同样按此序号。越界返回 `anchor.occurrence-out-of-range`。
5. 命中数 ≠ 1 时，返回 `anchor.not-found` 或 `anchor.ambiguous`。`details` 包括 `match_count` 和最多 5 个候选（`match_index`、行列、前后各 24 字符的上下文，不可见字符转义成 `​` 形式显示），以及 `truncated`。
6. 区间与公式/加粗只部分重叠时，返回 `anchor.structure-cut`。`details.required_original` 给出扩展后的完整原文与区间，不静默扩大。
7. 输入上限：`old_text` ≤ 1000 码点，`context_before` / `context_after` 各 ≤ 200 码点，`new_text` ≤ 2000 码点，`reason` ≤ 2000 码点，单条 evidence 文本 ≤ 4000 码点；超出返回 `anchor.too-long` / `revise.too-long`（交互类，不落盘）。

区间冲突由调用方检查，`resolve_anchor` 不管：与其他有效修订重叠返回 `anchor.overlap`（details 给冲突修订 ID 与原文）。`reason` 为空白返回 `revise.reason-empty`。`new_text` 允许为空，表示删除。old_text == new_text 返回 `revise.noop`。

### 4.3 P0-3 证据分层规格

分层结构（v3 提案与工作草稿共用）：

```json
{
  "unit_evidence": {
    "assumptions": [{"id": "a1", "text": "...", "source_locations": []}],
    "symbols": [],
    "images": [{"id": "i1", "reference_index": 1, "readable": true, "semantic": "...", "verdict": "..."}],
    "calculations": [{"id": "k1", "call_id": "...", "expression": "...", "result": 0.5}]
  },
  "corrections": [{"...": "...", "evidence_ids": ["a1"], "evidence": [{"kind": "calculation", "id": "k2", "...": "..."}]}]
}
```

- `images` / `calculations` 可以是 `{"status": "not_applicable", "reason": "..."}`，与 v2 相同。
- 图片项中的 `original_path`、`actual_read_path`、`position` 由 core 按 `reference_index` 从当前图片清单回填；模型只写 `reference_index`、`semantic`、`verdict`、`readable`。
- 修订局部证据 `evidence[]` 的 `kind` 取 `assumption | calculation | image`，字段与对应 v2 项相同。修订 ID 和证据 ID 在同一单元内唯一。
- v2 图片仍要求每个 `reference_index` 恰好一项：同图局部证据编译时以单元图片 ID 为规范 ID，将有效局部的 `semantic` / `verdict` 按修订顺序、带局部证据 ID 标签逐项追加；单元原观察与局部原观察都完整保留，不由 core 裁定语义分歧。局部图片引用改写为规范 ID；撤回只去掉对应追加文本。所有图片 `readable` 必须为 true，路径与位置仍由当前清单回填。此为 P0 实施核对既有 v2 唯一性约束后的编译适配，见 ADR 0008。
- 每条修订必须至少有一个证据引用：`evidence_ids` 指向 `unit_evidence`，或自带 `evidence`。

函数与继承规则：

- `merge_layers(unit_evidence, effective_corrections) -> (v2_evidence, v2_corrections)`：先按**当前有效修订**修剪继承证据，再合并 `unit_evidence` 和有效修订的局部证据，输出 v2 四键 `evidence`；每条修订的 `evidence_ids` 改写为全部引用 ID。被撤回/替代的修订及其局部证据不进入输出。
- `split_v2(proposal_v2) -> (unit_evidence, corrections_with_local)`：继承时**全部证据先归入 `unit_evidence`**；只被一条 correction 引用的 assumption/calculation 额外记内部字段 `inherited_ref: <correction id>`，不移动证据；images 永不加 `inherited_ref`、永不因撤回修剪。
- 修剪规则：带 `inherited_ref` 的 assumption/calculation，仅当 `inherited_ref` 指向的修订已 `retracted` 或 `superseded`，**且没有其他有效修订引用该证据**时移除。`update` 的旧项是 `superseded`，不能只看 `retracted`；新项仍引用则保留。修剪后 `unit_evidence.assumptions` 为空时返回交互错误 `revise.evidence-required`，要求补一条单元依据。
- `inherited_ref` 只存在于 v3/工作草稿，编译 v2 前必须剥除；v2 的 assumption 严格校验不接受多余字段。
- 覆盖校验（假设非空、图片引用全覆盖）**只看 `unit_evidence`**：先执行合并前的覆盖检查；合并内按有效引用修剪后若 assumptions 为空返回 `revise.evidence-required`；随后对合并结果执行现有 v2 校验，确保两层规则都满足。

### 4.4 P0-4 交互类错误

- `ERROR_CATEGORY_PREFIX` 前置 `("anchor.", INTERACTIVE)`、`("revise.", INTERACTIVE)`。
- `classify_error` 对这两类返回 `recoverable: False, interactive: True, reason: "交互诊断：按 details 修正参数后直接重试，不消耗恢复预算"`。
- `record_recovery_attempt` 遇到交互类码时返回 `recovery-interactive-code`（exit 6），不写盘。
- 现有 `location.*` 仍归 `call_correction`，不改。

### 4.5 P0-5 T09 收口

- `workflow.parse_unit`：有清单时，v1 报告不带 `--manual-legacy` 返回 `parse-v1-new-layout-forbidden`（exit 6）。带上时执行 verify 并写 `_校对数据.json`，附 `legacy_manual: true`，**不调用 `material.register`**。
- 若单元已有 schema v2 的 `_校对数据.json`、当前轮 v2 登记或数据损坏，`--manual-legacy` 返回 `legacy-overwrite-v2-forbidden`（exit 6），不覆盖。
- `report_repair --apply` 走同一判定（含 v2 数据保护）。
- `status.status_of_unit` 发现 `legacy_manual` 时判为 `CURRENT_PENDING`，reason 写「人工兼容交付，不计入本轮完成」；`build-report` / `build-docx` 拒绝。

### 4.6 P0-6 绑定收回 core

- `unit-submit` 新增 `--bind-current`：在材料锁内取 snapshot，覆盖提案中的 `task_id / unit_id / run_id / source_sha256 / body_sha256 / proposal_revision`。若提案原本带了这些字段且值不同，返回 `proposal-binding-conflict`，避免静默覆盖调用方的错误认知。仍然要求 `--expected-snapshot-sha256`。
- core 另导出 `unit-schema --bind-current`（全量 schema 去掉 6 个 required）；随包新增 `proposal-schema-bind-current.json`，插件直接读它，不再 clone/改写 schema。全量 `proposal-schema.json` 保持不变，继续与 `unit-schema --json` 逐字一致。
- 两包 `jiaodui_unit_submit` 改为直接透传 `--bind-current`，删除 JS 侧的 snapshot 调用与字段拼接。测试锁：全量 schema parity、bind schema parity、插件只读 bind、缺 6 个身份字段的提案能到 core。

### 4.7 P0-7 skill 预算

- 入口 SKILL.md 上限 8192 码点（[test_skill_docs.py](../tests/test_skill_docs.py)），现为物理 8107、化学 8169。
- 把子 agent 侧的步骤细节移入 `references/operation-manual.md`，入口只留一行指引。目标：两份入口都 ≤ 7850 码点。
- 后续任何分支对入口的**净增 ≤ 0**。

### 4.8 P0-8 样本

9 个物理样本、3 个化学样本（取公式、带图、退回三类；S9 为响应丢失重放）：

| 编号 | 类型 | 人工标注 |
| --- | --- | --- |
| S1 | 无问题 | 期望 0 修订 |
| S2 | 文字错误 | 期望修订的原文、建议、区间 |
| S3 | 重复短语（同一短语 ≥ 3 次，仅 1 处有误） | 正确的 match_index |
| S4 | 公式修订（含 `$...$` 与加粗边界） | 完整原文 |
| S5 | 带图（≥ 2 张，含图文不一致一处） | 图片观察要点 |
| S6 | 同位置误判后撤回 | 最终修订集 |
| S7 | 父复核退回后重交 | 退回意见与期望增量 |
| S8 | 技术中断后重派 | 期望最终修订集 |
| S9 | 响应丢失重放（工具成功、响应丢失后重试同一操作） | 最终修订集不重复、不丢 |

预期值由人工从原文标注，存成 `expected.json`，不用待测代码生成。样本冻结后记录源文 hash。

### 4.9 P0 测试（先红后绿）

| 文件 | 覆盖 |
| --- | --- |
| `tests/test_anchor.py`（新） | 单/零/多命中；重叠命中计数；上下文消歧；上下文不进区间；occurrence 合法与越界；context + occurrence 对组合串计数；CRLF、零宽归一化唯一命中且 `normalized_match`；归一化后多命中仍拒绝；emoji/代理对码点区间；公式、加粗切断拒绝并给 `required_original`；候选截断与不可见字符转义；old/context/new 长度上限 |
| `tests/test_evidence_layers.py`（新） | 单图 + 单修订 split→merge；全部假设只被单条修订引用；撤回/替代后的 `inherited_ref` 修剪；新项仍引用时不修剪；`unit_evidence` 单独满足覆盖；修剪后 assumptions 为空返回交互错误；`split_v2` 归属；merge→split→merge 稳定；图片字段回填 |
| `tests/test_error_classification.py` | `anchor.*`、`revise.*` 为 interactive；`unit-recovery` 用它们被拒且不写盘；`location.*` 仍为 call_correction |
| `tests/test_workflow_milestones.py` / `tests/test_report_repair.py` | 新布局 v1 parse 被拒；`--manual-legacy` 写数据不登记；已有 v2 数据时 `legacy-overwrite-v2-forbidden` 且不覆盖；status 为未完成；下游拒绝；无清单布局不受影响 |
| `tests/test_unit_delivery.py`、`tests/test_dsh_plugin_tool_behavior.py` | `--bind-current` 填写正确；字段冲突被拒；插件只透传；缺 6 个身份字段的提案通过；bind schema 与全量 schema 的差集正确 |
| `tests/test_skill_docs.py` | 入口 ≤ 7850 |

### 4.10 P0 出口

全量与 CI 口径通过；ADR 0008 经评审采纳；样本冻结并有人工标注；插件真机冒烟一次 `unit_submit`（验证 D5 改动后不回退）。

---

## 5. P0.5：对照实验

### 5.1 环境

worktree `exp/revise-ab`，基于 P0 合入后的 main。原型代码不合入 main；分支胜出后，生产实现按红→绿重写，原型只作参考。

### 5.2 三臂

**基线**：当前 `unit_locate → unit_submit`（带 D5）。

**A：无状态 v3**

- `unit-submit` 接受 `schema_version: 3`（结构见 6.2），core 用 P0-2 解析锚点、P0-3 合并证据，再编译为 v2 落盘。
- 新增只读 `unit-revise-check`，干跑单条修订：返回定位结果或 anchor 诊断，不写盘。
- 支持增量重交：`base_proposal_revision` + `withdrawn` + 新增修订。

**B：最小工作日志**

- `unit-work open/read`、`unit-revise add/update/retract`、`unit-finish`。接口按 7.3 的低状态设计（D10/D11）。
- 存储放在清单内（为了测 D7 的体积与端到端延迟）。
- 证据：修订局部证据随 revise 一起给出，`unit_evidence` 与自查在 finish 时给出。
- 原型包含最小父侧 `abandon` 与 `reopen --inherit submitted`；S7 用 reopen 继承，S8 用 abandon + 新 attempt open（不继承，符合 D8）。
- **不做** schema 升级、证据增量登记、7.5 判定接线的完整覆盖。

两臂共用 P0-2/P0-3 的生产实现。插件工具与 skill 说明按各臂单独编写，说明篇幅尽量相当。

### 5.3 执行规程

- 物理 9 样本 × 3 臂 = 27 次单元执行；化学 3 样本 × 3 臂 = 9 次；合计 36 次。
- 每次都在真实宿主上运行，包括真实读图。
- 同一样本三臂使用相同模型、相同学科规范和相同派发提示骨架；臂的执行顺序轮换，以减少时段因素。
- S8 在子 agent 完成 ≥ 2 条修订后由人工强杀，再按各臂的重派方式继续。
- S9 在工具成功返回后由 harness 丢弃响应，再以同一请求重试；记录是否重复登记、是否多一条修订。

### 5.4 指标

记录到 `docs/EXPERIMENT-revise-ab.md`，每次执行一行：

| 字段 | 说明 |
| --- | --- |
| 工具调用数 | 子 agent 全部工具调用 |
| 拒绝数 | 按参数 / 定位 / 提交 / 其他分类计 |
| 最长连续拒绝串 | 用于判断 B 是否加循环上限；A 已有 D13 硬上限 |
| 输出 token | 宿主统计 |
| 墙钟耗时 | 从派发到子 agent 返回 |
| 逐字还原 | 报告能否逐字恢复源文 |
| 误报 / 漏报 | 对照 `expected.json` 人工判定 |
| （B）清单增量 | 执行前后 `_校对记录.json` 字节差 |
| （B）revise 端到端延迟 | 另做 8 进程并发 revise 压测，记 p50/p95（含等锁） |
| S9 重放结果 | 是否重复登记、是否多一条修订 |

### 5.5 判定（D6）

1. A 相对基线：拒绝总数下降且漏报不增加。不满足则两臂都停，回到问题分析，并在实验记录里写明原因。
2. B 相对 A：拒绝数 ≤ A × 0.7，输出 token ≤ A × 1.15，耗时 ≤ A × 1.2，漏报 ≤ A，四项同时满足才走分支 B。
3. 其余情况走分支 A。
4. 任一臂最长连续拒绝串 > 10 时，该臂对应的生产分支必须增加循环上限：A 按 D13 在 core 计数（`unit-submit` 定位拒绝每单元每轮 8 次后 `stop`，`revise_check` 不计）；B 每代次拒绝计数，见 7.9。
5. S9：B 必须不重复登记；若 B 在 S9 也不占优，D6 不应仅凭逐条反馈选 B。

实验结论与判定写入实验记录，并更新本计划的状态行。

---

## 6. 分支 A：无状态 v3（A 胜出时）

### 6.1 任务

| ID | 任务 | 主要文件 | 规模 |
| --- | --- | --- | --- |
| A1-1 | v3 schema 导出与校验 | `jiaodui/report_suggestions.py`（或新增 `jiaodui/proposal_v3.py`） | M |
| A1-2 | v3 → v2 编译器（锚点解析、证据合并、summary 推导、编号） | `jiaodui/proposal_v3.py` | M |
| A1-3 | 增量重交：读取当前 v2 数据，按 `split_v2` 还原，应用 withdrawn 与新增 | 同上 | M |
| A1-4 | `unit-submit` 分派 v2/v3；`unit-revise-check`；`unit-snapshot --with-proposal` | `jiaodui/unit_delivery.py`、`jiaodui/cli.py` | S |
| A1-5 | A 定位拒绝计数与 `stop`（D13） | `jiaodui/unit_delivery.py`、`jiaodui/material.py`、`jiaodui/cli.py` | S |
| A2-1 | 两插件：`jiaodui_unit_submit` 接 v3 schema；新增 `jiaodui_revise_check` 并加入 `UNIT_TOOL_NAMES` | 两包 `tools/index.js`、`tools/proposal-schema-v3.json` | S |
| A2-2 | 两套 skill：子 agent 流程改为 v3（入口净增 ≤ 0），细节进 operation-manual；更新随包副本 | `skills/*`、`packages/*/skills/*` | S |
| A3 | 真机验证与切换（第 9 节） | 测试记录 | M |

### 6.2 v3 提案结构

```json
{
  "schema_version": 3,
  "base_proposal_revision": 2,
  "corrections": [
    {
      "id": "c1",
      "old_text": "研究对象为木板",
      "new_text": "研究对象为木块",
      "context_before": "",
      "context_after": "",
      "occurrence": null,
      "reason": "题干已将研究对象定义为木块，此处对象名称不一致。",
      "category": "term",
      "severity": "一般问题",
      "evidence_ids": ["a1"],
      "evidence": []
    }
  ],
  "withdrawn": [{"id": "c3", "reason": "误判：此处为另一物体"}],
  "unit_evidence": {"assumptions": [{"id": "a1", "text": "...", "source_locations": []}], "symbols": [], "images": [], "calculations": []},
  "self_check": {"status": "passed", "checks": ["..."], "unresolved": []}
}
```

- 身份、hash、`proposal_revision`、`summary` 都不出现在 v3 中，由 core 绑定或推导：summary 取有效修订的最高严重度，空集为「无问题」。
- `base_proposal_revision`、`withdrawn` 只在增量重交时出现。基础提案必须同轮同输入，否则返回 `proposal.base-stale`。增量重交时省略 `unit_evidence` 表示继承基础提案的单元证据；给出则整体替换。继承证据按 4.3 的 `inherited_ref` 规则修剪，`withdrawn` 的局部证据不进报告。
- 修改基础提案中的某条修订 = withdraw 该条 + 新增一条。新 ID 不得与基础提案中的 ID 冲突。
- `self_check` 每次都必须重新提供；继承不等于通过新的自查。
- `unit-snapshot --with-proposal` 返回当前已登记修订的精简列表（`id`、`original`、`replacement`、`reason`），供重交时引用。

### 6.3 A 的测试

`tests/test_proposal_v3.py`（新）：

- 合格必收：S1–S9 的人工期望能生成合格 v2，报告逐字可还原；S8 只验证重启后重新提交，不宣称持久化。
- 不合格必拒：锚点 0/多命中、结构切断、区间重叠、缺证据引用、单元覆盖不足、图片序号不在清单、calc call 不属于本单元或本轮、自查缺失、old/context/new/reason 超限。
- 增量：withdrawn 的修订及其局部证据不进报告；继承证据的 `inherited_ref` 修剪（含 update/替代后仍被引用）；基础提案过期被拒；ID 冲突被拒。
- 上限：`unit-submit` 定位拒绝每单元每轮 8 次后 `stop`；`revise_check` 不计数。
- v2 及 [test_legacy_corpus.py](../tests/test_legacy_corpus.py) 中逐份标注的语料仍按原预期。

插件测试：v3 schema 与 core 导出一致；`jiaodui_revise_check` 在 unit 工具集中可见；bind schema 随包文件存在。

### 6.4 A 的回滚

v3 只新增了入口，落盘仍是 v2，旧代码可以读。回滚就是撤回插件的 v3 schema 与 skill 说明，不需要迁移数据。

---

## 7. 分支 B：工作日志（B 胜出时）

### 7.1 任务

| ID | 任务 | 主要文件 | 规模 |
| --- | --- | --- | --- |
| B0-1 | ADR 0009「单元工作代次与存储」：按 D7 实测选定存储方案；若选独立草稿，同步修订 ADR 0002 与 AGENTS「契约」的允许路径（含 `.work/` 与单元锁文件） | `docs/adr/0009-*.md`、`docs/adr/0002-*.md`、`AGENTS.md` | S |
| B1-1 | 代次模型与草稿读写（open/read/revise/abandon/reopen） | 新增 `jiaodui/unit_work.py` | L |
| B1-2 | CLI：`unit-work`、`unit-revise`、`unit-finish` | `jiaodui/cli.py` | S |
| B2-1 | `delivery_state` 单一判定，并接入 7.5 表中全部消费方 | 新增 `jiaodui/delivery_state.py`；改 `status.py`、`material.py`、`review.py`、`unit_delivery.py`、`workflow.py`、`report_repair.py`、`report.py`、`docx_report.py` | L |
| B3-1 | finish：编译 + 候选摘要预登记 + 共用锁内提交 + 封存与登记同写 | `jiaodui/unit_work.py`、`jiaodui/unit_delivery.py`（拆出不加锁的 `_commit_locked`）、`jiaodui/material.py`（`register_locked` 接受封存参数） | M |
| B4-1 | 清单 v2 懒升级、`material-downgrade`、新入口开关 | `jiaodui/material.py`、`jiaodui/cli.py` | M |
| B5-1 | 两插件工具；父侧工具不进 unit 工具集 | 两包 `tools/index.js` | S |
| B5-2 | 两套 skill 与随包副本 | `skills/*`、`packages/*/skills/*` | S |
| B6 | 真机验证与切换（第 9 节） | 测试记录 | M |
| B7 | 可选增强：证据增量登记、计算参数路径回填、被放弃代次的只读参考 | — | 仅当 B6 数据显示收益时立项 |

### 7.2 代次模型

- 代次键 `(run_id, unit_id, generation)`，generation 从 1 递增。同一单元同一轮次最多一个 `open` 代次。
- 持久状态：`open`、`submitted`、`abandoned`。`stale` 是派生状态（读取时发现绑定输入摘要或轮次已变），不写盘。
- 代次头字段：

```json
{
  "generation": 2,
  "status": "open",
  "owner_attempt_id": "att-7",
  "opened_by": "child",
  "opened_at": "...",
  "inputs_digest": "...",
  "base": {"report_sha256": "...", "data_sha256": "...", "proposal_revision": 3, "accepted": true},
  "inherited_from": null,
  "closed_at": null,
  "close_reason": null,
  "candidates": [],
  "sealed": null
}
```

- 草稿：`{"format": "jiaodui-work-draft/1", "generation": 2, "revisions": [...], "audit": [...], "last_op_at": "..."}`。每条修订包含 `revision_id`（程序分配 `r1…`）、`status`（`effective | retracted | superseded`）、`start`、`end`、`original`、`new_text`、`reason`、`category`、`severity`、`evidence_ids`、`evidence`、`anchor`（原始入参）、`replaces`、`created_at`。
- 当前有效集合以草稿快照为真源，`audit` 只作审计，不靠重放归约，因此不存在 reducer 版本问题。草稿 `format` 未知、字段未知或结构损坏时一律失败关闭（`work-draft-invalid`），交父处理，不猜测修复。
- 继承证据在草稿内可带内部字段 `inherited_ref`；编译 v2 前必须剥除。
- 上限：每代次有效修订 ≤ 100 条、审计 ≤ 300 条、候选摘要 ≤ 4 条，超出返回 `work-limit-exceeded`；清单 > 512 KB 时 status 给出告警。

### 7.3 子侧接口（D10/D11）

子 agent 只携带 `task_id`、`unit_id`、`attempt_id`（派发时给定）和返回的 `revision_id`。

| CLI | 插件工具 | 行为 |
| --- | --- | --- |
| `unit-work open --task-id --unit-id --attempt-id` | `jiaodui_unit_work`（operation=open） | 无 open 代次、最近代次不是 `submitted` 且单元未 accepted → 新建，`owner = attempt`；已有本 attempt 的 open 代次 → 原样返回（幂等）；被其他未终结 attempt 持有 → `work-owned-by-other-attempt`；attempt 在 `terminated_attempts` 中 → `attempt-terminated`；单元已 accepted 或最近代次为 `submitted` → `work-reopen-required` |
| `unit-work read --task-id --unit-id [--offset --limit]` | 同上（operation=read） | 只读；返回代次头、有效修订分页、已撤回 ID 列表 |
| `unit-revise add --task-id --unit-id --attempt-id --revision-json FILE` | `jiaodui_revise`（action=add） | 用 `resolve_anchor` 定位并检查重叠；与某条有效修订的区间、new_text、reason 完全相同时返回其 ID，不写盘 |
| `unit-revise update ... --revision-id r2 --revision-json FILE` | action=update | 旧项置 `superseded`，新项 `replaces: r2`；重叠检查排除 r2 本身；内容相同时不写盘 |
| `unit-revise retract ... --revision-id r2 --reason` | action=retract | 置 `retracted`；已撤回的再次撤回返回成功、不写盘 |
| `unit-finish --task-id --unit-id --attempt-id --finish-json FILE` | `jiaodui_unit_finish` | 见 7.6；代次已封存且编译结果相同时返回原结果 |

所有写操作都在锁内校验：代次为 `open`；调用的 attempt == `owner_attempt_id` 且未终结；绑定输入与轮次未变（否则返回 `work-stale`）；执行模式已确认。方案 2 的 revise 取单元级锁；open/finish/abandon/reopen 取材料锁，finish/abandon 再按 material→unit 顺序取单元锁。

### 7.4 父侧接口

| CLI | 插件工具（不进 unit 工具集） | 行为 |
| --- | --- | --- |
| `unit-work abandon --task-id --unit-id --expected-snapshot-sha256 --reviewer-id --reason` | `jiaodui_unit_work_admin` | 当前 open 代次置 `abandoned`；`owner_attempt_id` 写入 `terminated_attempts`；`unit_state.phase = work_abandoned`（加入 `TERMINAL_PHASES`）。单元回落到基础交付，见 7.5 |
| `unit-work reopen ... --inherit none\|submitted` | 同上 | 对 accepted 或已提交单元开新代次，`opened_by: parent`，`owner_attempt_id` 由参数 `--attempt-id` 给出，供随后派发的子 agent 使用。`submitted` 只允许同轮同输入，按 `split_v2` 继承，并记录 `inherited_from` |

技术重派流程（D8）：父侧 `unit-cancel`（技术取消，现有）→ `unit-work abandon` → 若基础为 accepted 或最近代次为 submitted，先由父侧 `reopen --inherit none` 开新代次；否则按现有流程派发新 attempt，新实例 `open` 新代次。`unit-cancel` 的返回结果在发现 open 代次时附带 `open_work` 提示，但不会隐式放弃。

`snapshot` 增加 `work` 字段（当前代次头摘要，含 `candidates`），父侧 CAS 因此能感知代次变化。

### 7.5 单一判定 `delivery_state`

```python
def delivery_state(root, data, unit_dir) -> DeliveryState
# DeliveryState(state, reason, generation, base_state)
```

优先级：

1. 本轮存在 `open` 代次：输入未变时为 `working`，已变时为 `working_stale`。
2. 否则沿用现有判定（报告状态 → 登记 → 父复核）。v2 的 accepted 额外要求：若本轮存在 `submitted` 代次，`_校对数据.json` 的 `work_provenance` 必须与最后一个 `submitted` 代次的封存信息一致。
3. `abandoned` 代次不影响判定。基础交付的报告、数据、登记、复核仍然匹配时，原状态自动恢复；若 finish 强杀时代次仍为 open，当前文件等于 base 或本代次已登记候选时可按 7.6 重新 finish；一旦 abandon，候选只作审计，需父侧 reopen 后才能继续。两者都不匹配时为 `CURRENT_PENDING`，reason 写「基础交付已被未完成的提交覆盖」。

消费方行为：

| 消费方 | `working` | `working_stale` |
| --- | --- | --- |
| `status` | `CURRENT_PENDING`，reason「重校中，代次 N」 | `CURRENT_PENDING`，reason「工作已失效，需父放弃」 |
| `unit-progress` | phase `revising`；在途；超时按草稿 `last_op_at` 判定 | 不在途，列出待父处理 |
| `dispatch-plan` | 在途，占窗口；owner 已终结或超时时进入新增的 `needs_parent_action` | `needs_parent_action` |
| `unit-snapshot` | 返回 `work` 摘要（含 `candidates`） | 同左 |
| `unit-review` | 拒绝 `work-open` | 拒绝 `work-open` |
| `review_current` | False | False |
| `unit-submit` / `parse-report` / `repair-report --apply` | 拒绝 `work-open` | 拒绝 `work-open` |
| `build-report` / `build-docx` | 按未完成处理并拒绝 | 同左 |

`scan_status` 与 `dispatch_plan` 改为调用 `delivery_state`，不再各自拼装判定。所有分支逻辑只在 `delivery_state.py` 中出现一次。

### 7.6 finish 与提交（D9）

1. 锁内校验：代次 open、调用者是 owner、输入与轮次未变；当前报告/数据各自等于 `base` 或本代次已登记的任一 `candidate`，否则返回 `work-base-changed`。
2. 编译：有效修订 + `unit_evidence` → `merge_layers` → v2 提案；位置 ID、expected_original、编号、summary、proposal_revision 由程序计算。
3. 编译后、写文件前，在代次头原子预登记 `candidate: {report_sha256, data_sha256, draft_sha256, registered_at}`，最多保留最近 4 条；然后调用 `_commit_locked`，即从 `commit_unit_submission` 拆出的不加锁内部实现，避免嵌套加锁。依次写报告、写数据（含 `work_provenance: {run_id, unit_id, generation, draft_sha256, proposal_sha256}`）、执行完整 verify，最后进行**一次**清单写入：同时完成登记、代次 `submitted` 与 `sealed`、`unit_state.phase = awaiting_parent_review`。
4. 进程内异常沿用现有恢复逻辑，还原写入前的字节。
5. 进程被强杀：清单未写，所以未登记，代次仍为 open，判定为 `working`；当前文件等于 base 或任一已登记 candidate 时，子 agent（或重派后的新实例）可以重新 finish；都不匹配时停止并交父侧。读方见 candidate 不自行前滚。
6. finish 在校验阶段失败时，代次保持 open，返回完整错误；修订不丢。失败留痕沿用 `_校对失败.md`。

### 7.7 存储（D7，B0 定稿）

**方案 1：放在清单内**

- 位置 `runs[-1].unit_work[unit_id] = {"generations": [header + draft]}`。
- 每次 revise 全量校验并重写清单，心跳也在同一次写入中更新。

**方案 2：独立草稿文件**

- 清单只存代次头；草稿存 `.work/<run_id>/<unit_id>.g<N>.json`（材料目录下）。
- revise **只写草稿文件**（单元级锁 + 原子替换，不取材料锁），不写清单；open、finish、abandon、reopen 写清单。finish/abandon 按 material→unit 顺序取锁，避免读完草稿后被并发 revise 追加。
- 单元锁文件放 `.work/.locks/<unit_id>.lock`，随 `.work/` 一并进 B0/ADR 0002，不得新增自由命名锁文件。
- 扫描与集合核对忽略 `.work/`，与 `.superseded/` 一致。需要把 `.work/` 加入 ADR 0002 与 AGENTS 的允许路径。
- 草稿内嵌自身内容的 sha256；读取时校验失败返回 `work-draft-invalid`。
- 新轮次开启时，旧轮的 `.work/<old_run_id>/` 保留不删，用于审计。

### 7.8 schema 升级与回滚（D12）

- 首次 `open` 或 `reopen` 时，在同一次清单写入中把 `schema_version` 升为 2。未用新链的材料保持 1。现有 `validate` 只接受 1（[material.py:62](../jiaodui/material.py#L62)），旧代码遇到升级后的材料会直接拒绝。
- 新代码的 `validate` 接受 1 与 2；v2 清单额外校验 `unit_work` 结构。
- 开关 `JIAODUI_WORK_OPEN=0`：拒绝新的 open/reopen（`work-disabled`），但 read、revise、finish、abandon 照常。活着的 owner 可 finish；owner 失联时父侧 abandon 后单元没有 open 代次，直接走旧 `unit-submit` 收尾；被放弃草稿不继承（D8）。这只是功能开关，不涉及凭证。
- `material-downgrade --task-id`：前提是没有 open 代次。把代次数据（方案 2 还包括 `.work/`）移入 `units/<材料名>/.superseded/<run_id>/work/`（契约内路径，扫描忽略），`schema_version` 改回 1，并记录到轮次 action。不提供带 open 工作的降级。

### 7.9 错误码与预算

| 错误码 | 分类 | 说明 |
| --- | --- | --- |
| `anchor.*`（含 `anchor.too-long`）、`revise.reason-empty`、`revise.noop`、`revise.not-found`、`revise.not-effective`、`revise.too-long`、`revise.evidence-required` | interactive | 修正参数后重试，不计预算 |
| `work-owned-by-other-attempt`、`attempt-terminated`、`work-stale`、`work-base-changed`、`work-draft-invalid`、`work-reopen-required` | 不可恢复，结果带 `stop: true` | 交父处理 |
| `work-open` | call_correction | 调用了错误入口 |
| `work-limit-exceeded` | 不可恢复，`stop: true` | 交父裁定 |
| `work-disabled` | 不可恢复 | 新入口已关闭 |
| finish 期间的 `proposal.*`、`images-invalid`、`contract`、`calc*` 等 | 沿用现有映射 | 与 `unit-submit` 一致 |

- 预算按单元×轮次计；新代次、新 attempt 不重置。
- 若 P0.5 中 B 臂最长连续拒绝串 > 10：草稿加 `rejected_streak` 计数，达到 15 时返回 `revise.loop-limit`（`stop: true`）。这需要在拒绝时写草稿，AGENTS 中「被拒不写盘」的表述要相应限定为「恢复记账」，B0 一并修改。A 分支的硬上限按 D13 执行，不依赖本条的实验阈值。

### 7.10 插件与 skill

- 子侧工具 `jiaodui_unit_work`（open/read）、`jiaodui_revise`、`jiaodui_unit_finish` 加入 `UNIT_TOOL_NAMES`；父侧 `jiaodui_unit_work_admin` 不加入。`test_unit_subagents_cannot_cancel_their_own_unit` 的同类测试覆盖 admin 不可见。
- 子 preset 仍然没有 shell/write/edit。
- 两包 `tools/index.js` 保持一致，只透传参数。
- skill 入口净增 ≤ 0；子 agent 流程写在 operation-manual：open → 读/图/calc → 逐条 revise → read 自查 → finish → 一行摘要。

---

## 8. 测试矩阵

确定性层先写失败测试；预期值来自人工样本，不用待测实现生成。

### 8.1 共同（P0）

见 4.9。

### 8.2 分支 A

见 6.3。

### 8.3 分支 B

| 文件 | 覆盖 |
| --- | --- |
| `tests/test_unit_work.py`（新） | open 新建/恢复/他人持有/已终结/已 accepted/已 submitted/needs_revision；add/update/retract 及语义幂等（含响应丢失重放字节和 mtime 不变）；update 排除自身的重叠检查；继承证据 `inherited_ref` 修剪；上限拒绝；草稿损坏失败关闭；换轮、换输入后 stale |
| `tests/test_unit_work_parent.py`（新） | abandon 后旧 owner 的写入与 finish 被拒；abandon 后旧 owner 再 open 被拒；child 在 submitted/needs_revision 后 open 返回 `work-reopen-required`；基础交付恢复与被覆盖后的回落；reopen 继承的映射与来源记录；技术重派不继承；CAS 过期被拒 |
| `tests/test_delivery_state.py`（新） | 7.5 表中每个消费方 × {working, working_stale, abandoned 回落, submitted 待复核, accepted}；空代次不完成；accepted + open 代次不完成；新代次提交相同字节仍需新的接受；`work_provenance` 不符时 accepted 无效；open 代次候选摘要存在时判定与重新 finish；abandon 后候选只作审计；owner 失联时 abandon 后旧链可收尾 |
| `tests/test_unit_finish.py`（新） | 编译结果与人工期望一致；撤回项不进报告；`work-base-changed`；在预登记前、预登记后写报告前、写报告后、写数据后、verify 后、写清单前注入异常与强杀（子进程 `os._exit`），检查 base/candidate 判定、可重新 finish、读方不前滚 |
| `tests/test_concurrency.py` | 两个 CLI 进程竞争同一单元；8 单元并发 revise 无丢失；方案 2 单元锁下 finish/revise 竞争不丢修订；记端到端 p95（含等锁） |
| `tests/test_material_schema.py`（新） | 懒升级；旧版 `validate`（固定副本）拒绝 v2；downgrade 的前提与归档到 `units/<材料名>/.superseded/<run_id>/work/`；`JIAODUI_WORK_OPEN=0` 下活 owner finish、失联 owner abandon 后旧链收尾 |
| `tests/test_dsh_plugin_package.py` | admin 工具不在 unit 工具集；两包一致；全量 schema 与 core 导出一致；bind schema 与全量差集正确；插件只读 bind schema |
| `tests/test_skill_docs.py` | 入口预算；两包副本一致 |

### 8.4 每阶段固定执行

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -o addopts='' -q -rs
```

---

## 9. 真机验证与切换

### 9.1 门槛

1. 所选分支的确定性正反测试全部通过。
2. 物理、化学两个插件分别在真机上：至少一次合格接受、一次不合格拒绝；真实读图；B 分支另加一次中断重派（S8）与响应丢失重放（S9）。
3. 源文与源图 hash 不变；报告逐字可还原；Word 标记数 = 批注锚点数 + 公式兜底数，缺失为 0。
4. 没有旧报告冒充新完成：抽查 status、build-report、build-docx。
5. 父代理仍只收单元摘要，并最终通读汇总报告。

### 9.2 切换动作

- skill 正常入口改为新流程，旧 v2 `unit-submit` 保留为显式兼容入口。
- 同步 AGENTS.md「契约」中正常路径的表述，保留「结构化提交、程序生成、父复核」三项硬约束；同步 PRD、IMPLEMENTATION、README、两份 operation-manual。
- B 分支：存在 open 代次的材料不能切回旧链；活 owner 先 finish，owner 失联由父侧 abandon 后走旧链。

### 9.3 汇报口径

以 P0.5 和真机记录的指标呈现易用性变化，同时报告 token 与耗时，不预先宣称更快或更省；小样本不宣称质量提升。

---

## 10. 风险

| 风险 | 应对 |
| --- | --- |
| 交互类错误不计预算，导致定位死循环 | P0.5 统计最长连续拒绝串；A 按 D13 在 core 计数并在 8 次后 `stop`；B 超阈值时按 5.5 第 4 条加上限 |
| 匹配期归一化掩盖源文中的不可见字符问题 | 返回 `normalized_match`；报告中的 expected_original 取源文逐字原文；归一化范围只限 4.2 所列字符 |
| B 判定接线遗漏某个下游 | 判定只在 `delivery_state.py` 实现；7.5 表逐行有测试 |
| finish 被强杀后基础报告已被覆盖 | 候选摘要预登记；代次仍 open 且当前文件等于 base/候选时可重新 finish；都不匹配时未完成并交父；abandon 仍不承诺恢复 base |
| 清单升级后回滚困难 | 懒升级只影响用过新链的材料；提供 downgrade；开关下活 owner finish、失联 owner abandon 后旧链收尾 |
| skill 超出预算被宿主裁剪 | P0-7 先腾余量；入口净增 ≤ 0 由测试守住 |
| 实验样本太少，结论不稳 | 判定只看机械指标（拒绝、token、耗时）和漏报不增，不据此宣称质量提升 |
| B 相对 A 的差异化不足 | P0.5 增 S9 响应丢失重放；若 B 在 S9 也不占优，D6 倾向 A，不强行上 B |
| 8 并发下材料锁/单元锁等待 | D7 用端到端 p95（含等锁）；方案 2 的 revise 只取单元锁，finish/abandon 固定 material→unit 锁序 |

---

## 11. 文档同步清单

| 时点 | 文档 |
| --- | --- |
| P0 | PRD 增量、ADR 0008、TICKETS（T09 关闭）、两份 operation-manual 与入口瘦身；bind schema 随包文件；T09 v2 数据保护 |
| P0.5 | `docs/EXPERIMENT-revise-ab.md`、本计划状态行 |
| B0 | ADR 0009；方案 2 时修订 ADR 0002 与 AGENTS 允许路径（`.work/`、单元锁文件）；需要时修订 AGENTS「被拒不写盘」的适用范围 |
| 切换 | AGENTS 正常路径、PRD、IMPLEMENTATION、README、ARCHITECTURE；AGENTS「被拒不写盘」限定为恢复记账（D13） |

---

## 12. 依据

- [项目约定](../AGENTS.md)、[PRD](PRD.html)、[实施顺序](IMPLEMENTATION.md)。
- [ADR 0002 工作区布局](adr/0002-workspace-material-layout.md)、[ADR 0006 v2 编码](adr/0006-v2-lossless-marker-encoding-and-envelope.md)。
- 定位：[source_index.py](../jiaodui/source_index.py)；报告生成：[report_suggestions.py](../jiaodui/report_suggestions.py)；事务提交：[unit_delivery.py](../jiaodui/unit_delivery.py)。
- 父复核：[review.py](../jiaodui/review.py)；状态：[status.py](../jiaodui/status.py)；材料/派发/恢复/事件：[material.py](../jiaodui/material.py)。
- 错误分类：[error_classification.py](../jiaodui/error_classification.py)；预算：[execution_policy.py](../jiaodui/execution_policy.py)；v1 登记：[workflow.py](../jiaodui/workflow.py)。
- 插件：[物理](../packages/dsh-jiaodui/tools/index.js)、[化学](../packages/dsh-jiaodui-chemistry/tools/index.js)；测试：[skill 体积](../tests/test_skill_docs.py)、[插件包](../tests/test_dsh_plugin_package.py)。
- 背景记录：[T09](TICKETS-full-chain-2026-10-10.md)、[2026-10-13 审查](REVIEW-2026-10-13.md)。

---

## 13. 本版修正记录（2026-10-19 第三轮）

- P0-6：`--bind-current` 由 core 绑定；core 另导出 bind schema，随包第二份 JSON，插件不再 clone/改写 schema；全量 schema parity 保持不变。
- P0-3：继承时全部证据先归 `unit_evidence`；单引用 assumption/calculation 记内部 `inherited_ref`，按当前有效引用修剪（含 `superseded`），images 不修剪；`inherited_ref` 编译前剥除；assumptions 为空返回 `revise.evidence-required`。
- P0-5：已有 v2 数据/登记/损坏时拒绝 `--manual-legacy` 与 `report_repair --apply`，错误码 `legacy-overwrite-v2-forbidden`。
- D8：任何 `submitted` 代次（accepted 或 needs_revision）后 child `open` 一律 `work-reopen-required`，只能父侧 reopen/继承。
- D9：写文件前预登记 candidate（绑定 `draft_sha256`，最多 4 条）；代次仍 open 时重新 finish 允许当前文件等于 base 或 candidate；读方不前滚；abandon 仍不承诺恢复 base。
- D7：阈值改为端到端 revise p95（含等锁）；方案 2 的 revise 只取单元锁，finish/abandon 按 material→unit 锁序，锁文件进 B0/ADR。
- D12：downgrade 归档到 `units/<材料名>/.superseded/<run_id>/work/`；开关关闭后活 owner finish、失联 owner 由父 abandon 后旧链收尾。
- P0.5：B 原型补最小 abandon + `reopen --inherit submitted`；新增 S9 响应丢失重放，总执行 36 次；加 D13（A 定位拒绝 8 次 `stop`）与 D14（S9 差异化证据）。
- 输入上限：old_text ≤ 1000、context 各 ≤ 200、new_text ≤ 2000、reason ≤ 2000、单条 evidence 文本 ≤ 4000 码点；`occurrence` 对 context+old+context 组合串计数。

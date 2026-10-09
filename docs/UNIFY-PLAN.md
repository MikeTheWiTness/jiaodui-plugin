# 结构化校对并入 main：实施计划

> 本文件是**唯一**的合并计划文档，取代此前的 `P7-MERGE-DECISION.md` / `P2-ACCEPTANCE.md` / `NEXT-SESSION-BRIEF.md`（已删除；事实与批次记录保留在 `PROCESS_REWORK.md`）。
>
> 目标：**把分支的结构化校对方式并入 main，同时保留 main 中更优的部分**。
> 方式：不做一次性大合并——先让分支**吸收** main 的优点，再以集成分支落地，全程每批双口径测试。

---

## 0. 一句话结论

两条线的差异**极不对称**，所以正确的方向不是"把分支搬进 main"（那是 25 处冲突、重写 6 个模块的大工程），而是：

**先把 main 独有的少量优点搬进分支（4 个小批次）→ 再在集成分支上把分支并入 main（按类裁决冲突）→ 最后切环境收尾。**

工作量比反向操作小一个量级，且每一步都能保持测试全绿。

---

## 1. 项目结构回顾

### 1.1 分层（两条线相同）

```
jiaodui/            唯一核心逻辑（判断交给 agent，确定性交给 Python）
cli.py              只做参数解析与输出，零业务分支
packages/dsh-jiaodui/
  tools/index.js    宿主插件：注册原生工具 / argv 透传 CLI
  cordis.patch.yml  声明「校对」agent preset（父/子工具分层）
  skills/jiaodui/   随包 skill（与仓库 skills/ 逐字节一致）
skills/jiaodui/     仓库侧 skill 源
tests/              确定性层红→绿；闸门双向契约
```

### 1.2 核心模块：main 只独有 1 个，分支独有 6 个

| | main | 分支 |
|---|---|---|
| 模块数 | 31 | 36 |
| 独有 | **`execution_policy.py`**（120 行纯策略模块） | `error_classification.py`、`report_suggestions.py`、`review.py`、`source_index.py`、`unit_delivery.py`、`unit_reader.py` |
| 共用但语义分叉 | `material.py`（策略内嵌在 main？→ 不，main 抽成纯模块；分支内嵌）、`markers.py`（main 无 v2/转义概念）、`report_parse.py`/`verify.py`/`report.py`（main 无 v2 边界） | 同左 |

### 1.3 CLI：分支是 main 的严格超集

| | 结果 |
|---|---|
| main 独有子命令 | **0 个** |
| 分支独有子命令 | `unit-read`、`unit-locate`、`unit-snapshot`、`unit-submit`、`unit-review`、`unit-progress`、`dispatch-plan`、`unit-schema`、`calc-schema`（9 个） |
| 两边都有但签名不同 | `unit-recovery`、`unit-event`（见 §4 决策 2/3） |

### 1.4 插件与 preset：差距最大的一处

| | main | 分支 |
|---|---|---|
| `tools/index.js` | **192 行**，只有一个通用 `jiaodui` argv 透传工具 | **475 行**，注册 26 个原生工具（`jiaodui_task_prepare` / `jiaodui_delivery` / `jiaodui_unit_*` / `jiaodui_dispatch_plan` / `jiaodui_unit_progress` + 12 个 `jiaodui_calc_*`） |
| 随包 schema | 无 | `proposal-schema.json`、`calc-schemas.json` |
| preset 父侧 | 有 shell；子侧 allow = `[skill, read, read_image, write, edit, jiaodui]` | 有 shell + 只读搜索；子侧 allow = 封闭 20 项（无 shell/write/edit） |
| 真机验收 | 未做 | **P2 八条全绿**（父/子 catalog、`read_image` 实读、零 shell 真实校对、停止语义、判别器） |

### 1.5 测试

| | main | 分支 |
|---|---|---|
| 测试文件 | 46 | 57 |
| 当前口径 | （未在本轮复核） | 双口径 **1114 passed / 0 failed / 5 skipped** |
| 特有测试 | `test_execution_compat.py`(10)、`test_main_policy_contract.py`(11)、`test_policy_legacy_compat.py`(2) | `test_report_suggestions.py`、`test_unit_delivery.py`、`test_unit_reader.py`、`test_unit_identity.py`、`test_workflow_milestones.py`、`test_execution_policy.py`、`test_concurrency.py`、`test_error_classification.py`、`test_unit_progress.py`、`test_marker_escape.py`、`test_module_integrity.py` |

main 删掉了 4 个核心模块与 6 个结构化测试文件；分支保留并扩展了它们。

### 1.6 文档与 ADR

| | main | 分支 |
|---|---|---|
| ADR | 0001–0005 | 0001–**0006**（0006 = v2 无损标记编码与信封契约） |
| 独有计划文档 | `PLAN-rework-continuation.md`、`M0.md` | — |
| 独有记录 | — | `PROCESS_REWORK.md` 的分支批次记录（P3→P6 全部批次与口径） |
| 双写内容 | `SKILL.md`（≤8192 + 长度/链接回归）、`operation-manual.md`、`README.md`、`cordis.patch.yml` 在两条线上各改一版 | 同左（分支 8164 码点，同样有长度回归） |

### 1.7 谁更优：差异总表

| 维度 | 更优的一侧 | 说明 |
|---|---|---|
| 报告产物 | **分支** | 模型不写报告；程序从不可变源文生成（`report_suggestions` + v2 信封 + ADR 0006 无损转义） |
| 闸门完整性 | **分支** | v2 提案 + 父复核版本绑定 + `build-docx` 复核当前状态；main 无提案对象 |
| 工具面 | **分支** | 26 个强类型工具（含 `task_prepare`/`delivery`/`dispatch_plan`/`unit_progress`）vs 单一 argv 透传 |
| 子代理约束 | **分支** | 子侧封闭 20 项，「模型不写报告」有工具目录级落点 |
| 调度闭环 | **分支** | 错误码→类别确定性映射、心跳与超时判据、滑窗/停止判据、并发登记压测 |
| 策略模块结构 | **main** | `execution_policy.py` 抽成纯模块（可单测、无 IO）；分支内嵌在 `material.py` |
| 幂等与事件语义 | **main** | `attempt_id` 幂等 + `validate_attempt` 校验；分支用 `fingerprint` |
| 额度扣法细节 | **main** | `image_schema_fix` 连带扣 `call_correction`（`_charges`），有测试锁定 |
| 旧清单兼容 | **main** | `_LEGACY_BUDGETS` 映射 + `migrate_legacy_spent` 保守迁移 + 2 条兼容测试 |
| 计划文档 | **main** | `PLAN-rework-continuation.md`、`M0.md` 等（分支没有） |
| 中性中止传播 | 持平 | main `c1c24b9` ≈ 分支 `tools/index.js:419-422`，各自做完 |
| 入口长度纪律 | 持平 | 两条线各自把 SKILL.md 压到 ≤8192 并加回归 |

---

## 2. main 中必须保留的部分（移植清单）

| # | 内容 | 位置 | 为什么保留 | 落地方式 |
|---|---|---|---|---|
| M1 | 纯策略模块 | `jiaodui/execution_policy.py` | 把策略与 IO 分离，可单测；分支内嵌在 `material.py` 里是结构退化 | **B1**：把分支的预算/授权/记账搬进该模块，保留 `BUDGETS`/`spend`/`validate_attempt` 的形状 |
| M2 | `attempt_id` 幂等 + 校验 | 同上 `validate_attempt` / main `test_main_policy_contract` | 幂等比"同指纹换 agent 再花一次"更稳；分支的 `fingerprint` 记账会随 agent 更换漂移 | **B3**：两者并用（`attempt_id` 幂等 + `fingerprint` 作类别映射输入） |
| M3 | 额度扣法：`image_schema_fix` 连带 `call_correction` | 同上 `_charges` | 图片格式修复本身要占一次调用；只扣一类会漏算调用成本 | **B1**：采纳 main 语义，改分支 `error_classification` 的扣费模型 |
| M4 | 旧清单兼容与迁移 | 同上 `_LEGACY_BUDGETS` / `migrate_legacy_spent`；`test_policy_legacy_compat.py` | 已产出的旧材料仍要可读、且按单元保守迁移，不能因升级丢弃历史 | **B2**：移植映射与迁移 + 2 条断言 |
| M5 | 计划文档 | `docs/PLAN-rework-continuation.md`、`docs/M0.md` | 记载了 M0–M6 验收口径与收口计划 | **B4**：合并不删（分支只是缺，不需重写） |
| M6 | 中性中止传播 | main `c1c24b9` | 插件不猜取消来源 | 已持平，无需移植 |
| M7 | 入口 ≤8192 + 长度/链接回归 | main `cc1c21f` | 入口预算是硬约束 | 已持平，合并时以分支版为基线并重跑回归 |

---

## 3. 分支中必须保留的部分（随合并整体进入 main）

- **报告链**：`report_suggestions.py`（程序生成报告 + 证据校验）、`unit_delivery.py`（快照/提交/登记）、`review.py`（版本绑定父复核）、`markers.py` v2 转义与信封、`verify.py`/`report_parse.py`/`docx_report.py` 的 v2 边界
- **单元读取与身份**：`unit_reader.py`、`source_index.py`
- **调度闭环**：`error_classification.py`、`material.unit_progress`、`material.dispatch_plan`、并发登记（`material.locked` 压测）
- **工具面**：475 行插件 26 个原生工具 + 2 份 schema + preset 父/子分层（P2 真机验收过）
- **ADR 0006**、`PROCESS_REWORK.md` 的分支批次记录（P3→P6 的过程与口径，是合并时的判定依据）
- **Word 修复**：含锚点的 pipe table → grid table（真机失败样本已验证）

---

## 4. 必须由人拍板的决策（5 条）

| # | 决策 | 建议 | 理由 |
|---|---|---|---|
| 1 | 报告谁写 | **分支方式**（模型只交结构化提案，程序从源文生成报告） | 用户已指示"推进分支的校对方式合并到 main"；且这是分支唯一的核心主张 |
| 2 | 恢复记账是否兼容 main 的 `attempt_id` 契约 | **两者都用**：`attempt_id` 幂等 + `fingerprint` 作为错误码映射输入 | main 的幂等更强；分支的类别映射更强。CLI/工具签名统一为 `--attempt-id` 必填 + `--error-code` |
| 3 | `image_schema_fix` 是否连带扣 `call_correction` | **采纳 main**（连带扣，每 attempt 一次） | 图片修复本身占一次调用；main 已有测试锁定该语义 |
| 4 | 旧主链报告路径是否保留 | **保留为只读兼容**：`verify-report --legacy`、`parse-report`、`report_repair` 继续可用；不再作为正常交付路径 | 已产出的历史材料要能读；但正常路径只有结构化一条 |
| 5 | 合并后默认 preset | **「校对」为默认**（`agent-preset-registry.selectedDefault`），`standard` 保留 | 产品即校对流程；standard 仍在，便于代码工作 |

---

## 5. 实施计划

### Phase 1：分支吸收 main 的优点（4 批，每批 1 提交 + 双口径全量）

| 批 | 内容 | 验收 |
|---|---|---|
| **B1 ✅** | 抽 `execution_policy.py`：把 `material.py` 内嵌的授权/预算/记账搬进纯模块；把 `error_classification` 的分类作为 `spend()` 之前的钩子；扣费采纳 M3（连带扣） | 现有 `test_execution_policy.py`/`test_workflow_milestones.py` 全绿 + 新增扣费语义测试；`material.py` 不再内嵌预算表 |
| **B2 ✅** | 移植旧清单兼容：`_LEGACY_BUDGETS` 映射、`migrate_legacy_spent`、`test_policy_legacy_compat` 两条断言（旧清单可读但未授权；聚合预算按单元保守迁移） | 用工作区里 6 份 main 时期旧清单（`第 6 讲校对测试`、`第 6 讲校对测试-流程测试`、`-独立续测-02`、`-独立续测-03`、`_独立流程测试`、`_独立流程测试_重跑`；实测均无 `execution_policy`）验证：可读、不被授权、聚合预算按单元保守迁移 |
| **B3 ✅** | 统一恢复契约：`attempt_id` 幂等 + `fingerprint` + `error_code`；CLI/插件/工具 schema 同步；`unit-event` 签名对齐 | 幂等用例（同 attempt 不重复扣、同指纹换 attempt 再扣、换指纹不重置）+ 现有机试用例 |
| **B4 ✅** | 文档归位：**验证批，无需改动**——main 独有文档（`PLAN-rework-continuation.md`、`M0.md`）只在 main、合并不删；「旧主链=只读兼容」的边界已写在手册（`verify-report`/`parse-report` 兼容读取、仅旧报告可用完整性辅助）与 SKILL（`--legacy-layout` 显式开关），且有代码强制（`report_repair` 的 `repair.v2-not-supported` + `--legacy-layout` 显式 opt-in） | 入口 8164 码点 <8192、两份副本一致、skill 与插件包测试 34 例绿 |

Phase 1 全部在**分支**上做，main 不动。已完成 B1/B2/B3（见 `PROCESS_REWORK.md` 的对应批次记录）；B3 落地形态：`unit-recovery` 签名为 `--task-id --unit-id --attempt-id --fingerprint [--error-code | --category targeted_review] [--expected-run-id]`，幂等索引在 run 级 `recovery_attempts[unit][attempt_id]`（main 的幂等来自事件账本，分支的事件与预算账本分开，故另建索引，错误码沿用 main 的 `attempt-id-conflict`）。

### Phase 2：集成分支落地（一次性合并 + 按类裁决）

> **✅ 已完成（2026-10-10）**：合并提交 `98a7ac8`（双父：`e3deab4` main + `3f7c734` 分支；分支已成为祖先），已 `--ff-only` 快进到 `main`，临时集成分支与两个 worktree 已删除。
>
> 实际冲突 **28 处**（19 content + 7 modify/delete + 2 add/add，多于本计划原写的 25 处），另 19 处静默变更全部按 §6.1 处置。结果：根仓双口径 **1158 passed / 0 failed**、冻结语料 4/4、P6 材料真机 `build-report`/`build-docx` 通过（标记 2 = 锚点 2 + 兜底 0）。`jiaodui/`、`packages/`、`skills/` 与分支的差异只剩 4 份 main 重写文档（0 个 .py）。
>
> **映射 main 测试时额外采纳了六处 main 更优语义**（详见 `PROCESS_REWORK.md` 的 Phase 2 记录）：`report.to_dict()` 暴露 `ok`、`unit-event` 轮次 CAS、`unit-event` 要求当前授权、指纹错误码 `invalid-attempt-fingerprint`、**幂等重放不写盘**、**被拒 attempt 不写盘**（后两条同源：不改变状态就不写盘）。

1. 从 main 建集成分支：`integration/structured-into-main`
2. `git merge feature/structured-report-pipeline`（预期 25 处冲突）
3. 按 §6 的裁决规则逐类处理；**先做 §4 决策 1–3，再动冲突文件**（否则两套预算语义会在结果里共存）
4. 裁决后立刻做一次**语义复核**：`git diff main...HEAD -- jiaodui/` 通读，确认没有两条线的行为被"合并"成第三种
5. 验收：双口径全量 + 冻结语料 + `git diff --check` + 用 P6 两份材料与夹具做一次真机冒烟（`status`/`build-report`/`build-docx`）

### Phase 3：收尾

> **✅ 已完成（2026-10-10）**：profile 三处（`package.json` / `pnpm-lock.yaml` / `node_modules/dsh-jiaodui` 软链）已切回仓库根包并做 Node 解析自检（包、skills、插件 CLI 三处均解析到根仓，零 worktree 残留）；`.venv` 本就是指向已验证独立环境 `.venv-cli` 的软链（AGENTS 允许），editable 自动跟踪合并后的代码，故无需重建；`.worktrees/structured-report`（含其 255M venv）与 `.worktrees/integration` 已删除；临时集成分支已删（`feature/structured-report-pipeline` 保留为历史标记）；`AGENTS.md`/`README.md`/`IMPLEMENTATION.md` 已同步为「正常路径 = 结构化、旧链只读兼容」；P6 回放材料与 `archive/structured-pipeline-safety` tag 原样保留；全程未 push（本地领先 `origin/main` 39 个提交）。

| 项 | 动作 |
|---|---|
| 环境 | profile 软链切**回根包**；根仓重建 `.venv` 并 `pip install -e '.[dev,render]' build`；确认插件解析到根包 CLI |
| worktree | 合并后删除 `.worktrees/structured-report` 与它的 venv（保留 `archive/structured-pipeline-safety` tag 与回放材料作为证据） |
| 文档 | 更新 `AGENTS.md`/`README.md`/`IMPLEMENTATION.md`：正常路径 = 结构化；旧主链降级为只读兼容 |
| 证据留存 | `校对/` 的回放材料与 P6 材料原样保留（不删、不重写）；`PROCESS_REWORK.md` 作为合并过程的批次记录 |

---

## 6. 冲突裁决规则（按文件类）

| 文件类 | 裁决 | 原因 |
|---|---|---|
| `jiaodui/report_suggestions.py`、`unit_delivery.py`、`source_index.py`、`unit_reader.py`、`review.py` | **取分支** | main 已删除；分支是这些能力的唯一实现 |
| `jiaodui/cli.py` | **取分支** + 吸收 main 的 `unit-recovery`/`unit-event` 签名（决策 2/3） | 分支是超集；签名按决策统一 |
| `jiaodui/material.py` | **取分支**（B1 已把策略抽出） | 避免两套预算语义共存 |
| `jiaodui/execution_policy.py` | **取分支的 B1 版本** | 已吸收 main 的 M1–M3 |
| `jiaodui/report.py`、`report_parse.py`、`verify.py`、`markers.py`、`docx_report.py` | **取分支** | v2 边界与 ADR 0006 唯一定义 |
| `packages/dsh-jiaodui/tools/index.js`、`proposal-schema.json`、`calc-schemas.json` | **取分支** | main 只有 argv 透传 |
| `packages/dsh-jiaodui/cordis.patch.yml` | **取分支** | 父有 shell/只读搜索、子封闭 20 项，已真机验收 |
| `skills/jiaodui/SKILL.md`、`references/operation-manual.md`、`subjects/高中物理.md`、`packages/dsh-jiaodui/README.md` | **取分支**后重跑入口长度与链接回归 | 内容以结构化流程为准；≤8192 是硬约束 |
| `README.md`、`docs/PROCESS_REWORK.md` | **手工合并** | 两份都是"两边各自演进"的说明性文本 |
| main 独有文档（`PLAN-rework-continuation.md`、`M0.md`） | **保留** | 合并不会删；它们是 M0–M6 口径来源 |
| 6 个测试冲突文件 | **分支版为基线**，逐条把 main 的断言**映射**成结构化语义的等价断言 | main 的 3 个新测试锁旧主链语义，不能原样保留，但其断言意图（幂等、连带扣费、取消不花额度、`complete` 解耦）都要在分支里有对应测试——缺哪条补哪条 |

---

### 6.1 静默应用的 main 变更（比冲突更危险，B1/B2 复查时发现）

实测：main 改了 48 个文件、分支改了 42 个、冲突 28 个；**剩下 19 个是「分支没碰、main 改了」→ git 静默采用 main 版本**。其中这些会造成实质破坏：

| 文件 | main 的改动 | 合并后的后果 | 处置 |
|---|---|---|---|
| `jiaodui/source_index.py` | 整份删除（−132） | 分支 `report_suggestions.py`、`cli.py` 都 import 它 → **ImportError，分支核心全废** | **取回分支版本**（等于撤销 main 的删除） |
| `jiaodui/unit_reader.py` | 整份删除（−55） | 分支 `cli.py`（`unit-read`）import 它 → 命令不可用 | 取回分支版本 |
| `jiaodui/calc/schema.py` | 整份删除（−41） | 分支 `cli.py` 的 `calc-schema` 用 `all_json_schemas`/`json_schema_for` → 命令不可用 | 取回分支版本 |
| `packages/dsh-jiaodui/tools/calc-schemas.json` | 删除（−391） | 插件随包 schema 与 `test_calc_schema` 依赖它 | 取回分支版本 |
| `jiaodui/report_repair.py` | 删掉 v2 守门（−5） | 分支契约「v2 报告不走旧 Markdown 修复器」**静默失效**，`repair-report` 会去修 v2 | 取回分支版本 |
| `tests/test_calc_schema.py`、`test_source_index.py`、`test_unit_identity.py`、`test_unit_reader.py` | 删除 | 上述模块的测试覆盖静默消失 | 取回分支版本 |
| `tests/test_report.py` | 删 3 行 | 可能删掉了 v2 相关断言 | 逐行裁决 |
| `tests/test_skill_docs.py` | 重写（+51/−18） | **直接跑会红**（已实测）：把 main 版放在分支 skill 上，`test_repair_preview_is_documented_as_explicit_gate_auxiliary` 失败——它断言 `jiaodui repair-report` 出现在 SKILL.md | 以分支 skill 为准，逐条裁决断言（保留长度/链接回归，改措辞类断言） |
| `tests/test_execution_compat.py`、`tests/test_main_policy_contract.py` | 新增（+208/+234） | 锁 main 语义且**不在冲突清单** → 静默进入合并结果、很可能红 | 逐条**映射**成结构化语义的等价断言（`attempt_id` 幂等、连带扣费、取消不花额度、`complete` 解耦） |
| `docs/PLAN-rework-continuation.md` | 新增（+212） | 无风险 | 保留 |
| `AGENTS.md`、`skills/.../failure-modes.md`、`subject-matrix.md` | 措辞改写 | 与分支的 SKILL/手册可能不一致 | 取 main 措辞 + 与分支流程对齐 |

**另一处「自动合并但语义重复」**：`jiaodui/workflow.py` 不在冲突清单里（两边各改不同区域 → 自动合并），但 main 在该文件新增了两个**入口函数** `set_execution_policy(unit, *, mode, origin, expected_run_id)` 与 `record_unit_event(...)`（main 版 536 行；分叉点与分支分别 442/444 行、策略入口 0 个）。合并结果里会同时存在：

- main 的 `workflow.set_execution_policy` / `workflow.record_unit_event`（写 main 的 `policy["spent"]` 形态）
- 分支的 `material.set_execution_policy` / `material.record_unit_event`（写 v2 清单形态）

两套 API 并存且形态不兼容 → **必须删除 main 的这两个函数**（或改成委托分支实现），否则任何仍调用 workflow 版的路径都会写出错形态的清单。

### 6.2 修正后的冲突面（B1/B2 之后重算）

- **28 处**：19 content + 7 modify/delete + **2 add/add**。
- 新增的两处 add/add 来自 B1/B2：`jiaodui/execution_policy.py`（main 也有同名模块）、`tests/test_policy_legacy_compat.py`（main 也有同名测试）——都取分支版本。
- 7 处 modify/delete 全是「main 删、分支改」→ 取分支版本：`report_suggestions.py`、`unit_delivery.py`、`proposal-schema.json`、`test_execution_policy.py`、`test_report_suggestions.py`、`test_unit_delivery.py`、`test_workflow_milestones.py`。
- 测试冲突文件是 **8 个**（§6 表里原写「6 个」，以本节为准）：`test_cli`、`test_dsh_plugin_package`、`test_dsh_plugin_tool_behavior`、`test_execution_policy`、`test_policy_legacy_compat`、`test_report_suggestions`、`test_unit_delivery`、`test_workflow_milestones`。

### 6.3 落地时的操作配方（防这一类坑）

1. 建集成分支后**第一件事跑全量测试**：静默删除会以 ImportError 立刻暴露，`test_skill_docs` 的措辞断言会红。
2. 重算静默清单（改动前后各跑一次）：
   ```bash
   python3 - <<'EOF'
   import subprocess
   def names(cmd): return set(subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.split())
   main_changed = names("git diff --name-only <base>..main")
   branch_changed = names("git diff --name-only <base>..<branch>")
   conflicts = {l.split(':')[-1].split(' deleted in')[0].split(' in ')[0].strip()
                for l in subprocess.run("git merge-tree --write-tree main <branch>", shell=True,
                                        capture_output=True, text=True).stdout.splitlines()
                if l.startswith("CONFLICT")}
   print(sorted(main_changed - branch_changed - conflicts))
   EOF
   ```
3. 按本节 §6.1 的处置列逐项**取回分支版本**，并把它们补进 §6 的裁决表（否则下次重算仍会被当成"无冲突"）。
4. 裁决后 `git diff main...HEAD -- jiaodui/` 通读，确认没有把两条线的行为合成第三种。

## 7. 风险与验证矩阵

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| 两套预算语义被"合并"成第三种 | 未先定决策 1–3 就动冲突文件 | §5 Phase 2 第 3 步：决策先行；裁决后 `git diff main...HEAD -- jiaodui/` 通读 |
| 测试口径互斥导致"为了绿而删测试" | 直接保留 main 的旧主链断言 | 用 §6 最后一行：逐条**映射**而非删除；每删一条须在提交信息里写明对应替代 |
| **静默删除/改写**：分支依赖的模块被 main 删掉后无冲突地消失 | 只盯着冲突清单 | §6.1 清单 + 集成分支先跑全量测试 + §6.3 配方 |
| **两套入口 API 并存**（workflow 与 material 各一套策略入口） | `workflow.py` 自动合并 | §6.1 末段：删除或委托 main 版入口 |
| 旧材料不可读 | 策略模块搬迁破坏旧清单解析 | B2 用真实旧标记清单验证；保留 `migrate_legacy_spent` |
| 交付回退 | Word/整卷在合并后行为变化 | Phase 2 验收含真机冒烟（P6 两份材料 + 夹具，检查 `marker_count/anchor_count/missing_count`） |
| 环境错位 | profile 仍指向 worktree 包 | Phase 3 明确切回 + 重建根仓 venv + 插件 CLI 判别器复验 |
| 入口超预算 | 文档手工合并把 SKILL.md 撑过 8192 | 每个涉及文档的批次都跑长度与链接回归 |

---

## 8. 明确不做的事

- 不做一次性大合并（25 处冲突 + 6 个模块重写）后再补测试
- 不删除或重写 `校对/` 下的回放材料与 P6 材料（它们是合并判定的证据）
- 不保留两套报告路径作为"正常交付"（只有结构化一条；旧主链只读兼容）
- 不在合并前动 main：Phase 1 全部在分支上完成
- 不 push（落地与推送由人确认后再做）

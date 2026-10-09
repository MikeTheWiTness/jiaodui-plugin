# P7 合并 / 切换决策备忘

> 本文件只做**决策材料**：把「分支能不能并回 main」拆成可核验的事实、三条处置路径及代价，并给出推荐与触发条件。
> 结论由人拍板；本备忘不预设立场。

## 一、事实基（都可复现）

| 事实 | 证据 |
|---|---|
| 分支的基线提交是 `4c82e24`（structured unit submission pipeline） | `git log --oneline -1 4c82e24` |
| main **回退了同一个提交** | `git show --stat c7fa622`（`Revert "feat(workflow): add structured unit submission pipeline"`，reverts `4c82e24`） |
| main 在回退后另起一条线重建策略层 | `dde758d 兼容旧主链执行策略与恢复记录`、`04f0c78 按单元强制执行策略与预算`、`c1c24b9 中性传播宿主中止调用`、`cc1c21f 入口精简至 8192 码点以内`、`e3deab4 收口计划` |
| 分叉点→main 的净变化 | `git diff --stat 4c82e24..main` = 48 files, +1451 / −2659 |
| 试合并冲突面 | `git merge-tree --write-tree main feature/structured-report-pipeline` → **25 处冲突（19 content + 6 modify/delete）**，覆盖 `cli.py`、`material.py`、`report.py`、`report_parse.py`、`report_suggestions.py`、`unit_delivery.py`、`verify.py`、`markers` 相关、插件 `tools/index.js`、`cordis.patch.yml`、两份 SKILL/手册、以及 6 个测试文件 |
| 两条线**各自独立**实现了「按单元预算 + 恢复记录」 | main：`jiaodui/execution_policy.py`（120 行，纯模块：`BUDGETS`/`new_policy`/`spend`/`validate_attempt`/`migrate_legacy_spent`）。分支：同一概念内嵌在 `jiaodui/material.py`（`set_execution_policy`/`record_recovery_attempt`）+ 本批新增的 `jiaodui/error_classification.py`（169 行） |
| 报告形态不可互通 | main `jiaodui/markers.py` 无 v2 前缀与转义概念（`grep -c escape_marker_field` = 0）；分支的分支式报告（`report_suggestions.py` 由程序生成报告）在 main 上**已被删除** |
| main 删掉 4 个核心模块与 6 个测试文件 | `report_suggestions.py`/`unit_delivery.py`/`source_index.py`/`unit_reader.py` 及 `test_report_suggestions`/`test_unit_delivery`/`test_unit_identity`/`test_unit_reader`/`test_workflow_milestones`/`test_execution_policy` 均已不在 main（`git cat-file -e` 逐个确认），另新增 `test_execution_compat`/`test_main_policy_contract`/`test_policy_legacy_compat` |
| 核心模块规模 | main `jiaodui/*.py` 31 个；分支 36 个 |
| 两处**殊途同归**（不是分歧，是重复劳动） | 中性中止传播：main `c1c24b9` ≈ 分支 `tools/index.js:419-422`；入口 ≤8192 码点：main `cc1c21f` ≈ 分支 SKILL.md 8164 码点 + 长度回归测试 |

**一句话**：这不是「两条线都往前跑、需要合并」，而是 **main 主动回退了结构化流水线、改在旧主链上加策略；分支则把结构化流水线继续做深**。所以 P7 的选项里，「merge」实际等于「把被回退的架构重新装回 main」。

## 二、三条处置路径与代价

### A. 保持隔离（现状，符合 D3）
- 代价：main 与分支继续分叉；分支的 1112 例测试与 P3/P4/P5/P6 成果不进主线。
- 收益：不动 main 的既有决策；第 7 章实验结论未出前不冒险。
- 本备忘的立场：**先选 A，直到 P2/P6 给出证据**（见第四节）。

### B. 主题移植（只搬与架构无关的成果到 main）
候选（逐个都需要在 main 上重写测试，不能整文件 cherry-pick）：

| 候选 | 可移植性 | 说明 |
|---|---|---|
| 错误码 → 恢复类别的**分类思想** | 高 | main 的 `spend(policy, unit, category)` 仍由调用方给类别；把「类别由模型自选」改成「由错误码确定性映射」对 main 同样有价值（PLAN P5 第 1 项的真正动机） |
| 并发登记原子性压测 | 高 | `tests/test_concurrency.py` 压的是 `material.locked`（POSIX flock）+ 记账不丢条目，main 同构 |
| 交付/报告的**逐条件诊断**（P6 第 2 项） | 中 | 思想可移植（7 个绑定条件压成一句 → 逐条自报），但 main 无 v2 提案绑定，需映射到 main 的闸门错误 |
| ADR 0006 无损标记编码 | 低 | main 无 v2 报告与提案对象，转义契约没有落点；只在结构化线内有意义 |
| 心跳 / 滑窗 / `unit-progress` / `dispatch-plan` | 低 | 依赖分支的 per-unit `unit_state` 账本（main 是扁平 `unit_events` 列表） |
| Word-v2 端到端回归 | 低 | 依赖 v2 报告与父复核门 |

### C. 切换主线（把 main 切到分支）
- 代价：放弃 main 上 `dde758d`/`04f0c78` 的旧主链策略实现与 `e3deab4` 的计划文档；`c1c24b9`/`cc1c21f` 两项因已殊途同归不损失。
- 收益：结构化架构（判断交给 agent、确定性交给 Python、模型不写报告）成为唯一主线；分支的 1112 例测试、ADR 0006、强类型工具面、调度闭环全部生效。
- 前提：需要 **P2 真机验收 + P6 真实校对**证明它在真实会话里可用、且优于旧主链——否则是在没有证据的情况下推翻 main 已做出的判断。

## 三、若最终决定合并（C 或 B 的完整版）：处置顺序

1. **先决策策略模型归属**（唯一真正的架构冲突）：保留 main 的纯模块 `execution_policy.py`、把分支的 `material.py` 内嵌策略迁到该模块，还是反之。**在这件事定下来之前不要动冲突文件**——否则两套预算语义会在合并结果里共存。
2. 报告链：`report_suggestions.py` / `unit_delivery.py` / `report.py` / `report_parse.py` / `verify.py` 按「分支式报告为唯一产物」重建，不做逐行合并。
3. 插件与 preset：以分支的 `cordis.patch.yml` / `tools/index.js` 为准（main 侧已删掉 `proposal-schema.json` / `calc-schemas.json`）。
4. 文档：SKILL.md / operation-manual 两份副本重取分支版并重跑长度与链接回归；`docs/PLAN-*`（只在 main 上）保留。
5. 删除的测试：main 删掉的 6 个结构化测试文件按分支版恢复；同时保留 main 新增的 `test_execution_compat.py` / `test_main_policy_contract.py` / `test_policy_legacy_compat.py` 里对**旧主链兼容**的断言，逐条判断是否仍适用。
6. 收尾：双口径全量 + 冻结语料 + `git diff --check` + 重放快照；不 push，交人复核后再定 push。

## 四、推荐与触发条件

**推荐 A（保持隔离）+ 现在就把 B 清单写成待办**，并在 **P2 通过、P6 两个单元真实校对完成**之后重开本备忘做最终判断。理由：

1. 分支方案的核心主张（模型不写报告、程序从不可变源文生成、结构化提案 + 闸门）**正是 main 主动回退的东西**；要推翻这个判断，需要真实会话证据，而 P2/P6 就是拿这个证据的实验。
2. B 清单里的三项（错误码分类、并发压测、逐条件诊断）**不依赖结构化架构**，无论 C 是否成立都值得进 main，可以先做、低风险。
3. 25 处冲突里有 6 处 modify/delete、且两套预算模型必须二选一——这不是「谁先合谁吃亏」的技术问题，而是产品决策；在没有证据前合并，等于用工程代价替产品决策买单。

**重开本备忘的触发条件**（三者齐备后再判 C）：
- P2：真机新会话里，父/子 catalog 符合设计，且 `read_image` 实读与停止语义正确；
- P6：图片证据型 + 转义边界型两个单元在原生工具面下真实通过闸门并生成 Word；
- 失败可归因：任何失败都能落到具体错误码（不能是「未绑定」这类不可诊断的失败）。

# 实施清单

2026-10-19 [revise 校对工具升级计划](PLAN-revise-tool-upgrade.md) 的P0已获用户验收，现于 `integration/revise-p0-baseline` 整理必要前置与独立P0候选提交，来源和复验见[基线整理记录](<REVISE-P0-BASELINE.md>)，尚未合入main。原实施顺序为先完成共同前置 P0（锚点、证据分层、交互诊断、旧报告旁路保护、core 绑定与入口瘦身），通过出口后再进行真实宿主三臂实验 P0.5；实验决定无状态 v3（A）或持久工作日志（B），此前不编写 A/B 生产代码。报告仍编译为 schema v2，经过原有闸门与父复核；具体实施和验收证据见计划状态，不预设持久工作日志。

2026-10-10 第7章结构化报告主链并入 `main`：子 agent 提交 schema v2 结构化提案、报告由程序从源文生成、父代理复核版本绑定后登记成为**正常交付路径**；旧 Markdown 报告链降级为只读兼容。合并按 [UNIFY-PLAN](UNIFY-PLAN.md) §6 裁决 28 处冲突、修掉 19 处静默变更（main 回退时整份删除的 `source_index`/`unit_reader`/`calc/schema`/`calc-schemas.json` 与 v2 守门已取回），并在映射 main 测试时采纳六处 main 更优语义（`report.ok`、`unit-event` 轮次 CAS 与授权要求、指纹错误码、幂等重放不写盘、被拒 attempt 不写盘）。根仓双口径 **1158 passed / 0 failed**、冻结语料 4/4、P6 材料真机 `build-report`/`build-docx` 通过（标记 2 = 锚点 2 + 兜底 0）；桌面 profile 已切回仓库根包，实验 worktree 与集成分支已删除。见 [PROCESS_REWORK](PROCESS_REWORK.md) 的 Phase 2/3 记录。

2026-10 报告完整性程序化重建：新增 `jiaodui repair-report --unit <dir> [--apply]`（确定性核心 `jiaodui/report_repair.py`）。它只从单元源文重建 `### 标记原文`，把原报告的完整标记插回源文逐字唯一命中的位置；字段找不到、命中多处、乱序、重叠、编号/语法/原因/严重度无效或图片检查失败一律拒绝，`--apply` 前先验候选文本与图片、再原子替换并要求完整 verify-unit 复验，失败恢复原报告。修复不判断校对意见正确性、不改源文、不自动登记；`verify-report` 仍是唯一闸门。回归见 `tests/test_report_repair.py`、`tests/test_skill_docs.py`。

2026-09-30 固定视觉探针：skill/bundle 随包提供 SVG、透明 PNG 和白底 PNG，默认直接读白底 PNG，无需从教材取图；同会话同模型/工具配置成功后复用。入口补充 DSH `read_image(file_path=...)` 和参数错误有限修正，区分调用失败与视觉能力未确认。具体步骤及仅供主 agent 的验收答案见 `skills/jiaodui/references/vision-probe.md`；实际材料透明图仍按需白底处理。

2026-09-30 入口补齐：用户指定讲义/试卷优先；未知类型先只读检查 Word 嵌套表格，必要时有限预览或询问。核对旧仓后补齐类型驱动转换参数、原始 Markdown 导入保真和人工/整篇拆分入口。见 [ADR 0003](adr/0003-material-type-entry.md) 与 [迁移核对](ENTRY_MIGRATION.md)。校对与交付链共用；DSH 真机由用户验证。

状态：**M0 骨架与 M1 高中物理端到端竖切已完成**（见 [docs/M0.md](M0.md) / [docs/M1.md](M1.md) §9）；M1 后补修讲义导入清理与 P1/P2，并已在当前代码上重跑竖切（5/5 通过、28 标记 = 28 锚点 + 0 兜底）。**第7章结构化主链已于 2026-10-10 并入 `main` 成为正常路径**（见上）；下一步 M2 质量评估。
需求与验收口径以 [PRD](PRD.html) 为准；本清单用于确定执行顺序。

2026-09-30 工作区布局修复按 [ADR 0002](adr/0002-workspace-material-layout.md) 实现：写入边界、材料记录与轮次、双向单元集、当前轮交付登记、可搬移 raw 图片、DSH 每次调用工作区注入和延迟输出收集。自动测试与 wheel 仓库外安装另见 [工作区验证记录](WORKSPACE.md)。DSH 真机会话 A/B、子 agent 读图与落盘测试由用户执行，不把 Node 行为测试当作宿主验收。

2026-09-29 入口讨论已确认：主 agent 优先采用用户指定学科并跳过识别预览；未指定时可按入口 skill 的范围限制节选材料，仍不确定则询问。入口规范已同步，待宿主冒烟验证「明确学科跳过读取 / 未指定时有限预览 / 歧义询问 / 未落地学科不套用物理」四条路径；此变更不代表其他学科已落地，也不替代 M2 质量评估。

2026-09-29 DSH 插件包首次尝试：新增 `packages/dsh-jiaodui/`（随包 jiaodui skill + `jiaodui` agent preset + 原生工具 `jiaodui`），配套打包契约测试 `tests/test_dsh_plugin_package.py`。这是 M7 换壳的前置探索：**尚未安装进 profile、未做宿主端到端验收**，现有 CLI 与 skill 仍是主路径与退路（D20）。安装与验证步骤见该包 README。

M5 的入口、学科差异载体、逐科落地路径与验收见 [ADR-0001：M5 多学科入口与逐科落地](adr/0001-m5-subject-entry-and-rollout.md)。该 ADR 保留 M2 / M3 的前置门槛；六科的具体排期与样本范围仍待确定。

| 顺序 | 交付物 | 完成判据 |
| --- | --- | --- |
| 1. 基线与样本 | 旧仓只读语料清单、哈希、去重规则和复算脚本；冻结 22 单元评估清单 | 复算 364/344 及严重度分布，解释现有 194/248 与分布不一致；样本覆盖图片、公式、长单元、无问题单元 |
| 2. CLI 骨架 | 可安装的 `jiaodui` 包，11 个 v1 命令具备稳定参数与退出码 | `--help` 可查询；命令支持结构化错误；本地依赖检查不冒充宿主能力检查 |
| 3. 转换与拆分 | `convert`、规则 `split`、边界 `slice`、`precheck-split` | 试卷和讲义均从源文件生成单元源文及图片；重跑不覆盖已有校对报告；异常拆分可被预检发现 |
| 4. 报告闸门与恢复 | `verify-report`、`status`、`parse-report`、`build-report` | 完整源文、标记、原因、严重度双向契约通过；失败报告不进入汇总；修复后状态从失败转为完成 |
| 5. Word 交付 | `build-docx` | 对生成后的 docx 复核实际锚点；错误标记 = 锚点 + 公式可见兜底，缺失为 0；无问题标题批注单列 |
| 6. 宿主流程与质量 | 总入口 skill、高中物理参考资料、批量派发与两遍评估 | 实测子 agent 本地读图/落盘；22 单元两遍首次校验各至少 20 通过；严重内容错误无未处理漏检 |

每步合入前保留能独立复现的真实样本与命令记录。旧仓只读，新仓不以旧仓为运行时依赖。若基线复算或宿主能力实测推翻 PRD 的待验证前提，先更新相应决策与验收，再扩学科。

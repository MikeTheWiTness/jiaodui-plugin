# ADR 0008：锚点匹配、证据分层与交互类错误

- 日期：2026-10-19
- 状态：accepted（2026-10-19 用户确认P0出口验收通过；范围及证据来源见[验收结论](<../REVISE-P0-ACCEPTANCE-2026-10-19.md>)，D1–D5内容不变）
- 范围：仅限共同前置 D1–D5；不选择 A（无状态 v3）或 B（持久工作日志），不授权实现任一分支的生产接口。
- 关联：[升级计划](../PLAN-revise-tool-upgrade.md) §3–§4、[PRD](../PRD.html#s5-5)、[T09](../TICKETS-full-chain-2026-10-10.md#t09)、[术语表](../../CONTEXT.md)、[ADR 0006](0006-v2-lossless-marker-encoding-and-envelope.md)。

定位与提交分离造成逐字填写错误，平铺证据又会在撤回意见后残留核验说明；同时，新布局仍可借旧版报告解析路径绕过结构化提交。P0 决定先建立确定性锚点、证据分层、独立的交互诊断和 core 版本绑定，并封住人工兼容交付的完成状态边界；这些共同能力同时服务 A/B，分支选择仍须等待 P0.5 对照实验。

## D1：人工 v1 兼容结果不算本轮完成

有材料清单的新布局中，`parse-report` 默认拒绝 v1 报告，返回 `parse-v1-new-layout-forbidden`（exit 6）；显式 `--manual-legacy` 仍须 verify 通过，只写带 `legacy_manual: true` 的 `_校对数据.json`，不登记当前轮交付。`repair-report --apply` 遵循同一人工兼容判定及保护规则。

已有 schema v2 数据、当前轮 v2 登记，或数据已损坏时返回 `legacy-overwrite-v2-forbidden`（exit 6），拒绝覆盖。人工兼容结果的状态为 `CURRENT_PENDING`，原因明确为“人工兼容交付，不计入本轮完成”，`build-report` / `build-docx` 拒绝消费。无清单历史布局的显式 `--legacy-layout` 行为保持原边界。

这是对 T09 的边界决策；不能将 verify 通过的人工 v1 报告冒充父复核通过的结构化交付，也不能覆盖既有 v2 结果来降级交付。既有登记未保留 schema，因此无法证明版本的当前轮登记按可能的 v2 保护，保守拒绝人工兼容覆盖；不能依赖可变阶段事件、报告封套或可能丢失的数据文件猜测登记版本。保护检查、verify 与写入在同一材料锁内执行。

## D2：锚点定位可诊断，结构切断必须拒绝

锚点先严格查找 `context_before + old_text + context_after`，重叠命中也计数；替换区间只含 `old_text`。`occurrence` 是组合匹配串的 1 起命中序号，与既有 `match_index` 同义；不给序号时必须唯一，有序号时必须在界内。

仅在严格查找零命中时，匹配期允许 CRLF→LF 与去掉 U+200B–U+200D、U+FEFF；命中区间必须映射回源文码点，返回源文逐字 `original` 并标记 `normalized_match`。无消歧信息的归一化多命中仍拒绝；不做 NFC、空白折叠、模糊匹配或 LaTeX 归一化，不修改源文，也不放宽完整性闸门。

修订入口切断公式或加粗时返回 `anchor.structure-cut`，以 `details.required_original` 给出应覆盖的完整原文及区间，调用方重新确认后提交；禁止静默扩大修订范围。既有 `unit_locate` 保留自动扩展行为。找不到、不唯一、序号越界、空原文与超长输入各有诊断；歧义候选最多 5 个，含序号、行列、前后各 24 字符上下文及截断标志，不可见字符转义显示。其他有效修订间的重叠由调用方拒绝。空白原因与空操作拒绝，`new_text` 为空表示删除。输入上限沿用计划 §4.2，不能靠无限增长片段或上下文消歧。

## D3：交互诊断与六类恢复预算分离

`anchor.*` / `revise.*` 分类为 `interactive`，返回 `recoverable: false`、`interactive: true`，提示按 details 修正参数直接重试。它们不能用于 `unit-recovery`：恢复入口返回 `recovery-interactive-code`（exit 6），不写盘、不扣六类预算。既有 `location.*` 仍归 `call_correction`，不借新增前缀改变历史错误分类。

这是参数纠正与恢复尝试的职责划分，并不授权无限业务重试、不改变用户取消或权限拒绝的停止规则；A 的定位拒绝计数属于后续分支决策 D13，不在 P0 实现。

## D4：单元覆盖与修订局部依据分层

`unit_evidence` 承担整个单元的假设非空与图片引用全覆盖检查；每条修订至少引用一条单元证据，或携带自己的局部证据。局部证据只随当前有效修订合并与渲染，被撤回或替代的旧意见及其局部证据不进入报告。

继承 v2 时，全部证据先归 `unit_evidence`；当 assumption/calculation 仅被一条 correction 引用时，额外记内部 `inherited_ref`，不把它搬成局部证据。仅当该旧修订已撤回或被替代，且没有其他有效修订继续引用时才修剪。images 永不加 `inherited_ref`、永不因撤回修剪，避免撤回一条意见导致单元图片覆盖消失。新修订继续引用同一依据时必须保留；修剪后 assumptions 为空，返回 `revise.evidence-required`，要求补单元依据。

编译前先检查单元层覆盖，再按有效引用修剪和合并，输出仍是 schema v2 的四键 `evidence`（`assumptions` / `symbols` / `images` / `calculations`）及 corrections；内部 `inherited_ref` 必须剥除，再运行原 v2 校验。图片项的原图路径、实际读取路径与位置由 core 按当前图片清单和 `reference_index` 回填；资源绑定不证明宿主实际读图或模型理解图片语义。

### 图片局部证据的 v2 编译适配

单元层图片全覆盖与局部 image 若分别输出，会违反既有 v2“一条 reference 对应一份图片证据”的约束。编译时以单元层图片 ID 为规范 ID，同一 `reference_index` 的有效局部 image 不再新增 v2 图片项，而将其 `semantic` / `verdict` 带局部证据 ID 标签按顺序追加到规范项的对应观察中；单元层原观察必须完整保留，不得被局部观察覆盖，矛盾观察也原样保留供父复核。相关修订的证据引用 ID 改写为规范 ID。

撤回或替代只移除不再有效的局部追加文本，不删除单元层图片证据；所有参与合并的 `readable` 必须为 `true`，不能用单元项的真值遮蔽局部项的不可读结果。原图路径、实际读取路径与位置全部按当前图片清单回填，最终仍通过原 v2 唯一引用、覆盖与可读性校验。该无损折叠只适配两层证据到既有输出契约，不放宽图片验收，也不裁定观察语义。

## D5：身份与版本绑定由 core 在锁内完成

`unit-submit --bind-current` 在材料锁内取得当前 snapshot，填写 `task_id` / `unit_id` / `run_id` / `source_sha256` / `body_sha256` / `proposal_revision`；仍要求 `--expected-snapshot-sha256`。调用方显式携带的绑定字段若与当前值冲突，返回 `proposal-binding-conflict`，不能静默覆盖错误认知。

core 同时导出 `unit-schema --bind-current`，仅从 required 中移除上述六字段；全量 schema 不变。两学科插件读取随包 bind schema、透传绑定参数，删除 JS 侧额外 snapshot 调用、字段拼接和 schema 改写。CLI 与插件由同一核心规则绑定，避免壳路径决定交付语义。

## 取舍与验证边界

- 不采用模糊定位或静默扩展修订范围：参数更省事的代价是可能把真实发现标到另一段，或扩大模型未确认的修改。
- 不采用所有错误均扣恢复预算：定位参数试探不应耗尽报告自修或技术恢复额度；交互拒绝仍必须清楚可见。
- 不采用把全部继承证据直接改为局部证据：撤回意见不能破坏单元覆盖；引用修剪只去掉已失去有效引用的继承假设和计算。
- 不采用在插件壳继续自动绑定：CLI 与插件必须共用锁内身份和版本语义。
- 不采用人工 v1 直接登记完成：兼容读取与本轮结构化交付是不同事实。

本文记录目标契约，不作为实现通过证明。P0 出口仍需共同能力的正反向测试、全量与 CI 双口径通过、ADR 评审采纳、冻结样本及人工标注，并以真实插件 `unit_submit` 冒烟确认 D5 不回退；文档同步与模拟测试均不能替代人工验收或宿主冒烟。P0 出口通过前不进入 P0.5；P0.5 判定前不写 A/B 生产代码，本文不决定持久化日志、存储位置或 A 的拒绝计数机制。

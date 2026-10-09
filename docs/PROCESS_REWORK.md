# 校对流程改造执行记录（实验分支）

> **文档状态**：合并计划已重做为 [`UNIFY-PLAN.md`](UNIFY-PLAN.md)（唯一计划文档）。此前用于 P2 验收与 P7 判断的 `P2-ACCEPTANCE.md` / `NEXT-SESSION-BRIEF.md` / `P7-MERGE-DECISION.md` 已删除，其事实与批次记录保留在本文件（本文件只作**批次记录**，不再承担计划职责）。

依据 EasyUse《校对流程改造执行计划》。用户已澄清“第7条”指计划**第7章：定位建议与程序生成全文报告**，不是§1.1第7项。M2定位、M3结构化主链及依赖它们的M4审查全部隔离在 `feature/structured-report-pipeline`，不部署、不合入main；main维持旧Markdown报告主链，仅保留兼容改造。

## M0现状

- 初始main为`abfea6c`，工作树干净。`.venv`指向仓内独立`.venv-cli`；Python 3.12.13，editable CLI，pandoc 3.9.0.2。
- 改造前全量基线941 passed、4 subtests passed；后续只跑合成/临时目录的定向测试，不重跑既有业务样本。
- 已确认桌面profile的`node_modules/dsh-jiaodui`是软链，指向仓库根`packages/dsh-jiaodui`。未改profile或手动替换安装包；实验源码必须移到独立worktree，根目录回到main，避免下次重载意外加载实验链。官方新安装/重启/新会话验收仍待完成。
- 实际安装的ASAR以只读方式按归档索引提取供审计，未修改宿主或用提取副本作为部署源码。确认skill-filesystem支持`includeDefaultRoots:false`，默认来源是项目`.dsh/skills`、`.agents/skills`、用户dshHome/agentsHome及宿主bundled根。subagent支持`toolFilter`和`maxDepth`。配置可表达排除默认skill与子工具allowlist，实际新会话仍须验收。

## 实验实现

- **M1部分**：轮次执行模式与预算持久化；preset去掉shell、关闭web/goal/plan/fork。聚合fs必须暂保留真实read_image；父只读工具细分尚未实现，不能称完全隔离。
- **M2**：task/unit ID、源码SHA绑定、Unicode码点位置和重复词候选、安全公式/加粗范围；calc schema从核心元数据导出。**P4 已补齐父侧结构化工具**（准备 / 交付），正常路径不再手拼 argv，见下节。
- **M3初版**：schema v2提交少量建议，程序生成全文；长度封套保护正文中的报告标题/装饰行；快照CAS和材料锁，异常回滚报告/数据/清单，登记为最后提交标志。初版不能无损承载原文字面含`|`/标记括号的内容，只能明确拒绝；**P3 已按 ADR 0006 补齐可逆特殊字符编码与正文/信封契约**，见下节。
- **M4初版**：assumptions/symbols/images/calculations首轮证据、必需自查项；真实calc call_id与单元源码/轮次/结果关联；父复核绑定输入/建议/自查/报告hash。最新退回撤销旧接受。技术报告仍可汇总通读，但unreviewed时complete=false、Word拒绝。
- **M5部分**：恢复类别累计、失败指纹、阶段事件、显式取消来源API。调度尚依赖宿主/父代理主动登记；插件中断来源不得猜为用户。预算耗尽留痕，不能换agent刷新额度。**P5a 已把「错误码 → 恢复类别」变成确定性映射，P5b 已补心跳与超时判据，P5c 已收口并发登记与滑窗判据**，见下节。
- **M6部分**：Word与报告解析共享v2正文边界；旧parse/repair拒绝覆写v2数据。诊断文件生成与正式complete分离。双skill和bundle schema有漂移测试。

## P3无损契约（ADR 0006，已完成）

格式决策写在实施之前：新增 [ADR 0006](adr/0006-v2-lossless-marker-encoding-and-envelope.md)。按 D2 走「v2 正文内反斜杠转义 + 唯一反转义入口」，并补齐两处计划外的必要条件——① 语法检查只看结构分隔符，字段内容一律屏蔽（否则合法报告会被自己内容判成括号不配对/字段数错误）；② 正文/信封边界、`extract_body` 唯一提取点、空白正文显式拒绝。

落地：

- `markers.py`：新增 `escape_marker_field` / `unescape_marker_field` / `is_v2_report` / `mask_marker_fields`；标记正则改为「反斜杠加任意字符视为整体」，原文字段与改为字段都能容纳转义后的 `\|`、`\【`、`\】`；`split_marked_body` / `audit_markers` 增加显式 `escaped` 参数（v1 默认，不转义也不反转义）；`scan_math_spans` 的字段屏蔽改用等长结构屏蔽。
- `report_suggestions.py`：删除三处硬拒绝（原 `:205` 源文含标记语法、`:233`/`:234` 原文字面与改为含括号或竖线），改为写入侧转义；`source_sha256`（文件字节）与 `body_sha256`（正文文本）分别校验并让诊断指明是哪一项；新增 `proposal.empty-body`。
- 四个消费点接线：`verify.py`（语法、字段、完整性全部带 `escaped`）、`report_parse.py`（corrections 内容反转义）、`docx_report.py`（审计与 `_mask_markers` 反转义）、`unit_delivery.py`（`extract_body` 计算正文摘要、快照文件摘要作为 `expected_source_sha256`）。`report_repair` 保持 v1 语义——它已拒绝 v2 报告。
- 不放宽拒绝：空原文、空操作、无唯一位置、区间重叠、乱序、`split_marked_body != 正文` 全部保持拒绝；`verify-report` 仍是唯一闸门。

测试与口径：新增 `tests/test_marker_escape.py`、`tests/test_report_suggestions.py` 的执行计划 §11.1/§11.2 场景（竖线/标记括号/反斜杠/emoji/组合字符/零宽/CRLF/跨行公式无损恢复、空正文拒绝、21 字符短正文放行、v2 不剥信封、反向用例仍拒绝）。双口径全量 **1043 passed / 0 failed / 5 skipped**（P3 前 989 + 5 skip；5 个 skip 是 worktree 内语料路径依赖，非真跳过）；带 `JIAODUI_LEGACY_CORPUS` 的旧语料 4/4 与 `test_m1_fixture` 3/3 保持预期。实测冻结语料无一份含 `\】` 边界写法，故正则扩展不改变 v1 既有预期。

## P4强类型父工具（已完成）

父侧准备/交付不再靠 `args: string[]` 手拼命令行，改由结构化工具传名参数；壳仍只做参数搬运与协议转换，判断留在 core。

- `jiaodui_task_prepare`：`operation` 取 `check-env` / `inspect-source` / `convert` / `split` / `precheck-split` / `status` / `execution-policy`；按 operation 选参（`path`、`preview_chars`、`material_name`、`subject`、`mode`、`mode_origin`、`mode_reason`、`strategy`、`no_clean`、`execution_mode`、`origin`）。未用到的参数不拼进 argv，缺参数不在 JS 里判，交给 CLI 出稳定的用法错误（exit 2）。
- `jiaodui_delivery`：`operation` 取 `build-report` / `build-docx` + `paper_dir`；在通用四字段之外附 `json`（stdout 的解析副本，含 `ok` / `complete` / 结构计数），解析失败时缺省该字段、不抛错。
- 未做可选的 `jiaodui_finalize_unit`：v2 正常路径的 `unit-submit` 内部已完成 verify 与登记，独立 finalize 只服务旧 Markdown 报告链，而旧链走 `jiaodui` argv 退路。
- 通用 `jiaodui` argv 透传保留（CLI 是永久退路）；skill 正常路径只写结构化工具。

测试与冒烟：
- Node 行为测试（真加载插件）断言两个工具 `additionalProperties: false`、`required`、**不暴露 `args` 逃生口**，并逐条核对 argv（含 `--no-clean` 只在 `no_clean: true` 时出现、可选参数省略时不进 argv、`json` 字段在非 JSON stdout 下缺省）。
- Python 侧新增「插件拼出的每个 `--flag` ⊆ CLI 实际注册」「`TASK_PREPARE_OPERATIONS` / `DELIVERY_OPERATIONS` ⊆ 真实子命令」「准备/交付工具结构化注册且无 `args` 数组」三条一致性测试。
- 真机 CLI 冒烟（带插件同款 `JIAODUI_WORK_ROOT` 注入）：`check-env`、`inspect-source <docx> --preview-chars 0`、`status <paper_dir>`、`precheck-split <paper_dir>` 四条按工具拼出的 argv 全部 exit 0 且返回预期字段。
- 文档同步：两份 `SKILL.md`（**8133 码点**，余量 59，仍在 8192 阈值内）与两份 `references/operation-manual.md` 字节一致；顺手删掉一句因 P3 而过期的措辞（"标记不可无损表达时拒绝写入"）。

口径：双口径全量 **1047 passed / 0 failed / 5 skipped**（P4 前 1045 + 5 skip）。

## P5a确定性错误分类（已完成）

背景：预算与指纹记账已经能防重复，但**类别由模型自选**，同类故障可能被记进不同预算——第 11/12 讲回放的 `unit_events[].source` 里出现整段散文就是征兆。本批把「这个错误该花哪一类额度」变成确定性映射，编排侧只报错误码。

- 新增 `jiaodui/error_classification.py`（单一源）：`RECOVERY_CATEGORIES`、`RECOVERY_BUDGETS`、约 60 条精确码表、前缀规则（`proposal.` / `location.` / `calc*` / `images.` / `syntax.*` / `integrity.*` 等）、不可恢复集合，以及 `classify_error(code)` 的三向返回 `{recoverable, forbidden, category, reason, suggestion}`。
- `material.py` 原先在 `_validate_execution_policy`、`set_execution_policy`、`record_recovery_attempt` 各写一份类别/额度清单（CLI 里还有第四份），现全部收敛到该模块。
- `record_recovery_attempt(..., *, error_code=None)`：错误码决定类别；只给 `category` 时仅允许父代理判断类的 `targeted_review`；码与类别不一致拒绝；未分类码、用户取消、权限拒绝一律拒绝且**不消耗任何预算**；`recovery_events` 增加 `error_code` 留痕。
- CLI `unit-recovery` 新增 `--error-code`、`--category` 改为可选；`jiaodui_unit_recovery` 工具 schema 同步（`required` 去掉 category、新增 error_code）。
- 测试：新增 `tests/test_error_classification.py`（计划点名的四例 + 25 个真实错误码映射 + 取消/权限不可恢复 + 未分类给相近码建议 + 恢复入口三类拒绝 + 被拒绝不消耗预算 + `targeted_review` 免码）；`test_workflow_milestones` 的预算累计用例按新契约传码。
- **顺带发现并加了守卫**：`.venv` 的 editable 安装指向根仓 main，因此 worktree 能 import 到**只有 main 才有的模块**（`jiaodui.execution_policy`）——P5a 第一次跑红测试时 ImportError 的路径指向根仓文件，差点把排查方向带偏，更危险的是会静默读到另一条线的代码。新增 `tests/test_module_integrity.py`：断言本包相对导入必须指向本包内真实存在的模块（按声明文件所在目录解析，`calc/*.py` 不被误判）。
- 真机 CLI 冒烟（/tmp 临时材料 convert → split → execution-policy → unit-recovery）：`usage`/`verify_failed`/`images.missing`/`host-timeout` 分别记入 `call_correction`/`report_repair`/`image_schema_fix`/`technical_redispatch` 各 1 次；`user-cancel`、`no-such-code`、缺错误码的 `--category calc_representation` 三类被拒且 `recovery` 为空、无事件落盘。

口径：双口径全量 **1084 passed / 0 failed / 5 skipped**（P5a 前 1047 + 5 skip）。

## P5b心跳与超时判据（已完成）

背景：编排侧原先只能靠「沉默多久没消息」猜崩溃。`record_unit_event` 早已维护 `run["unit_state"][unit_id] = {phase, attempt_id, agent_id, last_event_at}`，本批把它变成只读投影 + 确定性判定。

- `material.unit_progress(task_id, *, unit_id=None, stale_after_seconds=900)`：只读（不取锁、不写盘），按 task_id 解析材料，返回每单元的 `phase` / `attempt_id` / `agent_id` / `last_event_at` / `age_seconds` / `event_count` / `in_flight` / `stale` / `cancelled`。
- 判据：终态为 `registered` / `parent_reviewed` / `deliverable`，到终态即不在途；被显式取消（`unit-event --cancel-initiator/--cancel-reason`）的单元不再算在途，因此**父代理技术取消不会被误判为超时**；`stale` 只在「在途且最后事件距今超过阈值」时为真。
- CLI `unit-progress --task-id T [--unit-id U] [--stale-after-seconds N]`；原生工具 `jiaodui_unit_progress`（父侧，不在子代理 allowlist 内）。
- 测试：新增 `tests/test_unit_progress.py`（无事件不在途、在途暴露 phase/attempt/时间、终态即便陈旧也不超时、沉默过久转 stale、取消后不在途且暴露发起者与原因、只读不改清单、未知 task/unit 报 not_found）。`tests/test_cli.py` 命令清单与 Node 行为测试同步补 `unit-progress`。
- 真机 CLI 冒烟（/tmp 临时材料）：① 无事件 → `in_flight=false`；② 记 `read` 心跳 → `in_flight=true`；③ 记终态 `registered` → `in_flight=false`（阈值 0 也不超时）；④ `--cancel-initiator parent --cancel-reason technical_timeout` → `in_flight=false` 且 `cancelled={'initiator':'parent','reason':'technical_timeout'}`；⑤ 未知 unit_id → exit 5 `not_found`；⑥ 负阈值 → exit 6 `progress-invalid`；正常查询 exit 0。

口径：双口径全量 **1092 passed / 0 failed / 5 skipped**（P5b 前 1084 + 5 skip）。入口 skill 8154 码点（余量 38，仍在 8192 阈值内）。

## P5c并发登记与滑窗判据（已完成）

**并发登记原子性（P5 第 4 项）**：新增 `tests/test_concurrency.py`，用线程与独立进程两条路径压 `material.locked`（`fcntl.flock` 锁材料目录 inode；清单原子替换不换锁对象）：

- 8 单元 × 5 次 `unit-event`（线程）→ 每单元恰好 5 条、合计 40 条，`unit_state` 不互相覆盖；
- 8 条独立 CLI 进程各登记 1 次 `unit-event` → 每单元恰好 1 条且 `attempt_id` 与进程一一对应（真实场景：8 个子 agent 各一条进程）；
- 8 个并发 `unit-recovery` 抢同一单元的 `call_correction` 预算（2）→ 恰好 2 个 allowed、其余 `retryable=false`，`used==2` 且指纹计数为 2；
- 8 单元并发 `unit-submit`（无问题报告）→ 全部 `registered`，`unit_records` 恰好 8 条，不丢不覆盖。

**滑窗与停止判据（P5 第 3 项中可由 core 判定的部分）**：新增只读 `material.dispatch_plan(task_id, *, window=8)` 与 CLI `dispatch-plan` / 工具 `jiaodui_dispatch_plan`：

- `dispatch` 只给下一批可派发单元，且**先排除在途单元**（`unit_progress.in_flight`），因此同一单元不会被重复派发；
- 候选只取「未开始 / 已交付未过校验 / 本轮未完成」；`waiting` 是窗口外排队；
- 任一单元被显式取消即 `stop=true`、`dispatch=[]`，候选留在 `waiting` 交人裁定，不为凑满窗口继续派发；父代理技术取消同样按停止处理，但不冒称用户取消；
- 只读：不派发、不占预算、不改清单。

边界说明：真实「补位、取消在途、确认停止后结束批次」的执行者仍是宿主/父代理——core 只提供可判定的输入与停止条件（本仓 PROCESS_REWORK 早已声明「本兼容核心只实现显式策略、按单元预算及事件记账，不声称完成真实 agent orchestration」）。取消来源分离与插件 `AbortError` 中性上报已分别由 `test_workflow_milestones`（parent 冒称 user_cancel 被拒）与 Node 行为测试锁定。

测试与冒烟：`tests/test_unit_progress.py` 增补 3 例滑窗判据（空位补位且不重复派发、取消后停止、非法窗口与只读）；`tests/test_cli.py` 命令清单与 Node 行为测试同步补 `dispatch-plan`。真机 CLI 冒烟：5 单元材料 `window=8` → `dispatch=['单元3','单元4','单元5']`（已完成的两个不再派）；`window=1` → `dispatch=['单元3']`、`waiting=['单元4','单元5']`；带 parent 技术取消的材料 → `stop=true`、`dispatch=[]`、`cancelled` 暴露发起者与原因；`--window 0` → exit 6。

口径：双口径全量 **1100 passed / 0 failed / 5 skipped**（P5c 前 1092 + 5 skip）。入口 skill 8164 码点（余量 28，仍 <8192）。

## P6两项失败单元根因（第 2 项，已完成）

按 PLAN-rework-continuation P6 第 2 项：只修根因、写能先失败的回归测试，**不重跑、不开新轮次、不动旧留痕**（两份 `_校对失败.md` 原样保留）。

**4讲 单元10（练9）——计算证据绑定**
- 现象：`{"code": "proposal.calc-call-mismatch", "message": "计算证据未绑定当前单元源文的成功calc调用"}`，exit 6；留痕列出 6 个已登记 `call_id`。
- 定位：核对材料记录里这 6 条调用——`run_id`/`source_sha256` 都与留痕一致、`success` 全为 true；其中 `fbedf055`、`d7cee961` 两条是 `dimensional`，`result.result` 是**对象**（`{consistent, left_dimensions, …}`）。原实现把 7 个绑定条件（call_id 存在、task/unit、run、源文摘要、success、expression 逐字、result 逐字）压成一句「未绑定」，因此无法判断当时是抄了布尔/部分对象，还是 expression 有空白差异；提案按设计不落盘，重放会话 dump 已不在，无法回放确切条件。
- 修复（core）：`_validate_calculation_evidence` 逐条件自报——call_id 不存在 / 属于别的单元 / 记录在另一轮次 / 绑定另一份源文摘要 / `success=false`（附 error）/ expression 与记录参数不逐字一致（附实际参数）/ result 与 `result.result` 不一致（附实际返回）；`details` 不便承载时信息进 message。
- 回归（先红）：`tests/test_report_suggestions.py` 新增 7 个条件各一例 + 1 个反向契约（逐字抄回含 `dimensional` 对象结果必须通过）。

**5讲 单元2（练1）——图片证据格式**
- 现象：`proposal-json-invalid`（把文件路径当 JSON 传）→ 改传 JSON 文本后 `{"code": "proposal.evidence-images", "message": "images须为证据数组或带原因的not_applicable"}`，exit 6。
- 定位：**契约缺口**。`_validate_first_pass_evidence` 只接受「数组」或 `{"status":"not_applicable","reason":…}`，而 `operation-manual.md` 的示例只示范了 `not_applicable` 形态——带图单元没有可照抄的数组样例；报错也不说收到的形状，模型只能猜。附带一条：`unit-submit --proposal-json` 只吃 JSON 文本，不吃文件路径，这也该在文档里写明。
- 修复（core + 文档）：拒绝信息改为列出两种合法形态 + 该键的数组项字段清单 + 实际收到的形状（对象列键、其他给类型）；`operation-manual.md` 的证据示例补上带图/带算的数组形态，并写明 `expression`/`result` 必须与记录逐字一致、`dimensional` 返回对象而非布尔。
- 回归（先红）：非法形状被拒且报错含「数组」「not_applicable」与实际键名；合法数组被接受。

口径：双口径全量 **1103 passed / 0 failed / 5 skipped**（P6 第 2 项前 1100 + 5 skip）。

## P6确定性链路验收：Word-v2 端到端 + 整卷 complete（第 1/3 项，已完成）

计划 §0 记录「`6e89d0d` 的 Word-v2 端到端回归在实验分支缺失」，本批移植并按新契约重写。

**为什么不能照搬**：归档那版跑在 `4c82e24`，当时 v2 报告不需要父复核，`build_docx(..., legacy_layout=True)` 直接生成即可。本分支的 M4 闸门（`docx_report.py:370-378`）要求 v2 单元**已登记且当前版本父复核 accepted**，`legacy_layout=True` 时没有清单（`data is None`）→ `current_review=False` → 单元被正确排除。照搬会得到「结构化建议尚无当前版本的父代理复核」的假失败。因此重写为完整链：`convert → split → execution-policy → unit-submit（登记）→ unit-review（accepted）→ build-docx`。

**新增用例（`tests/test_docx_report.py`，9 例）**
- `test_report_marker_count_handles_v2_body_heading_and_legacy_report`：正文自带 `### 修改原因` 时，`_report_marker_counts` / `_is_included_unit` 仍按共用分节解析计数（v2 与旧报告各一例）。
- `test_build_docx_accepts_v2_after_submit_and_parent_review`：走完整链后 `build_docx` 成功；`marker_count == anchor_count == 1`，`heading_comment_count/missing_count/over_count == 0`；Word 正文含原文「木板」、批注含「木块」与原因；**v2 正文字面保留**（`修改原因`、`编号：木板` 均在正文里，`jiaodui-body` 信封标记不泄漏）。
- `test_build_docx_excludes_v2_without_current_review`：提交但未复核 → 单元被排除、原因含「父代理复核」、不产出 docx。
- `test_build_docx_unescapes_v2_marker_fields_without_leaking_backslashes`：**P3 转义边界走完 Word**——源文含竖线与标记括号（`甲|乙与【注】尾。`），报告写入侧确实含 `甲\|乙`，Word 正文还原为 `甲|乙`、批注为 `甲或乙`，且 `\|` 不泄漏到正文或批注。
- `test_build_docx_legacy_requires_reasons_and_strips_decorations`（2 参数）：旧报告仍走兼容清理（`编号：`/`内容：` 不进正文），缺原因则整单元排除且不产出 docx。
- 整卷闸门三条：`test_build_report_is_complete_only_when_every_unit_passed`（1 单元通过 → `complete=true`，拼入正文含 `## 单元名` 与标记）、`test_build_report_marks_missing_unit_as_failed`（2 单元只交 1 个 → `complete=false`，缺报告的单元记 `failed`，`ok` 仅表示诊断文件已生成）、`test_build_report_marks_submitted_but_unreviewed_unit`（提交未复核 → `complete=false`，记 `unreviewed`）。

**顺带确认的两条语义**（写进用例，避免以后再猜）：材料单元集与磁盘不一致是**硬错误** `unit-set-mismatch`（带 `.superseded/<run_id>/` 提示），不是 `complete=false`；`unreviewed`（已提交未复核）与 `failed`（本轮无报告）是两个不同桶。

**操作口径修正（本批踩到）**：`pyproject.toml` 的 `addopts` 已含 `-q`，若命令行再加 `-q` 会变成 `-qq`——pytest 9 的 `-qq` 会**连汇总行一起吞掉**，看起来全绿却没有数字。规范调用：默认口径用 `python -m pytest`（不要另加 `-q`），CI 口径用 `python -m pytest -o addopts='' -q -rs`；批次口径从本批起同时记录 `--collect-only` 总数，便于核对新增例数。

测试与口径：本批新增 **9 例**（`tests/test_docx_report.py` collect 92 → 101；全量 1108 → 1117）。双口径执行均 **1112 passed / 0 failed / 5 skipped / 4 subtests**（1112 + 5 = 1117 = collect 总数，自洽；5 个 skip 仍是工作树路径相关的旧语料/回归样本）。

## P2准备：worktree 可独立安装 + profile 已切分支包（待重启验收）

PLAN-rework-continuation P2 的前置工作。**用户已选定「先做 P2，再用原生工具跑最小真实校对」**，因此本轮把宿主侧准备做完，验收需重启 DSH 后在新会话执行。

**发现并解决的硬阻塞**：`packages/dsh-jiaodui/tools/index.js:36-45` 的 `defaultCommand()` 按**包自身位置**找 CLI（`<包>/../../../.venv/bin/jiaodui`，并要求 `<包>/../../../jiaodui/cli.py` 存在），而 worktree 没有 `.venv`；更关键的是，即使有，若走的是主仓 `.venv-cli`，控制台脚本会 import 到**主仓**的 core。因此：

- 给 worktree 建独立 venv：`/Users/chouchou/.pyenv/versions/3.12.13/bin/python3.12 -m venv .venv` + `pip install -e '.[dev,render]' build`（清华源）；`.venv` 已被 `.gitignore` 覆盖，不进版本库。装完 `import jiaodui` → worktree。
- **判别器验证**：从 `cwd=主仓` 调 `<worktree>/.venv/bin/jiaodui --json dispatch-plan …` 成功（`dispatch-plan` 是分支独有命令；主仓 CLI 同命令 exit 2）。说明插件用控制台脚本时一定会跑分支 core。
- **一个必须记住的坑**：setuptools 的 editable 元路径查找器排在 `PathFinder` 之后，所以 `python -c` / `python -m jiaodui` 在 `cwd=主仓` 时会读到**主仓**的 `jiaodui`（实测 `jiaodui.__path__` 指向主仓）。控制台脚本的 `sys.path[0]` 是脚本目录而非 cwd，因此不受影响——**不要让插件改走 `python -m`**。

**profile 切换（三处必须一致，否则启动时 frozen install 对不上）**：
- `~/.dsh/profiles/desktop/package.json` 的 `dsh-jiaodui` 链接 → worktree 包；
- `pnpm-lock.yaml` 的 specifier 与 version 两条链接记录 → worktree 包；
- `node_modules/dsh-jiaodui` 软链 → worktree 包。
- 备份：`package.json.bak-p2-20261009-224655`、`pnpm-lock.yaml.bak-p2-20261009-224655`（回滚命令见 `docs/P2-ACCEPTANCE.md`）。
- 自检：`createRequire(profile/package.json).resolve('dsh-jiaodui/package.json')` → worktree 包；skill 目录解析到 worktree `skills/`；插件 CLI 解析到 worktree `.venv/bin/jiaodui`。
- 另查：profile 自己的 `cordis.patch.yml` **没有**覆盖 `preset-jiaodui`，所以分支 preset 原样生效；但 `agent-preset-registry` 的默认是 `standard`，新会话必须手动选「校对」。

**分支插件在 Node 下的加载面**：`apply/inject/name` 三键导出，桩 ctx 下注册 26 个工具；插件相关测试 24 例全绿。

新增 `docs/P2-ACCEPTANCE.md`：前置状态、会话设置、8 条验收项（父/子 catalog、skill 挂载、`read_image` 实读、零 shell 真实校对、停止语义、CLI 判别器、噪音）、以及一条命令的回滚。

**P6 最小真实校对的两份输入已就绪**（重启后直接可用，都在主工作区 `校对/` 下）：

| 类型 | 材料 | task_id | 单元 / unit_id | 特征 |
|---|---|---|---|---|
| 图片证据型 | `第 6 讲校对测试-分支性能测试`（既有夹具） | `236927c8ceb44ea3bfdef3bff15e525b` | `单元3` / `59759d1521a3449c8a183b77fe38ea82` | 2 张图（原图 + 白底副本），未开始 |
| 转义边界型 | `P6转义边界合成`（本批新建，合成试卷） | `6166638e79594f5caf77c0aadd5849c1` | `第1题` / `665683a274ad422795218044fe618d37` | 源文含 14 个表格竖线与 1 处 `【注】`；**默认 split 就保留竖线**（不需要 `--no-clean`），因此 ADR 0006 转义路径由真实判断可达 |

两份都未预设 `execution-policy`（或保持既有轮次），让真机流程自己走 `jiaodui_task_prepare` → 结构化提交，从而验证真实链路而不是我预先铺好的状态。

口径：本批只加文档与宿主准备，未改 `jiaodui/` 代码；双口径仍为 **1112 passed / 0 failed / 5 skipped / 4 subtests**。

## P7决策材料：合并/切换结论（已完成决策备忘，待证据齐备后拍板）

**本轮最重要的发现**：main 回退的正是分支的基线提交。`c7fa622` = `Revert "feat(workflow): add structured unit submission pipeline"`，reverts `4c82e24`——而 `4c82e24` 就是本分支的起点。所以 main 与分支不是「都往前跑需要合并」，而是 **main 主动回退结构化流水线、改在旧主链上加策略（`dde758d`/`04f0c78`），分支把结构化流水线继续做深**。

量化事实（新增 `docs/P7-MERGE-DECISION.md` 记录全部可复现命令）：

- 分叉点→main：48 files, +1451 / −2659；main 删掉 4 个核心模块（`report_suggestions.py`/`unit_delivery.py`/`source_index.py`/`unit_reader.py`）与 6 个测试文件，新增 3 个兼容/策略测试。
- 试合并冲突面（`git merge-tree --write-tree`，不动工作树）：**25 处（19 content + 6 modify/delete）**，覆盖所有分支碰过的核心模块、插件、两份 SKILL/手册与 6 个测试文件。
- **两条线各自独立实现了「按单元预算 + 恢复记录」**：main 是纯模块 `execution_policy.py`（120 行，`BUDGETS`/`new_policy`/`spend`/`validate_attempt`）；分支是 `material.py` 内嵌 + 本批的 `error_classification.py`（169 行）。这是唯一真正的架构冲突。
- 报告形态不可互通：main 的 `markers.py` 无 v2/转义概念；分支的程序生成报告链在 main 上已被删除。
- 两处殊途同归（不是分歧）：中性中止传播（main `c1c24b9` ≈ 分支 `tools/index.js:419-422`）、入口 ≤8192 码点（main `cc1c21f` ≈ 分支 SKILL.md 8164 码点 + 长度回归）。

**结论与推荐**：三条路径（A 保持隔离 / B 主题移植 / C 切换主线）已逐项列代价。推荐 **A + 现在就写 B 清单**，并在 P2 通过、P6 两个单元真实校对完成后重开备忘做最终判断——因为分支的核心主张正是 main 回退的东西，推翻该判断需要真实会话证据，而 P2/P6 就是取证的实验；B 清单里的三项（错误码分类、并发压测、逐条件诊断）不依赖结构化架构，无论 C 是否成立都值得进 main。**在策略模型归属（`execution_policy.py` vs 分支 `material.py`）定下来之前，不要动任何冲突文件**。

## P2交接：本会话是 standard preset，无法就地验收

用户已重启 DSH（profile 三处切换仍指向 worktree 包），但**本会话是 standard preset**（证据：本会话工具目录里没有 `jiaodui_*` 原生工具、但有 bash；分支 preset 会把整个 shell 移除）。preset 在会话创建时确定且工具目录按会话固定（请求缓存稳定），所以 P2/P6 的真机验收必须换到「校对」preset 的会话。

新增 `docs/NEXT-SESSION-BRIEF.md`：自包含交接（会话设置、任务一 8 条验收的重点四条、任务二两个单元的 task/unit id 与要求、禁止事项、做完后写哪里），使新会话不需要上一个会话的上下文即可开工。

### P2 中不依赖宿主会话的那条已验收：真实安装方式（wheel / pipx 路径）

插件在找不到 CLI 时提示「pipx install <jiaodui wheel>」，所以分发路径必须独立验证，不能只验 editable：

- `python -m build --wheel` 成功产出 `jiaodui-0.1.0-py3-none-any.whl`（194 KB，51 个条目）。内容核对：核心模块齐全（含分支新增的 `error_classification.py`、`review.py`、`report_suggestions.py`、`source_index.py`、`unit_delivery.py`、`unit_reader.py`），**包数据 `jiaodui/data/subjects/高中物理.json` 与 `py.typed` 都在**（包数据漏装是常见打包缺陷，这条证明没有）。
- 装入全新的 `python3.12 -m venv` 后：`import jiaodui` → **site-packages**（不是仓库），控制台脚本 `jiaodui` 可用，`check-env` → `ok=true`。
- **判别器**：同一 venv 里 `jiaodui --json dispatch-plan --task-id 236927c8…` 返回 `ok=true, dispatch=['单元3','单元4']`——分支独有命令可用，证明 wheel 里装的是**分支 core**。
- 优雅降级：该 venv 未装 matplotlib，`matplotlib_available()` 返回 `False` 且不抛异常，符合「render 依赖缺失时优雅降级」的约定。

尚未验收（需宿主会话）：父/子 catalog、skill 挂载、`read_image` 实读、零 shell 真实校对、停止语义。

### P7 收尾前检查（可独立完成的部分已全绿）

| 检查 | 结果 |
|---|---|
| 空白错误 | `git diff --check 4c82e24..HEAD` 无输出 |
| 凭证泄漏 | 分支净增内容扫描 `sk-*` / `api_key=` / `Bearer` / `AKIA*` 均无命中 |
| 文档不变量 | 两份 `SKILL.md` 逐字节一致、8164 码点 < 8192；`skills/jiaodui` 与打包副本整目录一致 |
| 回放材料未被今天的改动波及 | `find 校对 -newermt "2026-10-09 21:00"` 中「回放」命中 **0** 个；两份 `_校对失败.md` 仍是 14:22 |
| 今天写入 `校对/` 的全部文件 | 只有我为 P6 新建的 `P6转义边界合成/*`；夹具 `第 6 讲校对测试-分支性能测试` 的 mtime 是 **21:49:05**（早先那轮 2 单元性能测试），那之后只做过只读查询 |

顺带纠正一个我先前的错判：回放材料里**本来就有** v2 报告（第 4 讲 4 个、第 5 讲 4 个，见各自 `校对报告/*_整卷报告.md` 与成功单元的 `_校对报告.md`）——因为那次「流程改造回放」本身就是跑分支流程产出的；失败单元则只有 `_校对失败.md`。所以判据不是「回放材料不含 v2」，而是「今天没有改动它们」，后者已确认。

另注：夹具当前轮次 `12e3e268` 里两单元已登记但 `unit_reviews` 为 0、`unit_state` 空——即早先那次性能测试只走了提交、没走父复核，也没有心跳事件；这正好说明 P6 真机跑的时候父复核与心跳是新覆盖（不是我铺好的状态）。

口径：本批只加文档，未改 `jiaodui/` 代码；双口径仍为 **1112 passed / 0 failed / 5 skipped / 4 subtests**。

## P2 修正：父侧恢复 shell 与只读搜索（子侧保持封闭）

**触发**：P2 真机验收暴露的能力缺口。上一会话在「校对」preset 里复现了 Word 锚点丢失、把条件收窄到「标记落在表格行内 / 字段含转义」，但**没有任何读 docx 内部 XML 的通道**（`read` 对 docx 直接报 `binary file`，插件也未暴露解压/跑代码的工具），只能停在「根因待复核」并交接。同一个根因，在有 shell 的会话里（解 XML + pandoc 三层最小对照）一次定位完成。

**决策**（用户提出，经证据确认）：

| 侧 | 工具面 | 理由 |
|---|---|---|
| 父 agent | **恢复** `tool-bash` / `tool-pwsh`（按平台互补开关）+ `tool-fs-search`（只读搜索）；保留全部 `jiaodui_*` 原生工具 | 这个 preset 存在的意义就是最大限度利用 agent 的操作能力；长尾问题（环境、格式、根因定位）必须有观察通道 |
| 子 agent | **不变**：仍是封闭的 20 项，无 shell、无 `write`/`edit` | 「模型不写报告、只交结构化提案」这条硬约束的落点在这里。子 agent 一旦有 shell/write，就能直接写 `_校对报告.md`，`verify-report` 闸门形同虚设 |

**为什么父侧加 shell 不削弱该约束**：父侧本来就挂 `tool-fs`（含写入类工具），也就是说它今天已经能写文件；缺 shell 只是阻断了**观察与组合操作**，并没有阻止改文件。约束真正依赖的是闸门（`verify-report` / 父复核 / `build-docx` 复核当前状态），而不是「父 agent 少一把 shell」。

**顺带发现的自相矛盾**：`SKILL.md` 第 33 行本来就写着「经 bash 调用写入命令（convert / split / slice 非 preview / parse-report / build-report / build-docx / repair-report --apply）必须传 `--work-root <W>`」——这是旧主链留下的措辞，在「无 shell」的预设下是**死文本**。恢复 shell 后它重新生效，也说明原设计里的能力清单与 skill 文本本身就不自洽。

**配套加固（防两条线混用）**：手册新增「shell 与原生工具的边界」一节——确定性操作一律走原生工具；shell 只用于观察与修复；**禁止在 shell 里用 `python -m jiaodui`**（editable 查找器排在 `PathFinder` 之后，cwd 决定导入哪条线的 core，实测会话工作区是主仓时会读到主仓那份 `jiaodui`）；确需调 CLI 用控制台脚本并传对 `--work-root`。preset 头部注释同步写明分层与这条禁忌。

**测试**（红→绿）：`tests/test_dsh_plugin_package.py` 的父侧断言由「不得启用 `tool-bash`/`tool-pwsh`/`tool-fs-search`」改为「必须启用 + bash/pwsh 平台互补 + fs-search 启用」；**子侧断言保持不变**（`assert not child_tools & {"jiaodui", "write", "edit", "bash", …}`）——即"父开子不开"这件事被同时钉住，将来任一侧被误改都会红。

**文档同步**：`P2-ACCEPTANCE.md` 第 1 条由「不应可见 bash」反转为「应可见 shell 与只读搜索」并记录变更理由；`NEXT-SESSION-BRIEF.md` 同步为「父有 shell、子没有」+ 禁用 `python -m jiaodui` 的告诫。

口径：双口径 **1112 passed / 0 failed / 5 skipped / 4 subtests**（本批改断言与文档，未新增用例数）。

## P6 修复：含锚点的 pipe table → grid table（已完成）

**修法**：新增 `_gridify_marked_tables(text)`，在**锚点注入之后**（`_textify_skipped_formulas` 之后）把**含锚点 raw 的 pipe table 整块重排为 grid table**。

- 为什么放在注入之后：注入前单元格文字还没定型（列宽算不准），而 grid table 的 `+---+` 边框必须与 `|` 精确对齐。
- 为什么只重排含锚点的块：没有锚点的表格逐字保留 ⇒ 零爆半径，既有 Word 版式不变。
- 锚点落在哪：行首锚点并入第一个单元格、行尾锚点并入最后一个单元格、单元格内锚点留在本格 —— 这样「标记字段是一整行长」时，锚点跨单元格成立（pandoc 在 grid table 里保留 openxml raw）。
- 加了一条守卫：块的相邻行是 grid 边框时**跳过**。因为 `_convert_multiline_tables` 在注入前已把 multiline table 转成 grid table，若 marker 落在那类表里，二次重排会把边框留在外面、把表格拆坏。

**先红后绿**：`tests/test_docx_report.py::test_build_docx_keeps_table_and_anchor_when_marker_spans_a_row` —— 修复前 `marker_count=1, anchor_count=0, missing_count=1`（复现真机的 `docx_incomplete`），修复后通过。另加定向单测 `test_gridify_marked_tables_only_rewrites_tables_with_anchors`，锁「无锚点表格逐字保留」与「已是 grid table 不二次重排」两条。

**真机验收（用失败的那份材料）**：`校对/P6转义边界合成/units/P6转义边界合成` 重跑 `build-docx` → exit 0，`marker_count=2, anchor_count=2, missing_count=0, anchor_structure_ok=true`，交付 `校对Word/P6转义边界合成_校对批注版.docx`（`.failed.docx` 按契约保留）。docx 内 `w:tbl` 1 个、`commentRangeStart` 2 个；可见文本由修复前的 `t/s0.1y/cm40`（单元格丢失）变为 `t/s0.10.20.3y/cm40-4`（两行四列全在）。

口径：双口径均 **1114 passed / 0 failed / 5 skipped / 4 subtests**（1114+5=1119=collect）。

## 安全复核

发现并修复：父复核CLI参数接线错误；旧parse会丢proposal并绕复核；同hash退回未撤销接受；Word按首次报告标题切段吞标记；移除fs会丢read_image。通用兼容修复由独立工作树处理，不要求合并实验审查功能才能使用main。

## 隔离回放

在仓库工作区中新建第4/5讲完整材料名加“流程改造回放-20261009”，写入前核对两目录不存在。旧EasyUse材料只读源文件副本作输入，不读旧报告、不修改原稿/旧记录。第4讲拆11单元、图片10；第5讲拆12单元、图片14，缺失均0。

本会话首次真实视觉探针通过，实际read_image观察与参考一致。回放在开发会话中使用CLI/core退路，不是新校对preset安装验收。关键单元由路径/ID派干净子agent；主agent不逐单元读取源文，最终只通读汇总报告。

关键7单元回放结果：5个技术提交通过（不是最终父审完成），2个失败（第4讲练9calc证据绑定不匹配；第5讲练1图片证据结构/调用格式失败），完整错误和摘要保留在契约失败文件。其余16单元未开始，整份complete=false。父代理已通读两份汇总报告并将第4讲练5的g/悬点、第4讲练8传播方向语义按hash定向退回（每单元已消费1轮复核预算）；不能为凑Word或既有标记数刷新失败预算、伪造全部通过。3份证据超长行在报告展示修复预算内分行登记新revision；第5讲练3的该类额度已满，未继续变更，其余原报告保留。

## 未完成与交付限制

- **本分支侧任务已全部收口**：P3（ADR 0006 无损转义与信封契约）、P4（父侧强类型工具）、P5a/b/c（错误码→类别映射、心跳与超时判据、并发登记与滑窗判据）、P6（两个失败单元根因与回归、Word-v2 端到端与整卷 `complete` 三态、含锚点 pipe table→grid table 的 Word 修复）、P2（八条真机验收全绿 + wheel/pipx 安装路径验收）均有批次记录与口径。**未做的是「并入 main」本身**，其计划见 [`UNIFY-PLAN.md`](UNIFY-PLAN.md)：先让分支吸收 main 的 4 项优点（纯策略模块、`attempt_id` 幂等、连带扣费、旧清单迁移），再在集成分支上按类裁决 25 处冲突落地。
- 整份回放必须所有必需单元技术通过、父复核当前版本且Word结构/图片/批注记账通过才可交付；有未开始、失败或unreviewed时只交诊断，不生成冒充完整的Word。
- 不渲染最终Word、不检查分页截图、不提供视觉免责声明；仍保留题图真实读取和首次探针。

## P2 真机验收 + P6 最小真实校对（校对 preset 新会话，已完成，含一处失败发现）

会话设置与 `docs/NEXT-SESSION-BRIEF.md` 一致：preset = 校对，工作区 `JiaoDuiAgentSkill`，插件 CLI 走 worktree 包。两份材料的本轮执行模式由用户确认后写入 `automatic`（`origin=user`）；夹具轮次 `12e3e268`，P6 合成材料轮次 `2faec0a5`。

### P2 八条验收

| # | 验收项 | 结论 | 证据 |
|---|---|---|---|
| 1 | 父 catalog | ✅ | 可见 `jiaodui_task_prepare` / `jiaodui_delivery` / `jiaodui_unit_progress` / `jiaodui_dispatch_plan` / 通用 `jiaodui`；**无** `bash` |
| 2 | 子 catalog = 20 项 | ✅ | 派干净子 agent 点清：`skill`+`read`+`read_image`、6 个 `jiaodui_unit_*`（snapshot/read/locate/submit/event/recovery）、12 个 `jiaodui_calc_*`；`bash`/`pwsh`/`shell`/`write`/`edit`/`fs_search`/`jiaodui_dispatch_plan`/`jiaodui_delivery`/`jiaodui_task_prepare`/`jiaodui_unit_progress`/`jiaodui_unit_review` 逐项确认**不存在** |
| 3 | skill 挂载 | ✅ | 加载到 worktree 包 `skills/jiaodui/SKILL.md`（89 行、描述含「其余 6 科 M5 待落地」）；主仓同名文件为 76 行且描述不同（「当前只落地高中物理」），两者可判别，证明挂的是分支那份 |
| 4 | `read_image` 实读 | ✅ | 实读随包 `assets/vision-probe.png`（480×480，sha256 `4595529…`）一次成功；观察与参考一致：**红苹果 + 棕色果柄 + 绿叶 + 底部 3 个等距蓝点，无文字** |
| 5 | 零 shell 真实校对 | ✅ | 两个单元全程原生工具完成 读取→读图→calc 验算→`unit-submit`→登记；父代理只用 `dispatch_plan` / `unit_progress` / `unit_review` / `delivery`。**子 agent 中途无法解压 docx** 反证了它确实没有 shell/代码通道 |
| 6 | 停止语义 | ✅ | `interrupt_agent` 中性返回（只回报「interrupt requested」，不猜来源）；父代理用 `jiaodui_unit_event --cancel-initiator parent --cancel-reason superseded` 显式登记，`unit_progress` 回报 `cancelled{initiator:parent,reason:superseded}`、`in_flight=false` |
| 7 | CLI 判别器 | ✅ | `dispatch-plan --task-id <夹具task>` 返回 `ok=true, dispatch=['单元3','单元4','单元5']`，与记录逐项一致（主仓 CLI 无此子命令，证明跑的是分支 core） |
| 8 | `check-env` 噪音 | ✅ | 本次**未复现** matplotlib 缓存告警（matplotlib 已安装且 `matplotlib_available()=true`）；8 条前置全绿 |

补充：`build-report` 正确区分三态——夹具材料 `complete=false` 且 `deliverable=false`（单元4/5 记 `failed`「无校对报告」，单元1/2 记 `unreviewed`「结构化建议尚无当前版本的父代理复核」），P6 材料 `complete=true, deliverable=true`。

### P6 两个单元的真实结果（各跑一次，未扩大范围）

| 类型 | 材料 / 单元 | 结果 | 说明 |
|---|---|---|---|
| 图片证据型 | 夹具 `第 6 讲校对测试-分支性能测试` / `单元3` | ✅ `registered` + `verified`，父复核 `accepted`（`current=true`） | 报告 `4f1cbc58…`、数据 `81307399…`；`marker_count=1`。**真实读图成功**：读的白底副本（594×271 透明底线稿），识别出纵轴 y/mm、±0.4 刻度、横轴 x/(×10⁻²mm) 刻度 7/14/21/28/35、波谷−0.4→波峰+0.4→次波谷 λ=14×10⁻²mm，M 在平衡位置波前、N 在未扰动段，判「图文与解析一致」。6 条 calc 实算全部相符 |
| 转义边界型 | `P6转义边界合成` / `第1题` | ✅ `registered` + `verified`，父复核 `accepted`（`current=true`） | 报告 `cce9e125…`、数据 `983d55ea…`；`marker_count=2`。6 条 calc（含 1 条 `dimensional` 返回对象）+ 1 条严重错误 |

两条真实发现均为内容问题，非转换差异：单元3 的解析 C 项结束引号误用**左引号**（`不能“随波逐流“` → `”`）；第1题的数据表三时刻与题干 `T=0.5 s` 冲突（按 `y=A sin(2πt/T)` 反解表观周期 0.4 s，取表得 λ=1.6 m 无对应选项）+ 第2问引用的【注】在源文中不存在。

### ADR 0006 转义无损：报告侧与数据侧已实测通过

父代理亲自核对（不依赖子 agent 自述）：

- 源文真身 `raw/P6转义边界合成_raw.md` 里 `|` 与 `【注】` 都是**裸字符，无反斜杠**；
- 报告 `_校对报告.md` 与整卷报告里，标记原文字段的表格竖线写成 `\|`、方括号写成 `\【` / `\】`（`【1|\| t/s \| 0.1 \| 0.2 \| 0.3 \||…】`、`【2|解释\【注\】中的约定|…】`），而表格分隔行的 `|---|` 保持字面竖线 —— 即**只有标记字段内被转义，正文没有被误转义**；
- `_校对数据.json` 的 `corrections[].original` 是**反转义后的真字面**（`| t/s | 0.1 | 0.2 | 0.3 |`、`解释【注】中的约定`），而同一文件的 `marked_text` 保持带转义的报告字面 —— 正好符合 operation-manual §「`marked_text` 保持报告字面（带转义），`corrections` 是反转义后的内容」；
- 子 agent 全程未收到任何 `syntax.*` / `integrity.*` / `original.*` / `locate.*` 转义相关错误，证明写入侧不再硬拒绝竖线与标记括号（P3 的目标达成）。

### ⚠️ 未通过项：P6 材料的 `build-docx` 判 `missing_count=1`，未交付

这是本轮唯一失败发现，且**是闸门正确拒绝交付**，不是静默失败：

- P6 材料 `build-docx` exit 6 `docx_incomplete`：`marker_count=2, anchor_count=1, formula_fallback_count=0, missing_count=1`，stderr 明确报「批注 1 锚点不完整（缺 commentRangeStart/End/Reference），已移除残引用并从批注部件剔除」，产物按契约另存为 `校对Word/P6转义边界合成_校对批注版.failed.docx`，**未进交付路径**（`out_path=null`）。
- **已排除「生成器整体坏了」**：同一套代码对夹具材料 `build-docx` 得到 `marker_count=1, anchor_count=1, missing_count=0, anchor_structure_ok=true`（该次退出非 0 只因 单元4/5 无报告、单元1/2 未复核被正当排除）。所以锚点生成、注入、配对校验链路本身正常。
- **失败点收窄到「标记落在表格行内」这一条件**：第1题标记 1 的**原文字段本身就是一条表格行**（`\| t/s \| 0.1 \| 0.2 \| 0.3 \|`），替换文本也是表格行；标记 2 在普通段落里（也丢了锚点，两者共同点是字段内含被转义的 `\|` / `\【`）。夹具 单元3 的唯一标记是普通正文里的引号，锚点正常。
- **根因未能定位到行**：`_strip_unanchored_comments` 只在 pandoc 已把 openxml raw 丢掉/吃掉之后才看到残缺，要判断到底是「pandoc 在表格单元格里丢弃 `{=openxml}` raw」还是「转义反斜杠使 raw 被吞进数学/文本」，必须直接看生成中间态的 `word/document.xml`。
- **能力缺口（需下一会话补）**：校对 preset 无 shell，且插件未暴露任何「读 docx 内部 XML / 跑代码」的工具，父代理**无法解压 docx**；实测 `read` 对 docx 直接报 `binary file`，子 agent catalog 里也没有任何可执行通道（20 项逐条确认）。因此本条属「已复现、已定位到条件、根因待 raw XML 复核」，不是未执行。
- 建议的下一步：在 standard preset（有 shell/python）里对该 `.failed.docx` 与夹具那次成功的 docx 各解出 `word/document.xml`，对比标记 1/标记 2 位置的 `commentRangeStart` 是否存在、`{=openxml}` 是否变成可见文本；若确认是 pandoc 在表格单元格丢弃 raw，则表格行内的标记需要走 `_convert_multiline_tables` 同款「先转 grid table 再注入」的兜底。

#### 根因已复核（standard preset 有 shell，2026-10-09 晚）

**现象**：`.failed.docx` 解出的可见文本是 `…已知数据表：t/s0.1y/cm40说明「…` —— 表格**塌了**：`0.2`/`0.3` 与 `0`/`-4` 整段丢失，`|---|---|---|` 分隔行消失，`commentRangeStart/End/Reference` 各只有 **1** 个（即 2 个标记只锚住 1 个）。

**根因**：标记 1 的字段本身就是一整条 pipe table 行（`\| t/s \| 0.1 \| 0.2 \| 0.3 \|`）。锚点注入把该行变成
`` `<w:commentRangeStart/>`{=openxml} + 原文 + `<w:commentRangeEnd/>…`{=openxml} ``，
行首的 `|` 不再是行首字符 ⇒ **表格丢了表头行**，只剩孤立的分隔行与后面的 `| y/cm | … |` ⇒ pandoc 塌表/丢单元格（在列表项缩进内尤其明显），该标记的 openxml 也随之丢失 ⇒ `missing_count=1` ⇒ 闸门按契约拒绝交付。**报告侧（verify）通过、Word 侧不可交付**是这次的准确状态，不是静默失败。

**最小复现（`/tmp/tablex`，三层对照）**：

| 形态 | `commentRangeStart` | `w:tbl` | 可见文本 |
|---|---|---|---|
| 现状：pipe table + 注入（无表头） | 1 | **0** | 竖线全部当文本渲染，表格完全没生成 |
| grid table，锚点在同一单元格内 | 1 | 1 | 单元格齐全 |
| **grid table，锚点跨单元格（1→4）** | **1（End/Reference 也各 1）** | **1** | `t/s \| 0.1 \| 0.2 \| 0.3`、`y/cm40-4` 全部保留 |

⇒ **修复方向已验证**：把报告正文里的 pipe table 在注入前转成 grid table，锚点（含跨单元格）与表格结构都能保住。代码里 `_convert_multiline_tables`（`docx_report.py:806`）的注释早就写明了同一类根因——"pandoc 的 multiline table 单元格会丢弃 openxml raw；grid table 正常"——只是当时的兜底**只覆盖 multiline table，没覆盖 pipe table**，而 v2 报告正文是「原始源文逐字」，源文里出现 pipe table 时就会踩到。

**这条同时构成「preset 该不该给父 agent shell」的直接证据**：上一会话已复现、已收窄到条件，却因为没有 shell、也没有任何能读 docx 内部 XML 的工具而无法完成根因定位，只能交接；本轮在有 shell 的会话里，解 XML + 三层最小对照一次做完。

### 本轮未能验收 / 未执行（明确留痕）

- **Word 侧反转义字面未被实测确认**：简报要求确认「Word/交付侧是反转义后的字面」，但 P6 材料的 Word 未生成、夹具那次只有 单元3 的引号标记（不含 `\|`），且如上无工具可读 docx 内部 XML。因此该条**只验证了报告侧与数据侧，Word 侧未验证**——不能按 `test_docx_report.py` 的单元测试结论冒充真机通过。
- 夹具 `单元1` / `单元2` 是上一轮遗留的 `registered` 未复核状态，本轮**未动**（按简报「不要动回放材料既有留痕」）；它们被 `build-docx` 以「尚无当前版本的父代理复核」正当排除。
- 双口径测试数字未产出：本 preset 无 shell，无法跑 `pytest`。本次为纯宿主侧验收，**未改 `jiaodui/` 代码**，测试口径应与上一批一致（1112 passed / 0 failed / 5 skipped / 4 subtests），但需在 standard preset 复核确认。
- 未提交、未 push（简报禁止 push）。`docs/PROCESS_REWORK.md` 的本节由本会话写入，提交信息需另行补。

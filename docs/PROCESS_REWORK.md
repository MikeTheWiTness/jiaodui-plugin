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

## B1：策略机制抽成纯模块 + 采纳 main 的连带扣费（UNIFY-PLAN Phase 1 第 1 批）

**做什么**：把分支内嵌在 `material.py` 的授权/预算/扣费机制搬进纯模块，并采纳 main 的两条更优语义。

- 新增 `jiaodui/execution_policy.py`：**纯机制（无 IO、无 json）**，含 `CATEGORIES` / `BUDGETS` / `MODES` / `ORIGINS` 与 `charges()` / `charge()` / `new_policy()` / `is_current_policy()` / `validate_fingerprint()`。
- `error_classification.py` 改为从纯模块**重导出**类别与额度：分支里原先的第二份定义已删除，类别与额度现在只有一处（模块内自检 `open(`/`json.load`/`Path(`/`subprocess` 命中 0）。
- `material.py` 的**策略引用清零**：构造、校验、指纹校验、扣费全部委托纯模块；`record_recovery_attempt` 只剩取锁、读盘、记账与落盘。
- 语义变更（采纳 main `_charges`）：**`image_schema_fix` 连带扣一次 `call_correction`**（图片格式修复本身占一次调用）；先判全部被扣类别的余额，**任一不足即整次拒绝、不做部分扣费**；成功返回 `charged`，被拒返回 `blocked_category`；`recovery_events` 同时记这两个字段。连带扣只记成本、不记失败指纹。

**先红后绿**：`tests/test_execution_policy.py` 新增 3 例——连带扣生效（两类各 +1、指纹只记主类别）、`call_correction` 用满后图片修复被拒且 `image_schema_fix` 仍为 0、纯模块无 IO 且类别/额度单源。修复前 3 例全红。

**真机冒烟**（`/tmp` 临时材料，单次调用逐步）：① `images.missing` → `charged=['image_schema_fix','call_correction']`、`used=1/2`；② `usage` → `call_correction` `2/2`；③ 再用 `images.missing` → 被拒 `blocked_category=call_correction`、`remaining=0`、`retryable=false`；④ 记账 `{image_schema_fix:1, call_correction:2}`（无超扣、无部分扣费）；⑤ 事件带 `charged` 与 `blocked_category`。

> 冒烟脚本第一版把 CLI 调用写在字典推导里，导致"每个键调用一次"、数字虚高（`used=2` 而实际只该 1）。已改为单次调用复测；记在此处以便复查同类脚本。

**文档**：`operation-manual.md` 的「恢复与事件」补上连带扣费与`blocked_category`语义，两份副本一致。

**口径**：双口径均 **1117 passed / 0 failed / 5 skipped / 4 subtests**（B1 前 1114，+3 例）。

**边界**：`validate_attempt`（B3 的 `attempt_id` 幂等）与 `migrate_legacy_spent`（B2 的旧清单迁移）**不在本批引入**，避免留下无调用方的死代码；它们各自在对应批次连同测试一起加。

## B2：旧清单兼容——可读、未授权、重授权时按单元保守迁移（UNIFY-PLAN Phase 1 第 2 批）

**缺口**：分支原先要求 `execution_policy.budgets` **精确等于**当前六类额度，于是 main 时期的旧聚合策略会被判成 `invalid-manifest`——**连清单都打不开**，升级无从谈起。main 的做法是「可读但未授权」+ 重授权时保守迁移。

**改法**：

- 纯模块 `execution_policy.py` 新增 `LEGACY_BUDGETS`、`is_readable_policy()`、`migrate_legacy_spent()`。迁移映射照 main：`entry_question` 丢弃（它不是恢复额度）、`image_schema_fix` 由旧 `call_correction` 推（旧版把图像 schema 修正记在 call_correction）、`technical_redispatch` 取 `max(unit_recovery, technical_retry)`、每项 `min` 到当前额度、只返回非零项。
- `_validate_execution_policy` 的读盘门放宽为「**可读**」；新增 `material.require_current_policy(run, data)` 统一判定**授权**，并把 `record_recovery_attempt` / `record_calc_call` / `unit_delivery.submit` 三处 `policy is None` 改为调用它——旧策略、失效策略因此都**不再授权本轮工作**（这正是 main 那句「readable but not authorized」）。
- `set_execution_policy`：遇到非当前策略（含旧聚合）→ 把旧聚合 `spent` 迁移到各单元账本、再安装新策略，并在轮次 action 里记 `migrated_legacy_spent`，便于审计。

**先红后绿**：新增 `tests/test_policy_legacy_compat.py` 两例（缺策略：可读、操作被拒、重授权后可用；旧聚合：可读、仍不授权、迁移到各单元且**计数计入额度**）。修复前第二例因 `invalid-manifest` 直接失败。

**真机验收**：

- 工作区 6 份旧清单（`第 6 讲校对测试`、`-流程测试`、`-独立续测-02`、`-独立续测-03`、`_独立流程测试`、`_独立流程测试_重跑`）**全部可读、不再报 invalid-manifest**；它们属于更早形态（无 `task_id`/`unit_ids`），所以单元级迁移改用带 5 单元的真实材料**副本**（`/tmp`，原物未动）验证。
- 副本上：旧聚合策略①可读 →② `record_recovery_attempt` 被拒 `execution-policy-required` →③ `set_execution_policy("interactive")` 后各单元账本为 `{call_correction:1, calc_representation:1, report_repair:2, technical_redispatch:1, image_schema_fix:1}`，action 记录迁移类别 →④ 迁移计数**计入额度**（call_correction 已用 1，再记一次变 `used=2/remaining=0`，第三次被拒 `blocked_category=call_correction`）。

**口径**：双口径均 **1119 passed / 0 failed / 5 skipped / 4 subtests**（B2 前 1117，+2 例）。

## B1/B2 复查：发现的遗留坑（对抗性复核，未改行为，只加守卫与计划）

对 B1/B2 做了一次对抗性复核（代码、契约、文档、合并面四项），结论如下。

### 已修

1. **静态检查**：`ruff`（仓库 `pyproject.toml` 已配置，但两个 venv 都没装）装上后跑改动文件，**只有 `error_classification.py` 的两处 F401 是本批引入的**（重导出导入"未使用"），已加显式 `__all__`；另外 5 处（`material.py` 导入顺序、`units.scan_unit_dirs` 未用、2× `datetime.UTC`、`test_execution_policy.py` 导入顺序）在 B1 之前就存在——`material.py` 正是冲突文件，**故意不动**以免扩大合并面。
2. **插件类别 enum 漂移守卫**（B1 遗留）：插件 JS 无法 import Python，`jiaodui_unit_recovery` 的 `category` enum 是第二处类别表。已在 Node 行为测试里断言它逐项等于 core 的 `CATEGORIES`（期望值由 Python 单一源经 argv 注入）。**并做了反向对照**：把 enum 改坏 → 测试红；还原 → 绿，确认守卫不是空转。

### 未改、但要进合并裁决的坑（已写进 `UNIFY-PLAN.md` §6.1/6.2/6.3）

3. **静默应用的 main 变更 19 个文件**（分支没碰、main 改了、不在冲突清单 → git 直接采用 main 版本）。其中 4 处是**整份删除分支依赖的模块**，naive 合并后分支核心直接 ImportError：
   - `jiaodui/source_index.py`（−132，被 `report_suggestions.py`/`cli.py` import）
   - `jiaodui/unit_reader.py`（−55，被 `cli.py` import）
   - `jiaodui/calc/schema.py`（−41，被 `cli.py` 的 `calc-schema` import）
   - `packages/dsh-jiaodui/tools/calc-schemas.json`（−391）
   以及 `jiaodui/report_repair.py` 的 v2 守门被删（−5）→ 分支契约静默失效；4 个测试文件被删 → 覆盖静默消失。
4. **`workflow.py` 自动合并但语义重复**：main 在该文件新增 `set_execution_policy`/`record_unit_event` 两个入口（写 main 的 `policy["spent"]` 形态），与分支 `material.py` 的同名入口（v2 清单形态）**并存且不兼容**；`workflow.py` 不在冲突清单里，必须显式删除或改成委托。
5. **实测预判的"合并即红"**：把 main 版 `tests/test_skill_docs.py` 直接跑在分支 skill 上 → `test_repair_preview_is_documented_as_explicit_gate_auxiliary` 失败（断言 SKILL.md 里出现 `jiaodui repair-report`）。另有 main 新增的 `test_execution_compat.py`/`test_main_policy_contract.py`（+208/+234）不在冲突清单里，会静默进入结果并按 main 语义断言。
6. **冲突面本身也变了**：B1/B2 之后重算为 **28 处**（19 content + 7 modify/delete + 2 add/add）；新增的两处 add/add 是 `jiaodui/execution_policy.py` 与 `tests/test_policy_legacy_compat.py`；测试冲突文件是 8 个而非计划原写的 6 个。已在计划里更正。

### 顺带回应的两个自查点

- `unit_delivery._current` 里 `material.require_current_policy()` 的位置正确（在身份校验之后、读源文之前），三处授权检查已无遗漏（`grep 'execution_policy") is None'` 为空）。
- `recovery_events` 没有任何核心消费者（仅一处并发测试断言其为空），事件新增 `charged`/`blocked_category` 不构成契约破坏；`is_readable_policy` 的严格度与 main 的 `validate_policy` + 读盘门一致（预算漂移同样判在载入期，缺策略/旧聚合同样可读）。

**遗留（明确记录，非本批范围）**：迁移过来的旧计数**没有指纹**，因此对迁移前那部分额度，同一指纹重复记账不会被幂等挡住——这是旧数据本身缺信息，无法在迁移时凭空补出；B3 引入 `attempt_id` 后会按 attempt 维度解决。

口径：双口径 **1119 passed / 0 failed / 5 skipped / 4 subtests**（本批未改行为，新增 1 条 enum 守卫断言在既有用例内）。

## B3：恢复记账的 attempt_id 幂等契约（UNIFY-PLAN Phase 1 第 3 批）

**契约**（按已批准的决策 2）：

```
unit-recovery --task-id T --unit-id U --attempt-id A --fingerprint F
              [--error-code CODE | --category targeted_review] [--expected-run-id R]
```

**语义**：

| 情形 | 行为 |
|---|---|
| 同 attempt + 同指纹 + 同类别 | **幂等重放**：不再扣费，返回原结果并带 `idempotent=true`；事件忠实记录原结论并带 `replay=true` |
| 同 attempt + 不同指纹，或同 attempt 但映射到不同类别 | `attempt-id-conflict`（错误码与 main 对齐） |
| 同指纹 + 新 attempt | 正常再扣（到额度为止）；指纹只标识「同一失败」，不承担幂等 |
| `--expected-run-id` 与当前轮次不一致 | `run-changed`（CAS 防护，采纳 main） |
| `attempt_id` 空/超 200 字符/非字符串 | `invalid-attempt-id` |
| 被拒的 attempt | 也记账：重放返回同一否决结论（不会因重放变成允许） |

**为什么另建索引而不是照搬 main**：main 把恢复本身做成 unit_event，「同 attempt 不重复」免费来自事件账本里 attempt_id 的唯一性；分支的心跳事件账本与预算账本分家（心跳是 `unit_events[unit]` 的 phase 列表），所以新增 run 级 `recovery_attempts[unit][attempt_id]` 索引。**故意不**强制「必须先有同 attempt 的 unit-event」——实测有材料只记预算不记心跳，加这个约束会破坏既有流程；改为在手册里约定「`--attempt-id` 须与该单元 `unit-event` 登记的一致」，两者可按 attempt_id 关联。

**改动面（四处必须同时改，否则契约不一致）**：core（`material.record_recovery_attempt` 签名 + 幂等流程）、纯模块（`validate_attempt()` main 同形状 + `attempt_decision()` 重放/冲突判定）、CLI（`--attempt-id` 必填、`--expected-run-id` 可选）、插件（schema `required` 从 3 项变 4 项 + argv）、手册两份副本 + 工具顶层描述、Node 行为测试。

**先红后绿**：新增 `tests/test_recovery_attempt_idempotency.py` 7 例（幂等重放不重复扣、换指纹冲突、换类别冲突、同指纹换 attempt 再扣、CAS 防护、非法 attempt_id、被拒 attempt 的重放）——实现前 7 例全红。**22 个既有调用点**全部补 `attempt_id`；其中并发压测必须每线程用不同 attempt，否则会退化成重放（单独核对过）。

**真机冒烟 8 步**（每步单独一次调用，避免上次那种"字典推导里重复调用"的假数据）：① 缺 `--attempt-id` → exit 2 `usage`；② 首次 `usage` → `used=1/2`；③ 同 attempt 重放 → `idempotent=true` 且仍 `1/2`；④ 换指纹 → exit 6 `attempt-id-conflict`；⑤ `--expected-run-id` 不匹配 → exit 6 `run-changed`；⑥ 匹配轮次 + 新 attempt 同指纹 → 再扣到 `2/2`；⑦ 第三次 → 被拒 `blocked_category=call_correction`；⑧ 账本 `{call_correction: 2}`、attempt 索引 3 条（a1/a2 允许、a3 拒绝）、事件 4 条（含 1 条 `replay`）。

**自查修正**：我最初写的断言「allowed 事件数 == 1」是错的——重放事件忠实记录原结论，`allowed` 会沿用，所以断言改为「排除 `replay` 的授权记账 == 1」，而「额度不被重复扣」由账本断言单独把关。这是测试预期的问题，不是实现的问题。

**静态检查**：基线 11 处 → 现在 11 处，**本批零新增**；`material.py`/`cli.py` 的既有问题故意不动（它们是 Phase 2 的冲突文件，避免扩大合并面）。

**口径**：双口径均 **1126 passed / 0 failed / 5 skipped / 4 subtests**（B3 前 1119，+7 例）。

## B4：文档归位（UNIFY-PLAN Phase 1 第 4 批，验证批）

结论：**无需改动**。逐项核查如下（Phase 1 至此完成）。

| 核查项 | 结果 |
|---|---|
| main 独有文档是否会在合并后保留 | `docs/PLAN-rework-continuation.md`、`docs/M0.md` 只在 main；分支没有 → 合并不会删，无需搬运 |
| 「旧主链 = 只读兼容」是否写清 | 手册「只读与计算」：历史 Markdown 报告兼容读取（`verify-report` / `parse-report`），仅旧报告可用完整性辅助；SKILL 第 33 行：历史写入须显式 `--legacy-layout` 且仍限工作区内 |
| 这条边界是否**有代码强制** | 有两条：① `report_repair.py` 对 v2 报告返回 `repair.v2-not-supported`（测试 `test_report_suggestions.py:133` 锁定）；② 旧布局必须显式 `--legacy-layout`（`cli.py`/`report.py`/`docx_report.py`/`material.py`/`workflow.py` 均按此开关分支） |
| 入口预算与链接回归 | SKILL.md 8164 码点 < 8192；两份副本逐字节一致；`test_skill_docs.py` + `test_dsh_plugin_package.py` 34 例绿 |

因此 B4 只留下"合并不删 main 独有文档"这一条，已作为 Phase 2 的裁决规则（§6 表末行）。

**Phase 1 状态**：B1 ✅（纯策略模块 + 连带扣费）、B2 ✅（旧清单可读/未授权/保守迁移）、B3 ✅（`attempt_id` 幂等）、B4 ✅（文档归位验证）。分支口径 **1126 passed / 0 failed / 5 skipped / 4 subtests**（双口径）。
下一步是 Phase 2：从 main 建 `integration/structured-into-main`，按 §6 + §6.1 裁决 28 处冲突与 19 处静默变更，裁决后立刻跑全量并做真机冒烟。

## Phase 2 合并中采纳 main 的两处更优语义（在分支上实现）

合并试跑后发现 main 有两条语义比分支好，按「保留 main 更优的地方」的目标**在分支上实现**（分支是开发线），再拉进合并树。

**① `BuildReportResult.to_dict()` 暴露 `ok`**

- main 有 `ok`（`out_path is not None`），分支只有 CLI 补；契约（AGENTS）把 `ok` 定义为对外字段（"ok 仅表示诊断文件已生成"）→ 补进 dataclass。
- 同时**保留分支更严谨的 `complete`**：分支按「所有必需单元通过或显式跳过」计算并考虑 `unreviewed`，main 的 `not self.failed` 是粗近似（会漏掉"已提交但未父复核"的单元）。
- 红→绿：新增 `test_build_report_payload_exposes_ok_independently_of_complete`（断言 `ok=True` 而 `complete=False`，锁两者解耦）。

**② `unit-event` 的轮次 CAS**

- main 的 `record_unit_event` 有 `expected_run_id`，能防「迟到的阶段事件写进新轮次」；分支没有这个防护（直接 append 到 `runs[-1]`）→ 采纳为**可选**参数（不破坏既有调用）。
- 四处同步：core（`material.record_unit_event` 加 CAS）、CLI（`unit-event --expected-run-id`）、插件 schema/argv（`jiaodui_unit_event` 增属性）、手册两份副本；Node 行为测试加断言（属性存在 + argv 顺序）。
- 红→绿：新增 `test_unit_event_rejects_late_event_from_previous_run`（旧轮次 id → `run-changed` 且**不落盘**；新轮次 id → 正常记录）。

**口径**：分支双口径 **1128 passed / 0 failed / 5 skipped / 4 subtests**（本批 +2 例）。

## Phase 2 合并中采纳 main 的另外两处更优语义（在分支上实现）

**③ `unit-event` 要求当前执行授权**

- main 的 `record_unit_event` 经 `_require_execution_policy` 要求当前策略；分支的心跳不要求 → 「没有授权就不留下工作痕迹」在分支里没有确定性落点 → 采纳（顺序与 main 一致：先判轮次 CAS，再判授权）。
- 影响面先查过：分支所有 `record_unit_event` 调用点的 helper 都已先设执行模式，故无回归。
- 红→绿：新增 `test_unit_event_requires_execution_policy`（无策略 → `execution-policy-required` 且**不落盘**）。

**④ 指纹非法用更具体的错误码**

- main 用 `invalid-attempt-fingerprint`，分支是笼统的 `recovery-invalid` → 采纳 main（更能指认问题）。未知**类别**仍是 `recovery-invalid`（既有断言不变）。
- 红→绿：新增 `test_fingerprint_error_code_is_specific`（5 种非法形态 + attempt_id 仍为 `invalid-attempt-id`）。

两处均在面板同步：CLI/插件 schema 无需改（无新参数），手册两份副本补「unit-event 要求已确认执行模式」与「指纹非法返回 `invalid-attempt-fingerprint`」。

**口径**：分支双口径 **1130 passed / 0 failed / 5 skipped / 4 subtests**（本批 +2 例）。

## Phase 2 合并中采纳 main 的第五处更优语义：幂等重放不写盘（在分支上实现）

映射 main 测试时暴露的分歧：分支的 B3 实现把重放记一条 `replay=true` 事件（**会写盘**），而 main 的幂等是**真·无操作**（字节级不变）。

判断：**采纳 main**。理由是写盘的重放有两个坏处——被反复重试的同一 attempt 会让清单**无界增长**；而重放并不改变任何状态，审计需求已由 attempt 索引与返回值 `idempotent=true` 满足。

- 实现：`record_recovery_attempt` 的重放分支直接返回 `{**原结果, "idempotent": True}`，**不追加事件、不写盘**。
- 红→绿：`test_same_attempt_is_idempotent_and_does_not_charge_again` 增加「重放后清单字节不变」与「事件仍只有原一条、无 replay 标记」两条断言（改前红）。

**口径**：分支双口径 **1130 passed / 0 failed / 5 skipped / 4 subtests**。

## Phase 2 合并中采纳 main 的第六处更优语义：被拒的 attempt 不写盘（在分支上实现）

同一条原理的延续：**不改变状态的操作不该写盘**。分支原先会给被拒的 attempt 记一条记录（并写盘），main 的 `spend()` 抛错时**不改盘**。

判断：**采纳 main**。被拒不改变任何状态，重复判定必然得到同一结论（额度只减不增），因此记录被拒没有收益，反而让反复重试被拒 attempt 的调用撑大清单。

- 实现：`charge()` 返回 `allowed=False` 时直接返回结果，**不记 attempt、不追加事件、不写盘**。
- 影响与同步：`test_denied_attempt_leaves_no_trace_and_repeats_the_same_verdict`（重写：被拒后清单字节不变、attempt 索引无该条、重复同一 attempt_id 是**重新判定**而非幂等重放）；`test_exhausted_call_budget_blocks_image_schema_fix` 的账本读取改为容错（被拒不再产生零状态条目）。

至此 Phase 2 映射中共采纳 main **六处**更优语义：① `report.ok` ② `unit-event` 轮次 CAS ③ `unit-event` 要求授权 ④ 指纹错误码 ⑤ 幂等重放不写盘 ⑥ 被拒不写盘。其中 ⑤⑥ 同源（不改变状态就不写盘），是本轮最实质的两条行为改进。

**口径**：分支双口径 **1130 passed / 0 failed / 5 skipped / 4 subtests**。

## 补漏：`unit-event --expected-run-id` 的 CLI 传参曾无声通过（Phase 2）

采纳 main 的轮次 CAS 时，`material.record_unit_event` 与插件 schema/argv 都改了，但 **`cli.py` 的解析器与传参没落地**（该文件未进那次提交）。它无声通过了三道检查：

- 分支的单测直接调 core API（`material.record_unit_event(..., expected_run_id=…)`），绕过解析器；
- Node 行为测试只验插件拼出的 argv 字符串，**不验 CLI 是否接受这个参数**；
- 全量套件里没有一条端到端走 `python -m jiaodui unit-event --expected-run-id …`。

合并树的 CLI 断言把这条兜住了（`unrecognized arguments: --expected-run-id run-1`）。已补：`cli.py` 加参数并真的传入 `record_unit_event`，并新增端到端用例 `test_cli_unit_event_accepts_and_forwards_expected_run_id`（真子进程：旧轮次 → exit 6 `run-changed`；当前轮次 → exit 0 且载荷 `{ok, event}`）。

**教训**：新增 CLI 参数时，光有 core 单测 + 插件 argv 测试不够，必须有**穿过解析器**的端到端用例。

**口径**：分支双口径 **1131 passed / 0 failed / 5 skipped / 4 subtests**（本批 +1 例）。

## 分支侧的文档口径统一（Phase 2 收尾）

合并树里 main 的 `test_skill_docs.py` 断言 SKILL.md 出现 `jiaodui repair-report`（main 的入口写法带 `jiaodui ` 前缀）。分支 SKILL 写的是 `repair-report --apply`（无前缀），差 7 个码点。

选择**改文档而不是改测试**：把前缀补上（8164 → 8172 码点，仍在 8192 以内），main 的断言原样通过——保留 main 的测试比改写它更稳。

## 合并时核对的 main 线变化（Phase 2）

本分支期间 main 走了另一条线，合并时必须逐项核对（详见 `UNIFY-PLAN.md` §6.1/§6.2）。

| main 的提交/改动 | 内容 | 合并处置 |
|---|---|---|
| `c7fa622` | Revert「structured unit submission pipeline」（正是本分支的基线 `4c82e24`） | 本分支的工作即建立在该提交之上，合并后结构化主链成为正常路径 |
| `dde758d` / `04f0c78` | 旧主链上的执行策略与恢复记录、按单元强制预算 | 语义被 B1/B2/B3 与 Phase 2 六处采纳吸收；main 放在 `workflow.py` 的 `set_execution_policy`/`record_unit_event`/`recover_unit` 与分支 `material.py` 同名入口**形态不兼容**（还依赖分支没有的 `spend()`），合并后**整块去掉**，`workflow.py` 与分支逐字节一致 |
| `c1c24b9` | 中性传播宿主中止调用 | 分支已有等价实现，不冲突 |
| `cc1c21f` | 入口精简至 8192 码点以内并锁长度回归 | 分支独立达成（8172 码点 + 长度/链接回归），取分支版 |
| `e3deab4` | M0—M6 收口计划与 P0/P1 执行记录（`PLAN-rework-continuation.md`、`M0.md`） | 只在 main、合并不删；README 已补计划链接 |
| 静默删除的模块（`source_index.py`/`unit_reader.py`/`calc/schema.py`/`calc-schemas.json`）+ 4 个测试文件 | main 回退时整份删除 | **取回分支版本**（分支 `report_suggestions`/`cli.py` 依赖它们，否则 ImportError） |
| `report_repair.py` 的 v2 守门被删 | main 无 v2 概念 | 取回分支版本（保留 `repair.v2-not-supported`） |
| `tests/test_execution_compat.py`、`tests/test_main_policy_contract.py` | main 新增，锁旧主链语义 | **逐条映射**为结构化语义的等价断言（见下节），形态类断言改到分支 API/CLI 上 |
| `tests/test_skill_docs.py` 重写 | main 版断言 SKILL.md 出现 `jiaodui repair-report` | 改文档而非改测试：SKILL 补 `jiaodui ` 前缀，断言原样通过 |
| `failure-modes.md` / `subject-matrix.md` 重写（两份副本） | main 的版本更完整地写了六类预算、连带扣费、attempt 幂等 | 取 main 版（与合并后语义一致） |

## Phase 3：收尾（2026-10-10，已完成）

| 项 | 动作与证据 |
|---|---|
| main 落地 | `git merge --ff-only integration/structured-into-main` → `main` = `98a7ac8`；根仓树与合并树 `git rev-parse main^{tree}` 均为 `a9251fd…`（**逐字节一致**） |
| 全量口径 | 根仓默认口径与清空 addopts 口径均 **1158 passed / 0 failed / 4 subtests**（worktree 里的 5 条 skip 在根仓转为通过：它们依赖根仓 `.venv` 与随包 skill 的实体） |
| 冻结语料 | `JIAODUI_LEGACY_CORPUS=../JiaoDuiAgent/output` → `tests/test_legacy_corpus.py` **4/4 通过** |
| 真机冒烟 | 用 P6 回放材料（仍在根仓 `校对/`，未随 worktree 删除）：`status` 已完成 1；`build-report` → `ok=true, complete=true`（拼入 1、失败 0）；`build-docx` → **标记 2 = 锚点 2 + 公式兜底 0、缺失 0**；解包 docx 正文含转义后的表格行文字 `t/s0.10.20.3y/cm40-4`，旧的错误形态 `t/s0.1y/cm40` 已不存在 |
| profile | 三处切回仓库根包（`package.json` 链接、`pnpm-lock.yaml`、`node_modules/dsh-jiaodui` 软链），worktree 引用残留 **0/0**；Node `createRequire` 解析包、`skills/jiaodui/SKILL.md`、`.venv/bin/jiaodui` 三处均落到根仓 |
| 环境 | `.venv` 本就是指向已验证独立环境 `.venv-cli` 的软链（AGENTS 允许），editable 安装自动跟踪合并后代码，故**不需要**重建；根仓测试直接用 `.venv-cli/bin/python` 跑通 |
| worktree | 删 `.worktrees/structured-report`（含 255M venv）与 `.worktrees/integration`；`git worktree list` 只剩根仓；`.worktrees` 占用 267M → 148K（剩余为历史遗留的 `host-inspection`） |
| 分支 | 删临时集成分支 `integration/structured-into-main`（与 main 同内容、独有提交 0）；`feature/structured-report-pipeline`（`3f7c734`）**保留为历史标记**，相对 main 独有提交 0 |
| 文档 | `AGENTS.md` 契约段补「正常路径 = 结构化提交」「恢复预算与阶段事件由 core 强制」；`README.md` 状态段改写；`IMPLEMENTATION.md` 加条目 + 更新状态行；`PLAN-rework-continuation.md` 加「已被 UNIFY-PLAN 取代、隔离策略已终结」抬头；`UNIFY-PLAN.md` 标记 Phase 2/3 完成 |
| 未做 | 全程**未 push**（本地领先 `origin/main` 39 个提交）；未重跑 DSH 新会话真机验收（profile 已切回，需用户重启 DSH 后换「校对」preset 会话复验） |

**遗留与提醒**：① `feature/structured-report-pipeline` 分支保留但已完全并入 main，可随时删；② 桌面 profile 指向根包，**下次 DSH 重启后**插件加载的就是合并后的主链（preset 仍是「校对」；`agent-preset-registry` 默认仍是 `standard`，新会话需手动选）；③ `.worktrees/host-inspection` 是更早会话的遗留，与本轮无关。

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

## 回放（第 11/12 讲）三项可确定性修复：诊断与复制就绪清单（2026-10-10）

**材料**：用户提供的会话包 `dsh-session-session-d873f221-…zip`（12 个子 agent：1 个视觉探针完成，3 个被上游代理 `PI_AI_ERROR` 打死，其余 8 个随会话中止被杀）。上游抖动是主因、属宿主/代理层；以下三项是回放里能落到本仓的真问题——**只加诊断与只读输出，不改契约、不放宽任何闸门**。

| # | 现象（回放证据） | 修复 | 回归测试 |
|---|---|---|---|
| 1 | 12 讲单元3 提交被拒 `proposal.calc-call-mismatch`：模型把 equality 的 `expression_a`/`expression_b` 拼成 `'2*2 == 2*4 + (-2)*2'`；原报错只说「不逐字一致」并截断 params，模型无从机械修正 | `report_suggestions._calc_expression_mismatch`：列出该调用**每个可逐字填写的参数取值**（`字段='值'`），排除 task_id / unit_id / subject / unit_definitions 等身份与元数据字段；检测到「把两条参数拼成一条」时明确给出改法。`expression` 逐字匹配仍是硬条件 | `test_report_suggestions.py::test_calc_evidence_mismatch_lists_copyable_candidates_for_multi_argument_calls`（含反向契约：逐字抄其中一个字段即通过） |
| 2 | 11 讲单元4 子 agent 自行拼接目录层级（漏 `units/<材料名>/`），5 次 `read_image` not found 后才自行纠正 | `inspect-images` / `unit-read` 的清单新增 `read_paths`：按正文顺序、去重、可直接复制的实际读取路径（透明图给白底副本）。文档明确「只许逐字复制、不得拼接层级」，并把抄错路径归入 `call_correction`（不是 schema 错误，不扣 `image_schema_fix`） | `test_inspect_images.py::test_read_paths_are_copy_ready_and_deduplicated`、`::test_read_paths_stay_empty_when_no_reference_is_readable` |
| 3 | 12 讲单元4 子 agent 手抄 32 位 `unit_id` 错一位（…d7d8→…d7c8），两次 `calc` 只得 `not_found`，分不清抄错还是身份过期 | `material._unknown_unit_details`：`unit_id` 对不上时 `details` 带该材料完整 `known_units`（单元名→unit_id）与 `suggestion`（difflib 近似候选）；`find_unit_by_id` 与 `unit_progress` 共用 | `test_unit_identity.py::test_unknown_unit_id_reports_known_mapping_and_suggestion`、`::test_unknown_unit_id_without_close_match_omits_suggestion` |

**真机冒烟**（标准 preset，临时工作区）：`jiaodui inspect-images --unit …` 返回 `read_paths=['…/单元…/images/__jiaodui-whitebg-8145d9dfaa16f9d6.png']`；`jiaodui unit-progress --task-id T --unit-id <typod>` exit 5，`details` 带 `known_units` 与 `suggestion`。

**口径**：`pytest -o addopts='' -q -rs` → 1163 passed / 4 subtests passed。文档两份副本（`skills/jiaodui` 与 `packages/dsh-jiaodui/skills/jiaodui`）保持字节一致。

## 外部代码审查 6 项复核与修复（第 2 批，2026-10-10）

外部审查在 `origin/main`（abfea6c）→ `HEAD`（c54c843）+ 未提交改动上提了 6 项。逐条本地复现后**修 4 项、暂缓 2 项**；所有修复都附能先失败的回归测试，口径为「只修会静默产出错误交付或破坏调度闭环的，不动只对畸形输入才成立的」。

| # | 结论 | 修复 | 回归测试 |
|---|---|---|---|
| 1 [P1] 表格内批注锚点变空范围 | ✅ 已修 | `_gridify_marked_tables` 不再「先摘锚点再按竖线计数追加到格尾」，改为 `_pipe_cells_keeping_anchors` 直接在原行切格——锚点留在单元格内的原偏移；整行首/尾的纯锚点段并入相邻格（标记字段就是整行时仍不多列） | `test_cjk_table_keeps_columns_and_cell_anchor_keeps_offset`（断言锚点覆盖文本 == 「木板」，不只数锚点数）、`test_pipe_cells_keep_anchor_offset_and_row_edges` |
| 2 [P1] 中文表格两列并一列 | ✅ 已修，且修了两条独立成因 | ① `_display_width`/`_pad_display`：按显示宽度补齐（pandoc 实测 W/F 记 2、歧义宽记 1）；② `_convert_multiline_tables` 从锚点注入**之前**移到之后——宽度原本按标记文本 `【1\|cd\|ef】` 算，raw 注入后行宽变化，纯 ASCII 表格也会整表塌成一格。无标记单元的正文分支原来完全不做这个转换，也一并补上 | `test_dash_fenced_cjk_table_keeps_columns`、`test_display_width_follows_pandoc_grid_rule`；两条端到端断言 Word 行列结构而不只是 `ok` |
| 4 [P1] 复核前/退回后仍算「已完成」 | ✅ 已修 | `material.unit_needs_parent_review` + `run_units_complete`：v2 单元的「本轮完成」= 已登记 + 过闸 + 当前父复核 accepted；`scan_status` 把缺复核/被退回的单元降级为「本轮未完成」（因此自动回到 `dispatch-plan` 候选），`register_locked` 与 `record_parent_review` 共用同一完成口径（接受/退回都重算 `run.status`）。v1 报告不适用父复核，语义不变 | `test_parent_review_gates_completion_and_redispatch`（提交→待复核→accepted→退回，四个阶段查 status/dispatch/run.status） |
| 5 [P2] 无关材料坏清单阻断查询 | ✅ 已修 | `material._scan_materials`：遍历期隔离坏清单并保留现场（`material_dir`/`code`/`message`），`_material_by_task` 与 `find_unit_by_id` 共用；命中目标材料仍走严格校验，查不到 task 时把不可读清单列进 `not_found.details.unreadable_materials` | `test_unrelated_broken_manifest_does_not_block_queries` |
| 3 [P1] v1 报告可绕过结构化契约完成新材料 | ⏸ 待业主决策 | 未改。机理已复核：`parse_unit` 只拦 v2 前缀，v1 报告 + `parse-report` 在**新布局**材料上会 `registered=true / legacy=false`、`run.status=completed`、`build-report complete=true`。但现有测试 `test_concurrent_registration_keeps_all_units` 正依赖「新布局材料用 v1 `parse-report` 登记并算已完成」，属契约取舍而非 bug 修复，需先定「新材料是否允许人工补 v1 报告登记」 | — |
| 6 [P2] v1 标记正则兼容 | ⏸ 暂缓 | 未改。触发条件是「改为字段以**单个**孤立反斜杠结尾再紧接 `】`」（`\\】` 不受影响），全仓报告扫描无此形态；改法要按封套选正则，而 `INLINE_MARKER_CAPTURE_RE` 是模块级常量、被 verify/parse/docx/repair 共 10 处引用，收益是假想输入、代价是动兼容读取核心 | — |

**真机冒烟**（标准 preset，临时材料）：
- 表格：`| 对象 | 数值 | / | 前【1\|木板\|木块】后 | 10 |` 与破折线包裹的同类表格，Word 中都是 2 行 × 2 格，`commentRangeStart…End` 之间正是「木板」；无标记单元的破折线表格也从 1 列恢复为 2 列。
- 调度：v2 提交后 `status=本轮未完成/run=in_progress/dispatch=['单元1']`；`accepted` 后 `已完成/run=completed/dispatch=[]`；`needs_revision` 后回到 `本轮未完成/in_progress/dispatch=['单元1']`。

**口径**：`pytest -o addopts='' -q -rs` → 1169 passed / 4 subtests passed。skill 文档两份副本保持字节一致。

## 第 11 讲真机回放：子代理摩擦的 A/B 档修复（2026-10-10）

**材料**：用户提供的 `dsh-session-session-d72a3e46-….zip`（主会话 585 事件 + 15 个子代理会话）。10 个单元、15 次单元派发，**84 次 `unit_submit` 里 70 次被拒（83%）**。逐条归因后确认：**绝大多数不是判断问题，而是「报错不给定位信息」与「同一份身份/证据要抄两遍」造成的空转**。本轮按业主要求只做 **A（core 报错补细节）+ B（skill 文档）**，**不放宽任何契约、不改闸门、不动预算机制**。

| 错误码 | 次数 | 根因 | 本轮修复（A） | 文档（B） |
|---|---|---|---|---|
| `location.original-mismatch` | 10（单元3 同一写法连撞 20 次） | 只报「不一致」，不给实际/期望原文；`expected_original` 与 `location_id` 的绑定规则未写明。**后果**：单元3 放弃该条修改并改报「无问题」，同类发现却在单元10 被正常提交 → 静默漏报 | `source_index.resolve_location` 同时给出「实际命中的原文」与「你写的值」（`_brief` 按 120 字符截断并标真实长度） | `operation-manual`「四条硬规则」第 1 条；`failure-modes` 新增该行 |
| `proposal.schema` | 10（单元1 同一缺键连撞 5 次） | 报错恒为「字段缺失或包含未支持字段」，不点名；且 `task_id`/`unit_id` 要同时出现在工具顶层与 `proposal` 内部，模型在两处之间横跳（顶层漏传 → `not_found: "undefined"`） | `report_suggestions` 报出 `missing=[…]` / `unknown=[…]` 与允许字段全集；`material._identity_placeholder_hint` 把字面量 `undefined` 报成「漏传参数」而非「材料不存在」 | 同上硬规则第 3 条 |
| `proposal.calc-call-mismatch` | 19 | `result` 被字符串化（`'8.0'` vs `8.0`）、手打 `dimensional` 对象、多参数调用用 `==` 拼接、`vector_ops` 误填函数调用式 | 报错文案维持（上一批已列出可照抄取值） | 硬规则第 2 条：原生 JSON 类型、`expression_a`/`expression_b`/`formula`/`solve_for`/`vector_operation` 分条记录 |
| `proposal.self-check-incomplete` | 4 | 五个必需项是固定字面量，但入口与 schema 都没列出；模型写成 `"real_issue: 说明…"` | 报错列出缺失项与合法字面量清单 | 硬规则第 4 条 |
| `proposal.evidence-*` | 17 | 「须含 id/text/…」不指明第几项缺哪个字段 | `assumptions` / `calculations` 逐项报 `[下标] + 缺失字段`；`symbols` 报实际形状 | 硬规则第 4 条 |
| `execution-policy-required` | 17 | 授权绑定轮次，而 `execution-policy` 被登记在 `split` 之前；`split` 开新轮后 8 个并发子代理第 1 步全被拒 | `require_current_policy` 给出补救命令与当前 `run_id`；`split`/`slice` 开新轮次时在 `warnings` 显式告警 | `SKILL.md` 写明 `convert → split → execution-policy`；`operation-manual` 增「流程顺序是硬约束」段；`failure-modes` 新增该行 |
| `proposal-revision-stale` | 3 | 只报「必须增加 1」，不给当前版本 | 报出当前已登记 revision 与应填值 | `failure-modes` 新增该行 |

**未改（有意）**：`proposal.calc-call-mismatch` 的放宽（允许只给 `call_id` 由 ledger 回填）、`expected_original` 改为可选、`proposal` 身份字段改为可选、工具壳缺参不再序列化成 `undefined`、`self_check.checks` 补 enum —— 这些属 C 档（放宽契约必填字段），需业主先定边界。**预算机制也未改**：本轮 70 次失败提交中，子代理一次 `unit_recovery` 都没调（5 次全是父代理），`≤2 次`上限实际未生效；按业主要求本轮只记录、不改机制。

**回归测试**（新增 10 个，均为「报错必须给出可机械修正的定位信息」的正向契约）：
`test_source_index.py::test_original_mismatch_names_both_actual_and_expected_text`、`::test_original_mismatch_truncates_long_text_but_keeps_length_hint`；
`test_report_suggestions.py::test_schema_error_names_missing_and_unknown_keys`、`::test_self_check_incomplete_lists_missing_required_checks`、`::test_evidence_assumptions_error_names_index_and_missing_field`、`::test_evidence_symbols_error_reports_actual_shape`、`::test_evidence_calculation_error_names_index_and_missing_fields`；
`test_unit_identity.py::test_unknown_task_placeholder_is_reported_as_missing_argument`、`::test_split_warns_only_when_it_actually_opens_a_new_round`；
`test_main_policy_contract.py::test_missing_policy_error_teaches_how_to_rea_authorize`；并扩展 `test_unit_delivery.py::test_new_snapshot_cannot_reuse_old_proposal_revision` 断言当前版本号。

**入口体积**：`SKILL.md` 仍为 8172 码点（阈值 8192）——把与 `failure-modes.md` 重复的恢复预算句压缩掉，腾出空间写流程顺序契约。两份 skill 副本保持字节一致。

**口径**：`pytest -o addopts='' -q -rs` → 1179 passed / 4 subtests passed。

## 第 12 讲真机回放：伪造取消拖垮整轮的 P0 修复（2026-10-10）

**材料**：`dsh-session-session-5c46945e-….zip`（第 12 讲，`jiaodui` preset，模型 `gpt-6.1-sol`）。本轮**无交付物**，用户在 10:30:55 主动中止。逐条归因后确认：**一条由工具 schema 诱发的伪造取消链**是整轮失败的根因；另有 4 条是修复会话自身在 10:20:0x–10:23:55 把工作树改成中间态造成的（同一会话随即从 DSH 日志重放恢复，不属于本仓需要修的问题）。

### 因果链（真机证据）

| # | 环节 | 证据 |
|---|---|---|
| 1 | `execution-policy` 登记在 `split` **之前**，`split` 开新轮 → 授权失效 | 5 个子代理在 10:10:37–43 同时 `execution-policy-required`（step 45 登记、step 62 拆分） |
| 2 | **单元子代理在正常 `prepared` 心跳里填了取消字段** | `jiaodui_unit_event` 的 `cancel_initiator`/`cancel_reason` 是**没有 description 的可选 enum**；8 个子代理合计成功记录约 29 条 `user`/`user_cancel`（另有 8 条 `host`/`technical_timeout`） |
| 3 | `dispatch-plan` 的 `stopped = bool(cancelled)` → **永久 `stop=true`**，无超时、无撤销 | `dispatch=[]`、14 个单元全在 `waiting` |
| 4 | 父代理唯一出路是开新轮次，而 **`--rerun` 不在原生 `jiaodui_task_prepare` 里** | 退回 bash：`jiaodui: command not found`(127) → 再猜绝对路径 `/…/.venv-cli/bin/jiaodui`；`taskPrepareArgs` 的 split 分支只有 `--subject/--mode/--strategy/--no-clean` |
| 5 | `--rerun` 开新轮 → 在途子代理 `expected_run_id` 全部失效 | `run-changed` ×3（10:28:42–44） |
| 6 | 循环；用户中止 | `turn/end reason=user` |

### 本轮修复（P0：取消陷阱 + stop 锁死）

| 层 | 改动 |
|---|---|
| core | `record_unit_event` **移除** `cancel_initiator`/`cancel_reason`；新增 `record_unit_cancel`（配对校验 + `revoke`），`_last_cancellation` 统一「末尾是撤销记录即视为未取消」；`user_cancel` **不可撤销**（人的决定不是父代理能代撤的） |
| CLI | `unit-event` 去掉两个取消开关；新增 `unit-cancel --initiator/--reason [--revoke]` |
| 工具 | `jiaodui_unit_event` schema 删除取消字段；新增独立工具 `jiaodui_unit_cancel` |
| preset | 子代理 `toolFilter.allow` **不含** `jiaodui_unit_cancel`（并加注释锁住），`jiaodui_unit_event` 保留 |
| 输出 | `unit-progress` / `dispatch-plan` 的 `cancelled` 补 `agent_id`、`attempt_id`，伪造来源可追溯 |

**取消语义**：取消只由父代理/宿主记录。技术性停止被 `stop=true` 挡住时，父代理用 `unit-cancel --revoke` 直接恢复补位，**不再需要 `--rerun`**（后者会连带废掉在途子代理的轮次）。

### 回归测试（新增 6 个）

- `test_unit_progress.py`：`test_unit_event_has_no_cancellation_parameters`（签名反向契约）、`test_cancel_reports_actor_and_revoke_releases_dispatch_stop`、`test_user_cancel_cannot_be_revoked_by_parent`、`test_revoke_without_standing_cancel_is_rejected`、`test_cli_unit_cancel_records_and_revokes_end_to_end`（真子进程：旧写法必须 exit 2 且不得伪造取消）。
- `test_dsh_plugin_package.py`：`test_unit_subagents_cannot_cancel_their_own_unit`（子代理 toolFilter 必须排除 `jiaodui_unit_cancel`）。
- `test_dsh_plugin_tool_behavior.py`：扩充真 Node 断言——`jiaodui_unit_event` 不得再暴露取消字段、`jiaodui_unit_cancel` 的 argv 映射（含 `--revoke`）。

**真机 CLI 冒烟**（临时工作区）：① 旧写法 `unit-event --cancel-initiator user` → exit 2，`dispatch stop=False`（伪造被堵死）；② 父代理 `unit-cancel parent/technical_timeout` → `stop=true` 且 `cancelled` 带 `agent_id`/`attempt_id`；③ `--revoke` → `stop=False`、`dispatch=['第1题']`；④ 先记 `user_cancel` 再 revoke → `cancel-invalid`、`stop` 仍为 `True`。

**顺带确认**：上一批 A/B 档修复在真实链路里生效——10:20:20 与 10:28:37 出现新文案（「缺少 no_issue_review…只接受这些字面量」「assumptions[0] 有问题：不是对象」）；`execution-policy-required` 的复发正是 B 档要修的排序陷阱，该轮运行早于修复落地。

**未修（留待 P1/P2）**：原生工具缺 `--rerun/--replace-units/--adopt-units`、`execution-policy` 对不存在目录抛裸 traceback、`unit-recovery` 的 category 猜测。

**口径**：`pytest -o addopts='' -q -rs` → 1185 passed / 4 subtests passed。两份 skill 副本字节一致。

## 第 12 讲回放：P1/P2 低风险增补（2026-10-10）

承接上一节的因果链，补掉三处「让父代理只能猜」的缺口。**不动闸门、不放宽任何校验**。

| # | 现象（第 12 讲证据） | 修复 | 回归测试 |
|---|---|---|---|
| P1-3 | `split` 的 `--rerun`/`--replace-units`/`--adopt-units` 只有 CLI 有，`jiaodui_task_prepare` 没暴露 → 父代理退回 bash 猜 `.venv-cli/bin/jiaodui` 绝对路径（`jiaodui` 不在 PATH，先 exit 127），并**绕过原生工具自带的 `--work-root` 等值校验** | `taskPrepareArgs` 的 split 分支补 `--rerun`/`--replace-units`/`--adopt-units`/`--out-root`/`--base-name`/`--images-dir`；schema 同步加六个属性，并在 `rerun` 上注明「会重置执行模式授权」 | `test_dsh_plugin_tool_behavior.py` 断言三处 argv 映射；真机用同一串参数跑通 `split --rerun --replace-units` |
| P1-4 | 父代理在 `convert` 之前登记执行模式 → `locked()` 抛 `FileNotFoundError`，被 CLI 兜成**裸 traceback + `unexpected`(exit 1)**，无从判断该先做什么 | `material.set_execution_policy` 先判 `root.is_dir()`，报 `not_found`(exit 5) 并给出「先 convert，拆分之后再登记」的指引 | 真机冒烟断言 exit 5 且 stderr 无 `Traceback` |
| P2-5 | 父代理批量 4 次恢复都填了 `report_repair`（实为 `call_correction`）→ 整批被拒后重发 | 保留「类别由错误码确定性决定」的硬校验（不改契约、保留既有测试），但 `recovery-category-mismatch` 的 `details` 补 `error_code`/`provided_category`/`expected_category`，可一次机械修正；工具 schema 的 `category` 描述改为「错误驱动的恢复请省略」 | `test_error_classification.py` 扩断言：`details.expected_category == 'call_correction'`，并补「省略 category 即按码派生并扣费」的正向契约 |

**口径**：`pytest -o addopts='' -q -rs` → 1185 passed / 4 subtests passed；SKILL.md 仍 8172/8192 码点；两份 skill 副本字节一致。

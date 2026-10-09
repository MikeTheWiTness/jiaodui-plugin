# 校对流程改造执行记录（实验分支）

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

## 安全复核

发现并修复：父复核CLI参数接线错误；旧parse会丢proposal并绕复核；同hash退回未撤销接受；Word按首次报告标题切段吞标记；移除fs会丢read_image。通用兼容修复由独立工作树处理，不要求合并实验审查功能才能使用main。

## 隔离回放

在仓库工作区中新建第4/5讲完整材料名加“流程改造回放-20261009”，写入前核对两目录不存在。旧EasyUse材料只读源文件副本作输入，不读旧报告、不修改原稿/旧记录。第4讲拆11单元、图片10；第5讲拆12单元、图片14，缺失均0。

本会话首次真实视觉探针通过，实际read_image观察与参考一致。回放在开发会话中使用CLI/core退路，不是新校对preset安装验收。关键单元由路径/ID派干净子agent；主agent不逐单元读取源文，最终只通读汇总报告。

关键7单元回放结果：5个技术提交通过（不是最终父审完成），2个失败（第4讲练9calc证据绑定不匹配；第5讲练1图片证据结构/调用格式失败），完整错误和摘要保留在契约失败文件。其余16单元未开始，整份complete=false。父代理已通读两份汇总报告并将第4讲练5的g/悬点、第4讲练8传播方向语义按hash定向退回（每单元已消费1轮复核预算）；不能为凑Word或既有标记数刷新失败预算、伪造全部通过。3份证据超长行在报告展示修复预算内分行登记新revision；第5讲练3的该类额度已满，未继续变更，其余原报告保留。

## 未完成与交付限制

- 本轮尚不满足M0—M6全部验收：**P5 已按 core 可见口径收口**；**P6 第 2 项（两个失败单元根因 + 回归）已完成**，**P6 确定性链路验收已完成**（P3 转义边界走完 Word + Word-v2 端到端结构计数 + 整卷 `complete` 三态）；余下 P6 一块按用户 6C 决定执行——最小真实校对 1–2 个单元（图片证据型 + 转义边界型，需用户授权范围）。再往后是实际安装方式与新会话父子 catalog（P2）。P3 已收口特殊字符无损编码与正文/信封契约，P4 已补齐父侧结构化工具。
- 整份回放必须所有必需单元技术通过、父复核当前版本且Word结构/图片/批注记账通过才可交付；有未开始、失败或unreviewed时只交诊断，不生成冒充完整的Word。
- 不渲染最终Word、不检查分页截图、不提供视觉免责声明；仍保留题图真实读取和首次探针。

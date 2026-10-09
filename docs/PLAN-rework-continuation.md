# 后续实现计划：M0—M6 收口

- 依据：[EasyUse《校对流程改造执行计划》](/Users/chouchou/开发/EasyUse/校对流程改造执行计划.md) 的 M0—M6 与 §11 验收场景；需求口径仍以 [docs/PRD.html](PRD.html) 为准。
- 边界说明：[main 进度说明](PROCESS_REWORK.md)（旧 Markdown 报告主链）与 [实验进度说明](../.worktrees/structured-report/docs/PROCESS_REWORK.md)（第7章结构化主链）。
- 本计划只覆盖「把已实现的部分收口到可验收」和「补齐明确缺口」，不新增学科、不建设模型 benchmark、不动 GUI、不改源文、不 push、不改 profile。

## 0. 已核实的基线（2026-10-09，实跑复核）

| 对象 | 实测结果 |
| --- | --- |
| `main` `c1c24b9` | 工作树干净；全量 `.venv/bin/python -m pytest -q` = **968 passed / 0 failed / 0 skipped**；此前定向回归 217 通过 |
| `.worktrees/structured-report` `b4c1413` | 工作树干净；全量 = **998 collected / 0 failed / 5 skipped**（993 实跑）。5 个 skip 是**从 worktree 跑导致的路径问题**，不是真跳过：4 个 `test_legacy_corpus` 的默认语料路径 `../../JiaoDuiAgent/output` 在 worktree 下解析不到，1 个 `test_report_repair` 计划样本同理 |
| 实验分支对旧语料的双向契约 | 补 `JIAODUI_LEGACY_CORPUS=/Users/chouchou/开发/JiaoDuiAgent/output` 后 `test_legacy_corpus` **4/4 通过**（严格闸门在结构化链上未被放宽） |
| 回放材料（仓内 `校对/`） | 两份材料 23 单元：**6 个已生成报告+数据**（4讲 单元6/7/9，5讲 单元1/4/9）、**2 个失败留痕**（4讲 单元10=练9 计算证据绑定；5讲 单元2=练1 图片证据格式）、**15 个未开始**（4讲 1/2/3/4/5/8/11，5讲 3/5/6/7/8/10/11/12） |
| 入口 skill 长度 | **P1 已完成**：两份副本均从 14,376 码点精简到 **7,970 码点**（≤8,192），细节移入 `references/operation-manual.md`；`tests/test_skill_docs.py` 新增入口长度与链接存在性测试。裁剪机制见 §0.1 |
| 实验分支入口 skill | 已精简到 **8,083 字符**（本次 main 的精简参照了它的外移模式，并按 main 的旧链口径重写） |
| 辅助 worktree | **P0 已完成**：`fix/structured-pipeline-safety`（e830571）的三项修复经逐项核对均已落在 `b4c1413`（preset 保留 read_image、`parse-v2-requires-submit` 已有 `tests/test_review.py` 覆盖、Word 走 `_report_sections` v2 边界），其 Word-v2 端到端回归**在实验分支缺失**，故以 tag `archive/structured-pipeline-safety` 保留待 P3/P6 移植；`fix/main-policy-contract`（9ff6931）与 main 只差已被取代的文档 → 直接删除。两个 worktree 与分支均已移除 |

`main` 的 SKILL.md 分节字符预算（用于 P1 裁剪，总 14,376）：

| 节 | 字符 | 处理方向 |
| --- | --- | --- |
| §1 何时使用与目标 | 318 | 保留 |
| §2 入口判断与前置硬门槛 | 2,297 | 保留硬门槛；§2.2.4 宿主 schema 长段移入 `references/failure-modes.md` 第七节 |
| §3 完整流程 | 5,560 | 十步流程留入口；§3.0 路径/独立测试细则与调用示例移入 `references/operation-manual.md` |
| §4 调度规则 | 487 | 保留 |
| §5 子 agent 输入包 | 686 | 保留 |
| §6 硬约束 | 816 | 保留，不缩水 |
| §7 产物命名纪律 | 233 | 保留 |
| §8 命令速查 | 3,524 | 整体移入 `references/operation-manual.md`，入口只留 3–5 行指针 + 退出码一行 |
| §9 延伸阅读 | 296 | 保留并加 operation-manual 链接 |

### 0.1 入口超长到底会不会被裁（宿主源码复核）

结论：**8,192 是真阈值，但触发是有条件的**——不是每次加载都裁，而是**压缩触发时**才裁；一旦裁了，损失正好落在流程主体。

机制（从 `app.asar` 按归档索引只读提取核对，未改宿主）：

- 预设行 `tool-result-pruner` 配的是 `thresholdChars: 8192 / headChars: 4096 / tailChars: 1024`（与 DSH `standard` preset 同值）；desktop profile 没有覆盖项，所以是生效值。
- `dsh-tool-skill` 的 `skill` 工具把 **整份 SKILL.md 原样**作为单个文本块返回（`dsh-tool-skill/lib/index.js:151-156`，无长度保护；只有 skill 目录描述会被截到 500 字符）。因此它是「一个超预算的工具结果」。
- 修剪器对**每一个**超阈值的工具结果生效，没有按工具豁免；README 原文：「未达到压力阈值的对话保持不变」「每个文本超过阈值的工具结果都会被替换」（`dsh-compaction-tool-result-pruner/README.zh.md`）。
- 修剪**只在压缩触发后**运行：`compaction-basic.compactIfNeeded()` 在溢出恢复或 token 压力达标（默认 `thresholdRatio = 0.8` × 上下文窗口，`retainRatio = 0.16`）时先调 `prune.pruneSession()`，`dsh-compaction-basic/lib/index.js:926-945`。桌面 profile 的模型上下文是 1,000,000，压力线约 800k token，所以**普通单份材料的一轮校对通常根本不会裁到它**。

一旦触发，按码点切片，14,376 字符的入口只剩 **4,096 + 标记 + 1,024 = 5,159 码点**，中间 **9,256 码点（第 41–118 行）整段消失**，包括：§3 第 4–10 步（派发、子 agent 职责、verify→parse→build-report→build-docx→交付）、§4 调度规则、§5 子 agent 输入包、§6 硬约束（六类预算、取消/权限拒绝不得恢复）、§7 命名纪律、§8 命令速查的一半。

可恢复但不是零成本：

- 修剪会留下显式 `[... tool result middle pruned ...]` 标记，模型可以**重新调用 `skill`** 拿到一份全新的未修剪结果（下次压缩前有效），也可以用 `read` 按 offset/limit 分页读该文件。
- 用户直接调用 skill 时走的是 `agent/pre-step` 注入的**用户消息**（`dsh-tool-skill/lib/index.js:168-196`），不经工具结果通道，**不受修剪影响**；skill 目录本身也不受影响。

必要性判断：**值得做，但不是阻塞项**。理由是收益（PRD D22 合规 + 消除「上下文越紧张、流程规则越容易消失」的反向激励）远大于成本（实验分支已有 8,083 字符的成品可移植），但它不修任何当前功能故障，所以 P1 **不阻塞 P3–P6**；同时 P1 顺带加一条 1 行的兜底提示（见 P1 第 6 项），这条兜底与是否精简无关，本身就该有。

## 1. 里程碑 → 批次映射

| 里程碑 | 完成条件现状 | 由哪个批次收口 |
| --- | --- | --- |
| M0 现状核对 | 已完成 | P0（分支清理） |
| M1 执行模式与轻量 preset | main 已实现；「新会话只看见必要 skill/工具」未真机验收；入口超长是能力最小化的遗留 | P1 + P2 |
| M2 单元身份与定位 | 实验初版已实现（重复词唯一定位、版本失效、schema 共享）；父侧仍手拼 argv | P4 |
| M3 结构化建议与无损报告 | 初版已实现；**特殊字符/信封不可无损** | P3 |
| M4 证据、自查与父复核 | 初版已实现（首轮证据、真实 calc 关联、自查、按 hash 复核、退回撤销旧接受） | P6 回放验收 |
| M5 恢复预算与调度可靠性 | 预算/事件记账已实现；**错误分类、心跳、窗口补位、取消闭环**缺 | P5 |
| M6 整份交付与安装验证 | 仓内闸门/记账已实现；**宿主 catalog、新会话、停止后无写入未验收**。按 D4，本轮回放 2 个失败单元不重派 → 本轮 `complete=false`、不出 Word；M6 的「全部通过才出 Word」判据不变，等新轮次授权后补 | P2 + P6 |

## 2. 批次

### P0 基线冻结与分支清理（规模 S）— ✅ 已完成

执行结果：三项安全修复逐项核对落在实验分支（见 §0 辅助 worktree 行）；`fix/main-policy-contract`、`fix/main-safety` 的 worktree 与分支已删除，安全复核分支以 tag `archive/structured-pipeline-safety` 保留；安装边界复核为「软链 → 根仓 `packages/dsh-jiaodui`、根仓在 main」。

1. 基线以本文件 §0 为准（含命令与 junit 口径）；若需要独立记录，新建 `docs/REWORK_BASELINE.md`，写明 main 968 与实验 998/5 skip 的差别，以及 worktree 跑旧语料要设 `JIAODUI_LEGACY_CORPUS`。**不要改 [docs/BASELINE.md](BASELINE.md)**：它由 `scripts/recompute_baseline.py` 生成，文件头明确「请勿手改」。
2. 核对 `fix/structured-pipeline-safety` 的 2 个提交（`6e89d0d`、`e830571`）语义是否已全部落在 `b4c1413`：逐项比对「保留 read_image」「旧 parse 不覆写 v2 数据」「Word 按 v2 正文边界切段」。逐项确认后再 `git worktree remove` + `git branch -D`（只删本地分支，不触碰 remote）。
3. 确认 `fix/main-policy-contract` 的文档差异已被 main 取代后同样删除。
4. 顺手确认安装边界未漂移：桌面 profile 的 `node_modules/dsh-jiaodui` 仍是指向根仓的软链、根仓仍在 main（`readlink` + `git branch --show-current` 各留一条记录）。

完成判据：本机只剩 `main` 与 `feature/structured-report-pipeline` 两条工作分支；`git worktree list` 与基线记录一致；删除与软链检查动作逐个留痕。

### P1 main 入口精简至 8,192 以内（规模 M）— ✅ 已完成

执行结果：入口 14,376 → **7,970 码点**；新增 `references/operation-manual.md`（两份副本，6.8k 码点）承接命令速查、目录参数、写入前核对、讲义清理顺序、派发句柄与智能拆分步骤；§2.2.4 宿主 schema 长段只留结论并指向 `failure-modes.md` 第七节；入口 §1 加了抗裁剪提示。测试侧：新增 `test_skill_entry_stays_within_pruner_char_budget` 与 `test_skill_entry_referenced_files_exist`，参数/命令断言改为覆盖整个 skill 目录，随包副本一致性测试自动涵盖新文件。双口径全量 **971 passed / 0 failed / 0 skipped**（精简前 968）。

必要性口径见 §0.1：这是 PRD D22 合规与抗压缩退化的清理，不是当前故障修复，所以可以与 P3/P4/P5 并行推进；只有 P2 的真机验收需要它先落地。原执行步骤留档如下。

1. **先写失败测试**（`tests/test_skill_docs.py` 增补）：两份 SKILL.md 字符数 `≤ 8192`；两份字节一致；入口内引用的每个 `references/*.md` 真实存在。
2. 新增 `skills/jiaodui/references/operation-manual.md` 与随包副本：承接 §8 命令速查与 §3.0 细则（目录参数约定、写入前路径核对、独立流程测试规则、调用示例），另加讲义清理顺序、派发句柄、智能拆分步骤、宿主修剪兜底。
3. 入口只留：十步流程的可判定要点、六类预算与停止条件、`verify-report` 唯一闸门、不改源文、命名纪律、`operation-manual.md` 指针。
4. §2.2.4 的宿主 schema 长段（`read_image(file_path=…)`、`run_code` 纪律）只留结论并指向 `references/failure-modes.md` 第七节。
5. 逐节核对「入口必须仍可见」清单（删字不得删约束）：① verify 不过不算完成；② 六类预算与 `image_schema_fix` 同记 `call_correction` 不可叠加；③ 用户取消/权限拒绝不恢复；④ 未确认执行策略禁止记录尝试；⑤ 单元名精确匹配与单元内只允许的契约名；⑥ 一层扁平、禁嵌套；⑦ 首次视觉探针与真实题图读取仍是门槛。
6. **加抗裁剪兜底**：入口 §1 写明见到 `[... tool result middle pruned ...]` 时先重新加载 skill 或分页 `read`，再继续。

### P2 main 宿主验收（M6-main，规模 S，依赖 P1）

只用真机新会话判定，仓内测试不替代：

| 检查项 | 记录内容 |
| --- | --- |
| 安装形态 | `~/.dsh/profiles/desktop/node_modules/dsh-jiaodui` 仍是软链指向根仓 `packages/dsh-jiaodui`；根仓停在 main |
| skill 目录 | 新「校对」会话 `skill` 列表**只有** `jiaodui`；加载后正文完整（14,376 或精简后的长度，按码点核对，对照 §0.1）；全文末尾可见，无 `[... tool result middle pruned ...]` 标记 |
| 父工具目录 | 有 `read` / `read_image` / `write` / `edit` / `jiaodui` / `subagent` / `ask_user` / `todo` / `present`；无 web / goal / plan / fork / workflow / ralph / plugin-manager |
| 子工具目录 | allowlist 生效面（`skill/read/read_image/write/edit/jiaodui`）；`maxDepth=1` 无法嵌套派发；不把它记为「严格权限隔离」 |
| 真实能力 | `read_image(file_path=…)` 实读随包探针；对单元目录 `write` 旧报告；`jiaodui` 工具跑 `check-env` 与 `status` |
| 停止语义 | 取消在途子代理/受管子进程后，工作区**无继续写入**（对单元目录做前后 mtime/文件清单对比） |

完成判据：上表逐项有记录，新建 `docs/HOST_ACCEPTANCE.md` 承载（含日期、DSH 版本、按 `catalog` 逐项勾选与截图/文本证据）；未通过项直接回填为 P1/P4 的缺陷项，不勾选 M6。

### P3 实验：第7章无损契约（规模 L，无依赖；P4/P6 的前置）

1. **先定格式决策（ADR）**：新增 `docs/adr/0006-…`，把报告正文 v2 的可逆编码与版本策略写在实施之前。按 D2 已确认走「正文内反斜杠转义 + 唯一反转义入口」：
   - 仅 `<!-- jiaodui-report-v2 -->` 报告启用转义；字段编码 `\`→`\\`、`|`→`\|`、`【`→`\【`、`】`→`\】`；
   - **唯一反转义入口**放 `jiaodui/markers.py`（如 `unescape_marker_field`），供四个消费点共用：verify 重建、docx 渲染、`report_parse`、`report_repair`；
   - 旧 v1 报告不加 v2 标记，行为不变（逐份标注的旧语料回归必须保持 4/4 与既有拒绝集合）。
2. **先红**：`tests/test_report_suggestions.py` 增补双向契约——原文含 `|`、`【`、`】`、`\`、跨行、汉字/emoji/组合字符/零宽/CRLF 时，提交后 `split_marked_body(报告正文) == 源文` 逐字相等，且 `verify-report` 通过；同时保留「无唯一位置/重叠/空操作仍拒绝」的反向用例。
3. 实现：删除 `jiaodui/report_suggestions.py` 的三处硬拒绝（`report_suggestions.py:205` 源文含标记语法、`:233` 原文字段含 `|`/`【`/`】` 与修改后含 `【`/`】`），改为写入转义后校验。
   - 转义/反转义必须成对且对称：写入侧（`report_suggestions` 渲染正文、`report_repair` 插回标记）与读取侧（`markers.split_marked_body`、`audit_markers`、docx 的 `render_new` 分支、`report_parse`）共用 `escape_marker_field` / `unescape_marker_field`。
   - 语法约束要写进 ADR：原文字段正则 `(?:\\\||[^|])*` 本来只允许 `\|` 代表竖线，**且当前没有任何反转义**（所以老报告里的 `\|` 重建出来仍是 `\|`）；修改后字段是 `[^】]*?`，是唯一无法容纳字面 `】` 的字段。v2 的转义要同时修掉这两处，v1 保持原样不动。
4. **信封契约**：明确「源文正文」与「信封（标题/前置参考等非正文行）」的边界，并把 `body_sha256` 与 `source_sha256` 分开绑定（当前 `unit_delivery.py:57`、`report_suggestions.py:201` 两者相等）。必须覆盖：信封-only 单元（实测回放 4讲 单元1 源文只有 `第 4 讲\n\n【选修专项】简谐运动与机械波` 21 字符）、前置参考型旧源文、v2 报告不得剥信封（`verify.py:453` 已按 v2 标记跳过 `strip_reference_preamble`）。
5. 交付闸门不放宽：`verify-report` 仍是唯一闸门；`unit_delivery.py:94` 的 `split_marked_body == source_text` 严格相等保持不变，只增加可表达的字符集合。

完成判据：[执行计划 §11.1](/Users/chouchou/开发/EasyUse/校对流程改造执行计划.md) 的定位/保持场景全部有测试与结果；v1 语料逐份标注预期不变；信封-only 单元有明确契约（生成报告或显式 skip，不静默产出空报告）。

### P4 实验：强类型工具覆盖（规模 M，依赖 P3 的身份/版本语义）

现状：`packages/dsh-jiaodui/tools/index.js` 已注册 `jiaodui_unit_locate/read/snapshot/submit/recovery/event/review` 与 `jiaodui_calc_<op>`；**准备与交付仍是 `args: string[]` 透传**。

1. 补父侧结构化工具（薄 adapter，只拼 argv，判断留在 core）：
   - `jiaodui_task_prepare`：`check-env` / `inspect-source` / `convert` / `split` / `precheck-split` / `status` / `execution-policy`；
   - `jiaodui_delivery`：`build-report` / `build-docx`，返回结构计数（锚点/兜底/缺失/over_count）与 `complete`；
   - 可选 `jiaodui_finalize_unit`：按序 `verify-report` → `parse-report`，失败返回明确 stage。
2. 保留 `jiaodui` argv 透传作为退路（CLI 是永久退路，PRD D20/D21），但 skill 正常路径只写结构化工具。
3. 覆盖测试：`tests/test_dsh_plugin_package.py` / `test_dsh_plugin_tool_behavior.py` 断言参数 schema 与 CLI 实际注册一致（沿用「文档参数 ⊆ CLI 参数」口径），未知参数在调用前被 schema 拒绝。
4. 同步两份 SKILL.md 与 `references/operation-manual.md`；双副本一致性测试保持绿。

完成判据：正常校对路径不再需要模型手写路径或 JSON 字符串；未知参数在执行前报错（不是执行后）；`jiaodui` 透传仍可用。

### P5 实验：M5 调度闭环（规模 L，依赖 P3/P4）

现状：预算与 `attempt_id`/失败指纹记账已实现（`jiaodui/material.py`，`last_event_at` 见 `material.py:403`）；**core 里没有任何错误分类消费点**（无 `retry_class`），滑动窗口只写在 skill 散文里。

1. **确定性错误分类**：core 增一份「错误码 → 恢复类别」映射（`call_correction` / `calc_representation` / `report_repair` / `targeted_review` / `technical_redispatch` / `image_schema_fix`），`unit-recovery` 只接受已分类的码；未分类码拒绝并给出类别建议。先红：参数拼错、旧路径、编辑前置失败、不支持函数差异各自归类正确。
2. **心跳与超时判据**：新增只读 `unit-progress`（或并入 `status` 输出）暴露 `phase` / `attempt_id` / `last_event_at` / 在途状态；父代理据此判超时，不靠沉默时间猜崩溃。
3. **滑动窗口与取消闭环**：把 §9 的判据写成可执行检查——空位补位、同一单元不重复派发、首个致命错误后停止补位并取消在途、确认停止后再结束批次；取消来源 `user|parent|host` 与 `reason` 各记各的，`parent technical_timeout` 不冒称用户取消；`exec.signal` 中止仍以中性 `AbortError` 上报（插件不猜来源）。
4. **并发登记原子性**：8 单元并发 `unit-submit` / `unit-event` 压测，断言材料记录不丢条目、不互相覆盖（锁或原子 merge）。
5. **测试口径**：编排层用模拟派发/返回覆盖窗口补位、失败重派、断点扫描；宿主读图与落盘仍留真机冒烟。

完成判据：模拟首轮 5 类故障可在授权预算内恢复；预算耗尽留痕且不无限补位；用户取消无重派；父技术超时不误标用户取消；并发登记不丢结果。

### P6 实验：回放推进与工具缺陷修复（规模 L，依赖 P3/P4/P5；按 D4 不开新轮次）

1. 在实验核心（`--work-root` 指向仓内工作区）续跑 `校对/` 的 4讲/5讲回放材料中 **15 个未开始单元**：本轮沿用当前 run，不重派已失败的 2 个单元。
2. **2 个失败单元只修根因、不重跑**（4讲 单元10=练9 计算证据绑定；5讲 单元2=练1 图片证据格式）：
   - 按失败留痕里的完整 `unit-submit` 输出定位是 core 契约缺陷还是子代理调用形态问题；
   - 若属工具缺陷：先在 core/adapter 修，并写**能先失败的回归测试**（`calculation` 证据的 call_id 绑定、图片证据 schema 与调用格式），再改实现；
   - 旧 `_校对失败.md` 原样保留，不刷新旧预算、不删留痕、不重派、不重开 run。
3. 父代理对当前版本做复核（现有 5 个当前版本复核 + 新增）；`complete=true` 前不生成正式 Word。
4. 本轮按 D4 的预期结果是 **`complete=false`**：交付物为「续跑得到的整卷报告 + 诊断 + 当前失败清单 + 两个失败单元的工具根因修复与回归」，**不出正式 Word**、不渲染、不做分页截图、不写视觉免责声明。是否对这两个单元开新轮次，由用户在看到根因分析后另行授权。
5. 如后续获授权开新轮次：新轮次需重新登记 `execution-policy`（新 run 不自动授权），旧失败留痕保留；届时再按「23 单元全部技术通过 + 父复核为当前版本 → `complete=true` → 出 Word 并做结构/图片/批注记账机器断言」执行。

完成判据：15 个未开始单元全部有技术结果（通过或留痕失败）；2 个失败单元有明确的根因结论 + 回归测试锁定；本轮交付物与 `complete=false` 的判定一致；不出现「为凑 Word 而放行或用尽预算」的动作。

### P7 合并/切换决策与收尾（规模 M，依赖 P2/P6）

1. 决策点：按 D3 保持隔离的前提下，给出「是否合入 main / 是否把默认 preset 切到结构化链」的结论与代价（不允许无限期悬置）。
2. 若合入：先让 main 保持可独立验收（P1/P2 已绿），再以实验分支为源做一次合并，重新跑双口径全量 + 冻结语料 + 回放快照；合并后根仓软链即让桌面插件指向结构化链，需再次做一次 P2 的宿主验收。
3. 文档同步：`README.md`、两份 `PROCESS_REWORK.md`、`IMPLEMENTATION.md`、`packages/dsh-jiaodui/README.md`、ADR、双 skill 副本与 `references/`。
4. `git diff --check`；不 push（除非用户明确要求），不改 profile。

## 3. 决策（2026-10-09 已确认）

| # | 决策 | 结论 | 对计划的影响 |
| --- | --- | --- | --- |
| D1 | main 入口精简是否允许把 §8 命令速查整体移出 SKILL.md | **允许移出** | P1 按 §3.0/§8 外移执行；必要性口径见 §0.1（有条件触发，故不作阻塞项） |
| D2 | 无损编码方案 | **走 ①：v2 正文内反斜杠转义 + 唯一反转义入口** | P3 按此写 ADR 0006 与实现；若字段内 `\` 与 `\|` 的历史歧义无法覆盖全部字面，再回来评估换分隔符方案（需重新决策） |
| D3 | 实验分支归宿 | **保持隔离** | P7 只做「是否合入」的决策讨论，不先合；根仓继续常驻 main，桌面插件软链不接触实验链 |
| D4 | 2 个失败回放单元 | **先修工具缺陷，不开新轮次** | P6 改为：本轮 15 个未开始单元续跑 + 2 个失败单元只修工具根因并用回归锁定、**不重派**；本轮 `complete=false`，只交诊断 + 失败清单，不出正式 Word；是否开新轮次由用户另行授权 |

## 4. 不变量与工作纪律

- `verify-report` 是唯一闸门；任何批次都不得以放宽校验换取通过。
- 不改源文件；不删历史失败留痕；不刷新失败预算；失败单元交人裁定。
- 确定性层红→绿；测试预期值来自规格/已知样本，不用实现重算。
- 双 skill 副本、双学科配置副本必须字节一致，由测试锁。
- 根仓常驻 main；实验只在 `.worktrees/structured-report`；桌面插件软链跟随根仓，**不要在根仓切到实验分支**。
- 宿主相关项只由真机新会话判定，模拟/仓内测试不替代；替换已安装 JS 包需重启。
- 每个批次独立可审：一次提交对应一批，附测试结果与命令记录。

## 5. 每批统一验收命令

```bash
# 双口径全量（在对应工作树内）
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -o addopts='' -q -rs

# 实验 worktree 跑旧语料交叉验证时补语料路径
JIAODUI_LEGACY_CORPUS=/Users/chouchou/开发/JiaoDuiAgent/output .venv/bin/python -m pytest tests/test_legacy_corpus.py -q

# 冻结语料交付对账（CI 口径）
.venv/bin/python -m pytest tests/test_m1_fixture.py -q
```

计数用 `--junitxml` 复核（本机 `pytest -q` 不打印汇总行）：`tests / failures / errors / skipped` 四项必须有记录。

## 6. 风险与止损

| 风险 | 止损 |
| --- | --- |
| 裁剪入口时连带删掉硬约束，行为漂移 | P1 第 5 项的七条核对清单 + operation-manual 锚点测试 + P2 真机新会话读全文 |
| 长会话/溢出压缩把入口中间 9,256 码点换掉（§0.1） | 精简到阈值内 + P1 第 6 项的重载提示（先重新 `skill`，再 `read` 分页）；不做「靠模型自觉」以外的假设，P2 记录实测 |
| 转义改动波及 verify/docx/parse/repair 四个消费点 | 唯一反转义函数 + 旧语料逐份标注 + v1 不做转义 |
| 信封契约改动使 `split_marked_body == source_text` 严格性下降 | 保持严格相等；只扩大可表达字符集与显式 skip，不引入相似度 |
| 宿主验收依赖重启，占用用户时间 | P1 完成后一次性做 P2；未出结果前不宣称 M6 完成 |
| 把调度智能写进提示词冒充 M5 完成 | M5 完成判据限定为 core 可见的分类/记账/判据，提示词不算实现 |
| 实验分支长期不合并导致双线维护成本 | P7 强制给出合并/切换结论与代价，不允许无限期悬置 |

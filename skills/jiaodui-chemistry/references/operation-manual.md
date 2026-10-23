# 校对CLI操作参考

仅在需要核对命令参数时读取；完整参数以 `jiaodui <command> --help` 为准。

## 工作区和目录

`W` 是当前会话工作区。新材料位于 `W/校对/<材料名>/`，单元根目录是 `units/<材料名>/`，单元目录是其直接子目录。所有写命令必须使用宿主注入的工作区；`--work-root` 只能等于该路径，不能用于改变产物位置。

拆分后的 `task_id` 和 `unit_ids` 由 CLI 返回并保存在材料清单中。单元子代理使用这两个 ID，不拼接材料或单元长路径来调用结构化工具。ID随材料搬移保留，查找范围仍限于当前工作区。

## shell 与原生工具的边界

- 确定性操作（读取、计算、提交、恢复记账、复核、交付）**一律走原生 `jiaodui_*` 工具**：这些工具自带工作区校验，类别、预算与闸门都由 core 决定。
- shell（bash / pwsh）只用于**观察与修复**：解 docx 看内部 XML、核对文件与摘要、跑一次性诊断脚本、定位失败根因。父 agent 有 shell，**子 agent 没有**——子 agent 只能通过 `unit-submit` 交结构化提案，这是「模型不写报告」的落点。
- **不要在 shell 里用 `python -m jiaodui`**：editable 安装的元路径查找器排在 `PathFinder` 之后，cwd 决定导入哪条线的 core（实测：会话工作区是主仓时会读到主仓的 `jiaodui`，行为完全不同）。确需在 shell 调 CLI 时用已安装的控制台脚本 `jiaodui`；带 `--work-root` 的写入命令仍必须传对工作区。
- shell 里的写入同样受约束：产物只落 `校对/<材料名>/`、不改源文件、失败留痕用契约文件名，不新建自由命名的 attempt / 副本。
- **`jiaodui` 可能不在 PATH**（`which jiaodui` 为空）。bash 退路先读 `check-env` 输出里的 `runtime.cli_path`，用这个绝对路径调用；不要猜 `.venv-cli/bin/jiaodui`，也不要假定当前 shell 能直接解析 `jiaodui`。

## 入口和准备

正常路径调用结构化工具 `jiaodui_task_prepare`（`operation` 取 `check-env` / `inspect-source` / `inspect-images` / `convert` / `split` / `precheck-split` / `status` / `execution-policy`），参数按名传入，不再手拼命令行。
下面的 CLI 写法只在没有该工具（或需要上面没登记的参数）时作为退路：

```text
jiaodui check-env [--expect-schema-version 2|3 --expect-bundle-version V --expect-schema-file PATH]
jiaodui inspect-source <file> [--preview-chars 0..2000] --json
jiaodui inspect-images --unit <unit_dir> --json
jiaodui convert <file> --mode exam|lecture [--material-name NAME] --work-root W --json
jiaodui split <raw_md> --subject 高中化学 --mode exam|lecture [--strategy rule|manual|none] --work-root W --json
jiaodui execution-policy <material_dir> --mode automatic|interactive --origin user|confirmed --work-root W --json
jiaodui precheck-split <paper_dir>
jiaodui status <paper_dir> --json
```

`check-env` 的 `contract` 项比对插件声明的提案 schema 版本、bundle 版本与核心实际能力，并在提供 `--expect-schema-file` 时逐字段比对 schema 内容；新版 CLI 在这些不一致时失败，旧 CLI 会因不认识探针参数直接 exit 2。**不要把它当成本地依赖检查**。`inspect-images` 按正文顺序列出图片引用与实际读取图，派发单元前先跑。

`split` 可选 `--rerun` 开新轮；单元集合变更须显式 `--replace-units`，陈旧单元移入 `.superseded/<run_id>/`，只移动不删除。人工接纳现有集合用 `--adopt-units`。`convert` 另有 `--out-dir`、`--base-name`、`--mathjax`；`split` / `slice` 另有 `--base-name`、`--out-root`、`--no-clean`。材料类型来源可用 `--mode-origin` / `--mode-reason` 登记。所有选项以 `jiaodui <command> --help` 为准。

**重跑与集合变更走原生工具，不要退回 bash**：`jiaodui_task_prepare`（operation=split）已经暴露 `rerun` / `replace_units` / `adopt_units` / `out_root` / `base_name` / `images_dir`（布尔项传 `true`）。这些开关原先只有 CLI 有，实测导致父代理去 bash 里猜 `.venv-cli/bin/jiaodui` 的绝对路径（`jiaodui` 不在 PATH，先 exit 127），并且**绕过了原生工具自带的「`--work-root` 必须等于当前会话工作区」校验**。只有 `slice` 的边界清单仍按第 3 步走 `jiaodui` argv 工具。

**流程顺序是硬约束**：`convert → split → execution-policy → 派发单元`。`convert` / `split` / `slice` 在参数或单元集变化时会**开启新轮次**（含 `--rerun` / `--replace-units` / `--adopt-units`），而执行模式授权绑定轮次——先登记再拆分会让授权立即失效，子代理派出去后会在第 1 步被 `execution-policy-required` 拒绝。因此登记要放在拆分之后、派发之前；`split` 一旦开了新轮次会在返回的 `warnings` 里显式提示，看到该提示必须重新登记。

## 智能切片覆盖与明确节选

`slice` 默认 `scope=full`，边界使用与预览相同的 mode/subject/清理参数下的 1 基、含端点行区间。清理后所有非空行（包括标题）必须恰好覆盖一次；漏行或重复返回 `slice-coverage-invalid`，`details.uncovered_ranges` / `overlapping_ranges` 给出连续区间，写盘前拒绝。非法或越界行号返回 `invalid-boundaries`，不再自动收敛或生成空单元。

```json
{"raw":"...","mode":"lecture","subject":"高中化学","scope":"full","boundaries":[{"name":"单元1","start_line":1,"end_line":20}]}
```

只有用户明确要求节选时才使用 `"scope":"excerpt"` 和非空 `"scope_reason"`；CLI 对应 `--scope excerpt --scope-reason "用户指定范围"`。节选可留下未覆盖行，但已选行仍不能重复。历史 `text` 边界仅在明确节选时兼容，返回 `coverage.checked=false`，不宣称文本来自源文或全量覆盖。

切片 JSON 与 `precheck-split` 返回 `coverage`，新布局将它写入当前参数及轮次 action；范围变化开启新轮。整卷报告和 Word 交付携带同一摘要，节选交付正文标出原因；其 `complete=true` / Word `ok=true` 仅表示所选单元完成，不代表全材料完成。人工 `manual` 和整篇 `none` 策略继续按各自约定处理。带切片摘要的材料若使用 `--adopt-units`，旧覆盖核验失效，改记人工接纳范围（`checked=false`）；要重新确认全量覆盖须再执行 `slice --replace-units`。

## 单元身份和提交

正常入口提交 schema v3 原文修订：先读单元、真实读图和按需实算，再交「原文、改为、原因、证据」。父代理只派路径和身份，单元子代理自行读取，模型不写报告正文。

1. `jiaodui_unit_snapshot` 获取 `snapshot_sha256`、源文/图片/数据/报告摘要和当前轮次信息。返修时传 `with_proposal: true`（CLI：`jiaodui unit-snapshot --task-id T --unit-id U --with-proposal --json`），返回的 `proposal` 为当前 `proposal_revision` 与精简 `corrections` 列表（id、old_text、new_text、reason、category、severity）；没有可继承的当前提案时（未提交、上一轮或未登记数据）为 `null`。
2. `jiaodui_unit_read` 使用 task/unit ID 分页读取源文，图片路径取自同一份实际读取清单；单次最多2000行，后续页递增 `start_line`。清单的 `read_paths` 是按正文顺序去重的实际读取路径，读图时逐字复制，**不要自行拼接或增删目录层级**。通用 DSH `read` 读取参考文件时每次 `limit` 同样不超过 2000；需要更多行时按实际返回范围递增 `offset`，不要把被截页误当成全文。
3. 用真实 `read_image` 逐图核对可读内容及图文归属；按学科规范调用 `jiaodui_calc_<operation>` 实算，计算时绑定本单元 `task_id` / `unit_id`，保留返回的 `call_id`。首轮 `unit_evidence` 分为 assumptions（假设和核验依据）、symbols、images、calculations；无问题也保留核验依据。
4. `jiaodui_unit_submit` 的外层给 `task_id`、`unit_id`、`expected_snapshot_sha256` 和下述 `proposal`。身份、源文摘要、提案版本由 core 绑定，`summary` 按有效修订最高严重度推导，空集为“无问题”，模型不用填写。`preview: true`（CLI `unit-submit --preview`）可整包预检；正式提交会从不可变源文生成全文报告，编译为 v2 后走既有图片/calc 证据校验与 `verify-report`，通过后仍须父代理复核。

### 完整提案

```json
{
  "schema_version": 3,
  "corrections": [{
    "id": "c1",
    "old_text": "甲",
    "new_text": "乙",
    "reason": "此处指代应与题干中同一对象的名称一致。",
    "category": "term",
    "severity": "一般问题",
    "evidence_ids": ["e1"]
  }],
  "unit_evidence": {
    "assumptions": [{"id": "e1", "text": "已核对题干对象定义及前后指代。", "source_locations": []}],
    "symbols": [],
    "images": {"status": "not_applicable", "reason": "本单元源文没有图片引用。"},
    "calculations": {"status": "not_applicable", "reason": "本次对象指代核验不涉及计算。"}
  },
  "self_check": {
    "status": "passed",
    "checks": ["real_issue", "replacement_semantics", "related_coverage", "scope_and_uncertainty", "severity"],
    "unresolved": []
  }
}
```

- 每条修订必须有单元内唯一 `id`、`old_text`、`new_text`、`reason`、`category`、`severity`、`evidence_ids`。原文从单元逐字复制；`new_text` 为空表示删除，不能做零宽插入或纯图片替换。
- `evidence_ids` 只引用单元级证据；还可给该修订附可选 `evidence` 数组，条目 `kind` 为 `assumption` / `calculation` / `image`，其余字段沿用对应证据项。局部证据由 core 关联本修订，不必把其 ID 重填进 `evidence_ids`；仅使用局部证据时后者可为 `[]`。所有修订与证据 ID 避免重名。
- 原文重复时才补可选 `context_before`、`context_after` 或从 1 开始的 `occurrence` 消歧。找不到、不能唯一定位、切断公式/加粗或有效修订重叠时，按提交诊断修正，不猜位置、不改源文。优先逐字精确定位，归一化只沿用 core 已有的受限规则。
- 无问题提交 `corrections: []`，保留 `unit_evidence`，`self_check.checks` 改为 `["no_issue_review"]`；不能通过删掉真实发现来凑空集。

### 证据和自查

- `unit_evidence` 必须含 `assumptions`、`symbols`、`images`、`calculations` 四键。assumptions 至少有一条真实假设/核验依据；symbols 无内容写 `[]`。images / calculations 只有“证据数组”或确实不适用的 `{"status":"not_applicable","reason":"<原因>"}` 两种形态。
- 有图时单元级 images 必须覆盖全部正文引用：每项给 `id`、`reference_index`、`readable: true`、`semantic`（关键坐标/方向/标注等实际所见）、`verdict`（图文是否一致）。路径和位置由 core 从当前清单回填；真实读图不能省略。局部 `kind: "image"` 只补该修订的观察，不能替代单元级图片覆盖。
- calculations 每项给 `id`、`call_id`、`expression`、`result`。**`result` 抄 `result.result` 的原生 JSON 值**：数字写 `8.0` 而非 `"8.0"`；`dimensional` 对象与 `formula` 多解对象整体照抄，不手打摘要或擅选唯一根。多参数调用的 `expression` 复制其中一个参数的原样值（含空白）：`equality` 用 `expression_a`/`expression_b`、`formula` 用 `formula`/`solve_for`、`vector_ops` 用 `vector_operation`；不要用 `==` 或函数调用式拼接。引用上一轮或另一份源文的调用会被拒绝。
- `self_check.status` 为 `passed`、`unresolved` 为 `[]`。含有效修订时 `checks` 必须覆盖五个字面量 `real_issue` / `replacement_semantics` / `related_coverage` / `scope_and_uncertainty` / `severity`，不要加冒号说明后缀。检查的是本次提交后全部有效修订，不只新增项。
- `unit_id` 不存在时按 `not_found.details.known_units` 与 `suggestion` 重取，不重试同一串 ID；证据形状和 calc 绑定错误按实际诊断逐项修正。

### 增量返修

先重取带 `with_proposal` 的当前 snapshot；`base_proposal_revision` 必须是当前同轮、同输入的已提交版本。下例撤回 c1 并新增 c2，未列出的旧修订继续保留：

```json
{
  "schema_version": 3,
  "base_proposal_revision": 1,
  "withdrawn": [{"id": "c1", "reason": "收敛修改范围，保留完整对象名称。"}],
  "corrections": [{
    "id": "c2",
    "old_text": "甲物体",
    "new_text": "乙物体",
    "reason": "此处应沿用题干中同一对象的完整名称。",
    "category": "term",
    "severity": "一般问题",
    "evidence_ids": ["e1"]
  }],
  "self_check": {
    "status": "passed",
    "checks": ["real_issue", "replacement_semantics", "related_coverage", "scope_and_uncertainty", "severity"],
    "unresolved": []
  }
}
```

- `withdrawn` 是 `[{id, reason}]`，每次撤回需解释原因；`corrections` 只放新增修订。改一条就是撤回旧 ID 并新增 ID，不重抄全部提案，不复用旧 ID。
- `unit_evidence` 省略则继承，给出则整体替换；不要用 `{}` 表示继承。撤回修订的局部证据随之移除，沿用继承证据修剪；共享证据和单元图片覆盖保留。修剪后若缺必要单元依据，须补齐再提交。
- **每次重新提交 `self_check`**；撤回后没有有效修订时用 `no_issue_review`。外层仍提交最新 `expected_snapshot_sha256`；基础版本或 snapshot 过期即重读当前 snapshot，不手工递增版本、不自行合并冲突。
- 定位/结构诊断沿用宿主有限重试和现有恢复预算，不新增持久定位失败计数。只修有依据的原文、消歧或修订范围；**重复诊断仍无法解决即停止该单元**，按失败契约留痕并回报，不为凑“无问题”丢弃发现。

## 显式 v2 兼容

只有明确使用旧提案时调用 `jiaodui_unit_submit_v2`；CLI `unit-submit` 仍按 `schema_version=2` / 3 分派，schema 可用 `jiaodui unit-schema --schema-version 2`（正常入口用 `--schema-version 3`）查看。v2 的 correction 使用 `location_id`、`expected_original`、`replacement`，顶层为 `evidence` 与 `summary`；先用 `unit-locate` 取得位置，`expected_original` 必须逐字复制其 `original` 整段，不能截子串。

v2 外层仍需 `task_id` / `unit_id` / `expected_snapshot_sha256`。插件透传 `--bind-current`，CLI 可显式使用：core 在锁内绑定 task/unit/run 身份、source/body hash 和下一个 `proposal_revision`；显式冲突拒绝。不绑定时须按完整 v2 schema 填齐身份版本。兼容提交继续经过证据、图片、verify 和父复核，不作为定位失败的旁路。落盘仍为 v2，竖线与标记括号由程序转义无损承载（ADR 0006）；旧 Markdown 报告继续由 verify/parse/repair 显式兼容。

## 恢复与事件

执行模式记录后，以 `unit-recovery` 按 `unit_id`、**`--attempt-id`（幂等键）**、**失败错误码**与稳定 failure payload 消费有限预算：DSH 原生工具传 `failure: {message, details?}`，core 派生 SHA-256；CLI 对应 `--failure-json`。旧 CLI 仍可提供真实 `--fingerprint`，但禁止全零/全一占位值。`--attempt-id` 必须与该单元 `unit-event` 登记的 attempt_id 一致；每个新的恢复动作创建新 attempt 并先登记对应事件，同一 attempt 只可原样重放。可选 `--expected-run-id` 作 CAS 防护（与当前轮次不一致即 `run-changed`）。恢复类别由错误码确定性决定，不由模型自选——`usage`/`not_found`/`unsupported`/`*stale` → `call_correction`；`calc_failed`/`calc-evidence-invalid`/`proposal.calc-*` → `calc_representation`；`verify_failed`/`contract`/`out-of-contract`/`syntax.*`/`integrity.*`/`original.*`/`locate.*`/`report.*` → `report_repair`；`images.*`/`images-invalid` → `image_schema_fix`；`env`/`host-timeout`/`host-crash`/`parent-technical-timeout` → `technical_redispatch`。未分类的错误码会被拒绝并给出相近的已知码；用户取消与权限拒绝**不可恢复、不消耗预算**；只有父代理判断类的 `targeted_review` 可以不带错误码。**错误驱动的恢复请省略 `category`**——类别由错误码确定性派生；若填了但与映射不一致会整次被拒，`details.expected_category` 直接给出应填值（第 12 讲实测父代理批量填错类别，4 次调用全部作废后重发）。指纹非法返回 `invalid-attempt-fingerprint`。**`image_schema_fix` 会连带扣一次 `call_correction`**（图片格式修复本身要占一次调用）；任一被扣类别余额不足即整次拒绝，返回 `allowed=false` 并给出 `blocked_category`，**不做部分扣费**。成功时返回 `charged` 列出本次实际扣减的类别。换 agent 或更换指纹不能重置同轮计数。`unit-event` 只记录阶段、attempt、agent（**要求当前轮次已确认执行模式**，没有授权就不留下工作痕迹），可选 `--expected-run-id` 作 CAS 防护；**它不接受任何取消参数**。取消走独立工具 `jiaodui_unit_cancel`（`initiator` 与 `reason` 必须配对，`--revoke` 可撤销技术性取消），同样要求当前轮次已授权，且**只由父代理或宿主调用——子代理 preset 的 `toolset: unit` 不含该工具，单元子代理无法自证取消**。user取消不重派、**不可撤销**；parent技术取消不得记作user取消，撤销后即可继续补位。只读的 `jiaodui_unit_progress`（`jiaodui unit-progress --task-id T [--unit-id U] [--stale-after-seconds N]`）汇总每单元的 `phase` / `attempt_id` / `agent_id` / `last_event_at` / `age_seconds` / `event_count` / `in_flight` / `stale` / `cancelled`：终态为 `registered` / `parent_reviewed` / `deliverable`；被显式取消的单元不再算在途。父代理据此判超时与补位，不靠沉默时间猜崩溃；该命令只读，不改材料记录。补位与停止判据用只读的 `jiaodui_dispatch_plan`（`jiaodui dispatch-plan --task-id T [--window N]`，默认窗口 8）：返回 `dispatch`（下一批可派发单元，已排除在途单... (line truncated to 2000 chars)

派发后必须为每个在途单元记一次 `unit-event`（至少覆盖 `prepared` / `read`）；否则 `dispatch-plan` 的 `in_flight` 只能靠父代理内存推断，滑动窗口与补位判据会失真。

## 父代理复核

技术提交后，先生成整卷报告通读全文和证据。`unreviewed` 列出待审单元，但全文可读；complete 仍 false。复核与交付是**两趟 build-report**，顺序不能改：

1. `jiaodui_delivery`（operation=build-report）生成审阅全文；
2. `jiaodui_unit_snapshot` 取**生成报告之后**的新 `snapshot_sha256`（此时 hash 才包含 report_sha256 / data_sha256）；
3. 用该 hash 调 `jiaodui_unit_review`，decision 为 accepted 或 needs_revision；退回需 issue；
4. **复核后再跑一次 build-report**，登记当前复核结果，`complete` 这时才会变 true；
5. 最后 `jiaodui_delivery`（operation=build-docx）。

若在 build-report 之前取 snapshot，复核必然 `snapshot-stale`；若复核后不重跑 build-report，`complete` 会一直是 false。任何版本变化后重新取 snapshot、重新复核。Word 只允许当前版本已 accepted。

通读时若发现 **≥3 个单元在同一处问题或同一口径上漏标**，按系统性问题处理：用 `unit-recovery` 的 `targeted_review` 向全部单元下发定向复核，不要只修已发现的单元；最终仍以当前 snapshot 复核为准。

## 交付

正常路径调用 `jiaodui_delivery`（`operation` 取 `build-report` / `build-docx`，`paper_dir` 为拆分返回的单元根目录）。它的 `json` 字段直接给出 `ok` / `complete` 与结构计数，不必自己解析 `stdout`。CLI 退路：

```text
jiaodui build-report <paper_dir> --work-root W --json
jiaodui build-docx <paper_dir> --work-root W --json
```

`build-report` 的 `ok` 表示诊断报告文件已生成；只有 `complete: true` 才表示所有单元均已通过或显式跳过。任何失败占位意味着整卷尚未正式完成。Word交付还必须检查结构化 `ok: true`，缺失、记账异常或图片未嵌入均不交付。批注内公式降级会分 `dependency_missing` 与 `syntax_unsupported` 两类告警并列出失败公式原文；matplotlib 可用时按语法不支持排查，不要改去装依赖。不执行最终Word分页或截图验收。

- 全局选项：`--json`、`--quiet`、`--work-root`、`--version`。
- 历史Markdown报告兼容读取：`jiaodui verify-report` / `jiaodui parse-report`；仅旧报告可用完整性辅助 `jiaodui repair-report --unit <unit_dir> [--apply]`，应用时原子替换并复验。

## 只读与计算

`unit-locate`、`unit-snapshot`、`calc-schema` 为只读命令。计算优先调用 preset 中按operation区分的 `jiaodui_calc_<operation>` 工具；参数schema从 `jiaodui.calc.OPERATIONS` 元数据导出，未知字段拒绝。成功响应回显 `params`（实际记账参数）；`calculations[].expression` 直接从中复制某个字符串参数的原样值，不凭记忆重写。CLI 退路：

```text
jiaodui calc <op> --param NAME=VALUE ... [--subject 高中化学]
jiaodui quantities --subject 高中化学 [--search 关键词]
```

**化学 v1 的量表为空**：`quantities --subject 高中化学` 稳定返回 `count: 0`，`calc dimensional` 传入 `{"quantity": …}` 时**没有量表可交叉校验**。化学计算一律按题面写显式单位表达式（如 `"mole/liter"`、`"gram/mole"`、`"kilojoule/mole"`）或 `"dim:…"`，不要臆造化学量名。

稳定退出码为 0–7；用户中断为 130。插件超时/子进程失败使用 `exitCode: -1` 并返回 `stdout / stderr / truncated`。

## 新布局与人工兼容

新布局正常交付只走结构化 `unit-submit` 和父代理 `unit-review`，报告由 core 生成并登记。新布局中的 v1 Markdown 报告仅作显式人工兼容：`parse-report --manual-legacy` 或 `repair-report --apply --manual-legacy` 只写单元数据并标记 `legacy_manual`，不登记、不计入本轮完成，`status` 与下游交付仍按未完成处理。无新布局材料清单的历史布局继续兼容旧 parse/repair 行为；人工兼容不算新契约完成。

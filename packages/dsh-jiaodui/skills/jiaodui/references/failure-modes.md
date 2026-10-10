# 失败模式与自修指引

`verify-report` 的每个失败都带结构化 code 与位置。报告机械修复最多 3 次并记 `report_repair`；工具参数/schema 修正最多 2 次并记 `call_correction`；计算输入的表示/传输机械修正最多 2 次并记 `calc_representation`；定向复核最多 2 次并记 `targeted_review`；技术性重派最多 1 次并记 `technical_redispatch`。read_image schema 修正同一次 attempt 同时扣 `image_schema_fix` 与 `call_correction`，两类各计一次、不能合并成 4 次额度。六类预算都按单元、按 run 独立；入口提问不占这些预算。新 run 未显式执行 `execution-policy` 前，unit-event/recovery 必须拒绝写入。每次 event/recovery 都带 `attempt_id` 与请求载荷的 64 位小写 SHA256 fingerprint（不含 attempt_id/时间戳）：相同 attempt 重放幂等；相同 fingerprint 的不同 attempt 仍扣预算，不能因 agent 变化刷新。实质性判断争议在 interactive 模式询问用户。用户取消与权限拒绝只记录、不恢复、不重派。

## 一、格式型失败（最常见）
| 症状（code / 现象） | 自修动作 |
| --- | --- |
| 缺严重度行（`severity.missing`），或写成裸「无」「没问题」 | 在报告头部补总结行，取值只允许 `无问题 / 轻微问题 / 一般问题 / 严重错误`，且与正文标记情况一致 |
| 严重度非法（`severity.invalid`） | 只允许四个合法值；删掉自造写法（如 `总结：无`） |
| `无问题` 却含标记（`severity.contradiction`） | 二选一：按实际改严重度，或删掉不应存在的标记；两者不能并存 |
| 缺 `### 标记原文` 或 `### 修改原因`（`sections.missing-marked` / `sections.missing-reasons`） | 补齐两节；无问题也要写全，修改原因写「无」 |
| 用三反引号 / 波浪线围栏包裹正文 | **去掉围栏**，两节内容直接输出 Markdown 正文；同时删除 `编号：` / `内容：` 信封行 |
| 标记落在 `$...$` 或 `**...**` 内部 | 把标记移到公式 / 加粗**外侧**；整段公式要改就整段作为原文字段，或改写整段解析 |
| 括号 `【` / `】` 不配对（`syntax.unbalanced-brackets`）或编号后缺竖线（`syntax.malformed-marker`） | 用 `【编号|原文|改为】` 重写；补齐 / 删除多余括号；编号后用英文竖线，原文字段内竖线写成反斜杠竖线 |
| `$...$` 未配对（公式配对扫描异常、docx 公式兜底缺失） | 逐行检查美元符号成对；转义美元写成反斜杠美元；源文是 `\(\)` 形态时按 converter 实际输出修正 |

## 二、编号与原因对应失败
| 症状 | 自修动作 |
| --- | --- |
| 标记缺原因（`reason.missing`） | 给每个标记补一条 `编号. 原因`；编号从 1 起连续 |
| 原因多出编号（`reason.orphan`） | 删掉没有对应标记的原因；核验说明改成非编号段落 |
| 编号重复（`marker.duplicate-num`） | 每个编号只出现一次；多个问题用不同编号 |
| 原因行没被识别（正文被当原因或原因被当正文） | 编号行必须**行首锚定**且用 `.` / `)` / `、` 分隔；不要用纯空格分隔 |

## 三、图片资源失败（`images.*`，**改报告无法自修**）

引用与资源绑定由拆分阶段决定，只改 `_校对报告.md` 过不了闸门。子 agent 遇到 `images.*` 失败应**停止自修**，回报主 agent：检查源文引用与单元 `images/`，必要时重跑 `split`。

| 症状 | 自修动作 |
| --- | --- |
| 缺图（`images.missing`）/ 无效引用（`images.invalid_reference`） | 不删引用逃避：确认拆分已把图片复制进单元 `images/`；源文本身缺图须回源文件处理 |
| 远程引用（`images.remote_unsupported`）/ HTML `img`（`images.unsupported_syntax`） | 改用本地 Markdown 图片引用 `![alt](./images/x.png)`；远程 URL 与 `<img>` 不支持 |
| 图片无法解码（`images.unreadable`）/ 格式不支持（`images.unsupported_format`） | 换受支持格式（PNG/JPG 等）；损坏图片回源文件重转 |
| 白底副本缺失（`images.white_background_missing`）/ 白底图损坏（`images.white_background_unreadable`） | 不能手改报告规避：重跑 `split` 重新生成白底副本；历史布局用 `--legacy-layout` |
| `images/` 有未被正文引用的图片（`images.extra_images`，warning） | 不拒绝；确认是否为漏引用的配图，必要时在报告正文补引用 |

## 四、内容型失败（触及源文）
| 症状 | 自修动作 |
| --- | --- |
| 空原文（`original.empty`） | 原文字段填写**被修改的源文原句**，逐字抄录 |
| 空操作（`original.noop`，原文 == 改为） | 删除该标记，或把「改为」写成真正不同的修正文本 |
| 原文字段与源文不符（`original.not-locatable`，源文此处其实是「改为」） | 按源文逐字改正原文字段；不要凭印象写原文 |
| 缺段（`integrity.missing-paragraph`） | 从源文补回缺失段落；`### 标记原文` 必须是完整源文，不是只写被改句 |
| 多段 / 改变未标记正文（`integrity.extra-paragraph` / `integrity.changed`） | 删除报告中源文没有的段落；未标记正文必须与源文逐字一致 |
| 重段（`integrity.duplicate-paragraph`） | 删除重复段落，保持与源文段序、段数一致 |
| 原文字段定位不到（`locate.unknown`，warning） | 不改也可通过；建议核对 LaTeX 装饰（转义美元、空格、零宽字符）后重抄原文字段 |
| 改为与原文无法区分（`marker.manual-review`） | 不拒绝；请把「改为」写成实际不同的修正，或在原因中说明该处差异 |

**程序化重建（`repair-report`，不改源文）**：`integrity.missing-paragraph` / `integrity.extra-paragraph` / `integrity.changed` 若由未标记正文被转录改动引起，可先运行 `jiaodui repair-report --unit <dir>` 预览。它只从单元源文重建 `### 标记原文`，把原报告的完整标记插回源文对应位置；字段在源文中**必须唯一且逐字命中**，标记顺序单调、区间不重叠。预览给出 diff 与每个字段的源文行号；确认后用 `--apply` 原子替换报告并自动复验，复验失败恢复原报告。字段找不到、命中多处、乱序、重叠、编号重复、语法 / 原因 / 严重度无效或图片检查失败一律拒绝，原报告不变。修复不判断「改为」或原因是否正确；`verify-report` 仍是唯一闸门，修复通过后仍须重跑 verify-report 再 parse-report 登记，修复不自动登记、不生成汇总或 Word。

## 五、环境与报告缺失
| 症状 | 自修动作 |
| --- | --- |
| 报告为空（`report.empty`） / 找不到报告（`report.missing`） | 写出完整 `_校对报告.md`（含头部总结行 + 两节）后再自检 |
| 报告写入调用报语法或转义错误（如 `Unterminated template` / `Expected unicode escape`） | 不把报告正文拼进 JS/TS 模板字符串或 shell 命令；后续修复按第七节使用正确转义的结构化 `write` 参数；本次停止，不自行重试。保留完整错误并写 `_校对失败.md`，未执行的 verify / parse 明确写明 |
| `edit` 报旧文本未匹配 | 先读取当前报告，使用唯一且逐字一致的 `old_string`；匹配失败即停止并留痕，不猜测替换文本或继续登记 |
| Harness `run_code` 外层参数校验失败（如 `invalid justification`） | 内层程序和工具尚未执行；按当前外层 schema 检查必填字段，`justification` 用非空完整句子。保留完整错误并注明实际阶段；用户要求遇错即停时不重试，也不记作 CLI 执行失败 |
| 找不到单元源文（`integrity.no-source`，**error → 拒绝**） | 确认单元目录名与源文名匹配（`第N题.md` / `单元N.md`）；必要时用 `--source` 指定 |
| 工具参数校验错误 | 若修正只是恢复 schema 所需字段、类型或 JSON 格式，最多 2 次并记 `call_correction`；不可更换题意或命令来绕过失败。超过预算停止并留痕 |
| 计算输入解析错误 | 仅对缺字段、类型或表达式表示/传输格式做最多 2 次机械修正，记 `calc_representation`；不得更换题意、假设或目标来绕过失败。实质性计算争议按模式处理 |
| `proposal.calc-call-mismatch`（`expression` / `result` 与记账不逐字一致） | 按报错列出的「字段=取值」逐字抄回**其中一个**参数；多参数调用（`equality` 的 `expression_a`/`expression_b`、`formula` 的 `formula`/`solve_for`）没有唯一 `expression`，**不得用 `==` 自行拼接**，要两条证据就分条记录两次调用。`result` 抄 `result.result` 原值（`dimensional` 返回对象，不是布尔）。机械修正记 `calc_representation` |
| 读图报 `cannot read ... not found`（自行拼接目录层级） | 路径只能逐字复制 `jiaodui_unit_read` / `inspect-images` 清单里的 `read_paths`（或 `actual_read_path`），不得自行拼接、增删 `units/<材料名>/` 层级或改名。这是抄写错误，记 `call_correction`；不属 schema 错误，**不扣 `image_schema_fix`** |
| 工具报 `not_found`：unit_id 不存在 | 读 `details.known_units`（本材料全部「单元名 → unit_id」）与 `details.suggestion` 逐字重取；不要用同一串重试。unit_id 长且易抄错，优先从 snapshot / unit-read 返回值复制 |
| 工具报 `not_found`：`task_id` 显示为字面量 `undefined` | 这不是「材料不存在」，而是**顶层参数漏传 `task_id`/`unit_id`**（结构化工具把缺省值序列化成了该字符串）；报错会明确写出这一点。补齐顶层 `task_id` 与 `unit_id` 后重试，不要换材料或换命令 |
| `location.original-mismatch`（位置原文与 `expected_original` 不一致） | `expected_original` 必须**逐字复制 `unit-locate` 返回的 `original` 整段**——`location_id` 已绑定源文摘要，命中的区间就是原文字段，只截取子串必然失败。报错会同时给出「实际命中的原文」与「你写的值」，照抄前者即可。要改区间内的片段时，先把 `unit-locate` 的 `phrase` 收敛到该整段、整段写 `replacement`。机械修正记 `call_correction` |
| `proposal.schema`（建议字段缺失或包含未支持字段） | 报错会点名**缺哪个键、多哪个键**并列出允许的顶层字段，照着补齐或删除即可，不要整体重写。最常见的是把 `task_id`/`unit_id` 嵌进 `proposal` 却漏了工具顶层参数（或反之）——两处都要给。机械修正记 `call_correction` |
| `proposal.self-check-incomplete` / `proposal.self-check` | `checks` 只接受五个字面量 `real_issue` / `replacement_semantics` / `related_coverage` / `scope_and_uncertainty` / `severity`（无问题单元为 `["no_issue_review"]`），**不要写 `real_issue: 说明…` 这类带后缀的串**；报错会逐项列出缺哪些。`status` 必须是 `passed`、`unresolved` 必须为空数组 |
| `proposal.evidence-assumptions` / `-symbols` / `-calculation(s)` / `-images` | 报错会指明**第几项、缺哪个字段或实际收到的形状**，按位置补齐该字段即可，不要重写整份 evidence。`symbols` 无内容时写 `[]`（不是省略或 `null`）；`images`/`calculations` 只有「证据数组」或 `{"status":"not_applicable","reason":"…"}` 两种形态 |
| `proposal-revision-stale` | 报错会给出**当前已登记 revision** 与应填值；按它 +1 提交，不要试探性加减。被拒的建议不写盘，重放同一 revision 也仍会拒绝 |
| `execution-policy-required`（当前轮次尚未确认执行模式） | 授权**绑定轮次**：`convert`/`split`/`slice` 开新轮次（含 `--rerun`/`--replace-units`）后旧授权立即失效。这不是单元失败、不消耗恢复预算；由**父代理**重新运行 `jiaodui execution-policy <材料_dir> --mode … --origin … --work-root <W> --json` 后再重派该单元。`split` 开了新轮次时会在 `warnings` 里显式提示 |
| 读图参数错误（missing required property / invalid arguments） | 核对当前工具 schema，DSH read_image 使用 `file_path` 而非 `path`；每次图像 schema 修正同时扣 `image_schema_fix` 和 `call_correction` 各 1 次，总共最多 2 次尝试，不可将两个额度相加。用户取消或权限拒绝立即停止 |
| 固定读图探针失败 | 按 vision-probe.md 检查随包 assets/vision-probe.png 的绝对路径与实际图像返回；不依赖教材图片，不重复建立随机探针目录。有限修正后仍无法确认视觉能力 → 按 D14 停止校对 |
| 实际材料图片读不到（图片显示失败、模型看不到配图） | 先确认是否透明底 PNG：合成白底后重读；完成白底合成仍读不到 → 回报失败，由主 agent 按 D14 拒绝 / 重派；不得静默跳过图片内容检查 |
| 权限拒绝（permission denied / authorization required） | 不是参数错误，不用同一权限重复尝试；停止本次工具调用，说明需要宿主授权或用户处理，并写入失败留痕 |
| 用户取消 / 中止 | 不自动重派、不计入技术失败次数；立即停止，保留已收集输出和现有产物，确认在途调用已取消并写入失败留痕 |
| 取消一个单元（`jiaodui_unit_cancel`） | **只有父代理/宿主能记录取消**：单元子代理拿不到该工具，也不得用 `unit-event` 表达取消（它已不接受取消参数）。`initiator` 与 `reason` 必须配对：`user`+`user_cancel`、`parent`/`host`+`technical_timeout`/`superseded`，否则 `cancel-invalid`。**父代理技术停止后被 `dispatch-plan stop=true` 挡住时，用 `--revoke` 撤销这次技术性取消即可继续补位，不要为此 `--rerun`**（开新轮次会连带废掉在途子代理的 `expected_run_id`，触发 `run-changed`）。用户取消**不可撤销**（那是人的决定），只能由用户重新发起 |
| 提前失败 / 读图失败 / 图片归属不明 / 批次取消 | 在相关单元写 `_校对失败.md`；记录轮次、失败阶段、完整工具错误、引用序号及正文位置、产物摘要；verify 未执行时明确写“未执行”；子 agent 无法落盘时由主 agent 兜底 |
| 技术性崩溃 / 超时 / 限流 | 由主 agent **自动重派 1 次**（仅一次）；重派仍失败 → 写 `_校对失败.md` 标失败 |
| 自修 3 轮仍不过 | 写 `_校对失败.md`：失败原因 + 最后一次 verify 完整输出 + 最后一次产物摘要；保留报告供排查，不进下游 |

## 六、失败留痕格式（`_校对失败.md`）
1. 首行：失败原因（简短一行，`status` 会取首行做展示）。
2. 最后一次 `verify-report` 的**完整输出**。
3. 最后一次产物摘要（标记数、严重度、错误数）。
修复后重新校验通过即转「已完成」；该失败记录仅作历史，不再决定当前状态。

**机检（仅告警，不是闸门）**：`status --json` 的 `failure_note_problems` 会指出结构问题，code 为
`failure_note.empty`（没有首行原因）/ `failure_note.no-verify-output`（未见 verify 输出，也未写「未执行」）/
`failure_note.no-summary`（标记 / 严重度 / 错误 三个词至少命中两个才有摘要）。格式不全**不影响**
单元的「已完成 / 失败」判定，也不让已通过的单元回退——它只是提醒补全留痕。

## 七、宿主调用与报告落盘（子 agent 执行前阅读）

- 调用方式以当前宿主实际暴露的 schema 为准：直接暴露具名工具时按其 JSON schema 调用；若当前 Harness 只暴露 `run_code`，则通过外层 `run_code` 执行，并在程序体内调用 `await tools.skill(...)`、`await tools.jiaodui(...)`、`await tools.write(...)` 等 SDK。不得把外层字段塞进内层工具参数，也不得因为 skill 示例写了直接调用就绕过当前宿主接口。
- 当前 Harness 的 `run_code.justification` 是外层必填说明，必须是非空完整句子；空字符串会在程序体执行前被参数校验拒绝。该字段不是传给 `tools.jiaodui` / `tools.write` 的参数，也不能掩盖实际权限拒绝；sandbox 权限只按当前 schema 和真实授权需求处理。
- 在 `run_code` 程序体中并发派发子代理时，必须等待所有派发调用完成，再验证并记录每个返回句柄。成功返回形态为 `background.jobId`、`continuable.subagentId` 或 `foreground.runId`。遇到部分拒绝时先用 `await Promise.allSettled(...)` 收齐已启动句柄，再按停止规则取消在途任务；不要序列化未 await 的 Promise（它只会显示 `{}`），也不要在取得句柄前查状态或判断派发失败。

示例：下面代码放在 `run_code` 的 `code` 字段中；外层仍须按宿主 schema 提供非空 `justification` 等字段。
```ts
const settled = await Promise.allSettled(
  units.map((unit) => tools.subagent({
    description: `校对${unit.name}`,
    run_in_background: true,
    prompt: buildPrompt(unit),
  }))
);

const results = settled.map((item) => {
  if (item.status === "rejected") return { ok: false, error: String(item.reason) };
  const task = item.value;
  const handle = task.kind === "background" ? task.jobId
    : task.kind === "continuable" ? task.subagentId
    : task.kind === "foreground" ? task.runId : undefined;
  if (!handle) throw new Error(`无有效子代理句柄: ${JSON.stringify(task)}`);
  return { ok: true, kind: task.kind, handle };
});

// 若有失败，先依据已收集句柄取消在途任务并留痕；不要补派或进入下游。
```
- `jiaodui` 使用 `args` 数组传参，每个参数独立，不额外加 shell 引号。以下是对具名 `jiaodui` 工具的参数示例；`verify-report` 成功后才调用 `parse-report`，路径需替换为实际路径：

```json
{
  "args": [
    "parse-report",
    "--unit",
    "/绝对路径/工作区/校对/第 6 讲/units/第 6 讲/单元1",
    "--work-root",
    "/绝对路径/工作区",
    "--json"
  ]
}
```

- 报告使用 `write` 工具的 `file_path` 与 `content` 参数。覆盖已有报告前先读取该文件；局部修改前读取当前版本，以唯一、逐字一致的旧文本调用 `edit`。修订应限于报告，不改变单元源文。
- JSON 中 LaTeX 反斜杠写成双反斜杠，真实换行用 `\n`；美元符号、反引号和 `${…}` 都只是文本，不作为程序执行。不手动叠加 JS/TS 字符串转义，也不把最终文件的换行写成字面量反斜杠 n。以下是对具名 `write` 工具的参数示例，只示范文本传输，不是可交付的校对报告：

```json
{
  "file_path": "/绝对路径/工作区/校对/第 6 讲/units/第 6 讲/单元1/_校对报告.md",
  "content": "公式：$\\frac{1}{2}$\n代码：`示例` 与 ${占位}\n"
}
```

- 参数校验错误或编辑匹配错误必须记录原始错误及实际执行阶段；工具调用未执行不能称为 CLI 执行失败，报告未写入不能称为已落盘。已有产物保留，verify / parse 未执行须明确注明；不把这些工具错误算作报告内容自修。用户要求遇错即停时不重试，不能为继续流程改参数或改用另一个命令。

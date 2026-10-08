# 失败模式与自修指引

`verify-report` 的每个失败都带结构化 code 与位置。子 agent 拿到原因后**只改 `_校对报告.md`**，改完重跑 `jiaodui verify-report --unit <dir>`，**自修 ≤3 轮**；仍不过写 `_校对失败.md`，不阻塞批次。通用自修动作：按报错编号定位 → 修正 → 重跑；不要为了过闸门而删改真实发现（057 教训）。

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
| 读图参数错误（missing required property / invalid arguments） | 尚未验证视觉能力。核对当前工具 schema，DSH read_image 使用 file_path 而非 path；修正后最多重试 2 次。用户明确遇错即停则停止并保留完整错误，不称为宿主不支持读图 |
| 固定读图探针失败 | 按 vision-probe.md 检查随包 assets/vision-probe.png 的绝对路径与实际图像返回；不依赖教材图片，不重复建立随机探针目录。有限修正后仍无法确认视觉能力 → 按 D14 停止校对 |
| 实际材料图片读不到（图片显示失败、模型看不到配图） | 先确认是否透明底 PNG：合成白底后重读；完成白底合成仍读不到 → 回报失败，由主 agent 按 D14 拒绝 / 重派；不得静默跳过图片内容检查 |
| 权限拒绝（permission denied / authorization required） | 不是参数错误，不用同一权限重复尝试；停止本次工具调用，说明需要宿主授权或用户处理，并写入失败留痕 |
| 用户取消 / 中止 | 不自动重派、不计入技术失败次数；立即停止，保留已收集输出和现有产物，确认在途调用已取消并写入失败留痕 |
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

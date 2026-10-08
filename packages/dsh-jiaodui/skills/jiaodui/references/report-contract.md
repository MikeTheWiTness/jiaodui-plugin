# 产物格式与交付校验契约

权威来源：`jiaodui/verify.py`、`jiaodui/report_parse.py`、`jiaodui/markers.py`、`jiaodui/paths.py`、PRD §5。命令入口：`jiaodui verify-report --unit <dir> [--source S]`。

## 一、`_校对报告.md` 结构（两节必须存在）
1. **头部严重度总结行**：必须是 `无问题` / `轻微问题` / `一般问题` / `严重错误` 之一。可写 `总结行：一般问题`；裸「无」不是合法值。总结行只在首个三级标题之前的头部区域识别。
2. **`### 标记原文`**：逐字抄写单元源文正文，在需要修改处插入内联标记 `【编号|原文字段|修改后文字】`。
   - 编号为阿拉伯数字，建议从 1 起连续（闸门只查重号与原因对应，不查连续性）；原文字段逐字一致；禁止把标记插进 `$...$` 或 `**...**` 内部。
   - 公式等源文自身跨行时允许字段跨行（解析与 Word 生成共用同一语法）。
   - 不抄写 `编号：` / `内容：` 信封行；不用三反引号或波浪线围栏包裹（围栏会让公式无法转 Word 公式）。
3. **`### 修改原因`**：`编号. 原因`，编号与标记一一对应。
   - 编号行必须**行首锚定**，分隔符用 `.` / `)` / `、`；纯空格分隔（如 `1 原因`）不算编号。
   - 支持区间写法 `1-2` / `①-③`（一个原因覆盖多个编号）。
   - **无问题时两节仍须存在**，修改原因写「无」。
   - 经核验正确、无需修改的内容不得编入编号；如需说明，以非编号段落（如「核验说明：」）附在编号列表之后。
   - 混合内容仍只输出一个 `### 标记原文` + 一个 `### 修改原因`；来源区分用非编号小标题，不得用 `###`。

## 二、verify-report 检查项（逐条，`ok = 无 error`）
| 检查项 | 判定 | 失败 code |
| --- | --- | --- |
| 标记语法 | 必须匹配 `【编号|原文|改为】`；字段缺失、`【` / `】` 不配对、编号后缺竖线 → 拒绝 | `syntax.unbalanced-brackets`、`syntax.malformed-marker`、`syntax.field-count`（字段数不为 3，如 `【1|a】`） |
| 修改原因对应 | 编号与标记一一对应；多、少、错位 → 拒绝 | `reason.missing`（标记缺原因）、`reason.orphan`（原因多编号）、`reason.duplicate`（同一编号原因重复或区间重叠）、`marker.duplicate-num`（标记编号重复） |
| 严重度总结行 | 四值之一；缺失 / 非法 / `无问题` 却含错误标记 → 拒绝 | `severity.missing`、`severity.invalid`、`severity.contradiction` |
| 原文完整性 | 去掉标记语法、把各标记还原为「原文字段」后，与单元源文**逐段比对**；缺段、重段、改变未标记正文 → 拒绝 | `integrity.missing-paragraph`、`integrity.extra-paragraph`、`integrity.duplicate-paragraph`、`integrity.changed` |
| 找不到源文 | 源文缺失或为空，无法做原文全文比对 → **拒绝**（历史产物兼容走显式 `--legacy`） | `integrity.no-source`（error） |
| 空原文字段 | 原文字段为空 → 拒绝 | `original.empty` |
| 空操作 | 原文 == 改为（完全相同）→ 拒绝 | `original.noop` |
| 原文字段定位 | 无法在源文定位 → **unknown 只告警，不算失败**（LaTeX 装饰差异会让合法标记也定位不到） | `locate.unknown`（warning） |
| 原文字段与源文不符 | 原文字段对不上、但「改为」对得上（源文此处即「改为」）→ 拒绝：原文字段必须逐字一致 | `original.not-locatable` |
| 改为与原文无法区分 | 归一化后相同 → 记「需人工确认」，**不拒绝**（宁可多保留一条批注也不静默丢真实发现） | `marker.manual-review`（manual） |
| 涉及 unknown 的正文差异 | **仅当差异完全落在一个真实 `$…$` 公式区间内**（公式字段的 LaTeX 装饰差异）才降级为告警；公式之间的普通正文差异仍按缺段/多段/改动**拒绝** | `integrity.unknown-diff`（warning，仅限公式字段内） |
| 图片资源 | 仅支持正文行内图片 `![alt](path)`；引用的图片必须存在、格式受支持、可解码；透明图必须有拆分阶段生成且与原图尺寸一致的白底副本；缺图、无效/非行内引用、远程引用、HTML `img` → 拒绝；**行内代码与围栏代码块里的图片语法不算引用**；`images/` 中未被引用的图片仅告警 | `images.missing`、`images.invalid_reference`、`images.remote_unsupported`、`images.unsupported_format`、`images.unreadable`、`images.white_background_missing`、`images.white_background_unreadable`、`images.unsupported_syntax`；`images.extra_images`（warning） |
| 找不到单元源文 | 源文缺失 → 拒绝；图片检查与文本检查必须用同一份源文（含显式 `--source`） | `images.source_missing` |
| 报告本身 | 报告为空 → 拒绝；文件不存在 → 拒绝 | `report.empty`、`report.missing` |

> 注意：`locate.unknown` 与 `integrity.changed` 不能混为一类——对**无法定位**给警告，对**可确定的源文缺漏**给失败。
>
> `repair-report` 是工具侧辅助：只从源文重建 `### 标记原文`，让未标记正文回到源文字面，再按本节同一套检查项复验；它不放宽任何检查、不替代 `verify-report`，字段无法唯一定位即按 `repair.*` 拒绝。

## 三、`_校对数据.json`（parse-report 确定性产出）
```json
{
  "corrections": [
    {"num": 1, "type": "text", "original": "被改原文", "correction": "改后文字", "reason": "原因"}
  ],
  "summary": "一般问题",
  "marked_text": "带标记正文（换行转义为字面量反斜杠 n）",
  "tool_calls": []
}
```
- `corrections / summary / marked_text` 为必需；`tool_calls` 有可记录的工具调用时填写，无调用允许缺省。
- summary 头部识别不到时记 `未声明`（不冒充「无问题」）；「无问题」却含修正标记时同样记 `未声明`。
- `parse-report` 默认**拒绝解析未通过 verify-report 的报告**；仅历史产物兼容可显式加 `--legacy`。图片检查复用该闸门，拒绝可确定的缺图、无效引用和不支持的远程引用；闸门只能验证正文引用与资源绑定，不能证明模型理解了正确的图片语义归属，归属必须由真实宿主验收。新布局通过后同时在材料 `_校对记录.json` 登记本轮 run_id、报告 SHA 与单元输入摘要；必须登记成功才回报完成。历史写入另需 `--legacy-layout`，仍限于指定工作区，不登记为新交付。

## 四、docx 计数口径（build-docx）
- 输出逐项计数：错误标记数 `marker_count`、批注锚点数 `anchor_count`、公式可见兜底数 `formula_fallback_count`、缺失数 `missing_count`、记账异常 `over_count`、图片未嵌入 `image_missing_count`、批注公式降级 `comment_formula_fallback_count`、无问题单元标题批注数 `heading_comment_count`。
- 硬门槛：**`marker_count = anchor_count + formula_fallback_count`**，且 **`missing_count = 0`** 且 **`over_count = 0`**；无问题单元的标题批注**单列**，不得混入错误标记。
- 每条错误标记必须有 Word 批注锚点，或在公式内以可见高亮 + 修改意见兜底。
- **兜底按标记编号记账**：兜底文案固定为 `（标记 N 修改意见：原文→改为）`，`改为` 为空时写 `（标记 N 修改意见：删去「原文」）`，不得省略——编号是生成后复核唯一能逐条核对的依据。
- **逐单元不得出现负账**：某单元「锚点 + 兜底」多于报告标记数即为记账异常（`over_count > 0`），不通过交付；禁止靠全卷求和让一个单元虚增抵消另一个单元真丢。
- **静默降级必须留痕**：单元图片未能嵌入交付（`image_missing_count > 0`，悬空引用会让 Word 缺图）**不通过交付**；批注内公式渲染失败降级为文本（`comment_formula_fallback_count`）**允许降级但不许静默**——matplotlib 是可选依赖，只计数并告警，不阻塞交付。
- 必须复核**生成后的 docx** 实际批注与锚点，而不是只看生成前计划注入的数量；不满足则**不交付 docx**，按确定性代码 bug 处理。
- 空原文 / 空操作 / 原文字段对不上（RESTORE_NEW）三类在**交付路径**是「**整单元排除**」：verify-report 判 error，build-docx 整单元不进 Word——不是「该条不生成批注」。渲染侧的 `keep_comment=False` / `render_new` 分支只服务未过闸门的 legacy 直调入口（`generate_combined_docx`），交付路径不可达，已由测试锁定。

## 五、状态与闸门（status / 下游命令）
- **单元内非契约文件不做检查**（2026-10 决策 1："不管这些文件"）：单元内只应放契约名文件，但工具**不因存在 `第1题_尝试2.md` / `随手笔记.txt` 而失败**——它们不参与校验、不进交付。这是纪律而不是闸门；管住它们靠交付前的人工/agent 自查。**单元源文只有一个定义**（`paths.find_source_md`：优先契约名 `<单元名>.md`，回退该目录内任意非 `_` 开头的 md），status / verify / report / material / docx 标记审计**共用**它，不允许任何一侧另写一套。
- **只读入口允许软链越界，写入口一律按 realpath 拒绝**（2026-10 决策）：`status` / `verify-report` 等只读命令可以读工作区外的源文（软链挂载的只读材料很常见），它们不写；`parse-report` / `build-report` / `build-docx` 等写命令仍用 `ensure_inside` 判定真实路径，软链指向工作区外即报 `outside-workspace`，绝不顺着软链写出去。
- **单元目录名只认精确名**：`第N题` / `单元N` / `板块N`（`板块N` 与讲义 `单元N` 同权）。`第1题_备份`、`第1题(文言文)` 这类变体名**不是单元**：识别、扫描、清单核对一致忽略它们。历史目录若含变体名，需人工重命名或移出单元根目录；写命令因此不会再把「自己认出的目录」判成 `invalid-manifest`。
- 状态只由磁盘产物推导：`未开始` / `已交付未过校验` / `已完成` / `失败` / `本轮未完成`。
- 优先级：先校验现有报告；新布局还须匹配本轮交付登记、报告与单元输入摘要才「已完成」，否则为「本轮未完成」。有效的本轮完成不因旧 `_校对失败.md` 回退；历史布局保留通过即完成的读取语义。未通过且有失败记录为「失败」，未通过且无失败记录为「已交付未过校验」。清单单元集合与磁盘多出或缺失：**写命令**（`split` / `slice`）拒绝并列出（details 带 `hint`），不自动删除；**只读 `status` 退 0**，把同一份现场放进 `warnings` 与 `unit_set_mismatch`——诊断优先，集合不一致时也必须能看到真实现场。变更单元集用 `split` / `slice --replace-units`：陈旧单元整体移动到 `units/<材料名>/.superseded/<原 run_id>/`（保留源文、报告与图片，只移动不删除），归档路径写进轮次 action；归档目录不会被当成单元。
- `build-report` / `parse-report` / `build-docx` 必须复核当前状态，**拒绝消费未通过的报告**；`build-report` 对失败单元写明显占位与原因，不拼入未校验正文。
- **四条命令共用一个闸门定义**（`verify-report` / `parse-report` / `build-report` / `build-docx` 都调用 `jiaodui.verify.verify_unit`）。新增任何检查项必须同时接进这四条命令，只加固 `verify-report` 会造成「闸门拒绝、下游放行」的口径分裂。

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
| 标记语法 | 必须匹配 `【编号|原文|改为】`；字段缺失、`【` / `】` 不配对、编号后缺竖线 → 拒绝 | `syntax.unbalanced-brackets`、`syntax.malformed-marker` |
| 修改原因对应 | 编号与标记一一对应；多、少、错位 → 拒绝 | `reason.missing`（标记缺原因）、`reason.orphan`（原因多编号）、`marker.duplicate-num`（编号重复） |
| 严重度总结行 | 四值之一；缺失 / 非法 / `无问题` 却含错误标记 → 拒绝 | `severity.missing`、`severity.invalid`、`severity.contradiction` |
| 原文完整性 | 去掉标记语法、把各标记还原为「原文字段」后，与单元源文**逐段比对**；缺段、重段、改变未标记正文 → 拒绝 | `integrity.missing-paragraph`、`integrity.extra-paragraph`、`integrity.duplicate-paragraph`、`integrity.changed` |
| 找不到源文 | 无法做原文完整性比对，仅格式与标记检查生效 → 告警 | `integrity.no-source`（warning） |
| 空原文字段 | 原文字段为空 → 拒绝 | `original.empty` |
| 空操作 | 原文 == 改为（完全相同）→ 拒绝 | `original.noop` |
| 原文字段定位 | 无法在源文定位 → **unknown 只告警，不算失败**（LaTeX 装饰差异会让合法标记也定位不到） | `locate.unknown`（warning） |
| 原文字段与源文不符 | 原文字段对不上、但「改为」对得上（源文此处即「改为」）→ 拒绝：原文字段必须逐字一致 | `original.not-locatable` |
| 改为与原文无法区分 | 归一化后相同 → 记「需人工确认」，**不拒绝**（宁可多保留一条批注也不静默丢真实发现） | `marker.manual-review`（manual） |
| 涉及 unknown 的正文差异 | 源文与重建正文有差异但涉及无法定位字段 → 保留 unknown 警告，降级 | `integrity.unknown-diff`（warning） |
| 报告本身 | 报告为空 → 拒绝；文件不存在 → 拒绝 | `report.empty`、`report.missing` |

> 注意：`locate.unknown` 与 `integrity.changed` 不能混为一类——对**无法定位**给警告，对**可确定的源文缺漏**给失败。

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
- `parse-report` 默认**拒绝解析未通过 verify-report 的报告**；仅历史产物兼容可显式加 `--legacy`。

## 四、docx 计数口径（build-docx）
- 输出逐项计数：错误标记数 `marker_count`、批注锚点数 `anchor_count`、公式可见兜底数 `formula_fallback_count`、缺失数 `missing_count`、无问题单元标题批注数 `heading_comment_count`。
- 硬门槛：**`marker_count = anchor_count + formula_fallback_count`**，且 **`missing_count = 0`**；无问题单元的标题批注**单列**，不得混入错误标记。
- 每条错误标记必须有 Word 批注锚点，或在公式内以可见高亮 + 修改意见兜底。
- 必须复核**生成后的 docx** 实际批注与锚点，而不是只看生成前计划注入的数量；不满足则**不交付 docx**，按确定性代码 bug 处理。
- 空原文 / 空操作标记不生成批注（审计结论 `keep_comment=False`）。

## 五、状态与闸门（status / 下游命令）
- 状态只由磁盘产物推导：`未开始` / `已交付未过校验` / `已完成` / `失败`。
- 优先级：先校验现有报告；通过即「已完成」，即使保留旧 `_校对失败.md` 也不回退；未通过且有失败记录为「失败」，未通过且无失败记录为「已交付未过校验」。
- `build-report` / `parse-report` / `build-docx` 必须复核当前状态，**拒绝消费未通过的报告**；`build-report` 对失败单元写明显占位与原因，不拼入未校验正文。

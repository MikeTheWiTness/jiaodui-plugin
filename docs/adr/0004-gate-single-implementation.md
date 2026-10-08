# ADR 0004：交付闸门单一实现（图片资源纳入 §5.2）

- 状态：已采纳
- 相关：[PRD](PRD.html) §5.2、[ADR 0002](0002-workspace-material-layout.md)、[REMEDIATION](REMEDIATION.md) R-A01/R-A02/R-A03

## 背景

读图是校对的硬前提（D14：子 agent 无视觉能力即拒绝执行，不降级），因此「正文引用的图片能不能被读到」必须是交付闸门的一部分。图片检查最初只加在 `verify_unit` 上，而 `parse-report` / `build-report` / `build-docx` 实现的是 PRD §5.2 原有的 7 项**文本**检查——于是同一个缺图单元出现互相矛盾的结论：`verify-report` 拒绝（exit 4）、`status` 报「已交付未过校验」，而 `parse-report` 照常登记、`build-report` 把正文拼进整卷、`build-docx` `ok=true` 退 0 交付。

## 决策

1. **闸门只有一个实现**：`jiaodui.verify.verify_unit`。`verify-report` / `parse-report` / `build-report` / `build-docx` 四条命令一律调用它，不再各自组装检查项。
2. **图片资源纳入 PRD §5.2 检查项**（同步更新 PRD 表）。
3. **新增检查项必须同时接进四条命令**；只加固 `verify-report` 视为未完成。

## 图片检查的具体口径

- 仅支持行内 Markdown 图片 `![alt](path)`；参考式图片 `![alt][label]` / `![alt][]` 当前流水线未贯通，闸门明确拒绝，不得报告为可交付。
- 拒绝：文件不存在、无效引用、远程引用（http/ftp/协议相对）、HTML `<img>`、格式不在支持列表、无法解码、透明图缺少拆分阶段的白底副本、白底副本损坏或与原图尺寸不符。
- 不算引用：**行内代码与围栏代码块里**的图片语法（否则源文里的代码示例会误拒合法报告）。拆分和 Word 重写复用同一行内引用扫描器。
- 仅告警：`images/` 中存在未被正文引用的图片。
- 边界：闸门只验证**引用与资源的绑定**，不证明模型理解了图片的语义归属；归属仍由宿主读图与 §8 人评负责。
- `--source` 显式指定源文时，文本检查与图片检查必须用**同一份**源文。

## 后果

- 正面：闸门与交付口径统一；`status`、`parse-report`、`build-report`、`build-docx` 对同一单元不再给出相反结论。
- 代价：`verify_unit` 会解码图片，下游命令比以前慢（每单元一次图片元数据读取与哈希）；以「口径一致」换「一次多余 IO」，可接受。
- 风险：今后任何一处漏接，症状都是「闸门拒绝但交付通过」——用 `tests/test_image_gate_unified.py` 与 `tests/test_verify_images.py` 锁定，不靠人记。

## 被否决的备选

- **只加固 `verify-report`**：造成闸门与下游交付口径分裂，正是本 ADR 要消除的问题。
- **图片检查放在 split 阶段一次做完**：split 时还没有报告，无法与交付绑定；历史布局还要走 `--legacy-layout`，覆盖不到。
- **四条命令各自实现图片检查**：同一契约三处实现必然漂移，且违背「核心逻辑只有一份」。

---
name: jiaodui
description: K-12 试卷/讲义校对总入口。judgement 交给 agent，确定性交给 jiaodui CLI：convert→split→单元子 agent 校对→verify-report 闸门→整卷报告→Word 批注版。v1 预设学科只落地高中物理，其余 M5 待落地。
---

# jiaodui 校对总入口

## 1. 何时使用与目标
- 输入为 K-12 试卷/讲义源文件（docx / doc / idml / md）或已拆分单元目录，需要逐题校对并交付 Word 批注版时使用。
- 分工：**判断交给 agent，确定性交给 jiaodui CLI**。CLI 只做转换 / 拆分 / 校验 / 计算 / 拼装，不调用任何模型。
- v1 范围：只做**试卷 + 讲义**主链路；批注评审、自由校对、独立解题（冻结）、classics 古籍检索均后置。学科预设 v1 只落地**高中物理**，其余 6 科见 `references/subject-matrix.md`（M5 待落地）。
- 不做：GUI、LaTeX/PDF、自动改源文。

## 2. 前置硬门槛（先做，失败即拒绝执行）
1. `jiaodui check-env` 必须通过（Python≥3.12、sympy / python-docx / Pillow / lxml、pandoc）。它只证明本地依赖，**不证明宿主能力**。`matplotlib` 属可选：check-env 按真实 import 区分「未安装 / 已安装但无法加载」；不可用只让**批注内公式图片**降级为 `$…$` 文本，不阻塞流程。
2. 派发任何校对子 agent **之前**，主 agent 必须实际派发一次，让子 agent 读取一张**真实本地图片**，确认其视觉能力。失败 → **拒绝本次执行**，不得静默跳过图片检查（D14）。
3. 同时确认宿主支持：一层扁平子 agent、子 agent 能在单元目录内写文件并回传一行摘要。
4. 读图探针必须覆盖**透明底 PNG**：本流程配图多为透明底黑线稿（实测 alpha=0 像素占 93–95%），直接读图会呈现为空白；要求子 agent 先合成白底再判读，否则会把「透明图空白」误判成读图失败或漏检图片内容。

## 3. 完整流程
1. 转换：`jiaodui convert <源文件>` → `_raw.md` + `images/`（已经是 md 可跳过）。
2. 拆分：`jiaodui split <raw_md> --subject 高中物理 --mode exam|lecture`（默认规则拆分）。
   - **讲义模式默认执行完整导入清理**（与旧仓 `clean_enabled` 默认开启一致，顺序固定）：`fix_latex_escapes` 还原 pandoc 过度转义 → `comprehensive_clean` 去表格竖线 → `clean_intent` 清【出题意图】 → `fix_floating_images` 把浮进选项 A 的题图挪回独立行 → `normalize_option_spacing` 压选项/解答长空格 → `strip_decor_images` 清装饰图。pandoc 会把讲义渲染成网格表，`**例1**`/`**练1**` 落在表格行内（行首是竖线）；不清理则 `section_pattern` 命中不到，整篇会塌成一个超长单元。仅在需要保留原始表格做对照时才加 `--no-clean`（此时六步全不执行）。
3. 抽查：`jiaodui precheck-split <输出目录>`，看单元数、各单元首行、字符数分布、空单元与超长单元；异常才升级智能拆分（派拆分子 agent 出边界清单 → `jiaodui slice --boundaries`）。
4. 扫描：`jiaodui status <paper_dir>`，只派发未开始 / 未过校验的单元。
5. 滑动窗口派发**单元子 agent**（一个单元 = 一个干净上下文）。
6. 子 agent：读源文 + `images/` + 学科 references → 校对 → 写 `_校对报告.md` → `jiaodui verify-report --unit <dir>`；不过则按结构化原因**自修 ≤3 轮**。
7. `jiaodui build-report <paper_dir>` 拼接整卷报告。
8. 主 agent **通读整卷报告全文**（整体把关）：个别单元漏检 → 重派该单元；系统性问题 → 停手回报用户。
9. `jiaodui build-docx <paper_dir>`，复核 **错误标记数 = 批注锚点数 + 公式兜底数，且缺失数为 0**（无问题单元标题批注单列）。不满足按确定性 bug 处理，**不交付 docx**。
10. 交付：整卷报告 + Word 批注版 + 失败清单（不自动改源文）。

## 4. 调度规则
- 主 agent 纯调度：每单元只读**一行摘要**（单元号 / 问题数 / 校验结果 / 产物路径 / 失败原因），不把报告或源文读进主上下文。
- 一层扁平：主 agent 直接派单元子 agent，**禁止嵌套**。
- 滑动窗口补位：空位立即补派下一个单元，并发取宿主上限（DSH 默认 8）。

## 5. 子 agent 输入包（只给路径，不给内容）
- 路径：单元目录 + 源文 md + `images/` + `references/subjects/<学科>.md` + `references/report-contract.md`。
- 交付要求：写 `_校对报告.md` 并自跑 verify-report 至通过，回一行摘要。
- 禁止项：不改源文；不自由命名产物；不嵌套派子 agent。

## 6. 硬约束
- `verify-report` 不通过**不算完成**；不合格报告不得进入汇总或交付。
- 自修 ≤3 轮仍不过 → 写 `_校对失败.md`（失败原因 + 最后一次 verify 完整输出 + 产物摘要），**不阻塞批次**。
- 技术性崩溃 / 超时 / 限流 → 自动重派 **1 次**（仅一次）。
- 不自动改源文；失败单元批次结束后交人裁定。

## 7. 产物命名纪律
单元目录内只允许：`第N题.md`、`单元N.md`、`images/`、`_校对报告.md`、`_校对数据.json`、`_校对失败.md`；输出目录只允许 `校对报告/`、`校对Word/`。禁止 attempt / 副本等自由命名；多轮中间结果写在同一文件内分节。

## 8. v1 命令速查（11 个）
```
jiaodui check-env
jiaodui convert <file> [--out-dir D] [--base-name N] [--mathjax]
jiaodui split <raw_md> --subject 高中物理 --mode exam|lecture [--out-root D] [--images-dir D]
jiaodui precheck-split <dir>
jiaodui slice --boundaries <清单.json> [--raw R] [--out-root D] [--mode exam|lecture]
jiaodui status <paper_dir>
jiaodui verify-report --unit <dir> [--source S]
jiaodui parse-report --unit <dir> [--source S] [--legacy]
jiaodui calc <op> --param NAME=VALUE … [--show-code]
jiaodui build-report <paper_dir> [--out PATH]
jiaodui build-docx <paper_dir> [--out-dir D]
```
- `--json` / `--quiet` 可放子命令前或后（每个子命令也接受）：`jiaodui --json status <paper_dir>` 或 `jiaodui status --json <paper_dir>`。
- 退出码：0 成功 / 1 未预期 / 2 用法 / 3 环境 / 4 校验失败 / 5 未找到 / 6 契约 / 7 不支持。

## 9. 延伸阅读（按需读）
- 学科索引：[`references/subject-matrix.md`](references/subject-matrix.md)
- 高中物理：[`references/subjects/高中物理.md`](references/subjects/高中物理.md)
- 产物与校验：[`references/report-contract.md`](references/report-contract.md)
- 失败与自修：[`references/failure-modes.md`](references/failure-modes.md)

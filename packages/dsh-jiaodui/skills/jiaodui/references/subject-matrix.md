# 学科差异矩阵（索引）

学科之间真正不同的只有三样：**检查重点**（人读规范）、**工具集与输入格式**（机器读配置）、**拆分参数**（机器读配置）。共性流程只写一次，在总入口 `SKILL.md`。

## 一、7 学科一览表

按旧仓 `subjects/` 实际目录为准；**v1 只落地高中物理**，其余 6 科标注「M5 待落地」（M5 逐科加 references 行 + config 行，共性流程零改动）。

| 学科（旧仓目录） | v1 状态 | 输入格式 | 工具集（calc 映射） | 拆分规则 | 特殊钩子 |
| --- | --- | --- | --- | --- | --- |
| 高中物理 | **已落地** | 源文件 `.docx / .doc / .md / .idml` → convert；单元 `第N题.md`（exam）/ `单元N.md`（lecture）+ `images/` | `calc evaluate / solve / formula / dimensional / vector_ops / circle_from_two_points`（另可用 simplify / equality）；数值与公式必须实算 | 配置 `split_mode=section`；`exam_question_pattern` 为 `^(\d+)．`；`wrapped_patterns`=班型 / 例练；`nav_patterns`=直击课堂 / 本讲导航 | 受力图 / 电路图 / v-t 图一致性；量纲分析必须声明每个符号单位；独立解题冻结不启用 |
| 高中化学 | M5 待落地 | 同上 | `calc evaluate / solve / equality / simplify / chemistry_balance / stoichiometry`；配平与计量必须实算 | 目标：无独立题号规则；lecture 用班型 / 例练 `wrapped_patterns` | 化学用语检查清单；方程式配平矩阵；独立解题冻结不启用 |
| 小学数学 | M5 待落地 | 同上 | `calc evaluate / solve / equality / simplify / geometry`；数值与几何必须实算 | 目标：只配 lecture，`wrapped_patterns` 为 `\d+.*` | 几何构造与测量（`geometry`） |
| 高中语文 | M5 待落地 | 同上（含「前置参考」段，若有） | 无符号计算 | 目标：无独立题号规则；lecture 用班型 / 例练 `wrapped_patterns` | **文言文 / 古诗词 / 名篇默写前置检索**（classics，v1 后置）；无前置参考时须注明「无前置参考可供比对」；通假字 / 古今字 / 异体字不标错 |
| 高中历史 | M5 待落地 | 同上 | 无符号计算 | 目标：题号规则 `^(\d+)[．.、]`；lecture 含 `section_pattern`（`## 模块 / 例N / 练N / ### 模型大招`）与 `例 / 练 / 变式 / 真题` | 章节 / 模块 + 模型大招切分；史料与年份核对 |
| 初中英语 | M5 待落地 | 同上 | 无符号计算 | 目标：题号规则 `^(\d+)[.)]`；`wrapped_patterns` 为 `【例题精讲】`、`\d+.`、`【\d+】`，`unwrapped_patterns` 为 `^【例题精讲\d+】` | 例题精讲切分；语法 / 拼写 / 词形 |
| 小学语文 | M5 待落地 | 同上 | 无符号计算 | 目标：只配 lecture，`wrapped_patterns` 含班型（一本班 / 双一流班 / 清北班 / A班 / A+班 / S班）+ 例 / 练 / 变式 | 先审答案（准确性 / 解析逻辑 / 得分点）再校正文；班型拆分 |

## 二、机器读配置 `config/subjects/<学科>.json`
每个学科的**工具集白名单、支持扩展名、拆分参数**落在 `config/subjects/<学科>.json`（D23：改工具名不需要动人读长文）。**v1 已创建 `config/subjects/高中物理.json`**，其余 6 科 M5 逐步补齐；上表 M5 行的参数为**目标值**（源自旧仓 `subjects/*/config.json`），落地时改写进新 schema。
- `subject`：学科名。
- `tools`：工具集白名单（高中物理为 `["calc"]`）。
- `extensions`：支持扩展名（高中物理 `.docx / .doc / .md / .idml`）。
- `split_mode` / `section_pattern` / `section_extensions`：章节切分参数。
- `wrapped_patterns` / `unwrapped_patterns`：讲义包裹标记（班型、例练）。
- `exam_question_pattern`：试卷题号规则（高中物理 `^(\d+)．`）。
- `nav_patterns`：需忽略的导航段标记（高中物理 `直击课堂 / 本讲导航`）。
### 拆分模式 `--mode`
  - `exam`：试卷，产出 `第N题.md`，按题号规则切题。
  - `lecture`：讲义，产出 `单元N.md`，按班型 / 例练包裹标记切单元。
- 默认走**规则拆分**；`precheck-split` 报出空单元 / 超长单元 / 异常首行时才升级**智能拆分**（拆分子 agent 出边界清单 → `slice --boundaries`）。讲义模式由拆分子 agent 先用 `slice --preview` 取**清理后**正文再定行号（主 agent 不读预览），预览与切片必须同 `--mode`/`--subject`；新布局可复用材料类型，但未知类型拒绝，不默认 exam。用户指定类型直接采用，未指定时按总入口检查结构/有限预览，不确定再问。

## 三、共性（只写一次，在 SKILL.md）
采用用户指定学科或由主 agent 有限预览识别（不确定则询问，读取边界见 `SKILL.md` §2.1）→ 检查本表支持状态并加载对应规范 / 配置 → 环境与宿主能力检查 → 转换 → 拆分 → 抽查 → 状态扫描 → 滑动窗口派单元子 agent → verify-report 闸门（自修 ≤3 轮）→ 整卷报告 → 主 agent 通读 → Word 批注版 → 交付 + 失败清单。所有学科的产物命名、校验项、失败留痕完全一致，见 `references/report-contract.md` 与 `references/failure-modes.md`。未落地项不能作为已支持流程执行，也不能回退套用高中物理。

# 高中化学学科索引

本入口只服务**高中化学**。这里汇总这门学科区别于通用流程的三样东西：**检查重点**（人读规范）、**工具集与输入格式**（机器读配置）、**拆分参数**（机器读配置）。共性流程只写一次，在入口 `SKILL.md`。

## 一、教学科一览

| 学科 | 状态 | 输入格式 | 工具集（calc 映射） | 拆分规则 | 特殊钩子 |
| --- | --- | --- | --- | --- | --- |
| 高中化学 | **已落地** | 源文件 `.docx / .doc / .md / .idml` → convert；单元 `第N题.md`（exam）/ `单元N.md`（lecture）+ `images/` | `calc chemistry_balance / stoichiometry / evaluate / solve / equality / simplify`；配平与计量必须实算 | `split_mode=section`；`exam_question_pattern` 为 `^(\d+)．`；`wrapped_patterns`=班型 / 例练；`nav_patterns`=直击课堂 / 本讲导航 | 化学用语检查清单；方程式配平与电荷守恒；离子 / 热化学方程式专项；独立解题冻结不启用 |

其他学科（高中物理 / 高中数学 / 高中语文 / 高中历史 / 初中英语 / 小学语文 / 小学数学）**不在本入口范围内**：它们是独立插件包 `dsh-jiaodui` 及其后续学科包的事，化学会话不得加载或套用它们的规范。需要核对别的学科口径时到对应包的 `references/subject-matrix.md` 查，而不是在本包内猜测。跨学科的组织方式与取舍见仓库 `docs/adr/0007-second-subject-entry-and-bundle-split.md`。

> 旧仓 `subjects/` 里另有 6 科（小学数学 / 小学语文 / 初中英语 / 高中语文 / 高中历史 / 高中物理）。本包只搬高中化学。

## 二、机器读配置 `jiaodui/data/subjects/高中化学.json`（运行时唯一来源）

化学的**工具集白名单、支持扩展名、拆分参数**落在**包内** `jiaodui/data/subjects/高中化学.json`。运行时只读这里（`JIAODUI_CONFIG_DIR` 可覆盖指向别的配置目录，用于开发/测试），**不会读会话目录里的同名文件**——工作区放一份 json 不能悄悄改掉工具白名单或拆分口径。

仓库根的 `config/subjects/` 是**人工可读镜像**，便于浏览与评审，**不是运行时来源**：改配置请改包内文件，再 `cp jiaodui/data/subjects/*.json config/subjects/` 同步；两份一致性由 `tests/test_packaging.py` 守着。

- `subject`：`高中化学`。
- `tools`：工具集白名单，本学科为 `["calc"]`。配置写了未知工具名会在读取时就报 `contract` 错，不再静默失效；`jiaodui calc --subject 高中化学` 按它校验本学科能否使用 calc。
- `quantities`：**本学科为空对象**（化学 v1 不建量表）。`jiaodui quantities --subject 高中化学` 稳定返回 `count: 0`；`calc dimensional` 传入 `{"quantity": …}` 时没有量表可交叉校验，化学计算一律按题面写显式单位表达式（如 `"mole/liter"`、`"gram/mole"`、`"kilojoule/mole"`），不要臆造化学量名。
- `extensions`：支持扩展名 `.docx / .doc / .md / .idml`。旧版二进制 `.doc` **不受支持**：CLI 会明确拒绝并提示先另存为 `.docx`（pandoc 的 OOXML 解析器读不了它）。
- `split_mode` / `section_pattern` / `section_extensions`：章节切分参数（`section`，`section_pattern` 留空走默认标题模式）。
- `wrapped_patterns` / `unwrapped_patterns`：讲义包裹标记（班型、例练）；化学沿用与高中物理相同的班型集合。
- `exam_question_pattern`：试卷题号规则 `^(\d+)．`（全角句点）。
- `nav_patterns`：需忽略的导航段标记 `直击课堂 / 本讲导航`。

### 拆分模式 `--mode`
- `exam`：试卷，产出 `第N题.md`，按题号规则切题。
- `lecture`：讲义，产出 `单元N.md`，按班型 / 例练包裹标记切单元。
- 默认走**规则拆分**；`precheck-split` 报出空单元 / 超长单元 / 异常首行时才升级**智能拆分**（拆分子 agent 出边界清单 → `slice --boundaries`）。讲义模式由拆分子 agent 先用 `slice --preview` 取**清理后**正文再定行号（主 agent 不读预览），预览与切片必须同 `--mode`/`--subject`；类型未知时拒绝，不默认 exam。用户指定类型直接采用，未指定时按入口检查结构 / 有限预览，不确定再问。

## 三、共性（只写一次，在 SKILL.md）

确定材料类型（用户指定或按入口有限预览，读取边界见 `SKILL.md` §2.1）→ 加载 `references/subjects/高中化学.md` 与本节配置口径 → 环境与宿主能力检查 → 转换 → 拆分 → 抽查 → 状态扫描 → 滑动窗口派单元子 agent → verify-report 闸门（自修 ≤3 轮）→ 整卷报告 → 主 agent 通读 → Word 批注版 → 交付 + 失败清单。产物命名、校验项、失败留痕见 `references/report-contract.md` 与 `references/failure-modes.md`。**未落地项不能作为已支持流程执行，也不能回退套用高中物理。**

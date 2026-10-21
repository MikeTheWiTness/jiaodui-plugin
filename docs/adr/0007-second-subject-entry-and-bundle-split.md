# ADR-0007：第二学科入口与 bundle 拆分

- 日期：2026-10-16
- 状态：已采纳；高中化学按本文落地，宿主真机验收与真实材料端到端仍须补证。
- 范围：在高中物理之后新增已落地学科时，入口 skill、学科配置与 DSH 插件包的组织方式。
- 关联：[ADR-0001：多学科入口与逐科落地](0001-m5-subject-entry-and-rollout.md)、[PRD](../PRD.html) 的 D7 / D22–D27、[学科矩阵](../../skills/jiaodui/references/subject-matrix.md)、[插件包 README](../../packages/dsh-jiaodui-chemistry/README.md)、[化学落地验证记录](../CHEMISTRY-VERIFICATION.md)。
- 边界：不改变报告契约、闸门与调度纪律；不改变 Python 核心的确定性算法，只新增学科配置。

## 1. 背景

ADR-0001 决策「一个入口，按需加载学科规范，共用调度与交付」，并用一张 `references/subject-matrix.md` 索引全部学科。物理作为唯一落地学科时，入口 `skills/jiaodui/SKILL.md` 里到处写着「只落地高中物理」「不回退套用物理流程」——这在单学科包内是准确的守卫语。

同时，宿主侧已经用 DSH bundle 分发：`packages/dsh-jiaodui` 声明一个 `jiaodui` preset（名称「校对」），把随包 skill 挂进 `skill-filesystem`，并注册学科无关的原生工具。

现在要新增高中化学，需求是：**做出一个新的插件包入口，不和高中物理的合并**。若沿用 ADR-0001 的单一入口，化学会话读到的仍是一份主要在讲物理的入口文件，两门学科在插件管理页也是同一个条目，无法单独安装、启用与卸载。

## 2. 决策

### 2.1 学科 = 独立 bundle；入口 skill 一科一份

| 载体 | 物理 | 化学 | 说明 |
| --- | --- | --- | --- |
| 插件包 | `packages/dsh-jiaodui` | `packages/dsh-jiaodui-chemistry` | 各自 `package.json`、`cordis.patch.yml`、README、locale、icon |
| preset 行 id / preset id | `preset-jiaodui` / `jiaodui` | `preset-jiaodui-chemistry` / `jiaodui-chemistry` | 行 id 供 profile patch 按 id 覆盖；两个 preset 可共存 |
| 入口 skill | `skills/jiaodui/` | `skills/jiaodui-chemistry/` | 各自 `SKILL.md` + references；frontmatter `name` = 目录名 |
| 学科规范 | `references/subjects/高中物理.md` | `references/subjects/高中化学.md` | 人读，只讲本学科 |
| 学科配置 | `jiaodui/data/subjects/高中物理.json` | `jiaodui/data/subjects/高中化学.json` | 机器读，运行时唯一来源 |
| preset 名称 / order | 校对 / 10 | 校对（高中化学）/ 11 | 插件管理页与 preset 选择器里的区分点 |

**共用而非复制**：Python CLI（含 `calc chemistry_balance` / `stoichiometry`）、`tools/index.js`、`tools/calc-schemas.json`、`tools/proposal-schema.json`、`tools/proposal-schema-v3.json`、`tools/proposal-schema-bind-current.json` 在学科之间完全一致。两个包的 `tools/` 逐字节一致，由 `tests/test_dsh_plugin_package.py::test_native_tool_modules_do_not_fork_between_bundles` 守着：工具是学科无关的，出现分叉就是隐患。

### 2.2 学科入口不得夹带其他学科口径

每个 `SKILL.md` 只讲本学科。化学入口不出现「受力图 / 量纲分析 / 高中物理流程」，物理入口不出现化学专属词，由 `tests/test_skill_docs.py::test_skill_entry_only_speaks_for_its_own_subject` 锁定。通用流程（产物命名、闸门、预算、宿主纪律、派发规则）在每份入口里都必须完整保留，由同一测试文件的双份字节一致与体积断言守护。

物理入口里原本的守卫语「未落地学科不得回退套用物理流程」保留：它描述的是**物理入口**面对未落地学科时的行为，而不是要求化学入口也这么写。

### 2.3 学科索引退化为本包自述

`references/subject-matrix.md` 不再充当跨包总索引：每个包里它只说明本学科的状态、机器读配置口径与共性流程入口，并声明其他学科由各自插件包负责。跨包总表属于文档层（[ADR-0001 的迁移表](0001-m5-subject-entry-and-rollout.md) 与仓库 README），不属于运行时 skill。

### 2.4 化学关闭量纲交叉校验

化学的 `quantities` 为空对象：`jiaodui quantities --subject 高中化学` 稳定返回 0 条，`calc dimensional` 传入 `{"quantity": …}` 时没有量表可比对。化学单位一律按题面写显式单位表达式（`"mole/liter"`、`"gram/mole"`…）或 `"dim:…"`。理由是化学量多由单位而非量纲刻画，仓促建表会把「量纲一致」误当成结论已验算；需要时再按真实语料增长量表，不在本次决策里预置。

### 2.5 化学试卷按题号拆分

化学 `exam_question_pattern` 取 `^(\d+)．`，与物理一致：先让真实材料能端到端跑通，出现别的题号习惯时按样本调整配置（同时改包内与镜像，`config/subjects/` 由测试锁定一致）。ADR-0001 里「化学无独立题号规则」的目标值随之作废，改为「待真实语料确认」。

### 2.6 发布与版本

一次发布同时带两个 bundle 与同一版本 wheel：`scripts/release/build-release.sh` 与 `prepare-smoke-package.py` 对**每一个**包执行与 CLI 的版本一致性校验，归档里两个包各自成目录，安装脚本只装一次 CLI。目标机可以只装其中一个 bundle。

## 3. 备选方案与取舍

| 方案 | 结论与理由 |
| --- | --- |
| 沿用 ADR-0001 的单一入口，化学只加 references 行 | 不采用（本次需求明确要求独立入口）。化学会话会读到主要在讲物理的入口，两科在插件管理页同一条目、无法单独装卸 |
| 独立 bundle，但两个包共用同一份 skill 目录 | 不采用。入口文件的学科守卫语、学科索引、命令示例都会互相污染；共享目录还会让「化学包改了入口、物理包跟着变」不可见 |
| 独立 bundle，并连 Python CLI 也按学科拆开 | 不采用。确定性核心是学科无关的库，拆开会产生两份报告契约实现，违反「核心逻辑只有一份」 |
| 化学 `quantities` 一次建满量表 | 不采用。化学量的量纲刻画争议大，仓促建表会误导「量纲一致即验算通过」；留空并在文档写明兜底写法更安全 |
| 化学试卷先不拆题（整份一个单元） | 不采用。单元过大会挤压上下文并更容易触发超长单元；先用与物理一致的题号规则跑通，再按样本收敛 |

## 4. 后果与待定项

正面影响：两门学科可以独立安装、启用、卸载与演进；化学会话的上下文里不再出现物理口径；新增学科有了可复制的落地形状（新包 + 新 skill + 新配置 + 测试行）。

代价与风险：

- **入口文档重复**：学科入口与多数 references 是副本，靠「仓库源 ↔ 随包副本字节一致」「两包 tools 不分叉」「入口不夹带他科口径」三类测试约束，但共性流程改动仍需逐份同步。
- **两包版本必须同步**：共用 CLI，任一包的版本漂移都会让自动发现找不到运行时；发布脚本已强制校验。
- **测试覆盖是静态的**：宿主工具目录、读图与落盘行为仍需真机验收，见 `packages/dsh-jiaodui-chemistry/host-probe/README.md`。
- 2026-10-16 已用真实高中化学讲义（11 单元 + 12 图）跑通确定性链路（拆分 → 闸门 → 整卷报告 → Word 批注版，锚点 11 = 标记 11 + 兜底 0、缺失 0），并实算 4 条方程式与 1 组计量；宿主真机与模型质量仍未覆盖，记录见 [化学落地验证记录](../CHEMISTRY-VERIFICATION.md)。

待定项（不在本次决策内假定已解决）：

- 化学试卷题号规则的最终形态，需要真实化学语料样本验证后再定；当前取与物理一致。
- 化学量表的构建时机与条目范围。
- 后续学科（小学数学 / 高中语文 / 高中历史 / 初中英语 / 小学语文）是否继续「一科一包」；本 ADR 记录的是化学落地时的形状，不预先承诺其余学科的组织方式。
- 两个 bundle 是否需要一个共同的 icon 设计规范（当前化学包沿用物理包图标，只改 locale 标题）。
- 是否把「学科入口」的公共部分抽成一层可继承的 skill 片段；当前显式选择复制，优先保证化学入口不出现物理口径。

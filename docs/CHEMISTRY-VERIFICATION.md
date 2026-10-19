# 高中化学落地验证记录（2026-10-16）

本文件记录高中化学作为**独立插件包**落地时的确定性链路验证。宿主真机验收（父/子 agent 工具目录、子 agent 真实读图、单元子 agent 派发）**尚未执行**，见文末「未覆盖范围」。

## 1. 结论

| 范围 | 结论 |
| --- | --- |
| 化学学科配置可被运行时读取与校验 | 通过 |
| 化学 `calc` operation（配平 / 计量 / 电荷守恒）端到端可用 | 通过 |
| 真实化学讲义从 raw → split → 逐单元闸门 → 整卷报告 → Word 批注版 | 通过（11 单元，锚点 11 = 标记 11 + 兜底 0，缺失 0） |
| 闸门双向契约（不合格必拒 + 合格必收） | 通过 |
| 两学科包结构契约、skill 双副本一致、tools 不分叉 | 通过（`pytest` 全绿） |
| 宿主真机（DSH 会话内 preset、子 agent、读图） | **未验证** |
| 模型校对质量（误标 / 漏检） | **未评估**（本次不含模型判断） |

## 2. 验证对象

- 代码版本：`c5af3545fa357179c972bed46d965be50b472fbd`（工作树另有本次化学落地改动与既有未提交改动）
- CLI 版本：`jiaodui 0.1.0`
- 学科：`高中化学`（`jiaodui/data/subjects/高中化学.json`，镜像 `config/subjects/高中化学.json`）
- 素材（新仓外只读复制，未修改旧仓）：
  - 来源：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元10..20`
  - 口径：真实高中化学讲义（原电池）的既有拆分单元 Markdown + 单元配图，共 11 个单元、12 张图
  - 单元 Markdown 合计 SHA-256：`199068094ad7d4a774faf6b924c9f96d69ea3f22a51fc097f9805f8cc8fa6c52`
  - 单文件示例 `单元10/单元10.md` SHA-256：`cff62cba4ff98b59a5ac2e10e43f8df150997a160d7b214cbe8148bb69e75d91`
- 运行环境：仓库内独立 `.venv`（Python 3.12），`pandoc` 可用（`check-env` 通过）
- 运行位置：工作区 `/tmp/jiaodui-chem-verify/work`（新仓外临时目录，产物不污染仓库 `校对/`）

> 说明：本次把既有单元 Markdown 重新拼成 raw 再走 `split --mode lecture`，覆盖的是「拆分 → 闸门 → 汇总 → Word」的确定性链路与化学拆分规则；它不等价于从原始 DOCX 开始导入（`convert` 的 Word 嵌套表格路径不在本次范围内）。

## 3. 执行的检查项

脚本：`/tmp/jiaodui-chem-verify/run_chemistry_e2e.py`（一次性验收脚本，未入仓；检查项与结果见下）

| # | 检查 | 命令 / 依据 | 结果 |
| --- | --- | --- | --- |
| 1 | 环境预检 | `jiaodui check-env --json` | ok |
| 2 | 化学量表为空但命令可用 | `jiaodui quantities --subject 高中化学 --json` → `count=0` | ok |
| 3 | 化学学科工具白名单放行 | `jiaodui calc … --subject 高中化学` | ok |
| 4 | lecture 拆分 | `jiaodui split <raw> --subject 高中化学 --mode lecture --images-dir … --work-root … --legacy-layout` → 11 单元 | ok |
| 5 | 拆分预检 | `jiaodui precheck-split <paper_dir> --json` → 11 单元 | ok |
| 6 | 契约单元命名 | 单元目录为精确名 `单元N` | ok |
| 7 | 闸门拒绝伪造正文 | 报告正文与源文不符 → 退出码 4、`verify_failed` | ok |
| 8 | 闸门接受合格报告 | 11 个单元逐一 `verify-report --unit … --json` → `ok: true` | ok |
| 9 | 整卷报告 | `jiaodui build-report <paper_dir> --work-root … --legacy-layout --json` → `complete: true`，included 11 / failed 0 | ok |
| 10 | Word 交付复核 | `jiaodui build-docx …` → `ok: true`，标记 11 = 锚点 11 + 公式兜底 0，缺失 0 | ok |
| 11 | 配平实算（4 条真实方程式） | `calc chemistry_balance`：`Fe+O2`、`Zn+HCl`、`MnO2+HCl`、`Cu+HNO3` 均返回最简整数系数 | ok |
| 12 | 计量实算 | `calc stoichiometry`：4 g H₂ → H₂O 得 35.744 g | ok |
| 13 | 电荷守恒可实算 | `calc equality`（化学关闭量纲交叉校验）→ `true` | ok |

配平结果逐条：

- `Fe + O2 -> Fe2O3` → `4Fe + 3O2 -> 2Fe2O3`
- `Zn + HCl -> ZnCl2 + H2` → `Zn + 2HCl -> ZnCl2 + H2`
- `MnO2 + HCl -> MnCl2 + Cl2 + H2O` → `MnO2 + 4HCl -> MnCl2 + Cl2 + 2H2O`
- `Cu + HNO3 -> Cu(NO3)2 + NO2 + H2O` → `Cu + 4HNO3 -> Cu(NO3)2 + 2NO2 + 2H2O`

产物（临时目录，未入仓）：

- `校对报告/初识原电池_整卷报告.md`
- `校对Word/初识原电池_校对批注版.docx`

## 4. 静态契约检查（`pytest`）

本次新增 / 扩展的契约由测试锁定，`.venv/bin/python -m pytest -q` 全绿（1321 passed / 4 subtests，两种口径一致）：

- 化学学科配置存在、与镜像逐字一致、通过 schema 校验、与物理共用拆分口径（`tests/test_packaging.py`）。
- 化学 `calc` 两个 operation 与 `quantities` 空表的 CLI 行为（`tests/test_calc_cli.py`）。
- 两个 bundle 的 manifest / preset / skill 挂载 / 计算 schema 漂移 / 子代理工具面（`tests/test_dsh_plugin_package.py`）。
- 化学子代理 `toolFilter.allow` 含 `jiaodui_calc_chemistry_balance` / `jiaodui_calc_stoichiometry`。
- 两包 `tools/` 逐字节一致（禁止学科无关工具分叉）。
- 每个入口 skill 只讲自己那门学科，且都保留核验纪律与体积上限（`tests/test_skill_docs.py`）。

> **2026-10-18 后续变更**：DSH 0.2.1 起 `tool-subagent` 不再接受 `toolFilter`；上文关于 `toolFilter.allow` 的验证记录对应旧机制，现行实现改由子 preset `jiaodui-chemistry-unit` + `toolset: unit` 决定，静态断言已同步到 `tests/test_dsh_plugin_package.py` 与 `tests/test_dsh_plugin_tool_behavior.py`。

## 5. 仓库外安装验证（wheel）

`python -m build --wheel` 产出的 `jiaodui-0.1.0-py3-none-any.whl` 内含 `jiaodui/data/subjects/高中化学.json` 与 `高中物理.json`。把它装进一个独立 venv（仅装运行依赖），在仓库外的空目录执行：

- `jiaodui calc chemistry_balance --subject 高中化学 --param "equation=C2H5OH + O2 -> CO2 + H2O"` → `C2H5OH + 3O2 -> 2CO2 + 3H2O`
- `jiaodui quantities --subject 高中化学 --json` → `count: 0`
- 未落地学科仍被拒：`--subject 高中语文` → 退出码 5 `not_found`（找不到该学科配置，不会静默回退到物理）

说明「化学配置随包分发、仓库外可用、未落地学科不回退」三条成立。

## 6. 未覆盖范围（不得据此宣称已完成）

1. **宿主真机**：化学 preset「校对（高中化学）」在真实 DSH 会话里的父/子工具目录、`read_image` 实读、零 shell 校对、停止语义均未验收；清单见 `packages/dsh-jiaodui-chemistry/host-probe/README.md`。
2. **模型判断质量**：本次未派单元子 agent，无误标 / 漏检 / 严重度口径数据；化学规范中「配平与计量必须实算」的实际遵从度需真机运行观察。
3. **原始 DOCX 导入路径**：未用化学 Word 原件验证 `convert` 的嵌套表格判定与讲义清理六步。
4. **试卷路径**：化学试卷 `exam_question_pattern = ^(\d+)．` 沿用物理，尚未用真实化学试卷样本验证题号习惯。
5. **发布产物**：`scripts/release/build-release.sh` 已扩展为同时打两个 bundle，但未实际执行完整发布（需要 pandoc 与打包环境；发布脚本拒绝覆盖已存在的归档）。

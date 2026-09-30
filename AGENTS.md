# AGENTS.md

本文件是新仓 JiaoDuiAgentSkill（Python 包 `jiaodui`）唯一的 AI 约定文件。

## 项目概述

把 K-12 校对流程从「自研 agent 循环 + GUI」重构为「宿主 agent 驱动 + 可分发 skill + 确定性工具核心」。

- 判断交给 agent，确定性交给 Python。核心逻辑只有一份，CLI / MCP / skill 三个壳都不含逻辑（只做参数解析、格式化输出、协议转换）。
- Python 侧零凭证：不含 `.env`、不含 key 管理、不含 `env_config`、不调用任何模型 API。
- 旧仓 `../JiaoDuiAgent` 完全冻结，只读参考；新仓不以它为运行时依赖。复制只做一次，之后不回修旧仓。

需求与验收以 [docs/PRD.html](docs/PRD.html) 为准，执行顺序见 [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)。

## 工作语言

全程使用简体中文交流，代码注释与 docstring 用中文。

## 环境

- Python 3.12；用 pyenv / Homebrew / python.org 的独立解释器创建仓库内 `.venv`，不加 `--system-site-packages`，依赖全部装入该环境。不要用 DSH 自带的签名 Python 创建 CLI 环境：它可能拒绝加载 pip 安装的 matplotlib 等原生扩展（Team ID 不一致）。
  ```bash
  python3.12 -m venv .venv
  .venv/bin/python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e '.[dev,render]' build
  ```
- `.venv` 也可指向仓库内已验证的独立环境（本机为 `.venv-cli`）；插件仍从 `.venv/bin/jiaodui` 自动发现 CLI。旧 DSH 环境只作备份，不参与测试或运行。
- 外部依赖 `pandoc`（docx↔md）；路径可用 `JIAODUI_PANDOC` 覆盖。
- 测试：`.venv/bin/python -m pytest -q`；全量测试用 `.venv/bin/python -m pytest -o addopts='' -q -rs`（取消默认标记过滤）。CLI 子进程测试用 `sys.executable`，确保与测试进程使用同一环境；pip 安装优先清华源。

## 分层与禁令

- `jiaodui/` 是唯一核心逻辑。`cli.py` 只做参数解析与输出；不得在壳里写业务分支。
- 禁止依赖 `langchain` / `pydantic` / 任何 LLM SDK；禁止读环境变量里的 key。
- 允许依赖 `sympy` / `python-docx` / `Pillow` / `lxml` / 标准库；`matplotlib`、`playwright` 必须惰性 import 且缺失时优雅降级。

## 契约（硬约束，改流程不改契约）

- 产物默认位于当前工作区 `校对/<材料名>/`，允许 `source/`、`raw/`（`<材料名>_raw.md`、`<材料名>_images/media/`）、`units/<材料名>/`、`_校对记录.json`、`校对报告/`、`校对Word/`。单元内只允许：`第N题.md`、`单元N.md`、`images/`、`_校对报告.md`、`_校对数据.json`、`_校对失败.md`及既有跳过标记。禁止自由命名的 attempt / 副本文件；报告只保存当前交付，轮次与执行摘要进入记录。写入必须校验真实路径位于工作区内，见 ADR 0002。
- `verify-report` 是模型产出与下游之间的唯一闸门；新报告不通过即不算完成。历史报告可 `--legacy` 读取转换，但不得冒充新契约已完成。
- `build-report` / `parse-report` / `build-docx` 必须复核当前状态，拒绝消费未通过的报告。
- 状态只由磁盘产物推导（`status`），不依赖会话内存；新布局完成还须匹配当前轮次的交付登记、报告与单元输入摘要，旧失败记录不使有效的本轮完成状态回退。
- 退出码稳定：0 成功、1 未预期、2 用法、3 环境、4 校验失败、5 未找到、6 契约、7 不支持。失败向 stderr 输出一行结构化 JSON。

## 测试原则

以「用测试锁定行为契约」为目的，红→绿只适用于行为可规格化、有稳定接缝的确定性代码：

- 确定性层（解析、标记、校验、切片、批注锚点、报告拼接）：先写失败测试，再实现。
- 闸门双向契约：不合格必被拒 + 合格必被接受；旧报告作兼容语料要逐份标注预期结果，不能未经核对全标为合格。
- 编排层：模拟派发/返回覆盖窗口补位、失败重派、断点扫描；宿主读图与落盘属真实冒烟，不能靠模拟替代。
- 测试预期值必须来自独立来源（规格/已知样本），不得用与实现相同的逻辑重算。

## 中间产物与命名

- 校对报告与数据落盘遵循契约名；LLM 原始返回（若将来由宿主落盘）与结构化解析结果分文件。
- 失败必须留痕可见：`_校对失败.md` 记录失败原因 + 最后一次 verify 完整输出 + 产物摘要；不得静默截断或丢弃。

## 常用工作流

| 阶段 | 机制 | 产出 |
|---|---|---|
| 需求讨论 | grill 访谈，一次一个问题；事实先查，决策才问 | 更新 PRD / ADR |
| 计划 | todo_write（当前步骤）+ goal（跨轮长期目标） | 会话内任务清单 |
| 实现 | 确定性代码红→绿→重构；壳保持零逻辑 | feat commit |
| 验证 | `.venv/bin/pytest -q`；真实语料双向契约；宿主冒烟 | 测试记录 |

## 禁止事项

- 不修改旧仓 `../JiaoDuiAgent`；不复刻旧仓运行时依赖。
- 不在 Python 侧引入凭证、模型调用或 GUI/打包。
- 主 agent 仅可在入口为未明确的学科或材料类型按需检查结构、节选少量源文；用户已明确的项直接采用并跳过该项识别，学科与类型共用每份材料最多 2,000 字符的预览额度。大量嵌套表格承载正文是讲义强信号；类型不确定时询问，不默认试卷。具体读取边界见入口 skill / ADR 0003；后续不得逐单元读取源文进主上下文，单元子 agent 仍只收路径。
- 不自动修改源文件；失败单元交人裁定。

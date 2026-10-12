# JiaoDuiAgentSkill

K-12 多学科校对流程的 agent 驱动重构：**判断交给宿主 agent，确定性交给 Python**。

- 需求与契约：[docs/PRD.html](docs/PRD.html)
- 校对流程改造记录（M0–M6边界与宿主验收）：[docs/PROCESS_REWORK.md](docs/PROCESS_REWORK.md)
- 执行顺序与完成判据：[docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)
- M0—M6 收口计划：[docs/PLAN-rework-continuation.md](docs/PLAN-rework-continuation.md)
- 结构化并入 main 的实施计划：[docs/UNIFY-PLAN.md](docs/UNIFY-PLAN.md)
- M5 架构决策：[ADR-0001：多学科入口与逐科落地](docs/adr/0001-m5-subject-entry-and-rollout.md)
- 交付闸门：[ADR-0004：闸门单一实现（含图片资源）](docs/adr/0004-gate-single-implementation.md)
- 学科工具：[ADR-0005：量纲校验的声明形态与多解判定](docs/adr/0005-dimensional-declaration-and-ambiguity.md)
- 仓库约定（AI 助手必读）：[AGENTS.md](AGENTS.md)
- 缺陷修复计划：[docs/REMEDIATION.md](docs/REMEDIATION.md)
- M0 验收：[docs/M0.md](docs/M0.md)　·　M1 端到端验收：[docs/M1.md](docs/M1.md)
- 基线复算：[docs/BASELINE.md](docs/BASELINE.md)
- 入口与拆分迁移核对：[docs/ENTRY_MIGRATION.md](docs/ENTRY_MIGRATION.md)
- 可分发 skill：[skills/jiaodui/SKILL.md](skills/jiaodui/SKILL.md)
- DSH 插件包（M7 换壳的首次尝试）：[packages/dsh-jiaodui/README.md](packages/dsh-jiaodui/README.md)

## 当前状态：第7章结构化报告主链已并入 main

- **正常路径**：结构化主链——子 agent 只提交 schema v2 结构化提案，报告由程序从不可变源文生成，经 `verify-report` 闸门与父复核后交付；`build-report` / `build-docx` 只消费通过校验的当前版本。
- **只读兼容**：旧 Markdown 报告链保留读取与修复入口（`verify-report` / `parse-report` 兼容读取，`repair-report` 只服务旧报告），但**不再作为正常交付路径**；旧布局写入须显式 `--legacy-layout`。
- **宿主侧**：`dsh-jiaodui` 插件包提供 26 个原生工具与「校对」preset（父侧有 shell 与只读搜索，子侧封闭 20 项）。真机新会话验收（父/子 catalog、`read_image` 实读、零 shell 真实校对、停止语义）八条已通过。
- **已合并的接口语义**：每单元六类恢复预算（`call_correction`/`calc_representation`/`report_repair`/`targeted_review`/`technical_redispatch`/`image_schema_fix`），恢复记账以 `attempt_id` 幂等、错误码确定性映射类别、图片格式修复连带扣一次 `call_correction`；旧清单可读但未授权，重授权时按单元保守迁移。
- **测试基线**：双口径 `pytest` 全绿（合并前分支 1126 passed / 5 skipped）。
- **仍待办**：Phase 2 收尾（宿主 profile 切回仓库根包、处置实验 worktree、文档同步）。

已实现的核心与入口命令：

| 命令 | 作用 |
| --- | --- |
| `jiaodui check-env` | 环境预检（无凭证项），区分本地依赖与宿主能力 |
| `jiaodui inspect-source <file>` | 只读检查 Word 嵌套表格；显式 `--preview-chars 0..2000` 才返回有限正文 |
| `jiaodui convert <file> --mode exam\|lecture` | 按已确认类型导入 docx / idml / md，记录类型与来源 |
| `jiaodui split <raw_md> --subject <学科> [--mode exam\|lecture]` | 沿用材料类型；默认规则，`--strategy manual\|none` 支持人工标记/整篇 |
| `jiaodui precheck-split <dir>` | 拆分预检：单元数 / 首行 / 字符数分布 / 空与超长单元 |
| `jiaodui slice --boundaries <f> [--mode] [--subject]` | 默认按源文行区间全量切片，写前核对非空行覆盖；明确节选用 `--scope excerpt --scope-reason`；`--preview` 供定行号 |
| `jiaodui status <paper_dir>` | 扫描单元状态（未开始 / 已交付未过校验 / 已完成 / 失败） |
| `jiaodui verify-report --unit <dir>` | 交付即校验：格式 + 原因对应 + 严重度 + 原文完整性 + 图片资源 |
| `jiaodui parse-report --unit <dir>` | 旧Markdown报告兼容解析；默认拒绝未过校验的报告 |
| `jiaodui unit-read --task-id ID --unit-id ID` | 按身份分页读取源文和实际图片读取清单（最多2000行） |
| `jiaodui unit-locate --task-id ID --unit-id ID --phrase TEXT` | 查询重复短语候选、安全区间与版本绑定位置ID |
| `jiaodui unit-snapshot --task-id ID --unit-id ID` | 获取run、输入、报告和数据组成的提交快照 |
| `jiaodui unit-submit ...` | 从schema v2结构化建议生成全文报告并原子校验登记 |
| `jiaodui unit-recovery / unit-event` | 按类别消费有限预算；recovery 可传 `--failure-json` 由 core 派生指纹，同时记录阶段事件 |
| `jiaodui calc-schema [--operation OP]` | 从核心参数元数据导出operation-specific JSON Schema |
| `jiaodui unit-schema` | 导出结构化建议schema v2 |
| `jiaodui repair-report --unit <dir> [--apply]` | 旧Markdown报告完整性辅助，默认只预览 |
| `jiaodui calc <op>` | sympy 符号计算沙箱（白名单 + 容差，默认不回显生成代码）；`--subject` 校验工具族并注入物理量表 |
| `jiaodui quantities --subject <学科> [--search 词]` | 只读列出学科物理量表（不进 agent 上下文，按需查） |
| `jiaodui build-report <paper_dir>` | 生成整卷报告；失败单元写占位，`complete: true` 才表示正式完整 |
| `jiaodui build-docx <paper_dir>` | Word 批注版，生成后复核实际锚点，缺失必须为 0 |

所有命令支持 `--json`；失败向 stderr 输出一行结构化 JSON，退出码稳定（0/1/2/3/4/5/6/7）。

用户指定讲义或试卷时直接采用；未指定时主 agent 先看 Word 嵌套表格结构，主体大量使用重复嵌套表格时按讲义处理。证据不足才有限预览，不确定则询问。学科与类型分别补缺，共用每份材料 2,000 字符的预览额度。核心只统计结构事实并执行参数；两类材料共用后续校对和交付流程。完整规则见 [ADR 0003](docs/adr/0003-material-type-entry.md)。

## 工作区产物

新运行在当前工作区自动创建 `校对/<材料名>/`，分别用 `source/`、`raw/`、`units/<材料名>/`、`校对报告/`、`校对Word/` 保存源文件副本、中间产物和最终报告。执行模式、task/unit身份和恢复事件写入材料记录。写入命令（convert / split / slice 非 preview / execution-policy / unit-submit / unit-recovery / unit-event / build-report / build-docx / repair-report --apply）必须由宿主注入 `JIAODUI_WORK_ROOT`，或显式传 `--work-root /绝对工作区`；只读命令独立可用。源文件可位于工作区外，但产物不可越界。

新材料用 `unit-snapshot` 与 `unit-submit` 绑定当前源文、轮次和交付版本，程序生成报告后统一 verify、解析并登记；旧Markdown报告仍可显式走 `verify-report` / `parse-report` 兼容路径。若拆分结果与当前单元集不同，用 `split` / `slice --replace-units`（陈旧单元归档到 `units/<材料名>/.superseded/<run_id>/`，只移动不删除）。同名源文件变化拒绝覆盖，可用 `--material-name` 指定新材料名。历史产物写入使用 `--legacy-layout`，仍需授权工作区。详见 [ADR 0002](docs/adr/0002-workspace-material-layout.md)。

## 环境

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e '.[dev,render]' build
.venv/bin/jiaodui check-env --json
.venv/bin/python -m pytest -o addopts='' -q -rs
```

使用 pyenv / Homebrew / python.org 的独立 Python 3.12，不继承系统包。macOS 上不要用 DSH 自带的签名 Python 创建此环境，否则 pip 安装的原生扩展可能因 Team ID 不一致被拒绝加载。环境迁移时可让 `.venv` 指向已经验证的仓库内独立环境，插件的 CLI 自动发现路径不变。

需要外部 `pandoc`（docx↔md）；`render` 可选依赖组提供 matplotlib 公式图片渲染，`classics` 提供 Playwright。未安装时对应能力仍优雅降级；开发与 CI 安装 `render` 以实际执行公式和 Word 图片测试。

## 架构

```
jiaodui/           Python 包：确定性核心 + CLI 壳（唯一逻辑所在）
  cli.py           命令薄壳（参数解析、输出、退出码）
  inspect_source.py 只读结构统计与有限节选
  material_type.py  解析宿主给出的类型与来源
  verify.py        verify-report 闸门（PRD §5.2）
  markers.py       标记语法与真实性审计（单一源）
  report_parse.py  报告 → _校对数据.json
  split.py         规则拆分 / 切片 / 预检
  convert.py       docx / idml / md → _raw.md
  calc/            sympy 沙箱（白名单 + 容差）
  docx_report.py   Word 批注版生成与锚点复核
jiaodui/data/subjects/  机器读学科配置（运行时唯一来源）
config/subjects/   同上的人工可读镜像（改配置请改包内那份）
skills/jiaodui/    人读 skill 与 references
tests/             行为契约测试
```

## 纪律

- 旧仓 `../JiaoDuiAgent` 完全冻结，只读参考；新仓不以它为运行时依赖。
- Python 侧零凭证：不含 `.env` / key / 模型调用。
- 新报告必须通过 `verify-report` 才算完成；历史报告可读取转换，但不因文件存在被视作已通过新契约。

# JiaoDuiAgentSkill

K-12 多学科校对流程的 agent 驱动重构：**判断交给宿主 agent，确定性交给 Python**。

- 需求与契约：[docs/PRD.html](docs/PRD.html)
- 执行顺序与完成判据：[docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md)
- 仓库约定（AI 助手必读）：[AGENTS.md](AGENTS.md)
- M0 验收：[docs/M0.md](docs/M0.md)　·　M1 端到端验收：[docs/M1.md](docs/M1.md)
- 基线复算：[docs/BASELINE.md](docs/BASELINE.md)
- 可分发 skill：[skills/jiaodui/SKILL.md](skills/jiaodui/SKILL.md)

## 当前状态：M1（高中物理端到端竖切已跑通）

M0 骨架（可安装 `jiaodui` 包 + 11 个 v1 命令）之上，已在**当前代码**上完成高中物理一条真实竖切：
`convert → split（含完整讲义导入清理）→ 5 个单元子 agent 校对 → verify-report → build-report → build-docx`。
真机结果：5/5 单元通过校验（28 条标记）；Word 复核 **标记 28 = 锚点 28 + 公式兜底 0，缺失 0**，
28 条批注均带修改原因；不合格报告被排除出汇总与交付（反向验证退出码 4 / 6）。
样本、单元源文与报告冻结在 [evaluation/m1](evaluation/m1/README.md)，可还原后独立复现。详见 [docs/M1.md](docs/M1.md) §9。

已实现 11 个 v1 命令：

| 命令 | 作用 |
| --- | --- |
| `jiaodui check-env` | 环境预检（无凭证项），区分本地依赖与宿主能力 |
| `jiaodui convert <file>` | docx / idml / md → `_raw.md` |
| `jiaodui split <raw_md> --subject <学科> --mode exam\|lecture` | 规则拆分出单元目录与源文、图片 |
| `jiaodui precheck-split <dir>` | 拆分预检：单元数 / 首行 / 字符数分布 / 空与超长单元 |
| `jiaodui slice --boundaries <f> [--mode] [--subject]` | 按边界清单确定性切片；`--preview` 打印讲义清理后正文供定行号 |
| `jiaodui status <paper_dir>` | 扫描单元状态（未开始 / 已交付未过校验 / 已完成 / 失败） |
| `jiaodui verify-report --unit <dir>` | 交付即校验：格式 + 原因对应 + 严重度 + 原文完整性 |
| `jiaodui parse-report --unit <dir>` | 报告 → `_校对数据.json`（默认拒绝未过校验的报告） |
| `jiaodui calc <op>` | sympy 符号计算沙箱（白名单 + 容差，默认不回显生成代码） |
| `jiaodui build-report <paper_dir>` | 整卷报告：只拼入通过校验的正文，失败写占位 |
| `jiaodui build-docx <paper_dir>` | Word 批注版，生成后复核实际锚点，缺失必须为 0 |

所有命令支持 `--json`；失败向 stderr 输出一行结构化 JSON，退出码稳定（0/1/2/3/4/5/6/7）。

## 环境

```bash
python3.12 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -q sympy pytest
.venv/bin/python -m pip install -e .
jiaodui check-env
```

需要外部 `pandoc`（docx↔md）；`matplotlib`、`playwright` 为可选能力，缺失时优雅降级。

## 架构

```
jiaodui/           Python 包：确定性核心 + CLI 壳（唯一逻辑所在）
  cli.py           11 个命令的薄壳（参数解析、输出、退出码）
  verify.py        verify-report 闸门（PRD §5.2）
  markers.py       标记语法与真实性审计（单一源）
  report_parse.py  报告 → _校对数据.json
  split.py         规则拆分 / 切片 / 预检
  convert.py       docx / idml / md → _raw.md
  calc/            sympy 沙箱（白名单 + 容差）
  docx_report.py   Word 批注版生成与锚点复核
config/subjects/   机器读学科配置
skills/jiaodui/    人读 skill 与 references
tests/             行为契约测试
```

## 纪律

- 旧仓 `../JiaoDuiAgent` 完全冻结，只读参考；新仓不以它为运行时依赖。
- Python 侧零凭证：不含 `.env` / key / 模型调用。
- 新报告必须通过 `verify-report` 才算完成；历史报告可读取转换，但不因文件存在被视作已通过新契约。

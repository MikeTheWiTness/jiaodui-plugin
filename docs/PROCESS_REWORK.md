# 校对流程改造执行记录（实验分支）

依据 EasyUse《校对流程改造执行计划》。用户已澄清“第7条”指计划**第7章：定位建议与程序生成全文报告**，不是§1.1第7项。M2定位、M3结构化主链及依赖它们的M4审查全部隔离在 `feature/structured-report-pipeline`，不部署、不合入main；main维持旧Markdown报告主链，仅保留兼容改造。

## M0现状

- 初始main为`abfea6c`，工作树干净。`.venv`指向仓内独立`.venv-cli`；Python 3.12.13，editable CLI，pandoc 3.9.0.2。
- 改造前全量基线941 passed、4 subtests passed；后续只跑合成/临时目录的定向测试，不重跑既有业务样本。
- 已确认桌面profile的`node_modules/dsh-jiaodui`是软链，指向仓库根`packages/dsh-jiaodui`。未改profile或手动替换安装包；实验源码必须移到独立worktree，根目录回到main，避免下次重载意外加载实验链。官方新安装/重启/新会话验收仍待完成。
- 实际安装的ASAR以只读方式按归档索引提取供审计，未修改宿主或用提取副本作为部署源码。确认skill-filesystem支持`includeDefaultRoots:false`，默认来源是项目`.dsh/skills`、`.agents/skills`、用户dshHome/agentsHome及宿主bundled根。subagent支持`toolFilter`和`maxDepth`。配置可表达排除默认skill与子工具allowlist，实际新会话仍须验收。

## 实验实现

- **M1部分**：轮次执行模式与预算持久化；preset去掉shell、关闭web/goal/plan/fork。聚合fs必须暂保留真实read_image；父只读工具细分尚未实现，不能称完全隔离。
- **M2**：task/unit ID、源码SHA绑定、Unicode码点位置和重复词候选、安全公式/加粗范围；calc schema从核心元数据导出。
- **M3初版**：schema v2提交少量建议，程序生成全文；长度封套保护正文中的报告标题/装饰行；快照CAS和材料锁，异常回滚报告/数据/清单，登记为最后提交标志。初版不能无损承载原文字面含`|`/标记括号的内容，只能明确拒绝；**P3 已按 ADR 0006 补齐可逆特殊字符编码与正文/信封契约**，见下节。
- **M4初版**：assumptions/symbols/images/calculations首轮证据、必需自查项；真实calc call_id与单元源码/轮次/结果关联；父复核绑定输入/建议/自查/报告hash。最新退回撤销旧接受。技术报告仍可汇总通读，但unreviewed时complete=false、Word拒绝。
- **M5部分**：恢复类别累计、失败指纹、阶段事件、显式取消来源API。调度尚依赖宿主/父代理主动登记；插件中断来源不得猜为用户。预算耗尽留痕，不能换agent刷新额度。
- **M6部分**：Word与报告解析共享v2正文边界；旧parse/repair拒绝覆写v2数据。诊断文件生成与正式complete分离。双skill和bundle schema有漂移测试。

## P3无损契约（ADR 0006，已完成）

格式决策写在实施之前：新增 [ADR 0006](adr/0006-v2-lossless-marker-encoding-and-envelope.md)。按 D2 走「v2 正文内反斜杠转义 + 唯一反转义入口」，并补齐两处计划外的必要条件——① 语法检查只看结构分隔符，字段内容一律屏蔽（否则合法报告会被自己内容判成括号不配对/字段数错误）；② 正文/信封边界、`extract_body` 唯一提取点、空白正文显式拒绝。

落地：

- `markers.py`：新增 `escape_marker_field` / `unescape_marker_field` / `is_v2_report` / `mask_marker_fields`；标记正则改为「反斜杠加任意字符视为整体」，原文字段与改为字段都能容纳转义后的 `\|`、`\【`、`\】`；`split_marked_body` / `audit_markers` 增加显式 `escaped` 参数（v1 默认，不转义也不反转义）；`scan_math_spans` 的字段屏蔽改用等长结构屏蔽。
- `report_suggestions.py`：删除三处硬拒绝（原 `:205` 源文含标记语法、`:233`/`:234` 原文字面与改为含括号或竖线），改为写入侧转义；`source_sha256`（文件字节）与 `body_sha256`（正文文本）分别校验并让诊断指明是哪一项；新增 `proposal.empty-body`。
- 四个消费点接线：`verify.py`（语法、字段、完整性全部带 `escaped`）、`report_parse.py`（corrections 内容反转义）、`docx_report.py`（审计与 `_mask_markers` 反转义）、`unit_delivery.py`（`extract_body` 计算正文摘要、快照文件摘要作为 `expected_source_sha256`）。`report_repair` 保持 v1 语义——它已拒绝 v2 报告。
- 不放宽拒绝：空原文、空操作、无唯一位置、区间重叠、乱序、`split_marked_body != 正文` 全部保持拒绝；`verify-report` 仍是唯一闸门。

测试与口径：新增 `tests/test_marker_escape.py`、`tests/test_report_suggestions.py` 的执行计划 §11.1/§11.2 场景（竖线/标记括号/反斜杠/emoji/组合字符/零宽/CRLF/跨行公式无损恢复、空正文拒绝、21 字符短正文放行、v2 不剥信封、反向用例仍拒绝）。双口径全量 **1043 passed / 0 failed / 5 skipped**（P3 前 989 + 5 skip；5 个 skip 是 worktree 内语料路径依赖，非真跳过）；带 `JIAODUI_LEGACY_CORPUS` 的旧语料 4/4 与 `test_m1_fixture` 3/3 保持预期。实测冻结语料无一份含 `\】` 边界写法，故正则扩展不改变 v1 既有预期。

## 安全复核

发现并修复：父复核CLI参数接线错误；旧parse会丢proposal并绕复核；同hash退回未撤销接受；Word按首次报告标题切段吞标记；移除fs会丢read_image。通用兼容修复由独立工作树处理，不要求合并实验审查功能才能使用main。

## 隔离回放

在仓库工作区中新建第4/5讲完整材料名加“流程改造回放-20261009”，写入前核对两目录不存在。旧EasyUse材料只读源文件副本作输入，不读旧报告、不修改原稿/旧记录。第4讲拆11单元、图片10；第5讲拆12单元、图片14，缺失均0。

本会话首次真实视觉探针通过，实际read_image观察与参考一致。回放在开发会话中使用CLI/core退路，不是新校对preset安装验收。关键单元由路径/ID派干净子agent；主agent不逐单元读取源文，最终只通读汇总报告。

关键7单元回放结果：5个技术提交通过（不是最终父审完成），2个失败（第4讲练9calc证据绑定不匹配；第5讲练1图片证据结构/调用格式失败），完整错误和摘要保留在契约失败文件。其余16单元未开始，整份complete=false。父代理已通读两份汇总报告并将第4讲练5的g/悬点、第4讲练8传播方向语义按hash定向退回（每单元已消费1轮复核预算）；不能为凑Word或既有标记数刷新失败预算、伪造全部通过。3份证据超长行在报告展示修复预算内分行登记新revision；第5讲练3的该类额度已满，未继续变更，其余原报告保留。

## 未完成与交付限制

- 本轮尚不满足M0—M6全部验收：完整强类型父工具（P4）、错误分类与自动心跳/取消闭环（P5）、实际安装方式、新会话父子catalog（P2）均需继续。P3 已收口特殊字符无损编码与正文/信封契约。
- 整份回放必须所有必需单元技术通过、父复核当前版本且Word结构/图片/批注记账通过才可交付；有未开始、失败或unreviewed时只交诊断，不生成冒充完整的Word。
- 不渲染最终Word、不检查分页截图、不提供视觉免责声明；仍保留题图真实读取和首次探针。

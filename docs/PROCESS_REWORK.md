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
- **M3初版**：schema v2提交少量建议，程序生成全文；长度封套保护正文中的报告标题/装饰行；快照CAS和材料锁，异常回滚报告/数据/清单，登记为最后提交标志。不能无损承载的原文字面含`|`/标记括号时明确拒绝。源文信封提取与可逆特殊字符编码仍需补齐，不称全部M3验收完成。
- **M4初版**：assumptions/symbols/images/calculations首轮证据、必需自查项；真实calc call_id与单元源码/轮次/结果关联；父复核绑定输入/建议/自查/报告hash。最新退回撤销旧接受。技术报告仍可汇总通读，但unreviewed时complete=false、Word拒绝。
- **M5部分**：恢复类别累计、失败指纹、阶段事件、显式取消来源API。调度尚依赖宿主/父代理主动登记；插件中断来源不得猜为用户。预算耗尽留痕，不能换agent刷新额度。
- **M6部分**：Word与报告解析共享v2正文边界；旧parse/repair拒绝覆写v2数据。诊断文件生成与正式complete分离。双skill和bundle schema有漂移测试。

## 安全复核

发现并修复：父复核CLI参数接线错误；旧parse会丢proposal并绕复核；同hash退回未撤销接受；Word按首次报告标题切段吞标记；移除fs会丢read_image。通用兼容修复由独立工作树处理，不要求合并实验审查功能才能使用main。

## 隔离回放

在仓库工作区中新建第4/5讲完整材料名加“流程改造回放-20261009”，写入前核对两目录不存在。旧EasyUse材料只读源文件副本作输入，不读旧报告、不修改原稿/旧记录。第4讲拆11单元、图片10；第5讲拆12单元、图片14，缺失均0。

本会话首次真实视觉探针通过，实际read_image观察与参考一致。回放在开发会话中使用CLI/core退路，不是新校对preset安装验收。关键单元由路径/ID派干净子agent；主agent不逐单元读取源文，最终只通读汇总报告。

关键7单元回放结果：5个技术提交通过（不是最终父审完成），2个失败（第4讲练9calc证据绑定不匹配；第5讲练1图片证据结构/调用格式失败），完整错误和摘要保留在契约失败文件。其余16单元未开始，整份complete=false。父代理已通读两份汇总报告并将第4讲练5的g/悬点、第4讲练8传播方向语义按hash定向退回（每单元已消费1轮复核预算）；不能为凑Word或既有标记数刷新失败预算、伪造全部通过。3份证据超长行在报告展示修复预算内分行登记新revision；第5讲练3的该类额度已满，未继续变更，其余原报告保留。

## 未完成与交付限制

- 本轮尚不满足M0—M6全部验收：特殊字符无损编码、完整source body契约、完整强类型父工具、错误分类与自动心跳/取消闭环、实际安装方式、新会话父子catalog均需继续。
- 整份回放必须所有必需单元技术通过、父复核当前版本且Word结构/图片/批注记账通过才可交付；有未开始、失败或unreviewed时只交诊断，不生成冒充完整的Word。
- 不渲染最终Word、不检查分页截图、不提供视觉免责声明；仍保留题图真实读取和首次探针。

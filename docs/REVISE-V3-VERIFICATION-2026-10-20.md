# 无状态 v3 生产入口验证（2026-10-20）

状态：**生产 v3 实现、完整 CI 与同一份 12 题 CLI/core 真实验收已完成**。双插件 schema/透传与 skill 已接通并通过自动验证；本会话未暴露原生 jiaodui 工具，不将 CLI/core 或插件模拟测试当作原生插件宿主验收。

## 实现与数据边界

新增 jiaodui/proposal_v3.py，完整/增量 v3 复用 P0 锚点与证据编译 v2；unit-submit 在原材料锁与 snapshot CAS 内分派。同轮同输入、当前登记与 verify 合格的基础提交才可继承；当前分层输入重编译须与已提交 v2 一致。unit-snapshot --with-proposal 返回精简修订列表；unit-schema --schema-version 3 导出正常 schema，默认 2 保留兼容。

两学科正常 jiaodui_unit_submit 接 v3；显式 jiaodui_unit_submit_v2 保留旧 bind-current v2。双包 schema 从 core 导出，壳只透传。两学科 skill/手册/契约/失败说明及副本同步，真实读图、calc、verify、自查与父复核保留。

报告、数据顶层和 proposal 仍为 schema v2；现有 _校对数据.json 增可选 submission_v3，只保存当前有效分层输入，不保存草稿、撤回历史或工作日志，不新增布局、不迁移历史。与 v2 产物同事务写入；preview 不写盘，v2 重提清掉旧分层字段。

v2 局部图片观察折叠不可逆，不能从渲染文本可靠恢复归属。新 v3 撤回局部观察但保留单元图片覆盖；历史 v2 图片按单元证据继承，不保证逆撤回历史局部语义。继承假设/计算单引用随替换更新归属，多引用转共享。

## 自动验证

新增代表性契约测试按红绿开发。首次完整 CI 在父复核处停滞：新快照锁与原父复核锁嵌套。停止该进程，父复核改读已持锁的内部 snapshot；父复核、Word 和 v3 相关回归共 128 项通过（另 4 个 subtests）。随后重跑 `.venv/bin/python -m pytest -o addopts='' -q -rs`，退出 0：**1473 passed，4 subtests passed，38.89s**，无跳过或失败。

## 真实材料与宿主路径

源文件：/Users/chouchou/Downloads/测试用例12题.docx，SHA-256=bc9f8ecd9ec5fd9fb99d1003a961af8a6dbf4e3ecc382966e9a9defcb7b84b60，与旧 P0 材料相同。沿用高中物理/讲义类型，convert → rule split → execution-policy；12 单元、12 图，拆分预检无空/超长单元，图片资源初检通过。

隔离材料：校对/测试用例12题-v3验收-20261020/。task_id=677b18ad928048649d15cbda0b4ac609，run_id=fc8d27bffb8f4555a748b5a36cc8f9b9。干净子代理一次一单元、最多 6 并行；只给路径与身份、不提供旧答案，实际 read_image、按需 calc、v3 preview/提交及 verify。主侧收单行摘要，收尾通读整卷报告并按当前 snapshot 父复核。

当前会话无原生 jiaodui 工具，实际经仓库独立环境 CLI/core 退路执行；不改 DSH profile，不宣称新原生插件目录已在宿主验收。

### 已出现诊断

- 单元 1/2/3/4/6 在正式提交后追加 verified 事件，core 返回 attempt-terminated/awaiting_parent_review；提交和独立 verify 已通过，未重试事件。
- 单元 2 预览引用 call_id …04e9，实际登记 …04d9；查清是转抄错误，不是 core 丢账。已按预算恢复重算，保留原记录。
- 单元 5 calc-schema 误带 subject、一次表达式转抄错误，以及单元 6 两次快照参数错误均按预算留痕，最终提交成功。单元 4 曾探测不存在的 unit-calc 命令，实际计算用正确 calc。单元 7/8 也各有一次 calc-schema 误带 subject，按 usage 消费一次 call_correction 后纠正。
- 单元 7 初次原文锚点未包含完整公式，preview 返回结构切断诊断；改用完整公式后预览与正式提交通过，不消费恢复预算。

### 父复核发现与增量返修

主侧已通读整卷审阅稿全部 1186 行，并实际打开单元 7/8/12 白底题图。初次 v3 技术提交 12/12 通过，共 4 条修订；这不是最终质量结论。父侧接受其余 9 个当前单元，按当前 snapshot 退回 5/8/12：

- 单元 5：首轮漏检 sinα 中间式错误，要求实算确认并补最小修订。
- 单元 8：原句“三者近似圆周运动”应改，但新增“丙轨迹向远离圆心方向弯曲”无法由图支持且混淆径向偏离与曲率，要求撤旧 ID、新增准确修订。
- 单元 12：保留机械能分母多因子 2 的真错误；仅统一势能记号 P/p 的第二条无实质影响，按不强改润色原则撤回。该条曾触发 verify manual_review，未直接批准。

三单元均用新 attempt 和记账 targeted_review，真实使用 base_proposal_revision / withdrawn / corrections 增量入口，每次重提 self_check、不修改原文。单元 5 新增两条绑定计算，确认 √3/√21≠√21/7、√3/√7=√21/7，以完整公式新增修订；单元 12 撤回记号项后 manual_review 清空。单元 8 的改写已正确，父侧另要求仅精简 reason，删除首轮被撤回判断的历史说明，作为第 2/2 次定向复核。单元 8 最终 revision=3，当前 reason 已只解释源文问题；单元 5/12 均为 revision=2。三单元增量返修均再次 preview/正式提交/verify，并经当前 snapshot 父复核接受。

原始 DOCX 与本轮 source 副本 SHA-256 已复核一致。
## 最终验收结果

- 12/12 单元均保有 schema v3 当前分层提案，生成的 proposal 与报告为 v2；当前 verify 全部通过，errors / warnings / manual_review 均为空。
- 12/12 当前输入摘要与拆分记录相同，报告标记正文均可逐字节还原单元源文；交付登记与父复核均为当前版本，run.status=completed。
- 最终 4 处修订：单元 5 三角中间式分母、单元 7 速度平方上下标、单元 8 运动类型与向心力表述、单元 12 椭圆轨道机械能因子。8 个单元无修订。
- 所有单元各由子代理真实 read_image 1 张；主侧另实读 7/8/12 题图。实际 calc 记账 46 次，最终使用 42 条计算证据；成功计算的 equality=false 作为原式不等的反证，未把失败调用充作成功证据。
- build-report：complete=true、deliverable=true、failed=[]、unreviewed=[]、warnings=[]。
- build-docx：ok=true；4 标记=4 锚点+0 公式兜底，缺失/过量/图片缺失/批注公式降级均为 0，8 条无问题标题批注，anchor_structure_ok=true。
- python-docx 独立重开成功，正文 12 张内嵌图片；实际 OOXML 批注 12 条（4 修订+8 无问题标题），起点/终点/引用 ID 集合与计数完全一致，ZIP 无重复条目；4 条最终修改原因均存在，已撤回的历史说明未进入批注。

| 单元 | 当前 revision | 有效修订 | 计算证据 |
| --- | --- | --- | --- |
| 1 | 1 | 0 | 0 |
| 2 | 1 | 0 | 4 |
| 3 | 1 | 0 | 4 |
| 4 | 1 | 0 | 4 |
| 5 | 2 | 1 | 7 |
| 6 | 1 | 0 | 3 |
| 7 | 1 | 1 | 2 |
| 8 | 3 | 1 | 2 |
| 9 | 1 | 0 | 2 |
| 10 | 1 | 0 | 6 |
| 11 | 1 | 0 | 5 |
| 12 | 2 | 1 | 3 |

最终审计脚本最初误用 VerifyResult.manual_review 属性与相对 root，均在读取/断言阶段失败；改用 manual 和绝对 root 后通过，未修改生产代码或产物。首次完整测试锁等待及所有真实恢复诊断均保留记录，没有跳过既有测试或删数据。

## 产物与摘要

- [整卷报告](<../校对/测试用例12题-v3验收-20261020/校对报告/测试用例12题-v3验收-20261020_整卷报告.md>)：SHA-256 `0edb12f16f4098ec9780ea5ad9f12d71e69e38f9274b214c2e37f31639b1234b`。
- [Word 批注版](<../校对/测试用例12题-v3验收-20261020/校对Word/测试用例12题-v3验收-20261020_校对批注版.docx>)：SHA-256 `e0d4892fd58962478ec56b61b9cded357d6a192333ff078b24b817787d8e1335`。
- 原始 DOCX 与本轮 source 副本均仍为 `bc9f8ecd9ec5fd9fb99d1003a961af8a6dbf4e3ecc382966e9a9defcb7b84b60`，原件未改。

本次是一次功能与实际交付验收，不证明总体准确率或性能提升。未执行 A/B 实验、token 统计、DSH profile 改造或强杀等已取消的工作。

## 后续 P1 修复：插件学科枚举

后续审查发现：共用工具模块的 task_prepare.subject 及全部 calc.subject 仍只允许高中物理，之前的透传测试没有检查注册后 subject.enum。两个插件已同步使用物理/化学两门已落地学科的枚举；插件不设隐含默认学科，CLI 的拆分学科必填规则继续生效。

新增真实 Node 加载插件的回归：先确认两包均因缺少化学枚举失败，再修复转绿；检查父/子工具集所有 calc 的学科枚举，正向覆盖化学拆分、evaluate、chemistry_balance、stoichiometry 及实际 CLI argv 的学科透传。相关测试（插件行为、打包契约、calc CLI）**56 passed**，两包工具模块逐字节一致且 Node 语法、diff 空白检查通过。本次未重跑完整 CI；上文 1473 项是该修复前的历史结果。

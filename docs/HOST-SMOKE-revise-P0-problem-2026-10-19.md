# revise P0 有错真实单元父子代理盲校

日期：2026-10-19。分支：`feat/revise-tool-upgrade`。状态：**真实有错单元盲校提交已复核，非零修订 CLI/core → Word 批注链通过；未验收原生插件工具面**。

## 目的与成功标准

用户指出上一轮“无问题”路径不足以验证校对修改工具，本次专门覆盖非零修订的 unit-locate → preview → bind-current submit → 父复核 → Word 批注锚点。不能通过人为造错、照抄旧报告或把合理选项/近似/润色当作真实错误达标。若首次盲校漏检，必须如实记录，而非事后提示后冒充首轮检出。

仍采用真实 DSH 子代理、真实 read_image 与本分支 CLI 控制台脚本；不测试原生插件注册或受限 preset 工具目录。源文和图片只在隔离材料中参与程序生成报告，原材料既有交付不变。

## 独立筛选

- 第一轮第6讲候选筛选未确认数值或物理逻辑错误；另有5处SI单位字形问题，未作为本次主样本。
- 第5讲旧报告若干“加速度大小”“速度/速率”标记具有解释空间，不直接当作真错误。
- 选定第4讲原单元9：只读筛选代理 `705fe216-e5d7-41af-9013-1bad2ab0df6c` 已核对原文、既有报告和真实题图，独立确认1处解析传播方向陈述错误，不是设计错误选项。具体位置、修改文本和判据仅保留在筛选代理上下文，未传给盲校代理。
- 原单元15行、题图1张（甲乙两幅子图合图）；筛选过程不向原材料记账、不改文件。

## 隔离现场

原单元：[第4讲原单元9](<../校对/第 4 讲【选修专项】简谐运动与机械波流程改造回放-20261009/units/第 4 讲【选修专项】简谐运动与机械波流程改造回放-20261009/单元9/单元9.md>)。

测试材料：`校对/revise-P0-有错单元宿主测试-20261019-1506/`；通过 convert→split(none/no-clean)→execution-policy 创建，单元重新编号为单元1，源文字节与原单元9完全一致；不复制历史报告/数据。

```json
{
  "task_id": "4830588b32944cf59ab4f401a5e4d37d",
  "unit_id": "2fb24192dd8d46eeb3e4c40eda6884f6",
  "run_id": "487a7864b6044739bcf85a0b215842c7",
  "attempt_id": "host-problem-20261019-1506",
  "initial_snapshot_sha256": "defa12f31fe8b4acbb209eed0124e9a3f1a759cb6894e5da2f5623a709e113a5",
  "source_sha256": "1d1e0069e38f80303835a2d40604b3ed91df40da0a51724bd6e86d2cf1328862",
  "original_image_sha256": "eaaa373d07c8b674e44ff648dfa0585939c37a6eaf8785f210fea37463030c8e",
  "whitebg_image_sha256": "af4fe59ef46779e3b78857b97ae77060cfe0b4cfff0dd3a4d48adbc1875443e1",
  "original_manifest_sha256": "282fc2e95ccc51dd075633c512d12794ec929d129cac5d54033c8918300c2912",
  "original_report_sha256": "6be53cc27723ff8e7fecada71494ef1ed3b01bee65be97543dd4e68c9e6bee9b",
  "original_data_sha256": "5bc0351c4bd55916570acacd67445ad110d0714634d4992fd17f732bb7cce712"
}
```

## 盲校派发

干净校对子代理 `55edeac4-c1aa-44be-8f07-0692eabdf5f6` 仅收到隔离单元路径、身份与通用物理规范路径，不收到原单元9历史答案或具体错误提示；不得查看其他材料，不能硬凑问题。每条真实修订必须定位原文，提供证据与自查；preview 后以 --bind-current 提交，省略六绑定字段；父侧接受由主代理执行。

已要求真实读图、带身份calc、逐字定位、自查与完整错误/恢复留痕；单元15行，但不因测试而省略题目核验。原会话未收尾，后续按落盘结果续接验收，见下文。

首次实例在读源文前被宿主报告失败。父侧核对磁盘为prepared、0 calc、0登记、报告/数据均不存在；按一次 technical_redispatch 预算记录并终止旧attempt，新attempt为 `host-problem-20261019-1506-redispatch1`。随后原实例补报真实原因为两次run_code封套参数拒绝（空justification及错误权限模式），不是CLI或core崩溃；技术预算的归类依据是当时宿主失败通知，保留原记账并披露后续诊断，不追改历史。重派实例为 `35aac899-61e6-433b-b656-85196df73b06`，提示补充了当前宿主封套字段要求，未传入任何错误位置或答案。此失败计入宿主派发偏差，不算真实校对工具调用已失败或已完成。

## 续接与父侧验收

原会话上下文过长后，在新会话续接。磁盘显示重派实例已于 2026-10-19 15:17:32（Asia/Shanghai）登记 v2 提案，phase=awaiting_parent_review，并非仍在运行。续接没有再派一轮校对来替换该结果；本次新增子代理只做只读审计。当前会话未取得旧子代理逐条工具回放，不能仅凭磁盘证明 preview 返回或输入提案确实省略了六绑定字段；这些与已验证的 core 最终绑定正确分开陈述。

### 检出的问题

仅1处，一般问题：解析中“振动从$a$传播到$b$” → “振动从$b$传播到$a$”。原单元第9行，严格定位区间 [419,431)，location_id 中源文摘要与当前源文一致。

父侧通读完整173行汇总报告并真实打开白底题图：图甲 b 点空间斜率为正，图乙 b 点 t=0 向上，故波沿 −x 传播；xb=6 m、xa=2 m，应由 b 向 a。λ=8 m、T=8 s、v=1 m/s；半周期路程1 m，a初速沿−y，t=2 s 时a在负最大位移处且速度为0。修订位于解析的真实矛盾，不修改正常错误选项，答案D及其余数值结论不变。该检出与独立筛选记录的问题类别一致；单一样本不证明统计查全率或总体无误报。

| 阶段 | 续接实际结果 |
| --- | --- |
| 既有提交 | schema v2、revision=1、1条修订、12条带call_id计算证据；报告/数据均已登记 |
| 父侧 verify-report | exit 0，1标记，0错误、0警告，1处图片引用通过 |
| 父复核前 | status：本轮未完成=1；build-report：complete=false、deliverable=false、unreviewed=1 |
| 当前快照父复核 | 2026-10-19 15:35:31，accepted、current=true，reviewer_id=parent-host-problem-resume-20261019 |
| 父复核后 | complete=true、deliverable=true、unreviewed=[]；已完成=1、本轮未完成=0 |
| Word 生成 | exit 0、ok=true；1标记=1锚点+0公式兜底，缺失0、过量0、图片缺失0、批注公式兜底0 |
| Word 独立核验 | python-docx重新打开，正文内嵌题图1；实际comments.xml批注1，rangeStart/rangeEnd/reference各1且ID一致，无重复ZIP条目 |
| 实际批注内容 | 锚点逐字为“振动从a传播到b”；建议的a/b以公式图内嵌，按关系顺序提取并白底读图确认为b、a；修改原因完整 |
| 旧快照负测 | 用初始快照尝试父复核，exit 6、review-stale；清单、报告、数据SHA及mtime完全不变 |

批注公式图片核对：[原始第一张](<host-smoke-problem-20261019-assets/rIdPic1.png>)、[原始第二张](<host-smoke-problem-20261019-assets/rIdPic2.png>)、[白底顺序图](<host-smoke-problem-20261019-assets/comment-formulas-whitebg.png>)。它们是从最终Word只读提取的验收附件，未修改Word。

### 独立只读产物审计

只读子代理 41231070-1a0a-4768-bc2d-aac0cf5e94d5 于 2026-10-19 15:40:19+08:00 完成稳定读取核对，未修改源文/产物/清单，未调用unit-review。审计初期与主侧接受动作并发，已在父侧完成写入后重新确认读前读后稳定。

- 原件保护：第4讲原材料的源文、原图、白底图、清单、既有报告、既有数据六个基线SHA全部匹配本文“隔离现场”，无原件改动。
- 源文保护：隔离单元及隔离source与原单元逐字节相等（15行、915字符、1529 UTF-8字节）。通过已读核心纯解析接口去除1条标记，932字符标记正文还原为915字符源文，包含末尾换行，UTF-8字节及SHA完全一致。
- 六绑定、revision=1、input_digest与当前清单和实物一致。唯一register-unit/action及unit_record的run、inputs、report/data摘要全部对应现物；父侧accepted所绑report/proposal/self_check/inputs和重算snapshot一致。
- 清单12条calc_calls、12个唯一call_id，与k1—k12集合严格一一对应，身份、源文、input_digest、expression、success及result均匹配；含3次differentiate、equality及2次dimensional的实际参数。未发现缺失、重复或失败冒充成功。
- 恢复仅technical_redispatch一次，预算1/1，旧attempt cancelled、新attempt终态parent_reviewed，run completed；恢复事件、fingerprint与计数一致。沿用原host-crash分类及本文故障诊断披露，不修改历史。
- 最终稳定清单SHA256：bb9487a17ea6582df52ee219b7af133a9e1b823126bf9efc9947fbc39810eca6。未发现产物一致性错误。

证明边界：磁盘核对不能独立证明旧会话真实宿主工具调用、read_image调用、盲校上下文隔离或未泄题；calc_calls没有agent/attempt字段，unit_events的agent_id=null，不能仅从磁盘严格归属具体子代理实例。unit-locate/preview/bind-current的命令执行也不能由最终哈希倒推。本次明确验证的是既有盲校提交的完整性与续接后的父复核/Word交付；旧宿主过程依赖原会话记录，当前审计不补造证据。

### 最终摘要

- 父复核 snapshot_sha256：ee95f92056b086e55fdbcb0c6a0d98a65a159f0740235a4710f88f00e8375937。
- report_sha256：9b49697ab5aa5ae33a8eb0253b613bf1bde908f989c2da4e3515ffb2e5e62aae。
- data_sha256：83e27c34fee673b41509224d83962b7244e309e515928e9b23c1a7cae8e8f2e8。
- proposal_sha256：a14711faa29de1c7ca40b8d971756ee7400def0544553b080b00b60476594cb4。

### 续接操作偏差与边界

1. 父侧第一次unit-snapshot缺少--work-root，exit 6、workspace-required；verify此前已成功，后续&&链未继续。补齐工作区后成功。不归因于旧子代理，不消费恢复预算。
2. 验收脚本初次只提取批注文本，未包含公式图片字符，断言失败；查看OOXML关系、实际提取读图后确认内容正确。不是产品批注缺失。
3. 旧快照父复核负测脚本最初误期待提交入口的snapshot-stale；实际为复核专用review-stale。修正测试预期后拒绝及不写盘均通过，生产代码未改。
4. 当前会话另有run_code封套/脚本解析失败（空justification、嵌入脚本字符串解析），均未执行对应业务操作。封套拒绝不是CLI/core失败。
5. 续接排查时主侧误把隔离source及单元源文直接读入上下文，违反“父侧不逐单元读源文”的读取边界；此事发生于旧子代理提交之后，没有将具体答案传给校对子代理，但应作为父编排偏差保留，不冒充严格受限preset验收。
6. 没有修改生产代码或重跑全量pytest；本轮新增的是实物验收证据，不更改此前1457项全量验证口径。未推进P0.5，未选择A/B，也不替代ADR采纳、冻结样本人工核对及原生插件验收。

产物：[完整汇总报告](<../校对/revise-P0-有错单元宿主测试-20261019-1506/校对报告/revise-P0-有错单元宿主测试-20261019-1506_整卷报告.md>)、[Word批注版](<../校对/revise-P0-有错单元宿主测试-20261019-1506/校对Word/revise-P0-有错单元宿主测试-20261019-1506_校对批注版.docx>)。

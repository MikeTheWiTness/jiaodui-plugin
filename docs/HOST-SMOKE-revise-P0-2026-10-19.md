# revise P0 真实父子代理 CLI 冒烟

日期：2026-10-19。分支：`feat/revise-tool-upgrade`。状态：**真实宿主父子代理 CLI/core 链路通过；未切换 preset，未验收原生插件工具面**。

## 验证范围

用户要求在当前工作区选择真实单元，由主代理模拟父侧派发一次子代理校对。本次使用当前 DSH 宿主的真实 `subagent` / `read_image`，确定性操作通过本分支 `.venv/bin/jiaodui` 控制台脚本执行。未切换 preset、未修改 profile、未启动替代服务。

这可以验证“真实宿主派发→真实读图→真实 CLI 计算→core 绑定提交→父复核”的链路，但**不等于** `jiaodui_*` 原生插件工具、preset 子代理受限工具目录或宿主工作区自动注入验收。本次子代理仍具备当前编码会话的通用工具，CLI 使用是显式测试退路，不据此证明无 shell / 无 write 的权限隔离。

## 现场与隔离

- 真实输入：[第 6 讲讲义单元1](../校对/第%206%20讲校对测试-流程测试/units/第%206%20讲校对测试-流程测试/单元1/单元1.md)，材料记录标明高中物理、lecture。
- 测试材料：`校对/revise-P0-真实单元宿主测试-20261019-1445/`，一个单元，从原单元源文及图片制备，不复制既有报告或校对数据。
- 按 convert→split（none/no-clean，保持源文字节）→execution-policy(automatic/user) 准备；子代理只收路径与身份，不收源文全文或历史答案；父侧不读取逐单元源文。
- `task_id`: `a0fcf16838e04f12a99b6c6645d334fa`
- `unit_id`: `bab795a3305c47b9be4b8b3d6b290142`
- `run_id`: `d119a0261f494221bd9f38064e1a0771`
- `attempt_id`: `host-smoke-20261019-1445`
- 提交前 `snapshot_sha256`: `b3f66eb35e672a58873088ae0f63759e2396dc2c8918f3dfdc23699382fa24e6`
- 源文 SHA-256：`e91148c8437cb83afe582bbb6b9513b0ba596571dab10e897227f24e773079da`
- 原图 SHA-256：`7bce31a7ceb5cc4a36148d133001dddef1ade7b2cd22ce2aede233dc79459b84`
- 实际白底图 SHA-256：`a949a75518280bfe1503977e5dcf7b971e77ba8a10fe6f057bd5913377c394a6`
- 原材料清单 SHA-256：`8ad08c5e150fbe5d418c8e416013c70bd0334119bda072adcdcfaa4e6844e514`
- 原单元既有报告 SHA-256：`7ec21c2fe41ee8ab44ab216be8542b73c88e63cd3634a92145e27de729512932`；原单元无数据文件。

## 真实宿主视觉探针

干净子代理 `e7130e34-40ef-4098-ab1b-bcf4bb109f1f` 实际读取随包白底 PNG，未读取 SVG 或答案；返回红色苹果、棕色果梗、朝右上绿叶、底部横排三个蓝色圆点、无文字数字，与主侧探针验收一致。通过。该探针不替代真实题图读取。

环境：Python 3.12.13，pandoc 3.9.0.2，check-env 必需项通过；运行控制台脚本解析为仓库 `.venv-cli/bin/jiaodui`。

## 单元子代理

干净单元子代理：`0e7a4893-92b2-422f-a976-740f9fa515e8`。父侧先登记 prepared，子侧按物理规范执行 snapshot/read/实际题图读取/calc/locate/self_check；提交使用 `unit-submit --bind-current`，提案省略六绑定字段，仍携带 expected snapshot；报告与数据只由 core 写入。子代理不得调用父侧 unit-review。

### 执行结果

| 阶段 | 实际结果 |
| --- | --- |
| 真实题图 | 子代理亲自读取清单白底图；父侧通读汇总后亦独立打开复核 |
| 学科核验 | 16 次带 task/unit/run 身份的 calc 登记，均成功；数值、传播方向及量纲证据进入报告 |
| 子侧结论 | 无问题，0 条修订；没有为了测试强行制造错误 |
| bind-current | 子代理省略六绑定字段，真实 CLI 提交 exit 0；core 写出的 task/unit/run/hash/revision 均独立复核正确，revision=1 |
| verify-report | 子侧与父侧各自执行，均 exit 0，0 errors / 0 warnings；一处图片引用通过 |
| 父复核前 | build-report complete=false、unreviewed=1，status 本轮未完成=1 |
| 父侧复核 | 通读全部 305 行汇总与证据、读取实际题图后，对当前 snapshot 接受；unit-review exit 0、current=true |
| 父复核后 | build-report complete=true、unreviewed=[]；status 已完成=1，本轮未完成=0；轮次 completed |
| 旧 snapshot 负测 | 父侧以提交前 hash 尝试提交，exit 6、snapshot-stale；清单/报告/数据字节不变 |
| Word 交付 | build-docx exit 0、ok=true；0 错误标记=0 错误锚点+0 公式兜底；无问题标题批注1，缺失0，图片缺失0 |
| Word 独立复核 | python-docx 重新打开成功，内嵌图1；实际 comments.xml 有1条无问题批注，起止锚点与引用各1 |
| 原件保护 | 原材料清单、既有报告、源文、原图、白底图 SHA 均与基线一致，原单元仍无数据文件 |

父侧核对：图中 A 横坐标2.0 m上方是波峰，B=3.5 m是右侧过零波前，C=5.5 m；子侧证据计算 v=0.5 m/s、λ=2 m、T=4 s，C于绝对11 s开始向下振动，20 s已振9 s，为第三次波谷。父侧未发现需要退回的问题。此为一个真实单元的流程冒烟，不宣称统计质量提升或独立模型一致性。

子侧 CLI 错误0、恢复0、重试0。子代理主动披露一条审计偏差：额外 prepared 心跳的 agent_id 误填父代理ID，其余 read/images/calculated/proposed/self_checked 使用指定 attempt，未伪造程序交付阶段。该元数据偏差保留在清单和本记录，不追改历史，不把它记成CLI执行失败。父侧另行发起的旧快照拒绝是预期负测，不计入子侧错误数。

提交结果：

```json
{
  "summary": "无问题",
  "marker_count": 0,
  "registered": true,
  "verified": true,
  "report_sha256": "4c725083d6e65e8fc919c5e51dfb68333fd65854eddda6d0fa6d80cd7ceaacd7",
  "data_sha256": "34684eb27421c192538c5631836a9fe1f90fe76c457a6c757f35931aef9108e9",
  "proposal_sha256": "bda5159fe2ee4ba25fa5151233230684ee5aee04e2afc436e177c1e52790ee05",
  "submitted_snapshot_sha256": "4bde4de365e2153587b1fa3d9e1db4a38fe5e8c9dbed481e0d16a1ec313f5edf",
  "parent_review": "accepted",
  "reviewer_id": "parent-host-smoke-20261019",
  "run_status": "completed"
}
```

产物：[完整汇总报告](<../校对/revise-P0-真实单元宿主测试-20261019-1445/校对报告/revise-P0-真实单元宿主测试-20261019-1445_整卷报告.md>)、[Word批注版](<../校对/revise-P0-真实单元宿主测试-20261019-1445/校对Word/revise-P0-真实单元宿主测试-20261019-1445_校对批注版.docx>)。

本次是“无问题”合格链和过期版本拒绝，不证明非零修订的 Word 锚点路径，也没有执行 P0.5 的36次对照或S8/S9干预。

## preset 是否必要

- 执行上述 CLI/core 真实父子代理测试：不必切换 preset。
- 验证原生 `jiaodui_*` 参数/schema/工作区注入和受限子工具目录：必须在实际加载这些工具与配置的会话执行。本仓 patch 的父 preset 是“校对”，其 tool-subagent 指向 `jiaodui-unit` 子 preset；用户应选择父 preset，不手动选择单元子 preset。
- 本会话的 subagent 工具参数没有 preset 选择字段，不能靠在派发参数中临时指定 `jiaodui-unit` 改变真实工具权限。相关配置见 [插件 patch](../packages/dsh-jiaodui/cordis.patch.yml)。

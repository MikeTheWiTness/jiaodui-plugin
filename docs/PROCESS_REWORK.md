# 校对流程改造执行记录

依据 EasyUse《校对流程改造执行计划》；本记录区分仓内实现与 DSH 真机会话验收。用户指定计划 §1.1 第7项（子代理建议自查与父代理复核版本绑定）单独分支实现，不属于 main 的完成范围。

## M0 现状核对

- 仓库初始位于 `main`，HEAD `abfea6c`，工作树干净。
- `.venv` 指向仓库内 `.venv-cli`；Python 3.12.13，`jiaodui` 为 editable install，pandoc 3.9.0.2，`check-env` 必需依赖通过。
- 插件开发/安装约定来自 bundle README：DSH 官方 `install_bundle`；不能据此断言当前 profile 实际是软链或复制安装。本轮未改 profile。
- `skills/jiaodui` 与 bundle 副本由测试逐文件同步；旧 preset 含 shell、web、goal、plan、fork，原生工具只有 `args[]` 透传。
- 改造前全量基线：941 passed、4 subtests passed。

## 主分支实现

- **M1**：材料当前轮次可记录 `automatic` / `interactive` 策略、来源和固定预算；相同选择幂等，不同选择需新轮次。preset移除 shell，关闭 web / goal / plan / fork；入口skill低于8192字符。默认skill排他与子代理细粒度权限没有仓内宿主配置证据，仍待真机验收。
- **M2**：新材料持久化 task/unit ID；位置ID绑定源文SHA-256及 Unicode 码点区间，查询返回重复命中、match_index、行列和公式/加粗安全范围。calc JSON Schema从 `OPERATIONS` 元数据导出并由bundle测试核对。
- **M3**：schema v2建议只提交定位修改和证据；核心从不可变原文生成全文报告，版本化正文边界保护原文中的报告标题/装饰样式行。标记协议无法无损表示的原文字面明确拒绝。单元提交通过材料锁和snapshot CAS，报告/数据/登记失败回滚；登记仍复用现有verify/parse状态契约。
- **M5**：恢复预算按 run、unit、类别累计，保留失败指纹；phase/attempt/agent和取消发起者/原因持久化，取消来源不从错误文本推断。预算/阶段API已实现，但主机调度生命周期与进程取消后的全批次停止须宿主侧验证。
- **M6**：build-report结果区分文件 `ok` 与正式 `complete`；skill、README、schema和错误契约同步。bundle尚未通过本轮安装/重启/新会话宿主验收。

## 验证和限制

改造后仅运行不读取既有业务材料的定向测试，不重跑包含历史/真实材料样本的全量套件。当前已验证项和最终命令记录见本次交接；测试通过不代表DSH会话中的读图、skill目录排他、父子能力隔离或取消后不再写盘。

## 尚未完成

- M4（计划§1.1第7项）：另建分支加入建议自查、父代理review及输入/建议/报告hash失效链。
- DSH真机安装：按README使用官方安装方式替换已安装bundle，重启后新会话核验结构化tool schema、skill catalog、实际图片读取/单元提交和取消。
- 隔离回放：只在全新材料名下导入计划中的源文件；原交付、报告和历史记录不得读取后覆盖或修改。没有可用的真实宿主读图/派发通道时，只做确定性准备和提交冒烟，不把它报告为内容校对完成。

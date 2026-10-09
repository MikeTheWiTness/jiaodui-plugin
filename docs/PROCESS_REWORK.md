# 主线保留范围

`main` 保留旧 Markdown 报告主链：源文经转换/拆分后，由宿主完成校对，旧 `_校对报告.md` 仍按既有 verify/parse/build-report 规则读取；`build-report` 另报 `complete`，不把“诊断文件写出成功”视作整卷交付。当前兼容层增加 manifest v1 显式执行策略、六类固定预算、按单元 spent 与 attempt/fingerprint 事件；未确认策略不可执行恢复/校对尝试，不引入 task/unit ID、source-index 或 v2 schema，也没有新的结构化提交入口。

M2 定位建议与 M3 结构化提交/依赖审查是单独实验，留在 `feature/structured-report-pipeline`（起点提交 `4c82e24` 及其后续工作），不属于本 main。新计划的 M5 是恢复预算与调度可靠性；`IMPLEMENTATION.md` 及 subject-matrix 中 M0/M1/M5 的名称属于旧阶段计划，不能据此宣称新计划阶段已完成。

## Preset 边界

preset 保留宿主真实 `read_image`、旧报告 `write/edit` 和 `jiaodui` CLI；关闭 web、goal、plan 与 fork，限制一层 spawn，skill 只从组合包 custom 目录发现。随包子代理工具过滤名单为 `skill/read/read_image/write/edit/jiaodui`，这是当前宿主工具目录配置，不声称实现了严格子权限。依据 `.worktrees/host-inspection/tool-fs.js`：`read_image` 参数为 `file_path`，且由 filesystem 工具在 attachments 可用时注册；`skill-filesystem.js` 的 `includeDefaultRoots` 默认 true，故本 preset 显式关闭默认根；`tool-subagent.js` 支持 `toolFilter` 与 `maxDepth`，但只将 filter 转交子代理请求，不能据此证明底层能力/权限边界已收紧。需待第7章实验和新会话验收后再评估严格子权限。

## 尚未完成

- Desktop profile 已安装组合包：`node_modules/dsh-jiaodui` 是指向根仓 `packages/dsh-jiaodui` 的软链。尚未验收重载后的新会话 tool catalog/profile preset、read_image 实际读图和旧报告 write 的端到端行为；配置源码与 Node 测试不等于宿主会话验收。
- 新计划 M5 的恢复预算/调度可靠性仍需宿主回放验证：批量窗口补位、取消在途任务和失败重派真实性未完成；本兼容核心只实现显式策略、按单元预算及事件记账，不声称完成真实 agent orchestration。插件将 `exec.signal` 中止中性地传播为 `AbortError`；来源可能是用户、父代理或宿主，须由上层明确调用 `unit-event` 持久化，插件不自动推断/记录来源。
- Word 仅保留结构性产物复核，不再要求最终视觉验收；首次视觉探针和逐张真实题图读取仍是门槛。

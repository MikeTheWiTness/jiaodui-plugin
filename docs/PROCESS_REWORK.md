# 主线保留范围

`main` 保留旧 Markdown 报告主链：源文经转换/拆分后，由宿主完成校对，旧 `_校对报告.md` 仍按既有 verify/parse/build-report 规则读取；`build-report` 另报 `complete`，不把“诊断文件写出成功”视作整卷交付。当前兼容层只增加 manifest v1 轮次执行策略、固定预算及单元阶段/恢复事件，不引入 task/unit ID、source-index 或 v2 schema，也没有新的结构化提交入口。

M2 定位建议与 M3 结构化提交/依赖审查是单独实验，留在 `feature/structured-report-pipeline`（起点提交 `4c82e24` 及其后续工作），不属于本 main。旧 `IMPLEMENTATION.md` 中 M0/M1 的历史名称只描述旧计划，不表示新计划相应阶段已完成。

## Preset 边界

preset 保留宿主真实 `read_image`、旧报告 `write/edit` 和 `jiaodui` CLI；关闭 web、goal、plan 与 fork，限制一层 spawn，skill 只从组合包 custom 目录发现。随包子代理工具过滤名单为 `skill/read/read_image/write/edit/jiaodui`，这是当前宿主工具目录配置，不声称实现了严格子权限。依据 `.worktrees/host-inspection/tool-fs.js`：`read_image` 参数为 `file_path`，且由 filesystem 工具在 attachments 可用时注册；`skill-filesystem.js` 的 `includeDefaultRoots` 默认 true，故本 preset 显式关闭默认根；`tool-subagent.js` 支持 `toolFilter` 与 `maxDepth`，但只将 filter 转交子代理请求，不能据此证明底层能力/权限边界已收紧。需待第 7 章实验后再评估严格子权限。

## 尚未完成

- 安装与 profile 实际加载/读图/写报告验证仍未完成；源码配置与宿主 Node 检查不等于安装验收。
- M5 多学科、批量编排窗口补位、取消在途任务及回放真实性仍待宿主实测；本兼容实现只记录 run 内事件和预算，不声称完成真实 agent orchestration。
- Word 仅保留结构性产物复核，不再要求最终视觉验收；首次视觉探针和逐张真实题图读取仍是门槛。

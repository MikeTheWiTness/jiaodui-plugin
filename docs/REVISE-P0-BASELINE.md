# revise P0 基线整理记录

本记录只说明P0及其必要前置的提交边界，不选择A/B、不合入实验原型。

## 来源与保护

- 起点main：c5af3545fa357179c972bed46d965be50b472fbd。
- 新整理分支：integration/revise-p0-baseline；原工作区仍在feat/revise-tool-upgrade，未checkout/reset/stash/清理原文件。
- 来源P0及既有前置：完整混合快照2bafba7bdc9960229b58e8e376d4f98fefa2b19e；原已暂存树92c42b8aa40254695e96505f5a814548badc9323仅用于识别既有前置，不整包作为P0。
- 排除：实验分支a03f098的全部experiment_*、experiments/、实验报告及证据；架构HTML/图片/构建脚本、历史review材料、warm-paper截图及跨平台计划文档不纳入。
- 操作偏差：审计调用git write-tree刷新原索引内部TREE缓存，原index摘要从2170db1da39f32ee906e17dd097061d9c9c13b8b14a5eba294ce896c77a7e881变为68064a816e9e45de96c6dd8babed8263731f24005242aed18a8bac20eff1d6fe。该缓存变化不改变暂存文件/模式/blob；后续以暂存条目、cached/unstaged差异、状态与322个非ignored文件摘要作保护基线，源仓Git只读命令使用GIT_OPTIONAL_LOCKS=0。不宣称索引字节从始至终完全未动。

## 提交一：必要前置（非P0）

第二科配置与独立bundle、既有发布脚本、UTF-8及文件提案CLI、跨平台持久材料锁、DSH独立子preset与unit工具集合。两包工具保持字节一致。此层仍保留旧JS快照读取和六字段绑定，尚无--bind-current、人工v1收口、交互诊断或锚点/证据分层纯函数。

原index的57文件层不是独立可运行提交：化学插件已依赖提案文件CLI、两包工具不同步、CI字段不匹配。先实际运行暴露这些接缝，再把必要依赖原子组合为可运行前置，避免保留坏提交。README移除未纳入的架构/review链接，不删除原仓文件。

额外接缝修复：共享插件subject枚举原来仅高中物理，阻碍化学工具使用；按先失败断言补为物理/化学，core仍按配置加载学科。后续P0移植保留该修复，不能被来源快照覆盖回退。

验证：main起点1273 passed、5 skipped、4 subtests passed；前置层默认/CI双口径均通过，1320 passed、5 skipped、4 subtests passed（CI 36.77秒）。Node两包语法、逐字节一致和git diff --check通过。Windows安装/宿主真实工具权限仍按原证据边界，不把macOS自动测试冒充其他平台实机验收。

## 后续P0层

仅移植P0-1～8及相应测试/验收证据；CLI、材料与两插件混合文件只带入剩余P0语义，保留已独立提交的前置。必须同时迁移v1假完成测试至v2提交+父复核，不能靠放宽T09或削弱断言通过。之后跑全量双口径、冻结检查和独立边界审查。

## 合入边界

本分支是可审查候选，尚未合并main或推送。P0.5原型仍留在exp/revise-ab；正式实验应在本候选经审查合入main后重新固定基线，不能直接把混合快照或实验提交合入生产。

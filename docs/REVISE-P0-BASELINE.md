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

## 提交二：revise P0

必要前置提交为c098568dce77c1780ae8cc913975cd505619fd57。在该提交上仅移植P0-1～8及相应测试/验收证据；94条白名单路径来源于原P0快照，保留前置的双科subject补漏，README仅同步正式接口及候选状态。CLI、材料、两包index的后续差异不再夹带跨平台锁/提案文件/宿主工具集改造。

- P0核心：anchor/evidence_layers、交互分类及恢复拒绝、manual-legacy覆盖/登记/下游保护、core锁内六字段绑定及schema。
- 双包同时切换D5，删除旧JS快照与绑定；前置层的UTF-8、文件提案和工具白名单保持不变。
- v1正式完成夹具与相关6组测试同时迁移为真实v2提交+当前父复核；未放宽T09，也不把人工兼容结果改称完成。
- 四份skill入口及references同步瘦身；12份冻结候选按外置用户确认保持原载荷，manifest SHA为cd000e065a958795e6deb468607cad1c46b10114157d7b56ebcdeeb1c5b2abd8。
- 历史P0无问题/有错CLI宿主记录及小型公式附件保留；引用的校对实物原本即为ignored工作区产物，不承诺全新checkout自带这些实物。正式P0计划的v0草案仅作本计划的来源附件，不含任何实验实现。

本候选默认/CI双口径均exit0：1452 passed、5 skipped、4 subtests passed（CI37.30秒）。两插件Node语法、冻结只读校验、两包工具及四份skill副本一致性通过；5项skip为旧仓语料4项和当前worktree缺少指定修复回归样本1项，不能计为通过。

独立只读审查未发现可复现边界风险：核心差异仅P0、锁/双科学科schema未回退、无dispatcher/finalize/experiment_*模块；README无被排除架构/review链接。该结论是静态审查，不冒充原生插件或Windows实机验收。

## 安装包独立验证

隔离构建wheel成功：jiaodui-0.1.0-py3-none-any.whl，SHA-256=a20645bed7eac43af7413e972e9cd53b57f85085ea8126b9912f74f7e96eb6e6。逐项比对打包的anchor/evidence_layers/unit_delivery/report_suggestions与本树字节一致，包含两科学科配置，不含experiment模块或实验目录。

使用已验证的独立Python3.12.13创建新的wheel-venv，正常安装wheel及运行依赖，未改原仓共享venv。再在仓库外空工作目录用新解释器-I执行：jiaodui.__file__确认位于该新环境site-packages；化学配置加载成功，bind schema比完整schema少6必填字段；真实生成单元、--bind-current等价core提交成功，1条标记，verify及当前快照父复核通过。

该新环境运行依赖为sympy1.14.0、python-docx1.2.0、Pillow13.0.0、lxml6.1.3、mpmath1.3.0、typing_extensions4.16.0；此为本次wheel可安装冒烟，不代表旧release约束文件已重新锁定。构建保留setuptools的license表弃用及data.subjects包发现警告；本次已核对wheel确含配置文件，不为清警告扩大修改pyproject范围。

## 原工作区最终保护核对

322个受保护非ignored文件的SHA全部一致；原HEAD/main/分支、stage entries、cached diff、unstaged diff与status摘要一致。阶段检查暂存条目SHA256=cdf6da6ce4899390217fce3288e8e24fbaaef742b5a14268b22e590513524aec，cached diff=619f09a4729fb6ab0535069112d1d2ce1cf72ff2c06cad6bae15477608b5c417；索引缓存刷新后未再变化。详见本轮外置保护检查输出，不把Git对象和worktree元数据新增称为“没有任何磁盘写入”。

## 操作诊断

- 从原staged树单独复验时，发现插件/CLI/CI三项真实接缝；没有把不通过的层提交，已与必要依赖组合后独立复验。
- 新worktree规范路径移动后旧pyc保存旧co_filename，首次原staged层测试另有一次inspect.getsource路径错误；已使用独立PYTHONPYCACHEPREFIX隔离缓存并复验，未改产品或放宽测试。
- 一次大文档读取返回不完整，移植后差异检查发现截断；已按60行分页读全、逐字节核对，恢复源快照，仅保留原宿主迁移注记。
- 首次wheel尝试--no-isolation因共享环境无setuptools失败；改用隔离构建，不在原共享venv安装包。随后隔离构建、独立环境安装与完整提交冒烟均成功，不把先前构建环境缺依赖记为产品测试失败。


## 合入边界

本分支是可审查候选，尚未合并main或推送。P0.5原型仍留在exp/revise-ab；正式实验应在本候选经审查合入main后重新固定基线，不能直接把混合快照或实验提交合入生产。

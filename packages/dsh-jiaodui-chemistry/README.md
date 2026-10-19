# dsh-jiaodui-chemistry

把 jiaodui 的**高中化学**校对流程接入 DSH profile 的**自包含组合包（bundle）**：
挂载随包的 `jiaodui-chemistry` skill、注册 jiaodui 原生工具、并声明一个「校对（高中化学）」agent preset。

本包是 `dsh-jiaodui`（高中物理）的**独立配套包**，不是它的子集或分支：

- **独立安装 / 启用 / 卸载**：两个 bundle 的行 id、preset id、skill 名、locale 标题都不同，可同时装进同一个 profile，互不覆盖。
- **共用同一份确定性内核**：Python CLI（含 `calc chemistry_balance` / `stoichiometry`）与 `tools/` 里的学科无关原生工具模块。工具模块与 `calc-schemas.json` / `proposal-schema.json` 在 两包内逐字节一致，由 `tests/test_dsh_plugin_package.py` 守着，防止隐性分叉。
- **学科差异只落在三处**：本包 `skills/jiaodui-chemistry/`（人读规范）、`jiaodui/data/subjects/高中化学.json`（机器读配置）、本包 patch 里的 preset persona。
- **CLI 永远是退路**：插件坏了，bash 里照样能跑 `jiaodui`。

## 结构

    packages/dsh-jiaodui-chemistry/
      package.json           dsh.bundle.patch = ./cordis.patch.yml；同时是可挂载的插件入口
      cordis.patch.yml       自带组合包：插入 preset-jiaodui-chemistry（含 skill 挂载 + 原生工具行）
      tools/index.js         宿主适配：注册校对及强类型工具（与物理包字节一致）
      tools/calc-schemas.json 由计算核心元数据导出的 operation schema
      tools/proposal-schema.json 结构化建议 schema v2
      skills/jiaodui-chemistry/ 随包 skill（仓库 skills/jiaodui-chemistry 的副本，测试守一致性）
        assets/             固定读图探针（SVG 源、透明 PNG、预合成白底 PNG）
      locale/{zh,en}.json    插件管理页的标题与描述
      host-probe/README.md   真机会话验收清单（含化学配平补测）
      icon.svg               插件卡片图标
      README.md

## 它做了什么

- **实验分支 preset「校对（高中化学）」（id `jiaodui-chemistry`，行 id `preset-jiaodui-chemistry`）**：保留结构化单元读取/定位/提交、真实 read_image、单层子 agent 和交付能力，关闭 shell 外的非必要能力（web、goal、plan、fork）。父侧保留 shell 与只读搜索；子侧由独立子 preset「校对（高中化学·单元子代理）」（id `jiaodui-chemistry-unit`）封闭，`toolset: unit` 只允许读取 / 计算 / 提交，不暴露 write/edit、argv 退路、取消或父复核。
  - `skill-filesystem` 的 `customSkillDirs` 指向本包 `skills/`，用于发现随包 `jiaodui-chemistry` skill。
  - `./tools/index.js` 注册原生工具 `jiaodui` 及全部 `jiaodui_*` 结构化工具；`toolset: unit` 时只注册单元读取/定位/快照/提交/恢复/心跳与全部 `calc_*`。
  - `tool-subagent` 用 `agentPreset: jiaodui-chemistry-unit` 选择子 preset；DSH 0.2.1 起不再使用 `toolFilter`/`persona`，`backgroundMode` 也已移除。化学的 `jiaodui_calc_chemistry_balance` / `jiaodui_calc_stoichiometry` 在 `calc_*` 内一并放行；子代理仍拿不到 `jiaodui_unit_cancel`。
- **原生工具 `jiaodui`**：旧命令 `args: string[]` 透传入口继续保留，作为兼容 CLI 退路。
- **结构化工具**：按 task/unit ID 提供位置查询、版本快照、建议提交、恢复预算和阶段/取消事件；每个 calc operation 使用独立 JSON Schema。

## 安装

DSH bundle 本身不包含 Python CLI。最终发布 tar.gz 会同时提供 `dsh-jiaodui` 与 `dsh-jiaodui-chemistry` 两个 bundle、同一版本 `jiaodui` wheel、运行依赖约束和 macOS/Windows 安装脚本；归档由 `scripts/release/build-release.sh` 生成并附 SHA-256 sidecar。目标机不需要源码仓库、Node、构建工具或开发 venv。

目标机需预先安装独立 CPython 3.12 和 Pandoc。不要使用 DSH 自带签名 Python 创建 CLI 环境；其签名运行时可能拒绝加载 pip 安装的原生扩展。Pandoc 是 DOCX 导入与 Word 导出的必需外部程序，安装脚本会验证可执行状态。

解压发布 tar.gz 后运行对应脚本：

- macOS：`bash install-macos.sh`
- Windows PowerShell：`./install-windows.ps1`

脚本先校验 `SHA256SUMS`，再将 CLI 与受约束依赖安装到按版本隔离的用户数据目录，执行 `pip check`、真实依赖导入和 `check-env`：

- macOS：`$HOME/Library/Application Support/JiaoDuiAgentSkill/versions/<版本>/venv`
- Windows：`%LOCALAPPDATA%\\JiaoDuiAgentSkill\\versions\\<版本>\\venv`

安装完成后，通过 DSH 官方 `install_bundle` 安装发布目录里的 `dsh-jiaodui-chemistry`（物理包同理，可只装其中一个）。

CLI 的机器输出由 core 固定为 UTF-8，插件启动 Python 时也显式设置 UTF-8 mode 与 stdio 编码。结构化提案写入系统临时目录下的 UTF-8 JSON 文件并通过 `--proposal-json-file` 传入 CLI，调用结束即清理。

## 安装 bundle

推荐用 DSH 自己安装，不要手改 profile 的 `package.json` 或 `cordis.patch.yml`。

- **图形界面**：侧栏「插件」页 → 按**本地路径**安装下面的包目录：
  `<仓库根>/packages/dsh-jiaodui-chemistry`
- **creator 模式会话**：`plugin_manager`，`action: install_bundle`，
  `target` = 该包目录的绝对路径。

安装会把本包登记进 profile 的 `dsh.profile.bundles` 与 `dependencies`。
新增 bundle 可能经 HMR 立即生效；**替换已安装的包需要重启**才能加载新的 JS 模块代际。

## 启用与验证

1. 安装后确认 bundle 在「插件」页列出、行 `preset-jiaodui-chemistry` 激活。
2. **新开**一个会话，在 agent preset 里选「校对（高中化学）」（或在「设置 → 通用」把它设为之后会话的默认）。
3. 验证新会话工具目录包含 `jiaodui`、`jiaodui_unit_read`、`jiaodui_unit_locate`、`jiaodui_unit_snapshot`、`jiaodui_unit_submit`、`jiaodui_calc_chemistry_balance`、`jiaodui_calc_stoichiometry` 和 `subagent`；随包 `jiaodui-chemistry` skill 可加载。当前 preset 不挂载通用 shell/fs bundle 之外的工具；宿主可能额外注入默认 skill 或其他工具，须记录实际目录，不能以静态配置声称强隔离。
4. 验证工具：让 agent 调用 `jiaodui` 工具，例如 `args: ["check-env"]`；再调用 `args: ["calc", "chemistry_balance", "--subject", "高中化学", "--param", "equation=Fe + O2 -> Fe2O3"]`，应看到 `4Fe + 3O2 -> 2Fe2O3`。
5. 视觉门槛使用随包 `skills/jiaodui-chemistry/assets/vision-probe.png`，不依赖待校对文件有没有图片。按 skill 的 `references/vision-probe.md` 派发不带答案的观察任务；DSH `read_image` 使用 `file_path`。
6. 真机验收清单见 `host-probe/README.md`（含化学配平在子 agent 工具目录中的补测）。

## 配置（profile patch 按行 id 覆盖）

最终安装默认按 bundle 版本自动发现 CLI。仅需覆盖默认路径时，在 DSH 的插件配置中填写完整绝对路径：

    - id: jiaodui-tools
      name: dsh-jiaodui-chemistry
      config:
        command: /用户目录/Library/Application Support/JiaoDuiAgentSkill/versions/0.1.0/venv/bin/jiaodui
        timeoutMs: 180000
        maxOutputBytes: 65536

CLI 查找顺序为：显式 `command` → bundle 同版本的用户级运行时 → 仓库软链开发环境 → PATH。显式配置的路径不存在会报错，不回退到其他版本。两个 bundle 共用同一份用户级运行时，因此路径相同；覆盖其中一个不影响另一个。

每次调用从会话读取工作区 W，并同时设置 cwd 与 `JIAODUI_WORK_ROOT`；会话缺少工作区时拒绝执行。产物默认位于 `W/校对/<材料名>/`。

## 化学与物理的边界

- 化学只走本包的 `jiaodui-chemistry` skill：化学用语检查清单、配平与计量实算、离子/热化学方程式专项；**不套用物理的受力图 / 电路 / 量纲分析专项**。
- 化学 `quantities` 为空表：`jiaodui quantities --subject 高中化学` 稳定返回 0 条，`calc dimensional` 没有量表可交叉校验，单位一律按题面写显式单位表达式。
- 化学与物理的 `split_mode` / `wrapped_patterns` / `exam_question_pattern` / `nav_patterns` 逐字一致（由测试锁定），差异只在学科名与量表。
- 未落地学科不得回退套用任一已落地学科的流程。

## 已知限制

- preset 必须自带完整 plugins 列表，当前按校对流程显式维护。skill 默认发现和子代理工具范围依赖宿主，仓内静态测试不能替代真实会话验收。
- 化学 v1 只落地试卷 + 讲义主链路；独立解题（`independent_solve`）冻结不启用；批注评审、自由校对、classics 检索后置。
- 教学科配置 `exam_question_pattern = ^(\d+)．` 与物理一致（按题号拆题）；真实化学语料出现别的题号习惯时再按样本调整，调整要走镜像同步与测试。
- 原生工具**不是** bash 沙箱的替代：它只调用受信任的本地 CLI，不应对它传任意 shell。

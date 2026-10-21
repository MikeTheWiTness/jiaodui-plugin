# dsh-jiaodui

把 jiaodui 的**高中物理**校对流程接入 DSH profile 的**自包含组合包（bundle）**：
挂载随包的 jiaodui skill、注册一个 jiaodui 原生工具、并声明一个「校对」agent preset。

本包只是 PRD 所说的「薄适配」：不含任何校对业务判断，判断仍由宿主 agent 完成，
确定性仍由 jiaodui Python CLI 完成。**CLI 永远是退路**——插件坏了，bash 里照样能跑。

高中化学是**另一个独立包** [`dsh-jiaodui-chemistry`](../dsh-jiaodui-chemistry/README.md)（preset「校对（高中化学）」），
不并入本包：两者可同时安装、分别启用，共用同一份 CLI 与学科无关原生工具，取舍见 `docs/adr/0007-second-subject-entry-and-bundle-split.md`。

## 结构

    packages/dsh-jiaodui/
      package.json           dsh.bundle.patch = ./cordis.patch.yml；同时是可挂载的插件入口
      cordis.patch.yml       自带组合包：插入 preset-jiaodui（含 skill 挂载 + 原生工具行）
      tools/index.js         宿主适配：注册校对及强类型工具
      tools/calc-schemas.json 由计算核心元数据导出的operation schema
      tools/proposal-schema.json 结构化建议schema v2
      tools/proposal-schema-v3.json 正常原文修订 schema v3（core 导出）
      tools/proposal-schema-bind-current.json core 绑定的精简 v2 schema（unit_submit_v2 直接读）
      skills/jiaodui/        随包 skill（仓库 skills/jiaodui 的副本，测试守一致性）
        assets/             固定读图探针（SVG 源、透明 PNG、预合成白底 PNG）
      locale/{zh,en}.json    插件管理页的标题与描述
      icon.svg               插件卡片图标
      README.md

## 它做了什么

- **实验分支 preset「校对」（id `jiaodui`）**：保留结构化单元读取/定位/提交、真实 read_image、单层子 agent 和交付能力，关闭 shell、web、goal、plan 与 fork。父侧保留聚合 fs；子侧由独立子 preset「校对（高中物理·单元子代理）」（id `jiaodui-unit`）封闭，`toolset: unit` 只允许读取/计算/提交，不暴露 write/edit、argv 退路、取消或父复核。
  - `skill-filesystem` 的 `customSkillDirs` 指向本包 `skills/`，用于发现随包 jiaodui skill。
  - `./tools/index.js` 注册原生工具 `jiaodui`；`toolset: unit` 时只注册单元读取/定位/快照/提交/恢复/心跳与全部 `calc_*`。
  - `tool-subagent` 用 `agentPreset: jiaodui-unit` 选择子 preset；DSH 0.2.1 起不再使用 `toolFilter`/`persona`，`backgroundMode` 也已移除。
  实际宿主已确认支持 `includeDefaultRoots:false`、`agentPreset` 子 preset 选择和 `maxDepth:1`；本 preset 已配置这些字段。子 preset 先不挂 `agent-instructions`：单元规则以 SKILL 与派发 prompt 为准，避免仓库开发约定占子代理上下文。静态结构检查不替代新会话父子实际 catalog 验收，也不将开发会话 CLI 回放当作安装验证。
- **原生工具 `jiaodui`**：旧命令 `args: string[]` 透传入口继续保留，作为兼容CLI退路。
- **结构化工具**：按task/unit ID提供位置查询、版本快照、建议提交、恢复预算和阶段/取消事件；14个计算operation使用独立JSON Schema。calc schema从Python核心 `OPERATIONS` 元数据生成，打包测试核对副本漂移。

正常 `jiaodui_unit_submit` 使用 v3 原文修订，core 自动定位并编译 v2；`jiaodui_unit_snapshot` 的 `with_proposal` 用于按 ID 增量撤回/新增。`jiaodui_unit_submit_v2` 保留显式旧提案入口。两入口共用原有提交、证据、verify 与父复核闸门，插件只透传。

## 安装

DSH bundle 本身不包含 Python CLI。最终发布 tar.gz 会同时提供同版本 bundle、`jiaodui` wheel、运行依赖约束和 macOS/Windows 安装脚本；归档由 `scripts/release/build-release.sh` 生成并附 SHA-256 sidecar。目标机不需要源码仓库、Node、构建工具或开发 venv。

目标机需预先安装独立 CPython 3.12 和 Pandoc。不要使用 DSH 自带签名 Python 创建 CLI 环境；其签名运行时可能拒绝加载 pip 安装的原生扩展。Pandoc 是 DOCX 导入与 Word 导出的必需外部程序，安装脚本会验证可执行状态。

解压发布 tar.gz 后运行对应脚本：

- macOS：`bash install-macos.sh`
- Windows PowerShell：`./install-windows.ps1`

脚本先校验 `SHA256SUMS`，再将 CLI 与受约束依赖安装到按版本隔离的用户数据目录，执行 `pip check`、真实依赖导入和 `check-env`：

- macOS：`$HOME/Library/Application Support/JiaoDuiAgentSkill/versions/<版本>/venv`
- Windows：`%LOCALAPPDATA%\\JiaoDuiAgentSkill\\versions\\<版本>\\venv`

安装完成后，通过 DSH 官方 `install_bundle` 安装发布目录里的 `dsh-jiaodui`。插件读取 bundle 自身版本并自动发现匹配的 CLI；一般不需要设置 `command`。显式设置时必须指向当前 bundle 对应的版本目录。

CLI 的机器输出由 core 固定为 UTF-8，插件启动 Python 时也显式设置 UTF-8 mode 与 stdio 编码。结构化提案写入系统临时目录下的 UTF-8 JSON 文件并通过 `--proposal-json-file` 传入 CLI，调用结束即清理；不会把大 JSON 放进 Windows 命令行，也不会在材料目录留下额外文件。CLI 仍兼容小提案的 `--proposal-json` 参数。

仓库软链开发环境仍单独使用仓库内独立 `.venv`。自动发现会按平台检查 `.venv/bin/jiaodui` 或 `.venv/Scripts/jiaodui.exe`，并要求仓库 core 同时存在；这条开发后备不属于最终包或需要迁移的内容。

## 安装 bundle

推荐用 DSH 自己安装，不要手改 profile 的 `package.json` 或 `cordis.patch.yml`
（DSH 官方插件开发规范要求由 `install_bundle` 完成这些步骤）。

- **图形界面**：侧栏「插件」页 → 按**本地路径**安装下面的包目录：
  `<仓库根>/packages/dsh-jiaodui`
- **creator 模式会话**：`plugin_manager`，`action: install_bundle`，
  `target` = 该包目录的绝对路径。

安装会把本包登记进 profile 的 `dsh.profile.bundles` 与 `dependencies`。
新增 bundle 可能经 HMR 立即生效；**替换已安装的包需要重启**才能加载新的 JS 模块代际。

## 启用与验证

1. 安装后确认 bundle 在「插件」页列出、行 `preset-jiaodui` 激活。
2. **新开**一个会话，在 agent preset 里选「校对」（或在「设置 → 通用」把它设为之后会话的默认）。
3. 验证新会话工具目录包含 `jiaodui`、`jiaodui_unit_read`、`jiaodui_unit_locate`、`jiaodui_unit_snapshot`、`jiaodui_unit_submit`、`jiaodui_calc_evaluate` 和 `subagent`；随包 `jiaodui` skill可加载。当前preset不挂载通用shell/fs bundle工具，但宿主可能额外注入默认 skill 或其他工具；须记录实际目录，不能以静态配置声称强隔离。
4. 验证工具：让 agent 调用 `jiaodui` 工具，例如 `args: ["check-env"]`，应看到退出码与输出。
5. 视觉门槛使用随包 `skills/jiaodui/assets/vision-probe.png`，不依赖待校对文件有没有图片，不需要现场绘图。按 skill 的 `references/vision-probe.md` 派发不带答案的观察任务；DSH `read_image` 使用 `file_path`，应先核对工具 schema。同一会话和模型/工具配置通过一次即可复用。

## 配置（profile patch 按行 id 覆盖）

最终安装默认按 bundle 版本自动发现 CLI。仅需覆盖默认路径时，在 DSH 的插件配置中填写完整绝对路径；路径可含空格：

    - id: jiaodui-tools
      name: dsh-jiaodui
      config:
        command: /用户目录/Library/Application Support/JiaoDuiAgentSkill/versions/0.1.0/venv/bin/jiaodui
        timeoutMs: 180000
        maxOutputBytes: 65536
        # cwd 不再作为默认值：每次调用使用当前会话工作区。

CLI 查找顺序为：显式 `command` → bundle 同版本的用户级运行时 → 仓库软链开发环境 → PATH。显式配置的路径不存在会报错，不回退到其他版本。

每次调用从会话读取工作区 W，并同时设置 cwd 与 `JIAODUI_WORK_ROOT`；会话缺少工作区时拒绝执行。产物默认位于 `W/校对/<材料名>/`，不会随源文件位置或宿主进程 cwd 改变。标准输出和错误在进程结束后收集，超时仍保留已收集诊断；外部用户取消传播取消语义，不包装为普通技术失败，也不触发主 agent 重派。普通调用只传 `args`（及必要的 cwd 兼容字段），不要主动填写权限升级字段。

## 讲义与试卷

skill 优先采用用户指定类型；未指定时调用 `inspect-source` 读取 Word 嵌套表格统计，正文大量重复嵌套按讲义处理，证据不足再有限预览或询问。判断完成后 `convert --mode lecture|exam` 执行对应导入，`split` 沿用类型；未知类型不会默认成试卷。两类材料共用单元校对、校验登记和报告生成。

`inspect-source` 默认不返回正文，显式 `--preview-chars` 上限为 2,000 个字符（不是行数）；`slice --preview` 输出清理后的正文，边界清单使用行号。`inspect-images --unit <单元目录> --json` 按正文顺序返回图片引用、原图和实际读取图。识别工具只返回结构事实；类型来源通过 `--mode-origin user|structure|preview|confirmed` 与简短 `--mode-reason` 留在材料记录。人工标记/整篇拆分使用 `split --strategy manual|none`，智能拆分仍由宿主判断边界后调用 `slice`。

## 已知限制

- preset 必须自带完整 plugins 列表，当前按校对流程显式维护。skill默认发现和子代理工具范围依赖宿主，仓内静态测试不能替代真实会话验收。
- 本包只声明高中物理；高中化学是独立包 `dsh-jiaodui-chemistry`，其余学科未落地。未落地学科不得回退套用物理流程。
- 已通过打包契约、原生工具行为测试及仓库外 wheel 的确定性链路验证；
  DSH 实际会话中的子 agent 读图、落盘和整卷校对质量仍需宿主验收，自动测试不替代它。
- 原生工具**不是** bash 沙箱的替代：它只调用受信任的本地 CLI，不应对它传任意 shell。

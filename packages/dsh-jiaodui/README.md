# dsh-jiaodui

把 jiaodui 的 K-12 校对流程接入 DSH profile 的**自包含组合包（bundle）**：
挂载随包的 jiaodui skill、注册一个 jiaodui 原生工具、并声明一个「校对」agent preset。

本包只是 PRD 所说的「薄适配」：不含任何校对业务判断，判断仍由宿主 agent 完成，
确定性仍由 jiaodui Python CLI 完成。**CLI 永远是退路**——插件坏了，bash 里照样能跑。

## 结构

    packages/dsh-jiaodui/
      package.json           dsh.bundle.patch = ./cordis.patch.yml；同时是可挂载的插件入口
      cordis.patch.yml       自带组合包：插入 preset-jiaodui（含 skill 挂载 + 原生工具行）
      tools/index.js         宿主适配：注册校对及强类型工具
      tools/calc-schemas.json 由计算核心元数据导出的operation schema
      tools/proposal-schema.json 结构化建议schema v2
      skills/jiaodui/        随包 skill（仓库 skills/jiaodui 的副本，测试守一致性）
        assets/             固定读图探针（SVG 源、透明 PNG、预合成白底 PNG）
      locale/{zh,en}.json    插件管理页的标题与描述
      icon.svg               插件卡片图标
      README.md

## 它做了什么

- **agent preset「校对」（id `jiaodui`）**：自带 plugins 列表并使用 native 工具呈现；保留单元身份读取/定位/提交、子 agent、询问、任务、交付展示和压缩能力，关闭shell、通用fs、web、goal、plan与嵌套fork。
  - `skill-filesystem` 的 `customSkillDirs` 指向本包 `skills/`，用于发现随包 jiaodui skill。
  - `./tools/index.js` 注册原生工具 `jiaodui`。
  当前配置没有默认 skill 排他白名单，也没有按父/子角色限制文件工具操作；无关 skill 是否仍被宿主注入、子 agent 实际工具范围需在 DSH 新会话中核验，不能仅凭 bundle 配置认定已隔离。
- **原生工具 `jiaodui`**：旧命令 `args: string[]` 透传入口继续保留，作为兼容CLI退路。
- **结构化工具**：按task/unit ID提供位置查询、版本快照、建议提交、恢复预算和阶段/取消事件；14个计算operation使用独立JSON Schema。calc schema从Python核心 `OPERATIONS` 元数据生成，打包测试核对副本漂移。

## 安装

本 bundle 不包含 Python CLI。新机先安装 Python 3.12、pipx 和 pandoc，构建并安装 wheel：

```bash
python3.12 -m pip install build
python3.12 -m build --wheel
pipx install --python python3.12 'dist/jiaodui-0.1.0-py3-none-any.whl[render]'
jiaodui check-env --json
```

Python 须来自 pyenv / Homebrew / python.org 等独立安装。macOS 上不要用 DSH 自带的签名 Python 创建 CLI 环境，也不要继承其系统包：签名运行时可能拒绝加载 pip 安装的原生扩展（Team ID 不一致）。`[render]` 安装 matplotlib，供 Word 批注中的公式渲染；不需要此能力时可省略。

开发软链安装使用仓库内的独立 `.venv`：`python3.12 -m venv .venv`，再执行 `.venv/bin/python -m pip install -e '.[dev,render]'`。`.venv` 也可为指向已验证独立环境的软链，无须修改 profile 的工具配置。用 `.venv/bin/jiaodui check-env --json` 检查解释器路径和 matplotlib 可用性。

插件按显式 `command`、开发软链对应的仓库 venv、PATH 上的 `jiaodui` 查找；复制安装不依赖施工仓库。未找到时明确报安装错误，不自动安装或回退任意 Python。

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

    - id: jiaodui-tools
      name: dsh-jiaodui
      config:
        command: /绝对路径/.venv/bin/jiaodui   # 省略时自动探测；探测不到回退 PATH 上的 jiaodui
        timeoutMs: 180000
        maxOutputBytes: 65536
        # cwd 不再作为默认值：每次调用使用当前会话工作区。

`command` 的自动探测：工具模块按自身位置推导 `<仓库根>/.venv/bin/jiaodui`；
若包被**复制**进 profile（而非 `file:` 链接回仓库），该路径不存在，就回退 `jiaodui`，
此时须安装 wheel 并让 PATH 包含 pipx bin，或显式给 `command`。

每次调用从会话读取工作区 W，并同时设置 cwd 与 `JIAODUI_WORK_ROOT`；会话缺少工作区时拒绝执行。产物默认位于 `W/校对/<材料名>/`，不会随源文件位置或宿主进程 cwd 改变。标准输出和错误在进程结束后收集，超时仍保留已收集诊断；外部用户取消传播取消语义，不包装为普通技术失败，也不触发主 agent 重派。普通调用只传 `args`（及必要的 cwd 兼容字段），不要主动填写权限升级字段。

## 讲义与试卷

skill 优先采用用户指定类型；未指定时调用 `inspect-source` 读取 Word 嵌套表格统计，正文大量重复嵌套按讲义处理，证据不足再有限预览或询问。判断完成后 `convert --mode lecture|exam` 执行对应导入，`split` 沿用类型；未知类型不会默认成试卷。两类材料共用单元校对、校验登记和报告生成。

`inspect-source` 默认不返回正文，显式 `--preview-chars` 上限为 2,000 个字符（不是行数）；`slice --preview` 输出清理后的正文，边界清单使用行号。`inspect-images --unit <单元目录> --json` 按正文顺序返回图片引用、原图和实际读取图。识别工具只返回结构事实；类型来源通过 `--mode-origin user|structure|preview|confirmed` 与简短 `--mode-reason` 留在材料记录。人工标记/整篇拆分使用 `split --strategy manual|none`，智能拆分仍由宿主判断边界后调用 `slice`。

## 已知限制

- preset 必须自带完整 plugins 列表，当前按校对流程显式维护。skill默认发现和子代理工具范围依赖宿主，仓内静态测试不能替代真实会话验收。
- 只声明高中物理（skill 的学科矩阵里其余 6 科仍为 M5 待落地）。未落地学科不得回退套用物理流程。
- 已通过打包契约、原生工具行为测试及仓库外 wheel 的确定性链路验证；
  DSH 实际会话中的子 agent 读图、落盘和整卷校对质量仍需宿主验收，自动测试不替代它。
- 原生工具**不是** bash 沙箱的替代：它只调用受信任的本地 CLI，不应对它传任意 shell。

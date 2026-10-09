# dsh-jiaodui

把 jiaodui 的 K-12 校对流程接入 DSH profile 的**自包含组合包（bundle）**：
挂载随包的 jiaodui skill、注册一个 jiaodui 原生工具、并声明一个「校对」agent preset。

本包只是 PRD 所说的「薄适配」：不含任何校对业务判断，判断仍由宿主 agent 完成，
确定性仍由 jiaodui Python CLI 完成。**CLI 永远是退路**——插件坏了，bash 里照样能跑。

## 结构

    packages/dsh-jiaodui/
      package.json           dsh.bundle.patch = ./cordis.patch.yml；同时是可挂载的插件入口
      cordis.patch.yml       自带组合包：插入 preset-jiaodui（含 skill 挂载 + 原生工具行）
      tools/index.js         宿主半侧插件：注册 jiaodui 原生工具（argv 透传 CLI）
      skills/jiaodui/        随包 skill（仓库 skills/jiaodui 的副本，测试守一致性）
        assets/             固定读图探针（SVG 源、透明 PNG、预合成白底 PNG）
      locale/{zh,en}.json    插件管理页的标题与描述
      icon.svg               插件卡片图标
      README.md

## 它做了什么

- **agent preset「校对」（id `jiaodui`）**：自带完整 plugins 列表（以内置 `standard` preset 为底座，工具呈现为 `native`），保留 bash / filesystem / skill / spawn 子代理 / todo / present / compaction 与 jiaodui CLI；显式关闭 web、goal、plan、fork。
  - `tool-fs` 保留 `read`、`read_image`（宿主 attachments 可用时）与旧报告所需 `write` / `edit`；不挂载新的报告提交工具。
  - `skill-filesystem` 只从本包 `skills/` custom 目录加载，不读取默认 skill roots。
  - spawn 子代理限制 `maxDepth: 1`，工具目录 allowlist 为 `skill/read/read_image/write/edit/jiaodui`。宿主 `toolFilter` 不能据此视作严格权限隔离；待第 7 章依赖/子权限实验后再收紧。
  - `./tools/index.js` 注册原生工具 `jiaodui`。
  工具直接接收 JSON 参数，不要求生成 `run_code` 程序。子代理只开放单层 spawn 与并行派发，PTC workflow 引擎保持禁用。
- **原生工具 `jiaodui`**：参数 `args: string[]` 原样透传给 CLI（如
  `["verify-report", "--unit", "<单元目录>"]`），返回 `exitCode / stdout / stderr / truncated`。
  它走宿主平面的 `ctx.subprocess`（子进程服务会清洗环境变量），不是 bash。

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
3. 验证模式与 skill：重新加载组合包后新开「校对」会话，工具目录应包含 `read`、`read_image`（attachments 已挂载时）、`write`、`edit`、`jiaodui`、`subagent` 等；不应有 web/goal/plan/fork。子代理工具目录按 allowlist 配置，但这不是严格权限隔离证明。会话的 skill 目录里应出现 `jiaodui`；加载它返回 SKILL.md 正文。已有会话不作为模式切换成功的证明；若新会话仍仅暴露 `run_code`，先重启 DSH 以重新加载 preset。
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

- preset 的公共 plugins 列表以内置 `standard` preset 为参考：DSH 的 preset 不提供继承，
  公共能力行变更时需要同步。这是「薄适配」当前最脆的一处。
- 只声明高中物理（skill 学科矩阵中其余 6 科尚未落地）。未落地学科不得回退套用物理流程。
- Desktop profile 已安装本 bundle，`node_modules/dsh-jiaodui` 指向仓库 `packages/dsh-jiaodui`；新会话 tool catalog/profile 重载及实际读图、写报告仍需宿主验收。
- 已通过打包契约、原生工具行为测试及仓库外 wheel 的确定性链路验证；自动测试不替代 DSH 实际会话验收。
- 原生工具**不是** bash 沙箱的替代：它只调用受信任的本地 CLI，不应对它传任意 shell。

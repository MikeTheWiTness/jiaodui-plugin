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
      locale/{zh,en}.json    插件管理页的标题与描述
      icon.svg               插件卡片图标
      README.md

## 它做了什么

- **agent preset「校对」（id `jiaodui`）**：自带完整 plugins 列表（与内置 `ptc` preset 同构，
  含 bash / fs / subagent / todo / web / present / goal / plan / compaction），外加：
  - `skill-filesystem` 的 `customSkillDirs` 指向本包 `skills/`，所以 jiaodui skill
    只在这个 preset 的会话里可见（DSH 的 skill 发现按 preset 分层）；
  - `./tools/index.js` 注册原生工具 `jiaodui`。
- **原生工具 `jiaodui`**：参数 `args: string[]` 原样透传给 CLI（如
  `["verify-report", "--unit", "<单元目录>"]`），返回 `exitCode / stdout / stderr / truncated`。
  它走宿主平面的 `ctx.subprocess`（子进程服务会清洗环境变量），不是 bash。

## 安装

本 bundle 不包含 Python CLI。新机先安装 Python 3.12、pipx 和 pandoc，构建并安装 wheel：

```bash
python3.12 -m pip install build
python3.12 -m build --wheel
pipx install --python python3.12 dist/jiaodui-0.1.0-py3-none-any.whl
jiaodui check-env --json
```

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
3. 验证 skill：会话的 skill 目录里应出现 `jiaodui`；加载它返回 SKILL.md 正文。
4. 验证工具：让 agent 调用 `jiaodui` 工具，例如 `args: ["check-env"]`，应看到退出码与输出。

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

每次调用从会话读取工作区 W，并同时设置 cwd 与 `JIAODUI_WORK_ROOT`；会话缺少工作区时拒绝执行。产物默认位于 `W/校对/<材料名>/`，不会随源文件位置或宿主进程 cwd 改变。标准输出和错误在进程结束后收集，超时仍保留已收集诊断。

## 讲义与试卷

skill 优先采用用户指定类型；未指定时调用 `inspect-source` 读取 Word 嵌套表格统计，正文大量重复嵌套按讲义处理，证据不足再有限预览或询问。判断完成后 `convert --mode lecture|exam` 执行对应导入，`split` 沿用类型；未知类型不会默认成试卷。两类材料共用单元校对、校验登记和报告生成。

`inspect-source` 默认不返回正文，显式 `--preview-chars` 最大 2000。识别工具只返回结构事实；类型来源通过 `--mode-origin user|structure|preview|confirmed` 与简短 `--mode-reason` 留在材料记录。人工标记/整篇拆分使用 `split --strategy manual|none`，智能拆分仍由宿主判断边界后调用 `slice`。

## 已知限制

- preset 的 plugins 列表是内置 `ptc` preset 的副本：DSH 的 preset 不提供继承，
  公共能力行变更时需要同步。这是「薄适配」当前最脆的一处。
- 只声明高中物理（skill 的学科矩阵里其余 6 科仍为 M5 待落地）。未落地学科不得回退套用物理流程。
- 已通过打包契约、原生工具行为测试及仓库外 wheel 的确定性链路验证；
  DSH 实际会话中的子 agent 读图、落盘和整卷校对质量仍需宿主验收，自动测试不替代它。
- 原生工具**不是** bash 沙箱的替代：它只调用受信任的本地 CLI，不应对它传任意 shell。

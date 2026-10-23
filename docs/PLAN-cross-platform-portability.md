# 最终 DSH 插件包的 Windows / macOS 兼容性计划

状态：Windows 专属实现与验收暂停，等待 Windows 实机测试。本计划只覆盖最终插件交付与目标机安装运行；不迁移开发仓库、开发环境或校对工作区。持久材料锁、最终发布包、macOS 安装链和共用 CLI 行为已实现；Windows 代码与 PowerShell 安装器目前仅是待实机验证的候选，不据此声明兼容。macOS 与平台无关部分可继续推进。

## 1. 目标与边界

目标是在另一台受支持的 Mac 或 Windows 主机上，通过 DSH 官方插件安装入口安装最终交付物，配置完成后能运行 jiaodui 工具链，并通过完整校对与 Word 交付冒烟。

这里的“插件包”需要包括最终 DSH bundle 以及它运行所需的 jiaodui CLI 发布物、依赖版本信息和安装/诊断入口。插件 JS 目前只负责调用外部 Python CLI，因此仅复制当前 `dsh-jiaodui` 目录还不构成可运行交付。

明确不在本计划内：

- 移交 Git 仓库、开发脚本、测试环境、venv、编辑器设置或开发机 PATH。
- 迁移已处理的材料、校对报告或用户工作区；如需跨系统搬迁材料，另立计划。
- 构建独立桌面 GUI/冻结 exe；保留现有 DSH 插件 + Python CLI 架构。
- PDF/OCR 输入、其他学科扩展或其它 agent 宿主的移植。

目标平台建议：Windows 11 x64、macOS Apple Silicon、macOS Intel。要求目标机使用受支持的 DSH 桌面版本。若 DSH 尚未为某平台发布或支持插件安装/受管子进程，该平台不能仅凭 Python 包测试就宣称受支持。

## 2. 当前已确认的包交付缺口

| 现状 | 证据 | 对最终插件安装的影响 |
| --- | --- | --- |
| DSH bundle 明确不包含 Python CLI | [bundle README](../packages/dsh-jiaodui/README.md#L32) | 只安装或复制 bundle 后会出现“未找到 CLI”；必须提供同版本 CLI wheel 与依赖安装入口 |
| Python 要求 ≥3.12，依赖仅声明版本下限 | [pyproject.toml](../pyproject.toml#L6) | 目标机系统 Python 可能过旧；不同机器安装时也可能得到不同依赖组合 |
| 材料锁原先使用 `fcntl.flock` 并打开目录 fd | [material.py](../jiaodui/material.py#L462) | Windows 原实现无法运行；本轮已改为材料根持久锁文件，POSIX 与 Windows 各用系统锁 API，Windows 原生行为待 CI 验证 |
| 并发测试原先在缺少 `fcntl` 时跳过整个模块 | [test_concurrency.py](../tests/test_concurrency.py#L1) | 本轮已移除平台跳过，新增锁文件稳定、有限等待和持锁进程终止恢复测试；本机通过，Windows CI 待跑 |
| 插件自动发现原先仅查 `.venv/bin/jiaodui` | [插件适配器](../packages/dsh-jiaodui/tools/index.js#L35) | 已实现显式配置 → 同版本用户运行时 → 开发 venv → PATH；Node 模拟 macOS/Windows 发现分支通过，DSH GUI 真机仍待验收 |
| 最终用户此前需自行取得 wheel，未有一致安装入口 | [release README](../scripts/release/README.md) | 已生成最终 tar.gz、双平台安装器与两层 SHA；Mac 全新 HOME 安装通过，Windows 安装器等待 Windows CI/真机 |
| 安装说明围绕仓库 wheel 构建和 Unix venv 路径编写 | [bundle README](../packages/dsh-jiaodui/README.md#L32) | 这是开发安装流程，不能作为最终用户从发布包安装的步骤 |
| 结构化提案原先由插件以内联 JSON argv 传给 CLI | [插件提交](../packages/dsh-jiaodui/tools/index.js#L209)、[CLI 提交](../jiaodui/cli.py#L239) | 已改用受管临时 UTF-8 JSON 文件参数；CLI 保留内联兼容，200 KB 插件测试与真实 CLI 文件提交通过 |
| CLI / DSH 子进程原先未强制 UTF-8 | [CLI 入口](../jiaodui/cli.py#L782)、[插件适配器](../packages/dsh-jiaodui/tools/index.js#L570) | CLI 固定 stdout/stderr UTF-8，插件设置 Python UTF-8 mode 和 stdio；ASCII locale 模拟测试通过 |
| CI 原先只建 wheel、未执行最终 Windows 安装器 | [CI 配置](../.github/workflows/tests.yml#L34) | 已加入 Windows/macOS release smoke 目录组装与安装脚本步骤；尚待 CI runner 实际结果 |
| Pandoc 是单独的外部必需依赖；检测逻辑可能把版本查询失败当成可用 | [convert.py](../jiaodui/convert.py#L92)、[checkenv.py](../jiaodui/checkenv.py#L115) | 目标机要另装 Pandoc，或发布物须按平台附带；当前预检成功不总等于可执行 |
| CI 已扩展至 Ubuntu 24.04、Windows 2022、macOS 14 / Python 3.12 | [CI 配置](../.github/workflows/tests.yml#L4) | Windows/macOS 现运行最终 wheel 仓库外安装器冒烟；变更尚未在 GitHub runner 执行，真机 DSH 验收仍待完成 |

现有有利条件：Python core 是平台通用 wheel（`py3-none-any`）；大部分 Python 子进程调用已传 argv 数组；Pandoc 主调用已设置 UTF-8、超时和 Windows 窗口隐藏；JS 插件主要使用 Node 内置模块。需通过真实目标机运行确认这些基础的边界行为。

会话归档复现过实际分发失败：目标机系统 Python 为 3.9.6，只有 DSH 插件而没有 jiaodui CLI wheel，宿主因此无法找到 CLI。这也是本计划的直接依据。目标机不得因缺少 CLI 而退回开发仓路径或误用 DSH 签名 Python。

## 3. 最终交付物建议

最终交付目录已实现为版本化 `dsh-jiaodui-<版本>.tar.gz`：同一发布号中包含 DSH bundle、`py3-none-any` CLI wheel、runtime constraints、macOS/Windows 安装器、安装说明和全文件 SHA256SUMS；旁路 SHA256 校验归档本身。安装器已实现逐文件摘要验证。

- 已实现版本化 tar.gz 发布组装器：匹配 bundle 与 CLI 版本、复制 Git 跟踪 bundle 文件、构建 wheel，附带 runtime constraints、Mac/Windows 安装器、全文件 SHA256SUMS 和归档侧 checksum。安装器要求独立 CPython 3.12 与已安装 Pandoc；解释器和 Pandoc 本体当前不内嵌，目标机需要单独安装。

### Windows 实机门槛

用户要求 Windows 相关工作先等待 Windows 实机测试。本门槛前不新增 Windows 专属实现、不依据 Node 模拟或 GitHub Windows runner 把兼容性标记为通过，也不发布“Windows 已验收”结论。现有 Windows 代码、PowerShell 安装器和 CI job 保留为待检候选；实机测试时按最终 tar.gz 执行并记录 OS build、CPU、独立 Python 版本/架构、Pandoc 版本、命令和完整结果，再据失败修复。Mac 与平台无关的发布工作可以继续。


### 第一批：固定发布契约与目标矩阵

- 明确首发目标为 DSH 已支持的 Windows 11 x64、macOS Apple Silicon、macOS Intel；验证具体 DSH 版本和插件安装能力。
- 首批统一使用独立 CPython 3.12；Python 3.13/3.14 只有通过依赖与宿主验证后才增加支持声明。
- 定义 bundle / CLI / schema 的兼容版本字段与发布编号。bundle 与 CLI 不匹配时在安装预检或 `check-env` 中给出明确错误。
- 区分最终用户安装流程与开发流程：目标机不需要 git、仓库、Node、构建工具、pytest、editable install 或开发 venv。

完成判据：有一份发布契约，列出各目标 DSH、OS、CPU、Python、Pandoc 和依赖版本，并区分“目标支持”与“已验收”。

### 第二批：使 Python core 可在 Windows 主机运行

- **Windows 实机暂停项**：代码当前含 `msvcrt` 锁分支，但不据此宣称 Windows 可运行。待实机确认跨进程互斥、异常退出释放、等待行为和并发更新后，再决定是否保留或修正。
- POSIX/macOS 使用材料根 `.jiaodui.lock` 持久文件锁；目录边界、线程互斥、有界等待与进程退出恢复已在当前 macOS 测试通过。
- 并发测试已取消 `fcntl` 缺失时的整模块跳过；Windows runner 结果可作为辅助信号，但按用户要求不作为 Windows 验收依据。
- **Windows 实机暂停项**：Word/WPS 占用时 `os.replace`、OEM code page、盘符/UNC/长路径和取消行为待实机确认。
- `unit-submit` 支持 `--proposal-json-file` 并保留内联兼容；插件把提案写到系统临时 UTF-8 文件，调用结束清理。真实 CLI 文件提交与 200 KB 插件 argv 长度测试在 macOS 通过；Windows argv 限制规避仍待实机确认。
- CLI stdout/stderr 与 DSH 子进程 Python 环境已固定 UTF-8；ASCII locale 模拟测试通过。Windows 终端与 DSH GUI 的原生编码行为待实机确认。

完成判据：**macOS 与共用代码部分通过，Windows 待实机验收**。实机至少验证转换、拆分、授权、单元读取/计算、结构化提交、复核、Word 生成、并发、长提案、文件占用失败和中文路径。

### 第三批：为最终用户提供安装与 CLI 定位

- macOS 安装器已校验独立 CPython 3.12、Pandoc、bundle/wheel 版本、SHA256SUMS，安装后运行 `pip check` 和 `check-env`；已在仓库外全新 HOME 实测通过。
- Windows PowerShell 安装器具备相同检查逻辑，但**未在 Windows 实机运行**；等待实机测试，不标记为通过。
- 插件查找顺序为显式 `command` → bundle 同版本用户目录 → 仓库开发 venv → PATH；Node 的 macOS/Windows 平台分支模拟不替代 Windows 实机 executable resolver/spawn 验收。
- 最终包遵循 DSH 官方 bundle 安装方式，不写未知 profile 配置；tar.gz 包含 bundle、wheel、constraints、安装说明和两层摘要。
- Pandoc 需要目标机单独安装；安装器验证 `pandoc --version` 成功。
- 同版本安装会强制重装 wheel；升级按版本隔离目录，旧版环境暂留以供手工回退。没有自动卸载/回滚工具。

完成判据：**macOS 安装通过；Windows 安装待实机测试；两平台 DSH GUI 真实会话尚未验收**。

### 第四批：验证最终包与锁定版本

- 发布 constraints 已固定核心及 render 依赖。`pip download --only-binary` 已为 Windows x64、Intel Mac x86_64 和 Apple Silicon、CPython 3.12 找到 wheel；这是索引解析结果，不是目标机原生 import 验收。
- 最终 tar.gz 的 bundle、wheel、SHA 清单和中文 UTF-8 路径已在 macOS 构建、解压、校验；macOS arm64 仓库外安装通过。
- **Windows wheel/原生扩展兼容性待实机测试**；不依据远程 wheel 下载候选宣布支持。Python 3.13/3.14 继续列为未支持，直至按独立测试矩阵验收。
- `check-env` 版本与系统信息扩展仍待后续批次；当前通过只证明其已声明的必需项，不证明宿主/视觉/Office 能力。

完成判据：**发布结构及 macOS arm64 安装通过；Windows 与 Intel Mac 原生运行仍待验收**。

### 第五批：跨平台 CI 与 DSH 真机验收

- CI 配置保留 Ubuntu/Windows/macOS 合同作业和最终安装器冒烟，但按用户要求 Windows job 不作为本阶段支持门槛；Windows 相关结论必须来自指定 Windows 实机测试记录。
- Windows 实机测试前，不依据 Windows CI、Node 平台模拟或下载到 wheel 宣称 Windows 兼容。实机应记录 OS build、CPU、独立 Python 版本/架构、Pandoc 版本、发布 SHA、命令和原始结果。
- macOS arm64 已完成仓库外安装，但 Mac DSH GUI 会话、工具发现、视觉探针、真实读图、取消与 Word 冒烟仍未完成。Intel Mac 也待专门验收。
- 完整校对链需在每个宣称支持的实机逐项验证：bundle 安装 → CLI 发现 → 工作区注入 → 读图/结构化提交 → 状态/父复核 → Word 交付和 Office/WPS 打开。
- 发布 gate 只对已覆盖的实机和 DSH 版本声明支持；未测组合保留“未验收”。

完成判据：**目标整体未完成**；当前只有 Mac arm64 CLI 安装和 core 测试证据，Windows 实机与两平台 DSH 宿主链仍是硬缺口。

## 5. 最终包验收场景

| 场景 | 验收结果 |
| --- | --- |
| 目标机系统 Python 低于 3.12 | 安装器阻止误装并给出独立 CPython 安装步骤；不调用 DSH 签名 Python |
| 只迁移最终发布物，不迁移仓库和 venv | 插件及 CLI 安装成功，无 import checkout、家目录软链或开发 PATH 依赖 |
| DSH GUI PATH 与终端不同 | 插件仍发现安装登记路径的 CLI |
| Windows 中文用户名、带空格/括号路径 | 工具启动、Pandoc 转换、图片与 Word 输出正常 |
| Windows 多 CLI 进程写入 | 互斥可靠、进程崩溃后锁释放、材料记录与预算无丢失 |
| 大型 v2 提案 | 不受操作系统命令行长度上限影响，仍经过原验证与 CAS |
| Word/WPS 正打开目标文件 | 返回稳定错误，保留旧文件与失败信息，不把未完成产物登记为成功 |
| 缺 Pandoc/依赖、下载失败或 CLI 版本不匹配 | 安装/预检明确失败，不显示“可用”或自动退回其它 CLI |
| 升级中断或新版冒烟失败 | 保留可回退的上一已验证 CLI 版本 |
| DSH 未支持的目标平台 | 明确标记不支持/未验收，不宣称 Python wheel 可构建就等于插件可用 |

## 6. 执行顺序和变更约束

建议顺序：**发布契约 → Windows core 硬阻塞 → 最终用户安装/发现 → 依赖与诊断 → 跨平台 CI → DSH 真机验收与发布**。

确定性代码遵守 [AGENTS.md](../AGENTS.md#L46) 的行为契约测试要求；业务逻辑继续只放在 Python core，JS 插件仅做宿主适配。锁实现或 CLI 通讯改变前，核实现有工具 API；不得为了兼容而降低工作区边界、v2 提交、CAS、预算、图片证据或 Word 闸门。

本计划刻意不包含开发仓克隆、测试环境迁移或用户材料搬迁。最终包采用同一发布版本的 DSH bundle 与 Python CLI wheel，并附平台安装步骤；Python/Pandoc 是否随各目标平台附带二进制，作为第一批发布契约决策，须考虑体积、许可、更新和签名后再定。

# P2 真机验收清单（分支 preset + 原生工具面）

目标：在真实 DSH 新会话里验证 `feature/structured-report-pipeline` 的 preset 与原生工具面，
而不是用 CLI 代理路径代替。全程不改分支代码；验收前只做「worktree venv + profile 软链 + 重启」。

## 前置（本次已完成/待完成）

| 项 | 状态 | 说明 |
|---|---|---|
| worktree 独立 venv | ✅ 已建 | `.worktrees/structured-report/.venv`，`pip install -e '.[dev,render]' build`；`jiaodui` 解析到 worktree |
| 插件能找到 CLI | ✅ 已验证 | 插件按 `<包>/../../../.venv/bin/jiaodui` 发现；该文件存在且可执行 |
| CLI 确实跑分支 core | ✅ 已验证 | 从 `cwd=主仓` 调 `<worktree>/.venv/bin/jiaodui --json dispatch-plan …` 成功（分支独有命令）；主仓 CLI 同命令 exit 2 |
| profile 软链切分支 | ⏳ 见下 | `~/.dsh/profiles/desktop/package.json` 的 `dsh-jiaodui` 指向 worktree 包 |
| 重启 DSH | ⏳ 需用户执行 | bundle 在启动时加载，热更不生效 |

## 为什么必须切软链

插件有两处按**包自身位置**解析：

- `packages/dsh-jiaodui/tools/index.js:38` → `<包>/../../../.venv/bin/jiaodui`
- `cordis.patch.yml` 的 `customSkillDirs` → `createRequire(baseUrl).resolve('dsh-jiaodui/package.json')`

profile 仍指向主仓包时，这两处都会落到主仓：native 工具会驱动**主仓 core**（没有 `unit-submit`/`dispatch-plan` 这些命令），
skill 也会挂主仓那份。所以 P2 必须让 profile 解析到 worktree 包。

**易错点（实测）**：editable 安装的元路径查找器排在 `PathFinder` 之后，所以
`python -c` / `python -m jiaodui` 在 `cwd=主仓` 时会读到**主仓**的 `jiaodui`。
插件用的是**控制台脚本**（`sys.path[0]` = 脚本目录，不是 cwd），因此不受影响——
这也是「必须让插件走控制台脚本」的原因，不要改成 `python -m`。

## 会话设置

- 工作区：`/Users/chouchou/开发/JiaoDuiAgentSkill`（夹具与回放材料在 `校对/`）
- preset：**校对**（`agent-preset-registry` 的默认是 `standard`，需在建会话时选「校对」）
- 建议模型：与本次评测一致；图片证据型单元要真读图

## 验收项

1. **父 catalog**
   - 应可见：`jiaodui_task_prepare`、`jiaodui_delivery`、`jiaodui_unit_progress`、`jiaodui_dispatch_plan`、通用 `jiaodui`，**以及 shell（bash / pwsh 按平台）与只读搜索 `fs_search`**
   - 变更记录（2026-10-09，真机验收后）：初版预设移除了父侧 shell，实测代价是「能复现 Word 锚点丢失、能收窄到条件，却没有任何读 docx 内部 XML 的通道，根因查不下去、只能交接」。现改为**父侧恢复 shell + 只读搜索，子侧仍封闭**；理由与证据见 `PROCESS_REWORK.md` 的 Word 根因复核一节。
2. **子 catalog**（派一个子 agent，看它拿到什么）
   - 应为 `cordis.patch.yml` 里 `toolFilter.allow` 的 20 项：`skill`、`read`、`read_image`、
     `jiaodui_unit_read/locate/snapshot/submit/event/recovery`、`jiaodui_calc_*`
   - 不应有 `bash`、`write`、`edit`（子 agent 只能通过 `unit-submit` 交提案）
3. **skill 挂载**：只挂分支包 `skills/jiaodui`（`includeDefaultRoots: false`），`SKILL.md` 码点 < 8192
4. **`read_image` 实读**：对夹具单元3 的原图与白底副本各实读一次（不能用 CLI 代替读图）
5. **零 shell 的真实校对**：子 agent 全程用原生工具完成 读取→计算→自查→`unit-submit`；
   父代理用 `jiaodui_dispatch_plan` 补位、`jiaodui_delivery` 交付
6. **停止语义**：中止一次子 agent 调用 → 插件抛中性 `AbortError`（不猜来源），
   父代理用 `jiaodui_unit_event` 显式记 parent 取消
7. **CLI 发现判别器**：`jiaodui --json dispatch-plan --task-id <夹具task>` 可用即证明跑的是分支 core
8. **噪音**：`check-env` 会带 matplotlib 缓存警告（`~/.matplotlib` 不可写）。若影响阅读，
   设 `MPLCONFIGDIR` 指向可写目录

## 回滚（一条命令）

```bash
cd ~/.dsh/profiles/desktop
cp package.json.bak-p2-20261009-224655 package.json
cp pnpm-lock.yaml.bak-p2-20261009-224655 pnpm-lock.yaml
ln -sfn ../../../../开发/JiaoDuiAgentSkill/packages/dsh-jiaodui node_modules/dsh-jiaodui
# 然后重启 DSH
```

切换记录（2026-10-09 22:46:55）：`package.json`、`pnpm-lock.yaml`、`node_modules/dsh-jiaodui` 三处同步改到 worktree 包；
自检 `node -e createRequire(...).resolve('dsh-jiaodui/package.json')` → worktree 包，skill 目录与插件 CLI 均解析到 worktree。

## 与 P6 真实校对的关系

P2 通过后，P6 余下的最小真实校对（图片证据型＝夹具单元3；转义边界型＝新建含竖线合成单元）
改用**原生工具面**跑，不再用 CLI 代理路径。

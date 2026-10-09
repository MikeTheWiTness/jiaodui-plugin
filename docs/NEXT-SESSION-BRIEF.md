# 交接简报：P2 宿主验收 + P6 最小真实校对

> 给「校对」preset 新会话用的自包含简报。读这份 + [`P2-ACCEPTANCE.md`](P2-ACCEPTANCE.md) + [`PROCESS_REWORK.md`](PROCESS_REWORK.md) 即可开工；不需要上一个会话的上下文。

## 你现在在什么会话里

- preset = **校对**（`preset-jiaodui`，由 `packages/dsh-jiaodui/cordis.patch.yml` 声明）
- 工作区应是 `/Users/chouchou/开发/JiaoDuiAgentSkill`（材料在 `校对/`）
- 这个 preset **没有 shell**（`tool-bash` / `tool-pwsh` / `fs-search` 都被移除），父代理用 `jiaodui_*` 原生工具；这是设计，不是故障
- 插件用的 CLI 是 `/.worktrees/structured-report/.venv/bin/jiaodui`（分支 core），判别器：`jiaodui --json dispatch-plan --task-id <task>` 可用即证明跑的是分支

## 任务一：P2 验收（按 `docs/P2-ACCEPTANCE.md` 的 8 条逐条做）

重点四条，做之前先确认拿到的工具面本身：

1. **父 catalog**：应可见 `jiaodui_task_prepare`、`jiaodui_delivery`、`jiaodui_unit_progress`、`jiaodui_dispatch_plan`、通用 `jiaodui`；不应有 `bash`
2. **子 catalog**：派一个子 agent，看它拿到的是 20 项（`skill`/`read`/`read_image` + `jiaodui_unit_*` + `jiaodui_calc_*`），**没有** `bash`/`write`/`edit`
3. **`read_image` 实读**：必须真读图，不能用 CLI 代替
4. **停止语义**：中止一次子 agent 调用，父代理用 `jiaodui_unit_event` 显式记 parent 取消；插件应抛中性 `AbortError`，不猜来源

## 任务二：P6 最小真实校对（两个单元，各跑一次，不做更多）

| 类型 | 材料 | task_id | 单元 / unit_id | 特征 |
|---|---|---|---|---|
| 图片证据型 | `校对/第 6 讲校对测试-分支性能测试` | `236927c8ceb44ea3bfdef3bff15e525b` | `单元3` / `59759d1521a3449c8a183b77fe38ea82` | 2 张图（原图 + 白底副本），未开始 |
| 转义边界型 | `校对/P6转义边界合成` | `6166638e79594f5caf77c0aadd5849c1` | `第1题` / `665683a274ad422795218044fe618d37` | 源文含 14 个表格竖线与 1 处 `【注】`，转义路径由真实判断可达 |

要求：

- 走正常流程（`jiaodui_task_prepare` 执行模式 → 派子 agent → `jiaodui_dispatch_plan` 补位 → `jiaodui_delivery` 交付），不要手工铺状态
- **不要**跑这两份材料里其它未开始单元；**不要**动 4讲/5讲回放材料的既有留痕
- 转义边界型要确认：报告里的标记字段确实带转义（`\|`），而 Word/交付侧是反转义后的字面
- 结果（是否通过闸门、`_校对失败.md` 有则贴错误码、Word 结构计数）追加进 `docs/PROCESS_REWORK.md`

## 不许做

- 不 push；不改 `~/` 以外的宿主配置；不回退 profile 软链（除非要回滚整个 P2，见 `P2-ACCEPTANCE.md`）
- 不在 Python 侧加凭证/模型调用
- 真实校对只做上面这 2 个单元，不要扩大范围

## 做完之后

把结论写进 `docs/PROCESS_REWORK.md`，并在提交信息里写明：P2 验收结果（8 条逐条）+ 两个单元的真实结果 + 双口径测试数字（若需要跑测试：这个 preset 没 shell，得切回 standard preset 或用 `--work-root` 之外的会话跑）。

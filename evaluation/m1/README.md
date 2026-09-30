# M1 端到端竖切样本（高中物理「第 6 讲」）

> 此快照为历史布局，保持原样。当前新布局见 ADR 0002；历史写入仍须授权工作区并显式 `--legacy-layout`。

本目录是 [docs/M1.md](../../docs/M1.md) 的可复现快照，随提交入仓；
`output/` 下的运行产物仍不入仓，复现时先还原本快照。

快照对应当前代码的**重跑运行**（见 M1.md §9）：`split` 补齐讲义导入清理后
重新拆分，5 个单元子 agent 重新校对并全部通过闸门。

## 样本

| 项 | 值 |
| --- | --- |
| 源文件 | `source/第 6 讲校对测试.docx` |
| SHA-256 | `59c36b3781287e43438a8130f1bac7ac60b2f4bcf4972413212771f01f573fc2` |
| 来源 | 用户本地 `~/Downloads/第 6 讲校对测试.docx`，仅复制，未改原文件 |

## 快照内容与还原

- `source/`：原始 docx。
- `raw/`：`convert` 产物（`_raw.md` + `第 6 讲校对测试_images/media/`）。
- `units/`：`split` 的 5 个单元目录，含单元源文、`_校对报告.md`、`images/`。

还原到 M1 记录使用的路径：

```bash
mkdir -p output/M1-第6讲校对测试
cp -R evaluation/m1/. output/M1-第6讲校对测试/
```

> `evaluation/m1/units/**/_校对报告.md` 经 `git add -f` 纳入版本控制
> （`.gitignore` 默认忽略该文件名）；这是验收证据，不是可自由再生成的产物。

## 可复现的命令与预期

还原后：

```bash
for u in 单元1 单元2 单元3 单元4 单元5; do
  .venv/bin/jiaodui verify-report --unit "output/M1-第6讲校对测试/units/第 6 讲校对测试/$u"
  echo "$u exit=$?"
done
.venv/bin/jiaodui build-docx "output/M1-第6讲校对测试/units/第 6 讲校对测试" --work-root "$PWD" --legacy-layout
```

预期：5 个单元 `verify-report` 退出码全 0；`build-docx` 输出
`标记 28 = 锚点 28 + 公式兜底 0，缺失 0`，`ok=true`，且 28 条批注都带修改原因。
回归测试见 [tests/test_m1_fixture.py](../../tests/test_m1_fixture.py)。

单元字符数（清理后重跑）：1006 / 655 / 1175 / 656 / 1032。

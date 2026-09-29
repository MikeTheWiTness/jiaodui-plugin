# M1 端到端竖切样本（高中物理「第 6 讲」）

本目录是 [docs/M1.md](../../docs/M1.md) 验收记录的可复现快照，随提交入仓；
`output/` 下的运行产物仍不入仓，复现时先还原本快照。

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

## 可复现的命令

还原后，[docs/M1.md](../../docs/M1.md) §2 的命令可直接执行：

```bash
.venv/bin/jiaodui verify-report --unit "output/M1-第6讲校对测试/units/第 6 讲校对测试/单元1"
.venv/bin/jiaodui build-docx "output/M1-第6讲校对测试/units/第 6 讲校对测试"
```

预期：5 个单元 verify 通过；`build-docx` 输出 `标记 24 = 锚点 24 + 公式兜底 0，缺失 0`，
且 24 条批注都带修改原因。回归测试见 `tests/test_m1_fixture.py`。

## 注意

快照中的单元源文由**补齐导入清理之前**的 `split` 产出。当前代码的
`prepare_lecture_content` 已补上【出题意图】清理 / 题图挪位 / 选项空格压缩
（见 [docs/M1.md](../../docs/M1.md) §8），重新跑 `split` 会改变单元源文，
届时这批报告将因未标记正文差异无法通过 `verify-report`。要恢复一致性需在
修复后源文上重跑校对。

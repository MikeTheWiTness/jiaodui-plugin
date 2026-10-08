# M1 端到端竖切样本（高中物理「第 6 讲」）

> 此快照保留历史布局。2026-10-08 同步清理已确认的破图占位引用及其尺寸属性，原始 DOCX 不变。当前新布局见 ADR 0002；历史写入仍须授权工作区并显式 `--legacy-layout`。

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

占位图清理仅移除 raw 中的 image1/2/3 引用，以及单元1源文和报告中的
image2/3 引用及属性；其余正文、修改标记和修改原因不变。历史 PNG 保留供核对，
不再参与正文读图。重新导入后只复制 image4..8 五张有效图片，拆分后同样为五张。

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

回归测试见 [tests/test_m1_fixture.py](../../tests/test_m1_fixture.py)：CI 里断言
① 5 个单元过闸门；② **交付入口 `build_docx` 的对账**（`marker = anchor + formula_fallback`、
`missing = 0`、`over_count = 0`）外加独立解压数批注；③ 每条批注都带修改原因。
②是 R-F02 补上的——此前「28 = 28 + 0」只在 CI 之外用 shell 复现。

[tests/test_material_type.py](../../tests/test_material_type.py) 另从原始 DOCX 重跑
转换、拆分、交付登记和 Word 生成：逐单元源文与本快照一致、五个报告通过闸门，
并独立检查 28 条批注及 Word 正文无孤立的尺寸属性。

单元字符数（清理后重跑）：832 / 655 / 1175 / 656 / 1032。

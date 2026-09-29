# 22 单元评估样本（冻结）

- 冻结日期：2026-09-29
- 旧仓：`/Users/chouchou/开发/JiaoDuiAgent` @ `1c452430aebe`
- 清单：`evaluation/sample-22.json`（本文件是人读版，内容同源）
- 源文长度 P90：1268 字符（以有源文的 122 个单元计）
- 哈希算法：sha256（源文与旧报告均取文件原始字节）

> **冻结声明**：样本在编写 `scripts/recompute_baseline.py` 时确定并冻结；索引与成员不再变动。
> 新版结果只能与本清单对照，不得因新版表现更换样本（PRD §8 / D29）。

## 选入规则

从有同目录单元源文（{unit}.md）的真实旧产物中选取；逐一覆盖含图片、含公式标记、长单元（源文字符数 ≥ 源文样本 P90）、无问题单元、旧流程曾漏检候选（严重错误/严重度未声明/标记审计 unknown/空操作）。序在写脚本时冻结，不因新版结果更换。

按旧仓 source 目录布局，单元源文只存在于 `output/拆题结果/<文档>/<单元>/<单元>.md`；
`output/中间产物/<文档>/<单元>/` 只有报告、数据与 API 记录。因此样本一律取拆题结果目录（报告与源文同目录），并记录中间产物镜像报告路径。

## 覆盖矩阵

| 覆盖项 | 命中数 | 样本序号 |
| --- | ---: | --- |
| 含图片题 | 18 | 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 22 |
| 含公式标记 | 15 | 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19 |
| 长单元（源文 ≥ 1268 字符） | 7 | 5, 7, 8, 13, 15, 16, 20 |
| 无问题单元 | 4 | 1, 7, 8, 21 |
| 有标记单元 | 16 | 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20 |
| 无标记单元 | 6 | 1, 7, 8, 15, 21, 22 |
| 严重错误（旧报告） | 2 | 2, 17 |
| 严重度未声明/不可解析（旧报告） | 5 | 15, 16, 18, 19, 22 |
| 标记审计 unknown>0 | 7 | 2, 4, 5, 6, 10, 12, 13 |
| 含空操作标记 | 1 | 14 |

学科：物理 14 / 化学 8；来源模式：试卷 14 / 讲义 8。

## 逐样本清单

| # | 文档 | 单元 | 学科/模式 | 旧报告严重度 | 源文字符 | 图片 | 公式标记 | 标记数 | 空原文 | 空操作 |
| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 高一上期中卷 | 第1题 | 物理/试卷 | 无问题 | 288 | 0 | 0 | 0 | 0 | 0 |
| 2 | 高一上期中卷 | 第2题 | 物理/试卷 | 严重错误 | 580 | 1 | 2 | 4 | 0 | 0 |
| 3 | 高一上期中卷 | 第12题 | 物理/试卷 | 轻微问题 | 826 | 2 | 9 | 11 | 0 | 0 |
| 4 | 高一上期中卷 | 第11题 | 物理/试卷 | 轻微问题 | 605 | 0 | 5 | 5 | 0 | 0 |
| 5 | 高一上月考卷1 | 第15题 | 物理/试卷 | 轻微问题 | 1498 | 3 | 9 | 9 | 0 | 0 |
| 6 | 高一上月考卷1 | 第17题 | 物理/试卷 | 轻微问题 | 791 | 1 | 8 | 9 | 0 | 0 |
| 7 | 高一上月考卷1 | 第9题 | 物理/试卷 | 无问题 | 1414 | 1 | 0 | 0 | 0 | 0 |
| 8 | 高三年级-秋季-期末考试卷 | 第13题 | 物理/试卷 | 无问题 | 1268 | 1 | 0 | 0 | 0 | 0 |
| 9 | 高三年级-秋季-期末考试卷 | 第18题 | 物理/试卷 | 轻微问题 | 1090 | 2 | 7 | 7 | 0 | 0 |
| 10 | 高三年级-秋季-期末考试卷 | 第17题 | 物理/试卷 | 一般问题 | 692 | 1 | 4 | 4 | 0 | 0 |
| 11 | 2026年7月21日高中物理作业 | 第16题 | 物理/试卷 | 轻微问题 | 834 | 1 | 9 | 19 | 0 | 0 |
| 12 | 2026年7月21日高中物理作业 | 第18题 | 物理/试卷 | 轻微问题 | 1036 | 1 | 8 | 8 | 0 | 0 |
| 13 | 2026年7月21日高中物理作业 | 第15题 | 物理/试卷 | 轻微问题 | 1380 | 1 | 3 | 8 | 0 | 0 |
| 14 | 2026年7月21日高中物理作业 | 第5题 | 物理/试卷 | 轻微问题 | 462 | 1 | 1 | 2 | 0 | 1 |
| 15 | 第 1 讲初识原电池 | 单元53 | 化学/讲义 | <unparseable> | 1772 | 1 | 0 | 0 | 0 | 0 |
| 16 | 第 1 讲初识原电池 | 单元31 | 化学/讲义 | 未声明 | 1651 | 5 | 2 | 5 | 0 | 0 |
| 17 | 第 1 讲初识原电池 | 单元14 | 化学/讲义 | 严重错误 | 1167 | 0 | 3 | 3 | 0 | 0 |
| 18 | 第 1 讲初识原电池 | 单元19 | 化学/讲义 | 未声明 | 1187 | 3 | 1 | 7 | 0 | 0 |
| 19 | 第 1 讲初识原电池 | 单元42 | 化学/讲义 | 未声明 | 1151 | 4 | 5 | 6 | 0 | 0 |
| 20 | 第 1 讲初识原电池 | 单元3 | 化学/讲义 | 轻微问题 | 1541 | 5 | 0 | 5 | 0 | 0 |
| 21 | 第 1 讲初识原电池 | 单元29 | 化学/讲义 | 无问题 | 1240 | 0 | 0 | 0 | 0 | 0 |
| 22 | 第 1 讲初识原电池 | 单元9 | 化学/讲义 | <unparseable> | 1248 | 1 | 0 | 0 | 0 | 0 |

## 路径与哈希

### 1. 高一上期中卷 / 第1题

- 选入理由：无问题单元（旧报告走无问题快速通道）；无标记；源文无图片、无公式（最短基线样本）
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第1题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第1题/第1题.md`
  - sha256 `ff9d5b9fadc6de13e736912317ecc90babfda04dd0d18d0f91758ec67807c16e`（288 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第1题/_校对报告.md`
  - sha256 `30761c34d3c6cb242344e1c991e05d91fb8a2272ac862ea5ecdb3db9f5265a03`（1499 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/高一上期中卷/第1题/_校对报告.md`

### 2. 高一上期中卷 / 第2题

- 选入理由：旧流程曾漏检候选：旧报告声明严重错误，4/4 标记 audit=unknown（原文字段对不上源文）；严重错误
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第2题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第2题/第2题.md`
  - sha256 `827a1e5fbd7460ffb43fe277c03106e841af85a2bdffacc716cd50f33a21882a`（580 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第2题/_校对报告.md`
  - sha256 `54b6943249759651dae6ac1437e3fe85c3f79a71b1d88b823b3b23ca6df1886c`（2924 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/高一上期中卷/第2题/_校对报告.md`
- 旧标记审计：{"unknown": 4}

### 3. 高一上期中卷 / 第12题

- 选入理由：含公式标记（9/11 标记字段含 $）；多标记（11 条）；含图片
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第12题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第12题/第12题.md`
  - sha256 `1e28d91ddf3d4f5ccc9ec95ec7a5a99ac995319cbe3555b0314ff86ceb5ad47e`（826 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第12题/_校对报告.md`
  - sha256 `5615860839a546f659cc1678451158d68960153ec01d80e83e46b747bedfdd1a`（3119 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/高一上期中卷/第12题/_校对报告.md`
- 旧标记审计：{"ok": 11}

### 4. 高一上期中卷 / 第11题

- 选入理由：标记审计 unknown（5/5 定位不到源文）；源文无图片
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第11题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第11题/第11题.md`
  - sha256 `61f59813839d701848b30303abef1f03a89eca92fb2b3f0fd2127de62397adf8`（605 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上期中卷/第11题/_校对报告.md`
  - sha256 `825e7afbb5cb6d126907dfa5ffe223be9b5a1e9488323fda265b1f95072315a6`（7211 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/高一上期中卷/第11题/_校对报告.md`
- 旧标记审计：{"unknown": 5}

### 5. 高一上月考卷1 / 第15题

- 选入理由：长单元（1498 字符 ≥ P90）；含公式标记（9/9）；含图片（3 张）；审计 ok/unknown 混合
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上月考卷1/第15题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上月考卷1/第15题/第15题.md`
  - sha256 `824649f37c8af3ac1bc849935216b2010ca149c36562faa3004f9ed77006df6c`（1498 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上月考卷1/第15题/_校对报告.md`
  - sha256 `2c29216b2f4ca1c79a19b6b096a707c0bff8e975979a751f6862ebd82b90ee4e`（4912 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/高一上月考卷1/第15题/_校对报告.md`
- 旧标记审计：{"ok": 4, "unknown": 5}

### 6. 高一上月考卷1 / 第17题

- 选入理由：含公式标记（8/9）；标记审计 unknown 3 条
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上月考卷1/第17题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上月考卷1/第17题/第17题.md`
  - sha256 `6d4e57a2a34f2e7ee7c6cd2369847640b1c5f9afd588d8e0dc94e277f078256b`（791 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上月考卷1/第17题/_校对报告.md`
  - sha256 `9f3f2e53eb61eb2f298d8c0592fa04c2c1eba11f420a376cee406f08032710a1`（4623 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/高一上月考卷1/第17题/_校对报告.md`
- 旧标记审计：{"ok": 6, "unknown": 3}

### 7. 高一上月考卷1 / 第9题

- 选入理由：长单元（1414 字符）；无问题单元；含图片
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上月考卷1/第9题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上月考卷1/第9题/第9题.md`
  - sha256 `b0d75fe4126fda5f8c825f578900a01907a475170df3cd2803a2244274c5ede6`（1414 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高一上月考卷1/第9题/_校对报告.md`
  - sha256 `6d01fe7ed5edc7ce731d38d0ab28862e781e21ab8142eaa04679af10ffb8073c`（10025 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/高一上月考卷1/第9题/_校对报告.md`

### 8. 高三年级-秋季-期末考试卷 / 第13题

- 选入理由：长单元（1268 字符 = P90）；无问题单元；含图片
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高三年级-秋季-期末考试卷/第13题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高三年级-秋季-期末考试卷/第13题/第13题.md`
  - sha256 `45ea01e5ca5349edbbf780bb508ebafc1d9d94cb416ead91a8b608d9f6fd5e44`（1268 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高三年级-秋季-期末考试卷/第13题/_校对报告.md`
  - sha256 `c37c246bdad73c3db6bb85602147a1ef8e0b4794d642d2f01017a72d9a4d0f9c`（7690 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/高三年级-秋季-期末考试卷/第13题/_校对报告.md`

### 9. 高三年级-秋季-期末考试卷 / 第18题

- 选入理由：含公式标记（7/7）；含图片（2 张）
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高三年级-秋季-期末考试卷/第18题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高三年级-秋季-期末考试卷/第18题/第18题.md`
  - sha256 `5ef732432be3581b457b3f9cc9d1842db6070a122012ce05d88e0b9f455483ca`（1090 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高三年级-秋季-期末考试卷/第18题/_校对报告.md`
  - sha256 `8a04e8f0102f6afb4b8f81493d9e5dea741e0eac10369423086b53d90874db92`（9076 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/高三年级-秋季-期末考试卷/第18题/_校对报告.md`
- 旧标记审计：{"ok": 7}

### 10. 高三年级-秋季-期末考试卷 / 第17题

- 选入理由：严重度=一般问题；含公式标记（4/4）；标记审计 unknown 3 条
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高三年级-秋季-期末考试卷/第17题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高三年级-秋季-期末考试卷/第17题/第17题.md`
  - sha256 `8d132050a8a0bbbd3e1bf7c57631dbebd80dfc659a4b5ecffda5b7a9ab89a795`（692 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/高三年级-秋季-期末考试卷/第17题/_校对报告.md`
  - sha256 `13772c1310f770210748d6a5e0fd8dd5e7367ed01584a8f8b0083f5927f9d57d`（7419 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/高三年级-秋季-期末考试卷/第17题/_校对报告.md`
- 旧标记审计：{"unknown": 3, "ok": 1}

### 11. 2026年7月21日高中物理作业 / 第16题

- 选入理由：标记数最多（19 条）；含公式标记（9 条）；含图片
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第16题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第16题/第16题.md`
  - sha256 `8e5090e9fdf9c97eb19998728deb2a2fc4a5cbb7c93b7623650b53ef89441139`（834 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第16题/_校对报告.md`
  - sha256 `1f37bcdc62c24e84291b46223f944727cc3a519d79e7540bd84583083c3730ce`（7515 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/2026年7月21日高中物理作业/第16题/_校对报告.md`
- 旧标记审计：{"ok": 19}

### 12. 2026年7月21日高中物理作业 / 第18题

- 选入理由：含公式标记（8/8）；标记审计 unknown（8/8 全部定位不到）
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第18题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第18题/第18题.md`
  - sha256 `706257207e89c20cbc2e89ea33a52160242c39b6202b27d0a2c1be8c76c90fc7`（1036 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第18题/_校对报告.md`
  - sha256 `6e823a1b428bbfbef8f4e6fbe6a077ef014446a541647b5114172db4de8abf37`（9197 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/2026年7月21日高中物理作业/第18题/_校对报告.md`
- 旧标记审计：{"unknown": 8}

### 13. 2026年7月21日高中物理作业 / 第15题

- 选入理由：长单元（1380 字符）；含图片；含公式标记
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第15题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第15题/第15题.md`
  - sha256 `168fd48c29e86ec4c9ac1a3e5f08b822f9d56979f6a25f76aca92a47f00556cb`（1380 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第15题/_校对报告.md`
  - sha256 `ed4e80711d98f16ea319a03d4b406ed06b20414cd0381c19c54906539a06155e`（3796 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/2026年7月21日高中物理作业/第15题/_校对报告.md`
- 旧标记审计：{"ok": 7, "unknown": 1}

### 14. 2026年7月21日高中物理作业 / 第5题

- 选入理由：含空操作标记（原文==改为，旧产物不合格样本）；含公式标记；含图片
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第5题`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第5题/第5题.md`
  - sha256 `bb098cbaeb52847684bc36915b2615b33ad498b8be692e4d52fcedd63d4710f6`（462 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/2026年7月21日高中物理作业/第5题/_校对报告.md`
  - sha256 `14929de3840382903170032b054b77af3c2a62e64477b504adda7cddab910115`（3039 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/2026年7月21日高中物理作业/第5题/_校对报告.md`
- 旧标记审计：{"ok": 1, "noop": 1}

### 15. 第 1 讲初识原电池 / 单元53

- 选入理由：最长单元（1772 字符）；旧报告严重度未声明（parse 返回 None）；无标记
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元53`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元53/单元53.md`
  - sha256 `34acd5d07a96dea9c5716287bc2b3c4d3ea1a7f403a44b1a850bd7d60082ab95`（1772 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元53/_校对报告.md`
  - sha256 `0ba415c595e52f5acfa1ce33fed703300d57ff3dc239f7d73bd804520c5e305e`（2459 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/第 1 讲初识原电池/单元53/_校对报告.md`

### 16. 第 1 讲初识原电池 / 单元31

- 选入理由：长单元（1651 字符）；旧报告严重度未声明（总结行缺失）；含图片（5 张）；含公式标记
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元31`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元31/单元31.md`
  - sha256 `0d138521d92edc86a6e35b3bd12d1c2437cca666177eaf0ee65db20497cf1839`（1651 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元31/_校对报告.md`
  - sha256 `c03c4cd111b97c01543023c08fba3f24b5e4f5a277eef7259922b2560c9c93bd`（7544 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/第 1 讲初识原电池/单元31/_校对报告.md`
- 旧标记审计：{"ok": 5}

### 17. 第 1 讲初识原电池 / 单元14

- 选入理由：旧流程曾漏检候选：旧报告声明严重错误；严重错误
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元14`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元14/单元14.md`
  - sha256 `5590fdc2c786f6bc13735ef761e792c41c9bb65c8829b53458924c396b0e4420`（1167 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元14/_校对报告.md`
  - sha256 `8b161485899622405bbf0b5529822cbeb26a6dfba250e22042439b49dbca0c1a`（6382 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/第 1 讲初识原电池/单元14/_校对报告.md`
- 旧标记审计：{"ok": 3}

### 18. 第 1 讲初识原电池 / 单元19

- 选入理由：旧报告严重度未声明；多标记（7 条）；含图片
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元19`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元19/单元19.md`
  - sha256 `b8d9f740e898ee065ecc58cd6cd6ad5ae25ddc621a9635af0544074c551a5d46`（1187 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元19/_校对报告.md`
  - sha256 `62b5a9e22e0cbd50f6c23ce1626c717756cd5e2642818bdf1b01e06e64f09000`（5251 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/第 1 讲初识原电池/单元19/_校对报告.md`
- 旧标记审计：{"ok": 7}

### 19. 第 1 讲初识原电池 / 单元42

- 选入理由：旧报告严重度未声明；含公式标记；含图片（4 张）
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元42`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元42/单元42.md`
  - sha256 `1be5bf960ddc82bd7b0000ea2ac2af5a3f388cdb182b4f1183052a71d59e3c3e`（1151 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元42/_校对报告.md`
  - sha256 `f36361e4ace4012378d434a5e767938d14adc733d6351f05bf9e65f14746d587`（3110 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/第 1 讲初识原电池/单元42/_校对报告.md`
- 旧标记审计：{"ok": 6}

### 20. 第 1 讲初识原电池 / 单元3

- 选入理由：含图片（5 张）；有标记；长单元（1541 字符）
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元3`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元3/单元3.md`
  - sha256 `68da71f37cb975dcadc049b06bf335d673d6ae80d8c91cfd40258ee2474c23a5`（1541 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元3/_校对报告.md`
  - sha256 `3d9be01635835d4a1bcd27061d1d213df4add9a20fa198bf4204ea7619871762`（7387 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/第 1 讲初识原电池/单元3/_校对报告.md`
- 旧标记审计：{"ok": 5}

### 21. 第 1 讲初识原电池 / 单元29

- 选入理由：无问题单元；长单元（1240 字符）；无标记
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元29`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元29/单元29.md`
  - sha256 `5f1ba205471aacdde3cde13c2fb8adad80500e8cd09593e6c9f8f8e07cea84c8`（1240 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元29/_校对报告.md`
  - sha256 `d3e8a8f115cd352df0d36e8f055162efdcc3f8cfb14ff8720a52ac7d6e00c30d`（3390 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/第 1 讲初识原电池/单元29/_校对报告.md`

### 22. 第 1 讲初识原电池 / 单元9

- 选入理由：旧报告严重度未声明（parse 返回 None）；含图片；无标记
- 单元目录：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元9`
- 源文：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元9/单元9.md`
  - sha256 `e28e6e1e11bba178de2a5a219d177e48cec232da1f03e277113bcb4e466c7a5c`（1248 字符）
- 旧报告：`/Users/chouchou/开发/JiaoDuiAgent/output/拆题结果/第 1 讲初识原电池/单元9/_校对报告.md`
  - sha256 `834f2a62e5844a860f897ad8b9a289a835e2dd7106d486f538a0e6b78d329c4d`（4386 字符）
  - 镜像：`/Users/chouchou/开发/JiaoDuiAgent/output/中间产物/第 1 讲初识原电池/单元9/_校对报告.md`


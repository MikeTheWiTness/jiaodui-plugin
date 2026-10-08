# ADR 0005：量纲校验的声明形态与多解判定

- 状态：已采纳
- 相关：[PRD](PRD.html) §5.4 D13、[REMEDIATION](REMEDIATION.md) R-E02…R-E08、[ADR 0004](0004-gate-single-implementation.md)

## 背景

物理里同一个字母经常表示不同物理量甚至单位：`m` 质量／米，`T` 周期／特斯拉，`L` 长度／升，`N` 力／匝数。量纲校验要能在这类歧义下给出**可信**结论。

旧实现有三个问题：

1. **语义是「存在性」**：枚举到首个自洽组合即 `break`，返回单一 `matched_combination`。于是 `x = y` 且 `x`、`y` 都声明为 `[meter, second]` 时，返回 `{x: meter, y: meter}` 与 `consistent: true`——而 `(second, second)` 同样自洽，工具却像给出了唯一结论。
2. **候选列表只在 `check_consistency` 里枚举**：`get_dimensions` / `convert` 直接取 `candidate[0]`，实测 `["meter","second"]` 换算成 km 会静默按 meter 得 `0.001`。
3. **物理量名缺失**：只能声明单位，题目自定义量（「定义 X 为单位时间内通过的电荷量」）没有留痕位置。

一条必须写进决策记录的实测事实：**单位值那一侧是 sympy 单位命名空间，12 个单字母是活单位名**——`L`→liter³、`T`→tesla、`N`/`J`/`A`/`C`/`F`/`H`/`V`/`W`/`K`/`S`/`R`/`G` 全是单位。因此**量纲串绝不能直接交给单位解析器**，否则 `L` 会被静默读成体积。

## 决策

### 1. 声明取值三形态

| 形态 | 定位 | 量纲来源 |
| --- | --- | --- |
| `"kilogram"` / `"meter/second**2"` | 通用兜底，**覆盖全部情况含题目自定义量** | sympy 单位 |
| `"dim:M*L*T**-2"` | 逃生口（无合适单位时） | M/L/T/I/Θ/N/J 专用白名单解析，**不走 sympy 单位命名空间** |
| `{"quantity": "质量", "unit": "kilogram"}` | 常用量的推荐写法 | 单位；名字查表做交叉校验 |

### 2. 量纲真值只来自单位或 `dim:`，绝不来自名字

`quantity` **可选**，只承担两件事：迫使 agent 做出「这个字母在这题里是什么」的判断（留痕），以及在表命中时做交叉校验。**只给名字不给单位/量纲 → 直接拒绝**，工具绝不按名字猜量纲。这样表不全永远不会阻塞任何一道题，题目自定义量按定义写成单位表达式即可。

### 3. 表是交叉校验与可读性的来源，不是准入门槛

- 名字命中学科配置的 `quantities` 表 → 名字量纲必须与单位量纲一致，否则 error（抓「名字说质量、单位写 meter」）。
- 名字未命中 → `quantity.unknown` **告警放行**，并把未知名字回报出来，按告警统计按需扩表。
- 表放学科配置（Python 侧数据），**不进 skill 正文、不进 agent 上下文**；需要核对时用只读的 `calc quantities --subject X [--search 词]` 惰性查。
- 初版只需 20–40 个高频量。**表长不影响正确性**，因此不一次铺满。

### 4. 真判别：枚举全部组合，返回全部自洽解

- 恰好 1 组自洽 → `consistent: true, ambiguous: false, matched_combination: {...}`（语义不变，向后兼容）。
- ≥2 组自洽 → `consistent: true, ambiguous: true, candidates: [{...}, {...}]`，并说明「存在 N 组自洽赋值，量纲无法区分」。
- 0 组自洽 → `consistent: false`。
- **不再返回单一 `matched_combination` 充当结论**；候选组合上限 128 保持（fail-safe）。

### 5. `get_dimensions` / `convert` 遇到多读数报错要求收敛

不取 `candidate[0]`：要么调用方先收敛到单值，要么返回明确错误让 agent 决定。

## 后果

- 候选列表语义从「存在性判定」变为「判决」：`ambiguous` 是必须被 agent 处理的结果，而不是可以忽略的字段。
- `tests/test_calc_dimensional.py` 里锁定旧语义的断言（`matched_combination`、`tried_combinations`）按新契约重写，并补「两命中」这个此前**无测试**的关键场景。
- `calc` 新增 `--subject`（已由 R-E01 落地）用于取该学科的 `quantities` 表与工具族校验。
- 学科配置新增 `quantities` 字段；两处配置副本必须同步（R-H01 会收敛为单一真源）。

## 被否决的备选

- **只声明量纲串**：实测撞名（`L`=liter³、`T`=tesla），必须另立白名单与前缀语法，不适合作为主形态。
- **名字必填且名字是量纲来源**：题目自定义量会被表卡死，正是用户提出的反例。
- **保持存在性语义，只补文档**：单一 `matched_combination` 会被 agent 当成结论，风险正是本次要消除的。
- **一次铺满大表**：表本身不占上下文，但覆盖不全时会常态化告警；按 `quantity.unknown` 统计增长更稳。

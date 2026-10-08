# 修复计划（Remediation Plan）

- 来源：2026-10 全仓评审（主 agent 实机复现 + 5 个只读子审查：测试质量 / 工作区契约 / Word 交付 / 导入转换 / skill 与插件壳）。
- 与 [IMPLEMENTATION.md](IMPLEMENTATION.md) 的分工：那份是**里程碑顺序**，这份是**缺陷 backlog 与批次**；两者不互相替代。
- 需求口径仍以 [PRD.html](PRD.html) 为准；契约变更一律"先改 PRD/ADR，再改代码"。
- 严重度定义沿用评审：**P0** = 交付正确性已经出错或闸门失效；**P1** = 契约不成立、可复现的错判/漏判或安全边界缺口；**P2** = 健壮性、性能、可维护性、文档一致性。

---

## 0. 已完成（本轮，留档）

| ID | 问题 | 落点 |
| --- | --- | --- |
| R-A01 | 闸门两套定义：缺图报告被 `parse-report` / `build-report` / `build-docx` 放行 | 四条命令统一走 `verify_unit`（verify.py / report.py / workflow.py / docx_report.py） |
| R-A02 | 图片子闸门双向不成立（代码块误判为引用、白底图不校验、`--source` 与图片检查不同源） | inspect_images.py：等长屏蔽代码跨度 + 白底图独立校验 + `source_path` 同源 |
| R-A03 | 契约文档未含图片项 | PRD §5.2 / README / AGENTS.md / ADR 0002 / skill 两份同步 |
| R-E01 | `tools` 白名单无任何消费点 | 工具族校验（读取即拒未知族）+ `calc --subject`（core 层 `require_subject_tool`） |
| R-D01 | 单元集变更无处可走（改边界后材料被钉死） | `split` / `slice --replace-units`：陈旧单元归档到 `units/<材料名>/.superseded/<run_id>/`，只移动不删除，写进轮次 action；mismatch 错误带恢复提示 |
| 附带 | 4 个红测试转绿；`failure-modes` 中 `integrity.no-source` 由 warning 更正为 error；2 处夹具改用真实 PNG / 合法工具族 | — |

### 批次 1 完成（issue #1 已关闭）

| ID | 问题 | 落点 |
| --- | --- | --- |
| R-B01 | 兜底用裸子串计数 + 逐单元缺失可负 + 全卷求和 → 可虚增/漏计/抵消成假通过 | 兜底文案带编号 `（标记 N 修改意见：…）`（`改为` 为空也要输出）；审计按编号去重；逐单元不得负账，负账计入 `over_count` 并让 `ok=false` |
| R-B02 | 单元与段落按 Heading1 下标对齐 → 正文含一级标题时 per-unit 锚点整体错位 | `_split_unit_sections` 改为按「标题文本 = 单元名」切分；正文自带标题留在本单元内 |
| R-B03 | 门禁剥前置参考、渲染保留 → 同一标记两侧上下文不同 | 抽出 `_audit_body`，渲染与标记计数全部走 `strip_reference_preamble`，与 verify 同源 |
| R-B04 | 契约写「不生成批注」，交付实际「整单元消失」 | 明确为交付路径整单元排除；渲染分支只服务 legacy 直调入口，契约文档与测试同步 |
| R-B08 | 公式降级与图片未嵌入都静默 | 新增 `comment_formula_fallback_count`（计数+告警，可选依赖允许降级）与 `image_missing_count`（缺图不通过交付） |

批次 1 回归基线：双命令 **815 passed**；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`、`over_count=0`、独立复核 28 条批注。

历史基线（本轮评审修复）：双命令 **807 passed**；冻结语料 5/5 通过且 `28 = 28 锚点 + 0 兜底`。

### 批次 2 完成（issue #3 已关闭）

设计见 [ADR 0005](adr/0005-dimensional-declaration-and-ambiguity.md)。

| ID | 问题 | 落点 |
| --- | --- | --- |
| R-E02 | 只能声明单位，题目自定义量无留痕位 | 三种形态：单位表达式 / `"dim:M*L/T**2"`（只允许 M/L/T/I/Θ/N/J，**不走 sympy 单位命名空间**，实测 `L`=liter³、`T`=tesla）/ `{"quantity": 名, "unit": 单位}`；只给名字不给单位直接拒绝 |
| R-E03 | 无物理量表，无法交叉校验 | 学科配置新增 `quantities`（高中物理 58 条），两处副本同步；schema 校验为字符串映射 |
| R-E04 | 表若进上下文会挤占预算 | 新增只读命令 `jiaodui quantities --subject X [--search 词]`；表不进 skill 正文 |
| R-E05 | 「任一通过即通过」：命中即停并返回单一 `matched_combination` | 枚举**全部**组合、返回**所有**自洽解；≥2 组 → `ambiguous: true` + `candidates`，多解时不再给单一结论 |
| R-E06 | `get_dimensions`/`convert` 静默取 `candidate[0]` | 多读数直接报错要求收敛；`convert` 另拒绝 `dim:`（无标度不可换算） |
| R-E07 | 名字与单位矛盾无法提示 | 命中表则量纲必须一致（error）；未命中 → `quantity_unknown` 告警放行 |
| R-E08 | 旧语义被测试锁定 | 模块 docstring 与 9 条新测试改写；skill 两份（含 `高中物理.md`、`subject-matrix.md`）同步 |
| 附带 | `get_dimensions` 拿 str 与 Symbol 集合比较（恒为真）→ `x = x` / `F = F + m*a` 漏算整体量纲 | 改用字符串符号集合比较，并加回归测试 |

批次 2 回归基线：双命令 **824 passed**；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`、独立复核 28 条批注。

### 批次 3a 完成（issue #5 已关闭）

| ID | 问题 | 落点 |
| --- | --- | --- |
| R-C01 | `_IMG_RE` 的 `(.*?)` 在首个 `)` 截断：路径含括号时图片既没复制、宿主机绝对路径还留在 `_raw.md`，同一输入因工作区位置不同产出不同字节 | 新增 `image_destination`（支持 `<...>` 包裹与引号标题，**不按空白切分**）+ 允许一层括号的目标正则；`workflow` 的 md 源图片复制同样走该解析 |
| R-C02 | 同名不同图互相覆盖：两处都指向同一文件，落盘是后者，却报 `copied=2, missing=0` | **本次转换内**同名冲突按内容哈希加后缀各自保留；跨轮同名仍以源为准覆盖（重转语义不变） |
| 附带 | `_IMG_RE` 同时排除了 `(`（`[^)]` 允许左括号，贪婪匹配吃掉括号组导致可选组不触发） | 改为 `[^()\n]`，并在测试里逐形态锁定 |

批次 3a 回归基线：双命令 **828 passed**；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 批次 3b 完成（issue #6 已关闭）

| ID | 问题 | 落点 |
| --- | --- | --- |
| R-C04 | pandoc 三处调用无超时；`text=True` 未固定编码；只看 `returncode` 不校验产物（exit 0 不产文件 → 下游裸 `FileNotFoundError`） | 统一 `_run_pandoc`（超时 120s + `encoding="utf-8", errors="replace"`）；`convert_with_pandoc` / `pandoc_to_docx` / `docx_report` 三处均校验产物存在；超时/异常分支结构化返回 |
| R-C03 | idml 畸形输入抛裸异常（缺 designmap → KeyError、非 XML → ParseError、深嵌套 → RecursionError）；261KB zip 炸弹实测峰值 RSS 1GB | 新增 `_idml_read_xml`（类型化 `BusinessError code=invalid-source`）+ 单成员 32MB/总量 128MB/成员数 8192 上限；`_iter_all` 与 `_iter_with_parent_transform` 改为显式栈前序遍历 |
| R-C08 一半 | `extract_idml_to_markdown(idml, "only_name.md")` 崩在 `os.makedirs('')`；写盘无边界校验 | 输出路径走 `ensure_inside` + `parent.mkdir` |

批次 3b 回归基线：双命令 **835 passed**（+7 测试）；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 批次 3c 完成（issue #7 已关闭）

| ID | 问题 | 落点 |
| --- | --- | --- |
| R-C05 | `.doc` 被列为支持却固定 `-f docx`，必然失败（实测 EnvError） | 核心层与材料入口都明确拒绝并提示另存为 `.docx`（材料入口在创建目录前拒绝，不留空材料） |
| R-C07 | 学科配置坏正则未校验就拼进 `clean_intent_markers` → `re.error` 崩掉整条讲义清理链 | 配置正则逐条 `re.compile` 校验并降级告警（与 `config.get_lecture_patterns` 同口径）；拼接处再加兜底 |
| R-C08 | `convert_to_raw(base_name="../逃逸")` 写到 out_dir 之外 | 公开 API 层用 `safe_name` 消毒 base；`extract_idml_to_markdown` 输出已过 `ensure_inside` |
| R-C09 | 重转不清理 `images/media`，旧图留在材料目录并被登记进资源摘要 | `_organize_images` 结束时按本次引用清单清理未再引用的旧图，并计入 warnings |
| R-C10 | md 里源目录之外的引用（绝对路径 / `../`）可把宿主机任意可读文件吸进材料 | `_organize_images` 新增「必须在允许的源目录内」规则（docx 的 pandoc 媒体目录本身就是 search_dir，不受影响）；workflow 的 md 源复制同样限制 |
| R-C06 | 四处 O(n²)：`clean_intent_markers`（惰性回溯）、数学占位符逐块 `replace`、`_inject_format_markers`（先物化全部匹配）、`_IMG_RE`（未闭合 `![`） | ① 改为两次线性扫描 + 区间合并（语义等价）；② 单遍正则回填；③ 改惰性遍历、命中即 break；④ 无 `](` 时跳过正则（pipeline 与 md 源复制两处） |

实测（同一台机，改前 → 改后）：`clean_intent_markers` 4000 项 **276ms → 0.4ms**；`comprehensive_clean` 2000 公式 **12.4ms → 0.7ms**；`_inject_format_markers` 去掉全量匹配物化。

批次 3c 回归基线：双命令 **843 passed**（+8 测试）；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 批次 4a 部分完成（issue #9 仍开，余 R-D04 待决策）

| ID | 问题 | 落点 |
| --- | --- | --- |
| R-D05 | `split` / `slice` 先写单元文件、后校验清单：集合不一致时清单已被改成新集合、磁盘还留着旧目录，材料被钉死（连只读命令都失败） | 把集合核对**移到写清单之前**；不一致时撤掉本轮新建的单元目录（那是这次调用自己造的）并抛 `unit-set-mismatch`（带 `--replace-units` 提示）。清单不动 → 材料保持自洽 |
| R-D10 | `mark_navigation_units` 的 `.skip_proofread` `touch` 无写边界校验（当前 CLI 不可达） | 补 `ensure_inside`，避免接回编排时成为唯一未校验的写入口 |
| R-D04 | 集合不一致时只读 `status` 被锁死 | **待决策**：退 0（诊断优先）还是非 0（严格拒绝但输出完整现场） |

批次 4a 回归基线：双命令 **845 passed**（+2 测试）；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 批次 5a 部分完成（issue #12 / #2 各一部分，均仍开）

等 #8/#9/#10 的决策期间，先做不依赖决策的项：

| ID | 问题 | 落点 |
| --- | --- | --- |
| R-B05 | 历史布局没有「磁盘单元 vs 交付单元」核对：少一份报告的卷静默 `ok=true` 退出 | `build_docx` 的期望单元集改为「有清单用清单，无清单用 `scan_unit_dirs`」，缺报告一律进 `excluded_units` 并置 `ok=False` |
| R-F01 | addopts 里 `-m "not e2e and not network and not slow"` 空转（0 deselected），让「默认」看起来比「全量」窄 | 删掉空转表达式，加 `--strict-markers`（写错标记名直接报错）；同步 AGENTS.md 的测试口径说明 |
| R-F03 | `marker.duplicate-num` / `original.not-locatable` / `report.missing` 三个闸门错误码从未被断言 | 各补一条测试（不合格必被拒 + 精确到码） |
| R-F07 | `units.py` 零测试引用：前缀匹配注释声称「保留 `第1题_备份`、拒绝 `试题`」却没人锁 | 新增 `tests/test_units.py` 6 条：正反例、编号解析、排序、二级回退、缺失根 |

批次 5a 回归基线：双命令 **855 passed**（+10 测试）；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 批次 5b 部分完成（issue #13 仍开，余 R-F05；#12 已关闭）

| ID | 问题 | 落点 |
| --- | --- | --- |
| R-F06 | 写死绝对路径：开发者家目录的 node、`/usr/local/bin/pandoc` 兜底、`/tmp` | node 只认 `shutil.which`（找不到则按既有条件跳过，CI 仍强制）；pandoc 统一改用产品自己的 `find_pandoc()`（含 `JIAODUI_PANDOC` 覆盖）；`/tmp` 改 `tmp_path` |
| R-F08 | 恒真断言：`callable(extract_comments_to_md)`、`hasattr(result, …)`、`len(units) >= 3` | `callable` 那条删除并以行为断言替代（源缺失 → False 且不留输出文件）；`hasattr` 改成 `content == "text"`、`(copied, missing) == (0, 0)`；`>= 3` 改成精确的首行与文件名断言 |
| R-F09 | `calc/safety.py` 30+ 条危险模式只有 1 条被覆盖 | 新增 12 条绕过手法参数化（`__import__`、`os.system`、`exec`/`eval`、`__builtins__[`、`__subclasses__`、`chr()` 编码绕过等）+ 4 条良性表达式反向确认不误伤 |
| R-F04 | fixture 用被测解析器反推源文（`_source_from_report` 调 `markers.split_marked_body`），"合格必被接受"无法证伪 | `_source_from_report` 改为**按契约字面独立重建**（按 `### 标记原文`/`### 修改原因` 锚点取段、剥前置参考与装饰、标记还原为原文），不 import 任何 `jiaodui` 解析器；加两条护栏：AST 去 docstring 后断言代码里不出现 `split_marked_body`/`split_sections`/`strip_reference_preamble`/`jiaodui`，以及旗舰/前置参考/无标记/畸形四类样本与人工核对值一致 |
| R-F05 | 同义反复期望值 5 处 | ① `clean_md_text(raw) == comprehensive_clean(raw)`（前者就是后者的包装）→ 改成契约样本 `"a  b\n正文"`；② 文件级 `out == fix_latex_escapes_text(src)`（`_run_fix_file` 内部就调它）→ 改成 `out == "$x_1$"`；③ `test_split` 先用被测算出的 `cleaned` 求 index 再切片 → 先断言 `cleaned` 等于独立样本，再据此取行号；④⑤ `test_cli`/`test_e2e_flows` 的预览行号 → 加"预览输出等于契约样本"断言，清理逻辑一变立刻红 |

批次 5b 回归基线：双命令 **872 passed**（+17 测试）；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 批次 6 完成（issue #15 已关闭；#14 待决策 5）

| ID | 问题 | 落点 |
| --- | --- | --- |
| R-H02 | `syntax.field-count` / `reason.duplicate` 未进契约文档 | 补进 `report-contract.md` 的检查项表（含触发示例） |
| R-H03 | `--material-name` 被写成通用参数 | SKILL.md 标明只在 `convert` / `split` / `slice` 注册 |
| R-H04 | SKILL 速查表漏记 `--out-dir/--base-name/--mathjax/--no-clean/--rerun/--version` | 补全「全局四参 + 各命令额外参数」清单；新增 `tests/test_skill_docs.py`：**文档提到的每个 `--flag` 必须在 CLI 真实注册**（防臆造/改名漂移）+ 曾漏记的参数必须在位 |
| R-H05 | 退出码口径不闭合 | SKILL.md 写明两种非契约退出：中断 **130**、插件壳超时/失败 **-1**，且不是工具判定码 |
| R-H06 | calc 两套命名面 | SKILL.md 列出「可见名 vs 内部名」映射；skill 内示例与 `subject-matrix` 统一改用可见名（`dimension` / `vector` / `circle`），实测三者在 CLI 均生效 |
| R-H07 | 插件壳 DESCRIPTION 内嵌流程策略且与 SKILL.md 已不一致 | DESCRIPTION 只留命令速查 + 一句「以 SKILL.md 为准」，删掉内嵌入口判断 |
| R-H08 | 插件壳 `realpathSync` 对不存在路径抛原始 ENOENT | 新增 `realpathOrThrow`，三处调用统一转成结构化中文错误 |
| R-H09 | `.DS_Store` 随 npm 包分发 | `package.json` 的 `files` 加 `"!**/.DS_Store"` |
| R-H10 | `--work-root` 覆盖注入且无说明 | SKILL.md 写明必须等于宿主注入工作区、必须已存在、只读场景用 `JIAODUI_WORK_ROOT` |
| 附带 | `subject-matrix` 仍把 `.doc` 列为支持（R-C05 已改为拒绝） | 改为 `.docx / .md / .idml` 并注明 `.doc` 需先另存 |
| R-H11 | `_校对失败.md` 无结构校验点 | 新增 `jiaodui/failure_note.py` 的 `validate_failure_note`：可机检三条（首行非空 / 含 verify 输出或「未执行」/ 摘要三词命中两个），code 为 `failure_note.empty` / `no-verify-output` / `no-summary`；经 `status` 的 `failure_note_problems` 字段与 `warnings` 输出（CLI 人类可读路径也打印告警）。**只告警不改判定**：已通过单元不因旧失败记录或格式问题回退 |

新增 `tests/test_skill_docs.py` 四条：文档参数 ⊆ CLI 参数、曾漏记参数必须在位、**两份 skill 副本字节一致**、**两份学科配置副本一致**（后者是 R-H01 的一致性侧，来源归属仍待决策 5）。

批次 6 回归基线：双命令 **883 passed**（+11 测试）；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

> 到此 **decision-free 存量清零**：剩余 7 个 issue（#2 / #4 / #8 / #9 / #10 / #11 / #14）全部需要一个口径决策才能动，见 §3。§3 已按 2026-10 的答复更新（#4 除外的 6 项已定）。

### 决策落地（批次 6b，issue #9 已关闭）

| ID | 决策 | 落点 |
| --- | --- | --- |
| R-D04 | 集合不一致时只读 `status` **退 0**，诊断优先 | `scan_status` 捕获 `unit-set-mismatch` 不再抛出：现场进 `PaperStatus.unit_set_mismatch`（含 extra/missing/scannable/hint）与 `warnings`，并**继续扫描磁盘上的真实单元**；只有"扫了另一个已存在的单元目录"仍按 `paper-path-mismatch` 拒绝。`report-contract.md` 写明读写两侧口径不同 |

回归基线：双命令 **885 passed**；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 决策落地（批次 6c，issue #10 已关闭）

| ID | 决策 | 落点 |
| --- | --- | --- |
| R-D08 + R-D11 | 变体单元名**不合法**；`板块N` 与 `单元N` 同权 | `units.UNIT_DIR_RE` 改为**精确匹配**（`fullmatch`：`第N题` / `板块N` / `单元N`），识别层与清单层共用这一份；`paths` 删掉自己那份正则，改调 `is_unit_dir`；`--adopt-units` 不再把「自己认出的目录」判成 `invalid-manifest`。契约文档写明变体名需人工重命名/移出 |
| R-D06 | `_校对数据.json` 不在交付指纹里：删掉或改动它，单元仍算「已完成」 | `register` 要求数据文件存在并把 `data_sha256` 写进 `unit_records`；`registered` 要求数据文件存在且摘要一致（升级前的旧记录退化为「存在性」）；清单校验接受缺省字段、给了就必须是合法摘要 |
| R-D09 | `build-report --out` / `build-docx --out-dir` 可写工作区内任意自由命名路径 | **有清单时收口到契约目录**：`--out` 必须在 `校对报告/` 内、`--out-dir` 必须在 `校对Word/` 内，越界报 `out-of-contract`（在建目录之前拒绝，不留垃圾目录）；历史布局（无清单）保留 `--out` 作为兼容出口。契约目录内文件名仍可自取 |
| R-D07 | 只读入口无软链边界校验：软链源文 `verify_unit.ok=True`，同一单元 `parse-report` 抛 `outside-workspace` | **按决策保留这一分叉并文档化**：只读入口允许软链越界（不写），写入口一律按 realpath 拒绝。`report-contract.md` §五 写明；测试同时锁定两侧（只读能读、写命令报 `outside-workspace`） |

回归基线：双命令 **892 passed**；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 决策落地（批次 4 完成，issue #8 已关闭）

| ID | 决策 | 落点 |
| --- | --- | --- |
| R-D02 | 「单元源文」两个定义：`paths.find_source_md`（回退任意非 `_` 开头 md）vs `docx_report._read_unit_source`（只认契约名）→ 把 `第1题.md` 改名后 status 报「已完成」而 docx 静默读不到源文、跳过比对 | **统一到 `paths.find_source_md`**：docx 的标记审计改调它（与 status / verify / report / material 同一个定义）。不删回退——决策 1 是"不管非契约文件"，删回退会与它冲突 |
| R-D03 | 单元内文件名白名单无强制点 | **按决策不新增检查**：非契约文件容忍且不参与校验/交付，只把这条口径写进 `report-contract.md` §五；测试锁定"有额外文件仍能登记、仍算已完成" |

回归基线：双命令 **894 passed**；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 决策落地（批次 6d，issue #14 已关闭）

| ID | 决策 | 落点 |
| --- | --- | --- |
| R-H01 | 学科配置双源：运行时读 `jiaodui/data/subjects/`，而 `config.py` 的默认、文档与测试都指向 `config/subjects/` | **单一来源**：`config.resolve_config_dir()` 成为唯一解析入口（包内 `data/`，`JIAODUI_CONFIG_DIR` 可覆盖），`workflow.resolve_config_dir` 改为复用它；`subject_config_path` 默认解析到运行时而非镜像；`config/subjects/` 明确为**人工可读镜像**并在文档写明"改包内那份再 cp 同步"；原先断言镜像路径的测试改为断言运行时路径 |

回归基线：双命令 **894 passed**；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 决策落地（批次 5c，issue #11 已关闭）

| ID | 决策 | 落点 |
| --- | --- | --- |
| R-F02 | 真实语料双向契约在 CI 中整体 skip（`test_legacy_corpus.py` 默认指向仓库外旧仓目录） | **入仓固定子集**（决策 6）：CI 的语料防线是随仓的 `evaluation/m1`——`tests/test_m1_fixture.py` 已断言 5 个单元过闸门与 28 条批注带原因；本轮补上**交付入口 `build_docx` 的对账**（`标 28 = 锚 28 + 兜底 0`、`missing=0`、`over_count=0`）并独立解压数批注。`test_legacy_corpus.py` 降级为**旧仓外部语料的可选交叉验证**，skip 不再算 CI 缺口（文档写明） |

> 意义：目标里的验收口径（`5/5 通过 + build-docx 输出 28 = 28 锚点 + 0 兜底`）从此是**机器断言**，不再只是跑批时的人工 shell 复现。

回归基线：双命令 **895 passed**；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

### 决策落地（批次 1 收尾，issue #2 已关闭）

| ID | 决策 | 落点 |
| --- | --- | --- |
| R-B06 | 复核失败不失效交付路径上的旧 docx；`_tmp.docx` 固定名 | `build_docx` 生成前把旧交付挪到 `.prev`，**通过复核才 `os.replace` 顶上**；不通过则把本次产物改名 `*.failed.docx`（写入 `failed_out_path`、`out_path=None`）并把旧交付原样放回。交付路径上永远不会出现没通过复核的 Word |
| R-B07 | 渲染侧仍用只认契约名的源文入口，与闸门不一致 | 交付路径（`_read_unit_source`）与「无问题 → 插入单元原文」分支**都走 `paths.find_source_md`**；测试用非契约名源文锁定"闸门通过 ⇒ 渲染也渲染得出来" |
| R-B09 | `CMTEND{N}Z` 链无生产调用方，且无法区分注入占位符与正文字面量 | **按计划 §4 待定**：不改行为，在 `replace_comment_placeholders` 写明已知局限与"接回编排时用带随机前缀的令牌"的修法 |

> R-B06 与既有契约叠加出的一个结果值得记住：**有单元被排除 ⇒ `ok=False` ⇒ 整份产物不算交付**，于是被排除的卷会走 `*.failed.docx` 留痕而不是留在 `校对Word/`。`test_pipeline` 里那条伪造字段用例已按新契约更新（意图不变：伪造字段不得进 Word）。

回归基线：双命令 **898 passed**；冻结语料 5/5 通过、`28 = 28 锚点 + 0 兜底`。

> 过程记录：R-F09 的良性用例我先写成 `execute_code("x = 1 + 1")`，被 `Expecting value: line 1 column 1` 打回——`execute_code` 是低层 runner，要求被测代码自己打印 JSON；良性用例必须走 `run_operation(..., expression=...)`。`abs(-3)` 也被沙箱的白名单拒了（`abs` 不在白名单），换成纯算术。

> 关于 R-D05 的实现边界：集合"变大"不会触发 mismatch（新目录本就是新集合的一部分），只有"变小 / 部分重叠"才会——此时陈旧目录仍在，新建的那几个撤掉即可；清单不动是关键，材料因此不再被钉死。

> 过程中发现：`_idml_read_xml` 用到的 `BusinessError` 未在 `convert.py` 导入，编译能过但错误路径会 NameError——既有测试完全没覆盖错误路径，由本轮新增的 5 条测试兜住。

### 固定输入下的最小补修（本轮复审）

按用户确认的范围：只修标准材料流程的三个缺口，不为任意 Markdown、恶意输入或边缘历史调用建设通用防御体系。图片语法仍不扩展为通用 Markdown 解析；参考式语法明确拒绝，行内图片贯通转换、拆分、闸门和 Word。

| 项目 | 原实现缺口 | 最小修复与回归 |
| --- | --- | --- |
| R-B06 补修 | 先移旧交付、再在正式路径生成；批注注入异常被吞后，正式路径已有半成品，旧交付无法恢复 | 在独立临时文件生成及复核，生成器明确成功且复核通过才原子替换正式交付；未通过的本次产物仍另存为失败产物，不动旧交付，不再使用 `.prev` 恢复流程。测试覆盖首次失败、已有交付后失败、全公式兜底仍不得掩盖生成失败及复核期间旧交付仍可用 |
| R-D05 补修 | 保持清单不变、撤销新目录并不足够：失败前同名旧单元的源文和图片已被覆盖 | 拆分解析完成后通过 `before_write` 核对单元名，再实际写盘；删掉写盘后撤新目录的分支。规则、人工、整篇、边界切片共享接缝；因集合不一致而拒绝后，旧文件字节与完成状态不变。保留既有集合增补、`--replace-units` 归档与 `--adopt-units` 语义 |
| R-E05 补修 | 一个候选的加法项量纲不一致会中断全部枚举，已找到的合法解也被丢弃 | 只隔离预期的量纲不自洽组合，继续枚举并返回其他自洽解；非法声明、不支持表达式及其他执行错误仍报错，单组合错误保持原语义。测试覆盖候选顺序、多解、零解与错误不被吞掉 |

回归测试：[Word 交付](../tests/test_docx_report.py)、[材料拆分](../tests/test_workspace_workflow.py)、[量纲候选](../tests/test_calc_dimensional.py)。三项均先补失败回归测试再实现，新增 **18** 个用例（Word 4、拆分 7、量纲 7）。

验证：`.venv/bin/python -m pytest -q` 与 `.venv/bin/python -m pytest -o addopts='' -q -rs` 双口径均通过，**916 passed，4 subtests passed**（补修前 898 passed）。冻结语料的机器断言保持：5/5 单元过闸门、`28 = 28 锚点 + 0 兜底`、`missing=0`、`over_count=0`，独立解压确认 28 条批注。`git diff --check` 通过。

### 最小补修（五项交叉审查）

| 问题 | 最小修复 | 回归 |
| --- | --- | --- |
| 参考式图片闸门放行但 Word 丢图 | 支持范围明确为行内 `![alt](path)`；参考式语法由闸门拒绝；两份报告契约与 ADR 0004 同步 | `test_reference_style_is_rejected_as_unsupported_syntax` |
| 括号路径转换成功、拆分误拒 | 图片复制、闸门与 Word 重写共用转换器现有的一层括号路径扫描；不引入通用 Markdown 解析器 | `test_parentheses_in_material_image_path_survive_split_and_verify` |
| 非单元备份报告导致 Word 排除单元 | `_collect_reports` 复用 `units.is_unit_dir`，仅收集合约单元 | `test_non_unit_backup_report_is_ignored` |
| 代码里的图片示例被 Word 误计缺图 | 拆分复制与 Word 重写复用行内图片扫描器，扫描前统一屏蔽行内及围栏代码 | `test_inline_code_image_example_does_not_block_delivery` |
| `quantity` 交叉校验仅在 check-consistency 生效 | 同一校验片段注入 check-consistency、get-dimensions、convert 三个操作 | `test_quantity_cross_check_is_shared_by_all_operations`、`test_quantity_cross_check_accepts_matching_declaration_across_operations` |

以上修复限定于标准流水线支持范围：不支持参考式图片并明确拒绝；行内图片不扩展为通用 Markdown 语法解析。

五项补修阶段双口径验证：**921 passed，4 subtests passed**（修复前 **916 passed**）；`git diff --check` 通过。后续新增讲义破图占位过滤后，真实讲义回归出现 **1 failed、921 passed、4 subtests passed**，不能沿用本阶段的全绿结论。

### 讲义占位图清理与固定语料同步（2026-10-08）

- 删除已确认的占位图时，一并删除紧随其后的 Pandoc 属性块（含换行形式）；正常图片和默认导入仍保留属性，不扩展通用 Markdown 支持。
- 先用单行、换行属性的精确输出断言复现失败，再修复实现；无属性及正常图片作为接受方向回归。
- M1 raw、单元1源文及报告同步移除占位引用和属性；原始 DOCX、其余正文、28 条修改标记与原因保持不变，历史 PNG 留作核对。
- 真实 DOCX 端到端回归按五张有效图验收，逐单元核对固定源文，完成交付登记后独立检查 Word 的 28 条批注及正文无尺寸属性残留。

验证：定向回归 **7 passed**；默认与 CI 全量双口径均通过，**924 passed，4 subtests passed**。
`git diff --check` 通过；原始 DOCX SHA-256 仍为
`59c36b3781287e43438a8130f1bac7ac60b2f4bcf4972413212771f01f573fc2`。
---

## 1. 批次划分

| 批次 | 主题 | 完成判据 | 依赖 |
| --- | --- | --- | --- |
| **1** | Word 交付可信（B） | 兜底计数按标记编号记账、逐单元缺失不可为负；Word 单元归属不再按段落下标；失败复核不留下可误用的交付文件 | 无 |
| **2** | 学科工具（E，已批准设计） | 声明形态与真判别落地；`ambiguous` 可复现；`test_calc_dimensional` 按新契约重写 | 无 |
| **3** | 导入转换正确性（C 的 P0/P1） | 图片引用不再因路径形态断裂；同名图不再静默替换；idml 畸形输入走结构化错误；pandoc 有超时与产物校验 | 无 |
| **4** | 工作区与命名纪律（D） | 「单元源文」定义唯一；集合不一致时只读命令仍可用；无半成品窗口；`_校对数据.json` 进校验链 | 批次 1（下游口径统一后） |
| **5** | 测试与 CI 可信度（F） | 真实语料双向契约在 CI 中真的执行；旧语义测试重写为独立样本；无写死绝对路径 | 批次 1–4 同步补测 |
| **6** | 壳与文档单一源（G/H + C 余项） | 学科配置单一真源；skill/CLI 参数与退出码口径闭合；插件壳不复制流程策略 | 批次 4 |

每个批次内部按「红→绿」推进：先加能失败的测试（或复用已冻结的真实语料），再改实现，最后跑双命令全量 + 冻结语料复现。**不允许把"闸门放宽"当作修复手段。**

---

## 2. 明细

### 批次 1：Word 交付可信

| ID | 严重度 | 症状与证据 | 修复 | 规模 |
| --- | --- | --- | --- | --- |
| R-B01 | **P0** | 公式兜底用裸子串计数（[docx_report.py:220](../jiaodui/docx_report.py#L220) `sec.count("（修改意见：")`），逐单元 `missing = markers - anchors - fallbacks` 无下限（:351），全卷再求和（:366）。实测：源文自带该串 → `fallbacks` 虚增、`missing=-1`；"改为"为空不写兜底 → 漏计误拒；一增一减可**抵消成 ok** | 兜底按被跳过的 marker 编号记账（来自 `audit_markers` 的 verdict，而不是数正文子串）；每条标记要求「锚点 XOR 可见兜底」恰好其一；逐单元 `missing` 不得为负 | M |
| R-B02 | P1 | 单元与段落按位置下标对齐（[docx_report.py:210](../jiaodui/docx_report.py#L210) `sections[idx]`），`_split_unit_sections` 把任意 Heading1 当单元边界。实测源文含 `# 一、选择题` 时 sections≠included，第 2 题真实锚点被算成缺失、`ok=false` | 改为按单元标题文本匹配，或让生成端显式记录每个单元的锚点集合 | M |
| R-B03 | P1 | 门禁与渲染各跑一遍 `audit_markers`，但传入正文不同：verify 先 `strip_reference_preamble`（[verify.py:456](../jiaodui/verify.py#L456)），docx 渲染清洗保留前置参考/⚠️ 行（子审查定位 docx_report.py:486-495）。同一标记可得到不同 verdict | 把「报告 → 审计正文」抽成单一函数，门禁与渲染共用 | S |
| R-B04 | P1 | `RESTORE_NEW` / `NOOP` / `EMPTY_ORIG` 在交付路径不可达：verify 把它们判为 error，docx 随即整单元排除，于是"按改为渲染""不生成批注"两段代码永不执行；只有直调 `generate_combined_docx` 的测试走到 | 明确取舍并写进契约：要么"整单元排除"，要么按分支渲染；两处判定必须同源，并用交付路径的测试锁定 | M |
| R-B05 | P2 | legacy 路径没有单元集合完整性检查（docx_report.py:291-298 整段在 `data is not None` 内），缺一份报告可 `ok=true` 退出 | legacy 也核对「磁盘单元 vs 交付单元」并写占位 | S |
| R-B06 | P2 | 复核失败不失效交付路径上的旧 docx；`_tmp.docx` 固定名，异常路径残留 | 失败时把未通过复核的产物移到临时/失败位置或在结果中显式标注；`_tmp.docx` 用 `mkstemp` | S |
| R-B07 | P2 | 渲染侧仍用 `_read_unit_source`（只认 `<单元名>.md`，[docx_report.py:496](../jiaodui/docx_report.py#L496)），与闸门已改用的 `find_source_md` 回退不一致；源文名非契约名时闸门通过但渲染定位不到源文 | 渲染与门禁统一取源文入口 | S |
| R-B08 | 观察 | 批注内公式渲染失败完全静默（无降级计数）；正文图片丢失静默（`except OSError: pass`），均不进 `warnings`/`ok` | 加"降级/丢失"计数字段并进复核输出 | S |
| R-B09 | 观察 | `CMTEND{N}Z` 链无生产调用方；`replace_comment_placeholders` 无法区分注入占位符与正文字面量 | 接回编排时一并修（当前无调用方，低优先） | S |

### 批次 2：学科工具

| ID | 严重度 | 症状与证据 | 修复 | 规模 |
| --- | --- | --- | --- | --- |
| R-E02 | P1 | 现在只能声明单位；题目自定义量需按定义翻译，缺少"物理量名"这一层留痕 | 取值三形态：单位表达式（通用兜底，覆盖 100%）/ `"dim:M*L*T**-2"`（逃生口，M/L/T/I/Θ/N/J 白名单，**不走 sympy 单位命名空间**）/ `{"quantity": 名, "unit": 单位}`（推荐）。`quantity` 可选；只给名字不给单位 → 拒绝，绝不按名字猜量纲 | M |
| R-E03 | P1 | 无物理量表，无法做名字↔量纲交叉校验 | `quantities` 进学科配置（20–40 条起始，按告警增长）；两处配置同步 | S |
| R-E04 | P2 | 表一旦需要核对就会挤占上下文 | 新增只读 `calc quantities --subject X [--search 关键词]`，按需查、输出只含命中项；**表不进 skill 正文** | S |
| R-E05 | **P0** | "任一通过即通过"：枚举到首个自洽组合即 `break`（[templates.py:517](../jiaodui/calc/templates.py#L517)），返回单一 `matched_combination`。实测 `x=y` 两个符号都给 `[meter,second]` → 返回 `{x:meter,y:meter}` 且 `consistent:true` | 枚举全部组合、收集全部自洽解；≥2 → `ambiguous: true` + `consistent_readings: [...]`；不再返回单一 `matched_combination` 当结论 | M |
| R-E06 | P1 | `get_dimensions` / `convert` 直接取 `candidate[0]`（templates.py:546、:567）。实测 `["meter","second"]` → `convert to km` 得 `0.001`，静默按 meter 换算 | 多读数 → 报错要求收敛，不取第一个 | S |
| R-E07 | P2 | 名字与单位自相矛盾（名字说质量、单位写 meter）无法提示 | 名字命中表 → 量纲必须与单位一致（error）；未命中 → `quantity.unknown` warning 放行 | S |
| R-E08 | P1 | `test_calc_dimensional.py` 锁定了旧语义（`matched_combination`、`tried_combinations`） | 按新契约重写断言，并补 `ambiguous` 用例（"两命中"当前**无测试**）、自定义量用例、`dim:` 用例；skill 两份同步 | M |
| R-E09 | 待定 | `tools` 是工具族（`["calc"]`），不是 operation 列表 | 若需 op 级白名单，需新增配置字段并决定与 `subject-matrix.md` 谁是真源 | 需决策 |

### 批次 3：导入转换正确性

| ID | 严重度 | 症状与证据 | 修复 | 规模 |
| --- | --- | --- | --- | --- |
| R-C01 | **P0** | 工作区路径含空格/括号时：pandoc 写出绝对路径 → `_IMG_RE`（[convert.py:1203](../jiaodui/convert.py#L1203)）的 `(.*?)` 在首个 `)` 截断 → 图片既没复制、原引用（宿主机绝对路径）留在产物里，且同一 docx 因路径不同产出不同字节 | 换成能处理 `<...>` 包裹与括号的解析；图片按**内容哈希**命名而非 basename；产物内不写宿主机绝对路径（子审查已实测三种触发） | M |
| R-C02 | P1 | 同名不同图互相覆盖：`![一](img/pic.png)` + `![二](other/pic.png)` → 两处都指向同一文件，落盘是后者，却返回 `copied=2, missing=0` | 目标名冲突时按内容区分或直接拒绝 | S |
| R-C03 | P1 | idml 畸形输入抛裸异常：缺 `designmap.xml` → KeyError、Story 非 XML → ParseError、深嵌套 → RecursionError；261KB zip 炸弹实测峰值 1GB | 照 `inspect_source.py` 的模式：类型化 `BusinessError` + 解压大小/条目上限 + 非递归遍历 | M |
| R-C04 | P1 | `convert_to_raw` / `pandoc_to_docx` / build-docx 的 pandoc 调用无超时，`text=True` 未固定 encoding，且只看 returncode | 统一封装：超时、`encoding="utf-8"`、产物存在/非空校验（同仓 `checkenv.py` 已对同一二进制设 10s） | S |
| R-C05 | P2 | `.doc` 被列为支持格式却固定 `-f docx`，必然失败（实测 EnvError） | 明确拒绝并提示先另存为 `.docx`，或真的走转换 | S |
| R-C06 | P2 | 四处 O(n²)：`clean_intent_markers`（56KB 已 1.4s）、数学占位符逐块还原、`_inject_format_markers`、`_IMG_RE` | 改单遍扫描/索引替换 | M |
| R-C07 | P2 | 学科配置正则未校验就拼接（`"例(1"` → `re.error` 崩链），而 `config.get_lecture_patterns` 同输入已优雅降级 | 统一在拼接前 `re.compile` 校验并降级告警 | S |
| R-C08 | P2 | `convert_to_raw(base_name="../逃逸")` 写到 out_dir 之外（工作区内）；`extract_idml_to_markdown(p, "only_name.md")` 崩在 `os.makedirs("")` | 公开 API 层消毒 base_name；补目录判断与写边界 | S |
| R-C09 | P2 | 重转不清理 `images/media`，旧图留在材料目录并被登记 | 重转时按清单清理或在资源记录中显式剔除 | S |
| R-C10 | 观察 | md 源里绝对路径引用（如 `/etc/passwd`）被复制进材料 `source/` | 只允许源目录内相对引用，越界拒绝 | S |

### 批次 4：工作区与命名纪律

| ID | 严重度 | 症状与证据 | 修复 | 规模 |
| --- | --- | --- | --- | --- |
| R-D02 | P1 | 「单元源文」两个定义：[paths.py:34](../jiaodui/paths.py#L34) 回退任意非 `_` 开头 md（status/report/verify/material 全走它），而 `docx_report._read_unit_source` 只认契约名。实测把 `第1题.md` 改名 `草稿副本.md` 后 `status` 报"已完成"、`_校对记录.json` 的输入摘要锁的是该自由命名文件 | 二选一：删掉无条件回退，或给它一个显式 layout 开关，并让所有入口同源 | M |
| R-D03 | P1 | 单元内文件名白名单（PRD 380 / AGENTS 契约）无强制点：放入 `第1题_尝试2.md` + `随手笔记.txt` 后 parse-report 照常登记、status 报"已完成" | 在 `parse-report` / `status` 报告非契约文件（warn 或 error，需决策）；至少让违规可见 | S |
| R-D04 | P1 | 集合不一致时连只读命令一起失败：改边界后 `status` 也 exit 6，现场不可见。`check_units` 其实已算好逐单元摘要放进 `details.scannable` | `status` 输出 `units` + 集合不一致 warning（退出码 0）；写命令继续拒绝 | S |
| R-D05 | P1 | `split` / `slice` 先写单元文件、后校验清单，失败留半成品。`--replace-units` 已给出恢复路径，但不带参数时窗口仍在 | 规则拆分拆成 plan→verify→write；或对本轮新建目录回滚 | M |
| R-D06 | P2 | `_校对数据.json` 不在任何校验链：篡改或删除后 status 仍"已完成"、build-report 照常拼入 | 纳入状态与下游复核（存在性 + 与报告一致） | S |
| R-D07 | P2 | 只读入口无软链边界校验：源文软链到工作区外时 `verify_unit.ok=True`，而同单元 `parse-report` 抛 `outside-workspace` | 只读入口与写入口使用同一 realpath 判定（或明确文档化只读可越界） | S |
| R-D08 | P2 | `split --adopt-units` 接纳不了 units 层自称合法的变体名（`第1题_备份` 前缀匹配 vs 清单 fullmatch → `invalid-manifest`） | 单元名正则合并为一处常量，变体名口径二选一（需决策） | S |
| R-D09 | P2 | `build-report --out` / `build-docx --out-dir` 可写工作区内任意自由命名路径且不入清单 | 收口到契约目录，或写入即登记 | S |
| R-D10 | P2 | `mark_navigation_units` 的 `.skip_proofread` `touch` 无 `ensure_inside`（当前 CLI 不可达） | 补边界校验 | S |
| R-D11 | 观察 | `板块N` 代码全面支持但未入白名单文档 | 口径统一并补文档 | S |

### 批次 5：测试与 CI 可信度

| ID | 严重度 | 症状与证据 | 修复 | 规模 |
| --- | --- | --- | --- | --- |
| R-F01 | P1 | 默认 `-m "not e2e and not network and not slow"` 过滤掉 **0** 个用例（tests/ 从未使用这些 marker），且无 `--strict-markers` | 给真实重测试打标，或删掉空转的 `-m`；加 `--strict-markers` | S |
| R-F02 | P1 | 真实语料双向契约在 CI 中整体 skip（[test_legacy_corpus.py:25](../tests/test_legacy_corpus.py#L25) 默认指向仓库外 `../JiaoDuiAgent/output`） | 把固定子集入仓（如 `evaluation/`），或让 CI 生成可得的等价语料并单独标注预期 | M |
| R-F03 | P1 | 三个真实 error code 无断言：`marker.duplicate-num`、`original.not-locatable`、`report.missing` | 补"不合格必被拒"用例 | S |
| R-F04 | P1 | 用被测解析器反推源文构造 fixture（[test_docx_report.py:1280](../tests/test_docx_report.py#L1280)），使"合格必被接受"无法证伪 | 换成独立来源的固定样本 | M |
| R-F05 | P2 | 同义反复期望值：`test_clean_md.py:506`、`test_fix_latex_escapes.py:470`（断言别名包装，恒真）、`test_split.py:382`（用同一清理逻辑算行号）、`test_cli.py:161`、`test_e2e_flows.py:126` | 期望值改来自规格/已知样本 | M |
| R-F06 | P2 | 写死绝对路径：`test_dsh_plugin_tool_behavior.py:10`（开发者家目录 node）、`/usr/local/bin/pandoc` 兜底、`/tmp` 写死 | 改用 `shutil.which` + `tmp_path` + 明确的 skip 条件 | S |
| R-F07 | P2 | `jiaodui/units.py` **零测试引用**（其正反例注释无直测） | 补 `第1题_备份` / `试题` 这类接受与拒绝用例 | S |
| R-F08 | P2 | 存在性/宽松断言（`hasattr`、`callable`、`>= 3`） | 换成行为断言 | S |
| R-F09 | 观察 | `calc/safety.py` 30+ 条危险模式只覆盖 1 条 | 参数化覆盖绕过手法 | S |

### 批次 6：壳与文档单一源

| ID | 严重度 | 症状与证据 | 修复 | 规模 |
| --- | --- | --- | --- | --- |
| R-H01 | P1 | 学科配置双源：运行时只读 `jiaodui/data/subjects/`（[config.py:42](../jiaodui/config.py#L42)），文档与测试指向 `config/subjects/`（[test_pipeline.py:26](../tests/test_pipeline.py#L26)）；两份目前字节相同但无一致性测试 | 单一真源（需决策选哪边）：删其一，或让 `resolve_config_dir` 优先仓内配置并加一致性测试 | S |
| R-H02 | P2 | `syntax.field-count`、`reason.duplicate` 未进契约文档，而 skill 要求"按结构化原因自修" | 补进 `report-contract.md` 的表 | S |
| R-H03 | P2 | `--material-name` 被写成通用参数（实际只在 convert/split/slice 注册） | 修正 skill 措辞 | S |
| R-H04 | P2 | SKILL.md 速查表漏记 `--out-dir/--base-name/--mathjax/--no-clean/--rerun/--version` 等实参 | 补齐（可用脚本从 `--help` 生成校验） | S |
| R-H05 | P2 | 退出码口径不闭合：SKILL 声称 0..7，`KeyboardInterrupt` 返回 130，插件壳超时返回 -1 | 文档写明 130/-1，或统一归入既有码 | S |
| R-H06 | P2 | calc 两套命名面：CLI 可见名（`dimension/vector/circle`）与 skill 内部名（`dimensional/vector_ops/...`） | 统一文档口径（建议双写别名并在 skill 标注） | S |
| R-H07 | P2 | 插件壳 DESCRIPTION 内嵌流程策略，与 SKILL.md 双写且已不一致 | DESCRIPTION 只留一句指向 SKILL.md | S |
| R-H08 | P2 | `realpathSync` 对不存在路径抛原始 ENOENT，绕过相邻中文校验 | 先判存在再报结构化错误 | S |
| R-H09 | 观察 | `.DS_Store` 随 npm 包分发 | 打包时排除 | S |
| R-H10 | 观察 | `--work-root` 可覆盖宿主注入且不校验存在性；文档未说明 | 文档写明，或加"与注入不一致时告警" | S |
| R-H11 | 观察 | `_校对失败.md` 与 `.skip_proofread` 在 Python 侧无生产者，格式无校验点 | 保持"交 agent 写"，但可加结构检查（首行 + 含 verify 输出） | S |

---

## 3. 需要你决策的点

| # | 决策 | 结果（2026-10 定） |
| --- | --- | --- |
| 1 | 白名单违规：warn 还是 error？ | **不管**：不新增白名单检查，非契约文件容忍并忽略。「单元内只允许…」保持为纪律/文档口径，不做闸门（R-D03 记为"不做检查"） |
| 2 | 变体单元名（`第1题_备份`）算不算合法？ | **不合法**：只接受 `第N题` / `单元N` / `板块N` **精确名**；识别层与清单层统一为精确匹配（R-D08 / R-D11） |
| 3 | `.doc` 拒绝还是真支持？ | **拒绝**并提示另存为 `.docx`（R-C05 已按此实现） |
| 4 | 要不要 op 级白名单（如"物理不许用 geometry"）？ | **待决**：保持族级白名单现状（`tools: ["calc"]` / `classics`），R-E09 不动 |
| 5 | 学科配置单一源 | `jiaodui/data/subjects/` 为**唯一运行时来源**；`config/subjects/` 降为镜像 + 一致性测试（R-H01） |
| 6 | 真实语料如何进 CI | **把固定子集入仓**（复用 `evaluation/`），逐份标注预期（R-F02） |
| 7 | 集合不一致时只读 `status` 退码 | **退 0**：把不一致当 warning 打出来，诊断优先（R-D04；R-D05 之后材料不再被钉死） |

另有两条同族口径一并定下：**失败重转的旧产物改名保留**（`*.failed.docx`，旧交付不动，R-B06）；**`--out`/`--out-dir` 收口到契约目录，只读入口允许软链越界但不写**（R-D07 / R-D09）。

---

## 4. 明确不做 / 待定

- **calc 沙箱不做成真隔离**：现行实现是正则 deny-list + 受限 builtins 子进程，实测能挡住常见逃逸，但它**不是安全边界**，把它当边界会误导。计划只做一件事：在文档里写清定位（降低误操作，不防恶意）。
- **TOCTOU（写边界只在写前校验一次）**：收益低、改动面大，暂列待定。
- **`CMTEND` 占位符链**：当前无生产调用方，等编排接回再修（R-B09）。
- **旧仓 `../JiaoDuiAgent`**：保持冻结，只读；R-F02 不通过它来修 CI。

---

## 5. 每批的验收方式

1. 双命令全量：`pytest -q` 与 `pytest -o addopts='' -q -rs`。
2. 冻结语料复现：`evaluation/m1` 5/5 通过，`build-docx` 输出 `28 = 28 锚点 + 0 兜底`，且用 `zipfile` 独立数出 28 条批注。
3. 每个 P0/P1 都要有**能失败的测试**或可复现命令，不允许只靠代码审阅结论。
4. 契约变更（PRD/ADR）先改文档再改代码。
5. 宿主相关项（读图注册、真实派发）只由真机冒烟判定，模拟不替代——这与 F1（preset 能否注册 `read_image`）的验证合并进行。

---

## 6. Issue 索引（GitHub）

里程碑：`Remediation 2026-10`（[milestone #1](https://github.com/MikeTheWiTness/jiaodui-plugin/milestone/1)）。**本文档是内容真源**，issue 只承载状态、验收清单与讨论，不复制证据正文。

| Issue | 批次 | 严重度 | R 项 | 含待决策 |
| --- | --- | --- | --- | --- |
| [#1](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/1) | 1 | P0 | R-B01, R-B02, R-B03, R-B04, R-B08 | — |
| [#2](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/2) | 1 | P2 | R-B05, R-B06, R-B07, R-B09 | — |
| [#3](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/3) | 2 | P0 | R-E02, R-E03, R-E04, R-E05, R-E06, R-E07, R-E08 | — |
| [#4](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/4) | 2 | P2 | R-E09 | 决策 4 |
| [#5](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/5) | 3 | P0 | R-C01, R-C02 | — |
| [#6](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/6) | 3 | P1 | R-C03, R-C04 | — |
| [#7](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/7) | 3 | P2 | R-C05 … R-C10 | 决策 3（R-C05） |
| [#8](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/8) | 4 | P1 | R-D02, R-D03 | 决策 1 |
| [#9](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/9) | 4 | P1 | R-D04, R-D05 | 决策 7 |
| [#10](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/10) | 4 | P2 | R-D06 … R-D11 | 决策 2（R-D08） |
| [#11](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/11) | 5 | P1 | R-F01, R-F02 | 决策 6 |
| [#12](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/12) | 5 | P1 | R-F03, R-F04 | — |
| [#13](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/13) | 5 | P2 | R-F05 … R-F09 | — |
| [#14](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/14) | 6 | P1 | R-H01 | 决策 5 |
| [#15](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/15) | 6 | P2 | R-H02 … R-H11 | — |
| [#16](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/16) | — | P1 | 决策 1–7 汇总入口 | 全部 |

批次 1（[#1](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/1)、[#2](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/2)）与批次 2（[#3](https://github.com/MikeTheWiTness/jiaodui-plugin/issues/3)）**不依赖任何决策**，可直接开工。

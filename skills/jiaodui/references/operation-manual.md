# jiaodui 操作手册（入口按需参考）

本文件承接 `SKILL.md` 的目录参数、写入前核对、命令速查、导入清理顺序与派发细节。**强制项仍以 `SKILL.md` §6 为准**，本文件只做展开，不新增强制项；`SKILL.md` 与本文件冲突时以 `SKILL.md` 为准。

## 一、目录参数约定（不要混用）

- `material_dir` 是材料根目录：`W/校对/<材料名>/`，包含 `source/`、`raw/`、`units/` 与 `_校对记录.json`。
- `paper_dir` 是**单元根目录**：`W/校对/<材料名>/units/<材料名>/`，其直接子目录才是 `单元1` / `第1题` 等。`precheck-split`、`status`、`build-report`、`build-docx` 都传这个目录，**不是 `material_dir`，也不是中间的 `units/` 或某一个单元目录**。
- `unit_dir` 是单个单元目录，例如 `<paper_dir>/单元1/`；`inspect-images`、`verify-report`、`parse-report` 的 `--unit` 传这个目录。
- 拆分后从 `split` / `slice` 的 JSON 返回字段 `unit_dirs` 取各单元目录的**直接父目录**作为 `paper_dir`，并确认这些父目录一致；不要按源文件名猜路径（`--material-name` 可改变材料名）。恢复已有材料时，从材料 `_校对记录.json` 的 `paths.paper` 读取相对路径，以 `material_dir` 为基准解析。

## 二、写入前核对与独立流程测试

- 写入前确定本次实际材料名：默认采用源文件完整文件名去扩展名；若传 `--material-name`，则采用该显式名称。检查路径必须完整匹配本次名称，不能截短名称、沿用示例里的材料名，或把其他名称的 glob 无匹配当成本次目录不存在。检查时回显目标绝对路径；glob 只能发现文件，空目录是否存在还须使用宿主支持的只读目录检查。
- 用户要求「独立测试 / 忽略已有校对内容」时，选择经确认不存在的独立材料名并传 `convert --material-name <本次名称>`；只检查目标是否存在，不读取或复用旧报告、记录与单元。若目标存在则另选名称，禁止通过删除、清空或覆盖旧材料获得干净测试环境。独立材料名仍使用既定布局，不在单元内创建 attempt / 副本文件。
- 转换后以 JSON 返回的 `raw_md` / `images_dir` 为准，拆分后以 `unit_dirs` 为准，并核对都属于本次隔离材料。不得继续使用转换前猜测的路径，也不得复制示例路径直接执行。
- 区分正常告警与错误：退出码 0 且结果成功时，覆盖规范名、忽略已识别占位图、清理未引用图片等告警不自动等同 bug；结合本次隔离要求与资源完整性判断。独立测试出现覆盖告警仍是隔离异常，应停下核查。非零退出码、工具异常、结果失败或确定的契约异常属于错误；用户要求遇错即停时，本轮技术重派、参数修正与报告自修次数均为 0，停止全批次、取消在途任务并留痕，不修复后悄悄继续。

## 三、调用示例

先将 `W` 替换为当前工作区绝对路径，材料名替换为 CLI 实际使用的名称；以下下游命令共用同一个 `paper_dir`，汇总与 Word 生成仍须等单元校验和登记完成：

```bash
W="/绝对路径/工作区"
material_dir="<本次材料根目录绝对路径>"
paper_dir="<从 split / slice 返回的 unit_dirs 提取的共同直接父目录绝对路径>"
jiaodui precheck-split "${paper_dir}"
jiaodui status "${paper_dir}" --json
jiaodui build-report "${paper_dir}" --work-root "${W}" --json
jiaodui build-docx "${paper_dir}" --work-root "${W}" --json
```

## 四、命令速查

```
jiaodui check-env
jiaodui inspect-source <file> [--preview-chars 0..2000 字符] --json
jiaodui inspect-images --unit <unit_dir> --json
jiaodui convert <file> --mode exam|lecture [--mode-origin user|structure|preview|confirmed] [--mode-reason 依据]
jiaodui split <raw_md> --subject <已确定学科> [--mode exam|lecture] [--strategy rule|manual|none]
jiaodui precheck-split <paper_dir>   # 单元根目录，不是材料根目录
jiaodui slice --boundaries <清单.json> [--raw R] [--out-root D] [--mode exam|lecture] [--subject 学科]   # mode/subject 建议显式，与预览一致
jiaodui slice --raw R --mode lecture [--subject 学科] --preview   # 拆分子 agent 定边界行号用，只打印清理后正文
jiaodui status <paper_dir> --json   # 单元根目录：W/校对/<材料名>/units/<材料名>/
jiaodui verify-report --unit <dir> [--source S]
jiaodui execution-policy --unit <registered_unit_dir> --mode automatic|interactive --origin user|confirmed --expected-run-id <run>
jiaodui unit-event --unit <registered_unit_dir> --phase <phase> --event <event> --attempt-id <attempt> --fingerprint <sha256> [--source S] [--category call_correction|calc_representation|report_repair|targeted_review|technical_redispatch|image_schema_fix] --expected-run-id <run>
jiaodui unit-recovery --unit <registered_unit_dir> --source technical_crash|timeout|rate_limit --phase <phase> --attempt-id <attempt> --fingerprint <sha256> --expected-run-id <run>
jiaodui parse-report --unit <dir> [--source S] [--legacy]
jiaodui repair-report --unit <dir> [--source S] [--apply]   # 显式完整性修复；--apply 才原子写报告
jiaodui calc <op> --param NAME=VALUE … [--show-code] [--subject <学科>]
jiaodui quantities --subject <学科> [--search 关键词]
jiaodui build-report <paper_dir> [--out PATH]   # 同一个单元根目录
jiaodui build-docx <paper_dir> [--out-dir D]   # 同一个单元根目录
```

- 全局参数只有四个：`--json` / `--quiet` / `--work-root` / `--version`（`--json` / `--quiet` 可放子命令前或后：`jiaodui --json status <paper_dir>` 或 `jiaodui status --json <paper_dir>`）。
- 各写入命令的额外参数（速查表未逐条展开）：`convert` 有 `--out-dir` / `--base-name` / `--mathjax` / `--legacy-layout` / `--material-name`；`split` 有 `--base-name` / `--images-dir` / `--no-clean` / `--rerun` / `--replace-units` / `--adopt-units` / `--out-root` / `--legacy-layout` / `--material-name` / `--mode-origin` / `--mode-reason`；`slice` 有 `--raw` / `--out-root` / `--base-name` / `--images-dir` / `--no-clean` / `--rerun` / `--replace-units` / `--preview` / `--legacy-layout` / `--material-name` / `--mode-origin` / `--mode-reason`；`parse-report` 有 `--legacy` / `--legacy-layout`；`build-report` / `build-docx` 有 `--legacy-layout`；`verify-report` / `parse-report` / `repair-report` 有 `--source`，`repair-report` 有 `--apply`（原子替换并复验，缺省只预览）。完整清单以 `jiaodui <命令> --help` 为准。
- `--work-root` 同样可放子命令前或后，但**必须等于宿主注入的工作区**（不一致的绝对路径会被插件壳直接拒绝），且必须是已存在的目录；它不是「换个地方产物」的开关。跨机器/无注入的只读场景可用 `JIAODUI_WORK_ROOT`。
- `--material-name` **只在 `convert` / `split` / `slice` 上注册**，不是全局参数；`split --adopt-units` 仅在人工裁定后显式接纳磁盘集合，不自动删除。
- 拆分结果与当前单元集不同（多出或缺单元）时**不要手删目录**：用 `split` / `slice --replace-units`，陈旧单元会归档到 `units/<材料名>/.superseded/<run_id>/`（源文、报告与图片都保留），单元集与轮次记录一并更新。不带该参数时命令按 `unit-set-mismatch` 拒绝，并在 details 里给出这条提示。
- `calc` 的 op 名有两套：**用户可见名**（`evaluate` / `solve` / `formula` / `dimension` / `vector` / `circle` / `equality`）与**内部名**（`dimensional` / `vector_ops` / `circle_from_two_points`）。CLI 两套都接受，但文档、`--subject` 白名单与示例统一用可见名；不要调用未列入命令速查或 CLI 帮助的 `calc` 子命令。
- `calc --subject <学科>` 会按该学科配置的 `tools` 白名单校验：学科未声明 `calc` 时直接返回退出码 7（不支持）；不带 `--subject` 时不校验。它还会把该学科的 `quantities` 物理量表注入 `dimensional`，用于给 `{"quantity": …}` 声明做量纲交叉校验；量表不进模型上下文，需要核对用词时查 `jiaodui quantities --subject <学科> --search <关键词>`。
- 退出码：0 成功 / 1 未预期 / 2 用法 / 3 环境 / 4 校验失败 / 5 未找到 / 6 契约 / 7 不支持。另有两种**非契约**退出：用户中断（`KeyboardInterrupt`）返回 **130**；插件壳在超时或子进程失败时折算为 **-1** 并把 `success:false` 一并回传。两者都不是工具判定的失败码，不要按 0–7 的语义解释。
- 所有写入都限当前工作区：写入命令经插件调用时由宿主注入工作区，产物一律落在 `W/校对/<材料名>/` 内；越界路径由插件壳与 CLI 两侧共同拒绝。

## 五、讲义导入清理顺序（默认开启）

与旧仓 `clean_enabled` 默认开启一致，顺序固定：`fix_latex_escapes` 还原 pandoc 过度转义 → `comprehensive_clean` 去表格竖线 → `clean_intent` 清【出题意图】 → `fix_floating_images` 把浮进选项 A 的题图挪回独立行 → `normalize_option_spacing` 压选项/解答长空格 → `strip_decor_images` 清装饰图。

pandoc 会把讲义渲染成网格表，`**例1**`/`**练1**` 落在表格行内（行首是竖线）；不清理则 `section_pattern` 命中不到，整篇会塌成一个超长单元。仅在需要保留原始表格做对照时才加 `--no-clean`（此时六步全不执行）。

## 六、派发与异步句柄

滑动窗口补位：空位立即补派下一个单元，并发取宿主上限（DSH 默认 8）。首个单元错误达到批次停止条件后，立即停止补位并取消仍在途任务；区分此前已发出的并行调用与获知错误后新增的调用，确认在途任务均已停止后才结束批次。

异步派发必须等待调用完成后再判断结果：使用 `await Promise.all(...)`，或在需要完整收集部分失败时使用 `await Promise.allSettled(...)`；逐项验证返回的 `kind` 与任务句柄（`jobId` / `subagentId` / `runId`）。未 await 的 Promise 序列化成 `{}` 不代表派发结果；拿到并记录有效句柄前不得检查状态、认定派发失败或结束批次。

## 七、入口被宿主修剪时
宿主在压缩触发时会把超过字符预算的工具结果裁成「头部 + `[... tool result middle pruned ...]` + 尾部」。若你在上下文里看到该标记，说明本次加载的 `SKILL.md` 中间段（流程主体、预算与取消规则）已不可见：

1. 重新调用 `skill jiaodui` 拿一份新的完整正文（在被再次修剪前有效）；
2. 或直接用 `read` 按 `offset` / `limit` 分页读取该 skill 的 `SKILL.md` 绝对路径；
3. 在补齐之前不要凭记忆执行派发、登记与交付步骤。

## 八、智能拆分与边界清单

仅在 `precheck-split` 显示空单元、超长单元或明显错位时升级；主 agent 不亲自执行预览、不读预览正文：

1. 派**拆分子 agent**（主 agent 不亲自执行）：子 agent 自行运行 `jiaodui slice --raw <raw_md> --mode <mode> --subject <学科> --preview`，在输出的**清理后正文**上定行号；主 agent 只收边界文件路径与一行摘要，**不读预览正文**。
2. 边界清单 JSON 必须写明 `"mode"` 与 `"subject"`：`{"raw": "...", "mode": "lecture", "subject": "高中物理", "boundaries": [...]}`。
3. 主 agent 执行 `jiaodui slice --boundaries <清单.json> --mode <mode> --subject <学科>`——**必须与预览完全同一组参数**。
4. 讲义先清理再切，预览与执行须使用完全相同的 mode/subject/清理参数。新布局未知 mode 不再默认试卷；清单类型与显式类型冲突会拒绝。修改类型先重新 convert 再预览，不沿用旧类型的行号。

文本读取按宿主动上限分页：DSH 每次最多读取 2,000 行，这与入口识别共用的每份材料 2,000 字符预览额度不是一回事。


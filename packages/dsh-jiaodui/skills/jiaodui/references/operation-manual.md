# 校对CLI操作参考

仅在需要核对命令参数时读取；完整参数以 `jiaodui <command> --help` 为准。

## 工作区和目录

`W` 是当前会话工作区。新材料位于 `W/校对/<材料名>/`，单元根目录是 `units/<材料名>/`，单元目录是其直接子目录。所有写命令必须使用宿主注入的工作区；`--work-root` 只能等于该路径，不能用于改变产物位置。

拆分后的 `task_id` 和 `unit_ids` 由 CLI 返回并保存在材料清单中。单元子代理使用这两个 ID，不拼接材料或单元长路径来调用结构化工具。ID随材料搬移保留，查找范围仍限于当前工作区。

## 入口和准备

正常路径调用结构化工具 `jiaodui_task_prepare`（`operation` 取 `check-env` / `inspect-source` / `convert` / `split` / `precheck-split` / `status` / `execution-policy`），参数按名传入，不再手拼命令行。
下面的 CLI 写法只在没有该工具（或需要上面没登记的参数）时作为退路：

```text
jiaodui check-env
jiaodui inspect-source <file> [--preview-chars 0..2000] --json
jiaodui convert <file> --mode exam|lecture [--material-name NAME] --work-root W --json
jiaodui split <raw_md> --subject 高中物理 --mode exam|lecture [--strategy rule|manual|none] --work-root W --json
jiaodui execution-policy <material_dir> --mode automatic|interactive --origin user|confirmed --work-root W --json
jiaodui precheck-split <paper_dir>
jiaodui status <paper_dir> --json
```

`split` 可选 `--rerun` 开新轮；单元集合变更须显式 `--replace-units`，陈旧单元移入 `.superseded/<run_id>/`，只移动不删除。人工接纳现有集合用 `--adopt-units`。`convert` 另有 `--out-dir`、`--base-name`、`--mathjax`；`split` / `slice` 另有 `--base-name`、`--out-root`、`--no-clean`。材料类型来源可用 `--mode-origin` / `--mode-reason` 登记。所有选项以 `jiaodui <command> --help` 为准。

## 单元身份和提交

父代理读取拆分结果中的 `task_id`、`unit_ids` 后派发单元。单元子代理不收源文正文；先取单元snapshot，再按需分页读取源文和图片实际读取清单。

1. `jiaodui_unit_snapshot` 获取 `snapshot_sha256`、源文/图片/数据/报告摘要和 `run_id`。
2. `jiaodui_unit_read` 使用task/unit ID分页读取源文，图片路径取自同一份实际读取清单；单次最多2000行，后续页递增 `start_line`。
3. `jiaodui_unit_locate` 按短语取得候选 `location_id`、`match_index`、精确 Unicode 区间和安全范围。重复命中必须选定具体位置；源文版本变化后旧ID失效。
4. `jiaodui_unit_submit` 提交schema v2建议对象和步骤1的snapshot hash。工具从不可变源文生成全文报告，复核verify、图片和版本后再登记；过期版本拒绝写入。`preview: true` 只做预览。

建议对象字段：

```json
{
  "schema_version": 2,
  "task_id": "材料task_id",
  "unit_id": "单元unit_id",
  "run_id": "当前轮次ID",
  "source_sha256": "当前源文SHA-256",
  "body_sha256": "当前正文SHA-256",
  "proposal_revision": 1,
  "summary": "一般问题",
  "corrections": [{
    "id": "c1",
    "location_id": "unit-locate返回的ID",
    "expected_original": "木板",
    "replacement": "木块",
    "reason": "对象名称与上下文定义不一致。",
    "category": "term",
    "severity": "一般问题",
    "evidence_ids": ["e1"]
  }],
  "evidence": {
    "assumptions": [{"id": "e1", "text": "依据摘要", "source_locations": []}],
    "symbols": [],
    "images": {"status": "not_applicable", "reason": "无配图"},
    "calculations": {"status": "not_applicable", "reason": "无数值或公式核验"}
  },
  "self_check": {
    "status": "passed",
    "checks": ["real_issue", "replacement_semantics", "related_coverage", "scope_and_uncertainty", "severity"],
    "unresolved": []
  }
}
```

无问题单元提交空 `corrections`、`summary: "无问题"` 和必要的证据对象。竖线与标记括号由 v2 转义无损承载（ADR 0006），不再因此拒绝提交；`_校对数据.json` 的 `marked_text` 保持报告字面（带转义），`corrections` 是反转义后的内容。旧 Markdown 报告仍可由 `verify-report` / `parse-report` 兼容读取；`repair-report` 仍只服务旧报告修复。

## 恢复与事件

执行模式记录后，以 `unit-recovery` 按 `unit_id`、**失败错误码**和64位小写SHA-256失败指纹消费有限预算：恢复类别由错误码确定性决定，不由模型自选——`usage`/`not_found`/`unsupported`/`*stale` → `call_correction`；`calc_failed`/`calc-evidence-invalid`/`proposal.calc-*` → `calc_representation`；`verify_failed`/`contract`/`out-of-contract`/`syntax.*`/`integrity.*`/`original.*`/`locate.*`/`report.*` → `report_repair`；`images.*`/`images-invalid` → `image_schema_fix`；`env`/`host-timeout`/`host-crash`/`parent-technical-timeout` → `technical_redispatch`。未分类的错误码会被拒绝并给出相近的已知码；用户取消与权限拒绝**不可恢复、不消耗预算**；只有父代理判断类的 `targeted_review` 可以不带错误码，带了与映射不一致的类别会被拒绝。换 agent 或更换指纹不能重置同轮计数。`unit-event` 记录阶段、attempt、agent，以及明确的取消发起者和原因。user取消不重派；parent技术取消不得记作user取消。

## 父代理复核（第7项实验分支）

技术提交后，先生成整卷报告通读全文和证据。`unreviewed`列出待审单元，但全文可读；complete仍false。以提交后的unit-snapshot hash调用 `jiaodui_unit_review`，decision为accepted或needs_revision；退回需issue，接受绑定当前输入、建议、报告与自查hash。任何版本变化后重新复核。Word只允许当前版本已accepted。

## 交付

正常路径调用 `jiaodui_delivery`（`operation` 取 `build-report` / `build-docx`，`paper_dir` 为拆分返回的单元根目录）。它的 `json` 字段直接给出 `ok` / `complete` 与结构计数，不必自己解析 `stdout`。CLI 退路：

```text
jiaodui build-report <paper_dir> --work-root W --json
jiaodui build-docx <paper_dir> --work-root W --json
```

`build-report` 的 `ok` 表示诊断报告文件已生成；只有 `complete: true` 才表示所有单元均已通过或显式跳过。任何失败占位意味着整卷尚未正式完成。Word交付还必须检查结构化 `ok: true`，缺失、记账异常或图片未嵌入均不交付。不执行最终Word分页或截图验收。

- 全局选项：`--json`、`--quiet`、`--work-root`、`--version`。
- 历史Markdown报告兼容读取：`jiaodui verify-report` / `jiaodui parse-report`；仅旧报告可用完整性辅助 `jiaodui repair-report --unit <unit_dir> [--apply]`，应用时原子替换并复验。

## 只读与计算

`unit-locate`、`unit-snapshot`、`calc-schema` 为只读命令。计算优先调用 preset 中按operation区分的 `jiaodui_calc_<operation>` 工具；参数schema从 `jiaodui.calc.OPERATIONS` 元数据导出，未知字段拒绝。CLI 退路：

```text
jiaodui calc <op> --param NAME=VALUE ... [--subject 高中物理]
jiaodui quantities --subject 高中物理 [--search 关键词]
```

稳定退出码为 0–7；用户中断为 130。插件超时/子进程失败使用 `exitCode: -1` 并返回 `stdout / stderr / truncated`。

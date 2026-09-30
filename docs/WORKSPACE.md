# 工作区布局验证

实现契约见 [ADR 0002](adr/0002-workspace-material-layout.md)。默认产物位于当前会话工作区 `校对/<材料名>/`；源文件可来自工作区外。CLI 的相对路径按显式工作区解析。

## 自动验证

工作区阶段整体回归：713 passed、10 skipped、4 subtests passed；入口分流补齐后的整体回归为 740 passed、10 skipped、4 subtests passed（见 [迁移核对](ENTRY_MIGRATION.md)）。`git diff --check`、两份 skill 一致性、skill 校验和插件行为测试均通过。

- `tests/test_workspace_workflow.py`：无工作区拒绝、符号链接、转换子进程输出边界、目录布局、续跑、重新校对、参数/图片变化、重名冲突不改旧产物、集合双向检查和显式接纳、清单损坏/越界、真实 docx 图片搬移、并发登记。
- `tests/test_dsh_plugin_tool_behavior.py`：真 Node 加载工具，用子进程验证延迟 stdout、非零退出 stderr、超时诊断、截断、工作区注入、缺少会话工作区拒绝。CI 必须运行，不允许缺 Node 时跳过。
- 既有历史契约用例显式授权临时工作区与 legacy_layout；报告闸门语义不放松，旧 M1 文件保留原样。
- 构建 wheel 后安装到 `/tmp` 的独立 Python 3.12 环境，从仓库外运行 CLI，确认包内配置和默认布局可用。

2026-09-30 仓库外 CLI 真实材料冒烟通过：冻结 M1 docx 位于工作区之外，分别在临时 A、B 转换、拆分、校验并登记既有合格报告、生成整卷报告和 Word。每份 5 单元、28 标记、缺失 0；报告分别落在材料根的 `校对报告/`、`校对Word/`。续跑不改报告字节，A 的材料搬到 C 后 status/build-docx 通过，原始源文件 SHA 未变。此测试复用已核对的历史报告，只验证确定性链路，不代表重新进行模型校对或通过 DSH 会话验收。

## DSH 真机验证（用户执行）

按 [宿主探针](../packages/dsh-jiaodui/host-probe/README.md) 在 A、B 两个新工作区调用 `jiaodui check-env --json`，应看到非空 stdout，`runtime.work_root` 分别等于当前工作区。既有插件 JS 模块需重启 DSH 才能加载更新；开发软链安装无需重新安装 bundle。

接着调用 convert、split、单元校对、verify-report、parse-report、build-report、build-docx。重点检查所有产物在各自工作区、子 agent 收到 W 和单元绝对路径、通过后登记才计完成。此项尚未宣称通过；用户已明确自行测试。

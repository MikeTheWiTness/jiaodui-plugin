# 会话工作区与输出宿主探针

此探针必须在真实 DSH 会话执行；Node 行为测试不替代宿主验收。

1. 加载更新后的插件（既有 JS 模块代际需要重启宿主），打开独立工作区 A，在「校对」preset 调用原生工具：`args: ["check-env", "--json"]`。保存工具的完整返回与 `runtime.work_root`，确认 stdout 非空、CLI 路径正确、work_root 等于 A。
2. 同一宿主打开独立工作区 B，重复调用，确认 work_root 等于 B 且不同于 A。两次都不传 cwd 或 work-root，才能检验真实会话注入。
3. 首次校对派发前按随包 skill 的 `references/vision-probe.md` 验证子 agent：只派发 `assets/vision-probe.png` 的绝对路径和观察要求，不传答案或 SVG。不依赖教材图片，也不在工作区创建随机探针目录。DSH `read_image` 使用 `file_path`；参数错误按当前 schema 修正后最多重试 2 次，若用户明确遇错即停则停止。无图材料也必须能走此探针。
4. 以工作区外的同一源文件，在两会话分别调用 convert、split，再让单元子 agent 读取实际材料图片、落盘报告、verify、parse-report 登记，最后 build-report/build-docx。确认所有校对产物只在各自 `校对/<材料名>/` 下；原始源文件 SHA 不变。同会话同模型/工具配置复用成功的固定探针，不逐材料重测；透明教材图仍按需合成白底。
5. 将其中的材料目录整体搬到另一个工作区，重新 status/build-docx，确认登记有效且图片不缺失。重跑、冲突、双向单元集和符号链接反例另由确定性测试覆盖。

check-env 的 runtime.work_root 在子进程内解析 JIAODUI_WORK_ROOT，因此其正确返回同时验证显式 env 注入。记录包括宿主版本、会话工作区、工具退出码、完整 stdout/stderr、产物路径和执行日期。不记录凭证。

## 类型入口补测

- 明确告诉宿主“这是高中物理讲义”：应直接 convert --mode lecture，不再为类型或学科预览/询问。
- 同一份 Word 只说“帮我校对”：应先 inspect-source 获取结构事实；大量重复嵌套承载主要正文时采用 lecture，必要时仅为尚不明确的学科有限预览。
- 明确说“按试卷流程处理”：用户指定优先，不能让文件名或嵌套结构擅自改成讲义；拆分预检异常应按现有升级流程处理。
- 使用结构不明显、类型含混的材料：有限预览后仍不确定时询问，不能默认 exam。
- 类型确认后检查材料记录中的 mode/origin，以及 split/slice 使用同一类型；单元阶段仍共用同学科校对和交付要求。

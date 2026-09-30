# ADR 0002：工作区产物与材料身份

- 状态：已采纳（v3）
- 工作区 W 由宿主会话注入 `JIAODUI_WORK_ROOT`，或显式 `--work-root` 指定。写入缺少 W 返回契约错误；只读命令独立可用。
- 默认布局为 `W/校对/<材料名>/{source,raw,units,校对报告,校对Word}`；单元根为 `units/<材料名>/`。
- 六条写入命令：convert、split、slice（非 preview）、parse-report、build-report、build-docx。实际写入处检查真实路径归属，拒绝符号链接逃逸；不提供越界开关。系统临时文件不属于校对产物。
- `_校对记录.json` 带 schema_version，记录源文件 SHA、资源摘要、参数、单元输入摘要、轮次与交付登记。它不能授权写入；损坏不能回退历史布局。
- 同名不同源文件 SHA 拒绝覆盖。相同输入及参数续跑；资源或处理参数变化、显式 rerun 开新轮次，不复用旧轮交付。
- parse-report 是单元交付登记点：先 verify，再写单元数据，最后登记当前轮次、报告 SHA 与单元输入摘要。并发登记加锁且原子写入。
- status 由磁盘推导：新布局同时核对当前轮登记、报告 SHA、输入摘要和 verify；不信任 runs.status。无 W 时按材料目录校验内部相对路径，原始 source_path 只作溯源。
- 单元集合双向核对；多余、缺失均返回 unit-set-mismatch，details 包含可扫描状态。split --adopt-units 显式接纳磁盘集合，记录前后差异，不删除产物。
- `_校对报告.md` 只存当前交付；轮次摘要存记录。下游不消费旧轮或未登记报告。
- 历史写入须显式 --legacy-layout，仍受 W 边界限制；历史未通过报告只能 --legacy 解析且不能登记为新交付。
- 错误沿用 `{ok:false,error:{code,message,details}}`。内部依赖相对材料目录，JSON 命令输出使用绝对路径。材料搬移不依赖原机路径。
- 验收包括 A/B 工作区、外部源文件、冲突不改旧产物、单元集双向检查、重跑失败、搬移、符号链接、并发登记与真实宿主探针；模拟不替代宿主读图和会话验证。

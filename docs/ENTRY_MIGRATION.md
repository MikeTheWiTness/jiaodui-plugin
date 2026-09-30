# 入口、导入与拆分迁移核对

本次只读检查旧仓 `../JiaoDuiAgent`，以当前高中物理主链路为落地范围；没有修改旧仓、读取凭证或引入旧仓运行时依赖。

| 能力 | 旧仓事实 | 新项目对应与结论 |
| --- | --- | --- |
| 材料类型入口 | `ui/default_app.py:46` GUI 默认为讲义，用户选择类型，无自动结构识别 | skill 明确用户指定优先；新增 inspect-source 提供结构事实及有限节选，主 agent 判断或询问 |
| Word 格式转换 | `core/defaults.py:1040` Pandoc → 上下标归一 → 格式增强；`ui/default_app.py:929` 讲义启用 MathJax | 核心链已迁移；本次补 convert --mode 自动传入讲义参数 |
| 导入后处理分流 | `ui/default_app.py:956` 讲义修转义/表格/出题意图/浮图/空格；其余 Word 走 post_process_md_zw | 讲义六步清理已迁到 prepare_lecture_content，放在拆分时执行以保留 raw；本次限定试卷 Word 后处理只用于 exam |
| Markdown/IDML 导入 | GUI 对 Markdown 标为 needs_post=False；小学语文 IDML 提取器也返回 False | 图片归置、IDML 提取器已迁移；本次恢复不套用 Word 专属后处理，避免额外改变原有格式 |
| 讲义规则拆分 | `core/defaults.py:333` 板块/例练标题、连续标题合并、丢空标题壳、图片复制 | split_lecture 已迁移，保留现有契约测试；高中物理沿用同一通用实现 |
| 试卷规则拆分 | `core/defaults.py:666` 题号、随题/文末答案识别与回填、图片复制 | split_exam 已迁移，同一单元输出契约 |
| 人工标记与整篇 | `core/base_subject.py:144` rule/manual/smart/none；部分讲义学科也实现策略选择，物理旧入口仅规则 | 单元标记解析器已有但未接 CLI；本次补 split --strategy manual/none，两类材料复用写盘 |
| 智能拆分 | `shared/smart_split.py` 直接调用模型并解析其正文 | 按新架构由宿主拆分子 agent 判断边界，slice 确定性执行；不搬旧模型调用 |
| 导航/封面跳过 | 高中历史等个别学科在拆分后调用 mark_navigation_units；物理未调用 | 标记函数及读取契约已有，保持按学科接线，不给所有物理讲义新增自动跳过行为 |
| 附加清洗副本 | 旧人工/智能拆分生成 `第N题_clean.md` | 新契约明确不用该副本；原有源文、images 与报告接口取代 |
| 批量与恢复 | GUI 维护 file_list，遇重名自动加后缀 | skill 逐材料派发；工作区材料清单、SHA 冲突拒绝、磁盘 status 替代会话状态 |
| 其他界面和模式 | 压缩包/目录选取、独立清理开关、自由校对、批注评审、排版 GUI | 不等于全部迁移：GUI 由宿主文件选择替代；独立清理开关目前统一 no-clean；自由校对/批注评审/排版按现有 PRD 后置 |
| 其他学科 | 六科独立配置、规范、部分学科特有钩子 | 共用核心可复用，但学科配置与真实验收仍按 M5 推进；不能以此宣称六科已上线 |

目前通用 DOCX/Markdown/IDML 核心可用；旧版二进制 `.doc` 在旧、新仓都曾列为输入，却都传 Pandoc 的 docx reader，不能视为已验证支持。入口检查明确说明结构不可得，建议先另存为 `.docx`，不根据读取失败猜材料类型。

本次验证锁定真实讲义的结构计数，以及平铺表格反例、有限预览上限、用户指定不触发检查、未知类型拒绝、mode 持久化与预览/切片一致性、Word 与 Markdown 导入差异、人工/整篇拆分。类型判断质量与 DSH 会话行为由用户另行真机验收；自动测试只证明确定性工具及参数执行。

验证结果：整体回归 740 passed、10 skipped、4 subtests passed；skill 校验及随包副本一致性通过。仓库外安装新 wheel 后，从用户提供的 Downloads DOCX 读取到 42/32/3 的表格总数/嵌套数/深度，按 lecture 导入并沿用类型拆分为 5 单元，单元图片 7 张、缺失 0。真实讲义的既有 5 份合格报告仍通过闸门。源文件和旧仓保持只读。

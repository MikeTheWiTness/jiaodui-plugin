# 全链路审查记录（2026-10-10）

范围：当前工作树（HEAD 8fb19a8 + 未提交改动）；导入、清理、拆分、读取、计算、结构化提交、父复核、调度恢复、整卷报告、Word。只审查与复现，没有修改业务代码，也没有重跑真实模型校对。

评判按轻度实现：优先修正常教材/模型工具调用能触发的错误；不要求新增数据库、完整调度引擎、恶意输入防御体系或程序判断物理语义。P1 表示影响内容正确性、完成契约或调度闭环；P2 表示较局部的能力不一致或流程缺口。

共确认 16 项：12 项 P1、4 项 P2。其中 R13–R15 是上一轮已报告的最近提交回归，其余是此次扩大范围确认的现存缺口。现有全量测试 1192 passed、4 subtests passed；以下复现说明全绿不等于覆盖了这些链路。

## R1 [P1] 导入先按 basename 查图，正确相对路径被同名图片抢占

位置：[convert.py:1439](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/convert.py:1439)。

源文件同时引用 `a.png`（红色）和 `nested/a.png`（蓝色）。转换后两条引用都变成 `./配图_images/media/a.png`，实际都是红图，warnings 为空。按内容哈希处理同名冲突的代码没有机会生效，因为解析阶段就选错了源文件。

影响：后续读图、verify、提交、父复核都面对合法但错误的图片。图文不符可能被当成教材问题，或真实图片错误被漏掉。

最小处理：先精确解析正文路径；确实找不到时才用 basename 回退，且不同内容的候选不能任取。可复用拆分层 `copy_md_images` 已有的规则。

## R2 [P1] 智能切片无覆盖核对，漏掉正文仍得到 complete=true

位置：[split.py:807](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/split.py:807)、[precheck:838](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/split.py:838)。

三行源文为“第一题。/关键错误正文。/第二题。”，边界只取第 1 行和第 3 行。拆分不报告漏行，precheck 无空单元/超长单元/warnings。两个单元按正常 v2 提交并 accepted 后，build-report 返回 complete=true，遗漏的第 2 行永远不进入校对。

同一入口还接受任意 `text`，无法证明文本来自预览源文。这里不把历史支持 `text` 本身定为 bug；缺口是正式材料全量切片没有区分“整篇覆盖”与“人为节选”。

最小处理：正常智能拆分使用源文行区间，预检输出未覆盖/重复覆盖的非空区间；明确节选时留显式声明。无需做 DOCX 与 Markdown 的复杂反向语义校验。

## R3 [P1] 重复单元名先覆盖文件，最后才拒绝清单

位置：[split.py:821](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/split.py:821)。

在既有单元1上提交两个边界，name 都为“单元1”，分别取第 1 行和第 3 行。调用最终报 invalid-manifest，旧清单未变，但单元1.md 已变成“第三段”，旧输入摘要失效。

影响：一次被拒的模型边界提案会破坏此前可继续使用的材料现场。

最小处理：写盘前检查最终单元名唯一；不用添加全套事务或备份机制。

## R4 [P1] 试卷答案按拆出顺序回填，而不是原题号

位置：[split.py:488](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/split.py:488)。

题干原编号为 1、3，末尾参考答案有 1=A、2=B、3=C。拆分后的第三题正文被回填“【答案】B / 解析二。”，没有答案错配告警。题号从 5 起则全部找不到对应答案。

影响：节选试卷、缺号试卷或规则漏识别一题时，后续单元可携带别题的答案和解析。下游只能验证拆分后的错误源文。

最小处理：目录可连续编号，但回填答案用题干解析出的原题号，并对缺失/重复题号留诊断。

## R5 [P1] 圆轨迹计算返回不经过第二个点的圆

位置：[templates.py:570](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/calc/templates.py:570)。

直接使用高中物理 skill 的示例：entry_point=[1.5,1]、velocity_direction=[3,4]、impact_point=[0,-1.5]、impact_normal=[0,1]。工具 success=true，返回 center=[29/6,-3/2]、radius=25/6。

独立核算：圆心到入射点为 25/6，到撞击点为 29/6。返回的圆没有经过给定撞击点。实现只联立两个方向约束，没有检查两点到圆心等距。

影响：这是确定性计算错误，且示例属于宣称支持的数值路径；不是符号坐标限制或模型判断错误。错误结果能被记为成功 calc 证据。

最小处理：明确 normal 的物理含义、联立真实几何约束；返回前检查两点等距、方向条件。无解/条件冲突应明确报错，不能返回伪圆。

## R6 [P1] formula 多解时静默取第一个解

位置：[templates.py:277](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/calc/templates.py:277)。

formula='E = m*v**2/2'、solve_for='v'、substitutions={E:100,m:2} 返回 success=true、result=-10.0。实际上有 ±10 两个代数根；工具没有声明“选第一根”，也没有物理假设证明负根是本题应取的分支。

影响：校验速率时可能以负值反驳正确答案；即便目标是有向速度，也丢掉另一分支。

最小处理：返回全部解，或多解时报明确歧义让 agent 使用 solve/补假设；不要猜正根或负根。

## R7 [P2] 求导接受 substitutions，却完全忽略代入

位置：[templates.py:253](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/calc/templates.py:253)。

differentiate(expression='x**2', variable='x', substitutions={x:3}) 返回 success=true、result='2*x'，而按参数说明“求导后代入”应为 6。模板的 substitutions 被替换为空，求导后也未使用 subs_call。

最小处理：执行导数的后置代入；若暂不支持，应移除参数并明确拒绝，不能静默忽略。

## R8 [P1] 图片证据只验形状，没有与实际清单绑定

位置：[report_suggestions.py:231](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/report_suggestions.py:231)、[unit_delivery.py:118](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/unit_delivery.py:118)。

实测两种提案均可提交、accepted、build-report complete=true：

- 源文确有题图，但 evidence.images={status:not_applicable,reason:无图}。
- evidence.images 填 reference_index=999、position=999/999、original_path/actual_read_path 指向不存在的文件，readable=true。

inspect-images 检查的是真实源文资源，提案图片证据检查的是类型；两者没有对照。

最小处理：按清单校验引用序号、路径和位置，并要求实际存在的图片引用有对应证据。core 不必证明模型理解了图像，也不应伪称能证明真实 read_image 执行；这个确定性的绑定仍可做到。

## R9 [P1] 调度把“待父复核”当作“需重派”，并可能被旧心跳卡住

位置：[material.py:421](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/material.py:421)、[unit_delivery.py:219](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/unit_delivery.py:219)、[review.py:91](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/review.py:91)。

两种正常序列已复现：

- 窗口1有单元1、单元2。单元1提交成功并登记 registered 心跳，尚待收尾父复核。下一次 dispatch-plan 仍派“单元1”，单元2留在 waiting。与 skill“空位立即补下一单元、收尾通读整卷后复核”冲突；可能反复改版并浪费恢复额度。
- 子代理最后心跳为 proposed，unit-submit 成功后未补 registered（例如提交后退出）。父代理 accepted 再 needs_revision，status 为本轮未完成，但 dispatch-plan 仍将旧代理算在途，dispatch=[]。提交/父复核没有同步磁盘推导的技术终态。

最小处理：区分待父复核和已退回；待父复核不自动重派。成功提交/复核的持久结果应终结对应旧尝试，不能要求一个额外的模型心跳才能释放窗口。无需重建宿主 agent 循环。

## R10 [P1] v1 兼容入口仍能把新材料登记为正式完成

位置：[workflow.py:450](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/workflow.py:450)。

新布局材料写合规的旧 Markdown 报告，调用 parse-report，无需 --legacy/--legacy-layout，返回 verified=true、legacy=false、registered=true。没有 unit_reviews，build-report 仍 complete=true。

这是已在 PROCESS_REWORK 记为待决策的缺口，非此次新增回归；但与 README/AGENTS“新材料正常链为结构化提交、旧链只读兼容”的口径不一致。

最小处理：选择清楚的产品边界。若允许人工 v1 登记，应显式标注人工兼容交付；若只读兼容，则新材料拒绝旧链登记，避免冒充 v2 完成。

## R11 [P2] 恢复预算是主动记账，不是全链路强制重试上限

位置：[material.py:597](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/material.py:597)、[unit_delivery.py:164](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/unit_delivery.py:164)。

已复现：相同错误的 unit-submit 连续失败5次，recovery 账本仍为空；没有对应 unit-event 的 recovery 仍可成功；耗尽 call_correction 后有效 unit-submit 仍可成功。

主动调用 recovery 时，分类、扣费、幂等、被拒不写盘本身实现正确。PROCESS_REWORK 明确曾故意不强制心跳关联，因此不建议顺手增加兼容破坏。

最小处理：把“强制”范围写准确：core 强制记账入口，宿主负责每次恢复前记账与遵守 allowed。若确实需要硬限次，再绑定失败/重试入口；不能只补 prompt 就宣称全链路强制。

## R12 [P2] 跳过单元有旧报告时，整卷报告与 Word 口径相反

位置：[docx_report.py:367](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/docx_report.py:367)。

单元已有 v2 报告但未父复核，随后标记 .skip_proofread。build-report 视为跳过并 complete=true；build-docx 仍从 _collect_reports 收入旧报告，再以缺父复核列入 excluded_units，ok=false。已完成旧报告则也可能被 Word 收入，与整卷报告跳过规则不同。

最小处理：Word 收集/筛选阶段统一跳过标记；增加一个“存在旧报告再跳过”的用例。

## R13 [P1，上一轮] Word 表格删除真实的首尾空单元格

位置：[docx_report.py:863](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/docx_report.py:863)。

三列表格数据行 ['', '前木板后', '10']，含一条批注，输出为 ['前木板后','10','']。build-docx ok=true、anchor_count=1、missing_count=0。它把真实空格当成表格外侧锚点片段合并。

最小处理：只合并确实位于表格外的 raw 锚点片段；首尾真实空格保留。锚点计数无需扩成全套版式审核，但这个确定性错列必须修。

## R14 [P1，上一轮] 技术取消撤销后，已停止的旧代理重新被算在途

位置：[material.py:720](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/material.py:720)。

read 心跳 → parent/technical_timeout → revoke。dispatch-plan stop=false，但旧 state 仍是 read，in_flight=['单元1']、dispatch=[]。这与“撤销后即可补位”的宣称不符。

最小处理：技术取消终结旧 attempt；撤销停止标志不应复活已被停止的尝试。

## R15 [P1，上一轮] 用户取消可被后续技术取消覆盖再撤销

位置：[material.py:724](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/material.py:724)。

user/user_cancel → parent/technical_timeout → revoke，最终 stop=false、dispatch=['单元1']。只看最后一条记录导致先前的用户决定被盖掉。异步 timeout 收尾可产生此序列，无需恶意伪造。

最小处理：同轮 user_cancel 的效力不可被技术取消覆盖；直接增加这个三步序列的测试。

## R16 [P2] 原始图片消失后重转，旧输出图片仍被当成有效源图

位置：[convert.py:1437](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/convert.py:1437)、[convert.py:1561](/Users/chouchou/开发/JiaoDuiAgentSkill/jiaodui/convert.py:1561)。

首次导入 Markdown 与 a.png，随后删除原目录的 a.png，保持 Markdown 不变再 convert。返回 copied=1、missing=0，仅提示覆盖 raw；因为搜索目录包含先前生成的 images/media，旧图被回填成有效输入。

影响：重新导入不再反映当前源材料的资源缺失，资源溯源不准确。与“独立复用已导入副本”应作明确区分。

最小处理：重转外部原文件时只从本次源目录解析；显式从 source 副本重转可复用其资源，不能无声混用旧 raw 缓存。

## 已核实的保障与能力边界

- 正常 v2 提交的定位、源文摘要、正文逐字还原、CAS、报告/数据异常回滚已实现。
- 下游复用 verify_unit；本轮登记摘要和当前 accepted 父复核能拦住报告/输入变化。
- 计算证据能核验 call_id 属于当前材料/单元/轮次及结果内容；但这不能证明计算问题建模正确或原文全部结论已覆盖。
- Word 逐单元计数、锚点配对、缺图与降级检查已实现；计数不保证表格列位置或批注覆盖文字正确。
- 子代理工具过滤已经把取消、父复核、写文件与 shell 分离；真实宿主 catalog、读图执行与校对质量仍由宿主验收。
- 计算覆盖清单、自查字面量、同模型父审属于流程复核；不要求把物理语义判断再写一套 Python。
- 当前 review 未检查真实教材的物理结论，也未把自动测试作为新版本宿主冒烟结论。

## 建议处理顺序

1. 内容错误：R1 图片解析、R4 答案映射、R5 圆计算、R6 多根与 R13 表格错列。
2. 完整性入口：R2 覆盖诊断、R3 名称唯一预检、R8 图片证据绑定、R10 新旧交付边界。
3. 调度闭环：R9 待复核与旧心跳、R14 技术撤销、R15 用户取消保护。
4. 局部收口：R7 代入、R12 跳过一致、R16 重转资源来源；R11 先统一能力声明，再决定是否需要硬限次。

每项都可用少量独立样本和行为测试锁定；没有必要为本次问题引入重度防御或重写架构。

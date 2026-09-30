# GitHub Actions 的 Word 生成兼容修复

2026-09-30，提交 250ffd1 的 CI 作业 109796197634 在 pytest 步骤失败：5 failed、754 passed、4 skipped；依赖安装成功。Node 20 弃用警告与 ubuntu-latest 迁移提示不是退出码 1 的原因。

用户提供完整失败日志后确认两类问题：

- 4 项无问题单元的标题批注缺失。实现用正则限定 Heading1 的 pPr 和 run/rPr 固定布局，Ubuntu 安装的 Pandoc 输出不满足该布局。改为解析 OOXML 的样式、标题文字和文本节点，兼容可选 rPr、属性、pPr 顺序、书签及分拆 run；单元复核按同样的 XML 结构分段。
- 1 项含中文下标的公式测试把 matplotlib 可用当作中文字体可用。按原有渲染契约，无中文字体时保留 LaTeX 文本，不能强求 drawing 图片。测试分别核对有字体的图片与缺字体的可见文本，不静默丢失原因。

新增回归还锁定：无问题标题批注未产生时，不得通过整卷 Word 交付复核。无法匹配或同名标题歧义仍留告警，不自动在普通正文内插入标题批注。

CI 使用 Ubuntu 24.04、checkout v5、setup-python v6、setup-node v5；三个 action 的官方 action.yml 已确认使用 node24。Python 和 Node 项目运行时仍为 3.12 和 22。四项 legacy-corpus 跳过来自 CI 缺少本机旧仓只读语料，是现有约定，未放松报告闸门。

本机回归覆盖标题 XML 变体、真实 Word 批注生成、无中文字体降级与缺标题批注拒绝交付。Linux CI 的最终结果以新推送的 GitHub Actions 作业为准，本机通过不能冒充 Linux 验收。

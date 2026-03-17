# 语义目录编写指南（团队口径加深/更正）

语义目录的目标是把“团队共识的口径、字段含义、误用风险、推荐校验”配置化，让 Agent 在输出时更贴近真实口径，并主动提示不确定性与对账点。

## 你需要知道的两层“理解”
- 运行时事实：DataFrame 真实有哪些列、多少行、空值率/覆盖率（来自 Agent 的 context['datasets']）。
- 配置化语义：字段/指标/图表的口径解释与风险提示（来自本目录的 JSON，并注入到 context['semantic_context']）。

语义目录不会改变任何计算结果，只会影响 Agent 的“解释、提示、选图/选指标”的偏好。

## 推荐维护流程（最少投入也有效）
1. 先选 5 个最关键字段/维度（例如 project/aida/tester/status_phase/matrix）。
2. 再选 3 个高频问题（例如趋势、Top 分布、异常解释）。
3. 对应修改 datasets.json / charts.json（必要时 metrics.json），并补齐：
   - 含义（meaning / description）
   - 别名（aliases）：覆盖团队惯用叫法、历史字段名、导出字段名
   - 误用风险（misuse_risks）：最容易踩坑的口径偏差
   - 推荐校验（recommended_checks）：输出前建议看的覆盖率/空值率/分母条件
4. 用 evaluation/agent_eval_cases.jsonl 增加 2-3 条“对账型问题”，跑离线评测对比改动前后。

## datasets.json 怎么写（缺陷/测试数据集）
每个数据集条目建议包含：
- id：稳定、可追溯（例如 octane_defects / octane_tests）
- aliases：让“缺陷/bug/issue/工单”等都能召回同一个数据集
- granularity：一行代表什么
- time_columns / core_dimensions / common_columns：告诉 Agent 哪些列是核心口径
- field_lineage：把语义字段和来源字段串起来，方便对账
- can_answer：这个数据集能回答哪些问题（用团队常用问法写）
- misuse_risks：常见误用与反例

## charts.json 怎么写（看板语义）
每张图建议补齐：
- expected_focus：正常要关注什么（集中度、覆盖率、头部变化）
- abnormal_signals：什么情况算异常、需要进一步排查
- related_dimensions / related_metrics：这张图的关键维度/指标（用于对账列缺失时提示）
- aliases：把中文叫法/简称补进去，提升召回

## metrics.json 怎么写（指标语义）
建议补齐：
- business_meaning：一句话说清这个指标代表什么
- calculation / null_handling：分母/空值/过滤条件怎么处理
- misuse_risks：最容易解读错的地方
- recommended_checks：输出前建议检查哪些前提
- aliases：把团队/看板里常用的指标别名补进去

## 如何验证你改的语义是“有效的”
1. 结构校验（防止引用错误）：
   - 运行 semantic_catalog/validate_catalog.py（会校验 id 唯一性、data_source 引用、aliases 类型等）
2. 召回有效性（防止“写了但用不上”）：
   - 确保 aliases/can_answer/description 里包含团队常用提问关键词
   - 确保 common_columns/core_dimensions 与 data_processor 实际产出列名大致对齐
3. 输出对账（防止“误导”）：
   - 把对账型问题写进 evaluation/agent_eval_cases.jsonl，并运行 evaluation/run_agent_eval_cases.py 看报告


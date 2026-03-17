# 语义目录（Semantic Catalog）

这个目录提供“数据集 / 指标 / 图表”的配置化语义层，用于让 Agent 在分析时更理解口径、降低误用风险，并在输出中主动给出风险提示。

该目录是只读的：不会改变任何看板的数据产出与图表逻辑。

## 包含内容
- catalog_version.json：目录版本与说明
- datasets.json：数据集语义（用途、粒度、字段、可回答问题、误用风险）
- metrics.json：指标语义（公式引用、业务含义、误用风险、推荐校验）
- charts.json：图表语义（图表意图、正常/异常解读、关联维度与指标）

## 运行时行为
- Agent 在处理问题时会从语义目录中按“问题文本 + 数据列名”检索最相关条目，并写入 `context["semantic_context"]`。
- 语义检索默认关闭，可通过环境变量开启：
  - AGENT_SEMANTIC_CATALOG_ENABLED=1

## 开关
这些能力全部只影响 Agent 输出，不影响看板数据加载与绘图。

- AGENT_SEMANTIC_CATALOG_ENABLED=1：启用语义目录注入（默认 0）
- AGENT_CRITIC_ENABLED=1：启用 Critic 校验与质疑模块（默认 0）
- AGENT_VALIDATION_ENABLED=1：启用规则化校验器（默认 1）

## 如何新增语义
1. 在 datasets.json / metrics.json / charts.json 中新增条目，并保持 `schema_version` 不变或按需升级。
2. 建议为每个条目提供：
   - id（稳定、可追溯）
   - description（口径说明）
   - aliases（可选：团队常用叫法/历史字段名/简称）
   - misuse_risks（常见误用与反例）
   - recommended_checks（输出前应做的校验）
3. 图表语义建议使用 Dash Graph 的 id（如 `inflow-outflow-chart`）作为 chart id，便于定位与追溯。

## 结构校验
- 可用校验脚本检查 id 唯一性、data_source 引用、aliases 类型等：
  - semantic_catalog/validate_catalog.py

## 离线评测
- 用例：evaluation/agent_eval_cases.jsonl
- 运行：python evaluation/run_agent_eval_cases.py
- 输出：evaluation/agent_eval_report.md

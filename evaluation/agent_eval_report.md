# Agent 离线评测报告

- 用例文件：agent_eval_cases.jsonl
- 开关：AGENT_SEMANTIC_CATALOG_ENABLED=1, AGENT_CRITIC_ENABLED=1, AGENT_VALIDATION_ENABLED=1

- 汇总：passed=5/5 (100.0%)
## defect_trend_short_window

- Question: 最近两周缺陷趋势如何？能否下结论说问题在恶化？
- Tools: analyze_trend
- Warnings: 0
- Refusal: False

- EvidenceDetected: True
- StructuredEvidenceDetected: False
- NonSQLEvidenceDetected: True
- ClarificationMode: False
- RefusalReason: -
- UnsupportedClaimSignal: False

- Pass: True

### Answer

```text
根据您的问题「最近两周缺陷趋势如何？能否下结论说问题在恶化？」，我进行了以下分析：

**语义目录（口径/字段/误用风险）**
以下为系统内置的语义目录（配置驱动），用于约束与增强分析。不得编造未在目录中的口径。

【数据集语义】
- octane_defects | Octane Defects
  - granularity: 一行=一个缺陷(work_item)
  - can_answer: 不同时间/项目/AIDA/FV下缺陷数量趋势如何; 当前阶段分布、严重度分布是否异常; 高风险缺陷（按规则）集中在哪些域/团队/版本
  - misuse_risks: 仅用creation_time做趋势可能忽略状态迁移；需要明确口径（新增/存量/关闭）; aida_english可能来自提取或映射，存在Unknown/不一致，需要在结论里标注覆盖率
- octane_tests | Octane Tests
  - granularity: 一行=一个测试实体（具体以导出字段为准）
  - can_answer: 测试覆盖/测试用例数量在项目/AIDA/FV维度的分布; 缺陷与测试的联动（需要明确join键）
  - misuse_risks: 测试数据的粒度可能不是“执行记录”，不要直接解读为“通过率/失败率”除非字段明确

【指标语义】
- severity_rate | Severity Rate (Deprecated)
  - description: 历史兼容项：代码实现口径更接近 severe_rate（Critical Issues 规则），建议改用 severe_rate。
  - inputs: severity_group; matrix; classification
  - alias_of: severe_rate
- topissue_risk_score | TopIssue Risk Score
  - description: 用于评估TopIssue缺陷风险强度的综合评分，包含matrix严重度、classification、ECU/Domain转移、父子复杂度、处理周期与推迟修复等维度，并做非线性组合。
  - inputs: matrix; classification; ecu_pingpong_count; domain_pingpong_count; parent_child; child_count; processing_days; shift_pu_status
  - misuse_risks: 评分是规则/口径模型，不等价于缺陷真实影响；需要结合严重度与业务背景解释; 不同时间段/项目间对比前需确认评分口径是否一致、字段覆盖率是否一致
  - recommended_checks: 输出时给出评分分布（P50/P90/TopN）与关键驱动维度; 若评分依赖字段缺失率高（如classification为空），应提示结论可信度受限
- processing_cycle_days | Processing Cycle Days
  - description: 缺陷处理周期天数：从创建到当前阶段（或关键状态迁移）的耗时，来自历史记录计算。
  - inputs: defect_id; status_phase; creation_time
  - misuse_risks: 如果历史数据不完整或阶段定义变化，会导致周期偏差; 不同状态阶段的周期含义不同，比较前要锁定同一阶段或同一生命周期段
  - recommended_checks: 输出时说明使用的阶段口径与历史数据来源（文件/DB）; 当仅有少量票有历史数据时提示样本量不足
- tester_severe_rate | Tester Severe Rate
  - description: 按 tester 计算严重缺陷率（Severe Defect Rate
...(已截断)

**分析趋势（按week分组）**
- 趋势方向: 上升
- 变化率: 66.67%
- 总数: 8
- 平均: 4.0

**相关历史对话**
- 最近两周缺陷趋势如何？能否下结论说问题在恶化？...

**关键洞察**
1. 整体呈上升趋势，变化率为 66.7%

**建议**
- 缺陷数量呈上升趋势，建议加强代码审查和测试覆盖率

**校验与质疑**
- [info] 未发现明显风险提示缺失或工具异常。
```

## defect_inflow_outflow

- Question: 请解释 inflow/outflow 看板该怎么解读，最近是否在积压？
- Tools: defect_explore_dashboard
- Warnings: 0
- Refusal: False

- EvidenceDetected: True
- StructuredEvidenceDetected: False
- NonSQLEvidenceDetected: True
- ClarificationMode: False
- RefusalReason: -
- UnsupportedClaimSignal: False

- Pass: True

### Answer

```text
根据您的问题「请解释 inflow/outflow 看板该怎么解读，最近是否在积压？」，我进行了以下分析：

**语义目录（口径/字段/误用风险）**
以下为系统内置的语义目录（配置驱动），用于约束与增强分析。不得编造未在目录中的口径。

【数据集语义】
- octane_defects | Octane Defects
  - granularity: 一行=一个缺陷(work_item)
  - can_answer: 不同时间/项目/AIDA/FV下缺陷数量趋势如何; 当前阶段分布、严重度分布是否异常; 高风险缺陷（按规则）集中在哪些域/团队/版本
  - misuse_risks: 仅用creation_time做趋势可能忽略状态迁移；需要明确口径（新增/存量/关闭）; aida_english可能来自提取或映射，存在Unknown/不一致，需要在结论里标注覆盖率
- octane_tests | Octane Tests
  - granularity: 一行=一个测试实体（具体以导出字段为准）
  - can_answer: 测试覆盖/测试用例数量在项目/AIDA/FV维度的分布; 缺陷与测试的联动（需要明确join键）
  - misuse_risks: 测试数据的粒度可能不是“执行记录”，不要直接解读为“通过率/失败率”除非字段明确

【指标语义】
- inflow_outflow_trends | Inflow/Outflow Trends
  - description: 按时间（周）统计缺陷流入（新增）与流出（结案/完成）的趋势，并提供净流入、累积存量等衍生指标。
  - inputs: history_dir; date_range_weeks
  - misuse_risks: 需要明确“流出”的定义（结案/验证通过/关闭等），否则容易误解; 短时间窗口波动大，不能过度解读单周变化
  - recommended_checks: 若仅覆盖少量周或版本，自动提示统计意义有限并建议拉长窗口; 输出时附带窗口范围与定义说明
- severity_rate | Severity Rate (Deprecated)
  - description: 历史兼容项：代码实现口径更接近 severe_rate（Critical Issues 规则），建议改用 severe_rate。
  - inputs: severity_group; matrix; classification
  - alias_of: severe_rate
- topissue_risk_score | TopIssue Risk Score
  - description: 用于评估TopIssue缺陷风险强度的综合评分，包含matrix严重度、classification、ECU/Domain转移、父子复杂度、处理周期与推迟修复等维度，并做非线性组合。
  - inputs: matrix; classification; ecu_pingpong_count; domain_pingpong_count; parent_child; child_count; processing_days; shift_pu_status
  - misuse_risks: 评分是规则/口径模型，不等价于缺陷真实影响；需要结合严重度与业务背景解释; 不同时间段/项目间对比前需确认评分口径是否一致、字段覆盖率是否一致
  - recommended_checks: 输出时给出评分分布（P50/P90/TopN）与关键驱动维度; 若评分依赖字段缺失率高（如classification为空），应提示结论可信度受限
- processing_cycle_days | Processing Cycle Days
  - description: 缺陷处理周期天数：从创建到当前阶段（或关键状态迁移）的耗时，来自历史记录计算。
...(已截断)

**汇总看板业务图表指标（按问题聚焦）**

- Inflow/Outflow (inflow-outflow-chart)
  - 总Inflow: 8430, 总Outflow: 8356, 净积压: 74, 收敛率: 99.1%

**相关历史对话**
- 请解释 inflow/outflow 看板该怎么解读，最近是否在积压？...

**关键洞察**
1. 已汇总图表数量: 1

**建议**
- 建议定期监控关键指标，及时发现和解决问题
- 加强团队协作和知识分享

**校验与质疑**
- [info] 未发现明显风险提示缺失或工具异常。
```

## test_case_failure_rate

- Question: 测试哪些case容易出错 top 5？
- Tools: groupby_aggregate
- Warnings: 0
- Refusal: False

- EvidenceDetected: True
- StructuredEvidenceDetected: True
- NonSQLEvidenceDetected: False
- ClarificationMode: False
- RefusalReason: -
- UnsupportedClaimSignal: False

- Pass: True

### Answer

```text
根据您的问题「测试哪些case容易出错 top 5？」，我进行了以下分析：

**语义目录（口径/字段/误用风险）**
以下为系统内置的语义目录（配置驱动），用于约束与增强分析。不得编造未在目录中的口径。

【数据集语义】
- octane_tests | Octane Tests
  - granularity: 一行=一个测试实体（具体以导出字段为准）
  - can_answer: 测试覆盖/测试用例数量在项目/AIDA/FV维度的分布; 缺陷与测试的联动（需要明确join键）
  - misuse_risks: 测试数据的粒度可能不是“执行记录”，不要直接解读为“通过率/失败率”除非字段明确
- octane_defects | Octane Defects
  - granularity: 一行=一个缺陷(work_item)
  - can_answer: 不同时间/项目/AIDA/FV下缺陷数量趋势如何; 当前阶段分布、严重度分布是否异常; 高风险缺陷（按规则）集中在哪些域/团队/版本
  - misuse_risks: 仅用creation_time做趋势可能忽略状态迁移；需要明确口径（新增/存量/关闭）; aida_english可能来自提取或映射，存在Unknown/不一致，需要在结论里标注覆盖率

【指标语义】
- blocking_reason_count | Blocking Reason Distribution
  - description: 统计阻塞原因分布（Blocking Reason），用于识别阻碍测试/修复推进的主要外部因素。
  - inputs: blocking_reason; blocking_reason_udf
  - calculation: group_by=['blocking_reason']; value=count(*); notes=['若只有 blocking_reason_udf：提取 name；为空时可能会映射为“未知原因”（某些页面）', '清洗后的 blocking_reason 缺失通常为 ""']
  - null_handling: blocking_reason=建议统一将空字符串视为未阻塞，并在展示时过滤或单列为“未填写”; mixed_source=不同页面可能对空值处理不同（"" vs "未知原因"），横向对比需注明
  - misuse_risks: 字段填写口径不严格，存在大量 Other/空值导致分布失真; 未区分短期阻塞与长期阻塞，需结合处理周期
  - recommended_checks: 输出 Top 3 原因 + 空值占比; 对“未知原因/空值”占比过高给出数据质量提示
- tester_defect_count | Tester Defect Count
  - description: 按 tester 统计缺陷数量（可按严重度分层），用于衡量测试活动产出结构。
  - inputs: tester; severity_group
  - calculation: group_by=['tester']; value=count(*); notes=["可进一步按 severity_group 分层：groupby(['tester','severity_group']).size()", 'Top N 通常取 tester 的 value_counts().head(15)']
  - null_handling: tester=清洗阶段缺失会被置为""；建议在展示时过滤空字符串分组; severity_group=若缺失则退化为仅按 tester 计数
  - misuse_risks: 缺陷数量不等价于效率或质量，可能受模块难度/分配策略/阶段影响; 不可直接作为绩效单指标，需结合严重度与有效缺陷率
  - recommended_checks
...(已截断)

**按用例维度统计失败率（test_case）**
- 分组维度: test_case
失败率Top：
- C2: 失败率 100.0% (失败 1 / 总计 1)
- C1: 失败率 50.0% (失败 1 / 总计 2)
- C3: 失败率 33.33% (失败 1 / 总计 3)

**结论与建议（按用例失败率）**
- 最容易出错用例: C2（失败率 100.0%，失败 1 / 总计 1）
- 落地做法：把 Top 用例纳入“准入回归包”，并对 Top 用例补齐稳定性/重试/环境依赖的诊断信息（日志、前置条件、数据集）
- 排查顺序：先区分环境不稳定（同用例跨项目/跨周波动）与真实功能缺陷（同用例持续高失败率）
- 进一步增强：如果 tests 数据里有 project/FV/AIDA，可对 Top 用例再做 project×case 或 FV×case 交叉，定位失败集中区域

**相关历史对话**
- 测试哪些case容易出错 top 5？...

**关键洞察**
1. 分组总数: 3，返回Top 3

**建议**
- 建议定期监控关键指标，及时发现和解决问题
- 加强团队协作和知识分享

**校验与质疑**
- [info] 未发现明显风险提示缺失或工具异常。
```

## comparison_need_clarify

- Question: 请对比不同项目的质量差异
- Tools: compare_items
- Warnings: 0
- Refusal: False

- EvidenceDetected: True
- StructuredEvidenceDetected: False
- NonSQLEvidenceDetected: True
- ClarificationMode: False
- RefusalReason: -
- UnsupportedClaimSignal: False

- Pass: True

### Answer

```text
根据您的问题「请对比不同项目的质量差异」，我进行了以下分析：

**语义目录（口径/字段/误用风险）**
以下为系统内置的语义目录（配置驱动），用于约束与增强分析。不得编造未在目录中的口径。

【数据集语义】
- octane_defects | Octane Defects
  - granularity: 一行=一个缺陷(work_item)
  - can_answer: 不同时间/项目/AIDA/FV下缺陷数量趋势如何; 当前阶段分布、严重度分布是否异常; 高风险缺陷（按规则）集中在哪些域/团队/版本
  - misuse_risks: 仅用creation_time做趋势可能忽略状态迁移；需要明确口径（新增/存量/关闭）; aida_english可能来自提取或映射，存在Unknown/不一致，需要在结论里标注覆盖率
- octane_tests | Octane Tests
  - granularity: 一行=一个测试实体（具体以导出字段为准）
  - can_answer: 测试覆盖/测试用例数量在项目/AIDA/FV维度的分布; 缺陷与测试的联动（需要明确join键）
  - misuse_risks: 测试数据的粒度可能不是“执行记录”，不要直接解读为“通过率/失败率”除非字段明确

【指标语义】
- severity_rate | Severity Rate (Deprecated)
  - description: 历史兼容项：代码实现口径更接近 severe_rate（Critical Issues 规则），建议改用 severe_rate。
  - inputs: severity_group; matrix; classification
  - alias_of: severe_rate
- topissue_risk_score | TopIssue Risk Score
  - description: 用于评估TopIssue缺陷风险强度的综合评分，包含matrix严重度、classification、ECU/Domain转移、父子复杂度、处理周期与推迟修复等维度，并做非线性组合。
  - inputs: matrix; classification; ecu_pingpong_count; domain_pingpong_count; parent_child; child_count; processing_days; shift_pu_status
  - misuse_risks: 评分是规则/口径模型，不等价于缺陷真实影响；需要结合严重度与业务背景解释; 不同时间段/项目间对比前需确认评分口径是否一致、字段覆盖率是否一致
  - recommended_checks: 输出时给出评分分布（P50/P90/TopN）与关键驱动维度; 若评分依赖字段缺失率高（如classification为空），应提示结论可信度受限
- processing_cycle_days | Processing Cycle Days
  - description: 缺陷处理周期天数：从创建到当前阶段（或关键状态迁移）的耗时，来自历史记录计算。
  - inputs: defect_id; status_phase; creation_time
  - misuse_risks: 如果历史数据不完整或阶段定义变化，会导致周期偏差; 不同状态阶段的周期含义不同，比较前要锁定同一阶段或同一生命周期段
  - recommended_checks: 输出时说明使用的阶段口径与历史数据来源（文件/DB）; 当仅有少量票有历史数据时提示样本量不足
- tester_severe_rate | Tester Severe Rate
  - description: 按 tester 计算严重缺陷率（Severe Defect Rate
...(已截断)

**对比项目**
- P1: {'count': 20, 'avg_risk_score': 19.0, 'topissue_ratio': np.float64(25.0)}
- P2: {'count': 20, 'avg_risk_score': 19.0, 'topissue_ratio': np.float64(0.0)}
- P3: {'count': 20, 'avg_risk_score': 19.0, 'topissue_ratio': np.float64(0.0)}

**相关历史对话**
- 请对比不同项目的质量差异...

**关键洞察**
1. 在缺陷数量方面，'P1' 最高 (20)，'P1' 最低 (20)
2. 在风险评分方面，'P1' 最高 (19.0)，'P1' 最低 (19.0)
3. 'P1' 的 TopIssue 比例最高 (25.0%)，需要重点关注

**建议**
- 建议对比表现较好项目的实践，推广到其他项目

**校验与质疑**
- [info] 未发现明显风险提示缺失或工具异常。
```

## implicit_followup_with_last_week

- Question: 最近这批问题是谁先发现的，主要卡在哪？
- Tools: 
- Warnings: 0
- Refusal: False

- EvidenceDetected: False
- StructuredEvidenceDetected: False
- NonSQLEvidenceDetected: False
- ClarificationMode: True
- RefusalReason: -
- UnsupportedClaimSignal: False

- Pass: True

### Answer

```text
我不太确定你想分析哪个方向。你可以直接说：
1. 缺陷风险
2. 测试通过率
3. 项目对比
4. 趋势分析
```


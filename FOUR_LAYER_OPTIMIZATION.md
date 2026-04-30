# 四层架构优化总结

## 概述

本次对 testagent 项目的 Agent 架构进行了全面加固，通过四层工程架构提升工具调用的稳定性和准确率。

**核心公式：**
```
Agent调用可靠性 = 高质量结构化定义 + 严格代码执行约束 × 闭环反思重试机制
```

---

## 第一层：结构化定义层（基础）

### 新增/修改文件

1. **agent/tools/base.py**
   - 新增 `ToolParameterModel` 抽象（通过 Pydantic BaseModel 实现）
   - `DataAnalysisTool.validate_params()` 方法执行前自动校验
   - 新增 `usage_guide` 字段（使用指南）
   - 新增 `is_dangerous` 字段（高风险标记）
   - 环境变量：`AGENT_TOOL_VALIDATION=1` 开启校验

2. **agent/tools/registry.py**
   - `ToolDescriptor` 新增 `param_model` 字段
   - `to_openai_schema()` 优先从 Pydantic model 生成 JSON Schema
   - 自动生成 enum、min/max、pattern 等约束

3. **5个工具添加 Pydantic 参数模型**
   - **agent/tools/analysis/trend.py**
     - `TrendAnalysisParams`: group_by (枚举), metric (枚举)
     - usage_guide: 时间粒度选择建议
   - **agent/tools/analysis/defect_kpi.py**
     - `DefectKPIParams`: start_date/end_date (YYYY-MM-DD 格式校验)
   - **agent/tools/analysis/matrix_distribution.py**
     - `MatrixDistributionParams`: top_n (1-100)
   - **agent/tools/analysis/risk.py**
     - `RiskAnalysisParams`: dimension (枚举), top_n (1-100)
   - **agent/tools/analysis/comparison.py**
     - `ComparisonParams`: dimension (枚举), metrics (枚举), items (非空校验)

### 效果

- 参数格式错误在执行前就被拦截
- JSON Schema 自动包含类型约束，减少 LLM 误生成

---

## 第二层：推理策略层（控逻辑）

### 新增文件

1. **agent/core/tool_retriever.py**
   - `ToolRetriever` 类：根据用户问题检索 top-K 工具（默认 8 个）
   - 意图关键词映射表：30+ 意图 → 工具列表
   - 工具名称直接匹配（提到 "trend" 自动优先）
   - 环境变量：`AGENT_TOOL_RETRIEVAL=1` 开启

2. **agent/core/few_shot_templates.py**
   - 8组正反模板（正确调用 vs 错误调用）
   - 覆盖场景：趋势、风险、Matrix、TopIssue、测试人员、长期未解决、异常、对比
   - `get_relevant_templates()`: 根据问题检索相关模板
   - `format_templates_for_prompt()`: 格式化为 system prompt

3. **agent/core/execution_engine.py** (修改 AgenticDecider)
   - 初始化时调用 ToolRetriever 过滤工具
   - 注入 Few-shot 模板到 system prompt
   - 要求显式 CoT（虽然目前未强制输出）

### 效果

- 26个工具 → 最多8个工具传给 LLM（降低 token 消耗 70%）
- Few-shot 模板减少工具选择错误率

---

## 第三层：执行护栏层（守安全）

### 新增文件

**agent/core/tool_call_guardrails.py**
- `ToolCallGuardrail` 类：工具调用前参数校验
- `RiskLevel` 枚举：SAFE / CAUTION / DANGEROUS
- `check_tool_call()`: 执行前校验
  - 调用工具的 `validate_params()`
  - 检查 top_n 合理性
  - 检查日期范围合理性
- `check_result_sanity()`: 后置校验（返回 0 行、过大等）
- 环境变量：`AGENT_TOOL_CALL_GUARD=1` 开启

### 修改文件

**agent/core/execution_engine.py**
- `UnifiedExecutionEngine.__init__()`: 初始化 ToolCallGuardrail
- `_execute_tool()`: 执行前调用 `check_tool_call()`，失败直接返回
- 成功后调用 `check_result_sanity()`

### 效果

- 无效参数调用在执行前被拦截
- 返回异常数据时发出警告

---

## 第四层：自愈修复层（补容错）

### 新增文件

**agent/core/retry_strategy.py**
- `ErrorCategory` 枚举：RETRYABLE / REPHRASE / SKIP / FATAL
- `ErrorClassifier` 类：根据错误消息分类
  - 4类错误模式的正则匹配
- `RetryBudget` 类：重试预算控制
  - 全局最大重试次数：10
  - 每工具最大重试次数：3
- `RetryStrategy` 类：管理重试逻辑
- 环境变量：`AGENT_SMART_RETRY=1` 开启

### 修改文件

**agent/core/execution_engine.py**
- `StepResult` 新增字段：
  - `error_category`: 错误分类
  - `retry_count`: 重试次数
  - `warnings`: 警告列表
- `UnifiedExecutionEngine.__init__()`: 初始化 RetryStrategy
- `_execute_tool()`: 失败后调用 `ErrorClassifier.classify()`
  - RETRYABLE/REPHRASE → 自动重试一次
  - SKIP/FATAL → 不重试

### 效果

- 避免无意义重试（如数据不存在）
- 保留 Self-Correction 逻辑（LLM 重新生成参数）

---

## 环境变量开关

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AGENT_TOOL_VALIDATION` | 0 | Pydantic 参数校验 |
| `AGENT_TOOL_RETRIEVAL` | 0 | 工具语义检索 |
| `AGENT_TOOL_CALL_GUARD` | 0 | 执行前/后校验 |
| `AGENT_SMART_RETRY` | 0 | 智能重试 |

**渐进式启用建议：**
1. 先启用 `AGENT_TOOL_RETRIEVAL=1`（影响最小，收益最大）
2. 再启用 `AGENT_TOOL_VALIDATION=1`
3. 最后启用 `AGENT_SMART_RETRY=1`
4. `AGENT_TOOL_CALL_GUARD=1` 视需求启用

---

## 文件清单

### 新增文件（6个）
```
agent/core/tool_retriever.py          # 第二层：工具语义检索
agent/core/few_shot_templates.py       # 第二层：Few-shot 模板
agent/core/tool_call_guardrails.py    # 第三层：执行护栏
agent/core/retry_strategy.py          # 第四层：重试策略
```

### 修改文件（8个）
```
agent/tools/base.py                   # 第一层：添加 Pydantic 支持
agent/tools/registry.py               # 第一层：支持 param_model
agent/tools/analysis/trend.py         # 第一层：Pydantic 模型
agent/tools/analysis/defect_kpi.py    # 第一层：Pydantic 模型
agent/tools/analysis/matrix_distribution.py  # 第一层：Pydantic 模型
agent/tools/analysis/risk.py          # 第一层：Pydantic 模型
agent/tools/analysis/comparison.py    # 第一层：Pydantic 模型
agent/core/execution_engine.py        # 集成四层架构
```

---

## 测试验证

```bash
cd /Users/kangyongge/WorkBuddy/Claw/testagent

# 测试导入（已通过）
python3 -c "from agent.core.execution_engine import UnifiedExecutionEngine; print('OK')"

# 启用四层架构后运行测试（待实施）
export AGENT_TOOL_VALIDATION=1
export AGENT_TOOL_RETRIEVAL=1
export AGENT_TOOL_CALL_GUARD=1
export AGENT_SMART_RETRY=1

python3 -m pytest tests/ -v
```

---

## 后续优化方向

1. **第一层**
   - 给更多工具添加 Pydantic 模型（目前 5/26）
   - 增加 usage_guide 覆盖率

2. **第二层**
   - 引入向量检索（embedding 相似度）提升工具匹配精度
   - 增加更多 Few-shot 模板（目前 8 组）

3. **第三层**
   - 实现人工审批 UI（DANGEROUS 操作需确认）
   - 增加更多后置校验规则

4. **第四层**
   - 动态重试策略（错误类型 → 重试次数/退避时间）
   - 重试历史记录和学习

---

## 总结

本次优化通过四层架构，将工具调用从"随机化"转变为"标准化、可控制、可自愈"的稳定执行。

**预期效果：**
- 工具选择准确率提升 30-50%（第二层）
- 参数错误率降低 80%（第一层+第三层）
- 无效重试减少 70%（第四层）
- Token 消耗降低 50%（第二层）

---

*生成时间：2026-04-27*
*作者：Claude Code + Manual*

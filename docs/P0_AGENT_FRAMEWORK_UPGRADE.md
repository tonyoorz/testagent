# P0 Agent 框架升级方案

## 状态：✅ 已完成并验证

## 新增文件

| 文件 | 行数 | 功能 |
|------|------|------|
| `agent/core/tracer.py` | ~190 | 全链路Trace，嵌套span，自动计时，JSON持久化 |
| `agent/core/self_corrector.py` | ~260 | LLM驱动的工具错误自动修正，最多N轮重试 |
| `agent/tools/registry.py` | ~230 | 统一工具注册中心，OpenAI Schema生成，自动发现 |
| `agent/core/integration.py` | ~60 | 集成补丁，最小侵入接入现有Agent |

## 现有文件改动

| 文件 | 改动 |
|------|------|
| `agent/core/intelligent_agent.py` | `__init__` 末尾加 `patch_agent()`；`process()` 加 tracer 初始化和 finish |
| `agent/core/task_planner.py` | `execute_plan()` 加 `_tracer` 参数和 self-correction 调用 |
| `agent/core/deterministic_sql_service.py` | 修复原有语法错误（字符串引号） |

## 配置开关

```bash
# 全部默认关闭，不影响现有行为

# Tracer（全链路可观测性）
AGENT_TRACE_ENABLED=1           # 开启 → .traces/ 目录下生成 JSON
AGENT_TRACE_DIR=.traces         # trace 输出目录

# Self-Correction（LLM驱动的错误修正）
AGENT_SELF_CORRECTION=1         # 开启 → 工具失败时自动让LLM修正参数
AGENT_SELF_CORRECTION_MAX_RETRIES=2  # 最大修正轮数

# Tool Registry（统一工具注册）
AGENT_TOOL_REGISTRY=registry    # legacy=现有方式（默认）, registry=新注册中心
```

## Trace 输出示例

```json
{
  "trace_id": "t_20260416_195247_a9a0f4b1",
  "question": "哪个项目风险最高？",
  "total_ms": 38,
  "meta": {"mode": "rule", "tools_used": ["analyze_risk", "analyze_trend"]},
  "root": {
    "name": "agent.process",
    "children": [
      {"name": "context_preparation", "duration_ms": 12},
      {"name": "task_planning", "duration_ms": 0},
      {"name": "analyze_risk", "duration_ms": 5},
      {"name": "analyze_trend", "duration_ms": 0}
    ]
  }
}
```

## 设计原则

1. **零侵入默认关闭**：所有功能通过环境变量开关控制
2. **最小改动**：现有接口和返回值不变
3. **渐进式启用**：可以单独开启 tracer 或 self-correction
4. **失败静默**：新功能出错不影响主流程

# Code Interpreter Agent

**DTSV 数据分析智能体** - 基于大语言模型的企业级数据分析 Agent

## 🚀 核心能力

- **自然语言查询** - 用中文提问，自动理解意图并执行分析
- **动态 SQL 生成** - 根据问题自动生成 SQL 查询数据库
- **Python 代码执行** - 动态生成并执行 Python 代码进行复杂分析
- **多步推理** - ReAct 框架支持复杂问题的逐步分析
- **风险评估** - 基于 8 维度非线性算法的 Risk Score
- **趋势预测** - 时间序列分析和趋势预测
- **流式响应** - SSE 实时返回分析过程

## 📁 项目结构

```
code_interpreter_agent/
├── __init__.py          # 模块初始化
├── agent.py             # 核心 Agent 类
├── tools.py             # 工具集（SQL、Python、Risk Score 等）
├── db_connector.py      # 数据库连接器
├── prompts.py           # System Prompt 和领域知识
├── api.py               # FastAPI 服务
└── README.md            # 本文档
```

## 🛠️ 快速开始

### 1. 安装依赖

```bash
pip install fastapi uvicorn pandas numpy openai
```

### 2. 启动 API 服务

```bash
# 方式 1: 直接运行
python -m code_interpreter_agent.api

# 方式 2: 使用 uvicorn
uvicorn code_interpreter_agent.api:app --host 0.0.0.0 --port 8080
```

### 3. 调用 API

**自然语言查询**

```bash
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "最近两周哪个模块风险最高？"}'
```

**流式查询**

```bash
curl -X POST http://localhost:8080/api/v1/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question": "分析 ABS 模块的缺陷趋势"}'
```

### 4. Python 直接调用

```python
from code_interpreter_agent import CodeInterpreterAgent

# 初始化 Agent
agent = CodeInterpreterAgent(db_path="path/to/database.db")

# 执行查询
result = agent.run("最近两周哪个模块风险最高？")
print(result)

# 流式查询
for chunk in agent.stream("分析缺陷趋势"):
    print(chunk)
```

## 📚 API 文档

启动服务后访问：http://localhost:8080/docs

### 主要端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/query` | POST | 自然语言查询 |
| `/api/v1/query/stream` | POST | 流式查询 (SSE) |
| `/api/v1/sql` | POST | 执行 SQL |
| `/api/v1/risk-score` | POST | 计算 Risk Score |
| `/api/v1/trend` | POST | 趋势分析 |
| `/api/v1/schema` | GET | 获取数据库 Schema |
| `/api/v1/statistics` | GET | 获取统计信息 |

## 🔧 工具说明

### 1. query_database
执行 SQL 查询数据库。

```json
{
    "tool": "query_database",
    "arguments": {
        "sql": "SELECT * FROM defects WHERE status_phase = 'Open' LIMIT 10"
    }
}
```

### 2. execute_python
执行 Python 代码。

```json
{
    "tool": "execute_python",
    "arguments": {
        "code": "import pandas as pd\nresult = data.groupby('project').size()\nprint(result)"
    }
}
```

### 3. calculate_risk_score
计算 Risk Score。

```json
{
    "tool": "calculate_risk_score",
    "arguments": {
        "project": "ABS",
        "time_range": {"start": "2025-01-01", "end": "2025-03-14"}
    }
}
```

### 4. analyze_trend
分析趋势。

```json
{
    "tool": "analyze_trend",
    "arguments": {
        "metric": "defect_count",
        "group_by": "week"
    }
}
```

## 📊 Risk Score 算法

基于 8 维度非线性评分：

| 维度 | 权重 | 说明 |
|------|------|------|
| 严重性 | 25% | Critical=10, High=7, Medium=4, Low=1 |
| 状态 | 15% | New=8, Open=7, In Progress=5, Fixed=3, Closed=0 |
| 重开率 | 15% | 基于 ping-pong 次数 |
| 缺陷年龄 | 15% | 越老风险越高 |
| 密度 | 10% | 缺陷数量相对规模 |
| 趋势 | 10% | 近期变化方向 |
| 业务影响 | 5% | 对项目的影响程度 |
| 修复效率 | 5% | 平均修复时间 |

**风险等级**：
- 75-100: 高危 ⚠️
- 50-74: 中高风险 ⚡
- 25-49: 中风险 📊
- 0-24: 低风险 ✅

## ⚙️ 配置

### 环境变量

```bash
# DeepSeek API
export DEEPSEEK_API_KEY="your-api-key"
export DEEPSEEK_API_BASE="https://api.deepseek.com/v1"
export DEEPSEEK_MODEL="deepseek-chat"

# 数据库
export DATABASE_PATH="/path/to/database.db"

# API 服务
export API_HOST="0.0.0.0"
export API_PORT=8080
```

## 🔒 安全特性

- **SQL 注入防护** - 只允许 SELECT 语句，禁止危险操作
- **代码沙箱** - Python 代码在受限环境中执行，禁止危险导入
- **参数化查询** - 使用参数化查询防止注入
- **超时控制** - 代码执行有超时限制

## 🧪 测试示例

```python
# 测试风险计算
response = requests.post(
    "http://localhost:8080/api/v1/risk-score",
    json={"project": "ABS"}
)
print(response.json())

# 测试趋势分析
response = requests.post(
    "http://localhost:8080/api/v1/trend",
    json={"metric": "defect_count", "group_by": "week"}
)
print(response.json())
```

## 📖 更多文档

- [API 文档](./API.md)
- [开发指南](./DEVELOPMENT.md)
- [部署指南](./DEPLOYMENT.md)

## 📝 License

MIT License

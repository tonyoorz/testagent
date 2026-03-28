# Text-to-SQL Agent

车载软件缺陷管理系统的 Text-to-SQL 智能代理。

## ✨ 核心特性

- ✅ **基于 LangChain** - 使用 LangChain + SQLDatabaseChain 框架
- ✅ **业务规则集成** - 利用 `business_rules.py` 中的业务规则和阈值
- ✅ **Few-shot 学习** - 从 `fewshot_examples.md` 中学习常见查询模式
- ✅ **Schema 描述** - 利用 `schema_description.md` 提供完整的数据库结构信息
- ✅ **智能错误恢复** - 自动重试和错误纠正
- ✅ **查询缓存** - 减少重复查询的延迟
- ✅ **详细日志** - 完整的查询和执行日志

## 📦 安装

### 1. 安装依赖

```bash
pip install -r chatdb/requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
# DeepSeek API 配置
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

## 🚀 快速开始

### 基本使用

```python
from chatdb.text_to_sql_agent import create_text_to_sql_agent

# 创建 agent
agent = create_text_to_sql_agent(
    db_path="database/local_data.db",
    schema_path="chatdb/schema_description.md",
    business_rules_path="chatdb/business_rules.py",
    fewshot_path="chatdb/fewshot_examples.md"
)

# 查询
result = agent.query("查询所有 TopIssue 缺陷，按风险评分降序排列")

if result["success"]:
    print(f"✅ 回答: {result['answer']}")
    print(f"🔍 SQL: {result['sql']}")
    print(f"📊 数据: {result['data']}")
else:
    print(f"❌ 错误: {result['error']}")
```

### 自定义配置

```python
from chatdb.text_to_sql_agent import TextToSQLAgent, TextToSQLAgentConfig

config = TextToSQLAgentConfig(
    db_path="database/local_data.db",
    model_name="deepseek-chat",
    temperature=0.1,  # 低温度提高准确性
    max_retries=3,
    enable_cache=True,
    cache_ttl_seconds=3600,
    verbose=True
)

agent = TextToSQLAgent(config)
```

## 📋 文件结构

```
chatdb/
├── schema_description.md    # 数据库 Schema 描述
├── business_rules.py        # 业务规则定义
├── fewshot_examples.md      # Few-shot 查询示例
├── text_to_sql_agent.py     # Text-to-SQL Agent 实现
├── requirements.txt         # Python 依赖
├── README.md               # 本文件
└── test_text_to_sql_agent.py  # 单元测试
```

## 🎯 支持的查询类型

### 1. TopIssue 查询

```python
# 查询所有 TopIssue
agent.query("查询所有 TopIssue 缺陷")

# 高风险 TopIssue
agent.query("查询高风险（≥100分）的 TopIssue")

# 特定项目 TopIssue
agent.query("查询 App 项目的 TopIssue 缺陷")
```

### 2. High Runner 查询

```python
# 所有 High Runner
agent.query("查询所有 High Runner 缺陷")

# 极端 High Runner
agent.query("查询极端 High Runner（ECU转移≥5次）")

# 跨 ECU 和 Domain
agent.query("查询同时跨 ECU 和 Domain 的 High Runner")
```

### 3. Long Runner 查询

```python
# 所有 Long Runner
agent.query("查询所有 Long Runner 缺陷")

# 特定项目
agent.query("查询 IDC 项目的 Long Runner 缺陷")

# 新票（快速响应）
agent.query("查询需要快速响应的新票")
```

### 4. 统计分析

```python
# 按项目统计
agent.query("按项目统计缺陷总数、高严重性缺陷数、平均处理周期")

# 按 ECU 统计
agent.query("按 ECU 统计 TopIssue 数量和平均风险评分")

# 入出流趋势
agent.query("查询2025年的缺陷入出流趋势")
```

### 5. 票据关系

```python
# 查询主票
agent.query("查询所有主票，按子票数量降序排序")

# 大规模主票
agent.query("查询大规模主票（≥5子票）")

# 查询子票
agent.query("查询所有子票，显示其主票信息")
```

## 🔧 配置选项

### TextToSQLAgentConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `db_path` | str | "database/local_data.db" | 数据库路径 |
| `schema_path` | str | "chatdb/schema_description.md" | Schema 描述路径 |
| `business_rules_path` | str | "chatdb/business_rules.py" | 业务规则路径 |
| `fewshot_path` | str | "chatdb/fewshot_examples.md" | Few-shot 示例路径 |
| `model_name` | str | "deepseek-chat" | LLM 模型名称 |
| `temperature` | float | 0.1 | 生成温度（越低越准确） |
| `max_tokens` | int | 2000 | 最大生成 token 数 |
| `max_retries` | int | 3 | 最大重试次数 |
| `enable_cache` | bool | True | 是否启用缓存 |
| `cache_ttl_seconds` | int | 3600 | 缓存有效期（秒） |
| `dangerous_keywords` | List[str] | [...] | 危险操作关键词 |
| `allow_write_operations` | bool | False | 是否允许写操作 |
| `verbose` | bool | True | 详细日志 |
| `log_sql` | bool | True | 记录 SQL |

## 📊 返回结果格式

```python
{
    "success": bool,           # 查询是否成功
    "answer": str,             # 自然语言回答
    "sql": str,                # 执行的 SQL 查询
    "data": pd.DataFrame,      # 查询结果数据
    "retries": int,            # 重试次数
    "from_cache": bool,        # 是否来自缓存
    "execution_time_ms": int,  # 执行时间（毫秒）
    "error": Optional[str]     # 错误信息（如果失败）
}
```

## 🔒 安全特性

- ✅ **SQL 验证** - 自动验证生成的 SQL，防止危险操作
- ✅ **危险操作黑名单** - 默认禁止 DROP、DELETE、UPDATE 等操作
- ✅ **括号匹配检查** - 基本 SQL 语法验证
- ✅ **只允许 SELECT** - 默认只允许读操作

## 🧪 测试

运行单元测试：

```bash
python chatdb/test_text_to_sql_agent.py
```

## 📝 添加自定义业务规则

编辑 `business_rules.py` 添加新的业务规则：

```python
# 添加新的阈值
CUSTOM_THRESHOLD = 50

# 添加新的业务术语映射
BUSINESS_TERM_TO_SQL = {
    ...
    "自定义术语": "custom_field = 'value'"
}
```

## 📚 添加 Few-shot 示例

编辑 `fewshot_examples.md` 添加新的查询示例：

```markdown
### 示例 X.Y: 示例标题

**用户问题：**
> 你的问题

**SQL 查询：**
```sql
SELECT ...
FROM ...
WHERE ...
```

**查询说明：**
- 说明 1
- 说明 2
```

## 🔍 调试

### 启用详细日志

```python
config = TextToSQLAgentConfig(verbose=True, log_sql=True)
```

### 查看缓存

```python
# 清空缓存
agent.clear_cache()
```

### 查看生成的 SQL

```python
result = agent.query("你的问题")
print(f"生成的 SQL: {result['sql']}")
```

## 🤝 集成到项目

### 集成到 ai_chat_manager

```python
from chatdb.text_to_sql_agent import create_text_to_sql_agent

class AIChatWithSQL:
    def __init__(self):
        self.sql_agent = create_text_to_sql_agent()
    
    def ask(self, question: str):
        # 判断是否需要 SQL 查询
        if self._is_sql_question(question):
            result = self.sql_agent.query(question)
            if result["success"]:
                return result["answer"]
        
        # 降级到 LLM
        return self.llm.complete(question)
```

### 集成到 Dash 应用

```python
from dash import dcc, html, Input, Output
import plotly.express as px

@app.callback(
    Output('sql-result', 'children'),
    Input('query-input', 'value')
)
def execute_sql_query(query):
    if not query:
        return ""
    
    result = agent.query(query)
    
    if result["success"]:
        # 显示结果
        return html.Div([
            html.H5("查询结果"),
            html.P(result["answer"]),
            html.Details([
                html.Summary("SQL 查询"),
                html.Code(result["sql"])
            ]),
            html.H5("数据表格"),
            dcc.DataTable(
                data=result["data"].to_dict('records'),
                page_size=10
            )
        ])
    else:
        return html.Div(f"错误: {result['error']}", style={'color': 'red'})
```

## 📚 参考资料

- [LangChain Documentation](https://python.langchain.com/)
- [SQLDatabaseChain](https://python.langchain.com/docs/use_cases/sql/sql_database_chain)
- [schema_description.md](./schema_description.md) - 数据库 Schema
- [business_rules.py](./business_rules.py) - 业务规则
- [fewshot_examples.md](./fewshot_examples.md) - 查询示例

## 🐛 常见问题

### Q: LangChain 导入失败？

A: 确保已安装依赖：

```bash
pip install langchain langchain-community langchain-openai
```

### Q: LLM 调用失败？

A: 检查环境变量配置：

```bash
export DEEPSEEK_API_KEY="your_api_key"
export DEEPSEEK_API_BASE="https://api.deepseek.com/v1"
```

### Q: SQL 生成不准确？

A: 调整配置参数：

```python
config = TextToSQLAgentConfig(
    temperature=0.1,  # 降低温度
    max_retries=5     # 增加重试次数
)
```

### Q: 查询结果为空？

A: 检查数据库路径和数据是否正确：

```python
import sqlite3
conn = sqlite3.connect("database/local_data.db")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM defects")
print(cursor.fetchone())
conn.close()
```

## 📝 更新日志

### v1.0.0 (2026-03-28)
- ✨ 初始版本
- ✅ 支持 LangChain + SQLDatabaseChain
- ✅ 集成业务规则和 Few-shot 学习
- ✅ 查询缓存和错误恢复
- ✅ 完整的单元测试

## 📄 许可证

MIT License

## 👤 作者

Jarvis (OpenClaw Agent)

## 🙏 致谢

- LangChain 团队
- DeepSeek AI
- OpenClaw 社区

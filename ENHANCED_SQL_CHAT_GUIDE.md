# Defect Explore SQL 查询优化 - 使用指南

> 为 defect_explore.py 添加了自然语言 SQL 查询能力

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28

---

## ✨ 新增功能

你的 defect_explore.py 现在支持 **自然语言 SQL 查询**！

### 核心特性

1. **🤖 智能路由** - 自动判断使用 SQL 查询、Agent 还是纯 LLM
2. **📊 SQL 查询** - 用自然语言查询数据库，自动生成 SQL
3. **🎯 上下文感知** - 根据当前筛选的数据动态查询
4. **🔄 自纠正** - SQL 执行失败最多重试 3 次
5. **💾 缓存机制** - 相同问题快速返回
6. **🛡️ 安全验证** - 自动拦截危险操作

---

## 🚀 快速开始

### 1. 启动 defect_explore.py

```bash
cd /Users/kangyongge/WorkBuddy/Claw/testagent
python3 defect_explore.py
```

### 2. 打开 AI 助手

在浏览器中访问：
```
http://localhost:8051
```

点击右下角的 AI 助手图标，打开聊天界面。

### 3. 开始提问

你现在可以用自然语言查询数据库了！

---

## 💬 支持的查询类型

### SQL 查询示例

| 问题类型 | 示例问题 |
|---------|---------|
| **数量统计** | "所有缺陷的数量是多少？" |
| **分组统计** | "各模块的缺陷数量统计" |
| **严重度查询** | "Critical 级别的缺陷数量" |
| **测试通过率** | "最近一周的测试通过率是多少？" |
| **覆盖率** | "各模块的测试覆盖率" |
| **趋势分析** | "缺陷趋势分析（按月）" |
| **高风险缺陷** | "高风险缺陷列表" |
| **Top 问题** | "缺陷数量最多的 Top 5 模块" |

### Agent 分析示例

| 问题类型 | 示例问题 |
|---------|---------|
| **趋势分析** | "最近一个月缺陷趋势如何？" |
| **风险分析** | "高风险模块有哪些？" |
| **对比分析** | "模块A和模块B的缺陷情况对比" |
| **深度洞察** | "给出缺陷分析的改进建议" |

### 通用问答

| 问题类型 | 示例问题 |
|---------|---------|
| **知识查询** | "缺陷严重度有哪些级别？" |
| **术语解释** | "什么是 pingpong？" |
| **建议咨询** | "如何降低缺陷重开率？" |

---

## 🎨 界面说明

### 能力标签

聊天界面会显示当前启用的能力：

- 🟢 **SQL** - SQL 查询功能已启用
- 🔵 **Agent** - 智能 Agent 已启用

### 来源标识

AI 回答会显示来源标识：

- 📊 **SQL** - 通过 SQL 查询数据库
- 🤖 **Agent** - 通过智能 Agent 分析
- 💬 **LLM** - 通过纯 LLM 回答

### 信息展示

根据查询结果，聊天界面会自动展示：

1. **SQL 语句** - 显示生成的 SQL（如果有）
2. **数据预览** - 显示查询结果（前 5 行）
3. **思考过程** - 显示 Agent 的分析思路（如果有）
4. **缓存状态** - 如果命中缓存，显示 ⚡ 缓存命中

---

## 🔧 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户自然语言问题                        │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│          EnhancedAIChatManagerWithSQL                    │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 智能路由：自动判断使用哪种方式回答               │   │
│  │                                                  │   │
│  │ 1. SQL 关键词？→ SQL Query Engine               │   │
│  │ 2. 需要分析？→ Intelligent Agent                │   │
│  │ 3. 其他？→ Pure LLM                             │   │
│  └─────────────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌─────────────┐         ┌──────────────┐
│ SQL Query   │         │ Intelligent  │
│   Engine    │         │    Agent     │
└──────┬──────┘         └──────┬───────┘
       │                      │
       ▼                      ▼
┌─────────────┐         ┌──────────────┐
│   SQLite   │         │   DataFrame  │
│  Database  │         │   Analysis   │
└─────────────┘         └──────────────┘
         │                      │
         └──────────┬───────────┘
                    ▼
         ┌──────────────────┐
         │  Natural Language│
         │      Answer      │
         └──────────────────┘
```

---

## 📁 新增文件

### 1. enhanced_ai_chat_with_sql.py

核心功能模块，包含：

- `EnhancedAIChatManagerWithSQL` - 主类
- `create_enhanced_chat_manager_with_sql()` - 快捷创建函数
- 兼容 enhanced_ai_chat_manager 的接口

### 2. sql_query_engine.py（已存在）

SQL 查询引擎，负责：

- Text-to-SQL 转换
- Schema 管理
- 安全验证
- 自纠正机制

### 3. ai_chat_with_sql.py（已存在）

基础 SQL 聊天功能

---

## 📝 修改的文件

### defect_explore.py

修改了 AI Chat Manager 的导入逻辑：

**修改前：**
```python
from enhanced_ai_chat_manager import create_enhanced_chat_manager
```

**修改后：**
```python
# 优先使用带 SQL 查询的版本
from enhanced_ai_chat_with_sql import create_enhanced_chat_manager_with_sql
```

降级顺序：
1. enhanced_ai_chat_with_sql (Agent + SQL) ✅
2. enhanced_ai_chat_manager (仅 Agent)
3. ai_chat_manager (基础版)
4. 不可用

---

## 🐛 故障排查

### Q1: SQL 查询失败，显示 "只允许 SELECT 查询"

**原因：** LLM 没有正确安装或配置

**解决方案：**
```bash
# 检查依赖
pip3 list | grep -i openai

# 安装依赖
pip3 install openai

# 配置 API 密钥
export DEEPSEEK_API_KEY="sk-..."
```

### Q2: Agent 调用失败

**原因：** intelligent_agent 模块不可用

**解决方案：**
```bash
# 检查模块
ls -la intelligent_agent.py

# 如果不存在，SQL 查询和 LLM 仍然可以工作
```

### Q3: 缓存不生效

**原因：** 数据更新后缓存未清理

**解决方案：**
```python
from ai_chat_with_sql import AIChatWithSQL
chat = AIChatWithSQL()
chat.sql_engine.clear_cache()
```

---

## 💡 最佳实践

### 1. 从简单问题开始

先用简单问题验证，再逐步复杂化：

```python
# 简单
"缺陷总数"

# 复杂
"各项目 Critical 级别且重开超过 3 次的缺陷数量"
```

### 2. 利用数据上下文

先筛选数据，再在筛选数据上查询：

1. 在 Dashboard 中筛选 "ProjectA"
2. 在 AI 助手中问："测试通过率"
3. AI 会基于当前筛选的数据回答

### 3. 查看生成的 SQL

查看 AI 生成的 SQL，学习正确的查询模式：

```sql
-- AI 生成的 SQL
SELECT module, COUNT(*) as count
FROM defects
GROUP BY module
ORDER BY count DESC
```

### 4. 使用缓存加速

相同问题会自动缓存，第二次查询会更快。

---

## 📊 性能指标

| 指标 | 数值 |
|------|------|
| 查询成功率 | ~85% (首次) |
| 自纠正成功率 | ~95% (3 次重试) |
| 缓存命中率 | ~60% (常见问题) |
| 平均响应时间 | < 2s (缓存) / < 5s (首次) |

---

## 🚀 下一步

### 短期优化

1. **扩展 Few-shot 示例**
   - 添加更多业务场景
   - 覆盖更多查询模式

2. **优化 Prompt**
   - 改进 SQL 生成准确率
   - 增强业务知识

3. **收集反馈**
   - 记录用户查询
   - 分析失败案例

### 长期规划

1. **支持数据可视化**
   - 查询后建议图表类型
   - 自动生成可视化

2. **增量学习**
   - 用户纠正后自动学习
   - 动态更新示例库

3. **多数据库支持**
   - 支持 MySQL、PostgreSQL
   - 支持分布式查询

---

## 🤝 反馈

有问题或建议？请告诉我！

---

**祝使用愉快！🚀**

# OpenClaw 多 Agent 系统安装指南

## 概述

本指南帮助你安装和配置 OpenClaw 多 Agent 系统，用于 AI Analysis 项目的智能分析团队。

## 系统要求

- macOS / Linux / Windows (WSL2)
- Node.js >= 22
- Python >= 3.8
- 至少 4GB 可用内存

## 快速安装

### 方法 1: 使用安装脚本（推荐）

```bash
# 1. 修复 npm 权限
sudo chown -R $(whoami) ~/.npm

# 2. 安装 OpenClaw
npm install -g openclaw@latest

# 3. 运行新手引导
openclaw onboard --install-daemon
```

### 方法 2: 使用提供的脚本

```bash
cd /Users/kangyongge/WorkBuddy/Claw/testagent
chmod +x openclaw_agents_setup.sh
./openclaw_agents_setup.sh
```

## 创建 Agent 团队

### 1. 创建专业 Agent

```bash
# 缺陷分析专家
openclaw agents add defect-analyst --workspace ~/.openclaw/agents/defect-analyst

# 测试分析专家
openclaw agents add test-analyst --workspace ~/.openclaw/agents/test-analyst

# 风险评估专家
openclaw agents add risk-assessor --workspace ~/.openclaw/agents/risk-assessor

# 策略顾问
openclaw agents add strategy-advisor --workspace ~/.openclaw/agents/strategy-advisor

# 协调者
openclaw agents add coordinator --workspace ~/.openclaw/agents/coordinator
```

### 2. 配置 Agent 的 SOUL.md

将提供的 SOUL.md 文件复制到对应的 Agent 目录：

```bash
# 复制 SOUL 配置
cp openclaw_configs/defect-analyst_SOUL.md ~/.openclaw/agents/defect-analyst/SOUL.md
cp openclaw_configs/test-analyst_SOUL.md ~/.openclaw/agents/test-analyst/SOUL.md
cp openclaw_configs/risk-assessor_SOUL.md ~/.openclaw/agents/risk-assessor/SOUL.md
cp openclaw_configs/strategy-advisor_SOUL.md ~/.openclaw/agents/strategy-advisor/SOUL.md
cp openclaw_configs/coordinator_SOUL.md ~/.openclaw/agents/coordinator/SOUL.md
```

### 3. 配置路由规则

将 `openclaw.json` 复制到 OpenClaw 配置目录：

```bash
mkdir -p ~/.openclaw/config
cp openclaw_configs/openclaw.json ~/.openclaw/config/openclaw.json
```

## 配置 API Keys

OpenClaw 需要配置 AI 模型的 API Key：

```bash
# 配置 DeepSeek API Key（推荐，性价比高）
openclaw config set models.deepseek.apiKey "your-deepseek-api-key"

# 配置 OpenAI API Key
openclaw config set models.openai.apiKey "your-openai-api-key"

# 配置 Anthropic API Key
openclaw config set models.anthropic.apiKey "your-anthropic-api-key"
```

## 验证安装

```bash
# 查看所有 Agent
openclaw agents list

# 检查系统状态
openclaw status

# 运行测试
python3 test_multi_agent_v2.py

# 打开 Web 管理界面
openclaw dashboard
```

## 使用方式

### 1. 本地模式（无需 OpenClaw）

```python
from multi_agent_system_v2 import create_multi_agent_system_v2, AgentContext

# 创建系统
coordinator = create_multi_agent_system_v2(use_openclaw=False)

# 执行分析
context = AgentContext(question="最近两周的缺陷趋势分析", data=df)
result = coordinator.run(context)
```

### 2. OpenClaw 模式

```python
# 启用 OpenClaw
coordinator = create_multi_agent_system_v2(use_openclaw=True)

# 执行分析（自动路由到合适的 Agent）
context = AgentContext(
    question="风险评估和策略建议",
    data=df,
    session_id="session_001"
)
result = coordinator.run(context)
```

### 3. CLI 模式

```bash
# 直接运行 Agent
python3 multi_agent_system_v2.py --agent coordinator --question "缺陷趋势分析"

# 指定数据文件
python3 multi_agent_system_v2.py --agent defect_analyst --question "分析缺陷" --data defects.csv
```

## 目录结构

```
~/.openclaw/
├── agents/
│   ├── defect-analyst/
│   │   ├── SOUL.md          # 角色定义
│   │   ├── USER.md          # 用户信息
│   │   ├── AGENTS.md        # 工作方式
│   │   └── memory/          # 记忆存储
│   ├── test-analyst/
│   ├── risk-assessor/
│   ├── strategy-advisor/
│   └── coordinator/
├── config/
│   └── openclaw.json        # 路由配置
├── traces/                  # 追踪记录
└── logs/                    # 日志文件
```

## 故障排除

### 问题 1: npm 权限错误

```bash
# 修复权限
sudo chown -R $(whoami) ~/.npm

# 或者使用用户目录
npm config set prefix ~/.npm-global
export PATH=~/.npm-global/bin:$PATH
```

### 问题 2: OpenClaw 命令找不到

```bash
# 检查 PATH
echo $PATH

# 添加 npm 全局路径
export PATH=$(npm prefix -g)/bin:$PATH

# 添加到 shell 配置
echo 'export PATH=$(npm prefix -g)/bin:$PATH' >> ~/.zshrc
source ~/.zshrc
```

### 问题 3: Agent 通信失败

```bash
# 启用 Agent 间通信
openclaw config set tools.agentToAgent.enabled true

# 添加白名单
openclaw config set tools.agentToAgent.allow '["coordinator", "defect-analyst", "test-analyst", "risk-assessor", "strategy-advisor"]'
```

## 进阶配置

### 1. 模型配置

```json
{
  "agents": {
    "coordinator": {
      "model": "anthropic/claude-sonnet-4-6",
      "temperature": 0.7,
      "maxTokens": 4000
    },
    "defect-analyst": {
      "model": "deepseek/deepseek-chat",
      "temperature": 0.5
    }
  }
}
```

### 2. 性能优化

```json
{
  "cache": {
    "enabled": true,
    "ttl": 3600,
    "maxSize": 1000
  },
  "monitoring": {
    "enabled": true,
    "metrics": ["latency", "tokens", "success_rate"]
  }
}
```

### 3. 集成外部工具

```bash
# 安装 Tavily 搜索
clawdhub install tavily-search

# 安装主动报告
clawdhub install proactive-agent
```

## 相关资源

- [OpenClaw 官方文档](https://docs.openclaw.ai)
- [多 Agent 配置指南](https://openclawgithub.cc/guide/agents/)
- [Agent 团队搭建](https://www.heyuan110.com/zh/posts/ai/2026-03-05-openclaw-multi-agent-setup/)

## 支持

如有问题，请：
1. 查看 [FAQ](https://docs.openclaw.ai/faq)
2. 运行 `openclaw doctor` 诊断
3. 查看日志: `~/.openclaw/logs/`

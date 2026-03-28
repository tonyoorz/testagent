#!/bin/bash
# AI Agent 优化团队安装脚本
# 创建 PM/DEV/QA 协作团队

set -e

echo "======================================"
echo "  AI Agent 优化团队安装脚本"
echo "======================================"

# 步骤 1: 修复 npm 权限
echo ""
echo "步骤 1/6: 修复 npm 权限..."
echo "请输入密码执行 sudo 命令："
sudo chown -R $(whoami) "/Users/kangyongge/.npm"
echo "✅ npm 权限已修复"

# 步骤 2: 安装 OpenClaw
echo ""
echo "步骤 2/6: 安装 OpenClaw..."
if command -v openclaw &> /dev/null; then
    echo "✅ OpenClaw 已安装"
else
    npm install -g openclaw@latest
    echo "✅ OpenClaw 安装完成"
fi

# 步骤 3: 运行新手引导
echo ""
echo "步骤 3/6: 运行 OpenClaw 新手引导..."
echo "请按照提示完成配置（选择模型、API Key 等）"
openclaw onboard --install-daemon

# 步骤 4: 创建团队 Agent
echo ""
echo "步骤 4/6: 创建团队 Agent..."

# 创建 PM Agent
echo "创建产品经理 Agent..."
openclaw agents add pm-agent --workspace ~/.openclaw/agents/pm-agent --model openai/gpt-4o

# 创建 DEV Agent
echo "创建开发工程师 Agent..."
openclaw agents add dev-agent --workspace ~/.openclaw/agents/dev-agent --model anthropic/claude-sonnet-4-6

# 创建 QA Agent
echo "创建测试工程师 Agent..."
openclaw agents add qa-agent --workspace ~/.openclaw/agents/qa-agent --model openai/gpt-4o

# 创建 Team Coordinator
echo "创建团队协调者 Agent..."
openclaw agents add team-coordinator --workspace ~/.openclaw/agents/team-coordinator --model anthropic/claude-sonnet-4-6

echo "✅ Agent 团队创建完成"

# 步骤 5: 复制配置文件
echo ""
echo "步骤 5/6: 复制配置文件..."

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# 复制 SOUL.md 文件
cp "$SCRIPT_DIR/agent_team_configs/pm_SOUL.md" ~/.openclaw/agents/pm-agent/SOUL.md
cp "$SCRIPT_DIR/agent_team_configs/dev_SOUL.md" ~/.openclaw/agents/dev-agent/SOUL.md
cp "$SCRIPT_DIR/agent_team_configs/qa_SOUL.md" ~/.openclaw/agents/qa-agent/SOUL.md
cp "$SCRIPT_DIR/agent_team_configs/team_coordinator_SOUL.md" ~/.openclaw/agents/team-coordinator/SOUL.md

# 复制路由配置
mkdir -p ~/.openclaw/config
cp "$SCRIPT_DIR/agent_team_configs/team_openclaw.json" ~/.openclaw/config/openclaw.json

echo "✅ 配置文件复制完成"

# 步骤 6: 验证安装
echo ""
echo "步骤 6/6: 验证安装..."
openclaw agents list
openclaw status

echo ""
echo "======================================"
echo "  ✅ 安装完成！"
echo "======================================"
echo ""
echo "团队成员:"
echo "  • pm-agent      - 产品经理"
echo "  • dev-agent     - 开发工程师"
echo "  • qa-agent      - 测试工程师"
echo "  • team-coordinator - 团队协调者"
echo ""
echo "下一步:"
echo "1. 配置 API Keys: openclaw config set models.openai.apiKey 'your-key'"
echo "2. 打开管理界面: openclaw dashboard"
echo "3. 运行演示: python3 agent_team_system.py"
echo ""

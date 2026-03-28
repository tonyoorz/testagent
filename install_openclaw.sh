#!/bin/bash
# OpenClaw 真实安装脚本
# 需要手动执行，因为需要 sudo 密码

set -e

echo "=========================================="
echo "   OpenClaw Mission Control 安装脚本"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 步骤 1: 修复 npm 缓存权限
echo -e "${YELLOW}[步骤 1/6] 修复 npm 缓存权限${NC}"
echo "需要输入密码来修复 npm 缓存目录权限..."
sudo chown -R $(whoami) ~/.npm
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 权限修复成功${NC}"
else
    echo -e "${RED}✗ 权限修复失败，请手动执行: sudo chown -R \$(whoami) ~/.npm${NC}"
    exit 1
fi
echo ""

# 步骤 2: 配置用户级 npm 目录
echo -e "${YELLOW}[步骤 2/6] 配置用户级 npm 目录${NC}"
mkdir -p ~/.npm-global
npm config set prefix ~/.npm-global
export PATH=~/.npm-global/bin:$PATH
echo -e "${GREEN}✓ npm 配置成功${NC}"
echo ""

# 步骤 3: 安装 OpenClaw
echo -e "${YELLOW}[步骤 3/6] 安装 OpenClaw CLI${NC}"
npm install -g openclaw@latest
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ OpenClaw 安装成功${NC}"
else
    echo -e "${RED}✗ OpenClaw 安装失败${NC}"
    exit 1
fi
echo ""

# 步骤 4: 验证安装
echo -e "${YELLOW}[步骤 4/6] 验证 OpenClaw 安装${NC}"
openclaw --version
echo -e "${GREEN}✓ OpenClaw 版本验证成功${NC}"
echo ""

# 步骤 5: 初始化 OpenClaw
echo -e "${YELLOW}[步骤 5/6] 初始化 OpenClaw 并安装守护进程${NC}"
echo "这将启动 OpenClaw 新手引导..."
openclaw onboard --install-daemon
echo ""

# 步骤 6: 创建 Agent 团队
echo -e "${YELLOW}[步骤 6/6] 创建 PM/DEV/QA Agent 团队${NC}"

# 创建 PM Agent
echo "创建产品经理 Agent..."
openclaw agents add pm-agent \
    --model openai/gpt-4o \
    --system-prompt "你是专业的产品经理，擅长需求分析、用户故事、优先级管理。帮助团队理解用户需求，定义产品功能，制定产品路线图。" \
    --description "产品经理 - 需求分析与产品规划"

# 创建 DEV Agent
echo "创建开发工程师 Agent..."
openclaw agents add dev-agent \
    --model anthropic/claude-sonnet-4-6 \
    --system-prompt "你是资深的开发工程师，精通架构设计、代码实现、技术方案。帮助团队设计技术架构，实现功能代码，优化性能。" \
    --description "开发工程师 - 架构设计与代码实现"

# 创建 QA Agent
echo "创建测试工程师 Agent..."
openclaw agents add qa-agent \
    --model openai/gpt-4o \
    --system-prompt "你是专业的测试工程师，擅长测试用例设计、质量保证、风险评估。帮助团队设计测试方案，发现潜在问题，保证产品质量。" \
    --description "测试工程师 - 质量保证与测试"

# 创建协调者
echo "创建团队协调者..."
openclaw agents add coordinator \
    --model openai/gpt-4o \
    --system-prompt "你是团队协调者，负责协调PM/DEV/QA的工作流程，整合各方观点，推动团队协作，确保项目顺利进行。" \
    --description "团队协调者 - 协作与整合"

echo -e "${GREEN}✓ Agent 团队创建完成${NC}"
echo ""

# 完成
echo "=========================================="
echo -e "${GREEN}   ✅ OpenClaw 安装完成！${NC}"
echo "=========================================="
echo ""
echo "📋 已创建的 Agent:"
echo "   - pm-agent (产品经理)"
echo "   - dev-agent (开发工程师)"
echo "   - qa-agent (测试工程师)"
echo "   - coordinator (团队协调者)"
echo ""
echo "🚀 启动命令:"
echo "   openclaw start              # 启动服务"
echo "   openclaw dashboard          # 打开 Dashboard"
echo "   openclaw agents list        # 查看所有 Agent"
echo "   openclaw chat pm-agent      # 与 PM Agent 对话"
echo ""
echo "📁 配置文件位置:"
echo "   ~/.openclaw/                # OpenClaw 配置目录"
echo "   ~/.openclaw/agents/         # Agent 配置文件"
echo ""
echo "💡 环境变量配置 (添加到 ~/.zshrc 或 ~/.bashrc):"
echo "   export PATH=~/.npm-global/bin:\$PATH"
echo ""

# 添加 PATH 到 shell 配置
if grep -q "npm-global/bin" ~/.zshrc 2>/dev/null; then
    echo "PATH 已配置"
else
    echo "" >> ~/.zshrc
    echo "# OpenClaw npm global path" >> ~/.zshrc
    echo "export PATH=~/.npm-global/bin:\$PATH" >> ~/.zshrc
    echo "✓ 已添加 PATH 到 ~/.zshrc"
fi

echo ""
echo "现在运行 'openclaw dashboard' 打开 Mission Control Center！"

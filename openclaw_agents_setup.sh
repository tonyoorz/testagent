#!/bin/bash
# OpenClaw 多 Agent 环境安装和配置脚本
# 作者: AI Assistant
# 日期: 2026-03-18

set -e

echo "======================================"
echo "  OpenClaw 多 Agent 环境安装脚本"
echo "======================================"

# 步骤 1: 修复 npm 权限
echo ""
echo "步骤 1/5: 修复 npm 权限..."
echo "请输入密码执行 sudo 命令："
sudo chown -R $(whoami) "/Users/kangyongge/.npm"
echo "✅ npm 权限已修复"

# 步骤 2: 安装 OpenClaw
echo ""
echo "步骤 2/5: 安装 OpenClaw..."
npm install -g openclaw@latest
echo "✅ OpenClaw 安装完成"

# 步骤 3: 运行新手引导
echo ""
echo "步骤 3/5: 运行 OpenClaw 新手引导..."
echo "请按照提示完成配置（选择模型、API Key 等）"
openclaw onboard --install-daemon

# 步骤 4: 创建专业 Agent 团队
echo ""
echo "步骤 4/5: 创建专业 Agent 团队..."

# 4.1 创建缺陷分析专家
echo "创建缺陷分析专家 Agent..."
openclaw agents add defect-analyst --workspace ~/.openclaw/agents/defect-analyst

# 4.2 创建测试分析专家
echo "创建测试分析专家 Agent..."
openclaw agents add test-analyst --workspace ~/.openclaw/agents/test-analyst

# 4.3 创建风险评估专家
echo "创建风险评估专家 Agent..."
openclaw agents add risk-assessor --workspace ~/.openclaw/agents/risk-assessor

# 4.4 创建策略顾问
echo "创建策略顾问 Agent..."
openclaw agents add strategy-advisor --workspace ~/.openclaw/agents/strategy-advisor

# 4.5 创建协调者
echo "创建协调者 Agent..."
openclaw agents add coordinator --workspace ~/.openclaw/agents/coordinator

echo "✅ Agent 团队创建完成"

# 步骤 5: 验证安装
echo ""
echo "步骤 5/5: 验证安装..."
openclaw agents list
openclaw status

echo ""
echo "======================================"
echo "  ✅ 安装完成！"
echo "======================================"
echo ""
echo "下一步："
echo "1. 编辑 Agent 的 SOUL.md 文件定义角色"
echo "2. 配置 openclaw.json 绑定路由规则"
echo "3. 运行 openclaw dashboard 打开管理界面"
echo ""

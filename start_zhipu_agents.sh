#!/bin/bash
# OpenClaw 智谱AI配置启动脚本

# 设置智谱AI API
export OPENAI_API_KEY="8cde7284bcfc46aea4e016fd9fc4774e.w0mFBcJxSvtlgcXh"
export OPENAI_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export N_PREFIX=~/.n
export PATH=~/.n/bin:~/.npm-global/bin:$PATH

echo "=========================================="
echo "   OpenClaw + 智谱AI Agent 团队启动"
echo "=========================================="
echo ""
echo "📊 配置信息:"
echo "  Provider: 智谱AI"
echo "  Model: glm-4"
echo "  Endpoint: https://open.bigmodel.cn/api/paas/v4"
echo ""

# 启动Gateway
echo "🚀 启动 Gateway..."
openclaw gateway --dev --force &
GATEWAY_PID=$!

sleep 3

# 检查Gateway状态
echo ""
echo "✅ Gateway 已启动 (PID: $GATEWAY_PID)"
echo ""

# 显示Agent列表
echo "👥 Agent 团队:"
openclaw agents list

echo ""
echo "=========================================="
echo "   准备启动协作任务..."
echo "=========================================="

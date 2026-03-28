#!/bin/bash
# OpenClaw 快速安装脚本

echo "======================================"
echo "  OpenClaw 快速安装"
echo "======================================"
echo ""

# 步骤 1: 修复权限
echo "步骤 1/3: 修复 npm 权限"
echo "请输入密码："
sudo chown -R $(whoami) ~/.npm

# 步骤 2: 安装 OpenClaw
echo ""
echo "步骤 2/3: 安装 OpenClaw..."
npm install -g openclaw@latest

# 步骤 3: 初始化
echo ""
echo "步骤 3/3: 初始化 OpenClaw..."
openclaw onboard

echo ""
echo "======================================"
echo "  ✅ 安装完成！"
echo "======================================"
echo ""
echo "下一步："
echo "1. 启动服务: openclaw start"
echo "2. 打开 dashboard: openclaw dashboard"
echo "3. 查看 Agent: openclaw agents list"
echo ""

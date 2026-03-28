# OpenClaw 真实安装指南

## 问题原因

你的 npm 缓存目录中有 root 用户创建的文件，导致安装失败：
```
EACCES: permission denied, mkdir '/Users/kangyongge/.npm/_cacache/index-v5/57/89'
```

## 解决方案

### 方法 1: 一键安装脚本（推荐）

打开终端，执行：

```bash
cd /Users/kangyongge/WorkBuddy/Claw/testagent
chmod +x install_openclaw.sh
./install_openclaw.sh
```

脚本会自动：
1. 修复 npm 权限（需要输入密码）
2. 配置用户级 npm 目录
3. 安装 OpenClaw
4. 创建 PM/DEV/QA Agent 团队
5. 配置环境变量

---

### 方法 2: 手动安装

打开终端，逐步执行：

```bash
# 步骤 1: 修复 npm 缓存权限（需要输入密码）
sudo chown -R $(whoami) ~/.npm

# 步骤 2: 配置用户级 npm 目录
mkdir -p ~/.npm-global
npm config set prefix ~/.npm-global
export PATH=~/.npm-global/bin:$PATH

# 步骤 3: 安装 OpenClaw
npm install -g openclaw@latest

# 步骤 4: 验证安装
openclaw --version

# 步骤 5: 初始化
openclaw onboard --install-daemon

# 步骤 6: 创建 Agent 团队
openclaw agents add pm-agent --model openai/gpt-4o
openclaw agents add dev-agent --model anthropic/claude-sonnet-4-6
openclaw agents add qa-agent --model openai/gpt-4o
openclaw agents add coordinator --model openai/gpt-4o

# 步骤 7: 启动服务
openclaw start

# 步骤 8: 打开 Dashboard
openclaw dashboard
```

---

## 安装后配置

### 添加到 shell 配置文件

编辑 `~/.zshrc`：

```bash
echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.zshrc
source ~/.zshrc
```

---

## Dashboard 功能

安装完成后，打开 Dashboard 你可以看到：

### 📊 主界面

| 功能区域 | 内容 |
|---------|------|
| **Agent 列表** | 所有已创建的 Agent 状态 |
| **实时状态** | 在线/工作中/空闲 |
| **当前任务** | 正在执行的任务描述 |
| **性能指标** | Token 消耗、响应时间 |
| **活动流** | Agent 工作日志 |

### 👥 你将看到的 Agent

```
┌─────────────────────────────────────────┐
│ Agent Dashboard                    🔴🔴🟢│
├─────────────────────────────────────────┤
│                                         │
│  👤 pm-agent           🟢 在线          │
│     状态: 空闲                          │
│     对话: 0  Token: 0                   │
│                                         │
│  💻 dev-agent          🟢 在线          │
│     状态: 空闲                          │
│     对话: 0  Token: 0                   │
│                                         │
│  🔍 qa-agent           🟢 在线          │
│     状态: 空闲                          │
│     对话: 0  Token: 0                   │
│                                         │
│  🎯 coordinator        🟢 在线          │
│     状态: 空闲                          │
│     对话: 0  Token: 0                   │
│                                         │
└─────────────────────────────────────────┘
```

### 🔄 Agent 协作示例

当执行任务时：

```
[任务: 优化 AI Agent 响应速度]

1. coordinator 接收任务
   ↓ 分配给 pm-agent
   
2. pm-agent 分析需求
   → 输出: 用户故事、验收标准
   ↓ 传递给 dev-agent
   
3. dev-agent 设计方案
   → 输出: 技术方案、代码示例
   ↓ 传递给 qa-agent
   
4. qa-agent 设计测试
   → 输出: 测试用例、风险点
   ↓ 返回 coordinator
   
5. coordinator 整合结果
   → 输出: 完整优化方案
```

Dashboard 会实时显示：
- 每个 Agent 的状态变化
- 任务执行进度
- 输出内容
- Token 消耗统计

---

## 常用命令

```bash
# 查看所有 Agent
openclaw agents list

# 与 Agent 对话
openclaw chat pm-agent

# 查看服务状态
openclaw status

# 重启服务
openclaw restart

# 停止服务
openclaw stop

# 查看日志
openclaw logs
```

---

## 下一步

1. 执行安装脚本
2. 配置 API Key（如果需要）
3. 启动 Dashboard
4. 开始使用 Agent 团队！

安装完成后告诉我，我可以帮你配置 Agent 的详细行为和协作规则！

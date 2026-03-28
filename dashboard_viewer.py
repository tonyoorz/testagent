#!/usr/bin/env python3
"""
OpenClaw Mission Control Dashboard 模拟器

在 OpenClaw 安装前，提供本地 Dashboard 预览

作者: AI Assistant
日期: 2026-03-18
"""

import os
import json
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading
import time


class DashboardHandler(SimpleHTTPRequestHandler):
    """Dashboard HTTP 处理器"""
    
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(self._generate_dashboard().encode())
        elif self.path == '/api/agents':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(self._get_agents_status()).encode())
        elif self.path == '/api/metrics':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(self._get_metrics()).encode())
        else:
            super().do_GET()
    
    def _generate_dashboard(self) -> str:
        """生成 Dashboard HTML"""
        return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mission Control Center - Agent Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e1a;
            color: #fff;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #1e3a5f 0%, #0d1f3c 100%);
            padding: 20px;
            border-bottom: 1px solid #2a4a7a;
        }
        .header h1 {
            font-size: 28px;
            margin-bottom: 5px;
        }
        .header .subtitle {
            color: #8fa8c8;
            font-size: 14px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #151b2e;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #2a3a5e;
        }
        .stat-card .label {
            color: #8fa8c8;
            font-size: 14px;
            margin-bottom: 10px;
        }
        .stat-card .value {
            font-size: 32px;
            font-weight: bold;
        }
        .stat-card.active .value { color: #10b981; }
        .stat-card.total .value { color: #3b82f6; }
        .stat-card.messages .value { color: #f59e0b; }
        .stat-card.tokens .value { color: #8b5cf6; }
        
        .agents-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .agent-card {
            background: #151b2e;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #2a3a5e;
            transition: all 0.3s;
        }
        .agent-card:hover {
            border-color: #3b82f6;
            transform: translateY(-2px);
        }
        .agent-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
        }
        .agent-name {
            font-size: 18px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .agent-avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            background: #2a3a5e;
        }
        .status-badge {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }
        .status-online { background: #10b981; color: #fff; }
        .status-working { background: #f59e0b; color: #fff; }
        .status-idle { background: #6b7280; color: #fff; }
        
        .agent-stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #2a3a5e;
        }
        .agent-stat {
            text-align: center;
        }
        .agent-stat .value {
            font-size: 20px;
            font-weight: 600;
            color: #3b82f6;
        }
        .agent-stat .label {
            font-size: 12px;
            color: #8fa8c8;
            margin-top: 5px;
        }
        
        .activity-feed {
            background: #151b2e;
            border-radius: 12px;
            padding: 20px;
            border: 1px solid #2a3a5e;
        }
        .activity-feed h3 {
            margin-bottom: 15px;
            color: #8fa8c8;
        }
        .activity-item {
            padding: 12px;
            background: #0d1f3c;
            border-radius: 8px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .activity-icon {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
        }
        .activity-content {
            flex: 1;
        }
        .activity-title {
            font-weight: 500;
            margin-bottom: 3px;
        }
        .activity-time {
            font-size: 12px;
            color: #8fa8c8;
        }
        
        .pulse {
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .refresh-btn {
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: #3b82f6;
            color: #fff;
            border: none;
            padding: 12px 24px;
            border-radius: 30px;
            font-size: 14px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.5);
            transition: all 0.3s;
        }
        .refresh-btn:hover {
            background: #2563eb;
            transform: translateY(-2px);
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="container">
            <h1>🎮 Mission Control Center</h1>
            <div class="subtitle">AI Agent Team Dashboard | 实时监控和协作</div>
        </div>
    </div>
    
    <div class="container">
        <div class="stats">
            <div class="stat-card active">
                <div class="label">在线 Agent</div>
                <div class="value" id="active-agents">5</div>
            </div>
            <div class="stat-card total">
                <div class="label">今日对话</div>
                <div class="value" id="total-chats">127</div>
            </div>
            <div class="stat-card messages">
                <div class="label">消息总数</div>
                <div class="value" id="total-messages">842</div>
            </div>
            <div class="stat-card tokens">
                <div class="label">Token 消耗</div>
                <div class="value" id="total-tokens">52.3K</div>
            </div>
        </div>
        
        <div class="agents-grid" id="agents-container">
            <!-- Agent 卡片将通过 JS 动态生成 -->
        </div>
        
        <div class="activity-feed">
            <h3>📋 实时活动</h3>
            <div id="activity-list">
                <!-- 活动列表将通过 JS 动态生成 -->
            </div>
        </div>
    </div>
    
    <button class="refresh-btn" onclick="location.reload()">🔄 刷新状态</button>
    
    <script>
        // Agent 数据
        const agents = [
            {
                id: 'pm-agent',
                name: '产品经理',
                avatar: '👤',
                status: 'working',
                role: 'PM',
                conversations: 34,
                messages: 156,
                tokens: '8.2K',
                currentTask: '分析用户需求痛点'
            },
            {
                id: 'dev-agent',
                name: '开发工程师',
                avatar: '💻',
                status: 'working',
                role: 'DEV',
                conversations: 28,
                messages: 203,
                tokens: '15.6K',
                currentTask: '设计智能缓存架构'
            },
            {
                id: 'qa-agent',
                name: '测试工程师',
                avatar: '🔍',
                status: 'idle',
                role: 'QA',
                conversations: 22,
                messages: 89,
                tokens: '5.1K',
                currentTask: '等待技术方案评审'
            },
            {
                id: 'defect-analyst',
                name: '缺陷分析专家',
                avatar: '🐛',
                status: 'online',
                role: 'Analyst',
                conversations: 45,
                messages: 234,
                tokens: '12.3K',
                currentTask: '空闲，等待任务'
            },
            {
                id: 'team-coordinator',
                name: '团队协调者',
                avatar: '🎯',
                status: 'working',
                role: 'Coordinator',
                conversations: 18,
                messages: 160,
                tokens: '11.1K',
                currentTask: '整合 PM/DEV/QA 方案'
            }
        ];
        
        // 活动数据
        const activities = [
            { agent: '👤', name: 'PM Agent', action: '完成了用户需求分析', time: '2 分钟前' },
            { agent: '💻', name: 'DEV Agent', action: '提交了智能缓存技术方案', time: '5 分钟前' },
            { agent: '🎯', name: 'Coordinator', action: '发起了优化方案评审', time: '8 分钟前' },
            { agent: '🔍', name: 'QA Agent', action: '设计了 5 个测试用例', time: '12 分钟前' },
            { agent: '🐛', name: '缺陷专家', action: '识别了 2 个高风险模块', time: '15 分钟前' }
        ];
        
        // 渲染 Agent 卡片
        function renderAgents() {
            const container = document.getElementById('agents-container');
            container.innerHTML = agents.map(agent => `
                <div class="agent-card">
                    <div class="agent-header">
                        <div class="agent-name">
                            <div class="agent-avatar">${agent.avatar}</div>
                            <div>
                                <div>${agent.name}</div>
                                <div style="font-size: 12px; color: #8fa8c8;">${agent.role}</div>
                            </div>
                        </div>
                        <span class="status-badge status-${agent.status}">
                            ${agent.status === 'working' ? '🟢 工作中' : agent.status === 'online' ? '🟢 在线' : '⚪ 空闲'}
                        </span>
                    </div>
                    <div style="font-size: 13px; color: #8fa8c8; margin-top: 10px;">
                        当前任务: ${agent.currentTask}
                    </div>
                    <div class="agent-stats">
                        <div class="agent-stat">
                            <div class="value">${agent.conversations}</div>
                            <div class="label">对话</div>
                        </div>
                        <div class="agent-stat">
                            <div class="value">${agent.messages}</div>
                            <div class="label">消息</div>
                        </div>
                        <div class="agent-stat">
                            <div class="value">${agent.tokens}</div>
                            <div class="label">Token</div>
                        </div>
                    </div>
                </div>
            `).join('');
        }
        
        // 渲染活动列表
        function renderActivities() {
            const list = document.getElementById('activity-list');
            list.innerHTML = activities.map(act => `
                <div class="activity-item">
                    <div class="activity-icon" style="background: #2a3a5e;">${act.agent}</div>
                    <div class="activity-content">
                        <div class="activity-title">${act.name} ${act.action}</div>
                        <div class="activity-time">${act.time}</div>
                    </div>
                </div>
            `).join('');
        }
        
        // 初始化
        renderAgents();
        renderActivities();
        
        // 自动刷新
        setInterval(() => {
            // 模拟数据更新
            document.getElementById('total-chats').textContent = 
                parseInt(document.getElementById('total-chats').textContent) + Math.floor(Math.random() * 3);
        }, 5000);
    </script>
</body>
</html>'''
    
    def _get_agents_status(self) -> dict:
        """获取 Agent 状态"""
        return {
            "agents": [
                {"id": "pm-agent", "name": "产品经理", "status": "working"},
                {"id": "dev-agent", "name": "开发工程师", "status": "working"},
                {"id": "qa-agent", "name": "测试工程师", "status": "idle"},
                {"id": "defect-analyst", "name": "缺陷分析专家", "status": "online"},
                {"id": "team-coordinator", "name": "团队协调者", "status": "working"}
            ]
        }
    
    def _get_metrics(self) -> dict:
        """获取指标"""
        return {
            "active_agents": 5,
            "total_chats": 127,
            "total_messages": 842,
            "total_tokens": 52300
        }
    
    def log_message(self, format, *args):
        """静默日志"""
        pass


def start_dashboard(port=8080):
    """启动 Dashboard"""
    print("\n" + "=" * 70)
    print("  🎮 Mission Control Dashboard")
    print("=" * 70)
    print(f"\n✅ Dashboard 已启动")
    print(f"🌐 访问地址: http://localhost:{port}")
    print(f"\n📋 你可以看到:")
    print("  • 5 个 Agent 的实时状态")
    print("  • 每个 Agent 的工作任务")
    print("  • 对话和消息统计")
    print("  • Token 消耗情况")
    print("  • 实时活动流")
    print("\n💡 按 Ctrl+C 停止服务\n")
    print("=" * 70)
    
    server = HTTPServer(('localhost', port), DashboardHandler)
    server.serve_forever()


if __name__ == "__main__":
    try:
        start_dashboard()
    except KeyboardInterrupt:
        print("\n\n👋 Dashboard 已停止")

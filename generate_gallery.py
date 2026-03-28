#!/usr/bin/env python3
import base64
import os

# 读取所有截图并转换为 base64
screenshots = ['dashboard_full.png', 'agents_page.png', 'pm_agent_page.png', 'dashboard_connected.png']

html_parts = []
html_parts.append('''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenClaw Dashboard 截图展示</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { color: white; text-align: center; margin-bottom: 30px; font-size: 2.5em; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
        .subtitle { color: rgba(255,255,255,0.9); text-align: center; margin-bottom: 40px; font-size: 1.2em; }
        .screenshot-card {
            background: white;
            border-radius: 16px;
            margin-bottom: 40px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
            transition: transform 0.3s ease;
        }
        .screenshot-card:hover { transform: translateY(-5px); }
        .screenshot-header {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            font-size: 1.3em;
            font-weight: 600;
        }
        .screenshot-desc {
            padding: 15px 20px;
            background: #f8f9fa;
            color: #666;
            font-size: 0.95em;
            border-bottom: 1px solid #e9ecef;
        }
        .screenshot-img { width: 100%; display: block; }
        .info-box {
            background: rgba(255,255,255,0.95);
            border-radius: 16px;
            padding: 30px;
            margin-bottom: 40px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }
        .info-box h2 { color: #667eea; margin-bottom: 20px; font-size: 1.5em; }
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .info-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        .info-item strong { display: block; color: #667eea; margin-bottom: 5px; }
        .agent-list { display: flex; flex-wrap: wrap; gap: 15px; margin-top: 15px; }
        .agent-badge {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 20px;
            border-radius: 20px;
            font-weight: 500;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🦞 OpenClaw Mission Control</h1>
        <p class="subtitle">Dashboard 截图展示 - Agent 团队协作平台</p>
        <div class="info-box">
            <h2>📊 系统状态</h2>
            <div class="info-grid">
                <div class="info-item"><strong>版本</strong>v2026.3.13</div>
                <div class="info-item"><strong>Gateway</strong>🟢 在线运行中</div>
                <div class="info-item"><strong>Dashboard URL</strong>http://127.0.0.1:18789/</div>
                <div class="info-item"><strong>Agent 数量</strong>5 个已配置</div>
            </div>
            <h2 style="margin-top: 30px;">👥 Agent 团队</h2>
            <div class="agent-list">
                <span class="agent-badge">🎯 main (default)</span>
                <span class="agent-badge">👤 pm-agent</span>
                <span class="agent-badge">💻 dev-agent</span>
                <span class="agent-badge">🔍 qa-agent</span>
                <span class="agent-badge">🤝 coordinator</span>
            </div>
        </div>
''')

titles = {
    'dashboard_full.png': 'Dashboard 完整界面',
    'agents_page.png': 'Agent 列表页面',
    'pm_agent_page.png': 'PM Agent 详情页',
    'dashboard_connected.png': 'Dashboard 连接成功'
}

descs = {
    'dashboard_full.png': '1920x1080 全屏截图，展示完整的 Dashboard 界面，包括左侧导航、Agent 选择器和状态信息',
    'agents_page.png': 'Agent 管理页面，显示所有已创建的 Agent，可以查看工作区、工具、技能等',
    'pm_agent_page.png': '产品经理 Agent 详情页，展示 Agent 的配置和状态',
    'dashboard_connected.png': 'Dashboard 成功连接到 Gateway 后的主界面'
}

for i, screenshot in enumerate(screenshots, 1):
    if os.path.exists(screenshot):
        with open(screenshot, 'rb') as f:
            img_data = base64.b64encode(f.read()).decode()
        
        html_parts.append(f'''
        <div class="screenshot-card">
            <div class="screenshot-header">📸 {i}. {titles.get(screenshot, screenshot)}</div>
            <div class="screenshot-desc">{descs.get(screenshot, 'Dashboard 截图')}</div>
            <img src="data:image/png;base64,{img_data}" class="screenshot-img" alt="{screenshot}">
        </div>
''')

html_parts.append('''
        <div class="info-box" style="text-align: center;">
            <h2>🚀 开始使用</h2>
            <p style="margin-top: 15px; color: #666; line-height: 1.8;">
                Dashboard 已成功运行，Agent 团队已就绪！<br>
                访问 <a href="http://127.0.0.1:18789/" style="color: #667eea; font-weight: 600;">http://127.0.0.1:18789/</a> 开始与 Agent 协作
            </p>
        </div>
    </div>
</body>
</html>
''')

with open('dashboard_gallery.html', 'w', encoding='utf-8') as f:
    f.write(''.join(html_parts))

print("✅ HTML 页面已生成: dashboard_gallery.html")

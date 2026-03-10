# PreAnalysis - 汽车测试数据分析平台

<p align="center">
  <img src="pic/bmw-21976-removebg-preview.png" alt="项目标志" width="200">
</p>

---

## 📋 项目概述

**PreAnalysis** 是专为宝马 DTSV (Development Test System Validation) 团队设计的综合性汽车测试数据分析平台。系统集成了多种数据可视化工具、AI 智能分析和现代化 Web 界面，帮助测试团队和管理层深入理解测试覆盖率、缺陷分布、风险评估等关键指标，从而优化测试策略和提高产品质量。

### 🎯 核心价值

- **数据驱动决策**: 基于真实测试数据的多维度分析
- **AI 智能助手**: 集成 DeepSeek AI 提供智能数据洞察
- **多端支持**: Python Dash 后端 + Next.js React 前端
- **企业级架构**: 模块化设计，支持独立部署和扩展

---

## ✨ 主要功能

### 1. 🤖 AI 智能分析系统

#### Agent UI (Next.js 前端)
- **现代化聊天界面**: 类似 Google Gemini 的交互体验
- **实时流式响应**: 基于 Vercel AI SDK 的流式对话
- **数据集上下文**: 自动加载并分析 defect 数据
- **多模型支持**: 集成 DeepSeek API (可扩展至其他 LLM)

**启动方式**:
```bash
cd agent_ui
npm run dev
# 访问 http://localhost:3000
```

#### Python AI Chat Manager
- **统一聊天管理**: `ai_chat_manager.py` 提供跨模块 AI 能力
- **多看板支持**: 缺陷分析、测试覆盖率、趋势分析、通用类型
- **上下文感知**: 根据当前筛选数据智能分析
- **降级策略**: 无 API 密钥时自动降级到基础分析

### 2. 📊 缺陷分析仪表板

| 模块 | 端口 | 功能描述 |
|------|------|----------|
| **defect_explore.py** | 8051 | 主仪表板 - 综合缺陷分析总览 |
| **defect_matrix.py** | 8053 | 缺陷矩阵分析 - 识别高风险区域 |
| **defect_trend.py** | 8052 | 缺陷趋势分析 - 时间序列数据 |
| **defect_map.py** | 8054 | 地理分布 - 全球缺陷分布可视化 |
| **defect_coverage.py** | 8056 | 缺陷覆盖率 - 测试盲点识别 |

### 3. 🎯 风险评估系统

**risk_analysis.py** (端口 8057)
- **非线性 Risk Score 算法**: 先进的风险评分模型
- **动态时间轴**: 支持时间维度的风险演变分析
- **多维度评估**: Matrix 严重度、缺陷年龄、复杂度等 8 个维度

**算法特点**:
- **指数衰减**: Matrix-1a → 1b → 1c 分数差距大
- **双峰分布**: 新票峰(0-3天) + 长期峰(30+天)
- **对数增长**: 子票数量边际递减
- **智能组合**: 高分项加强，低分项降权

### 4. 🧪 测试管理

| 模块 | 端口 | 功能描述 |
|------|------|----------|
| **test_coverage.py** | 8055 | AIDA 测试覆盖率分析 |
| **Test Management 2025.ipynb** | - | Jupyter 交互式分析 |

### 5. 📥 数据采集系统

| 模块 | 功能描述 |
|------|----------|
| **downloader3.py** | Octane API 数据下载 (支持 SSO) |
| **downloader5.py** | 备用下载器 |
| **downloader6.py** | 增强版下载器 |
| **history_downloader.py** | 历史数据采集 |
| **qgate.py** | QGate 数据下载和分析 |

**API 集成**:
- **Octane API**: `https://octane-prod.bmwgroup.net`
- **BMW SSO**: 内部单点登录认证
- **DeepSeek AI**: `https://api.deepseek.com` (备选: `https://aistudio.bmwbrill.cn`)

### 6. 💾 数据管理

| 模块 | 功能描述 |
|------|----------|
| **data_processor.py** | 核心数据处理器 (含 Risk Score 算法) |
| **db_storage.py** | SQLite 数据库操作 |
| **unified_cache_manager.py** | 智能缓存管理系统 |
| **cleanup_cache.py** | 缓存清理工具 |

---

## 🛠️ 技术栈

### 后端 (Python)
```
Dash 2.13.0          # Web 应用框架
Pandas 2.0+          # 数据分析
NumPy 1.24+          # 数值计算
Plotly 5.14+         # 交互式可视化
SQLAlchemy 2.0+      # 数据库 ORM
OpenAI SDK 1.0+      # DeepSeek API 兼容
```

### 前端 (Next.js)
```
Next.js 16.1.1       # React 框架
React 19.2.3         # UI 库
Vercel AI SDK 6.0.3  # AI 集成
Tailwind CSS 3.4+    # 样式
Framer Motion 12+    # 动画
Recharts 3.6+        # 图表
```

### 数据存储
- **JSON**: 主要数据格式 (defect, history)
- **SQLite**: 本地数据库 (`database/local_data.db`)
- **Excel**: 映射数据 (AIDA, VIN)
- **Pickle**: 缓存数据

---

## 🚀 快速开始

### 前置要求

- Python 3.8+
- Node.js 18+ (用于 Agent UI)
- BMW 内网访问权限 (Octane API)

### 1️⃣ 安装 Python 依赖

```bash
# 克隆项目
cd testanalysis

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2️⃣ 配置环境

```bash
# 创建配置文件
cp login_info.txt.example login_info.txt
# 编辑 login_info.txt 填入 BMW SSO 凭据

# 配置 DeepSeek API (可选)
export DEEPSEEK_API_KEY="sk-..."
```

### 3️⃣ 准备数据

```bash
# 下载最新缺陷数据
python downloader3.py --defect-years 2025 --auth-method cookie

# 更新 AIDA 映射
python aida_mapping_updater.py
```

### 4️⃣ 启动应用

#### 方式 A: 主仪表板 (推荐)
```bash
# 启动主应用 (端口 8051)
python defect_explore.py

# 访问 http://localhost:8051
```

#### 方式 B: Agent UI (Next.js 前端)
```bash
cd agent_ui
cp .env.local.example .env.local
# 编辑 .env.local 填入 DEEPSEEK_API_KEY

npm install
npm run dev

# 访问 http://localhost:3000
```

#### 方式 C: 独立模块
```bash
# 风险分析
python risk_analysis.py          # 端口 8057

# 缺陷矩阵 (含 AI)
python defect_matrix.py          # 端口 8053

# 测试覆盖率
python test_coverage.py          # 端口 8055
```

#### 方式 D: 应用启动器
```bash
# 快速启动
python app_launcher.py --quick-start

# 启动所有模块
python app_launcher.py --with-submodules

# 查看状态
python app_launcher.py --status
```

---

## 📂 项目结构

```
testanalysis/
├── 📊 核心分析模块
│   ├── defect_explore.py          # 主仪表板 (8051)
│   ├── defect_matrix.py           # 缺陷矩阵 (8053)
│   ├── defect_trend.py            # 缺陷趋势 (8052)
│   ├── defect_map.py              # 地理分布 (8054)
│   ├── defect_coverage.py         # 覆盖率分析 (8056)
│   ├── risk_analysis.py           # 风险评估 (8057)
│   └── test_coverage.py           # 测试覆盖率 (8055)
│
├── 🤖 AI 集成
│   ├── ai_chat_manager.py         # AI 聊天管理器
│   ├── agent_ui/                  # Next.js 前端
│   │   ├── app/                   # Next.js App Router
│   │   ├── components/            # React 组件
│   │   ├── lib/                   # 工具函数
│   │   └── package.json
│   └── sso_session.py             # BMW SSO 认证
│
├── 📥 数据采集
│   ├── downloader3.py             # 主下载器
│   ├── downloader5.py             # 备用下载器
│   ├── downloader6.py             # 增强下载器
│   ├── history_downloader.py      # 历史数据
│   └── qgate.py                   # QGate 数据
│
├── 💾 数据管理
│   ├── data_processor.py          # 核心处理器
│   ├── db_storage.py              # 数据库操作
│   ├── unified_cache_manager.py   # 缓存管理
│   └── cleanup_cache.py           # 清理工具
│
├── 📁 数据目录
│   ├── defect/                    # 缺陷数据
│   │   ├── 2025_defect.json       # 主要数据 (47MB)
│   │   └── 2025_defect_master.json
│   ├── history/                   # 历史数据
│   ├── aida/                      # AIDA 映射
│   ├── cache/                     # 缓存文件
│   ├── database/                  # SQLite 数据库
│   └── mr/                        # 测试需求数据
│
├── 📓 配置文件
│   ├── config.py                  # 统一配置
│   ├── dash_common_styles.py      # 样式定义
│   ├── page_components.py         # 页面组件
│   └── navigation_manager.py      # 导航管理
│
├── 🔧 工具脚本
│   ├── app_launcher.py            # 应用启动器
│   ├── run_app.py                 # 运行脚本
│   ├── deploy.py                  # 部署脚本
│   └── longrunner_analysis.py     # 长期运行分析
│
├── 📓 Jupyter Notebooks
│   ├── Defect Management 2025.ipynb
│   ├── Test Management 2025.ipynb
│   └── Downloader.ipynb
│
└── 📄 文档
    ├── README.md                  # 本文档
    ├── CLAUDE.md                  # Claude Code 指南
    ├── requirements.txt           # Python 依赖
    └── .gitignore                 # Git 忽略规则
```

---

## 🔧 开发指南

### 添加新模块

1. **更新配置** (`config.py`)
   ```python
   NAVIGATION_CONFIG = [
       {
           'id': 'tab-new-module',
           'label': '新模块',
           'icon': 'fas fa-chart-bar',
           'component': 'new_module_page',
           'enabled': True
       },
       # ... 其他模块
   ]
   ```

2. **创建页面组件** (`page_components.py`)
   ```python
   def create_new_module_page(self):
       return html.Div([
           nav_manager.create_breadcrumb('tab-new-module'),
           html.H2("新模块"),
           # 页面内容
       ])
   ```

3. **注册回调**
   ```python
   @app.callback(
       Output('new-module-content', 'children'),
       [Input('new-module-filter', 'value')]
   )
   def update_new_module(filters):
       # 回调逻辑
       pass
   ```

### 集成 AI 功能

```python
from ai_chat_manager import ai_chat_manager

# 创建聊天界面
ai_chat_manager.create_chat_interface(
    chat_id_prefix='my-dashboard-chat',
    dashboard_type='defect'  # 'defect', 'test', 'trend', 'general'
)

# 注册回调
ai_chat_manager.register_chat_callbacks(
    app=app,
    chat_id_prefix='my-dashboard-chat',
    data_store_id='filtered-data',
    dashboard_type='defect'
)
```

### 样式自定义

项目支持主题切换，在 `dash_common_styles.py` 中定义：
- 明亮主题
- 暗色主题
- 组件样式
- 响应式布局

---

## 🧹 缓存管理

### 查看缓存状态
```bash
python cleanup_cache.py
```

### 手动清理
```bash
# 清理 Python 缓存
find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# 清理 7 天以上的缓存文件
find cache/ -name "*.pkl" -mtime +7 -delete 2>/dev/null
```

### 缓存配置
- **最大缓存大小**: 10GB
- **文件保留天数**: 30 天
- **自动清理阈值**: 超过 80% 限制时触发

---

## 📝 Risk Score 算法详解

### 核心维度 (总分 200+)

| 维度 | 权重 | 算法特点 |
|------|------|----------|
| **Matrix 严重度** | 30 分 | 指数衰减 `30 × e^(-0.25 × order)` |
| **分类标签** | 30 分 | 线性阶梯 |
| **ECU 转移次数** | 30 分 | 阶梯递增 |
| **域转移次数** | 20 分 | 阶梯递增 |
| **父票复杂度** | 30 分 | 对数增长 `10 × log(count+1) × 2.5` |
| **子票复杂度** | 30 分 | 对数增长 |
| **处理时间** | 25 分 | 双峰分布 |
| **Shift PU** | 10 分 | 二元状态 |

### 风险等级划分

| 分数范围 | 风险等级 | 说明 |
|---------|---------|------|
| ≥140 分 | 🔴 极高风险 | 立即处理 |
| ≥100 分 | 🟠 高风险 | 高优先级 |
| ≥60 分 | 🟡 中风险 | TopIssue 阈值 |
| ≥30 分 | 🟢 低风险 | 正常跟踪 |
| <30 分 | ⚪ 无风险 | 常规处理 |

---

## 🔐 安全与认证

### BMW SSO 配置

```python
# login_info.txt 格式
{
    "username": "your.username@bmw.com",
    "password": "your_password",
    "octane_url": "https://octane-prod.bmwgroup.net"
}
```

### API 密钥管理

```bash
# DeepSeek API
export DEEPSEEK_API_KEY="sk-..."

# 或使用 .env 文件
echo "DEEPSEEK_API_KEY=sk-..." > .env
```

---

## 🐛 故障排查

### 常见问题

**Q: Agent UI 启动报错 "404"**
```bash
# 清理缓存并禁用 Turbopack
cd agent_ui
rm -rf .next
npm run dev  # 确保使用了 NEXT_PRIVATE_DISABLE_TURBOPACK=1
```

**Q: 数据下载失败**
- 检查 VPN 连接 (BMW 内网)
- 验证 `login_info.txt` 凭据
- 尝试使用 `--auth-method sso` 参数

**Q: AI 功能无响应**
- 验证 API 密钥: `echo $DEEPSEEK_API_KEY`
- 检查网络连接
- 查看浏览器控制台错误日志

---

## 📈 性能优化

### 数据预加载
```python
# defect_explore.py 内置优化
- 历史数据后台预加载
- LRU 缓存机制
- 单例数据管理
```

### 并发下载
```bash
# 多线程下载
python downloader3.py --defect-years 2025 --workers 4
```

---

## 🚢 部署指南

### 生产环境

```bash
# 启动生产服务
python deploy.py start

# 后台运行
nohup python defect_explore.py > logs/app.log 2>&1 &

# 使用 Gunicorn (推荐)
gunicorn -w 4 -b 0.0.0.0:8051 defect_explore:server
```

### Docker 部署 (可选)

```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "defect_explore.py"]
```

---

## 📞 支持与反馈

- 📧 Email: 项目维护者
- 🐛 Issues: 创建 GitHub Issue
- 📖 Wiki: 项目文档
- 💬 Discussions: 项目讨论区

---

## 📜 许可证

内部项目 - BMW 专用

---

## 🙏 致谢

感谢宝马 DTSV 团队的支持和贡献。

---

**最后更新**: 2025-01-14
**版本**: 2.0.0
**维护者**: PreAnalysis Team

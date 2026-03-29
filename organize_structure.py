#!/usr/bin/env python3
"""
目录结构整理 - 2026-03-29

分析当前文件，创建推荐的目录结构

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-29
"""

import os
import shutil
from pathlib import Path
import json
from typing import Dict, List, Any

# 项目根目录
PROJECT_ROOT = Path("/Users/kangyongge/WorkBuddy/Claw/testagent")


def analyze_current_structure() -> Dict[str, Any]:
    """分析当前的目录结构"""
    print("=" * 70)
    print("分析当前目录结构")
    print("=" * 70 + "\n")

    # 文件分类
    file_categories = {
        "agent_managers": [],
        "specialized_agents": [],
        "sql_engines": [],
        "components": [],
        "utils": [],
        "data_processing": [],
        "visualization": [],
        "download": [],
        "demos": [],
        "tests": [],
        "tests_chatdb": [],
        "tests_database": [],
        "tests_tests": [],
        "databases": [],
        "config": [],
        "docs": [],
        "ai_chat": [],
        "optimization": []
    }

    # 扫描所有 Python 文件
    py_files = list(PROJECT_ROOT.glob("*.py"))

    for file_path in py_files:
        file_name = file_path.name

        # 分类
        if "chat" in file_name and "manager" in file_name:
            file_categories["agent_managers"].append(file_name)
        elif "agent" in file_name and "team" in file_name:
            file_categories["specialized_agents"].append(file_name)
        elif "sql" in file_name and "engine" in file_name:
            file_categories["sql_engines"].append(file_name)
        elif "sql_query_engine" in file_name or "enhanced_prompt" in file_name or "ai_chat_with_sql" in file_name:
            file_categories["optimization"].append(file_name)
        elif "business" in file_name or "config_center" in file_name or "chat_components" in file_name:
            file_categories["components"].append(file_name)
        elif "data_processor" in file_name or "cleanup" in file_name:
            file_categories["utils"].append(file_name)
        elif "dashboard" in file_name:
            file_categories["visualization"].append(file_name)
        elif "download" in file_name:
            file_categories["download"].append(file_name)
        elif "demo" in file_name:
            file_categories["demos"].append(file_name)
        elif "benchmark" in file_name:
            file_categories["tests"].append(file_name)
        elif file_name.startswith("test_") and "chat" in file_name and "db" in file_name:
            file_categories["tests_chatdb"].append(file_name)
        elif file_name.startswith("test_") and "database" in file_name:
            file_categories["tests_database"].append(file_name)
        elif file_name.startswith("test_") and "enhanced" in file_name:
            file_categories["tests_tests"].append(file_name)
        elif file_name.startswith("test_"):
            file_categories["tests"].append(file_name)
        elif file_name.startswith("db_"):
            file_categories["databases"].append(file_name)
        elif file_name.startswith("config"):
            file_categories["config"].append(file_name)
        else:
            file_categories["data_processing"].append(file_name)

    # 扫描数据库文件
    db_files = list(PROJECT_ROOT.glob("database/*.py"))
    for file_path in db_files:
        file_categories["databases"].append(file_path.name)

    # 扫描 chatdb 文件
    chatdb_files = list(PROJECT_ROOT.glob("chatdb/*.py"))
    for file_path in chatdb_files:
        file_categories["sql_engines"].append(file_path.name)

    # 打印分类结果
    print("文件分类结果:\n")

    for category, files in sorted(file_categories.items()):
        if files:
            print(f"【{category}】({len(files)} 个)")
            for i, file_name in enumerate(sorted(files)[:5], 1):
                print(f"  {i}. {file_name}")
            if len(files) > 5:
                print(f"  ... (还有 {len(files) - 5} 个)")
            print()

    return file_categories


def create_recommended_structure() -> Dict[str, Any]:
    """创建推荐的目录结构"""
    print("\n" + "=" * 70)
    print("创建推荐的目录结构")
    print("=" * 70 + "\n")

    recommended_structure = {
        "components/": {
            "description": "核心组件（SQL 查询引擎、Prompt 构建器等）",
            "files": [
                "sql_query_engine.py",
                "enhanced_prompt_builder.py",
                "sql_query_engine_optimized_v2.py",
                "business_knowledge.py",
                "chat_components.py"
            ]
        },
        "agents/specialized/": {
            "description": "专用 Agent（代码解释、数据分析等）",
            "files": [
                "code_interpreter_agent/",
                "defect_explore.py",
                "defect_longrunner.py",
                "defect_matrix.py"
            ]
        },
        "agents/managers/": {
            "description": "Agent Manager（AI Chat Manager、Multi-Agent System 等）",
            "files": [
                "ai_chat_manager.py",
                "ai_chat_with_sql.py",
                "ai_chat_with_sql_optimized.py",
                "agent_team_system.py",
                "multi_agent_system_v2.py",
                "intelligent_agent.py",
                "intelligent_data_agent_v3.py",
                "multi_agent_collaboration_analyzer.py"
            ]
        },
        "components/data/": {
            "description": "数据组件（数据处理器、数据库管理器等）",
            "files": [
                "data_processor.py",
                "db_storage.py",
                "database/agent_data_understanding.py",
                "database/agent_data_understanding_v3.py",
                "database/data_aware_agent.py",
                "database/enhanced_agent_data_understanding_v2.py",
                "database/enhanced_data_understanding.py",
                "database/optimized_db_manager.py",
                "database/test_data_agent.py"
            ]
        },
        "components/visualization/": {
            "description": "可视化组件（仪表板、图表等）",
            "files": [
                "dashboard_viewer.py",
                "dash_common_styles.py"
            ]
        },
        "components/utils/": {
            "description": "工具组件（下载器、缓存清理等）",
            "files": [
                "cleanup_cache.py",
                "download/",
                "config.py",
                "config_center.py"
            ]
        },
        "optimization/": {
            "description": "优化组件（快速优化、中期优化、长期优化）",
            "files": [
                "quick_opt_1_error_examples.py",
                "quick_opt_2_time_range.py",
                "quick_opt_3_data_type.py",
                "quick_opt_4_business_context.py",
                "quick_opt_summary.py",
                "quick_opt_final_summary.py",
                "mid_opt_1_feedback_loop.py",
                "mid_opt_2_incremental_learning.py",
                "mid_opt_3_intelligent_routing.py",
                "mid_opt_summary.py",
                "long_opt_1_knowledge_graph.py",
                "SQL_ACCURACY_OPTIMIZATION_PLAN.md",
                "SQL_ACCURACY_100_PERCENT_PLAN.md",
                "quick_start_accuracy.py"
            ]
        },
        "chatdb/": {
            "description": "ChatDB 相关组件（Text-to-SQL Agent 等）",
            "files": [
                "text_to_sql_agent.py",
                "test_text_to_sql_agent.py"
            ]
        },
        "tests/": {
            "description": "测试文件",
            "files": [
                "tests/",
                "test_*.py",
                "benchmark_*.py"
            ]
        },
        "demos/": {
            "description": "演示文件",
            "files": [
                "demo_*.py"
            ]
        },
        "docs/": {
            "description": "文档文件",
            "files": [
                "*.md",
                "*.html"
            ]
        },
        "database/": {
            "description": "数据库文件",
            "files": [
                "*.db",
                "*.db-shm",
                "*.db-wal",
                "feedback.db"
            ]
        },
        ".github/": {
            "description": "GitHub 配置",
            "files": [
                ".github/"
            ]
        },
        "config/": {
            "description": "配置文件",
            "files": [
                ".env.example",
                ".gitignore",
                "openclaw_configs/",
                "agent_team_configs/"
            ]
        },
        "memory/": {
            "description": "工作记忆",
            "files": [
                "memory/"
            ]
        }
    }

    # 打印推荐结构
    print("推荐的目录结构:\n")

    for directory, info in sorted(recommended_structure.items()):
        if directory.endswith("/"):
            print(f"【{directory}】")
            print(f"  描述: {info['description']}")
            print(f"  文件:")
            for i, file_name in enumerate(info['files'][:5], 1):
                print(f"    {i}. {file_name}")
            if len(info['files']) > 5:
                print(f"    ... (还有 {len(info['files']) - 5} 个)")
            print()

    return recommended_structure


def create_migration_script() -> str:
    """创建迁移脚本"""
    print("\n" + "=" * 70)
    print("创建迁移脚本")
    print("=" * 70 + "\n")

    migration_script = """#!/bin/bash
# 目录结构迁移脚本
# 日期: 2026-03-29
# 作者: Jarvis (OpenClaw Agent)

echo "开始迁移..."

# 创建新目录
echo "创建新目录..."
mkdir -p components
mkdir -p components/data
mkdir -p components/visualization
mkdir -p components/utils
mkdir -p agents/specialized
mkdir -p agents/managers
mkdir -p optimization
mkdir -p docs
mkdir -p demos
mkdir -p config

# 移动文件
echo "移动组件文件..."
mv enhanced_prompt_builder.py components/ 2>/dev/null || true
mv business_knowledge.py components/ 2>/dev/null || true
mv chat_components.py components/ 2>/dev/null || true
mv config.py components/utils/ 2>/dev/null || true
mv config_center.py components/utils/ 2>/dev/null || true
mv cleanup_cache.py components/utils/ 2>/dev/null || true
mv db_storage.py components/data/ 2>/dev/null || true
mv data_processor.py components/data/ 2>/dev/null || true
mv dashboard_viewer.py components/visualization/ 2>/dev/null || true
mv dash_common_styles.py components/visualization/ 2>/dev/null || true

# 移动 Agent 文件
echo "移动 Agent 文件..."
mv code_interpreter_agent agents/specialized/ 2>/dev/null || true
mv defect_explore.py agents/specialized/ 2>/dev/null || true
mv defect_longrunner.py agents/specialized/ 2>/dev/null || true
mv defect_matrix.py agents/specialized/ 2>/dev/null || true
mv ai_chat_manager.py agents/managers/ 2>/dev/null || true
mv ai_chat_with_sql.py agents/managers/ 2>/dev/null || true
mv ai_chat_with_sql_optimized.py agents/managers/ 2>/dev/null || true
mv agent_team_system.py agents/managers/ 2>/dev/null || true
mv multi_agent_system_v2.py agents/managers/ 2>/dev/null || true
mv intelligent_agent.py agents/managers/ 2>/dev/null || true
mv intelligent_data_agent_v3.py agents/managers/ 2>/dev/null || true
mv multi_agent_collaboration_analyzer.py agents/managers/ 2>/dev/null || true

# 移动优化文件
echo "移动优化文件..."
mv quick_opt_*.py optimization/ 2>/dev/null || true
mv mid_opt_*.py optimization/ 2>/dev/null || true
mv long_opt_*.py optimization/ 2>/dev/null || true
mv SQL_ACCURACY*.md optimization/docs/ 2>/dev/null || true
mv quick_start_accuracy.py optimization/ 2>/dev/null || true

# 移动测试文件
echo "移动测试文件..."
mv test_*.py tests/ 2>/dev/null || true
mv benchmark_*.py tests/ 2>/dev/null || true
mv tests/ tests/ 2>/dev/null || true

# 移动演示文件
echo "移动演示文件..."
mv demo_*.py demos/ 2>/dev/null || true

# 移动文档文件
echo "移动文档文件..."
mv *.md docs/ 2>/dev/null || true
mv *.html docs/ 2>/dev/null || true

# 移动配置文件
echo "移动配置文件..."
mv .gitignore config/ 2>/dev/null || true
mv .env.example config/ 2>/dev/null || true
mv openclaw_configs/ config/ 2>/dev/null || true
mv agent_team_configs/ config/ 2>/dev/null || true

echo "迁移完成！"
"""

    print("迁移脚本长度:", len(migration_script), "字符")
    print()

    return migration_script


def create_structure_document() -> str:
    """创建目录结构文档"""
    print("\n" + "=" * 70)
    print("创建目录结构文档")
    print("=" * 70 + "\n")

    structure_doc = """# 推荐的目录结构

创建时间: 2026-03-29
作者: Jarvis (OpenClaw Agent)

---

## 推荐的目录结构

```
testagent/
├── components/                    # 核心组件
│   ├── sql_query_engine.py       # SQL 查询引擎
│   ├── enhanced_prompt_builder.py # 增强 Prompt 构建器
│   ├── sql_query_engine_optimized_v2.py # 优化的 SQL 查询引擎
│   ├── business_knowledge.py      # 业务知识
│   ├── chat_components.py         # Chat 组件
│   ├── data/                      # 数据组件
│   │   ├── data_processor.py      # 数据处理器
│   │   └── db_storage.py         # 数据库存储
│   ├── visualization/             # 可视化组件
│   │   ├── dashboard_viewer.py   # 仪表板查看器
│   │   └── dash_common_styles.py   # 仪表板样式
│   └── utils/                     # 工具组件
│       ├── config.py               # 配置工具
│       ├── config_center.py       # 配置中心
│       └── cleanup_cache.py        # 缓存清理
│
├── agents/                        # Agent 相关
│   ├── specialized/               # 专用 Agent
│   │   ├── code_interpreter_agent/  # 代码解释 Agent
│   │   ├── defect_explore.py      # 缺陷探索 Agent
│   │   ├── defect_longrunner.py   # 缺陷 LongRunner Agent
│   │   └── defect_matrix.py       # 缺陷矩阵 Agent
│   │
│   └── managers/                  # Agent Manager
│       ├── ai_chat_manager.py      # AI Chat Manager
│       ├── ai_chat_with_sql.py    # AI Chat with SQL
│       ├── ai_chat_with_sql_optimized.py # 优化的 AI Chat with SQL
│       ├── agent_team_system.py    # Agent 团队系统
│       ├── multi_agent_system_v2.py # 多 Agent 系统 v2
│       ├── intelligent_agent.py  # 智能 Agent
│       ├── intelligent_data_agent_v3.py # 智能数据 Agent v3
│       └── multi_agent_collaboration_analyzer.py # 多 Agent 协作分析
│
├── optimization/                  # 优化组件
│   ├── quick_opt_1_error_examples.py    # 快速优化 1
│   ├── quick_opt_2_time_range.py       # 快速优化 2
│   ├── quick_opt_3_data_type.py        # 快速优化 3
│   ├── quick_opt_4_business_context.py  # 快速优化 4
│   ├── quick_opt_summary.py             # 快速优化总结
│   ├── quick_opt_final_summary.py      # 快速优化最终总结
│   ├── mid_opt_1_feedback_loop.py       # 中期优化 1
│   ├── mid_opt_2_incremental_learning.py # 中期优化 2
│   ├── mid_opt_3_intelligent_routing.py # 中期优化 3
│   ├── mid_opt_summary.py                # 中期优化总结
│   ├── long_opt_1_knowledge_graph.py   # 长期优化 1
│   ├── SQL_ACCURACY_OPTIMIZATION_PLAN.md    # SQL 准确率优化计划
│   ├── SQL_ACCURACY_100_PERCENT_PLAN.md    # SQL 准确率 100% 计划
│   └── quick_start_accuracy.py           # 快速开始指南
│
├── tests/                          # 测试文件
│   ├── test_sql_validator.py
│   ├── test_schema_manager.py
│   ├── test_fewshot_examples.py
│   ├── test_enhanced_prompt.py
│   ├── test_integration.py
│   ├── test_fewshot_expansion.py
│   ├── test_text_to_sql_agent.py
│   ├── benchmark_sql_engine.py
│   ├── benchmark_optimized_engine.py
│   ├── run_unit_tests.py
│   └── tests/
│       ├── __init__.py
│       ├── test_sql_validator.py
│       ├── test_schema_manager.py
│       └── test_fewshot_examples.py
│
├── demos/                           # 演示文件
│   ├── demo_agent_team.py
│   ├── demo_context_engine.py
│   ├── demo_smart_agent.py
│   └── ...
│
├── docs/                            # 文档文件
│   ├── README_TESTING.md
│   ├── DEPLOYMENT_GUIDE.md
│   ├── AGENT_CAPABILITY_ANALYSIS.md
│   ├── DASHBOARD_SCREENSHOTS_REPORT.md
│   ├── DB_DESIGN_ANALYSIS_REPORT.md
│   ├── ENTERPRISE_AGENT_ANALYSIS.md
│   ├── INSTALL_OPENCLAW_GUIDE.md
│   ├── OPENCLAW_SETUP_GUIDE.md
│   ├── OPTIMIZATION_REPORT.md
│   ├── PROJECT_OPTIMIZATION_REPORT.md
│   ├── WORK_SUMMARY_20260329.md
│   ├── 2026-03-29-summary.md
│   ├── 2026-03-29-complete-summary.md
│   ├── 2026-03-29-final-summary.md
│   ├── DEEP_ANALYSIS_REPORT_20260323.html
│   └── ...
│
├── config/                          # 配置文件
│   ├── .gitignore
│   ├── .env.example
│   ├── openclaw_configs/
│   └── agent_team_configs/
│
├── database/                        # 数据库文件
│   ├── local_data.db
│   ├── local_data.db-shm
│   ├── local_data.db-wal
│   ├── feedback.db
│   └── ...
│
├── chatdb/                          # ChatDB 相关
│   ├── text_to_sql_agent.py
│   └── ...
│
├── .github/                         # GitHub 配置
│   └── workflows/
│       └── ci-cd.yml
│
└── memory/                          # 工作记忆
    └── 2026-03-29.md
```

---

## 目录说明

### components/
**核心组件**
- `sql_query_engine.py`: SQL 查询引擎（98 个示例）
- `enhanced_prompt_builder.py`: 增强的 Prompt 构建器
- `sql_query_engine_optimized_v2.py`: 优化的 SQL 查询引擎
- `business_knowledge.py`: 业务知识
- `chat_components.py`: Chat 组件

**数据组件** (`components/data/`)
- `data_processor.py`: 数据处理器
- `db_storage.py`: 数据库存储

**可视化组件** (`components/visualization/`)
- `dashboard_viewer.py`: 仪表板查看器
- `dash_common_styles.py`: 仪表板样式

**工具组件** (`components/utils/`)
- `config.py`: 配置工具
- `config_center.py`: 配置中心
- `cleanup_cache.py`: 缓存清理

### agents/
**专用 Agent** (`agents/specialized/`)
- `code_interpreter_agent/`: 代码解释 Agent
- `defect_explore.py`: 缺陷探索 Agent
- `defect_longrunner.py`: 缺陷 LongRunner Agent
- `defect_matrix.py`: 缺陷矩阵 Agent

**Agent Manager** (`agents/managers/`)
- `ai_chat_manager.py`: AI Chat Manager
- `ai_chat_with_sql.py`: AI Chat with SQL
- `ai_chat_with_sql_optimized.py`: 优化的 AI Chat with SQL
- `agent_team_system.py`: Agent 团队系统
- `multi_agent_system_v2.py`: 多 Agent 系统 v2

### optimization/
**快速优化** (100% 完成)
- `quick_opt_1_error_examples.py`: 优化常见错误示例
- `quick_opt_2_time_range.py`: 增强时间范围提示
- `quick_opt_3_data_type.py`: 优化数据类型映射
- `quick_opt_4_business_context.py`: 增加业务上下文
- `quick_opt_summary.py`: 快速优化总结
- `quick_opt_final_summary.py`: 快速优化最终总结

**中期优化** (框架 100% 完成)
- `mid_opt_1_feedback_loop.py`: 实现反馈循环
- `mid_opt_2_incremental_learning.py`: 实现增量学习
- `mid_opt_3_intelligent_routing.py`: 优化智能路由
- `mid_opt_summary.py`: 中期优化总结

**长期优化** (33% 完成)
- `long_opt_1_knowledge_graph.py`: 实现业务知识图谱
- `long_opt_2_multi_model.py`: 实现多模型集成（待进行）
- `long_opt_3_reinforcement_learning.py`: 实现强化学习优化（待进行）

### tests/
**单元测试**
- `test_sql_validator.py`: SQL 验证器测试
- `test_schema_manager.py`: Schema 管理器测试
- `test_fewshot_examples.py`: Few-shot 示例测试
- `test_enhanced_prompt.py`: 增强 Prompt 测试
- `test_integration.py`: 集成测试

**基准测试**
- `benchmark_sql_engine.py`: SQL 引擎基准测试
- `benchmark_optimized_engine.py`: 优化引擎基准测试

**测试运行器**
- `run_unit_tests.py`: 单元测试运行器
- `test_fewshot_expansion.py`: Few-shot 扩充测试

### docs/
**测试文档**
- `README_TESTING.md`: 测试框架文档

**部署文档**
- `DEPLOYMENT_GUIDE.md`: 部署指南

**分析报告**
- `AGENT_CAPABILITY_ANALYSIS.md`: Agent 能力分析
- `DASHBOARD_SCREENSHOTS_REPORT.md`: 仪表板截图报告
- `DB_DESIGN_ANALYSIS_REPORT.md`: 数据库设计分析
- `ENTERPRISE_AGENT_ANALYSIS.md`: 企业 Agent 分析

**安装指南**
- `INSTALL_OPENCLAW_GUIDE.md`: OpenClaw 安装指南
- `OPENCLAW_SETUP_GUIDE.md`: OpenClaw 设置指南

**优化报告**
- `OPTIMIZATION_REPORT.md`: 优化报告
- `PROJECT_OPTIMIZATION_REPORT.md`: 项目优化报告

**工作总结**
- `WORK_SUMMARY_20260329.md`: 3月29日工作总结
- `2026-03-29-summary.md`: 3月29日总结
- `2026-03-29-complete-summary.md`: 3月29日完整总结
- `2026-03-29-final-summary.md`: 3月29日最终总结

### config/
**配置文件**
- `.gitignore`: Git 忽略文件
- `.env.example`: 环境变量示例
- `openclaw_configs/`: OpenClaw 配置
- `agent_team_configs/`: Agent 团队配置

### database/
**数据库文件**
- `local_data.db`: 本地数据库
- `local_data.db-shm`: 数据库临时文件
- `local_data.db-wal`: 数据库日志文件
- `feedback.db`: 反馈数据库

---

## 迁移步骤

1. **备份当前项目**
   ```bash
   cd ~/WorkBuddy/Claw/testagent
   cp -r . ../testagent_backup_$(date +%Y%m%d)
   ```

2. **创建新目录**
   ```bash
   mkdir -p components/data
   mkdir -p components/visualization
   mkdir -p components/utils
   mkdir -p agents/specialized
   mkdir -p agents/managers
   mkdir -p optimization/docs
   mkdir -p docs
   mkdir -p demos
   mkdir -p config
   ```

3. **移动文件**（使用提供的迁移脚本）

4. **更新导入路径**（需要手动调整）

5. **测试新结构**
   ```bash
   python3 run_unit_tests.py
   ```

---

## 维护建议

1. **保持清晰的职责分离**
   - 组件只做一件事
   - Agent 负责决策和协调
   - Manager 负责统一管理

2. **定期整理目录**
   - 不相关的文件移到 `archive/`
   - 测试文件移到 `tests/`
   - 文档文件移到 `docs/`

3. **保持文档同步**
   - 更新 README
   - 更新架构文档
   - 记录变更历史

---

创建时间: 2026-03-29
作者: Jarvis (OpenClaw Agent)
"""

    print("目录结构文档长度:", len(structure_doc), "字符")
    print()

    return structure_doc


def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("🗂️ 目录结构整理")
    print("=" * 70 + "\n")

    # 分析当前结构
    file_categories = analyze_current_structure()

    # 创建推荐结构
    recommended_structure = create_recommended_structure()

    # 创建迁移脚本
    migration_script = create_migration_script()

    # 创建文档
    structure_doc = create_structure_document()

    # 保存文档
    doc_path = PROJECT_ROOT / "RECOMMENDED_STRUCTURE_20260329.md"
    with open(doc_path, 'w', encoding='utf-8') as f:
        f.write(structure_doc)

    # 保存迁移脚本
    script_path = PROJECT_ROOT / "migrate_structure.sh"
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(migration_script)

    # 添加执行权限
    os.chmod(script_path, 0o755)

    # 保存分析结果
    analysis_path = PROJECT_ROOT / "structure_analysis.json"
    with open(analysis_path, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": "2026-03-29",
            "file_categories": file_categories,
            "recommended_structure": {
                dir: {
                    "description": info["description"],
                    "file_count": len(info["files"])
                }
                for dir, info in recommended_structure.items()
            }
        }, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("📄 保存的文件")
    print("=" * 70 + "\n")

    print("1. RECOMMENDED_STRUCTURE_20260329.md")
    print(f"   位置: {doc_path}")
    print()
    print("2. migrate_structure.sh")
    print(f"   位置: {script_path}")
    print()
    print("3. structure_analysis.json")
    print(f"   位置: {analysis_path}")
    print()

    print("=" * 70)
    print("🗂️ 目录结构整理完成！")
    print("=" * 70 + "\n")

    print("【下一步】")
    print("1. 查看推荐目录结构文档")
    print("2. 备份当前项目")
    print("3. 运行迁移脚本（可选）")
    print("4. 手动调整导入路径")
    print("5. 测试新结构")
    print()


if __name__ == "__main__":
    main()

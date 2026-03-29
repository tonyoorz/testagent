#!/bin/bash
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

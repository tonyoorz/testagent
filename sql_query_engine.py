#!/usr/bin/env python3
"""
SQL 查询引擎 - Text-to-SQL 核心模块

基于 Harness Engineering 原则设计：
- 强约束：Schema 上下文 + 业务知识 + Few-shot 示例
- 快速反馈：执行前验证，错误后自纠正
- 幂等性：多次生成相同问题的 SQL 一致

集成方式：
from sql_query_engine import SQLQueryEngine
engine = SQLQueryEngine()
result = engine.query("最近一周的测试通过率是多少？")

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import sqlite3
import re
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import pandas as pd

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# 配置类
# ============================================================================

@dataclass
class SQLQueryConfig:
    """SQL 查询配置"""
    db_path: str = "database/local_data.db"
    max_retries: int = 3
    enable_cache: bool = True
    cache_ttl_seconds: int = 3600  # 缓存 1 小时
    verbose: bool = True
    
    # 危险操作黑名单
    dangerous_keywords: List[str] = field(default_factory=lambda: [
        "DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE", "INSERT", "CREATE"
    ])


# ============================================================================
# Schema 管理器
# ============================================================================

class SchemaManager:
    """数据库 Schema 管理"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._schema_cache = None
    
    def get_schema(self, force_refresh: bool = False) -> str:
        """获取数据库 Schema 上下文"""
        if self._schema_cache and not force_refresh:
            return self._schema_cache
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 获取所有表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        
        schema_parts = ["数据库 Schema：\n"]
        
        for table in tables:
            schema_parts.append(f"\n### 表: {table}")
            
            # 获取列信息
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            
            schema_parts.append("字段:")
            for col in columns:
                col_id, name, col_type, not_null, default, pk = col
                pk_mark = " (PK)" if pk else ""
                null_mark = " NOT NULL" if not_null else ""
                schema_parts.append(f"  - {name}: {col_type}{pk_mark}{null_mark}")
            
            # 获取索引
            cursor.execute(f"PRAGMA index_list({table})")
            indexes = cursor.fetchall()
            if indexes:
                schema_parts.append("索引:")
                for idx in indexes:
                    schema_parts.append(f"  - {idx[1]}")
        
        conn.close()
        self._schema_cache = "\n".join(schema_parts)
        return self._schema_cache
    
    def get_table_sample(self, table_name: str, limit: int = 3) -> str:
        """获取表数据样本"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
            rows = cursor.fetchall()
            
            # 获取列名
            columns = [desc[0] for desc in cursor.description]
            
            conn.close()
            
            # 格式化样本
            sample_parts = [f"\n### 表 {table_name} 样本数据（前 {limit} 行）："]
            sample_parts.append("字段: " + ", ".join(columns))
            
            for row in rows:
                sample_parts.append("数据: " + ", ".join([str(v) if v is not None else "NULL" for v in row]))
            
            return "\n".join(sample_parts)
        except Exception as e:
            logger.warning(f"获取表样本失败: {e}")
            return ""


# ============================================================================
# 业务知识库
# ============================================================================

class BusinessKnowledge:
    """业务知识管理"""
    
    KNOWLEDGE_BASE = """
业务术语说明：
- test_week（测试周）: 格式为 'YY-CWww'，例如 '26-CW12' 表示 2026 年第 12 周
- severity（缺陷严重度）: Critical（致命） > Major（严重） > Medium（中等） > Minor（轻微）
- status（测试状态）: Passed（通过）、Failed（失败）、Blocked（阻塞）、No Run（未运行）
- defect status（缺陷状态）: New（新建）、Open（打开）、In Progress（进行中）、Fixed（已修复）、Closed（已关闭）
- AIDA: 汽车仪表显示系统（Automotive Instrument Display Application）
- build_number: 构建号，用于关联测试执行和缺陷
- project/module/component: 三级项目结构（项目 -> 模块 -> 组件）
- pingpong: 缺陷重开次数，值越大表示问题越难解决
- coverage_percent: 测试覆盖率 = (已测试用例 / 总用例) * 100

时间过滤建议：
- 使用 creation_time（缺陷创建时间）、start_time（测试开始时间）
- SQLite 日期函数: date('now'), datetime('now', '-7 days'), strftime('%Y-%m', creation_time)

查询最佳实践：
1. 统计时使用 COUNT(*), SUM(), AVG() 等聚合函数
2. 处理除法时使用 NULLIF 防止除零: COUNT(*) / NULLIF(SUM(condition), 0)
3. 关联表时使用 build_number 或 project + module + component
4. 时间范围使用 WHERE creation_time >= date('now', '-7 days')
5. 分组使用 GROUP BY, 排序使用 ORDER BY

常见查询模式：
1. 数量统计: SELECT COUNT(*) FROM table_name WHERE condition
2. 分组统计: SELECT column, COUNT(*) FROM table_name GROUP BY column ORDER BY COUNT(*) DESC
3. 通过率: SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) FROM test_runs
4. 缺陷密度: SELECT project, COUNT(*) as defect_count FROM defects GROUP BY project
5. 趋势分析: GROUP BY strftime('%Y-%m', creation_time) 或 GROUP BY test_week
"""
    
    @classmethod
    def get_knowledge(cls) -> str:
        """获取业务知识"""
        return cls.KNOWLEDGE_BASE


# ============================================================================
# Few-shot 示例管理器
# ============================================================================

class FewShotExamples:
    """Few-shot 示例管理"""
    
    EXAMPLES = [
        # ========== 基础统计查询 (4个) ==========
        {
            "question": "统计所有缺陷的数量",
            "sql": "SELECT COUNT(*) as total_defects FROM defects"
        },
        {
            "question": "统计 Critical 级别的缺陷数量",
            "sql": "SELECT COUNT(*) as critical_defects FROM defects WHERE severity = 'Critical'"
        },
        {
            "question": "各模块的缺陷数量统计",
            "sql": "SELECT module, COUNT(*) as defect_count FROM defects GROUP BY module ORDER BY defect_count DESC"
        },
        {
            "question": "测试通过率是多少",
            "sql": "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs"
        },

        # ========== 时间过滤查询 (4个) ==========
        {
            "question": "最近7天的测试通过率",
            "sql": "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs WHERE start_time >= date('now', '-7 days')"
        },
        {
            "question": "本周新增的缺陷数量",
            "sql": "SELECT COUNT(*) as new_defects_this_week FROM defects WHERE creation_time >= date('now', 'weekday 0', '-7 days', 'start of day')"
        },
        {
            "question": "最近30天创建的 Critical 缺陷",
            "sql": "SELECT * FROM defects WHERE severity = 'Critical' AND creation_time >= date('now', '-30 days') ORDER BY creation_time DESC"
        },
        {
            "question": "本月测试执行次数",
            "sql": "SELECT COUNT(*) as test_count FROM test_runs WHERE start_time >= date('now', 'start of month')"
        },

        # ========== 多表 JOIN 查询 (12个) ==========
        {
            "question": "每个缺陷对应的测试执行情况",
            "sql": "SELECT d.id, d.severity, d.status as defect_status, tr.test_name, tr.result as test_result FROM defects d LEFT JOIN test_runs tr ON d.build_number = tr.build_number WHERE d.id IS NOT NULL LIMIT 20"
        },
        {
            "question": "测试覆盖率与缺陷数量的关系",
            "sql": "SELECT tc.module, tc.component, tc.coverage_percent, COUNT(d.id) as defect_count FROM test_coverage tc LEFT JOIN defects d ON tc.module = d.module AND tc.component = d.component WHERE tc.test_week = (SELECT MAX(test_week) FROM test_coverage) GROUP BY tc.module, tc.component ORDER BY tc.coverage_percent ASC"
        },
        {
            "question": "各项目在不同严重度上的缺陷分布",
            "sql": "SELECT d.project, d.severity, COUNT(*) as defect_count, ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM defects WHERE project = d.project), 2) as percentage FROM defects d GROUP BY d.project, d.severity ORDER BY d.project, COUNT(*) DESC"
        },
        {
            "question": "测试失败的用例对应的缺陷",
            "sql": "SELECT tr.test_name, tr.project, tr.module, d.id as defect_id, d.severity, d.status as defect_status FROM test_runs tr INNER JOIN defects d ON tr.build_number = d.build_number WHERE tr.result = 'Failed' ORDER BY tr.start_time DESC LIMIT 15"
        },
        {
            "question": "模块的测试通过率与缺陷数量的对比",
            "sql": "SELECT tr.module, ROUND(100.0 * SUM(CASE WHEN tr.status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate, COUNT(DISTINCT d.id) as defect_count FROM test_runs tr LEFT JOIN defects d ON tr.build_number = d.build_number GROUP BY tr.module ORDER BY defect_count DESC"
        },
        {
            "question": "查找关联同一构建号的测试和缺陷",
            "sql": "SELECT tr.test_name, tr.status as test_status, d.id as defect_id, d.severity, d.status as defect_status FROM test_runs tr INNER JOIN defects d ON tr.build_number = d.build_number WHERE tr.build_number = '2025-WW10-Build123' ORDER BY tr.start_time DESC"
        },
        {
            "question": "每个组件的覆盖率和缺陷密度分析",
            "sql": "SELECT tc.module, tc.component, tc.coverage_percent, COUNT(d.id) as defect_count, ROUND(COUNT(d.id) * 100.0 / NULLIF(tc.coverage_percent, 0), 2) as defect_density FROM test_coverage tc LEFT JOIN defects d ON tc.module = d.module AND tc.component = d.component WHERE tc.test_week = (SELECT MAX(test_week) FROM test_coverage) GROUP BY tc.module, tc.component ORDER BY defect_density DESC"
        },
        {
            "question": "测试覆盖率低的模块的缺陷情况",
            "sql": "SELECT tc.module, tc.component, tc.coverage_percent, d.id as defect_id, d.severity, d.status FROM test_coverage tc INNER JOIN defects d ON tc.module = d.module AND tc.component = d.component WHERE tc.test_week = (SELECT MAX(test_week) FROM test_coverage) AND tc.coverage_percent < 70 ORDER BY tc.coverage_percent ASC, d.severity DESC LIMIT 20"
        },
        {
            "question": "多维度分析：项目-模块-组件的测试和缺陷数据",
            "sql": "SELECT tr.project, tr.module, tr.component, COUNT(DISTINCT tr.id) as test_count, ROUND(100.0 * SUM(CASE WHEN tr.status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate, COUNT(DISTINCT d.id) as defect_count FROM test_runs tr LEFT JOIN defects d ON tr.build_number = d.build_number GROUP BY tr.project, tr.module, tr.component ORDER BY defect_count DESC LIMIT 30"
        },
        {
            "question": "查找测试失败但没有关联缺陷的用例",
            "sql": "SELECT tr.id, tr.test_name, tr.project, tr.module, tr.start_time, tr.result FROM test_runs tr LEFT JOIN defects d ON tr.build_number = d.build_number WHERE tr.result = 'Failed' AND d.id IS NULL ORDER BY tr.start_time DESC LIMIT 10"
        },
        {
            "question": "各项目测试执行次数与缺陷数量的比例",
            "sql": "SELECT tr.project, COUNT(DISTINCT tr.id) as total_tests, COUNT(DISTINCT d.id) as total_defects, ROUND(COUNT(DISTINCT d.id) * 100.0 / NULLIF(COUNT(DISTINCT tr.id), 0), 2) as defect_rate FROM test_runs tr LEFT JOIN defects d ON tr.build_number = d.build_number GROUP BY tr.project ORDER BY defect_rate DESC"
        },
        {
            "question": "跨表查找最近一周的高风险组合",
            "sql": "SELECT d.project, d.module, d.severity, d.pingpong, tc.coverage_percent, COUNT(*) as risk_count FROM defects d JOIN test_coverage tc ON d.module = tc.module AND d.component = tc.component WHERE d.creation_time >= date('now', '-7 days') AND tc.test_week = (SELECT MAX(test_week) FROM test_coverage) GROUP BY d.project, d.module, d.severity, d.pingpong, tc.coverage_percent ORDER BY risk_count DESC LIMIT 10"
        },

        # ========== 子查询示例 (12个) ==========
        {
            "question": "缺陷数量超过平均值的模块",
            "sql": "SELECT module, COUNT(*) as defect_count FROM defects GROUP BY module HAVING COUNT(*) > (SELECT AVG(defect_count) FROM (SELECT module, COUNT(*) as defect_count FROM defects GROUP BY subq.module) as subq) ORDER BY defect_count DESC"
        },
        {
            "question": "测试通过率低于项目平均水平的模块",
            "sql": "SELECT module, ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs GROUP BY module HAVING pass_rate < (SELECT ROUND(AVG(pass_rate), 2) FROM (SELECT module, ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs GROUP BY module) as avg_rates) ORDER BY pass_rate ASC"
        },
        {
            "question": "本周的测试覆盖率（使用子查询获取最新周）",
            "sql": "SELECT module, component, coverage_percent FROM test_coverage WHERE test_week = (SELECT MAX(test_week) FROM test_coverage)"
        },
        {
            "question": "找出重开次数最多的前 5 个缺陷",
            "sql": "SELECT * FROM defects WHERE pingpong = (SELECT MAX(pingpong) FROM defects) UNION SELECT * FROM defects WHERE pingpong = (SELECT MAX(pingpong) FROM defects WHERE pingpong < (SELECT MAX(pingpong) FROM defects)) ORDER BY pingpong DESC LIMIT 5"
        },
        {
            "question": "各项目的测试数量，对比项目平均值",
            "sql": "SELECT project, COUNT(*) as test_count, (SELECT AVG(test_count) FROM (SELECT project, COUNT(*) as test_count FROM test_runs GROUP BY project) as avg_counts) as avg_test_count FROM test_runs GROUP BY project ORDER BY test_count DESC"
        },
        {
            "question": "最近一周内的 Critical 缺陷占总 Critical 缺陷的比例",
            "sql": "SELECT ROUND(100.0 * (SELECT COUNT(*) FROM defects WHERE severity = 'Critical' AND creation_time >= date('now', '-7 days')) / NULLIF((SELECT COUNT(*) FROM defects WHERE severity = 'Critical'), 0), 2) as critical_percentage_recent_week"
        },
        {
            "question": "查找缺陷密度最高的模块（缺陷数/测试数）",
            "sql": "SELECT d.module, COUNT(d.id) as defect_count, (SELECT COUNT(*) FROM test_runs WHERE module = d.module) as test_count, ROUND(COUNT(d.id) * 100.0 / NULLIF((SELECT COUNT(*) FROM test_runs WHERE module = d.module), 0), 2) as defect_density FROM defects d GROUP BY d.module HAVING test_count > 0 ORDER BY defect_density DESC LIMIT 10"
        },
        {
            "question": "测试覆盖率超过 80% 且缺陷数量低于平均的模块",
            "sql": "SELECT tc.module, tc.coverage_percent, COUNT(d.id) as defect_count FROM test_coverage tc LEFT JOIN defects d ON tc.module = d.module WHERE tc.test_week = (SELECT MAX(test_week) FROM test_coverage) AND tc.coverage_percent > 80 GROUP BY tc.module, tc.coverage_percent HAVING COUNT(d.id) < (SELECT AVG(defect_count) FROM (SELECT module, COUNT(*) as defect_count FROM defects GROUP BY module) as avg_counts) ORDER BY tc.coverage_percent DESC"
        },
        {
            "question": "查找缺陷修复时间最长的 10 个（已关闭的缺陷）",
            "sql": "SELECT * FROM defects WHERE status = 'Closed' AND (julianday('now') - julianday(creation_time)) > (SELECT AVG(julianday(CASE WHEN status = 'Closed' THEN 'now' ELSE creation_time END) - julianday(creation_time)) FROM defects WHERE status = 'Closed') ORDER BY creation_time ASC LIMIT 10"
        },
        {
            "question": "每个严重度级别中重开次数最多的缺陷",
            "sql": "SELECT * FROM defects WHERE (severity, pingpong) IN (SELECT severity, MAX(pingpong) FROM defects GROUP BY severity) ORDER BY CASE severity WHEN 'Critical' THEN 1 WHEN 'Major' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END"
        },
        {
            "question": "测试通过率提升最快的模块（对比上周）",
            "sql": "SELECT current_week.module, ROUND(100.0 * SUM(CASE WHEN current_week.status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as current_pass_rate, ROUND(100.0 * SUM(CASE WHEN last_week.status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as last_pass_rate FROM test_runs current_week INNER JOIN test_runs last_week ON current_week.module = last_week.module WHERE current_week.start_time >= date('now', 'weekday 0', '-7 days') AND last_week.start_time >= date('now', 'weekday 0', '-14 days') AND last_week.start_time < date('now', 'weekday 0', '-7 days') GROUP BY current_week.module HAVING current_pass_rate > last_pass_rate ORDER BY (current_pass_rate - last_pass_rate) DESC"
        },
        {
            "question": "找出没有测试执行的缺陷",
            "sql": "SELECT d.* FROM defects d WHERE NOT EXISTS (SELECT 1 FROM test_runs tr WHERE tr.build_number = d.build_number) ORDER BY d.creation_time DESC LIMIT 20"
        },

        # ========== 窗口函数示例 (8个) ==========
        {
            "question": "按创建时间排序并给每个缺陷编号",
            "sql": "SELECT id, severity, status, creation_time, ROW_NUMBER() OVER (ORDER BY creation_time DESC) as row_num FROM defects LIMIT 20"
        },
        {
            "question": "每个模块内缺陷数量排名",
            "sql": "SELECT module, id, severity, creation_time, ROW_NUMBER() OVER (PARTITION BY module ORDER BY creation_time DESC) as rank_in_module FROM defects WHERE module IS NOT NULL"
        },
        {
            "question": "查找各模块最新的缺陷",
            "sql": "SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY module ORDER BY creation_time DESC) as rn FROM defects) ranked WHERE rn = 1 ORDER BY creation_time DESC"
        },
        {
            "question": "缺陷密度排名（按项目分组）",
            "sql": "SELECT project, module, defect_count, RANK() OVER (PARTITION BY project ORDER BY defect_count DESC) as density_rank FROM (SELECT project, module, COUNT(*) as defect_count FROM defects GROUP BY project, module) defect_counts"
        },
        {
            "question": "计算每个缺陷与上一个缺陷的时间间隔",
            "sql": "SELECT id, severity, creation_time, LAG(creation_time) OVER (ORDER BY creation_time) as prev_defect_time, julianday(creation_time) - julianday(LAG(creation_time) OVER (ORDER BY creation_time)) as days_since_prev FROM defects WHERE creation_time IS NOT NULL LIMIT 30"
        },
        {
            "question": "各模块缺陷总数的累计百分比",
            "sql": "SELECT module, defect_count, SUM(defect_count) OVER (ORDER BY defect_count DESC) as running_total, ROUND(100.0 * SUM(defect_count) OVER (ORDER BY defect_count DESC) / (SELECT SUM(defect_count) FROM (SELECT module, COUNT(*) as defect_count FROM defects GROUP BY module) as total), 2) as cumulative_percent FROM (SELECT module, COUNT(*) as defect_count FROM defects GROUP BY module ORDER BY defect_count DESC)"
        },
        {
            "question": "查找每个严重度级别的前 5 个最新缺陷",
            "sql": "SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY severity ORDER BY creation_time DESC) as rn FROM defects) ranked WHERE rn <= 5 ORDER BY CASE severity WHEN 'Critical' THEN 1 WHEN 'Major' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, rn"
        },
        {
            "question": "移动平均：每周缺陷数量的 3 周移动平均",
            "sql": "SELECT week, defect_count, AVG(defect_count) OVER (ORDER BY week ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) as moving_avg_3weeks FROM (SELECT strftime('%Y-W%W', creation_time) as week, COUNT(*) as defect_count FROM defects WHERE creation_time >= date('now', '-90 days') GROUP BY week ORDER BY week) weekly_data"
        },

        # ========== 时间序列分析示例 (8个) ==========
        {
            "question": "缺陷趋势分析（按月）",
            "sql": "SELECT strftime('%Y-%m', creation_time) as month, COUNT(*) as total_defects, SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical_count FROM defects WHERE creation_time IS NOT NULL GROUP BY strftime('%Y-%m', creation_time) ORDER BY month DESC LIMIT 12"
        },
        {
            "question": "每周缺陷数量统计",
            "sql": "SELECT strftime('%Y-W%W', creation_time) as week, COUNT(*) as defect_count, SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical_count, SUM(CASE WHEN severity = 'Major' THEN 1 ELSE 0 END) as major_count FROM defects WHERE creation_time >= date('now', '-90 days') GROUP BY week ORDER BY week DESC LIMIT 12"
        },
        {
            "question": "每日测试执行趋势",
            "sql": "SELECT DATE(start_time) as date, COUNT(*) as test_count, ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs WHERE start_time >= date('now', '-30 days') GROUP BY date ORDER BY date DESC"
        },
        {
            "question": "缺陷修复时间分布（按天数分组）",
            "sql": "SELECT CASE WHEN julianday(CASE WHEN status = 'Closed' THEN 'now' ELSE creation_time END) - julianday(creation_time) < 1 THEN '< 1 day' WHEN julianday(CASE WHEN status = 'Closed' THEN 'now' ELSE creation_time END) - julianday(creation_time) < 7 THEN '1-7 days' WHEN julianday(CASE WHEN status = 'Closed' THEN 'now' ELSE creation_time END) - julianday(creation_time) < 30 THEN '7-30 days' ELSE '> 30 days' END as fix_time_range, COUNT(*) as defect_count FROM defects WHERE status IN ('Closed', 'Open', 'In Progress') GROUP BY fix_time_range ORDER BY fix_time_range"
        },
        {
            "question": "季度测试执行和缺陷统计",
            "sql": "SELECT strftime('%Y-Q', (strftime('%m', start_time) - 1) / 3 + 1) as quarter, COUNT(DISTINCT tr.id) as test_count, ROUND(100.0 * SUM(CASE WHEN tr.status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate, COUNT(DISTINCT d.id) as defect_count FROM test_runs tr LEFT JOIN defects d ON tr.build_number = d.build_number WHERE tr.start_time >= date('now', '-12 months') GROUP BY quarter ORDER BY quarter DESC"
        },
        {
            "question": "工作日 vs 周末的缺陷创建对比",
            "sql": "SELECT CASE WHEN strftime('%w', creation_time) IN ('0', '6') THEN 'Weekend' ELSE 'Weekday' END as day_type, COUNT(*) as defect_count, ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) as percentage FROM defects WHERE creation_time >= date('now', '-90 days') GROUP BY day_type"
        },
        {
            "question": "缺陷生命周期时间分析（创建到关闭）",
            "sql": "SELECT d.id, d.severity, d.status, d.creation_time, julianday(CASE WHEN d.status = 'Closed' THEN 'now' ELSE creation_time END) - julianday(d.creation_time) as lifecycle_days FROM defects d WHERE d.creation_time >= date('now', '-60 days') ORDER BY lifecycle_days DESC LIMIT 20"
        },
        {
            "question": "测试覆盖率的时间变化趋势",
            "sql": "SELECT test_week, ROUND(AVG(coverage_percent), 2) as avg_coverage, ROUND(MIN(coverage_percent), 2) as min_coverage, ROUND(MAX(coverage_percent), 2) as max_coverage FROM test_coverage WHERE test_week >= '26-CW01' GROUP BY test_week ORDER BY test_week DESC LIMIT 12"
        },

        # ========== 复杂条件组合示例 (8个) ==========
        {
            "question": "高风险缺陷（Critical + 重开 > 3 次）",
            "sql": "SELECT * FROM defects WHERE severity = 'Critical' AND pingpong > 3"
        },
        {
            "question": "各严重度级别的缺陷数量",
            "sql": "SELECT severity, COUNT(*) as count FROM defects GROUP BY severity ORDER BY CASE severity WHEN 'Critical' THEN 1 WHEN 'Major' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END"
        },
        {
            "question": "测试执行失败的详细信息",
            "sql": "SELECT tr.test_name, tr.project, tr.module, tr.result, tr.start_time FROM test_runs tr WHERE tr.result = 'Failed' ORDER BY tr.start_time DESC LIMIT 10"
        },
        {
            "question": "多条件筛选：Critical 或 Major 状态为 Open 且创建时间超过 30 天",
            "sql": "SELECT * FROM defects WHERE severity IN ('Critical', 'Major') AND status = 'Open' AND creation_time <= date('now', '-30 days') ORDER BY severity DESC, creation_time ASC"
        },
        {
            "question": "复杂条件：测试失败率高（<70%）且缺陷多（>10个）的模块",
            "sql": "SELECT tr.module, ROUND(100.0 * SUM(CASE WHEN tr.status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate, COUNT(DISTINCT d.id) as defect_count FROM test_runs tr LEFT JOIN defects d ON tr.build_number = d.build_number GROUP BY tr.module HAVING pass_rate < 70 AND defect_count > 10 ORDER BY pass_rate ASC"
        },
        {
            "question": "查找特定组合：AIDA 项目中 Critical 或 Major 状态为 New 或 Open 的缺陷",
            "sql": "SELECT * FROM defects WHERE project = 'AIDA' AND severity IN ('Critical', 'Major') AND status IN ('New', 'Open') ORDER BY severity DESC, creation_time DESC"
        },
        {
            "question": "时间范围 + 多条件：过去14天内创建的 Critical 缺陷，且未被修复",
            "sql": "SELECT * FROM defects WHERE severity = 'Critical' AND creation_time >= date('now', '-14 days') AND status NOT IN ('Fixed', 'Closed') ORDER BY creation_time DESC"
        },
        {
            "question": "综合分析：各模块在多个维度上的表现",
            "sql": "SELECT tr.module, ROUND(100.0 * SUM(CASE WHEN tr.status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate, COUNT(DISTINCT d.id) as defect_count, ROUND(AVG(CASE WHEN d.severity = 'Critical' THEN 10 WHEN d.severity = 'Major' THEN 7 WHEN d.severity = 'Medium' THEN 4 ELSE 1 END), 2) as avg_severity_score FROM test_runs tr LEFT JOIN defects d ON tr.build_number = d.build_number GROUP BY tr.module ORDER BY pass_rate DESC, defect_count ASC"
        },

        # ========== 聚合函数进阶示例 (4个) ==========
        {
            "question": "各项目的测试数量统计",
            "sql": "SELECT project, COUNT(*) as test_count FROM test_runs GROUP BY project ORDER BY test_count DESC"
        },
        {
            "question": "最近创建的 10 个缺陷",
            "sql": "SELECT * FROM defects ORDER BY creation_time DESC LIMIT 10"
        },
        {
            "question": "缺陷平均修复时间（按严重度分组）",
            "sql": "SELECT severity, ROUND(AVG(julianday(CASE WHEN status = 'Closed' THEN 'now' ELSE creation_time END) - julianday(creation_time)), 2) as avg_fix_days FROM defects WHERE status = 'Closed' GROUP BY severity ORDER BY CASE severity WHEN 'Critical' THEN 1 WHEN 'Major' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END"
        },
        {
            "question": "测试通过率的中位数（使用分组统计）",
            "sql": "SELECT project, ROUND(AVG(pass_rate), 2) as avg_pass_rate FROM (SELECT project, ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate FROM test_runs GROUP BY project, build_number) project_pass_rates GROUP BY project ORDER BY avg_pass_rate DESC"
        }
    ]
    
    @classmethod
    def get_examples(cls, limit: int = 5) -> str:
        """获取 Few-shot 示例"""
        examples = cls.EXAMPLES[:limit]
        output = ["\n示例查询（学习这些模式）：\n"]
        
        for i, ex in enumerate(examples, 1):
            output.append(f"\n示例 {i}:")
            output.append(f"问题: {ex['question']}")
            output.append(f"SQL: {ex['sql']}")
        
        return "\n".join(output)
    
    @classmethod
    def find_similar_example(cls, question: str) -> Optional[str]:
        """找到相似示例（简单匹配）"""
        for ex in cls.EXAMPLES:
            # 简单关键词匹配
            for keyword in ["数量", "统计", "通过率", "覆盖率", "趋势", "缺陷", "测试", "Critical"]:
                if keyword in question and keyword in ex["question"]:
                    return f"问题: {ex['question']}\nSQL: {ex['sql']}"
        return None


# ============================================================================
# SQL 验证器
# ============================================================================

class SQLValidator:
    """SQL 查询验证器"""
    
    def __init__(self, dangerous_keywords: List[str]):
        self.dangerous_keywords = dangerous_keywords
    
    def validate(self, sql: str) -> Tuple[bool, Optional[str]]:
        """
        验证 SQL 是否安全
        
        Returns:
            (is_valid, error_message)
        """
        # 检查危险操作
        sql_upper = sql.upper()
        for keyword in self.dangerous_keywords:
            if keyword in sql_upper:
                return False, f"危险操作 '{keyword}' 被阻止"
        
        # 检查语法（简单正则）
        if not re.search(r'^\s*SELECT\s+', sql, re.IGNORECASE):
            return False, "只允许 SELECT 查询"
        
        return True, None
    
    def sanitize_sql(self, sql: str) -> str:
        """清理 SQL，移除多余空格和注释"""
        # 移除注释
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        
        # 压缩空格
        sql = re.sub(r'\s+', ' ', sql).strip()
        
        return sql


# ============================================================================
# SQL 查询引擎
# ============================================================================

class SQLQueryEngine:
    """SQL 查询引擎 - Text-to-SQL 核心类"""
    
    def __init__(self, config: Optional[SQLQueryConfig] = None):
        self.config = config or SQLQueryConfig()
        
        # 初始化组件
        self.schema_manager = SchemaManager(self.config.db_path)
        self.validator = SQLValidator(self.config.dangerous_keywords)
        self._query_cache = {}
        
        logger.info(f"SQL查询引擎初始化完成: {self.config.db_path}")
    
    def query(
        self,
        question: str,
        llm_generate_func: callable,
        data_context: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        执行 Text-to-SQL 查询
        
        Args:
            question: 自然语言问题
            llm_generate_func: LLM 生成函数，接收 prompt 返回 SQL
            data_context: 额外的数据上下文（如当前筛选的数据）
            use_cache: 是否使用缓存
        
        Returns:
            {
                "success": bool,
                "sql": str,
                "result": pd.DataFrame,
                "error": Optional[str],
                "retries": int,
                "execution_time_ms": float
            }
        """
        import time
        start_time = time.time()
        
        # 检查缓存
        cache_key = self._generate_cache_key(question, data_context)
        if use_cache and self.config.enable_cache and cache_key in self._query_cache:
            cached = self._query_cache[cache_key]
            # 检查缓存是否过期
            if (time.time() - cached['timestamp']) < self.config.cache_ttl_seconds:
                if self.config.verbose:
                    logger.info(f"使用缓存结果: {question[:50]}...")
                return {
                    "success": True,
                    "sql": cached['sql'],
                    "result": cached['result'],
                    "retries": 0,
                    "execution_time_ms": (time.time() - start_time) * 1000,
                    "from_cache": True
                }
        
        # 生成 SQL
        sql = None
        last_error = None
        
        for attempt in range(self.config.max_retries):
            try:
                # 构建 Prompt
                prompt = self._build_prompt(question, data_context, last_error)
                
                # 调用 LLM 生成 SQL
                sql = llm_generate_func(prompt)
                
                # 验证 SQL
                is_valid, error_msg = self.validator.validate(sql)
                if not is_valid:
                    raise ValueError(error_msg)
                
                # 执行 SQL
                conn = sqlite3.connect(self.config.db_path)
                df = pd.read_sql_query(sql, conn)
                conn.close()
                
                execution_time = (time.time() - start_time) * 1000
                
                # 缓存结果
                if self.config.enable_cache:
                    self._query_cache[cache_key] = {
                        'sql': sql,
                        'result': df,
                        'timestamp': time.time()
                    }
                
                if self.config.verbose:
                    logger.info(f"SQL 查询成功（尝试 {attempt + 1}/{self.config.max_retries}）")
                
                return {
                    "success": True,
                    "sql": sql,
                    "result": df,
                    "retries": attempt,
                    "execution_time_ms": execution_time,
                    "from_cache": False
                }
                
            except Exception as e:
                last_error = str(e)
                if self.config.verbose:
                    logger.warning(f"SQL 查询失败（尝试 {attempt + 1}/{self.config.max_retries}）: {last_error}")
                
                if attempt >= self.config.max_retries - 1:
                    break
        
        return {
            "success": False,
            "sql": sql,
            "result": None,
            "error": last_error,
            "retries": self.config.max_retries,
            "execution_time_ms": (time.time() - start_time) * 1000,
            "from_cache": False
        }
    
    def _build_prompt(
        self,
        question: str,
        data_context: Optional[str] = None,
        last_error: Optional[str] = None
    ) -> str:
        """构建 SQL 生成 Prompt"""
        
        prompt_parts = [
            "# SQL 查询助手\n",
            "你是一个专业的 SQL 查询助手，专门查询汽车测试数据库。\n",
            "## 数据库 Schema\n",
            self.schema_manager.get_schema(),
            "\n## 业务知识\n",
            BusinessKnowledge.get_knowledge(),
            "\n## 查询示例\n",
            FewShotExamples.get_examples(limit=5)
        ]
        
        # 添加相似示例
        similar_example = FewShotExamples.find_similar_example(question)
        if similar_example:
            prompt_parts.append("\n## 相似问题参考\n")
            prompt_parts.append(similar_example)
        
        # 添加数据上下文
        if data_context:
            prompt_parts.append("\n## 当前数据上下文\n")
            prompt_parts.append(data_context)
        
        # 添加历史错误
        if last_error:
            prompt_parts.append(f"\n## 上次错误\n{last_error}\n请根据错误修正 SQL。")
        
        # 用户问题
        prompt_parts.append(f"\n## 用户问题\n{question}\n")
        prompt_parts.append("请生成 SQL 查询语句。只输出 SQL，不要任何解释或多余文字。")
        
        return "\n".join(prompt_parts)
    
    def _generate_cache_key(self, question: str, data_context: Optional[str] = None) -> str:
        """生成缓存键"""
        key = question.lower()
        if data_context:
            key += f"|{data_context[:100]}"
        return key
    
    def clear_cache(self):
        """清空查询缓存"""
        self._query_cache.clear()
        logger.info("查询缓存已清空")


# ============================================================================
# 快捷函数
# ============================================================================

def create_sql_engine(db_path: str = "database/local_data.db") -> SQLQueryEngine:
    """创建 SQL 查询引擎"""
    config = SQLQueryConfig(db_path=db_path)
    return SQLQueryEngine(config)


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    # 测试 Schema 获取
    print("=" * 60)
    print("测试 Schema 管理")
    print("=" * 60)
    schema_mgr = SchemaManager("database/local_data.db")
    print(schema_mgr.get_schema())
    
    # 测试表样本
    print("\n" + "=" * 60)
    print("测试表样本数据")
    print("=" * 60)
    print(schema_mgr.get_table_sample("defects"))
    
    # 测试 SQL 验证
    print("\n" + "=" * 60)
    print("测试 SQL 验证")
    print("=" * 60)
    validator = SQLValidator(["DROP", "DELETE"])
    
    test_sqls = [
        "SELECT * FROM defects",
        "DROP TABLE defects",
        "SELECT COUNT(*) FROM test_runs"
    ]
    
    for sql in test_sqls:
        is_valid, error = validator.validate(sql)
        print(f"SQL: {sql}")
        print(f"有效: {is_valid}, 错误: {error}\n")

#!/usr/bin/env python3
"""
增强版 Agent 数据理解层 v2.0

核心改进：
1. 深度业务语义理解 - 理解测试周、AIDA、缺陷生命周期等业务概念
2. 智能上下文关联 - 自动关联测试执行和缺陷数据
3. 多维度分析能力 - 趋势、对比、根因分析
4. 主动洞察生成 - 不仅回答问题，还能发现隐藏问题

作者: AI Assistant (Mission Control Center 多 Agent 协作优化)
日期: 2026-03-19
"""

import sqlite3
import json
import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# 业务语义枚举
# ============================================================================

class TestStatus(Enum):
    """测试状态"""
    PASSED = "Passed"
    FAILED = "Failed"
    BLOCKED = "Blocked"
    SKIPPED = "Skipped"
    NO_RUN = "No Run"
    
    @classmethod
    def pass_statuses(cls):
        return [cls.PASSED]
    
    @classmethod
    def fail_statuses(cls):
        return [cls.FAILED, cls.BLOCKED]


class DefectSeverity(Enum):
    """缺陷严重程度"""
    CRITICAL = "Critical"
    MAJOR = "Major"
    MEDIUM = "Medium"
    MINOR = "Minor"
    
    @classmethod
    def high_severity(cls):
        return [cls.CRITICAL, cls.MAJOR]
    
    @classmethod
    def from_string(cls, s: str) -> 'DefectSeverity':
        mapping = {
            "critical": cls.CRITICAL,
            "致命": cls.CRITICAL,
            "严重": cls.MAJOR,
            "major": cls.MAJOR,
            "中等": cls.MEDIUM,
            "medium": cls.MEDIUM,
            "轻微": cls.MINOR,
            "minor": cls.MINOR
        }
        return mapping.get(s.lower(), cls.MINOR)


class DefectPhase(Enum):
    """缺陷生命周期阶段"""
    NEW = "New"
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    FIXED = "Fixed"
    VERIFIED = "Verified"
    CLOSED = "Closed"
    REJECTED = "Rejected"
    
    @classmethod
    def active_phases(cls):
        return [cls.NEW, cls.OPEN, cls.IN_PROGRESS]
    
    @classmethod
    def closed_phases(cls):
        return [cls.CLOSED, cls.REJECTED]


class IntentType(Enum):
    """问题意图类型"""
    # 统计类
    COUNT = "count"
    PASS_RATE = "pass_rate"
    DEFECT_DENSITY = "defect_density"
    
    # 列表类
    LIST_TESTS = "list_tests"
    LIST_DEFECTS = "list_defects"
    LIST_MODULES = "list_modules"
    
    # 趋势类
    TREND_TEST = "trend_test"
    TREND_DEFECT = "trend_defect"
    TREND_QUALITY = "trend_quality"
    
    # 分析类
    ROOT_CAUSE = "root_cause"
    CORRELATION = "correlation"
    RISK_ASSESSMENT = "risk_assessment"
    COMPARISON = "comparison"
    
    # 建议类
    TEST_STRATEGY = "test_strategy"
    PRIORITY = "priority"
    RESOURCE_ALLOCATION = "resource_allocation"
    
    # 综合类
    OVERVIEW = "overview"
    INSIGHT = "insight"


# ============================================================================
# 数据类
# ============================================================================

@dataclass
class QueryIntent:
    """查询意图"""
    intent_type: IntentType
    domain: str  # "test", "defect", "both"
    time_range: Optional[Tuple[datetime, datetime]] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    dimensions: List[str] = field(default_factory=list)
    aggregation: Optional[str] = None
    confidence: float = 1.0
    original_question: str = ""
    parsed_entities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataInsight:
    """数据洞察"""
    insight_type: str
    title: str
    description: str
    severity: str  # "info", "warning", "critical"
    related_data: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    confidence: float = 0.8


@dataclass
class AnalysisResult:
    """分析结果"""
    success: bool
    data: Any
    insights: List[DataInsight] = field(default_factory=list)
    sql: Optional[str] = None
    execution_time_ms: float = 0
    message: str = ""


# ============================================================================
# 增强版数据理解引擎
# ============================================================================

class EnhancedDataUnderstanding:
    """增强版数据理解引擎"""
    
    def __init__(self, db_path: str = 'database/local_data.db'):
        self.db_path = db_path
        self.conn = None
        self.schema_cache = None
        self._init_schema_understanding()
    
    def _get_connection(self):
        """获取数据库连接"""
        if not self.conn:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def _init_schema_understanding(self):
        """初始化 Schema 理解"""
        self.schema_cache = {
            "test_runs": {
                "pk": "run_id",
                "time_column": "test_week",
                "status_column": "status",
                "dimensions": ["project", "module", "tester", "test_week"],
                "metrics": ["duration_seconds", "status"],
                "business_concepts": {
                    "test_week": "测试周，格式 YY-CWww，如 26-CW11 表示 2026 年第 11 周",
                    "module": "测试模块，通常对应 AIDA 产品区域",
                    "tester": "测试执行人",
                    "duration_seconds": "执行耗时（秒）"
                }
            },
            "defects": {
                "pk": "defect_id",
                "time_column": "creation_time",
                "status_column": "status",
                "dimensions": ["project", "module", "severity", "status", "detected_by"],
                "metrics": ["pingpong", "severity"],
                "business_concepts": {
                    "severity": "严重程度：Critical/Major/Medium/Minor",
                    "pingpong": "往返次数，值越高说明修复效率越低",
                    "phase": "缺陷生命周期阶段",
                    "aidas": "产品区域列表（JSON）"
                }
            },
            "test_coverage": {
                "pk": "id",
                "dimensions": ["module", "test_week"],
                "metrics": ["coverage_percent", "passed_tests", "failed_tests"]
            },
            "defect_trends": {
                "pk": "id",
                "dimensions": ["project", "module", "test_week"],
                "metrics": ["new_defects", "closed_defects", "open_defects"]
            }
        }
    
    # ========================================================================
    # 意图理解
    # ========================================================================
    
    def understand_intent(self, question: str) -> QueryIntent:
        """
        深度理解用户问题意图
        
        改进点：
        1. 多层意图识别（统计、趋势、分析、建议）
        2. 实体提取（项目、模块、人员、时间）
        3. 业务语义理解（测试周、严重程度等）
        """
        question_lower = question.lower()
        
        # Step 1: 识别意图类型
        intent_type = self._classify_intent(question_lower)
        
        # Step 2: 识别数据域
        domain = self._identify_domain(question_lower)
        
        # Step 3: 提取时间范围
        time_range = self._extract_time_range(question_lower)
        
        # Step 4: 提取过滤条件
        filters = self._extract_filters(question_lower)
        
        # Step 5: 提取分析维度
        dimensions = self._extract_dimensions(question_lower)
        
        # Step 6: 提取命名实体
        parsed_entities = self._extract_entities(question)
        
        return QueryIntent(
            intent_type=intent_type,
            domain=domain,
            time_range=time_range,
            filters=filters,
            dimensions=dimensions,
            original_question=question,
            parsed_entities=parsed_entities
        )
    
    def _classify_intent(self, question: str) -> IntentType:
        """分类意图类型"""
        # 统计类
        if any(kw in question for kw in ["多少", "数量", "统计", "count", "total"]):
            if "通过率" in question or "pass rate" in question:
                return IntentType.PASS_RATE
            if "缺陷密度" in question or "defect density" in question:
                return IntentType.DEFECT_DENSITY
            return IntentType.COUNT
        
        # 列表类
        if any(kw in question for kw in ["列出", "哪些", "显示", "list", "show"]):
            if "测试" in question or "test" in question:
                return IntentType.LIST_TESTS
            if "缺陷" in question or "defect" in question or "bug" in question:
                return IntentType.LIST_DEFECTS
            return IntentType.LIST_MODULES
        
        # 趋势类
        if any(kw in question for kw in ["趋势", "变化", "trend", "走势"]):
            if "测试" in question or "test" in question:
                return IntentType.TREND_TEST
            if "缺陷" in question or "defect" in question:
                return IntentType.TREND_DEFECT
            return IntentType.TREND_QUALITY
        
        # 分析类
        if any(kw in question for kw in ["原因", "为什么", "root cause", "分析"]):
            return IntentType.ROOT_CAUSE
        if any(kw in question for kw in ["关联", "相关", "correlation"]):
            return IntentType.CORRELATION
        if any(kw in question for kw in ["风险", "评估", "risk"]):
            return IntentType.RISK_ASSESSMENT
        if any(kw in question for kw in ["对比", "比较", "compare"]):
            return IntentType.COMPARISON
        
        # 建议类
        if any(kw in question for kw in ["建议", "策略", "recommend", "strategy"]):
            return IntentType.TEST_STRATEGY
        if any(kw in question for kw in ["优先", "排序", "priority"]):
            return IntentType.PRIORITY
        
        # 洞察类
        if any(kw in question for kw in ["洞察", "发现", "insight", "问题"]):
            return IntentType.INSIGHT
        
        return IntentType.OVERVIEW
    
    def _identify_domain(self, question: str) -> str:
        """识别数据域"""
        test_keywords = ["测试", "test", "用例", "执行", "运行", "pass", "fail"]
        defect_keywords = ["缺陷", "defect", "bug", "问题", "故障", "severity", "critical"]
        
        test_score = sum(1 for kw in test_keywords if kw in question)
        defect_score = sum(1 for kw in defect_keywords if kw in question)
        
        if test_score > defect_score:
            return "test"
        elif defect_score > test_score:
            return "defect"
        else:
            return "both"
    
    def _extract_time_range(self, question: str) -> Optional[Tuple[datetime, datetime]]:
        """提取时间范围"""
        now = datetime.now()
        
        # 本周
        if "本周" in question:
            start = now - timedelta(days=now.weekday())
            return (start, now)
        
        # 上周
        if "上周" in question:
            start = now - timedelta(days=now.weekday() + 7)
            end = now - timedelta(days=now.weekday())
            return (start, end)
        
        # 本月
        if "本月" in question:
            start = now.replace(day=1)
            return (start, now)
        
        # 最近 N 天
        match = re.search(r"最近(\d+)天", question)
        if match:
            days = int(match.group(1))
            start = now - timedelta(days=days)
            return (start, now)
        
        # 测试周格式
        match = re.search(r"(\d{2})-CW(\d{2})", question)
        if match:
            year = int("20" + match.group(1))
            week = int(match.group(2))
            # 计算测试周的开始和结束日期
            start = datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w")
            end = start + timedelta(days=6)
            return (start, end)
        
        return None
    
    def _extract_filters(self, question: str) -> Dict[str, Any]:
        """提取过滤条件"""
        filters = {}
        
        # 状态
        status_mapping = {
            "通过": "Passed", "passed": "Passed",
            "失败": "Failed", "failed": "Failed",
            "阻塞": "Blocked", "blocked": "Blocked",
            "open": "Open", "打开": "Open",
            "closed": "Closed", "关闭": "Closed"
        }
        for keyword, status in status_mapping.items():
            if keyword in question.lower():
                filters["status"] = status
                break
        
        # 严重程度
        severity_mapping = {
            "critical": "Critical", "致命": "Critical",
            "major": "Major", "严重": "Major", "重要": "Major",
            "medium": "Medium", "中等": "Medium",
            "minor": "Minor", "轻微": "Minor"
        }
        for keyword, severity in severity_mapping.items():
            if keyword in question.lower():
                filters["severity"] = severity
                break
        
        return filters
    
    def _extract_dimensions(self, question: str) -> List[str]:
        """提取分析维度"""
        dimensions = []
        
        dimension_keywords = {
            "project": ["项目", "project"],
            "module": ["模块", "module", "aida"],
            "tester": ["人员", "tester", "执行人"],
            "severity": ["严重程度", "severity"],
            "test_week": ["测试周", "week", "周"]
        }
        
        for dim, keywords in dimension_keywords.items():
            if any(kw in question for kw in keywords):
                dimensions.append(dim)
        
        return dimensions if dimensions else ["project"]
    
    def _extract_entities(self, question: str) -> Dict[str, Any]:
        """提取命名实体"""
        entities = {}
        
        # 项目名称（中文或英文）
        project_match = re.search(r"(\w+)系统|项目[:\s]*(\w+)", question)
        if project_match:
            entities["project"] = project_match.group(1) or project_match.group(2)
        
        # 模块名称
        module_match = re.search(r"(\w+)模块", question)
        if module_match:
            entities["module"] = module_match.group(1)
        
        # 人员名称
        tester_match = re.search(r"(\w+)执行|tester[:\s]*(\w+)", question)
        if tester_match:
            entities["tester"] = tester_match.group(1) or tester_match.group(2)
        
        return entities
    
    # ========================================================================
    # 查询执行
    # ========================================================================
    
    def execute_analysis(self, intent: QueryIntent) -> AnalysisResult:
        """执行分析"""
        start_time = datetime.now()
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 根据意图类型选择分析策略
            if intent.intent_type == IntentType.PASS_RATE:
                result = self._analyze_pass_rate(cursor, intent)
            elif intent.intent_type == IntentType.DEFECT_DENSITY:
                result = self._analyze_defect_density(cursor, intent)
            elif intent.intent_type == IntentType.TREND_TEST:
                result = self._analyze_test_trend(cursor, intent)
            elif intent.intent_type == IntentType.TREND_DEFECT:
                result = self._analyze_defect_trend(cursor, intent)
            elif intent.intent_type == IntentType.RISK_ASSESSMENT:
                result = self._analyze_risk(cursor, intent)
            elif intent.intent_type == IntentType.INSIGHT:
                result = self._generate_insights(cursor, intent)
            elif intent.intent_type == IntentType.CORRELATION:
                result = self._analyze_correlation(cursor, intent)
            else:
                result = self._general_query(cursor, intent)
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            result.execution_time_ms = execution_time
            
            return result
            
        except Exception as e:
            logger.error(f"分析执行失败: {e}")
            return AnalysisResult(
                success=False,
                data=None,
                message=f"分析失败: {str(e)}"
            )
    
    def _analyze_pass_rate(self, cursor, intent: QueryIntent) -> AnalysisResult:
        """分析测试通过率"""
        filters = intent.filters
        entities = intent.parsed_entities
        
        where_clauses = []
        params = []
        
        # 构建过滤条件
        if "project" in entities:
            where_clauses.append("project = ?")
            params.append(entities["project"])
        if "module" in entities:
            where_clauses.append("module = ?")
            params.append(entities["module"])
        if "status" in filters:
            where_clauses.append("status = ?")
            params.append(filters["status"])
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # 按维度分组统计
        dimensions = intent.dimensions if intent.dimensions else ["project"]
        group_cols = []
        for dim in dimensions:
            if dim in ["project", "module", "tester", "test_week"]:
                group_cols.append(dim)
        
        if not group_cols:
            group_cols = ["project"]
        
        sql = f"""
        SELECT 
            {', '.join(group_cols)},
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN status = 'Blocked' THEN 1 ELSE 0 END) as blocked,
            ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate
        FROM test_runs
        WHERE {where_sql}
        GROUP BY {', '.join(group_cols)}
        ORDER BY total DESC
        LIMIT 50
        """
        
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        
        data = [dict(row) for row in rows]
        
        # 生成洞察
        insights = []
        for row in data:
            if row["pass_rate"] is not None and row["pass_rate"] < 80:
                insights.append(DataInsight(
                    insight_type="low_pass_rate",
                    title=f"低通过率警告",
                    description=f"{row.get('project', 'N/A')} - {row.get('module', 'N/A')} 通过率仅 {row['pass_rate']}%",
                    severity="warning",
                    related_data=row
                ))
        
        return AnalysisResult(
            success=True,
            data=data,
            insights=insights,
            sql=sql,
            message=f"查询到 {len(data)} 条通过率数据"
        )
    
    def _analyze_defect_density(self, cursor, intent: QueryIntent) -> AnalysisResult:
        """分析缺陷密度"""
        # 缺陷密度 = 缺陷数 / 测试用例数
        sql = """
        SELECT 
            t.project,
            t.module,
            COUNT(DISTINCT t.run_id) as test_count,
            COUNT(DISTINCT d.defect_id) as defect_count,
            ROUND(1.0 * COUNT(DISTINCT d.defect_id) / NULLIF(COUNT(DISTINCT t.run_id), 0), 2) as defect_density
        FROM test_runs t
        LEFT JOIN defects d ON t.project = d.project AND t.module = d.module
        GROUP BY t.project, t.module
        ORDER BY defect_density DESC
        LIMIT 20
        """
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        
        insights = []
        for row in data:
            if row["defect_density"] and row["defect_density"] > 0.5:
                insights.append(DataInsight(
                    insight_type="high_defect_density",
                    title="高缺陷密度警告",
                    description=f"{row['project']} - {row['module']} 缺陷密度 {row['defect_density']}，需要重点关注",
                    severity="critical",
                    related_data=row,
                    recommendations=["增加测试覆盖", "进行代码审查", "分析根因"]
                ))
        
        return AnalysisResult(
            success=True,
            data=data,
            insights=insights,
            sql=sql,
            message=f"分析了 {len(data)} 个模块的缺陷密度"
        )
    
    def _analyze_test_trend(self, cursor, intent: QueryIntent) -> AnalysisResult:
        """分析测试趋势"""
        sql = """
        SELECT 
            test_week,
            COUNT(*) as total_tests,
            SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed,
            ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate
        FROM test_runs
        WHERE test_week IS NOT NULL
        GROUP BY test_week
        ORDER BY test_week DESC
        LIMIT 12
        """
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        
        # 计算趋势
        insights = []
        if len(data) >= 2:
            recent = data[0]
            previous = data[1]
            
            if recent["pass_rate"] and previous["pass_rate"]:
                change = recent["pass_rate"] - previous["pass_rate"]
                if change < -5:
                    insights.append(DataInsight(
                        insight_type="pass_rate_decline",
                        title="通过率下降警告",
                        description=f"通过率从 {previous['pass_rate']}% 下降到 {recent['pass_rate']}%，下降 {abs(change):.1f}%",
                        severity="warning",
                        related_data={"recent": recent, "previous": previous}
                    ))
        
        return AnalysisResult(
            success=True,
            data=data,
            insights=insights,
            sql=sql,
            message=f"分析了 {len(data)} 个测试周的趋势"
        )
    
    def _analyze_defect_trend(self, cursor, intent: QueryIntent) -> AnalysisResult:
        """分析缺陷趋势"""
        sql = """
        SELECT 
            strftime('%Y-%m', creation_time) as month,
            COUNT(*) as total,
            SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical,
            SUM(CASE WHEN severity = 'Major' THEN 1 ELSE 0 END) as major,
            SUM(CASE WHEN status IN ('Open', 'New', 'In Progress') THEN 1 ELSE 0 END) as open_count
        FROM defects
        WHERE creation_time IS NOT NULL
        GROUP BY strftime('%Y-%m', creation_time)
        ORDER BY month DESC
        LIMIT 12
        """
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        
        insights = []
        if len(data) >= 2:
            recent = data[0]
            if recent["critical"] > 0:
                insights.append(DataInsight(
                    insight_type="critical_defects",
                    title="Critical 缺陷警告",
                    description=f"本月有 {recent['critical']} 个 Critical 缺陷",
                    severity="critical",
                    related_data=recent
                ))
        
        return AnalysisResult(
            success=True,
            data=data,
            insights=insights,
            sql=sql,
            message=f"分析了 {len(data)} 个月的缺陷趋势"
        )
    
    def _analyze_risk(self, cursor, intent: QueryIntent) -> AnalysisResult:
        """风险评估"""
        # 综合风险评分
        sql = """
        WITH test_stats AS (
            SELECT 
                project,
                module,
                COUNT(*) as test_count,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed_count,
                ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate
            FROM test_runs
            GROUP BY project, module
        ),
        defect_stats AS (
            SELECT 
                project,
                module,
                COUNT(*) as defect_count,
                SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical_count,
                SUM(CASE WHEN status IN ('Open', 'New', 'In Progress') THEN 1 ELSE 0 END) as open_count
            FROM defects
            GROUP BY project, module
        )
        SELECT 
            COALESCE(t.project, d.project) as project,
            COALESCE(t.module, d.module) as module,
            t.test_count,
            t.pass_rate,
            d.defect_count,
            d.critical_count,
            d.open_count,
            ROUND(
                COALESCE(100 - t.pass_rate, 50) + 
                COALESCE(d.critical_count * 10, 0) + 
                COALESCE(d.open_count * 2, 0),
                2
            ) as risk_score
        FROM test_stats t
        FULL OUTER JOIN defect_stats d ON t.project = d.project AND t.module = d.module
        ORDER BY risk_score DESC
        LIMIT 20
        """
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        
        insights = []
        for row in data:
            if row["risk_score"] and row["risk_score"] > 50:
                insights.append(DataInsight(
                    insight_type="high_risk",
                    title="高风险模块警告",
                    description=f"{row['project']} - {row['module']} 风险评分 {row['risk_score']}",
                    severity="critical",
                    related_data=row,
                    recommendations=["优先测试", "增加资源", "进行风险缓解"]
                ))
        
        return AnalysisResult(
            success=True,
            data=data,
            insights=insights,
            sql=sql,
            message=f"评估了 {len(data)} 个模块的风险"
        )
    
    def _analyze_correlation(self, cursor, intent: QueryIntent) -> AnalysisResult:
        """关联分析"""
        # 测试失败与缺陷的关联
        sql = """
        SELECT 
            t.project,
            t.module,
            t.test_week,
            SUM(CASE WHEN t.status = 'Failed' THEN 1 ELSE 0 END) as failed_tests,
            COUNT(DISTINCT d.defect_id) as related_defects,
            ROUND(1.0 * COUNT(DISTINCT d.defect_id) / NULLIF(SUM(CASE WHEN t.status = 'Failed' THEN 1 ELSE 0 END), 0), 2) as defect_per_failure
        FROM test_runs t
        LEFT JOIN defects d ON t.project = d.project 
            AND t.module = d.module
            AND strftime('%Y-%m', d.creation_time) = strftime('%Y-%m', t.test_week)
        GROUP BY t.project, t.module, t.test_week
        HAVING failed_tests > 0
        ORDER BY failed_tests DESC
        LIMIT 20
        """
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        
        return AnalysisResult(
            success=True,
            data=data,
            insights=[],
            sql=sql,
            message=f"分析了 {len(data)} 条测试失败与缺陷的关联"
        )
    
    def _generate_insights(self, cursor, intent: QueryIntent) -> AnalysisResult:
        """生成洞察"""
        insights = []
        
        # 1. 通过率异常
        cursor.execute("""
            SELECT project, module, 
                   ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / COUNT(*), 2) as pass_rate
            FROM test_runs
            GROUP BY project, module
            HAVING pass_rate < 80
            ORDER BY pass_rate ASC
            LIMIT 5
        """)
        for row in cursor.fetchall():
            insights.append(DataInsight(
                insight_type="low_pass_rate",
                title="低通过率模块",
                description=f"{row['project']} - {row['module']} 通过率 {row['pass_rate']}%",
                severity="warning",
                related_data=dict(row)
            ))
        
        # 2. 高风险缺陷
        cursor.execute("""
            SELECT project, module, severity, COUNT(*) as count
            FROM defects
            WHERE severity = 'Critical' AND status IN ('Open', 'New', 'In Progress')
            GROUP BY project, module
            ORDER BY count DESC
            LIMIT 5
        """)
        for row in cursor.fetchall():
            insights.append(DataInsight(
                insight_type="critical_defect",
                title="Critical 缺陷待处理",
                description=f"{row['project']} - {row['module']} 有 {row['count']} 个 Critical 缺陷未关闭",
                severity="critical",
                related_data=dict(row)
            ))
        
        # 3. 缺陷修复效率
        cursor.execute("""
            SELECT project, module, AVG(pingpong) as avg_pingpong
            FROM defects
            WHERE pingpong > 0
            GROUP BY project, module
            HAVING avg_pingpong > 3
            ORDER BY avg_pingpong DESC
            LIMIT 5
        """)
        for row in cursor.fetchall():
            insights.append(DataInsight(
                insight_type="low_fix_efficiency",
                title="缺陷修复效率低",
                description=f"{row['project']} - {row['module']} 平均往返 {row['avg_pingpong']:.1f} 次",
                severity="warning",
                related_data=dict(row)
            ))
        
        return AnalysisResult(
            success=True,
            data=[insight.__dict__ for insight in insights],
            insights=insights,
            message=f"生成了 {len(insights)} 条洞察"
        )
    
    def _general_query(self, cursor, intent: QueryIntent) -> AnalysisResult:
        """通用查询"""
        domain = intent.domain
        filters = intent.filters
        entities = intent.parsed_entities
        
        if domain == "test":
            return self._query_tests(cursor, intent)
        elif domain == "defect":
            return self._query_defects(cursor, intent)
        else:
            return self._query_overview(cursor)
    
    def _query_tests(self, cursor, intent: QueryIntent) -> AnalysisResult:
        """测试数据查询"""
        sql = """
        SELECT 
            project, module, tester, test_week,
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed,
            ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / COUNT(*), 2) as pass_rate
        FROM test_runs
        GROUP BY project, module, tester, test_week
        ORDER BY total DESC
        LIMIT 50
        """
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        
        return AnalysisResult(
            success=True,
            data=data,
            sql=sql,
            message=f"查询到 {len(data)} 条测试数据"
        )
    
    def _query_defects(self, cursor, intent: QueryIntent) -> AnalysisResult:
        """缺陷数据查询"""
        sql = """
        SELECT 
            project, module, severity, status,
            COUNT(*) as count
        FROM defects
        GROUP BY project, module, severity, status
        ORDER BY count DESC
        LIMIT 50
        """
        
        cursor.execute(sql)
        rows = cursor.fetchall()
        data = [dict(row) for row in rows]
        
        return AnalysisResult(
            success=True,
            data=data,
            sql=sql,
            message=f"查询到 {len(data)} 条缺陷数据"
        )
    
    def _query_overview(self, cursor) -> AnalysisResult:
        """综合概览"""
        # 测试概览
        cursor.execute("""
            SELECT 
                COUNT(*) as total_tests,
                SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed,
                ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / COUNT(*), 2) as pass_rate
            FROM test_runs
        """)
        test_stats = dict(cursor.fetchone())
        
        # 缺陷概览
        cursor.execute("""
            SELECT 
                COUNT(*) as total_defects,
                SUM(CASE WHEN status IN ('Open', 'New', 'In Progress') THEN 1 ELSE 0 END) as open_defects,
                SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN severity = 'Major' THEN 1 ELSE 0 END) as major
            FROM defects
        """)
        defect_stats = dict(cursor.fetchone())
        
        data = {
            "tests": test_stats,
            "defects": defect_stats
        }
        
        insights = []
        if defect_stats.get("critical", 0) > 0:
            insights.append(DataInsight(
                insight_type="critical_defects",
                title="Critical 缺陷警告",
                description=f"有 {defect_stats['critical']} 个 Critical 缺陷需要立即处理",
                severity="critical",
                related_data={"count": defect_stats["critical"]}
            ))
        
        return AnalysisResult(
            success=True,
            data=data,
            insights=insights,
            message="综合概览查询完成"
        )
    
    # ========================================================================
    # 对话接口
    # ========================================================================
    
    def chat(self, question: str) -> str:
        """
        对话式问答
        
        改进点：
        1. 自然语言理解
        2. 上下文感知
        3. 洞察生成
        """
        # 理解意图
        intent = self.understand_intent(question)
        
        # 执行分析
        result = self.execute_analysis(intent)
        
        # 生成回复
        response = self._format_response(result, intent)
        
        return response
    
    def _format_response(self, result: AnalysisResult, intent: QueryIntent) -> str:
        """格式化回复"""
        lines = []
        
        # 主标题
        lines.append(f"## 📊 {self._get_intent_title(intent.intent_type)}")
        lines.append("")
        
        # 结果摘要
        if result.success:
            lines.append(f"**{result.message}** (耗时: {result.execution_time_ms:.0f}ms)")
            lines.append("")
            
            # 数据表格
            if result.data:
                if isinstance(result.data, dict):
                    for key, value in result.data.items():
                        if isinstance(value, dict):
                            lines.append(f"### {key}")
                            for k, v in value.items():
                                lines.append(f"- **{k}**: {v}")
                            lines.append("")
                        else:
                            lines.append(f"- **{key}**: {value}")
                elif isinstance(result.data, list):
                    lines.append("| " + " | ".join(result.data[0].keys()) + " |")
                    lines.append("| " + " | ".join(["---"] * len(result.data[0])) + " |")
                    for row in result.data[:10]:
                        lines.append("| " + " | ".join(str(v) for v in row.values()) + " |")
                    if len(result.data) > 10:
                        lines.append(f"\n*...共 {len(result.data)} 条记录*")
            
            # 洞察
            if result.insights:
                lines.append("")
                lines.append("### 💡 洞察与建议")
                for insight in result.insights:
                    severity_emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
                    lines.append(f"\n{severity_emoji.get(insight.severity, '📌')} **{insight.title}**")
                    lines.append(f"   {insight.description}")
                    if insight.recommendations:
                        for rec in insight.recommendations:
                            lines.append(f"   - {rec}")
        else:
            lines.append(f"❌ {result.message}")
        
        return "\n".join(lines)
    
    def _get_intent_title(self, intent_type: IntentType) -> str:
        """获取意图标题"""
        titles = {
            IntentType.COUNT: "数量统计",
            IntentType.PASS_RATE: "通过率分析",
            IntentType.DEFECT_DENSITY: "缺陷密度分析",
            IntentType.LIST_TESTS: "测试列表",
            IntentType.LIST_DEFECTS: "缺陷列表",
            IntentType.TREND_TEST: "测试趋势分析",
            IntentType.TREND_DEFECT: "缺陷趋势分析",
            IntentType.ROOT_CAUSE: "根因分析",
            IntentType.CORRELATION: "关联分析",
            IntentType.RISK_ASSESSMENT: "风险评估",
            IntentType.COMPARISON: "对比分析",
            IntentType.TEST_STRATEGY: "测试策略建议",
            IntentType.INSIGHT: "洞察发现",
            IntentType.OVERVIEW: "综合概览"
        }
        return titles.get(intent_type, "分析结果")
    
    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    # 动态获取数据库路径
    try:
        from config_center import cfg
        db_path = str(cfg.DATABASE_FILE)
    except ImportError:
        import os
        _this_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(_this_dir, 'local_data.db')
    engine = EnhancedDataUnderstanding(db_path)
    
    # 测试各种问题
    questions = [
        "测试通过率是多少?",
        "最近一周的缺陷趋势",
        "哪些模块风险最高?",
        "给我一些洞察",
        "ABS系统的测试情况怎么样?"
    ]
    
    for q in questions:
        print(f"\n{'='*60}")
        print(f"❓ 问题: {q}")
        print(f"{'='*60}")
        print(engine.chat(q))
    
    engine.close()

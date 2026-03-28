#!/usr/bin/env python3
"""
Agent 数据理解层
让Agent能够理解数据库结构并智能回答用户关于测试和缺陷的问题
"""

import sqlite3
import json
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AgentDataUnderstanding:
    """Agent数据理解层"""
    
    def __init__(self, db_path: str = 'database/local_data.db'):
        self.db_path = db_path
        self.conn = None
        self.schema_context = self._build_schema_context()
    
    def _get_connection(self):
        """获取数据库连接"""
        if not self.conn:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def _build_schema_context(self) -> str:
        """构建数据库Schema上下文（供Agent理解）"""
        return """
## 数据库结构说明

### 表1: test_runs (测试运行记录)
存储每次测试执行的详细信息。

关键字段：
- run_id: 测试运行唯一ID
- test_name: 测试用例名称
- status: 运行状态 (Passed/Failed/Blocked/Skipped)
- tester: 执行人
- project: 所属项目
- module: 所属模块
- test_week: 测试周 (格式: 26-CW11)
- duration_seconds: 执行时长

常用查询场景：
1. 测试通过率统计
2. 测试执行趋势
3. 按模块/项目/人员统计

### 表2: defects (缺陷记录)
存储缺陷的详细信息。

关键字段：
- defect_id: 缺陷唯一ID
- title: 缺陷标题
- severity: 严重程度 (Critical/Major/Medium/Minor)
- status: 状态 (Open/In Progress/Fixed/Closed)
- project: 所属项目
- module: 所属模块
- detected_by: 发现人
- creation_time: 创建时间
- pingpong: 往返次数

常用查询场景：
1. 缺陷分布统计
2. 缺陷趋势分析
3. 按严重程度/状态统计
"""
    
    def understand_question(self, question: str) -> Dict[str, Any]:
        """理解用户问题，返回查询意图"""
        question_lower = question.lower()
        
        # 意图识别
        intent = {
            "domain": None,  # test 或 defect
            "action": None,  # count, list, trend, analyze
            "filters": {},
            "aggregation": None,
            "time_range": None,
            "original_question": question
        }
        
        # 识别领域
        if any(kw in question_lower for kw in ['测试', 'test', '用例', '运行', '执行']):
            intent["domain"] = "test"
        elif any(kw in question_lower for kw in ['缺陷', 'defect', 'bug', '问题', '故障']):
            intent["domain"] = "defect"
        
        # 识别动作
        if any(kw in question_lower for kw in ['多少', '数量', '统计', 'count']):
            intent["action"] = "count"
        elif any(kw in question_lower for kw in ['列表', '哪些', 'list']):
            intent["action"] = "list"
        elif any(kw in question_lower for kw in ['趋势', '变化', 'trend']):
            intent["action"] = "trend"
        elif any(kw in question_lower for kw in ['分析', '情况', 'analyze']):
            intent["action"] = "analyze"
        
        # 识别筛选条件
        # 项目
        project_match = re.search(r'(\w+)系统|项目[:\s]*(\w+)', question)
        if project_match:
            intent["filters"]["project"] = project_match.group(1) or project_match.group(2)
        
        # 模块
        module_match = re.search(r'(\w+)模块|module[:\s]*(\w+)', question)
        if module_match:
            intent["filters"]["module"] = module_match.group(1) or module_match.group(2)
        
        # 状态
        if '通过' in question_lower or 'passed' in question_lower:
            intent["filters"]["status"] = "Passed"
        elif '失败' in question_lower or 'failed' in question_lower:
            intent["filters"]["status"] = "Failed"
        elif 'open' in question_lower or '打开' in question_lower:
            intent["filters"]["status"] = "Open"
        
        # 严重程度
        if 'critical' in question_lower or '严重' in question_lower:
            intent["filters"]["severity"] = "Critical"
        elif 'major' in question_lower or '重要' in question_lower:
            intent["filters"]["severity"] = "Major"
        elif 'minor' in question_lower or '轻微' in question_lower:
            intent["filters"]["severity"] = "Minor"
        
        # 时间范围
        if '本周' in question_lower:
            intent["time_range"] = "this_week"
        elif '上周' in question_lower:
            intent["time_range"] = "last_week"
        elif '本月' in question_lower:
            intent["time_range"] = "this_month"
        elif '最近' in question_lower:
            intent["time_range"] = "recent"
        
        return intent
    
    def execute_query(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """根据意图执行查询"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        results = {
            "success": False,
            "data": None,
            "sql": None,
            "message": "",
            "intent": intent
        }
        
        try:
            # 测试相关查询
            if intent["domain"] == "test":
                results = self._query_tests(cursor, intent)
            # 缺陷相关查询
            elif intent["domain"] == "defect":
                results = self._query_defects(cursor, intent)
            # 综合查询
            else:
                results = self._query_overview(cursor, intent)
        
        except Exception as e:
            results["message"] = f"查询失败: {str(e)}"
        
        return results
    
    def _query_tests(self, cursor, intent: Dict) -> Dict[str, Any]:
        """测试数据查询"""
        filters = intent.get("filters", {})
        action = intent.get("action", "count")
        
        # 构建WHERE条件
        where_clauses = []
        params = []
        
        if "project" in filters:
            where_clauses.append("project = ?")
            params.append(filters["project"])
        if "module" in filters:
            where_clauses.append("module = ?")
            params.append(filters["module"])
        if "status" in filters:
            where_clauses.append("status = ?")
            params.append(filters["status"])
        if "tester" in filters:
            where_clauses.append("tester = ?")
            params.append(filters["tester"])
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # 根据动作选择查询
        if action == "count":
            # 统计查询
            sql = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'Blocked' THEN 1 ELSE 0 END) as blocked,
                ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate
            FROM test_runs
            WHERE {where_sql}
            """
            cursor.execute(sql, params)
            row = cursor.fetchone()
            
            results = {
                "success": True,
                "sql": sql,
                "data": {
                    "total": row["total"],
                    "passed": row["passed"],
                    "failed": row["failed"],
                    "blocked": row["blocked"],
                    "pass_rate": f"{row['pass_rate']}%" if row["pass_rate"] else "N/A"
                },
                "message": f"共 {row['total']} 个测试，通过 {row['passed']} 个，失败 {row['failed']} 个，通过率 {row['pass_rate']}%"
            }
        
        elif action == "list":
            # 列表查询
            sql = f"""
            SELECT run_id, test_name, status, tester, project, module, test_week
            FROM test_runs
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT 50
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = {
                "success": True,
                "sql": sql,
                "data": [dict(row) for row in rows],
                "message": f"找到 {len(rows)} 条测试记录"
            }
        
        elif action == "trend":
            # 趋势查询
            sql = f"""
            SELECT 
                test_week,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed
            FROM test_runs
            WHERE {where_sql}
            GROUP BY test_week
            ORDER BY test_week DESC
            LIMIT 10
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = {
                "success": True,
                "sql": sql,
                "data": [dict(row) for row in rows],
                "message": f"查询到 {len(rows)} 个测试周的趋势数据"
            }
        
        else:
            # 默认分析
            sql = f"""
            SELECT 
                project,
                module,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate
            FROM test_runs
            WHERE {where_sql}
            GROUP BY project, module
            ORDER BY total DESC
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = {
                "success": True,
                "sql": sql,
                "data": [dict(row) for row in rows],
                "message": f"查询到 {len(rows)} 个项目/模块的测试情况"
            }
        
        return results
    
    def _query_defects(self, cursor, intent: Dict) -> Dict[str, Any]:
        """缺陷数据查询"""
        filters = intent.get("filters", {})
        action = intent.get("action", "count")
        
        # 构建WHERE条件
        where_clauses = []
        params = []
        
        if "project" in filters:
            where_clauses.append("project = ?")
            params.append(filters["project"])
        if "module" in filters:
            where_clauses.append("module = ?")
            params.append(filters["module"])
        if "status" in filters:
            where_clauses.append("status = ?")
            params.append(filters["status"])
        if "severity" in filters:
            where_clauses.append("severity = ?")
            params.append(filters["severity"])
        if "detected_by" in filters:
            where_clauses.append("detected_by = ?")
            params.append(filters["detected_by"])
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # 根据动作选择查询
        if action == "count":
            # 统计查询
            sql = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END) as open_count,
                SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'Closed' THEN 1 ELSE 0 END) as closed,
                SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN severity = 'Major' THEN 1 ELSE 0 END) as major,
                SUM(CASE WHEN severity = 'Minor' THEN 1 ELSE 0 END) as minor
            FROM defects
            WHERE {where_sql}
            """
            cursor.execute(sql, params)
            row = cursor.fetchone()
            
            results = {
                "success": True,
                "sql": sql,
                "data": {
                    "total": row["total"],
                    "open": row["open_count"],
                    "in_progress": row["in_progress"],
                    "closed": row["closed"],
                    "critical": row["critical"],
                    "major": row["major"],
                    "minor": row["minor"]
                },
                "message": f"共 {row['total']} 个缺陷，其中 Open {row['open_count']} 个，Critical {row['critical']} 个"
            }
        
        elif action == "list":
            # 列表查询
            sql = f"""
            SELECT defect_id, title, severity, status, project, module, detected_by, creation_time
            FROM defects
            WHERE {where_sql}
            ORDER BY creation_time DESC
            LIMIT 50
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = {
                "success": True,
                "sql": sql,
                "data": [dict(row) for row in rows],
                "message": f"找到 {len(rows)} 条缺陷记录"
            }
        
        elif action == "trend":
            # 趋势查询
            sql = f"""
            SELECT 
                strftime('%Y-%m', creation_time) as month,
                COUNT(*) as total,
                SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN severity = 'Major' THEN 1 ELSE 0 END) as major
            FROM defects
            WHERE {where_sql}
            GROUP BY strftime('%Y-%m', creation_time)
            ORDER BY month DESC
            LIMIT 12
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = {
                "success": True,
                "sql": sql,
                "data": [dict(row) for row in rows],
                "message": f"查询到 {len(rows)} 个月的缺陷趋势"
            }
        
        else:
            # 按模块/严重程度分布
            sql = f"""
            SELECT 
                project,
                module,
                severity,
                COUNT(*) as count
            FROM defects
            WHERE {where_sql}
            GROUP BY project, module, severity
            ORDER BY count DESC
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            results = {
                "success": True,
                "sql": sql,
                "data": [dict(row) for row in rows],
                "message": f"查询到 {len(rows)} 个项目/模块的缺陷分布"
            }
        
        return results
    
    def _query_overview(self, cursor, intent: Dict) -> Dict[str, Any]:
        """综合概览查询"""
        # 测试概览
        cursor.execute("""
            SELECT 
                COUNT(*) as total_tests,
                SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed
            FROM test_runs
        """)
        test_stats = cursor.fetchone()
        
        # 缺陷概览
        cursor.execute("""
            SELECT 
                COUNT(*) as total_defects,
                SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END) as open_defects,
                SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical
            FROM defects
        """)
        defect_stats = cursor.fetchone()
        
        results = {
            "success": True,
            "data": {
                "tests": {
                    "total": test_stats["total_tests"],
                    "passed": test_stats["passed"],
                    "failed": test_stats["failed"],
                    "pass_rate": f"{100 * test_stats['passed'] / max(test_stats['total_tests'], 1):.1f}%"
                },
                "defects": {
                    "total": defect_stats["total_defects"],
                    "open": defect_stats["open_defects"],
                    "critical": defect_stats["critical"]
                }
            },
            "message": f"测试概览: {test_stats['total_tests']} 个测试, 通过率 {100 * test_stats['passed'] / max(test_stats['total_tests'], 1):.1f}%\n缺陷概览: {defect_stats['total_defects']} 个缺陷, {defect_stats['open_defects']} 个未关闭"
        }
        
        return results
    
    def answer_question(self, question: str) -> str:
        """回答用户问题"""
        # 理解问题
        intent = self.understand_question(question)
        
        # 执行查询
        result = self.execute_query(intent)
        
        # 格式化回答
        if result["success"]:
            response = f"📊 {result['message']}\n\n"
            
            if isinstance(result["data"], dict):
                for key, value in result["data"].items():
                    response += f"- **{key}**: {value}\n"
            elif isinstance(result["data"], list):
                for i, item in enumerate(result["data"][:10], 1):
                    response += f"{i}. {item}\n"
            
            return response
        else:
            return f"❌ {result['message']}"
    
    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()


# 使用示例
if __name__ == "__main__":
    # 动态获取数据库路径
    try:
        from config_center import cfg
        db_path = str(cfg.DATABASE_FILE)
    except ImportError:
        import os
        _this_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(_this_dir, 'local_data.db')
    data_agent = AgentDataUnderstanding(db_path)
    
    # 测试各种问题
    questions = [
        "测试通过率是多少?",
        "有多少个Open的缺陷?",
        "ABS系统的测试情况怎么样?",
        "显示所有的Critical缺陷",
        "本周的测试执行情况"
    ]
    
    for q in questions:
        print(f"\n❓ 问题: {q}")
        print(f"📝 回答:\n{data_agent.answer_question(q)}")
        print("-" * 60)
    
    data_agent.close()

#!/usr/bin/env python3
"""
集成业务知识的增强版 Agent 数据理解层 V3
自动加载 business_knowledge.py 中的业务知识
让 Agent 能够深度理解你的测试业务

使用方法:
    from database.agent_data_understanding_v3 import AgentDataUnderstandingV3
    agent = AgentDataUnderstandingV3()
    result = agent.understand_and_query("最近一周 ABS 系统的缺陷情况")
"""

import sqlite3
import json
import re
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

# 导入业务知识
try:
    import business_knowledge as bk
    BUSINESS_KNOWLEDGE_AVAILABLE = True
except ImportError:
    BUSINESS_KNOWLEDGE_AVAILABLE = False
    bk = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AgentDataUnderstandingV3:
    """增强版 Agent 数据理解层 V3 - 集成业务知识"""
    
    def __init__(self, db_path: str = 'database/local_data.db'):
        self.db_path = db_path
        self.conn = None
        self.schema_context = self._build_schema_context()
        self.business_context = self._build_business_context()
    
    def _get_connection(self):
        if not self.conn:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def _build_schema_context(self) -> str:
        """构建数据库 Schema 上下文"""
        return """
## 数据库结构说明

### test_runs (测试运行记录)
- run_id: 测试运行唯一ID
- test_name: 测试用例名称
- status: 运行状态 (Passed/Failed/Blocked/Skipped)
- tester: 执行人
- project: 所属项目
- module: 所属模块
- test_week: 测试周 (格式: 26-CW11)
- duration_seconds: 执行时长

### defects (缺陷记录)
- defect_id: 缺陷唯一ID
- title: 缺陷标题
- severity: 严重程度 (Critical/Major/Medium/Minor)
- status: 状态 (Open/In Progress/Fixed/Closed)
- project: 所属项目
- module: 所属模块
- detected_by: 发现人
- creation_time: 创建时间
- pingpong: 往返次数
"""
    
    def _build_business_context(self) -> str:
        """构建业务上下文 - 从 business_knowledge.py 加载"""
        if not BUSINESS_KNOWLEDGE_AVAILABLE:
            return ""
        
        context = "\n## 业务知识\n"
        
        # 项目定义
        if hasattr(bk, 'PROJECTS') and bk.PROJECTS:
            context += "\n### 项目代号说明\n"
            for code, meaning in bk.PROJECTS.items():
                context += f"- {code}: {meaning}\n"
        
        # 模块定义
        if hasattr(bk, 'MODULES') and bk.MODULES:
            context += "\n### AIDA 模块说明\n"
            for code, meaning in bk.MODULES.items():
                context += f"- {code}: {meaning}\n"
        
        # 严重程度定义
        if hasattr(bk, 'SEVERITY_LEVELS') and bk.SEVERITY_LEVELS:
            context += "\n### 缺陷严重程度定义\n"
            for level, info in bk.SEVERITY_LEVELS.items():
                ctx = info.get('chinese', '')
                desc = info.get('description', '')
                response = info.get('response_time', '')
                context += f"- {level} ({ctx}): {desc} (响应时间: {response})\n"
        
        # 测试周期说明
        if hasattr(bk, 'TEST_CYCLE_INFO') and bk.TEST_CYCLE_INFO:
            context += "\n### 测试周期说明\n"
            context += bk.TEST_CYCLE_INFO + "\n"
        
        # 风险评分规则
        if hasattr(bk, 'RISK_RULES') and bk.RISK_RULES:
            context += "\n### 风险评分扩展规则\n"
            context += bk.RISK_RULES + "\n"
        
        # 业务规则
        if hasattr(bk, 'BUSINESS_RULES') and bk.BUSINESS_RULES:
            context += "\n### 特定业务规则\n"
            context += bk.BUSINESS_RULES + "\n"
        
        logger.info("✅ 业务知识上下文已加载")
        return context
    
    def understand_question(self, question: str) -> Dict[str, Any]:
        """理解用户问题，返回查询意图"""
        question_lower = question.lower()
        
        intent = {
            "domain": None,  # test 或 defect
            "action": None,  # count, list, trend, analyze
            "filters": {},
            "aggregation": None,
            "time_range": None,
            "original_question": question
        }
        
        # 识别领域
        if any(kw in question_lower for kw in ['测试', 'test', '用例', '运行', '执行', '通过率']):
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
        elif any(kw in question_lower for kw in ['风险', 'risk', '高危']):
            intent["action"] = "risk"
        elif any(kw in question_lower for kw in ['通过率', 'pass rate']):
            intent["action"] = "pass_rate"
        
        # 识别时间范围
        if any(kw in question_lower for kw in ['最近', '上周', '本周', 'last']):
            if 'week' in question_lower or '周' in question_lower:
                intent["time_range"] = "last_week"
            elif 'month' in question_lower or '月' in question_lower:
                intent["time_range"] = "last_month"
        
        # 识别项目/模块（使用业务知识中的定义）
        if BUSINESS_KNOWLEDGE_AVAILABLE and hasattr(bk, 'PROJECTS'):
            for project_code in bk.PROJECTS.keys():
                if project_code.lower() in question_lower:
                    intent["filters"]["project"] = project_code
        
        if BUSINESS_KNOWLEDGE_AVAILABLE and hasattr(bk, 'MODULES'):
            for module_code in bk.MODULES.keys():
                if module_code.lower() in question_lower.replace('_', ''):
                    intent["filters"]["module"] = module_code
        
        # 识别严重程度
        if BUSINESS_KNOWLEDGE_AVAILABLE and hasattr(bk, 'SEVERITY_LEVELS'):
            for severity in bk.SEVERITY_LEVELS.keys():
                if severity.lower() in question_lower:
                    intent["filters"]["severity"] = severity
        
        return intent
    
    def execute_query(self, intent: Dict) -> Dict[str, Any]:
        """根据意图执行查询"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            domain = intent.get("domain", "defect")
            action = intent.get("action", "count")
            filters = intent.get("filters", {})
            
            # 构建查询
            if domain == "test":
                sql = "SELECT * FROM test_runs WHERE 1=1"
                for key, value in filters.items():
                    sql += f" AND {key} = '{value}'"
                if action == "count":
                    sql = sql.replace("*", "COUNT(*) as count")
            else:
                sql = "SELECT * FROM defects WHERE 1=1"
                for key, value in filters.items():
                    sql += f" AND {key} = '{value}'"
                if action == "count":
                    sql = sql.replace("*", "COUNT(*) as count")
            
            cursor.execute(sql)
            results = cursor.fetchall()
            
            if action == "count":
                return {"success": True, "data": [{"count": results[0][0] if results else 0}]}
            else:
                return {"success": True, "data": [dict(row) for row in results]}
                
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def get_full_context(self) -> str:
        """获取完整的上下文（Schema + 业务知识）"""
        return self.schema_context + self.business_context
    
    def close(self):
        if self.conn:
            self.conn.close()


# 测试代码
if __name__ == "__main__":
    print("=" * 70)
    print("🎯 Agent 数据理解层 V3 - 业务知识集成版")
    print("=" * 70)
    
    # 创建 Agent
    agent = AgentDataUnderstandingV3()
    
    # 显示加载的业务知识
    print("\n📚 已加载的业务知识:")
    print(agent.business_context[:500] + "...")
    
    # 测试问题理解
    print("\n" + "=" * 70)
    print("🧪 测试问题理解")
    print("=" * 70)
    
    test_questions = [
        "最近一周 ABS 系统的缺陷有多少？",
        "显示所有 Critical 级别的缺陷",
        "IDCEVO 项目的测试通过率是多少？",
        "哪个模块的风险最高？"
    ]
    
    for q in test_questions:
        intent = agent.understand_question(q)
        print(f"\n问题: {q}")
        print(f"意图: {json.dumps(intent, ensure_ascii=False, indent=2)}")
    
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("=" * 70)

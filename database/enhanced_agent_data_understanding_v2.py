#!/usr/bin/env python3
"""
增强版 Agent 数据理解层 V2
基于多 Agent 协作分析结果改进

改进内容：
1. ✅ 添加完善的异常处理机制 (QA-Agent 建议)
2. ✅ 增强测试周格式理解 (PM-Agent 建议)
3. ✅ 添加测试效率分析场景 (PM-Agent 建议)
4. ✅ 实现 Schema 自动发现 (Dev-Agent 建议)
5. ✅ 添加语义层抽象 (Dev-Agent 建议)
6. ✅ 添加输入验证和清洗 (QA-Agent 建议)
7. ✅ 实现 Few-Shot 意图识别优化 (Dev-Agent 建议)

作者: AI Assistant (多 Agent 协作)
日期: 2026-03-19
"""

import sqlite3
import json
import re
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# 语义层 - 抽象数据库细节 (Dev-Agent 建议2)
# ============================================================================

@dataclass
class SemanticField:
    """语义字段定义"""
    db_name: str           # 数据库字段名
    display_name: str      # 显示名称
    description: str       # 描述
    data_type: str         # 数据类型
    business_meaning: str  # 业务含义
    example_values: List[str] = field(default_factory=list)


@dataclass
class SemanticTable:
    """语义表定义"""
    db_name: str
    display_name: str
    description: str
    business_purpose: str
    fields: Dict[str, SemanticField] = field(default_factory=dict)


class SemanticLayer:
    """语义层 - 将数据库 Schema 映射为业务概念"""
    
    def __init__(self):
        self.tables: Dict[str, SemanticTable] = {}
        self._initialize_semantic_model()
    
    def _initialize_semantic_model(self):
        """初始化语义模型"""
        # 测试运行表语义定义
        test_runs_fields = {
            'run_id': SemanticField(
                db_name='run_id', display_name='测试运行ID',
                description='唯一标识一次测试运行',
                data_type='TEXT', business_meaning='测试执行追踪标识',
                example_values=['TR-26-001', 'TR-26-002']
            ),
            'test_name': SemanticField(
                db_name='test_name', display_name='测试用例名称',
                description='测试用例的名称',
                data_type='TEXT', business_meaning='测试内容描述',
                example_values=['用户登录测试', '数据导入测试']
            ),
            'status': SemanticField(
                db_name='status', display_name='执行状态',
                description='测试执行结果状态',
                data_type='TEXT', business_meaning='测试通过/失败',
                example_values=['Passed', 'Failed', 'Blocked']
            ),
            'tester': SemanticField(
                db_name='tester', display_name='执行人员',
                description='执行测试的人员',
                data_type='TEXT', business_meaning='责任归属',
                example_values=['张三', '李四']
            ),
            'project': SemanticField(
                db_name='project', display_name='项目',
                description='所属项目',
                data_type='TEXT', business_meaning='项目维度分析',
                example_values=['ABS系统', 'CRM系统']
            ),
            'module': SemanticField(
                db_name='module', display_name='模块',
                description='所属模块',
                data_type='TEXT', business_meaning='模块维度分析',
                example_values=['用户管理', '数据处理']
            ),
            'test_week': SemanticField(
                db_name='test_week', display_name='测试周',
                description='测试周期标识（格式：年份-CW周数）',
                data_type='TEXT', business_meaning='时间维度分析',
                example_values=['26-CW11', '26-CW12']
            ),
            'duration_seconds': SemanticField(
                db_name='duration_seconds', display_name='执行时长(秒)',
                description='测试执行耗时',
                data_type='REAL', business_meaning='测试效率指标',
                example_values=['120.5', '300.0']
            )
        }
        
        self.tables['test_runs'] = SemanticTable(
            db_name='test_runs',
            display_name='测试运行记录',
            description='存储每次测试执行的详细信息',
            business_purpose='跟踪测试执行情况，分析测试覆盖率和通过率',
            fields=test_runs_fields
        )
        
        # 缺陷表语义定义
        defects_fields = {
            'defect_id': SemanticField(
                db_name='defect_id', display_name='缺陷ID',
                description='唯一标识一个缺陷',
                data_type='TEXT', business_meaning='缺陷追踪标识',
                example_values=['DEF-26-001', 'DEF-26-002']
            ),
            'title': SemanticField(
                db_name='title', display_name='缺陷标题',
                description='缺陷的简要描述',
                data_type='TEXT', business_meaning='问题概述',
                example_values=['登录失败时无提示信息']
            ),
            'severity': SemanticField(
                db_name='severity', display_name='严重程度',
                description='缺陷的严重等级',
                data_type='TEXT', business_meaning='风险优先级',
                example_values=['Critical', 'Major', 'Minor']
            ),
            'status': SemanticField(
                db_name='status', display_name='缺陷状态',
                description='缺陷当前处理状态',
                data_type='TEXT', business_meaning='处理进度',
                example_values=['Open', 'In Progress', 'Fixed', 'Closed']
            ),
            'project': SemanticField(
                db_name='project', display_name='项目',
                description='所属项目',
                data_type='TEXT', business_meaning='项目维度分析',
                example_values=['ABS系统']
            ),
            'module': SemanticField(
                db_name='module', display_name='模块',
                description='所属模块',
                data_type='TEXT', business_meaning='模块维度分析',
                example_values=['用户管理', '数据处理']
            ),
            'detected_by': SemanticField(
                db_name='detected_by', display_name='发现人',
                description='发现缺陷的人员',
                data_type='TEXT', business_meaning='发现来源',
                example_values=['张三', '李四']
            ),
            'creation_time': SemanticField(
                db_name='creation_time', display_name='创建时间',
                description='缺陷创建时间',
                data_type='TEXT', business_meaning='时间维度分析',
                example_values=['2026-03-15']
            ),
            'pingpong': SemanticField(
                db_name='pingpong', display_name='往返次数',
                description='缺陷往返开发测试的次数',
                data_type='INTEGER', business_meaning='修复效率指标',
                example_values=['0', '1', '2']
            )
        }
        
        self.tables['defects'] = SemanticTable(
            db_name='defects',
            display_name='缺陷记录',
            description='存储缺陷的详细信息',
            business_purpose='跟踪缺陷生命周期，分析质量风险',
            fields=defects_fields
        )
    
    def get_business_context(self, table_name: str) -> str:
        """获取表的业务上下文描述"""
        if table_name in self.tables:
            table = self.tables[table_name]
            context = f"表 {table.display_name}: {table.description}\n"
            context += f"业务用途: {table.business_purpose}\n"
            context += "关键字段:\n"
            for field_name, field in table.fields.items():
                context += f"  - {field.display_name}({field.db_name}): {field.business_meaning}\n"
            return context
        return ""
    
    def suggest_queries(self, question: str) -> List[str]:
        """基于语义层建议查询"""
        suggestions = []
        question_lower = question.lower()
        
        for table_name, table in self.tables.items():
            if any(kw in question_lower for kw in ['测试', 'test']) and table_name == 'test_runs':
                suggestions.append(f"建议查询表: {table.display_name}")
            elif any(kw in question_lower for kw in ['缺陷', 'bug', 'defect']) and table_name == 'defects':
                suggestions.append(f"建议查询表: {table.display_name}")
        
        return suggestions


# ============================================================================
# Schema 自动发现 (Dev-Agent 建议1)
# ============================================================================

class SchemaDiscovery:
    """数据库 Schema 自动发现"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.schema_cache: Dict[str, Any] = {}
    
    def discover_schema(self) -> Dict[str, Any]:
        """自动发现数据库结构"""
        if self.schema_cache:
            return self.schema_cache
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取所有表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                # 获取表结构
                cursor.execute(f"PRAGMA table_info({table})")
                columns = cursor.fetchall()
                
                # 获取记录数
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                
                # 获取样例数据
                cursor.execute(f"SELECT * FROM {table} LIMIT 1")
                sample = cursor.fetchone()
                
                self.schema_cache[table] = {
                    'columns': [
                        {
                            'name': col[1],
                            'type': col[2],
                            'notnull': bool(col[3]),
                            'pk': bool(col[5])
                        } for col in columns
                    ],
                    'row_count': count,
                    'sample_data': sample
                }
            
            conn.close()
            logger.info(f"✅ Schema 发现完成: {len(tables)} 个表")
            
        except Exception as e:
            logger.error(f"Schema 发现失败: {e}")
        
        return self.schema_cache
    
    def get_table_summary(self) -> str:
        """获取表摘要"""
        schema = self.discover_schema()
        summary = "数据库结构摘要:\n"
        for table, info in schema.items():
            summary += f"  - {table}: {info['row_count']} 条记录, {len(info['columns'])} 个字段\n"
        return summary


# ============================================================================
# 测试周解析器 (PM-Agent 建议1)
# ============================================================================

class TestWeekParser:
    """测试周格式解析器"""
    
    # 测试周格式正则表达式
    PATTERNS = [
        (r'(\d{2})-CW(\d{2})', 'YY-CWNN'),      # 26-CW11
        (r'(\d{4})-CW(\d{2})', 'YYYY-CWNN'),    # 2026-CW11
        (r'CW(\d{2})', 'CWNN'),                  # CW11
        (r'第(\d+)周', '中文'),                   # 第11周
    ]
    
    @classmethod
    def parse(cls, test_week: str) -> Optional[Dict[str, Any]]:
        """解析测试周格式"""
        if not test_week:
            return None
        
        for pattern, format_name in cls.PATTERNS:
            match = re.search(pattern, test_week)
            if match:
                groups = match.groups()
                if format_name == 'YY-CWNN':
                    return {
                        'year': 2000 + int(groups[0]),
                        'week': int(groups[1]),
                        'format': format_name,
                        'display': f"{groups[0]}年第{groups[1]}周"
                    }
                elif format_name == 'YYYY-CWNN':
                    return {
                        'year': int(groups[0]),
                        'week': int(groups[1]),
                        'format': format_name,
                        'display': f"{groups[0]}年第{groups[1]}周"
                    }
                elif format_name == 'CWNN':
                    current_year = datetime.now().year
                    return {
                        'year': current_year,
                        'week': int(groups[0]),
                        'format': format_name,
                        'display': f"{current_year}年第{groups[0]}周"
                    }
                elif format_name == '中文':
                    current_year = datetime.now().year
                    return {
                        'year': current_year,
                        'week': int(groups[0]),
                        'format': format_name,
                        'display': f"{current_year}年第{groups[0]}周"
                    }
        
        return None
    
    @classmethod
    def compare(cls, week1: str, week2: str) -> int:
        """比较两个测试周，返回 -1, 0, 1"""
        parsed1 = cls.parse(week1)
        parsed2 = cls.parse(week2)
        
        if not parsed1 or not parsed2:
            return 0
        
        if parsed1['year'] != parsed2['year']:
            return -1 if parsed1['year'] < parsed2['year'] else 1
        if parsed1['week'] != parsed2['week']:
            return -1 if parsed1['week'] < parsed2['week'] else 1
        return 0
    
    @classmethod
    def get_week_range(cls, test_week: str) -> Tuple[datetime, datetime]:
        """获取测试周对应的日期范围"""
        parsed = cls.parse(test_week)
        if not parsed:
            return None, None
        
        year = parsed['year']
        week = parsed['week']
        
        # ISO 周的第一天是周一
        first_day = datetime.strptime(f"{year}-{week}-1", "%Y-%W-%w")
        last_day = first_day + timedelta(days=6)
        
        return first_day, last_day


# ============================================================================
# Few-Shot 意图识别 (Dev-Agent 建议3)
# ============================================================================

@dataclass
class IntentExample:
    """意图识别示例"""
    question: str
    domain: str
    action: str
    filters: Dict[str, str] = field(default_factory=dict)


class FewShotIntentRecognizer:
    """Few-Shot 意图识别器"""
    
    # 预定义示例
    EXAMPLES = [
        IntentExample("测试通过率是多少？", "test", "count", {}),
        IntentExample("有多少个测试失败？", "test", "count", {"status": "Failed"}),
        IntentExample("ABS系统的测试情况", "test", "analyze", {"project": "ABS系统"}),
        IntentExample("用户管理模块的缺陷有多少？", "defect", "count", {"module": "用户管理"}),
        IntentExample("显示所有Critical缺陷", "defect", "list", {"severity": "Critical"}),
        IntentExample("本周的测试趋势", "test", "trend", {"time_range": "this_week"}),
        IntentExample("缺陷趋势分析", "defect", "trend", {}),
        IntentExample("张三发现了多少缺陷？", "defect", "count", {"detected_by": "张三"}),
        IntentExample("测试效率怎么样？", "test", "efficiency", {}),
        IntentExample("执行时间最长的测试", "test", "list", {"sort": "duration_seconds"}),
    ]
    
    def __init__(self):
        self.intent_keywords = self._build_intent_keywords()
    
    def _build_intent_keywords(self) -> Dict[str, List[str]]:
        """构建意图关键词映射"""
        return {
            'test': ['测试', 'test', '用例', '运行', '执行', '通过率', '效率'],
            'defect': ['缺陷', 'defect', 'bug', '问题', '故障', '缺陷'],
            'count': ['多少', '数量', '统计', 'count', '几个'],
            'list': ['列表', '哪些', '显示', 'list', '列出'],
            'trend': ['趋势', '变化', 'trend', '走势'],
            'analyze': ['分析', '情况', '怎么样', 'analyze'],
            'efficiency': ['效率', '时长', '耗时', '速度', 'efficiency']
        }
    
    def recognize(self, question: str) -> Dict[str, Any]:
        """识别问题意图"""
        question_lower = question.lower()
        
        # 计算与示例的相似度
        best_match = None
        best_score = 0
        
        for example in self.EXAMPLES:
            score = self._calculate_similarity(question_lower, example.question.lower())
            if score > best_score:
                best_score = score
                best_match = example
        
        # 基于关键词的意图识别
        intent = {
            'domain': None,
            'action': None,
            'filters': {},
            'confidence': 0.0,
            'matched_example': None
        }
        
        # 识别领域
        for domain, keywords in self.intent_keywords.items():
            if domain in ['test', 'defect']:
                if any(kw in question_lower for kw in keywords):
                    intent['domain'] = domain
                    break
        
        # 识别动作
        for action, keywords in self.intent_keywords.items():
            if action in ['count', 'list', 'trend', 'analyze', 'efficiency']:
                if any(kw in question_lower for kw in keywords):
                    intent['action'] = action
                    break
        
        # 如果有最佳匹配，使用其信息
        if best_match and best_score > 0.3:
            intent['domain'] = intent['domain'] or best_match.domain
            intent['action'] = intent['action'] or best_match.action
            intent['filters'] = {**best_match.filters, **intent['filters']}
            intent['matched_example'] = best_match.question
            intent['confidence'] = best_score
        
        return intent
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（简单版）"""
        words1 = set(text1)
        words2 = set(text2)
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)


# ============================================================================
# 输入验证器 (QA-Agent 建议3)
# ============================================================================

class InputValidator:
    """输入验证和清洗"""
    
    # SQL 注入危险模式
    SQL_INJECTION_PATTERNS = [
        r"'.*--",
        r";\s*DROP",
        r";\s*DELETE",
        r";\s*INSERT",
        r";\s*UPDATE",
        r"UNION\s+SELECT",
        r"OR\s+1\s*=\s*1",
    ]
    
    @classmethod
    def validate_and_sanitize(cls, user_input: str) -> Tuple[bool, str, str]:
        """
        验证并清洗用户输入
        返回: (是否有效, 清洗后的输入, 错误信息)
        """
        if not user_input:
            return False, "", "输入不能为空"
        
        # 长度检查
        if len(user_input) > 500:
            return False, "", "输入过长，最大500字符"
        
        # SQL 注入检查
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, user_input, re.IGNORECASE):
                logger.warning(f"检测到可疑SQL注入模式: {user_input}")
                return False, "", "输入包含不允许的内容"
        
        # 清洗：移除多余空格
        sanitized = ' '.join(user_input.split())
        
        # 清洗：移除特殊字符（保留中文、英文、数字、常见符号）
        sanitized = re.sub(r'[^\w\s\u4e00-\u9fff,.;:!?，。；：！？、]', '', sanitized)
        
        return True, sanitized, ""


# ============================================================================
# 增强版数据理解层
# ============================================================================

class EnhancedAgentDataUnderstandingV2:
    """
    增强版 Agent 数据理解层 V2
    
    集成所有改进：
    - 语义层抽象
    - Schema 自动发现
    - 测试周解析
    - Few-Shot 意图识别
    - 输入验证
    - 异常处理
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        
        # 初始化各组件
        self.semantic_layer = SemanticLayer()
        self.schema_discovery = SchemaDiscovery(db_path)
        self.intent_recognizer = FewShotIntentRecognizer()
        
        # 初始化 Schema
        self.schema = self.schema_discovery.discover_schema()
        
        logger.info("✅ 增强版数据理解层 V2 初始化完成")
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if not self.conn:
            try:
                self.conn = sqlite3.connect(self.db_path)
                self.conn.row_factory = sqlite3.Row
            except Exception as e:
                logger.error(f"数据库连接失败: {e}")
                raise
        return self.conn
    
    def understand_question(self, question: str) -> Dict[str, Any]:
        """
        理解用户问题
        
        改进：
        - 添加输入验证
        - 使用 Few-Shot 意图识别
        - 增强测试周解析
        """
        # 输入验证
        is_valid, sanitized, error = InputValidator.validate_and_sanitize(question)
        if not is_valid:
            return {
                'success': False,
                'error': error,
                'domain': None,
                'action': None
            }
        
        question = sanitized
        
        # Few-Shot 意图识别
        intent = self.intent_recognizer.recognize(question)
        
        # 增强测试周解析
        time_range = self._parse_time_range(question)
        if time_range:
            intent['time_range'] = time_range
        
        # 添加原始问题
        intent['original_question'] = question
        
        return intent
    
    def _parse_time_range(self, question: str) -> Optional[Dict[str, Any]]:
        """解析时间范围"""
        question_lower = question.lower()
        
        # 测试周格式
        week_pattern = r'\d{2}-CW\d{2}'
        match = re.search(week_pattern, question)
        if match:
            parsed = TestWeekParser.parse(match.group())
            if parsed:
                return {
                    'type': 'test_week',
                    'value': match.group(),
                    'parsed': parsed
                }
        
        # 相对时间
        if '本周' in question_lower:
            return {'type': 'relative', 'value': 'this_week'}
        elif '上周' in question_lower:
            return {'type': 'relative', 'value': 'last_week'}
        elif '本月' in question_lower:
            return {'type': 'relative', 'value': 'this_month'}
        
        return None
    
    def execute_query(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行查询
        
        改进：
        - 添加完善的异常处理
        - 支持测试效率分析
        - 支持更多场景
        """
        result = {
            'success': False,
            'data': None,
            'sql': None,
            'message': '',
            'intent': intent
        }
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            domain = intent.get('domain')
            action = intent.get('action')
            
            if domain == 'test':
                result = self._query_tests(cursor, intent)
            elif domain == 'defect':
                result = self._query_defects(cursor, intent)
            else:
                result = self._query_overview(cursor, intent)
                
        except sqlite3.Error as e:
            logger.error(f"数据库查询错误: {e}")
            result['message'] = f"数据库查询失败: {str(e)}"
            result['error_type'] = 'database_error'
            
        except Exception as e:
            logger.error(f"未知错误: {e}")
            result['message'] = f"查询失败: {str(e)}"
            result['error_type'] = 'unknown_error'
        
        return result
    
    def _query_tests(self, cursor, intent: Dict) -> Dict[str, Any]:
        """测试数据查询 - 支持效率分析"""
        filters = intent.get('filters', {})
        action = intent.get('action', 'count')
        
        # 构建安全 WHERE 条件
        where_clauses, params = self._build_safe_where('test_runs', filters)
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        if action == 'efficiency':
            # 测试效率分析 (PM-Agent 建议2)
            sql = f"""
            SELECT 
                project,
                module,
                tester,
                COUNT(*) as total_tests,
                SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                ROUND(AVG(duration_seconds), 2) as avg_duration,
                ROUND(MAX(duration_seconds), 2) as max_duration,
                ROUND(MIN(duration_seconds), 2) as min_duration,
                ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate
            FROM test_runs
            WHERE {where_sql}
            GROUP BY project, module, tester
            ORDER BY avg_duration DESC
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return {
                'success': True,
                'sql': sql,
                'data': [dict(row) for row in rows],
                'message': f"测试效率分析: 找到 {len(rows)} 个测试单元"
            }
        
        elif action == 'count':
            sql = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN status = 'Blocked' THEN 1 ELSE 0 END) as blocked,
                ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate,
                ROUND(AVG(duration_seconds), 2) as avg_duration
            FROM test_runs
            WHERE {where_sql}
            """
            cursor.execute(sql, params)
            row = cursor.fetchone()
            
            return {
                'success': True,
                'sql': sql,
                'data': dict(row),
                'message': f"共 {row['total']} 个测试，通过率 {row['pass_rate']}%，平均耗时 {row['avg_duration']}秒"
            }
        
        elif action == 'list':
            sql = f"""
            SELECT run_id, test_name, status, tester, project, module, test_week, duration_seconds
            FROM test_runs
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT 50
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return {
                'success': True,
                'sql': sql,
                'data': [dict(row) for row in rows],
                'message': f"找到 {len(rows)} 条测试记录"
            }
        
        elif action == 'trend':
            sql = f"""
            SELECT 
                test_week,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed,
                ROUND(AVG(duration_seconds), 2) as avg_duration
            FROM test_runs
            WHERE {where_sql}
            GROUP BY test_week
            ORDER BY test_week DESC
            LIMIT 10
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            # 解析测试周
            for row in rows:
                parsed = TestWeekParser.parse(row['test_week'])
                if parsed:
                    row = dict(row)
                    row['week_display'] = parsed['display']
            
            return {
                'success': True,
                'sql': sql,
                'data': [dict(row) for row in rows],
                'message': f"查询到 {len(rows)} 个测试周的趋势数据"
            }
        
        else:
            # 默认分析
            sql = f"""
            SELECT 
                project,
                module,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) as pass_rate,
                ROUND(AVG(duration_seconds), 2) as avg_duration
            FROM test_runs
            WHERE {where_sql}
            GROUP BY project, module
            ORDER BY total DESC
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return {
                'success': True,
                'sql': sql,
                'data': [dict(row) for row in rows],
                'message': f"查询到 {len(rows)} 个项目/模块的测试情况"
            }
    
    def _query_defects(self, cursor, intent: Dict) -> Dict[str, Any]:
        """缺陷数据查询"""
        filters = intent.get('filters', {})
        action = intent.get('action', 'count')
        
        where_clauses, params = self._build_safe_where('defects', filters)
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        if action == 'count':
            sql = f"""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END) as open_count,
                SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'Closed' THEN 1 ELSE 0 END) as closed,
                SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN severity = 'Major' THEN 1 ELSE 0 END) as major,
                SUM(CASE WHEN severity = 'Minor' THEN 1 ELSE 0 END) as minor,
                ROUND(AVG(pingpong), 2) as avg_pingpong
            FROM defects
            WHERE {where_sql}
            """
            cursor.execute(sql, params)
            row = cursor.fetchone()
            
            return {
                'success': True,
                'sql': sql,
                'data': dict(row),
                'message': f"共 {row['total']} 个缺陷，Open {row['open_count']} 个，Critical {row['critical']} 个，平均往返 {row['avg_pingpong']} 次"
            }
        
        elif action == 'list':
            sql = f"""
            SELECT defect_id, title, severity, status, project, module, detected_by, creation_time, pingpong
            FROM defects
            WHERE {where_sql}
            ORDER BY 
                CASE severity 
                    WHEN 'Critical' THEN 1 
                    WHEN 'Major' THEN 2 
                    WHEN 'Medium' THEN 3 
                    WHEN 'Minor' THEN 4 
                    ELSE 5 
                END,
                creation_time DESC
            LIMIT 50
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return {
                'success': True,
                'sql': sql,
                'data': [dict(row) for row in rows],
                'message': f"找到 {len(rows)} 条缺陷记录"
            }
        
        elif action == 'trend':
            sql = f"""
            SELECT 
                strftime('%Y-%m', creation_time) as month,
                COUNT(*) as total,
                SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) as critical,
                SUM(CASE WHEN severity = 'Major' THEN 1 ELSE 0 END) as major,
                SUM(CASE WHEN severity = 'Minor' THEN 1 ELSE 0 END) as minor
            FROM defects
            WHERE {where_sql}
            GROUP BY strftime('%Y-%m', creation_time)
            ORDER BY month DESC
            LIMIT 12
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return {
                'success': True,
                'sql': sql,
                'data': [dict(row) for row in rows],
                'message': f"查询到 {len(rows)} 个月的缺陷趋势"
            }
        
        else:
            sql = f"""
            SELECT 
                project,
                module,
                severity,
                COUNT(*) as count,
                SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END) as open_count
            FROM defects
            WHERE {where_sql}
            GROUP BY project, module, severity
            ORDER BY count DESC
            """
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            return {
                'success': True,
                'sql': sql,
                'data': [dict(row) for row in rows],
                'message': f"查询到 {len(rows)} 个项目/模块的缺陷分布"
            }
    
    def _query_overview(self, cursor, intent: Dict) -> Dict[str, Any]:
        """综合概览查询"""
        # 测试概览
        cursor.execute("""
            SELECT 
                COUNT(*) as total_tests,
                SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) as passed,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) as failed,
                ROUND(AVG(duration_seconds), 2) as avg_duration
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
        
        return {
            'success': True,
            'data': {
                'tests': {
                    'total': test_stats['total_tests'],
                    'passed': test_stats['passed'],
                    'failed': test_stats['failed'],
                    'pass_rate': f"{100 * test_stats['passed'] / max(test_stats['total_tests'], 1):.1f}%",
                    'avg_duration': test_stats['avg_duration']
                },
                'defects': {
                    'total': defect_stats['total_defects'],
                    'open': defect_stats['open_defects'],
                    'critical': defect_stats['critical']
                }
            },
            'message': f"测试: {test_stats['total_tests']} 个, 通过率 {100 * test_stats['passed'] / max(test_stats['total_tests'], 1):.1f}%, 平均耗时 {test_stats['avg_duration']}秒\n缺陷: {defect_stats['total_defects']} 个, Open {defect_stats['open_defects']} 个"
        }
    
    def _build_safe_where(self, table: str, filters: Dict) -> Tuple[List[str], List]:
        """构建安全的 WHERE 条件"""
        where_clauses = []
        params = []
        
        # 允许的字段白名单
        allowed_fields = {
            'test_runs': ['status', 'project', 'module', 'tester', 'test_week'],
            'defects': ['status', 'project', 'module', 'severity', 'detected_by']
        }
        
        for field, value in filters.items():
            if field in allowed_fields.get(table, []):
                where_clauses.append(f"{field} = ?")
                params.append(value)
        
        return where_clauses, params
    
    def answer_question(self, question: str) -> Dict[str, Any]:
        """回答用户问题"""
        # 理解问题
        intent = self.understand_question(question)
        
        if not intent.get('domain'):
            # 尝试使用语义层建议
            suggestions = self.semantic_layer.suggest_queries(question)
            if suggestions:
                return {
                    'success': False,
                    'message': f"无法确定问题领域，{'. '.join(suggestions)}",
                    'suggestions': suggestions
                }
            return {
                'success': False,
                'message': "无法理解问题，请尝试更明确的表达。例如：'测试通过率是多少？' 或 '显示所有Critical缺陷'"
            }
        
        # 执行查询
        result = self.execute_query(intent)
        
        # 格式化回答
        if result['success']:
            return {
                'success': True,
                'message': result['message'],
                'data': result['data'],
                'sql': result['sql'],
                'intent': intent
            }
        else:
            return result
    
    def get_business_context(self) -> str:
        """获取业务上下文描述"""
        context = "# 测试资产业务上下文\n\n"
        
        for table_name in ['test_runs', 'defects']:
            context += self.semantic_layer.get_business_context(table_name) + "\n"
        
        context += self.schema_discovery.get_table_summary()
        
        return context
    
    def close(self):
        """关闭连接"""
        if self.conn:
            self.conn.close()
            self.conn = None


# ============================================================================
# 测试
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

    # 初始化
    agent = EnhancedAgentDataUnderstandingV2(db_path)
    
    # 打印业务上下文
    print("=" * 80)
    print(agent.get_business_context())
    print("=" * 80)
    
    # 测试问题
    questions = [
        "测试通过率是多少？",
        "有多少个Open的缺陷？",
        "ABS系统的测试情况怎么样？",
        "显示所有的Critical缺陷",
        "测试效率怎么样？",
        "26-CW11测试周的执行情况",
        "本周的缺陷趋势"
    ]
    
    for q in questions:
        print(f"\n❓ 问题: {q}")
        result = agent.answer_question(q)
        if result['success']:
            print(f"📝 回答: {result['message']}")
            if 'data' in result and result['data']:
                print(f"📊 数据: {json.dumps(result['data'], indent=2, ensure_ascii=False, default=str)[:500]}")
        else:
            print(f"❌ {result['message']}")
        print("-" * 60)
    
    agent.close()

#!/usr/bin/env python3
"""
业务语义理解 - 理解业务术语、时间范围、项目上下文

能够：
1. 解析时间范围（"今天"、"本周"、"最近一周"等）
2. 理解项目上下文（每个项目的特点、常见问题）
3. 识别业务术语（TopIssue、High Runner、Long Runner 等）
4. 扩展查询上下文（根据关键词添加相关上下文）

使用方法：
from chatdb.business_semantics import BusinessSemantics

semantics = BusinessSemantics()

# 解析时间范围
time_range = semantics.parse_time_range("最近一周的 TopIssue")

# 获取项目上下文
context = semantics.get_project_context("App")

# 扩展查询
expanded_query = semantics.expand_query_with_context("导航缺陷", "App")

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

# 导入业务规则
from chatdb.business_rules import (
    PROJECTS,
    PROJECT_FULL_NAMES,
    TEAMS,
    FVP_ASSIGNMENTS,
    HIGH_RUNNER_THRESHOLD,
    LONG_RUNNER_THRESHOLD,
    BUSINESS_TERM_TO_SQL
)

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BusinessSemantics:
    """业务语义理解"""
    
    def __init__(self):
        """初始化语义理解器"""
        # 时间范围映射
        self.TIME_RANGES = {
            '今天': self._get_today_range,
            '昨天': self._get_yesterday_range,
            '前天': self._get_yesterday_range,
            '最近一天': self._get_yesterday_range,
            '最近3天': self._get_recent_days_range(3),
            '最近一周': self._get_recent_days_range(7),
            '最近7天': self._get_recent_days_range(7),
            '最近两周': self._get_recent_days_range(14),
            '最近一个月': self._get_recent_days_range(30),
            '最近30天': self._get_recent_days_range(30),
            '本周': self._get_this_week_range,
            '上周': self._get_last_week_range,
            '本月': self._get_this_month_range,
            '上月': self._get_last_month_range,
        }
        
        # 项目上下文
        self.PROJECT_CONTEXT = {
            'App': {
                'name': 'MyBMW App',
                'focus': '移动应用功能',
                'description': 'MyBMW 手机 App 的功能缺陷',
                'common_issues': [
                    '导航',
                    '蓝牙',
                    '音频',
                    'Car Apps',
                    '连接',
                    '推送通知'
                ],
                'typical_ecu': 'IuK_HU',
                'typical_team': 'IUK',
                'related_projects': ['IDC', 'MGU']
            },
            'IDC': {
                'name': 'ID Connected',
                'focus': '互联驾驶功能',
                'description': '车机互联、导航、地图显示等功能',
                'common_issues': [
                    '导航',
                    '地图显示',
                    '车机交互',
                    'CarPlay',
                    'Android Auto',
                    '连接'
                ],
                'typical_ecu': 'DIPS_HU',
                'typical_team': 'DIPS',
                'related_projects': ['App', 'MGU']
            },
            'IDCevo': {
                'name': 'IDC Evolution',
                'focus': '新一代IDC项目',
                'description': 'IDC项目的最新版本，包含新功能',
                'common_issues': [
                    '导航',
                    '地图',
                    '界面',
                    '新功能'
                ],
                'typical_ecu': 'DIPS_HU',
                'typical_team': 'DIPS',
                'related_projects': ['IDC']
            },
            'MGU': {
                'name': 'Media Graphics Unit',
                'focus': '媒体和图形功能',
                'description': '音频、视频、显示屏等媒体相关功能',
                'common_issues': [
                    '音频',
                    '视频',
                    '显示屏',
                    '图像显示',
                    '多媒体'
                ],
                'typical_ecu': 'IuK_HU',
                'typical_team': 'IUK',
                'related_projects': ['IDC', 'App']
            },
            'RSU': {
                'name': 'Remote Software Update',
                'focus': '远程软件更新',
                'description': 'OTA 软件更新功能',
                'common_issues': [
                    '更新失败',
                    '版本管理',
                    '下载',
                    '安装',
                    '更新流程'
                ],
                'typical_ecu': 'IuK_HU',
                'typical_team': 'IUK',
                'related_projects': ['App']
            },
        }
        
        # 功能模块上下文
        self.MODULE_CONTEXT = {
            'Navigation': {
                'keywords': ['导航', '路线', 'GPS', '导航地图'],
                'related_aidas': ['Navigation', 'Map Display'],
                'typical_ecu': 'IuK_HU',
                'typical_projects': ['App', 'IDC', 'MGU']
            },
            'Connectivity': {
                'keywords': ['连接', '蓝牙', 'WiFi', 'CarPlay', 'Android Auto'],
                'related_aidas': ['Connectivity'],
                'typical_ecu': ['IuK_HU', 'DIPS_HU'],
                'typical_projects': ['App', 'IDC']
            },
            'Audio': {
                'keywords': ['音频', '音乐', '声音', '扬声器'],
                'related_aidas': ['Entertainment', 'Audio'],
                'typical_ecu': 'IuK_HU',
                'typical_projects': ['MGU', 'IDC', 'App']
            },
            'Display': {
                'keywords': ['屏幕', '显示', '界面', '触摸屏'],
                'related_aidas': ['Map Display', 'Entertainment'],
                'typical_ecu': ['DIPS_HU', 'IuK_HU'],
                'typical_projects': ['MGU', 'IDC']
            },
            'OTA': {
                'keywords': ['OTA', '更新', '升级', '版本', '远程'],
                'related_aidas': ['OTA'],
                'typical_ecu': 'IuK_HU',
                'typical_projects': ['RSU']
            },
        }
        
        # 业务术语映射
        self.BUSINESS_TERMS = {
            'TopIssue': {
                'keywords': ['topissue', 'top issue', 'top 问题', '高风险'],
                'sql_condition': BUSINESS_TERM_TO_SQL.get('TopIssue'),
                'related_terms': ['极高风险', '高风险', 'risk score']
            },
            'High Runner': {
                'keywords': ['high runner', 'highrunner', '频繁转移', 'pingpong'],
                'sql_condition': BUSINESS_TERM_TO_SQL.get('High Runner'),
                'related_terms': ['ECU转移', 'Domain转移', '流转']
            },
            'Long Runner': {
                'keywords': ['long runner', 'longrunner', '长期未解决', '处理周期长'],
                'sql_condition': BUSINESS_TERM_TO_SQL.get('Long Runner'),
                'related_terms': ['处理周期', '未解决', '积压']
            },
            'Showstopper': {
                'keywords': ['showstopper', '阻塞', 'blocker', '严重'],
                'sql_condition': BUSINESS_TERM_TO_SQL.get('Showstopper'),
                'related_terms': ['阻塞发布', '关键路径']
            },
            'Parent': {
                'keywords': ['主票', 'parent', 'master'],
                'sql_condition': BUSINESS_TERM_TO_SQL.get('主票'),
                'related_terms': ['子票', 'child', 'master ticket']
            },
            'Child': {
                'keywords': ['子票', 'child', 'sub'],
                'sql_condition': BUSINESS_TERM_TO_SQL.get('子票'),
                'related_terms': ['主票', 'parent', 'master ticket']
            },
        }
        
        # 缓存
        self._cache = {}
    
    def parse_time_range(self, text: str) -> Optional[Tuple[datetime, datetime]]:
        """
        解析时间范围
        
        Args:
            text: 包含时间范围的文本
        
        Returns:
            (start_time, end_time) 或 None
        """
        text_lower = text.lower()
        
        # 匹配时间范围关键词
        for keyword, range_func in self.TIME_RANGES.items():
            if keyword in text_lower:
                try:
                    start_time, end_time = range_func()
                    logger.info(f"识别时间范围: {keyword} → {start_time} ~ {end_time}")
                    return start_time, end_time
                except Exception as e:
                    logger.warning(f"解析时间范围 '{keyword}' 失败: {e}")
                    continue
        
        # 尝试解析具体日期
        return self._parse_specific_dates(text)
    
    def get_project_context(self, project: str) -> Dict:
        """
        获取项目上下文
        
        Args:
            project: 项目名称
        
        Returns:
            项目上下文字典
        """
        project_key = None
        
        # 查找匹配的项目
        for p in PROJECTS:
            if p.lower() in project.lower():
                project_key = p
                break
        
        if not project_key:
            logger.warning(f"未找到项目上下文: {project}")
            return {}
        
        return self.PROJECT_CONTEXT.get(project_key, {})
    
    def get_module_context(self, module: str) -> Dict:
        """
        获取模块上下文
        
        Args:
            module: 模块名称
        
        Returns:
            模块上下文字典
        """
        module_lower = module.lower()
        
        for module_name, context in self.MODULE_CONTEXT.items():
            for keyword in context['keywords']:
                if keyword.lower() in module_lower:
                    logger.info(f"识别模块: {module_name}")
                    return context
        
        logger.warning(f"未找到模块上下文: {module}")
        return {}
    
    def identify_business_terms(self, text: str) -> List[Dict]:
        """
        识别文本中的业务术语
        
        Args:
            text: 输入文本
        
        Returns:
            识别的业务术语列表
        """
        text_lower = text.lower()
        identified = []
        
        for term_name, term_info in self.BUSINESS_TERMS.items():
            for keyword in term_info['keywords']:
                if keyword in text_lower:
                    identified.append({
                        'term': term_name,
                        'keyword': keyword,
                        'sql_condition': term_info['sql_condition'],
                        'related_terms': term_info['related_terms']
                    })
                    logger.info(f"识别业务术语: {term_name} (关键词: {keyword})")
                    break
        
        return identified
    
    def expand_query_with_context(self, query: str, project: str = None) -> str:
        """
        根据上下文扩展查询
        
        Args:
            query: 原始查询
            project: 项目名称（可选）
        
        Returns:
            扩展后的查询
        """
        expanded_parts = [query]
        
        # 1. 添加项目上下文
        if project:
            context = self.get_project_context(project)
            if context and 'common_issues' in context:
                common_issues = ', '.join(context['common_issues'])
                expanded_parts.append(f"(相关功能: {common_issues})")
        
        # 2. 识别并添加模块上下文
        module_context = self.get_module_context(query)
        if module_context:
            if 'related_aidas' in module_context:
                related_aidas = ', '.join(module_context['related_aidas'])
                expanded_parts.append(f"(相关功能模块: {related_aidas})")
        
        # 3. 识别业务术语并添加上下文
        terms = self.identify_business_terms(query)
        if terms:
            for term in terms:
                if term['related_terms']:
                    related = ', '.join(term['related_terms'])
                    expanded_parts.append(f"(相关概念: {related})")
        
        return ' '.join(expanded_parts)
    
    def _get_today_range(self) -> Tuple[datetime, datetime]:
        """今天的范围"""
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
    
    def _get_yesterday_range(self) -> Tuple[datetime, datetime]:
        """昨天的范围"""
        now = datetime.now()
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
    
    def _get_recent_days_range(self, days: int) -> Tuple[datetime, datetime]:
        """最近N天的范围"""
        now = datetime.now()
        start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        return start, end
    
    def _get_this_week_range(self) -> Tuple[datetime, datetime]:
        """本周的范围（周一到今天）"""
        now = datetime.now()
        # 计算本周一
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        return start, end
    
    def _get_last_week_range(self) -> Tuple[datetime, datetime]:
        """上周的范围"""
        now = datetime.now()
        # 计算本周一
        this_monday = now - timedelta(days=now.weekday())
        # 上周一
        start = this_monday - timedelta(weeks=1)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        # 上周日
        end = this_monday - timedelta(days=1)
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
    
    def _get_this_month_range(self) -> Tuple[datetime, datetime]:
        """本月的范围"""
        now = datetime.now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
        return start, end
    
    def _get_last_month_range(self) -> Tuple[datetime, datetime]:
        """上月的范围"""
        now = datetime.now()
        # 本月第一天
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # 上月第一天
        start = this_month_start - timedelta(days=1)
        start = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # 上月最后一天
        end = this_month_start - timedelta(seconds=1)
        end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
    
    def _parse_specific_dates(self, text: str) -> Optional[Tuple[datetime, datetime]]:
        """解析具体的日期"""
        # 尝试解析日期格式：YYYY-MM-DD
        date_pattern = r'(\d{4}-\d{2}-\d{2})'
        matches = re.findall(date_pattern, text)
        
        if matches:
            dates = []
            for date_str in matches:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    dates.append(date_obj)
                except ValueError:
                    continue
            
            if dates:
                start = min(dates)
                end = max(dates)
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
                end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
                
                if len(dates) == 1:
                    # 如果只有一个日期，返回当天的范围
                    end = datetime.now()
                
                logger.info(f"解析具体日期: {start} ~ {end}")
                return start, end
        
        return None
    
    def explain_query_with_context(self, query: str, project: str = None) -> str:
        """
        解释查询的上下文含义
        
        Args:
            query: 查询文本
            project: 项目名称（可选）
        
        Returns:
            上下文解释文本
        """
        parts = []
        
        # 1. 识别时间范围
        time_range = self.parse_time_range(query)
        if time_range:
            start, end = time_range
            parts.append(f"📅 时间范围: {start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}")
        
        # 2. 识别项目
        if project:
            context = self.get_project_context(project)
            if context:
                parts.append(f"📋 项目: {context.get('name', project)}")
                parts.append(f"📝 描述: {context.get('description', '')}")
                parts.append(f"🔧 常见问题: {', '.join(context.get('common_issues', [])[:3])}")
        
        # 3. 识别业务术语
        terms = self.identify_business_terms(query)
        if terms:
            parts.append(f"🏷️  识别的业务术语:")
            for term in terms[:3]:
                parts.append(f"  - {term['term']}: {term['sql_condition']}")
        
        return '\n'.join(parts) if parts else "未识别到明确的上下文信息"


# ============================================================================
# 工厂函数
# =============================================================================

def create_business_semantics() -> BusinessSemantics:
    """创建业务语义理解器"""
    return BusinessSemantics()


# ============================================================================
# 示例使用
# =============================================================================

if __name__ == "__main__":
    # 示例使用
    semantics = BusinessSemantics()
    
    print("="*70)
    print("📊 业务语义理解示例")
    print("="*70)
    
    # 示例 1: 解析时间范围
    print("\n【示例 1: 解析时间范围】")
    print("-"*70)
    
    test_queries = [
        "今天的 TopIssue",
        "最近一周的缺陷",
        "本周的 High Runner",
        "上个月的问题"
    ]
    
    for query in test_queries:
        print(f"\n问题: {query}")
        time_range = semantics.parse_time_range(query)
        if time_range:
            start, end = time_range
            print(f"  时间范围: {start.strftime('%Y-%m-%d %H:%M')} ~ {end.strftime('%Y-%m-%d %H:%M')}")
        else:
            print(f"  未识别到时间范围")
    
    # 示例 2: 获取项目上下文
    print("\n" + "="*70)
    print("【示例 2: 获取项目上下文】")
    print("-"*70)
    
    for project in PROJECTS[:3]:
        print(f"\n项目: {project}")
        context = semantics.get_project_context(project)
        if context:
            print(f"  名称: {context.get('name', '')}")
            print(f"  专注: {context.get('focus', '')}")
            print(f"  描述: {context.get('description', '')}")
            print(f"  常见问题: {', '.join(context.get('common_issues', [])[:3])}")
        else:
            print(f"  未找到上下文")
    
    # 示例 3: 扩展查询上下文
    print("\n" + "="*70)
    print("【示例 3: 扩展查询上下文】")
    print("-"*70)
    
    test_expansions = [
        ("导航缺陷", "App"),
        ("音频问题", "MGU"),
        ("OTA 更新", "RSU")
    ]
    
    for query, project in test_expansions:
        print(f"\n原查询: {query}")
        expanded = semantics.expand_query_with_context(query, project)
        print(f"扩展查询: {expanded}")
    
    # 示例 4: 识别业务术语
    print("\n" + "="*70)
    print("【示例 4: 识别业务术语】")
    print("-"*70)
    
    test_term_queries = [
        "查询所有 TopIssue",
        "找到 High Runner 缺陷",
        "Showstopper 问题"
    ]
    
    for query in test_term_queries:
        print(f"\n问题: {query}")
        terms = semantics.identify_business_terms(query)
        if terms:
            for term in terms:
                print(f"  术语: {term['term']}")
                print(f"  SQL: {term['sql_condition']}")
                print(f"  相关: {', '.join(term['related_terms'])}")
        else:
            print(f"  未识别到业务术语")
    
    print("\n" + "="*70)
    print("✅ 示例运行完成")
    print("="*70)

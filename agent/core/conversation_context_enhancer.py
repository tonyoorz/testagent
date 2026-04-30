"""
多轮对话上下文增强模块

基于现有 conversation_entity_tracker.py 的基础指代消解能力，
提供更深层的上下文理解，包括省略主语补全、追问上下文注入、比较意图处理、
澄清问题生成和可视化意图检测。

Features:
1. ContextEnhancer - 对话上下文增强，补全省略主语/追问/比较意图
2. ClarificationLayer - 低置信度意图的澄清问题生成
3. ChartIntentDetector - 从用户query检测可视化图表意图

Author: AI Assistant
Date: 2026-04-12
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime

from agent.core.conversation_entity_tracker import ConversationState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ContextEnhancer - 对话上下文增强
# ---------------------------------------------------------------------------

class ContextEnhancer:
    """
    多轮对话上下文增强器

    接收 ConversationState，对用户 query 进行增强：
    - 补全省略的主语/宾语
    - 处理追问意图（如 "为什么"、"原因呢"）
    - 处理比较意图（如 "和上月比"、"对比"）
    """

    # 省略主语的模式 → 需要从上下文填充的槽位
    SUBJECT_OMISSION_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
        # (pattern, 前缀模板槽名, 后缀)
        (re.compile(r'^(其中|里面|当中)(哪个|哪个ECU|哪个项目|谁)', re.IGNORECASE),
         'prefix_context', ''),
        (re.compile(r'^(哪个|哪几个|谁)(最|ECU|项目|测试)', re.IGNORECASE),
         'prefix_context', ''),
        (re.compile(r'^(有多少|总共|一共|数量)', re.IGNORECASE),
         'prefix_context', ''),
        (re.compile(r'^(分布|占比|比例|百分比)', re.IGNORECASE),
         'prefix_context', '情况'),
        (re.compile(r'^(严重|紧急|高风险)的', re.IGNORECASE),
         'prefix_context', ''),
        (re.compile(r'^(还有|另外)', re.IGNORECASE),
         'prefix_context', ''),
    ]

    # 追问意图模式
    FOLLOWUP_PATTERNS: List[Tuple[re.Pattern, str]] = [
        (re.compile(r'^为什么', re.IGNORECASE), 'reason'),
        (re.compile(r'^原因(是什么|呢|？|是什么)', re.IGNORECASE), 'reason'),
        (re.compile(r'^(怎么|如何)(处理|解决|改进|优化)', re.IGNORECASE), 'action'),
        (re.compile(r'^(还有|另外)(什么|哪些)', re.IGNORECASE), 'extend'),
        (re.compile(r'^(详细|具体|展开|深入)', re.IGNORECASE), 'detail'),
        (re.compile(r'^(然后|接下来|之后)', re.IGNORECASE), 'next'),
    ]

    # 比较意图模式
    COMPARISON_PATTERNS: List[Tuple[re.Pattern, str]] = [
        (re.compile(r'和(上个?月|上月|上个月)比', re.IGNORECASE), 'last_month'),
        (re.compile(r'和(上个?周|上周|上星期)比', re.IGNORECASE), 'last_week'),
        (re.compile(r'和(去年|上一年|同期)比', re.IGNORECASE), 'last_year'),
        (re.compile(r'(同比|环比|YoY|MoM)', re.IGNORECASE), 'yoy'),
        (re.compile(r'(对比|比较|compare)\s*(一?下|一下)?', re.IGNORECASE), 'general'),
    ]

    def enhance_query(self, question: str, state: ConversationState) -> str:
        """
        对用户 query 进行上下文增强

        Args:
            question: 用户原始问题
            state: 当前对话状态

        Returns:
            增强后的完整query
        """
        if not question or not state:
            return question

        enhanced = question.strip()

        # 1) 比较意图增强
        enhanced = self._enhance_comparison(enhanced, state)

        # 2) 追问意图增强
        enhanced = self._enhance_followup(enhanced, state)

        # 3) 省略主语增强
        enhanced = self._enhance_omitted_subject(enhanced, state)

        if enhanced != question:
            logger.debug("ContextEnhancer: '%s' → '%s'", question, enhanced)

        return enhanced

    # ---- 内部方法 ----

    def _build_context_prefix(self, state: ConversationState) -> str:
        """根据对话状态构建上下文前缀"""
        parts: List[str] = []
        if state.time_description:
            parts.append(state.time_description)
        if state.current_domain:
            parts.append(state.current_domain)
        if state.current_project:
            parts.append(state.current_project + "项目")
        if state.current_ecu:
            parts.append(state.current_ecu)
        if state.current_aida:
            parts.append(state.current_aida)
        return "".join(parts) if parts else ""

    def _enhance_comparison(self, question: str, state: ConversationState) -> str:
        """处理比较意图，注入时间/实体范围"""
        for pattern, comp_type in self.COMPARISON_PATTERNS:
            if pattern.search(question):
                # 已有明确时间范围则不再增强
                if state.time_description:
                    return question
                if comp_type == 'last_month':
                    return f"与上个月相比，{question}"
                elif comp_type == 'last_week':
                    return f"与上周相比，{question}"
                elif comp_type == 'last_year':
                    return f"与去年同期相比，{question}"
                elif comp_type == 'yoy':
                    return f"同比环比分析，{question}"
                else:
                    return question
        return question

    def _enhance_followup(self, question: str, state: ConversationState) -> str:
        """处理追问意图，追加上一轮上下文"""
        for pattern, followup_type in self.FOLLOWUP_PATTERNS:
            if pattern.search(question):
                if state.last_question and state.last_response_summary:
                    # 将追问转化为带有完整上下文的问题
                    ctx = self._build_context_prefix(state)
                    if ctx:
                        return f"{ctx}的{question}"
                elif state.last_question:
                    ctx = self._build_context_prefix(state)
                    if ctx:
                        return f"{ctx}的{question}"
                break
        return question

    def _enhance_omitted_subject(self, question: str, state: ConversationState) -> str:
        """处理省略主语的情况"""
        for pattern, _, suffix in self.SUBJECT_OMISSION_PATTERNS:
            if pattern.search(question):
                ctx = self._build_context_prefix(state)
                if ctx:
                    return f"{ctx}{question}"
        return question


# ---------------------------------------------------------------------------
# ClarificationLayer - 低置信度澄清
# ---------------------------------------------------------------------------

class ClarificationLayer:
    """
    澄清层 - 当语义意图置信度在 0.3-0.5 之间时，生成澄清问题

    用于消除用户 query 的歧义，帮助系统选择正确的处理路径。
    """

    # 意图 ↔ 中文标签映射（覆盖常见意图）
    INTENT_LABELS: Dict[str, str] = {
        'risk': '风险分析',
        'trend': '趋势分析',
        'comparison': '对比分析',
        'distribution': '分布分析',
        'detail': '详细信息',
        'coverage': '覆盖率分析',
        'defect': '缺陷查询',
        'test': '测试分析',
        'summary': '总体概况',
        'anomaly': '异常检测',
        'root_cause': '根因分析',
    }

    def generate_clarification(
        self,
        question: str,
        candidates: List[str],
    ) -> str:
        """
        生成澄清问题

        Args:
            question: 用户原始问题
            candidates: 候选意图列表

        Returns:
            澄清问题字符串
        """
        if not candidates:
            return f"请问您想了解关于哪方面的信息？"

        labels = []
        for c in candidates[:4]:
            labels.append(self.INTENT_LABELS.get(c, c))

        if len(labels) == 1:
            return f"您是想查询{labels[0]}相关的内容吗？"
        elif len(labels) == 2:
            return f"您是想查{labels[0]}，还是{labels[1]}？"
        else:
            options = "、".join(labels[:-1]) + f"，还是{labels[-1]}"
            return f"请问您是想查{options}？"

    def should_clarify(self, confidence: float) -> bool:
        """
        判断是否需要澄清

        Args:
            confidence: 意图识别置信度

        Returns:
            当置信度在 0.3-0.5 区间时返回 True
        """
        return 0.3 <= confidence <= 0.5


# ---------------------------------------------------------------------------
# ChartIntentDetector - 可视化意图检测
# ---------------------------------------------------------------------------

@dataclass
class ChartIntent:
    """图表意图"""
    chart_type: str           # trend / bar / pie / matrix
    x: Optional[str] = None   # X轴维度
    y: Optional[str] = None   # Y轴维度
    group_by: Optional[str] = None  # 分组维度


class ChartIntentDetector:
    """
    从用户 query 中检测可视化图表意图

    支持：
    - 趋势图 (trend): "趋势"、"变化"、"走势"
    - 柱状图 (bar): "对比"、"排名"、"top"
    - 饼图 (pie): "分布"、"占比"、"比例"
    - 矩阵图 (matrix): "矩阵"、"交叉"、"严重度矩阵"
    """

    # 图表类型关键词 → chart_type
    CHART_KEYWORDS: List[Tuple[str, List[str]]] = [
        ('trend', ['趋势', '走势', '变化', '曲线', '增长', '下降', '上升', '波动',
                    'trend', 'timeline', 'over time', '按周', '按月', '按天']),
        ('bar', ['对比', '比较', '排名', 'top', '排行', '谁多', '谁少', '最高',
                 '最低', 'compare', 'rank', 'bar', '柱状', '条形']),
        ('pie', ['分布', '占比', '比例', '百分比', '各占', '份额', '构成',
                 'distribution', 'proportion', 'share', 'pie', '饼']),
        ('matrix', ['矩阵', '交叉', '严重度矩阵', '二维', 'matrix', 'heatmap', '热力']),
    ]

    # 维度关键词映射
    DIMENSION_MAP: Dict[str, str] = {
        'ecu': 'target_ecu',
        '项目': 'project',
        'project': 'project',
        '严重度': 'severity',
        'severity': 'severity',
        '状态': 'status',
        'status': 'status_phase',
        '时间': 'created_date',
        '月份': 'month',
        '周': 'week',
        'domain': 'domain',
        '领域': 'domain',
        '测试人员': 'detected_by',
        'fv': 'fv',
        '功能车': 'fv',
    }

    def detect(self, question: str) -> Optional[ChartIntent]:
        """
        检测用户 query 中的可视化意图

        Args:
            question: 用户问题

        Returns:
            ChartIntent 或 None
        """
        if not question:
            return None

        q_lower = question.lower()

        # 匹配图表类型
        chart_type = self._match_chart_type(q_lower)
        if not chart_type:
            return None

        # 检测维度
        x, y, group_by = self._detect_dimensions(question)

        return ChartIntent(
            chart_type=chart_type,
            x=x,
            y=y,
            group_by=group_by,
        )

    def _match_chart_type(self, q_lower: str) -> Optional[str]:
        """匹配图表类型"""
        best_type: Optional[str] = None
        best_count = 0
        for ctype, keywords in self.CHART_KEYWORDS:
            count = sum(1 for kw in keywords if kw in q_lower)
            if count > best_count:
                best_count = count
                best_type = ctype
        return best_type

    def _detect_dimensions(
        self, question: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """从问题中提取 x / y / group_by 维度"""
        x: Optional[str] = None
        y: Optional[str] = None
        group_by: Optional[str] = None

        found_dims: List[str] = []
        for keyword, field_name in self.DIMENSION_MAP.items():
            if keyword in question:
                found_dims.append(field_name)

        if len(found_dims) >= 1:
            x = found_dims[0]
        if len(found_dims) >= 2:
            group_by = found_dims[1]
        if len(found_dims) >= 3:
            y = found_dims[2]

        return x, y, group_by


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_context_enhancer() -> ContextEnhancer:
    """创建对话上下文增强器实例"""
    return ContextEnhancer()


def create_clarification_layer() -> ClarificationLayer:
    """创建澄清层实例"""
    return ClarificationLayer()


def create_chart_intent_detector() -> ChartIntentDetector:
    """创建图表意图检测器实例"""
    return ChartIntentDetector()


# ---------------------------------------------------------------------------
# 测试代码
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    print("=" * 60)
    print("Conversation Context Enhancer - 测试")
    print("=" * 60)

    # ---- ContextEnhancer 测试 ----
    print("\n[1] ContextEnhancer 测试")
    print("-" * 40)

    enhancer = create_context_enhancer()
    state = ConversationState(
        current_project="G01",
        current_domain="座舱",
        time_description="上个月",
        last_intent="risk",
        last_question="G01座舱上个月的风险分析",
        last_response_summary="G01座舱上月共发现23个缺陷...",
        turn_count=3,
    )

    tests = [
        "其中哪个ECU最多",
        "为什么",
        "和上月比怎么样",
        "有多少个严重缺陷",
        "分布情况",
        "怎么处理",
    ]
    for q in tests:
        result = enhancer.enhance_query(q, state)
        print(f"  Q: {q}")
        print(f"  → {result}")
        print()

    # ---- ClarificationLayer 测试 ----
    print("\n[2] ClarificationLayer 测试")
    print("-" * 40)

    clarifier = create_clarification_layer()
    print(f"  should_clarify(0.4): {clarifier.should_clarify(0.4)}")
    print(f"  should_clarify(0.8): {clarifier.should_clarify(0.8)}")
    print(f"  澄清问题: {clarifier.generate_clarification('座舱缺陷', ['trend', 'distribution'])}")
    print(f"  单候选拟: {clarifier.generate_clarification('缺陷', ['risk'])}")
    print(f"  多候选拟: {clarifier.generate_clarification('分析', ['risk', 'trend', 'comparison', 'distribution'])}")

    # ---- ChartIntentDetector 测试 ----
    print("\n[3] ChartIntentDetector 测试")
    print("-" * 40)

    detector = create_chart_intent_detector()
    chart_tests = [
        "座舱缺陷的月度趋势",
        "各ECU的缺陷排名",
        "缺陷按严重度的分布占比",
        "严重度矩阵",
        "今天天气不错",  # 无意图
    ]
    for q in chart_tests:
        intent = detector.detect(q)
        print(f"  Q: {q}")
        if intent:
            print(f"  → chart_type={intent.chart_type}, x={intent.x}, y={intent.y}, group_by={intent.group_by}")
        else:
            print(f"  → None")
        print()

    print("测试完成!")

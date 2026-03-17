"""
Conversation Entity Tracker - 多轮对话实体追踪

Features:
1. Multi-turn conversation state management
2. Entity extraction and tracking
3. Pronoun resolution (指代消解)
4. Context-aware entity reference resolution

Author: AI Assistant
Date: 2025-02-21
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class ConversationState:
    """
    对话状态 - 追踪多轮对话中的关键信息
    """
    # 当前聚焦的实体
    current_project: Optional[str] = None
    current_aida: Optional[str] = None
    current_tester: Optional[str] = None
    current_ecu: Optional[str] = None
    current_fv: Optional[str] = None
    current_domain: Optional[str] = None

    # 时间范围
    time_range: Optional[Tuple[str, str]] = None
    time_description: Optional[str] = None

    # 历史提及的实体
    mentioned_entities: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))

    # 对话上下文
    last_intent: Optional[str] = None
    last_tools_used: List[str] = field(default_factory=list)
    last_question: Optional[str] = None
    last_response_summary: Optional[str] = None

    # 对话元数据
    turn_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于JSON序列化）"""
        return {
            'current_project': self.current_project,
            'current_aida': self.current_aida,
            'current_tester': self.current_tester,
            'current_ecu': self.current_ecu,
            'current_fv': self.current_fv,
            'current_domain': self.current_domain,
            'time_range': self.time_range,
            'time_description': self.time_description,
            'mentioned_entities': dict(self.mentioned_entities),
            'last_intent': self.last_intent,
            'last_tools_used': self.last_tools_used,
            'last_question': self.last_question,
            'last_response_summary': self.last_response_summary,
            'turn_count': self.turn_count,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationState':
        """从字典创建实例"""
        state = cls()
        if not data:
            return state

        state.current_project = data.get('current_project')
        state.current_aida = data.get('current_aida')
        state.current_tester = data.get('current_tester')
        state.current_ecu = data.get('current_ecu')
        state.current_fv = data.get('current_fv')
        state.current_domain = data.get('current_domain')
        state.time_range = tuple(data['time_range']) if data.get('time_range') else None
        state.time_description = data.get('time_description')
        state.mentioned_entities = defaultdict(list, data.get('mentioned_entities', {}))
        state.last_intent = data.get('last_intent')
        state.last_tools_used = data.get('last_tools_used', [])
        state.last_question = data.get('last_question')
        state.last_response_summary = data.get('last_response_summary')
        state.turn_count = data.get('turn_count', 0)
        state.created_at = data.get('created_at', datetime.now().isoformat())
        state.updated_at = data.get('updated_at', datetime.now().isoformat())
        return state


class ConversationEntityTracker:
    """
    对话实体追踪器

    负责：
    1. 从问题中提取新实体
    2. 指代消解（将"它"、"该项目"等替换为具体实体）
    3. 维护对话状态
    4. 检测实体变化
    """

    # 指代词映射
    PRONOUN_PATTERNS = {
        'project': ['它', '该项目', '这个project', '此项目', '这个项目', '该project', '它'],
        'aida': ['该aida', '这个aida', '此aida', '该测试项'],
        'ecu': ['该ecu', '这个ecu', '此ecu'],
        'tester': ['该tester', '这个tester', '该测试人员', '他', '她'],
        'domain': ['该domain', '这个domain', '该领域', '此领域']
    }

    # 时间表达式
    TIME_PATTERNS = {
        'today': ['今天', '今日', 'today'],
        'this_week': ['本周', '这周', '最近一周', 'this week', 'last 7 days'],
        'last_week': ['上周', '上星期', 'last week'],
        'this_month': ['本月', '这个月', '最近一个月', 'this month', 'last 30 days'],
        'last_month': ['上月', '上个月', 'last month'],
        'recent': ['最近', '近期', 'recently', 'lately', '最近几天'],
        'all_time': ['全部', '所有', 'overall', 'all time', '历史']
    }

    def __init__(self):
        self.entity_patterns = self._compile_entity_patterns()

    def _compile_entity_patterns(self) -> Dict[str, re.Pattern]:
        """编译实体提取正则表达式"""
        return {
            'project': re.compile(r'\b([GFIU]\d{2,3}[a-z]?)\b', re.IGNORECASE),
            'ecu': re.compile(r'\b(ECU[_-]?[A-Z0-9]+|[A-Z]{2,6}_ECU)\b', re.IGNORECASE),
            'aida': re.compile(r'\b([A-Z]{2,8}_\d{4,6}|AIDA[_-]?\w+)\b', re.IGNORECASE),
            'fv': re.compile(r'\b(FV[_-]?[A-Z0-9]+|Feature[_-]?Vehicle[_-]?\w+)\b', re.IGNORECASE),
            'domain': re.compile(r'\b(DP|EE|SW|HW|ME|NW|AS|HU|IC|BC)\b', re.IGNORECASE),
            'tester': re.compile(r' tester[:：]?\s*(\w+)', re.IGNORECASE)
        }

    def resolve_references(self, question: str, state: ConversationState) -> str:
        """
        指代消解 - 将代词替换为具体实体

        Args:
            question: 用户原始问题
            state: 当前对话状态

        Returns:
            消解后的新问题
        """
        if not question or not state:
            return question

        resolved = question
        resolved_any = False

        # 检测是否包含指代词
        for entity_type, pronouns in self.PRONOUN_PATTERNS.items():
            for pronoun in pronouns:
                if pronoun in question:
                    # 获取当前实体
                    current = getattr(state, f'current_{entity_type}', None)
                    if current:
                        # 替换指代词
                        resolved = resolved.replace(pronoun, current)
                        resolved_any = True
                        logger.debug(f"Resolved '{pronoun}' to '{current}'")
                        break

        # 特殊处理：如果问题以"呢？"、"如何？"等结尾，且前面有指代词
        if not resolved_any and len(question) < 20:
            # 短问题可能是跟进问题
            follow_up_patterns = [
                (r'^(那|那么)?[它該该此这]+[个項目项目]呢？?$', 'project'),
                (r'^(那|那么)？?[呢?？]+$', 'general')
            ]
            for pattern, entity_type in follow_up_patterns:
                if re.match(pattern, question.strip()):
                    if entity_type == 'project' and state.current_project:
                        resolved = f"{state.current_project}项目情况如何？"
                    elif state.last_question:
                        # 重复上一个问题
                        resolved = state.last_question
                    break

        return resolved

    def extract_new_entities(self, question: str) -> Dict[str, List[str]]:
        """
        从问题中提取新实体

        Args:
            question: 用户问题

        Returns:
            Dictionary of entity_type -> list of entities
        """
        entities = defaultdict(list)

        if not question:
            return dict(entities)

        for entity_type, pattern in self.entity_patterns.items():
            matches = pattern.findall(question)
            if matches:
                # 去重并标准化
                unique_matches = []
                seen = set()
                for m in matches:
                    key = str(m).upper().strip()
                    if key and key not in seen:
                        seen.add(key)
                        unique_matches.append(str(m).strip())
                entities[entity_type] = unique_matches

        # 提取时间表达式
        time_entities = self._extract_time_expressions(question)
        if time_entities:
            entities['time'] = time_entities

        return dict(entities)

    def _extract_time_expressions(self, question: str) -> List[str]:
        """提取时间表达式"""
        found_times = []
        question_lower = question.lower()

        for time_type, expressions in self.TIME_PATTERNS.items():
            for expr in expressions:
                if expr in question or expr in question_lower:
                    found_times.append(time_type)
                    break

        return found_times

    def update_state(self, state: ConversationState, question: str,
                     intent: Optional[str] = None,
                     tools_used: Optional[List[str]] = None,
                     response_summary: Optional[str] = None) -> ConversationState:
        """
        更新对话状态

        Args:
            state: 当前状态
            question: 用户问题（已消解）
            intent: 检测到的意图
            tools_used: 使用的工具列表
            response_summary: 回答摘要

        Returns:
            更新后的状态
        """
        if state is None:
            state = ConversationState()

        # 提取新实体
        new_entities = self.extract_new_entities(question)

        # 更新当前实体
        entity_mapping = {
            'project': 'current_project',
            'aida': 'current_aida',
            'ecu': 'current_ecu',
            'tester': 'current_tester',
            'fv': 'current_fv',
            'domain': 'current_domain'
        }

        for entity_type, attr_name in entity_mapping.items():
            if entity_type in new_entities and new_entities[entity_type]:
                # 更新当前实体（取第一个）
                new_value = new_entities[entity_type][0]
                old_value = getattr(state, attr_name)

                if new_value != old_value:
                    # 实体发生变化，记录到历史
                    if old_value:
                        state.mentioned_entities[entity_type].append(old_value)
                    setattr(state, attr_name, new_value)
                    logger.debug(f"Updated {attr_name}: {old_value} -> {new_value}")

        # 更新时间
        if 'time' in new_entities:
            state.time_description = new_entities['time'][0]

        # 更新意图和工具
        if intent:
            state.last_intent = intent
        if tools_used:
            state.last_tools_used = tools_used

        # 更新对话历史
        state.last_question = question
        if response_summary:
            state.last_response_summary = response_summary

        state.turn_count += 1
        state.updated_at = datetime.now().isoformat()

        return state

    def get_context_summary(self, state: ConversationState) -> str:
        """
        生成上下文摘要（用于AI提示）

        Args:
            state: 对话状态

        Returns:
            上下文摘要字符串
        """
        if not state or state.turn_count == 0:
            return ""

        parts = []

        # 当前聚焦
        focus_parts = []
        if state.current_project:
            focus_parts.append(f"项目={state.current_project}")
        if state.current_aida:
            focus_parts.append(f"AIDA={state.current_aida}")
        if state.current_tester:
            focus_parts.append(f"测试人员={state.current_tester}")
        if state.current_ecu:
            focus_parts.append(f"ECU={state.current_ecu}")

        if focus_parts:
            parts.append(f"当前聚焦: {', '.join(focus_parts)}")

        # 时间范围
        if state.time_description:
            parts.append(f"时间范围: {state.time_description}")

        # 上一步操作
        if state.last_intent:
            parts.append(f"上一步意图: {state.last_intent}")

        # 历史提及（最近的）
        history_parts = []
        for entity_type, entities in state.mentioned_entities.items():
            if entities:
                recent = entities[-3:]  # 最近3个
                history_parts.append(f"{entity_type}: {', '.join(recent)}")

        if history_parts:
            parts.append(f"历史提及: {'; '.join(history_parts)}")

        return "\n".join(parts)

    def detect_context_switch(self, state: ConversationState, question: str) -> bool:
        """
        检测是否发生上下文切换

        Args:
            state: 当前状态
            question: 新问题

        Returns:
            True if context switch detected
        """
        if not state or state.turn_count == 0:
            return False

        new_entities = self.extract_new_entities(question)

        # 检查是否有新实体与当前实体冲突
        entity_mapping = {
            'project': 'current_project',
            'aida': 'current_aida',
            'ecu': 'current_ecu',
            'tester': 'current_tester'
        }

        for entity_type, attr_name in entity_mapping.items():
            if entity_type in new_entities and new_entities[entity_type]:
                new_val = new_entities[entity_type][0]
                current_val = getattr(state, attr_name)
                if current_val and new_val != current_val:
                    logger.debug(f"Context switch detected: {attr_name} {current_val} -> {new_val}")
                    return True

        return False

    def generate_follow_up_suggestions(self, state: ConversationState) -> List[str]:
        """
        生成跟进问题建议

        Args:
            state: 对话状态

        Returns:
            建议问题列表
        """
        if not state or state.turn_count == 0:
            return []

        suggestions = []

        # 基于当前实体的建议
        if state.current_project:
            suggestions.append(f"{state.current_project}的风险分布如何？")
            suggestions.append(f"{state.current_project}和整体平均水平对比？")

        if state.current_aida:
            suggestions.append(f"{state.current_aida}的历史趋势？")

        # 基于上一步意图的建议
        if state.last_intent == 'risk':
            suggestions.append("这些风险问题的处理进展？")
        elif state.last_intent == 'trend':
            suggestions.append("趋势变化的原因是什么？")
        elif state.last_intent == 'comparison':
            suggestions.append("这些差异的根本原因？")

        # 去重并限制数量
        seen = set()
        unique = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique.append(s)
                if len(unique) >= 3:
                    break

        return unique


# 工厂函数
def create_conversation_entity_tracker() -> ConversationEntityTracker:
    """创建对话实体追踪器实例"""
    return ConversationEntityTracker()


def create_initial_conversation_state() -> ConversationState:
    """创建初始对话状态"""
    return ConversationState()


# 测试代码
if __name__ == "__main__":
    print("Conversation Entity Tracker Test")
    print("=" * 50)

    tracker = create_conversation_entity_tracker()
    state = create_initial_conversation_state()

    # 模拟对话
    dialog = [
        ("G01项目的风险如何？", "risk"),
        ("那它的测试覆盖率呢？", "test"),  # "它"应该被消解为G01
        ("和G20对比一下", "comparison"),  # 上下文切换到G20
        ("该项目的严重缺陷有多少？", "risk"),  # "该项目"应该被消解为G20
    ]

    for question, intent in dialog:
        print(f"\n用户: {question}")

        # 指代消解
        resolved = tracker.resolve_references(question, state)
        if resolved != question:
            print(f"  消解后: {resolved}")

        # 提取实体
        entities = tracker.extract_new_entities(resolved)
        if entities:
            print(f"  提取实体: {entities}")

        # 更新状态
        state = tracker.update_state(state, resolved, intent=intent)

        # 显示当前状态
        print(f"  当前项目: {state.current_project}")
        print(f"  对话轮数: {state.turn_count}")

    print("\n" + "=" * 50)
    print("上下文摘要:")
    print(tracker.get_context_summary(state))

    print("\n跟进建议:")
    for suggestion in tracker.generate_follow_up_suggestions(state):
        print(f"  - {suggestion}")

    print("\n测试完成!")

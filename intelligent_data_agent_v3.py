#!/usr/bin/env python3
"""
智能数据分析 Agent v3.0

核心特性：
1. 深度数据理解 - 理解测试执行和缺陷数据的业务语义
2. 多维度分析 - 趋势、对比、关联、风险评估
3. 主动洞察 - 自动发现隐藏问题
4. 自然语言交互 - 支持复杂的自然语言查询

与 Mission Control Center 集成：
- 可作为独立 Agent 运行
- 可与其他 Agent 协作（缺陷分析师、测试分析师、风险评估师）

作者: AI Assistant (Mission Control Center 多 Agent 协作优化)
日期: 2026-03-19
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field, asdict
from enum import Enum

# 添加 database 目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.enhanced_data_understanding import (
    EnhancedDataUnderstanding,
    QueryIntent,
    AnalysisResult,
    DataInsight,
    IntentType
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# Agent 配置
# ============================================================================

@dataclass
class AgentConfig:
    """Agent 配置"""
    name: str = "智能数据分析Agent"
    version: str = "3.0.0"
    db_path: str = "database/local_data.db"
    # 智谱 AI 模型 - 优先从 config_center 读取
    model: str = None  # 将在 __init__ 或类方法中初始化
    max_context_tokens: int = 4000
    enable_insights: bool = True
    enable_recommendations: bool = True
    verbose: bool = True

    @classmethod
    def get_model(cls) -> str:
        """获取模型名称，优先从 config_center 读取"""
        if cls.model is None:
            try:
                from config_center import cfg
                cls.model = cfg.ZHIPU_MODEL
            except ImportError:
                cls.model = "glm-4.7"  # 默认值
        return cls.model


@dataclass
class AgentContext:
    """Agent 上下文"""
    session_id: str = ""
    user_id: str = ""
    conversation_history: List[Dict] = field(default_factory=list)
    current_intent: Optional[QueryIntent] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResponse:
    """Agent 响应"""
    success: bool
    content: str
    data: Any = None
    insights: List[DataInsight] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    confidence: float = 1.0
    execution_time_ms: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 智能数据分析 Agent
# ============================================================================

class IntelligentDataAgent:
    """
    智能数据分析 Agent
    
    能力：
    1. 数据理解：理解测试执行和缺陷数据的业务语义
    2. 意图识别：识别用户问题的统计、分析、建议意图
    3. 洞察生成：自动发现数据中的异常和模式
    4. 建议生成：基于分析结果提供可执行的建议
    """
    
    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig()
        self.data_engine = EnhancedDataUnderstanding(self.config.db_path)
        self.context = AgentContext()
        self.name = self.config.name
        self.version = self.config.version
        
        logger.info(f"✅ {self.name} v{self.version} 初始化完成")
    
    # ========================================================================
    # 核心 API
    # ========================================================================
    
    def chat(self, message: str, context: AgentContext = None) -> AgentResponse:
        """
        对话式交互
        
        Args:
            message: 用户消息
            context: 对话上下文（可选）
        
        Returns:
            AgentResponse: Agent 响应
        """
        start_time = datetime.now()
        
        if context:
            self.context = context
        
        try:
            # Step 1: 理解意图
            intent = self.data_engine.understand_intent(message)
            self.context.current_intent = intent
            
            if self.config.verbose:
                logger.info(f"📝 意图识别: {intent.intent_type.value} (置信度: {intent.confidence:.2f})")
            
            # Step 2: 执行分析
            result = self.data_engine.execute_analysis(intent)
            
            if self.config.verbose:
                logger.info(f"🔍 分析完成: {result.message} (耗时: {result.execution_time_ms:.0f}ms)")
            
            # Step 3: 生成响应
            response = self._generate_response(result, intent)
            
            # Step 4: 添加建议（如果启用）
            if self.config.enable_recommendations:
                response.recommendations = self._generate_recommendations(result, intent)
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            response.execution_time_ms = execution_time
            
            # 记录对话历史
            self.context.conversation_history.append({
                "role": "user",
                "content": message,
                "timestamp": datetime.now().isoformat()
            })
            self.context.conversation_history.append({
                "role": "agent",
                "content": response.content,
                "timestamp": datetime.now().isoformat()
            })
            
            return response
            
        except Exception as e:
            logger.error(f"处理消息失败: {e}")
            return AgentResponse(
                success=False,
                content=f"处理失败: {str(e)}",
                confidence=0.0
            )
    
    def analyze(self, question: str) -> Dict[str, Any]:
        """
        分析接口（返回结构化数据）
        
        Args:
            question: 分析问题
        
        Returns:
            Dict: 结构化分析结果
        """
        response = self.chat(question)
        return {
            "success": response.success,
            "content": response.content,
            "data": response.data,
            "insights": [asdict(i) for i in response.insights],
            "recommendations": response.recommendations,
            "confidence": response.confidence,
            "execution_time_ms": response.execution_time_ms
        }
    
    def get_insights(self, domain: str = "all") -> List[DataInsight]:
        """
        获取洞察
        
        Args:
            domain: 数据域（test/defect/all）
        
        Returns:
            List[DataInsight]: 洞察列表
        """
        intent = QueryIntent(
            intent_type=IntentType.INSIGHT,
            domain=domain,
            original_question="给我一些洞察"
        )
        result = self.data_engine.execute_analysis(intent)
        return result.insights
    
    def get_risk_assessment(self, project: str = None, module: str = None) -> Dict[str, Any]:
        """
        获取风险评估
        
        Args:
            project: 项目名称（可选）
            module: 模块名称（可选）
        
        Returns:
            Dict: 风险评估结果
        """
        filters = {}
        if project:
            filters["project"] = project
        if module:
            filters["module"] = module
        
        intent = QueryIntent(
            intent_type=IntentType.RISK_ASSESSMENT,
            domain="both",
            filters=filters,
            original_question="风险评估"
        )
        result = self.data_engine.execute_analysis(intent)
        return {
            "success": result.success,
            "data": result.data,
            "insights": [asdict(i) for i in result.insights]
        }
    
    def get_test_summary(self, time_range: str = None) -> Dict[str, Any]:
        """
        获取测试概览
        
        Args:
            time_range: 时间范围（如 "本周"、"上周"、"本月"）
        
        Returns:
            Dict: 测试概览
        """
        question = f"{time_range}的测试概览" if time_range else "测试概览"
        return self.analyze(question)
    
    def get_defect_summary(self, severity: str = None, status: str = None) -> Dict[str, Any]:
        """
        获取缺陷概览
        
        Args:
            severity: 严重程度（Critical/Major/Medium/Minor）
            status: 状态（Open/Closed/In Progress）
        
        Returns:
            Dict: 缺陷概览
        """
        question = "缺陷概览"
        if severity:
            question = f"{severity}级别的缺陷统计"
        if status:
            question = f"{status}状态的缺陷统计"
        return self.analyze(question)
    
    # ========================================================================
    # 内部方法
    # ========================================================================
    
    def _generate_response(self, result: AnalysisResult, intent: QueryIntent) -> AgentResponse:
        """生成响应"""
        content = self._format_content(result, intent)
        
        return AgentResponse(
            success=result.success,
            content=content,
            data=result.data,
            insights=result.insights,
            confidence=result.success and 1.0 or 0.0,
            metadata={
                "intent_type": intent.intent_type.value,
                "domain": intent.domain,
                "sql": result.sql
            }
        )
    
    def _format_content(self, result: AnalysisResult, intent: QueryIntent) -> str:
        """格式化响应内容"""
        lines = []
        
        # 标题
        intent_titles = {
            IntentType.COUNT: "📊 数量统计",
            IntentType.PASS_RATE: "📈 通过率分析",
            IntentType.DEFECT_DENSITY: "📉 缺陷密度分析",
            IntentType.LIST_TESTS: "📋 测试列表",
            IntentType.LIST_DEFECTS: "📋 缺陷列表",
            IntentType.TREND_TEST: "📊 测试趋势",
            IntentType.TREND_DEFECT: "📊 缺陷趋势",
            IntentType.ROOT_CAUSE: "🔍 根因分析",
            IntentType.CORRELATION: "🔗 关联分析",
            IntentType.RISK_ASSESSMENT: "⚠️ 风险评估",
            IntentType.COMPARISON: "📊 对比分析",
            IntentType.TEST_STRATEGY: "💡 测试策略建议",
            IntentType.INSIGHT: "💡 洞察发现",
            IntentType.OVERVIEW: "📊 综合概览"
        }
        
        lines.append(f"## {intent_titles.get(intent.intent_type, '📊 分析结果')}")
        lines.append("")
        
        if result.success:
            # 摘要
            lines.append(f"*{result.message}*")
            lines.append("")
            
            # 数据
            if result.data:
                if isinstance(result.data, dict):
                    self._format_dict_data(result.data, lines)
                elif isinstance(result.data, list) and result.data:
                    self._format_list_data(result.data, lines)
            
            # 洞察
            if result.insights:
                lines.append("")
                lines.append("### 💡 洞察")
                for insight in result.insights:
                    severity_emoji = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}
                    lines.append(f"\n{severity_emoji.get(insight.severity, '📌')} **{insight.title}**")
                    lines.append(f"   {insight.description}")
        else:
            lines.append(f"❌ 分析失败: {result.message}")
        
        return "\n".join(lines)
    
    def _format_dict_data(self, data: Dict, lines: List[str]):
        """格式化字典数据"""
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"### {key}")
                for k, v in value.items():
                    lines.append(f"- **{k}**: {v}")
                lines.append("")
            else:
                lines.append(f"- **{key}**: {value}")
    
    def _format_list_data(self, data: List, lines: List[str]):
        """格式化列表数据"""
        if not data:
            return
        
        # 获取列名
        if isinstance(data[0], dict):
            columns = list(data[0].keys())
        else:
            columns = ["value"]
        
        # 表头
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
        
        # 数据行
        for row in data[:15]:
            if isinstance(row, dict):
                lines.append("| " + " | ".join(str(v) if v is not None else "-" for v in row.values()) + " |")
            else:
                lines.append(f"| {row} |")
        
        if len(data) > 15:
            lines.append(f"\n*...共 {len(data)} 条记录*")
    
    def _generate_recommendations(self, result: AnalysisResult, intent: QueryIntent) -> List[str]:
        """生成建议"""
        recommendations = []
        
        # 基于洞察生成建议
        for insight in result.insights:
            if insight.insight_type == "low_pass_rate":
                recommendations.append(f"建议对 {insight.related_data.get('module', '相关模块')} 增加测试覆盖")
            elif insight.insight_type == "critical_defect":
                recommendations.append("建议立即处理 Critical 缺陷，优先级最高")
            elif insight.insight_type == "high_defect_density":
                recommendations.append("建议进行代码审查和增加自动化测试")
            elif insight.insight_type == "low_fix_efficiency":
                recommendations.append("建议优化缺陷修复流程，减少往返次数")
        
        # 基于意图生成建议
        if intent.intent_type == IntentType.RISK_ASSESSMENT:
            recommendations.append("建议制定风险缓解计划")
            recommendations.append("建议增加高风险模块的测试资源")
        
        return list(set(recommendations))  # 去重
    
    # ========================================================================
    # 工具方法
    # ========================================================================
    
    def get_schema(self) -> Dict[str, Any]:
        """获取数据 Schema"""
        return self.data_engine.schema_cache
    
    def get_capabilities(self) -> List[str]:
        """获取 Agent 能力列表"""
        return [
            "📊 测试数据统计分析",
            "📉 缺陷数据统计分析",
            "📈 趋势分析（测试/缺陷）",
            "🔗 关联分析（测试失败与缺陷）",
            "⚠️ 风险评估",
            "💡 洞察发现",
            "📋 建议生成",
            "💬 自然语言交互"
        ]
    
    def close(self):
        """关闭 Agent"""
        self.data_engine.close()
        logger.info(f"👋 {self.name} 已关闭")


# ============================================================================
# CLI 接口
# ============================================================================

def main():
    """命令行接口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="智能数据分析 Agent v3.0")
    parser.add_argument("--db", type=str, default="database/local_data.db", help="数据库路径")
    parser.add_argument("--question", type=str, help="问题")
    parser.add_argument("--interactive", action="store_true", help="交互模式")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    
    args = parser.parse_args()
    
    # 创建 Agent
    config = AgentConfig(db_path=args.db)
    agent = IntelligentDataAgent(config)
    
    if args.interactive:
        # 交互模式
        print("\n" + "="*60)
        print(f"  {agent.name} v{agent.version}")
        print("="*60)
        print("\n能力：")
        for cap in agent.get_capabilities():
            print(f"  {cap}")
        print("\n输入问题开始对话，输入 'quit' 退出")
        print("-"*60 + "\n")
        
        while True:
            try:
                question = input("❓ 你: ").strip()
                if question.lower() in ["quit", "exit", "q"]:
                    print("\n👋 再见！")
                    break
                if not question:
                    continue
                
                response = agent.chat(question)
                print(f"\n🤖 Agent:\n{response.content}")
                if response.recommendations:
                    print("\n💡 建议：")
                    for rec in response.recommendations:
                        print(f"   - {rec}")
                print("\n" + "-"*60 + "\n")
                
            except KeyboardInterrupt:
                print("\n\n👋 再见！")
                break
    
    elif args.question:
        # 单次查询
        response = agent.chat(args.question)
        if args.json:
            print(json.dumps({
                "success": response.success,
                "content": response.content,
                "data": response.data,
                "insights": [asdict(i) for i in response.insights],
                "recommendations": response.recommendations
            }, indent=2, ensure_ascii=False, default=str))
        else:
            print(response.content)
            if response.recommendations:
                print("\n💡 建议：")
                for rec in response.recommendations:
                    print(f"   - {rec}")
    
    else:
        # 演示模式
        print("\n" + "="*60)
        print(f"  {agent.name} v{agent.version} - 演示模式")
        print("="*60)
        
        questions = [
            "测试通过率是多少?",
            "最近的缺陷趋势如何?",
            "哪些模块风险最高?",
            "给我一些洞察"
        ]
        
        for q in questions:
            print(f"\n❓ 问题: {q}")
            print("-"*60)
            response = agent.chat(q)
            print(response.content)
            print()
    
    agent.close()


if __name__ == "__main__":
    main()

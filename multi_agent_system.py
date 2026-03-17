"""
多 Agent 协作系统

实现类似 OpenAI Agents SDK 的多 Agent 协作架构：
- CoordinatorAgent: 协调者，负责任务分配和结果整合
- DefectAnalyst: 缺陷分析专家
- TestAnalyst: 测试分析专家
- RiskAssessor: 风险评估专家
- StrategyAdvisor: 策略顾问

核心机制：
- Handoffs: Agent 之间的任务交接
- Tools: 每个 Agent 的专属工具
- Context: 共享上下文

作者: AI Assistant
日期: 2025-01-19
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Union, Callable, Type
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================================
# 数据类
# ============================================================================

class AgentRole(Enum):
    """Agent 角色枚举"""
    COORDINATOR = "coordinator"
    DEFECT_ANALYST = "defect_analyst"
    TEST_ANALYST = "test_analyst"
    RISK_ASSESSOR = "risk_assessor"
    STRATEGY_ADVISOR = "strategy_advisor"


@dataclass
class AgentContext:
    """Agent 上下文"""
    question: str
    data: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict] = field(default_factory=list)
    intent: Optional[Dict] = None


@dataclass
class AgentResult:
    """Agent 执行结果"""
    agent_name: str
    success: bool
    output: Any
    confidence: float = 1.0
    reasoning: str = ""
    next_agent: Optional[str] = None  # Handoff
    tools_used: List[str] = field(default_factory=list)
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Handoff:
    """任务交接"""
    from_agent: str
    to_agent: str
    context: AgentContext
    reason: str


# ============================================================================
# 基础 Agent 类
# ============================================================================

class BaseAgent:
    """基础 Agent 类"""
    
    name: str = "base_agent"
    role: AgentRole = AgentRole.COORDINATOR
    description: str = "基础 Agent"
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self._register_tools()
    
    def _register_tools(self):
        """注册工具（子类实现）"""
        pass
    
    def run(self, context: AgentContext) -> AgentResult:
        """执行任务"""
        raise NotImplementedError
    
    def handoff_to(self, target_agent: str, context: AgentContext, reason: str) -> Handoff:
        """交接任务给其他 Agent"""
        return Handoff(
            from_agent=self.name,
            to_agent=target_agent,
            context=context,
            reason=reason
        )


# ============================================================================
# 专业 Agent 实现
# ============================================================================

class DefectAnalyst(BaseAgent):
    """缺陷分析专家"""
    
    name = "defect_analyst"
    role = AgentRole.DEFECT_ANALYST
    description = "专注于缺陷数据分析，包括趋势、分布、严重性等"
    
    def _register_tools(self):
        """注册缺陷分析工具"""
        self.tools = {
            "analyze_defect_trend": self._analyze_trend,
            "analyze_defect_distribution": self._analyze_distribution,
            "find_high_severity_defects": self._find_high_severity,
            "analyze_defect_by_project": self._analyze_by_project,
        }
    
    def run(self, context: AgentContext) -> AgentResult:
        """执行缺陷分析"""
        start_time = datetime.now()
        
        if context.data is None or (isinstance(context.data, pd.DataFrame) and context.data.empty):
            return AgentResult(
                agent_name=self.name,
                success=False,
                output="没有可用的缺陷数据",
                confidence=0.0
            )
        
        df = context.data
        results = {}
        tools_used = []
        
        # 分析趋势
        if "趋势" in context.question or "trend" in context.question.lower():
            results["trend"] = self.tools["analyze_defect_trend"](df)
            tools_used.append("analyze_defect_trend")
        
        # 分析分布
        if "分布" in context.question or "distribution" in context.question.lower():
            results["distribution"] = self.tools["analyze_defect_distribution"](df)
            tools_used.append("analyze_defect_distribution")
        
        # 查找高风险
        if "风险" in context.question or "高风险" in context.question or "risk" in context.question.lower():
            results["high_risk"] = self.tools["find_high_severity_defects"](df)
            tools_used.append("find_high_severity_defects")
        
        # 如果没有特定分析，执行全面分析
        if not results:
            results["overview"] = {
                "total": len(df),
                "columns": list(df.columns),
                "sample": df.head(5).to_dict('records') if len(df) > 0 else []
            }
            tools_used.append("overview")
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=results,
            confidence=0.9,
            reasoning=f"完成了 {len(tools_used)} 项缺陷分析",
            tools_used=tools_used,
            execution_time=execution_time
        )
    
    def _analyze_trend(self, df: pd.DataFrame) -> Dict:
        """分析缺陷趋势"""
        if 'tcreationtime' in df.columns:
            df = df.copy()
            df['tcreationtime'] = pd.to_datetime(df['tcreationtime'], errors='coerce')
            trend = df.groupby(df['tcreationtime'].dt.to_period('W')).size()
            return {
                "direction": "上升" if trend.iloc[-1] > trend.iloc[0] else "下降",
                "weekly_counts": trend.to_dict()
            }
        return {"message": "缺少时间字段"}
    
    def _analyze_distribution(self, df: pd.DataFrame) -> Dict:
        """分析缺陷分布"""
        distribution = {}
        
        for col in ['tproject', 'severity_group', 'pu', 'aida']:
            if col in df.columns:
                distribution[col] = df[col].value_counts().head(10).to_dict()
        
        return distribution
    
    def _find_high_severity(self, df: pd.DataFrame) -> Dict:
        """查找高风险缺陷"""
        high_severity = df[df['severity_group'].isin(['致命', '严重', 'Critical', 'High'])] if 'severity_group' in df.columns else df
        
        return {
            "count": len(high_severity),
            "top_projects": high_severity['tproject'].value_counts().head(5).to_dict() if 'tproject' in high_severity.columns else {}
        }
    
    def _analyze_by_project(self, df: pd.DataFrame) -> Dict:
        """按项目分析"""
        if 'tproject' not in df.columns:
            return {"message": "缺少项目字段"}
        
        return df.groupby('tproject').agg({
            'id': 'count',
            'severity_group': lambda x: x.value_counts().to_dict() if 'severity_group' in df.columns else {}
        }).to_dict()


class TestAnalyst(BaseAgent):
    """测试分析专家"""
    
    name = "test_analyst"
    role = AgentRole.TEST_ANALYST
    description = "专注于测试数据分析，包括覆盖率、通过率、效率等"
    
    def _register_tools(self):
        """注册测试分析工具"""
        self.tools = {
            "analyze_test_coverage": self._analyze_coverage,
            "analyze_pass_rate": self._analyze_pass_rate,
            "analyze_test_efficiency": self._analyze_efficiency,
            "find_failed_tests": self._find_failed,
        }
    
    def run(self, context: AgentContext) -> AgentResult:
        """执行测试分析"""
        start_time = datetime.now()
        
        if context.data is None or (isinstance(context.data, pd.DataFrame) and context.data.empty):
            return AgentResult(
                agent_name=self.name,
                success=False,
                output="没有可用的测试数据",
                confidence=0.0
            )
        
        df = context.data
        results = {}
        tools_used = []
        
        # 分析通过率
        if "通过率" in context.question or "失败率" in context.question or "pass" in context.question.lower():
            results["pass_rate"] = self.tools["analyze_pass_rate"](df)
            tools_used.append("analyze_pass_rate")
        
        # 分析覆盖率
        if "覆盖" in context.question or "coverage" in context.question.lower():
            results["coverage"] = self.tools["analyze_test_coverage"](df)
            tools_used.append("analyze_test_coverage")
        
        # 查找失败测试
        if "失败" in context.question or "failed" in context.question.lower():
            results["failed_tests"] = self.tools["find_failed_tests"](df)
            tools_used.append("find_failed_tests")
        
        # 如果没有特定分析，执行全面分析
        if not results:
            results["overview"] = {
                "total": len(df),
                "columns": list(df.columns)
            }
            tools_used.append("overview")
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=results,
            confidence=0.9,
            reasoning=f"完成了 {len(tools_used)} 项测试分析",
            tools_used=tools_used,
            execution_time=execution_time
        )
    
    def _analyze_coverage(self, df: pd.DataFrame) -> Dict:
        """分析测试覆盖率"""
        if 'aida' in df.columns:
            coverage = df['aida'].nunique()
            return {"covered_modules": coverage}
        return {"message": "缺少模块字段"}
    
    def _analyze_pass_rate(self, df: pd.DataFrame) -> Dict:
        """分析通过率"""
        if 'run_status' in df.columns:
            status_counts = df['run_status'].value_counts()
            total = len(df)
            passed = status_counts.get('Passed', 0) + status_counts.get('通过', 0)
            return {
                "pass_rate": round(passed / total * 100, 2) if total > 0 else 0,
                "total": total,
                "passed": passed,
                "failed": total - passed
            }
        return {"message": "缺少状态字段"}
    
    def _analyze_efficiency(self, df: pd.DataFrame) -> Dict:
        """分析测试效率"""
        return {"message": "效率分析功能开发中"}
    
    def _find_failed(self, df: pd.DataFrame) -> Dict:
        """查找失败测试"""
        if 'run_status' in df.columns:
            failed = df[df['run_status'].isin(['Failed', '失败'])]
            return {
                "count": len(failed),
                "top_aida": failed['aida'].value_counts().head(5).to_dict() if 'aida' in failed.columns else {}
            }
        return {"message": "缺少状态字段"}


class RiskAssessor(BaseAgent):
    """风险评估专家"""
    
    name = "risk_assessor"
    role = AgentRole.RISK_ASSESSOR
    description = "专注于风险评估，识别高风险项目、模块和问题"
    
    def _register_tools(self):
        """注册风险评估工具"""
        self.tools = {
            "assess_project_risk": self._assess_project_risk,
            "assess_module_risk": self._assess_module_risk,
            "calculate_risk_score": self._calculate_risk_score,
        }
    
    def run(self, context: AgentContext) -> AgentResult:
        """执行风险评估"""
        start_time = datetime.now()
        
        if context.data is None:
            return AgentResult(
                agent_name=self.name,
                success=False,
                output="没有可用的数据进行风险评估",
                confidence=0.0
            )
        
        df = context.data
        results = {}
        tools_used = []
        
        # 项目风险评估
        results["project_risk"] = self.tools["assess_project_risk"](df)
        tools_used.append("assess_project_risk")
        
        # 模块风险评估
        results["module_risk"] = self.tools["assess_module_risk"](df)
        tools_used.append("assess_module_risk")
        
        # 综合风险评分
        results["overall_score"] = self.tools["calculate_risk_score"](df)
        tools_used.append("calculate_risk_score")
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=results,
            confidence=0.85,
            reasoning="完成综合风险评估",
            tools_used=tools_used,
            execution_time=execution_time
        )
    
    def _assess_project_risk(self, df: pd.DataFrame) -> Dict:
        """评估项目风险"""
        if 'tproject' not in df.columns:
            return {}
        
        risk_by_project = df.groupby('tproject').agg({
            'id': 'count'
        }).rename(columns={'id': 'issue_count'})
        
        # 简单风险评分
        risk_by_project['risk_score'] = risk_by_project['issue_count'] / risk_by_project['issue_count'].max() * 100
        
        return risk_by_project.sort_values('risk_score', ascending=False).head(10).to_dict()
    
    def _assess_module_risk(self, df: pd.DataFrame) -> Dict:
        """评估模块风险"""
        module_col = 'aida' if 'aida' in df.columns else 'pu' if 'pu' in df.columns else None
        
        if not module_col:
            return {}
        
        return df[module_col].value_counts().head(10).to_dict()
    
    def _calculate_risk_score(self, df: pd.DataFrame) -> float:
        """计算综合风险评分"""
        # 基于问题数量、严重性等因素
        score = 0.0
        
        # 问题数量
        score += min(len(df) / 100, 30)  # 最多 30 分
        
        # 严重性（如果有）
        if 'severity_group' in df.columns:
            high_severity = df['severity_group'].isin(['致命', '严重', 'Critical', 'High']).sum()
            score += min(high_severity / 10, 40)  # 最多 40 分
        
        # 时间因素（最近的问题权重更高）
        if 'tcreationtime' in df.columns:
            df = df.copy()
            df['tcreationtime'] = pd.to_datetime(df['tcreationtime'], errors='coerce')
            recent = df[df['tcreationtime'] > datetime.now() - pd.Timedelta(days=30)]
            score += min(len(recent) / 20, 30)  # 最多 30 分
        
        return round(min(score, 100), 2)


class StrategyAdvisor(BaseAgent):
    """策略顾问"""
    
    name = "strategy_advisor"
    role = AgentRole.STRATEGY_ADVISOR
    description = "提供测试策略建议，综合各方分析结果给出指导"
    
    def _register_tools(self):
        """注册策略工具"""
        self.tools = {
            "generate_test_strategy": self._generate_strategy,
            "prioritize_actions": self._prioritize_actions,
        }
    
    def run(self, context: AgentContext) -> AgentResult:
        """生成策略建议"""
        start_time = datetime.now()
        
        # 基于上下文和之前 Agent 的结果
        results = {}
        tools_used = []
        
        # 生成测试策略
        results["strategy"] = self.tools["generate_test_strategy"](context)
        tools_used.append("generate_test_strategy")
        
        # 优先级行动
        results["priorities"] = self.tools["prioritize_actions"](context)
        tools_used.append("prioritize_actions")
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=results,
            confidence=0.8,
            reasoning="基于分析结果生成策略建议",
            tools_used=tools_used,
            execution_time=execution_time
        )
    
    def _generate_strategy(self, context: AgentContext) -> Dict:
        """生成测试策略"""
        strategy = {
            "focus_areas": [],
            "recommendations": [],
            "risk_mitigation": []
        }
        
        question = context.question.lower()
        
        # 根据问题类型提供建议
        if "缺陷" in question or "defect" in question:
            strategy["focus_areas"].append("缺陷分析和回归测试")
            strategy["recommendations"].append("优先修复高风险缺陷")
        
        if "测试" in question or "test" in question:
            strategy["focus_areas"].append("测试覆盖率优化")
            strategy["recommendations"].append("增加失败模块的测试用例")
        
        if "风险" in question or "risk" in question:
            strategy["focus_areas"].append("风险管控")
            strategy["recommendations"].append("建立风险监控机制")
        
        # 默认建议
        if not strategy["focus_areas"]:
            strategy["focus_areas"].append("全面质量保障")
            strategy["recommendations"].append("定期进行测试回顾和优化")
        
        return strategy
    
    def _prioritize_actions(self, context: AgentContext) -> List[Dict]:
        """优先级行动列表"""
        return [
            {"priority": 1, "action": "修复高风险缺陷", "urgency": "高"},
            {"priority": 2, "action": "增加核心模块测试覆盖", "urgency": "中"},
            {"priority": 3, "action": "优化测试执行效率", "urgency": "低"},
        ]


# ============================================================================
# 协调者 Agent
# ============================================================================

class CoordinatorAgent(BaseAgent):
    """
    协调者 Agent
    
    负责任务分配、结果整合和工作流编排
    """
    
    name = "coordinator"
    role = AgentRole.COORDINATOR
    description = "协调多个专业 Agent，分配任务并整合结果"
    
    def __init__(self):
        super().__init__()
        
        # 注册专业 Agent
        self.specialists = {
            "defect_analyst": DefectAnalyst(),
            "test_analyst": TestAnalyst(),
            "risk_assessor": RiskAssessor(),
            "strategy_advisor": StrategyAdvisor(),
        }
    
    def _register_tools(self):
        """注册协调工具"""
        self.tools = {
            "analyze_intent": self._analyze_intent,
            "select_agents": self._select_agents,
            "merge_results": self._merge_results,
        }
    
    def run(self, context: AgentContext) -> AgentResult:
        """执行协调任务"""
        start_time = datetime.now()
        
        # 1. 分析意图
        intent = self._analyze_intent(context.question)
        context.intent = intent
        
        # 2. 选择合适的 Agent
        selected_agents = self._select_agents(intent)
        
        # 3. 分发任务给专业 Agent
        specialist_results = {}
        for agent_name in selected_agents:
            agent = self.specialists.get(agent_name)
            if agent:
                result = agent.run(context)
                specialist_results[agent_name] = result
        
        # 4. 整合结果
        merged_result = self._merge_results(specialist_results, context)
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=merged_result,
            confidence=0.9,
            reasoning=f"协调了 {len(selected_agents)} 个专业 Agent",
            tools_used=["analyze_intent", "select_agents", "merge_results"],
            execution_time=execution_time,
            metadata={
                "agents_used": list(specialist_results.keys()),
                "intent": intent
            }
        )
    
    def _analyze_intent(self, question: str) -> Dict:
        """分析问题意图"""
        question_lower = question.lower()
        
        intent = {
            "data_type": "all",
            "analysis_type": [],
            "focus": []
        }
        
        # 数据类型
        if "缺陷" in question or "defect" in question_lower:
            intent["data_type"] = "defects"
        elif "测试" in question or "test" in question_lower:
            intent["data_type"] = "tests"
        
        # 分析类型
        if "趋势" in question or "trend" in question_lower:
            intent["analysis_type"].append("trend")
        if "风险" in question or "risk" in question_lower:
            intent["analysis_type"].append("risk")
        if "策略" in question or "strategy" in question_lower:
            intent["analysis_type"].append("strategy")
        
        return intent
    
    def _select_agents(self, intent: Dict) -> List[str]:
        """根据意图选择 Agent"""
        agents = []
        
        # 数据类型决定主要 Agent
        if intent["data_type"] == "defects":
            agents.append("defect_analyst")
        elif intent["data_type"] == "tests":
            agents.append("test_analyst")
        else:
            # 未知类型，使用所有
            agents.extend(["defect_analyst", "test_analyst"])
        
        # 分析类型添加额外 Agent
        if "risk" in intent["analysis_type"]:
            agents.append("risk_assessor")
        if "strategy" in intent["analysis_type"]:
            agents.append("strategy_advisor")
        
        # 去重
        return list(set(agents))
    
    def _merge_results(
        self,
        specialist_results: Dict[str, AgentResult],
        context: AgentContext
    ) -> Dict:
        """整合多个 Agent 的结果"""
        merged = {
            "question": context.question,
            "analyses": {},
            "summary": "",
            "recommendations": []
        }
        
        # 收集各 Agent 结果
        for agent_name, result in specialist_results.items():
            if result.success:
                merged["analyses"][agent_name] = result.output
                
                # 收集建议
                if agent_name == "strategy_advisor" and isinstance(result.output, dict):
                    if "strategy" in result.output:
                        merged["recommendations"].extend(
                            result.output["strategy"].get("recommendations", [])
                        )
        
        # 生成摘要
        agent_count = len([r for r in specialist_results.values() if r.success])
        merged["summary"] = f"已协调 {agent_count} 个专业 Agent 完成分析"
        
        return merged


# ============================================================================
# 工厂函数
# ============================================================================

def create_multi_agent_system() -> CoordinatorAgent:
    """创建多 Agent 系统"""
    return CoordinatorAgent()


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("多 Agent 协作系统测试")
    print("=" * 70)
    
    # 创建系统
    coordinator = create_multi_agent_system()
    
    # 测试场景
    test_cases = [
        {
            "question": "最近两周 ABS 模块的缺陷趋势分析",
            "data_type": "defects"
        },
        {
            "question": "测试覆盖率不足的风险评估",
            "data_type": "tests"
        },
        {
            "question": "给我一个测试策略建议",
            "data_type": "all"
        }
    ]
    
    for case in test_cases:
        print(f"\n问题: {case['question']}")
        print("-" * 50)
        
        # 创建上下文
        context = AgentContext(
            question=case['question'],
            data=pd.DataFrame({"id": [1, 2, 3], "tproject": ["ABS", "IDCEVO", "ABS"]})
        )
        
        # 执行
        result = coordinator.run(context)
        
        print(f"协调结果:")
        print(f"  - 成功: {result.success}")
        print(f"  - 参与Agent: {result.metadata.get('agents_used', [])}")
        print(f"  - 摘要: {result.output.get('summary', '')}")
        print(f"  - 建议: {result.output.get('recommendations', [])}")

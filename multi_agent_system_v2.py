"""
多 Agent 协作系统 V2 - OpenClaw 集成版

增强功能：
1. 兼容 OpenClaw 框架 - 可作为 OpenClaw Agent 运行
2. 本地独立运行 - 无需 OpenClaw 也可使用
3. 智能上下文加载 - 集成智能上下文引擎
4. A2A 通信 - Agent 间通信支持
5. 追踪调试 - 完整的执行追踪

作者: AI Assistant
日期: 2026-03-18
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Union, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import pandas as pd
import asyncio
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


# ============================================================================
# OpenClaw 兼容性检查
# ============================================================================

OPENCLAW_AVAILABLE = False
try:
    # 尝试导入 OpenClaw 相关模块
    import subprocess
    result = subprocess.run(['openclaw', '--version'], capture_output=True, text=True)
    if result.returncode == 0:
        OPENCLAW_AVAILABLE = True
        logger.info(f"✅ OpenClaw 可用: {result.stdout.strip()}")
except Exception as e:
    logger.debug(f"OpenClaw 不可用，使用本地模式: {e}")


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
    session_id: str = ""
    user_id: str = ""
    
    def to_openclaw_format(self) -> Dict:
        """转换为 OpenClaw 格式"""
        return {
            "message": self.question,
            "context": {
                "data": self.data.to_dict() if isinstance(self.data, pd.DataFrame) else self.data,
                "metadata": self.metadata,
                "history": self.history
            },
            "session_id": self.session_id,
            "user_id": self.user_id
        }


@dataclass
class AgentResult:
    """Agent 执行结果"""
    agent_name: str
    success: bool
    output: Any
    confidence: float = 1.0
    reasoning: str = ""
    next_agent: Optional[str] = None
    tools_used: List[str] = field(default_factory=list)
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        result = asdict(self)
        if isinstance(self.output, pd.DataFrame):
            result['output'] = self.output.to_dict('records')
        return result


@dataclass
class Handoff:
    """任务交接"""
    from_agent: str
    to_agent: str
    context: AgentContext
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)


# ============================================================================
# 追踪系统
# ============================================================================

class AgentTracer:
    """Agent 执行追踪器"""
    
    def __init__(self, trace_dir: str = "~/.openclaw/traces"):
        self.trace_dir = os.path.expanduser(trace_dir)
        os.makedirs(self.trace_dir, exist_ok=True)
        self.current_trace: List[Dict] = []
        self.trace_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def start_span(self, agent_name: str, action: str, **kwargs):
        """开始一个追踪跨度"""
        span = {
            "trace_id": self.trace_id,
            "span_id": f"{agent_name}_{len(self.current_trace)}",
            "agent": agent_name,
            "action": action,
            "start_time": datetime.now().isoformat(),
            "metadata": kwargs
        }
        self.current_trace.append(span)
        return span["span_id"]
    
    def end_span(self, span_id: str, result: Any = None, error: str = None):
        """结束追踪跨度"""
        for span in self.current_trace:
            if span["span_id"] == span_id:
                span["end_time"] = datetime.now().isoformat()
                span["duration_ms"] = (
                    datetime.fromisoformat(span["end_time"]) - 
                    datetime.fromisoformat(span["start_time"])
                ).total_seconds() * 1000
                span["result"] = str(result)[:500] if result else None
                span["error"] = error
                break
    
    def save_trace(self):
        """保存追踪记录"""
        trace_file = os.path.join(self.trace_dir, f"trace_{self.trace_id}.json")
        with open(trace_file, 'w', encoding='utf-8') as f:
            json.dump(self.current_trace, f, indent=2, ensure_ascii=False, default=str)
        return trace_file
    
    def get_summary(self) -> Dict:
        """获取追踪摘要"""
        if not self.current_trace:
            return {}
        
        total_time = sum(
            span.get("duration_ms", 0) for span in self.current_trace
        )
        
        return {
            "trace_id": self.trace_id,
            "total_spans": len(self.current_trace),
            "total_time_ms": total_time,
            "agents_used": list(set(span["agent"] for span in self.current_trace)),
            "actions": [span["action"] for span in self.current_trace]
        }


# ============================================================================
# OpenClaw 集成适配器
# ============================================================================

class OpenClawAdapter:
    """OpenClaw 集成适配器"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.workspace = os.path.expanduser(f"~/.openclaw/agents/{agent_name}")
    
    def load_soul(self) -> str:
        """加载 SOUL.md"""
        soul_path = os.path.join(self.workspace, "SOUL.md")
        if os.path.exists(soul_path):
            with open(soul_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""
    
    def load_user_context(self) -> Dict:
        """加载用户上下文"""
        user_path = os.path.join(self.workspace, "USER.md")
        if os.path.exists(user_path):
            with open(user_path, 'r', encoding='utf-8') as f:
                return {"user_profile": f.read()}
        return {}
    
    def call_agent(self, target_agent: str, message: str) -> str:
        """调用其他 Agent"""
        if not OPENCLAW_AVAILABLE:
            logger.warning("OpenClaw 不可用，无法调用其他 Agent")
            return ""
        
        try:
            result = subprocess.run(
                ['openclaw', 'agents', 'call', target_agent, '--message', message],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return result.stdout
            else:
                logger.error(f"调用 Agent {target_agent} 失败: {result.stderr}")
                return ""
        except Exception as e:
            logger.error(f"调用 Agent 异常: {e}")
            return ""
    
    def send_message(self, channel: str, message: str):
        """发送消息到频道"""
        if not OPENCLAW_AVAILABLE:
            return
        
        try:
            subprocess.run(
                ['openclaw', 'send', '--channel', channel, '--message', message],
                capture_output=True,
                text=True
            )
        except Exception as e:
            logger.error(f"发送消息失败: {e}")


# ============================================================================
# 基础 Agent 类 V2
# ============================================================================

class BaseAgentV2:
    """基础 Agent 类 V2 - 支持 OpenClaw 集成"""
    
    name: str = "base_agent"
    role: AgentRole = AgentRole.COORDINATOR
    description: str = "基础 Agent"
    
    def __init__(self, use_openclaw: bool = True):
        self.tools: Dict[str, Callable] = {}
        self.use_openclaw = use_openclaw and OPENCLAW_AVAILABLE
        self.tracer = AgentTracer()
        
        # OpenClaw 适配器
        if self.use_openclaw:
            self.openclaw_adapter = OpenClawAdapter(self.name)
            self.soul = self.openclaw_adapter.load_soul()
        else:
            self.openclaw_adapter = None
            self.soul = ""
        
        self._register_tools()
    
    def _register_tools(self):
        """注册工具（子类实现）"""
        pass
    
    def run(self, context: AgentContext) -> AgentResult:
        """执行任务"""
        raise NotImplementedError
    
    def run_async(self, context: AgentContext) -> AgentResult:
        """异步执行任务"""
        return self.run(context)
    
    def handoff_to(self, target_agent: str, context: AgentContext, reason: str) -> Handoff:
        """交接任务给其他 Agent"""
        handoff = Handoff(
            from_agent=self.name,
            to_agent=target_agent,
            context=context,
            reason=reason
        )
        
        # 如果启用了 OpenClaw，执行实际交接
        if self.use_openclaw and self.openclaw_adapter:
            self.openclaw_adapter.call_agent(
                target_agent, 
                f"[Handoff from {self.name}] {reason}\n\nContext: {context.question}"
            )
        
        return handoff
    
    def _trace_execution(self, action: str, func: Callable, *args, **kwargs) -> Any:
        """追踪执行"""
        span_id = self.tracer.start_span(self.name, action, **kwargs)
        try:
            result = func(*args, **kwargs)
            self.tracer.end_span(span_id, result)
            return result
        except Exception as e:
            self.tracer.end_span(span_id, error=str(e))
            raise


# ============================================================================
# 专业 Agent 实现 V2
# ============================================================================

class DefectAnalystV2(BaseAgentV2):
    """缺陷分析专家 V2"""
    
    name = "defect_analyst"
    role = AgentRole.DEFECT_ANALYST
    description = "专注于缺陷数据分析，包括趋势、分布、严重性等"
    
    def _register_tools(self):
        self.tools = {
            "analyze_trend": self._analyze_trend,
            "analyze_distribution": self._analyze_distribution,
            "find_high_severity": self._find_high_severity,
            "analyze_by_project": self._analyze_by_project,
            "predict_trend": self._predict_trend,
            "find_patterns": self._find_patterns,
        }
    
    def run(self, context: AgentContext) -> AgentResult:
        """执行缺陷分析"""
        start_time = datetime.now()
        span_id = self.tracer.start_span(self.name, "defect_analysis", question=context.question)
        
        try:
            if context.data is None:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    output="没有可用的缺陷数据",
                    confidence=0.0,
                    trace_id=self.tracer.trace_id
                )
            
            df = context.data if isinstance(context.data, pd.DataFrame) else pd.DataFrame(context.data)
            results = {}
            tools_used = []
            
            # 智能分析 - 根据问题自动选择工具
            question_lower = context.question.lower()
            
            if any(kw in question_lower for kw in ["趋势", "trend", "预测", "predict"]):
                results["trend"] = self.tools["analyze_trend"](df)
                results["prediction"] = self.tools["predict_trend"](df)
                tools_used.extend(["analyze_trend", "predict_trend"])
            
            if any(kw in question_lower for kw in ["分布", "distribution", "统计", "stats"]):
                results["distribution"] = self.tools["analyze_distribution"](df)
                tools_used.append("analyze_distribution")
            
            if any(kw in question_lower for kw in ["风险", "高风险", "严重", "critical", "risk"]):
                results["high_severity"] = self.tools["find_high_severity"](df)
                tools_used.append("find_high_severity")
            
            if any(kw in question_lower for kw in ["模式", "pattern", "规律", "关联"]):
                results["patterns"] = self.tools["find_patterns"](df)
                tools_used.append("find_patterns")
            
            # 默认全面分析
            if not results:
                results["overview"] = {
                    "total": len(df),
                    "columns": list(df.columns),
                    "summary": df.describe(include='all').to_dict() if len(df) > 0 else {}
                }
                tools_used.append("overview")
            
            execution_time = (datetime.now() - start_time).total_seconds()
            self.tracer.end_span(span_id, results)
            
            return AgentResult(
                agent_name=self.name,
                success=True,
                output=results,
                confidence=0.9,
                reasoning=f"完成了 {len(tools_used)} 项缺陷分析",
                tools_used=tools_used,
                execution_time=execution_time,
                trace_id=self.tracer.trace_id
            )
        
        except Exception as e:
            self.tracer.end_span(span_id, error=str(e))
            return AgentResult(
                agent_name=self.name,
                success=False,
                output=f"分析失败: {str(e)}",
                confidence=0.0,
                trace_id=self.tracer.trace_id
            )
    
    def _analyze_trend(self, df: pd.DataFrame) -> Dict:
        """分析缺陷趋势"""
        if 'tcreationtime' not in df.columns:
            return {"message": "缺少时间字段"}
        
        df = df.copy()
        df['tcreationtime'] = pd.to_datetime(df['tcreationtime'], errors='coerce')
        df = df.dropna(subset=['tcreationtime'])
        
        if len(df) == 0:
            return {"message": "无有效时间数据"}
        
        # 按周统计
        df['week'] = df['tcreationtime'].dt.to_period('W')
        weekly = df.groupby('week').size()
        
        return {
            "direction": "上升" if len(weekly) > 1 and weekly.iloc[-1] > weekly.iloc[0] else "下降",
            "weekly_counts": {str(k): v for k, v in weekly.to_dict().items()},
            "total_weeks": len(weekly),
            "avg_per_week": round(weekly.mean(), 2)
        }
    
    def _analyze_distribution(self, df: pd.DataFrame) -> Dict:
        """分析缺陷分布"""
        distribution = {}
        
        for col in ['tproject', 'severity_group', 'pu', 'aida', 'team']:
            if col in df.columns:
                distribution[col] = df[col].value_counts().head(10).to_dict()
        
        return distribution
    
    def _find_high_severity(self, df: pd.DataFrame) -> Dict:
        """查找高风险缺陷"""
        if 'severity_group' not in df.columns:
            return {"message": "缺少严重性字段"}
        
        high_keywords = ['致命', '严重', 'Critical', 'High', 'Blocker', 'Major']
        high_df = df[df['severity_group'].isin(high_keywords)]
        
        result = {
            "count": len(high_df),
            "percentage": round(len(high_df) / len(df) * 100, 2) if len(df) > 0 else 0
        }
        
        if 'tproject' in high_df.columns:
            result["by_project"] = high_df['tproject'].value_counts().head(10).to_dict()
        
        if 'aida' in high_df.columns:
            result["by_module"] = high_df['aida'].value_counts().head(10).to_dict()
        
        return result
    
    def _analyze_by_project(self, df: pd.DataFrame) -> Dict:
        """按项目分析"""
        if 'tproject' not in df.columns:
            return {"message": "缺少项目字段"}
        
        return df.groupby('tproject').agg({
            'id': 'count'
        }).rename(columns={'id': 'count'}).sort_values('count', ascending=False).head(20).to_dict()
    
    def _predict_trend(self, df: pd.DataFrame) -> Dict:
        """预测趋势（简单线性回归）"""
        if 'tcreationtime' not in df.columns:
            return {"message": "缺少时间字段"}
        
        try:
            df = df.copy()
            df['tcreationtime'] = pd.to_datetime(df['tcreationtime'], errors='coerce')
            df = df.dropna(subset=['tcreationtime'])
            df = df.sort_values('tcreationtime')
            
            # 按天统计
            daily = df.groupby(df['tcreationtime'].dt.date).size()
            
            if len(daily) < 7:
                return {"message": "数据不足，需要至少7天数据"}
            
            # 简单移动平均预测
            recent_avg = daily.tail(7).mean()
            trend = "上升" if daily.tail(7).mean() > daily.head(7).mean() else "下降"
            
            return {
                "prediction": f"预计下周每天新增 {int(recent_avg)} 个缺陷",
                "trend": trend,
                "confidence": 0.7
            }
        except Exception as e:
            return {"message": f"预测失败: {str(e)}"}
    
    def _find_patterns(self, df: pd.DataFrame) -> Dict:
        """发现缺陷模式"""
        patterns = []
        
        # 检查重复标题
        if 'title' in df.columns or 'name' in df.columns:
            title_col = 'title' if 'title' in df.columns else 'name'
            duplicates = df[title_col].value_counts()
            duplicates = duplicates[duplicates > 1]
            if len(duplicates) > 0:
                patterns.append({
                    "type": "重复缺陷",
                    "count": len(duplicates),
                    "top_titles": duplicates.head(5).to_dict()
                })
        
        # 检查模块聚集
        if 'aida' in df.columns:
            module_counts = df['aida'].value_counts()
            hot_modules = module_counts[module_counts > module_counts.mean() * 2]
            if len(hot_modules) > 0:
                patterns.append({
                    "type": "热点模块",
                    "modules": hot_modules.head(5).to_dict()
                })
        
        return {"patterns": patterns, "count": len(patterns)}


class TestAnalystV2(BaseAgentV2):
    """测试分析专家 V2"""
    
    name = "test_analyst"
    role = AgentRole.TEST_ANALYST
    description = "专注于测试数据分析，包括覆盖率、通过率、效率等"
    
    def _register_tools(self):
        self.tools = {
            "analyze_coverage": self._analyze_coverage,
            "analyze_pass_rate": self._analyze_pass_rate,
            "analyze_efficiency": self._analyze_efficiency,
            "find_failed_tests": self._find_failed,
            "analyze_flaky": self._analyze_flaky,
        }
    
    def run(self, context: AgentContext) -> AgentResult:
        """执行测试分析"""
        start_time = datetime.now()
        
        if context.data is None:
            return AgentResult(
                agent_name=self.name,
                success=False,
                output="没有可用的测试数据",
                confidence=0.0,
                trace_id=self.tracer.trace_id
            )
        
        df = context.data if isinstance(context.data, pd.DataFrame) else pd.DataFrame(context.data)
        results = {}
        tools_used = []
        
        question_lower = context.question.lower()
        
        if any(kw in question_lower for kw in ["覆盖", "coverage"]):
            results["coverage"] = self.tools["analyze_coverage"](df)
            tools_used.append("analyze_coverage")
        
        if any(kw in question_lower for kw in ["通过率", "失败率", "pass", "fail"]):
            results["pass_rate"] = self.tools["analyze_pass_rate"](df)
            tools_used.append("analyze_pass_rate")
        
        if any(kw in question_lower for kw in ["失败", "failed", "问题"]):
            results["failed_tests"] = self.tools["find_failed_tests"](df)
            tools_used.append("find_failed_tests")
        
        if any(kw in question_lower for kw in ["不稳定", "flaky", "偶发"]):
            results["flaky"] = self.tools["analyze_flaky"](df)
            tools_used.append("analyze_flaky")
        
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
            execution_time=execution_time,
            trace_id=self.tracer.trace_id
        )
    
    def _analyze_coverage(self, df: pd.DataFrame) -> Dict:
        """分析测试覆盖率"""
        coverage = {}
        
        if 'aida' in df.columns:
            coverage["covered_modules"] = df['aida'].nunique()
        
        if 'test_type' in df.columns:
            coverage["by_type"] = df['test_type'].value_counts().to_dict()
        
        return coverage
    
    def _analyze_pass_rate(self, df: pd.DataFrame) -> Dict:
        """分析通过率"""
        if 'run_status' not in df.columns:
            return {"message": "缺少状态字段"}
        
        status_counts = df['run_status'].value_counts()
        total = len(df)
        passed = status_counts.get('Passed', 0) + status_counts.get('通过', 0)
        
        return {
            "pass_rate": round(passed / total * 100, 2) if total > 0 else 0,
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "status_distribution": status_counts.to_dict()
        }
    
    def _analyze_efficiency(self, df: pd.DataFrame) -> Dict:
        """分析测试效率"""
        return {"message": "效率分析功能开发中"}
    
    def _find_failed(self, df: pd.DataFrame) -> Dict:
        """查找失败测试"""
        if 'run_status' not in df.columns:
            return {"message": "缺少状态字段"}
        
        failed = df[df['run_status'].isin(['Failed', '失败'])]
        
        result = {
            "count": len(failed),
            "percentage": round(len(failed) / len(df) * 100, 2) if len(df) > 0 else 0
        }
        
        if 'aida' in failed.columns:
            result["by_module"] = failed['aida'].value_counts().head(10).to_dict()
        
        return result
    
    def _analyze_flaky(self, df: pd.DataFrame) -> Dict:
        """分析不稳定测试"""
        return {"message": "不稳定测试分析功能开发中"}


class RiskAssessorV2(BaseAgentV2):
    """风险评估专家 V2"""
    
    name = "risk_assessor"
    role = AgentRole.RISK_ASSESSOR
    description = "专注于风险评估，识别高风险项目、模块和问题"
    
    def _register_tools(self):
        self.tools = {
            "assess_project_risk": self._assess_project_risk,
            "assess_module_risk": self._assess_module_risk,
            "calculate_risk_score": self._calculate_risk_score,
            "generate_risk_matrix": self._generate_risk_matrix,
        }
    
    def run(self, context: AgentContext) -> AgentResult:
        """执行风险评估"""
        start_time = datetime.now()
        
        if context.data is None:
            return AgentResult(
                agent_name=self.name,
                success=False,
                output="没有可用的数据进行风险评估",
                confidence=0.0,
                trace_id=self.tracer.trace_id
            )
        
        df = context.data if isinstance(context.data, pd.DataFrame) else pd.DataFrame(context.data)
        results = {}
        tools_used = []
        
        results["project_risk"] = self.tools["assess_project_risk"](df)
        results["module_risk"] = self.tools["assess_module_risk"](df)
        results["overall_score"] = self.tools["calculate_risk_score"](df)
        results["risk_matrix"] = self.tools["generate_risk_matrix"](df)
        tools_used.extend(["assess_project_risk", "assess_module_risk", "calculate_risk_score", "generate_risk_matrix"])
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=results,
            confidence=0.85,
            reasoning="完成综合风险评估",
            tools_used=tools_used,
            execution_time=execution_time,
            trace_id=self.tracer.trace_id
        )
    
    def _assess_project_risk(self, df: pd.DataFrame) -> Dict:
        """评估项目风险"""
        if 'tproject' not in df.columns:
            return {}
        
        risk_by_project = df.groupby('tproject').agg({'id': 'count'}).rename(columns={'id': 'issue_count'})
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
        score = 0.0
        
        score += min(len(df) / 100, 30)
        
        if 'severity_group' in df.columns:
            high_severity = df['severity_group'].isin(['致命', '严重', 'Critical', 'High']).sum()
            score += min(high_severity / 10, 40)
        
        if 'tcreationtime' in df.columns:
            df = df.copy()
            df['tcreationtime'] = pd.to_datetime(df['tcreationtime'], errors='coerce')
            recent = df[df['tcreationtime'] > datetime.now() - pd.Timedelta(days=30)]
            score += min(len(recent) / 20, 30)
        
        return round(min(score, 100), 2)
    
    def _generate_risk_matrix(self, df: pd.DataFrame) -> Dict:
        """生成风险矩阵"""
        matrix = {
            "high_probability_high_impact": [],
            "high_probability_low_impact": [],
            "low_probability_high_impact": [],
            "low_probability_low_impact": []
        }
        
        # 简化实现 - 基于严重性和数量
        if 'severity_group' in df.columns and 'tproject' in df.columns:
            for project in df['tproject'].unique()[:5]:
                project_df = df[df['tproject'] == project]
                count = len(project_df)
                high_severity_count = project_df['severity_group'].isin(['致命', '严重', 'Critical', 'High']).sum()
                
                if count > len(df) / len(df['tproject'].unique()) and high_severity_count > 0:
                    matrix["high_probability_high_impact"].append(project)
                elif count > len(df) / len(df['tproject'].unique()):
                    matrix["high_probability_low_impact"].append(project)
                elif high_severity_count > 0:
                    matrix["low_probability_high_impact"].append(project)
                else:
                    matrix["low_probability_low_impact"].append(project)
        
        return matrix


class StrategyAdvisorV2(BaseAgentV2):
    """策略顾问 V2"""
    
    name = "strategy_advisor"
    role = AgentRole.STRATEGY_ADVISOR
    description = "提供测试策略建议，综合各方分析结果给出指导"
    
    def _register_tools(self):
        self.tools = {
            "generate_strategy": self._generate_strategy,
            "prioritize_actions": self._prioritize_actions,
            "generate_timeline": self._generate_timeline,
        }
    
    def run(self, context: AgentContext) -> AgentResult:
        """生成策略建议"""
        start_time = datetime.now()
        
        results = {}
        tools_used = []
        
        results["strategy"] = self.tools["generate_strategy"](context)
        results["priorities"] = self.tools["prioritize_actions"](context)
        results["timeline"] = self.tools["generate_timeline"](context)
        tools_used.extend(["generate_strategy", "prioritize_actions", "generate_timeline"])
        
        execution_time = (datetime.now() - start_time).total_seconds()
        
        return AgentResult(
            agent_name=self.name,
            success=True,
            output=results,
            confidence=0.8,
            reasoning="基于分析结果生成策略建议",
            tools_used=tools_used,
            execution_time=execution_time,
            trace_id=self.tracer.trace_id
        )
    
    def _generate_strategy(self, context: AgentContext) -> Dict:
        """生成测试策略"""
        strategy = {
            "focus_areas": [],
            "recommendations": [],
            "risk_mitigation": [],
            "quick_wins": []
        }
        
        question = context.question.lower()
        
        if "缺陷" in question or "defect" in question:
            strategy["focus_areas"].append("缺陷分析和回归测试")
            strategy["recommendations"].append("优先修复高风险缺陷")
            strategy["quick_wins"].append("建立缺陷看板，每日跟踪")
        
        if "测试" in question or "test" in question:
            strategy["focus_areas"].append("测试覆盖率优化")
            strategy["recommendations"].append("增加失败模块的测试用例")
            strategy["quick_wins"].append("分析失败用例根因")
        
        if "风险" in question or "risk" in question:
            strategy["focus_areas"].append("风险管控")
            strategy["recommendations"].append("建立风险监控机制")
            strategy["risk_mitigation"].append("高风险模块增加测试资源")
        
        if not strategy["focus_areas"]:
            strategy["focus_areas"].append("全面质量保障")
            strategy["recommendations"].append("定期进行测试回顾和优化")
        
        return strategy
    
    def _prioritize_actions(self, context: AgentContext) -> List[Dict]:
        """优先级行动列表"""
        return [
            {"priority": 1, "action": "修复高风险缺陷", "urgency": "高", "effort": "中"},
            {"priority": 2, "action": "增加核心模块测试覆盖", "urgency": "中", "effort": "高"},
            {"priority": 3, "action": "优化测试执行效率", "urgency": "低", "effort": "中"},
            {"priority": 4, "action": "建立风险预警机制", "urgency": "中", "effort": "中"},
        ]
    
    def _generate_timeline(self, context: AgentContext) -> Dict:
        """生成时间线"""
        return {
            "short_term": [
                {"week": 1, "actions": ["修复阻断性缺陷", "补充关键用例"]},
                {"week": 2, "actions": ["提升覆盖率至80%", "优化失败用例"]}
            ],
            "mid_term": [
                {"month": 1, "actions": ["建立自动化回归", "完善测试数据"]},
                {"month": 2, "actions": ["性能测试覆盖", "安全测试引入"]}
            ],
            "long_term": [
                {"quarter": 1, "actions": ["持续集成优化", "质量门禁完善"]}
            ]
        }


# ============================================================================
# 协调者 Agent V2
# ============================================================================

class CoordinatorAgentV2(BaseAgentV2):
    """协调者 Agent V2 - 支持并行和串行协作"""
    
    name = "coordinator"
    role = AgentRole.COORDINATOR
    description = "协调多个专业 Agent，分配任务并整合结果"
    
    def __init__(self, use_openclaw: bool = True, max_workers: int = 4):
        super().__init__(use_openclaw)
        self.max_workers = max_workers
        
        # 注册专业 Agent
        self.specialists = {
            "defect_analyst": DefectAnalystV2(use_openclaw),
            "test_analyst": TestAnalystV2(use_openclaw),
            "risk_assessor": RiskAssessorV2(use_openclaw),
            "strategy_advisor": StrategyAdvisorV2(use_openclaw),
        }
    
    def _register_tools(self):
        self.tools = {
            "analyze_intent": self._analyze_intent,
            "select_agents": self._select_agents,
            "merge_results": self._merge_results,
            "parallel_execute": self._parallel_execute,
        }
    
    def run(self, context: AgentContext) -> AgentResult:
        """执行协调任务"""
        start_time = datetime.now()
        span_id = self.tracer.start_span(self.name, "coordination", question=context.question)
        
        try:
            # 1. 分析意图
            intent = self._analyze_intent(context.question)
            context.intent = intent
            self.tracer.end_span(self.tracer.start_span(self.name, "intent_analysis"), intent)
            
            # 2. 选择 Agent
            selected_agents = self._select_agents(intent)
            self.tracer.end_span(self.tracer.start_span(self.name, "agent_selection"), selected_agents)
            
            # 3. 并行执行
            specialist_results = self._parallel_execute(selected_agents, context)
            
            # 4. 整合结果
            merged_result = self._merge_results(specialist_results, context)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            self.tracer.end_span(span_id, merged_result)
            
            # 保存追踪
            trace_file = self.tracer.save_trace()
            
            return AgentResult(
                agent_name=self.name,
                success=True,
                output=merged_result,
                confidence=0.9,
                reasoning=f"协调了 {len(selected_agents)} 个专业 Agent",
                tools_used=["analyze_intent", "select_agents", "parallel_execute", "merge_results"],
                execution_time=execution_time,
                metadata={
                    "agents_used": list(specialist_results.keys()),
                    "intent": intent,
                    "trace_file": trace_file
                },
                trace_id=self.tracer.trace_id
            )
        
        except Exception as e:
            self.tracer.end_span(span_id, error=str(e))
            return AgentResult(
                agent_name=self.name,
                success=False,
                output=f"协调失败: {str(e)}",
                confidence=0.0,
                trace_id=self.tracer.trace_id
            )
    
    def _analyze_intent(self, question: str) -> Dict:
        """分析问题意图"""
        question_lower = question.lower()
        
        intent = {
            "data_type": "all",
            "analysis_type": [],
            "focus": [],
            "urgency": "normal"
        }
        
        # 数据类型
        if any(kw in question_lower for kw in ["缺陷", "defect", "bug", "issue"]):
            intent["data_type"] = "defects"
        elif any(kw in question_lower for kw in ["测试", "test", "覆盖", "coverage"]):
            intent["data_type"] = "tests"
        
        # 分析类型
        if any(kw in question_lower for kw in ["趋势", "trend", "预测", "predict"]):
            intent["analysis_type"].append("trend")
        if any(kw in question_lower for kw in ["风险", "risk", "评估", "assess"]):
            intent["analysis_type"].append("risk")
        if any(kw in question_lower for kw in ["策略", "strategy", "建议", "recommend"]):
            intent["analysis_type"].append("strategy")
        if any(kw in question_lower for kw in ["分布", "distribution", "统计", "stats"]):
            intent["analysis_type"].append("distribution")
        
        # 紧急程度
        if any(kw in question_lower for kw in ["紧急", "urgent", "立即", "马上"]):
            intent["urgency"] = "high"
        
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
            agents.extend(["defect_analyst", "test_analyst"])
        
        # 分析类型添加额外 Agent
        if "risk" in intent["analysis_type"]:
            agents.append("risk_assessor")
        if "strategy" in intent["analysis_type"]:
            agents.append("strategy_advisor")
        
        # 高紧急度总是添加策略顾问
        if intent["urgency"] == "high":
            agents.append("strategy_advisor")
        
        return list(set(agents))
    
    def _parallel_execute(
        self, 
        agent_names: List[str], 
        context: AgentContext
    ) -> Dict[str, AgentResult]:
        """并行执行多个 Agent"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for agent_name in agent_names:
                agent = self.specialists.get(agent_name)
                if agent:
                    future = executor.submit(agent.run, context)
                    futures[future] = agent_name
            
            for future in futures:
                agent_name = futures[future]
                try:
                    results[agent_name] = future.result(timeout=60)
                except Exception as e:
                    results[agent_name] = AgentResult(
                        agent_name=agent_name,
                        success=False,
                        output=f"执行失败: {str(e)}",
                        confidence=0.0
                    )
        
        return results
    
    def _merge_results(
        self,
        specialist_results: Dict[str, AgentResult],
        context: AgentContext
    ) -> Dict:
        """整合多个 Agent 的结果"""
        merged = {
            "question": context.question,
            "intent": context.intent,
            "analyses": {},
            "summary": "",
            "recommendations": [],
            "risk_alerts": [],
            "action_items": []
        }
        
        # 收集各 Agent 结果
        for agent_name, result in specialist_results.items():
            if result.success:
                merged["analyses"][agent_name] = result.output
                
                # 收集建议
                if agent_name == "strategy_advisor" and isinstance(result.output, dict):
                    strategy = result.output.get("strategy", {})
                    merged["recommendations"].extend(strategy.get("recommendations", []))
                    merged["action_items"].extend([
                        {"action": action, "source": "strategy_advisor"}
                        for action in strategy.get("quick_wins", [])
                    ])
                
                # 收集风险预警
                if agent_name == "risk_assessor" and isinstance(result.output, dict):
                    if result.output.get("overall_score", 0) > 70:
                        merged["risk_alerts"].append({
                            "level": "high",
                            "score": result.output["overall_score"],
                            "message": "整体风险评分较高，需要立即关注"
                        })
        
        # 生成摘要
        agent_count = len([r for r in specialist_results.values() if r.success])
        merged["summary"] = f"已协调 {agent_count} 个专业 Agent 完成分析"
        
        # 添加执行统计
        merged["execution_stats"] = {
            "total_agents": len(specialist_results),
            "successful_agents": agent_count,
            "total_time_ms": sum(r.execution_time for r in specialist_results.values()) * 1000,
            "trace_id": self.tracer.trace_id
        }
        
        return merged


# ============================================================================
# 工厂函数
# ============================================================================

def create_multi_agent_system_v2(
    use_openclaw: bool = True,
    max_workers: int = 4
) -> CoordinatorAgentV2:
    """创建多 Agent 系统 V2"""
    return CoordinatorAgentV2(use_openclaw, max_workers)


def create_openclaw_agent(name: str, role: str) -> BaseAgentV2:
    """创建 OpenClaw 兼容的 Agent"""
    agent_classes = {
        "defect_analyst": DefectAnalystV2,
        "test_analyst": TestAnalystV2,
        "risk_assessor": RiskAssessorV2,
        "strategy_advisor": StrategyAdvisorV2,
        "coordinator": CoordinatorAgentV2
    }
    
    agent_class = agent_classes.get(name)
    if agent_class:
        return agent_class(use_openclaw=True)
    
    raise ValueError(f"Unknown agent: {name}")


# ============================================================================
# CLI 入口（用于 OpenClaw 集成）
# ============================================================================

def main():
    """CLI 入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="多 Agent 协作系统 V2")
    parser.add_argument("--agent", type=str, default="coordinator", help="Agent 名称")
    parser.add_argument("--question", type=str, required=True, help="问题")
    parser.add_argument("--data", type=str, help="数据文件路径")
    parser.add_argument("--output", type=str, default="json", help="输出格式")
    parser.add_argument("--no-openclaw", action="store_true", help="禁用 OpenClaw")
    
    args = parser.parse_args()
    
    # 加载数据
    data = None
    if args.data:
        if args.data.endswith('.csv'):
            data = pd.read_csv(args.data)
        elif args.data.endswith('.json'):
            data = pd.read_json(args.data)
    
    # 创建 Agent
    use_openclaw = not args.no_openclaw
    if args.agent == "coordinator":
        agent = create_multi_agent_system_v2(use_openclaw)
    else:
        agent = create_openclaw_agent(args.agent, args.agent)
    
    # 执行
    context = AgentContext(question=args.question, data=data)
    result = agent.run(context)
    
    # 输出
    if args.output == "json":
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))
    else:
        print(f"Result: {result.output}")


if __name__ == "__main__":
    main()

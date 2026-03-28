#!/usr/bin/env python3
"""
业务规则解释器 - 解释为什么某个缺陷是 TopIssue/High Runner/Long Runner

能够详细解释评分原因，并生成有价值的业务洞察和建议。

使用方法：
from chatdb.business_rule_explainer import BusinessRuleExplainer

explainer = BusinessRuleExplainer()
explanation = explainer.explain_top_issue(defect_data)
print(explanation)

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

# 导入业务规则
from chatdb.business_rules import (
    TOP_ISSUE_THRESHOLD,
    HIGH_RUNNER_THRESHOLD,
    LONG_RUNNER_THRESHOLD,
    MATRIX_SEVERITY_NUMERIC,
    TOP_ISSUE_DIMENSIONS,
    CLASSIFICATION_SCORES,
    ECU_TRANSFER_SCORES,
    DOMAIN_TRANSFER_SCORES,
    PROCESSING_CYCLE_SCORING,
    RESOLVED_PHASES
)

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BusinessRuleExplainer:
    """业务规则解释器"""
    
    def __init__(self):
        """初始化解释器"""
        self._cache = {}
    
    def explain_top_issue(self, defect: Dict) -> str:
        """
        解释为什么这个缺陷是 TopIssue
        
        Args:
            defect: 缺陷数据字典
        
        Returns:
            解释文本（格式化的 Markdown）
        """
        # 提取关键信息
        risk_score = defect.get('topissue_risk_score', 0)
        is_master_score = defect.get('is_master_score', False)
        
        # 生成解释
        parts = []
        
        # 1. 总体说明
        parts.append(self._explain_overall(risk_score, is_master_score))
        
        # 2. 评分维度分解
        parts.append(self._explain_dimensions(defect))
        
        # 3. 业务洞察
        insights = self._generate_insights(defect)
        if insights:
            parts.append("## 💡 业务洞察\n")
            for i, insight in enumerate(insights, 1):
                parts.append(f"{i}. {insight}")
        
        # 4. 建议
        recommendations = self._generate_recommendations(defect)
        if recommendations:
            parts.append("## 🎯 建议\n")
            for i, rec in enumerate(recommendations, 1):
                parts.append(f"{i}. {rec}")
        
        return "\n\n".join(parts)
    
    def explain_high_runner(self, defect: Dict) -> str:
        """
        解释为什么这个缺陷是 High Runner
        
        Args:
            defect: 缺陷数据字典
        
        Returns:
            解释文本（格式化的 Markdown）
        """
        ecu_transfers = defect.get('ecu_no_of_changes', 0)
        domain_transfers = defect.get('domain_pingpong_count', 0)
        ecu_path = defect.get('ecu_pingpong_display', '')
        domain_path = defect.get('domain_pingpong_display', '')
        
        parts = []
        
        # 1. 总体说明
        parts.append(f"## 📊 High Runner 分析")
        parts.append(f"\n这个缺陷是 **High Runner**，因为它频繁转移。")
        
        # 2. ECU 转移
        if ecu_transfers >= HIGH_RUNNER_THRESHOLD:
            parts.append(f"\n### 🔧 ECU 转移")
            parts.append(f"- **转移次数**: {ecu_transfers} 次")
            parts.append(f"- **转移路径**: {ecu_path}")
            
            # 评分
            score = self._calculate_transfer_score(ecu_transfers)
            parts.append(f"- **风险评分**: {score} 分")
            
            # 严重性
            if ecu_transfers >= 5:
                parts.append(f"- **严重性**: ⚠️ 极端 High Runner (≥5次)")
            else:
                parts.append(f"- **严重性**: 🔶 High Runner (≥3次)")
        
        # 3. Domain 转移
        if domain_transfers >= HIGH_RUNNER_THRESHOLD:
            parts.append(f"\n### 🌐 Domain 转移")
            parts.append(f"- **转移次数**: {domain_transfers} 次")
            parts.append(f"- **转移路径**: {domain_path}")
            
            # 评分
            score = self._calculate_domain_score(domain_transfers)
            parts.append(f"- **风险评分**: {score} 分")
        
        # 4. 业务洞察
        insights = self._generate_high_runner_insights(defect)
        if insights:
            parts.append("\n### 💡 业务洞察")
            for insight in insights:
                parts.append(f"- {insight}")
        
        # 5. 建议
        recommendations = self._generate_high_runner_recommendations(defect)
        if recommendations:
            parts.append("\n### 🎯 建议")
            for rec in recommendations:
                parts.append(f"- {rec}")
        
        return "\n".join(parts)
    
    def explain_long_runner(self, defect: Dict) -> str:
        """
        解释为什么这个缺陷是 Long Runner
        
        Args:
            defect: 缺陷数据字典
        
        Returns:
            解释文本（格式化的 Markdown）
        """
        processing_days = defect.get('processing_cycle_days', 0)
        status_phase = defect.get('status_phase', '')
        creation_time = defect.get('creation_time', '')
        shift_pu = defect.get('shift_pu', '')
        
        parts = []
        
        # 1. 总体说明
        parts.append(f"## ⏰ Long Runner 分析")
        parts.append(f"\n这个缺陷是 **Long Runner**，因为它长期未解决。")
        
        # 2. 处理周期
        parts.append(f"\n### 📅 处理周期")
        parts.append(f"- **处理天数**: {processing_days} 天")
        parts.append(f"- **当前状态**: {status_phase}")
        parts.append(f"- **创建时间**: {creation_time}")
        
        if shift_pu:
            parts.append(f"- **Shift PU**: {shift_pu} (已延期)")
        
        # 3. 阶段分析
        parts.append(f"\n### 🔄 阶段分析")
        stage_info = self._analyze_processing_stage(processing_days, status_phase)
        parts.append(stage_info)
        
        # 4. 业务洞察
        insights = self._generate_long_runner_insights(defect)
        if insights:
            parts.append("\n### 💡 业务洞察")
            for insight in insights:
                parts.append(f"- {insight}")
        
        # 5. 建议
        recommendations = self._generate_long_runner_recommendations(defect)
        if recommendations:
            parts.append("\n### 🎯 建议")
            for rec in recommendations:
                parts.append(f"- {rec}")
        
        return "\n".join(parts)
    
    def _explain_overall(self, risk_score: float, is_master_score: bool) -> str:
        """解释总体情况"""
        parts = ["## 📊 总体评估"]
        
        # 风险等级
        if risk_score >= 140:
            risk_level = "🔴 **极高风险** (Extremely High Risk)"
        elif risk_score >= 100:
            risk_level = "🟠 **高风险** (High Risk)"
        elif risk_score >= 60:
            risk_level = "🟡 **中等风险** (Medium Risk)"
        else:
            risk_level = "🟢 **低风险** (Low Risk)"
        
        parts.append(f"\n这个缺陷是 **TopIssue**，风险评分: **{risk_score:.1f}** 分")
        parts.append(f"\n风险等级: {risk_level}")
        
        if is_master_score:
            parts.append("\n⚠️ **注意**: 使用主票的风险评分（主票有更复杂的子票情况）")
        
        return "\n".join(parts)
    
    def _explain_dimensions(self, defect: Dict) -> str:
        """解释评分维度"""
        parts = ["## 📋 评分维度分解"]
        
        # 1. Matrix 严重性
        matrix = defect.get('matrix', '')
        if matrix:
            parts.append("\n### 1. Matrix 严重性 (30分)")
            
            # 计算分数
            score = self._calculate_matrix_score(matrix)
            
            # 严重性等级
            severity_level = self._get_matrix_level(matrix)
            
            parts.append(f"- **Matrix**: {matrix}")
            parts.append(f"- **等级**: {severity_level}")
            parts.append(f"- **得分**: {score:.1f} 分 / 30分")
            
            # 说明
            if severity_level == "High Severity":
                parts.append(f"- **影响**: 这是最严重的缺陷，需要立即关注")
            elif severity_level == "Medium Severity":
                parts.append(f"- **影响**: 严重的缺陷，需要尽快处理")
            else:
                parts.append(f"- **影响**: 中低等严重性，可以按优先级处理")
        
        # 2. Classification
        classification = defect.get('classification_display', '')
        if classification:
            parts.append("\n### 2. Classification (30分)")
            
            # 计算分数
            score = self._calculate_classification_score(classification)
            
            parts.append(f"- **Classification**: {classification}")
            parts.append(f"- **得分**: {score:.1f} 分 / 30分")
            
            # 说明
            if 'Showstopper' in classification or 'Preventing Maturity' in classification:
                parts.append(f"- **影响**: 这个缺陷阻塞了项目进度或发布")
            else:
                parts.append(f"- **影响**: 这个缺陷有特殊标注")
        
        # 3. ECU 转移
        ecu_transfers = defect.get('ecu_no_of_changes', 0)
        if ecu_transfers > 0:
            parts.append("\n### 3. ECU 转移 (30分)")
            
            score = self._calculate_transfer_score(ecu_transfers)
            
            parts.append(f"- **转移次数**: {ecu_transfers} 次")
            parts.append(f"- **得分**: {score:.1f} 分 / 30分")
            
            if ecu_transfers >= 5:
                parts.append(f"- **严重性**: ⚠️ 极端频繁转移 (≥5次)")
            elif ecu_transfers >= 3:
                parts.append(f"- **严重性**: 🔶 频繁转移 (≥3次)")
            
            # 转移路径
            ecu_path = defect.get('ecu_pingpong_display', '')
            if ecu_path:
                parts.append(f"- **转移路径**: {ecu_path}")
        
        # 4. Parent/Child 复杂度
        parent_child = defect.get('parent_child', '')
        if parent_child == 'Parent':
            child_count = defect.get('child_count', 0)
            if child_count > 0:
                parts.append("\n### 4. 主票复杂度 (30分)")
                
                score = self._calculate_parent_score(child_count)
                
                parts.append(f"- **子票数量**: {child_count} 个")
                parts.append(f"- **得分**: {score:.1f} 分 / 30分")
                
                if child_count > 10:
                    parts.append(f"- **严重性**: ⚠️ 超大规模主票 (>{child_count-10} 个)")
                elif child_count >= 5:
                    parts.append(f"- **严重性**: 🔶 大规模主票 (≥5个)")
                
                parts.append(f"- **影响**: 主票有多个子票，说明问题影响范围广")
        
        elif parent_child == 'Child':
            master_child_count = defect.get('master_child_count', 0)
            if master_child_count > 0:
                parts.append("\n### 4. 子票复杂度 (30分)")
                
                score = self._calculate_parent_score(master_child_count)
                
                parts.append(f"- **主票子票数**: {master_child_count} 个")
                parts.append(f"- **得分**: {score:.1f} 分 / 30分")
                
                parts.append(f"- **影响**: 使用主票的复杂度评分")
        
        # 5. 处理周期
        processing_days = defect.get('processing_cycle_days', 0)
        if processing_days > 0:
            parts.append("\n### 5. 处理周期 (20分)")
            
            score = self._calculate_cycle_score(processing_days)
            stage = self._get_processing_stage(processing_days)
            
            parts.append(f"- **处理天数**: {processing_days} 天")
            parts.append(f"- **阶段**: {stage}")
            parts.append(f"- **得分**: {score:.1f} 分 / 20分")
        
        # 6. Shift PU
        shift_pu = defect.get('shift_pu', '')
        if shift_pu:
            parts.append("\n### 6. Shift PU (10分)")
            parts.append(f"- **Shift PU**: {shift_pu}")
            parts.append(f"- **得分**: 10 分 / 10分")
            parts.append(f"- **影响**: 这个缺陷已延期到后续版本")
        
        return "\n".join(parts)
    
    def _calculate_matrix_score(self, matrix: str) -> float:
        """计算 Matrix 严重性分数"""
        matrix_lower = matrix.lower()
        
        # 获取 numeric 值
        numeric = MATRIX_SEVERITY_NUMERIC.get(matrix_lower, 32)
        
        # 转换为分数（越小越严重，分数越高）
        # 范围: 10-32 → 30-2 分
        return max(2, 30 - (numeric - 10))
    
    def _calculate_classification_score(self, classification: str) -> float:
        """计算 Classification 分数"""
        # 直接从业务规则中查找
        for term, score in CLASSIFICATION_SCORES.items():
            if term in classification:
                return float(score)
        
        return 0.0
    
    def _calculate_transfer_score(self, transfers: int) -> float:
        """计算转移分数"""
        if transfers >= 5:
            return 30.0
        elif transfers >= 3:
            return 24.0
        elif transfers >= 1:
            return 20.0
        else:
            return 0.0
    
    def _calculate_domain_score(self, transfers: int) -> float:
        """计算 Domain 转移分数"""
        if transfers >= 5:
            return 20.0
        elif transfers >= 3:
            return 14.0
        elif transfers >= 1:
            return 10.0
        else:
            return 0.0
    
    def _calculate_parent_score(self, child_count: int) -> float:
        """计算 Parent/Child 复杂度分数"""
        import math
        return min(30.0, round(10 * math.log(child_count + 1) * 2.5))
    
    def _calculate_cycle_score(self, days: int) -> float:
        """计算处理周期分数（双峰分布）"""
        if days <= 3:
            # 新票高峰
            return 24.0 - (days * 2.0)
        elif days <= 20:
            # 正常处理低谷
            return max(5.0, 15.0 - (days * 0.5))
        elif days <= 30:
            # Long Runner 上升
            return 15.0 + ((days - 20) * 0.5)
        else:
            # Long Runner 高峰
            base = 20.0
            extra = min(5.0, ((days - 30) / 10) * 2)
            return base + extra
    
    def _get_matrix_level(self, matrix: str) -> str:
        """获取 Matrix 严重性等级"""
        matrix_lower = matrix.lower()
        
        high_severity = [
            'matrix-1a', 'matrix-1b', 'matrix-1c', 'matrix-1d', 'matrix-1e',
            'matrix-2a', 'matrix-2b', 'matrix-2c', 'matrix-2d', 'matrix-3a'
        ]
        
        if matrix_lower in high_severity:
            return "High Severity"
        elif matrix_lower.startswith('matrix-2') or matrix_lower.startswith('matrix-3'):
            return "Medium Severity"
        else:
            return "Low Severity"
    
    def _get_processing_stage(self, days: int) -> str:
        """获取处理周期阶段"""
        if days <= 3:
            return "新票 (New Issue)"
        elif days <= 20:
            return "正常处理 (Normal Processing)"
        elif days <= 30:
            return "Long Runner 上升 (Long Runner Rise)"
        else:
            return "Long Runner 高峰 (Long Runner Peak)"
    
    def _analyze_processing_stage(self, days: int, status: str) -> str:
        """分析处理周期阶段"""
        if status in RESOLVED_PHASES:
            return f"✅ 已解决（处理周期: {days}天）"
        
        if days <= 3:
            return f"🆕 新票（{days}天）- 需要快速响应"
        elif days <= 15:
            return f"⏳ 正常处理中（{days}天）"
        elif days <= 30:
            return f"⚠️ 中期 Long Runner（{days}天）- 需要关注"
        else:
            return f"🔴 严重 Long Runner（{days}天）- 立即处理"
    
    def _generate_insights(self, defect: Dict) -> List[str]:
        """生成业务洞察"""
        insights = []
        
        # 洞察 1: 跨团队协作问题
        ecu_transfers = defect.get('ecu_no_of_changes', 0)
        domain_transfers = defect.get('domain_pingpong_count', 0)
        
        if ecu_transfers >= 5:
            insights.append(
                "这是一个**典型的跨团队协作问题**。"
                "问题在不同 ECU 之间反复转移，建议："
                "1. 召开跨团队会议，统一对问题的理解"
                "2. 指定一个负责人，避免责任推诿"
                "3. 检查是否是架构设计问题导致的边界不清晰"
            )
        
        elif ecu_transfers >= 3 and domain_transfers >= 3:
            insights.append(
                "这是一个**复杂的跨 ECU 和跨 Domain 问题**。"
                "问题涉及多个领域和团队，建议："
                "1. 建立跨团队协作机制"
                "2. 定期同步进展"
                "3. 考虑是否需要架构调整"
            )
        
        # 洞察 2: 新票快速响应
        processing_days = defect.get('processing_cycle_days', 0)
        if processing_days <= 3:
            insights.append(
                "这是一个**新票**，需要快速响应。"
                "建议："
                "1. 立即分配给相应的 ECU 负责人"
                "2. 制定 24 小时内给出初步分析的计划"
                "3. 优先处理，避免影响其他问题"
            )
        
        # 洞察 3: Long Runner 风险
        elif processing_days >= 30:
            insights.append(
                "这是一个**Long Runner**，需要重点关注。"
                "可能原因："
                "1. 问题复杂，技术难度大"
                "2. 资源不足，处理人员被其他问题占用"
                "3. 优先级不够，被低优先级问题阻塞"
                "建议："
                "1. 评估是否需要增加资源"
                "2. 检查是否有技术瓶颈"
                "3. 考虑是否需要升级处理"
            )
        
        # 洞察 4: 主票影响范围
        parent_child = defect.get('parent_child', '')
        if parent_child == 'Parent':
            child_count = defect.get('child_count', 0)
            if child_count >= 5:
                insights.append(
                    f"这是一个**大规模主票**（{child_count}个子票）。"
                    "说明问题影响范围广，可能是一个系统性问题。"
                    "建议："
                    "1. 分析子票的共同特点"
                    "2. 找出根本原因"
                    "3. 一次性解决，避免类似问题"
                )
        
        # 洞察 5: Showstopper 风险
        classification = defect.get('classification_display', '')
        if 'Showstopper' in classification:
            insights.append(
                "这是一个**Showstopper**，阻塞了项目进度或发布。"
                "建议："
                "1. 最高优先级处理"
                "2. 每日跟进进度"
                "3. 准备备选方案"
            )
        
        return insights
    
    def _generate_recommendations(self, defect: Dict) -> List[str]:
        """生成建议"""
        recommendations = []
        
        # 基于风险评估优先级
        risk_score = defect.get('topissue_risk_score', 0)
        if risk_score >= 140:
            recommendations.append(
                "🔴 **极高风险**: 立即升级到管理层，确保最高优先级处理"
            )
        elif risk_score >= 100:
            recommendations.append(
                "🟠 **高风险**: 作为本周优先级最高的 TopIssue 处理"
            )
        
        # 基于问题类型的建议
        parent_child = defect.get('parent_child', '')
        if parent_child == 'Parent':
            child_count = defect.get('child_count', 0)
            if child_count >= 5:
                recommendations.append(
                    "🎯 针对主票: 召开专题会议，分析所有子票，找出根本原因"
                )
        
        # 基于转移的建议
        ecu_transfers = defect.get('ecu_no_of_changes', 0)
        if ecu_transfers >= 3:
            recommendations.append(
                "🔧 针对频繁转移: 建立跨团队协作机制，明确责任边界"
                "避免责任推诿，加快问题解决"
            )
        
        # 基于处理周期的建议
        processing_days = defect.get('processing_cycle_days', 0)
        if processing_days >= 30:
            recommendations.append(
                "⏰ 针对长期未解决: 评估是否需要增加资源或升级处理"
                "考虑技术难度是否超出了当前团队的能力范围"
            )
        
        return recommendations
    
    def _generate_high_runner_insights(self, defect: Dict) -> List[str]:
        """生成 High Runner 洞察"""
        insights = []
        
        ecu_transfers = defect.get('ecu_no_of_changes', 0)
        ecu_path = defect.get('ecu_pingpong_display', '')
        
        if ecu_transfers >= 5:
            insights.append(
                f"极端频繁转移（{ecu_transfers}次）说明："
                f"可能是**架构设计问题**或**责任边界不清**"
            )
        
        if ecu_path and '->' in ecu_path:
            # 分析转移模式
            parts = ecu_path.split(',')
            if len(parts) >= 3:
                insights.append(
                    f"转移路径包含{len(parts)}个跳转，说明问题在{len(parts)+1}个团队间流转"
                )
        
        return insights
    
    def _generate_high_runner_recommendations(self, defect: Dict) -> List[str]:
        """生成 High Runner 建议"""
        recommendations = []
        
        ecu_transfers = defect.get('ecu_no_of_changes', 0)
        project = defect.get('project', '')
        
        if ecu_transfers >= 3:
            recommendations.append(
                f"🎯 针对{project}项目的High Runner问题："
                "建议建立定期的跨团队同步会议机制"
            )
        
        if ecu_transfers >= 5:
            recommendations.append(
                "🔧 针对极端High Runner："
                "建议进行架构审查，明确模块责任边界"
            )
        
        return recommendations
    
    def _generate_long_runner_insights(self, defect: Dict) -> List[str]:
        """生成 Long Runner 洞察"""
        insights = []
        
        processing_days = defect.get('processing_cycle_days', 0)
        matrix = defect.get('matrix', '')
        
        # 结合 Matrix 严重性分析
        if processing_days >= 30 and matrix:
            if matrix.startswith('Matrix-1'):
                insights.append(
                    "⚠️ **高危组合**: 高严重性缺陷长期未解决"
                    "可能导致严重的业务影响或客户投诉"
                )
            elif matrix.startswith('Matrix-2'):
                insights.append(
                    "⚠️ **中危组合**: 中等严重性缺陷长期未解决"
                    "可能影响项目进度和团队士气"
                )
        
        return insights
    
    def _generate_long_runner_recommendations(self, defect: Dict) -> List[str]:
        """生成 Long Runner 建议"""
        recommendations = []
        
        processing_days = defect.get('processing_cycle_days', 0)
        ecu = defect.get('ecu', '')
        tester = defect.get('tester', '')
        
        if processing_days >= 30:
            recommendations.append(
                f"⏰ 针对{ecu}的Long Runner问题："
                "建议每周审查，确保有持续进展"
            )
        
        if tester:
            recommendations.append(
                f"👤 建议与测试人员 {tester} 沟通："
                "了解阻碍解决的具体原因"
            )
        
        recommendations.append(
            "📋 建议建立 Long Runner 跟踪机制："
            "定期更新处理计划和预计解决时间"
        )
        
        return recommendations


# ============================================================================
# 工厂函数
# =============================================================================

def create_business_rule_explainer() -> BusinessRuleExplainer:
    """创建业务规则解释器"""
    return BusinessRuleExplainer()


# ============================================================================
# 示例使用
# =============================================================================

if __name__ == "__main__":
    # 示例使用
    explainer = BusinessRuleExplainer()
    
    # 示例缺陷数据
    defect_data = {
        'id': 123456,
        'name': '导航无法启动',
        'project': 'App',
        'ecu': 'IuK_HU',
        'matrix': 'Matrix-1A',
        'classification_display': 'Showstopper Confirmed',
        'is_topissue': True,
        'topissue_risk_score': 145.5,
        'is_master_score': False,
        'ecu_no_of_changes': 5,
        'domain_pingpong_count': 2,
        'processing_cycle_days': 45,
        'parent_child': 'Parent',
        'child_count': 3,
        'status_phase': '04-In Progress',
        'creation_time': '2025-03-28 10:30:00',
        'ecu_pingpong_display': '5, IuK_HU -> DIPS_HU -> IuK_HU',
        'domain_pingpong_display': '2, Navigation -> Display'
    }
    
    print("="*70)
    print("TopIssue 解释")
    print("="*70)
    print(explainer.explain_top_issue(defect_data))
    
    print("\n" + "="*70)
    print("High Runner 解释")
    print("="*70)
    print(explainer.explain_high_runner(defect_data))
    
    print("\n" + "="*70)
    print("Long Runner 解释")
    print("="*70)
    print(explainer.explain_long_runner(defect_data))

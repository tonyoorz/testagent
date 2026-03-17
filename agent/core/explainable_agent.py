"""
Explainable Agent - Provides transparency and interpretability for AI Agent decisions

Features:
1. Decision process visualization
2. Confidence assessment
3. Key findings extraction
4. User-friendly explanation generation
5. Tool execution reasoning

Author: AI Assistant
Date: 2025-02-04
"""

import re
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class KeyFinding:
    """Data class for key findings"""
    category: str  # 'insight', 'anomaly', 'trend', 'risk'
    content: str
    confidence: float
    supporting_data: Dict[str, Any]
    importance: float  # 0.0-1.0


@dataclass
class ConfidenceBreakdown:
    """Confidence score breakdown"""
    overall_confidence: float
    data_quality: float
    tool_reliability: float
    result_consistency: float
    factors: List[str]


class ExplainableAgent:
    """Explainable agent - provides transparency for AI decision-making"""
    
    def __init__(self):
        self.tool_descriptions = {
            'time_series_counts': 'Time series analysis to identify trends over time',
            'inflow_outflow_summary': 'Track how defects flow in and out of different states',
            'top_counts': 'Identify the most frequent categories or values',
            'severity_rate_by': 'Calculate severity distribution across different dimensions',
            'pick_risk_score_column': 'Select and analyze risk score metrics',
            'defect_quality_stats': 'Evaluate defect quality indicators (age, transfers, complexity)',
            'compute_defect_explore_kpis': 'Calculate comprehensive key performance indicators',
            'stacked_top_counts': 'Multi-dimensional distribution analysis',
            'nunique_by': 'Count unique values grouped by categories',
            'longrunner_phase_statistics': 'Analyze long-running defects by phase',
            'word_frequencies': 'Extract and count keyword frequencies from text',
            'defect_wordcloud_source': 'Generate word cloud data from defect descriptions'
        }
        
        self.intent_descriptions = {
            'trend': 'analyzing trends and changes over time',
            'comparison': 'comparing different categories or groups',
            'risk': 'assessing risks and priorities',
            'summary': 'providing an overview and summary',
            'quality': 'evaluating quality metrics',
            'wordcloud': 'analyzing text and keywords',
            'test': 'analyzing test results and coverage'
        }
    
    def generate_explanation(self, question: str, intents: List[str],
                           tool_executions: List[Dict], final_answer: str,
                           data_context: Optional[Dict] = None) -> str:
        """
        Generate comprehensive explanation of agent's decision process
        
        Args:
            question: User's original question
            intents: Detected intents
            tool_executions: List of tool execution results
            final_answer: Final answer generated
            data_context: Data context information
        
        Returns:
            Formatted explanation string
        """
        explanation_parts = []
        
        # 1. Question understanding
        explanation_parts.append(self._explain_question_understanding(question, intents))
        
        # 2. Analysis process
        explanation_parts.append(self._explain_analysis_process(tool_executions))
        
        # 3. Key findings
        key_findings = self._extract_key_findings(tool_executions, final_answer)
        if key_findings:
            explanation_parts.append(self._format_key_findings(key_findings))
        
        # 4. Confidence assessment
        confidence = self._calculate_confidence(tool_executions, data_context)
        explanation_parts.append(self._format_confidence_assessment(confidence))
        
        # 5. Limitations and caveats
        limitations = self._identify_limitations(tool_executions, data_context)
        if limitations:
            explanation_parts.append(self._format_limitations(limitations))
        
        return "\n\n".join(explanation_parts)
    
    def _explain_question_understanding(self, question: str, intents: List[str]) -> str:
        """Explain how the agent understood the question"""
        parts = ["## 🧠 Question Understanding"]
        
        # Summarize intents
        if intents:
            intent_descriptions = [
                self.intent_descriptions.get(intent, intent) 
                for intent in intents
            ]
            parts.append(f"Your question involves: **{', '.join(intent_descriptions)}**")
        else:
            parts.append("Your question is a general inquiry.")
        
        # Extract key entities
        entities = self._extract_entities(question)
        if entities:
            parts.append(f"Key entities mentioned: {', '.join(entities)}")
        
        return "\n".join(parts)
    
    def _explain_analysis_process(self, tool_executions: List[Dict]) -> str:
        """Explain the analysis process step by step"""
        parts = ["## 🔍 Analysis Process"]
        
        if not tool_executions:
            parts.append("No tools were executed for this analysis.")
            return "\n".join(parts)
        
        for i, execution in enumerate(tool_executions, 1):
            tool_name = execution.get('tool', 'unknown')
            success = execution.get('success', False)
            execution_time = execution.get('execution_time', 0)
            
            # Status icon
            status_icon = "✅" if success else "❌"
            
            # Tool description
            tool_desc = self.tool_descriptions.get(tool_name, 'Perform data analysis')
            
            # Format step
            step_text = f"{i}. {status_icon} **{tool_name}**"
            step_text += f"\n   - Purpose: {tool_desc}"
            
            if success:
                step_text += f"\n   - Execution time: {execution_time:.2f}s"
                
                # Add result summary if available
                result = execution.get('result', {})
                if isinstance(result, dict) and result.get('success'):
                    result_summary = self._summarize_tool_result(tool_name, result)
                    if result_summary:
                        step_text += f"\n   - Result: {result_summary}"
            else:
                error = execution.get('error', 'Unknown error')
                step_text += f"\n   - Error: {error}"
            
            parts.append(step_text)
        
        return "\n".join(parts)
    
    def _summarize_tool_result(self, tool_name: str, result: Dict) -> str:
        """Summarize tool execution result"""
        data = result.get('data', {})
        
        if not data:
            return "Completed successfully"
        
        # Tool-specific summaries
        if tool_name == 'time_series_counts':
            if isinstance(data, dict) and 'counts' in data:
                total = sum(data['counts'].values()) if data['counts'] else 0
                return f"Analyzed {total} records across time periods"
        
        elif tool_name == 'top_counts':
            if isinstance(data, dict):
                count = len(data)
                return f"Found {count} categories"
        
        elif tool_name == 'defect_quality_stats':
            if isinstance(data, dict):
                metrics = len(data)
                return f"Calculated {metrics} quality metrics"
        
        elif tool_name == 'compute_defect_explore_kpis':
            if isinstance(data, dict):
                kpis = len(data)
                return f"Computed {kpis} KPIs"
        
        return "Completed successfully"
    
    def _extract_key_findings(self, tool_executions: List[Dict], 
                             final_answer: str) -> List[KeyFinding]:
        """Extract key findings from tool executions and answer"""
        findings = []
        
        # Extract from tool results
        for execution in tool_executions:
            if not execution.get('success'):
                continue
            
            result = execution.get('result', {})
            if not isinstance(result, dict):
                continue
            
            data = result.get('data', {})
            tool_name = execution.get('tool', '')
            
            # Extract findings based on tool type
            tool_findings = self._extract_findings_from_tool(tool_name, data)
            findings.extend(tool_findings)
        
        # Extract from final answer
        answer_findings = self._extract_findings_from_answer(final_answer)
        findings.extend(answer_findings)
        
        # Deduplicate and rank by importance
        findings = self._deduplicate_findings(findings)
        findings.sort(key=lambda x: x.importance, reverse=True)
        
        return findings[:5]  # Top 5 findings
    
    def _extract_findings_from_tool(self, tool_name: str, 
                                   data: Dict) -> List[KeyFinding]:
        """Extract findings from specific tool results"""
        findings = []
        
        # This is a simplified version - in production, you'd have more sophisticated extraction
        if tool_name == 'severity_rate_by' and isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (int, float)) and value > 0.3:  # High rate
                    findings.append(KeyFinding(
                        category='risk',
                        content=f"High severity rate in {key}: {value:.1%}",
                        confidence=0.9,
                        supporting_data={'category': key, 'rate': value},
                        importance=0.8
                    ))
        
        return findings
    
    def _extract_findings_from_answer(self, answer: str) -> List[KeyFinding]:
        """Extract findings from final answer text"""
        findings = []
        
        # Look for patterns indicating important findings
        patterns = [
            (r'(critical|severe|high risk)', 'risk', 0.8),
            (r'(increasing|decreasing|trend)', 'trend', 0.7),
            (r'(anomaly|unusual|unexpected)', 'anomaly', 0.9),
            (r'(recommend|suggest|should)', 'insight', 0.6)
        ]
        
        for pattern, category, importance in patterns:
            matches = re.finditer(pattern, answer, re.IGNORECASE)
            for match in matches:
                # Extract sentence containing the match
                start = max(0, match.start() - 50)
                end = min(len(answer), match.end() + 50)
                context = answer[start:end].strip()
                
                findings.append(KeyFinding(
                    category=category,
                    content=context,
                    confidence=0.7,
                    supporting_data={},
                    importance=importance
                ))
        
        return findings
    
    def _deduplicate_findings(self, findings: List[KeyFinding]) -> List[KeyFinding]:
        """Remove duplicate findings"""
        seen = set()
        unique_findings = []
        
        for finding in findings:
            # Simple deduplication based on content similarity
            content_key = finding.content.lower()[:50]
            if content_key not in seen:
                seen.add(content_key)
                unique_findings.append(finding)
        
        return unique_findings
    
    def _format_key_findings(self, findings: List[KeyFinding]) -> str:
        """Format key findings for display"""
        parts = ["## 💡 Key Findings"]
        
        for i, finding in enumerate(findings, 1):
            icon = self._get_category_icon(finding.category)
            parts.append(f"{i}. {icon} **{finding.category.title()}**: {finding.content}")
            
            if finding.confidence < 0.7:
                parts.append(f"   ⚠️ Confidence: {finding.confidence:.0%} (moderate)")
        
        return "\n".join(parts)
    
    def _get_category_icon(self, category: str) -> str:
        """Get icon for finding category"""
        icons = {
            'risk': '⚠️',
            'trend': '📈',
            'anomaly': '🔴',
            'insight': '💡',
            'quality': '🎯'
        }
        return icons.get(category, '•')
    
    def _calculate_confidence(self, tool_executions: List[Dict],
                             data_context: Optional[Dict] = None) -> ConfidenceBreakdown:
        """Calculate overall confidence with breakdown"""
        # 1. Data quality score
        data_quality = self._assess_data_quality(data_context)
        
        # 2. Tool reliability score
        tool_reliability = self._assess_tool_reliability(tool_executions)
        
        # 3. Result consistency score
        result_consistency = self._assess_result_consistency(tool_executions)
        
        # 4. Overall confidence (weighted average)
        overall = (data_quality * 0.3 + tool_reliability * 0.4 + result_consistency * 0.3)
        
        # 5. Identify factors affecting confidence
        factors = []
        if data_quality < 0.7:
            factors.append("Limited data quality")
        if tool_reliability < 0.7:
            factors.append("Some tools failed or had issues")
        if result_consistency < 0.7:
            factors.append("Results show some inconsistencies")
        
        if not factors:
            factors.append("All indicators are positive")
        
        return ConfidenceBreakdown(
            overall_confidence=overall,
            data_quality=data_quality,
            tool_reliability=tool_reliability,
            result_consistency=result_consistency,
            factors=factors
        )
    
    def _assess_data_quality(self, data_context: Optional[Dict]) -> float:
        """Assess data quality score"""
        if not data_context:
            return 0.7  # Default moderate quality
        
        score = 0.8  # Base score
        
        # Check data size
        data_size = data_context.get('data_size', 0)
        if data_size < 10:
            score -= 0.3
        elif data_size < 100:
            score -= 0.1
        
        # Check data completeness
        missing_rate = data_context.get('missing_rate', 0)
        if missing_rate > 0.3:
            score -= 0.2
        elif missing_rate > 0.1:
            score -= 0.1
        
        return max(0.0, min(1.0, score))
    
    def _assess_tool_reliability(self, tool_executions: List[Dict]) -> float:
        """Assess tool reliability score"""
        if not tool_executions:
            return 0.5
        
        successful = sum(1 for e in tool_executions if e.get('success', False))
        total = len(tool_executions)
        
        return successful / total if total > 0 else 0.5
    
    def _assess_result_consistency(self, tool_executions: List[Dict]) -> float:
        """Assess result consistency score"""
        # Simplified version - in production, you'd check if different tools
        # produce consistent results
        
        if not tool_executions:
            return 0.5
        
        # If all tools succeeded, assume good consistency
        all_success = all(e.get('success', False) for e in tool_executions)
        
        return 0.9 if all_success else 0.6
    
    def _format_confidence_assessment(self, confidence: ConfidenceBreakdown) -> str:
        """Format confidence assessment for display"""
        parts = ["## 📊 Confidence Assessment"]
        
        # Overall confidence with visual indicator
        confidence_level = self._get_confidence_level(confidence.overall_confidence)
        parts.append(f"**Overall Confidence: {confidence.overall_confidence:.0%}** ({confidence_level})")
        
        # Breakdown
        parts.append("\n**Breakdown:**")
        parts.append(f"- Data Quality: {confidence.data_quality:.0%}")
        parts.append(f"- Tool Reliability: {confidence.tool_reliability:.0%}")
        parts.append(f"- Result Consistency: {confidence.result_consistency:.0%}")
        
        # Factors
        if confidence.factors:
            parts.append("\n**Factors:**")
            for factor in confidence.factors:
                parts.append(f"- {factor}")
        
        # Warning if low confidence
        if confidence.overall_confidence < 0.7:
            parts.append("\n⚠️ **Note**: Due to moderate confidence, please verify these findings with additional data or analysis.")
        
        return "\n".join(parts)
    
    def _get_confidence_level(self, confidence: float) -> str:
        """Get confidence level description"""
        if confidence >= 0.9:
            return "Very High"
        elif confidence >= 0.8:
            return "High"
        elif confidence >= 0.7:
            return "Moderate"
        elif confidence >= 0.6:
            return "Low"
        else:
            return "Very Low"
    
    def _identify_limitations(self, tool_executions: List[Dict],
                            data_context: Optional[Dict] = None) -> List[str]:
        """Identify limitations and caveats"""
        limitations = []
        
        # Check for failed tools
        failed_tools = [e.get('tool', 'unknown') for e in tool_executions if not e.get('success', False)]
        if failed_tools:
            limitations.append(f"Some analysis tools failed: {', '.join(failed_tools)}")
        
        # Check data limitations
        if data_context:
            data_size = data_context.get('data_size', 0)
            if data_size < 100:
                limitations.append(f"Small dataset size ({data_size} records) may limit statistical significance")
            
            missing_rate = data_context.get('missing_rate', 0)
            if missing_rate > 0.2:
                limitations.append(f"High missing data rate ({missing_rate:.0%}) may affect accuracy")
        
        # Check time range
        if data_context and 'time_range_days' in data_context:
            days = data_context['time_range_days']
            if days < 7:
                limitations.append(f"Short time range ({days} days) may not capture long-term trends")
        
        return limitations
    
    def _format_limitations(self, limitations: List[str]) -> str:
        """Format limitations for display"""
        parts = ["## ⚠️ Limitations & Caveats"]
        
        for limitation in limitations:
            parts.append(f"- {limitation}")
        
        parts.append("\nPlease consider these limitations when interpreting the results.")
        
        return "\n".join(parts)
    
    def _extract_entities(self, text: str) -> List[str]:
        """Extract entities from text"""
        entities = []
        
        # Extract project codes (G01, F30, etc.)
        project_pattern = r'\b([GFIUgfiu]\d{2})\b'
        projects = re.findall(project_pattern, text)
        entities.extend([p.upper() for p in projects])
        
        # Extract quoted strings
        quoted = re.findall(r'"([^"]+)"', text)
        entities.extend(quoted)
        
        return list(set(entities))
    
    def generate_simple_explanation(self, tool_executions: List[Dict],
                                   confidence: float) -> str:
        """Generate a simple one-paragraph explanation"""
        successful_tools = [e.get('tool', '') for e in tool_executions if e.get('success', False)]
        
        if not successful_tools:
            return "I attempted to analyze your data but encountered issues with the analysis tools."
        
        explanation = f"I analyzed your data using {len(successful_tools)} analysis tool(s): "
        explanation += ", ".join(successful_tools[:3])
        
        if len(successful_tools) > 3:
            explanation += f" and {len(successful_tools) - 3} more"
        
        explanation += f". The analysis has a confidence level of {confidence:.0%}."
        
        if confidence < 0.7:
            explanation += " Please note that the confidence is moderate, so you may want to verify these findings."
        
        return explanation


# Factory function
def create_explainable_agent() -> ExplainableAgent:
    """Create explainable agent instance"""
    return ExplainableAgent()


# Test code
if __name__ == "__main__":
    print("Explainable Agent Test")
    print("=" * 50)
    
    # Create explainable agent
    agent = create_explainable_agent()
    
    # Test data
    question = "What is the defect trend for G01 project?"
    intents = ['trend', 'comparison']
    
    tool_executions = [
        {
            'tool': 'time_series_counts',
            'success': True,
            'execution_time': 0.8,
            'result': {
                'success': True,
                'data': {'counts': {'2024-01': 10, '2024-02': 15, '2024-03': 12}}
            }
        },
        {
            'tool': 'top_counts',
            'success': True,
            'execution_time': 0.3,
            'result': {
                'success': True,
                'data': {'G01': 50, 'G20': 30, 'F30': 20}
            }
        },
        {
            'tool': 'severity_rate_by',
            'success': False,
            'execution_time': 0.0,
            'error': 'Missing required field: severity_group'
        }
    ]
    
    final_answer = "The defect trend for G01 project shows an increasing pattern. Critical defects have increased by 20% in the last month. I recommend focusing on high-risk areas."
    
    data_context = {
        'data_size': 500,
        'missing_rate': 0.05,
        'time_range_days': 90
    }
    
    # Test 1: Full explanation
    print("\n1. Testing full explanation generation:")
    explanation = agent.generate_explanation(
        question=question,
        intents=intents,
        tool_executions=tool_executions,
        final_answer=final_answer,
        data_context=data_context
    )
    print(explanation)
    
    # Test 2: Simple explanation
    print("\n2. Testing simple explanation:")
    simple = agent.generate_simple_explanation(tool_executions, 0.85)
    print(simple)
    
    print("\n✅ All tests completed!")

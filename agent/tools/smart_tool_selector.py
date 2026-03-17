"""
Smart Tool Selector - Intelligent tool selection and execution optimization

Features:
1. Intent-based tool mapping
2. Tool performance history tracking
3. Data availability validation
4. Dynamic tool combination optimization
5. Tool execution feedback learning

Author: AI Assistant
Date: 2025-02-04
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
import logging
from collections import defaultdict
import pandas as pd
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ToolExecutionRecord:
    """Record of tool execution"""
    tool_name: str
    success: bool
    execution_time: float
    result_quality: float  # 0.0-1.0
    data_size: int
    intents: List[str]
    timestamp: datetime
    error_message: str = ""


@dataclass
class ToolRecommendation:
    """Tool recommendation with confidence"""
    tool_name: str
    confidence: float
    reason: str
    estimated_time: float
    required_fields: List[str]


class SmartToolSelector:
    """Intelligent tool selector - dynamically selects optimal tool combinations based on question intent"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize smart tool selector
        
        Args:
            db_path: Path to SQLite database for storing tool performance history
        """
        if db_path is None:
            db_path = os.path.join(PROJECT_ROOT, 'database', 'tool_performance.db')
        
        # Ensure directory exists
        dirpath = os.path.dirname(db_path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        
        self.db_path = db_path
        self._init_performance_db()
        
        # Intent to tool mapping
        self.intent_tool_mapping = {
            'trend': [
                'time_series_counts',
                'inflow_outflow_summary',
                'longrunner_phase_statistics'
            ],
            'comparison': [
                'top_counts',
                'severity_rate_by',
                'nunique_by',
                'stacked_top_counts'
            ],
            'risk': [
                'pick_risk_score_column',
                'defect_quality_stats',
                'severity_rate_by'
            ],
            'summary': [
                'compute_defect_explore_kpis',
                'stacked_top_counts',
                'top_counts',
                'defect_quality_stats'
            ],
            'quality': [
                'defect_quality_stats',
                'longrunner_phase_statistics'
            ],
            'wordcloud': [
                'word_frequencies',
                'defect_wordcloud_source'
            ],
            'test': [
                'top_counts',
                'severity_rate_by'
            ]
        }
        
        # Tool requirements (required fields for each tool)
        self.tool_requirements = {
            'time_series_counts': ['created_date', 'tcreationtime', 'finished_udf_dt'],  # At least one
            'inflow_outflow_summary': ['status_phase', 'created_date'],
            'top_counts': [],  # Flexible, works with any categorical column
            'severity_rate_by': ['severity_group', 'severity'],  # At least one
            'pick_risk_score_column': ['risk_score', 'risk_score_v2', 'risk_score_nonlinear'],  # At least one
            'defect_quality_stats': [],  # Works with available quality fields
            'compute_defect_explore_kpis': [],  # Flexible
            'stacked_top_counts': [],  # Flexible
            'nunique_by': [],  # Flexible
            'longrunner_phase_statistics': ['is_long_runner', 'status_phase'],
            'word_frequencies': ['name', 'description', 'summary'],  # At least one text field
            'defect_wordcloud_source': ['name', 'description']
        }
        
        # Tool execution time estimates (seconds)
        self.tool_time_estimates = {
            'time_series_counts': 0.5,
            'inflow_outflow_summary': 0.8,
            'top_counts': 0.3,
            'severity_rate_by': 0.4,
            'pick_risk_score_column': 0.2,
            'defect_quality_stats': 0.6,
            'compute_defect_explore_kpis': 1.0,
            'stacked_top_counts': 0.5,
            'nunique_by': 0.4,
            'longrunner_phase_statistics': 0.7,
            'word_frequencies': 1.2,
            'defect_wordcloud_source': 0.8
        }
        
        logger.info(f"Smart tool selector initialized (DB: {db_path})")
    
    def _init_performance_db(self):
        """Initialize tool performance database"""
        conn = sqlite3.connect(self.db_path)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tool_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_name TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                execution_time REAL NOT NULL,
                result_quality REAL,
                data_size INTEGER,
                intents TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message TEXT
            )
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tool_name ON tool_performance(tool_name)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON tool_performance(timestamp)
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("Tool performance database initialized")
    
    def select_tools(self, question: str, intents: List[str], 
                    data_context: Dict, available_columns: List[str],
                    max_tools: int = 5) -> List[ToolRecommendation]:
        """
        Select optimal tools based on question, intents, and data context
        
        Args:
            question: User question
            intents: Detected intents
            data_context: Data context information
            available_columns: Available columns in the dataset
            max_tools: Maximum number of tools to select
        
        Returns:
            List of tool recommendations
        """
        # 1. Get base tools from intent mapping
        base_tools = self._get_base_tools_from_intents(intents)
        
        # 2. Filter by historical performance
        filtered_tools = self._filter_by_performance(base_tools)
        
        # 3. Validate data requirements
        validated_tools = self._validate_tool_requirements(filtered_tools, available_columns)
        
        # 4. Rank tools by confidence
        ranked_tools = self._rank_tools(validated_tools, question, intents, data_context)
        
        # 5. Select top tools
        selected_tools = ranked_tools[:max_tools]
        
        logger.info(f"Selected {len(selected_tools)} tools from {len(base_tools)} candidates")
        
        return selected_tools
    
    def _get_base_tools_from_intents(self, intents: List[str]) -> List[str]:
        """Get base tool set from intents"""
        tools = set()
        
        for intent in intents:
            intent_tools = self.intent_tool_mapping.get(intent, [])
            tools.update(intent_tools)
        
        # If no intents matched, use summary tools
        if not tools:
            tools.update(self.intent_tool_mapping['summary'])
        
        return list(tools)
    
    def _filter_by_performance(self, tools: List[str], 
                               min_success_rate: float = 0.7) -> List[str]:
        """Filter tools by historical performance"""
        filtered = []
        
        for tool in tools:
            success_rate = self._get_tool_success_rate(tool)
            
            # If no history, include the tool (give it a chance)
            if success_rate is None or success_rate >= min_success_rate:
                filtered.append(tool)
            else:
                logger.debug(f"Tool {tool} filtered out due to low success rate: {success_rate:.2f}")
        
        return filtered
    
    def _get_tool_success_rate(self, tool_name: str, days: int = 30) -> Optional[float]:
        """Get tool success rate from history"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=days)
            
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes
                FROM tool_performance
                WHERE tool_name = ? AND timestamp > ?
            """, (tool_name, cutoff_date))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row[0] > 0:
                return row[1] / row[0]
            
            return None  # No history
            
        except Exception as e:
            logger.error(f"Failed to get tool success rate: {e}")
            return None
    
    def _validate_tool_requirements(self, tools: List[str], 
                                   available_columns: List[str]) -> List[str]:
        """Validate that tools have required data fields"""
        validated = []
        available_set = set(available_columns)
        
        for tool in tools:
            required_fields = self.tool_requirements.get(tool, [])
            
            # If no requirements, tool is valid
            if not required_fields:
                validated.append(tool)
                continue
            
            # Check if at least one required field is available
            has_required = any(field in available_set for field in required_fields)
            
            if has_required:
                validated.append(tool)
            else:
                logger.debug(f"Tool {tool} missing required fields: {required_fields}")
        
        return validated
    
    def _rank_tools(self, tools: List[str], question: str, 
                   intents: List[str], data_context: Dict) -> List[ToolRecommendation]:
        """Rank tools by confidence and relevance"""
        recommendations = []
        
        for tool in tools:
            # Calculate confidence score
            confidence = self._calculate_tool_confidence(tool, question, intents, data_context)
            
            # Get estimated execution time
            estimated_time = self._get_estimated_execution_time(tool, data_context)
            
            # Get required fields
            required_fields = self.tool_requirements.get(tool, [])
            
            # Generate reason
            reason = self._generate_selection_reason(tool, intents)
            
            recommendation = ToolRecommendation(
                tool_name=tool,
                confidence=confidence,
                reason=reason,
                estimated_time=estimated_time,
                required_fields=required_fields
            )
            
            recommendations.append(recommendation)
        
        # Sort by confidence (descending)
        recommendations.sort(key=lambda x: x.confidence, reverse=True)
        
        return recommendations
    
    def _calculate_tool_confidence(self, tool: str, question: str,
                                  intents: List[str], data_context: Dict) -> float:
        """Calculate confidence score for tool selection"""
        confidence = 0.5  # Base confidence
        
        # 1. Intent match bonus
        for intent in intents:
            if tool in self.intent_tool_mapping.get(intent, []):
                confidence += 0.15
        
        # 2. Historical performance bonus
        success_rate = self._get_tool_success_rate(tool)
        if success_rate is not None:
            confidence += success_rate * 0.2
        
        # 3. Question keyword match bonus
        question_lower = question.lower()
        tool_keywords = {
            'time_series_counts': ['trend', 'over time', 'history', '趋势', '历史'],
            'top_counts': ['top', 'most', 'distribution', '分布', '排名'],
            'severity_rate_by': ['severity', 'critical', '严重性'],
            'word_frequencies': ['word', 'keyword', 'text', '关键词', '词频']
        }
        
        if tool in tool_keywords:
            if any(kw in question_lower for kw in tool_keywords[tool]):
                confidence += 0.1
        
        # 4. Data size penalty for expensive tools
        data_size = data_context.get('data_size', 0)
        if data_size > 10000 and tool in ['word_frequencies', 'defect_wordcloud_source']:
            confidence -= 0.1
        
        # Cap confidence at 1.0
        return min(confidence, 1.0)
    
    def _get_estimated_execution_time(self, tool: str, data_context: Dict) -> float:
        """Get estimated execution time for tool"""
        base_time = self.tool_time_estimates.get(tool, 1.0)
        
        # Adjust based on data size
        data_size = data_context.get('data_size', 1000)
        size_factor = max(1.0, data_size / 1000)
        
        return base_time * size_factor
    
    def _generate_selection_reason(self, tool: str, intents: List[str]) -> str:
        """Generate human-readable reason for tool selection"""
        reasons = {
            'time_series_counts': 'Analyze time series trends',
            'inflow_outflow_summary': 'Track inflow/outflow patterns',
            'top_counts': 'Identify top categories',
            'severity_rate_by': 'Analyze severity distribution',
            'pick_risk_score_column': 'Assess risk scores',
            'defect_quality_stats': 'Evaluate defect quality metrics',
            'compute_defect_explore_kpis': 'Calculate comprehensive KPIs',
            'stacked_top_counts': 'Multi-dimensional distribution analysis',
            'nunique_by': 'Count unique values by category',
            'longrunner_phase_statistics': 'Analyze long-running defects',
            'word_frequencies': 'Extract keyword frequencies',
            'defect_wordcloud_source': 'Generate word cloud data'
        }
        
        base_reason = reasons.get(tool, 'Perform data analysis')
        
        # Add intent context
        if intents:
            intent_str = ', '.join(intents)
            return f"{base_reason} (for {intent_str})"
        
        return base_reason
    
    def record_execution(self, tool_name: str, success: bool, 
                        execution_time: float, result_quality: float,
                        data_size: int, intents: List[str],
                        error_message: str = ""):
        """
        Record tool execution result for learning
        
        Args:
            tool_name: Name of the tool
            success: Whether execution succeeded
            execution_time: Execution time in seconds
            result_quality: Quality score (0.0-1.0)
            data_size: Size of input data
            intents: Question intents
            error_message: Error message if failed
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO tool_performance
                (tool_name, success, execution_time, result_quality, data_size, intents, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                tool_name,
                success,
                execution_time,
                result_quality,
                data_size,
                json.dumps(intents),
                error_message
            ))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Recorded execution: {tool_name} (success: {success})")
            
        except Exception as e:
            logger.error(f"Failed to record execution: {e}")
    
    def get_tool_statistics(self, tool_name: Optional[str] = None, 
                           days: int = 30) -> Dict[str, Any]:
        """Get tool performance statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=days)
            
            if tool_name:
                cursor.execute("""
                    SELECT 
                        tool_name,
                        COUNT(*) as total_executions,
                        SUM(CASE WHEN success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
                        AVG(execution_time) as avg_execution_time,
                        AVG(result_quality) as avg_quality
                    FROM tool_performance
                    WHERE tool_name = ? AND timestamp > ?
                    GROUP BY tool_name
                """, (tool_name, cutoff_date))
            else:
                cursor.execute("""
                    SELECT 
                        tool_name,
                        COUNT(*) as total_executions,
                        SUM(CASE WHEN success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
                        AVG(execution_time) as avg_execution_time,
                        AVG(result_quality) as avg_quality
                    FROM tool_performance
                    WHERE timestamp > ?
                    GROUP BY tool_name
                    ORDER BY total_executions DESC
                """, (cutoff_date,))
            
            rows = cursor.fetchall()
            conn.close()
            
            if tool_name:
                if rows:
                    row = rows[0]
                    return {
                        'tool_name': row[0],
                        'total_executions': row[1],
                        'success_rate': row[2] or 0.0,
                        'avg_execution_time': row[3] or 0.0,
                        'avg_quality': row[4] or 0.0
                    }
                return {}
            else:
                stats = []
                for row in rows:
                    stats.append({
                        'tool_name': row[0],
                        'total_executions': row[1],
                        'success_rate': row[2] or 0.0,
                        'avg_execution_time': row[3] or 0.0,
                        'avg_quality': row[4] or 0.0
                    })
                return {'tools': stats, 'period_days': days}
            
        except Exception as e:
            logger.error(f"Failed to get tool statistics: {e}")
            return {}
    
    def get_tool_recommendations_for_similar_questions(self, 
                                                      question: str,
                                                      top_k: int = 5) -> List[str]:
        """Get tool recommendations based on similar historical questions"""
        # This is a simplified version - in production, you'd use embeddings
        # or more sophisticated similarity matching
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get tools that succeeded recently
            cursor.execute("""
                SELECT tool_name, COUNT(*) as count
                FROM tool_performance
                WHERE success = 1 
                AND timestamp > datetime('now', '-30 days')
                GROUP BY tool_name
                ORDER BY count DESC
                LIMIT ?
            """, (top_k,))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [row[0] for row in rows]
            
        except Exception as e:
            logger.error(f"Failed to get tool recommendations: {e}")
            return []
    
    def cleanup_old_records(self, days: int = 90):
        """Clean up old performance records"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cutoff_date = datetime.now() - timedelta(days=days)
            
            cursor.execute("""
                DELETE FROM tool_performance
                WHERE timestamp < ?
            """, (cutoff_date,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            logger.info(f"Cleaned up {deleted_count} old tool performance records")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup records: {e}")
            return 0


class ToolExecutionFeedback:
    """Tool execution feedback system - learns optimal tool combinations"""
    
    def __init__(self, selector: SmartToolSelector):
        self.selector = selector
        self.session_feedback = []
    
    def record_feedback(self, tools_used: List[str], intents: List[str],
                       overall_quality: float, user_satisfied: bool):
        """Record feedback on tool combination"""
        feedback = {
            'tools_used': tools_used,
            'intents': intents,
            'overall_quality': overall_quality,
            'user_satisfied': user_satisfied,
            'timestamp': datetime.now()
        }
        
        self.session_feedback.append(feedback)
        
        # Learn from feedback
        if user_satisfied and overall_quality > 0.7:
            # This combination worked well
            logger.info(f"Good tool combination: {tools_used} for intents {intents}")
    
    def get_best_combinations(self, intent: str, top_k: int = 3) -> List[List[str]]:
        """Get best tool combinations for an intent"""
        # Filter feedback by intent
        relevant_feedback = [
            f for f in self.session_feedback 
            if intent in f['intents'] and f['user_satisfied']
        ]
        
        # Sort by quality
        relevant_feedback.sort(key=lambda x: x['overall_quality'], reverse=True)
        
        # Return top combinations
        return [f['tools_used'] for f in relevant_feedback[:top_k]]


# Factory functions
def create_smart_tool_selector(db_path: Optional[str] = None) -> SmartToolSelector:
    """Create smart tool selector instance"""
    return SmartToolSelector(db_path)


def create_tool_feedback_system(selector: SmartToolSelector) -> ToolExecutionFeedback:
    """Create tool execution feedback system"""
    return ToolExecutionFeedback(selector)


# Test code
if __name__ == "__main__":
    print("Smart Tool Selector Test")
    print("=" * 50)
    
    # Create selector
    selector = create_smart_tool_selector(db_path="test_tool_performance.db")
    
    # Test 1: Select tools for trend analysis
    print("\n1. Testing tool selection for trend analysis:")
    recommendations = selector.select_tools(
        question="What is the defect trend over time?",
        intents=['trend', 'summary'],
        data_context={'data_size': 5000},
        available_columns=['created_date', 'project', 'severity_group', 'status_phase']
    )
    
    print(f"Selected {len(recommendations)} tools:")
    for rec in recommendations:
        print(f"  - {rec.tool_name} (confidence: {rec.confidence:.2f})")
        print(f"    Reason: {rec.reason}")
        print(f"    Estimated time: {rec.estimated_time:.2f}s")
    
    # Test 2: Record execution
    print("\n2. Testing execution recording:")
    selector.record_execution(
        tool_name='time_series_counts',
        success=True,
        execution_time=0.8,
        result_quality=0.9,
        data_size=5000,
        intents=['trend']
    )
    print("✅ Execution recorded")
    
    # Test 3: Get statistics
    print("\n3. Testing statistics retrieval:")
    stats = selector.get_tool_statistics('time_series_counts')
    print(f"Tool statistics: {stats}")
    
    # Test 4: Tool feedback system
    print("\n4. Testing feedback system:")
    feedback = create_tool_feedback_system(selector)
    feedback.record_feedback(
        tools_used=['time_series_counts', 'top_counts'],
        intents=['trend', 'summary'],
        overall_quality=0.85,
        user_satisfied=True
    )
    print("✅ Feedback recorded")
    
    print("\n✅ All tests completed!")
    
    # Cleanup test database
    import os
    if os.path.exists("test_tool_performance.db"):
        os.remove("test_tool_performance.db")
        print("Test database cleaned up")

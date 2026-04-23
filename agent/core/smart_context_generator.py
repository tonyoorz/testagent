"""
Smart Context Generator - Intelligent data context generation for AI Agent

Features:
1. Intent-driven field selection (with semantic detection)
2. Question keyword extraction and data filtering
3. Automatic anomaly detection
4. Concise but information-rich context generation
5. Hybrid retrieval strategy (structured + semantic)

Author: AI Assistant
Date: 2025-02-04
Updated: 2025-02-21 - Integrated semantic intent detection and hybrid retriever
"""

import re
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
import logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SemanticIntentDetector removed — keyword fallback is sufficient and avoids
# duplicating the intent-detection work that LLM function-calling already does.
SEMANTIC_INTENT_AVAILABLE = False

try:
    from agent.core.hybrid_retriever import HybridRetriever, create_hybrid_retriever
    HYBRID_RETRIEVER_AVAILABLE = True
except ImportError:
    HYBRID_RETRIEVER_AVAILABLE = False
    logger.info("HybridRetriever not available, using keyword fallback")


class SmartContextGenerator:
    """Intelligent context generator - dynamically generates most relevant data context based on questions"""

    def __init__(self, use_semantic_intent: bool = True, use_hybrid_retriever: bool = True):
        """
        Initialize SmartContextGenerator

        Args:
            use_semantic_intent: Whether to use semantic intent detection
            use_hybrid_retriever: Whether to use hybrid retrieval strategy
        """
        # Semantic intent detector removed (LLM function-calling handles this).
        self.semantic_intent_detector = None

        # Initialize hybrid retriever
        self.hybrid_retriever = None
        if use_hybrid_retriever and HYBRID_RETRIEVER_AVAILABLE:
            try:
                self.hybrid_retriever = HybridRetriever()
                logger.info("✅ HybridRetriever initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize HybridRetriever: {e}")

        self.intent_field_mapping = {
            'trend': ['created_date', 'tcreationtime', 'finished_udf_dt', 'status_phase', 'matrix_display'],
            'comparison': ['project', 'tproject', 'ecu', 'domain', 'domain_display', 'aida_english', 'fv'],
            'risk': ['severity_group', 'severity', 'matrix_display', 'is_topissue', 'risk_score', 'is_long_runner'],
            'summary': ['status_phase', 'severity_group', 'matrix_display', 'project', 'is_topissue'],
            'quality': ['defect_age_days', 'ecu_transfer_count', 'domain_transfer_count', 'child_count'],
            'test': ['run_status', 'status', 'test_coverage', 'pass_rate', 'failure_rate']
        }
        
        self.keyword_field_mapping = {
            'project': ['project', 'tproject'],
            'ecu': ['ecu', 'ecu_display'],
            'domain': ['domain', 'domain_display'],
            'aida': ['aida_english', 'aida_chinese'],
            'matrix': ['matrix_display', 'matrix'],
            'severity': ['severity_group', 'severity'],
            'topissue': ['is_topissue'],
            'longrunner': ['is_long_runner'],
            'status': ['status_phase', 'status'],
            'fv': ['fv'],
            'test': ['run_status', 'test_name', 'test_type']
        }
        
        self.anomaly_thresholds = {
            'critical_rate_high': 0.3,
            'topissue_concentration': 0.2,
            'longrunner_rate_high': 0.15,
            'failure_rate_high': 0.4,
            'single_project_dominance': 0.5
        }
    
    def generate_context(self, question: str, full_data: pd.DataFrame,
                        intents: Optional[List[str]] = None,
                        max_context_length: int = 2000,
                        dataset_key: Optional[str] = None) -> str:
        """
        Generate question-relevant concise context
        
        Args:
            question: User question
            full_data: Complete dataset
            intents: Detected intents (if None, will auto-detect)
            max_context_length: Maximum context length (characters)
        
        Returns:
            Formatted context string
        """
        if full_data is None or full_data.empty:
            return "No data available."
        
        # Auto-detect intents if not provided
        if intents is None:
            intents = self._detect_intents(question)
        
        # Extract keywords
        keywords = self._extract_keywords(question)

        # Filter data based on keywords (using hybrid retrieval if available)
        filtered_data = self._filter_by_keywords(full_data, keywords, question=question, dataset_key=dataset_key)
        
        # If filtering is too aggressive, use full data
        if len(filtered_data) < len(full_data) * 0.1 and len(filtered_data) < 50:
            filtered_data = full_data
            logger.info(f"Keyword filtering too aggressive, using full dataset: {len(full_data)} records")
        
        # Generate context parts
        context_parts = []
        
        # 1. Basic statistics (always include)
        context_parts.extend(self._generate_basic_stats(filtered_data, full_data))
        
        # 2. Intent-specific statistics
        if 'trend' in intents:
            context_parts.extend(self._generate_trend_context(filtered_data))
        if 'risk' in intents:
            context_parts.extend(self._generate_risk_context(filtered_data))
        if 'comparison' in intents:
            context_parts.extend(self._generate_comparison_context(filtered_data))
        if 'summary' in intents:
            context_parts.extend(self._generate_summary_context(filtered_data))
        if 'quality' in intents:
            context_parts.extend(self._generate_quality_context(filtered_data))
        if 'test' in intents:
            context_parts.extend(self._generate_test_context(filtered_data))
        
        # 3. Automatic anomaly detection
        anomalies = self._detect_anomalies(filtered_data)
        if anomalies:
            context_parts.append("\n⚠️ Detected anomalies:")
            context_parts.extend([f"  - {a}" for a in anomalies[:3]])
        
        # 4. Keyword-specific context
        if keywords:
            context_parts.extend(self._generate_keyword_context(filtered_data, keywords))
        
        # Combine and truncate if needed
        full_context = "\n".join(context_parts)
        
        if len(full_context) > max_context_length:
            full_context = full_context[:max_context_length] + "\n... (context truncated)"
        
        return full_context
    
    def _detect_intents(self, question: str) -> List[str]:
        """
        Auto-detect question intents using semantic detection with keyword fallback
        """
        # 优先使用语义意图检测
        if self.semantic_intent_detector:
            try:
                semantic_results = self.semantic_intent_detector.detect_intent(question)
                intents = [intent for intent, confidence in semantic_results if intent != 'clarification']
                if intents:
                    logger.debug(f"Semantic intent detection: {intents}")
                    return intents
            except Exception as e:
                logger.warning(f"Semantic intent detection failed, falling back to keywords: {e}")

        # 关键词匹配回退
        question_lower = question.lower()
        intents = []

        trend_keywords = ['trend', 'change', 'evolution', 'over time', 'history', '趋势', '变化', '演变', '历史']
        risk_keywords = ['risk', 'critical', 'severe', 'topissue', 'high priority', '风险', '严重', '高优先级']
        comparison_keywords = ['compare', 'versus', 'vs', 'difference', 'between', '对比', '比较', '差异']
        summary_keywords = ['summary', 'overview', 'total', 'overall', '总结', '概览', '整体']
        quality_keywords = ['quality', 'age', 'transfer', 'complexity', '质量', '年龄', '转移', '复杂度']
        test_keywords = ['test', 'coverage', 'pass', 'fail', '测试', '覆盖率', '通过', '失败']

        if any(kw in question_lower for kw in trend_keywords):
            intents.append('trend')
        if any(kw in question_lower for kw in risk_keywords):
            intents.append('risk')
        if any(kw in question_lower for kw in comparison_keywords):
            intents.append('comparison')
        if any(kw in question_lower for kw in summary_keywords):
            intents.append('summary')
        if any(kw in question_lower for kw in quality_keywords):
            intents.append('quality')
        if any(kw in question_lower for kw in test_keywords):
            intents.append('test')

        # Default to summary if no intent detected
        if not intents:
            intents.append('summary')

        return intents
    
    def _extract_keywords(self, question: str) -> Set[str]:
        """Extract keywords from question"""
        keywords = set()
        question_lower = question.lower()
        
        # Extract entity names (project names, ECU names, etc.)
        # Common BMW project patterns
        project_patterns = [
            r'\b(g\d{2})\b',  # G01, G20, etc.
            r'\b(f\d{2})\b',  # F30, F90, etc.
            r'\b(i\d{2})\b',  # i20, i30, etc.
            r'\b(u\d{2})\b',  # U11, etc.
        ]
        
        for pattern in project_patterns:
            matches = re.findall(pattern, question_lower)
            keywords.update(matches)
        
        # Extract common domain keywords
        for keyword_type, fields in self.keyword_field_mapping.items():
            if keyword_type in question_lower:
                keywords.add(keyword_type)
        
        # Extract quoted strings
        quoted = re.findall(r'"([^"]+)"', question)
        keywords.update([q.lower() for q in quoted])
        
        return keywords
    
    def _filter_by_keywords(self, data: pd.DataFrame, keywords: Set[str],
                            question: Optional[str] = None,
                            dataset_key: Optional[str] = None) -> pd.DataFrame:
        """
        Filter data based on keywords using hybrid retrieval strategy

        Args:
            data: Full dataset
            keywords: Extracted keywords
            question: Original question (for semantic retrieval)

        Returns:
            Filtered dataset
        """
        if not keywords or data.empty:
            return data

        # 优先使用混合检索器
        if self.hybrid_retriever and question:
            try:
                # 构建结构化约束
                constraints = self.hybrid_retriever.build_structured_constraints(
                    question, data.columns.tolist()
                )

                # 执行混合检索
                result = self.hybrid_retriever.retrieve(
                    question=question,
                    data=data,
                    structured_constraints=constraints if constraints else None,
                    semantic_top_k=50,
                    dataset_key=dataset_key
                )

                logger.debug(f"Hybrid retrieval: {result.method}, "
                           f"{result.filtered_count}/{result.original_count} records")
                return result.data

            except Exception as e:
                logger.warning(f"Hybrid retrieval failed, falling back to keyword: {e}")

        # 关键词匹配回退
        mask = pd.Series([False] * len(data), index=data.index)

        for keyword in keywords:
            # Search in relevant columns
            for col in data.columns:
                if data[col].dtype == 'object':
                    try:
                        col_mask = data[col].astype(str).str.lower().str.contains(keyword, na=False, regex=False)
                        mask = mask | col_mask
                    except:
                        continue

        filtered = data[mask]
        return filtered if not filtered.empty else data
    
    def _generate_basic_stats(self, filtered_data: pd.DataFrame, 
                             full_data: pd.DataFrame) -> List[str]:
        """Generate basic statistics"""
        stats = []
        
        if len(filtered_data) < len(full_data):
            stats.append(f"Data scale: {len(filtered_data)} records (filtered from {len(full_data)} total)")
        else:
            stats.append(f"Data scale: {len(filtered_data)} records")
        
        # Time range
        time_cols = ['created_date', 'tcreationtime', 'finished_udf_dt']
        for col in time_cols:
            if col in filtered_data.columns:
                try:
                    dates = pd.to_datetime(filtered_data[col], errors='coerce')
                    dates = dates.dropna()
                    if not dates.empty:
                        min_date = dates.min().strftime('%Y-%m-%d')
                        max_date = dates.max().strftime('%Y-%m-%d')
                        stats.append(f"Time range: {min_date} to {max_date}")
                        break
                except:
                    continue
        
        return stats
    
    def _generate_trend_context(self, data: pd.DataFrame) -> List[str]:
        """Generate trend-related context"""
        context = ["\n📈 Trend analysis:"]
        
        # Find time column
        time_col = None
        for col in ['created_date', 'tcreationtime', 'finished_udf_dt']:
            if col in data.columns:
                time_col = col
                break
        
        if time_col:
            try:
                dates = pd.to_datetime(data[time_col], errors='coerce')
                data_with_date = data.copy()
                data_with_date['_date'] = dates
                data_with_date = data_with_date[data_with_date['_date'].notna()]
                
                if not data_with_date.empty:
                    # Weekly trend
                    data_with_date['_week'] = data_with_date['_date'].dt.to_period('W')
                    weekly_counts = data_with_date.groupby('_week').size()
                    
                    if len(weekly_counts) >= 2:
                        recent_avg = weekly_counts.tail(4).mean()
                        earlier_avg = weekly_counts.head(4).mean() if len(weekly_counts) >= 8 else weekly_counts.mean()
                        
                        if recent_avg > earlier_avg * 1.2:
                            context.append(f"  - Recent trend: ↗️ Increasing (recent avg: {recent_avg:.1f}/week vs earlier: {earlier_avg:.1f}/week)")
                        elif recent_avg < earlier_avg * 0.8:
                            context.append(f"  - Recent trend: ↘️ Decreasing (recent avg: {recent_avg:.1f}/week vs earlier: {earlier_avg:.1f}/week)")
                        else:
                            context.append(f"  - Recent trend: → Stable (avg: {recent_avg:.1f}/week)")
            except Exception as e:
                logger.debug(f"Trend analysis error: {e}")
        
        return context
    
    def _generate_risk_context(self, data: pd.DataFrame) -> List[str]:
        """Generate risk-related context"""
        context = ["\n⚠️ Risk analysis:"]
        
        # Severity distribution
        severity_col = 'severity_group' if 'severity_group' in data.columns else 'severity' if 'severity' in data.columns else None
        if severity_col:
            severity_counts = data[severity_col].value_counts()
            critical_count = severity_counts.get('Critical', 0)
            critical_rate = critical_count / len(data) if len(data) > 0 else 0
            context.append(f"  - Critical defects: {critical_count} ({critical_rate:.1%})")
        
        # TopIssue
        if 'is_topissue' in data.columns:
            topissue_count = int(pd.to_numeric(data['is_topissue'], errors='coerce').fillna(0).sum())
            topissue_rate = topissue_count / len(data) if len(data) > 0 else 0
            context.append(f"  - TopIssue: {topissue_count} ({topissue_rate:.1%})")
        
        # LongRunner
        if 'is_long_runner' in data.columns:
            lr_count = int(pd.to_numeric(data['is_long_runner'], errors='coerce').fillna(0).sum())
            lr_rate = lr_count / len(data) if len(data) > 0 else 0
            context.append(f"  - LongRunner: {lr_count} ({lr_rate:.1%})")
        
        # Risk score distribution
        risk_col = None
        for col in ['risk_score', 'risk_score_v2', 'risk_score_nonlinear']:
            if col in data.columns:
                risk_col = col
                break
        
        if risk_col:
            try:
                risk_scores = pd.to_numeric(data[risk_col], errors='coerce').dropna()
                if not risk_scores.empty:
                    high_risk = (risk_scores >= 100).sum()
                    context.append(f"  - High risk (score≥100): {high_risk} ({high_risk/len(risk_scores):.1%})")
            except:
                pass
        
        return context
    
    def _generate_comparison_context(self, data: pd.DataFrame) -> List[str]:
        """Generate comparison-related context"""
        context = ["\n🔄 Comparison data:"]
        
        # Project distribution
        project_col = 'project' if 'project' in data.columns else 'tproject' if 'tproject' in data.columns else None
        if project_col:
            project_counts = data[project_col].value_counts().head(5)
            context.append(f"  - Top 5 projects: {dict(project_counts)}")
        
        # Domain distribution
        domain_col = 'domain_display' if 'domain_display' in data.columns else 'domain' if 'domain' in data.columns else None
        if domain_col:
            domain_counts = data[domain_col].value_counts().head(3)
            context.append(f"  - Top 3 domains: {dict(domain_counts)}")
        
        return context
    
    def _generate_summary_context(self, data: pd.DataFrame) -> List[str]:
        """Generate summary context"""
        context = ["\n📊 Summary:"]
        
        # Status distribution
        status_col = 'status_phase' if 'status_phase' in data.columns else 'status' if 'status' in data.columns else None
        if status_col:
            status_counts = data[status_col].value_counts().head(5)
            context.append(f"  - Status distribution: {dict(status_counts)}")
        
        # Matrix distribution
        if 'matrix_display' in data.columns:
            matrix_counts = data['matrix_display'].value_counts().head(5)
            context.append(f"  - Matrix Top 5: {dict(matrix_counts)}")
        
        return context
    
    def _generate_quality_context(self, data: pd.DataFrame) -> List[str]:
        """Generate quality-related context"""
        context = ["\n🎯 Quality metrics:"]
        
        # Defect age
        if 'defect_age_days' in data.columns:
            try:
                ages = pd.to_numeric(data['defect_age_days'], errors='coerce').dropna()
                if not ages.empty:
                    context.append(f"  - Avg defect age: {ages.mean():.1f} days (median: {ages.median():.1f})")
            except:
                pass
        
        # Transfer counts
        if 'ecu_transfer_count' in data.columns:
            try:
                transfers = pd.to_numeric(data['ecu_transfer_count'], errors='coerce').dropna()
                if not transfers.empty:
                    high_transfer = (transfers >= 3).sum()
                    context.append(f"  - High ECU transfers (≥3): {high_transfer} ({high_transfer/len(transfers):.1%})")
            except:
                pass
        
        return context
    
    def _generate_test_context(self, data: pd.DataFrame) -> List[str]:
        """Generate test-related context"""
        context = ["\n🧪 Test metrics:"]
        
        # Test status
        status_col = 'run_status' if 'run_status' in data.columns else 'status' if 'status' in data.columns else None
        if status_col:
            status_lower = data[status_col].astype(str).str.lower()
            failure_keywords = ['fail', 'failed', 'error', 'blocked', 'aborted', 'ng']
            is_fail = status_lower.apply(lambda x: any(k in x for k in failure_keywords))
            
            total = len(data)
            failures = is_fail.sum()
            failure_rate = failures / total if total > 0 else 0
            context.append(f"  - Test failures: {failures}/{total} ({failure_rate:.1%})")
        
        return context
    
    def _generate_keyword_context(self, data: pd.DataFrame, keywords: Set[str]) -> List[str]:
        """Generate keyword-specific context"""
        context = []
        
        if keywords:
            context.append(f"\n🔍 Keyword filter applied: {', '.join(list(keywords)[:5])}")
        
        return context
    
    def _detect_anomalies(self, data: pd.DataFrame) -> List[str]:
        """Automatically detect data anomalies"""
        anomalies = []
        
        if data.empty:
            return anomalies
        
        # 1. Critical defect rate abnormally high
        severity_col = 'severity_group' if 'severity_group' in data.columns else 'severity' if 'severity' in data.columns else None
        if severity_col:
            try:
                critical_mask = data[severity_col].astype(str).str.lower().str.contains('critical', na=False)
                critical_rate = critical_mask.mean()
                if critical_rate > self.anomaly_thresholds['critical_rate_high']:
                    anomalies.append(f"Critical defect rate abnormally high: {critical_rate:.1%} (threshold: {self.anomaly_thresholds['critical_rate_high']:.1%})")
            except:
                pass
        
        # 2. TopIssue concentration anomaly
        if 'is_topissue' in data.columns:
            project_col = 'project' if 'project' in data.columns else 'tproject' if 'tproject' in data.columns else None
            if project_col:
                try:
                    topissue_data = data[pd.to_numeric(data['is_topissue'], errors='coerce').fillna(0) == 1]
                    if len(topissue_data) > 0:
                        topissue_by_project = topissue_data.groupby(project_col).size()
                        max_project = topissue_by_project.idxmax()
                        max_count = topissue_by_project.max()
                        max_rate = max_count / len(data)
                        
                        if max_rate > self.anomaly_thresholds['topissue_concentration']:
                            anomalies.append(f"TopIssue concentrated in {max_project}: {max_count} ({max_rate:.1%})")
                except:
                    pass
        
        # 3. LongRunner rate abnormally high
        if 'is_long_runner' in data.columns:
            try:
                lr_rate = pd.to_numeric(data['is_long_runner'], errors='coerce').fillna(0).mean()
                if lr_rate > self.anomaly_thresholds['longrunner_rate_high']:
                    anomalies.append(f"LongRunner rate abnormally high: {lr_rate:.1%}")
            except:
                pass
        
        # 4. Single project dominance
        project_col = 'project' if 'project' in data.columns else 'tproject' if 'tproject' in data.columns else None
        if project_col:
            try:
                project_counts = data[project_col].value_counts()
                if len(project_counts) > 0:
                    top_project_rate = project_counts.iloc[0] / len(data)
                    if top_project_rate > self.anomaly_thresholds['single_project_dominance']:
                        anomalies.append(f"Single project dominance: {project_counts.index[0]} accounts for {top_project_rate:.1%}")
            except:
                pass
        
        # 5. Test failure rate abnormally high
        status_col = 'run_status' if 'run_status' in data.columns else 'status' if 'status' in data.columns else None
        if status_col:
            try:
                status_lower = data[status_col].astype(str).str.lower()
                failure_keywords = ['fail', 'failed', 'error', 'blocked', 'aborted', 'ng']
                is_fail = status_lower.apply(lambda x: any(k in x for k in failure_keywords))
                failure_rate = is_fail.mean()
                
                if failure_rate > self.anomaly_thresholds['failure_rate_high']:
                    anomalies.append(f"Test failure rate abnormally high: {failure_rate:.1%}")
            except:
                pass
        
        return anomalies


# Factory function
def create_smart_context_generator(use_semantic_intent: bool = True,
                                   use_hybrid_retriever: bool = True) -> SmartContextGenerator:
    """
    Create smart context generator instance

    Args:
        use_semantic_intent: Whether to use semantic intent detection
        use_hybrid_retriever: Whether to use hybrid retrieval strategy
    """
    return SmartContextGenerator(
        use_semantic_intent=use_semantic_intent,
        use_hybrid_retriever=use_hybrid_retriever
    )


# Test code
if __name__ == "__main__":
    print("Smart Context Generator Test")
    print("=" * 50)
    
    # Create test data
    test_data = pd.DataFrame({
        'project': ['G01', 'G20', 'G01', 'F30', 'G01'] * 20,
        'severity_group': ['Critical', 'Major', 'Minor', 'Critical', 'Major'] * 20,
        'is_topissue': [1, 0, 0, 1, 0] * 20,
        'status_phase': ['Open', 'In Progress', 'Closed', 'Open', 'In Progress'] * 20,
        'matrix_display': ['1A', '1B', '2A', '1A', '1C'] * 20,
        'created_date': pd.date_range('2024-01-01', periods=100, freq='D')
    })
    
    generator = create_smart_context_generator()
    
    # Test 1: Trend question
    print("\n1. Testing trend question:")
    question1 = "What is the trend of defects over time?"
    context1 = generator.generate_context(question1, test_data)
    print(context1)
    
    # Test 2: Risk question
    print("\n2. Testing risk question:")
    question2 = "Analyze the high risk defects"
    context2 = generator.generate_context(question2, test_data)
    print(context2)
    
    # Test 3: Comparison question
    print("\n3. Testing comparison question:")
    question3 = "Compare defects across different projects"
    context3 = generator.generate_context(question3, test_data)
    print(context3)
    
    # Test 4: Keyword filtering
    print("\n4. Testing keyword filtering:")
    question4 = "Show me G01 project defects"
    context4 = generator.generate_context(question4, test_data)
    print(context4)
    
    print("\n✅ All tests completed!")

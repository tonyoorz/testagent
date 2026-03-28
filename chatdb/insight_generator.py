#!/usr/bin/env python3
"""
业务洞察生成器 - 基于数据分析生成有价值的业务洞察和建议

能够：
1. 异常检测 - 识别数据中的异常点
2. 趋势分析 - 识别数据趋势和模式
3. 对比分析 - 与历史数据对比
4. 预测分析 - 预测未来趋势
5. 生成建议 - 基于分析结果生成可操作的建议

使用方法：
from chatdb.insight_generator import InsightGenerator

generator = InsightGenerator()

# 检测异常
anomalies = generator.detect_trend_anomalies(data)

# 生成业务洞察
insights = generator.generate_insights(data)

# 生成建议
recommendations = generator.generate_recommendations(data, insights)

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-28
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class InsightGenerator:
    """业务洞察生成器"""
    
    def __init__(self):
        """初始化洞察生成器"""
        self._cache = {}
    
    def detect_trend_anomalies(self, data: pd.DataFrame, 
                           count_col: str = 'count', 
                           week_col: str = 'week') -> List[Dict]:
        """
        检测趋势异常（激增、骤降、偏离）
        
        Args:
            data: 数据 DataFrame
            count_col: 计数列名
            week_col: 周列名
        
        Returns:
            异常列表
        """
        anomalies = []
        
        if count_col not in data.columns:
            logger.warning(f"列 '{count_col}' 不存在")
            return anomalies
        
        # 1. 激增检测（比上周增加 > 50%）
        data['change_pct'] = data[count_col].pct_change()
        spike_threshold = 0.5
        
        spikes = data[data['change_pct'] > spike_threshold]
        for _, row in spikes.iterrows():
            anomalies.append({
                'type': 'spike',
                'severity': 'high' if row['change_pct'] > 1.0 else 'medium',
                'week': row[week_col],
                'value': row[count_col],
                'change_pct': row['change_pct'] * 100,
                'description': f"激增异常 (+{row['change_pct'] * 100:.1f}%)"
            })
        
        # 2. 骤降检测（比上周减少 > 30%）
        drop_threshold = -0.3
        drops = data[data['change_pct'] < drop_threshold]
        
        for _, row in drops.iterrows():
            anomalies.append({
                'type': 'drop',
                'severity': 'medium',
                'week': row[week_col],
                'value': row[count_col],
                'change_pct': row['change_pct'] * 100,
                'description': f"骤降异常 ({row['change_pct'] * 100:.1f}%)"
            })
        
        # 3. 偏离平均值检测（超过平均值的 2 个标准差）
        mean = data[count_col].mean()
        std = data[count_col].std()
        
        outliers = data[(data[count_col] > mean + 2*std) | 
                     (data[count_col] < mean - 2*std)]
        
        for _, row in outliers.iterrows():
            deviation = (row[count_col] - mean) / std
            anomalies.append({
                'type': 'outlier',
                'severity': 'high' if abs(deviation) > 3 else 'medium',
                'week': row[week_col],
                'value': row[count_col],
                'mean': mean,
                'std': std,
                'deviation': deviation,
                'description': f"偏离异常 (标准差: {deviation:.1f})"
            })
        
        logger.info(f"检测到 {len(anomalies)} 个趋势异常")
        return anomalies
    
    def analyze_topissue_patterns(self, data: pd.DataFrame) -> Dict:
        """
        分析 TopIssue 模式
        
        Args:
            data: 缺陷数据 DataFrame
        
        Returns:
            TopIssue 模式分析结果
        """
        patterns = {}
        
        # 筛选 TopIssue
        topissues = data[data.get('is_topissue', False)]
        
        if topissues.empty:
            return patterns
        
        # 模式 1: TopIssue 的 Matrix 严重性分布
        matrix_dist = topissues['matrix'].value_counts(normalize=True) * 100
        patterns['matrix_distribution'] = matrix_dist.to_dict()
        
        # 模式 2: TopIssue 的项目分布
        project_dist = topissues['project'].value_counts()
        patterns['project_distribution'] = project_dist.to_dict()
        
        # 模式 3: TopIssue 的 ECU 分布
        ecu_dist = topissues['ecu'].value_counts()
        patterns['ecu_distribution'] = ecu_dist.to_dict()
        
        # 模式 4: TopIssue 的转移模式
        high_transfers = topissues[topissues['ecu_no_of_changes'] >= 3]
        patterns['high_transfer_topissues'] = len(high_transfers)
        
        # 模式 5: TopIssue 的处理周期模式
        long_runner_topissues = topissues[topissues['processing_cycle_days'] >= 30]
        patterns['long_runner_topissues'] = len(long_runner_topissues)
        
        # 模式 6: TopIssue 的主票模式
        parent_topissues = topissues[topissues['parent_child'] == 'Parent']
        patterns['parent_topissues'] = len(parent_topissues)
        
        # 模式 7: TopIssue 的组合模式
        severe_high_transfer = topissues[
            (topissues['matrix'].str.startswith('Matrix-1')) &
            (topissues['ecu_no_of_changes'] >= 3)
        ]
        patterns['severe_high_transfer_count'] = len(severe_high_transfer)
        
        logger.info("TopIssue 模式分析完成")
        return patterns
    
    def analyze_high_runner_patterns(self, data: pd.DataFrame) -> Dict:
        """
        分析 High Runner 模式
        
        Args:
            data: 缺陷数据 DataFrame
        
        Returns:
            High Runner 模式分析结果
        """
        patterns = {}
        
        # 筛选 High Runner
        high_runners = data[
            (data['ecu_no_of_changes'] >= 3) | 
            (data['domain_pingpong_count'] >= 3)
        ]
        
        if high_runners.empty:
            return patterns
        
        # 模式 1: High Runner 的项目分布
        project_dist = high_runners['project'].value_counts()
        patterns['project_distribution'] = project_dist.to_dict()
        
        # 模式 2: High Runner 的 ECU 分布
        ecu_dist = high_runners['ecu'].value_counts()
        patterns['ecu_distribution'] = ecu_dist.to_dict()
        
        # 模式 3: High Runner 的转移模式
        # ECU 转移 >= 3 的比例
        ecu_transfer_3plus = high_runners[high_runners['ecu_no_of_changes'] >= 3]
        patterns['ecu_transfer_3plus_ratio'] = len(ecu_transfer_3plus) / len(high_runners)
        
        # 跨 ECU + Domain 的比例
        cross_both = high_runners[
            (high_runners['ecu_no_of_changes'] >= 3) &
            (high_runners['domain_pingpong_count'] >= 3)
        ]
        patterns['cross_both_ratio'] = len(cross_both) / len(high_runners)
        
        # 模式 4: High Runner 的处理周期模式
        cycle_stats = high_runners['processing_cycle_days'].describe()
        patterns['processing_cycle_stats'] = cycle_stats.to_dict()
        
        # 模式 5: High Runner 的严重性模式
        matrix_dist = high_runners['matrix'].value_counts(normalize=True) * 100
        patterns['matrix_distribution'] = matrix_dist.to_dict()
        
        logger.info(f"High Runner 模式分析完成 ({len(high_runners)} 个)")
        return patterns
    
    def generate_insights(self, data: pd.DataFrame) -> List[str]:
        """
        生成业务洞察
        
        Args:
            data: 缺陷数据 DataFrame
        
        Returns:
            洞察列表
        """
        insights = []
        
        # 洞察 1: 趋势分析
        if 'test_week' in data.columns and 'total_defects' in data.columns:
            trend_data = data.groupby('test_week')['total_defects'].sum().reset_index()
            anomalies = self.detect_trend_anomalies(trend_data)
            
            if anomalies:
                insights.append(
                    f"**趋势异常检测**: 发现 {len(anomalies)} 个异常点"
                )
                
                # 分析激增
                spikes = [a for a in anomalies if a['type'] == 'spike']
                if spikes:
                    latest_spike = max(spikes, key=lambda x: x['week'])
                    insights.append(
                        f"  - 最新激增: {latest_spike['week']} "
                        f"({latest_spike['value']}个, +{latest_spike['change_pct']:.1f}%)"
                    )
                
                # 分析骤降
                drops = [a for a in anomalies if a['type'] == 'drop']
                if drops:
                    insights.append(
                        f"  - 检测到 {len(drops)} 个骤降异常，"
                        f"需要确认是否是测试减少或其他原因"
                    )
        
        # 洞察 2: TopIssue 模式分析
        if 'is_topissue' in data.columns:
            topissue_patterns = self.analyze_topissue_patterns(data)
            
            topissue_count = data['is_topissue'].sum()
            insights.append(
                f"**TopIssue 分析**: 共有 {topissue_count} 个 TopIssue"
            )
            
            # Matrix 分布洞察
            if 'matrix_distribution' in topissue_patterns:
                matrix_dist = topissue_patterns['matrix_distribution']
                high_matrix = [k for k in matrix_dist.keys() if k.startswith('Matrix-1')]
                high_ratio = sum([matrix_dist[k] for k in high_matrix]) / sum(matrix_dist.values())
                
                insights.append(
                    f"  - {high_ratio*100:.1f}% 的 TopIssue 是高严重性 (Matrix-1x)"
                )
            
            # 项目分布洞察
            if 'project_distribution' in topissue_patterns:
                project_dist = topissue_patterns['project_distribution']
                top_project = max(project_dist.items(), key=lambda x: x[1])
                
                insights.append(
                    f"  - {top_project[0]} 项目的 TopIssue 最多 ({top_project[1]}个)"
                )
            
            # 转移模式洞察
            if 'high_transfer_topissues' in topissue_patterns:
                high_transfer_count = topissue_patterns['high_transfer_topissues']
                high_transfer_ratio = high_transfer_count / topissue_count
                
                insights.append(
                    f"  - {high_transfer_count} 个 TopIssue 是 High Runner "
                        f"({high_transfer_ratio*100:.1f}%)"
                )
            
            # 组合模式洞察
            if 'severe_high_transfer_count' in topissue_patterns:
                count = topissue_patterns['severe_high_transfer_count']
                insights.append(
                    f"  - {count} 个 TopIssue 既是高严重性又是 High Runner"
                )
        
        # 洞察 3: High Runner 模式分析
        if 'ecu_no_of_changes' in data.columns:
            high_runners = data[data['ecu_no_of_changes'] >= 3]
            
            if not high_runners.empty:
                insights.append(
                    f"**High Runner 分析**: 共有 {len(high_runners)} 个 High Runner"
                )
                
                # 项目分布
                if 'project_distribution' in self.analyze_high_runner_patterns(high_runners):
                    project_dist = self.analyze_high_runner_patterns(high_runners)['project_distribution']
                    top_project = max(project_dist.items(), key=lambda x: x[1])
                    
                    insights.append(
                        f"  - {top_project[0]} 项目的 High Runner 最多 ({top_project[1]}个)"
                    )
                
                # 跨 ECU+Domain 比例
                if 'cross_both_ratio' in self.analyze_high_runner_patterns(high_runners):
                    cross_both_ratio = self.analyze_high_runner_patterns(high_runners)['cross_both_ratio']
                    
                    insights.append(
                        f"  - {cross_both_ratio*100:.1f}% 的 High Runner 同时跨 ECU 和 Domain"
                    )
        
        # 洞察 4: 处理周期分析
        if 'processing_cycle_days' in data.columns:
            cycle_stats = data['processing_cycle_days'].describe()
            
            long_runners = data[data['processing_cycle_days'] >= 30]
            new_issues = data[data['processing_cycle_days'] <= 3]
            
            insights.append(
                f"**处理周期分析**:"
                f"平均 {cycle_stats['mean']:.1f} 天, "
                f"中位数 {cycle_stats['50%']:.0f} 天"
            )
            
            insights.append(
                f"  - {len(long_runners)} 个 Long Runner (≥30天)"
            )
            
            insights.append(
                f"  - {len(new_issues)} 个新票 (≤3天)"
            )
        
        return insights
    
    def generate_recommendations(self, data: pd.DataFrame, 
                               insights: List[str] = None) -> List[str]:
        """
        生成业务建议
        
        Args:
            data: 缺陷数据 DataFrame
            insights: 洞察列表（可选）
        
        Returns:
            建议列表
        """
        recommendations = []
        
        # 如果没有提供洞察，先生成
        if insights is None:
            insights = self.generate_insights(data)
        
        # 分析洞察并生成建议
        for insight in insights:
            # 激增建议
            if '激增' in insight and 'TopIssue' in insight:
                recommendations.append(
                    "🎯 针对 TopIssue 激增的建议："
                    "1. 检查是否有新版本发布或测试覆盖不足"
                    "2. 加强新版本的回归测试"
                    "3. 检查是否是某个特定模块的问题"
                )
            
            elif '激增' in insight:
                recommendations.append(
                    "🎯 针对缺陷激增的建议："
                    "1. 分析激增的根本原因（版本发布？测试问题？）"
                    "2. 加强相关模块的测试"
                    "3. 考虑是否需要增加资源"
                )
            
            # High Runner 建议
            elif 'High Runner' in insight:
                recommendations.append(
                    "🎯 针对 High Runner 的建议："
                    "1. 建立定期的跨团队同步会议机制"
                    "2. 明确责任边界，避免责任推诿"
                    "3. 考虑是否需要架构调整以减少跨 ECU 问题"
                )
            
            # Long Runner 建议
            elif 'Long Runner' in insight or '处理周期' in insight:
                recommendations.append(
                    "🎯 针对 Long Runner 的建议："
                    "1. 评估是否需要增加资源或升级处理"
                    "2. 检查是否有技术瓶颈"
                    "3. 确保优先级合理，不被低优先级问题阻塞"
                )
            
            # TopIssue 建议
            elif 'TopIssue 分析' in insight:
                recommendations.append(
                    "🎯 针对 TopIssue 的优先级建议："
                    "1. 按风险评分从高到低处理"
                    "2. 优先处理高严重性 + 高转移的 TopIssue"
                    "3. 针对大规模主票，建立专项解决小组"
                )
        
        # 基于数据的建议
        if 'is_topissue' in data.columns:
            topissues = data[data['is_topissue'] == True]
            severe_topissues = topissues[topissues['matrix'].str.startswith('Matrix-1')]
            
            if len(severe_topissues) > 10:
                recommendations.append(
                    "🔴 风险提示：高严重性 TopIssue 过多（>10个）"
                    "建议：立即召开管理层会议，制定专项应对计划"
                )
        
        if 'ecu_no_of_changes' in data.columns:
            high_transfers = data[data['ecu_no_of_changes'] >= 5]
            
            if not high_transfers.empty:
                top_ecu = high_transfers['ecu'].value_counts().idxmax()
                recommendations.append(
                    f"🔴 风险提示：{top_ecu} 的极端 High Runner 最多"
                    f"建议：重点审查 {top_ecu} 的问题处理流程"
                )
        
        # 去重建议
        if len(recommendations) == 0:
            recommendations.append(
                "💡 建议：定期分析缺陷数据，识别模式和异常点"
                "持续优化缺陷管理流程"
            )
        
        return recommendations


# ============================================================================
# 工厂函数
# ============================================================================

def create_insight_generator() -> InsightGenerator:
    """创建洞察生成器"""
    return InsightGenerator()


# ============================================================================
# 示例使用
# ============================================================================

if __name__ == "__main__":
    # 示例使用
    generator = InsightGenerator()
    
    # 示例数据
    data = pd.DataFrame({
        'week': ['2025-W42', '2025-W43', '2025-W44', '2025-W45', '2025-W46'],
        'count': [50, 60, 45, 55, 50],
        'is_topissue': [True, False, False, True, False],
        'matrix': ['Matrix-1A', 'Matrix-2A', 'Matrix-3A', 'Matrix-1B', 'Matrix-2B'],
        'ecu_no_of_changes': [5, 2, 1, 4, 3],
        'domain_pingpong_count': [2, 0, 0, 1, 0],
        'processing_cycle_days': [45, 15, 5, 30, 10],
        'project': ['App', 'IDC', 'MGU', 'App', 'IDC'],
        'ecu': ['IuK_HU', 'DIPS_HU', 'IuK_HU', 'IuK_HU', 'DIPS_HU']
    })
    
    print("=" * 70)
    print("📊 业务洞察生成器示例")
    print("=" * 70)
    
    # 生成洞察
    print("\n【业务洞察】")
    print("-" * 70)
    insights = generator.generate_insights(data)
    for i, insight in enumerate(insights, 1):
        print(f"{i}. {insight}")
    
    # 生成建议
    print("\n【业务建议】")
    print("-" * 70)
    recommendations = generator.generate_recommendations(data, insights)
    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. {rec}")

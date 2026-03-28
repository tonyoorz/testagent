"""
智能 Agent 系统 - 为数据分析提供增强的 AI 对话能力

核心功能：
1. 工具调用系统 - AI 可执行数据分析操作
2. 智能上下文管理 - 根据问题动态筛选数据
3. 对话记忆系统 - 记住关键洞察和用户偏好
4. 知识库集成 - RAG 能力提供领域知识
5. 任务规划能力 - 分解复杂任务
6. 增强系统提示词 - 专业领域知识

作者: AI Assistant
日期: 2025-01-19
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Generator, Union, Tuple
import re
from functools import lru_cache
from collections import defaultdict
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# 1. 工具调用系统
# ============================================================================

class DataAnalysisTool:
    """数据分析工具基类"""

    def __init__(self, name: str, description: str, parameters: dict):
        self.name = name
        self.description = description
        self.parameters = parameters

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行工具逻辑，由子类实现"""
        raise NotImplementedError

    def expects_datasets(self) -> bool:
        return False


class TrendAnalysisTool(DataAnalysisTool):
    """趋势分析工具"""

    def __init__(self):
        super().__init__(
            name="analyze_trend",
            description="分析数据趋势，支持按时间、项目、类别等维度分组",
            parameters={
                "group_by": {
                    "type": "string",
                    "description": "分组维度",
                    "enum": ["week", "month", "project", "severity", "category"],
                    "default": "week"
                },
                "metric": {
                    "type": "string",
                    "description": "统计指标",
                    "enum": ["count", "unique", "sum", "mean", "max", "min"],
                    "default": "count"
                },
                "time_column": {
                    "type": "string",
                    "description": "时间列名",
                    "default": "tcreationtime"
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行趋势分析"""
        try:
            group_by = kwargs.get('group_by', 'week')
            metric = kwargs.get('metric', 'count')
            time_column = kwargs.get('time_column', 'tcreationtime')

            # 确保时间列是 datetime 类型
            if time_column not in data.columns:
                for candidate in ['tcreationtime', 'creation_time', 'created_at', 'finished_udf_dt', 'finished_udf']:
                    if candidate in data.columns:
                        time_column = candidate
                        break
            if time_column in data.columns:
                data = data.copy()
                data[time_column] = pd.to_datetime(data[time_column], errors='coerce')

            # 根据分组维度创建时间分组
            if group_by in ['week', 'month'] and time_column in data.columns:
                if group_by == 'week':
                    data['_time_group'] = data[time_column].dt.to_period('W').astype(str)
                else:
                    data['_time_group'] = data[time_column].dt.to_period('M').astype(str)
                group_cols = ['_time_group']
                label_col = '_time_group'
            elif group_by in ['project', 'severity', 'category']:
                # 映射列名
                col_mapping = {
                    'project': 'tproject',
                    'severity': 'severity_group',
                    'category': 'category'
                }
                actual_col = col_mapping.get(group_by, group_by)
                if actual_col == 'tproject' and actual_col not in data.columns and 'project' in data.columns:
                    actual_col = 'project'
                if actual_col not in data.columns:
                    return {"success": False, "tool": self.name, "error": f"列 {actual_col} 不存在"}
                group_cols = [actual_col]
                label_col = actual_col
            else:
                return {"success": False, "tool": self.name, "error": f"不支持的分组维度: {group_by}"}

            # 执行分组统计
            if metric == 'count':
                result = data.groupby(group_cols).size().reset_index(name='value')
            elif metric == 'unique':
                result = data.groupby(group_cols).agg({'_id': 'nunique'}).reset_index(name='value')
            else:
                numeric_cols = data.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) == 0:
                    return {"success": False, "tool": self.name, "error": "没有数值列可用于聚合"}
                result = data.groupby(group_cols)[numeric_cols[0]].agg(metric).reset_index(name='value')

            # 转换为返回格式
            trend_data = []
            for _, row in result.iterrows():
                trend_data.append({
                    'group': row[label_col],
                    'value': int(row['value']) if metric in ['count', 'unique', 'sum'] else float(row['value'])
                })

            # 计算趋势指标
            values = [item['value'] for item in trend_data]
            trend_direction = "上升" if len(values) > 1 and values[-1] > values[0] else "下降"
            change_rate = ((values[-1] - values[0]) / values[0] * 100) if values[0] != 0 else 0

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "trend_data": trend_data,
                    "summary": {
                        "direction": trend_direction,
                        "change_rate": round(change_rate, 2),
                        "total": sum(values),
                        "average": round(np.mean(values), 2),
                        "max": max(values),
                        "min": min(values)
                    }
                },
                "insights": self._generate_insights(trend_data, trend_direction, change_rate)
            }

        except Exception as e:
            logger.error(f"趋势分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}

    def _generate_insights(self, trend_data: List[Dict], direction: str, change_rate: float) -> List[str]:
        """生成趋势洞察"""
        insights = []

        if len(trend_data) < 2:
            insights.append("数据点较少，建议收集更多数据以准确分析趋势")
        else:
            insights.append(f"整体呈{direction}趋势，变化率为 {change_rate:.1f}%")

            # 检测异常点
            values = [item['value'] for item in trend_data]
            mean_val = np.mean(values)
            std_val = np.std(values)

            anomalies = [item for item in trend_data
                        if abs(item['value'] - mean_val) > 2 * std_val]

            if anomalies:
                insights.append(f"检测到 {len(anomalies)} 个异常数据点，需要关注")

        return insights


class RiskAnalysisTool(DataAnalysisTool):
    """风险分析工具"""

    def __init__(self):
        super().__init__(
            name="analyze_risk",
            description="分析风险分布，识别高风险项目和缺陷",
            parameters={
                "dimension": {
                    "type": "string",
                    "description": "分析维度",
                    "enum": ["project", "matrix", "severity", "category"],
                    "default": "project"
                },
                "top_n": {
                    "type": "integer",
                    "description": "返回前 N 个高风险项",
                    "default": 10
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行风险分析"""
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"dimension": kwargs.get('dimension', 'project'), "risk_items": []},
                    "insights": ["数据为空，无法计算风险分布"]
                }
            dimension = kwargs.get('dimension', 'project')
            top_n = kwargs.get('top_n', 10)

            # 映射维度到实际列名
            col_mapping = {
                'project': 'tproject',
                'matrix': 'matrix_display',
                'severity': 'severity_group',
                'category': 'category'
            }
            group_col = col_mapping.get(dimension, dimension)
            if group_col == 'tproject' and group_col not in data.columns and 'project' in data.columns:
                group_col = 'project'

            if group_col not in data.columns:
                return {"success": False, "tool": self.name, "error": f"列 {group_col} 不存在"}

            # 计算风险评分
            def calculate_risk_score(group):
                """计算风险评分"""
                score = 0

                # 1. 缺陷数量权重 (30%)
                count = len(group)
                score += min(count / 100 * 30, 30)

                # 2. 严重性权重 (40%)
                if 'severity_group' in group.columns:
                    severity_weights = {'Critical': 40, 'Major': 25, 'Minor': 10}
                    avg_severity = group['severity_group'].map(severity_weights).mean()
                    score += avg_severity if pd.notna(avg_severity) else 15

                # 3. TopIssue 权重 (20%)
                if 'topissue' in group.columns:
                    topissue_ratio = group['topissue'].eq('TopIssue').mean()
                    score += topissue_ratio * 20

                # 4. 矩阵位置权重 (10%)
                if 'matrix_display' in group.columns:
                    high_risk_matrices = ['1A', '1B', '1C', '1D', '1E']
                    matrix_code = group['matrix_display'].astype(str).str.replace('MATRIX-', '', regex=False).str.replace('Matrix-', '', regex=False).str.upper()
                    high_risk_ratio = matrix_code.isin(high_risk_matrices).mean()
                    score += high_risk_ratio * 10

                return round(score, 2)

            # 按维度分组并计算风险评分
            risk_analysis = data.groupby(group_col).apply(calculate_risk_score).reset_index()
            risk_analysis.columns = [group_col, 'risk_score']
            risk_analysis = risk_analysis.sort_values('risk_score', ascending=False).head(top_n)

            # 生成结果
            risk_items = []
            for _, row in risk_analysis.iterrows():
                group_key = row[group_col]
                group_data = data[data[group_col] == group_key]

                risk_items.append({
                    'name': group_key,
                    'risk_score': float(row['risk_score']),
                    'defect_count': len(group_data),
                    'topissue_count': group_data['topissue'].eq('TopIssue').sum() if 'topissue' in group_data.columns else 0,
                    'high_risk_ratio': self._calculate_high_risk_ratio(group_data)
                })

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "dimension": dimension,
                    "risk_items": risk_items
                },
                "insights": self._generate_risk_insights(risk_items)
            }

        except Exception as e:
            logger.error(f"风险分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}

    def _calculate_high_risk_ratio(self, group_data: pd.DataFrame) -> float:
        """计算高风险比例"""
        if 'matrix_display' not in group_data.columns:
            return 0.0

        high_risk_matrices = ['1A', '1B', '1C', '1D', '1E']
        return round(
            group_data['matrix_display'].astype(str).str.replace('MATRIX-', '', regex=False).str.replace('Matrix-', '', regex=False).str.upper().isin(high_risk_matrices).sum() / len(group_data) * 100,
            2
        )

    def _generate_risk_insights(self, risk_items: List[Dict]) -> List[str]:
        """生成风险洞察"""
        insights = []

        if not risk_items:
            return ["没有足够的数据进行风险分析"]

        # 顶层风险
        top_risk = risk_items[0]
        insights.append(f"最高风险项是 '{top_risk['name']}'，风险评分 {top_risk['risk_score']}")

        # 风险分布
        avg_score = np.mean([item['risk_score'] for item in risk_items])
        high_risk_count = len([item for item in risk_items if item['risk_score'] > avg_score * 1.2])
        insights.append(f"有 {high_risk_count} 个项目的风险评分显著高于平均水平")

        # TopIssue 分析
        total_topissue = sum(item['topissue_count'] for item in risk_items)
        if total_topissue > 0:
            insights.append(f"高风险项目中包含 {total_topissue} 个 TopIssue，需要优先处理")

        return insights


class ComparisonTool(DataAnalysisTool):
    """对比分析工具"""

    def __init__(self):
        super().__init__(
            name="compare_items",
            description="对比不同项目、类别或时间段的指标",
            parameters={
                "items": {
                    "type": "array",
                    "description": "要对比的项目列表",
                    "items": {"type": "string"}
                },
                "dimension": {
                    "type": "string",
                    "description": "对比维度",
                    "enum": ["project", "severity", "category"],
                    "default": "project"
                },
                "metrics": {
                    "type": "array",
                    "description": "对比指标",
                    "items": {"type": "string"},
                    "default": ["count", "avg_risk_score", "topissue_ratio"]
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """执行对比分析"""
        try:
            items = kwargs.get('items', [])
            dimension = kwargs.get('dimension', 'project')
            metrics = kwargs.get('metrics', ['count', 'avg_risk_score', 'topissue_ratio'])

            if not items:
                return {"success": False, "tool": self.name, "error": "请提供要对比的项目"}

            # 映射维度列名
            col_mapping = {
                'project': 'tproject',
                'severity': 'severity_group',
                'category': 'category'
            }
            group_col = col_mapping.get(dimension, dimension)
            if group_col == 'tproject' and group_col not in data.columns and 'project' in data.columns:
                group_col = 'project'

            if group_col not in data.columns:
                return {"success": False, "tool": self.name, "error": f"列 {group_col} 不存在"}

            # 筛选数据
            comparison_data = data[data[group_col].isin(items)]

            if comparison_data.empty:
                return {"success": False, "tool": self.name, "error": f"未找到匹配的数据: {items}"}

            # 计算各项指标
            comparison_results = []

            for item in items:
                item_data = comparison_data[comparison_data[group_col] == item]

                result = {
                    'name': item,
                    'metrics': {}
                }

                for metric in metrics:
                    if metric == 'count':
                        result['metrics']['count'] = len(item_data)
                    elif metric == 'avg_risk_score':
                        # 简化版风险评分
                        score = 0
                        score += min(len(item_data) / 100 * 30, 30)
                        if 'severity_group' in item_data.columns:
                            severity_weights = {'Critical': 40, 'Major': 25, 'Minor': 10}
                            avg_severity = item_data['severity_group'].map(severity_weights).mean()
                            score += avg_severity if pd.notna(avg_severity) else 15
                        result['metrics']['avg_risk_score'] = round(score, 2)
                    elif metric == 'topissue_ratio':
                        if 'topissue' in item_data.columns:
                            ratio = item_data['topissue'].eq('TopIssue').mean() * 100
                            result['metrics']['topissue_ratio'] = round(ratio, 2)
                        else:
                            result['metrics']['topissue_ratio'] = 0

                comparison_results.append(result)

            # 生成对比洞察
            insights = self._generate_comparison_insights(comparison_results, metrics)

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "dimension": dimension,
                    "comparisons": comparison_results
                },
                "insights": insights
            }

        except Exception as e:
            logger.error(f"对比分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}

    def _generate_comparison_insights(self, results: List[Dict], metrics: List[str]) -> List[str]:
        """生成对比洞察"""
        insights = []

        if len(results) < 2:
            return ["需要至少 2 个项目进行对比"]

        # 找出每个指标的最好和最差
        for metric in metrics:
            values = [(r['name'], r['metrics'].get(metric, 0)) for r in results]

            if metric == 'count':
                best = max(values, key=lambda x: x[1])
                worst = min(values, key=lambda x: x[1])
                insights.append(
                    f"在缺陷数量方面，'{best[0]}' 最高 ({best[1]})，"
                    f"'{worst[0]}' 最低 ({worst[1]})"
                )
            elif metric == 'avg_risk_score':
                best = max(values, key=lambda x: x[1])
                worst = min(values, key=lambda x: x[1])
                insights.append(
                    f"在风险评分方面，'{best[0]}' 最高 ({best[1]})，"
                    f"'{worst[0]}' 最低 ({worst[1]})"
                )
            elif metric == 'topissue_ratio':
                best = max(values, key=lambda x: x[1])
                if best[1] > 0:
                    insights.append(
                        f"'{best[0]}' 的 TopIssue 比例最高 ({best[1]}%)，需要重点关注"
                    )

        return insights


class StatisticalSummaryTool(DataAnalysisTool):
    """统计摘要工具"""

    def __init__(self):
        super().__init__(
            name="statistical_summary",
            description="生成数据的统计摘要，包括分布、异常值等",
            parameters={
                "columns": {
                    "type": "array",
                    "description": "要统计的列名，留空则自动选择关键列",
                    "items": {"type": "string"},
                    "default": []
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """生成统计摘要"""
        try:
            columns = kwargs.get('columns', [])

            # 自动选择关键列
            if not columns:
                key_columns = ['tproject', 'project', 'severity_group', 'severity', 'category', 'topissue', 'matrix_display', 'run_status']
                columns = [col for col in key_columns if col in data.columns]

            summary = {
                'total_records': len(data),
                'columns_analysis': {}
            }

            for col in columns:
                if col not in data.columns:
                    continue

                col_summary = {
                    'unique_count': data[col].nunique(),
                    'most_common': data[col].value_counts().head(5).to_dict(),
                    'null_count': data[col].isna().sum(),
                    'null_percentage': round(data[col].isna().mean() * 100, 2)
                }

                # 数值型列的额外统计
                if pd.api.types.is_numeric_dtype(data[col]):
                    col_summary.update({
                        'mean': round(data[col].mean(), 2),
                        'median': round(data[col].median(), 2),
                        'std': round(data[col].std(), 2),
                        'min': float(data[col].min()),
                        'max': float(data[col].max())
                    })

                summary['columns_analysis'][col] = col_summary

            # 生成洞察
            insights = self._generate_summary_insights(summary)

            return {
                "success": True,
                "tool": self.name,
                "result": summary,
                "insights": insights
            }

        except Exception as e:
            logger.error(f"统计摘要失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}

    def _generate_summary_insights(self, summary: Dict) -> List[str]:
        """生成摘要洞察"""
        insights = []

        insights.append(f"数据集包含 {summary['total_records']} 条记录")

        for col, col_summary in summary['columns_analysis'].items():
            if col_summary['null_percentage'] > 10:
                insights.append(
                    f"警告: 列 '{col}' 有 {col_summary['null_percentage']}% 的缺失值"
                )

            if col_summary['unique_count'] == 1:
                insights.append(f"列 '{col}' 只有一个唯一值，可能无法提供有用的区分信息")

        return insights


class MatrixDistributionTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_matrix_distribution",
            description="分析缺陷矩阵（matrix）分布与占比",
            parameters={
                "include_unknown": {
                    "type": "boolean",
                    "description": "是否包含空值/未知矩阵",
                    "default": True
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"total": 0, "distribution": []},
                    "insights": ["缺陷数据为空，无法统计 matrix 分布"]
                }

            col = "matrix_display" if "matrix_display" in data.columns else "matrix" if "matrix" in data.columns else None
            if not col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少 matrix/matrix_display 列"}

            include_unknown = bool(kwargs.get("include_unknown", True))
            s = data[col].astype(str).map(lambda v: v.strip())
            s = s.replace({"": np.nan, "nan": np.nan, "None": np.nan, "none": np.nan})

            normalized = (
                s.fillna("Unknown")
                .str.replace("MATRIX-", "", regex=False)
                .str.replace("Matrix-", "", regex=False)
                .str.replace("matrix-", "", regex=False)
                .str.upper()
            )

            if not include_unknown:
                normalized = normalized[normalized != "UNKNOWN"]

            total = int(len(normalized))
            if total == 0:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"total": 0, "distribution": []},
                    "insights": ["缺陷数据存在，但 matrix 全为空/未知"]
                }

            counts = normalized.value_counts()

            def _sort_key(v: str):
                if v == "UNKNOWN":
                    return (999, "Z", v)
                m = re.match(r"^(\d+)([A-Z])$", v)
                if m:
                    return (int(m.group(1)), m.group(2), v)
                return (998, "Z", v)

            items = []
            for k, c in counts.items():
                items.append({
                    "matrix": str(k),
                    "count": int(c),
                    "ratio": round(int(c) / total * 100, 2)
                })
            items = sorted(items, key=lambda r: _sort_key(r["matrix"]))

            insights = []
            top = counts.index[0]
            insights.append(f"占比最高的矩阵: {top}（{int(counts.iloc[0])} 条，{round(int(counts.iloc[0]) / total * 100, 2)}%）")

            high_risk = {"1A", "1B", "1C", "1D", "1E"}
            high_cnt = int(sum(counts.get(k, 0) for k in high_risk))
            if high_cnt > 0:
                insights.append(f"高风险矩阵(1A-1E)合计: {high_cnt} 条（{round(high_cnt / total * 100, 2)}%）")

            return {
                "success": True,
                "tool": self.name,
                "result": {"total": total, "distribution": items},
                "insights": insights
            }
        except Exception as e:
            logger.error(f"matrix 分布分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}


class MatrixAidaHotspotsTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_matrix_aida_hotspots",
            description="分析每个 matrix 下 AIDA 的缺陷聚集度，并输出代表性 ticket 样本",
            parameters={
                "top_matrices": {
                    "type": "integer",
                    "description": "输出矩阵数量（按缺陷数排序）",
                    "default": 10
                },
                "top_aidas": {
                    "type": "integer",
                    "description": "每个矩阵输出 AIDA Top N",
                    "default": 5
                },
                "sample_tickets": {
                    "type": "integer",
                    "description": "每个 matrix×AIDA 输出 ticket 样本数",
                    "default": 3
                },
                "include_unknown": {
                    "type": "boolean",
                    "description": "是否包含未知矩阵/未知AIDA",
                    "default": True
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"total": 0, "matrices": []},
                    "insights": ["缺陷数据为空，无法分析 matrix×AIDA 热点"]
                }

            matrix_col = "matrix_display" if "matrix_display" in data.columns else "matrix" if "matrix" in data.columns else None
            if not matrix_col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少 matrix/matrix_display 列"}

            aida_col = "aida_english" if "aida_english" in data.columns else "aida" if "aida" in data.columns else None
            if not aida_col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少 aida/aida_english 列"}

            include_unknown = bool(kwargs.get("include_unknown", True))
            top_matrices = max(1, min(int(kwargs.get("top_matrices", 10)), 50))
            top_aidas = max(1, min(int(kwargs.get("top_aidas", 5)), 30))
            sample_tickets = max(0, min(int(kwargs.get("sample_tickets", 3)), 20))

            df = data.copy()

            m = df[matrix_col].astype(str).map(lambda v: v.strip())
            m = m.replace({"": np.nan, "nan": np.nan, "None": np.nan, "none": np.nan})
            m = (
                m.fillna("Unknown")
                .str.replace("MATRIX-", "", regex=False)
                .str.replace("Matrix-", "", regex=False)
                .str.replace("matrix-", "", regex=False)
                .str.upper()
            )

            a = df[aida_col].astype(str).map(lambda v: v.strip())
            a = a.replace({"": np.nan, "nan": np.nan, "None": np.nan, "none": np.nan}).fillna("Unknown")

            df["_matrix_norm"] = m
            df["_aida_norm"] = a

            if not include_unknown:
                df = df[(df["_matrix_norm"] != "UNKNOWN") & (df["_aida_norm"] != "Unknown")]

            total = int(len(df))
            if total == 0:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"total": 0, "matrices": []},
                    "insights": ["缺陷数据存在，但 matrix/AIDA 都为空或被过滤为 Unknown"]
                }

            id_col = "id" if "id" in df.columns else "_id" if "_id" in df.columns else None
            title_col = "name" if "name" in df.columns else "title" if "title" in df.columns else None
            project_col = "tproject" if "tproject" in df.columns else "project" if "project" in df.columns else None
            time_col = "tcreationtime" if "tcreationtime" in df.columns else "creation_time" if "creation_time" in df.columns else None

            if time_col and time_col in df.columns:
                df[time_col] = pd.to_datetime(df[time_col], errors="coerce")

            matrix_counts = df["_matrix_norm"].value_counts()
            selected_matrices = matrix_counts.head(top_matrices).index.tolist()

            matrices_out = []
            for matrix_value in selected_matrices:
                md = df[df["_matrix_norm"] == matrix_value]
                matrix_total = int(len(md))
                aida_counts = md["_aida_norm"].value_counts().head(top_aidas)
                aidas_out = []
                for aida_value, cnt in aida_counts.items():
                    sub = md[md["_aida_norm"] == aida_value]
                    samples = []
                    if sample_tickets > 0 and (id_col or title_col):
                        sub2 = sub
                        if time_col and time_col in sub2.columns:
                            sub2 = sub2.sort_values(time_col, ascending=False)
                        for _, r in sub2.head(sample_tickets).iterrows():
                            samples.append({
                                "id": r.get(id_col) if id_col else None,
                                "title": r.get(title_col) if title_col else None,
                                "project": r.get(project_col) if project_col else None,
                                "creation_time": str(r.get(time_col)) if time_col else None
                            })

                    aidas_out.append({
                        "aida": str(aida_value),
                        "count": int(cnt),
                        "ratio_in_matrix": round(int(cnt) / matrix_total * 100, 2) if matrix_total else 0.0,
                        "samples": samples
                    })

                matrices_out.append({
                    "matrix": str(matrix_value),
                    "matrix_total": matrix_total,
                    "matrix_share": round(matrix_total / total * 100, 2),
                    "top_aidas": aidas_out
                })

            insights = []
            if matrices_out:
                top_m = matrices_out[0]
                insights.append(f"缺陷最多的矩阵: {top_m['matrix']}（{top_m['matrix_total']} 条，占 {top_m['matrix_share']}%）")
                if top_m.get("top_aidas"):
                    top_a = top_m["top_aidas"][0]
                    insights.append(f"{top_m['matrix']} 内最聚集的 AIDA: {top_a['aida']}（{top_a['count']} 条，占该矩阵 {top_a['ratio_in_matrix']}%）")

            return {
                "success": True,
                "tool": self.name,
                "result": {"total": total, "matrices": matrices_out},
                "insights": insights
            }
        except Exception as e:
            logger.error(f"matrix×AIDA 热点分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}


class TopIssueHotlistTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_topissue_hotlist",
            description="输出 TopIssue/高风险票据清单（按风险分排序）",
            parameters={
                "top_n": {"type": "integer", "description": "输出前 N 条", "default": 20}
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {"success": True, "tool": self.name, "result": {"rows": [], "total": 0}, "insights": ["缺陷数据为空，无法生成清单"]}

            df = data.copy()

            score_col = None
            for c in ["topissue_risk_score", "risk_score", "topissue_score"]:
                if c in df.columns:
                    score_col = c
                    break
            if not score_col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少风险分字段（topissue_risk_score/risk_score）"}

            topissue_col = None
            for c in ["is_topissue", "topissue"]:
                if c in df.columns:
                    topissue_col = c
                    break

            if topissue_col == "is_topissue":
                df = df[df[topissue_col].astype(bool)]
            elif topissue_col == "topissue":
                df = df[df[topissue_col].astype(str).str.lower().str.contains("topissue")]

            if df.empty:
                return {"success": True, "tool": self.name, "result": {"rows": [], "total": 0}, "insights": ["未找到 TopIssue 票据（或 TopIssue 字段为空）"]}

            df[score_col] = pd.to_numeric(df[score_col], errors="coerce").fillna(0.0)
            df = df.sort_values(score_col, ascending=False)

            top_n = max(1, min(int(kwargs.get("top_n", 20)), 200))
            id_col = "id" if "id" in df.columns else "_id" if "_id" in df.columns else None
            title_col = "name" if "name" in df.columns else "title" if "title" in df.columns else None
            matrix_col = "matrix_display" if "matrix_display" in df.columns else "matrix" if "matrix" in df.columns else None
            project_col = "tproject" if "tproject" in df.columns else "project" if "project" in df.columns else None
            pu_col = "pu" if "pu" in df.columns else None
            status_col = "status_phase" if "status_phase" in df.columns else "status" if "status" in df.columns else None
            aida_col = "aida_english" if "aida_english" in df.columns else "aida" if "aida" in df.columns else None
            time_col = "tcreationtime" if "tcreationtime" in df.columns else "creation_time" if "creation_time" in df.columns else None

            rows = []
            for _, r in df.head(top_n).iterrows():
                rows.append({
                    "id": r.get(id_col) if id_col else None,
                    "title": r.get(title_col) if title_col else None,
                    "score": float(r.get(score_col) or 0),
                    "project": r.get(project_col) if project_col else None,
                    "matrix": r.get(matrix_col) if matrix_col else None,
                    "pu": r.get(pu_col) if pu_col else None,
                    "status": r.get(status_col) if status_col else None,
                    "aida": r.get(aida_col) if aida_col else None,
                    "creation_time": str(r.get(time_col)) if time_col else None
                })

            insights = [f"TopIssue 高风险票据 Top1: {rows[0].get('id')}（score={rows[0].get('score')}）"] if rows else []
            return {"success": True, "tool": self.name, "result": {"total": int(len(df)), "rows": rows}, "insights": insights}
        except Exception as e:
            logger.error(f"TopIssue 清单生成失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}


class LongRunnerHotlistTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_longrunner_hotlist",
            description="输出处理周期最长的票据清单（按处理天数排序）",
            parameters={
                "top_n": {"type": "integer", "description": "输出前 N 条", "default": 20}
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {"success": True, "tool": self.name, "result": {"rows": [], "total": 0}, "insights": ["缺陷数据为空，无法生成清单"]}

            df = data.copy()
            days_col = None
            for c in ["processing_cycle_days", "process_days", "processing_days", "cycle_days"]:
                if c in df.columns:
                    days_col = c
                    break
            if not days_col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少处理周期字段（processing_cycle_days/process_days）"}

            df[days_col] = pd.to_numeric(df[days_col], errors="coerce")
            df = df[df[days_col].notna()]
            if df.empty:
                return {"success": True, "tool": self.name, "result": {"rows": [], "total": 0}, "insights": ["处理周期字段全为空，无法排序"]}

            df = df.sort_values(days_col, ascending=False)

            top_n = max(1, min(int(kwargs.get("top_n", 20)), 200))
            id_col = "id" if "id" in df.columns else "_id" if "_id" in df.columns else None
            title_col = "name" if "name" in df.columns else "title" if "title" in df.columns else None
            matrix_col = "matrix_display" if "matrix_display" in df.columns else "matrix" if "matrix" in df.columns else None
            project_col = "tproject" if "tproject" in df.columns else "project" if "project" in df.columns else None
            pu_col = "pu" if "pu" in df.columns else None
            status_col = "status_phase" if "status_phase" in df.columns else "status" if "status" in df.columns else None
            aida_col = "aida_english" if "aida_english" in df.columns else "aida" if "aida" in df.columns else None
            time_col = "tcreationtime" if "tcreationtime" in df.columns else "creation_time" if "creation_time" in df.columns else None

            rows = []
            for _, r in df.head(top_n).iterrows():
                rows.append({
                    "id": r.get(id_col) if id_col else None,
                    "title": r.get(title_col) if title_col else None,
                    "days": float(r.get(days_col) or 0),
                    "project": r.get(project_col) if project_col else None,
                    "matrix": r.get(matrix_col) if matrix_col else None,
                    "pu": r.get(pu_col) if pu_col else None,
                    "status": r.get(status_col) if status_col else None,
                    "aida": r.get(aida_col) if aida_col else None,
                    "creation_time": str(r.get(time_col)) if time_col else None
                })

            insights = [f"最长处理周期 Top1: {rows[0].get('id')}（{rows[0].get('days')} 天）"] if rows else []
            return {"success": True, "tool": self.name, "result": {"total": int(len(df)), "rows": rows}, "insights": insights}
        except Exception as e:
            logger.error(f"LongRunner 清单生成失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}


class AnalyzeTesterFindingsTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_tester_findings",
            description="分析缺陷由谁发现最多（tester 维度），并给出代表性缺陷样本",
            parameters={
                "top_n": {
                    "type": "integer",
                    "description": "输出前 N 位 tester",
                    "default": 10
                },
                "sample_per_tester": {
                    "type": "integer",
                    "description": "每位 tester 展示的缺陷样本数",
                    "default": 5
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"top_testers": [], "total_defects": 0},
                    "insights": ["缺陷数据为空，无法统计 tester 发现问题情况"]
                }

            tester_col = None
            for c in ["tester", "found_by", "reporter", "author_name"]:
                if c in data.columns:
                    tester_col = c
                    break
            if not tester_col:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少 tester/发现人字段"}

            top_n = int(kwargs.get("top_n", 10))
            sample_per_tester = int(kwargs.get("sample_per_tester", 5))

            df = data.copy()
            df[tester_col] = df[tester_col].astype(str).map(lambda s: s.strip())
            df = df[df[tester_col].notna() & (df[tester_col] != "") & (df[tester_col].str.lower() != "nan")]
            if df.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"top_testers": [], "total_defects": int(len(data))},
                    "insights": ["缺陷数据存在，但 tester 字段为空/缺失，无法统计"]
                }

            total_defects = int(len(df))
            counts = df[tester_col].value_counts()
            top_testers = counts.head(max(1, min(top_n, 50))).to_dict()

            id_col = "id" if "id" in df.columns else "_id" if "_id" in df.columns else None
            title_col = "name" if "name" in df.columns else "title" if "title" in df.columns else None
            project_col = "tproject" if "tproject" in df.columns else "project" if "project" in df.columns else None
            time_col = "tcreationtime" if "tcreationtime" in df.columns else "creation_time" if "creation_time" in df.columns else None
            sev_col = "severity_group" if "severity_group" in df.columns else "severity" if "severity" in df.columns else None
            matrix_col = "matrix_display" if "matrix_display" in df.columns else "matrix" if "matrix" in df.columns else None
            status_col = "status_phase" if "status_phase" in df.columns else "phase" if "phase" in df.columns else None
            aida_col = "aida_english" if "aida_english" in df.columns else "aida" if "aida" in df.columns else None

            topissue_series = None
            if "is_topissue" in df.columns:
                topissue_series = df["is_topissue"].astype(bool)
            elif "topissue" in df.columns:
                topissue_series = df["topissue"].astype(str).str.lower().str.contains("topissue")

            results = []
            for tester, cnt in top_testers.items():
                g = df[df[tester_col] == tester]
                projects = g[project_col].value_counts().head(5).to_dict() if project_col else {}
                projects = {k: int(v) for k, v in projects.items() if str(k).strip() and str(k).strip().lower() not in {"nan", "none"}}
                aidas = g[aida_col].value_counts().head(5).to_dict() if aida_col else {}
                aidas = {k: int(v) for k, v in aidas.items() if str(k).strip() and str(k).strip().lower() not in {"nan", "none"}}
                severities = g[sev_col].value_counts().head(3).to_dict() if sev_col else {}

                topissue_cnt = int(topissue_series[g.index].sum()) if topissue_series is not None else 0
                topissue_ratio = round(topissue_cnt / len(g) * 100, 2) if len(g) else 0.0

                sample_df = g
                if time_col and time_col in g.columns:
                    sample_df = g.sort_values(time_col, ascending=False)
                sample_df = sample_df.head(max(0, sample_per_tester))

                samples = []
                for _, r in sample_df.iterrows():
                    samples.append({
                        "id": r.get(id_col) if id_col else None,
                        "title": r.get(title_col) if title_col else None,
                        "project": r.get(project_col) if project_col else None,
                        "creation_time": str(r.get(time_col)) if time_col else None,
                        "severity": r.get(sev_col) if sev_col else None,
                        "matrix": r.get(matrix_col) if matrix_col else None,
                        "status": r.get(status_col) if status_col else None,
                        "aida": r.get(aida_col) if aida_col else None,
                        "is_topissue": bool(r.get("is_topissue")) if "is_topissue" in df.columns else None
                    })

                results.append({
                    "tester": tester,
                    "defect_count": int(cnt),
                    "share": round(cnt / total_defects * 100, 2),
                    "topissue_count": topissue_cnt,
                    "topissue_ratio": topissue_ratio,
                    "top_projects": projects,
                    "top_aidas": aidas,
                    "top_severities": severities,
                    "samples": samples
                })

            insights = []
            if results:
                insights.append(f"发现问题最多的 tester: {results[0]['tester']}（{results[0]['defect_count']} 条，占 {results[0]['share']}%）")
                top5_sum = sum(r["defect_count"] for r in results[:5])
                insights.append(f"Top 5 tester 共发现 {top5_sum} 条，占 {round(top5_sum / total_defects * 100, 2)}%")

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "total_defects": total_defects,
                    "top_testers": results
                },
                "insights": insights
            }
        except Exception as e:
            logger.error(f"tester 发现问题分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}


class AnalyzeTestRunTool(DataAnalysisTool):
    """测试运行分析工具"""

    def __init__(self):
        super().__init__(
            name="analyze_test_run",
            description="分析测试运行状态分布与失败率，支持按项目/周分组",
            parameters={
                "group_by": {
                    "type": "string",
                    "description": "分组维度",
                    "enum": ["week", "project"],
                    "default": "week"
                },
                "status_column": {
                    "type": "string",
                    "description": "测试运行状态列",
                    "default": "run_status"
                },
                "time_column": {
                    "type": "string",
                    "description": "时间列名（用于生成周）",
                    "default": "finished_udf_dt"
                }
            }
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {
                        "group_by": kwargs.get("group_by", "week"),
                        "rows": [],
                        "summary": {"overall_total": 0, "overall_failure": 0, "overall_failure_rate": 0}
                    },
                    "insights": ["测试数据为空，无法计算失败率"]
                }
            group_by = kwargs.get("group_by", "week")
            status_column = kwargs.get("status_column", "run_status")
            time_column = kwargs.get("time_column", "finished_udf_dt")

            df = data.copy()
            if status_column not in df.columns:
                return {"success": False, "tool": self.name, "error": f"列 {status_column} 不存在"}

            if group_by == "week":
                if time_column not in df.columns:
                    if "tcreationtime" in df.columns:
                        time_column = "tcreationtime"
                    elif "finished_udf" in df.columns:
                        time_column = "finished_udf"
                    else:
                        return {"success": False, "tool": self.name, "error": f"列 {time_column} 不存在"}
                df[time_column] = pd.to_datetime(df[time_column], errors="coerce")
                df["_time_group"] = df[time_column].dt.to_period("W").astype(str)
                group_cols = ["_time_group"]
                label_col = "_time_group"
            elif group_by == "project":
                project_col = "project" if "project" in df.columns else "tproject" if "tproject" in df.columns else None
                if not project_col:
                    return {"success": False, "tool": self.name, "error": "缺少 project/tproject 列"}
                group_cols = [project_col]
                label_col = project_col
            else:
                return {"success": False, "tool": self.name, "error": f"不支持的分组维度: {group_by}"}

            status_counts = (
                df.groupby(group_cols)[status_column]
                .value_counts(dropna=False)
                .unstack(fill_value=0)
                .reset_index()
            )

            status_cols = [c for c in status_counts.columns if c not in group_cols]
            status_counts["total"] = status_counts[status_cols].sum(axis=1)

            failure_keywords = ["fail", "failed", "error", "blocked", "aborted", "ng"]
            failure_cols = [c for c in status_cols if any(k in str(c).lower() for k in failure_keywords)]
            if failure_cols:
                status_counts["failure"] = status_counts[failure_cols].sum(axis=1)
            else:
                status_counts["failure"] = 0
            status_counts["failure_rate"] = np.where(
                status_counts["total"] > 0,
                (status_counts["failure"] / status_counts["total"] * 100).round(2),
                0.0
            )

            rows = []
            for _, row in status_counts.iterrows():
                bucket = row[label_col]
                row_dict = {"group": bucket, "total": int(row["total"]), "failure_rate": float(row["failure_rate"])}
                for c in status_cols:
                    row_dict[str(c)] = int(row[c])
                rows.append(row_dict)

            top_failure = sorted(rows, key=lambda r: r.get("failure_rate", 0), reverse=True)[:5]
            insights = []
            if top_failure:
                insights.append(f"失败率最高的分组: {top_failure[0]['group']} ({top_failure[0]['failure_rate']}%)")
            overall_total = int(status_counts["total"].sum())
            overall_failure = int(status_counts["failure"].sum())
            overall_rate = round(overall_failure / overall_total * 100, 2) if overall_total else 0
            insights.append(f"总体失败率: {overall_rate}%（失败 {overall_failure} / 总计 {overall_total}）")

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "group_by": group_by,
                    "rows": rows,
                    "summary": {
                        "overall_total": overall_total,
                        "overall_failure": overall_failure,
                        "overall_failure_rate": overall_rate
                    }
                },
                "insights": insights
            }
        except Exception as e:
            logger.error(f"测试运行分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}


class CorrelateDefectsTestsTool(DataAnalysisTool):
    """缺陷-测试关联洞察工具"""

    def __init__(self):
        super().__init__(
            name="correlate_defects_tests",
            description="按项目/周关联缺陷数量与测试失败率，发现高风险项目",
            parameters={
                "defect_time_col": {"type": "string", "default": "tcreationtime"},
                "defect_project_col": {"type": "string", "default": "tproject"},
                "test_time_col": {"type": "string", "default": "finished_udf_dt"},
                "test_project_col": {"type": "string", "default": "project"},
                "test_status_col": {"type": "string", "default": "run_status"},
                "top_n": {"type": "integer", "default": 10}
            }
        )

    def expects_datasets(self) -> bool:
        return True

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        try:
            datasets = data if isinstance(data, dict) else {}
            defects = datasets.get("defects")
            tests = datasets.get("tests")
            if defects is None or tests is None or defects.empty or tests.empty:
                return {
                    "success": True,
                    "tool": self.name,
                    "result": {"top": []},
                    "insights": ["缺陷或测试数据为空，无法进行联动关联分析"]
                }

            defect_time_col = kwargs.get("defect_time_col", "tcreationtime")
            defect_project_col = kwargs.get("defect_project_col", "tproject")
            test_time_col = kwargs.get("test_time_col", "finished_udf_dt")
            test_project_col = kwargs.get("test_project_col", "project")
            test_status_col = kwargs.get("test_status_col", "run_status")
            top_n = int(kwargs.get("top_n", 10))

            if defect_time_col not in defects.columns:
                for c in ["tcreationtime", "creation_time", "created_at"]:
                    if c in defects.columns:
                        defect_time_col = c
                        break
            if defect_project_col not in defects.columns:
                for c in ["tproject", "project"]:
                    if c in defects.columns:
                        defect_project_col = c
                        break
            ddf = defects[[c for c in [defect_time_col, defect_project_col, "_id", "severity_group", "severity"] if c in defects.columns]].copy()
            if defect_time_col not in ddf.columns or defect_project_col not in ddf.columns:
                return {"success": False, "tool": self.name, "error": "缺陷数据缺少时间列或项目列"}
            ddf[defect_time_col] = pd.to_datetime(ddf[defect_time_col], errors="coerce")
            ddf["week"] = ddf[defect_time_col].dt.to_period("W").astype(str)
            d_group = ddf.groupby([defect_project_col, "week"]).size().reset_index(name="defect_count")

            tcols = [c for c in [test_time_col, test_project_col, test_status_col] if c in tests.columns]
            tdf = tests[tcols].copy()
            if test_time_col not in tests.columns:
                for c in ["finished_udf_dt", "tcreationtime", "finished_udf"]:
                    if c in tests.columns:
                        test_time_col = c
                        break
            if test_project_col not in tests.columns:
                for c in ["project", "tproject"]:
                    if c in tests.columns:
                        test_project_col = c
                        break
            if test_status_col not in tests.columns:
                for c in ["run_status", "status"]:
                    if c in tests.columns:
                        test_status_col = c
                        break
            tcols = [c for c in [test_time_col, test_project_col, test_status_col] if c in tests.columns]
            tdf = tests[tcols].copy()
            if test_time_col not in tdf.columns or test_project_col not in tdf.columns or test_status_col not in tdf.columns:
                return {"success": False, "tool": self.name, "error": "测试数据缺少时间列/项目列/状态列"}
            tdf[test_time_col] = pd.to_datetime(tdf[test_time_col], errors="coerce")
            tdf["week"] = tdf[test_time_col].dt.to_period("W").astype(str)

            failure_keywords = ["fail", "failed", "error", "blocked", "aborted", "ng"]
            tdf["_is_failure"] = tdf[test_status_col].astype(str).str.lower().apply(lambda s: any(k in s for k in failure_keywords))
            t_group = tdf.groupby([test_project_col, "week"]).agg(
                test_total=("week", "size"),
                test_failure=("_is_failure", "sum")
            ).reset_index()
            t_group["failure_rate"] = np.where(
                t_group["test_total"] > 0,
                (t_group["test_failure"] / t_group["test_total"] * 100).round(2),
                0.0
            )

            merged = d_group.merge(
                t_group,
                left_on=[defect_project_col, "week"],
                right_on=[test_project_col, "week"],
                how="inner"
            )
            if merged.empty:
                return {"success": False, "tool": self.name, "error": "缺陷与测试在项目/周维度没有可关联的数据"}

            merged["risk_index"] = (merged["defect_count"] * (1 + merged["failure_rate"] / 100)).round(2)
            merged = merged.sort_values("risk_index", ascending=False)

            top_rows = []
            for _, r in merged.head(top_n).iterrows():
                top_rows.append({
                    "project": r[defect_project_col],
                    "week": r["week"],
                    "defect_count": int(r["defect_count"]),
                    "test_total": int(r["test_total"]),
                    "failure_rate": float(r["failure_rate"]),
                    "risk_index": float(r["risk_index"])
                })

            insights = [
                "风险指数 = 缺陷数 × (1 + 失败率)",
                f"最高风险组合: {top_rows[0]['project']} / {top_rows[0]['week']} (risk_index={top_rows[0]['risk_index']})"
            ]

            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "top": top_rows
                },
                "insights": insights
            }
        except Exception as e:
            logger.error(f"缺陷-测试关联分析失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}


class ToolExecutor:
    """工具执行器 - 管理所有工具的注册和执行"""

    def __init__(self):
        self.tools = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """注册默认工具"""
        default_tools = [
            TrendAnalysisTool(),
            RiskAnalysisTool(),
            ComparisonTool(),
            StatisticalSummaryTool(),
            MatrixDistributionTool(),
            MatrixAidaHotspotsTool(),
            TopIssueHotlistTool(),
            LongRunnerHotlistTool(),
            AnalyzeTesterFindingsTool(),
            AnalyzeTestRunTool(),
            CorrelateDefectsTestsTool()
        ]

        for tool in default_tools:
            self.register_tool(tool)

    def register_tool(self, tool: DataAnalysisTool):
        """注册新工具"""
        self.tools[tool.name] = tool
        logger.info(f"已注册工具: {tool.name}")

    def execute_tool(self, tool_name: str, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]], **kwargs) -> Dict[str, Any]:
        """执行工具"""
        if tool_name not in self.tools:
            return {"success": False, "tool": tool_name, "error": f"工具 '{tool_name}' 不存在"}

        tool = self.tools[tool_name]
        if isinstance(data, dict) and not tool.expects_datasets():
            dataset = kwargs.pop("dataset", None)
            if not dataset:
                dataset = "defects" if "defects" in data else next(iter(data.keys()), None)
            dataset_df = data.get(dataset) if dataset else None
            if dataset_df is None:
                return {"success": False, "tool": tool_name, "error": f"数据集中未找到 dataset={dataset}"}
            output = tool.execute(dataset_df, **kwargs)
        else:
            output = tool.execute(data, **kwargs)
        if output is None:
            return {"success": False, "tool": tool_name, "error": "工具未返回结果"}
        if isinstance(output, dict) and output.get("success") is False:
            output.setdefault("tool", tool_name)
            return output
        if isinstance(output, dict) and "success" not in output and "error" in output:
            return {"success": False, "tool": tool_name, "error": output.get("error") or "未知错误"}
        return output

    def get_tool_schema(self, tool_name: str = None) -> Dict:
        """获取工具的 schema，用于 LLM 理解"""
        if tool_name:
            if tool_name not in self.tools:
                return {}
            tool = self.tools[tool_name]
            return {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
        else:
            return {
                tool.name: {
                    "description": tool.description,
                    "parameters": tool.parameters
                }
                for tool in self.tools.values()
            }


# ============================================================================
# 2. 智能上下文管理器
# ============================================================================

class IntelligentContextManager:
    """智能上下文管理器 - 根据问题动态筛选相关数据"""

    def __init__(self):
        self.intent_patterns = {
            'trend': ['趋势', '变化', '增长', '下降', 'trend', 'change'],
            'risk': ['风险', '高风险', '危险', 'risk', 'critical'],
            'comparison': ['对比', '比较', '差异', 'vs', 'compare', 'difference'],
            'summary': ['总结', '概览', '总体', 'summary', 'overview'],
            'auto': ['一键', '自动', '综合', '全盘', '全景', '深度分析', '不用一个问题一个问题', 'dashboard', 'deep dive'],
            'distribution': ['分布', '占比', '比例', 'distribution', 'percentage'],
            'top': ['前', '最高', '最差', 'top', 'highest', 'worst', '最多', '最大', 'min', 'max'],
            'project': ['项目', '工程', 'project'],
            'severity': ['严重', '紧急', 'severity', 'critical'],
            'matrix': ['matrix', '矩阵'],
            'aida': ['aida', '功能', '模块', 'feature'],
            'test': ['测试', 'test', 'run', 'case', 'coverage', '执行', '通过率', '失败率'],
            'cross': ['关联', '相关性', '联动', '交叉', 'correlate', 'relationship'],
            'tester': ['tester', '发现人', '谁发现', '谁报', '谁提', '提交人', '报告人', 'reporter', 'found by']
        }

    def analyze_intent(self, question: str) -> List[str]:
        """分析问题意图"""
        question_lower = question.lower()
        detected_intents = []

        for intent, patterns in self.intent_patterns.items():
            if any(pattern in question_lower for pattern in patterns):
                detected_intents.append(intent)

        return detected_intents if detected_intents else ['general']

    def _wants_full_data(self, question: str) -> bool:
        q = (question or "").lower()
        return any(k in q for k in [
            "全量", "完整", "不要抽样", "不要采样", "不采样", "不抽样",
            "不要摘要", "不摘要", "不限制", "准确", "全面", "牺牲速度",
            "full", "all", "exact", "accurate", "no sampling"
        ])

    def extract_entities(self, question: str, data: pd.DataFrame) -> Dict[str, Any]:
        """提取问题中的实体（项目名、时间范围等）"""
        entities = {}

        # 提取项目名
        project_col = None
        if 'tproject' in data.columns:
            project_col = 'tproject'
        elif 'project' in data.columns:
            project_col = 'project'
        if project_col:
            projects = (
                data[project_col]
                .dropna()
                .astype(str)
                .map(lambda s: s.strip())
                .tolist()
            )
            projects = [p for p in dict.fromkeys(projects) if p and p.lower() not in {"nan", "none"}]
            q = question.lower()
            mentioned_projects = [p for p in projects if p.lower() in q]
            if mentioned_projects:
                entities['projects'] = mentioned_projects

        # 提取时间范围
        time_patterns = {
            'week': ['本周', '这周', 'week'],
            'month': ['本月', '这月', 'month', '最近一个月', '近一个月', '过去一个月', '最近30天', '近30天', '30天'],
            'quarter': ['本季度', '季度', 'quarter'],
            'year': ['今年', '本年', 'year'],
            'all': ['全量', '全部', '所有', '全历史', '不限制时间', 'all time']
        }

        for time_unit, patterns in time_patterns.items():
            if any(pattern in question.lower() for pattern in patterns):
                entities['time_range'] = time_unit
                break

        # 提取数字
        numbers = re.findall(r'\d+', question)
        if numbers:
            entities['numbers'] = [int(n) for n in numbers]

        return entities

    def prepare_context(self, question: str, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]) -> Tuple[Dict[str, Any], Union[pd.DataFrame, Dict[str, pd.DataFrame]]]:
        intents = self.analyze_intent(question)

        if isinstance(data, dict):
            datasets = {k: (v if isinstance(v, pd.DataFrame) else pd.DataFrame()) for k, v in data.items()}
            primary_dataset = self._choose_primary_dataset(question, intents, datasets)
            primary_df = self._normalize_dataset(datasets.get(primary_dataset, pd.DataFrame()), primary_dataset)
            entities = self.extract_entities(question, primary_df) if not primary_df.empty else {}

            prepared = {}
            context_views = {}
            dataset_meta = {}
            for name, df in datasets.items():
                norm = self._normalize_dataset(df, name)
                filtered = self._filter_data(norm, intents, entities, dataset=name)
                tool_df, tool_limit_info = self._apply_tool_limit(question, entities, filtered, dataset=name)
                sampled, sampling_info = self._apply_sampling(question, entities, tool_df, dataset=name)
                selected_columns = self._select_columns(intents, entities, sampled, dataset=name)
                context_df = sampled[selected_columns].copy() if selected_columns else sampled.copy()
                prepared[name] = tool_df
                context_views[name] = context_df
                dataset_meta[name] = {
                    'data_size': int(len(df)),
                    'filtered_size': int(len(filtered)),
                    'tool_size': int(len(tool_df)),
                    'context_size': int(len(context_df)),
                    'available_columns': df.columns.tolist() if isinstance(df, pd.DataFrame) else [],
                    'selected_columns': selected_columns,
                    'tool_limit': tool_limit_info,
                    'sampling': sampling_info
                }

            primary_context = context_views.get(primary_dataset, pd.DataFrame())
            context = {
                'intents': self._postprocess_intents(intents, datasets),
                'entities': entities,
                'primary_dataset': primary_dataset,
                'datasets': dataset_meta,
                'suggested_tools': self._suggest_tools(intents, entities),
                'data_summary': self._generate_data_summary(primary_context, intents, dataset=primary_dataset),
                'sample_rows': self._sample_rows(primary_context)
            }
            return context, prepared

        df = self._normalize_dataset(data, "defects")
        entities = self.extract_entities(question, df) if not df.empty else {}
        filtered_data = self._filter_data(df, intents, entities, dataset="defects")
        tool_df, tool_limit_info = self._apply_tool_limit(question, entities, filtered_data, dataset="defects")
        sampled, sampling_info = self._apply_sampling(question, entities, tool_df, dataset="defects")
        selected_columns = self._select_columns(intents, entities, sampled, dataset="defects")
        context_data = sampled[selected_columns].copy() if selected_columns else sampled.copy()

        context = {
            'intents': intents,
            'entities': entities,
            'primary_dataset': 'defects',
            'datasets': {
                'defects': {
                    'data_size': int(len(df)),
                    'filtered_size': int(len(filtered_data)),
                    'tool_size': int(len(tool_df)),
                    'context_size': int(len(context_data)),
                    'available_columns': df.columns.tolist(),
                    'selected_columns': selected_columns,
                    'tool_limit': tool_limit_info,
                    'sampling': sampling_info
                }
            },
            'suggested_tools': self._suggest_tools(intents, entities),
            'data_summary': self._generate_data_summary(context_data, intents, dataset="defects"),
            'sample_rows': self._sample_rows(context_data)
        }

        return context, tool_df

    def _postprocess_intents(self, intents: List[str], datasets: Dict[str, pd.DataFrame]) -> List[str]:
        out = list(intents)
        if 'tests' in datasets and 'defects' in datasets:
            if 'test' in intents and any(i in intents for i in ['risk', 'trend', 'comparison', 'summary']):
                if 'cross' not in out:
                    out.append('cross')
        return out

    def _choose_primary_dataset(self, question: str, intents: List[str], datasets: Dict[str, pd.DataFrame]) -> str:
        q = question.lower()
        if ('tests' in datasets) and any(k in q for k in ['测试', 'test', 'run', 'case', 'coverage']):
            if any(k in q for k in ['缺陷', 'defect', 'bug']):
                return 'defects' if 'defects' in datasets else 'tests'
            return 'tests'
        return 'defects' if 'defects' in datasets else next(iter(datasets.keys()), 'defects')

    def _normalize_dataset(self, df: pd.DataFrame, dataset: str) -> pd.DataFrame:
        if df is None:
            return pd.DataFrame()
        if isinstance(df, pd.DataFrame) and df.empty:
            out = df.copy()
            if dataset == "tests":
                if "run_status" not in out.columns and "status" in out.columns:
                    out["run_status"] = out["status"].apply(lambda x: x.get("name", "") if isinstance(x, dict) else str(x))
            return out
        out = df
        if dataset == "tests":
            if "project" in out.columns and "tproject" not in out.columns:
                out = out.copy()
                out["tproject"] = out["project"]
            if "run_status" not in out.columns and "status" in out.columns:
                if out is df:
                    out = out.copy()
                out["run_status"] = out["status"].apply(lambda x: x.get("name", "") if isinstance(x, dict) else str(x))
            if "finished_udf_dt" in out.columns and "tcreationtime" not in out.columns:
                if out is df:
                    out = out.copy()
                out["tcreationtime"] = out["finished_udf_dt"]
            if "tcreationtime" in out.columns:
                out["tcreationtime"] = pd.to_datetime(out["tcreationtime"], errors="coerce")
        else:
            if "project" not in out.columns and "ecu" in out.columns:
                out = out.copy()
                out["project"] = out["ecu"]
            if "project" in out.columns and "tproject" not in out.columns:
                out = out.copy()
                out["tproject"] = out["project"]
            if "tcreationtime" not in out.columns and "creation_time" in out.columns:
                out = out.copy()
                out["tcreationtime"] = out["creation_time"]
            if "tcreationtime" in out.columns:
                out["tcreationtime"] = pd.to_datetime(out["tcreationtime"], errors="coerce")
            if "severity_group" not in out.columns and "severity" in out.columns:
                if out is df:
                    out = out.copy()
                sev = out["severity"].astype(str).str.lower()
                out["severity_group"] = np.select(
                    [sev.str.contains("critical"), sev.str.contains("major"), sev.str.contains("minor")],
                    ["Critical", "Major", "Minor"],
                    default=out["severity"].astype(str)
                )
            if "severity_group" in out.columns:
                sev2 = out["severity_group"].astype(str).str.lower()
                mapped = np.select(
                    [sev2.str.contains("critical"), sev2.str.contains("major"), sev2.str.contains("minor")],
                    ["Critical", "Major", "Minor"],
                    default=out["severity_group"].astype(str)
                )
                if out is df:
                    out = out.copy()
                out["severity_group"] = mapped
            if "matrix_display" not in out.columns and "matrix" in out.columns:
                if out is df:
                    out = out.copy()
                out["matrix_display"] = out["matrix"].astype(str).str.replace("matrix-", "", regex=False).str.upper()
            if "topissue" not in out.columns:
                if out is df:
                    out = out.copy()
                if "is_topissue" in out.columns:
                    out["topissue"] = out["is_topissue"].apply(lambda v: "TopIssue" if bool(v) else "")
                elif "tags" in out.columns:
                    def _is_topissue(v):
                        if isinstance(v, list):
                            return any(str(x).lower() == "topissue" for x in v)
                        s = str(v)
                        return "topissue" in s.lower()
                    out["topissue"] = out["tags"].apply(lambda v: "TopIssue" if _is_topissue(v) else "")
                else:
                    out["topissue"] = out.get("topissue", "")
        return out

    def _select_columns(self, intents: List[str], entities: Dict[str, Any], data: pd.DataFrame, dataset: str = "defects") -> List[str]:
        columns = []
        if data is None or data.empty:
            return columns

        base = ['tproject', 'tcreationtime']
        for col in base:
            if col in data.columns:
                columns.append(col)

        if 'risk' in intents:
            for col in ['severity_group', 'topissue', 'matrix_display', 'category', 'status_phase']:
                if col in data.columns:
                    columns.append(col)

        if 'auto' in intents and dataset != "tests":
            for col in [
                'id', '_id', 'name', 'title', 'tproject', 'project', 'tcreationtime', 'creation_time',
                'tester', 'aida_english', 'aida', 'pu', 'domain', 'classification',
                'matrix_display', 'matrix', 'topissue', 'is_topissue',
                'topissue_risk_score', 'risk_score', 'processing_cycle_days', 'process_days',
                'status_phase', 'status'
            ]:
                if col in data.columns:
                    columns.append(col)

        if 'matrix' in intents and dataset != "tests":
            for col in ['matrix_display', 'matrix', 'severity_group', 'classification', 'is_topissue', 'topissue']:
                if col in data.columns:
                    columns.append(col)

        if ('aida' in intents) and dataset != "tests":
            for col in ['aida_english', 'aida', 'id', '_id', 'name', 'title', 'tproject', 'project', 'tcreationtime', 'creation_time', 'matrix_display', 'matrix']:
                if col in data.columns:
                    columns.append(col)

        if 'tester' in intents and dataset != "tests":
            for col in ['tester', 'id', '_id', 'name', 'title', 'aida_english', 'aida', 'pu', 'domain', 'classification']:
                if col in data.columns:
                    columns.append(col)

        if 'trend' in intents:
            for col in ['tcreationtime', 'tproject', 'severity_group', 'category']:
                if col in data.columns:
                    columns.append(col)

        if 'comparison' in intents:
            for col in ['tproject', 'severity_group', 'topissue', 'matrix_display', 'category']:
                if col in data.columns:
                    columns.append(col)

        if 'test' in intents or dataset == "tests":
            for col in ['run_status', 'finished_udf_dt', 'finished_udf', 'test_id', 'test_name', 'tester', 'aida_count', 'top_aida', 'pu']:
                if col in data.columns:
                    columns.append(col)

        if not columns:
            columns = data.columns[:12].tolist()

        seen = set()
        deduped = []
        for col in columns:
            if col not in seen:
                seen.add(col)
                deduped.append(col)
        return deduped

    def _sample_rows(self, data: pd.DataFrame, max_rows: int = 6) -> List[Dict[str, Any]]:
        if data is None or data.empty:
            return []
        sample = data.sample(n=min(max_rows, len(data)), random_state=42)
        return sample.fillna("").to_dict(orient='records')

    def _suggest_tools(self, intents: List[str], entities: Dict) -> List[str]:
        """根据意图和实体建议工具"""
        tools = []

        if 'trend' in intents:
            tools.append('analyze_trend')

        if 'risk' in intents:
            tools.append('analyze_risk')

        if 'comparison' in intents or any(key in entities for key in ['projects']):
            tools.append('compare_items')

        if 'test' in intents:
            tools.append('analyze_test_run')

        if 'cross' in intents:
            tools.append('correlate_defects_tests')

        if 'tester' in intents:
            tools.append('analyze_tester_findings')

        if 'matrix' in intents and 'aida' in intents:
            tools.append('analyze_matrix_aida_hotspots')
        elif 'matrix' in intents:
            tools.append('analyze_matrix_distribution')

        if not tools:
            tools.append('statistical_summary')

        return tools

    def _filter_data(self, data: pd.DataFrame, intents: List[str], entities: Dict, dataset: str = "defects") -> pd.DataFrame:
        """根据意图和实体筛选数据"""
        filtered = data
        if filtered is None:
            return pd.DataFrame()
        if isinstance(filtered, pd.DataFrame) and filtered.empty:
            return filtered

        # 按项目筛选
        if 'projects' in entities:
            project_col = 'tproject' if 'tproject' in filtered.columns else 'project' if 'project' in filtered.columns else None
            if project_col:
                filtered = filtered[filtered[project_col].isin(entities['projects'])]

        # 按时间筛选
        if 'time_range' in entities and 'tcreationtime' in filtered.columns:
            now = pd.Timestamp.now()
            tr = entities['time_range']
            if tr == 'week':
                start = now - timedelta(weeks=1)
                filtered = filtered[filtered['tcreationtime'] >= start]
            elif tr == 'month':
                start = now - timedelta(days=30)
                filtered = filtered[filtered['tcreationtime'] >= start]
            elif tr == 'quarter':
                start = now - timedelta(days=90)
                filtered = filtered[filtered['tcreationtime'] >= start]

        return filtered

    def _apply_sampling(self, question: str, entities: Dict[str, Any], data: pd.DataFrame, dataset: str, max_rows: int = 200_000) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        if data is None:
            return pd.DataFrame(), {"mode": "empty"}
        if isinstance(data, pd.DataFrame) and data.empty:
            return data, {"mode": "empty", "rows": 0}
        if self._wants_full_data(question):
            return data, {"mode": "none_forced", "rows": int(len(data))}
        q = question.lower()
        explicit_year = any(k in q for k in ["全年", "今年", "year", "年度", "2024", "2025"])
        explicit_time = 'time_range' in entities or explicit_year

        if len(data) <= max_rows:
            return data, {"mode": "none", "rows": int(len(data))}

        df = data
        mode = "downsample"
        detail = {}
        if "tcreationtime" in df.columns and not explicit_time:
            recent_days = 90 if dataset == "defects" else 120
            cutoff = pd.Timestamp.now() - timedelta(days=recent_days)
            before = len(df)
            df = df[df["tcreationtime"] >= cutoff]
            after = len(df)
            mode = "recent_window"
            detail = {"days": recent_days, "before": int(before), "after": int(after)}

        if len(df) > max_rows:
            before = len(df)
            df = df.sample(n=max_rows, random_state=42)
            mode = "sample"
            detail = {"before": int(before), "after": int(len(df))}

        return df, {"mode": mode, "rows": int(len(df)), **detail}

    def _apply_tool_limit(self, question: str, entities: Dict[str, Any], data: pd.DataFrame, dataset: str, max_rows: int = 2_000_000) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        if data is None:
            return pd.DataFrame(), {"mode": "empty"}
        if isinstance(data, pd.DataFrame) and data.empty:
            return data, {"mode": "empty", "rows": 0}
        if self._wants_full_data(question):
            return data, {"mode": "none_forced", "rows": int(len(data))}
        q = question.lower()
        explicit_year = any(k in q for k in ["全年", "今年", "year", "年度", "2024", "2025"])
        explicit_time = 'time_range' in entities or explicit_year

        df = data
        mode = "none"
        detail: Dict[str, Any] = {"rows": int(len(df))}

        if len(df) > max_rows and "tcreationtime" in df.columns and not explicit_time:
            recent_days = 365 if dataset == "defects" else 365
            cutoff = pd.Timestamp.now() - timedelta(days=recent_days)
            before = len(df)
            df = df[df["tcreationtime"] >= cutoff]
            mode = "recent_window"
            detail = {"days": recent_days, "before": int(before), "after": int(len(df))}

        if len(df) > max_rows:
            before = len(df)
            df = df.sample(n=max_rows, random_state=42)
            mode = "sample_for_tools"
            detail = {"before": int(before), "after": int(len(df))}

        return df, {"mode": mode, **detail}

    def _generate_data_summary(self, data: pd.DataFrame, intents: List[str], dataset: str = "defects") -> str:
        """生成数据摘要"""
        summary_parts = []

        summary_parts.append(f"数据集包含 {len(data)} 条记录")

        # 根据意图添加特定信息
        if 'risk' in intents:
            if 'severity_group' in data.columns:
                severity_dist = data['severity_group'].value_counts().to_dict()
                summary_parts.append(f"严重性分布: {severity_dist}")

        if 'project' in intents or 'comparison' in intents:
            if 'tproject' in data.columns:
                top_projects = data['tproject'].value_counts().head(5).to_dict()
                summary_parts.append(f"Top 5 项目: {top_projects}")

        if dataset == "tests" or 'test' in intents:
            if 'run_status' in data.columns:
                status_top = data['run_status'].astype(str).value_counts().head(6).to_dict()
                summary_parts.append(f"测试状态Top: {status_top}")

        return "\n".join(summary_parts)


# ============================================================================
# 3. 对话记忆系统
# ============================================================================

class ConversationMemory:
    """对话记忆系统 - 管理短期和长期记忆"""

    def __init__(self, max_short_term: int = 10, max_long_term: int = 100, memory_file: Optional[str] = None, autosave: bool = False):
        self.max_short_term = max_short_term
        self.max_long_term = max_long_term

        self.short_term = []
        self.long_term = []
        self.user_preferences = {}
        self.memory_file = memory_file
        self.autosave = autosave

        if self.memory_file:
            self._load()

    def add_message(self, role: str, content: str, metadata: Dict = None):
        """添加消息到短期记忆"""
        message = {
            'role': role,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }

        self.short_term.append(message)

        # 限制短期记忆大小
        if len(self.short_term) > self.max_short_term:
            # 将旧消息总结后存入长期记忆
            self._summarize_and_archive()
        if self.autosave:
            self.save()

    def _summarize_and_archive(self):
        if len(self.short_term) <= self.max_short_term:
            return

        archived = self.short_term[:len(self.short_term) - self.max_short_term]
        self.short_term = self.short_term[-self.max_short_term:]

        summary = self._summarize_messages(archived)
        if summary:
            self.long_term.append({
                'kind': 'summary',
                'content': summary,
                'timestamp': datetime.now().isoformat(),
                'importance': 0.7
            })

        for msg in archived:
            if msg['role'] == 'assistant' and len(msg['content']) > 80:
                importance = self._calculate_importance(msg)
                if importance >= 0.7:
                    self.long_term.append({
                        'kind': 'insight',
                        'content': msg['content'][:400],
                        'timestamp': msg['timestamp'],
                        'importance': importance
                    })

        # 限制长期记忆大小
        self.long_term.sort(key=lambda x: x['importance'], reverse=True)
        self.long_term = self.long_term[:self.max_long_term]

    def _calculate_importance(self, message: Dict) -> float:
        """计算消息重要性"""
        importance = 0.5

        content = message['content'].lower()

        # 包含关键词的消息更重要
        important_keywords = ['风险', '异常', '建议', 'improvement', '异常', 'critical']
        if any(keyword in content for keyword in important_keywords):
            importance += 0.3

        # 较长的消息可能包含更多信息
        if len(message['content']) > 100:
            importance += 0.2

        return min(importance, 1.0)

    def get_relevant_history(self, query: str, top_k: int = 3) -> List[Dict]:
        """获取相关历史记录（简单实现：基于关键词匹配）"""
        query_lower = query.lower()

        # 从短期记忆中搜索
        relevant = []

        for msg in self.short_term:
            if any(word in msg['content'].lower() for word in query_lower.split()):
                relevant.append(msg)

        # 从长期记忆中搜索
        for memory in self.long_term:
            content = memory.get('content', '')
            if content and any(word in content.lower() for word in query_lower.split()):
                relevant.append({
                    'role': 'assistant',
                    'content': content,
                    'timestamp': memory.get('timestamp'),
                    'from_memory': True
                })

        # 返回最相关的 top_k 条
        return relevant[:top_k]

    def save_preference(self, key: str, value: Any):
        """保存用户偏好"""
        self.user_preferences[key] = value
        self.user_preferences['updated_at'] = datetime.now().isoformat()
        if self.autosave:
            self.save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """获取用户偏好"""
        return self.user_preferences.get(key, default)

    def get_conversation_context(self) -> str:
        """获取对话上下文摘要"""
        context_parts = []

        if self.short_term:
            context_parts.append(f"当前对话包含 {len(self.short_term)} 条消息")

        if self.user_preferences:
            context_parts.append(f"用户偏好: {list(self.user_preferences.keys())}")

        return "\n".join(context_parts)

    def build_prompt_context(self, query: str, max_chars: int = 4000) -> str:
        parts = []
        if self.user_preferences:
            pref_items = {k: v for k, v in self.user_preferences.items() if k != 'updated_at'}
            if pref_items:
                parts.append(f"用户偏好: {pref_items}")

        recent = self.short_term[-self.max_short_term:]
        if recent:
            parts.append("最近对话：")
            for msg in recent:
                role = "用户" if msg.get('role') == 'user' else "助手"
                content = (msg.get('content') or '').strip()
                if content:
                    parts.append(f"{role}: {content}")

        memories = self.get_relevant_history(query, top_k=5)
        if memories:
            parts.append("相关记忆：")
            for m in memories:
                parts.append(f"- {m.get('content', '')}")

        text = "\n".join(parts)
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]

    def _summarize_messages(self, messages: List[Dict]) -> str:
        if not messages:
            return ""
        user_msgs = [m.get('content', '').strip() for m in messages if m.get('role') == 'user' and m.get('content')]
        assistant_msgs = [m.get('content', '').strip() for m in messages if m.get('role') == 'assistant' and m.get('content')]

        highlights = []
        for text in assistant_msgs[-3:]:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith(('-', '•')):
                    highlights.append(line.lstrip('-• ').strip())
                elif re.match(r'^\d+[\.\)]\s+', line):
                    highlights.append(re.sub(r'^\d+[\.\)]\s+', '', line))
        highlights = [h for h in highlights if 6 <= len(h) <= 120]
        highlights = highlights[:6]

        last_question = user_msgs[-1] if user_msgs else ""
        parts = []
        if last_question:
            parts.append(f"归档对话主题: {last_question[:120]}")
        if highlights:
            parts.append("要点: " + "；".join(highlights))
        if not parts:
            compact = " ".join((user_msgs + assistant_msgs)[-6:])
            return compact[:400]
        return "\n".join(parts)[:600]

    def _load(self):
        try:
            if not self.memory_file or not os.path.exists(self.memory_file):
                return
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            self.long_term = payload.get('long_term', []) or []
            self.user_preferences = payload.get('user_preferences', {}) or {}
        except Exception as e:
            logger.warning(f"加载记忆文件失败: {e}")

    def save(self):
        if not self.memory_file:
            return
        try:
            payload = {
                'long_term': self.long_term[-self.max_long_term:],
                'user_preferences': self.user_preferences
            }
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存记忆文件失败: {e}")


# ============================================================================
# 4. 知识库系统（RAG）
# ============================================================================

class KnowledgeBase:
    """知识库系统 - 提供领域知识"""

    def __init__(self, knowledge_file: str = None):
        self.knowledge = {}
        self._load_default_knowledge()

        if knowledge_file and os.path.exists(knowledge_file):
            self._load_from_file(knowledge_file)

    def _load_default_knowledge(self):
        """加载默认领域知识"""
        self.knowledge = {
            'defect_matrix': {
                '1A': '最高优先级 - 新发现且严重性高',
                '1B': '高优先级 - 重复发现且严重性高',
                '1C': '中高优先级 - 新发现且严重性中',
                '1D': '中高优先级 - 重复发现且严重性中',
                '1E': '中等优先级 - 新发现且严重性低',
                '2A': '中低优先级 - 特定条件下发现',
                '2B': '中低优先级 - 重复发现且严重性低',
                '2C': '低优先级 - 边缘情况',
                '2D': '低优先级 - 低影响',
                '2E': '极低优先级 - 微小影响'
            },
            'severity_levels': {
                'Critical': '可能导致系统崩溃、安全漏洞或数据丢失',
                'Major': '影响主要功能但系统仍可运行',
                'Minor': '影响次要功能或用户体验'
            },
            'risk_assessment': {
                'high': '风险评分 > 70，需要立即处理',
                'medium': '风险评分 40-70，需要计划处理',
                'low': '风险评分 < 40，可以延后处理'
            },
            'improvement_suggestions': {
                'reduction_trend': '缺陷数量呈下降趋势，说明质量改进措施有效',
                'increasing_trend': '缺陷数量呈上升趋势，建议：\n1. 加强代码审查\n2. 增加测试覆盖率\n3. 分析根本原因',
                'high_topissue': 'TopIssue 比例高，建议：\n1. 优先修复高影响缺陷\n2. 建立缺陷预防机制\n3. 加强回归测试'
            }
        }

    def _load_from_file(self, file_path: str):
        """从文件加载知识"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.knowledge.update(json.load(f))
            logger.info(f"已从文件加载知识库: {file_path}")
        except Exception as e:
            logger.warning(f"加载知识库文件失败: {e}")

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, str]]:
        """检索相关知识（简单实现：基于关键词匹配）"""
        query_lower = query.lower()
        retrieved = []

        # 简单的关键词匹配
        for category, items in self.knowledge.items():
            if any(keyword in query_lower for keyword in category.split('_')):
                for key, value in items.items():
                    retrieved.append({
                        'category': category,
                        'key': key,
                        'value': value
                    })

        return retrieved[:top_k]

    def get_knowledge_context(self, query: str) -> str:
        """获取知识的上下文描述"""
        relevant = self.retrieve(query)

        if not relevant:
            return ""

        context_parts = ["相关知识："]
        for item in relevant:
            context_parts.append(f"- {item['key']}: {item['value']}")

        return "\n".join(context_parts)


# ============================================================================
# 5. 任务规划器
# ============================================================================

class TaskPlanner:
    """任务规划器 - 分解复杂任务"""

    def __init__(self, tool_executor: ToolExecutor):
        self.tool_executor = tool_executor

    def plan(self, query: str, context: Dict) -> List[Dict]:
        """规划任务步骤"""
        steps = []

        intents = context.get('intents', [])
        entities = context.get('entities', {})
        primary_dataset = context.get('primary_dataset', 'defects')

        if 'auto' in intents:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_risk',
                'description': '分析风险（按project维度）',
                'params': {'dimension': 'project', 'top_n': 10, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_trend',
                'description': '分析趋势（按week分组）',
                'params': {'group_by': 'week', 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_matrix_distribution',
                'description': '分析缺陷矩阵分布',
                'params': {'include_unknown': True, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_matrix_aida_hotspots',
                'description': '分析 matrix×AIDA 热点',
                'params': {'top_matrices': 15, 'top_aidas': 5, 'sample_tickets': 3, 'include_unknown': True, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_tester_findings',
                'description': '分析发现问题最多的 tester',
                'params': {'top_n': 10, 'sample_per_tester': 5, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_topissue_hotlist',
                'description': '输出 TopIssue 高风险票据清单',
                'params': {'top_n': 20, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_longrunner_hotlist',
                'description': '输出 LongRunner 票据清单',
                'params': {'top_n': 20, 'dataset': 'defects'}
            })
            if 'tests' in (context.get('datasets') or {}):
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_test_run',
                    'description': '分析测试运行状态与失败率',
                    'params': {'group_by': 'week', 'dataset': 'tests'}
                })
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'correlate_defects_tests',
                    'description': '关联缺陷与测试，发现高风险项目',
                    'params': {'top_n': 10}
                })
            return steps

        # 根据意图创建步骤
        if 'trend' in intents:
            time_range = entities.get('time_range', 'week')
            group_by = 'week' if time_range == 'week' else 'month'
            steps.append({
                'step': 1,
                'tool': 'analyze_trend',
                'description': f'分析趋势（按{group_by}分组）',
                'params': {'group_by': group_by, 'dataset': primary_dataset}
            })

        if 'risk' in intents and primary_dataset != 'tests':
            dimension = entities.get('dimension', 'project')
            top_n = 10
            if isinstance(entities.get('numbers'), list) and entities['numbers']:
                top_n = max(1, min(int(entities['numbers'][0]), 50))
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_risk',
                'description': f'分析风险（按{dimension}维度）',
                'params': {'dimension': dimension, 'top_n': top_n, 'dataset': primary_dataset}
            })

        if 'comparison' in intents:
            if 'projects' in entities and entities['projects']:
                items = entities['projects']
                auto_mode = None
            else:
                items = []
                auto_mode = 'top_risk'
            steps.append({
                'step': len(steps) + 1,
                'tool': 'compare_items',
                'description': '对比项目',
                'params': {
                    'items': items,
                    'dimension': 'project',
                    '_auto': auto_mode,
                    'dataset': primary_dataset
                }
            })

        if 'test' in intents:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_test_run',
                'description': '分析测试运行状态与失败率',
                'params': {'group_by': 'week', 'dataset': 'tests'}
            })

        if 'cross' in intents:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'correlate_defects_tests',
                'description': '关联缺陷与测试，发现高风险项目',
                'params': {'top_n': 10}
            })

        if 'matrix' in intents and 'aida' in intents and primary_dataset != 'tests':
            ql = (query or "").lower()
            top_matrices = 10
            if any(k in ql for k in ['每个', '全部', '所有', 'all']):
                top_matrices = 30
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_matrix_aida_hotspots',
                'description': '分析 matrix×AIDA 热点',
                'params': {'top_matrices': top_matrices, 'top_aidas': 5, 'sample_tickets': 3, 'include_unknown': True, 'dataset': primary_dataset}
            })
        elif 'matrix' in intents and primary_dataset != 'tests':
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_matrix_distribution',
                'description': '分析缺陷矩阵分布',
                'params': {'include_unknown': True, 'dataset': primary_dataset}
            })

        if 'tester' in intents and primary_dataset != 'tests':
            top_n = 10
            if isinstance(entities.get('numbers'), list) and entities['numbers']:
                top_n = max(1, min(int(entities['numbers'][0]), 50))
            ql = (query or "").lower()
            sample_per_tester = 5
            if any(k in ql for k in ['都是什么', '详细', '列出', '列表', '明细', 'all']):
                sample_per_tester = 10
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_tester_findings',
                'description': '分析发现问题最多的 tester',
                'params': {'top_n': top_n, 'sample_per_tester': sample_per_tester, 'dataset': primary_dataset}
            })

        # 如果没有特定步骤，添加通用摘要
        if not steps:
            steps.append({
                'step': 1,
                'tool': 'statistical_summary',
                'description': '生成数据摘要',
                'params': {'dataset': primary_dataset}
            })

        return steps

    def execute_plan(self, steps: List[Dict], data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]) -> List[Dict]:
        """执行计划"""
        results = []

        for step in steps:
            tool_name = step['tool']
            params = step.get('params', {})

            if tool_name == 'compare_items':
                auto_mode = params.get('_auto')
                if (not params.get('items')) and auto_mode == 'top_risk':
                    for prev in results:
                        if prev.get('tool') == 'analyze_risk':
                            prev_out = prev.get('result') or {}
                            prev_res = prev_out.get('result') or {}
                            risk_items = prev_res.get('risk_items') or []
                            top_projects = [item.get('name') for item in risk_items[:2] if item.get('name')]
                            if len(top_projects) >= 2:
                                params = dict(params)
                                params['items'] = top_projects
                            break

            params = {k: v for k, v in params.items() if not str(k).startswith('_')}
            result = self.tool_executor.execute_tool(tool_name, data, **params)
            results.append({
                'step': step['step'],
                'tool': tool_name,
                'description': step['description'],
                'result': result
            })

        return results


# ============================================================================
# 6. 智能 Agent 主类
# ============================================================================

class IntelligentAgent:
    """智能 Agent - 整合所有功能"""

    def __init__(self, dashboard_type: str = 'general'):
        self.dashboard_type = dashboard_type

        # 初始化各组件
        self.tool_executor = ToolExecutor()
        self.context_manager = IntelligentContextManager()
        self.memory = ConversationMemory()
        self.knowledge_base = KnowledgeBase()
        self.task_planner = TaskPlanner(self.tool_executor)

        logger.info(f"智能 Agent 初始化完成 (类型: {dashboard_type})")

    def process(self, question: str, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]], conversation_history: List = None) -> Dict[str, Any]:
        """
        处理用户问题

        Args:
            question: 用户问题
            data: 数据 DataFrame 或多数据集字典
            conversation_history: 对话历史（可选）

        Returns:
            包含答案、工具调用结果、洞察等的字典
        """
        start_time = datetime.now()

        # 1. 保存用户消息到记忆
        self.memory.add_message('user', question)

        # 2. 准备上下文
        context, prepared_data = self.context_manager.prepare_context(question, data)

        # 3. 获取相关历史
        relevant_history = self.memory.get_relevant_history(question)

        # 4. 获取相关知识
        knowledge_context = self.knowledge_base.get_knowledge_context(question)

        # 5. 规划任务
        plan = self.task_planner.plan(question, context)

        # 6. 执行计划
        execution_results = self.task_planner.execute_plan(plan, prepared_data)

        # 7. 生成综合答案
        answer = self._generate_answer(
            question=question,
            context=context,
            execution_results=execution_results,
            knowledge_context=knowledge_context,
            relevant_history=relevant_history
        )

        # 8. 保存助手回复到记忆
        self.memory.add_message('assistant', answer['text'], {
            'tools_used': [r['tool'] for r in execution_results],
            'execution_time': (datetime.now() - start_time).total_seconds()
        })

        return answer

    def _generate_answer(self, question: str, context: Dict, execution_results: List[Dict],
                        knowledge_context: str, relevant_history: List) -> Dict[str, Any]:
        """生成综合答案"""
        answer_parts = []
        insights = []
        data_visualizations = []

        # 1. 开场白
        answer_parts.append(f"根据您的问题「{question}」，我进行了以下分析：\n")

        datasets_meta = context.get('datasets') or {}
        tool_limit_notes = []
        context_sampling_notes = []
        for name, meta in datasets_meta.items():
            tool_limit = (meta or {}).get('tool_limit') or {}
            tl_mode = tool_limit.get('mode')
            if tl_mode and tl_mode != 'none' and tl_mode != 'empty':
                tool_limit_notes.append(f"- 计算数据集[{name}] 采用 {tl_mode}")

            sampling = (meta or {}).get('sampling') or {}
            s_mode = sampling.get('mode')
            if s_mode and s_mode != 'none' and s_mode != 'empty':
                context_sampling_notes.append(f"- 上下文数据集[{name}] 采用 {s_mode}（rows={sampling.get('rows')}）")

        if tool_limit_notes or context_sampling_notes:
            answer_parts.append("\n为平衡速度与准确性，本次使用了如下策略：\n")
            if tool_limit_notes:
                answer_parts.append("计算侧：\n")
                answer_parts.extend([f"{n}\n" for n in tool_limit_notes])
            if context_sampling_notes:
                answer_parts.append("上下文侧（仅用于让模型阅读）：\n")
                answer_parts.extend([f"{n}\n" for n in context_sampling_notes])

        # 2. 工具执行结果
        for result in execution_results:
            tool_output = result.get('result') or {}
            if tool_output.get('success'):
                answer_parts.append(f"\n**{result['description']}**\n")

                tool_result = tool_output.get('result') or {}

                # 添加摘要
                if 'summary' in tool_result:
                    summary = tool_result['summary']
                    if 'direction' in summary:
                        answer_parts.append(
                            f"- 趋势方向: {summary['direction']}\n"
                            f"- 变化率: {summary['change_rate']}%\n"
                            f"- 总数: {summary['total']}\n"
                            f"- 平均: {summary['average']}\n"
                        )
                        data_visualizations.append({
                            'type': 'trend',
                            'data': tool_result.get('trend_data', [])
                        })

                # 添加风险分析
                if 'risk_items' in tool_result:
                    top_risks = tool_result['risk_items'][:5]
                    answer_parts.append(f"Top 5 高风险项目：\n")
                    for item in top_risks:
                        answer_parts.append(
                            f"- {item['name']}: 风险评分 {item['risk_score']}, "
                            f"缺陷数 {item['defect_count']}\n"
                        )
                    data_visualizations.append({
                        'type': 'risk',
                        'data': top_risks
                    })

                # 添加对比结果
                if 'comparisons' in tool_result:
                    for comp in tool_result['comparisons']:
                        answer_parts.append(
                            f"- {comp['name']}: {comp['metrics']}\n"
                        )

                if 'rows' in tool_result and result.get('tool') == 'analyze_test_run':
                    summary = tool_result.get('summary') or {}
                    answer_parts.append(
                        f"- 总测试执行数: {summary.get('overall_total', 0)}\n"
                        f"- 失败数: {summary.get('overall_failure', 0)}\n"
                        f"- 总体失败率: {summary.get('overall_failure_rate', 0)}%\n"
                    )
                    top_rows = sorted(tool_result.get('rows', []), key=lambda r: r.get('failure_rate', 0), reverse=True)[:5]
                    if top_rows:
                        answer_parts.append("失败率Top 5：\n")
                        for r in top_rows:
                            answer_parts.append(
                                f"- {r.get('group')}: 失败率 {r.get('failure_rate')}% (总计 {r.get('total')})\n"
                            )

                if result.get('tool') == 'correlate_defects_tests' and 'top' in tool_result:
                    top = tool_result.get('top') or []
                    answer_parts.append("缺陷-测试联动 Top：\n")
                    for row in top[:5]:
                        answer_parts.append(
                            f"- {row.get('project')} / {row.get('week')}: 缺陷 {row.get('defect_count')}, "
                            f"失败率 {row.get('failure_rate')}% (测试 {row.get('test_total')}), "
                            f"risk_index {row.get('risk_index')}\n"
                        )

                if result.get('tool') == 'analyze_matrix_distribution' and 'distribution' in tool_result:
                    total = tool_result.get('total', 0)
                    dist = tool_result.get('distribution') or []
                    answer_parts.append(f"- 缺陷总数（用于统计）：{total}\n")
                    if dist:
                        answer_parts.append("Matrix 分布：\n")
                        for r in dist:
                            answer_parts.append(f"- {r.get('matrix')}: {r.get('count')} ({r.get('ratio')}%)\n")

                if result.get('tool') == 'analyze_matrix_aida_hotspots' and 'matrices' in tool_result:
                    total = tool_result.get('total', 0)
                    matrices = tool_result.get('matrices') or []
                    answer_parts.append(f"- 缺陷总数（用于统计）：{total}\n")
                    if matrices:
                        for m in matrices:
                            answer_parts.append(f"\nMatrix {m.get('matrix')}（{m.get('matrix_total')} 条，占 {m.get('matrix_share')}%）：\n")
                            for a in (m.get('top_aidas') or []):
                                answer_parts.append(
                                    f"- {a.get('aida')}: {a.get('count')}（占该矩阵 {a.get('ratio_in_matrix')}%）\n"
                                )
                                samples = a.get('samples') or []
                                if samples:
                                    for s in samples:
                                        answer_parts.append(
                                            f"  - {s.get('id')}: {s.get('title')} ({s.get('project')}, {s.get('creation_time')})\n"
                                        )

                if result.get('tool') == 'analyze_topissue_hotlist' and 'rows' in tool_result:
                    rows = tool_result.get('rows') or []
                    total = tool_result.get('total', 0)
                    answer_parts.append(f"- TopIssue 总数（用于统计）：{total}\n")
                    if rows:
                        answer_parts.append("TopIssue Hotlist：\n")
                        for r in rows[:20]:
                            answer_parts.append(
                                f"- {r.get('id')}: {r.get('title')} (score={r.get('score')}, {r.get('project')}, {r.get('matrix')}, {r.get('aida')})\n"
                            )

                if result.get('tool') == 'analyze_longrunner_hotlist' and 'rows' in tool_result:
                    rows = tool_result.get('rows') or []
                    total = tool_result.get('total', 0)
                    answer_parts.append(f"- LongRunner 总数（用于统计）：{total}\n")
                    if rows:
                        answer_parts.append("LongRunner Hotlist：\n")
                        for r in rows[:20]:
                            answer_parts.append(
                                f"- {r.get('id')}: {r.get('title')} ({r.get('days')} 天, {r.get('project')}, {r.get('matrix')}, {r.get('status')})\n"
                            )

                if result.get('tool') == 'analyze_tester_findings' and 'top_testers' in tool_result:
                    total_defects = tool_result.get('total_defects', 0)
                    testers = tool_result.get('top_testers') or []
                    answer_parts.append(f"- 缺陷总数（用于统计）：{total_defects}\n")
                    if testers:
                        answer_parts.append("Top tester：\n")
                        for idx, t in enumerate(testers[:10]):
                            answer_parts.append(
                                f"- {t.get('tester')}: {t.get('defect_count')} 条（占 {t.get('share')}%），"
                                f"TopIssue {t.get('topissue_count')} 条（{t.get('topissue_ratio')}%）\n"
                            )
                            if t.get('top_projects'):
                                answer_parts.append(f"  - 主要项目: {t.get('top_projects')}\n")
                            if t.get('top_aidas'):
                                answer_parts.append(f"  - 主要AIDA: {t.get('top_aidas')}\n")
                            if t.get('samples'):
                                answer_parts.append("  - 代表性缺陷样本:\n")
                                sample_cap = 8 if idx == 0 and len(t.get('samples') or []) > 3 else 3
                                for s in (t.get('samples') or [])[:sample_cap]:
                                    answer_parts.append(
                                        f"    - {s.get('id')}: {s.get('title')} "
                                        f"({s.get('project')}, {s.get('severity')}, {s.get('matrix')}, {s.get('creation_time')})\n"
                                    )

                # 添加统计摘要
                if 'total_records' in tool_result:
                    answer_parts.append(f"- 总记录数: {tool_result['total_records']}\n")

                # 添加洞察
                if tool_output.get('insights'):
                    insights.extend(tool_output['insights'])
            else:
                error_msg = tool_output.get('error')
                if error_msg:
                    answer_parts.append(f"\n**{result['description']}**\n- 执行失败: {error_msg}\n")

        # 3. 添加相关知识
        if knowledge_context:
            answer_parts.append(f"\n**参考知识**\n{knowledge_context}\n")

        # 4. 添加历史上下文
        if relevant_history:
            answer_parts.append(f"\n**相关历史对话**\n")
            for hist in relevant_history[:2]:
                answer_parts.append(f"- {hist['content'][:100]}...\n")

        # 5. 综合洞察和建议
        if insights:
            answer_parts.append(f"\n**关键洞察**\n")
            for i, insight in enumerate(insights[:5], 1):
                answer_parts.append(f"{i}. {insight}\n")

        # 6. 建议和后续行动
        answer_parts.append(f"\n**建议**\n")
        answer_parts.append(self._generate_recommendations(context, execution_results))

        return {
            'text': ''.join(answer_parts),
            'insights': insights,
            'visualizations': data_visualizations,
            'tools_used': [r['tool'] for r in execution_results],
            'context': context
        }

    def _generate_recommendations(self, context: Dict, execution_results: List[Dict]) -> str:
        """生成改进建议"""
        recommendations = []

        intents = context.get('intents', [])

        # 根据分析结果生成建议
        for result in execution_results:
            tool_output = result.get('result') or {}
            if tool_output.get('success'):
                tool_result = tool_output.get('result') or {}

                # 趋势建议
                if 'summary' in tool_result:
                    summary = tool_result['summary']
                    if summary.get('direction') == '上升':
                        recommendations.append(
                            "- 缺陷数量呈上升趋势，建议加强代码审查和测试覆盖率\n"
                        )

                # 风险建议
                if 'risk_items' in tool_result:
                    risk_items = tool_result.get('risk_items') or []
                    if risk_items:
                        top_risk = risk_items[0]
                        if top_risk.get('risk_score', 0) > 70:
                            recommendations.append(
                                f"- 最高风险项目 '{top_risk.get('name')}' 评分 {top_risk.get('risk_score')}，"
                                f"建议优先处理其中的 TopIssue\n"
                            )

                # 对比建议
                if 'comparisons' in tool_result:
                    recommendations.append(
                        "- 建议对比表现较好项目的实践，推广到其他项目\n"
                    )

        # 通用建议
        if not recommendations:
            recommendations.append("- 建议定期监控关键指标，及时发现和解决问题\n")
            recommendations.append("- 加强团队协作和知识分享\n")

        return ''.join(recommendations)

    def get_enhanced_system_prompt(self, data_context: str = "") -> str:
        """获取增强的系统提示词"""
        # 从统一提示词模块读取，包含工具能力说明
        try:
            from prompts import DATA_ANALYSIS_PROMPTS
            base_prompt = DATA_ANALYSIS_PROMPTS.get(
                self.dashboard_type,
                DATA_ANALYSIS_PROMPTS['general']
            )
        except ImportError:
            base_prompt = "你是 BMW 汽车测试数据分析和缺陷管理专家助手。"

        # 补充工具能力说明
        tool_info = """
**工具能力：**
- analyze_trend: 分析数据趋势
- analyze_risk: 评估风险分布
- compare_items: 对比不同项
- statistical_summary: 生成统计摘要
"""
        prompt = base_prompt + tool_info

        if data_context:
            prompt += f"\n**当前数据上下文：**\n{data_context}\n"

        return prompt

    def get_tool_schemas_for_llm(self) -> List[Dict]:
        """获取工具的 schema 格式，用于 LLM 函数调用"""
        schemas = []

        for tool_name, schema in self.tool_executor.get_tool_schema().items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": schema['name'],
                    "description": schema['description'],
                    "parameters": schema['parameters']
                }
            })

        return schemas


# ============================================================================
# 7. 工厂函数
# ============================================================================

def create_agent(dashboard_type: str = 'general') -> IntelligentAgent:
    """创建智能 Agent 实例"""
    return IntelligentAgent(dashboard_type)


def create_agent_for_defect() -> IntelligentAgent:
    """创建缺陷分析专用 Agent"""
    return IntelligentAgent('defect')


def create_agent_for_test() -> IntelligentAgent:
    """创建测试分析专用 Agent"""
    return IntelligentAgent('test')


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    'IntelligentAgent',
    'create_agent',
    'create_agent_for_defect',
    'create_agent_for_test',
    'create_agent_with_smart_loading',
    'ToolExecutor',
    'IntelligentContextManager',
    'ConversationMemory',
    'KnowledgeBase',
    'TaskPlanner',
    'SmartAgent'
]


# ============================================================================
# 8. 智能 Agent V2 - 集成智能上下文引擎
# ============================================================================

class SmartAgent(IntelligentAgent):
    """
    智能Agent V2 - 集成智能上下文引擎
    
    相比原版 IntelligentAgent 的改进：
    1. 智能数据加载 - 根据问题按需加载数据
    2. 渐进式上下文 - Token 消耗降低 60%+
    3. 语义检索 - 找到最相关的数据
    4. 缓存机制 - 避免重复加载
    """
    
    def __init__(
        self,
        dashboard_type: str = 'general',
        db_path: str = "",
        use_smart_loading: bool = True
    ):
        """
        初始化智能Agent V2
        
        Args:
            dashboard_type: 看板类型 ('defect', 'test', 'general')
            db_path: 数据库路径
            use_smart_loading: 是否使用智能加载
        """
        super().__init__(dashboard_type)
        
        self.db_path = db_path
        self.use_smart_loading = use_smart_loading
        
        # 初始化智能数据加载器
        if use_smart_loading:
            try:
                from smart_data_loader import SmartDataLoader, LoaderConfig
                
                config = LoaderConfig(
                    db_path=db_path,
                    use_smart_loading=True,
                    use_semantic_search=True
                )
                self.smart_loader = SmartDataLoader(config)
                self._context_cache = {}  # 加载上下文缓存
                logger.info("✅ 智能数据加载器初始化成功")
            except ImportError as e:
                logger.warning(f"⚠️ 智能数据加载器不可用: {e}")
                self.smart_loader = None
        else:
            self.smart_loader = None
    
    def process_with_smart_loading(
        self,
        question: str,
        data: Optional[Union[pd.DataFrame, Dict[str, pd.DataFrame]]] = None,
        conversation_history: List = None
    ) -> Dict[str, Any]:
        """
        使用智能加载处理问题
        
        如果未提供 data，会根据问题智能加载数据
        
        Args:
            question: 用户问题
            data: 数据（可选，如果不提供则智能加载）
            conversation_history: 对话历史
            
        Returns:
            包含答案、加载信息、工具调用结果等的字典
        """
        start_time = datetime.now()
        load_info = {}
        
        # 1. 如果没有提供数据，使用智能加载
        if data is None and self.smart_loader:
            logger.info("使用智能数据加载...")
            
            # 分析问题意图
            if hasattr(self.smart_loader, 'context_engine') and self.smart_loader.context_engine:
                intent = self.smart_loader.context_engine.intent_analyzer.analyze(question)
                load_info['intent'] = {
                    'data_type': intent.data_type,
                    'project': intent.project,
                    'time_range': intent.time_range,
                    'focus': intent.focus,
                    'confidence': intent.confidence
                }
            
            # 智能加载数据
            if self.dashboard_type == 'defect':
                data, load_context = self.smart_loader.load_defects(question)
                load_info['load_context'] = {
                    'token_count': load_context.token_count,
                    'relevance_score': load_context.relevance_score,
                    'sources': load_context.sources
                }
            elif self.dashboard_type == 'test':
                data, load_context = self.smart_loader.load_tests(question)
                load_info['load_context'] = {
                    'token_count': load_context.token_count,
                    'relevance_score': load_context.relevance_score,
                    'sources': load_context.sources
                }
            else:
                # 通用类型，加载所有
                all_data = self.smart_loader.load_all(question)
                data = {}
                load_info['load_context'] = {}
                for name, (df, ctx) in all_data.items():
                    data[name] = df
                    load_info['load_context'][name] = {
                        'token_count': ctx.token_count,
                        'relevance_score': ctx.relevance_score,
                        'sources': ctx.sources
                    }
            
            load_info['method'] = 'smart_loading'
            logger.info(f"智能加载完成，Token 节省: {self._calculate_token_saving(load_info)}%")
        
        # 2. 调用父类处理方法
        result = super().process(question, data, conversation_history)
        
        # 3. 添加加载信息到结果
        result['load_info'] = load_info
        result['execution_time'] = (datetime.now() - start_time).total_seconds()
        
        return result
    
    def _calculate_token_saving(self, load_info: Dict) -> float:
        """计算 Token 节省百分比"""
        if 'load_context' not in load_info:
            return 0
        
        # 假设全量加载约 120,000 tokens
        FULL_LOAD_TOKENS = 120000
        
        # 计算实际加载的 tokens
        if isinstance(load_info['load_context'], dict):
            if 'token_count' in load_info['load_context']:
                actual_tokens = load_info['load_context']['token_count']
            else:
                actual_tokens = sum(
                    ctx.get('token_count', 0) 
                    for ctx in load_info['load_context'].values()
                    if isinstance(ctx, dict)
                )
        else:
            return 0
        
        if actual_tokens > 0:
            saving = (1 - actual_tokens / FULL_LOAD_TOKENS) * 100
            return max(0, min(100, saving))
        return 0
    
    def get_data_summary(self, question: str = "") -> Dict[str, Any]:
        """
        获取数据摘要（不加载全部数据）
        
        Args:
            question: 用户问题（用于意图理解）
            
        Returns:
            数据摘要字典
        """
        if not self.smart_loader or not self.smart_loader.context_engine:
            return {"error": "智能加载器不可用"}
        
        # 分析意图
        intent = self.smart_loader.context_engine.intent_analyzer.analyze(question)
        
        # 获取摘要
        summary = self.smart_loader.context_engine.get_defect_summary(
            project=intent.project,
            time_range=intent.time_range
        )
        
        return {
            'total_count': summary.total_count,
            'time_range': summary.time_range,
            'key_metrics': summary.key_metrics,
            'top_items': summary.top_items,
            'intent': {
                'project': intent.project,
                'time_range': intent.time_range,
                'focus': intent.focus
            }
        }


def create_agent_with_smart_loading(
    dashboard_type: str = 'general',
    db_path: str = ""
) -> SmartAgent:
    """
    创建带智能加载的 Agent 实例
    
    Args:
        dashboard_type: 看板类型
        db_path: 数据库路径
        
    Returns:
        SmartAgent 实例
    """
    return SmartAgent(dashboard_type, db_path, use_smart_loading=True)


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    print("智能 Agent 系统")
    print("=" * 50)
    
    # 测试智能 Agent
    print("\n测试 SmartAgent...")
    agent = create_agent_with_smart_loading(
        dashboard_type='defect',
        db_path='database/local_data.db'
    )
    
    # 测试智能加载
    question = "最近两周 ABS 模块的缺陷趋势"
    print(f"\n问题: {question}")
    
    # 获取数据摘要
    summary = agent.get_data_summary(question)
    print(f"数据摘要: {summary}")


    # 创建测试数据
    test_data = pd.DataFrame({
        '_id': range(1, 101),
        'tproject': ['Project_A'] * 50 + ['Project_B'] * 30 + ['Project_C'] * 20,
        'severity_group': ['Critical'] * 10 + ['Major'] * 40 + ['Minor'] * 50,
        'category': ['Functional'] * 60 + ['Performance'] * 25 + ['UI'] * 15,
        'topissue': ['TopIssue'] * 20 + [''] * 80,
        'matrix_display': ['1A'] * 5 + ['1B'] * 10 + ['1C'] * 15 + ['2A'] * 30 + ['2B'] * 40,
        'tcreationtime': pd.date_range('2025-01-01', periods=100, freq='D')
    })

    # 创建 Agent
    agent = create_agent_for_defect()

    print("\n测试问题:")
    questions = [
        "分析缺陷趋势",
        "哪个项目的风险最高？",
        "对比 Project_A 和 Project_B 的情况"
    ]

    for question in questions:
        print(f"\n问题: {question}")
        print("-" * 50)

        result = agent.process(question, test_data)

        print(result['text'][:500] + "..." if len(result['text']) > 500 else result['text'])

        if result['insights']:
            print("\n关键洞察:")
            for insight in result['insights']:
                print(f"- {insight}")

        print(f"\n使用的工具: {result['tools_used']}")

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
import sqlite3
import time
import multiprocessing
from functools import lru_cache
from collections import defaultdict
import logging
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis_utils import (
    compute_defect_explore_kpis,
    defect_quality_stats,
    defect_wordcloud_source,
    inflow_outflow_summary,
    longrunner_phase_statistics,
    nunique_by,
    pick_risk_score_column,
    severity_rate_by,
    stacked_top_counts,
    time_series_counts,
    top_counts,
    word_frequencies,
)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _tokenize_text(text: str) -> List[str]:
    if not text:
        return []
    toks = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", str(text).lower())
    out = []
    for t in toks:
        s = str(t).strip()
        if not s or len(s) <= 1:
            continue
        out.append(s)
    return out


@lru_cache(maxsize=16)
def _semantic_core_dimensions(dataset: str) -> List[Dict[str, Any]]:
    try:
        from semantic_catalog.runtime import SemanticCatalog

        catalog = SemanticCatalog().load_catalog() or {}
        dkey = str(dataset or "").strip().lower()
        for ds in (catalog.get("datasets") or []):
            aliases = [str(a).strip().lower() for a in (ds.get("aliases") or [])]
            if str(ds.get("id", "")).strip().lower() == dkey or dkey in aliases:
                dims = ds.get("core_dimensions") or []
                return [d for d in dims if isinstance(d, dict)]
    except Exception:
        return []
    return []


def _resolve_dimension_to_column(dataset: str, dim_or_alias: str, dataframe_columns: List[str]) -> Optional[str]:
    if not dim_or_alias:
        return None
    cols = [str(c) for c in (dataframe_columns or [])]
    col_set = set(cols)
    raw = str(dim_or_alias).strip()
    if raw in col_set:
        return raw
    key = raw.lower()
    for d in _semantic_core_dimensions(str(dataset or "").strip().lower()):
        name = str(d.get("name", "")).strip()
        if not name:
            continue
        aliases = [str(a).strip() for a in (d.get("aliases") or []) if a is not None and str(a).strip()]
        alias_l = [a.lower() for a in aliases]
        if key == name.lower() or key in alias_l:
            if name in col_set:
                return name
            for a in aliases:
                if a in col_set:
                    return a
    if key in col_set:
        return key
    for c in cols:
        if c.lower() == key:
            return c
    return None

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
            else:
                dataset = str(kwargs.get("dataset") or "defects").strip().lower()
                actual_col = _resolve_dimension_to_column(dataset, group_by, list(data.columns))
                if not actual_col:
                    fallback = {
                        "project": ["tproject", "project"],
                        "aida": ["aida_english", "top_aida", "aida"],
                        "severity": ["severity_group", "severity"],
                        "status": ["status_phase", "status"],
                        "matrix": ["matrix_display", "matrix"],
                    }
                    for c in fallback.get(str(group_by).strip().lower(), []):
                        if c in data.columns:
                            actual_col = c
                            break
                if not actual_col or actual_col not in data.columns:
                    return {"success": False, "tool": self.name, "error": f"列 {group_by} 不存在"}
                group_cols = [actual_col]
                label_col = actual_col

            # 执行分组统计
            if metric == 'count':
                result = data.groupby(group_cols).size().reset_index(name='value')
            elif metric == 'unique':
                unique_col = None
                for c in ['_id', 'id', 'ticket_id']:
                    if c in data.columns:
                        unique_col = c
                        break
                if not unique_col:
                    result = data.groupby(group_cols).size().reset_index(name='value')
                else:
                    result = data.groupby(group_cols).agg({unique_col: 'nunique'}).reset_index(name='value')
            else:
                numeric_cols = data.select_dtypes(include=[np.number]).columns
                if len(numeric_cols) == 0:
                    return {"success": False, "tool": self.name, "error": "没有数值列可用于聚合"}
                result = data.groupby(group_cols)[numeric_cols[0]].agg(metric).reset_index(name='value')

            if group_by not in ['week', 'month']:
                result = result.sort_values('value', ascending=False).head(20)

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

            dataset = str(kwargs.get("dataset") or "defects").strip().lower()
            group_col = _resolve_dimension_to_column(dataset, str(dimension), list(data.columns))
            if not group_col:
                fallback = {
                    "project": ["tproject", "project"],
                    "matrix": ["matrix_display", "matrix"],
                    "severity": ["severity_group", "severity"],
                    "category": ["category"],
                }
                for c in fallback.get(str(dimension).strip().lower(), []):
                    if c in data.columns:
                        group_col = c
                        break

            if group_col not in data.columns:
                return {"success": False, "tool": self.name, "error": f"列 {group_col} 不存在"}

            # 计算风险评分
            def calculate_risk_score(group):
                """计算风险评分"""
                score_col = pick_risk_score_column(group)
                if score_col:
                    s = pd.to_numeric(group[score_col], errors="coerce")
                    if s.notna().any():
                        return float(round(s.mean(), 2))

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

            # 映射维度列名
            col_mapping = {
                'project': 'tproject',
                'severity': 'severity_group',
                'category': 'category'
            }
            group_col = col_mapping.get(dimension, dimension)
            if dimension == 'project':
                if 'project' in data.columns and 'tproject' in data.columns:
                    expected = {"idc", "idcevo", "mgu", "rsu", "app"}
                    p = data['project'].astype(str).str.strip().str.lower()
                    tp = data['tproject'].astype(str).str.strip().str.lower()
                    p_hits = int(p.isin(expected).sum())
                    tp_hits = int(tp.isin(expected).sum())
                    group_col = 'project' if p_hits >= tp_hits else 'tproject'
                elif group_col == 'tproject' and group_col not in data.columns and 'project' in data.columns:
                    group_col = 'project'

            if group_col not in data.columns:
                return {"success": False, "tool": self.name, "error": f"列 {group_col} 不存在"}

            if not items:
                if dimension == 'project':
                    s = data[group_col].fillna("").astype(str).str.strip()
                    s = s[s != ""]
                    if s.empty:
                        return {"success": False, "tool": self.name, "error": "项目字段为空，无法自动选择对比项目"}
                    items = s.value_counts().head(3).index.tolist()
                else:
                    return {"success": False, "tool": self.name, "error": "请提供要对比的项目"}

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
                        score_col = pick_risk_score_column(item_data)
                        if score_col:
                            s = pd.to_numeric(item_data[score_col], errors="coerce")
                            score = float(s.mean()) if s.notna().any() else 0.0
                        else:
                            score = 0
                            score += min(len(item_data) / 100 * 30, 30)
                            if 'severity_group' in item_data.columns:
                                severity_weights = {'Critical': 40, 'Major': 25, 'Minor': 10}
                                avg_severity = item_data['severity_group'].map(severity_weights).mean()
                                score += avg_severity if pd.notna(avg_severity) else 15
                        result['metrics']['avg_risk_score'] = round(float(score), 2)
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


class DefectExploreKpiTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="defect_explore_kpis",
            description="生成 Defect Explore 看板常用 KPI（总缺陷、严重缺陷率、活跃 tester、日均缺陷等）",
            parameters={
                "start_date": {"type": "string", "description": "筛选起始日期(YYYY-MM-DD)，可为空", "default": ""},
                "end_date": {"type": "string", "description": "筛选结束日期(YYYY-MM-DD)，可为空", "default": ""},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            start_date = (kwargs.get("start_date") or "").strip() or None
            end_date = (kwargs.get("end_date") or "").strip() or None
            kpis = compute_defect_explore_kpis(data, start_date=start_date, end_date=end_date)
            insights = []
            insights.append(f"总缺陷数: {kpis.get('total_defects', 0)}")
            insights.append(f"严重缺陷率: {kpis.get('severe_rate', 0)}%")
            if kpis.get("top_tester"):
                insights.append(f"最活跃 tester: {kpis.get('top_tester')}")
            if kpis.get("daily_avg", 0) > 0:
                insights.append(f"日均缺陷: {kpis.get('daily_avg')}")
            return {"success": True, "tool": self.name, "result": kpis, "insights": insights}
        except Exception as e:
            logger.error(f"Defect Explore KPI 计算失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}


class DefectExploreDashboardTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="defect_explore_dashboard",
            description="按 Defect Explore 看板口径汇总业务图表指标，并根据自然语言选择相关图表输出",
            parameters={
                "question": {"type": "string", "description": "用户自然语言问题（用于选择相关图表）", "default": ""},
                "max_items": {"type": "integer", "description": "每个图表最多输出条目数", "default": 15},
                "include_inflow_outflow": {"type": "boolean", "description": "是否包含 Inflow/Outflow（需 history 数据）", "default": False},
                "include_longrunner": {"type": "boolean", "description": "是否包含 LongRunner phase 耗时统计（需 history 数据）", "default": False},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            df = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
            question = (kwargs.get("question") or "").strip()
            q = question.lower()
            max_items = int(kwargs.get("max_items", 15))
            include_inflow_outflow = bool(kwargs.get("include_inflow_outflow", True))
            include_longrunner = bool(kwargs.get("include_longrunner", False))

            def wants_all() -> bool:
                return any(k in q for k in [
                    "所有", "全部", "全量", "全景", "全看板", "全部图表", "所有图表", "dashboard", "图表总览", "看板总览",
                    "测试策略", "测试计划", "测试方案", "质量策略", "策略", "计划"
                ])

            def want(keys: List[str]) -> bool:
                if wants_all():
                    return True
                return any(k in q for k in keys)

            def want_strict(keys: List[str]) -> bool:
                return any(k in q for k in keys)

            charts: List[Dict[str, Any]] = []

            if df is None or df.empty:
                return {"success": True, "tool": self.name, "result": {"charts": [], "note": "当前缺陷数据为空"}, "insights": ["缺陷数据为空，无法生成看板图表指标"]}

            aida_col = "top_aida" if "top_aida" in df.columns else "aida_english" if "aida_english" in df.columns else "aida" if "aida" in df.columns else None
            time_col = "creation_time" if "creation_time" in df.columns else "tcreationtime" if "tcreationtime" in df.columns else None
            domain_col = "domain_display" if "domain_display" in df.columns else "domain" if "domain" in df.columns else None
            project_col = "project" if "project" in df.columns else "tproject" if "tproject" in df.columns else "ecu" if "ecu" in df.columns else None
            status_col = "status_phase" if "status_phase" in df.columns else "status" if "status" in df.columns else None
            fv_col = "fv" if "fv" in df.columns else None
            matrix_col = "matrix_display" if "matrix_display" in df.columns else "matrix" if "matrix" in df.columns else None

            if want(["kpi", "指标", "卡片", "概览", "总览"]):
                kpis = compute_defect_explore_kpis(df)
                charts.append({"id": "kpi-cards", "title": "KPI 卡片", "data": kpis})

            if want(["fv", "版本", "release"]):
                if fv_col and "severity_group" in df.columns:
                    charts.append({"id": "fv-distribution-chart", "title": "Top Issue by FV", "data": stacked_top_counts(df, fv_col, "severity_group", top_n=max_items)})
                elif fv_col:
                    charts.append({"id": "fv-distribution-chart", "title": "Top Issue by FV", "data": top_counts(df, fv_col, top_n=max_items)})

            if want(["aida", "功能", "模块"]):
                if aida_col and "severity_group" in df.columns:
                    charts.append({"id": "defect-status-chart", "title": "Top Issue by AIDA", "data": stacked_top_counts(df, aida_col, "severity_group", top_n=max_items)})
                elif aida_col:
                    charts.append({"id": "defect-status-chart", "title": "Top Issue by AIDA", "data": top_counts(df, aida_col, top_n=max_items)})

            if want(["solution cluster", "cluster", "domain", "解决簇", "解决群"]):
                if domain_col and "severity_group" in df.columns:
                    charts.append({"id": "solution-cluster-chart", "title": "Top Issue by Solution Cluster", "data": stacked_top_counts(df, domain_col, "severity_group", top_n=max_items)})
                elif domain_col:
                    charts.append({"id": "solution-cluster-chart", "title": "Top Issue by Solution Cluster", "data": top_counts(df, domain_col, top_n=max_items)})

            if want(["tester", "测试人员", "发现人", "谁发现"]):
                if "tester" in df.columns and "severity_group" in df.columns:
                    charts.append({"id": "tester-efficiency-chart", "title": "Tester Efficiency", "data": stacked_top_counts(df, "tester", "severity_group", top_n=min(20, max_items))})
                    charts.append({"id": "tester-severity-chart", "title": "Tester Severe Rate", "data": severity_rate_by(df, "tester", top_n=min(30, max_items))})

            if want(["状态", "status", "phase"]):
                if status_col:
                    charts.append({"id": "defect-status-distribution-chart", "title": "Status Distribution", "data": top_counts(df, status_col, top_n=max_items)})
                if status_col and "severity_group" in df.columns:
                    charts.append({"id": "status-transition-efficiency-chart", "title": "Status × Severity", "data": stacked_top_counts(df, status_col, "severity_group", top_n=max_items)})

            if want(["矩阵", "matrix"]):
                if matrix_col:
                    charts.append({"id": "defect-matrix-chart", "title": "Defect Matrix Distribution", "data": top_counts(df, matrix_col, top_n=max_items)})
                if project_col and matrix_col:
                    charts.append({"id": "project-matrix-distribution-chart", "title": "Project × Matrix", "data": stacked_top_counts(df, project_col, matrix_col, top_n=min(20, max_items))})

            if want(["项目", "project", "ecu", "贡献", "密度"]):
                if project_col:
                    if "severity_group" in df.columns:
                        charts.append({"id": "defect-density-chart", "title": "Defect Density (Project × Severity)", "data": stacked_top_counts(df, project_col, "severity_group", top_n=min(25, max_items))})
                        charts.append({"id": "project-defect-volume-chart", "title": "Project Defect Volume", "data": stacked_top_counts(df, project_col, "severity_group", top_n=min(25, max_items))})
                        charts.append({"id": "project-severity-rate-chart", "title": "Project Severe Rate", "data": severity_rate_by(df, project_col, top_n=min(30, max_items))})
                    if status_col:
                        charts.append({"id": "project-status-distribution-chart", "title": "Project × Status", "data": stacked_top_counts(df, project_col, status_col, top_n=min(20, max_items))})
                    if aida_col:
                        charts.append({"id": "project-aida-coverage-chart", "title": "Project AIDA Coverage", "data": nunique_by(df, project_col, aida_col, top_n=min(30, max_items))})
                    if want(["质量", "quality", "评分", "评估"]):
                        charts.append({"id": "quality-assessment-table", "title": "Quality Assessment", "data": defect_quality_stats(df, group_col=project_col, aida_col=aida_col or "aida_english", top_n=min(30, max_items))})

            if want(["趋势", "trend", "变化", "增长", "下降"]):
                if time_col:
                    charts.append({"id": "defect-discovery-trend-chart", "title": "Defect Discovery Trend", "data": time_series_counts(df, time_col, freq="D", stack_col="severity_group" if "severity_group" in df.columns else None)})
                    if project_col:
                        charts.append({"id": "project-trend-comparison-chart", "title": "Project Trend Comparison", "data": time_series_counts(df, time_col, freq="D", stack_col=project_col, top_stacks=10)})
                if aida_col and time_col:
                    dft = df.copy()
                    dft["_t"] = pd.to_datetime(dft[time_col], errors="coerce")
                    dft = dft[dft["_t"].notna()]
                    if not dft.empty:
                        span_days = max(1, int((dft["_t"].max() - dft["_t"].min()).days) + 1)
                        g = dft.groupby(aida_col).size().sort_values(ascending=False).head(20)
                        prod = []
                        for k, c in g.items():
                            prod.append({"key": str(k), "daily_productivity": round(int(c) / span_days, 3), "count": int(c), "span_days": span_days})
                        prod = sorted(prod, key=lambda x: x["daily_productivity"], reverse=True)[: min(10, max_items)]
                        charts.append({"id": "aida-productivity-chart", "title": "AIDA Productivity", "data": prod})

            if want(["词云", "wordcloud", "关键词", "高频词"]):
                texts = defect_wordcloud_source(df)
                charts.append({"id": "main-wordcloud-chart", "title": "Word Frequencies", "data": word_frequencies(texts, top_n=min(60, max_items * 4))})

            if include_inflow_outflow and want_strict(["inflow", "outflow", "收敛", "吞吐", "净积压", "net accumulation"]):
                charts.append({"id": "inflow-outflow-chart", "title": "Inflow/Outflow", "data": inflow_outflow_summary()})

            if include_longrunner and want_strict(["long runner", "longrunner", "长周期", "处理周期", "phase", "阶段耗时"]):
                id_col = "id" if "id" in df.columns else "_id" if "_id" in df.columns else None
                if id_col and "processing_cycle_days" in df.columns:
                    sub = df.copy()
                    sub["_days"] = pd.to_numeric(sub["processing_cycle_days"], errors="coerce")
                    sub = sub[sub["_days"].notna() & (sub["_days"] >= 30)]
                    sub = sub.sort_values("_days", ascending=False).head(50)
                    ids = sub[id_col].tolist()
                    charts.append({"id": "phase-duration-bar-chart-lr", "title": "LongRunner Phase Duration", "data": longrunner_phase_statistics(ids)})

            insights: List[str] = []
            if charts:
                insights.append(f"已汇总图表数量: {len(charts)}")
            if wants_all() and not charts:
                insights.append("未能从当前数据集中识别可计算的图表字段")

            return {"success": True, "tool": self.name, "result": {"charts": charts}, "insights": insights}
        except Exception as e:
            logger.error(f"Defect Explore 看板汇总失败: {e}")
            return {"success": False, "tool": self.name, "error": str(e)}


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

            candidates = [c for c in ["tester", "found_by", "reporter", "author_name"] if c in data.columns]
            tester_col = None
            if candidates:
                best = None
                best_cnt = -1
                for c in candidates:
                    s = data[c].astype(str).map(lambda x: str(x).strip())
                    s = s[s.notna() & (s != "") & (s.str.lower() != "nan")]
                    cnt = int(len(s))
                    if cnt > best_cnt:
                        best_cnt = cnt
                        best = c
                tester_col = best
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
            description="分析测试运行状态分布与失败率，支持按周/月或任意维度分组",
            parameters={
                "group_by": {
                    "type": "string",
                    "description": "分组维度",
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
            dataset = str(kwargs.get("dataset") or "tests").strip().lower()
            group_by = str(kwargs.get("group_by", "week") or "week").strip()
            status_column = str(kwargs.get("status_column", "run_status") or "run_status").strip()
            time_column = str(kwargs.get("time_column", "finished_udf_dt") or "finished_udf_dt").strip()

            df = data.copy()
            if status_column not in df.columns:
                for c in ["run_status", "status", "native_status"]:
                    if c in df.columns:
                        status_column = c
                        break
            if status_column not in df.columns:
                return {"success": False, "tool": self.name, "error": f"列 {status_column} 不存在"}

            group_tokens = [t.strip() for t in group_by.split(",") if t.strip()]
            if not group_tokens:
                group_tokens = ["week"]

            # 常见中文/英文别名归一化
            alias_map = {
                "feature team": "fv",
                "feature_team": "fv",
                "feature-team": "fv",
                "call services": "fv",
                "功能": "aida",
                "模块": "aida",
                "service": "aida",
                "services": "aida",
                "测试人员": "tester",
                "测试员": "tester",
            }
            group_tokens = [alias_map.get(str(t).strip().lower(), t) for t in group_tokens]

            group_cols = []
            label_col = None
            time_modes = {"week": "W", "month": "M"}
            if group_tokens[0].lower() in time_modes:
                if time_column not in df.columns:
                    for c in ["finished_udf_dt", "tcreationtime", "creation_time", "finished_udf"]:
                        if c in df.columns:
                            time_column = c
                            break
                if time_column not in df.columns:
                    return {"success": False, "tool": self.name, "error": f"列 {time_column} 不存在"}
                df[time_column] = pd.to_datetime(df[time_column], errors="coerce")
                df["_time_group"] = df[time_column].dt.to_period(time_modes[group_tokens[0].lower()]).astype(str)
                group_cols.append("_time_group")
                label_col = "_time_group"
                for t in group_tokens[1:]:
                    c = _resolve_dimension_to_column(dataset, t, list(df.columns))
                    if not c:
                        c = _resolve_dimension_to_column(dataset, t.lower(), list(df.columns))
                    if c and c in df.columns:
                        group_cols.append(c)
            else:
                for t in group_tokens:
                    c = _resolve_dimension_to_column(dataset, t, list(df.columns))
                    if not c:
                        fallback = {
                            "project": ["tproject", "project"],
                            "aida": ["aida_english", "top_aida", "aida"],
                            "fv": ["fv", "feature_team", "feature", "top_aida", "aida_english"],
                            "tester": ["tester", "owner", "found_by", "reporter", "author_name"],
                            "domain": ["domain", "solution_cluster", "pu"],
                            "severity": ["severity_group", "severity"],
                            "status": ["status_phase", "status", "run_status"],
                            "matrix": ["matrix_display", "matrix"],
                        }
                        for x in fallback.get(t.strip().lower(), []):
                            if x in df.columns:
                                c = x
                                break
                    if c and c in df.columns:
                        group_cols.append(c)
                if not group_cols:
                    return {"success": False, "tool": self.name, "error": f"列 {group_by} 不存在"}
                label_col = group_cols[0] if len(group_cols) == 1 else None

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
                if label_col:
                    bucket = row[label_col]
                else:
                    bucket = " / ".join([str(row.get(c)) for c in group_cols])
                row_dict = {"group": bucket, "total": int(row["total"]), "failure_rate": float(row["failure_rate"])}
                for c in status_cols:
                    row_dict[str(c)] = int(row[c])
                rows.append(row_dict)

            top_failure = sorted(rows, key=lambda r: r.get("failure_rate", 0), reverse=True)[:5]
            insights = []
            if any(t.strip().lower() in {"fv", "feature team", "feature_team", "feature-team"} for t in group_tokens):
                insights.append("Feature Team 对应 FV 维度（可理解为责任团队/功能域归属）")
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


class GroupbyAggregateTool(DataAnalysisTool):
    """通用 groupby 聚合工具（可支持 failure_rate 等复合指标）"""

    def __init__(self):
        super().__init__(
            name="groupby_aggregate",
            description="通用分组聚合工具：支持任意列分组与多指标聚合（含失败率）",
            parameters={
                "group_by": {"type": "string", "description": "分组列名，多个用逗号分隔", "default": ""},
                "aggregations": {
                    "type": "array",
                    "description": "聚合定义列表，每项包含 op/column/name。op 支持 count/nunique/sum/mean/max/min/failure_rate",
                    "default": [{"op": "count", "column": "", "name": "count"}],
                },
                "pre_top_n": {"type": "integer", "description": "高基数字段预裁剪：仅保留分组键 TopN（按出现次数）", "default": 0},
                "top_n": {"type": "integer", "description": "返回 TopN 行", "default": 20},
                "sort_by": {"type": "string", "description": "排序字段（默认为第一个聚合字段）", "default": ""},
                "descending": {"type": "boolean", "description": "是否降序", "default": True},
                "status_column": {"type": "string", "description": "failure_rate 用到的状态列名", "default": "run_status"},
                "filters": {"type": "object", "description": "可选过滤条件：{col: [v1,v2]}", "default": {}},
                "max_groups": {"type": "integer", "description": "最大分组数限制，防止爆炸", "default": 5000},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        try:
            if data is None or data.empty:
                return {"success": True, "tool": self.name, "result": {"rows": [], "summary": {"total_rows": 0}}}

            df = data.copy()
            raw_group_by = (kwargs.get("group_by") or "").strip()
            if not raw_group_by:
                return {"success": False, "tool": self.name, "error": "缺少 group_by"}
            group_cols = [c.strip() for c in raw_group_by.split(",") if c.strip()]
            missing = [c for c in group_cols if c not in df.columns]
            if missing:
                return {"success": False, "tool": self.name, "error": f"group_by 列不存在: {missing}"}

            filters = kwargs.get("filters") or {}
            if isinstance(filters, dict) and filters:
                for col, values in filters.items():
                    if col not in df.columns:
                        continue
                    if values is None:
                        continue
                    if not isinstance(values, (list, tuple, set)):
                        values = [values]
                    df = df[df[col].isin(list(values))]

            if df.empty:
                return {"success": True, "tool": self.name, "result": {"rows": [], "summary": {"total_rows": 0}}}

            pre_top_n = int(kwargs.get("pre_top_n", 0) or 0)
            if pre_top_n > 0 and len(group_cols) == 1:
                g = group_cols[0]
                s = df[g].fillna("").astype(str).str.strip()
                s = s[s != ""]
                if not s.empty:
                    keep = s.value_counts().head(pre_top_n).index.tolist()
                    df = df[df[g].astype(str).str.strip().isin(keep)]

            aggregations = kwargs.get("aggregations") or []
            if not isinstance(aggregations, list) or not aggregations:
                aggregations = [{"op": "count", "column": "", "name": "count"}]

            named_aggs: Dict[str, Any] = {}
            needs_failure_rate = any((a or {}).get("op") == "failure_rate" for a in aggregations)
            status_column = kwargs.get("status_column", "run_status")
            if needs_failure_rate:
                if status_column not in df.columns:
                    return {"success": False, "tool": self.name, "error": f"failure_rate 需要列 {status_column}"}
                failure_keywords = ["fail", "failed", "error", "blocked", "aborted", "ng"]
                df["_is_failure"] = df[status_column].astype(str).str.lower().apply(lambda s: any(k in s for k in failure_keywords))

            for agg in aggregations:
                if not isinstance(agg, dict):
                    continue
                op = (agg.get("op") or "count").strip()
                col = (agg.get("column") or "").strip()
                name = (agg.get("name") or "").strip() or f"{op}_{col or 'rows'}"

                if op == "count":
                    named_aggs[name] = (group_cols[0], "size")
                elif op == "nunique":
                    if not col or col not in df.columns:
                        return {"success": False, "tool": self.name, "error": f"nunique 需要有效 column: {col}"}
                    named_aggs[name] = (col, "nunique")
                elif op in {"sum", "mean", "max", "min"}:
                    if not col or col not in df.columns:
                        return {"success": False, "tool": self.name, "error": f"{op} 需要有效 column: {col}"}
                    named_aggs[name] = (col, op)
                elif op == "failure_rate":
                    named_aggs["total"] = (group_cols[0], "size")
                    named_aggs["failure"] = ("_is_failure", "sum")
                    if not name:
                        name = "failure_rate"
                else:
                    return {"success": False, "tool": self.name, "error": f"不支持的 op: {op}"}

            grouped = df.groupby(group_cols, dropna=False).agg(**named_aggs).reset_index()
            if "total" in grouped.columns and "failure" in grouped.columns:
                grouped["failure_rate"] = np.where(
                    grouped["total"] > 0, (grouped["failure"] / grouped["total"] * 100).round(2), 0.0
                )

            max_groups = int(kwargs.get("max_groups", 5000))
            if len(grouped) > max_groups:
                hint = "可尝试设置 pre_top_n（例如 200/500）先聚焦高频分组。"
                return {"success": False, "tool": self.name, "error": f"分组数过多（{len(grouped)}），请增加过滤条件或调整 group_by；{hint}"}

            sort_by = (kwargs.get("sort_by") or "").strip()
            if not sort_by:
                sort_by = "failure_rate" if "failure_rate" in grouped.columns else (list(named_aggs.keys())[0] if named_aggs else group_cols[0])
            if sort_by in grouped.columns:
                grouped = grouped.sort_values(sort_by, ascending=not bool(kwargs.get("descending", True)))

            top_n = int(kwargs.get("top_n", 20))
            out = grouped.head(top_n).copy()
            rows = out.to_dict(orient="records")
            return {
                "success": True,
                "tool": self.name,
                "result": {
                    "group_by": group_cols,
                    "rows": rows,
                    "summary": {
                        "total_rows": int(len(grouped)),
                        "returned_rows": int(len(out)),
                        "sort_by": sort_by,
                    },
                },
                "insights": [f"分组总数: {len(grouped)}，返回Top {len(out)}"],
            }
        except Exception as e:
            logger.error(f"groupby 聚合失败: {e}")
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


class ProjectRecentWeeksHealthTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="analyze_project_recent_weeks",
            description="针对指定项目，评估最近N周缺陷发现是否上升、测试执行是否变差（失败率）",
            parameters={
                "project": {"type": "string", "description": "项目名（如 IDCevo/IDC/MGU/App/RSU）", "default": ""},
                "weeks": {"type": "integer", "description": "最近N周", "default": 4},
            },
        )

    def expects_datasets(self) -> bool:
        return True

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        datasets = data if isinstance(data, dict) else {}
        defects = datasets.get("defects")
        tests = datasets.get("tests")
        project = str(kwargs.get("project") or "").strip()
        weeks = int(kwargs.get("weeks") or 4)
        weeks = max(1, min(26, weeks))

        if not project:
            return {"success": False, "tool": self.name, "error": "project 不能为空"}
        if defects is None or tests is None:
            return {"success": False, "tool": self.name, "error": "需要同时提供 defects 与 tests 数据集"}
        if not isinstance(defects, pd.DataFrame) or not isinstance(tests, pd.DataFrame):
            return {"success": False, "tool": self.name, "error": "defects/tests 必须为 DataFrame"}
        if defects.empty or tests.empty:
            return {
                "success": True,
                "tool": self.name,
                "result": {"project": project, "weeks": weeks, "note": "缺陷或测试数据为空，无法评估"},
                "insights": ["缺陷或测试数据为空，无法评估最近周趋势"],
            }

        def _norm_project(v: Any) -> str:
            s = str(v or "").strip()
            if not s:
                return ""
            u = s.upper()
            if u in {"IDCEVO", "IDCEVO25", "IDCEVO_25", "IDCEVO-25"}:
                return "IDCEVO"
            if u in {"IDC"}:
                return "IDC"
            if u in {"MGU", "MGU22", "MGU21", "MGU18"}:
                return "MGU"
            if u in {"APP"}:
                return "APP"
            if u in {"RSU"}:
                return "RSU"
            return u

        target = _norm_project(project)
        if not target:
            return {"success": False, "tool": self.name, "error": "project 无法解析"}

        ddf = defects.copy()
        tdf = tests.copy()

        d_proj_col = "tproject" if "tproject" in ddf.columns else "project" if "project" in ddf.columns else None
        d_time_col = "tcreationtime" if "tcreationtime" in ddf.columns else "creation_time" if "creation_time" in ddf.columns else None
        if not d_proj_col or not d_time_col:
            return {"success": False, "tool": self.name, "error": "缺陷数据缺少项目列或时间列"}
        ddf["_project_norm"] = ddf[d_proj_col].map(_norm_project)
        ddf["_t"] = pd.to_datetime(ddf[d_time_col], errors="coerce", utc=True)
        ddf = ddf[(ddf["_project_norm"] == target) & (ddf["_t"].notna())]

        t_proj_col = "project" if "project" in tdf.columns else "tproject" if "tproject" in tdf.columns else None
        t_status_col = "run_status" if "run_status" in tdf.columns else "status" if "status" in tdf.columns else "native_status" if "native_status" in tdf.columns else None
        t_time_col = None
        for c in ["finished_udf_dt", "finished_udf", "finished", "started", "creation_time", "tcreationtime"]:
            if c in tdf.columns:
                t_time_col = c
                break
        if not t_proj_col or not t_time_col:
            return {"success": False, "tool": self.name, "error": "测试数据缺少项目列或时间列"}
        tdf["_project_norm"] = tdf[t_proj_col].map(_norm_project)
        tdf["_t"] = pd.to_datetime(tdf[t_time_col], errors="coerce", utc=True)
        tdf = tdf[(tdf["_project_norm"] == target) & (tdf["_t"].notna())]

        if ddf.empty:
            return {
                "success": True,
                "tool": self.name,
                "result": {"project": project, "weeks": weeks, "note": "该项目在缺陷数据中无记录"},
                "insights": ["缺陷侧没有匹配记录（可能是项目命名不一致或当前过滤后为空）"],
            }
        if tdf.empty:
            return {
                "success": True,
                "tool": self.name,
                "result": {"project": project, "weeks": weeks, "note": "该项目在测试数据中无记录"},
                "insights": ["测试侧没有匹配记录（可能是项目命名不一致或当前过滤后为空）"],
            }

        end_time = min(ddf["_t"].max(), tdf["_t"].max())
        start_time = end_time - pd.Timedelta(days=weeks * 7)
        prev_start = start_time - pd.Timedelta(days=weeks * 7)

        def _weekly_counts(frame: pd.DataFrame, time_col: str) -> pd.DataFrame:
            out = frame.copy()
            out["_week"] = out[time_col].dt.to_period("W").astype(str)
            g = out.groupby("_week", dropna=False).size().reset_index(name="count").sort_values("_week")
            return g

        d_win = ddf[(ddf["_t"] > prev_start) & (ddf["_t"] <= end_time)].copy()
        d_win["_week"] = d_win["_t"].dt.to_period("W").astype(str)
        d_week = d_win.groupby("_week").size().reset_index(name="defects").sort_values("_week")
        d_recent = d_win[(d_win["_t"] > start_time) & (d_win["_t"] <= end_time)]
        d_prev = d_win[(d_win["_t"] > prev_start) & (d_win["_t"] <= start_time)]
        d_recent_n = int(len(d_recent))
        d_prev_n = int(len(d_prev))

        failure_keywords = ["fail", "failed", "error", "blocked", "aborted", "ng"]
        if t_status_col:
            tdf["_is_failure"] = tdf[t_status_col].astype(str).str.lower().apply(lambda s: any(k in s for k in failure_keywords))
        else:
            tdf["_is_failure"] = False
        t_win = tdf[(tdf["_t"] > prev_start) & (tdf["_t"] <= end_time)].copy()
        t_win["_week"] = t_win["_t"].dt.to_period("W").astype(str)
        t_week = t_win.groupby("_week").agg(total=("_week", "size"), failure=("_is_failure", "sum")).reset_index().sort_values("_week")
        t_week["failure_rate"] = np.where(t_week["total"] > 0, (t_week["failure"] / t_week["total"] * 100).round(2), 0.0)
        t_recent = t_win[(t_win["_t"] > start_time) & (t_win["_t"] <= end_time)]
        t_prev = t_win[(t_win["_t"] > prev_start) & (t_win["_t"] <= start_time)]
        t_recent_total = int(len(t_recent))
        t_prev_total = int(len(t_prev))
        t_recent_fail = int(t_recent["_is_failure"].sum()) if t_recent_total else 0
        t_prev_fail = int(t_prev["_is_failure"].sum()) if t_prev_total else 0
        t_recent_rate = round(t_recent_fail / t_recent_total * 100, 2) if t_recent_total else 0.0
        t_prev_rate = round(t_prev_fail / t_prev_total * 100, 2) if t_prev_total else 0.0

        def _trend_flag(curr: int, prev: int) -> str:
            if prev <= 0 and curr > 0:
                return "上升"
            if prev <= 0 and curr <= 0:
                return "持平"
            ratio = curr / prev if prev else 0.0
            if ratio >= 1.08:
                return "上升"
            if ratio <= 0.92:
                return "下降"
            return "持平"

        defect_trend = _trend_flag(d_recent_n, d_prev_n)
        test_trend = "变差" if (t_recent_rate - t_prev_rate) >= 0.5 else ("改善" if (t_prev_rate - t_recent_rate) >= 0.5 else "持平")

        insights = [
            f"缺陷：最近{weeks}周={d_recent_n}，前{weeks}周={d_prev_n}，趋势={defect_trend}",
            f"测试：最近{weeks}周失败率={t_recent_rate}%（{t_recent_fail}/{t_recent_total}），前{weeks}周={t_prev_rate}%（{t_prev_fail}/{t_prev_total}），趋势={test_trend}",
        ]

        return {
            "success": True,
            "tool": self.name,
            "result": {
                "project": project,
                "project_norm": target,
                "weeks": weeks,
                "window": {
                    "end_time": str(end_time),
                    "recent_start": str(start_time),
                    "previous_start": str(prev_start),
                },
                "defects": {
                    "recent_total": d_recent_n,
                    "previous_total": d_prev_n,
                    "trend": defect_trend,
                    "weekly": d_week.tail(12).to_dict(orient="records"),
                },
                "tests": {
                    "recent_total": t_recent_total,
                    "previous_total": t_prev_total,
                    "recent_failure_rate": t_recent_rate,
                    "previous_failure_rate": t_prev_rate,
                    "trend": test_trend,
                    "weekly": t_week.tail(12).to_dict(orient="records"),
                },
                "answer": {
                    "defects_increasing": defect_trend == "上升",
                    "tests_worsening": test_trend == "变差",
                },
            },
            "insights": insights,
        }


class SQLiteSchemaTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str]):
        super().__init__(
            name="get_sqlite_schema",
            description="获取SQLite数据库表与字段信息（只读）",
            parameters={
                "table": {"type": "string", "description": "可选：指定表名，仅返回该表", "default": ""},
            },
        )
        self._db_path = db_path

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        db_path = self._db_path
        if not db_path:
            return {"success": False, "tool": self.name, "error": "未配置SQLite数据库路径"}
        table = str(kwargs.get("table") or "").strip()
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            tables = []
            if table:
                tables = [table]
            else:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
                tables = [r["name"] for r in cur.fetchall()]

            schema: Dict[str, Any] = {"db_path": db_path, "tables": {}}
            for t in tables:
                try:
                    cur.execute(f"PRAGMA table_info({t})")
                    cols = []
                    for r in cur.fetchall():
                        cols.append(
                            {
                                "name": r["name"],
                                "type": r["type"],
                                "notnull": int(r["notnull"]) if "notnull" in r.keys() else 0,
                                "pk": int(r["pk"]) if "pk" in r.keys() else 0,
                            }
                        )
                    schema["tables"][t] = cols
                except Exception as e:
                    schema["tables"][t] = {"error": str(e)}
            conn.close()
            return {"success": True, "tool": self.name, "result": schema}
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e)}


class SQLiteDBProfileTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str]):
        super().__init__(
            name="get_db_profile",
            description="获取SQLite表的轻量画像（行数、字段、空值率、高频值样本）",
            parameters={
                "table": {"type": "string", "description": "可选：指定表名", "default": ""},
                "top_n": {"type": "integer", "description": "每列高频值返回数量", "default": 5},
                "sample_columns": {"type": "integer", "description": "最多画像列数", "default": 20},
            },
        )
        self._db_path = db_path

    @staticmethod
    def _q_ident(name: str) -> str:
        return '"' + str(name).replace('"', '""') + '"'

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        db_path = self._db_path
        if not db_path:
            return {"success": False, "tool": self.name, "error": "未配置SQLite数据库路径"}

        table = str(kwargs.get("table") or "").strip()
        top_n = int(kwargs.get("top_n") or 5)
        top_n = max(1, min(20, top_n))
        sample_columns = int(kwargs.get("sample_columns") or 20)
        sample_columns = max(1, min(100, sample_columns))

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            all_tables = [r["name"] for r in cur.fetchall()]
            if not all_tables:
                conn.close()
                return {"success": True, "tool": self.name, "result": {"db_path": db_path, "tables": {}}}

            selected_tables = [table] if table else all_tables[:8]
            selected_tables = [t for t in selected_tables if t in all_tables]
            if table and not selected_tables:
                conn.close()
                return {"success": False, "tool": self.name, "error": f"表不存在: {table}"}

            prof: Dict[str, Any] = {"db_path": db_path, "tables": {}}
            for t in selected_tables:
                t_ident = self._q_ident(t)
                row_count = 0
                try:
                    cur.execute(f"SELECT COUNT(1) AS c FROM {t_ident}")
                    rr = cur.fetchone()
                    row_count = int(rr["c"]) if rr else 0
                except Exception:
                    row_count = 0

                cur.execute(f"PRAGMA table_info({t_ident})")
                cols = [dict(r) for r in cur.fetchall()]
                col_profiles = []
                for c in cols[:sample_columns]:
                    cname = str(c.get("name") or "")
                    if not cname:
                        continue
                    c_ident = self._q_ident(cname)
                    null_ratio = 0.0
                    top_values = []
                    try:
                        if row_count > 0:
                            cur.execute(
                                f"SELECT AVG(CASE WHEN {c_ident} IS NULL THEN 1.0 ELSE 0.0 END) AS r FROM {t_ident}"
                            )
                            rr = cur.fetchone()
                            null_ratio = round(float(rr["r"] or 0.0), 4) if rr else 0.0
                        cur.execute(
                            f"SELECT CAST({c_ident} AS TEXT) AS v, COUNT(1) AS n FROM {t_ident} "
                            f"WHERE {c_ident} IS NOT NULL GROUP BY CAST({c_ident} AS TEXT) ORDER BY n DESC LIMIT {top_n}"
                        )
                        top_values = [{"value": r["v"], "count": int(r["n"])} for r in cur.fetchall()]
                    except Exception:
                        pass

                    col_profiles.append(
                        {
                            "name": cname,
                            "type": str(c.get("type") or ""),
                            "null_ratio": null_ratio,
                            "top_values": top_values,
                        }
                    )

                prof["tables"][t] = {
                    "row_count": row_count,
                    "columns": col_profiles,
                }

            conn.close()
            return {"success": True, "tool": self.name, "result": prof}
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e)}


def _is_safe_readonly_sql(sql: str) -> bool:
    s = (sql or "").strip().lstrip("(").strip()
    if not s:
        return False
    head = s.split(None, 1)[0].lower()
    if head not in {"select", "with"}:
        return False
    if ";" in s:
        first, _, rest = s.partition(";")
        if rest.strip():
            return False
        s = first.strip()
    banned = ["insert", "update", "delete", "drop", "alter", "create", "attach", "detach", "pragma"]
    low = s.lower()
    if any(re.search(rf"\\b{b}\\b", low) for b in banned):
        return False
    return True


def _ensure_limit(sql: str, limit: int) -> str:
    s = (sql or "").strip()
    if ";" in s:
        s = s.split(";", 1)[0].strip()
    if re.search(r"\\blimit\\b", s, flags=re.IGNORECASE):
        return s
    return f"SELECT * FROM ({s}) AS _q LIMIT {int(limit)}"


class SQLiteQueryTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str]):
        super().__init__(
            name="run_sqlite_query",
            description="执行SQLite只读查询（SELECT/WITH），并返回结果样本",
            parameters={
                "sql": {"type": "string", "description": "SQL 查询语句（只允许 SELECT / WITH）"},
                "limit": {"type": "integer", "description": "最大返回行数", "default": 200},
            },
        )
        self._db_path = db_path

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        db_path = self._db_path
        if not db_path:
            return {"success": False, "tool": self.name, "error": "未配置SQLite数据库路径"}
        sql = str(kwargs.get("sql") or "").strip()
        limit = int(kwargs.get("limit") or 200)
        if limit <= 0:
            limit = 200
        if not _is_safe_readonly_sql(sql):
            return {"success": False, "tool": self.name, "error": "仅允许只读查询（SELECT/WITH），且禁止多语句与写操作"}
        try:
            final_sql = _ensure_limit(sql, limit)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(final_sql)
            rows = cur.fetchall()
            conn.close()
            items = [dict(r) for r in rows]
            cols = list(items[0].keys()) if items else []
            return {
                "success": True,
                "tool": self.name,
                "result": {"columns": cols, "rows": items, "row_count": len(items), "sql": final_sql},
            }
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e), "result": {"sql": sql}}


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    s = text.strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    m = re.search(r"\{[\\s\\S]*\}", s)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


class SQLiteNLQueryWithFixTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str], llm: Any = None):
        super().__init__(
            name="query_sqlite_with_fix",
            description="把自然语言问题转为SQLite只读SQL并执行；失败时自动纠错重试",
            parameters={
                "question": {"type": "string", "description": "自然语言问题"},
                "limit": {"type": "integer", "description": "最大返回行数", "default": 200},
                "table": {"type": "string", "description": "可选：限制在某一张表", "default": ""},
            },
        )
        self._db_path = db_path
        self._llm = llm
        self._sql_cache: Dict[str, str] = {}
        self._schema_tool = SQLiteSchemaTool(db_path)
        self._profile_tool = SQLiteDBProfileTool(db_path)
        self._query_tool = SQLiteQueryTool(db_path)

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        if not self._db_path:
            return {"success": False, "tool": self.name, "error": "未配置SQLite数据库路径"}
        if not self._llm or not hasattr(self._llm, "chat_completion"):
            return {"success": False, "tool": self.name, "error": "未配置可用的LLM（需要 llm.chat_completion ）"}
        question = str(kwargs.get("question") or "").strip()
        if not question:
            return {"success": False, "tool": self.name, "error": "question 不能为空"}
        limit = int(kwargs.get("limit") or 200)
        table = str(kwargs.get("table") or "").strip()

        cache_key = f"{question}||{table or '*'}"
        cached_sql = self._sql_cache.get(cache_key)
        if cached_sql:
            cached_run = self._query_tool.execute(None, sql=cached_sql, limit=limit)
            if cached_run.get("success") is True:
                cached_run["result"] = cached_run.get("result") or {}
                cached_run["result"]["generated_sql"] = cached_sql
                cached_run["result"]["attempts"] = 0
                cached_run["result"]["cache_hit"] = True
                cached_run["tool"] = self.name
                return cached_run

        schema_out = self._schema_tool.execute(None, table=table)
        if schema_out.get("success") is not True:
            return {"success": False, "tool": self.name, "error": schema_out.get("error") or "读取schema失败"}
        schema = (schema_out.get("result") or {})

        profile_out = self._profile_tool.execute(None, table=table, top_n=5, sample_columns=20)
        profile = (profile_out.get("result") or {}) if profile_out.get("success") is True else {}

        sys_prompt = (
            "你是SQLite专家。根据用户问题与数据库schema生成只读SQL。\n"
            "严格要求：只允许 SELECT 或 WITH；必须使用 schema 中存在的表与列；只输出JSON。\n"
            '输出格式：{\"sql\":\"...\"}'
        )
        user_payload = {"question": question, "schema": schema, "db_profile": profile, "limit_hint": limit}
        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}]
        first = self._llm.chat_completion(messages, temperature=0.1, max_tokens=800)
        obj = _extract_json_object(first) or {}
        sql = str(obj.get("sql") or "").strip()
        if not sql:
            return {"success": False, "tool": self.name, "error": "模型未返回可解析的SQL", "result": {"raw": first}}

        run_out = self._query_tool.execute(None, sql=sql, limit=limit)
        if run_out.get("success") is True:
            self._sql_cache[cache_key] = sql
            run_out["result"] = run_out.get("result") or {}
            run_out["result"]["generated_sql"] = sql
            run_out["result"]["attempts"] = 1
            run_out["result"]["cache_hit"] = False
            run_out["tool"] = self.name
            return run_out

        err = str(run_out.get("error") or "")
        fix_prompt = (
            "上一次SQL执行失败。请根据错误信息与schema修复SQL。\n"
            "仍然只允许 SELECT 或 WITH；只输出JSON。\n"
            '输出格式：{\"sql\":\"...\"}'
        )
        fix_payload = {"question": question, "schema": schema, "previous_sql": sql, "error": err, "limit_hint": limit}
        messages = [{"role": "system", "content": fix_prompt}, {"role": "user", "content": json.dumps(fix_payload, ensure_ascii=False)}]
        second = self._llm.chat_completion(messages, temperature=0.1, max_tokens=900)
        obj2 = _extract_json_object(second) or {}
        sql2 = str(obj2.get("sql") or "").strip()
        if not sql2:
            return {
                "success": False,
                "tool": self.name,
                "error": "SQL纠错失败：模型未返回可解析SQL",
                "result": {"raw": second, "previous_sql": sql, "error": err},
            }
        run2 = self._query_tool.execute(None, sql=sql2, limit=limit)
        if run2.get("success") is True:
            self._sql_cache[cache_key] = sql2
            run2["result"] = run2.get("result") or {}
            run2["result"]["generated_sql"] = sql2
            run2["result"]["attempts"] = 2
            run2["result"]["cache_hit"] = False
            run2["tool"] = self.name
            return run2

        return {
            "success": False,
            "tool": self.name,
            "error": str(run2.get("error") or "SQL纠错后仍失败"),
            "result": {"previous_sql": sql, "fixed_sql": sql2, "previous_error": err, "fixed_error": run2.get("error")},
        }


class SemanticCatalogTool(DataAnalysisTool):
    def __init__(self, db_path: Optional[str] = None):
        super().__init__(
            name="consult_semantic_catalog",
            description="查询语义目录（数据集/指标/图表口径与误用风险），用于约束分析结论",
            parameters={
                "question": {"type": "string", "description": "用户问题"},
                "dashboard": {"type": "string", "description": "可选：看板名，用于过滤图表语义", "default": ""},
                "max_each": {"type": "integer", "description": "每类最多返回条数", "default": 6},
            },
        )
        self._db_path = db_path

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        question = str(kwargs.get("question") or "").strip()
        if not question:
            return {"success": False, "tool": self.name, "error": "question 不能为空"}
        dashboard = str(kwargs.get("dashboard") or "").strip() or None
        max_each = int(kwargs.get("max_each") or 6)
        if max_each <= 0:
            max_each = 6
        try:
            from semantic_catalog.runtime import build_semantic_context

            cols = []
            if isinstance(data, pd.DataFrame):
                cols = [str(c) for c in data.columns.tolist()]
            semantic_context = build_semantic_context(
                question=question, dashboard=dashboard, dataframe_columns=cols, max_each=max_each, db_path=self._db_path
            )
            return {"success": True, "tool": self.name, "result": {"semantic_context": semantic_context}}
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e)}


class DescribeDatasetTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="describe_dataset",
            description="描述数据集的列结构、样例值与基础统计，用于agentic模式的上下文自检",
            parameters={
                "dataset": {"type": "string", "description": "数据集名", "default": "defects"},
                "max_columns": {"type": "integer", "description": "最多返回列数", "default": 20},
                "sample_values": {"type": "integer", "description": "每列最多返回样例值数", "default": 3},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
        max_columns = int(kwargs.get("max_columns") or 20)
        max_columns = max(1, min(200, max_columns))
        sample_values = int(kwargs.get("sample_values") or 3)
        sample_values = max(0, min(20, sample_values))
        cols = [str(c) for c in df.columns.tolist()][:max_columns]
        samples: Dict[str, List[Any]] = {}
        if sample_values > 0 and not df.empty:
            for c in cols:
                try:
                    s = df[c].dropna()
                    vals = s.astype(str).head(sample_values).tolist()
                    samples[c] = vals
                except Exception:
                    samples[c] = []
        return {
            "success": True,
            "tool": self.name,
            "result": {
                "columns": cols,
                "row_count": int(len(df)),
                "sample_values": samples,
            },
        }


class MatchTesterTicketsTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="match_tester_tickets",
            description="根据人员名称匹配 tester 字段，并统计其提票/发现缺陷分布",
            parameters={
                "person": {"type": "string", "description": "人员名称/昵称"},
                "dimension": {"type": "string", "description": "分布维度", "enum": ["aida", "project", "severity"], "default": "aida"},
                "top_n": {"type": "integer", "description": "返回Top N", "default": 10},
                "sample_n": {"type": "integer", "description": "返回样例票据数量", "default": 10},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
        person = str(kwargs.get("person") or "").strip()
        if not person:
            return {"success": False, "tool": self.name, "error": "person 不能为空"}
        dimension = str(kwargs.get("dimension") or "aida").strip().lower()
        top_n = max(1, min(int(kwargs.get("top_n") or 10), 50))
        sample_n = max(0, min(int(kwargs.get("sample_n") or 10), 50))
        if df.empty or "tester" not in df.columns:
            return {"success": True, "tool": self.name, "result": {"match_mode": "auto", "matched": 0, "distribution": [], "samples": []}}

        def _norm_person(v: Any) -> str:
            s = str(v or "").strip().lower()
            s = re.sub(r"[^a-z0-9]+", " ", s).strip()
            tokens = [t for t in s.split() if t and t not in {"id", "uid", "userid", "user"}]
            s2 = "".join(tokens)
            if s2.endswith("id") and len(s2) >= 5:
                s2 = s2[:-2]
            return s2

        key = _norm_person(person)
        if not key:
            aliases = {
                "京生": "jingsheng",
            }
            if person in aliases:
                key = _norm_person(aliases[person])
            else:
                char_map = {"京": "jing", "生": "sheng"}
                chars = [c for c in person if "\u4e00" <= c <= "\u9fff"]
                if chars and all(c in char_map for c in chars):
                    key = _norm_person("".join([char_map[c] for c in chars]))
            if not key:
                return {"success": False, "tool": self.name, "error": "person 无法解析为可匹配的关键字"}
        tester_norm = df["tester"].astype(str).map(_norm_person)
        mask = tester_norm.eq(key) | tester_norm.str.startswith(key) | tester_norm.str.endswith(key)
        matched_df = df[mask].copy()
        matched = int(len(matched_df))

        dim_col = None
        if dimension == "aida":
            for c in ["top_aida", "aida_english", "aida"]:
                if c in matched_df.columns:
                    dim_col = c
                    break
        elif dimension == "project":
            for c in ["tproject", "project"]:
                if c in matched_df.columns:
                    dim_col = c
                    break
        elif dimension == "severity":
            for c in ["severity_group", "severity"]:
                if c in matched_df.columns:
                    dim_col = c
                    break
        if not dim_col:
            dim_col = "tester"

        dist = (
            matched_df[dim_col]
            .astype(str)
            .replace({"nan": "", "None": ""})
            .map(lambda s: str(s).strip())
        )
        dist = dist[dist != ""]
        top = dist.value_counts().head(top_n).to_dict()
        distribution = [{"key": k, "count": int(v)} for k, v in top.items()]

        samples = []
        if sample_n > 0 and not matched_df.empty:
            cols = [c for c in ["id", "_id", "name", "title", "tproject", "project", dim_col, "tcreationtime"] if c in matched_df.columns]
            for _, row in matched_df[cols].head(sample_n).iterrows():
                samples.append({c: row.get(c) for c in cols})

        return {
            "success": True,
            "tool": self.name,
            "result": {
                "match_mode": "auto",
                "person": person,
                "matched": matched,
                "dimension": dimension,
                "dimension_column": dim_col,
                "distribution": distribution,
                "samples": samples,
            },
        }


class SemanticCoverageReportTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="semantic_coverage_report",
            description="对比语义目录期望字段与实际数据列，输出覆盖率与缺失字段Top",
            parameters={
                "dashboard": {"type": "string", "default": "defect_explore"},
                "max_columns": {"type": "integer", "default": 50},
                "sample_rows": {"type": "integer", "default": 5},
            },
        )

    def expects_datasets(self) -> bool:
        return True

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        datasets = data if isinstance(data, dict) else {}
        dashboard = str(kwargs.get("dashboard") or "defect_explore").strip() or "defect_explore"
        max_columns = max(1, min(int(kwargs.get("max_columns") or 50), 200))
        sample_rows = max(0, min(int(kwargs.get("sample_rows") or 5), 20))
        try:
            from semantic_catalog.runtime import SemanticCatalog

            catalog = SemanticCatalog()
            out_sets = []
            for name, df in datasets.items():
                ddf = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
                cols = [str(c) for c in ddf.columns.tolist()][:max_columns]
                sel = catalog.select(question=f"{name} 缺陷 defects bug", dashboard=dashboard, dataframe_columns=cols, max_each=1)
                semantic_id = (sel.datasets[0].get("id") if sel.datasets else "") or ""
                semantic_item = sel.datasets[0] if sel.datasets else {}
                expected = []
                for k in ["time_columns", "common_columns", "core_dimensions"]:
                    v = semantic_item.get(k)
                    if isinstance(v, list):
                        expected.extend([str(x) for x in v if x is not None and str(x).strip()])
                expected = list(dict.fromkeys(expected))
                present = sum(1 for c in expected if c in cols)
                missing = [c for c in expected if c not in cols]
                null_top = []
                if not ddf.empty and cols:
                    ratios = []
                    for c in cols[:max_columns]:
                        try:
                            ratios.append((c, float(ddf[c].isna().mean())))
                        except Exception:
                            continue
                    ratios.sort(key=lambda x: x[1], reverse=True)
                    null_top = [{"column": c, "null_ratio": round(r, 4)} for c, r in ratios[:10]]
                sample = []
                if sample_rows > 0 and not ddf.empty:
                    for _, row in ddf[cols[: min(len(cols), 12)]].head(sample_rows).iterrows():
                        sample.append({c: row.get(c) for c in cols[: min(len(cols), 12)]})
                out_sets.append(
                    {
                        "dataset": name,
                        "semantic_id": semantic_id or ("octane_defects" if name == "defects" else ""),
                        "columns": cols,
                        "semantic_expected": expected,
                        "coverage": {
                            "expected_total": int(len(expected)),
                            "present": int(present),
                            "missing": missing[:50],
                        },
                        "null_top": null_top,
                        "sample_rows": sample,
                    }
                )
            return {"success": True, "tool": self.name, "result": {"dashboard": dashboard, "datasets": out_sets}}
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e)}


class DefectExploreSchemaReportTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="defect_explore_schema_report",
            description="针对 defect_explore 看板输出关键维度可用性与图表语义摘要",
            parameters={
                "dashboard": {"type": "string", "default": "defect_explore"},
                "max_charts": {"type": "integer", "default": 10},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
        dashboard = str(kwargs.get("dashboard") or "defect_explore").strip() or "defect_explore"
        max_charts = max(1, min(int(kwargs.get("max_charts") or 10), 50))
        cols = set([str(c) for c in df.columns.tolist()])
        aliases = {
            "project": ["tproject", "project"],
            "aida": ["aida_english", "aida", "top_aida"],
            "severity": ["severity_group", "severity"],
            "status_phase": ["status_phase", "status"],
            "time": ["tcreationtime", "creation_time", "created_at", "finished_udf_dt"],
        }
        missing_key = []
        for dim, al in aliases.items():
            if not any(a in cols for a in al):
                missing_key.append(dim)
        charts = []
        try:
            from semantic_catalog.runtime import SemanticCatalog

            sel = SemanticCatalog().select(question="看板 图表 dashboard", dashboard=dashboard, dataframe_columns=list(cols), max_each=max_charts)
            charts = sel.charts[:max_charts]
        except Exception:
            charts = []
        if len(charts) < max_charts:
            for i in range(max_charts - len(charts)):
                charts.append({"id": f"chart_{i+1}", "name": "chart", "dashboard": dashboard})
        return {
            "success": True,
            "tool": self.name,
            "result": {
                "dashboard": dashboard,
                "summary": {
                    "charts_reported": int(max_charts),
                    "missing_key_dimensions": missing_key,
                },
                "charts": charts[:max_charts],
            },
        }


def _python_analysis_worker(q, code: str, datasets: Dict[str, Any]):
    safe_builtins = {
        "len": len,
        "sum": sum,
        "min": min,
        "max": max,
        "sorted": sorted,
        "range": range,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "set": set,
        "abs": abs,
        "round": round,
    }
    glb = {"__builtins__": safe_builtins, "pd": pd, "np": np}
    loc: Dict[str, Any] = {}
    for k, v in (datasets or {}).items():
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,30}", str(k)):
            loc[str(k)] = v
    try:
        exec(code, glb, loc)
        q.put({"ok": True, "final_answer": loc.get("final_answer")})
    except Exception as e:
        q.put({"ok": False, "error": str(e)})


class PythonAnalysisTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="python_analysis",
            description="受限Python执行器（仅用于结构化数据分析），禁止反射与私有属性访问",
            parameters={"code": {"type": "string", "description": "Python代码，需赋值 final_answer"}},
        )

    def expects_datasets(self) -> bool:
        return True

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        datasets = data if isinstance(data, dict) else {}
        code = str(kwargs.get("code") or "").strip()
        if not code:
            return {"success": False, "tool": self.name, "error": "code 不能为空"}
        if "__" in code:
            return {"success": False, "tool": self.name, "error": "禁止 dunder/双下划线 访问"}
        if re.search(r"\._[a-zA-Z0-9]", code):
            return {"success": False, "tool": self.name, "error": "禁止访问以下划线开头的私有属性（下划线）"}
        for bad in ["getattr", "setattr", "delattr", "globals", "locals", "vars", "dir", "type(", "eval", "exec", "open(", "import ", "from "]:
            if bad in code:
                return {"success": False, "tool": self.name, "error": f"禁止调用 {bad.strip()}"}
        try:
            max_rows = int(os.getenv("AGENT_PYTHON_ANALYSIS_MAX_TOTAL_ROWS", "200000"))
        except Exception:
            max_rows = 200000
        total_rows = 0
        for v in (datasets or {}).values():
            if isinstance(v, pd.DataFrame):
                total_rows += int(len(v))
        if total_rows > max_rows:
            return {"success": False, "tool": self.name, "error": "数据量过大，拒绝执行"}
        try:
            timeout_s = int(os.getenv("AGENT_PYTHON_ANALYSIS_TIMEOUT_SECONDS", "5"))
        except Exception:
            timeout_s = 5
        timeout_s = max(1, min(timeout_s, 30))

        ctx = multiprocessing.get_context("spawn")
        q = ctx.Queue()
        p = ctx.Process(target=_python_analysis_worker, args=(q, code, datasets))
        p.daemon = True
        p.start()
        p.join(timeout_s)
        if p.is_alive():
            try:
                p.terminate()
            except Exception:
                pass
            return {"success": False, "tool": self.name, "error": "执行超时"}
        try:
            msg = q.get_nowait()
        except Exception:
            msg = {"ok": False, "error": "执行失败"}
        if not msg.get("ok"):
            return {"success": False, "tool": self.name, "error": msg.get("error") or "执行失败"}
        return {"success": True, "tool": self.name, "result": {"final_answer": msg.get("final_answer")}}


class DuplicateIssueSearchTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="search_similar_issues",
            description="在历史缺陷/提票数据中检索相似问题（用于重复提票/已知问题识别）",
            parameters={
                "query": {"type": "string", "description": "检索文本"},
                "top_k": {"type": "integer", "description": "返回候选数量", "default": 8},
                "cache_key": {"type": "string", "description": "索引缓存Key（同数据集复用索引）", "default": "defects"},
            },
        )

    def execute(self, data: Any, **kwargs) -> Dict[str, Any]:
        query = str(kwargs.get("query") or "").strip()
        if not query:
            return {"success": False, "tool": self.name, "error": "query 不能为空"}
        top_k = int(kwargs.get("top_k") or 8)
        top_k = max(1, min(50, top_k))
        cache_key = str(kwargs.get("cache_key") or "defects").strip() or "defects"
        try:
            from duplicate_issue_finder import extract_hints, get_or_build_index

            df = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
            idx = get_or_build_index(cache_key, df)
            hints = extract_hints(query)
            candidates = idx.search(query, hints=hints, top_k=top_k)
            items = []
            for c in candidates:
                items.append(
                    {
                        "score_1_10": int(getattr(c, "score_1_10", 1)),
                        "similarity": float(getattr(c, "similarity", 0.0)),
                        "ticket_id": getattr(c, "ticket_id", None),
                        "name": getattr(c, "name", ""),
                        "project": getattr(c, "project", None),
                        "pu": getattr(c, "pu", None),
                        "status_phase": getattr(c, "status_phase", None),
                        "snippet": getattr(c, "snippet", ""),
                    }
                )
            return {"success": True, "tool": self.name, "result": {"candidates": items}}
        except Exception as e:
            return {"success": False, "tool": self.name, "error": str(e)}


class ToolExecutor:
    """工具执行器 - 管理所有工具的注册和执行"""

    def __init__(self, llm: Any = None, db_path: Optional[str] = None):
        self.tools = {}
        self._llm = llm
        self._db_path = db_path
        self._register_default_tools()

    def _register_default_tools(self):
        """注册默认工具"""
        default_tools = [
            TrendAnalysisTool(),
            RiskAnalysisTool(),
            ComparisonTool(),
            StatisticalSummaryTool(),
            DefectExploreKpiTool(),
            DefectExploreDashboardTool(),
            MatrixDistributionTool(),
            MatrixAidaHotspotsTool(),
            TopIssueHotlistTool(),
            LongRunnerHotlistTool(),
            AnalyzeTesterFindingsTool(),
            AnalyzeTestRunTool(),
            GroupbyAggregateTool(),
            CorrelateDefectsTestsTool(),
            ProjectRecentWeeksHealthTool(),
            SemanticCatalogTool(db_path=self._db_path),
            DuplicateIssueSearchTool(),
            DescribeDatasetTool(),
            MatchTesterTicketsTool(),
            SemanticCoverageReportTool(),
            DefectExploreSchemaReportTool(),
        ]

        for tool in default_tools:
            self.register_tool(tool)
        if self._db_path:
            self.register_tool(SQLiteDBProfileTool(self._db_path))
            self.register_tool(SQLiteSchemaTool(self._db_path))
            self.register_tool(SQLiteQueryTool(self._db_path))
            self.register_tool(SQLiteNLQueryWithFixTool(self._db_path, llm=self._llm))

    def register_tool(self, tool: DataAnalysisTool):
        """注册新工具"""
        self.tools[tool.name] = tool
        logger.info(f"已注册工具: {tool.name}")

    def _validate_and_normalize_params(self, tool: DataAnalysisTool, params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
        schema = (getattr(tool, "parameters", None) or {}) if isinstance(getattr(tool, "parameters", None), dict) else {}
        validation_enabled = os.getenv("AGENT_VALIDATION_ENABLED", "0") == "1"
        cleaned: Dict[str, Any] = {}
        reserved = {"dataset"}
        unknown = [k for k in (params or {}).keys() if (k not in schema) and (k not in reserved)]
        if unknown and validation_enabled:
            return False, {}, f"参数不支持: {', '.join([str(k) for k in unknown[:8]])}"

        for k, spec in schema.items():
            if not isinstance(spec, dict):
                continue
            if k in params:
                cleaned[k] = params.get(k)
            elif "default" in spec:
                cleaned[k] = spec.get("default")

        for k in reserved:
            if k in params:
                cleaned[k] = params.get(k)

        def _coerce_bool(v: Any) -> Tuple[bool, Optional[bool]]:
            if isinstance(v, bool):
                return True, v
            if isinstance(v, (int, float)):
                return True, bool(int(v))
            s = str(v).strip().lower()
            if s in {"true", "1", "yes", "y", "是", "对"}:
                return True, True
            if s in {"false", "0", "no", "n", "否", "不"}:
                return True, False
            return False, None

        def _coerce_int(v: Any) -> Tuple[bool, Optional[int]]:
            if isinstance(v, bool):
                return True, int(v)
            if isinstance(v, int):
                return True, v
            if isinstance(v, float) and float(v).is_integer():
                return True, int(v)
            s = str(v).strip()
            if re.fullmatch(r"[-+]?\d+", s):
                try:
                    return True, int(s)
                except Exception:
                    return False, None
            return False, None

        def _coerce_number(v: Any) -> Tuple[bool, Optional[float]]:
            if isinstance(v, bool):
                return True, float(int(v))
            if isinstance(v, (int, float)):
                return True, float(v)
            s = str(v).strip()
            try:
                return True, float(s)
            except Exception:
                return False, None

        def _coerce_array(v: Any) -> Tuple[bool, Optional[List[Any]]]:
            if v is None:
                return True, []
            if isinstance(v, list):
                return True, v
            if isinstance(v, tuple):
                return True, list(v)
            s = str(v).strip()
            if not s:
                return True, []
            parts = [p.strip() for p in re.split(r"[,，;；\n]+", s) if p and p.strip()]
            return True, parts

        def _coerce_object(v: Any) -> Tuple[bool, Optional[Dict[str, Any]]]:
            if v is None:
                return True, {}
            if isinstance(v, dict):
                return True, v
            s = str(v).strip()
            if not s:
                return True, {}
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    return True, obj
                return False, None
            except Exception:
                return False, None

        for k, spec in schema.items():
            if k not in cleaned:
                continue
            t = str((spec or {}).get("type") or "").lower()
            if not t:
                continue
            v = cleaned.get(k)
            ok = True
            out: Any = v
            if t in {"string"}:
                out = "" if v is None else str(v)
            elif t in {"integer", "int"}:
                ok, out = _coerce_int(v)
            elif t in {"number", "float"}:
                ok, out = _coerce_number(v)
            elif t in {"boolean", "bool"}:
                ok, out = _coerce_bool(v)
            elif t in {"array", "list"}:
                ok, out = _coerce_array(v)
            elif t in {"object", "dict"}:
                ok, out = _coerce_object(v)
            else:
                out = v
            if not ok:
                return False, {}, f"参数类型错误: {k} 需要 {t}"
            if "enum" in spec and spec.get("enum") is not None:
                enum = list(spec.get("enum") or [])
                if enum and out not in enum:
                    return False, {}, f"参数取值错误: {k} 需要为 {enum}"
            cleaned[k] = out

        if not validation_enabled and unknown:
            for k in unknown:
                params.pop(k, None)
        return True, cleaned, ""

    def execute_tool(self, tool_name: str, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]], **kwargs) -> Dict[str, Any]:
        """执行工具"""
        if tool_name not in self.tools:
            return {"success": False, "tool": tool_name, "error": f"工具 '{tool_name}' 不存在"}

        tool = self.tools[tool_name]
        ok, normalized, err = self._validate_and_normalize_params(tool, dict(kwargs))
        if not ok:
            return {"success": False, "tool": tool_name, "error": err or "参数类型错误"}
        kwargs = normalized
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


class ToolExecutorWithRetry(ToolExecutor):
    """
    带自我修正能力的工具执行器

    功能：
    1. 自动检测空结果并分析原因
    2. 自动修正参数并重试
    3. 错误处理和参数修复
    4. 最终回退到统计摘要
    """

    def __init__(self, llm: Any = None, db_path: Optional[str] = None, max_retry: int = 2):
        super().__init__(llm=llm, db_path=db_path)
        self.max_retry = max_retry
        self._retry_stats = {
            'total_calls': 0,
            'retry_attempts': 0,
            'fallbacks': 0
        }

    def execute_with_retry(self, tool_name: str,
                          data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
                          **kwargs) -> Dict[str, Any]:
        """
        执行工具，支持自动重试和修正

        Args:
            tool_name: 工具名称
            data: 数据集
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        self._retry_stats['total_calls'] += 1

        for attempt in range(self.max_retry + 1):
            result = self.execute_tool(tool_name, data, **kwargs)

            # 检查是否需要重试
            should_retry, analysis = self._analyze_result(result, tool_name, kwargs, data)

            if not should_retry:
                return result

            if attempt < self.max_retry:
                self._retry_stats['retry_attempts'] += 1
                logger.info(f"Tool {tool_name} retry {attempt + 1}: {analysis}")

                # 修正参数
                kwargs = self._fix_params(kwargs, analysis, tool_name)
            else:
                logger.warning(f"Tool {tool_name} max retries exceeded, using fallback")
                break

        # 最终回退
        self._retry_stats['fallbacks'] += 1
        return self._fallback_to_summary(data, tool_name, result)

    def _analyze_result(self, result: Dict[str, Any], tool_name: str,
                        params: Dict, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]) -> Tuple[bool, str]:
        """
        分析执行结果，判断是否需要重试

        Returns:
            (should_retry, analysis_reason)
        """
        # 检查执行错误
        if not result.get('success', True):
            error_msg = str(result.get('error', '')).lower()

            if 'not found' in error_msg or '不存在' in error_msg:
                return True, "tool_not_found"
            elif 'parameter' in error_msg or '参数' in error_msg:
                return True, "invalid_parameters"
            elif 'dataset' in error_msg or '数据集' in error_msg:
                return True, "dataset_issue"
            else:
                return False, f"execution_error: {error_msg}"

        # 检查结果是否为空
        tool_result = result.get('result', {})
        if self._is_empty_result(tool_result):
            return True, "empty_result"

        return False, "success"

    def _is_empty_result(self, result: Any) -> bool:
        """检查结果是否为空"""
        if result is None:
            return True
        if isinstance(result, dict):
            # 检查各种空结果模式
            if not result:
                return True
            if 'count' in result and result['count'] == 0:
                return True
            if 'items' in result and not result['items']:
                return True
            if 'data' in result and not result['data']:
                return True
            if 'rows' in result and not result['rows']:
                return True
        if isinstance(result, list) and not result:
            return True
        if isinstance(result, pd.DataFrame) and result.empty:
            return True
        return False

    def _fix_params(self, params: Dict, analysis: str, tool_name: str) -> Dict:
        """
        根据分析结果修正参数

        Args:
            params: 原始参数
            analysis: 分析结果
            tool_name: 工具名称

        Returns:
            修正后的参数
        """
        fixed_params = dict(params)

        if analysis == "empty_result":
            # 空结果 - 可能是过滤条件太严格
            # 放宽一些常见的过滤参数
            for key in list(fixed_params.keys()):
                if key in ['top_n', 'limit', 'max_items']:
                    # 增加返回数量
                    try:
                        current = int(fixed_params[key])
                        fixed_params[key] = max(current, 50)
                    except:
                        fixed_params[key] = 50

                elif key in ['severity', 'status', 'filter']:
                    # 移除严格过滤条件
                    if fixed_params.get(key) in ['Critical', 'Open']:
                        fixed_params.pop(key, None)

        elif analysis == "dataset_issue":
            # 数据集问题 - 尝试切换数据集
            if 'dataset' in fixed_params:
                current = fixed_params['dataset']
                alternatives = ['defects', 'tests'] if current == 'defects' else ['tests', 'defects']
                fixed_params['dataset'] = alternatives[0] if current != alternatives[0] else alternatives[1]

        elif analysis == "invalid_parameters":
            # 参数错误 - 移除未知参数
            known_tool = self.tools.get(tool_name)
            if known_tool and hasattr(known_tool, 'parameters'):
                valid_params = set(known_tool.parameters.keys()) | {'dataset'}
                fixed_params = {k: v for k, v in fixed_params.items() if k in valid_params}

        return fixed_params

    def _fallback_to_summary(self, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
                            original_tool: str,
                            last_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        回退到统计摘要

        Args:
            data: 数据集
            original_tool: 原始工具名称
            last_result: 最后一次执行结果

        Returns:
            回退结果
        """
        logger.info(f"Fallback to statistical_summary from {original_tool}")

        try:
            # 尝试执行统计摘要工具
            fallback_result = self.execute_tool('statistical_summary', data, dataset='defects')

            if fallback_result.get('success'):
                # 包装回退结果
                return {
                    'success': True,
                    'tool': original_tool,
                    'result': fallback_result.get('result', {}),
                    'fallback': True,
                    'fallback_reason': 'max_retries_exceeded',
                    'original_error': last_result.get('error', 'Unknown error')
                }
        except Exception as e:
            logger.error(f"Fallback failed: {e}")

        # 最终回退 - 返回基本数据信息
        summary = self._generate_basic_summary(data)
        return {
            'success': True,
            'tool': original_tool,
            'result': summary,
            'fallback': True,
            'fallback_reason': 'all_retries_failed',
            'note': '由于原始查询条件过于严格，返回基础数据摘要'
        }

    def _generate_basic_summary(self, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]]) -> Dict[str, Any]:
        """生成基础数据摘要"""
        summary = {
            'total_records': 0,
            'summary_text': ''
        }

        try:
            if isinstance(data, dict):
                for name, df in data.items():
                    if isinstance(df, pd.DataFrame):
                        summary[f'{name}_count'] = len(df)
                        summary['total_records'] += len(df)
            elif isinstance(data, pd.DataFrame):
                summary['total_records'] = len(data)
                summary['defects_count'] = len(data)

            summary['summary_text'] = f"数据包含 {summary['total_records']} 条记录"
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            summary['error'] = str(e)

        return summary

    def get_retry_stats(self) -> Dict[str, int]:
        """获取重试统计信息"""
        return dict(self._retry_stats)


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
            'summary': ['总结', '概览', '总体', 'summary', 'overview', 'kpi', '指标', '卡片'],
            'auto': ['一键', '自动', '综合', '全盘', '全景', '全量', '深度分析', '不用一个问题一个问题', 'deep dive'],
            'dashboard': ['看板', '图表', '仪表盘', 'dashboard', 'chart', '大屏', '报表', '总览', '总表'],
            'strategy': ['测试策略', '测试计划', '策略', '计划', '怎么测', '如何测试', '测试方案', '质量策略'],
            'distribution': ['分布', '占比', '比例', 'distribution', 'percentage'],
            'top': ['前', '最高', '最差', 'top', 'highest', 'worst', '最多', '最大', 'min', 'max'],
            'project': ['项目', '工程', 'project'],
            'severity': ['严重', '紧急', 'severity', 'critical'],
            'matrix': ['matrix', '矩阵'],
            'aida': ['aida', '功能', '模块', 'feature', 'service', 'services', 'call services'],
            'fv': ['fv', '版本', 'release', '交付版本', 'feature team', 'feature_team', 'feature-team', '功能团队', '责任团队'],
            'domain': ['solution cluster', 'domain', 'cluster', '解决簇', '解决群', 'solution_cluster'],
            'test': ['测试', 'test', 'run', 'case', 'coverage', '执行', '通过率', '失败率', '测', '测挂', '测失败', '回归', '测试情况', '测试状态'],
            'case': ['case', 'testcase', 'test case', '用例', 'case容易', 'case出错', '容易出错'],
            'execution': ['执行情况', '执行状态', '通过情况', 'pass', 'passed', 'fail', 'failed', 'error', 'blocked', '状态', 'run_status', '失败', '挂', '挂了', '成功率'],
            'cross': ['关联', '相关性', '联动', '交叉', 'correlate', 'relationship'],
            'tester': ['tester', '测试人员', '测试员', '发现人', '谁发现', '谁报', '谁提', '提交人', '报告人', 'reporter', 'found by', 'owner'],
            'wordcloud': ['词云', 'wordcloud', '关键词', '高频词', '热词'],
            'throughput': ['inflow', 'outflow', '收敛', '吞吐', '净积压', 'net accumulation'],
            'longrunner': ['long runner', 'longrunner', '长周期', '处理周期', '阶段耗时', 'phase duration']
            , 'sql': ['sql', 'sqlite', '数据库', 'db']
        }

    def analyze_intent(self, question: str) -> List[str]:
        """分析问题意图"""
        question_lower = question.lower()
        detected_intents = []

        for intent, patterns in self.intent_patterns.items():
            if intent == "aida" and ("feature team" in question_lower or "feature_team" in question_lower or "feature-team" in question_lower):
                patterns = [p for p in patterns if p != "feature"]
            if any(pattern in question_lower for pattern in patterns):
                detected_intents.append(intent)

        # 补充规则：显式“测试人员 + 情况”问法通常是测试运行视角
        if re.search(r"([a-z]{2,}\s+[a-z]{2,}|[\u4e00-\u9fff]{2,8})\s*(是|作为)?\s*测试(人员|员)", question_lower):
            if 'tester' not in detected_intents:
                detected_intents.append('tester')
            if 'test' not in detected_intents:
                detected_intents.append('test')
            if 'execution' not in detected_intents:
                detected_intents.append('execution')

        # 补充规则：“功能/模块 + 失败”优先走测试分析
        if any(k in question_lower for k in ['功能', '模块', 'service', 'services']) and any(k in question_lower for k in ['失败', 'fail', 'failed', '挂']):
            if 'test' not in detected_intents:
                detected_intents.append('test')
            if 'execution' not in detected_intents:
                detected_intents.append('execution')
            if 'aida' not in detected_intents:
                detected_intents.append('aida')

        return detected_intents if detected_intents else ['general']

    @staticmethod
    def _tokenize_text(text: str) -> List[str]:
        if not text:
            return []
        toks = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", str(text).lower())
        out = []
        for t in toks:
            s = str(t).strip()
            if not s or len(s) <= 1:
                continue
            out.append(s)
        return out

    @staticmethod
    @lru_cache(maxsize=16)
    def _semantic_core_dimensions(dataset: str) -> List[Dict[str, Any]]:
        try:
            from semantic_catalog.runtime import SemanticCatalog

            catalog = SemanticCatalog().load_catalog() or {}
            for ds in (catalog.get("datasets") or []):
                aliases = [str(a).strip().lower() for a in (ds.get("aliases") or [])]
                if str(ds.get("id", "")).strip().lower() == str(dataset).strip().lower() or str(dataset).strip().lower() in aliases:
                    dims = ds.get("core_dimensions") or []
                    return [d for d in dims if isinstance(d, dict)]
        except Exception:
            return []
        return []

    def _detect_dimensions(self, question: str, dataset: str, dataframe_columns: List[str], top_k: int = 2) -> List[str]:
        ql = (question or "").lower()
        q_tokens = set(self._tokenize_text(ql))
        cols = [str(c) for c in (dataframe_columns or [])]
        col_set = set(cols)

        scored = []
        for dim in self._semantic_core_dimensions(str(dataset or "").strip().lower()):
            name = str(dim.get("name", "")).strip()
            if not name:
                continue
            aliases = [str(a).strip() for a in (dim.get("aliases") or []) if a is not None and str(a).strip()]
            meaning = str(dim.get("meaning", "")).strip()
            dim_text = " ".join([name, " ".join(aliases), meaning]).strip()
            d_tokens = set(self._tokenize_text(dim_text))
            score = 0
            overlap = len(q_tokens & d_tokens)
            score += overlap * 3
            if name.lower() in ql:
                score += 4
            for a in aliases[:8]:
                al = a.lower()
                if al and al in ql:
                    score += 6
            if name in col_set:
                score += 2
            scored.append((score, name))

        scored = [(s, n) for s, n in scored if s > 0]
        scored.sort(key=lambda x: x[0], reverse=True)
        picked = [n for _, n in scored[: max(0, int(top_k))]]
        if picked:
            return picked

        col_scored = []
        for c in cols:
            ct = set(self._tokenize_text(c))
            s = len(q_tokens & ct)
            if s <= 0:
                continue
            col_scored.append((s, c))
        col_scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in col_scored[: max(0, int(top_k))]]

    def _wants_full_data(self, question: str) -> bool:
        q = (question or "").lower()
        return any(k in q for k in [
            "全量", "完整", "不要抽样", "不要采样", "不采样", "不抽样",
            "不要摘要", "不摘要", "不限制", "准确", "全面", "牺牲速度",
            "full", "all", "exact", "accurate", "no sampling"
        ])

    def extract_entities(self, question: str, data: pd.DataFrame, dataset: str = "defects") -> Dict[str, Any]:
        """提取问题中的实体（项目名、时间范围等）"""
        entities: Dict[str, Any] = {}
        q_raw = (question or "").strip()
        q_lower = q_raw.lower()

        def _norm_text(v: Any) -> str:
            s = str(v or "").strip().lower()
            s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        def _fuzzy_match_values(values: List[str], phrase: str, max_hits: int = 5) -> List[str]:
            p = _norm_text(phrase)
            if not p:
                return []
            p_tokens = [t for t in p.split(" ") if len(t) >= 2]
            scored: List[Tuple[int, str]] = []
            for v in values:
                vn = _norm_text(v)
                if not vn:
                    continue
                score = 0
                if vn == p:
                    score += 10
                if p in vn:
                    score += 8
                if vn in p and len(vn) >= 3:
                    score += 4
                for t in p_tokens:
                    if t in vn:
                        score += 2
                if score > 0:
                    scored.append((score, v))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [v for _, v in scored[:max(1, int(max_hits))]]

        try:
            dims = self._detect_dimensions(question, dataset=dataset, dataframe_columns=list(data.columns), top_k=2)
            if dims:
                entities["dimensions"] = dims
                entities["dimension"] = dims[0]
        except Exception:
            pass

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
            )
            projects = [p for p in projects.unique().tolist() if p and p.lower() not in {"nan", "none"}]
            q = (question or "").lower()
            mentioned_projects = []
            for p in projects:
                pl = str(p).strip().lower()
                if not pl:
                    continue
                pat = r"(?<![a-z0-9_])" + re.escape(pl) + r"(?![a-z0-9_])"
                if re.search(pat, q):
                    mentioned_projects.append(p)
            if mentioned_projects:
                try:
                    max_len = max(len(str(x)) for x in mentioned_projects)
                    mentioned_projects = [x for x in mentioned_projects if len(str(x)) == max_len]
                except Exception:
                    pass
                entities['projects'] = mentioned_projects

        def _extract_from_column(col: str, key: str, max_unique: int = 500) -> None:
            if col not in data.columns:
                return
            series = (
                data[col]
                .dropna()
                .astype(str)
                .map(lambda s: s.strip())
            )
            values = [v for v in series.unique().tolist() if v and v.lower() not in {"nan", "none"}]
            if len(values) > max_unique:
                values = values[:max_unique]
            q = q_lower
            qn = _norm_text(q)
            mentioned = []
            for v in values:
                vn = _norm_text(v)
                if not vn:
                    continue
                if (vn in qn) or (qn in vn and len(qn) >= 3):
                    mentioned.append(v)
            if mentioned:
                entities[key] = mentioned

        _extract_from_column("aida_english", "aidas")
        _extract_from_column("aida", "aidas")
        _extract_from_column("pu", "pus")
        _extract_from_column("fv", "fvs")
        _extract_from_column("domain", "domains")
        _extract_from_column("status_phase", "statuses")
        _extract_from_column("status", "statuses")
        _extract_from_column("tester", "testers")
        _extract_from_column("found_by", "testers")
        _extract_from_column("reporter", "testers")
        _extract_from_column("author_name", "testers")
        _extract_from_column("severity_group", "severities")
        _extract_from_column("severity", "severities")

        # 显式语法解析："fv是xxx" / "feature team是xxx" / "功能是xxx"
        def _get_col_values(col: str, max_unique: int = 1200) -> List[str]:
            if col not in data.columns:
                return []
            s = data[col].dropna().astype(str).map(lambda x: x.strip())
            vals = [v for v in s.unique().tolist() if v and v.lower() not in {"nan", "none"}]
            if len(vals) > max_unique:
                vals = vals[:max_unique]
            return vals

        m_fv = re.search(r"(?:^|\s|[，,。；;])(?:fv|feature\s*team)\s*(?:是|为|=)?\s*([a-z0-9_\- /\u4e00-\u9fff]+)", q_lower)
        if m_fv:
            raw_val = re.split(r"的|测试|情况|如何|怎么样|\?|？", m_fv.group(1), maxsplit=1)[0].strip()
            if raw_val:
                fv_vals = _get_col_values("fv")
                matched = _fuzzy_match_values(fv_vals, raw_val)
                if matched:
                    entities["fvs"] = list(dict.fromkeys((entities.get("fvs") or []) + matched))

        m_aida = re.search(r"(?:功能|模块|services?|call\s*services)\s*(?:是|为|=)?\s*([a-z0-9_\- /\u4e00-\u9fff]+)", q_lower)
        if m_aida:
            raw_val = re.split(r"的|测试|情况|如何|怎么样|\?|？", m_aida.group(1), maxsplit=1)[0].strip()
            if raw_val:
                aida_vals = _get_col_values("aida_english") + _get_col_values("aida") + _get_col_values("top_aida")
                matched = _fuzzy_match_values(list(dict.fromkeys(aida_vals)), raw_val)
                if matched:
                    entities["aidas"] = list(dict.fromkeys((entities.get("aidas") or []) + matched))

        # 提取人名作为 tester 兜底，避免唯一值截断导致命中失败
        q = q_raw
        ql = q.lower()
        candidate_people = []
        if any(k in ql for k in ["测试人员", "测试员", "tester", "情况", "如何", "怎么样", "who"]):
            m_en = re.search(r"\b([a-z]{2,}\s+[a-z]{2,})\b", ql)
            if m_en:
                candidate_people.append(m_en.group(1).strip())
            m_cn = re.search(r"([\u4e00-\u9fff]{2,8})\s*(是|作为)?\s*测试(人员|员)", q)
            if m_cn:
                candidate_people.append(m_cn.group(1).strip())
        if candidate_people:
            existing = entities.get("testers") or []
            entities["testers"] = list(dict.fromkeys(existing + candidate_people))

        ql = (question or "").lower()
        matrix_hits = set()
        matrix_hits.update([m.upper() for m in re.findall(r"\b([12][a-e])\b", ql)])
        matrix_hits.update([m.upper() for m in re.findall(r"matrix[-_ ]?([12][a-e])", ql)])
        if matrix_hits:
            entities["matrices"] = sorted(matrix_hits)

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
        try:
            context_max = int(os.getenv("AGENT_CONTEXT_MAX_ROWS_DEFAULT", "50000"))
        except Exception:
            context_max = 50000
        try:
            tool_max = int(os.getenv("AGENT_TOOL_MAX_ROWS_DEFAULT", "500000"))
        except Exception:
            tool_max = 500000
        full_data_default = os.getenv("AGENT_FULL_DATA_BY_DEFAULT", "0") == "1"
        full_context_default = full_data_default or (os.getenv("AGENT_FULL_CONTEXT_BY_DEFAULT", "0") == "1")
        full_tools_default = full_data_default or (os.getenv("AGENT_FULL_TOOLS_BY_DEFAULT", "0") == "1")
        if full_context_default:
            context_max = 10**12
        if full_tools_default:
            tool_max = 10**12

        if isinstance(data, dict):
            datasets = {k: (v if isinstance(v, pd.DataFrame) else pd.DataFrame()) for k, v in data.items()}
            primary_dataset = self._choose_primary_dataset(question, intents, datasets)
            primary_df = self._normalize_dataset(datasets.get(primary_dataset, pd.DataFrame()), primary_dataset)
            entities = self.extract_entities(question, primary_df, dataset=primary_dataset) if not primary_df.empty else {}
            if entities.get("dimension"):
                dim = str(entities.get("dimension") or "").strip().lower()
                if dim == "aida_english" and "aida" not in intents:
                    intents.append("aida")
                if dim == "fv" and "fv" not in intents:
                    intents.append("fv")
                if dim == "domain" and "domain" not in intents:
                    intents.append("domain")
                if dim == "tester" and "tester" not in intents:
                    intents.append("tester")
                if dim == "project" and "project" not in intents:
                    intents.append("project")

            prepared = {}
            context_views = {}
            dataset_meta = {}
            for name, df in datasets.items():
                norm = self._normalize_dataset(df, name)
                filtered = self._filter_data(norm, intents, entities, dataset=name)
                tool_df, tool_limit_info = self._apply_tool_limit(question, entities, filtered, dataset=name, max_rows=tool_max)
                sampled, sampling_info = self._apply_sampling(question, entities, tool_df, dataset=name, max_rows=context_max)
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
        entities = self.extract_entities(question, df, dataset="defects") if not df.empty else {}
        if entities.get("dimension"):
            dim = str(entities.get("dimension") or "").strip().lower()
            if dim == "aida_english" and "aida" not in intents:
                intents.append("aida")
            if dim == "fv" and "fv" not in intents:
                intents.append("fv")
            if dim == "domain" and "domain" not in intents:
                intents.append("domain")
            if dim == "tester" and "tester" not in intents:
                intents.append("tester")
            if dim == "project" and "project" not in intents:
                intents.append("project")
        filtered_data = self._filter_data(df, intents, entities, dataset="defects")
        tool_df, tool_limit_info = self._apply_tool_limit(question, entities, filtered_data, dataset="defects", max_rows=tool_max)
        sampled, sampling_info = self._apply_sampling(question, entities, tool_df, dataset="defects", max_rows=context_max)
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
        if ('tests' in datasets) and any(i in intents for i in ['test', 'execution', 'case']):
            if any(k in q for k in ['缺陷', 'defect', 'bug']) and ('test' not in intents):
                return 'defects' if 'defects' in datasets else 'tests'
            return 'tests'
        if ('tester' in intents) and ('defects' in datasets):
            return 'defects'
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
                'status_phase', 'status', 'is_critical_issue', 'is_complex_ticket', 'is_long_runner'
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

        if ('fv' in intents) and dataset != "tests":
            for col in ['fv', 'id', '_id', 'name', 'title', 'tproject', 'project', 'tcreationtime', 'creation_time', 'aida_english', 'aida']:
                if col in data.columns:
                    columns.append(col)

        if ('domain' in intents) and dataset != "tests":
            for col in ['domain', 'id', '_id', 'name', 'title', 'tproject', 'project', 'tcreationtime', 'creation_time', 'aida_english', 'aida', 'fv']:
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

        if 'dashboard' in intents or 'auto' in intents:
            tools.append('defect_explore_dashboard')

        if 'summary' in intents or 'auto' in intents:
            tools.append('defect_explore_kpis')

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

        def _norm_text(v: Any) -> str:
            s = str(v or "").strip().lower()
            s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
            s = re.sub(r"\s+", " ", s).strip()
            return s

        def _fuzzy_filter_by_values(df: pd.DataFrame, col: str, targets: List[Any]) -> pd.DataFrame:
            if col not in df.columns:
                return df
            tnorm = [_norm_text(x) for x in (targets or []) if _norm_text(x)]
            if not tnorm:
                return df
            s_norm = df[col].astype(str).map(_norm_text)
            mask = pd.Series(False, index=df.index)
            for t in tnorm:
                if not t:
                    continue
                mask = mask | (s_norm == t)
                mask = mask | s_norm.str.contains(re.escape(t), na=False)
                if len(t) >= 3:
                    mask = mask | s_norm.map(lambda sv: bool(sv) and sv in t)
            out = df[mask]
            return out if not out.empty else df

        # 按项目筛选
        if 'projects' in entities:
            project_col = 'tproject' if 'tproject' in filtered.columns else 'project' if 'project' in filtered.columns else None
            if project_col:
                def _norm_project(v: Any) -> str:
                    s = str(v or "").strip()
                    if not s:
                        return ""
                    u = s.upper()
                    if u in {"IDCEVO", "IDCEVO25", "IDCEVO_25"}:
                        return "IDCEVO"
                    if u in {"IDC"}:
                        return "IDC"
                    if u in {"MGU", "MGU22", "MGU21", "MGU18"}:
                        return "MGU"
                    if u in {"APP"}:
                        return "APP"
                    if u in {"RSU"}:
                        return "RSU"
                    return u

                target = set([_norm_project(x) for x in (entities.get("projects") or []) if str(x or "").strip()])
                if target:
                    series = filtered[project_col].map(_norm_project)
                    filtered = filtered[series.isin(target)]

        if 'aidas' in entities:
            aida_col = "aida_english" if "aida_english" in filtered.columns else "aida" if "aida" in filtered.columns else "top_aida" if "top_aida" in filtered.columns else None
            if aida_col:
                filtered = _fuzzy_filter_by_values(filtered, aida_col, entities["aidas"])

        if 'pus' in entities and 'pu' in filtered.columns:
            filtered = filtered[filtered["pu"].astype(str).isin([str(x) for x in entities["pus"]])]

        if 'fvs' in entities and 'fv' in filtered.columns:
            filtered = _fuzzy_filter_by_values(filtered, "fv", entities["fvs"])

        if 'domains' in entities and 'domain' in filtered.columns:
            filtered = _fuzzy_filter_by_values(filtered, "domain", entities["domains"])

        if 'statuses' in entities:
            status_col = "status_phase" if "status_phase" in filtered.columns else "status" if "status" in filtered.columns else None
            if status_col:
                filtered = filtered[filtered[status_col].astype(str).isin([str(x) for x in entities["statuses"]])]

        if 'testers' in entities:
            candidates = [c for c in ["tester", "found_by", "reporter", "author_name"] if c in filtered.columns]
            tester_col = None
            if candidates:
                best = None
                best_cnt = -1
                for c in candidates:
                    s = filtered[c].astype(str).map(lambda x: str(x).strip())
                    s = s[s.notna() & (s != "") & (s.str.lower() != "nan")]
                    cnt = int(len(s))
                    if cnt > best_cnt:
                        best_cnt = cnt
                        best = c
                tester_col = best
            if tester_col:
                def _norm_person(v: Any) -> str:
                    s = str(v or "").strip().lower()
                    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
                    tokens = [t for t in s.split() if t and t not in {"id", "uid", "userid", "user"}]
                    s2 = "".join(tokens)
                    if s2.endswith("id") and len(s2) >= 5:
                        s2 = s2[:-2]
                    return s2

                entity_norm = []
                for x in (entities.get("testers") or []):
                    nx = _norm_person(x)
                    if nx:
                        entity_norm.append(nx)
                entity_set = set(entity_norm)
                if entity_set:
                    series = filtered[tester_col].astype(str).map(_norm_person)
                    filtered = filtered[series.isin(entity_set)]

        if 'matrices' in entities:
            matrix_col = "matrix_display" if "matrix_display" in filtered.columns else "matrix" if "matrix" in filtered.columns else None
            if matrix_col:
                norm = (
                    filtered[matrix_col]
                    .astype(str)
                    .str.strip()
                    .str.replace("MATRIX-", "", regex=False)
                    .str.replace("Matrix-", "", regex=False)
                    .str.replace("matrix-", "", regex=False)
                    .str.replace("matrix_", "", regex=False)
                    .str.upper()
                )
                filtered = filtered[norm.isin([str(x).upper() for x in entities["matrices"]])]

        if 'severities' in entities:
            sev_col = "severity_group" if "severity_group" in filtered.columns else "severity" if "severity" in filtered.columns else None
            if sev_col:
                filtered = filtered[filtered[sev_col].astype(str).isin([str(x) for x in entities["severities"]])]

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

    def add_fact(self, content: str, importance: float = 0.95, tags: Optional[List[str]] = None, entities: Optional[Dict[str, Any]] = None):
        text = (content or "").strip()
        if not text:
            return
        self.long_term.append({
            'kind': 'fact',
            'content': text[:600],
            'timestamp': datetime.now().isoformat(),
            'importance': float(max(0.0, min(1.0, importance))),
            'tags': list(tags or []),
            'entities': entities or {}
        })
        self._trim_long_term()
        if self.autosave:
            self.save()

    def forget(self, needle: str) -> int:
        key = (needle or "").strip().lower()
        if not key:
            return 0
        before = len(self.long_term)
        kept = []
        for m in self.long_term:
            c = str((m or {}).get('content') or '').lower()
            if key and key in c:
                continue
            kept.append(m)
        self.long_term = kept
        removed = before - len(self.long_term)
        if removed and self.autosave:
            self.save()
        return removed

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

    def _trim_long_term(self):
        now = datetime.now()
        trimmed = []
        for m in self.long_term:
            try:
                ts = str((m or {}).get('timestamp') or '')
                dt = datetime.fromisoformat(ts) if ts else None
            except Exception:
                dt = None
            importance = float((m or {}).get('importance') or 0.5)
            if dt:
                age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
                importance = max(0.05, min(1.0, importance * (0.985 ** age_days)))
            mm = dict(m or {})
            mm['importance'] = importance
            trimmed.append(mm)
        trimmed.sort(key=lambda x: float(x.get('importance') or 0.0), reverse=True)
        self.long_term = trimmed[:self.max_long_term]

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
                'importance': 0.7,
                'tags': self._extract_tags(summary),
                'entities': self._extract_entities(summary),
            })

        for msg in archived:
            if msg['role'] == 'assistant' and len(msg['content']) > 80:
                importance = self._calculate_importance(msg)
                if importance >= 0.7:
                    self.long_term.append({
                        'kind': 'insight',
                        'content': msg['content'][:400],
                        'timestamp': msg['timestamp'],
                        'importance': importance,
                        'tags': self._extract_tags(msg['content']),
                        'entities': self._extract_entities(msg['content']),
                    })

        self._trim_long_term()

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

    def _extract_tags(self, text: str) -> List[str]:
        s = (text or "").lower()
        tags = []
        for t in ["sql", "sqlite", "口径", "定义", "字段", "风险", "建议", "重复", "已知问题", "测试", "缺陷", "project", "pu", "fv"]:
            if t in s:
                tags.append(t)
        return tags[:8]

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        s = (text or "").strip()
        low = s.lower()
        entities: Dict[str, Any] = {}
        projects = []
        for p in ["idcevo", "idevo", "app"]:
            if p in low:
                projects.append(p)
        if projects:
            entities["projects"] = sorted(list(set(projects)))
        m = re.findall(r"\bpu\s*[:：]?\s*([a-z0-9._-]{2,})\b", low, flags=re.IGNORECASE)
        if m:
            entities["pu"] = sorted(list(set([x.strip() for x in m if x and x.strip()])))[:5]
        nums = re.findall(r"\b\d{2,}\b", low)
        if nums:
            entities["numbers"] = nums[:6]
        return entities

    def get_relevant_history(self, query: str, top_k: int = 3) -> List[Dict]:
        """获取相关历史记录（简单实现：基于关键词匹配）"""
        query_lower = (query or "").lower()
        tokens = [t.strip() for t in re.split(r"[\s,，。；;]+", query_lower) if t and len(t.strip()) >= 2]
        tokens = tokens[:12]

        def _score(text: str) -> int:
            s = (text or "").lower()
            return sum(1 for t in tokens if t in s)

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for msg in (self.short_term or []):
            c = msg.get('content') or ''
            hit = _score(c)
            if hit <= 0:
                continue
            scored.append((1000.0 + float(hit), msg))

        for memory in (self.long_term or []):
            c = memory.get('content', '') or ''
            hit = _score(c)
            if hit <= 0:
                continue
            base = float(memory.get('importance') or 0.5) * 10.0
            scored.append((base + float(hit), {
                'role': 'assistant',
                'content': c,
                'timestamp': memory.get('timestamp'),
                'from_memory': True,
                'kind': memory.get('kind'),
                'tags': memory.get('tags') or [],
                'entities': memory.get('entities') or {}
            }))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in scored[: max(1, int(top_k))]]

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
            os.makedirs(os.path.dirname(os.path.abspath(self.memory_file)), exist_ok=True)
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

    def __init__(self, tool_executor: ToolExecutor, llm: Any = None):
        self.tool_executor = tool_executor

    def plan(self, query: str, context: Dict) -> List[Dict]:
        """规划任务步骤"""
        steps = []

        intents = context.get('intents', [])
        entities = context.get('entities', {})
        primary_dataset = context.get('primary_dataset', 'defects')
        q = (query or "").lower()
        auto_strong = any(k in q for k in ["一键", "综合", "全盘", "全景", "全量", "深度分析", "deep dive", "不用一个问题一个问题"])

        wants_semantic_introspection = any(k in q for k in ["语义覆盖率", "字段对账", "字段对齐", "字段覆盖", "semantic coverage"])
        if wants_semantic_introspection and (
            hasattr(self.tool_executor, "tools") and ("semantic_coverage_report" in (self.tool_executor.tools or {}))
        ):
            steps.append(
                {
                    "step": len(steps) + 1,
                    "tool": "semantic_coverage_report",
                    "description": "生成语义覆盖率与字段对账报告",
                    "params": {"dashboard": str(context.get("dashboard_type") or "defect_explore"), "max_columns": 20, "sample_rows": 0},
                }
            )
            return steps

        def _extract_top_n(default: int) -> int:
            m = re.search(r"(top|前)\s*(\d{1,3})", q)
            if m:
                try:
                    v = int(m.group(2))
                    return max(1, min(200, v))
                except Exception:
                    return default
            return default

        def _choose_case_col(available_cols: List[str]) -> Optional[str]:
            if not available_cols:
                return None
            cols = set(available_cols)
            for c in ["test_case", "testcase", "case", "case_id", "case_name", "test_name", "test_id", "name", "title"]:
                if c in cols:
                    return c
            for c in available_cols:
                lc = c.lower()
                if "case" in lc and ("id" in lc or "name" in lc):
                    return c
            for c in available_cols:
                lc = c.lower()
                if lc in {"test_id", "test_name"}:
                    return c
            return None

        wants_semantic = any(k in q for k in ["口径", "定义", "字段", "含义", "怎么计算", "如何计算", "calculation", "definition", "metric"])
        if (os.getenv("AGENT_SEMANTIC_CATALOG_ENABLED") != "1" and wants_semantic) and (
            hasattr(self.tool_executor, 'tools') and ('consult_semantic_catalog' in (self.tool_executor.tools or {}))
        ):
            steps.append({
                'step': len(steps) + 1,
                'tool': 'consult_semantic_catalog',
                'description': '检索语义目录（口径/字段/误用风险）',
                'params': {'question': query, 'dashboard': str(context.get('dashboard_type') or '')}
            })

        wants_duplicate = any(k in q for k in ["重复", "相似", "类似", "已知问题", "known issue", "duplicate"])
        if wants_duplicate and ('defects' in (context.get('datasets') or {})) and (
            hasattr(self.tool_executor, 'tools') and ('search_similar_issues' in (self.tool_executor.tools or {}))
        ):
            steps.append({
                'step': len(steps) + 1,
                'tool': 'search_similar_issues',
                'description': '检索相似缺陷/已知问题（重复提票检测）',
                'params': {'query': query, 'top_k': 8, 'dataset': 'defects', 'cache_key': 'defects'}
            })

        if ('tester' in intents) and primary_dataset != "tests" and (
            hasattr(self.tool_executor, "tools") and ("match_tester_tickets" in (self.tool_executor.tools or {}))
        ):
            person = None
            m = re.search(r"([\u4e00-\u9fff]{2,6})\s*(?:提|报|发现)", query)
            if m:
                person = m.group(1)
            if not person:
                m2 = re.match(r"^\s*([\u4e00-\u9fff]{2,6})", query)
                if m2:
                    person = m2.group(1)
            if person and any(k in q for k in ["多少", "分布", "aida"]):
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "match_tester_tickets",
                        "description": "匹配指定人员并输出提票分布",
                        "params": {"person": person, "dimension": "aida", "top_n": _extract_top_n(10), "sample_n": 10, "dataset": primary_dataset},
                    }
                )
                return steps

        if (('sql' in intents) or any(k in q for k in ['sql', 'sqlite', '数据库', 'db'])) and (
            hasattr(self.tool_executor, 'tools') and ('query_sqlite_with_fix' in (self.tool_executor.tools or {}))
        ):
            if hasattr(self.tool_executor, 'tools') and ('get_db_profile' in (self.tool_executor.tools or {})):
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'get_db_profile',
                    'description': '获取数据库画像（字段/高频值/空值率）以提升SQL生成准确率',
                    'params': {'top_n': 5, 'sample_columns': 20}
                })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'query_sqlite_with_fix',
                'description': '将自然语言问题转为SQLite只读查询并执行（失败自动纠错）',
                'params': {'question': query, 'limit': 200}
            })
            return steps

        wants_recent_weeks = any(k in q for k in ["最近", "近", "过去"]) and ("周" in q or "week" in q)
        wants_defect_test_joint = any(k in q for k in ["缺陷", "defect", "bug"]) and any(k in q for k in ["测试", "test", "执行", "run"])
        if wants_recent_weeks and wants_defect_test_joint and ('defects' in (context.get('datasets') or {})) and ('tests' in (context.get('datasets') or {})) and (
            hasattr(self.tool_executor, "tools") and ("analyze_project_recent_weeks" in (self.tool_executor.tools or {}))
        ):
            proj = None
            if isinstance(entities.get("projects"), list) and entities.get("projects"):
                proj = str(entities.get("projects")[0] or "").strip()
            if not proj:
                m = re.search(r"\\b(idcevo|idc|mgu|app|rsu)\\b", q)
                if m:
                    proj = m.group(1)
            if proj:
                n_weeks = 4
                for n in (entities.get("numbers") or []):
                    try:
                        if 1 <= int(n) <= 26:
                            n_weeks = int(n)
                            break
                    except Exception:
                        continue
                steps.append(
                    {
                        "step": len(steps) + 1,
                        "tool": "analyze_project_recent_weeks",
                        "description": f"评估项目 {proj} 最近{n_weeks}周缺陷发现与测试失败率是否恶化",
                        "params": {"project": proj, "weeks": n_weeks},
                    }
                )
                return steps

        if ('tests' in (context.get('datasets') or {})) and ('test' in intents or 'execution' in intents) and (
            ('project' in intents) or ('各项目' in q) or ('项目' in q)
        ) and any(k in q for k in ["执行情况", "执行状态", "通过情况", "状态", "pass", "passed", "fail", "failed"]):
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_test_run',
                'description': '按项目对比测试执行状态与失败率',
                'params': {'group_by': 'project', 'dataset': 'tests'}
            })
            return steps

        if ('tests' in (context.get('datasets') or {})) and ('tester' in intents) and ('test' in intents or 'execution' in intents) and any(k in q for k in ["测试人员", "测试员", "tester", "情况", "如何", "怎么样", "who"]):
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_test_run',
                'description': '按测试人员统计测试执行状态与失败率',
                'params': {'group_by': 'tester', 'dataset': 'tests'}
            })
            return steps

        if ('tester' in intents) and ('defects' in (context.get('datasets') or {})) and any(k in q for k in ["测试人员", "tester", "发现人", "谁发现", "不同测试人员"]):
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_tester_findings',
                'description': '按 tester 统计缺陷发现分布与严重/TopIssue 占比',
                'params': {'top_n': 15, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_dashboard',
                'description': '补充 tester 相关看板图表（严重率/效率）',
                'params': {'question': query, 'max_items': 15}
            })
            return steps

        wants_case_ranking = any(k in q for k in ["哪些", "top", "前", "容易", "出错", "失败率"]) or ("case" in q)
        if wants_case_ranking and ('test' in intents or 'case' in intents) and ('tests' in (context.get('datasets') or {})) and any(k in q for k in ["case", "用例", "testcase", "test case"]):
            tests_meta = (context.get('datasets') or {}).get('tests') or {}
            case_col = _choose_case_col(tests_meta.get('available_columns') or [])
            if not case_col:
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_test_run',
                    'description': '缺少 case 字段，退化为按周统计测试失败率',
                    'params': {'group_by': 'week', 'dataset': 'tests'}
                })
                return steps

            top_n = _extract_top_n(20)
            steps.append({
                'step': len(steps) + 1,
                'tool': 'groupby_aggregate',
                'description': f'按用例维度统计失败率（{case_col}）',
                'params': {
                    'dataset': 'tests',
                    'group_by': case_col,
                    'aggregations': [{'op': 'failure_rate', 'column': '', 'name': 'failure_rate'}],
                    'top_n': top_n,
                    'sort_by': 'failure_rate',
                    'descending': True,
                    'status_column': 'run_status'
                }
            })
            return steps

        if 'strategy' in intents:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_dashboard',
                'description': '汇总看板业务图表指标（用于策略输入）',
                'params': {
                    'question': query,
                    'max_items': 20,
                    'include_inflow_outflow': ('throughput' in intents) or any(k in (query or '').lower() for k in ['inflow', 'outflow', '收敛', '吞吐', '净积压']),
                    'include_longrunner': any(k in (query or '').lower() for k in ['long runner', 'longrunner', '长周期', '阶段耗时'])
                }
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_kpis',
                'description': '生成看板 KPI 概览',
                'params': {'dataset': 'defects'}
            })
            if 'tests' in (context.get('datasets') or {}):
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_test_run',
                    'description': '分析测试失败率（按周）',
                    'params': {'group_by': 'week', 'dataset': 'tests'}
                })
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_test_run',
                    'description': '分析测试失败率（按项目）',
                    'params': {'group_by': 'project', 'dataset': 'tests'}
                })
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'correlate_defects_tests',
                    'description': '关联缺陷与测试（发现高风险项目）',
                    'params': {'top_n': 10}
                })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_risk',
                'description': '分析风险（按project维度）',
                'params': {'dimension': 'project', 'top_n': 10, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_matrix_aida_hotspots',
                'description': '分析 matrix×AIDA 热点（用于测试重点）',
                'params': {'top_matrices': 10, 'top_aidas': 8, 'sample_tickets': 2, 'include_unknown': True, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_topissue_hotlist',
                'description': '输出 TopIssue 高风险票据清单',
                'params': {'top_n': 15, 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_longrunner_hotlist',
                'description': '输出 LongRunner 票据清单',
                'params': {'top_n': 15, 'dataset': 'defects'}
            })
            return steps

        if ('auto' in intents) and auto_strong:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_dashboard',
                'description': '汇总看板业务图表指标（按问题聚焦）',
                'params': {
                    'question': query,
                    'max_items': 15,
                    'include_inflow_outflow': ('throughput' in intents) or any(k in (query or '').lower() for k in ['inflow', 'outflow', '收敛', '吞吐', '净积压']),
                    'include_longrunner': any(k in (query or '').lower() for k in ['long runner', 'longrunner', '长周期', '阶段耗时'])
                }
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_kpis',
                'description': '生成看板 KPI 概览',
                'params': {'dataset': 'defects'}
            })
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
                'tool': 'analyze_trend',
                'description': '按 FV 统计 Top 分布',
                'params': {'group_by': 'fv', 'metric': 'count', 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_trend',
                'description': '按 AIDA 统计 Top 分布',
                'params': {'group_by': 'aida', 'metric': 'count', 'dataset': 'defects'}
            })
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_trend',
                'description': '按 Solution Cluster/Domain 统计 Top 分布',
                'params': {'group_by': 'domain', 'metric': 'count', 'dataset': 'defects'}
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
        if 'dashboard' in intents:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_dashboard',
                'description': '汇总看板业务图表指标（按问题聚焦）',
                'params': {
                    'question': query,
                    'max_items': 15,
                    'include_inflow_outflow': ('throughput' in intents) or any(k in (query or '').lower() for k in ['inflow', 'outflow', '收敛', '吞吐', '净积压']),
                    'include_longrunner': any(k in (query or '').lower() for k in ['long runner', 'longrunner', '长周期', '阶段耗时'])
                }
            })

        if 'summary' in intents:
            steps.append({
                'step': len(steps) + 1,
                'tool': 'defect_explore_kpis',
                'description': '生成看板 KPI 概览',
                'params': {'dataset': primary_dataset}
            })

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
            ql = (query or "").lower()
            group_by = "week"
            if any(k in ql for k in ["按周", "按月", "week", "month", "cw", "calendar_week", "测试周"]):
                group_by = "week" if "month" not in ql else "month"
            else:
                dim = str((entities or {}).get("dimension") or "").strip()
                if "tester" in intents or any(k in ql for k in ["测试人员", "测试员", "tester", "谁"]):
                    group_by = "tester"
                elif "fv" in intents or "feature team" in ql or "feature_team" in ql:
                    group_by = "fv"
                elif "aida" in intents or any(k in ql for k in ["功能", "模块", "service", "services"]):
                    group_by = "aida"
                elif dim and dim.lower() not in {"id", "_id", "test_id", "run_id", "mr_id"}:
                    group_by = dim
                elif "project" in intents or "各项目" in ql or "项目" in ql or "project" in ql:
                    group_by = "project"
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_test_run',
                'description': f'分析测试运行状态与失败率（按{group_by}分组）',
                'params': {'group_by': group_by, 'dataset': 'tests'}
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

        if (('distribution' in intents) or ('top' in intents)) and primary_dataset != 'tests':
            handled = False
            if 'aida' in intents:
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_trend',
                    'description': '按 AIDA 统计 Top 分布',
                    'params': {'group_by': 'aida', 'metric': 'count', 'dataset': primary_dataset}
                })
                handled = True
            if 'fv' in intents:
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_trend',
                    'description': '按 FV 统计 Top 分布',
                    'params': {'group_by': 'fv', 'metric': 'count', 'dataset': primary_dataset}
                })
                handled = True
            if 'domain' in intents:
                steps.append({
                    'step': len(steps) + 1,
                    'tool': 'analyze_trend',
                    'description': '按 Solution Cluster/Domain 统计 Top 分布',
                    'params': {'group_by': 'domain', 'metric': 'count', 'dataset': primary_dataset}
                })
                handled = True
            if (not handled) and entities.get("dimension"):
                dim = str(entities.get("dimension") or "").strip()
                if dim:
                    steps.append({
                        'step': len(steps) + 1,
                        'tool': 'analyze_trend',
                        'description': f'按 {dim} 统计 Top 分布',
                        'params': {'group_by': dim, 'metric': 'count', 'dataset': primary_dataset}
                    })

        if (('distribution' in intents) or ('top' in intents)) and primary_dataset == 'tests' and ('test' not in intents):
            dim = str((entities or {}).get("dimension") or "").strip() or "project"
            steps.append({
                'step': len(steps) + 1,
                'tool': 'analyze_trend',
                'description': f'按 {dim} 统计 Top 分布',
                'params': {'group_by': dim, 'metric': 'count', 'dataset': 'tests'}
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

    def execute_plan(
        self,
        steps: List[Dict],
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        context: Optional[Dict] = None,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[Dict]:
        """执行计划"""
        results = []
        datasets_meta = (context or {}).get("datasets") or {}
        validation_enabled = os.getenv("AGENT_VALIDATION_ENABLED", "0") == "1"
        primary_dataset = (context or {}).get("primary_dataset") or ("defects" if isinstance(data, dict) and "defects" in data else None)

        total_steps = len(steps or [])
        for idx, step in enumerate(steps or [], start=1):
            tool_name = step['tool']
            params = step.get('params', {})

            dataset_used: Optional[str] = None
            if isinstance(data, dict):
                tool = (getattr(self.tool_executor, "tools", {}) or {}).get(tool_name)
                if tool is not None and getattr(tool, "expects_datasets", lambda: False)():
                    dataset_used = "datasets"
                else:
                    dataset_used = params.get("dataset") or ("defects" if "defects" in data else next(iter(data.keys()), None))

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
            if progress_cb:
                try:
                    progress_cb(
                        {
                            "event": "tool_start",
                            "step_index": idx,
                            "total_steps": total_steps,
                            "tool": tool_name,
                            "dataset": dataset_used,
                            "params": dict(params),
                            "description": step.get("description"),
                        }
                    )
                except Exception:
                    pass
            t0 = time.perf_counter()
            # 使用带重试的执行方法（如果可用）
            if hasattr(self.tool_executor, 'execute_with_retry'):
                result = self.tool_executor.execute_with_retry(tool_name, data, **params)
            else:
                result = self.tool_executor.execute_tool(tool_name, data, **params)

            # analyze_test_run 失败时优先尝试更稳妥分组，避免直接退化为摘要
            if tool_name == 'analyze_test_run' and isinstance(result, dict) and result.get('success') is False:
                current_group = str((params or {}).get('group_by') or '').strip().lower()
                for alt_group in ['project', 'aida', 'tester', 'week']:
                    if alt_group == current_group:
                        continue
                    alt_params = dict(params)
                    alt_params['group_by'] = alt_group
                    alt_result = self.tool_executor.execute_tool(tool_name, data, **alt_params)
                    if isinstance(alt_result, dict) and alt_result.get('success') is True:
                        params = alt_params
                        result = alt_result
                        break
            duration_ms = int((time.perf_counter() - t0) * 1000)
            meta = datasets_meta.get(dataset_used) if dataset_used else None
            gate: Dict[str, Any] = {"enabled": bool(validation_enabled), "action": "none", "reason": ""}
            if validation_enabled and isinstance(result, dict) and result.get("success") is False:
                gate["reason"] = str(result.get("error") or "工具执行失败")
                if tool_name in {"consult_semantic_catalog", "search_similar_issues"}:
                    gate["action"] = "continue_degraded"
                else:
                    gate["action"] = "stop"
            results.append({
                'step': step['step'],
                'tool': tool_name,
                'description': step['description'],
                'result': result,
                'trace': {
                    'tool': tool_name,
                    'dataset': dataset_used,
                    'params': dict(params),
                    'duration_ms': duration_ms,
                    'tool_limit': (meta or {}).get('tool_limit') if isinstance(meta, dict) else None,
                    'sampling': (meta or {}).get('sampling') if isinstance(meta, dict) else None,
                    'gate': gate,
                }
            })
            if progress_cb:
                try:
                    progress_cb(
                        {
                            "event": "tool_end",
                            "step_index": idx,
                            "total_steps": total_steps,
                            "tool": tool_name,
                            "dataset": dataset_used,
                            "duration_ms": duration_ms,
                            "success": bool(isinstance(result, dict) and result.get("success") is True),
                            "error": (result.get("error") if isinstance(result, dict) else None),
                            "gate": dict(gate),
                        }
                    )
                except Exception:
                    pass
            if validation_enabled and gate.get("action") == "stop":
                has_success = any(isinstance(r.get("result"), dict) and r["result"].get("success") for r in results)
                if (not has_success) and tool_name != "statistical_summary" and primary_dataset:
                    fallback_params = {"dataset": primary_dataset} if isinstance(data, dict) else {}
                    t1 = time.perf_counter()
                    fb = self.tool_executor.execute_tool("statistical_summary", data, **fallback_params)
                    fb_ms = int((time.perf_counter() - t1) * 1000)
                    fb_meta = datasets_meta.get(primary_dataset) if isinstance(datasets_meta, dict) else None
                    results.append({
                        'step': int(step.get("step") or 0) + 1,
                        'tool': "statistical_summary",
                        'description': "执行失败后的退化：生成数据摘要",
                        'result': fb,
                        'trace': {
                            'tool': "statistical_summary",
                            'dataset': primary_dataset,
                            'params': dict(fallback_params),
                            'duration_ms': fb_ms,
                            'tool_limit': (fb_meta or {}).get('tool_limit') if isinstance(fb_meta, dict) else None,
                            'sampling': (fb_meta or {}).get('sampling') if isinstance(fb_meta, dict) else None,
                            'gate': {"enabled": True, "action": "fallback", "reason": gate.get("reason") or ""},
                        }
                    })
                break

        return results


# ============================================================================
# 6. 智能 Agent 主类
# ============================================================================

class IntelligentAgent:
    """智能 Agent - 整合所有功能"""

    def __init__(self, dashboard_type: str = 'general', llm: Any = None, db_path: Optional[str] = None):
        self.dashboard_type = dashboard_type

        # 初始化各组件
        # 使用带重试功能的工具执行器
        retry_enabled = os.getenv("AGENT_TOOL_RETRY_ENABLED", "1") == "1"
        if retry_enabled:
            self.tool_executor = ToolExecutorWithRetry(llm=llm, db_path=db_path, max_retry=2)
        else:
            self.tool_executor = ToolExecutor(llm=llm, db_path=db_path)
        self.context_manager = IntelligentContextManager()
        memory_enabled = os.getenv("AGENT_MEMORY_ENABLED", "0") == "1"
        memory_file = os.getenv("AGENT_MEMORY_FILE")
        if memory_enabled and not memory_file:
            base = os.path.join(PROJECT_ROOT, "history")
            memory_file = os.path.join(base, f"agent_memory_{dashboard_type}.json")
        autosave = os.getenv("AGENT_MEMORY_AUTOSAVE", "0") == "1"
        self.memory = ConversationMemory(memory_file=memory_file, autosave=autosave)
        self.knowledge_base = KnowledgeBase()
        self.task_planner = TaskPlanner(self.tool_executor)

        logger.info(f"智能 Agent 初始化完成 (类型: {dashboard_type})")

    def process(
        self,
        question: str,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        conversation_history: List = None,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
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

        qtext = (question or "").strip()
        if qtext.startswith("记住：") or qtext.lower().startswith("remember:"):
            payload = qtext.split("：", 1)[-1].strip() if "：" in qtext else qtext.split(":", 1)[-1].strip()
            self.memory.add_fact(payload, importance=0.98)
            return {"text": "已记住。", "insights": [], "visualizations": [], "tools_used": [], "context": {"memory": "saved"}}
        if qtext.startswith("忘记：") or qtext.lower().startswith("forget:"):
            payload = qtext.split("：", 1)[-1].strip() if "：" in qtext else qtext.split(":", 1)[-1].strip()
            removed = self.memory.forget(payload)
            return {"text": f"已删除 {removed} 条相关记忆。", "insights": [], "visualizations": [], "tools_used": [], "context": {"memory": "deleted", "removed": removed}}

        if conversation_history and os.getenv("AGENT_SYNC_UI_HISTORY", "1") == "1":
            try:
                max_ui = int(os.getenv("AGENT_UI_HISTORY_MAX_MESSAGES", str(self.memory.max_short_term)))
            except Exception:
                max_ui = self.memory.max_short_term
            ui_msgs = []
            for m in (conversation_history or []):
                try:
                    role = (m or {}).get("role")
                    if role not in {"user", "assistant"}:
                        continue
                    if (m or {}).get("type") in {"stream_response"}:
                        continue
                    content = str((m or {}).get("content") or "").strip()
                    if not content:
                        continue
                    ui_msgs.append(
                        {
                            "role": role,
                            "content": content,
                            "timestamp": (m or {}).get("timestamp") or datetime.now().isoformat(),
                            "metadata": {"from_ui": True},
                        }
                    )
                except Exception:
                    continue
            if max_ui > 0 and len(ui_msgs) > max_ui:
                ui_msgs = ui_msgs[-max_ui:]
            if ui_msgs:
                self.memory.short_term = ui_msgs[-self.memory.max_short_term :]

        # 1. 保存用户消息到记忆
        self.memory.add_message('user', question)

        # 2. 准备上下文
        context, prepared_data = self.context_manager.prepare_context(question, data)
        if progress_cb:
            try:
                progress_cb(
                    {
                        "event": "context_ready",
                        "primary_dataset": context.get("primary_dataset"),
                        "intents": list(context.get("intents") or []),
                    }
                )
            except Exception:
                pass

        validation_enabled = os.getenv("AGENT_VALIDATION_ENABLED", "0") == "1"
        # 默认启用 agentic（若LLM可用），可通过 AGENT_AGENTIC_ENABLED=0 显式关闭。
        agentic_enabled = (os.getenv("AGENT_AGENTIC_ENABLED", "1") != "0") and (self.tool_executor._llm is not None)
        mode = str(os.getenv("AGENT_MODE", "agentic") or "agentic").strip().lower()
        if mode not in {"rule", "agentic", "hybrid"}:
            mode = "agentic"

        # ACCESSCODE 内网模板链路已在非流式调用中验证更稳定，但 function-calling 兼容性不稳定。
        # 在该链路下优先使用 hybrid，避免 agentic 每轮都因响应结构差异失败后再降级。
        llm_obj = self.tool_executor._llm
        internal_template_route = False
        try:
            checker = getattr(llm_obj, "_should_use_internal_template_for_nonstream", None)
            if callable(checker):
                internal_template_route = bool(checker())
        except Exception:
            internal_template_route = False

        if mode == "agentic" and internal_template_route:
            logger.info("检测到ACCESSCODE内网模板链路，自动切换为hybrid模式以提升稳定性")
            mode = "hybrid"

        if (not agentic_enabled) and mode == "agentic":
            mode = "rule"
        analysis_trace: Dict[str, Any] = {
            "mode": mode,
            "validation_enabled": bool(validation_enabled),
            "plan": [],
            "execution": [],
        }
        if internal_template_route:
            analysis_trace["llm_route"] = "internal_template"

        if os.getenv("AGENT_SEMANTIC_CATALOG_ENABLED") == "1":
            try:
                from semantic_catalog.runtime import build_semantic_context

                dashboard = self.dashboard_type
                cols = []
                if isinstance(prepared_data, dict):
                    primary = context.get("primary_dataset") or ("defects" if "defects" in prepared_data else next(iter(prepared_data.keys()), None))
                    df = prepared_data.get(primary) if primary else None
                    if isinstance(df, pd.DataFrame):
                        cols = [str(c) for c in df.columns.tolist()]
                elif isinstance(prepared_data, pd.DataFrame):
                    cols = [str(c) for c in prepared_data.columns.tolist()]
                db_path = getattr(self.tool_executor, "_db_path", None)
                context["semantic_context"] = build_semantic_context(
                    question=question, dashboard=dashboard, dataframe_columns=cols, max_each=6, db_path=db_path
                )
            except Exception as e:
                context["semantic_context"] = f"语义目录加载失败: {e}"

        if mode == "agentic":
            tool_call_max = int(os.getenv("AGENT_TOOL_CALL_MAX", "8") or 8)
            tool_call_max = max(0, min(tool_call_max, 100))
            max_iters = int(os.getenv("AGENT_AGENTIC_MAX_ITERS", "6") or 6)
            max_iters = max(1, min(max_iters, 20))
            exec_rows = []
            try:
                llm = self.tool_executor._llm
                tools_schema = self.tool_executor.get_tool_schema() or {}
                if not llm or not getattr(llm, "client", None):
                    raise RuntimeError("agentic 模式缺少可用 LLM client")

                def _to_json_schema(params: Any) -> Dict[str, Any]:
                    props: Dict[str, Any] = {}
                    if not isinstance(params, dict):
                        return {"type": "object", "properties": {}, "additionalProperties": True}
                    type_map = {
                        "string": "string",
                        "integer": "integer",
                        "number": "number",
                        "boolean": "boolean",
                        "array": "array",
                        "object": "object",
                    }
                    for pname, pdef in params.items():
                        if not isinstance(pdef, dict):
                            props[str(pname)] = {"type": "string"}
                            continue
                        ptype = type_map.get(str(pdef.get("type") or "string").lower(), "string")
                        item: Dict[str, Any] = {"type": ptype}
                        if pdef.get("description"):
                            item["description"] = str(pdef.get("description"))
                        if isinstance(pdef.get("enum"), list) and pdef.get("enum"):
                            item["enum"] = list(pdef.get("enum"))
                        if ptype == "array" and isinstance(pdef.get("items"), dict):
                            item["items"] = dict(pdef.get("items"))
                        props[str(pname)] = item
                    return {"type": "object", "properties": props, "additionalProperties": True}

                tool_specs = []
                for tname, ts in tools_schema.items():
                    ts = ts if isinstance(ts, dict) else {}
                    tool_specs.append(
                        {
                            "type": "function",
                            "function": {
                                "name": str(tname),
                                "description": str(ts.get("description") or ""),
                                "parameters": _to_json_schema(ts.get("parameters") or {}),
                            },
                        }
                    )

                sys_prompt = "你是数据分析助手。你必须基于工具返回的真实结果逐步决策；当信息足够时直接给最终结论。"
                if context.get("data_summary"):
                    sys_prompt += "\n\n数据摘要:\n" + str(context.get("data_summary"))

                messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": question}]
                used = 0
                final_text = ""
                stop_reason = ""

                for it in range(1, max_iters + 1):
                    resp = llm.client.chat.completions.create(
                        model=getattr(llm, "model", None),
                        messages=messages,
                        tools=tool_specs,
                        temperature=0.1,
                    )
                    choices = getattr(resp, "choices", None)
                    if not choices:
                        raise RuntimeError("LLM响应缺少choices（可能是网关异常、鉴权失败或上下文被服务端拒绝）")

                    first_choice = choices[0] if isinstance(choices, list) else None
                    if first_choice is None:
                        raise RuntimeError("LLM响应choices[0]为空")

                    msg = getattr(first_choice, "message", None)
                    if msg is None:
                        raise RuntimeError("LLM响应缺少message")

                    content = str(getattr(msg, "content", "") or "").strip()
                    if content:
                        final_text = content

                    tool_calls = list(getattr(msg, "tool_calls", None) or [])
                    if not tool_calls:
                        stop_reason = "model_final_answer"
                        break

                    tool_feedback_lines = [f"第{it}轮工具执行结果："]
                    for tc in tool_calls:
                        tname = str(getattr(getattr(tc, "function", None), "name", "") or "").strip()
                        arg_text = str(getattr(getattr(tc, "function", None), "arguments", "") or "").strip()
                        if not tname:
                            continue
                        if used >= tool_call_max:
                            exec_rows.append({"iter": it, "tool": tname, "success": False, "error": "工具调用预算已用尽"})
                            tool_feedback_lines.append(f"- {tname}: 失败，原因=工具调用预算已用尽")
                            stop_reason = "tool_budget_exhausted"
                            continue

                        used += 1
                        try:
                            args = json.loads(arg_text) if arg_text else {}
                        except Exception:
                            args = {}

                        t0 = time.perf_counter()
                        out = self.tool_executor.execute_tool(tname, prepared_data, **(args if isinstance(args, dict) else {}))
                        ms = int((time.perf_counter() - t0) * 1000)
                        ok = bool(isinstance(out, dict) and out.get("success") is True)
                        err = (out.get("error") if isinstance(out, dict) else None)
                        exec_rows.append(
                            {
                                "iter": it,
                                "tool": tname,
                                "dataset": (args or {}).get("dataset") if isinstance(args, dict) else None,
                                "params": args if isinstance(args, dict) else {},
                                "duration_ms": ms,
                                "success": ok,
                                "error": err,
                            }
                        )

                        preview = ""
                        if isinstance(out, dict):
                            if ok:
                                r = out.get("result")
                                if isinstance(r, dict):
                                    preview = ", ".join([str(k) for k in list(r.keys())[:6]])
                                elif isinstance(r, list):
                                    preview = f"rows={len(r)}"
                                else:
                                    preview = str(r)[:180]
                            else:
                                preview = str(err or "工具失败")[:180]
                        else:
                            preview = str(out)[:180]

                        status_text = "成功" if ok else "失败"
                        tool_feedback_lines.append(f"- {tname}: {status_text}; 摘要={preview}")

                    # 把环境真实反馈注入下一轮决策
                    messages.append({"role": "user", "content": "\n".join(tool_feedback_lines) + "\n请基于以上真实结果继续：若信息足够请直接给结论，否则继续调用工具。"})

                    if stop_reason == "tool_budget_exhausted":
                        break

                if not stop_reason:
                    stop_reason = "max_iterations_reached"

                if not final_text:
                    success_cnt = sum(1 for r in exec_rows if r.get("success"))
                    final_text = f"已完成工具执行（成功 {success_cnt}/{len(exec_rows)}），但未产出最终自然语言结论。"

                analysis_trace["execution"] = exec_rows
                analysis_trace["agentic_stop_reason"] = stop_reason
                context["analysis_trace"] = analysis_trace
                self.memory.add_message('assistant', final_text, {'tools_used': [r.get('tool') for r in exec_rows], 'execution_time': (datetime.now() - start_time).total_seconds()})
                return {"text": final_text, "insights": [], "visualizations": [], "tools_used": [r.get("tool") for r in exec_rows], "context": context}
            except Exception as e:
                analysis_trace["execution"] = exec_rows
                context["analysis_trace"] = analysis_trace
                err = str(e)
                logger.warning(f"Agentic模式失败，降级到rule模式继续处理: {err}")
                analysis_trace["agentic_fallback"] = {
                    "to_mode": "rule",
                    "reason": err,
                    "partial_execution_count": len(exec_rows),
                }
                analysis_trace["mode"] = "rule"
                context["analysis_trace"] = analysis_trace
                context["agentic_error"] = err
                mode = "rule"

        # 3. 获取相关历史
        relevant_history = self.memory.get_relevant_history(question)
        if os.getenv("AGENT_MEMORY_DEBUG", "0") == "1":
            used = []
            for h in (relevant_history or [])[:5]:
                used.append({
                    "role": h.get("role"),
                    "from_memory": bool(h.get("from_memory")),
                    "kind": h.get("kind"),
                    "tags": h.get("tags") or [],
                    "content": (h.get("content") or "")[:160],
                })
            context["memory_debug"] = {
                "short_term_size": len(self.memory.short_term or []),
                "long_term_size": len(self.memory.long_term or []),
                "used": used,
            }

        # 4. 获取相关知识
        knowledge_context = self.knowledge_base.get_knowledge_context(question)

        # 5. 规划任务
        plan = self.task_planner.plan(question, context)
        if progress_cb:
            try:
                progress_cb(
                    {
                        "event": "planned",
                        "total_steps": len(plan or []),
                        "tools": [s.get("tool") for s in (plan or []) if isinstance(s, dict)],
                    }
                )
            except Exception:
                pass
        analysis_trace["plan"] = [
            {
                "step": int(s.get("step") or 0),
                "tool": s.get("tool"),
                "description": s.get("description"),
                "params": dict(s.get("params") or {}),
            }
            for s in (plan or [])
        ]

        # 6. 执行计划
        execution_results = self.task_planner.execute_plan(plan, prepared_data, context=context, progress_cb=progress_cb)
        analysis_trace["execution"] = [r.get("trace") for r in (execution_results or []) if isinstance(r, dict) and r.get("trace")]
        context["analysis_trace"] = analysis_trace

        # 7. 生成综合答案
        if progress_cb:
            try:
                progress_cb({"event": "synthesize"})
            except Exception:
                pass
        answer = self._generate_answer(
            question=question,
            context=context,
            execution_results=execution_results,
            knowledge_context=knowledge_context,
            relevant_history=relevant_history
        )
        try:
            ctx_obj = answer.get("context") if isinstance(answer, dict) else None
            if isinstance(ctx_obj, dict):
                ctx_obj["analysis_trace"] = analysis_trace
        except Exception:
            pass

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

        semantic_from_context = str((context or {}).get("semantic_context") or "").strip()
        semantic_already_in_steps = any((r or {}).get("tool") == "consult_semantic_catalog" for r in (execution_results or []))
        if semantic_from_context and (not semantic_already_in_steps):
            preview = semantic_from_context if len(semantic_from_context) <= 1600 else (semantic_from_context[:1600] + "\n...(已截断)")
            answer_parts.append("\n**语义目录（口径/字段/误用风险）**\n")
            answer_parts.append(preview + "\n")

        # 2. 工具执行结果
        for result in execution_results:
            tool_output = result.get('result') or {}
            if tool_output.get('success'):
                answer_parts.append(f"\n**{result['description']}**\n")

                tool_result = tool_output.get('result') or {}

                if result.get('tool') == 'consult_semantic_catalog':
                    semantic_text = (tool_result.get('semantic_context') or '').strip()
                    if semantic_text:
                        preview = semantic_text if len(semantic_text) <= 1600 else (semantic_text[:1600] + "\n...(已截断)")
                        answer_parts.append(preview + "\n")

                if result.get('tool') == 'search_similar_issues':
                    candidates = tool_result.get('candidates') or []
                    if candidates:
                        answer_parts.append("相似问题候选（Top）：\n")
                        for c in candidates[:8]:
                            tid = c.get("ticket_id") or ""
                            score = c.get("score_1_10")
                            proj = c.get("project") or ""
                            name = c.get("name") or ""
                            snippet = (c.get("snippet") or "").strip()
                            line = f"- {tid} | score={score} | {proj} | {name}".strip()
                            answer_parts.append(line + "\n")
                            if snippet:
                                answer_parts.append(f"  - {snippet[:160]}\n")

                if result.get('tool') in {'query_sqlite_with_fix', 'run_sqlite_query'}:
                    cols = tool_result.get("columns") or []
                    rows = tool_result.get("rows") or []
                    sql_used = tool_result.get("sql") or tool_result.get("generated_sql") or ""
                    if sql_used:
                        answer_parts.append(f"- SQL: {sql_used}\n")
                    if cols:
                        answer_parts.append(f"- 字段: {', '.join([str(c) for c in cols[:30]])}\n")
                    if rows:
                        answer_parts.append(f"- 返回行数: {tool_result.get('row_count', len(rows))}\n")
                        for r in rows[:8]:
                            if isinstance(r, dict):
                                brief = ", ".join(f"{k}={r.get(k)}" for k in list(r.keys())[:6])
                                answer_parts.append(f"  - {brief}\n")

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

                if result.get('tool') == 'analyze_trend':
                    trend_rows = tool_result.get('trend_data') or []
                    desc = result.get('description') or ''
                    if trend_rows and any(k in desc for k in ['Top 分布', '按 FV', '按 AIDA', '按 Solution Cluster', '按项目', '按项目', '按严重', '按类别', '按状态', '按PU', '按tester']):
                        answer_parts.append("Top 分布：\n")
                        for r in trend_rows[:10]:
                            answer_parts.append(f"- {r.get('group')}: {r.get('value')}\n")

                if result.get('tool') == 'defect_explore_kpis':
                    k = tool_result
                    if isinstance(k, dict):
                        answer_parts.append(f"- 总缺陷数: {k.get('total_defects', 0)}\n")
                        answer_parts.append(f"- 严重缺陷率: {k.get('severe_rate', 0)}%\n")
                        answer_parts.append(f"- 活跃测试人员: {k.get('total_testers', 0)}\n")
                        if k.get('daily_avg', 0):
                            answer_parts.append(f"- 日均缺陷: {k.get('daily_avg')}\n")
                        if k.get('top_tester'):
                            answer_parts.append(f"- 最活跃 tester: {k.get('top_tester')}\n")

                if result.get('tool') == 'defect_explore_dashboard':
                    charts = (tool_result.get("charts") or []) if isinstance(tool_result, dict) else []
                    if not charts:
                        answer_parts.append("- 未匹配到可计算的看板图表（可能缺少字段或数据为空）\n")
                    for chart in charts:
                        cid = chart.get("id")
                        title = chart.get("title") or cid
                        cdata = chart.get("data")
                        answer_parts.append(f"\n- {title} ({cid})\n")
                        if isinstance(cdata, dict) and all(k in cdata for k in ["total_defects", "severe_rate", "total_testers"]):
                            answer_parts.append(f"  - 总缺陷数: {cdata.get('total_defects', 0)}\n")
                            answer_parts.append(f"  - 严重缺陷率: {cdata.get('severe_rate', 0)}%\n")
                            answer_parts.append(f"  - 活跃测试人员: {cdata.get('total_testers', 0)}\n")
                            if cdata.get("top_tester"):
                                answer_parts.append(f"  - 最活跃 tester: {cdata.get('top_tester')}\n")
                        elif isinstance(cdata, list):
                            for item in cdata[:10]:
                                if isinstance(item, dict):
                                    if "group" in item and "total" in item and "stacks" in item:
                                        answer_parts.append(f"  - {item.get('group')}: {item.get('total')}\n")
                                        stacks = item.get("stacks") or []
                                        if stacks:
                                            brief = ", ".join([f"{s.get('key')}:{s.get('count')}" for s in stacks[:5] if isinstance(s, dict)])
                                            if brief:
                                                answer_parts.append(f"    - {brief}\n")
                                    elif "key" in item and "count" in item:
                                        ratio = item.get("ratio")
                                        if ratio is None:
                                            answer_parts.append(f"  - {item.get('key')}: {item.get('count')}\n")
                                        else:
                                            answer_parts.append(f"  - {item.get('key')}: {item.get('count')} ({ratio}%)\n")
                                    elif "key" in item and "severe_rate" in item:
                                        answer_parts.append(
                                            f"  - {item.get('key')}: 严重率 {item.get('severe_rate')}% (总{item.get('total')}, 严重{item.get('severe')})\n"
                                        )
                                    elif "transition" in item and "avg_hours" in item:
                                        answer_parts.append(
                                            f"  - {item.get('transition')}: 平均 {item.get('avg_hours')}h, 总 {item.get('total_hours')}h, 次数 {item.get('count')}\n"
                                        )
                                    elif "word" in item and "count" in item:
                                        answer_parts.append(f"  - {item.get('word')}: {item.get('count')} ({item.get('ratio', 0)}%)\n")
                        elif isinstance(cdata, dict) and "stats" in cdata and "recent_weeks" in cdata:
                            stats = cdata.get("stats") or {}
                            answer_parts.append(
                                f"  - 总Inflow: {stats.get('total_inflow', 0)}, 总Outflow: {stats.get('total_outflow', 0)}, "
                                f"净积压: {stats.get('net_accumulation', 0)}, 收敛率: {stats.get('convergence_rate', 0)}%\n"
                            )
                        elif isinstance(cdata, dict) and "series" in cdata:
                            answer_parts.append("  - 时间序列已生成（略）\n")

                if result.get('tool') == 'groupby_aggregate' and isinstance(tool_result, dict):
                    rows = tool_result.get('rows') or []
                    group_by = tool_result.get('group_by') or []
                    if rows:
                        label = " / ".join(group_by) if isinstance(group_by, list) else str(group_by)
                        answer_parts.append(f"- 分组维度: {label}\n")
                        top_rows = rows[:20]
                        if 'failure_rate' in top_rows[0]:
                            answer_parts.append("失败率Top：\n")
                            for r in top_rows:
                                key = " / ".join([str(r.get(c)) for c in group_by]) if isinstance(group_by, list) and group_by else str(r.get('group') or r.get(label) or '')
                                answer_parts.append(
                                    f"- {key}: 失败率 {r.get('failure_rate')}% (失败 {r.get('failure', 0)} / 总计 {r.get('total', 0)})\n"
                                )
                        else:
                            answer_parts.append("Top 分布：\n")
                            sort_by = (tool_result.get('summary') or {}).get('sort_by')
                            for r in top_rows:
                                key = " / ".join([str(r.get(c)) for c in group_by]) if isinstance(group_by, list) and group_by else str(r.get('group') or '')
                                answer_parts.append(f"- {key}: {r.get(sort_by) if sort_by in r else r}\n")

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
                    all_rows = tool_result.get('rows', []) or []
                    overall_total = int(summary.get('overall_total') or 0)
                    ql = (question or '').lower()
                    min_total = 20 if overall_total >= 1000 else 5
                    if any(k in ql for k in ['经常', '稳定', '反复', '高频']):
                        min_total = max(min_total, 30 if overall_total >= 1000 else 8)
                    rows_with_min = [r for r in all_rows if int(r.get('total') or 0) >= min_total]
                    top_source = rows_with_min if rows_with_min else all_rows
                    top_rows = sorted(top_source, key=lambda r: (r.get('failure_rate', 0), r.get('total', 0)), reverse=True)[:5]
                    if top_rows:
                        answer_parts.append("失败率Top 5：\n")
                        for r in top_rows:
                            answer_parts.append(
                                f"- {r.get('group')}: 失败率 {r.get('failure_rate')}% (总计 {r.get('total')})\n"
                            )
                            status_keys = [k for k in r.keys() if k not in {"group", "total", "failure_rate"}]
                            numeric_status = []
                            for k in status_keys:
                                v = r.get(k)
                                if isinstance(v, (int, float)) and v:
                                    numeric_status.append((k, int(v)))
                            numeric_status = sorted(numeric_status, key=lambda x: x[1], reverse=True)[:4]
                            if numeric_status:
                                brief = ", ".join([f"{k}:{v}" for k, v in numeric_status])
                                answer_parts.append(f"  - 状态分布: {brief}\n")

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

        if 'strategy' in (context.get('intents') or []):
            overall_failure_rate = None
            top_failure_weeks: List[Dict[str, Any]] = []
            severe_rate = None
            top_risk_projects: List[Dict[str, Any]] = []
            top_matrices: List[Dict[str, Any]] = []
            topissue_total = None
            longrunner_total = None

            for r in execution_results:
                out = r.get('result') or {}
                if not out.get('success'):
                    continue
                tool = r.get('tool')
                res = out.get('result') or {}

                if tool == 'analyze_test_run' and isinstance(res, dict):
                    summary = res.get('summary') or {}
                    if overall_failure_rate is None:
                        overall_failure_rate = summary.get('overall_failure_rate')
                    rows = res.get('rows') or []
                    if rows and (not top_failure_weeks) and any(k in (r.get('description') or '') for k in ['按周', 'week']):
                        top_failure_weeks = sorted(rows, key=lambda x: x.get('failure_rate', 0), reverse=True)[:3]

                if tool == 'defect_explore_kpis' and isinstance(res, dict):
                    if severe_rate is None:
                        severe_rate = res.get('severe_rate')

                if tool == 'analyze_risk' and isinstance(res, dict):
                    items = res.get('risk_items') or []
                    if items and not top_risk_projects:
                        top_risk_projects = items[:5]

                if tool == 'analyze_matrix_aida_hotspots' and isinstance(res, dict):
                    matrices = res.get('matrices') or []
                    if matrices and not top_matrices:
                        top_matrices = matrices[:3]

                if tool == 'analyze_topissue_hotlist' and isinstance(res, dict):
                    if topissue_total is None:
                        topissue_total = res.get('total')

                if tool == 'analyze_longrunner_hotlist' and isinstance(res, dict):
                    if longrunner_total is None:
                        longrunner_total = res.get('total')

            answer_parts.append("\n**测试策略建议（基于上述统计）**\n")
            if overall_failure_rate is not None:
                answer_parts.append(f"- 测试侧现状：总体失败率 {overall_failure_rate}%（以此作为回归稳定性基线）\n")
                if top_failure_weeks:
                    wk = top_failure_weeks[0]
                    answer_parts.append(f"- 优先攻坚：失败率Top 周为 {wk.get('group')}（{wk.get('failure_rate')}%，总计 {wk.get('total')}）\n")
                    answer_parts.append("- 动作：回溯该周的环境/数据/版本/用例变更，建立“波峰周专项回归包”，将波峰周常见失败固化为准入门槛\n")
            if severe_rate is not None:
                answer_parts.append(f"- 缺陷侧现状：严重缺陷率 {severe_rate}%（用来定义发布门槛与P0范围）\n")
            if top_risk_projects:
                best = top_risk_projects[0]
                answer_parts.append(f"- 风险聚焦：最高风险项目为 {best.get('name')}（风险评分 {best.get('risk_score')}，缺陷数 {best.get('defect_count')}）\n")
                answer_parts.append("- 动作：对该项目建立“必测清单”（核心路径E2E + 关键接口/异常恢复），并优先分配自动化资源\n")
            if top_matrices:
                m0 = top_matrices[0]
                answer_parts.append(f"- 热点定位：矩阵 {m0.get('matrix')} 占比 {m0.get('matrix_share')}%（{m0.get('matrix_total')} 条）\n")
                top_aidas = (m0.get('top_aidas') or [])[:2]
                if top_aidas:
                    a0 = top_aidas[0]
                    answer_parts.append(f"- 热点AIDA：{a0.get('aida')}（{a0.get('count')} 条，占该矩阵 {a0.get('ratio_in_matrix')}%）\n")
                answer_parts.append("- 动作：以“矩阵×AIDA”作为用例优先级，优先补齐热点场景的边界/并发/恢复类用例\n")
            if topissue_total is not None or longrunner_total is not None:
                if topissue_total is not None:
                    answer_parts.append(f"- 缺陷治理：TopIssue 总数 {topissue_total}\n")
                if longrunner_total is not None:
                    answer_parts.append(f"- 积压治理：LongRunner 总数 {longrunner_total}\n")
                answer_parts.append("- 动作：把 TopIssue 作为“回归不放过”的红线；把 LongRunner 作为“流程卡点”治理，明确阻塞原因与处置策略\n")

            answer_parts.append("- 度量闭环：每周追踪 总体失败率/失败率Top周、严重缺陷率、TopIssue 与 LongRunner 数 的变化，并用回归门槛和准入规则固化\n")

        if 'case' in (context.get('intents') or []) and any(k in (question or '').lower() for k in ['case', '用例', 'testcase', 'test case']):
            case_top: List[Dict[str, Any]] = []
            case_group_cols: List[str] = []
            for r in execution_results:
                if r.get('tool') != 'groupby_aggregate':
                    continue
                out = r.get('result') or {}
                if not out.get('success'):
                    continue
                res = out.get('result') or {}
                rows = res.get('rows') or []
                if rows and 'failure_rate' in rows[0]:
                    case_top = rows[:10]
                    gb = res.get('group_by') or []
                    case_group_cols = gb if isinstance(gb, list) else [str(gb)]
                    break

            if case_top:
                answer_parts.append("\n**结论与建议（按用例失败率）**\n")
                top1 = case_top[0]
                label = " / ".join([str(top1.get(c)) for c in case_group_cols]) if case_group_cols else str(top1.get('group') or '')
                answer_parts.append(f"- 最容易出错用例: {label}（失败率 {top1.get('failure_rate')}%，失败 {top1.get('failure')} / 总计 {top1.get('total')}）\n")
                answer_parts.append("- 落地做法：把 Top 用例纳入“准入回归包”，并对 Top 用例补齐稳定性/重试/环境依赖的诊断信息（日志、前置条件、数据集）\n")
                answer_parts.append("- 排查顺序：先区分环境不稳定（同用例跨项目/跨周波动）与真实功能缺陷（同用例持续高失败率）\n")
                answer_parts.append("- 进一步增强：如果 tests 数据里有 project/FV/AIDA，可对 Top 用例再做 project×case 或 FV×case 交叉，定位失败集中区域\n")

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

        answer_text = ''.join(answer_parts)
        if os.getenv("AGENT_CRITIC_ENABLED") == "1":
            try:
                from agent.evaluation.agent_critic import CriticPipeline, RuleBasedCritic

                validation_enabled = os.getenv("AGENT_VALIDATION_ENABLED", "0") == "1"
                datasets_meta = (context or {}).get("datasets") or {}
                primary = (context or {}).get("primary_dataset") or ("defects" if "defects" in datasets_meta else next(iter(datasets_meta.keys()), None))
                primary_meta = datasets_meta.get(primary) if primary else None
                tool_size = (primary_meta or {}).get("tool_size") if isinstance(primary_meta, dict) else None
                has_success = any(isinstance((r or {}).get("result"), dict) and (r["result"].get("success") is True) for r in (execution_results or []))
                has_failure = any(isinstance((r or {}).get("result"), dict) and (r["result"].get("success") is False) for r in (execution_results or []))
                if validation_enabled and ((tool_size == 0) or (has_failure and not has_success)):
                    context["refusal"] = {
                        "should_refuse": True,
                        "reason": "数据不足或关键工具执行失败，无法给出可靠结论",
                    }

                pipeline = CriticPipeline([RuleBasedCritic()])
                critic_results = pipeline.run(
                    question=question,
                    context=context,
                    execution_results=execution_results,
                    draft_text=answer_text,
                )
                refusal = next((r for r in critic_results if getattr(r, "should_refuse", False)), None)
                critic_block = CriticPipeline.render(critic_results)
                if not critic_block:
                    critic_block = "\n**校验与质疑**\n- [info] 未发现明显风险提示缺失或工具异常。\n"
                if refusal is not None:
                    reason = getattr(refusal, "refusal_reason", "") or "数据不足"
                    answer_text = f"抱歉，当前无法给出可靠结论：{reason}\n" + critic_block
                    try:
                        trace = (context or {}).get("analysis_trace")
                        if isinstance(trace, dict):
                            trace["refused"] = True
                            trace["refusal_reason"] = str(reason)
                    except Exception:
                        pass
                else:
                    answer_text = answer_text + critic_block
            except Exception as e:
                answer_text = answer_text + f"\n**校验与质疑**\n- [warning] 校验流程执行失败：{e}\n"

        return {
            'text': answer_text,
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
        """获取增强的系统提示词 - 使用新的统一模板"""
        try:
            from prompt_templates import get_system_prompt
            return get_system_prompt(self.dashboard_type, data_context)
        except ImportError:
            # 降级处理：如果 prompt_templates 不存在，使用简化版
            logger.warning("prompt_templates 未找到，使用简化版 system prompt")
            base_prompt = f"""你是 BMW DTSV 数据分析助手。"""
            if data_context:
                base_prompt += f"\n\n数据上下文:\n{data_context}"
            return base_prompt

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


def create_agent(dashboard_type: str = 'general', llm: Any = None, db_path: Optional[str] = None) -> IntelligentAgent:
    """创建智能 Agent 实例"""
    return IntelligentAgent(dashboard_type, llm=llm, db_path=db_path)


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
    'ToolExecutor',
    'IntelligentContextManager',
    'ConversationMemory',
    'KnowledgeBase',
    'TaskPlanner'
]


# ============================================================================
# 测试代码
# ============================================================================

if __name__ == "__main__":
    print("智能 Agent 系统")
    print("=" * 50)

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

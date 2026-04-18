"""
Data Profiler — 数据自动画像

数据加载时自动分析数据特征，生成"数据理解"注入到 Agent context。

产出：
- 基础形状（行/列/数据类型）
- 时间范围
- 分类字段分布（top values）
- 数值字段统计（mean/std/min/max/null）
- 高基数/低基数识别
- 空值率报告
- 字段间相关性（分类 + 数值）
- 自动异常标注（"classification 空值率35%，结论可信度受限"）
- 业务维度识别（自动检测 project/severity/matrix/status 等业务字段）

用法：
    from agent.core.data_profiler import DataProfiler

    profiler = DataProfiler()
    profile = profiler.profile(df, dataset_name="defects")
    summary = profiler.generate_summary(profile)  # 文本摘要，可注入 prompt
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 业务字段识别规则
_BUSINESS_FIELD_PATTERNS = {
    "project": ["project", "tproject", "项目"],
    "severity": ["severity", "severity_group", "problem_severity", "严重"],
    "status": ["status", "status_phase", "状态"],
    "ecu": ["ecu", "assigned_ecu", "target_ecu"],
    "matrix": ["matrix"],
    "classification": ["classification"],
    "tester": ["tester", "detected_by", "found_by"],
    "time": ["creation_time", "tcreationtime", "created", "datetime", "date"],
    "defect_id": ["id", "defect_id", "work_item_id", "ticket_id"],
    "title": ["title", "name", "subject"],
    "release": ["release", "detected_in_release"],
    "fv": ["fv", "feature_version"],
    "pu": ["pu", "planned_update"],
    "domain": ["domain", "aida"],
}


@dataclass
class ColumnProfile:
    """单个列的画像。"""
    name: str
    dtype: str
    count: int
    null_count: int
    null_rate: float
    unique_count: int
    is_numeric: bool
    is_datetime: bool
    is_boolean: bool
    is_high_cardinality: bool  # unique > 50% of count
    top_values: Optional[List[Tuple[str, int]]] = None  # (value, count)
    numeric_stats: Optional[Dict[str, float]] = None  # mean, std, min, max, p50, p90
    business_role: Optional[str] = None  # 自动识别的业务角色


@dataclass
class DataProfile:
    """完整数据画像。"""
    dataset_name: str
    shape: Tuple[int, int]
    columns: Dict[str, ColumnProfile] = field(default_factory=dict)
    time_range: Optional[Tuple[str, str]] = None
    business_dimensions: Dict[str, str] = field(default_factory=dict)  # role -> col_name
    anomalies: List[str] = field(default_factory=list)
    correlations: List[Dict[str, Any]] = field(default_factory=list)
    key_insights: List[str] = field(default_factory=list)
    # 语义增强：来自 SchemaGraph 的业务语义标注
    semantic_annotations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    semantic_relationships: List[Dict[str, Any]] = field(default_factory=list)
    semantic_state_machines: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class DataProfiler:
    """数据自动画像引擎。"""

    def __init__(self, max_top_values: int = 10, correlation_threshold: float = 0.3):
        self._max_top_values = max_top_values
        self._corr_threshold = correlation_threshold

    def profile(self, df: pd.DataFrame, dataset_name: str = "data") -> DataProfile:
        """对 DataFrame 执行完整画像。"""
        p = DataProfile(
            dataset_name=dataset_name,
            shape=(len(df), len(df.columns)),
        )

        # 1. 列画像
        for col in df.columns:
            try:
                p.columns[col] = self._profile_column(df, col)
            except Exception as e:
                logger.debug(f"Column profile failed for {col}: {e}")

        # 2. 时间范围
        p.time_range = self._detect_time_range(df, p.columns)

        # 3. 业务维度识别
        p.business_dimensions = self._detect_business_dimensions(df.columns)

        # 4. 异常检测
        p.anomalies = self._detect_anomalies(df, p.columns)

        # 5. 相关性分析（采样，大数据集加速）
        p.correlations = self._detect_correlations(df, p.columns)

        # 6. 关键洞察
        p.key_insights = self._generate_insights(df, p)

        return p

    def generate_summary(self, profile: DataProfile, max_length: int = 2000) -> str:
        """生成文本摘要，可直接注入 prompt。"""
        parts: List[str] = []

        # 基础信息
        rows, cols = profile.shape
        parts.append(f"数据集 {profile.dataset_name}: {rows} 行 × {cols} 列")

        # 时间范围
        if profile.time_range:
            parts.append(f"时间范围: {profile.time_range[0]} ~ {profile.time_range[1]}")

        # 业务维度概览
        if profile.business_dimensions:
            dim_parts = []
            for role, col_name in profile.business_dimensions.items():
                col_p = profile.columns.get(col_name)
                if col_p and col_p.top_values:
                    top3 = [f"{v}({c})" for v, c in col_p.top_values[:3]]
                    dim_parts.append(f"  {role}({col_name}): {', '.join(top3)}")
                else:
                    dim_parts.append(f"  {role}({col_name})")
            parts.append("业务维度:\n" + "\n".join(dim_parts))

        # 数据质量问题
        if profile.anomalies:
            parts.append("数据质量:\n" + "\n".join(f"  ⚠️ {a}" for a in profile.anomalies[:5]))

        # 关键洞察
        if profile.key_insights:
            parts.append("关键特征:\n" + "\n".join(f"  • {i}" for i in profile.key_insights[:5]))

        # 显著相关
        strong_corrs = [c for c in profile.correlations if abs(c.get("strength", 0)) >= 0.5]
        if strong_corrs:
            corr_strs = [f"  {c['col1']} ↔ {c['col2']}: {c['strength']:.2f}" for c in strong_corrs[:5]]
            parts.append("显著相关:\n" + "\n".join(corr_strs))

        # 语义增强：业务语义标注
        if profile.semantic_annotations:
            sem_parts = []
            for col_name, sem in profile.semantic_annotations.items():
                meaning = sem.get("meaning", "")
                if meaning:
                    sem_parts.append(f"  {col_name}: {meaning}")
                warning = sem.get("data_quality_warning", "")
                if warning:
                    sem_parts.append(f"    ⚠️ {warning}")
            if sem_parts:
                parts.append("业务语义:\n" + "\n".join(sem_parts[:15]))

        # 语义增强：状态机概览
        if profile.semantic_state_machines:
            sm_parts = []
            for col_name, sm in profile.semantic_state_machines.items():
                states = [s["name"] for s in sm.get("states", [])]
                sm_parts.append(f"  {col_name}: {' → '.join(states)}")
                for gk, gv in sm.get("category_groups", {}).items():
                    sm_parts.append(f"    {gv.get('label', gk)}: {', '.join(gv.get('states', []))}")
            if sm_parts:
                parts.append("状态机:\n" + "\n".join(sm_parts[:10]))

        # 语义增强：关系提醒
        if profile.semantic_relationships:
            seen_rels = set()
            rel_parts = []
            for r in profile.semantic_relationships:
                rid = r.get("id", "")
                if rid in seen_rels:
                    continue
                seen_rels.add(rid)
                rel_parts.append(f"  {r['source']} ↔ {r['target']}: {r.get('description', '')}")
            if rel_parts:
                parts.append("字段关系:\n" + "\n".join(rel_parts[:8]))

        summary = "\n\n".join(parts)
        if len(summary) > max_length:
            summary = summary[:max_length] + "\n...(已截断)"
        return summary

    def profile_to_dict(self, profile: DataProfile) -> Dict[str, Any]:
        """序列化为字典。"""
        result: Dict[str, Any] = {
            "dataset": profile.dataset_name,
            "shape": list(profile.shape),
            "time_range": list(profile.time_range) if profile.time_range else None,
            "business_dimensions": profile.business_dimensions,
            "anomalies": profile.anomalies,
            "correlations": profile.correlations,
            "key_insights": profile.key_insights,
            "semantic_annotations": profile.semantic_annotations,
            "semantic_relationships": profile.semantic_relationships,
            "semantic_state_machines": profile.semantic_state_machines,
            "columns": {},
        }
        for name, col in profile.columns.items():
            result["columns"][name] = {
                "dtype": col.dtype,
                "null_rate": round(col.null_rate, 3),
                "unique_count": col.unique_count,
                "is_numeric": col.is_numeric,
                "is_datetime": col.is_datetime,
                "is_high_cardinality": col.is_high_cardinality,
                "business_role": col.business_role,
                "top_values": col.top_values,
                "numeric_stats": col.numeric_stats,
            }
        return result

    def profile_with_semantics(self, df: pd.DataFrame, dataset_name: str = "data", schema_graph=None) -> DataProfile:
        """在 profile() 基础上融合 SchemaGraph 的业务语义。

        优先使用外部传入的 schema_graph 实例，避免重复加载 JSON。
        如果未传入或不可用，graceful fallback 到普通 profile。
        """
        p = self.profile(df, dataset_name=dataset_name)

        graph = schema_graph
        if graph is None:
            try:
                from semantic_catalog.schema_graph import SchemaGraph
                graph = SchemaGraph()
                if not graph.is_loaded:
                    return p
            except Exception as e:
                logger.debug(f"SchemaGraph unavailable, skip semantic enrichment: {e}")
                return p

        # 1. 字段语义标注（只存储必要字段，减少 profile 体积）
        for col_name, col_profile in p.columns.items():
            field_def = graph.get_field(col_name)
            if field_def:
                p.semantic_annotations[col_name] = {
                    "meaning": field_def.get("meaning", ""),
                    "data_quality_warning": field_def.get("data_quality_warning", ""),
                    "business_role": field_def.get("business_role", ""),
                }

        # 2. 关系标注：仅对已识别的业务维度补充关系（去重）
        _seen_rel_ids = set()
        for role, col_name in p.business_dimensions.items():
            rels = graph.get_relationships(col_name)
            if not rels:
                rels = graph.get_relationships(role)
            for rel in rels:
                rid = rel.get("id", "")
                if rid and rid not in _seen_rel_ids:
                    _seen_rel_ids.add(rid)
                    p.semantic_relationships.append(rel)

        # 3. 状态机标注
        for role, col_name in p.business_dimensions.items():
            sm = graph.get_state_machine(col_name)
            if sm:
                p.semantic_state_machines[col_name] = sm

        return p

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _profile_column(self, df: pd.DataFrame, col: str) -> ColumnProfile:
        series = df[col]
        count = len(series)
        null_count = int(series.isnull().sum())
        null_rate = null_count / max(count, 1)
        unique_count = int(series.nunique())
        dtype_str = str(series.dtype)

        is_numeric = pd.api.types.is_numeric_dtype(series)
        is_datetime = pd.api.types.is_datetime64_any_dtype(series)
        is_boolean = pd.api.types.is_bool_dtype(series) or set(series.dropna().unique()) <= {True, False, 0, 1, "0", "1"}
        is_high_cardinality = unique_count > count * 0.5

        # 业务角色识别
        business_role = self._identify_business_role(col)

        cp = ColumnProfile(
            name=col,
            dtype=dtype_str,
            count=count,
            null_count=null_count,
            null_rate=null_rate,
            unique_count=unique_count,
            is_numeric=is_numeric,
            is_datetime=is_datetime,
            is_boolean=is_boolean,
            is_high_cardinality=is_high_cardinality,
            business_role=business_role,
        )

        # 分类字段：top values
        if not is_numeric and not is_datetime:
            vc = series.value_counts().head(self._max_top_values)
            cp.top_values = [(str(v), int(c)) for v, c in vc.items()]

        # 数值字段：统计
        if is_numeric:
            clean = series.dropna()
            if len(clean) > 0:
                cp.numeric_stats = {
                    "mean": float(clean.mean()),
                    "std": float(clean.std()),
                    "min": float(clean.min()),
                    "max": float(clean.max()),
                    "p50": float(clean.quantile(0.5)),
                    "p90": float(clean.quantile(0.9)),
                    "p99": float(clean.quantile(0.99)),
                }

        return cp

    def _identify_business_role(self, col_name: str) -> Optional[str]:
        """根据列名识别业务角色。"""
        col_lower = col_name.lower().strip()
        for role, patterns in _BUSINESS_FIELD_PATTERNS.items():
            for pattern in patterns:
                if pattern in col_lower:
                    return role
        return None

    def _detect_time_range(self, df: pd.DataFrame, columns: Dict[str, ColumnProfile]) -> Optional[Tuple[str, str]]:
        """检测时间范围。"""
        for col_name, cp in columns.items():
            if cp.is_datetime:
                series = df[col_name].dropna()
                if len(series) > 0:
                    return (str(series.min()), str(series.max()))
            # 尝试检测时间字符串列
            if cp.business_role == "time" and not cp.is_datetime:
                try:
                    series = pd.to_datetime(df[col_name], errors="coerce").dropna()
                    if len(series) > 0:
                        return (str(series.min()), str(series.max()))
                except Exception:
                    pass
        return None

    def _detect_business_dimensions(self, col_names) -> Dict[str, str]:
        """自动识别业务维度字段。"""
        dims = {}
        for col in col_names:
            role = self._identify_business_role(col)
            if role and role not in dims:
                dims[role] = col
        return dims

    def _detect_anomalies(self, df: pd.DataFrame, columns: Dict[str, ColumnProfile]) -> List[str]:
        """检测数据质量异常。"""
        anomalies = []

        for col_name, cp in columns.items():
            # 高空值率
            if cp.null_rate > 0.3:
                anomalies.append(f"{col_name} 空值率 {cp.null_rate:.0%}，相关分析结论可信度受限")
            elif cp.null_rate > 0.1:
                anomalies.append(f"{col_name} 空值率 {cp.null_rate:.0%}")

            # 高基数分类字段
            if not cp.is_numeric and not cp.is_datetime and cp.is_high_cardinality and cp.unique_count > 100:
                anomalies.append(f"{col_name} 有 {cp.unique_count} 个唯一值，不适合直接 GROUP BY，建议取 TOP N")

            # 数值字段异常分布
            if cp.is_numeric and cp.numeric_stats:
                stats = cp.numeric_stats
                if stats["std"] == 0:
                    anomalies.append(f"{col_name} 全部为相同值 ({stats['mean']})，无分析价值")
                elif stats["max"] > stats["p99"] * 10 and stats["p99"] > 0:
                    anomalies.append(f"{col_name} 有极端值 (max={stats['max']:.0f}, p99={stats['p99']:.0f})，注意离群值影响")

        return anomalies

    def _detect_correlations(self, df: pd.DataFrame, columns: Dict[str, ColumnProfile]) -> List[Dict[str, Any]]:
        """检测字段间相关性。"""
        corrs = []

        # 采样加速
        sample = df
        if len(df) > 10000:
            sample = df.sample(n=10000, random_state=42)

        # 数值相关性
        numeric_cols = [c for c, cp in columns.items() if cp.is_numeric and cp.null_rate < 0.3]
        if len(numeric_cols) >= 2:
            try:
                corr_matrix = sample[numeric_cols].corr()
                for i, c1 in enumerate(numeric_cols):
                    for c2 in numeric_cols[i + 1:]:
                        val = corr_matrix.loc[c1, c2]
                        if abs(val) >= self._corr_threshold:
                            corrs.append({
                                "col1": c1, "col2": c2,
                                "strength": round(float(val), 3),
                                "type": "numeric",
                            })
            except Exception:
                pass

        # 分类相关性（Cramér's V，限制列数避免太慢）
        cat_cols = [c for c, cp in columns.items()
                    if not cp.is_numeric and not cp.is_datetime
                    and not cp.is_high_cardinality and cp.null_rate < 0.3
                    and cp.unique_count <= 20]
        if len(cat_cols) >= 2 and len(cat_cols) <= 10:
            try:
                for i, c1 in enumerate(cat_cols):
                    for c2 in cat_cols[i + 1:]:
                        v = self._cramers_v(sample[c1], sample[c2])
                        if v >= self._corr_threshold:
                            corrs.append({
                                "col1": c1, "col2": c2,
                                "strength": round(float(v), 3),
                                "type": "categorical",
                            })
            except Exception:
                pass

        # 按强度排序
        corrs.sort(key=lambda x: abs(x["strength"]), reverse=True)
        return corrs[:20]

    @staticmethod
    def _cramers_v(x: pd.Series, y: pd.Series) -> float:
        """计算 Cramér's V（分类变量相关性）。"""
        try:
            contingency = pd.crosstab(x, y)
            chi2 = contingency.values.flatten()
            n = len(x.dropna())
            if n == 0:
                return 0.0
            from scipy.stats import chi2_contingency
            chi2_stat, _, _, _ = chi2_contingency(contingency)
            min_dim = min(contingency.shape) - 1
            if min_dim == 0:
                return 0.0
            return float(np.sqrt(chi2_stat / (n * min_dim)))
        except Exception:
            return 0.0

    def _generate_insights(self, df: pd.DataFrame, profile: DataProfile) -> List[str]:
        """基于画像自动生成关键洞察。"""
        insights = []
        rows = profile.shape[0]

        # 数据量洞察
        if rows > 100000:
            insights.append(f"大数据集({rows}行)，建议使用采样或过滤缩小范围")
        elif rows < 100:
            insights.append(f"数据量较少({rows}行)，统计结论可能不够稳健")

        # 业务维度分布洞察
        for role, col_name in profile.business_dimensions.items():
            cp = profile.columns.get(col_name)
            if not cp or not cp.top_values:
                continue

            top_val, top_count = cp.top_values[0]
            top_pct = top_count / max(rows, 1)

            if role == "project" and top_pct > 0.5:
                insights.append(f"项目分布不均：{top_val} 占 {top_pct:.0%}，注意跨项目对比的样本量差异")
            elif role == "severity" and len(cp.top_values) >= 2:
                crit = next((c for v, c in cp.top_values if "critical" in str(v).lower() or "严重" in str(v)), 0)
                if crit > 0:
                    crit_pct = crit / max(rows, 1)
                    insights.append(f"严重缺陷占比 {crit_pct:.1%} ({crit}条)")
            elif role == "status" and top_pct > 0.7:
                insights.append(f"状态分布集中：{top_val} 占 {top_pct:.0%}")

        # 时间洞察
        if profile.time_range:
            try:
                from datetime import datetime
                t1 = pd.to_datetime(profile.time_range[0])
                t2 = pd.to_datetime(profile.time_range[1])
                span_days = (t2 - t1).days
                if span_days > 0:
                    avg_per_day = rows / span_days
                    insights.append(f"时间跨度 {span_days} 天，日均 {avg_per_day:.0f} 条")
            except Exception:
                pass

        return insights

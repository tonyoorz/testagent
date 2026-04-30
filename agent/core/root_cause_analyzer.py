"""
根因分析引擎

基于缺陷数据的多维度根因分析，包括文本聚类（TF-IDF + cosine similarity）、
ECU关联分析、时间规律发现、版本关联分析等。

Features:
1. DefectClusterer - 缺陷文本聚类
2. RootCauseAnalyzer - 多维度根因分析
3. 集成 tool 接口，可注册到 agentic_runtime

Author: AI Assistant
Date: 2026-04-12
"""

import logging
import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class DefectCluster:
    """缺陷聚类结果"""
    cluster_id: str
    label: str               # 聚类标签（自动生成）
    defect_ids: List[str]    # 包含的缺陷ID列表
    keywords: List[str]      # 关键词列表
    size: int                # 聚类大小
    centroid_text: str = ""  # 代表性描述


@dataclass
class DimensionAnalysis:
    """单维度分析结果"""
    dimension: str           # 维度名
    findings: List[str]      # 发现列表
    data: Dict[str, Any]     # 原始数据摘要
    significance: str = "medium"  # high/medium/low


@dataclass
class RootCauseReport:
    """根因分析报告"""
    cluster_info: Optional[DefectCluster] = None
    dimension_analysis: List[DimensionAnalysis] = field(default_factory=list)
    hypothesis: str = ""
    recommended_actions: List[str] = field(default_factory=list)
    confidence: float = 0.0  # 0-1 置信度
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ---------------------------------------------------------------------------
# DefectClusterer - 缺陷文本聚类
# ---------------------------------------------------------------------------

class DefectClusterer:
    """
    基于 TF-IDF + cosine similarity 的缺陷文本聚类

    不依赖外部 embedding API，纯数学方法。
    使用简单的层次聚类（agglomerative）。
    """

    # 中文停用词
    _STOP_WORDS = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会",
        "着", "没有", "看", "好", "自己", "这", "他", "她", "它", "们",
        "问题", "发生", "出现", "发现", "时", "当", "中", "导致", "造成",
        "该", "此", "某", "些", "所有", "进行", "需要", "可能", "导致",
    }

    def __init__(self, similarity_threshold: float = 0.3, min_cluster_size: int = 2):
        """
        Args:
            similarity_threshold: 聚类相似度阈值（0-1），越低越宽松
            min_cluster_size: 最小聚类大小
        """
        self.similarity_threshold = similarity_threshold
        self.min_cluster_size = min_cluster_size

    def cluster(
        self,
        defects: List[Dict],
        text_field: str = "defect_description",
        id_field: str = "id",
    ) -> List[DefectCluster]:
        """
        对缺陷描述做文本聚类

        Args:
            defects: 缺陷列表，每个元素需包含 text_field 和 id_field
            text_field: 文本描述字段名
            id_field: ID字段名

        Returns:
            聚类结果列表
        """
        if not defects or len(defects) < self.min_cluster_size:
            return []

        # 1. 提取文本
        texts = []
        ids = []
        for d in defects:
            text = str(d.get(text_field, "")).strip()
            did = str(d.get(id_field, ""))
            if text and did:
                texts.append(text)
                ids.append(did)

        if len(texts) < self.min_cluster_size:
            return []

        # 2. 分词 + TF-IDF
        tokenized = [self._tokenize(t) for t in texts]
        tfidf_matrix, vocab = self._compute_tfidf(tokenized)

        if tfidf_matrix is None or len(vocab) == 0:
            return []

        # 3. 计算余弦相似度矩阵
        n = len(texts)
        sim_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                sim = self._cosine_similarity(tfidf_matrix[i], tfidf_matrix[j])
                sim_matrix[i][j] = sim
                sim_matrix[j][i] = sim

        # 4. 简单层次聚类（合并相似度超阈值的对）
        clusters = self._agglomerative_cluster(sim_matrix, ids, texts, tokenized)

        return clusters

    def _tokenize(self, text: str) -> List[str]:
        """简单分词：中文按字/词，英文按空格"""
        # 英文词
        en_words = re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())
        # 中文字（2-4字组合的简单 bigram/trigram）
        cn_chars = re.findall(r"[\u4e00-\u9fff]+", text)
        cn_words = []
        for segment in cn_chars:
            # 2-gram
            for i in range(len(segment) - 1):
                bigram = segment[i:i + 2]
                if bigram not in self._STOP_WORDS:
                    cn_words.append(bigram)
            # 3-gram
            for i in range(len(segment) - 2):
                trigram = segment[i:i + 3]
                cn_words.append(trigram)

        all_words = en_words + cn_words
        # 过滤停用词和过短的
        return [w for w in all_words if w not in self._STOP_WORDS and len(w) >= 2]

    def _compute_tfidf(
        self, tokenized: List[List[str]]
    ) -> Tuple[Optional[List[Dict[str, float]]], List[str]]:
        """计算 TF-IDF"""
        # 构建词汇表
        doc_freq: Counter = Counter()
        for tokens in tokenized:
            unique_tokens = set(tokens)
            for t in unique_tokens:
                doc_freq[t] += 1

        # 过滤低频词（只出现1次）和超高频词（>80%文档）
        n_docs = len(tokenized)
        vocab = [
            w for w, freq in doc_freq.items()
            if 1 < freq < n_docs * 0.8
        ]

        if not vocab:
            return None, []

        idf = {}
        for w in vocab:
            idf[w] = math.log(n_docs / (1 + doc_freq[w]))

        # 计算每个文档的 TF-IDF 向量
        tfidf_matrix = []
        for tokens in tokenized:
            tf = Counter(tokens)
            total = len(tokens) if tokens else 1
            vec = {}
            for w in vocab:
                if w in tf:
                    vec[w] = (tf[w] / total) * idf[w]
            tfidf_matrix.append(vec)

        return tfidf_matrix, vocab

    @staticmethod
    def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
        """计算两个稀疏向量的余弦相似度"""
        common_keys = set(vec_a.keys()) & set(vec_b.keys())
        if not common_keys:
            return 0.0

        dot = sum(vec_a[k] * vec_b[k] for k in common_keys)
        norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
        norm_b = math.sqrt(sum(v * v for v in vec_b.values()))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    def _agglomerative_cluster(
        self,
        sim_matrix: np.ndarray,
        ids: List[str],
        texts: List[str],
        tokenized: List[List[str]],
    ) -> List[DefectCluster]:
        """简单层次聚类"""
        n = len(ids)
        # 初始化：每个文档自成一簇
        cluster_map: Dict[int, List[int]] = {i: [i] for i in range(n)}

        # 不断合并最相似的对
        changed = True
        while changed:
            changed = False
            best_sim = self.similarity_threshold
            best_pair = None

            cluster_ids = list(cluster_map.keys())
            for ci_idx in range(len(cluster_ids)):
                for cj_idx in range(ci_idx + 1, len(cluster_ids)):
                    ci, cj = cluster_ids[ci_idx], cluster_ids[cj_idx]
                    # 计算簇间最大相似度（complete linkage）
                    max_sim = 0.0
                    for a in cluster_map[ci]:
                        for b in cluster_map[cj]:
                            max_sim = max(max_sim, sim_matrix[a][b])

                    if max_sim > best_sim:
                        best_sim = max_sim
                        best_pair = (ci, cj)

            if best_pair:
                ci, cj = best_pair
                cluster_map[ci].extend(cluster_map[cj])
                del cluster_map[cj]
                changed = True

        # 生成聚类结果
        result = []
        for idx, (cluster_id, members) in enumerate(cluster_map.items()):
            if len(members) < self.min_cluster_size:
                continue

            member_ids = [ids[m] for m in members]
            member_texts = [texts[m] for m in members]
            member_tokens = []
            for m in members:
                member_tokens.extend(tokenized[m])

            # 关键词 = 聚类内高频词
            word_freq = Counter(member_tokens)
            keywords = [w for w, _ in word_freq.most_common(5)]

            # 标签 = 前3个关键词拼接
            label = " / ".join(keywords[:3])

            # 代表性描述 = 中心文档（与所有成员平均相似度最高的）
            centroid_idx = members[0]
            centroid_text = member_texts[0] if member_texts else ""

            result.append(DefectCluster(
                cluster_id=f"cluster_{idx:03d}",
                label=label,
                defect_ids=member_ids,
                keywords=keywords,
                size=len(members),
                centroid_text=centroid_text,
            ))

        # 按大小降序
        result.sort(key=lambda c: c.size, reverse=True)
        return result


# ---------------------------------------------------------------------------
# RootCauseAnalyzer - 多维度根因分析
# ---------------------------------------------------------------------------

class RootCauseAnalyzer:
    """
    多维度根因分析器

    分析链条：
    1. 频次分析 → 缺陷出现频率趋势
    2. ECU关联 → 哪些ECU共同出现
    3. 时间规律 → 是否集中在特定时间段
    4. 版本关联 → 是否特定版本引入
    5. 状态分布 → 大多数处于什么状态
    """

    def __init__(self):
        self.clusterer = DefectClusterer()

    def analyze(
        self,
        defects: List[Dict],
        cluster: Optional[DefectCluster] = None,
        dimensions: Optional[List[str]] = None,
    ) -> RootCauseReport:
        """
        执行根因分析

        Args:
            defects: 缺陷数据列表
            cluster: 可选，指定分析某个聚类（不指定则自动聚类）
            dimensions: 分析维度列表，默认全部分析

        Returns:
            根因分析报告
        """
        if not defects:
            return RootCauseReport(hypothesis="无缺陷数据可供分析", confidence=0.0)

        # 自动聚类（如果未指定）
        if cluster is None:
            clusters = self.clusterer.cluster(defects)
            if clusters:
                cluster = clusters[0]  # 取最大的
            else:
                # 无法聚类，对全部数据做分析
                cluster = DefectCluster(
                    cluster_id="all",
                    label="全部缺陷",
                    defect_ids=[str(d.get("id", "")) for d in defects],
                    keywords=[],
                    size=len(defects),
                )

        # 过滤到目标缺陷
        if cluster.defect_ids:
            id_set = set(cluster.defect_ids)
            target_defects = [d for d in defects if str(d.get("id", "")) in id_set]
        else:
            target_defects = defects

        if not target_defects:
            target_defects = defects

        # 确定分析维度
        all_dimensions = ["frequency", "ecu_correlation", "time_pattern", "version_correlation", "status_distribution"]
        active_dims = dimensions or all_dimensions

        report = RootCauseReport(cluster_info=cluster)

        # 逐维度分析
        for dim in active_dims:
            analysis = self._analyze_dimension(dim, target_defects)
            if analysis:
                report.dimension_analysis.append(analysis)

        # 综合推理
        report.hypothesis = self._generate_hypothesis(report.dimension_analysis, cluster)
        report.recommended_actions = self._generate_actions(report.dimension_analysis)
        report.confidence = self._calculate_confidence(report.dimension_analysis)

        return report

    def _analyze_dimension(self, dim: str, defects: List[Dict]) -> Optional[DimensionAnalysis]:
        """分析单个维度"""
        if dim == "frequency":
            return self._analyze_frequency(defects)
        elif dim == "ecu_correlation":
            return self._analyze_ecu_correlation(defects)
        elif dim == "time_pattern":
            return self._analyze_time_pattern(defects)
        elif dim == "version_correlation":
            return self._analyze_version_correlation(defects)
        elif dim == "status_distribution":
            return self._analyze_status_distribution(defects)
        return None

    def _analyze_frequency(self, defects: List[Dict]) -> DimensionAnalysis:
        """频次分析"""
        # 按时间聚合
        date_counts: Counter = Counter()
        for d in defects:
            date = str(d.get("created_date", ""))[:7]  # YYYY-MM
            if date:
                date_counts[date] += 1

        findings = []
        data = {"monthly_counts": dict(date_counts), "total": len(defects)}

        if date_counts:
            sorted_dates = sorted(date_counts.items())
            if len(sorted_dates) >= 2:
                peak_month, peak_count = max(sorted_dates, key=lambda x: x[1])
                avg_count = sum(c for _, c in sorted_dates) / len(sorted_dates)
                findings.append(f"峰值月份: {peak_month}，共 {peak_count} 个缺陷")
                findings.append(f"月均缺陷数: {avg_count:.1f}")

                # 趋势判断
                if len(sorted_dates) >= 3:
                    recent_3 = sum(c for _, c in sorted_dates[-3:])
                    earlier_3 = sum(c for _, c in sorted_dates[:3])
                    if recent_3 > earlier_3 * 1.5:
                        findings.append("📈 趋势上升：近3期缺陷数显著高于早期")
                    elif recent_3 < earlier_3 * 0.5:
                        findings.append("📉 趋势下降：近3期缺陷数显著低于早期")

        significance = "high" if len(findings) >= 3 else "medium"
        return DimensionAnalysis(
            dimension="频次分析",
            findings=findings,
            data=data,
            significance=significance,
        )

    def _analyze_ecu_correlation(self, defects: List[Dict]) -> DimensionAnalysis:
        """ECU关联分析"""
        ecu_counts: Counter = Counter()
        ecu_pairs: Counter = Counter()

        for d in defects:
            ecu = str(d.get("target_ecu", ""))
            if ecu:
                ecu_counts[ecu] += 1

        # 共现分析：同一时间段内的ECU对
        time_ecus: Dict[str, Set[str]] = defaultdict(set)
        for d in defects:
            date = str(d.get("created_date", ""))[:7]
            ecu = str(d.get("target_ecu", ""))
            if date and ecu:
                time_ecus[date].add(ecu)

        for month, ecus in time_ecus.items():
            ecu_list = sorted(ecus)
            for i in range(len(ecu_list)):
                for j in range(i + 1, len(ecu_list)):
                    ecu_pairs[(ecu_list[i], ecu_list[j])] += 1

        findings = []
        data = {"ecu_distribution": dict(ecu_counts.most_common(10)),
                "co_occurrence": {f"{k[0]}↔{k[1]}": v for k, v in ecu_pairs.most_common(5)}}

        if ecu_counts:
            top_ecu, top_count = ecu_counts.most_common(1)[0]
            findings.append(f"最集中ECU: {top_ecu}，占 {top_count}/{len(defects)} ({top_count/len(defects)*100:.0f}%)")

            if len(ecu_counts) >= 2:
                findings.append(f"涉及 {len(ecu_counts)} 个ECU，可能存在跨ECU协调问题")

        if ecu_pairs:
            top_pair, pair_count = ecu_pairs.most_common(1)[0]
            if pair_count >= 2:
                findings.append(f"高频共现: {top_pair[0]} ↔ {top_pair[1]}（{pair_count}个月份同时出现）")

        significance = "high" if len(ecu_counts) >= 3 else "medium"
        return DimensionAnalysis(
            dimension="ECU关联",
            findings=findings,
            data=data,
            significance=significance,
        )

    def _analyze_time_pattern(self, defects: List[Dict]) -> DimensionAnalysis:
        """时间规律分析"""
        weekday_counts: Counter = Counter()
        hour_counts: Counter = Counter()

        for d in defects:
            date_str = str(d.get("created_date", ""))
            try:
                from datetime import datetime as dt
                dt_obj = dt.fromisoformat(date_str.replace("Z", "").replace("T", " ")[:19])
                weekday_counts[dt_obj.strftime("%A")] += 1
                hour_counts[dt_obj.hour] += 1
            except (ValueError, TypeError):
                pass

        findings = []
        data = {"weekday_distribution": dict(weekday_counts), "hour_distribution": dict(hour_counts)}

        if weekday_counts:
            peak_day, peak_count = weekday_counts.most_common(1)[0]
            total = sum(weekday_counts.values())
            if total > 0 and peak_count / total > 0.3:
                findings.append(f"星期模式: {peak_day}缺陷占比 {peak_count/total*100:.0f}%，"
                              f"可能存在\"{peak_day}效应\"")

        if hour_counts:
            peak_hour, peak_h_count = hour_counts.most_common(1)[0]
            findings.append(f"提交高峰: {peak_hour}:00，共 {peak_h_count} 个缺陷")

        if not findings:
            findings.append("未发现显著的时间规律模式")

        return DimensionAnalysis(
            dimension="时间规律",
            findings=findings,
            data=data,
            significance="low",
        )

    def _analyze_version_correlation(self, defects: List[Dict]) -> DimensionAnalysis:
        """版本关联分析"""
        version_counts: Counter = Counter()

        for d in defects:
            # 尝试多个可能的版本字段
            version = (str(d.get("software_version", ""))
                      or str(d.get("fv", ""))
                      or str(d.get("version", "")))
            if version and version != "None":
                version_counts[version] += 1

        findings = []
        data = {"version_distribution": dict(version_counts.most_common(10))}

        if version_counts:
            top_version, top_count = version_counts.most_common(1)[0]
            total = sum(version_counts.values())
            findings.append(f"最集中版本: {top_version}，占 {top_count}/{total} ({top_count/total*100:.0f}%)")

            if len(version_counts) == 1:
                findings.append(f"⚠️ 所有缺陷均出现在版本 {top_version}，强烈指向该版本引入")
            elif top_count / total > 0.7:
                findings.append(f"高度集中在版本 {top_version}，可能是回归问题")
        else:
            findings.append("缺少版本信息，无法进行版本关联分析")

        significance = "high" if version_counts and len(version_counts) <= 2 else "medium"
        return DimensionAnalysis(
            dimension="版本关联",
            findings=findings,
            data=data,
            significance=significance,
        )

    def _analyze_status_distribution(self, defects: List[Dict]) -> DimensionAnalysis:
        """状态分布分析"""
        status_counts: Counter = Counter()

        for d in defects:
            status = str(d.get("status", ""))
            if status:
                # 取前缀（去掉严重度后缀）
                status_prefix = status.split("_")[0] if "_" in status else status
                status_counts[status_prefix] += 1

        findings = []
        data = {"status_distribution": dict(status_counts)}

        total = sum(status_counts.values())
        if status_counts and total > 0:
            open_count = sum(c for s, c in status_counts.items()
                           if s in ("01", "02", "03", "04"))
            closed_count = sum(c for s, c in status_counts.items()
                             if s in ("06", "09", "10"))

            findings.append(f"开放/进行中: {open_count}，已关闭: {closed_count}")

            if open_count / total > 0.5:
                findings.append(f"⚠️ {open_count/total*100:.0f}% 缺陷仍未关闭，处理效率需关注")

            if "05" in status_counts:
                findings.append(f"延期(Deferred): {status_counts['05']} 个，需确认是否仍需处理")

        return DimensionAnalysis(
            dimension="状态分布",
            findings=findings,
            data=data,
            significance="medium",
        )

    def _generate_hypothesis(self, analyses: List[DimensionAnalysis], cluster: DefectCluster) -> str:
        """综合各维度分析，生成根因假设"""
        if not analyses:
            return "数据不足，无法生成根因假设。"

        parts = []
        high_dims = [a for a in analyses if a.significance == "high"]

        if high_dims:
            parts.append("高相关性维度：")
            for a in high_dims:
                parts.append(f"  - {a.dimension}: {'; '.join(a.findings[:2])}")

        # 综合推理
        dim_names = {a.dimension for a in analyses}

        if "ECU关联" in dim_names and "版本关联" in dim_names:
            ecu_analysis = next((a for a in analyses if a.dimension == "ECU关联"), None)
            ver_analysis = next((a for a in analyses if a.dimension == "版本关联"), None)
            if ecu_analysis and ver_analysis:
                parts.append("\n推断：该问题可能由特定版本的软件变更引发，影响多个关联ECU的交互逻辑。")

        if "频次分析" in dim_names:
            freq = next((a for a in analyses if a.dimension == "频次分析"), None)
            if freq and any("上升" in f for f in freq.findings):
                parts.append("趋势上升值得关注，建议排查近期变更。")

        if not parts:
            parts.append("基于现有数据的初步分析，建议结合业务上下文进一步排查。")

        return "\n".join(parts)

    def _generate_actions(self, analyses: List[DimensionAnalysis]) -> List[str]:
        """生成改进建议"""
        actions = []
        dim_names = {a.dimension for a in analyses}

        if "ECU关联" in dim_names:
            actions.append("组织涉及ECU的跨团队联合排查会议")
        if "版本关联" in dim_names:
            actions.append("对比问题版本与前版本的变更记录，定位引入点")
        if "频次分析" in dim_names:
            actions.append("建立该类缺陷的自动监控和告警机制")
        if "状态分布" in dim_names:
            actions.append("推动未关闭缺陷的处理，确认延期缺陷是否仍有效")
        if "time_pattern" in dim_names:
            actions.append("关注时间规律，优化对应时段的测试策略")

        if not actions:
            actions.append("持续监控该类缺陷趋势，积累更多数据后深入分析")

        return actions

    def _calculate_confidence(self, analyses: List[DimensionAnalysis]) -> float:
        """计算分析置信度"""
        if not analyses:
            return 0.0

        high_count = sum(1 for a in analyses if a.significance == "high")
        total = len(analyses)

        # 高维度越多，置信度越高
        base = 0.3
        high_bonus = min(high_count * 0.2, 0.4)
        coverage_bonus = min(total * 0.05, 0.2)

        return min(base + high_bonus + coverage_bonus, 1.0)


# ---------------------------------------------------------------------------
# Tool 接口（可注册到 agentic_runtime）
# ---------------------------------------------------------------------------

ROOT_CAUSE_ANALYSIS_TOOL_SPEC = {
    "description": "根因分析：对缺陷数据进行多维度深度分析，包括文本聚类、ECU关联、时间规律、版本关联等，生成根因假设和改进建议",
    "parameters": {
        "query": {
            "type": "string",
            "description": "分析查询，如'分析低温显示异常的根因'",
        },
        "cluster_id": {
            "type": "string",
            "description": "可选，指定分析的缺陷聚类ID",
        },
        "dimensions": {
            "type": "array",
            "description": "可选，分析维度列表：frequency/ecu_correlation/time_pattern/version_correlation/status_distribution",
            "items": {"type": "string"},
        },
    },
}


def execute_root_cause_analysis(
    defects: List[Dict],
    cluster_id: Optional[str] = None,
    dimensions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    执行根因分析（tool 接口）

    Args:
        defects: 缺陷数据列表
        cluster_id: 可选聚类ID
        dimensions: 可选分析维度

    Returns:
        分析结果字典
    """
    analyzer = RootCauseAnalyzer()
    cluster = None  # TODO: 从缓存中查找 cluster_id 对应的聚类

    report = analyzer.analyze(defects, cluster=cluster, dimensions=dimensions)

    return {
        "success": True,
        "result": {
            "cluster_info": {
                "id": report.cluster_info.cluster_id if report.cluster_info else None,
                "label": report.cluster_info.label if report.cluster_info else None,
                "size": report.cluster_info.size if report.cluster_info else 0,
            },
            "dimensions": [
                {
                    "name": a.dimension,
                    "significance": a.significance,
                    "findings": a.findings,
                }
                for a in report.dimension_analysis
            ],
            "hypothesis": report.hypothesis,
            "recommended_actions": report.recommended_actions,
            "confidence": report.confidence,
        },
    }


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_defect_clusterer(**kwargs) -> DefectClusterer:
    """创建缺陷聚类器实例"""
    return DefectClusterer(**kwargs)


def create_root_cause_analyzer() -> RootCauseAnalyzer:
    """创建根因分析器实例"""
    return RootCauseAnalyzer()


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("根因分析引擎测试")
    print("=" * 60)

    # 模拟缺陷数据
    test_defects = [
        {"id": "D001", "defect_description": "中控屏在低温-20度冷启动时偶发黑屏", "target_ecu": "ECU_Display", "status": "03_In Progress", "created_date": "2026-01-15", "fv": "v2.3.1"},
        {"id": "D002", "defect_description": "冷启动时显示屏无响应，需要重启", "target_ecu": "ECU_Display", "status": "03_In Progress", "created_date": "2026-01-20", "fv": "v2.3.1"},
        {"id": "D003", "defect_description": "仪表盘冬季启动闪烁后恢复正常", "target_ecu": "ECU_IC", "status": "02_Investigation", "created_date": "2026-02-05", "fv": "v2.3.1"},
        {"id": "D004", "defect_description": "低温环境下Power模块初始化超时", "target_ecu": "ECU_Power", "status": "01_New", "created_date": "2026-02-10", "fv": "v2.3.1"},
        {"id": "D005", "defect_description": "低温冷启动Display和Power模块竞争异常", "target_ecu": "ECU_Display", "status": "03_In Progress", "created_date": "2026-02-15", "fv": "v2.3.2"},
        {"id": "D006", "defect_description": "导航功能在高温环境下路线计算错误", "target_ecu": "ECU_NAV", "status": "04_Waiting", "created_date": "2026-03-01", "fv": "v2.3.2"},
        {"id": "D007", "defect_description": "低温启动后中控屏白屏", "target_ecu": "ECU_Display", "status": "02_Investigation", "created_date": "2026-03-10", "fv": "v2.3.2"},
    ]

    # 聚类测试
    print("\n--- 聚类测试 ---")
    clusterer = create_defect_clusterer(similarity_threshold=0.15, min_cluster_size=2)
    clusters = clusterer.cluster(test_defects)
    for c in clusters:
        print(f"\n聚类 {c.cluster_id}: {c.label}")
        print(f"  大小: {c.size}, 关键词: {c.keywords}")
        print(f"  缺陷: {c.defect_ids}")

    # 根因分析测试
    print("\n\n--- 根因分析测试 ---")
    analyzer = create_root_cause_analyzer()
    report = analyzer.analyze(test_defects)

    print(f"\n聚类: {report.cluster_info.label if report.cluster_info else 'N/A'}")
    print(f"\n假设:\n{report.hypothesis}")
    print(f"\n置信度: {report.confidence:.0%}")
    print(f"\n建议:")
    for action in report.recommended_actions:
        print(f"  • {action}")

    # Tool 接口测试
    print("\n\n--- Tool 接口测试 ---")
    result = execute_root_cause_analysis(test_defects)
    print(f"成功: {result['success']}")
    print(f"置信度: {result['result']['confidence']:.0%}")

    print("\n✅ 测试完成")

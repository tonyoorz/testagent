"""
关联异常发现模块

发现跨维度的隐藏关联模式，如OTA后缺陷变化、测试人员效率差异、
时间模式（周五效应）、ECU间缺陷传递（乒乓效应增强版）。

Features:
1. AssociationMiner - 关联规则挖掘
2. CrossDimensionAnalyzer - 跨维度场景分析
3. AnomalyDigestGenerator - 关联发现自然语言摘要

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
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class Association:
    """关联规则"""
    antecedent: str           # 前件描述
    consequent: str           # 后件描述
    support: float            # 支持度
    confidence: float         # 置信度
    lift: float               # 提升度
    description: str          # 自然语言描述
    dimensions: List[str]     # 涉及的维度
    significance: str = "medium"  # high/medium/low


# ---------------------------------------------------------------------------
# AssociationMiner
# ---------------------------------------------------------------------------

class AssociationMiner:
    """
    关联规则挖掘器

    使用简单的支持度/置信度统计，不依赖 MLP/FP-Growth 库。
    适用于中小规模数据的探索性关联发现。
    """

    def __init__(
        self,
        min_support: float = 0.05,
        min_confidence: float = 0.5,
        min_lift: float = 1.2,
        max_combinations: int = 1000,
    ):
        """
        Args:
            min_support: 最小支持度（0-1）
            min_confidence: 最小置信度（0-1）
            min_lift: 最小提升度
            max_combinations: 最大组合数（防止组合爆炸）
        """
        self.min_support = min_support
        self.min_confidence = min_confidence
        self.min_lift = min_lift
        self.max_combinations = max_combinations

    def mine(
        self,
        data: pd.DataFrame,
        dimensions: List[str],
    ) -> List[Association]:
        """
        挖掘跨维度关联

        Args:
            data: 数据 DataFrame
            dimensions: 要分析的维度列名列表

        Returns:
            关联规则列表
        """
        if data is None or data.empty or len(dimensions) < 2:
            return []

        df = data.copy()
        # 确保维度列存在
        valid_dims = [d for d in dimensions if d in df.columns]
        if len(valid_dims) < 2:
            return []

        # 离散化数值列（如果有的话）
        for dim in valid_dims:
            if pd.api.types.is_numeric_dtype(df[dim]):
                df[dim] = pd.qcut(df[dim], q=4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")

        total = len(df)
        associations = []

        # 生成所有维度对
        for i in range(len(valid_dims)):
            for j in range(i + 1, len(valid_dims)):
                dim_a, dim_b = valid_dims[i], valid_dims[j]
                pair_rules = self._mine_pair(df, dim_a, dim_b, total)
                associations.extend(pair_rules)

        # 过滤和排序
        filtered = [
            a for a in associations
            if a.support >= self.min_support
            and a.confidence >= self.min_confidence
            and a.lift >= self.min_lift
        ]

        filtered.sort(key=lambda a: a.lift, reverse=True)
        return filtered[:50]  # 最多返回50条

    def _mine_pair(
        self,
        df: pd.DataFrame,
        dim_a: str,
        dim_b: str,
        total: int,
    ) -> List[Association]:
        """挖掘两个维度间的关联"""
        associations = []

        # 统计 (value_a, value_b) 的共现频率
        pair_counts: Counter = Counter()
        a_counts: Counter = Counter()
        b_counts: Counter = Counter()

        for _, row in df.iterrows():
            va = str(row.get(dim_a, ""))
            vb = str(row.get(dim_b, ""))
            if va and vb and va != "nan" and vb != "nan":
                pair_counts[(va, vb)] += 1
                a_counts[va] += 1
                b_counts[vb] += 1

        if not pair_counts:
            return []

        # 限制组合数
        top_pairs = pair_counts.most_common(self.max_combinations)

        for (va, vb), count in top_pairs:
            support = count / total
            if support < self.min_support:
                continue

            # A → B 的置信度
            conf_ab = count / a_counts[va] if a_counts[va] > 0 else 0
            # B 的先验概率
            prob_b = b_counts[vb] / total if total > 0 else 0
            # 提升度
            lift_ab = conf_ab / prob_b if prob_b > 0 else 0

            if conf_ab >= self.min_confidence and lift_ab >= self.min_lift:
                dim_label_a = dim_a.replace("_", " ").title()
                dim_label_b = dim_b.replace("_", " ").title()

                associations.append(Association(
                    antecedent=f"{dim_label_a}={va}",
                    consequent=f"{dim_label_b}={vb}",
                    support=round(support, 4),
                    confidence=round(conf_ab, 4),
                    lift=round(lift_ab, 2),
                    description=f"当{dim_label_a}为\"{va}\"时，"
                               f"{dim_label_b}为\"{vb}\"的概率为{conf_ab:.0%}"
                               f"（提升度={lift_ab:.2f}）",
                    dimensions=[dim_a, dim_b],
                    significance="high" if lift_ab > 2 else "medium",
                ))

            # B → A 的置信度
            conf_ba = count / b_counts[vb] if b_counts[vb] > 0 else 0
            prob_a = a_counts[va] / total if total > 0 else 0
            lift_ba = conf_ba / prob_a if prob_a > 0 else 0

            if conf_ba >= self.min_confidence and lift_ba >= self.min_lift:
                dim_label_a = dim_a.replace("_", " ").title()
                dim_label_b = dim_b.replace("_", " ").title()

                associations.append(Association(
                    antecedent=f"{dim_label_b}={vb}",
                    consequent=f"{dim_label_a}={va}",
                    support=round(support, 4),
                    confidence=round(conf_ba, 4),
                    lift=round(lift_ba, 2),
                    description=f"当{dim_label_b}为\"{vb}\"时，"
                               f"{dim_label_a}为\"{va}\"的概率为{conf_ba:.0%}"
                               f"（提升度={lift_ba:.2f}）",
                    dimensions=[dim_b, dim_a],
                    significance="high" if lift_ba > 2 else "medium",
                ))

        return associations


# ---------------------------------------------------------------------------
# CrossDimensionAnalyzer
# ---------------------------------------------------------------------------

class CrossDimensionAnalyzer:
    """
    跨维度场景分析器

    预设场景：
    1. OTA升级后缺陷变化
    2. 测试人员效率差异
    3. 时间模式（周五效应等）
    4. ECU间缺陷传递（乒乓效应增强版）
    """

    def analyze(
        self,
        data: pd.DataFrame,
        scenario: str,
    ) -> Dict[str, Any]:
        """
        执行特定场景分析

        Args:
            data: 缺陷数据 DataFrame
            scenario: 场景名 (ota_impact/tester_efficiency/time_pattern/ecu_pingpong)

        Returns:
            分析结果字典
        """
        if data is None or data.empty:
            return {"success": False, "error": "无数据"}

        handlers = {
            "ota_impact": self._analyze_ota_impact,
            "tester_efficiency": self._analyze_tester_efficiency,
            "time_pattern": self._analyze_time_pattern,
            "ecu_pingpong": self._analyze_ecu_pingpong,
        }

        handler = handlers.get(scenario)
        if not handler:
            available = ", ".join(handlers.keys())
            return {"success": False, "error": f"未知场景: {scenario}，可用: {available}"}

        return handler(data)

    def _analyze_ota_impact(self, data: pd.DataFrame) -> Dict[str, Any]:
        """OTA升级后缺陷变化分析"""
        findings = []
        data_dict = {}

        # 按版本/日期统计缺陷数
        if "created_date" in data.columns and "fv" in data.columns:
            df = data.copy()
            try:
                df["_date"] = pd.to_datetime(df["created_date"], errors="coerce")
                df = df.dropna(subset=["_date"])

                # 按版本统计
                version_counts = df.groupby("fv").size().to_dict()
                data_dict["version_defect_counts"] = version_counts

                # 找出版本切换点
                versions = sorted(df["fv"].dropna().unique())
                if len(versions) >= 2:
                    for i in range(1, len(versions)):
                        prev_count = version_counts.get(versions[i - 1], 0)
                        curr_count = version_counts.get(versions[i], 0)

                        if prev_count > 0:
                            change_pct = (curr_count - prev_count) / prev_count * 100
                            if change_pct > 30:
                                findings.append(
                                    f"⚠️ 版本 {versions[i]} 升级后缺陷增加 {change_pct:.0f}%"
                                    f"（{prev_count}→{curr_count}）"
                                )
                            elif change_pct < -30:
                                findings.append(
                                    f"✅ 版本 {versions[i]} 升级后缺陷减少 {abs(change_pct):.0f}%"
                                    f"（{prev_count}→{curr_count}）"
                                )

                        # 分析升级后3天内的缺陷
                        version_dates = df[df["fv"] == versions[i]]["_date"]
                        if not version_dates.empty:
                            upgrade_date = version_dates.min()
                            post_3d = df[
                                (df["_date"] >= upgrade_date) &
                                (df["_date"] <= upgrade_date + pd.Timedelta(days=3))
                            ]
                            if len(post_3d) > 5:
                                findings.append(
                                    f"版本 {versions[i]} 升级后3天内新增 {len(post_3d)} 个缺陷"
                                )
            except Exception as e:
                findings.append(f"分析异常: {e}")

        if not findings:
            findings.append("未发现显著的OTA升级影响模式")

        return {
            "success": True,
            "scenario": "ota_impact",
            "findings": findings,
            "data": data_dict,
        }

    def _analyze_tester_efficiency(self, data: pd.DataFrame) -> Dict[str, Any]:
        """测试人员效率差异分析"""
        findings = []
        data_dict = {}

        # 测试人员字段可能是 reporter 或 tester
        tester_field = None
        for field_name in ["reporter", "tester", "created_by", "owner"]:
            if field_name in data.columns:
                tester_field = field_name
                break

        if not tester_field:
            return {"success": False, "error": "缺少测试人员字段"}

        # 按人员统计
        tester_stats = {}
        for tester, group in data.groupby(tester_field):
            tester = str(tester)
            if not tester or tester == "nan":
                continue

            stats = {
                "defect_count": len(group),
                "severity_dist": {},
            }

            # 严重度分布
            if "severity" in group.columns:
                sev_counts = group["severity"].value_counts().to_dict()
                stats["severity_dist"] = sev_counts
                high_sev = sum(v for k, v in sev_counts.items() if str(k)[0] in ("1", "2"))
                stats["high_severity_count"] = high_sev
                stats["high_severity_ratio"] = high_sev / len(group) if len(group) > 0 else 0

            # 模块覆盖
            if "target_ecu" in group.columns:
                stats["modules_covered"] = group["target_ecu"].nunique()

            tester_stats[tester] = stats

        data_dict["tester_statistics"] = tester_stats

        # 异常检测
        if tester_stats:
            counts = {t: s["defect_count"] for t, s in tester_stats.items()}
            if counts:
                avg_count = np.mean(list(counts.values()))
                std_count = np.std(list(counts.values()))

                for tester, count in counts.items():
                    if std_count > 0 and (count - avg_count) / std_count > 2:
                        findings.append(
                            f"⚠️ {tester} 的缺陷发现数 ({count}) 显著高于团队均值 ({avg_count:.1f})"
                        )
                    elif std_count > 0 and (avg_count - count) / std_count > 2:
                        findings.append(
                            f"📌 {tester} 的缺陷发现数 ({count}) 显著低于团队均值 ({avg_count:.1f})"
                        )

            # 严重度发现率
            high_ratios = {t: s.get("high_severity_ratio", 0) for t, s in tester_stats.items()}
            if high_ratios:
                top_tester = max(high_ratios, key=high_ratios.get)
                if high_ratios[top_tester] > 0.5:
                    findings.append(
                        f"🔍 {top_tester} 高严重度缺陷占比 {high_ratios[top_tester]:.0%}，"
                        f"可能是测试深度更高或负责的模块更复杂"
                    )

        if not findings:
            findings.append("未发现显著的测试人员效率差异")

        return {
            "success": True,
            "scenario": "tester_efficiency",
            "findings": findings,
            "data": data_dict,
        }

    def _analyze_time_pattern(self, data: pd.DataFrame) -> Dict[str, Any]:
        """时间模式分析（周五效应等）"""
        findings = []
        data_dict = {}

        if "created_date" not in data.columns:
            return {"success": False, "error": "缺少日期字段"}

        df = data.copy()
        try:
            df["_date"] = pd.to_datetime(df["created_date"], errors="coerce")
            df = df.dropna(subset=["_date"])

            # 星期分布
            df["_weekday"] = df["_date"].dt.day_name()
            weekday_counts = df["_weekday"].value_counts().to_dict()
            data_dict["weekday_distribution"] = weekday_counts

            total = len(df)
            if weekday_counts and total > 0:
                expected = total / 7
                for day, count in sorted(weekday_counts.items(), key=lambda x: -x[1]):
                    ratio = count / total
                    deviation = (count - expected) / expected * 100
                    if abs(deviation) > 30:
                        emoji = "📈" if deviation > 0 else "📉"
                        findings.append(
                            f"{emoji} {day}: {count}个 ({ratio:.0%})，"
                            f"偏离均匀分布 {deviation:+.0f}%"
                        )

            # 小时分布
            df["_hour"] = df["_date"].dt.hour
            hour_counts = df["_hour"].value_counts().to_dict()
            data_dict["hour_distribution"] = hour_counts

            if hour_counts:
                peak_hour = max(hour_counts, key=hour_counts.get)
                findings.append(
                    f"提交高峰时段: {peak_hour}:00（{hour_counts[peak_hour]}个）"
                )

            # 月度模式
            df["_month"] = df["_date"].dt.month
            month_counts = df["_month"].value_counts().to_dict()
            data_dict["month_distribution"] = month_counts

            if month_counts:
                peak_month = max(month_counts, key=month_counts.get)
                findings.append(
                    f"缺陷高峰月份: {peak_month}月（{month_counts[peak_month]}个）"
                )

        except Exception as e:
            findings.append(f"分析异常: {e}")

        if not findings:
            findings.append("未发现显著的时间模式")

        return {
            "success": True,
            "scenario": "time_pattern",
            "findings": findings,
            "data": data_dict,
        }

    def _analyze_ecu_pingpong(self, data: pd.DataFrame) -> Dict[str, Any]:
        """ECU间缺陷传递分析（乒乓效应增强版）"""
        findings = []
        data_dict = {}

        # 需要 ECU 和缺陷ID 以及状态流转历史
        if "target_ecu" not in data.columns:
            return {"success": False, "error": "缺少ECU字段"}

        # 分析同一缺陷在不同ECU间的转派
        # 如果有 assignee_history 或 status_history 字段，可以做更精确的分析
        # 这里做简化版：分析同一 project/fv 下不同ECU的缺陷共现

        ecu_pairs: Counter = Counter()
        ecu_defects: Dict[str, List[str]] = defaultdict(list)

        for _, row in data.iterrows():
            ecu = str(row.get("target_ecu", ""))
            defect_id = str(row.get("id", ""))
            if ecu and ecu != "nan":
                ecu_defects[ecu].append(defect_id)

        # 通过 project/fv 关联
        if "project" in data.columns:
            for project, group in data.groupby("project"):
                ecus_in_project = group["target_ecu"].dropna().unique()
                ecu_list = sorted(ecus_in_project)
                for i in range(len(ecu_list)):
                    for j in range(i + 1, len(ecu_list)):
                        ecu_pairs[(ecu_list[i], ecu_list[j])] += len(group)

        data_dict["ecu_defect_counts"] = {ecu: len(defects) for ecu, defects in ecu_defects.items()}
        data_dict["ecu_co_occurrence"] = {f"{k[0]}↔{k[1]}": v for k, v in ecu_pairs.most_common(10)}

        # 分析乒乓模式
        if ecu_pairs:
            for (ecu_a, ecu_b), count in ecu_pairs.most_common(5):
                if count >= 3:
                    findings.append(
                        f"🔄 {ecu_a} ↔ {ecu_b}: 在 {count} 个project中共现，"
                        f"可能存在跨ECU协调问题"
                    )

        # 单ECU高缺陷密度
        ecu_counts = {ecu: len(defects) for ecu, defects in ecu_defects.items()}
        if ecu_counts:
            total_defects = sum(ecu_counts.values())
            for ecu, count in sorted(ecu_counts.items(), key=lambda x: -x[1])[:3]:
                ratio = count / total_defects * 100
                if ratio > 30:
                    findings.append(
                        f"🔴 {ecu}: {count}个缺陷（占 {ratio:.0f}%），缺陷高度集中"
                    )

        if not findings:
            findings.append("未发现显著的ECU间传递模式")

        return {
            "success": True,
            "scenario": "ecu_pingpong",
            "findings": findings,
            "data": data_dict,
        }

    def analyze_all(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        执行所有场景分析

        Args:
            data: 缺陷数据 DataFrame

        Returns:
            所有场景的分析结果
        """
        results = {}
        for scenario in ["ota_impact", "tester_efficiency", "time_pattern", "ecu_pingpong"]:
            results[scenario] = self.analyze(data, scenario)
        return results


# ---------------------------------------------------------------------------
# AnomalyDigestGenerator
# ---------------------------------------------------------------------------

class AnomalyDigestGenerator:
    """
    关联发现自然语言摘要生成器
    """

    def generate(self, associations: List[Association]) -> str:
        """
        生成关联发现的自然语言摘要

        Args:
            associations: 关联规则列表

        Returns:
            摘要文本
        """
        if not associations:
            return "未发现显著的跨维度关联模式。"

        lines = ["🔍 关联异常发现报告", ""]

        # 按维度对分组
        dim_pairs: Dict[str, List[Association]] = defaultdict(list)
        for a in associations:
            key = " × ".join(sorted(a.dimensions))
            dim_pairs[key].append(a)

        for dim_pair, rules in dim_pairs.items():
            lines.append(f"**{dim_pair}**")
            for r in rules[:3]:  # 每个维度对最多3条
                emoji = "🔴" if r.significance == "high" else "🟡"
                lines.append(f"  {emoji} {r.description}")
                lines.append(f"     支持度={r.support:.2%} 置信度={r.confidence:.0%} 提升度={r.lift:.2f}")
            lines.append("")

        # 总结
        high_count = sum(1 for a in associations if a.significance == "high")
        if high_count > 0:
            lines.append(f"发现 {high_count} 个高显著性关联，建议重点关注。")
        else:
            lines.append(f"共发现 {len(associations)} 个关联，显著性中等，可持续关注。")

        return "\n".join(lines)

    def generate_scenario_digest(self, results: Dict[str, Any]) -> str:
        """
        生成场景分析摘要

        Args:
            results: CrossDimensionAnalyzer.analyze_all() 的输出

        Returns:
            摘要文本
        """
        scenario_labels = {
            "ota_impact": "OTA升级影响",
            "tester_efficiency": "测试人员效率",
            "time_pattern": "时间模式",
            "ecu_pingpong": "ECU间传递",
        }

        lines = ["📊 跨维度场景分析摘要", ""]

        for scenario, result in results.items():
            label = scenario_labels.get(scenario, scenario)
            if not result.get("success"):
                lines.append(f"**{label}**: {result.get('error', '分析失败')}")
                continue

            findings = result.get("findings", [])
            lines.append(f"**{label}**（{len(findings)}个发现）：")
            for f in findings[:3]:
                lines.append(f"  • {f}")
            if len(findings) > 3:
                lines.append(f"  ...还有 {len(findings) - 3} 个发现")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_association_miner(**kwargs) -> AssociationMiner:
    """创建关联规则挖掘器"""
    return AssociationMiner(**kwargs)


def create_cross_dimension_analyzer() -> CrossDimensionAnalyzer:
    """创建跨维度分析器"""
    return CrossDimensionAnalyzer()


def create_anomaly_digest_generator() -> AnomalyDigestGenerator:
    """创建异常摘要生成器"""
    return AnomalyDigestGenerator()


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("关联异常发现模块测试")
    print("=" * 60)

    # 模拟缺陷数据
    test_data = pd.DataFrame([
        {"id": "D1", "target_ecu": "ECU_Display", "severity": "1A", "status": "03_In Progress", "project": "G01", "fv": "v2.3.1", "created_date": "2026-01-15", "reporter": "张三"},
        {"id": "D2", "target_ecu": "ECU_Display", "severity": "2B", "status": "01_New", "project": "G01", "fv": "v2.3.1", "created_date": "2026-01-16", "reporter": "张三"},
        {"id": "D3", "target_ecu": "ECU_Power", "severity": "2A", "status": "02_Investigation", "project": "G01", "fv": "v2.3.1", "created_date": "2026-01-20", "reporter": "李四"},
        {"id": "D4", "target_ecu": "ECU_Display", "severity": "1C", "status": "03_In Progress", "project": "G01", "fv": "v2.3.2", "created_date": "2026-02-01", "reporter": "张三"},
        {"id": "D5", "target_ecu": "ECU_NAV", "severity": "3C", "status": "06_Concluded", "project": "G02", "fv": "v2.3.2", "created_date": "2026-02-05", "reporter": "王五"},
        {"id": "D6", "target_ecu": "ECU_IC", "severity": "1A", "status": "01_New", "project": "G02", "fv": "v2.3.2", "created_date": "2026-02-10", "reporter": "张三"},
        {"id": "D7", "target_ecu": "ECU_NAV", "severity": "4D", "status": "06_Concluded", "project": "G02", "fv": "v2.3.2", "created_date": "2026-02-15", "reporter": "王五"},
        {"id": "D8", "target_ecu": "ECU_Display", "severity": "2A", "status": "03_In Progress", "project": "G01", "fv": "v2.3.3", "created_date": "2026-03-01", "reporter": "李四"},
        {"id": "D9", "target_ecu": "ECU_Power", "severity": "3B", "status": "04_Waiting", "project": "G01", "fv": "v2.3.3", "created_date": "2026-03-05", "reporter": "李四"},
        {"id": "D10", "target_ecu": "ECU_IC", "severity": "1B", "status": "02_Investigation", "project": "G02", "fv": "v2.3.3", "created_date": "2026-03-10", "reporter": "张三"},
    ])

    # 1. 关联规则挖掘
    print("\n--- 关联规则挖掘 ---")
    miner = create_association_miner(min_support=0.05, min_confidence=0.4, min_lift=1.0)
    rules = miner.mine(test_data, dimensions=["target_ecu", "severity", "project", "reporter"])
    for r in rules[:10]:
        print(f"  {r.description} [L={r.lift}]")

    # 2. 跨维度场景分析
    print("\n--- 跨维度场景分析 ---")
    analyzer = create_cross_dimension_analyzer()
    all_results = analyzer.analyze_all(test_data)
    for scenario, result in all_results.items():
        print(f"\n[{scenario}]")
        for f in result.get("findings", []):
            print(f"  • {f}")

    # 3. 摘要生成
    print("\n--- 关联发现摘要 ---")
    gen = create_anomaly_digest_generator()
    print(gen.generate(rules))
    print("\n--- 场景分析摘要 ---")
    print(gen.generate_scenario_digest(all_results))

    print("\n✅ 测试完成")

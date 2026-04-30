"""
测试用例智能推荐模块

分析历史缺陷分布与测试用例覆盖的差距，生成智能测试建议。

Features:
1. TestCoverageAnalyzer - 测试覆盖差距分析
2. TestCaseGenerator - 基于缺陷的测试用例建议生成
3. RegressionTestSelector - 回归测试智能选择

Author: AI Assistant
Date: 2026-04-12
"""

import logging
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
class CoverageGap:
    """测试覆盖缺口"""
    module: str
    defect_count: int          # 该模块缺陷数
    test_case_count: int       # 该模块测试用例数
    gap_score: float           # 缺口分数（0-100，越高越缺）
    severity: str              # high/medium/low
    uncovered_areas: List[str] # 未覆盖的领域


@dataclass
class TestCaseSuggestion:
    """测试用例建议"""
    title: str                 # 测试用例标题
    module: str                # 所属模块
    priority: str              # P0/P1/P2
    steps: List[str]           # 测试步骤
    related_defects: List[str] # 关联的缺陷ID
    test_type: str = "functional"  # functional/performance/regression


@dataclass
class RegressionPlan:
    """回归测试计划"""
    selected_tests: List[str]  # 选中的测试用例ID
    total_tests: int           # 总测试用例数
    selected_ratio: float      # 选择比例
    reason: str                # 选择理由
    estimated_effort: str      # 预估工作量


# ---------------------------------------------------------------------------
# TestCoverageAnalyzer
# ---------------------------------------------------------------------------

class TestCoverageAnalyzer:
    """
    测试覆盖差距分析器

    对比缺陷分布与测试用例覆盖，找出高风险低覆盖的模块。
    """

    def __init__(
        self,
        defect_module_field: str = "target_ecu",
        test_module_field: str = "module",
    ):
        self.defect_module_field = defect_module_field
        self.test_module_field = test_module_field

    def find_gaps(
        self,
        defects: pd.DataFrame,
        test_cases: pd.DataFrame,
        severity_field: str = "severity",
    ) -> List[CoverageGap]:
        """
        分析缺陷分布与测试用例覆盖的差距

        Args:
            defects: 缺陷数据 DataFrame
            test_cases: 测试用例数据 DataFrame
            severity_field: 严重度字段

        Returns:
            覆盖缺口列表
        """
        if defects is None or defects.empty:
            return []

        # 统计每个模块的缺陷数
        defect_counts: Counter = Counter()
        defect_severities: Dict[str, List[str]] = defaultdict(list)
        defect_types: Dict[str, Set[str]] = defaultdict(set)

        for _, row in defects.iterrows():
            module = str(row.get(self.defect_module_field, ""))
            if not module or module == "nan":
                continue
            defect_counts[module] += 1

            sev = str(row.get(severity_field, ""))
            if sev:
                defect_severities[module].append(sev)

            # 提取缺陷类型关键词
            desc = str(row.get("defect_description", ""))
            keywords = self._extract_keywords(desc)
            defect_types[module].update(keywords)

        # 统计每个模块的测试用例数
        test_counts: Counter = Counter()
        test_types_covered: Dict[str, Set[str]] = defaultdict(set)

        if test_cases is not None and not test_cases.empty:
            for _, row in test_cases.iterrows():
                module = str(row.get(self.test_module_field, ""))
                if module and module != "nan":
                    test_counts[module] += 1

                # 提取测试覆盖的关键词
                tc_desc = str(row.get("description", "")) + " " + str(row.get("title", ""))
                tc_keywords = self._extract_keywords(tc_desc)
                test_types_covered[module].update(tc_keywords)

        # 计算缺口
        gaps = []
        all_modules = set(defect_counts.keys()) | set(test_counts.keys())

        for module in all_modules:
            d_count = defect_counts.get(module, 0)
            t_count = test_counts.get(module, 0)

            # 缺口分数：缺陷多 + 测试少 = 高缺口
            if d_count == 0 and t_count == 0:
                continue

            if d_count == 0:
                gap_score = 0
            elif t_count == 0:
                gap_score = min(d_count * 15, 100)
            else:
                ratio = d_count / max(t_count, 1)
                gap_score = min(ratio * 20, 100)

            # 严重度加权
            severities = defect_severities.get(module, [])
            high_sev_count = sum(1 for s in severities if s and s[0] in ("1", "2"))
            if high_sev_count > 0:
                gap_score = min(gap_score + high_sev_count * 10, 100)

            # 未覆盖领域
            defect_kw = defect_types.get(module, set())
            test_kw = test_types_covered.get(module, set())
            uncovered = sorted(defect_kw - test_kw)

            severity = "high" if gap_score >= 70 else ("medium" if gap_score >= 40 else "low")

            gaps.append(CoverageGap(
                module=module,
                defect_count=d_count,
                test_case_count=t_count,
                gap_score=round(gap_score, 1),
                severity=severity,
                uncovered_areas=uncovered[:5],
            ))

        # 按缺口分数排序
        gaps.sort(key=lambda g: g.gap_score, reverse=True)
        return gaps

    def _extract_keywords(self, text: str) -> Set[str]:
        """从文本提取关键词"""
        if not text or text == "nan":
            return set()

        keywords = set()
        # 英文关键词
        en_words = re.findall(r"\b[A-Za-z0-9_]{3,}\b", text.lower())
        # 过滤常见停用词
        stop = {"the", "and", "for", "not", "has", "was", "are", "but", "with", "this", "that"}
        keywords.update(w for w in en_words if w not in stop)

        # 中文关键词（bigram）
        cn_segments = re.findall(r"[\u4e00-\u9fff]+", text)
        for seg in cn_segments:
            for i in range(len(seg) - 1):
                keywords.add(seg[i:i + 2])

        return keywords


# ---------------------------------------------------------------------------
# TestCaseGenerator
# ---------------------------------------------------------------------------

class TestCaseGenerator:
    """
    基于历史缺陷的测试用例建议生成器

    从缺陷描述中提取测试场景，生成结构化的测试用例建议。
    纯规则驱动，不依赖 LLM。
    """

    # 缺陷模式 → 测试场景映射
    PATTERN_TEST_MAP = {
        r"低温|冷启动|零下|寒冷": {
            "title": "低温环境启动测试",
            "steps": [
                "1. 将环境温度设置为-20°C",
                "2. 执行冷启动操作",
                "3. 验证各模块初始化状态",
                "4. 检查显示是否正常",
                "5. 验证功能响应时间",
            ],
            "type": "environmental",
        },
        r"高温|过热|温度过高": {
            "title": "高温环境稳定性测试",
            "steps": [
                "1. 将环境温度设置为85°C",
                "2. 持续运行2小时",
                "3. 监控各模块温度和性能",
                "4. 验证降频保护是否生效",
                "5. 检查功能是否正常",
            ],
            "type": "environmental",
        },
        r"黑屏|白屏|闪烁|花屏|无显示": {
            "title": "显示异常专项测试",
            "steps": [
                "1. 在不同温度条件下启动",
                "2. 执行多次切换操作",
                "3. 监控GPU渲染状态",
                "4. 验证帧率和画面完整性",
                "5. 长时间运行稳定性检查",
            ],
            "type": "functional",
        },
        r"内存泄漏|内存不足|OOM|memory": {
            "title": "内存泄漏压力测试",
            "steps": [
                "1. 启动内存监控工具",
                "2. 循环执行目标操作100次",
                "3. 记录内存使用变化",
                "4. 验证内存是否持续增长",
                "5. 检查GC是否正常回收",
            ],
            "type": "performance",
        },
        r"OTA|升级|更新|刷写": {
            "title": "OTA升级可靠性测试",
            "steps": [
                "1. 准备升级包",
                "2. 执行正常升级流程",
                "3. 中途断网/断电测试",
                "4. 验证回滚机制",
                "5. 升级后功能全面验证",
            ],
            "type": "functional",
        },
        r"语音|voice|nlu|识别": {
            "title": "语音交互鲁棒性测试",
            "steps": [
                "1. 准备多方言/口音测试集",
                "2. 在不同噪音背景下测试",
                "3. 测试中英混杂指令",
                "4. 验证语义理解准确率",
                "5. 测试响应延迟",
            ],
            "type": "functional",
        },
        r"延迟|超时|响应慢|卡顿|lag": {
            "title": "性能响应时间测试",
            "steps": [
                "1. 建立性能基线",
                "2. 在目标场景下测量响应时间",
                "3. 与基线对比分析",
                "4. 检查CPU/内存占用",
                "5. 多次执行取平均值",
            ],
            "type": "performance",
        },
        r"崩溃|crash|重启|reset": {
            "title": "稳定性与崩溃测试",
            "steps": [
                "1. 复现触发条件",
                "2. 分析崩溃日志",
                "3. 执行压力测试（Monkey测试）",
                "4. 验证异常恢复机制",
                "5. 检查数据完整性",
            ],
            "type": "stability",
        },
    }

    def generate_suggestions(
        self,
        defect_cluster: Dict,
        context: str = "",
    ) -> List[TestCaseSuggestion]:
        """
        基于缺陷聚类生成测试用例建议

        Args:
            defect_cluster: 缺陷聚类信息，应包含 keywords, defect_ids, label
            context: 额外上下文信息

        Returns:
            测试用例建议列表
        """
        suggestions = []
        seen_types: Set[str] = set()

        # 从聚类关键词和描述中匹配测试场景
        search_text = " ".join(defect_cluster.get("keywords", []))
        search_text += " " + defect_cluster.get("label", "")
        search_text += " " + defect_cluster.get("centroid_text", "")
        search_text += " " + context

        for pattern, test_info in self.PATTERN_TEST_MAP.items():
            if re.search(pattern, search_text, re.IGNORECASE):
                test_type = test_info["type"]
                if test_type in seen_types:
                    continue
                seen_types.add(test_type)

                # 确定优先级
                defect_ids = defect_cluster.get("defect_ids", [])
                priority = "P0" if len(defect_ids) >= 5 else ("P1" if len(defect_ids) >= 3 else "P2")

                suggestions.append(TestCaseSuggestion(
                    title=test_info["title"],
                    module=defect_cluster.get("module", "unknown"),
                    priority=priority,
                    steps=test_info["steps"],
                    related_defects=defect_ids[:5],
                    test_type=test_type,
                ))

        # 如果没匹配到特定模式，生成通用建议
        if not suggestions:
            defect_ids = defect_cluster.get("defect_ids", [])
            label = defect_cluster.get("label", "未知问题")
            suggestions.append(TestCaseSuggestion(
                title=f"针对\"{label}\"的专项测试",
                module=defect_cluster.get("module", "unknown"),
                priority="P2",
                steps=[
                    "1. 分析关联缺陷的共同特征",
                    "2. 设计覆盖这些特征的测试场景",
                    "3. 执行测试并记录结果",
                    "4. 与缺陷数据进行对比验证",
                ],
                related_defects=defect_ids[:5],
                test_type="functional",
            ))

        return suggestions


# ---------------------------------------------------------------------------
# RegressionTestSelector
# ---------------------------------------------------------------------------

class RegressionTestSelector:
    """
    回归测试智能选择器

    基于模块变更影响选择回归测试范围，避免全量回归。
    """

    def __init__(
        self,
        module_field: str = "module",
        related_modules_field: str = "related_modules",
    ):
        self.module_field = module_field
        self.related_modules_field = related_modules_field

    def select(
        self,
        changed_modules: List[str],
        all_test_cases: pd.DataFrame,
        module_dependency: Optional[Dict[str, List[str]]] = None,
    ) -> RegressionPlan:
        """
        选择回归测试范围

        Args:
            changed_modules: 本次变更的模块列表
            all_test_cases: 所有测试用例 DataFrame
            module_dependency: 模块依赖关系 {module: [dependent_modules]}

        Returns:
            回归测试计划
        """
        if not changed_modules or all_test_cases is None or all_test_cases.empty:
            return RegressionPlan(
                selected_tests=[], total_tests=0,
                selected_ratio=0, reason="无变更或无测试用例",
                estimated_effort="0人天",
            )

        total = len(all_test_cases)

        # 计算受影响模块（含传递依赖）
        affected = set(changed_modules)
        if module_dependency:
            for mod in changed_modules:
                deps = module_dependency.get(mod, [])
                affected.update(deps)

        # 选择测试用例
        selected_ids = []
        for _, row in all_test_cases.iterrows():
            tc_module = str(row.get(self.module_field, ""))
            # 直接匹配
            if tc_module in affected:
                selected_ids.append(str(row.get("id", "")))
                continue

            # 关联模块匹配
            related = str(row.get(self.related_modules_field, ""))
            if related:
                related_list = [r.strip() for r in related.split(",")]
                if any(r in affected for r in related_list):
                    selected_ids.append(str(row.get("id", "")))

        ratio = len(selected_ids) / total if total > 0 else 0

        # 预估工作量（假设每个用例0.5人时）
        hours = len(selected_ids) * 0.5
        if hours < 8:
            effort = f"{hours:.0f}小时"
        else:
            effort = f"{hours / 8:.1f}人天"

        reason_parts = [
            f"变更模块: {', '.join(changed_modules)}",
            f"受影响范围: {len(affected)} 个模块",
            f"选中测试: {len(selected_ids)}/{total} ({ratio:.0%})",
        ]

        if len(affected) > len(changed_modules):
            reason_parts.append(f"（含传递依赖 {len(affected) - len(changed_modules)} 个模块）")

        return RegressionPlan(
            selected_tests=selected_ids,
            total_tests=total,
            selected_ratio=round(ratio, 2),
            reason="；".join(reason_parts),
            estimated_effort=effort,
        )


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def create_test_coverage_analyzer(**kwargs) -> TestCoverageAnalyzer:
    """创建测试覆盖分析器"""
    return TestCoverageAnalyzer(**kwargs)


def create_test_case_generator() -> TestCaseGenerator:
    """创建测试用例生成器"""
    return TestCaseGenerator()


def create_regression_test_selector(**kwargs) -> RegressionTestSelector:
    """创建回归测试选择器"""
    return RegressionTestSelector(**kwargs)


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("测试用例智能推荐模块测试")
    print("=" * 60)

    # 模拟缺陷数据
    defects = pd.DataFrame([
        {"id": "D1", "target_ecu": "ECU_Display", "severity": "1A", "defect_description": "低温冷启动黑屏"},
        {"id": "D2", "target_ecu": "ECU_Display", "severity": "2B", "defect_description": "高温环境闪屏"},
        {"id": "D3", "target_ecu": "ECU_Display", "severity": "1A", "defect_description": "多次切换后内存泄漏导致崩溃"},
        {"id": "D4", "target_ecu": "ECU_NAV", "severity": "3C", "defect_description": "导航路线计算错误"},
        {"id": "D5", "target_ecu": "ECU_NAV", "severity": "4D", "defect_description": "语音识别不准确"},
        {"id": "D6", "target_ecu": "ECU_Power", "severity": "2A", "defect_description": "OTA升级中断电导致系统异常"},
    ])

    # 模拟测试用例数据
    test_cases = pd.DataFrame([
        {"id": "TC1", "module": "ECU_Display", "title": "基本显示功能测试"},
        {"id": "TC2", "module": "ECU_Display", "title": "多任务切换测试"},
        {"id": "TC3", "module": "ECU_NAV", "title": "导航基本功能测试"},
        {"id": "TC4", "module": "ECU_NAV", "title": "路线规划测试"},
    ])

    # 1. 覆盖差距分析
    print("\n--- 覆盖差距分析 ---")
    analyzer = create_test_coverage_analyzer()
    gaps = analyzer.find_gaps(defects, test_cases)
    for g in gaps:
        print(f"  {g.module}: 缺陷={g.defect_count}, 用例={g.test_case_count}, "
              f"缺口={g.gap_score}, 严重度={g.severity}")
        if g.uncovered_areas:
            print(f"    未覆盖: {g.uncovered_areas}")

    # 2. 测试用例生成
    print("\n--- 测试用例建议 ---")
    generator = create_test_case_generator()
    cluster = {
        "keywords": ["低温", "冷启动", "黑屏", "内存", "崩溃"],
        "defect_ids": ["D1", "D2", "D3"],
        "label": "低温/高温 显示异常",
        "module": "ECU_Display",
    }
    suggestions = generator.generate_suggestions(cluster)
    for s in suggestions:
        print(f"\n  [{s.priority}] {s.title}")
        print(f"  类型: {s.test_type}")
        print(f"  步骤: {s.steps}")

    # 3. 回归测试选择
    print("\n--- 回归测试选择 ---")
    selector = create_regression_test_selector()
    plan = selector.select(
        changed_modules=["ECU_Display"],
        all_test_cases=test_cases,
        module_dependency={"ECU_Display": ["ECU_IC", "ECU_Power"]},
    )
    print(f"  选择: {plan.selected_tests}")
    print(f"  比例: {plan.selected_ratio:.0%}")
    print(f"  工作量: {plan.estimated_effort}")
    print(f"  理由: {plan.reason}")

    print("\n✅ 测试完成")

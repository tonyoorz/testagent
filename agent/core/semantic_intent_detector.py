"""
Semantic Intent Detector - 基于语义相似度的意图识别

Features:
1. TF-IDF + cosine similarity based intent detection
2. Example-based intent matching with confidence scores
3. Multi-intent detection support
4. Fallback to clarification for low confidence

Author: AI Assistant
Date: 2025-02-21
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    TfidfVectorizer = None
    cosine_similarity = None
    logger.warning("sklearn not available, falling back to keyword matching")


@dataclass
class IntentDetectionResult:
    """意图识别结果"""
    intent: str
    confidence: float
    matched_examples: List[str] = field(default_factory=list)


class SemanticIntentDetector:
    """
    基于语义相似度的意图识别器

    使用 TF-IDF + cosine similarity 计算用户问题与预定义意图示例的相似度，
    返回最匹配的意图及其置信度。
    """

    # 意图示例库 - 中英文混合
    INTENT_EXAMPLES = {
        'risk': [
            "idcevo风险如何？", "有哪些严重问题？", "Critical缺陷多吗？",
            "高风险缺陷分布", "top issue分析", "长期未关闭的问题",
            "风险最高的项目是什么？", "哪些缺陷最紧急？",
            "risk analysis", "critical defects", "high priority issues",
            "severe problems", "top issues", "urgent defects",
            "风险", "严重", "紧急", "critical", "high risk",
            "最近有啥问题", "哪个最严重", "危险", "topissue",
            "高风险票", "showstopper有哪些", "有什么严重bug",
            "最紧急的缺陷", "需要关注的缺陷", "关键问题",
            "风险评估", "风险分析", "最危险的缺陷",
            "blocking issues", "major defects", "showstoppers",
            "有什么大问题", "严重的issue", "高危缺陷"
        ],
        'comparison': [
            "idcevo和mgu对比", "哪个项目缺陷多？", "vs比较",
            "G01和G20哪个更严重？", "对比两个项目的测试情况",
            "哪个ECU的问题最多？", "横向对比各项目",
            "compare projects", "versus", "vs", "difference between",
            "which project has more defects", "comparison analysis",
            "对比", "比较", "vs", "差异", "哪个更多",
            "哪个好", "哪个差", "差别", "差距",
            "A和B的区别", "两者对比", "横向比较",
            "项目间差异", "不同项目对比", "比较分析",
            "compare", "benchmark", "relative",
            "谁更多", "谁更好", "哪个项目最差"
        ],
        'trend': [
            "最近趋势如何？", "缺陷增长了吗？", "历史走势",
            "本周新增多少缺陷？", "月度趋势分析", "时间变化",
            "缺陷数量在上升吗？", "过去一个月的趋势",
            "缺陷流转历史", "状态变更记录", "defect status history",
            "trend analysis", "over time", "historical trend",
            "growth pattern", "weekly trend", "monthly change",
            "趋势", "变化", "增长", "走势", "历史", "流转历史", "状态变更",
            "变化趋势", "增长趋势", "趋势分析", "历史数据",
            "按周趋势", "按月趋势", "每周变化",
            "上升还是下降", "趋势好不好", "走势怎么样",
            "近几周的变化", "缺陷趋势走向",
            "evolution", "progress", "trajectory",
            "过去几周", "近期走势", "周环比"
        ],
        'summary': [
            "总结一下", "当前整体情况", "数据概览",
            "总体分析", "给我一个概况", "整体统计",
            "summary", "overview", "overall status", "general picture",
            "high level summary", "total count", "statistics",
            "总结", "概览", "整体", "概况", "统计",
            "整体情况", "当前状态", "数据总览",
            "怎么样", "好不好", "啥情况",
            "全部数据", "总共有多少", "整体看看",
            "大面上怎么样", "宏观情况", "综合来看",
            "big picture", "at a glance", "in general",
            "一句话总结", "目前怎么样", "现在什么情况"
        ],
        'quality': [
            "缺陷质量如何？", "平均处理时间？", "转移次数分析",
            "哪些缺陷处理太慢？", "缺陷年龄分布", "复杂度分析",
            "缺陷处理效率", "响应时间分析",
            "quality analysis", "defect age", "transfer count",
            "processing time", "complexity", "efficiency",
            "质量", "年龄", "转移", "效率", "处理时间",
            "处理效率", "响应时间", "问题质量", "处理慢",
            "longrunner", "长期票", "长周期问题",
            "处理周期", "解决速度", "修复速度",
            "效率怎么样", "处理得快不快",
            "long running", "resolution time", "turnaround",
            "积压情况", "处理瓶颈", "效率分析"
        ],
        'test': [
            "测试覆盖率如何？", "通过率怎么样？", "失败测试分析",
            "哪些测试失败了？", "测试执行情况", "测试趋势",
            "测试效率", "测试质量",
            "测试用例执行情况", "testcase execution status", "test cases execution",
            "test coverage", "pass rate", "failure analysis",
            "test execution", "test results", "testing trend",
            "测试", "覆盖率", "通过率", "失败", "执行", "测试用例", "testcase", "test cases",
            "测试结果", "测试情况", "用例执行", "通过率怎么样",
            "test run", "manual run", "manual runs",
            "执行状态", "run status", "test results",
            "测试通过多少", "失败率", "blocked测试",
            "测试进度", "测试完成情况", "用例运行情况",
            "test progress", "execution summary",
            "跑了多少测试", "测试报告"
        ],
        'dashboard': [
            "看板指标", "KPI数据", "关键指标",
            "业务图表", "汇总数据", "核心指标",
            "dashboard metrics", "kpi summary", "key indicators",
            "business charts", "overview metrics",
            "看板", "指标", "KPI", "图表", "汇总",
            "关键数据", "核心指标", "dashboard",
            "绩效指标", "度量", "metrics",
            "主要数据", "数据面板", "KPI看板"
        ],
        'matrix': [
            "矩阵分布", "1A缺陷有多少？", "矩阵热点分析",
            "哪些矩阵区域问题多？", "严重性和优先级矩阵",
            "matrix distribution", "1A defects", "matrix hotspots",
            "severity priority matrix", "quadrant analysis",
            "矩阵", "1A", "1B", "热点", "分布",
            "严重度分布", "象限分析", "矩阵图",
            "2A缺陷", "3B有多少", "矩阵情况",
            "matrix view", "risk matrix",
            "哪个象限多", "矩阵气泡图", "matrix bubble",
            "1C", "2B", "3A", "4E"
        ],
        'cross': [
            "缺陷和测试关联", "综合风险分析", "缺陷测试对比",
            "关联分析", "cross analysis", "defect test correlation",
            "关联", "综合", "交叉", "对比",
            "综合分析", "交叉对比", "多维度分析",
            "correlation", "cross reference",
            "测试和缺陷关系", "联动分析",
            "综合来看", "全方面分析"
        ],
        'tester': [
            "测试人员效率", "谁发现最多缺陷？", "tester分析",
            "测试团队表现", "个人产出分析",
            "tester performance", "who found most defects",
            "testing team analysis", "individual productivity",
            "测试人员", "效率", "发现", "产出", "团队",
            "谁提的bug多", "哪个测试人员最活跃",
            "提票人分析", "谁发现的缺陷",
            "tester ranking", "top testers",
            "发现人", "reporter分析", "detected by",
            "谁的缺陷最多", "测试贡献",
            "人员产出", "个人分析"
        ],
        'anomaly': [
            "最近有没有异常？", "数据里有什么异常点？", "异常检测",
            "有没有突增突降？", "这周数据正不正常？", "反常数据",
            "哪些时间段数据不正常？", "有没有spike？", "异常波动",
            "anomaly detection", "spike", "outlier", "anomaly",
            "异常", "突增", "突降", "不正常", "反常",
            "数据异常分析", "检测异常值", "有什么异常模式",
            "这周缺陷是不是突然多了", "有没有突然暴增",
            "abnormal", "irregular", "突然变化",
            "异常点", "离群值", "异常值检测",
            "find anomalies", "detect outliers",
            "哪个时期数据反常", "异常报告",
            "anomaly scan", "scan for anomalies",
            "数据里有没有什么不对劲的地方",
            "有什么异常趋势", "突发性增长"
        ],
        'root_cause': [
            "为什么会有这个问题？", "根因是什么？", "分析一下原因",
            "是什么导致的？", "root cause analysis", "为什么会这样",
            "根因分析", "根本原因", "是什么导致", "为什么出现",
            "找出根本原因", "分析原因", "为什么缺陷这么多",
            "为什么这个模块问题多", "根源在哪里",
            "what caused this", "why did this happen",
            "root cause", "cause analysis", "why so many",
            "追溯原因", "导致因素", "产生原因",
            "问题根源", "深层原因", "原因排查",
            "为什么会集中在Display", "为什么低温下出问题",
            "why", "cause of", "reason behind",
            "产生这些缺陷的原因", "为什么会出现这种情况",
            "trigger analysis", "underlying cause"
        ],
        'risk_eval': [
            "风险评估", "哪里风险最高？", "风险热力图",
            "模块风险评分", "哪个模块风险最大？", "risk heatmap",
            "风险等级分布", "风险高的模块", "综合风险评价",
            "风险热力图分析", "模块风险排行",
            "risk evaluation", "risk score", "risk assessment",
            "heat map", "heatmap", "risk ranking",
            "风险评分", "风险排行", "风险最大的ECU",
            "哪些模块需要优先测试", "高风险区域",
            "哪个ECU最危险", "risk level",
            "风险画像", "模块风险画像", "风险概况",
            "risk profile", "module risk", "risk overview",
            "各模块风险对比", "风险矩阵",
            "哪里最需要关注", "优先级最高的风险"
        ],
        'coverage': [
            "覆盖率怎么样？", "测试够不够？", "缺什么用例？",
            "测试盲区在哪？", "覆盖差距分析", "test coverage gap",
            "哪些模块没有测试覆盖？", "测试覆盖情况",
            "覆盖率", "覆盖", "测试够不够", "缺什么用例",
            "测试盲区", "覆盖差距", "coverage",
            "test coverage", "coverage gap", "blind spot",
            "哪些模块缺测试", "需要补充什么测试",
            "覆盖不足的地方", "测试遗漏",
            "测试覆盖缺口", "没有测试的模块",
            "缺测试用例", "测试不够充分",
            "uncovered areas", "missing tests",
            "哪些地方没有测到", "测试短板",
            "测试覆盖报告", "覆盖率分析",
            "test strategy", "testing gaps"
        ],
        'association': [
            "关联分析", "ECU之间有没有乒乓问题？", "跨维度分析",
            "OTA升级对缺陷有什么影响？", "测试效率分析",
            "ECU乒乓效应", "关联关系", "correlation analysis",
            "关联", "ECU乒乓", "OTA影响", "测试效率",
            "跨维度", "关联发现", "隐藏关联",
            "有没有关联模式？", "哪些因素相关联",
            "association analysis", "cross dimension",
            "correlation", "related factors", "co-occurrence",
            "OTA升级后缺陷变化", "关联规则",
            "跨维度关联", "ECU间传递",
            "什么因素相互关联", "关联挖掘",
            "association mining", "pattern discovery",
            "有没有共同出现的模式", "哪些维度有关联",
            "OTA后缺陷有没有增加", "跨模块关联"
        ],
        'strategy': [
            "测试策略评估", "我们测试做得怎么样？", "测试策略怎么样",
            "测试好不好", "test strategy evaluation",
            "测试质量评估", "综合评估", "策略评估",
            "测试策略", "整体评估", "测试效果",
            "测试体系评估", "测试成熟度",
            "how is our testing", "test strategy", "test evaluation",
            "testing assessment", "overall testing quality",
            "测试能力", "测试水平", "测得好不好",
            "测试做的如何", "测试整体情况",
            "测试体系怎么样", "我们的测试怎么样",
            "strategy evaluation", "test maturity"
        ],
        'predict': [
            "预测下个月缺陷数量", "未来趋势怎么样", "风险预判",
            "预判", "预测", "未来", "趋势预测",
            "下个月", "predict", "forecast", "future",
            "会怎样", "接下来会怎样", "未来会怎样",
            "缺陷会变多吗", "风险会加大吗",
            "predictive risk", "risk prediction",
            "下个版本", "下个迭代", "风险预测",
            "将来", "后面", "后续趋势",
            "预计缺陷", "预测新增", "趋势外推",
            "会不会恶化", "会继续恶化吗",
            "未来30天", "未来一个月", "下个月会怎样"
        ]
    }

    # 置信度阈值
    CONFIDENCE_HIGH = 0.5
    CONFIDENCE_LOW = 0.3
    CONFIDENCE_CLARIFICATION = 0.2

    def __init__(self):
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._intent_vectors: Dict[str, any] = {}
        self._fitted = False

        if SKLEARN_AVAILABLE:
            self._build_vectors()

    def _preprocess_text(self, text: str) -> str:
        """文本预处理"""
        if not text:
            return ""
        # 转换为小写
        text = text.lower()
        # 移除非字母数字字符，保留中文
        text = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', text)
        # 合并多个空格
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _build_vectors(self):
        """构建意图示例的TF-IDF向量"""
        if not SKLEARN_AVAILABLE:
            return

        try:
            # 为每个意图构建向量
            all_examples = []
            intent_boundaries = {}
            current_idx = 0

            for intent, examples in self.INTENT_EXAMPLES.items():
                intent_boundaries[intent] = (current_idx, current_idx + len(examples))
                for example in examples:
                    all_examples.append(self._preprocess_text(example))
                current_idx += len(examples)

            if not all_examples:
                logger.warning("No intent examples available")
                return

            # 创建向量化器 - 使用字符n-grams以更好地处理中英文混合
            self._vectorizer = TfidfVectorizer(
                analyzer='char_wb',
                ngram_range=(2, 4),
                max_features=10000,
                lowercase=True
            )

            # 拟合所有示例
            self._vectorizer.fit(all_examples)

            # 为每个意图存储其示例的向量
            for intent, (start, end) in intent_boundaries.items():
                intent_examples = [ex for ex in all_examples[start:end] if ex.strip()]
                if intent_examples:
                    self._intent_vectors[intent] = self._vectorizer.transform(intent_examples)

            self._fitted = True
            logger.info(f"SemanticIntentDetector initialized with {len(self.INTENT_EXAMPLES)} intents")

        except Exception as e:
            logger.error(f"Failed to build intent vectors: {e}")
            self._fitted = False

    def detect_intent(self, question: str) -> List[Tuple[str, float]]:
        """
        检测用户问题的意图

        Args:
            question: 用户问题

        Returns:
            List of (intent, confidence) tuples, sorted by confidence descending
        """
        if not question or not question.strip():
            return [('clarification', 0.0)]

        # 如果sklearn不可用，回退到关键词匹配
        if not SKLEARN_AVAILABLE or not self._fitted:
            return self._fallback_keyword_detection(question)

        try:
            # 预处理问题
            processed_question = self._preprocess_text(question)
            if not processed_question:
                return [('clarification', 0.0)]

            # 向量化问题
            question_vector = self._vectorizer.transform([processed_question])

            # 计算与每个意图的相似度
            intent_scores = {}
            for intent, intent_matrix in self._intent_vectors.items():
                # 计算与所有示例的相似度
                similarities = cosine_similarity(question_vector, intent_matrix).flatten()
                # 如果没有相似度数据（意图矩阵为空），跳过
                if len(similarities) == 0:
                    continue
                # 使用最高相似度作为意图得分
                max_sim = float(similarities.max())
                # 也考虑平均相似度（前3个）
                top_k = min(3, len(similarities))
                avg_top_sim = float(sum(sorted(similarities, reverse=True)[:top_k]) / top_k) if top_k > 0 else 0
                # 综合得分：最高相似度占70%，平均占30%
                final_score = max_sim * 0.7 + avg_top_sim * 0.3
                intent_scores[intent] = final_score

            # 排序并返回top-2意图
            sorted_intents = sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)

            # 如果最高相似度低于阈值，返回clarification
            if not sorted_intents or sorted_intents[0][1] < self.CONFIDENCE_LOW:
                return [('clarification', sorted_intents[0][1] if sorted_intents else 0.0)]

            # 返回top-2意图（如果第二个的置信度也足够高）
            results = [sorted_intents[0]]
            if len(sorted_intents) > 1 and sorted_intents[1][1] >= self.CONFIDENCE_HIGH:
                results.append(sorted_intents[1])

            return results

        except Exception as e:
            logger.error(f"Semantic intent detection failed: {e}")
            return self._fallback_keyword_detection(question)

    def detect_intents_with_details(self, question: str) -> Dict[str, any]:
        """
        详细意图检测，返回完整信息

        Args:
            question: 用户问题

        Returns:
            Dictionary with intents, confidences, and recommendations
        """
        intents = self.detect_intent(question)

        primary_intent = intents[0][0]
        primary_confidence = intents[0][1]

        result = {
            'intents': intents,
            'primary_intent': primary_intent,
            'primary_confidence': primary_confidence,
            'needs_clarification': primary_intent == 'clarification',
            'clarification_question': None,
            'all_scores': {}
        }

        # 如果需要澄清，生成澄清问题
        if result['needs_clarification']:
            result['clarification_question'] = self._generate_clarification_question(question)

        # 记录所有意图的分数（用于调试）
        if SKLEARN_AVAILABLE and self._fitted:
            try:
                processed = self._preprocess_text(question)
                if processed:
                    qv = self._vectorizer.transform([processed])
                    for intent, im in self._intent_vectors.items():
                        sims = cosine_similarity(qv, im).flatten()
                        if len(sims) > 0:
                            result['all_scores'][intent] = {
                                'max': float(sims.max()),
                                'mean': float(sims.mean())
                            }
            except Exception:
                pass

        return result

    def _fallback_keyword_detection(self, question: str) -> List[Tuple[str, float]]:
        """
        关键词匹配回退方案
        """
        question_lower = question.lower()
        scores = {}

        keyword_patterns = {
            'trend': ['trend', 'change', 'evolution', 'over time', 'history', 'status history', 'change history', 'change log', '趋势', '变化', '演变', '历史', '增长', '走势', '流转历史', '状态变更', '状态流转', '变更记录'],
            'risk': ['risk', 'critical', 'severe', 'topissue', 'high priority', '风险', '严重', '高优先级', '紧急'],
            'comparison': ['compare', 'versus', 'vs', 'difference', 'between', '对比', '比较', '差异', 'vs'],
            'summary': ['summary', 'overview', 'total', 'overall', '总结', '概览', '整体', '概况'],
            'quality': ['quality', 'age', 'transfer', 'complexity', '质量', '年龄', '转移', '复杂度', '效率'],
            'test': ['test', 'coverage', 'pass', 'fail', 'testcase', 'testcases', 'test case', 'test cases', '测试', '测试用例', '用例', '覆盖率', '通过', '失败', '执行'],
            'dashboard': ['dashboard', 'kpi', 'metrics', '看板', '指标', '图表', '汇总'],
            'matrix': ['matrix', '1a', '1b', '矩阵', '象限', '分布'],
            'cross': ['cross', 'correlation', 'associate', '关联', '综合', '交叉', '对比'],
            'tester': ['tester', 'performance', 'productivity', '测试人员', '效率', '团队'],
            'anomaly': ['anomaly', 'spike', 'outlier', '异常', '突增', '突降', '不正常', '反常', '异常检测'],
            'root_cause': ['root cause', 'why', 'cause', '根因', '为什么', '原因', '根源', '是什么导致'],
            'risk_eval': ['risk heatmap', 'risk score', '风险热力图', '风险评分', '模块风险', '风险评估', '哪里风险'],
            'coverage': ['coverage gap', '覆盖差距', '测试盲区', '缺什么用例', '覆盖', '测试够不够', 'test coverage'],
            'association': ['association', 'correlation', '关联', 'ecu乒乓', 'ota影响', '跨维度', '关联分析', '测试效率'],
            'strategy': ['test strategy', '策略评估', '测试策略', '测试做得怎么样', '测试好不好', '测试成熟度', '综合评估', 'testing quality'],
            'predict': ['predict', 'forecast', '预测', '预判', '未来', '下个月', '趋势预测', '会怎样', '风险预测']
        }

        for intent, keywords in keyword_patterns.items():
            score = sum(1 for kw in keywords if kw in question_lower)
            if score > 0:
                scores[intent] = min(1.0, score / 3)  # 归一化到0-1

        if not scores:
            return [('summary', 0.3)]  # 默认返回summary

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:2]

    def _generate_clarification_question(self, question: str) -> str:
        """
        生成澄清问题
        """
        # 分析问题中的关键词
        has_project = any(p in question.lower() for p in ['project', '项目', 'g', 'f', 'i', 'u'])
        has_time = any(t in question.lower() for t in ['time', 'date', '最近', '本周', '本月', '趋势'])
        has_metric = any(m in question.lower() for m in ['defect', 'bug', 'issue', 'test', '缺陷', '测试'])

        suggestions = []
        if not has_project:
            suggestions.append("指定项目（如G01、G20）")
        if not has_time:
            suggestions.append("时间范围（如最近一周、本月）")
        if not has_metric:
            suggestions.append("分析维度（如缺陷、测试、风险）")

        if suggestions:
            return f"抱歉，我没有完全理解您的问题。您可以尝试补充以下信息：{', '.join(suggestions)}"
        else:
            return "抱歉，我没有完全理解您的问题。您可以换个方式描述，或者从预设问题中选择。"

    def get_intent_description(self, intent: str) -> str:
        """获取意图描述"""
        descriptions = {
            'risk': '风险分析 - 识别高风险缺陷和问题',
            'comparison': '对比分析 - 比较不同项目/维度',
            'trend': '趋势分析 - 分析时间变化趋势',
            'summary': '数据摘要 - 生成整体概览',
            'quality': '质量分析 - 评估缺陷质量和处理效率',
            'test': '测试分析 - 分析测试覆盖率和执行',
            'dashboard': '看板指标 - 汇总KPI和业务图表',
            'matrix': '矩阵分析 - 分析严重性和优先级矩阵',
            'cross': '交叉分析 - 关联多维度数据',
            'tester': '人员分析 - 分析测试人员效率',
            'anomaly': '异常检测 - 识别时序数据中的异常模式',
            'root_cause': '根因分析 - 多维度深度分析缺陷根因',
            'risk_eval': '风险热力图 - 模块风险评分与测试优先级',
            'coverage': '覆盖差距 - 测试覆盖分析与用例推荐',
            'association': '关联发现 - 跨维度关联模式挖掘',
            'strategy': '策略评估 - 测试策略综合评估与成熟度评分',
            'predict': '风险预判 - 基于趋势预测未来风险分布',
            'clarification': '需要澄清 - 意图不明确'
        }
        return descriptions.get(intent, '未知意图')


# 工厂函数
def create_semantic_intent_detector() -> SemanticIntentDetector:
    """创建语义意图检测器实例"""
    return SemanticIntentDetector()


# 兼容性函数 - 与原有关键词检测兼容
def detect_intents_semantic(question: str) -> List[str]:
    """
    兼容原有接口的意图检测函数

    Args:
        question: 用户问题

    Returns:
        List of intent strings
    """
    detector = create_semantic_intent_detector()
    results = detector.detect_intent(question)
    return [intent for intent, _ in results]


# 测试代码
if __name__ == "__main__":
    print("Semantic Intent Detector Test")
    print("=" * 50)

    detector = create_semantic_intent_detector()

    test_questions = [
        "idcevo风险如何？",
        "G01和G20哪个项目缺陷多？",
        "最近一周的趋势如何？",
        "总结一下当前数据",
        "测试覆盖率怎么样？",
        "矩阵分布情况",
        "哪些测试人员效率最高？",
        "看不懂的问题xyz123"  # 测试低置信度
    ]

    for q in test_questions:
        print(f"\n问题: {q}")
        result = detector.detect_intents_with_details(q)
        print(f"  主要意图: {result['primary_intent']} (置信度: {result['primary_confidence']:.3f})")
        print(f"  所有意图: {result['intents']}")
        if result['needs_clarification']:
            print(f"  澄清建议: {result['clarification_question']}")

    print("\n" + "=" * 50)
    print("测试完成!")

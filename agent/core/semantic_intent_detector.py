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
            "风险", "严重", "紧急", "critical", "high risk"
        ],
        'comparison': [
            "idcevo和mgu对比", "哪个项目缺陷多？", "vs比较",
            "G01和G20哪个更严重？", "对比两个项目的测试情况",
            "哪个ECU的问题最多？", "横向对比各项目",
            "compare projects", "versus", "vs", "difference between",
            "which project has more defects", "comparison analysis",
            "对比", "比较", "vs", "差异", "哪个更多"
        ],
        'trend': [
            "最近趋势如何？", "缺陷增长了吗？", "历史走势",
            "本周新增多少缺陷？", "月度趋势分析", "时间变化",
            "缺陷数量在上升吗？", "过去一个月的趋势",
            "trend analysis", "over time", "historical trend",
            "growth pattern", "weekly trend", "monthly change",
            "趋势", "变化", "增长", "走势", "历史"
        ],
        'summary': [
            "总结一下", "当前整体情况", "数据概览",
            "总体分析", "给我一个概况", "整体统计",
            "summary", "overview", "overall status", "general picture",
            "high level summary", "total count", "statistics",
            "总结", "概览", "整体", "概况", "统计"
        ],
        'quality': [
            "缺陷质量如何？", "平均处理时间？", "转移次数分析",
            "哪些缺陷处理太慢？", "缺陷年龄分布", "复杂度分析",
            "缺陷处理效率", "响应时间分析",
            "quality analysis", "defect age", "transfer count",
            "processing time", "complexity", "efficiency",
            "质量", "年龄", "转移", "效率", "处理时间"
        ],
        'test': [
            "测试覆盖率如何？", "通过率怎么样？", "失败测试分析",
            "哪些测试失败了？", "测试执行情况", "测试趋势",
            "测试效率", "测试质量",
            "test coverage", "pass rate", "failure analysis",
            "test execution", "test results", "testing trend",
            "测试", "覆盖率", "通过率", "失败", "执行"
        ],
        'dashboard': [
            "看板指标", "KPI数据", "关键指标",
            "业务图表", "汇总数据", "核心指标",
            "dashboard metrics", "kpi summary", "key indicators",
            "business charts", "overview metrics",
            "看板", "指标", "KPI", "图表", "汇总"
        ],
        'matrix': [
            "矩阵分布", "1A缺陷有多少？", "矩阵热点分析",
            "哪些矩阵区域问题多？", "严重性和优先级矩阵",
            "matrix distribution", "1A defects", "matrix hotspots",
            "severity priority matrix", "quadrant analysis",
            "矩阵", "1A", "1B", "热点", "分布"
        ],
        'cross': [
            "缺陷和测试关联", "综合风险分析", "缺陷测试对比",
            "关联分析", "cross analysis", "defect test correlation",
            "关联", "综合", "交叉", "对比"
        ],
        'tester': [
            "测试人员效率", "谁发现最多缺陷？", "tester分析",
            "测试团队表现", "个人产出分析",
            "tester performance", "who found most defects",
            "testing team analysis", "individual productivity",
            "测试人员", "效率", "发现", "产出", "团队"
        ]
    }

    # 置信度阈值
    CONFIDENCE_HIGH = 0.6
    CONFIDENCE_LOW = 0.4
    CONFIDENCE_CLARIFICATION = 0.25

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
            'trend': ['trend', 'change', 'evolution', 'over time', 'history', '趋势', '变化', '演变', '历史', '增长', '走势'],
            'risk': ['risk', 'critical', 'severe', 'topissue', 'high priority', '风险', '严重', '高优先级', '紧急'],
            'comparison': ['compare', 'versus', 'vs', 'difference', 'between', '对比', '比较', '差异', 'vs'],
            'summary': ['summary', 'overview', 'total', 'overall', '总结', '概览', '整体', '概况'],
            'quality': ['quality', 'age', 'transfer', 'complexity', '质量', '年龄', '转移', '复杂度', '效率'],
            'test': ['test', 'coverage', 'pass', 'fail', '测试', '覆盖率', '通过', '失败', '执行'],
            'dashboard': ['dashboard', 'kpi', 'metrics', '看板', '指标', '图表', '汇总'],
            'matrix': ['matrix', '1a', '1b', '矩阵', '象限', '分布'],
            'cross': ['cross', 'correlation', 'associate', '关联', '综合', '交叉', '对比'],
            'tester': ['tester', 'performance', 'productivity', '测试人员', '效率', '团队']
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

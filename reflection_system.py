"""
自我反思机制 - Reflection Loop

实现 Agent 的自我反思能力：
1. 执行任务
2. 验证结果
3. 反思问题
4. 改进方案
5. 置信度评估

参考 Manus AI 和 Claude Code 的最佳实践

作者: AI Assistant
日期: 2025-01-19
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re

logger = logging.getLogger(__name__)


# ============================================================================
# 枚举和数据类
# ============================================================================

class ReflectionStatus(Enum):
    """反思状态"""
    PENDING = "pending"
    VALIDATED = "validated"
    NEEDS_IMPROVEMENT = "needs_improvement"
    FAILED = "failed"
    COMPLETED = "completed"


@dataclass
class ValidationResult:
    """验证结果"""
    passed: bool
    score: float  # 0-1
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


@dataclass
class ReflectionResult:
    """反思结果"""
    original_output: Any
    issues_found: List[str]
    improvements: List[str]
    refined_output: Any
    confidence: float
    iterations: int
    status: ReflectionStatus


@dataclass
class ReflectionContext:
    """反思上下文"""
    question: str
    original_output: Any
    validation_result: Optional[ValidationResult] = None
    previous_reflections: List[Dict] = field(default_factory=list)
    max_iterations: int = 3


# ============================================================================
# 验证器
# ============================================================================

class OutputValidator:
    """输出验证器"""
    
    def __init__(self):
        self.rules: List[Callable] = []
        self._register_default_rules()
    
    def _register_default_rules(self):
        """注册默认验证规则"""
        self.rules = [
            self._check_completeness,
            self._check_relevance,
            self._check_accuracy,
            self._check_clarity,
        ]
    
    def validate(self, question: str, output: Any) -> ValidationResult:
        """
        验证输出
        
        Args:
            question: 原始问题
            output: Agent 输出
            
        Returns:
            ValidationResult
        """
        issues = []
        suggestions = []
        scores = []
        
        for rule in self.rules:
            try:
                passed, score, issue, suggestion = rule(question, output)
                scores.append(score)
                if not passed:
                    issues.append(issue)
                    if suggestion:
                        suggestions.append(suggestion)
            except Exception as e:
                logger.warning(f"验证规则 {rule.__name__} 执行失败: {e}")
                scores.append(0.5)
        
        avg_score = sum(scores) / len(scores) if scores else 0.5
        passed = avg_score >= 0.7 and len(issues) < 2
        
        return ValidationResult(
            passed=passed,
            score=avg_score,
            issues=issues,
            suggestions=suggestions
        )
    
    def _check_completeness(self, question: str, output: Any) -> Tuple[bool, float, str, str]:
        """检查完整性"""
        if output is None:
            return False, 0.0, "输出为空", "请生成有意义的输出"
        
        output_str = str(output)
        
        # 检查是否有实际内容
        if len(output_str.strip()) < 10:
            return False, 0.3, "输出内容过短", "请提供更详细的回答"
        
        # 检查是否回答了问题
        question_keywords = set(re.findall(r'\w+', question.lower()))
        output_keywords = set(re.findall(r'\w+', output_str.lower()))
        
        overlap = len(question_keywords & output_keywords) / max(len(question_keywords), 1)
        
        if overlap < 0.1:
            return False, 0.5, "输出与问题相关性不足", "请确保回答与问题相关"
        
        return True, 0.8, "", ""
    
    def _check_relevance(self, question: str, output: Any) -> Tuple[bool, float, str, str]:
        """检查相关性"""
        output_str = str(output)
        
        # 检查关键实体是否出现
        question_entities = re.findall(r'[A-Z]{2,}|\d+', question)
        output_entities = re.findall(r'[A-Z]{2,}|\d+', output_str)
        
        if question_entities:
            matched = sum(1 for e in question_entities if e in output_str)
            relevance = matched / len(question_entities)
            
            if relevance < 0.3:
                return False, 0.4, "关键实体缺失", "请在输出中提及问题中的关键信息"
            
            return True, relevance, "", ""
        
        return True, 0.7, "", ""
    
    def _check_accuracy(self, question: str, output: Any) -> Tuple[bool, float, str, str]:
        """检查准确性"""
        output_str = str(output)
        
        # 检查是否有明显错误标记
        error_patterns = [
            r'\berror\b',
            r'\bfailed\b',
            r'\b无法\b',
            r'\b错误\b',
            r'\b失败\b',
        ]
        
        error_count = sum(1 for p in error_patterns if re.search(p, output_str, re.IGNORECASE))
        
        # 如果有很多错误标记，可能是有问题的
        if error_count > 3:
            return True, 0.6, "输出包含较多错误标记", "请检查是否正确处理了数据"
        
        return True, 0.9, "", ""
    
    def _check_clarity(self, question: str, output: Any) -> Tuple[bool, float, str, str]:
        """检查清晰度"""
        output_str = str(output)
        
        # 检查结构
        has_structure = any([
            '\n-' in output_str,
            '\n*' in output_str,
            '\n1.' in output_str,
            '\n##' in output_str,
            '"key"' in output_str.lower() or "'key'" in output_str.lower(),
        ])
        
        # 检查长度是否合适
        length_score = 1.0 if 50 < len(output_str) < 5000 else 0.7
        
        score = 0.8 if has_structure else 0.5
        score *= length_score
        
        if not has_structure and len(output_str) > 200:
            return True, 0.6, "输出缺乏结构", "建议使用列表或分节提高可读性"
        
        return True, score, "", ""


# ============================================================================
# 反思器
# ============================================================================

class Reflector:
    """反思器"""
    
    def __init__(self):
        self.reflection_strategies = {
            "completeness": self._reflect_on_completeness,
            "relevance": self._reflect_on_relevance,
            "accuracy": self._reflect_on_accuracy,
            "clarity": self._reflect_on_clarity,
        }
    
    def reflect(
        self,
        question: str,
        output: Any,
        validation: ValidationResult
    ) -> Tuple[List[str], List[str]]:
        """
        反思输出
        
        Args:
            question: 原始问题
            output: 当前输出
            validation: 验证结果
            
        Returns:
            (问题列表, 改进建议列表)
        """
        issues = list(validation.issues)
        improvements = list(validation.suggestions)
        
        # 根据验证分数决定反思深度
        if validation.score < 0.5:
            # 需要深度反思
            for strategy_name, strategy in self.reflection_strategies.items():
                try:
                    found_issues, suggested_improvements = strategy(question, output, validation)
                    issues.extend(found_issues)
                    improvements.extend(suggested_improvements)
                except Exception as e:
                    logger.warning(f"反思策略 {strategy_name} 执行失败: {e}")
        
        # 去重
        issues = list(dict.fromkeys(issues))
        improvements = list(dict.fromkeys(improvements))
        
        return issues, improvements
    
    def _reflect_on_completeness(
        self,
        question: str,
        output: Any,
        validation: ValidationResult
    ) -> Tuple[List[str], List[str]]:
        """完整性反思"""
        issues = []
        improvements = []
        
        # 检查是否回答了问题的所有方面
        question_aspects = []
        
        if "趋势" in question:
            question_aspects.append("趋势分析")
        if "风险" in question:
            question_aspects.append("风险评估")
        if "策略" in question or "建议" in question:
            question_aspects.append("策略建议")
        if "对比" in question:
            question_aspects.append("对比分析")
        
        output_str = str(output)
        
        for aspect in question_aspects:
            if aspect.split("分析")[0].split("评估")[0].split("建议")[0] not in output_str:
                issues.append(f"缺少{aspect}")
                improvements.append(f"请补充{aspect}相关内容")
        
        return issues, improvements
    
    def _reflect_on_relevance(
        self,
        question: str,
        output: Any,
        validation: ValidationResult
    ) -> Tuple[List[str], List[str]]:
        """相关性反思"""
        issues = []
        improvements = []
        
        # 提取问题中的关键项目/模块
        projects = re.findall(r'[A-Z]{2,}', question)
        output_str = str(output)
        
        for project in projects:
            if project not in output_str and len(project) > 2:
                issues.append(f"未提及项目 {project}")
                improvements.append(f"请在分析中包含 {project} 的数据")
        
        return issues, improvements
    
    def _reflect_on_accuracy(
        self,
        question: str,
        output: Any,
        validation: ValidationResult
    ) -> Tuple[List[str], List[str]]:
        """准确性反思"""
        issues = []
        improvements = []
        
        output_str = str(output)
        
        # 检查数字是否合理
        numbers = re.findall(r'\d+(?:\.\d+)?%?', output_str)
        
        for num_str in numbers:
            try:
                if '%' in num_str:
                    num = float(num_str.replace('%', ''))
                    if num > 100:
                        issues.append(f"百分比值异常: {num_str}")
                        improvements.append("请检查百分比计算是否正确")
                elif float(num_str) > 1000000:
                    issues.append(f"数值可能过大: {num_str}")
                    improvements.append("请验证数值计算")
            except ValueError:
                pass
        
        return issues, improvements
    
    def _reflect_on_clarity(
        self,
        question: str,
        output: Any,
        validation: ValidationResult
    ) -> Tuple[List[str], List[str]]:
        """清晰度反思"""
        issues = []
        improvements = []
        
        output_str = str(output)
        
        # 检查是否有过长的段落
        paragraphs = output_str.split('\n\n')
        
        for i, para in enumerate(paragraphs):
            if len(para) > 500:
                issues.append(f"第 {i+1} 段过长")
                improvements.append("建议将长段落拆分为多个小段落")
        
        return issues, improvements


# ============================================================================
# 反思循环
# ============================================================================

class ReflectionLoop:
    """
    反思循环
    
    执行 → 验证 → 反思 → 改进 → 置信度评估
    """
    
    def __init__(self, max_iterations: int = 3, min_confidence: float = 0.7):
        """
        初始化
        
        Args:
            max_iterations: 最大迭代次数
            min_confidence: 最低置信度阈值
        """
        self.max_iterations = max_iterations
        self.min_confidence = min_confidence
        self.validator = OutputValidator()
        self.reflector = Reflector()
    
    def execute_with_reflection(
        self,
        question: str,
        execute_func: Callable,
        context: Optional[Dict] = None
    ) -> ReflectionResult:
        """
        执行任务并进行反思
        
        Args:
            question: 用户问题
            execute_func: 执行函数，接收问题返回输出
            context: 额外上下文
            
        Returns:
            ReflectionResult
        """
        iterations = 0
        output = None
        all_issues = []
        all_improvements = []
        previous_reflections = []
        
        while iterations < self.max_iterations:
            iterations += 1
            
            # 执行
            try:
                output = execute_func(question, context, previous_reflections)
            except Exception as e:
                logger.error(f"执行失败: {e}")
                return ReflectionResult(
                    original_output=None,
                    issues_found=[f"执行错误: {str(e)}"],
                    improvements=[],
                    refined_output=None,
                    confidence=0.0,
                    iterations=iterations,
                    status=ReflectionStatus.FAILED
                )
            
            # 验证
            validation = self.validator.validate(question, output)
            
            # 记录反思
            reflection_record = {
                "iteration": iterations,
                "validation_score": validation.score,
                "issues": validation.issues,
                "passed": validation.passed
            }
            previous_reflections.append(reflection_record)
            
            # 判断是否通过
            if validation.passed and validation.score >= self.min_confidence:
                return ReflectionResult(
                    original_output=output,
                    issues_found=all_issues,
                    improvements=all_improvements,
                    refined_output=output,
                    confidence=validation.score,
                    iterations=iterations,
                    status=ReflectionStatus.COMPLETED
                )
            
            # 反思
            issues, improvements = self.reflector.reflect(question, output, validation)
            all_issues.extend(issues)
            all_improvements.extend(improvements)
            
            # 更新上下文用于下一次迭代
            if context is None:
                context = {}
            context["reflection_feedback"] = {
                "issues": issues,
                "improvements": improvements
            }
        
        # 达到最大迭代次数
        return ReflectionResult(
            original_output=output,
            issues_found=all_issues,
            improvements=all_improvements,
            refined_output=output,
            confidence=validation.score,
            iterations=iterations,
            status=ReflectionStatus.NEEDS_IMPROVEMENT if validation.score > 0.5 else ReflectionStatus.FAILED
        )
    
    def quick_validate(self, question: str, output: Any) -> float:
        """快速验证输出质量"""
        validation = self.validator.validate(question, output)
        return validation.score


# ============================================================================
# 集成到 Agent
# ============================================================================

class ReflectiveAgent:
    """
    带反思能力的 Agent 包装器
    
    可以包装任何 Agent，添加自我反思能力
    """
    
    def __init__(self, base_agent: Any, max_iterations: int = 3):
        """
        初始化
        
        Args:
            base_agent: 基础 Agent
            max_iterations: 最大反思迭代次数
        """
        self.base_agent = base_agent
        self.reflection_loop = ReflectionLoop(max_iterations=max_iterations)
    
    def run(self, question: str, context: Optional[Dict] = None) -> ReflectionResult:
        """执行并反思"""
        
        def execute_func(q, ctx, prev_reflections):
            # 将反思信息传递给基础 Agent
            if ctx is None:
                ctx = {}
            ctx["previous_reflections"] = prev_reflections
            
            # 调用基础 Agent
            result = self.base_agent.run(q, ctx)
            
            # 提取输出
            if hasattr(result, 'output'):
                return result.output
            return result
        
        return self.reflection_loop.execute_with_reflection(
            question=question,
            execute_func=execute_func,
            context=context
        )


# ============================================================================
# 工厂函数
# ============================================================================

def create_reflection_loop(max_iterations: int = 3, min_confidence: float = 0.7) -> ReflectionLoop:
    """创建反思循环"""
    return ReflectionLoop(max_iterations=max_iterations, min_confidence=min_confidence)


def add_reflection_to_agent(agent: Any, max_iterations: int = 3) -> ReflectiveAgent:
    """为 Agent 添加反思能力"""
    return ReflectiveAgent(agent, max_iterations=max_iterations)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("自我反思机制测试")
    print("=" * 70)
    
    # 创建反思循环
    loop = create_reflection_loop(max_iterations=3)
    
    # 模拟执行函数
    def mock_execute(question: str, context: Dict = None, reflections: List = None) -> str:
        """模拟执行"""
        if reflections and len(reflections) > 0:
            # 有反思记录，尝试改进
            return f"改进后的回答：针对 '{question}' 的分析结果..."
        else:
            # 首次执行
            return f"对 '{question}' 的初步分析..."
    
    # 测试
    question = "最近两周 ABS 模块的缺陷趋势分析"
    print(f"\n问题: {question}")
    
    result = loop.execute_with_reflection(
        question=question,
        execute_func=mock_execute
    )
    
    print(f"\n结果:")
    print(f"  - 状态: {result.status.value}")
    print(f"  - 置信度: {result.confidence:.2f}")
    print(f"  - 迭代次数: {result.iterations}")
    print(f"  - 发现问题: {result.issues_found}")
    print(f"  - 改进建议: {result.improvements}")

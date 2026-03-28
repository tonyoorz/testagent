#!/usr/bin/env python3
"""
增强的 SQL Prompt 构建器

优化 Prompt 以提高 SQL 生成准确率（目标：85% → 90%+）

优化策略：
1. 更清晰的 System Prompt 和任务定义
2. 增强的业务规则和约束
3. 优化的 Few-shot 示例展示
4. 添加 SQL 质量检查提示
5. 错误分析和自学习机制

作者: Jarvis (OpenClaw Agent)
日期: 2026-03-29
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


# ============================================================================
# Prompt 优化配置
# ============================================================================

@dataclass
class PromptOptimizationConfig:
    """Prompt 优化配置"""
    include_thinking_process: bool = True      # 包含思考过程
    include_quality_checks: bool = True         # 包含质量检查
    include_common_errors: bool = True          # 包含常见错误
    include_best_practices: bool = True         # 包含最佳实践
    few_shot_examples_count: int = 7           # Few-shot 示例数量（从5增加到7）
    use_structured_examples: bool = True        # 使用结构化示例格式


# ============================================================================
# 增强的业务规则
# ============================================================================

class EnhancedBusinessRules:
    """增强的业务规则库"""

    RULES = """
## SQL 查询最佳实践

### 1. 数据选择原则
- ✅ 优先使用 SELECT column_name 而非 SELECT *（除非需要所有列）
- ✅ 使用 LIMIT 限制返回行数（建议：10-100 行）
- ✅ 使用 ORDER BY 确保结果可预测
- ❌ 避免 SELECT * 除非用户明确要求"所有字段"

### 2. 时间过滤规则
- 使用 date('now') 获取当前日期
- 使用 date('now', '-7 days') 获取7天前的日期
- 使用 date('now', '-30 days') 获取30天前的日期
- 使用 strftime('%Y-%m', creation_time) 按月分组
- 使用 strftime('%Y-W%W', creation_time) 按周分组
- 使用 DATE(start_time) 按日分组

### 3. 聚合函数使用
- COUNT(*) - 计数
- SUM(column) - 求和
- AVG(column) - 平均值
- MAX(column) - 最大值
- MIN(column) - 最小值
- ROUND(value, decimals) - 四舍五入

### 4. 百分比计算
使用 NULLIF 防止除零错误：
```sql
SELECT ROUND(100.0 * SUM(condition) / NULLIF(COUNT(*), 0), 2)
```

### 5. JOIN 使用原则
- 优先使用 INNER JOIN（只返回匹配的行）
- 需要包含不匹配的行时使用 LEFT JOIN
- JOIN 条件应该基于关联字段（如 build_number, project, module）
- 多表 JOIN 时注意性能，使用 LIMIT

### 6. 子查询使用场景
- 需要聚合结果后再过滤（HAVING 不够用时）
- 需要比较聚合值（如超过平均值）
- 需要计算比率或排名
- NOT EXISTS / IN 用于检查是否存在

### 7. 窗口函数使用场景
- ROW_NUMBER() - 每个分组内的行号
- RANK() - 排名（相同值排名相同，跳过后续排名）
- LAG(col, n) - 获取前 n 行的值
- LEAD(col, n) - 获取后 n 行的值
- SUM() OVER - 累计和

### 8. 分组和排序
- GROUP BY 应该包含所有非聚合列
- ORDER BY 默认升序，DESC 表示降序
- 多列排序：ORDER BY col1, col2 DESC
- 复杂排序：ORDER BY CASE WHEN ... END

### 9. 条件表达式
- CASE WHEN condition THEN result ELSE default END
- 多个 WHEN 条件按顺序判断
- 可以用于复杂的排序逻辑

### 10. 常见错误规避
❌ 错误：SELECT * FROM defects GROUP BY module
✅ 正确：SELECT module, COUNT(*) FROM defects GROUP BY module

❌ 错误：SELECT COUNT(*) / SUM(condition)
✅ 正确：SELECT ROUND(COUNT(*) * 100.0 / NULLIF(SUM(condition), 0), 2)

❌ 错误：WHERE AVG(score) > 80
✅ 正确：WHERE score > (SELECT AVG(score) FROM table)

### 11. 性能优化提示
- 在 WHERE 子句中使用索引字段（如 id, build_number）
- 避免在 WHERE 中使用函数（如 WHERE YEAR(date) = 2024）
- 使用 LIMIT 限制返回行数
- 避免使用 SELECT *，明确指定列名

### 12. 业务逻辑映射
- "测试通过率" = (Passed 数量 / 总数量) * 100
- "缺陷密度" = 缺陷数量 / 测试数量
- "高风险" = severity IN ('Critical', 'Major') AND pingpong > 3
- "长期未修复" = status NOT IN ('Closed', 'Fixed') AND creation_time < date('now', '-30 days')
- "重开率高" = pingpong > 平均重开次数
"""

    @classmethod
    def get_rules(cls) -> str:
        """获取增强的业务规则"""
        return cls.RULES


# ============================================================================
# 常见错误模式
# ============================================================================

class CommonErrorPatterns:
    """常见 SQL 错误模式"""

    ERRORS = """
## 常见 SQL 错误及修正

### 错误 1: GROUP BY 中包含非聚合列
❌ 错误示例：
```sql
SELECT module, severity, COUNT(*)
FROM defects
GROUP BY module
```
✅ 修正：所有非聚合列都要包含在 GROUP BY 中
```sql
SELECT module, severity, COUNT(*)
FROM defects
GROUP BY module, severity
```

### 错误 2: 在 WHERE 中使用聚合函数
❌ 错误示例：
```sql
SELECT module, COUNT(*)
FROM defects
WHERE COUNT(*) > 10
GROUP BY module
```
✅ 修正：使用 HAVING 子句
```sql
SELECT module, COUNT(*)
FROM defects
GROUP BY module
HAVING COUNT(*) > 10
```

### 错误 3: 除零错误
❌ 错误示例：
```sql
SELECT 100.0 * SUM(condition) / COUNT(*)
```
✅ 修正：使用 NULLIF 防止除零
```sql
SELECT ROUND(100.0 * SUM(condition) / NULLIF(COUNT(*), 0), 2)
```

### 错误 4: 忘记 JOIN 条件
❌ 错误示例：
```sql
SELECT * FROM defects d JOIN test_runs tr
```
✅ 修正：添加 JOIN 条件
```sql
SELECT d.*, tr.*
FROM defects d
JOIN test_runs tr ON d.build_number = tr.build_number
```

### 错误 5: 时间范围错误
❌ 错误示例：
```sql
WHERE creation_time > '2024-01-01'
```
✅ 修正：使用 SQLite 日期函数
```sql
WHERE creation_time >= date('now', '-90 days')
```

### 错误 6: 混淆 WHERE 和 HAVING
- WHERE: 过滤行（在聚合前）
- HAVING: 过滤组（在聚合后）

### 错误 7: 忘记 LIMIT
❌ 错误示例：
```sql
SELECT * FROM defects ORDER BY creation_time DESC
```
✅ 修正：添加 LIMIT 限制结果数量
```sql
SELECT * FROM defects ORDER BY creation_time DESC LIMIT 10
```

### 错误 8: 子查询返回多行但用于单值比较
❌ 错误示例：
```sql
SELECT * FROM defects WHERE module = (SELECT module FROM test_runs)
```
✅ 修正：使用 IN 而非 =
```sql
SELECT * FROM defects WHERE module IN (SELECT DISTINCT module FROM test_runs)
```

### 错误 9: 错误的日期格式
❌ 错误示例：
```sql
WHERE creation_time = '2024-03-28'
```
✅ 修正：使用日期比较
```sql
WHERE DATE(creation_time) = date('now')
```

### 错误 10: 忽略 NULL 值
❌ 错误示例：
```sql
SELECT * FROM defects WHERE module = ''
```
✅ 修正：处理 NULL 值
```sql
SELECT * FROM defects WHERE (module IS NULL OR module = '')
```
"""

    @classmethod
    def get_errors(cls) -> str:
        """获取常见错误模式"""
        return cls.ERRORS


# ============================================================================
# 增强 Prompt 构建器
# ============================================================================

class EnhancedPromptBuilder:
    """增强的 Prompt 构建器"""

    def __init__(
        self,
        schema_manager,
        config: Optional[PromptOptimizationConfig] = None
    ):
        """
        初始化 Prompt 构建器

        Args:
            schema_manager: Schema 管理器
            config: 优化配置
        """
        self.schema_manager = schema_manager
        self.config = config or PromptOptimizationConfig()

    def build_prompt(
        self,
        question: str,
        data_context: Optional[str] = None,
        last_error: Optional[str] = None,
        attempt: int = 1
    ) -> str:
        """
        构建增强的 SQL 生成 Prompt

        Args:
            question: 用户问题
            data_context: 数据上下文
            last_error: 上次错误
            attempt: 尝试次数

        Returns:
            构建的 Prompt
        """
        from sql_query_engine import FewShotExamples, BusinessKnowledge

        prompt_parts = []

        # ========== 1. 系统提示 ==========
        prompt_parts.append(self._build_system_header())

        # ========== 2. 数据库 Schema ==========
        prompt_parts.append("\n## 数据库 Schema\n")
        prompt_parts.append(self.schema_manager.get_schema())

        # ========== 3. 增强的业务规则 ==========
        if self.config.include_best_practices:
            prompt_parts.append("\n## SQL 最佳实践\n")
            prompt_parts.append(EnhancedBusinessRules.get_rules())

        # ========== 4. 常见错误模式 ==========
        if self.config.include_common_errors and attempt > 1:
            prompt_parts.append("\n## 常见 SQL 错误\n")
            prompt_parts.append(CommonErrorPatterns.get_errors())

        # ========== 5. 查询示例（Few-shot） ==========
        prompt_parts.append(f"\n## 查询示例（学习这些模式）\n")
        if self.config.use_structured_examples:
            prompt_parts.append(FewShotExamples.get_examples(
                limit=self.config.few_shot_examples_count
            ))
        else:
            prompt_parts.append(FewShotExamples.get_examples(limit=5))

        # ========== 6. 相似问题参考 ==========
        similar_example = FewShotExamples.find_similar_example(question)
        if similar_example:
            prompt_parts.append("\n## 相似问题参考\n")
            prompt_parts.append(similar_example)

        # ========== 7. 数据上下文 ==========
        if data_context:
            prompt_parts.append("\n## 当前数据上下文\n")
            prompt_parts.append(data_context)

        # ========== 8. 历史错误 ==========
        if last_error:
            prompt_parts.append(f"\n## 上次错误\n{last_error}\n")
            if attempt > 1:
                prompt_parts.append("请仔细分析错误原因，修正 SQL。\n")

        # ========== 9. 思考过程（可选） ==========
        if self.config.include_thinking_process:
            prompt_parts.append("\n## 思考过程\n")
            prompt_parts.append(self._get_thinking_template())

        # ========== 10. 质量检查（可选） ==========
        if self.config.include_quality_checks:
            prompt_parts.append("\n## 质量检查清单\n")
            prompt_parts.append(self._get_quality_checklist())

        # ========== 11. 用户问题 ==========
        prompt_parts.append(f"\n## 用户问题\n{question}\n")

        # ========== 12. 输出要求 ==========
        prompt_parts.append("请生成 SQL 查询语句。")
        prompt_parts.append("要求：")
        prompt_parts.append("1. 只输出 SQL，不要任何解释或多余文字")
        prompt_parts.append("2. SQL 必须以 SELECT 开头")
        prompt_parts.append("3. 使用 LIMIT 限制返回行数（建议 10-100）")
        prompt_parts.append("4. 确保语法正确，避免常见错误")

        return "\n".join(prompt_parts)

    def _build_system_header(self) -> str:
        """构建系统头部提示"""
        return """# SQL 查询专家助手

你是一个专业的 SQL 查询专家，专门处理汽车测试数据库的查询任务。

## 核心能力
- 准确理解用户的自然语言问题
- 生成正确、高效的 SQL 查询语句
- 识别并避免常见的 SQL 错误
- 遵循 SQL 最佳实践和性能优化原则

## 任务要求
1. 仔细分析用户问题的意图
2. 根据 Schema 选择正确的表和字段
3. 使用适当的 SQL 特性（JOIN、子查询、窗口函数等）
4. 确保结果准确且符合业务逻辑
5. 限制返回行数以提高性能"""

    def _get_thinking_template(self) -> str:
        """获取思考过程模板"""
        return """在生成 SQL 之前，请先进行思考：

1. **分析问题意图**：用户想了解什么？
2. **选择数据表**：需要查询哪些表？为什么？
3. **确定查询类型**：是统计？分组？排序？还是关联？
4. **选择字段**：需要返回哪些列？
5. **应用条件**：需要哪些 WHERE 条件？
6. **考虑性能**：是否需要 LIMIT？是否有索引可用？
7. **检查约束**：是否符合业务规则？是否会除零？NULL 如何处理？

完成思考后，生成最终的 SQL 查询语句。"""

    def _get_quality_checklist(self) -> str:
        """获取质量检查清单"""
        return """生成 SQL 后，请检查：

✓ 是否以 SELECT 开头？
✓ GROUP BY 是否包含所有非聚合列？
✓ 百分比计算是否使用 NULLIF 防止除零？
✓ JOIN 是否有明确的 ON 条件？
✓ 时间范围是否使用 SQLite 日期函数？
✓ 是否添加了 LIMIT 限制返回行数？
✓ 是否处理了 NULL 值？
✓ ORDER BY 是否合理？
✓ 子查询是否返回预期结果？
✓ 整体逻辑是否符合问题意图？

确认无误后输出 SQL。"""


# ============================================================================
# 工厂函数
# ============================================================================

def create_enhanced_prompt_builder(schema_manager) -> EnhancedPromptBuilder:
    """
    创建增强的 Prompt 构建器

    Args:
        schema_manager: Schema 管理器

    Returns:
        EnhancedPromptBuilder 实例
    """
    config = PromptOptimizationConfig(
        include_thinking_process=True,
        include_quality_checks=True,
        include_common_errors=True,
        include_best_practices=True,
        few_shot_examples_count=7,
        use_structured_examples=True
    )

    return EnhancedPromptBuilder(schema_manager, config)

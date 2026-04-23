"""
Query Result Validator — SQL 执行结果后置校验

参照 Anthropic "Agentic Systems" 中 Evaluator-Optimizer 模式：
"One LLM call generates a response while another provides evaluation and feedback."

本模块是确定性校验层（无需 LLM），检查 SQL 结果的常见异常：
1. 0-row results → 可能 WHERE 条件拼写错误
2. 过高 NULL 率 → 可能用了不存在或稀疏列
3. 类型异常 → 数值列出现非数值
4. 缺少 LIMIT → 大表风险
5. 单值 GROUP BY → 可能分组列选择错误
"""

import re
from typing import Any, Dict, List, Optional

# 验证级别
LEVEL_INFO = "info"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"


class ValidationIssue:
    __slots__ = ("level", "code", "message", "fix_hint")

    def __init__(self, level: str, code: str, message: str, fix_hint: str = ""):
        self.level = level
        self.code = code
        self.message = message
        self.fix_hint = fix_hint

    def to_dict(self) -> Dict[str, str]:
        d = {"level": self.level, "code": self.code, "message": self.message}
        if self.fix_hint:
            d["fix_hint"] = self.fix_hint
        return d

    def __repr__(self) -> str:
        return f"[{self.level}] {self.code}: {self.message}"


def validate_sql_result(
    *,
    sql: str,
    rows: List[Dict[str, Any]],
    total_count: Optional[int] = None,
    table_name: str = "octane_defects",
    expected_row_count: Optional[int] = None,
) -> List[ValidationIssue]:
    """对 SQL 查询结果执行后置校验，返回发现的问题列表。"""
    issues: List[ValidationIssue] = []
    sql_upper = (sql or "").upper()

    # ── Check 1: 0-row result ──
    if not rows:
        issues.append(ValidationIssue(
            LEVEL_WARNING,
            "ZERO_ROWS",
            "查询返回 0 行结果",
            "检查 WHERE 条件中的值是否拼写正确（注意大小写）。"
            "可用 SELECT DISTINCT <column> FROM table LIMIT 10 确认实际值。",
        ))
        return issues  # 后续检查无意义

    # ── Check 2: 缺少 LIMIT（非聚合查询） ──
    is_aggregate = bool(re.search(
        r"\b(COUNT|SUM|AVG|MIN|MAX|GROUP\s+BY)\b", sql_upper
    ))
    has_limit = bool(re.search(r"\bLIMIT\s+\d+", sql_upper))
    if not is_aggregate and not has_limit and len(rows) >= 200:
        issues.append(ValidationIssue(
            LEVEL_WARNING,
            "MISSING_LIMIT",
            f"非聚合查询返回 {len(rows)} 行但无 LIMIT",
            "在 SELECT 末尾添加 LIMIT 50 避免返回过多数据。",
        ))

    # ── Check 3: 高 NULL 率列 ──
    if rows:
        col_null_rates = {}
        for col in rows[0].keys():
            null_count = sum(
                1 for r in rows
                if r.get(col) is None or str(r.get(col, "")).strip() in ("", "None")
            )
            col_null_rates[col] = null_count / len(rows)

        high_null_cols = [
            (col, rate)
            for col, rate in col_null_rates.items()
            if rate > 0.8 and col not in ("raw_json",)
        ]
        if high_null_cols:
            cols_str = ", ".join(
                f"{col}({rate:.0%})" for col, rate in high_null_cols[:3]
            )
            issues.append(ValidationIssue(
                LEVEL_WARNING,
                "HIGH_NULL_RATE",
                f"以下列的 NULL 率超过 80%: {cols_str}",
                "考虑是否使用了错误的列名，或添加 WHERE col IS NOT NULL 过滤。",
            ))

    # ── Check 4: 单值 GROUP BY ──
    if "GROUP BY" in sql_upper and rows:
        # 获取第一列（通常是 GROUP BY 列）
        first_col = list(rows[0].keys())[0]
        unique_vals = set(str(r.get(first_col, "")) for r in rows)
        if len(unique_vals) == 1 and len(rows) == 1:
            issues.append(ValidationIssue(
                LEVEL_INFO,
                "SINGLE_GROUP",
                f"GROUP BY 结果只有 1 组 ({first_col}={list(unique_vals)[0]})",
                "如果期望多组结果，检查 WHERE 条件是否过于严格。",
            ))

    # ── Check 5: 结果数远少于预期 ──
    if (
        expected_row_count is not None
        and expected_row_count > 0
        and len(rows) < expected_row_count * 0.1
    ):
        issues.append(ValidationIssue(
            LEVEL_WARNING,
            "UNEXPECTED_LOW_COUNT",
            f"返回 {len(rows)} 行，远少于预期的 ~{expected_row_count} 行",
            "检查 WHERE 条件或 JOIN 条件是否过滤了过多数据。",
        ))

    # ── Check 6: 数值列包含非数值 ──
    numeric_like_cols = [
        col for col in (rows[0].keys() if rows else [])
        if any(kw in col.lower() for kw in ("count", "cnt", "rate", "score", "avg", "sum", "total", "pct"))
    ]
    for col in numeric_like_cols:
        non_numeric = 0
        for r in rows[:50]:
            val = r.get(col)
            if val is not None:
                try:
                    float(val)
                except (ValueError, TypeError):
                    non_numeric += 1
        if non_numeric > len(rows[:50]) * 0.3:
            issues.append(ValidationIssue(
                LEVEL_WARNING,
                "TYPE_MISMATCH",
                f"列 {col} 看起来应为数值，但 {non_numeric}/{min(50, len(rows))} 行包含非数值",
                f"检查 SQL 中 {col} 的表达式是否正确。",
            ))

    return issues


def format_validation_summary(issues: List[ValidationIssue]) -> str:
    """生成紧凑的验证结果摘要（注入到 LLM 上下文）"""
    if not issues:
        return ""

    lines = ["⚠️ 数据质量检查:"]
    for iss in issues:
        prefix = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(iss.level, "•")
        lines.append(f"{prefix} {iss.message}")
        if iss.fix_hint:
            lines.append(f"  → {iss.fix_hint}")
    return "\n".join(lines)


def has_blocking_issues(issues: List[ValidationIssue]) -> bool:
    """检查是否有阻塞性问题（error 级别）"""
    return any(iss.level == LEVEL_ERROR for iss in issues)


__all__ = [
    "ValidationIssue",
    "validate_sql_result",
    "format_validation_summary",
    "has_blocking_issues",
]

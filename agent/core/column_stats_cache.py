"""
Column Value Statistics Cache — 为 NL→SQL 提供列值分布信息

当模型需要生成 SQL 时，了解 categorical 列的实际值分布至关重要。
例如：用户说 "BDC 的缺陷"，模型需要知道 ecu 列中 BDC 存储为 "CDE-01"。

设计原则（参照 Defog MCP stats://table/{name} 和 Vanna schema auto-doc）：
- 启动时对主要 categorical 列预计算 top values + null rate
- 缓存到内存 + 可选持久化到 SQLite
- 提供紧凑的 prompt context（<800 tokens）供 LLM 参考
"""

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 需要统计值分布的 categorical 列及其业务含义
CATEGORICAL_COLUMNS = {
    "project": "项目/车系",
    "tproject": "项目(原始)",
    "severity": "严重度",
    "severity_group": "严重度分组",
    "phase": "阶段",
    "status_phase": "状态/阶段",
    "ecu": "ECU 名称",
    "assigned_ecu": "分配的 ECU",
    "top_aida": "AIDA 产品域",
    "fv": "Feature Team",
    "domain": "Domain 领域",
    "tester": "测试人员",
    "owner": "Owner",
    "team": "团队",
    "problem_finder_team": "发现问题的团队",
    "classification": "分类",
    "market": "市场",
    "matrix": "Matrix",
    "lead_model": "Lead Model",
    "program": "Program",
    "year": "年份",
}

# 数值列（统计 min/max/avg）
NUMERIC_COLUMNS = {
    "risk_score": "风险评分",
    "tolerated_count": "容忍次数",
    "ecu_no_of_changes": "ECU 变更次数",
    "reprel_changes": "Reprel 变更次数",
}


class ColumnStatsCache:
    """列值统计缓存 — 为 SQL 生成提供列值分布上下文"""

    def __init__(self, db_path: str, table_name: str = "octane_defects"):
        self._db_path = db_path
        self._table_name = table_name
        self._stats: Dict[str, Dict[str, Any]] = {}
        self._table_row_count: int = 0
        self._built_at: float = 0
        self._ttl_seconds: int = 3600  # 1 hour

    @property
    def is_stale(self) -> bool:
        return time.time() - self._built_at > self._ttl_seconds

    def build(self) -> None:
        """从数据库预计算列值统计"""
        start = time.time()
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            cur = conn.cursor()

            # 总行数
            self._table_row_count = cur.execute(
                f'SELECT COUNT(*) FROM "{self._table_name}"'
            ).fetchone()[0]

            # Categorical 列统计
            for col, label in CATEGORICAL_COLUMNS.items():
                try:
                    self._stats[col] = self._compute_categorical(cur, col, label)
                except Exception as exc:
                    logger.debug("column_stats skip %s: %s", col, exc)

            # 数值列统计
            for col, label in NUMERIC_COLUMNS.items():
                try:
                    self._stats[col] = self._compute_numeric(cur, col, label)
                except Exception as exc:
                    logger.debug("column_stats skip %s: %s", col, exc)

            conn.close()
            self._built_at = time.time()
            elapsed = round(time.time() - start, 2)
            logger.info(
                "column_stats built: %d columns, %d rows, %.2fs",
                len(self._stats), self._table_row_count, elapsed,
            )
        except Exception as exc:
            logger.warning("column_stats build failed: %s", exc)

    def _compute_categorical(
        self, cur: sqlite3.Cursor, col: str, label: str
    ) -> Dict[str, Any]:
        # Top 15 values by count
        rows = cur.execute(
            f"""
            SELECT COALESCE(NULLIF(TRIM(CAST("{col}" AS TEXT)), ''), '<EMPTY>') AS val,
                   COUNT(*) AS cnt
            FROM "{self._table_name}"
            GROUP BY val
            ORDER BY cnt DESC
            LIMIT 15
            """,
        ).fetchall()

        null_count = cur.execute(
            f"""
            SELECT COUNT(*) FROM "{self._table_name}"
            WHERE "{col}" IS NULL OR TRIM(CAST("{col}" AS TEXT)) = ''
            """,
        ).fetchone()[0]

        distinct = cur.execute(
            f"""
            SELECT COUNT(DISTINCT TRIM(CAST("{col}" AS TEXT)))
            FROM "{self._table_name}"
            WHERE "{col}" IS NOT NULL AND TRIM(CAST("{col}" AS TEXT)) != ''
            """,
        ).fetchone()[0]

        return {
            "type": "categorical",
            "label": label,
            "distinct_count": distinct,
            "null_count": null_count,
            "null_pct": round(100 * null_count / max(1, self._table_row_count), 1),
            "top_values": [(val, cnt) for val, cnt in rows if val != "<EMPTY>"][:12],
        }

    def _compute_numeric(
        self, cur: sqlite3.Cursor, col: str, label: str
    ) -> Dict[str, Any]:
        row = cur.execute(
            f"""
            SELECT MIN(CAST("{col}" AS REAL)),
                   MAX(CAST("{col}" AS REAL)),
                   AVG(CAST("{col}" AS REAL)),
                   COUNT(*),
                   SUM(CASE WHEN "{col}" IS NULL THEN 1 ELSE 0 END)
            FROM "{self._table_name}"
            WHERE "{col}" IS NOT NULL
            """,
        ).fetchone()

        return {
            "type": "numeric",
            "label": label,
            "min": row[0],
            "max": row[1],
            "avg": round(row[2], 2) if row[2] is not None else None,
            "non_null_count": row[3],
            "null_count": row[4],
            "null_pct": round(100 * row[4] / max(1, self._table_row_count), 1),
        }

    def get_stats(self, column: str) -> Optional[Dict[str, Any]]:
        if self.is_stale and not self._stats:
            self.build()
        return self._stats.get(column)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        if self.is_stale and not self._stats:
            self.build()
        return dict(self._stats)

    def lookup_value(self, query_text: str, column: str) -> Optional[str]:
        """模糊匹配用户输入到实际列值。
        
        例如：用户说 "BDC"，在 ecu 列的 top_values 中查找包含 "BDC" 的值。
        """
        stats = self.get_stats(column)
        if not stats or stats.get("type") != "categorical":
            return None

        query_lower = query_text.lower().strip()
        for val, _cnt in stats.get("top_values", []):
            if query_lower == str(val).lower():
                return val
            if query_lower in str(val).lower() or str(val).lower() in query_lower:
                return val
        return None

    def build_prompt_context(self, max_tokens: int = 800) -> str:
        """生成紧凑的列统计上下文供 LLM 参考。
        
        格式设计参照 Anthropic context engineering 原则：
        "find the smallest possible set of high-signal tokens"
        """
        if not self._stats:
            if self.is_stale:
                self.build()
            if not self._stats:
                return ""

        lines = [
            f"## {self._table_name} schema stats ({self._table_row_count:,} rows)",
        ]

        for col, stat in self._stats.items():
            if stat["type"] == "categorical":
                top3 = stat["top_values"][:5]
                vals = ", ".join(f"{v}({c})" for v, c in top3)
                null_info = f", null={stat['null_pct']}%" if stat["null_pct"] > 5 else ""
                lines.append(
                    f"- {col}: {stat['distinct_count']} distinct [{vals}]{null_info}"
                )
            elif stat["type"] == "numeric":
                lines.append(
                    f"- {col}: min={stat['min']}, max={stat['max']}, avg={stat['avg']}"
                )

        text = "\n".join(lines)
        # Token-aware truncation (rough: 1 token ≈ 4 chars)
        max_chars = max_tokens * 4
        if len(text) > max_chars:
            text = text[:max_chars] + "\n..."
        return text

    def build_value_mapping_context(self, question: str) -> str:
        """基于用户问题中的实体，生成值映射提示。
        
        例如：用户提到 "IDCEVO"，返回 "project 列中 IDCEVO 有 3421 条记录"
        """
        if not self._stats:
            return ""

        question_lower = question.lower()
        hints = []

        for col, stat in self._stats.items():
            if stat.get("type") != "categorical":
                continue
            for val, cnt in stat.get("top_values", []):
                val_lower = str(val).lower()
                if len(val_lower) >= 3 and val_lower in question_lower:
                    hints.append(f'"{col}" 列中值 "{val}" 有 {cnt} 条记录')
                    break

        return "; ".join(hints) if hints else ""


# Singleton
_instance: Optional[ColumnStatsCache] = None


def get_column_stats_cache(db_path: str, table_name: str = "octane_defects") -> ColumnStatsCache:
    global _instance
    if _instance is None or _instance._db_path != db_path:
        _instance = ColumnStatsCache(db_path, table_name)
    return _instance


__all__ = ["ColumnStatsCache", "get_column_stats_cache"]

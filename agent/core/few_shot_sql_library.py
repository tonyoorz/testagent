"""
Few-Shot SQL Examples Library — 为 NL→SQL 提供高质量示例对

设计原则（参照 Anthropic context engineering）：
"Examples are the 'pictures' worth a thousand words."

核心思路：
1. 维护 50+ 个 question→SQL pairs，覆盖常见查询模式
2. 基于关键词匹配检索 top-3 相关示例注入 prompt
3. 按 table_name 分类，避免注入无关示例
"""

import re
from typing import Any, Dict, List, Optional

# ──────────────────────────────────────────────────────────────
# Few-shot SQL examples for octane_defects table
# ──────────────────────────────────────────────────────────────

DEFECT_EXAMPLES: List[Dict[str, str]] = [
    # === 计数 / 统计 ===
    {
        "question": "总共有多少缺陷？",
        "sql": "SELECT COUNT(*) AS total_defects FROM octane_defects",
        "tags": "count total summary",
    },
    {
        "question": "各项目缺陷数量排名",
        "sql": "SELECT project, COUNT(*) AS cnt FROM octane_defects GROUP BY project ORDER BY cnt DESC",
        "tags": "count project ranking groupby",
    },
    {
        "question": "各严重度缺陷分布",
        "sql": "SELECT severity, COUNT(*) AS cnt FROM octane_defects GROUP BY severity ORDER BY cnt DESC",
        "tags": "severity distribution groupby",
    },
    {
        "question": "各 ECU 的缺陷数量",
        "sql": "SELECT ecu, COUNT(*) AS cnt FROM octane_defects WHERE ecu IS NOT NULL AND TRIM(ecu) != '' GROUP BY ecu ORDER BY cnt DESC LIMIT 20",
        "tags": "ecu count groupby top",
    },
    {
        "question": "各 AIDA 领域的缺陷数",
        "sql": "SELECT top_aida, COUNT(*) AS cnt FROM octane_defects WHERE top_aida IS NOT NULL AND TRIM(top_aida) != '' GROUP BY top_aida ORDER BY cnt DESC",
        "tags": "aida domain groupby count",
    },
    {
        "question": "各 Feature Team 缺陷排名",
        "sql": "SELECT fv, COUNT(*) AS cnt FROM octane_defects WHERE fv IS NOT NULL AND TRIM(fv) != '' GROUP BY fv ORDER BY cnt DESC LIMIT 20",
        "tags": "fv feature team groupby ranking",
    },
    # === 过滤 ===
    {
        "question": "IDCEVO 项目有多少 Critical 缺陷？",
        "sql": "SELECT COUNT(*) AS cnt FROM octane_defects WHERE project = 'IDCEVO' AND severity = 'Critical'",
        "tags": "filter project severity critical count",
    },
    {
        "question": "上周新增了多少缺陷？",
        "sql": "SELECT COUNT(*) AS cnt FROM octane_defects WHERE creation_time >= date('now', '-7 days')",
        "tags": "time week recent count filter",
    },
    {
        "question": "本月各项目的 Critical 和 High 缺陷分布",
        "sql": "SELECT project, severity, COUNT(*) AS cnt FROM octane_defects WHERE severity IN ('Critical', 'High') AND creation_time >= date('now', 'start of month') GROUP BY project, severity ORDER BY cnt DESC",
        "tags": "month filter severity project distribution",
    },
    {
        "question": "DTSV_China 团队发现的缺陷",
        "sql": "SELECT project, severity, COUNT(*) AS cnt FROM octane_defects WHERE problem_finder_team = 'DTSV_China' GROUP BY project, severity ORDER BY cnt DESC",
        "tags": "team filter dtsv china groupby",
    },
    # === 趋势 ===
    {
        "question": "每周缺陷新增趋势",
        "sql": "SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS cnt FROM octane_defects WHERE creation_time >= date('now', '-90 days') GROUP BY week ORDER BY week",
        "tags": "trend weekly time creation",
    },
    {
        "question": "各项目每月缺陷趋势",
        "sql": "SELECT strftime('%Y-%m', creation_time) AS month, project, COUNT(*) AS cnt FROM octane_defects WHERE creation_time >= date('now', '-180 days') GROUP BY month, project ORDER BY month",
        "tags": "trend monthly project time",
    },
    {
        "question": "最近几周 Critical 缺陷数变化",
        "sql": "SELECT strftime('%Y-W%W', creation_time) AS week, COUNT(*) AS cnt FROM octane_defects WHERE severity = 'Critical' AND creation_time >= date('now', '-60 days') GROUP BY week ORDER BY week",
        "tags": "trend critical severity weekly",
    },
    # === 对比 ===
    {
        "question": "IDCEVO 和 IDC 哪个项目缺陷更多？",
        "sql": "SELECT project, COUNT(*) AS cnt FROM octane_defects WHERE project IN ('IDCEVO', 'IDC') GROUP BY project ORDER BY cnt DESC",
        "tags": "compare project vs filter",
    },
    {
        "question": "对比各项目 Critical 缺陷占比",
        "sql": "SELECT project, SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) AS critical_cnt, COUNT(*) AS total, ROUND(100.0 * SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) / COUNT(*), 1) AS critical_pct FROM octane_defects GROUP BY project HAVING total > 10 ORDER BY critical_pct DESC",
        "tags": "compare ratio severity critical percentage project",
    },
    # === 状态 ===
    {
        "question": "各状态的缺陷数",
        "sql": "SELECT phase, COUNT(*) AS cnt FROM octane_defects GROUP BY phase ORDER BY cnt DESC",
        "tags": "status phase distribution",
    },
    {
        "question": "还有多少缺陷未关闭？",
        "sql": "SELECT COUNT(*) AS open_cnt FROM octane_defects WHERE phase NOT IN ('Closed', 'Deferred', 'Rejected')",
        "tags": "open status filter not closed",
    },
    {
        "question": "各项目未关闭的 Critical 和 High 缺陷数",
        "sql": "SELECT project, severity, COUNT(*) AS cnt FROM octane_defects WHERE phase NOT IN ('Closed', 'Deferred', 'Rejected') AND severity IN ('Critical', 'High') GROUP BY project, severity ORDER BY cnt DESC",
        "tags": "open critical high project filter",
    },
    # === Top Issue / 热点 ===
    {
        "question": "最严重的10个缺陷是什么？",
        "sql": "SELECT defect_id, name, project, severity, phase, ecu, creation_time FROM octane_defects WHERE severity = 'Critical' AND phase NOT IN ('Closed', 'Deferred', 'Rejected') ORDER BY creation_time DESC LIMIT 10",
        "tags": "top critical open list detail",
    },
    {
        "question": "风险评分最高的缺陷",
        "sql": "SELECT defect_id, name, project, severity, risk_score, ecu FROM octane_defects WHERE risk_score IS NOT NULL ORDER BY risk_score DESC LIMIT 15",
        "tags": "risk score top ranking",
    },
    {
        "question": "哪些 ECU 的 Critical 缺陷最多？",
        "sql": "SELECT ecu, COUNT(*) AS cnt FROM octane_defects WHERE severity = 'Critical' AND ecu IS NOT NULL AND TRIM(ecu) != '' GROUP BY ecu ORDER BY cnt DESC LIMIT 10",
        "tags": "ecu critical hotspot top",
    },
    # === 交叉分析 ===
    {
        "question": "项目 × 严重度 交叉表",
        "sql": "SELECT project, severity, COUNT(*) AS cnt FROM octane_defects GROUP BY project, severity ORDER BY project, cnt DESC",
        "tags": "matrix cross project severity pivot",
    },
    {
        "question": "ECU × 项目 分布",
        "sql": "SELECT ecu, project, COUNT(*) AS cnt FROM octane_defects WHERE ecu IS NOT NULL AND TRIM(ecu) != '' GROUP BY ecu, project ORDER BY cnt DESC LIMIT 30",
        "tags": "matrix ecu project cross distribution",
    },
    {
        "question": "AIDA 领域 × 严重度 分布",
        "sql": "SELECT top_aida, severity, COUNT(*) AS cnt FROM octane_defects WHERE top_aida IS NOT NULL AND TRIM(top_aida) != '' GROUP BY top_aida, severity ORDER BY cnt DESC",
        "tags": "matrix aida severity cross",
    },
    # === 测试人员 ===
    {
        "question": "各测试人员发现了多少缺陷？",
        "sql": "SELECT tester, COUNT(*) AS cnt FROM octane_defects WHERE tester IS NOT NULL AND TRIM(tester) != '' GROUP BY tester ORDER BY cnt DESC LIMIT 20",
        "tags": "tester found count ranking",
    },
    {
        "question": "哪个测试人员发现的 Critical 缺陷最多？",
        "sql": "SELECT tester, COUNT(*) AS cnt FROM octane_defects WHERE severity = 'Critical' AND tester IS NOT NULL AND TRIM(tester) != '' GROUP BY tester ORDER BY cnt DESC LIMIT 10",
        "tags": "tester critical top ranking",
    },
    # === 时间相关 ===
    {
        "question": "2025年的缺陷总数",
        "sql": "SELECT COUNT(*) AS cnt FROM octane_defects WHERE year = 2025",
        "tags": "year 2025 filter count",
    },
    {
        "question": "今年各月的缺陷数",
        "sql": "SELECT strftime('%Y-%m', creation_time) AS month, COUNT(*) AS cnt FROM octane_defects WHERE year = 2026 GROUP BY month ORDER BY month",
        "tags": "monthly 2026 trend this year",
    },
    {
        "question": "最近30天新增的缺陷按项目统计",
        "sql": "SELECT project, COUNT(*) AS cnt FROM octane_defects WHERE creation_time >= date('now', '-30 days') GROUP BY project ORDER BY cnt DESC",
        "tags": "recent 30 days project filter",
    },
    # === 复杂查询 ===
    {
        "question": "各项目的缺陷关闭率是多少？",
        "sql": "SELECT project, COUNT(*) AS total, SUM(CASE WHEN phase IN ('Closed', 'Deferred') THEN 1 ELSE 0 END) AS closed, ROUND(100.0 * SUM(CASE WHEN phase IN ('Closed', 'Deferred') THEN 1 ELSE 0 END) / COUNT(*), 1) AS close_rate_pct FROM octane_defects GROUP BY project HAVING total > 10 ORDER BY close_rate_pct DESC",
        "tags": "close rate ratio project percentage",
    },
    {
        "question": "平均每个项目有多少缺陷？",
        "sql": "SELECT ROUND(1.0 * COUNT(*) / COUNT(DISTINCT project), 1) AS avg_per_project FROM octane_defects",
        "tags": "average per project statistics",
    },
    {
        "question": "各 domain 的 Critical 占比",
        "sql": "SELECT domain, COUNT(*) AS total, SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) AS critical, ROUND(100.0 * SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct FROM octane_defects WHERE domain IS NOT NULL AND TRIM(domain) != '' GROUP BY domain HAVING total > 5 ORDER BY pct DESC",
        "tags": "domain critical ratio percentage",
    },
    # === Manual Runs 相关 ===
    {
        "question": "各状态的 test run 数量",
        "sql": "SELECT status, COUNT(*) AS cnt FROM octane_manual_runs GROUP BY status ORDER BY cnt DESC",
        "tags": "test run status count manual_runs",
    },
    {
        "question": "今年的 test run 通过率",
        "sql": "SELECT ROUND(100.0 * SUM(CASE WHEN status = 'Passed' THEN 1 ELSE 0 END) / COUNT(*), 1) AS pass_rate FROM octane_manual_runs WHERE year = 2026",
        "tags": "pass rate test run manual_runs",
    },
]


def _tokenize(text: str) -> set:
    """简单分词 — 中英文混合"""
    tokens = set()
    for tok in re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
        if len(tok) > 1:
            tokens.add(tok)
    return tokens


def retrieve_few_shot_examples(
    question: str,
    table_name: str = "octane_defects",
    top_k: int = 3,
) -> List[Dict[str, str]]:
    """基于关键词重叠检索最相关的 few-shot 示例。
    
    设计上故意用简单的关键词匹配而非 embedding，因为：
    1. 不引入额外依赖（sklearn/sentence-transformers）
    2. SQL 示例的匹配更依赖关键词而非语义
    3. 遵循 "do the simplest thing that works" 原则
    """
    examples = DEFECT_EXAMPLES  # TODO: 按 table_name 切换

    question_tokens = _tokenize(question)
    if not question_tokens:
        return examples[:top_k]

    scored = []
    for ex in examples:
        ex_tokens = _tokenize(ex["question"]) | _tokenize(ex.get("tags", ""))
        overlap = len(question_tokens & ex_tokens)
        if overlap > 0:
            # Jaccard-like score
            score = overlap / len(question_tokens | ex_tokens)
            scored.append((score, ex))

    scored.sort(key=lambda x: -x[0])
    return [ex for _score, ex in scored[:top_k]]


def build_few_shot_prompt(question: str, table_name: str = "octane_defects") -> str:
    """生成 few-shot SQL 示例 prompt 块。
    
    格式紧凑（<400 tokens），直接注入 system prompt 或 tool description。
    """
    examples = retrieve_few_shot_examples(question, table_name, top_k=3)
    if not examples:
        return ""

    lines = ["## Similar query examples:"]
    for i, ex in enumerate(examples, 1):
        lines.append(f"{i}. Q: {ex['question']}")
        lines.append(f"   SQL: {ex['sql']}")
    return "\n".join(lines)


__all__ = [
    "DEFECT_EXAMPLES",
    "retrieve_few_shot_examples",
    "build_few_shot_prompt",
]

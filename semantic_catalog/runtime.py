import json
import os
import re
import sqlite3
from dataclasses import dataclass
from collections import Counter
from functools import lru_cache
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SemanticSelection:
    datasets: List[Dict[str, Any]]
    metrics: List[Dict[str, Any]]
    charts: List[Dict[str, Any]]
    business_rules: List[Dict[str, Any]]


class SemanticCatalog:
    def __init__(self, base_dir: Optional[str] = None, db_path: Optional[str] = None, prefer_db: bool = False):
        self.base_dir = base_dir or os.path.join(os.path.dirname(__file__))
        self.db_path = str(db_path).strip() if db_path else None
        self.prefer_db = bool(prefer_db)

    def _path(self, filename: str) -> str:
        return os.path.join(self.base_dir, filename)

    @lru_cache(maxsize=8)
    def load_catalog(self) -> Dict[str, Any]:
        if self.prefer_db and self.db_path and os.path.exists(self.db_path):
            try:
                db_data = self._load_catalog_from_sqlite(self.db_path)
                if db_data:
                    if not isinstance(db_data.get("business_rules"), list):
                        business_rules = self._load_json(self._path("business_rules.json")) or {}
                        db_data["business_rules"] = business_rules.get("business_rules") or []
                    return db_data
            except Exception:
                pass
        data: Dict[str, Any] = {
            "datasets": [],
            "metrics": [],
            "charts": [],
            "business_rules": [],
            "schema_version": "unknown",
        }
        data.update(self._load_json(self._path("datasets.json")) or {})
        metrics = self._load_json(self._path("metrics.json")) or {}
        charts = self._load_json(self._path("charts.json")) or {}
        business_rules = self._load_json(self._path("business_rules.json")) or {}
        if isinstance(metrics.get("metrics"), list):
            data["metrics"] = metrics["metrics"]
        if isinstance(charts.get("charts"), list):
            data["charts"] = charts["charts"]
        if isinstance(business_rules.get("business_rules"), list):
            data["business_rules"] = business_rules["business_rules"]
        if "schema_version" in metrics:
            data["schema_version"] = str(metrics["schema_version"])
        return data

    def _load_json(self, path: str) -> Optional[Dict[str, Any]]:
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _normalize_catalog_part(self, catalog_type: str, payload: Any) -> Dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, list):
            return {catalog_type: payload}
        return {}

    def _ensure_semantic_catalog_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS semantic_catalog (
                catalog_type TEXT PRIMARY KEY,
                catalog_json TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )

    def _seed_semantic_catalog_row(self, conn: sqlite3.Connection, catalog_type: str, payload: Dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO semantic_catalog (catalog_type, catalog_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(catalog_type) DO UPDATE SET
                catalog_json=excluded.catalog_json,
                updated_at=excluded.updated_at
            """,
            (catalog_type, json.dumps(payload, ensure_ascii=False), datetime.utcnow().isoformat() + "Z"),
        )

    def _load_catalog_from_sqlite(self, db_path: str) -> Dict[str, Any]:
        conn = sqlite3.connect(db_path)
        try:
            self._ensure_semantic_catalog_table(conn)
            data: Dict[str, Any] = {"datasets": [], "metrics": [], "charts": [], "schema_version": "unknown"}
            for catalog_type, filename in (("datasets", "datasets.json"), ("metrics", "metrics.json"), ("charts", "charts.json")):
                row = conn.execute(
                    "SELECT catalog_json FROM semantic_catalog WHERE catalog_type = ?",
                    (catalog_type,),
                ).fetchone()
                payload: Any = None
                if row and row[0]:
                    try:
                        payload = json.loads(row[0])
                    except Exception:
                        payload = None
                if payload is None:
                    file_payload = self._load_json(self._path(filename)) or {}
                    self._seed_semantic_catalog_row(conn, catalog_type, file_payload)
                    payload = file_payload
                part = self._normalize_catalog_part(catalog_type, payload)
                if catalog_type == "datasets":
                    data.update(part or {})
                elif catalog_type == "metrics":
                    if isinstance(part.get("metrics"), list):
                        data["metrics"] = part["metrics"]
                    if "schema_version" in part:
                        data["schema_version"] = str(part["schema_version"])
                elif catalog_type == "charts":
                    if isinstance(part.get("charts"), list):
                        data["charts"] = part["charts"]
            conn.commit()
            return data
        finally:
            conn.close()

    def select(
        self,
        question: str,
        dashboard: Optional[str] = None,
        dataframe_columns: Optional[Sequence[str]] = None,
        max_each: int = 6,
    ) -> SemanticSelection:
        catalog = self.load_catalog()
        q_tokens = _tokenize(question)
        col_tokens = set()
        if dataframe_columns:
            for c in dataframe_columns:
                col_tokens.update(_tokenize(str(c)))
        datasets = _rank_items(
            catalog.get("datasets") or [],
            q_tokens=q_tokens,
            col_tokens=col_tokens,
            extra_filters=None,
            max_items=max_each,
        )
        metrics = _rank_items(
            catalog.get("metrics") or [],
            q_tokens=q_tokens,
            col_tokens=col_tokens,
            extra_filters=None,
            max_items=max_each,
        )
        chart_filters = None
        if dashboard:
            chart_filters = [("dashboard", dashboard)]
        charts = _rank_items(
            catalog.get("charts") or [],
            q_tokens=q_tokens,
            col_tokens=col_tokens,
            extra_filters=chart_filters,
            max_items=max_each,
        )
        business_rules = _rank_items(
            catalog.get("business_rules") or [],
            q_tokens=q_tokens,
            col_tokens=col_tokens,
            extra_filters=None,
            max_items=max(max_each, 10),
        )
        return SemanticSelection(datasets=datasets, metrics=metrics, charts=charts, business_rules=business_rules)


def build_semantic_context(
    question: str,
    dashboard: Optional[str] = None,
    dataframe_columns: Optional[Sequence[str]] = None,
    max_each: int = 6,
    db_path: Optional[str] = None,
    prefer_db: Optional[bool] = None,
) -> str:
    if prefer_db is None:
        prefer_db = bool(db_path)
    selection = SemanticCatalog(db_path=db_path, prefer_db=bool(prefer_db)).select(
        question=question, dashboard=dashboard, dataframe_columns=dataframe_columns, max_each=max_each
    )
    blocks: List[str] = []
    if selection.datasets:
        blocks.append(_format_block("数据集语义", selection.datasets, fields=("id", "name", "granularity", "can_answer", "misuse_risks")))
    if selection.metrics:
        blocks.append(
            _format_block(
                "指标语义",
                selection.metrics,
                fields=(
                    "id",
                    "name",
                    "description",
                    "inputs",
                    "calculation",
                    "null_handling",
                    "misuse_risks",
                    "recommended_checks",
                    "alias_of",
                ),
            )
        )
    if selection.charts:
        blocks.append(_format_block("图表语义", selection.charts, fields=("id", "name", "description", "expected_focus", "abnormal_signals")))
    business_rules_for_context = _merge_business_rules_for_context(selection.business_rules, SemanticCatalog(db_path=db_path, prefer_db=bool(prefer_db)).load_catalog().get("business_rules") or [])
    if business_rules_for_context:
        blocks.append(
            _format_block(
                "业务规则语义",
                business_rules_for_context,
                fields=("id", "name", "description", "rules", "trigger_terms", "sql_guardrails", "aliases"),
            )
        )

    db_semantic_enabled = (os.getenv("AGENT_DB_SEMANTIC_ENABLED", "1") or "1").strip().lower() not in {"0", "false", "no"}
    if db_semantic_enabled and db_path and os.path.exists(db_path):
        db_block = build_db_semantic_glossary(question=question, db_path=db_path, max_columns=max(8, int(max_each) * 3))
        if db_block:
            blocks.append(db_block)

    if not blocks:
        return ""
    header = "以下为系统内置的语义目录（配置驱动），用于约束与增强分析。不得编造未在目录中的口径。"
    return header + "\n\n" + "\n\n".join(blocks)


def _merge_business_rules_for_context(selected: List[Dict[str, Any]], all_rules: List[Dict[str, Any]], min_items: int = 12) -> List[Dict[str, Any]]:
    """Keep semantic relevance, but guarantee a minimum breadth of business rules in context."""
    selected = [r for r in (selected or []) if isinstance(r, dict)]
    all_rules = [r for r in (all_rules or []) if isinstance(r, dict)]
    if not all_rules:
        return selected

    by_id: Dict[str, Dict[str, Any]] = {}
    ordered: List[Dict[str, Any]] = []
    for r in selected:
        rid = str(r.get("id") or "").strip()
        if rid and rid not in by_id:
            by_id[rid] = r
            ordered.append(r)

    target_n = min(len(all_rules), max(min_items, len(selected)))
    for r in all_rules:
        if len(ordered) >= target_n:
            break
        rid = str(r.get("id") or "").strip()
        if rid and rid not in by_id:
            by_id[rid] = r
            ordered.append(r)

    return ordered


def _format_block(title: str, items: List[Dict[str, Any]], fields: Tuple[str, ...]) -> str:
    lines = [f"【{title}】"]
    for it in items:
        it_id = str(it.get("id", "")).strip()
        it_name = str(it.get("name", "")).strip()
        lines.append(f"- {it_id} | {it_name}".strip())
        for f in fields:
            if f in ("id", "name"):
                continue
            val = it.get(f)
            if val is None:
                continue
            rendered = _render_value(val)
            if not rendered:
                continue
            lines.append(f"  - {f}: {rendered}")
    return "\n".join(lines)


def _render_value(val: Any) -> str:
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        parts = []
        for x in val:
            if x is None:
                continue
            s = str(x).strip()
            if s:
                parts.append(s)
        return "; ".join(parts)
    if isinstance(val, dict):
        parts = []
        for k, v in val.items():
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                continue
            parts.append(f"{k}={s}")
        return "; ".join(parts)
    return str(val).strip()


def _rank_items(
    items: List[Dict[str, Any]],
    q_tokens: set,
    col_tokens: set,
    extra_filters: Optional[List[Tuple[str, str]]],
    max_items: int,
) -> List[Dict[str, Any]]:
    q_terms = sorted([t for t in (q_tokens or set()) if t])
    if not q_terms:
        return []

    field_weights: List[Tuple[str, int]] = [
        ("id", 3),
        ("name", 4),
        ("aliases", 3),
        ("trigger_terms", 3),
        ("rules", 2),
        ("sql_guardrails", 2),
        ("synonyms", 3),
        ("description", 2),
        ("business_meaning", 2),
        ("can_answer", 2),
        ("expected_focus", 2),
        ("inputs", 1),
        ("output", 1),
        ("calculation", 1),
        ("null_handling", 1),
        ("granularity", 1),
        ("alias_of", 2),
        ("core_dimensions", 1),
        ("time_columns", 1),
        ("common_columns", 1),
        ("field_lineage", 1),
        ("list_field_lineage", 1),
        ("related_dimensions", 1),
        ("related_metrics", 1),
        ("misuse_risks", 2),
        ("recommended_checks", 2),
    ]

    docs: List[Tuple[Dict[str, Any], List[str], set]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if extra_filters:
            passed = True
            for k, v in extra_filters:
                if str(it.get(k, "")).strip() != v:
                    passed = False
                    break
            if not passed:
                continue

        doc_tokens: List[str] = []
        for k, w in field_weights:
            val = it.get(k)
            if val is None:
                continue
            toks = _tokenize_list(_render_value(val))
            if not toks:
                continue
            doc_tokens.extend(toks * max(1, int(w)))
        if not doc_tokens:
            continue
        docs.append((it, doc_tokens, set(doc_tokens)))

    if not docs:
        return []

    df: Counter = Counter()
    for _, _, uniq in docs:
        for t in uniq:
            df[t] += 1

    n_docs = float(len(docs))
    avgdl = sum(len(tokens) for _, tokens, _ in docs) / n_docs
    k1 = 1.3
    b = 0.75

    def _idf(term: str) -> float:
        d = float(df.get(term, 0))
        return float(math.log((n_docs - d + 0.5) / (d + 0.5) + 1.0))

    import math

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for it, doc_tokens, uniq in docs:
        tf = Counter(doc_tokens)
        dl = float(len(doc_tokens))
        score = 0.0
        for t in q_terms:
            f = float(tf.get(t, 0))
            if f <= 0:
                continue
            denom = f + k1 * (1.0 - b + b * (dl / avgdl))
            score += _idf(t) * (f * (k1 + 1.0) / denom)
        if col_tokens:
            score += 0.25 * float(len(uniq & col_tokens))
        if score <= 0:
            continue
        scored.append((score, it))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:max_items]]


def _item_text(it: Dict[str, Any]) -> str:
    keys = (
        "id",
        "name",
        "description",
        "granularity",
        "business_meaning",
        "can_answer",
        "expected_focus",
        "inputs",
        "output",
        "calculation",
        "null_handling",
        "alias_of",
    )
    parts: List[str] = []
    for k in keys:
        v = it.get(k)
        if v is None:
            continue
        parts.append(_render_value(v))
    for k in (
        "core_dimensions",
        "time_columns",
        "common_columns",
        "field_lineage",
        "list_field_lineage",
        "related_dimensions",
        "related_metrics",
        "misuse_risks",
        "recommended_checks",
    ):
        v = it.get(k)
        if v is None:
            continue
        parts.append(_render_value(v))
    return " ".join([p for p in parts if p])


_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def _tokenize_list(text: str) -> List[str]:
    if not text:
        return []
    raw = _TOKEN_RE.findall(text.lower())
    out: List[str] = []
    for t in raw:
        s = t.strip()
        if not s:
            continue
        if len(s) <= 1:
            continue
        out.append(s)
    return out


def _tokenize(text: str) -> set:
    if not text:
        return set()
    return set(_tokenize_list(text))


def build_db_semantic_glossary(
    question: str,
    db_path: str,
    target_table: Optional[str] = None,
    max_columns: int = 18,
) -> str:
    entries = _collect_db_semantic_entries(db_path=db_path, target_table=target_table)
    if not entries:
        return ""

    q_tokens = _tokenize(question)
    ranked = _rank_db_semantic_entries(entries=entries, q_tokens=q_tokens, max_items=max_columns)
    if not ranked:
        ranked = entries[:max(1, min(max_columns, len(entries)))]

    lines: List[str] = ["【数据库字段语义（自动推断）】"]
    for it in ranked:
        table_name = str(it.get("table") or "")
        col = str(it.get("column") or "")
        meaning = str(it.get("meaning") or "").strip()
        semantic_type = str(it.get("semantic_type") or "").strip()
        aliases = [str(x).strip() for x in (it.get("aliases") or []) if str(x).strip()]
        sample_values = [str(x).strip() for x in (it.get("sample_values") or []) if str(x).strip()]
        if not col:
            continue
        head = f"- {table_name}.{col}" if table_name else f"- {col}"
        lines.append(head)
        if meaning:
            lines.append(f"  - meaning: {meaning}")
        if semantic_type:
            lines.append(f"  - semantic_type: {semantic_type}")
        if aliases:
            lines.append(f"  - aliases: {'; '.join(aliases[:8])}")
        if sample_values:
            lines.append(f"  - sample_values: {'; '.join(sample_values[:5])}")
    lines.append("  - note: 以上字段语义由列名+样本值自动推断，生成SQL时应优先匹配语义最相近字段。")
    return "\n".join(lines)


def _collect_db_semantic_entries(db_path: str, target_table: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    out: List[Dict[str, Any]] = []
    try:
        table_names: List[str] = []
        if target_table:
            table_names = [str(target_table).strip()]
        else:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            table_names = [str(r[0]) for r in rows if r and r[0]]

        for table in table_names[:30]:
            try:
                cols = conn.execute(f"PRAGMA table_info({_q_ident(table)})").fetchall()
            except Exception:
                continue
            for c in cols:
                name = str(c["name"] if isinstance(c, sqlite3.Row) else c[1])
                col_type = str(c["type"] if isinstance(c, sqlite3.Row) else c[2])
                sample_values = _sample_column_values(conn, table, name, limit=5)
                sem = _infer_column_semantics(name=name, col_type=col_type, sample_values=sample_values)
                out.append(
                    {
                        "table": table,
                        "column": name,
                        "meaning": sem.get("meaning") or "",
                        "semantic_type": sem.get("semantic_type") or "",
                        "aliases": sem.get("aliases") or [],
                        "sample_values": sample_values,
                    }
                )
    finally:
        conn.close()
    return out


def _rank_db_semantic_entries(entries: List[Dict[str, Any]], q_tokens: set, max_items: int) -> List[Dict[str, Any]]:
    if not entries:
        return []
    if not q_tokens:
        return entries[:max(1, min(max_items, len(entries)))]

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for e in entries:
        text_parts = [
            str(e.get("table") or ""),
            str(e.get("column") or ""),
            str(e.get("meaning") or ""),
            str(e.get("semantic_type") or ""),
            " ".join([str(a) for a in (e.get("aliases") or [])]),
            " ".join([str(v) for v in (e.get("sample_values") or [])]),
        ]
        toks = _tokenize(" ".join(text_parts))
        overlap = float(len(toks & q_tokens))
        if overlap <= 0:
            continue
        bonus = 0.0
        semantic_type = str(e.get("semantic_type") or "")
        if semantic_type in {"time", "status", "severity", "person", "project", "module", "risk", "test_result"}:
            bonus = 0.25
        scored.append((overlap + bonus, e))

    if not scored:
        return entries[:max(1, min(max_items, len(entries)))]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:max(1, min(max_items, len(scored)))]]


def _sample_column_values(conn: sqlite3.Connection, table: str, col: str, limit: int = 5) -> List[str]:
    try:
        sql = (
            f"SELECT CAST({_q_ident(col)} AS TEXT) AS v FROM {_q_ident(table)} "
            f"WHERE {_q_ident(col)} IS NOT NULL AND TRIM(CAST({_q_ident(col)} AS TEXT)) <> '' LIMIT {int(limit)}"
        )
        rows = conn.execute(sql).fetchall()
        vals: List[str] = []
        for r in rows:
            v = str(r[0] if not isinstance(r, sqlite3.Row) else r["v"]).strip()
            if not v:
                continue
            v = re.sub(r"\s+", " ", v)
            if len(v) > 120:
                v = v[:117] + "..."
            vals.append(v)
        return vals
    except Exception:
        return []


def _infer_column_semantics(name: str, col_type: str, sample_values: List[str]) -> Dict[str, Any]:
    n = str(name or "").strip().lower()
    t = str(col_type or "").strip().lower()
    samples = [str(v).strip() for v in (sample_values or []) if str(v).strip()]
    joined = " ".join(samples).lower()

    def _has_any(*keys: str) -> bool:
        return any(k in n for k in keys)

    if n in {"id", "defect_id", "test_id", "run_id", "case_id", "ticket_id", "work_item_id"} or n.endswith("_id"):
        return {"semantic_type": "identifier", "meaning": "实体唯一标识ID", "aliases": ["id", "编号", "ticket", "work item"]}

    if _has_any("creation_time", "created", "create_time", "ctime", "date_created"):
        return {"semantic_type": "time", "meaning": "创建时间（用于新增趋势）", "aliases": ["创建时间", "新增时间", "creation time"]}
    if _has_any("last_modified", "updated", "update_time", "closed_time", "finish_time", "resolved_time"):
        return {"semantic_type": "time", "meaning": "状态更新时间/关闭时间（用于处理时效）", "aliases": ["更新时间", "关闭时间", "resolved time"]}
    if _has_any("week", "test_week", "cw"):
        return {"semantic_type": "time_bucket", "meaning": "测试周/周维度时间桶", "aliases": ["周", "calendar week", "cw"]}

    if _has_any("status", "phase", "state", "lifecycle") or re.search(r"\b(open|closed|fixed|resolved|in progress|blocked)\b", joined):
        return {"semantic_type": "status", "meaning": "状态/阶段字段（用于流转和关闭率）", "aliases": ["状态", "阶段", "phase", "status"]}

    if _has_any("severity", "priority", "matrix") or re.search(r"\b(critical|major|minor|s1|s2|s3|s4)\b", joined):
        return {"semantic_type": "severity", "meaning": "严重度/优先级字段", "aliases": ["严重度", "优先级", "risk level"]}

    if _has_any("tester", "detected_by", "reporter", "found_by", "author", "owner", "assignee"):
        return {"semantic_type": "person", "meaning": "人员字段（发现人/负责人/处理人）", "aliases": ["测试员", "发现人", "负责人", "owner", "reporter"]}

    if _has_any("project", "tproject", "vehicle", "carline"):
        return {"semantic_type": "project", "meaning": "项目/车系维度", "aliases": ["项目", "车系", "project"]}

    if _has_any("aida", "product_area", "module", "component", "domain", "ecu", "fv"):
        return {"semantic_type": "module", "meaning": "模块/域/组件维度", "aliases": ["aida", "模块", "域", "ecu", "fv"]}

    if _has_any("risk", "score", "topissue"):
        return {"semantic_type": "risk", "meaning": "风险相关字段（风险分/TopIssue）", "aliases": ["风险", "risk score", "topissue"]}

    if _has_any("result", "passed", "failed", "blocked", "verdict") or re.search(r"\b(pass|passed|fail|failed|blocked|aborted|ng)\b", joined):
        return {"semantic_type": "test_result", "meaning": "测试执行结果字段", "aliases": ["通过", "失败", "blocked", "结果"]}

    if _has_any("version", "release", "istep", "milestone"):
        return {"semantic_type": "version", "meaning": "版本/里程碑字段", "aliases": ["版本", "release", "milestone"]}

    if "int" in t or "real" in t or "float" in t or "double" in t or "numeric" in t:
        return {"semantic_type": "numeric", "meaning": "数值字段（可聚合统计）", "aliases": ["count", "sum", "avg"]}

    return {"semantic_type": "text", "meaning": "文本维度字段", "aliases": ["文本", "维度"]}


def _q_ident(name: str) -> str:
    return '"' + str(name or "").replace('"', '""') + '"'

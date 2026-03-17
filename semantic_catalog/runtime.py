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
                    return db_data
            except Exception:
                pass
        data: Dict[str, Any] = {"datasets": [], "metrics": [], "charts": [], "schema_version": "unknown"}
        data.update(self._load_json(self._path("datasets.json")) or {})
        metrics = self._load_json(self._path("metrics.json")) or {}
        charts = self._load_json(self._path("charts.json")) or {}
        if isinstance(metrics.get("metrics"), list):
            data["metrics"] = metrics["metrics"]
        if isinstance(charts.get("charts"), list):
            data["charts"] = charts["charts"]
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
        return SemanticSelection(datasets=datasets, metrics=metrics, charts=charts)


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
    if not blocks:
        return ""
    header = "以下为系统内置的语义目录（配置驱动），用于约束与增强分析。不得编造未在目录中的口径。"
    return header + "\n\n" + "\n\n".join(blocks)


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

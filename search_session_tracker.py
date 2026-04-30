"""
Search Session Tracker for duplicate-issue search.

Records every search session: query, result set, and subsequent user actions
(clicks, explicit feedback). This data is later mined by TrainingDataMiner
to produce training pairs/triplets automatically — no manual labeling required.

Storage: SQLite (same database as feedback_store).
"""

import hashlib
import logging
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "database", "ticket_embeddings.db"
)

_SESSION_DDL = """
CREATE TABLE IF NOT EXISTS search_sessions (
    session_id    TEXT PRIMARY KEY,
    query_text    TEXT NOT NULL,
    query_hash    TEXT NOT NULL,
    user_id       TEXT,
    result_count  INTEGER DEFAULT 0,
    model_phase   TEXT DEFAULT 'baseline',
    created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS search_results (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT NOT NULL,
    ticket_id             TEXT NOT NULL,
    rank_pos              INTEGER NOT NULL,
    similarity            REAL,
    was_clicked           INTEGER DEFAULT 0,
    was_explicit_positive INTEGER DEFAULT 0,
    was_explicit_negative INTEGER DEFAULT 0,
    was_explicit_uncertain INTEGER DEFAULT 0,
    created_at            REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ses_hash ON search_sessions(query_hash);
CREATE INDEX IF NOT EXISTS idx_ses_time ON search_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_sres_session ON search_results(session_id);
CREATE INDEX IF NOT EXISTS idx_sres_ticket ON search_results(ticket_id);
"""


class SearchSessionTracker:
    """Track every duplicate search session for later training-data mining."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH):
        self.db_path = db_path
        self._local = threading.local()
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._ensure_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, '_conn') or self._local._conn is None:
            self._local._conn = sqlite3.connect(self.db_path)
        return self._local._conn

    def _ensure_schema(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.executescript(_SESSION_DDL)
        conn.commit()
        conn.close()

    @staticmethod
    def query_hash(text: str) -> str:
        return hashlib.md5((text or "").strip().encode("utf-8", errors="replace")).hexdigest()

    # ------------------------------------------------------------------
    # Write API (called from Dash callbacks)
    # ------------------------------------------------------------------

    def begin_session(
        self,
        query_text: str,
        candidates: Sequence[Any],
        user_id: Optional[str] = None,
        model_phase: str = "baseline",
    ) -> str:
        """Call when a duplicate search completes. Records the full result set."""
        session_id = uuid.uuid4().hex[:12]
        now = time.time()

        conn = self._conn()
        conn.execute(
            "INSERT INTO search_sessions "
            "(session_id, query_text, query_hash, user_id, result_count, model_phase, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, query_text.strip(), self.query_hash(query_text),
             user_id, len(candidates), model_phase, now),
        )

        for i, c in enumerate(candidates):
            tid = getattr(c, "ticket_id", None) or ""
            sim = float(getattr(c, "similarity", 0.0) or 0.0)
            conn.execute(
                "INSERT INTO search_results "
                "(session_id, ticket_id, rank_pos, similarity, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, tid, i, sim, now),
            )

        conn.commit()
        return session_id

    def record_explicit(
        self,
        session_id: str,
        ticket_id: str,
        signal: str,
    ) -> None:
        """Record an explicit user action (positive / negative / uncertain)."""
        pos = 1 if signal == "positive" else 0
        neg = 1 if signal == "negative" else 0
        unc = 1 if signal == "uncertain" else 0
        conn = self._conn()
        conn.execute(
            "UPDATE search_results "
            "SET was_explicit_positive=?, was_explicit_negative=?, was_explicit_uncertain=? "
            "WHERE session_id=? AND ticket_id=?",
            (pos, neg, unc, session_id, ticket_id),
        )
        conn.commit()

    def record_click(self, session_id: str, ticket_id: str) -> None:
        """Record that the user clicked/opened a ticket from the results."""
        conn = self._conn()
        conn.execute(
            "UPDATE search_results SET was_clicked=1 "
            "WHERE session_id=? AND ticket_id=?",
            (session_id, ticket_id),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Read API (for monitoring / mining)
    # ------------------------------------------------------------------

    def session_count(self) -> int:
        conn = self._conn()
        row = conn.execute("SELECT COUNT(*) AS cnt FROM search_sessions").fetchone()
        return int(row[0])

    def feedback_coverage(self) -> Dict[str, Any]:
        """How many sessions have at least one explicit label."""
        conn = self._conn()
        total = conn.execute("SELECT COUNT(*) FROM search_sessions").fetchone()[0]
        labeled = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM search_results "
            "WHERE was_explicit_positive=1 OR was_explicit_negative=1"
        ).fetchone()[0]
        clicked = conn.execute(
            "SELECT COUNT(DISTINCT session_id) FROM search_results WHERE was_clicked=1"
        ).fetchone()[0]
        return {
            "total_sessions": total,
            "sessions_with_label": labeled,
            "sessions_with_click": clicked,
            "label_rate": labeled / max(1, total),
        }

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        session = conn.execute(
            "SELECT * FROM search_sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        if not session:
            return None
        results = conn.execute(
            "SELECT * FROM search_results WHERE session_id=? ORDER BY rank_pos",
            (session_id,),
        ).fetchall()
        return {
            "session": dict(session),
            "results": [dict(r) for r in results],
        }

    def get_recent_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM search_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        import datetime as _dt
        result = []
        for r in rows:
            d = dict(r)
            ts = d.get("created_at")
            if isinstance(ts, (int, float)):
                d["created_at"] = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            q = str(d.get("query_text") or "")
            if len(q) > 60:
                d["query_text"] = q[:57] + "..."
            result.append(d)
        return result


# ---------------------------------------------------------------------------
# Singleton + TrainingDataMiner
# ---------------------------------------------------------------------------

_tracker_instance: Optional[SearchSessionTracker] = None


def get_session_tracker(db_path: Optional[str] = None) -> SearchSessionTracker:
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = SearchSessionTracker(db_path or _DEFAULT_DB_PATH)
    return _tracker_instance


class TrainingDataMiner:
    """Mine training pairs from search-session logs."""

    def __init__(self, tracker: Optional[SearchSessionTracker] = None):
        self.tracker = tracker or get_session_tracker()

    def mine(self, min_sessions: int = 10) -> Dict[str, Any]:
        """
        Produce training data from all recorded sessions.

        Returns:
            {
                "pairs":     [{query, ticket_id, label, weight, source}, ...],
                "triplets":  [{query, positive_id, negative_id, weight}, ...],
                "stats":     {...},
            }
        """
        conn = sqlite3.connect(self.tracker.db_path)
        conn.row_factory = sqlite3.Row

        sessions = conn.execute(
            "SELECT * FROM search_sessions ORDER BY created_at ASC"
        ).fetchall()

        if len(sessions) < min_sessions:
            return {
                "pairs": [], "triplets": [],
                "stats": {"sessions": len(sessions), "ready": False},
            }

        pairs: List[Dict[str, Any]] = []
        triplets: List[Dict[str, Any]] = []

        for session in sessions:
            sid = session["session_id"]
            query = session["query_text"]

            results = conn.execute(
                "SELECT * FROM search_results WHERE session_id=? ORDER BY rank_pos",
                (sid,),
            ).fetchall()

            if not results:
                continue

            positives: List[Tuple[str, float]] = []   # (ticket_id, weight)
            negatives: List[Tuple[str, float]] = []

            has_any_click = any(r["was_clicked"] for r in results)

            for r in results:
                tid = r["ticket_id"]
                rank = r["rank_pos"]

                # ── Explicit signals (strongest) ──
                if r["was_explicit_positive"]:
                    positives.append((tid, 1.0))
                    pairs.append({
                        "query": query, "ticket_id": tid,
                        "label": 1, "weight": 1.0, "source": "explicit",
                    })
                    continue

                if r["was_explicit_negative"]:
                    negatives.append((tid, 1.0))
                    pairs.append({
                        "query": query, "ticket_id": tid,
                        "label": 0, "weight": 1.0, "source": "explicit",
                    })
                    continue

                if r["was_explicit_uncertain"]:
                    # Uncertain → skip training, but count as "seen"
                    continue

                # ── Implicit signals ──
                if r["was_clicked"]:
                    positives.append((tid, 0.6))
                    pairs.append({
                        "query": query, "ticket_id": tid,
                        "label": 1, "weight": 0.6, "source": "implicit_click",
                    })
                elif rank < 5:
                    # Ranked high but user ignored → negative
                    negatives.append((tid, 0.3))
                    pairs.append({
                        "query": query, "ticket_id": tid,
                        "label": 0, "weight": 0.3, "source": "implicit_skip",
                    })

            # Whole-page rejection: no clicks, no labels at all
            if not positives and not has_any_click:
                for r in results[:5]:
                    pairs.append({
                        "query": query, "ticket_id": r["ticket_id"],
                        "label": 0, "weight": 0.4, "source": "reject_all",
                    })

            # Build triplets from this session
            for pos_tid, pos_w in positives:
                for neg_tid, neg_w in negatives:
                    triplets.append({
                        "query": query,
                        "positive_id": pos_tid,
                        "negative_id": neg_tid,
                        "weight": min(pos_w, neg_w),
                    })

        conn.close()

        stats = {
            "sessions": len(sessions),
            "ready": True,
            "pairs": len(pairs),
            "triplets": len(triplets),
            "positive_pairs": sum(1 for p in pairs if p["label"] == 1),
            "negative_pairs": sum(1 for p in pairs if p["label"] == 0),
            "explicit_pairs": sum(1 for p in pairs if p.get("source") == "explicit"),
            "implicit_pairs": sum(1 for p in pairs if p.get("source") != "explicit"),
        }

        return {"pairs": pairs, "triplets": triplets, "stats": stats}

    def export_for_embedding_finetune(
        self, output_dir: str, min_pairs: int = 50,
    ) -> Optional[str]:
        """
        Export mined data to JSONL files compatible with train_embedding.py.
        Returns output directory path, or None if not enough data.
        """
        import json

        mined = self.mine()
        if mined["stats"]["pairs"] < min_pairs:
            logger.info(
                "Not enough data for export: %d pairs (need %d)",
                mined["stats"]["pairs"], min_pairs,
            )
            return None

        os.makedirs(output_dir, exist_ok=True)

        # Load ticket texts from defect DB for embedding fine-tune
        ticket_texts = self._load_ticket_texts()

        # Export pairs (for MNRL)
        pair_path = os.path.join(output_dir, "mined_pairs.jsonl")
        with open(pair_path, "w", encoding="utf-8") as f:
            for p in mined["pairs"]:
                if p["label"] == 1 and p["ticket_id"] in ticket_texts:
                    f.write(json.dumps({
                        "anchor": p["query"],
                        "positive": ticket_texts[p["ticket_id"]],
                        "weight": p["weight"],
                    }, ensure_ascii=False) + "\n")

        # Export triplets (for TripletLoss)
        triplet_path = os.path.join(output_dir, "mined_triplets.jsonl")
        with open(triplet_path, "w", encoding="utf-8") as f:
            for t in mined["triplets"]:
                pos_text = ticket_texts.get(t["positive_id"])
                neg_text = ticket_texts.get(t["negative_id"])
                if pos_text and neg_text:
                    f.write(json.dumps({
                        "anchor": t["query"],
                        "positive": pos_text,
                        "negative": neg_text,
                        "weight": t["weight"],
                    }, ensure_ascii=False) + "\n")

        # Stats
        meta_path = os.path.join(output_dir, "mined_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(mined["stats"], f, indent=2, ensure_ascii=False)

        logger.info("Exported to %s: %d pairs, %d triplets",
                     output_dir, mined["stats"]["pairs"], mined["stats"]["triplets"])
        return output_dir

    def _load_ticket_texts(self) -> Dict[str, str]:
        """Load ticket_id → document text from defect database."""
        from duplicate_issue_finder import _build_document, _normalize_text, DEFAULT_TEXT_FIELDS
        try:
            from data_processor import load_defect_data
            df = load_defect_data()
        except Exception:
            return {}

        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return {}

        import pandas as pd
        texts: Dict[str, str] = {}
        for _, row in df.iterrows():
            tid = str(row.get("id") or row.get("defect_id") or "").strip()
            if not tid:
                continue
            doc = _build_document(row, DEFAULT_TEXT_FIELDS)
            if doc:
                texts[tid] = doc
        return texts


__all__ = [
    "SearchSessionTracker",
    "TrainingDataMiner",
    "get_session_tracker",
]

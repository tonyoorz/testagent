import hashlib
import glob
import json
import os
import re
import sqlite3
import time
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine_similarity
except Exception:  # pragma: no cover
    TfidfVectorizer = None
    sklearn_cosine_similarity = None

try:
    import chromadb

    CHROMADB_AVAILABLE = True
except Exception:  # pragma: no cover
    chromadb = None
    CHROMADB_AVAILABLE = False

# ---------------------------------------------------------------------------
# Sentence-transformer embedding (preferred, semantic understanding)
# ---------------------------------------------------------------------------
_DEFAULT_EMBEDDING_MODEL_ID = "BAAI/bge-small-zh-v1.5"
_EMBEDDING_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "cache", "embedding_models"
)


def _discover_local_embedding_model() -> Optional[str]:
    """Prefer a local model directory when available to avoid network dependency."""
    local_base = os.path.join(_EMBEDDING_CACHE_DIR, "modelscope", "BAAI")
    if not os.path.isdir(local_base):
        return None

    patterns = [
        os.path.join(local_base, "bge-small-zh-v1.5"),
        os.path.join(local_base, "bge-small-zh-v1___5"),
        os.path.join(local_base, "bge-small-zh-v1*"),
    ]
    for pattern in patterns:
        for candidate in sorted(glob.glob(pattern)):
            if os.path.isfile(os.path.join(candidate, "config.json")):
                return candidate
    return None


_DEFAULT_EMBEDDING_MODEL = os.getenv(
    "DUPLICATE_EMBEDDING_MODEL",
    _discover_local_embedding_model() or _DEFAULT_EMBEDDING_MODEL_ID,
)
_DEFAULT_VECTOR_BACKEND = os.getenv("DUPLICATE_VECTOR_BACKEND", "sqlite").strip().lower() or "sqlite"
_CHROMA_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "cache", "duplicate_chroma"
)

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMER_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    SENTENCE_TRANSFORMER_AVAILABLE = False

_st_model_instance = None


def _get_st_model() -> Any:
    """Lazy-load the sentence-transformer model (singleton)."""
    global _st_model_instance
    if _st_model_instance is not None:
        return _st_model_instance
    if not SENTENCE_TRANSFORMER_AVAILABLE:
        return None
    try:
        os.makedirs(_EMBEDDING_CACHE_DIR, exist_ok=True)
        _st_model_instance = SentenceTransformer(
            _DEFAULT_EMBEDDING_MODEL, cache_folder=_EMBEDDING_CACHE_DIR
        )
        logger.info("Loaded embedding model: %s", _DEFAULT_EMBEDDING_MODEL)
        return _st_model_instance
    except Exception as exc:
        logger.warning("Failed to load embedding model %s: %s", _DEFAULT_EMBEDDING_MODEL, exc)
        return None


# ---------------------------------------------------------------------------
# SQLite embedding cache
# ---------------------------------------------------------------------------
_DEFAULT_EMBEDDING_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "database", "ticket_embeddings.db"
)

_DDL = """
CREATE TABLE IF NOT EXISTS ticket_embeddings (
    ticket_id   TEXT PRIMARY KEY,
    text_hash   TEXT NOT NULL,
    embedding   BLOB NOT NULL,
    model_name  TEXT NOT NULL,
    updated_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_te_model ON ticket_embeddings(model_name);
"""


class _EmbeddingCache:
    """Lightweight SQLite cache for pre-computed ticket embeddings."""

    def __init__(self, db_path: str = _DEFAULT_EMBEDDING_DB):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.executescript(_DDL)
        conn.close()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    @staticmethod
    def _text_hash(text: str) -> str:
        return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()

    def get_many(
        self, ticket_ids: Sequence[str], model_name: str
    ) -> Dict[str, Tuple[str, np.ndarray]]:
        """Return {ticket_id: (text_hash, embedding_vector)} for cached tickets."""
        if not ticket_ids:
            return {}
        conn = self._conn()
        result: Dict[str, Tuple[str, np.ndarray]] = {}
        batch_size = 500
        for start in range(0, len(ticket_ids), batch_size):
            batch = ticket_ids[start : start + batch_size]
            placeholders = ",".join("?" for _ in batch)
            rows = conn.execute(
                f"SELECT ticket_id, text_hash, embedding FROM ticket_embeddings "
                f"WHERE model_name=? AND ticket_id IN ({placeholders})",
                [model_name] + list(batch),
            ).fetchall()
            for tid, thash, blob in rows:
                result[tid] = (thash, np.frombuffer(blob, dtype=np.float32))
        conn.close()
        return result

    def put_many(
        self,
        items: Sequence[Tuple[str, str, np.ndarray]],
        model_name: str,
    ) -> None:
        """Upsert (ticket_id, text_hash, embedding) rows."""
        if not items:
            return
        conn = self._conn()
        now = time.time()
        conn.executemany(
            "INSERT OR REPLACE INTO ticket_embeddings "
            "(ticket_id, text_hash, embedding, model_name, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (tid, thash, vec.astype(np.float32).tobytes(), model_name, now)
                for tid, thash, vec in items
            ],
        )
        conn.commit()
        conn.close()


_embedding_cache_instance: Optional[_EmbeddingCache] = None
_chroma_client_instance: Any = None


def _get_embedding_cache() -> _EmbeddingCache:
    global _embedding_cache_instance
    if _embedding_cache_instance is None:
        _embedding_cache_instance = _EmbeddingCache()
    return _embedding_cache_instance


def _get_chroma_client() -> Any:
    global _chroma_client_instance
    if _chroma_client_instance is not None:
        return _chroma_client_instance
    if not CHROMADB_AVAILABLE:
        return None
    try:
        os.makedirs(_CHROMA_PERSIST_DIR, exist_ok=True)
        _chroma_client_instance = chromadb.PersistentClient(path=_CHROMA_PERSIST_DIR)
        return _chroma_client_instance
    except Exception as exc:
        logger.warning("Failed to initialize ChromaDB client: %s", exc)
        return None


DEFAULT_EXCLUDED_PHASE_PREFIXES = ("00-", "06-", "09-")
DEFAULT_TEXT_FIELDS = (
    "name",
    "description",
    "error_description",
    "error_occurrence",
    "comments",
    "project",
    "pu",
    "ecu",
    "top_aida",
    "fv",
    "team",
    "fvp",
    "lead_model",
)


@dataclass(frozen=True)
class DuplicateSearchHints:
    project: Optional[str] = None
    pu: Optional[str] = None
    ecu: Optional[str] = None
    lead_model: Optional[str] = None


@dataclass(frozen=True)
class DuplicateCandidate:
    score_1_10: int
    similarity: float
    ticket_id: Optional[str]
    name: str
    project: Optional[str]
    pu: Optional[str]
    status_phase: Optional[str]
    snippet: str


def _normalize_project(value: Any) -> Optional[str]:
    text = _normalize_text(value).lower()
    return text or None


def _normalize_pu(value: Any) -> Optional[str]:
    text = _normalize_text(value).lower()
    if not text:
        return None
    text = text.replace("/", "-")
    match = re.search(r"\b(\d{2})-(\d{2})\b", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return text


def _normalize_ecu(value: Any) -> Optional[str]:
    text = _normalize_text(value).lower()
    if not text:
        return None
    text = re.sub(r"\s+", "", text)
    return text.replace("/", "-")


def _normalize_lead_model(value: Any) -> Optional[str]:
    text = _normalize_text(value).lower()
    if not text:
        return None
    return re.sub(r"\s+", "", text)


def _hint_matches(candidate_value: Any, hint_value: Optional[str], normalizer) -> bool:
    if not hint_value:
        return True
    candidate_norm = normalizer(candidate_value)
    if not candidate_norm:
        return True
    hint_norm = normalizer(hint_value)
    if not hint_norm:
        return True
    return hint_norm in candidate_norm


def _hint_matches_strict(candidate_value: Any, hint_value: Optional[str], normalizer) -> bool:
    if not hint_value:
        return False
    candidate_norm = normalizer(candidate_value)
    hint_norm = normalizer(hint_value)
    if not candidate_norm or not hint_norm:
        return False
    return hint_norm in candidate_norm


def _apply_hint_boost(similarity: float, meta: Dict[str, Any], hints: Optional[DuplicateSearchHints]) -> float:
    score = float(similarity)
    if not hints:
        return score

    if hints.project and _hint_matches_strict(meta.get("project"), hints.project, _normalize_project):
        score += 0.08
    if hints.pu and _hint_matches_strict(meta.get("pu"), hints.pu, _normalize_pu):
        score += 0.12
    if hints.ecu and _hint_matches_strict(meta.get("ecu"), hints.ecu, _normalize_ecu):
        score += 0.10
    if hints.lead_model and _hint_matches_strict(meta.get("lead_model"), hints.lead_model, _normalize_lead_model):
        score += 0.05

    return max(0.0, min(1.0, score))


# Known project names ordered longest-first so "idcevo" matches before "idc".
_PROJECT_KEYWORDS: List[Tuple[str, str]] = [
    ("idcevo", "idcevo"),
    ("idc evo", "idcevo"),
    ("idc-evo", "idcevo"),
    ("idevo", "idevo"),
    ("idc", "idc"),
    ("app", "app"),
    ("rsu", "rsu"),
]


def _strip_noise(text: str) -> str:
    """Remove punctuation / special chars that are NOT part of version tokens
    (digits, letters, slashes, hyphens, dots, underscores are kept)."""
    # Keep alphanumeric, space, and version-related separators
    return re.sub(r"[^\w\s/.\-]", " ", text)


def extract_hints(user_text: str) -> DuplicateSearchHints:
    if not user_text:
        return DuplicateSearchHints()

    # 1. Normalise: lowercase + strip noise characters
    text = _strip_noise(user_text.strip().lower())
    # collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()

    # 2. Project – longest-match-first scan on the cleaned text
    project = None
    for keyword, canonical in _PROJECT_KEYWORDS:
        if keyword in text:
            project = canonical
            break

    # 3. PU – multi-strategy extraction
    pu = None
    # Strategy A: explicit "PU" prefix with flexible separators/whitespace
    m = re.search(
        r"\bpu\s*[:：=]?\s*(\d{2})\s*[/.\-]\s*(\d{2})\b",
        text, flags=re.IGNORECASE,
    )
    if m:
        pu = f"{m.group(1)}-{m.group(2)}"
    else:
        # Strategy B: bare NN/NN or NN-NN (2-digit pairs)
        m = re.search(r"\b(\d{2})\s*[/.\-]\s*(\d{2})\b", text)
        if m:
            pu = f"{m.group(1)}-{m.group(2)}"
        else:
            # Strategy C: freeform "PU" followed by an identifier like "EE", "HV"
            m = re.search(
                r"\bpu\s*[:：=]?\s*([a-z0-9][a-z0-9._\-]{0,15})\b",
                text, flags=re.IGNORECASE,
            )
            if m:
                pu = _normalize_pu(m.group(1).strip())

    ecu = None
    m = re.search(
        r"\becu\s*[:：=]?\s*([a-z0-9][a-z0-9._/\-]{1,31})\b",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        ecu = _normalize_ecu(m.group(1).strip())

    lead_model = None
    m = re.search(
        r"\blead(?:\s|_)?model\s*[:：=]?\s*([a-z0-9][a-z0-9._/\-]{0,15})\b",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        lead_model = _normalize_lead_model(m.group(1).strip())

    return DuplicateSearchHints(project=project, pu=pu, ecu=ecu, lead_model=lead_model)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    s = str(value)
    s = s.replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


_COMMENT_MAX_CHARS = 280
_COMMENT_TOTAL_BUDGET = 600
_COMMENT_SIGNAL_TERMS = (
    "root cause",
    "trace",
    "timeout",
    "failed",
    "failure",
    "error",
    "exception",
    "reproduce",
    "steps",
    "stack",
    "log",
    "logs",
    "gateway",
    "retry",
    "wake",
    "boot",
    "handshake",
    "canoe",
    "kl15",
)
_COMMENT_LOW_SIGNAL_TERMS = (
    "thanks",
    "thank you",
    "will check",
    "check again",
    "tomorrow",
    "noted",
    "ok",
    "okay",
)


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    truncated = text[: max_chars - 1].rsplit(" ", 1)[0].strip()
    if not truncated:
        truncated = text[: max_chars - 1].strip()
    return truncated + "…"


def _comment_signal_score(text: str) -> int:
    lowered = text.lower()
    score = 0

    if len(text) >= 40:
        score += 1
    if len(text) >= 120:
        score += 1

    score += sum(2 for term in _COMMENT_SIGNAL_TERMS if term in lowered)
    score -= sum(2 for term in _COMMENT_LOW_SIGNAL_TERMS if term in lowered)

    tokens = re.findall(r"\b[a-z0-9][a-z0-9._\-/]*\b", lowered)
    if tokens:
        unique_ratio = len(set(tokens)) / len(tokens)
        if len(tokens) >= 12 and unique_ratio < 0.45:
            score -= 2

    return score


def _select_comment_entries(entries: Sequence[str]) -> List[str]:
    scored = [(_comment_signal_score(text), idx, text) for idx, text in enumerate(entries)]
    positive = [item for item in scored if item[0] > 0]
    ranked = positive if positive else scored
    ranked.sort(key=lambda item: (item[0], len(item[2])), reverse=True)

    selected: List[str] = []
    remaining = _COMMENT_TOTAL_BUDGET
    for _, _, text in ranked:
        if remaining < 32:
            break
        normalized = _truncate_text(text, min(_COMMENT_MAX_CHARS, remaining))
        if not normalized:
            continue
        selected.append(normalized)
        remaining -= len(normalized) + 1
    return selected


def _normalize_comments_text(value: Any) -> str:
    if value is None:
        return ""

    parsed = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if text[:1] in ("[", "{"):
            try:
                parsed = json.loads(text)
            except Exception:
                return _normalize_text(value)
        else:
            return _normalize_text(value)

    entries: List[str] = []
    if isinstance(parsed, dict):
        parsed = [parsed]
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                comment_text = _normalize_text(item.get("text"))
                if comment_text:
                    entries.append(comment_text)
            else:
                comment_text = _normalize_text(item)
                if comment_text:
                    entries.append(comment_text)
    return "\n".join(_select_comment_entries(entries)).strip()


def _normalize_document_field(field: str, value: Any) -> str:
    if field == "comments":
        return _normalize_comments_text(value)
    return _normalize_text(value)


def _build_document(row: pd.Series, fields: Sequence[str]) -> str:
    parts: List[str] = []
    for f in fields:
        if f not in row:
            continue
        v = _normalize_document_field(f, row.get(f))
        if not v:
            continue
        parts.append(v)
    return "\n".join(parts)


def _to_score_1_10(similarity: float) -> int:
    try:
        sim = float(similarity)
    except Exception:
        return 1
    if sim < 0:
        sim = 0.0
    if sim > 1:
        sim = 1.0
    return max(1, min(10, int(round(sim * 9 + 1))))


def _phase_is_excluded(status_phase: Any, excluded_prefixes: Sequence[str]) -> bool:
    s = _normalize_text(status_phase).lower()
    if not s:
        return False
    for prefix in excluded_prefixes:
        p = str(prefix).lower()
        if s.startswith(p):
            return True
    return False


def _safe_snippet(text: Any, max_len: int = 240) -> str:
    s = _normalize_text(text)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _safe_collection_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", value or "duplicate_index").strip("_")
    if len(name) < 3:
        name = (name + "___")[:3]
    return name[:63]


def _build_chroma_where(hints: Optional[DuplicateSearchHints]) -> Optional[Dict[str, Any]]:
    if hints is None:
        return None
    clauses: List[Dict[str, Any]] = []
    if hints.project:
        clauses.append({"project_norm": _normalize_project(hints.project)})
    if hints.pu:
        clauses.append({"pu_norm": _normalize_pu(hints.pu)})
    if hints.ecu:
        clauses.append({"ecu_norm": _normalize_ecu(hints.ecu)})
    if hints.lead_model:
        clauses.append({"lead_model_norm": _normalize_lead_model(hints.lead_model)})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _get_chroma_max_batch_size(client: Any) -> Optional[int]:
    if client is None:
        return None
    getter = getattr(client, "get_max_batch_size", None)
    if callable(getter):
        try:
            value = int(getter())
            return value if value > 0 else None
        except Exception:
            return None
    value = getattr(client, "max_batch_size", None)
    try:
        value = int(value)
    except Exception:
        return None
    return value if value > 0 else None


class DuplicateIssueIndex:
    def __init__(
        self,
        excluded_phase_prefixes: Sequence[str] = DEFAULT_EXCLUDED_PHASE_PREFIXES,
        text_fields: Sequence[str] = DEFAULT_TEXT_FIELDS,
        vector_backend: str = _DEFAULT_VECTOR_BACKEND,
    ):
        self.excluded_phase_prefixes = tuple(excluded_phase_prefixes)
        self.text_fields = tuple(text_fields)
        self.vector_backend = str(vector_backend or "sqlite").strip().lower() or "sqlite"
        # TF-IDF backend (fallback)
        self._vectorizer = None
        self._matrix = None
        # Embedding backend (preferred)
        self._embedding_matrix: Optional[np.ndarray] = None
        self._use_embeddings = False
        self._use_chroma = False
        self._chroma_collection = None
        self._meta_index_by_ticket_id: Dict[str, int] = {}
        # Shared
        self._meta: List[Dict[str, Any]] = []
        self._documents: List[str] = []
        self._built_at = 0.0
        self._row_count = 0

    @property
    def ready(self) -> bool:
        if self._use_chroma and self._chroma_collection is not None and self._meta:
            return True
        if self._use_embeddings and self._embedding_matrix is not None and self._meta:
            return True
        return bool(self._vectorizer is not None and self._matrix is not None and self._meta)

    def build_from_df(self, df: pd.DataFrame) -> "DuplicateIssueIndex":
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            self._vectorizer = None
            self._matrix = None
            self._embedding_matrix = None
            self._use_embeddings = False
            self._use_chroma = False
            self._chroma_collection = None
            self._meta_index_by_ticket_id = {}
            self._meta = []
            self._documents = []
            self._built_at = time.time()
            self._row_count = 0
            return self

        work = df.copy()
        if "status_phase" in work.columns:
            mask = ~work["status_phase"].apply(lambda x: _phase_is_excluded(x, self.excluded_phase_prefixes))
            work = work[mask]

        work = work.reset_index(drop=True)
        self._row_count = len(work)

        documents = [_build_document(work.iloc[i], self.text_fields) for i in range(len(work))]
        documents = [d if d else _normalize_text(work.iloc[i].get("name") if "name" in work.columns else "") for i, d in enumerate(documents)]
        self._documents = documents

        self._meta = []
        for i in range(len(work)):
            row = work.iloc[i]
            self._meta.append(
                {
                    "ticket_id": _normalize_text(row.get("id")) or _normalize_text(row.get("defect_id")) or None,
                    "name": _normalize_text(row.get("name")) or _normalize_text(row.get("title")) or "",
                    "project": _normalize_text(row.get("project")) or None,
                    "pu": _normalize_text(row.get("pu")) or None,
                    "ecu": _normalize_text(row.get("ecu")) or None,
                    "lead_model": _normalize_text(row.get("lead_model")) or None,
                    "status_phase": _normalize_text(row.get("status_phase")) or None,
                    "description": _normalize_text(row.get("description")) or "",
                }
            )
        self._meta_index_by_ticket_id = {
            str(meta.get("ticket_id")): idx
            for idx, meta in enumerate(self._meta)
            if meta.get("ticket_id")
        }

        # --- Try sentence-transformer embeddings first ---
        st_model = _get_st_model()
        if st_model is not None:
            try:
                self._build_embedding_index(st_model, documents)
                logger.info(
                    "Built embedding index: %d tickets, model=%s",
                    len(documents), _DEFAULT_EMBEDDING_MODEL,
                )
                self._built_at = time.time()
                return self
            except Exception as exc:
                logger.warning("Embedding index build failed, falling back to TF-IDF: %s", exc)

        # --- Fallback: TF-IDF ---
        self._embedding_matrix = None
        self._use_embeddings = False

        if TfidfVectorizer is None or sklearn_cosine_similarity is None:
            self._vectorizer = None
            self._matrix = None
            self._built_at = time.time()
            return self

        vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            max_features=200_000,
            lowercase=True,
        )
        self._matrix = vectorizer.fit_transform(documents)
        self._vectorizer = vectorizer
        self._built_at = time.time()
        return self

    def _build_embedding_index(self, st_model: Any, documents: List[str]) -> None:
        """Build numpy embedding matrix with SQLite cache for incremental updates."""
        cache = _get_embedding_cache()
        model_name = _DEFAULT_EMBEDDING_MODEL

        # Gather ticket IDs and text hashes
        ticket_ids = [m.get("ticket_id") or f"__idx_{i}" for i, m in enumerate(self._meta)]
        text_hashes = [_EmbeddingCache._text_hash(doc) for doc in documents]

        # Load cached embeddings
        cached = cache.get_many(ticket_ids, model_name)

        # Find which tickets need (re-)encoding
        to_encode_indices: List[int] = []
        for i, tid in enumerate(ticket_ids):
            entry = cached.get(tid)
            if entry is None or entry[0] != text_hashes[i]:
                to_encode_indices.append(i)

        # Encode missing/stale tickets
        if to_encode_indices:
            texts_to_encode = [documents[i] for i in to_encode_indices]
            new_vecs = st_model.encode(
                texts_to_encode, batch_size=64, show_progress_bar=False, normalize_embeddings=True,
            )
            # Persist to cache
            items = [
                (ticket_ids[i], text_hashes[i], new_vecs[j])
                for j, i in enumerate(to_encode_indices)
            ]
            cache.put_many(items, model_name)
            # Merge into cached dict
            for j, i in enumerate(to_encode_indices):
                cached[ticket_ids[i]] = (text_hashes[i], new_vecs[j])
            logger.info(
                "Embedding cache: %d cached, %d newly encoded",
                len(ticket_ids) - len(to_encode_indices), len(to_encode_indices),
            )

        # Assemble matrix in original order
        vecs = [cached[tid][1] for tid in ticket_ids]
        self._embedding_matrix = np.vstack(vecs).astype(np.float32)
        self._use_embeddings = True
        self._use_chroma = False
        self._chroma_collection = None

        if self.vector_backend == "chroma":
            if self._build_chroma_index(ticket_ids, documents, self._embedding_matrix):
                self._use_chroma = True

    def _build_chroma_index(
        self,
        ticket_ids: Sequence[str],
        documents: Sequence[str],
        embedding_matrix: np.ndarray,
    ) -> bool:
        client = _get_chroma_client()
        if client is None:
            return False
        try:
            signature = hashlib.md5(
                "|".join(ticket_ids).encode("utf-8", errors="replace")
            ).hexdigest()[:16]
            collection_name = _safe_collection_name(
                f"duplicate_{self.vector_backend}_{_DEFAULT_EMBEDDING_MODEL}_{signature}"
            )
            collection = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            metadatas: List[Dict[str, Any]] = []
            for meta in self._meta:
                chroma_meta = {
                    key: value
                    for key, value in meta.items()
                    if value is not None and value != ""
                }
                project_norm = _normalize_project(meta.get("project"))
                pu_norm = _normalize_pu(meta.get("pu"))
                ecu_norm = _normalize_ecu(meta.get("ecu"))
                lead_model_norm = _normalize_lead_model(meta.get("lead_model"))
                if project_norm:
                    chroma_meta["project_norm"] = project_norm
                if pu_norm:
                    chroma_meta["pu_norm"] = pu_norm
                if ecu_norm:
                    chroma_meta["ecu_norm"] = ecu_norm
                if lead_model_norm:
                    chroma_meta["lead_model_norm"] = lead_model_norm
                metadatas.append(chroma_meta)
            all_ids = list(ticket_ids)
            all_embeddings = embedding_matrix.astype(np.float32).tolist()
            all_documents = list(documents)
            batch_size = _get_chroma_max_batch_size(client) or len(all_ids)
            for start in range(0, len(all_ids), batch_size):
                end = start + batch_size
                collection.upsert(
                    ids=all_ids[start:end],
                    embeddings=all_embeddings[start:end],
                    documents=all_documents[start:end],
                    metadatas=metadatas[start:end],
                )
            self._chroma_collection = collection
            return True
        except Exception as exc:
            logger.warning("Failed to build ChromaDB index, falling back to numpy matrix: %s", exc)
            self._chroma_collection = None
            return False

    def _coarse_search(self, query: str, hints: Optional[DuplicateSearchHints], top_k: int) -> List[DuplicateCandidate]:
        q = _normalize_text(query)
        if not q:
            return []
        if not self.ready:
            return self._keyword_fallback(q, hints=hints, top_k=top_k)

        try:
            if self._use_chroma and self._chroma_collection is not None:
                return self._chroma_search(q, hints=hints, top_k=top_k)
            if self._use_embeddings and self._embedding_matrix is not None:
                sims = self._embedding_search(q)
            else:
                qv = self._vectorizer.transform([q])
                sims = sklearn_cosine_similarity(self._matrix, qv).reshape(-1)
        except Exception as e:
            logger.warning(f"duplicate search failed, fallback to keyword: {e}")
            return self._keyword_fallback(q, hints=hints, top_k=top_k)

        ranked: List[Tuple[int, float]] = []
        for idx, raw_sim in enumerate(sims):
            meta = self._meta[idx]
            if hints:
                if hints.project and not _hint_matches(meta.get("project"), hints.project, _normalize_project):
                    continue
                if hints.pu and not _hint_matches(meta.get("pu"), hints.pu, _normalize_pu):
                    continue
            ranked.append((idx, _apply_hint_boost(float(raw_sim), meta, hints)))

        ranked.sort(key=lambda x: float(x[1]), reverse=True)
        return self._ranked_to_candidates(ranked, top_k=top_k)

    def _chroma_search(self, query: str, hints: Optional[DuplicateSearchHints], top_k: int) -> List[DuplicateCandidate]:
        st_model = _get_st_model()
        if st_model is None or self._chroma_collection is None:
            raise RuntimeError("Chroma search backend not available")
        qvec = st_model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False,
        ).astype(np.float32)
        result_count = min(len(self._meta), max(max(1, int(top_k)) * 8, 50))
        result = self._chroma_collection.query(
            query_embeddings=qvec.tolist(),
            n_results=result_count,
            include=["distances"],
            where=_build_chroma_where(hints),
        )
        ids = ((result or {}).get("ids") or [[]])[0]
        distances = ((result or {}).get("distances") or [[]])[0]

        ranked: List[Tuple[int, float]] = []
        for pos, ticket_id in enumerate(ids):
            idx = self._meta_index_by_ticket_id.get(_normalize_text(ticket_id))
            if idx is None:
                continue
            meta = self._meta[idx]
            if hints:
                if hints.project and not _hint_matches(meta.get("project"), hints.project, _normalize_project):
                    continue
                if hints.pu and not _hint_matches(meta.get("pu"), hints.pu, _normalize_pu):
                    continue
            distance = distances[pos] if pos < len(distances) else None
            raw_sim = 1.0 if distance is None else max(0.0, min(1.0, 1.0 - float(distance)))
            ranked.append((idx, _apply_hint_boost(raw_sim, meta, hints)))

        ranked.sort(key=lambda item: float(item[1]), reverse=True)
        return self._ranked_to_candidates(ranked, top_k=top_k)

    def _ranked_to_candidates(self, ranked: Sequence[Tuple[int, float]], top_k: int) -> List[DuplicateCandidate]:
        candidates: List[DuplicateCandidate] = []
        for idx, sim in ranked[: max(1, int(top_k))]:
            meta = self._meta[idx]
            candidates.append(
                DuplicateCandidate(
                    score_1_10=_to_score_1_10(float(sim)),
                    similarity=float(sim),
                    ticket_id=meta.get("ticket_id"),
                    name=meta.get("name") or "",
                    project=meta.get("project"),
                    pu=meta.get("pu"),
                    status_phase=meta.get("status_phase"),
                    snippet=_safe_snippet(meta.get("description") or ""),
                )
            )
            if len(candidates) >= top_k:
                break
        return candidates

    def search_with_metadata(
        self,
        query: str,
        hints: Optional[DuplicateSearchHints] = None,
        top_k: int = 10,
        reranker: Optional[Any] = None,
        feedback_db_path: Optional[str] = None,
    ) -> Tuple[List[DuplicateCandidate], Dict[str, Any]]:
        candidates = self._coarse_search(query, hints=hints, top_k=max(int(top_k), 50))
        metadata: Dict[str, Any] = {
            "model_phase": "baseline",
            "feedback_count": 0,
        }
        active_reranker = reranker
        if active_reranker is None and feedback_db_path is not None:
            try:
                from progressive_reranker import get_progressive_reranker

                active_reranker = get_progressive_reranker(db_path=feedback_db_path)
            except Exception:
                active_reranker = None
        if active_reranker is not None:
            try:
                candidates = active_reranker.rerank(
                    query,
                    candidates,
                    hints=hints,
                    index=self,
                    top_k=top_k,
                )
                metadata["model_phase"] = str(getattr(active_reranker, "model_phase", "baseline") or "baseline")
                metadata["feedback_count"] = int(getattr(active_reranker, "feedback_count", 0) or 0)
                return candidates[: max(1, int(top_k))], metadata
            except Exception:
                pass
        return candidates[: max(1, int(top_k))], metadata

    def search(self, query: str, hints: Optional[DuplicateSearchHints] = None, top_k: int = 10) -> List[DuplicateCandidate]:
        candidates, _ = self.search_with_metadata(query, hints=hints, top_k=top_k)
        return candidates

    def _embedding_search(self, query_text: str) -> np.ndarray:
        """Encode query and compute cosine similarity against the embedding matrix."""
        st_model = _get_st_model()
        if st_model is None:
            raise RuntimeError("sentence-transformer model not available")
        qvec = st_model.encode(
            [query_text], normalize_embeddings=True, show_progress_bar=False,
        ).astype(np.float32)
        # dot product on L2-normalised vectors == cosine similarity
        return (self._embedding_matrix @ qvec.T).reshape(-1)

    def _keyword_fallback(self, query: str, hints: Optional[DuplicateSearchHints], top_k: int) -> List[DuplicateCandidate]:
        query_l = query.lower()
        scored: List[Tuple[int, float]] = []
        for i, meta in enumerate(self._meta):
            hay = (
                f"{meta.get('name','')}\n"
                f"{meta.get('description','')}\n"
                f"{meta.get('project','')}\n"
                f"{meta.get('pu','')}\n"
                f"{meta.get('ecu','')}\n"
                f"{meta.get('lead_model','')}"
            ).lower()
            if hints:
                if hints.project and not _hint_matches(meta.get("project"), hints.project, _normalize_project):
                    continue
                if hints.pu and not _hint_matches(meta.get("pu"), hints.pu, _normalize_pu):
                    continue
            score = 0
            for token in re.findall(r"[a-z0-9_./-]{3,}", query_l):
                if token in hay:
                    score += 1
            sim = 0.0 if not score else min(1.0, score / 8.0)
            scored.append((i, _apply_hint_boost(sim, meta, hints)))

        scored.sort(key=lambda x: x[1], reverse=True)
        candidates: List[DuplicateCandidate] = []
        for idx, sim in scored[: max(1, int(top_k))]:
            meta = self._meta[idx]
            candidates.append(
                DuplicateCandidate(
                    score_1_10=_to_score_1_10(sim),
                    similarity=sim,
                    ticket_id=meta.get("ticket_id"),
                    name=meta.get("name") or "",
                    project=meta.get("project"),
                    pu=meta.get("pu"),
                    status_phase=meta.get("status_phase"),
                    snippet=_safe_snippet(meta.get("description") or ""),
                )
            )
        return candidates


_INDEX_CACHE: Dict[str, DuplicateIssueIndex] = {}


def get_or_build_index(cache_key: str, df: pd.DataFrame, excluded_phase_prefixes: Sequence[str] = DEFAULT_EXCLUDED_PHASE_PREFIXES) -> DuplicateIssueIndex:
    idx = _INDEX_CACHE.get(cache_key)
    if idx is None:
        idx = DuplicateIssueIndex(excluded_phase_prefixes=excluded_phase_prefixes)
        _INDEX_CACHE[cache_key] = idx

    expected_excluded = tuple(excluded_phase_prefixes)
    if idx.excluded_phase_prefixes != expected_excluded:
        idx = DuplicateIssueIndex(
            excluded_phase_prefixes=expected_excluded,
            text_fields=idx.text_fields,
            vector_backend=idx.vector_backend,
        )
        _INDEX_CACHE[cache_key] = idx

    if idx._row_count != (len(df) if isinstance(df, pd.DataFrame) else 0) or not idx.ready:
        idx.build_from_df(df if isinstance(df, pd.DataFrame) else pd.DataFrame())
    return idx


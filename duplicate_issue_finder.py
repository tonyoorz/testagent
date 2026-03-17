import re
import time
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception:  # pragma: no cover
    TfidfVectorizer = None
    cosine_similarity = None


DEFAULT_EXCLUDED_PHASE_PREFIXES = ("00-", "06-", "09-")
DEFAULT_TEXT_FIELDS = ("name", "description", "project", "pu", "ecu", "top_aida", "fv", "team", "fvp", "lead_model")


@dataclass(frozen=True)
class DuplicateSearchHints:
    project: Optional[str] = None
    pu: Optional[str] = None


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


def extract_hints(user_text: str) -> DuplicateSearchHints:
    if not user_text:
        return DuplicateSearchHints()

    text = user_text.strip().lower()

    project = None
    if "idcevo" in text:
        project = "idcevo"
    elif "idevo" in text:
        project = "idevo"
    elif "app" in text:
        project = "app"

    pu = None
    m = re.search(r"\bpu\s*[:：]?\s*([a-z0-9._-]{2,})\b", text, flags=re.IGNORECASE)
    if m:
        pu = m.group(1).strip()

    return DuplicateSearchHints(project=project, pu=pu)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    s = str(value)
    s = s.replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _build_document(row: pd.Series, fields: Sequence[str]) -> str:
    parts: List[str] = []
    for f in fields:
        if f not in row:
            continue
        v = _normalize_text(row.get(f))
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


class DuplicateIssueIndex:
    def __init__(
        self,
        excluded_phase_prefixes: Sequence[str] = DEFAULT_EXCLUDED_PHASE_PREFIXES,
        text_fields: Sequence[str] = DEFAULT_TEXT_FIELDS,
    ):
        self.excluded_phase_prefixes = tuple(excluded_phase_prefixes)
        self.text_fields = tuple(text_fields)
        self._vectorizer = None
        self._matrix = None
        self._meta: List[Dict[str, Any]] = []
        self._built_at = 0.0
        self._row_count = 0

    @property
    def ready(self) -> bool:
        return bool(self._vectorizer is not None and self._matrix is not None and self._meta)

    def build_from_df(self, df: pd.DataFrame) -> "DuplicateIssueIndex":
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            self._vectorizer = None
            self._matrix = None
            self._meta = []
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

        self._meta = []
        for i in range(len(work)):
            row = work.iloc[i]
            self._meta.append(
                {
                    "ticket_id": _normalize_text(row.get("id")) or _normalize_text(row.get("defect_id")) or None,
                    "name": _normalize_text(row.get("name")) or _normalize_text(row.get("title")) or "",
                    "project": _normalize_text(row.get("project")) or None,
                    "pu": _normalize_text(row.get("pu")) or None,
                    "status_phase": _normalize_text(row.get("status_phase")) or None,
                    "description": _normalize_text(row.get("description")) or "",
                }
            )

        if TfidfVectorizer is None or cosine_similarity is None:
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

    def search(self, query: str, hints: Optional[DuplicateSearchHints] = None, top_k: int = 10) -> List[DuplicateCandidate]:
        q = _normalize_text(query)
        if not q:
            return []
        if not self.ready:
            return self._keyword_fallback(q, hints=hints, top_k=top_k)

        try:
            qv = self._vectorizer.transform([q])
            sims = cosine_similarity(self._matrix, qv).reshape(-1)
        except Exception as e:
            logger.warning(f"duplicate search failed, fallback to keyword: {e}")
            return self._keyword_fallback(q, hints=hints, top_k=top_k)

        ranked = list(enumerate(sims))
        ranked.sort(key=lambda x: float(x[1]), reverse=True)
        candidates: List[DuplicateCandidate] = []
        for idx, sim in ranked[: max(1, int(top_k))]:
            meta = self._meta[idx]
            if hints:
                if hints.project and meta.get("project") and hints.project.lower() not in str(meta.get("project")).lower():
                    continue
                if hints.pu and meta.get("pu") and hints.pu.lower() not in str(meta.get("pu")).lower():
                    continue

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

    def _keyword_fallback(self, query: str, hints: Optional[DuplicateSearchHints], top_k: int) -> List[DuplicateCandidate]:
        query_l = query.lower()
        scored: List[Tuple[int, int]] = []
        for i, meta in enumerate(self._meta):
            hay = f"{meta.get('name','')}\n{meta.get('description','')}\n{meta.get('project','')}\n{meta.get('pu','')}".lower()
            if hints:
                if hints.project and meta.get("project") and hints.project.lower() not in str(meta.get("project")).lower():
                    continue
                if hints.pu and meta.get("pu") and hints.pu.lower() not in str(meta.get("pu")).lower():
                    continue
            score = 0
            for token in re.findall(r"[a-z0-9_./-]{3,}", query_l):
                if token in hay:
                    score += 1
            scored.append((i, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        candidates: List[DuplicateCandidate] = []
        for idx, kw_score in scored[: max(1, int(top_k))]:
            meta = self._meta[idx]
            sim = 0.0 if not kw_score else min(1.0, kw_score / 8.0)
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

    if idx._row_count != (len(df) if isinstance(df, pd.DataFrame) else 0) or not idx.ready:
        idx.build_from_df(df if isinstance(df, pd.DataFrame) else pd.DataFrame())
    return idx


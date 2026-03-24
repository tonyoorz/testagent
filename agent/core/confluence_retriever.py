"""
Confluence retriever for chat mode integration.

This module fetches Confluence pages from a space (or descendants of a root page),
chunks page content, and returns top-k relevant chunks for a user query.
"""

from __future__ import annotations

import os
import re
import time
import sys
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


def _read_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return str(value)

    if sys.platform.startswith("win"):
        try:
            import winreg

            reg_paths = [
                (winreg.HKEY_CURRENT_USER, r"Environment"),
                (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            ]
            for hive, path in reg_paths:
                try:
                    with winreg.OpenKey(hive, path) as key:
                        reg_value, _ = winreg.QueryValueEx(key, name)
                        if reg_value:
                            return str(reg_value)
                except Exception:
                    continue
        except Exception:
            pass

    return default


@dataclass
class RetrievedChunk:
    score: float
    title: str
    url: str
    content: str
    updated_at: str = ""


def _safe_int(raw: Optional[str], default: int) -> int:
    try:
        return int(str(raw or "").strip())
    except Exception:
        return default


def _strip_html(html: str) -> str:
    # Keep this lightweight to avoid adding parser complexity.
    text = re.sub(r"<script[\\s\\S]*?</script>", " ", html or "", flags=re.IGNORECASE)
    text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\\s+", " ", text)
    return text.strip()


def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    tokens = re.findall(r"[A-Za-z0-9_\\-]{2,}|[\\u4e00-\\u9fff]{2,}", text.lower())
    return tokens


def _score(query: str, content: str, title: str) -> float:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0

    query_l = (query or "").strip().lower()
    content_l = (content or "").lower()
    title_l = (title or "").lower()

    title_hits = 0
    body_hits = 0
    for t in q_tokens:
        if t in title_l:
            title_hits += 1
        if t in content_l:
            body_hits += 1

    coverage = 0.0
    if q_tokens:
        coverage = float(len([t for t in q_tokens if t in content_l or t in title_l])) / float(len(q_tokens))

    phrase_boost = 0.0
    if query_l and (query_l in title_l):
        phrase_boost += 6.0
    if query_l and (query_l in content_l):
        phrase_boost += 3.0

    # Title matches are weighted higher. Coverage and phrase boosts improve precision.
    return float(title_hits * 4 + body_hits * 1.2 + coverage * 5.0 + phrase_boost)


class ConfluenceRetriever:
    def __init__(self) -> None:
        # Compatible with both this project and tmp-master naming.
        self.base_url = (
            _read_env("CONFLUENCE_BASE_URL")
            or _read_env("CONFLUENCE_URL")
            or "https://atc.bmwgroup.net/confluence"
        ).rstrip("/")
        self.token = _read_env("CONFLUENCE_TOKEN", "").strip()
        self.space_key = _read_env("CONFLUENCE_SPACE_KEY", "").strip()
        self.root_page_id = _read_env("CONFLUENCE_ROOT_PAGE_ID", "").strip()
        self.page_url = _read_env("CONFLUENCE_PAGE_URL", "").strip()
        self.timeout = float(_read_env("CONFLUENCE_TIMEOUT", "30"))
        self.max_pages = _safe_int(_read_env("CONFLUENCE_MAX_PAGES"), 120)
        self.chunk_size = _safe_int(_read_env("CONFLUENCE_CHUNK_SIZE"), 800)
        self.chunk_overlap = _safe_int(_read_env("CONFLUENCE_CHUNK_OVERLAP"), 80)
        self.cache_ttl_sec = _safe_int(_read_env("CONFLUENCE_CACHE_TTL_SEC"), 600)
        if self.page_url and (not self.space_key or not self.root_page_id):
            self._hydrate_from_page_url(self.page_url)

        self.enabled = bool(self.base_url and self.token and (self.space_key or self.root_page_id))

        # Simple in-memory cache per instance.
        self._cache: Dict[str, Any] = {
            "ts": 0.0,
            "chunks": [],
            "meta": {},
        }

        self._client = httpx.Client(timeout=self.timeout, verify=False)

    @staticmethod
    def from_page_url(page_url: str, token: str) -> "ConfluenceRetriever":
        obj = ConfluenceRetriever()
        if page_url:
            obj._hydrate_from_page_url(page_url)

        if token:
            obj.token = token

        obj.enabled = bool(obj.base_url and obj.token and (obj.space_key or obj.root_page_id))
        return obj

    def _hydrate_from_page_url(self, page_url: str) -> None:
        parsed = urlparse(page_url)
        origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        if origin:
            if "/confluence/" in (parsed.path or ""):
                self.base_url = origin + "/confluence"
            else:
                self.base_url = origin

        m_space = re.search(r"/spaces/([^/]+)/", parsed.path or "", flags=re.IGNORECASE)
        if m_space and not self.space_key:
            self.space_key = m_space.group(1)

        m_page = re.search(r"/pages/(\\d+)/", parsed.path or "", flags=re.IGNORECASE)
        if m_page and not self.root_page_id:
            self.root_page_id = m_page.group(1)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _fetch_paginated(self, path_or_url: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        next_url: Optional[str] = None
        first = True
        current_path = path_or_url
        current_params = dict(params or {})

        while True:
            if next_url:
                url = next_url
                req_params = None
            else:
                url = current_path
                req_params = current_params if first else None

            if url.startswith("http://") or url.startswith("https://"):
                full_url = url
            else:
                full_url = f"{self.base_url}{url}"

            resp = self._client.get(full_url, headers=self._headers(), params=req_params)
            resp.raise_for_status()
            body = resp.json() if resp.content else {}

            page_items = body.get("results") or []
            if isinstance(page_items, list):
                items.extend([x for x in page_items if isinstance(x, dict)])

            links = body.get("_links") or {}
            next_rel = links.get("next") if isinstance(links, dict) else None
            if not next_rel:
                break

            if str(next_rel).startswith("http://") or str(next_rel).startswith("https://"):
                next_url = str(next_rel)
            else:
                next_url = f"{self.base_url}{next_rel}"

            if len(items) >= self.max_pages:
                break
            first = False

        return items[: self.max_pages]

    def _extract_page_text(self, page: Dict[str, Any]) -> Tuple[str, str, str, str]:
        title = str(page.get("title") or "").strip() or "Untitled"
        body = page.get("body") or {}
        storage = body.get("storage") if isinstance(body, dict) else {}
        raw_html = ""
        if isinstance(storage, dict):
            raw_html = str(storage.get("value") or "")
        text = _strip_html(raw_html)

        links = page.get("_links") or {}
        webui = links.get("webui") if isinstance(links, dict) else ""
        if webui:
            if str(webui).startswith("http://") or str(webui).startswith("https://"):
                url = str(webui)
            else:
                url = f"{self.base_url}{webui}"
        else:
            page_id = str(page.get("id") or "").strip()
            if self.space_key and page_id:
                url = f"{self.base_url}/spaces/{self.space_key}/pages/{page_id}"
            else:
                url = self.base_url

        version = page.get("version") or {}
        when = str(version.get("when") or "") if isinstance(version, dict) else ""
        return title, text, url, when

    def _fetch_page_by_id(self, page_id: str) -> Optional[Dict[str, Any]]:
        pid = str(page_id or "").strip()
        if not pid:
            return None
        url = f"{self.base_url}/rest/api/content/{pid}"
        params = {"expand": "body.storage,version"}
        resp = self._client.get(url, headers=self._headers(), params=params)
        resp.raise_for_status()
        body = resp.json() if resp.content else {}
        return body if isinstance(body, dict) else None

    def _fetch_pages_by_ancestor_cql(self) -> List[Dict[str, Any]]:
        if not self.root_page_id:
            return []
        cql_parts = [f"ancestor={self.root_page_id}", "type=page"]
        if self.space_key:
            cql_parts.append(f"space={self.space_key}")
        cql = " and ".join(cql_parts)
        params = {
            "cql": cql,
            "limit": min(self.max_pages, 100),
            "expand": "body.storage,version",
        }
        return self._fetch_paginated("/rest/api/content/search", params=params)

    def _chunk_text(self, text: str) -> List[str]:
        if not text:
            return []
        size = max(200, self.chunk_size)
        overlap = max(0, min(size // 2, self.chunk_overlap))
        chunks: List[str] = []
        start = 0
        n = len(text)
        while start < n:
            end = min(n, start + size)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= n:
                break
            start = max(0, end - overlap)
        return chunks

    def _load_space_chunks(self) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        now = time.time()
        if self._cache.get("chunks") and (now - float(self._cache.get("ts") or 0.0) < self.cache_ttl_sec):
            return list(self._cache.get("chunks") or []), dict(self._cache.get("meta") or {})

        if not self.enabled:
            raise RuntimeError("Confluence 未启用，请设置 CONFLUENCE_BASE_URL、CONFLUENCE_TOKEN 以及 SPACE/ROOT_PAGE 配置")

        pages: List[Dict[str, Any]] = []
        source_mode = ""
        seen_ids: set[str] = set()

        def _add_page(p: Optional[Dict[str, Any]]) -> None:
            if not isinstance(p, dict):
                return
            pid = str(p.get("id") or "").strip()
            if pid and pid in seen_ids:
                return
            if pid:
                seen_ids.add(pid)
            pages.append(p)

        # 1) include root page itself first (homepage content is often essential)
        if self.root_page_id:
            try:
                _add_page(self._fetch_page_by_id(self.root_page_id))
            except Exception as e:
                logger.warning(f"root page 拉取失败({self.root_page_id}): {e}")

        # 2) prefer CQL ancestor scope for precision
        if self.root_page_id:
            try:
                for p in self._fetch_pages_by_ancestor_cql():
                    _add_page(p)
                if pages:
                    source_mode = "ancestor_cql"
            except Exception as e:
                logger.warning(f"ancestor CQL 拉取失败，尝试 descendant endpoint: {e}")

        # 3) fallback to descendant endpoint
        if (not pages) and self.root_page_id:
            path = f"/rest/api/content/{self.root_page_id}/descendant/page"
            params = {
                "limit": min(self.max_pages, 100),
                "expand": "body.storage,version",
            }
            try:
                for p in self._fetch_paginated(path, params=params):
                    _add_page(p)
                if pages:
                    source_mode = "descendant"
            except Exception as e:
                logger.warning(f"descendant 拉取失败，回退到 space 全量拉取: {e}")

        # 4) last fallback: full space (noisy but keeps availability)
        if (not pages) and self.space_key:
            path = "/rest/api/content"
            params = {
                "spaceKey": self.space_key,
                "type": "page",
                "limit": min(self.max_pages, 100),
                "expand": "body.storage,version",
            }
            for p in self._fetch_paginated(path, params=params):
                _add_page(p)
            if pages:
                source_mode = "space_fallback"

        if len(pages) > self.max_pages:
            pages = pages[: self.max_pages]

        chunks: List[Dict[str, Any]] = []
        for p in pages:
            title, text, url, updated_at = self._extract_page_text(p)
            if not text:
                continue
            for c in self._chunk_text(text):
                chunks.append(
                    {
                        "title": title,
                        "url": url,
                        "content": c,
                        "updated_at": updated_at,
                    }
                )

        meta = {
            "page_count": len(pages),
            "chunk_count": len(chunks),
            "space_key": self.space_key,
            "root_page_id": self.root_page_id,
            "base_url": self.base_url,
            "source_mode": source_mode or "unknown",
            "fetched_at": int(now),
        }

        self._cache["ts"] = now
        self._cache["chunks"] = chunks
        self._cache["meta"] = meta

        return list(chunks), dict(meta)

    def retrieve(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        chunks, meta = self._load_space_chunks()

        scored: List[RetrievedChunk] = []
        for item in chunks:
            title = str(item.get("title") or "")
            content = str(item.get("content") or "")
            url = str(item.get("url") or "")
            updated_at = str(item.get("updated_at") or "")
            s = _score(query, content, title)
            if s <= 0:
                continue
            scored.append(
                RetrievedChunk(
                    score=s,
                    title=title,
                    url=url,
                    content=content,
                    updated_at=updated_at,
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)

        # Prefer one chunk per page first to reduce repeated snippets from same page.
        top: List[RetrievedChunk] = []
        seen_url: set[str] = set()
        for r in scored:
            key = r.url or r.title
            if key in seen_url:
                continue
            seen_url.add(key)
            top.append(r)
            if len(top) >= max(1, top_k):
                break

        if len(top) < max(1, top_k):
            for r in scored:
                if r in top:
                    continue
                top.append(r)
                if len(top) >= max(1, top_k):
                    break

        return {
            "meta": meta,
            "results": [
                {
                    "score": r.score,
                    "title": r.title,
                    "url": r.url,
                    "content": r.content,
                    "updated_at": r.updated_at,
                }
                for r in top
            ],
        }


def create_confluence_retriever() -> ConfluenceRetriever:
    return ConfluenceRetriever()

"""Duplicate 检测 API

- POST /search — 纯 TF-IDF 检索，返回候选列表
- POST /judge  — 检索 + 大模型判定（如已配置 LLM key）
"""

import os
import logging
from typing import Optional, List

from pydantic import BaseModel
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 请求 / 响应模型 ──────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    project: Optional[str] = None
    pu: Optional[str] = None
    top_k: int = 10


class CandidateOut(BaseModel):
    ticket_id: Optional[str]
    name: str
    project: Optional[str]
    pu: Optional[str]
    status_phase: Optional[str]
    similarity: float
    score_1_10: int
    snippet: str


class SearchResponse(BaseModel):
    candidates: List[CandidateOut]
    total: int
    error: Optional[str] = None


# ── 端点 ─────────────────────────────────────────────────────────

@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, request: Request):
    """纯 TF-IDF 检索，返回候选列表 + 相似度评分"""
    from duplicate_issue_finder import extract_hints, DuplicateSearchHints

    cache: dict = getattr(request.app.state, "index_cache", {})

    # 从用户输入中提取 hint
    hints = extract_hints(req.query)

    # 选择索引：优先用指定 project，回退到 all
    project = req.project or hints.project
    idx = cache.get(project) if project else None
    if idx is None or not getattr(idx, "ready", False):
        idx = cache.get("all")

    if idx is None or not getattr(idx, "ready", False):
        return SearchResponse(candidates=[], total=0, error="索引未就绪")

    search_hints = DuplicateSearchHints(
        project=project or hints.project,
        pu=req.pu or hints.pu,
    )
    candidates = idx.search(req.query, hints=search_hints, top_k=req.top_k)

    return SearchResponse(
        candidates=[
            CandidateOut(
                ticket_id=c.ticket_id,
                name=c.name,
                project=c.project,
                pu=c.pu,
                status_phase=c.status_phase,
                similarity=c.similarity,
                score_1_10=c.score_1_10,
                snippet=c.snippet,
            )
            for c in candidates
        ],
        total=len(candidates),
    )


@router.post("/judge", response_model=SearchResponse)
async def judge(req: SearchRequest, request: Request):
    """检索 + 大模型判定（如已配置 DEEPSEEK_API_KEY）"""
    result = await search(req, request)

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if api_key and result.candidates:
        # 检索有结果且配置了 LLM，标记待实现
        # TODO: 接入 LLM 做 duplicate 判定
        pass

    return result

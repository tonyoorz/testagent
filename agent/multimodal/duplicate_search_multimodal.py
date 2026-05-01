"""
多模态 Duplicate Search - 集成图片/语音输入到 duplicate 检测链路

在原有文字 duplicate 搜索基础上，增加：
1. 图片输入 → GLM Vision 提取 ticket → duplicate search
2. 语音输入 → ASR 转文字 → duplicate search
3. 批量图片 → 多个 ticket 并行搜索 → 汇总报告
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

from duplicate_issue_finder import extract_hints, get_or_build_index, DuplicateSearchHints
from agent.multimodal.multimodal_router import MultimodalRouter

logger = logging.getLogger(__name__)


@dataclass
class BatchDuplicateResult:
    """批量 duplicate 检测结果"""
    query: str                          # 原始查询文本
    source: str                         # 输入来源
    candidates: List[Dict[str, Any]]    # 候选重复 ticket
    top_score: float                    # 最高相似度
    is_likely_duplicate: bool           # 是否疑似重复
    parsed_ticket: Optional[Dict]       # 解析出的原始 ticket 信息


class MultimodalDuplicateSearcher:
    """
    多模态 Duplicate 搜索器

    统一处理文字/图片/语音输入，走 duplicate 检测链路
    """

    def __init__(self):
        self.router = MultimodalRouter()

    def search(
        self,
        text: Optional[str] = None,
        images: Optional[List[bytes]] = None,
        audio: Optional[bytes] = None,
        audio_base64: Optional[str] = None,
        df: Optional[pd.DataFrame] = None,
        cache_key: str = "duplicate:general",
        top_k: int = 10,
        duplicate_threshold: float = 7.0,  # score_1_10 >= 7 算疑似重复
    ) -> Dict[str, Any]:
        """
        多模态 duplicate 搜索

        Args:
            text: 文字描述
            images: 图片列表（bytes）
            audio: 音频数据（bytes）
            audio_base64: base64 音频
            df: 缺陷数据 DataFrame
            cache_key: 索引缓存 key
            top_k: 返回 top_k 个候选
            duplicate_threshold: 疑似重复阈值

        Returns:
            {
                "results": [BatchDuplicateResult...],
                "summary": {...},
                "source": "text/image/audio/mixed",
            }
        """
        # 1. 多模态解析
        mm_result = self.router.process_for_duplicate_search(
            text=text,
            images=images,
            audio=audio,
            audio_base64=audio_base64,
        )

        if not mm_result.get("tickets"):
            return {
                "success": False,
                "message": "未能从输入中提取到 ticket 信息",
                "source": mm_result.get("source", "unknown"),
                "results": [],
                "summary": {"total": 0, "duplicates": 0, "new_issues": 0},
            }

        # 2. 加载索引
        if df is None or df.empty:
            try:
                from data_processor import load_defect_data
                df = load_defect_data()
            except Exception as e:
                logger.error(f"加载缺陷数据失败: {e}")
                return {
                    "success": False,
                    "message": f"加载缺陷数据失败: {e}",
                    "source": mm_result["source"],
                    "results": [],
                    "summary": {"total": 0, "duplicates": 0, "new_issues": 0},
                }

        index = get_or_build_index(cache_key=cache_key, df=df)

        # 3. 对每个 ticket 执行 duplicate search
        all_results: List[Dict[str, Any]] = []
        duplicate_count = 0

        for ticket_dict in mm_result["tickets"]:
            query_text = ticket_dict.get("title", "")
            if not query_text:
                continue

            # 用 extract_hints 从解析出的结构化信息中提取搜索提示
            # 优先用结构化字段构造 hints，而非纯文字
            hints = self._build_hints_from_ticket(ticket_dict)

            # 执行搜索
            candidates = index.search(query_text, hints=hints, top_k=top_k)

            # 转换候选结果
            candidate_dicts = []
            for c in candidates:
                candidate_dicts.append({
                    "score_1_10": c.score_1_10,
                    "similarity": c.similarity,
                    "ticket_id": c.ticket_id,
                    "name": c.name,
                    "project": c.project,
                    "pu": c.pu,
                    "status_phase": c.status_phase,
                    "snippet": c.snippet,
                })

            top_score = candidate_dicts[0]["score_1_10"] if candidate_dicts else 0.0
            is_dup = top_score >= duplicate_threshold
            if is_dup:
                duplicate_count += 1

            all_results.append({
                "query": query_text,
                "source": mm_result["source"],
                "candidates": candidate_dicts,
                "top_score": top_score,
                "is_likely_duplicate": is_dup,
                "parsed_ticket": ticket_dict,
            })

        # 4. 汇总
        total = len(all_results)
        summary = {
            "total": total,
            "duplicates": duplicate_count,
            "new_issues": total - duplicate_count,
            "transcribed_text": mm_result.get("transcribed_text", ""),
            "combined_text": mm_result.get("combined_text", ""),
        }

        return {
            "success": True,
            "source": mm_result["source"],
            "results": all_results,
            "summary": summary,
        }

    def _build_hints_from_ticket(self, ticket: Dict[str, Any]) -> DuplicateSearchHints:
        """
        从解析出的 ticket 结构化信息构造 DuplicateSearchHints

        比 extract_hints(text) 更精准，因为有结构化字段
        """
        # 先用文字提取 hints 作为基础
        text = " ".join(filter(None, [
            ticket.get("title", ""),
            ticket.get("project", ""),
            ticket.get("pu", ""),
            ticket.get("ecu", ""),
            ticket.get("description", ""),
        ]))
        hints = extract_hints(text)

        # 用结构化字段覆盖（更精准）
        project = ticket.get("project")
        if project and not hints.project:
            hints.project = project.strip()

        pu = ticket.get("pu")
        if pu and not hints.pu:
            # 标准化 PU 格式
            pu_clean = pu.replace("/", "-").replace(".", "-").strip()
            if len(pu_clean.split("-")) == 2:
                hints.pu = pu_clean

        ecu = ticket.get("ecu")
        if ecu and not hints.ecu:
            hints.ecu = ecu.strip()

        return hints



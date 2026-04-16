"""Auto-extracted tool module."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from agent.tools.base import DataAnalysisTool

logger = logging.getLogger(__name__)


class MatchTesterTicketsTool(DataAnalysisTool):
    def __init__(self):
        super().__init__(
            name="match_tester_tickets",
            description="根据人员名称匹配 tester 字段，并统计其提票/发现缺陷分布",
            parameters={
                "person": {"type": "string", "description": "人员名称/昵称"},
                "dimension": {"type": "string", "description": "分布维度", "enum": ["aida", "project", "severity"], "default": "aida"},
                "top_n": {"type": "integer", "description": "返回Top N", "default": 10},
                "sample_n": {"type": "integer", "description": "返回样例票据数量", "default": 10},
            },
        )

    def execute(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame()
        person = str(kwargs.get("person") or "").strip()
        if not person:
            return {"success": False, "tool": self.name, "error": "person 不能为空"}
        dimension = str(kwargs.get("dimension") or "aida").strip().lower()
        top_n = max(1, min(int(kwargs.get("top_n") or 10), 50))
        sample_n = max(0, min(int(kwargs.get("sample_n") or 10), 50))
        if df.empty or "tester" not in df.columns:
            return {"success": True, "tool": self.name, "result": {"match_mode": "auto", "matched": 0, "distribution": [], "samples": []}}

        def _norm_person(v: Any) -> str:
            s = str(v or "").strip().lower()
            s = re.sub(r"[^a-z0-9]+", " ", s).strip()
            tokens = [t for t in s.split() if t and t not in {"id", "uid", "userid", "user"}]
            s2 = "".join(tokens)
            if s2.endswith("id") and len(s2) >= 5:
                s2 = s2[:-2]
            return s2

        key = _norm_person(person)
        if not key:
            aliases = {
                "京生": "jingsheng",
            }
            if person in aliases:
                key = _norm_person(aliases[person])
            else:
                char_map = {"京": "jing", "生": "sheng"}
                chars = [c for c in person if "\u4e00" <= c <= "\u9fff"]
                if chars and all(c in char_map for c in chars):
                    key = _norm_person("".join([char_map[c] for c in chars]))
            if not key:
                return {"success": False, "tool": self.name, "error": "person 无法解析为可匹配的关键字"}
        tester_norm = df["tester"].astype(str).map(_norm_person)
        mask = tester_norm.eq(key) | tester_norm.str.startswith(key) | tester_norm.str.endswith(key)
        matched_df = df[mask].copy()
        matched = int(len(matched_df))

        dim_col = None
        if dimension == "aida":
            for c in ["top_aida", "aida_english", "aida"]:
                if c in matched_df.columns:
                    dim_col = c
                    break
        elif dimension == "project":
            for c in ["tproject", "project"]:
                if c in matched_df.columns:
                    dim_col = c
                    break
        elif dimension == "severity":
            for c in ["severity_group", "severity"]:
                if c in matched_df.columns:
                    dim_col = c
                    break
        if not dim_col:
            dim_col = "tester"

        dist = (
            matched_df[dim_col]
            .astype(str)
            .replace({"nan": "", "None": ""})
            .map(lambda s: str(s).strip())
        )
        dist = dist[dist != ""]
        top = dist.value_counts().head(top_n).to_dict()
        distribution = [{"key": k, "count": int(v)} for k, v in top.items()]

        samples = []
        if sample_n > 0 and not matched_df.empty:
            cols = [c for c in ["id", "_id", "name", "title", "tproject", "project", dim_col, "tcreationtime"] if c in matched_df.columns]
            for _, row in matched_df[cols].head(sample_n).iterrows():
                samples.append({c: row.get(c) for c in cols})

        return {
            "success": True,
            "tool": self.name,
            "result": {
                "match_mode": "auto",
                "person": person,
                "matched": matched,
                "dimension": dimension,
                "dimension_column": dim_col,
                "distribution": distribution,
                "samples": samples,
            },
        }

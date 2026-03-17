from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


def pick_risk_score_column(df: pd.DataFrame) -> Optional[str]:
    if df is None or df.empty:
        return None
    for c in ["topissue_risk_score", "risk_score", "topissue_score"]:
        if c in df.columns:
            s = pd.to_numeric(df[c], errors="coerce")
            if s.notna().any():
                return c
    return None


def normalize_matrix_series(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = (
        s.str.replace("MATRIX-", "", regex=False)
        .str.replace("Matrix-", "", regex=False)
        .str.replace("matrix-", "", regex=False)
        .str.replace("matrix_", "", regex=False)
        .str.upper()
    )
    s = s.replace({"": np.nan, "NAN": np.nan, "NONE": np.nan})
    return s


def critical_defect_mask(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty:
        return pd.Series([], dtype=bool)
    col = None
    for c in ["severity_group", "severity"]:
        if c in df.columns:
            col = c
            break
    if not col:
        return pd.Series([False] * len(df), index=df.index, dtype=bool)
    s = df[col].astype(str).str.lower()
    return s.str.contains("critical")


def compute_defect_explore_kpis(df: pd.DataFrame, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    if df is None or df.empty:
        return {
            "total_defects": 0,
            "total_testers": 0,
            "severe_defects": 0,
            "severe_rate": 0.0,
            "daily_avg": 0.0,
            "top_tester": "无数据",
        }

    total_defects = int(len(df))

    tester_col = None
    candidates = [c for c in ["tester", "found_by", "reporter", "author_name"] if c in df.columns]
    if candidates:
        best = None
        best_cnt = -1
        for c in candidates:
            s = df[c].dropna().astype(str).map(lambda x: x.strip())
            s = s[(s != "") & (s.str.lower() != "nan")]
            cnt = int(len(s))
            if cnt > best_cnt:
                best_cnt = cnt
                best = c
        tester_col = best

    if tester_col:
        s = df[tester_col].dropna().astype(str).map(lambda x: x.strip())
        s = s[(s != "") & (s.str.lower() != "nan")]
        total_testers = int(s.nunique())
        top_tester = str(s.value_counts().index[0]) if not s.empty else "无数据"
    else:
        total_testers = 0
        top_tester = "无数据"

    severe_mask = critical_defect_mask(df)
    severe_defects = int(severe_mask.sum()) if len(severe_mask) else 0
    severe_rate = float(round(severe_defects / total_defects * 100, 2)) if total_defects else 0.0

    daily_avg = 0.0
    if start_date and end_date:
        try:
            date_diff = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1
            daily_avg = float(total_defects / date_diff) if date_diff > 0 else 0.0
        except Exception:
            daily_avg = 0.0

    return {
        "total_defects": total_defects,
        "total_testers": total_testers,
        "severe_defects": severe_defects,
        "severe_rate": severe_rate,
        "daily_avg": float(round(daily_avg, 4)),
        "top_tester": str(top_tester),
    }


def safe_str_series(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).map(lambda s: s.strip())


def top_counts(df: pd.DataFrame, group_col: str, top_n: int = 20) -> List[Dict[str, Any]]:
    if df is None or df.empty or group_col not in df.columns:
        return []
    s = safe_str_series(df[group_col])
    s = s[s != ""]
    counts = s.value_counts().head(max(1, top_n))
    total = int(counts.sum())
    out = []
    for k, v in counts.items():
        out.append({"key": str(k), "count": int(v), "ratio": round(int(v) / total * 100, 2) if total else 0.0})
    return out


def stacked_top_counts(
    df: pd.DataFrame,
    group_col: str,
    stack_col: str,
    top_n: int = 15,
    stack_top_n: int = 6,
) -> List[Dict[str, Any]]:
    if df is None or df.empty or group_col not in df.columns or stack_col not in df.columns:
        return []
    g = safe_str_series(df[group_col])
    s = safe_str_series(df[stack_col])
    base = pd.DataFrame({"_g": g, "_s": s})
    base = base[(base["_g"] != "") & (base["_s"] != "")]
    if base.empty:
        return []
    top_groups = base["_g"].value_counts().head(max(1, top_n)).index.tolist()
    base = base[base["_g"].isin(top_groups)]
    pivot = base.groupby(["_g", "_s"]).size().reset_index(name="count")
    totals = pivot.groupby("_g")["count"].sum().sort_values(ascending=False)
    out = []
    for group in totals.index.tolist():
        sub = pivot[pivot["_g"] == group].sort_values("count", ascending=False).head(max(1, stack_top_n))
        stacks = [{"key": str(r["_s"]), "count": int(r["count"])} for _, r in sub.iterrows()]
        out.append({"group": str(group), "total": int(totals.loc[group]), "stacks": stacks})
    return out


def severity_rate_by(df: pd.DataFrame, group_col: str, top_n: int = 20) -> List[Dict[str, Any]]:
    if df is None or df.empty or group_col not in df.columns:
        return []
    g = safe_str_series(df[group_col])
    base = df.copy()
    base["_g"] = g
    base = base[base["_g"] != ""]
    if base.empty:
        return []
    severe_mask = critical_defect_mask(base)
    base["_is_severe"] = severe_mask.astype(int).reindex(base.index).fillna(0).astype(int)
    agg = base.groupby("_g").agg(total=("_g", "size"), severe=("_is_severe", "sum"))
    agg["severe_rate"] = np.where(agg["total"] > 0, (agg["severe"] / agg["total"] * 100).round(2), 0.0)
    agg = agg.sort_values(["severe_rate", "total"], ascending=[False, False]).head(max(1, top_n))
    out = []
    for idx, row in agg.reset_index().iterrows():
        out.append({"key": str(row["_g"]), "total": int(row["total"]), "severe": int(row["severe"]), "severe_rate": float(row["severe_rate"])})
    return out


def time_series_counts(
    df: pd.DataFrame,
    time_col: str,
    freq: str = "D",
    stack_col: Optional[str] = None,
    top_stacks: int = 6,
    max_points: int = 180,
) -> Dict[str, Any]:
    if df is None or df.empty or time_col not in df.columns:
        return {"series": [], "freq": freq}
    ts = pd.to_datetime(df[time_col], errors="coerce")
    base = df.copy()
    base["_t"] = ts
    base = base[base["_t"].notna()]
    if base.empty:
        return {"series": [], "freq": freq}
    base["_bucket"] = base["_t"].dt.to_period(freq).astype(str)
    if not stack_col or stack_col not in base.columns:
        counts = base.groupby("_bucket").size().reset_index(name="count").sort_values("_bucket")
        if len(counts) > max_points:
            counts = counts.tail(max_points)
        return {"series": [{"name": "count", "points": counts.to_dict(orient="records")}], "freq": freq}
    stacks = safe_str_series(base[stack_col])
    base["_s"] = stacks
    base = base[base["_s"] != ""]
    if base.empty:
        return {"series": [], "freq": freq}
    top_s = base["_s"].value_counts().head(max(1, top_stacks)).index.tolist()
    base = base[base["_s"].isin(top_s)]
    pivot = base.groupby(["_bucket", "_s"]).size().reset_index(name="count")
    out = []
    for s in top_s:
        sub = pivot[pivot["_s"] == s].sort_values("_bucket")
        if len(sub) > max_points:
            sub = sub.tail(max_points)
        out.append({"name": str(s), "points": [{"bucket": r["_bucket"], "count": int(r["count"])} for _, r in sub.iterrows()]})
    return {"series": out, "freq": freq}


def nunique_by(df: pd.DataFrame, group_col: str, value_col: str, top_n: int = 20) -> List[Dict[str, Any]]:
    if df is None or df.empty or group_col not in df.columns or value_col not in df.columns:
        return []
    g = safe_str_series(df[group_col])
    v = safe_str_series(df[value_col])
    base = pd.DataFrame({"_g": g, "_v": v})
    base = base[(base["_g"] != "") & (base["_v"] != "")]
    if base.empty:
        return []
    agg = base.groupby("_g")["_v"].nunique().sort_values(ascending=False).head(max(1, top_n))
    out = []
    for k, c in agg.items():
        out.append({"key": str(k), "nunique": int(c)})
    return out


def defect_quality_stats(df: pd.DataFrame, group_col: str = "project", aida_col: str = "aida_english", top_n: int = 30) -> List[Dict[str, Any]]:
    if df is None or df.empty or group_col not in df.columns:
        return []
    base = df.copy()
    base["_g"] = safe_str_series(base[group_col])
    base = base[base["_g"] != ""]
    if base.empty:
        return []
    severe_mask = critical_defect_mask(base)
    base["_is_severe"] = severe_mask.astype(int).reindex(base.index).fillna(0).astype(int)
    if aida_col in base.columns:
        base["_aida"] = safe_str_series(base[aida_col])
    else:
        base["_aida"] = ""
    if "creation_time" in base.columns:
        tcol = "creation_time"
    elif "tcreationtime" in base.columns:
        tcol = "tcreationtime"
    else:
        tcol = None
    if tcol:
        base["_t"] = pd.to_datetime(base[tcol], errors="coerce")
        ages = (pd.Timestamp.now(tz=None) - base["_t"]).dt.total_seconds() / 86400
        base["_age_days"] = pd.to_numeric(ages, errors="coerce").fillna(0)
    else:
        base["_age_days"] = 0.0
    agg = base.groupby("_g").agg(
        total=("_g", "size"),
        severe=("_is_severe", "sum"),
        avg_age_days=("_age_days", "mean"),
        aida_coverage=("_aida", "nunique"),
    )
    agg["severe_rate"] = np.where(agg["total"] > 0, (agg["severe"] / agg["total"] * 100).round(2), 0.0)
    total_aidas = int(base["_aida"].nunique()) if (aida_col in df.columns) else 0
    if total_aidas > 0:
        agg["aida_coverage_pct"] = (agg["aida_coverage"] / total_aidas * 100).round(1)
    else:
        agg["aida_coverage_pct"] = 0.0
    agg["quality_score"] = ((100 - agg["severe_rate"]) * 0.5 + (100 - (agg["total"] / 10).clip(upper=100) * 10) * 0.2 + agg["aida_coverage_pct"] * 0.3).round(1)
    agg = agg.sort_values("quality_score", ascending=False).head(max(1, top_n))
    out = []
    for _, r in agg.reset_index().iterrows():
        out.append(
            {
                "key": str(r["_g"]),
                "total_defects": int(r["total"]),
                "severe_defects": int(r["severe"]),
                "severe_rate": float(r["severe_rate"]),
                "avg_age_days": float(round(r["avg_age_days"], 1)),
                "aida_coverage": int(r["aida_coverage"]),
                "aida_coverage_pct": float(r["aida_coverage_pct"]),
                "quality_score": float(r["quality_score"]),
            }
        )
    return out


def word_frequencies(texts: Sequence[str], top_n: int = 50, min_len: int = 2) -> List[Dict[str, Any]]:
    from collections import Counter
    import re

    buf: List[str] = []
    for t in texts:
        if not t:
            continue
        s = str(t)
        tokens = re.findall(r"[A-Za-z0-9_\\-]+|[\\u4e00-\\u9fff]{2,}", s)
        buf.extend([x.lower() for x in tokens if len(x) >= min_len])
    if not buf:
        return []
    counts = Counter(buf)
    top = counts.most_common(max(1, top_n))
    total = sum(v for _, v in top)
    out = []
    for w, c in top:
        out.append({"word": w, "count": int(c), "ratio": round(int(c) / total * 100, 2) if total else 0.0})
    return out


def defect_wordcloud_source(df: pd.DataFrame) -> List[str]:
    if df is None or df.empty:
        return []
    cols = []
    for c in ["name", "title", "defect_name", "summary", "description", "domain", "aida_english", "top_aida"]:
        if c in df.columns:
            cols.append(c)
    if not cols:
        return []
    merged = df[cols].fillna("").astype(str).agg(" ".join, axis=1)
    return merged.tolist()


def inflow_outflow_summary(start_date: Optional[str] = None, end_date: Optional[str] = None) -> Dict[str, Any]:
    from data_processor import calculate_inflow_outflow_trends, get_inflow_outflow_summary_stats

    weeks_range = 52
    if start_date and end_date:
        try:
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            weeks_range = max(4, int((end_dt - start_dt).days / 7))
        except Exception:
            weeks_range = 52
    trends_df = calculate_inflow_outflow_trends(date_range_weeks=weeks_range)
    stats = get_inflow_outflow_summary_stats(trends_df)
    tail = []
    if isinstance(trends_df, pd.DataFrame) and not trends_df.empty:
        tail_df = trends_df.tail(16)
        tail = tail_df.to_dict(orient="records")
    return {"stats": stats, "recent_weeks": tail}


def longrunner_phase_statistics(ticket_ids: Iterable[str], history_folder: str = "history", max_tickets: int = 80) -> Dict[str, Any]:
    from longrunner_analysis import analyze_ticket_phases_cached
    from collections import defaultdict

    ids = [str(x).strip() for x in ticket_ids if str(x).strip()]
    if not ids:
        return {"phase_stats": [], "errors": 0, "tickets": 0}
    ids = ids[: max(1, max_tickets)]
    rows = []
    errors = 0
    for tid in ids:
        out = analyze_ticket_phases_cached(tid, history_folder=history_folder, cache_dir=None, use_cache=True)
        if out.get("error"):
            errors += 1
            continue
        for d in out.get("phase_durations") or []:
            rows.append(
                {
                    "ticket_id": tid,
                    "from_phase": d.get("from_phase"),
                    "to_phase": d.get("to_phase"),
                    "duration_hours": float(d.get("duration_hours") or 0),
                }
            )
    if not rows:
        return {"phase_stats": [], "errors": errors, "tickets": len(ids)}
    df = pd.DataFrame(rows)
    df["transition"] = df["from_phase"].astype(str) + " -> " + df["to_phase"].astype(str)
    agg = df.groupby("transition")["duration_hours"].agg(["count", "mean", "min", "max", "median", "sum"]).reset_index()
    agg = agg.sort_values(["sum", "count"], ascending=False).head(25)
    out_stats = []
    for _, r in agg.iterrows():
        out_stats.append(
            {
                "transition": str(r["transition"]),
                "count": int(r["count"]),
                "avg_hours": float(round(r["mean"], 2)),
                "avg_days": float(round(r["mean"] / 24, 2)),
                "min_hours": float(round(r["min"], 2)),
                "max_hours": float(round(r["max"], 2)),
                "median_hours": float(round(r["median"], 2)),
                "total_hours": float(round(r["sum"], 2)),
            }
        )
    return {"phase_stats": out_stats, "errors": errors, "tickets": len(ids)}

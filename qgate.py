import argparse
from functools import lru_cache
import json
import os
import re
import sqlite3
import time
from typing import Optional

import pandas as pd
from io import StringIO

import longrunner_analysis as lra

from dash import Dash, dcc, html, Input, Output, State, dash_table
import dash
import plotly.express as px
import plotly.graph_objects as go
from dash.exceptions import PreventUpdate
from plotly.subplots import make_subplots

from dash_common_styles import (
    create_theme_switcher,
    MAIN_CONTAINER_STYLE,
    LIGHT_MAIN_CONTAINER_STYLE,
    TEXT_COLOR,
    LIGHT_TEXT_COLOR,
    theme_manager,
)


DEFAULT_TEAMS = [
    "DTSV_China",
    "Spotlight_DTSV_China",
    "Spotlight_FIT",
    "[AT]BBA_Basis-FIT",
    "[AT]FIT_LAENDER_CHINA",
    "Plant-Dadong FIT",
    "Plant-Tiexi FIT",
]

CHINA_SPECIFIC_FIF = {
    "Connected Music China [01.04.01.06.04]",
    "DELETED_BMW Points (Mobile App) [01.04.03.02.01.01.01]",
    "Festival Mode [01.04.02.01.02.01.04]",
    "Itinerary (Mobile App) [01.04.03.01.01.07.09]",
    "Play audio via Online Services (Connected Music) [01.04.01.01.02]",
    "Provide 3rd Party Gaming App [01.04.01.02.03.05]",
    "Provide 3rd party gaming enablement [01.04.01.02.03]",
    "Provide App Center China [01.04.01.06.09]",
    "Provide Child Seat App [01.04.01.06.12]",
    "Provide Festival Mode [01.04.02.01.04.08]",
    "Provide Karaoke Service [01.04.01.06.10]",
    "Provide NetEase Cloud Music [01.04.01.06.04.03]",
    "Provide Projected Modes China [01.04.01.06.13]",
    "QQ Music [01.04.01.06.04.02]",
    "QQ Music [01.04.01.06.06.02]",
    "Smart Access / Digital Key (Plus) [01.03.03.03.04]",
    "Tencent MiniProgramPlatform (Tencent MPP) [01.04.01.06.01]",
    "Tencent WeChat [01.04.01.06.02]",
    "Use App Store China [01.04.01.06.07]",
    "Use Speech operation [01.04.02.01.01.05]",
    "Video streaming China [01.04.01.06.05]",
    "Voice Interface [01.04.02.01.01.02]",
    "WeChat VoiP Call [01.04.01.06.02.02]",
    "Ximalaya [01.04.01.06.04.01]",
    "Ximalaya [01.04.01.06.06.03]",
}

global_issue_df = pd.DataFrame()
global_timespan_slider_min = 0
global_timespan_slider_max = 1
OCTANE_BASE_URL = os.environ.get("OCTANE_BASE_URL", "https://octane-prod.bmwgroup.net")
OCTANE_SHARED_SPACE = os.environ.get("OCTANE_SHARED_SPACE", "1002")
OCTANE_WORKSPACE = os.environ.get("OCTANE_WORKSPACE", "2001")


def build_octane_work_item_url(ticket_id: str) -> str:
    tid = str(ticket_id or "").strip()
    if not tid:
        return ""
    return f"{OCTANE_BASE_URL}/ui/entity-navigation?p={OCTANE_SHARED_SPACE}/{OCTANE_WORKSPACE}&entityType=work_item&id={tid}"


def slugify_team_name(team_name: str) -> str:
    if not team_name:
        return "UNKNOWN_TEAM"
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", team_name.strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "UNKNOWN_TEAM"


def _default_qgate_db_path() -> str:
    return os.environ.get("QGATE_DB_PATH") or os.path.join("qgate", "qgate_data.db")


def _current_qgate_source_mode() -> str:
    return os.environ.get("OCTANE_DATA_SOURCE", "db_only").strip().lower()


def _extract_tester_name(row: dict) -> str:
    detected_by = row.get("detected_by")
    if isinstance(detected_by, dict):
        return str(detected_by.get("full_name") or "").strip()
    return ""


@lru_cache(maxsize=64)
def _load_combined_defect_info_for_team(defect_dir: str, team: str, db_path: str) -> dict[str, dict[str, str]]:
    info: dict[str, dict[str, str]] = {}
    source_mode = _current_qgate_source_mode()

    if db_path and os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT raw_json
                    FROM octane_defects
                    WHERE team = ? OR problem_finder_team = ?
                    ORDER BY defect_id
                    """,
                    (team, team),
                ).fetchall()
            finally:
                conn.close()

            for row in rows:
                try:
                    payload = json.loads(row[0]) if row and row[0] else None
                except Exception:
                    payload = None
                if not isinstance(payload, dict):
                    continue
                tid = str(payload.get("id") or "").strip()
                if not tid:
                    continue
                info[tid] = {
                    "name": str(payload.get("name") or "").strip(),
                    "tester": _extract_tester_name(payload),
                }
        except sqlite3.Error:
            pass

    team_slug = slugify_team_name(team)
    if source_mode != "db_only" and os.path.isdir(defect_dir):
        for filename in os.listdir(defect_dir):
            if not filename.endswith("_defect.json"):
                continue
            if f"_{team_slug}_defect.json" not in filename:
                continue
            path = os.path.join(defect_dir, filename)
            try:
                df = pd.read_json(path)
            except ValueError:
                continue
            if df.empty or "id" not in df.columns:
                continue
            for _, row in df.iterrows():
                tid = str(row.get("id") or "").strip()
                if not tid or tid in info:
                    continue
                info[tid] = {
                    "name": str(row.get("name") or "").strip(),
                    "tester": _extract_tester_name(row),
                }

    return info


def parse_args():
    parser = argparse.ArgumentParser(description="按 team 展示 phase transition 效率（基于 defect + history 数据）")
    parser.add_argument("--defect-dir", default="qgate/defect", help="defect 数据目录（默认: qgate/defect）")
    parser.add_argument("--history-dir", default="qgate/history", help="history 数据目录（默认: qgate/history）")
    parser.add_argument("--teams", default=",".join(DEFAULT_TEAMS), help="Team 列表（逗号分隔）")
    parser.add_argument("--out-dir", default="qgate_out", help="输出目录（默认: qgate_out）")
    parser.add_argument("--min-transition-count", type=int, default=5, help="纳入统计的最小 transition 样本数（默认: 5）")
    parser.add_argument("--no-progress", action="store_true", help="不输出分析进度")
    parser.add_argument("--analysis-workers", type=int, default=0, help="分析并行线程数（0=自动，默认: 0）")
    parser.add_argument("--cache-dir", default="qgate_cache", help="分析缓存目录（默认: qgate_cache）")
    parser.add_argument("--no-cache", action="store_true", help="禁用分析缓存")
    parser.add_argument("--html", action="store_true", help="同时输出可视化 HTML")
    parser.add_argument("--batch", action="store_true", help="仅生成离线 CSV/HTML，不启动看板")
    parser.add_argument("--host", default="0.0.0.0", help="看板监听地址（默认: 0.0.0.0）")
    parser.add_argument("--port", type=int, default=8063, help="看板端口（默认: 8063）")
    return parser.parse_args()


def load_defect_ids_for_team(defect_dir: str, team: str):
    db_path = _default_qgate_db_path()
    return set(_load_combined_defect_info_for_team(defect_dir, team, db_path).keys())


def load_defect_info_for_team(defect_dir: str, team: str):
    db_path = _default_qgate_db_path()
    return dict(_load_combined_defect_info_for_team(defect_dir, team, db_path))


def classify_group(phase_transition: str) -> str:
    from_part, to_part = phase_transition, ""
    if "→" in phase_transition:
        from_part, to_part = phase_transition.split("→", 1)
    from_part = from_part.strip()
    to_part = to_part.strip()

    def get_prefix(phase_text: str):
        m = re.match(r"^(\d{2})-", (phase_text or "").strip())
        return m.group(1) if m else None

    from_prefix = get_prefix(from_part)
    to_prefix = get_prefix(to_part)

    if from_prefix == "09" and to_prefix == "01":
        return "Integration"
    if from_prefix == "06" and to_prefix == "05":
        return "Integration"

    if not from_prefix:
        return "Other"

    if from_prefix in {"02", "07"}:
        return "Q-Gate"
    if from_prefix in {"00", "01", "08"}:
        return "Integration"
    if from_prefix in {"03", "04", "05"}:
        return "CoC"
    return "Other"


def build_team_statistics(team: str, ticket_ids, history_dir: str, show_progress: bool, analysis_workers: int, cache_dir: Optional[str], use_cache: bool, defect_info: dict):
    workers = int(analysis_workers or 0)
    if workers <= 0:
        workers = min(24, max(4, (os.cpu_count() or 4) * 2))
    if use_cache and ticket_ids:
        try:
            from data_processor import history_cache

            preload_workers = max(1, min(8, workers))
            history_cache.preload_histories(
                sorted(str(ticket_id) for ticket_id in ticket_ids),
                history_dir=history_dir,
                max_workers=preload_workers,
            )
        except Exception:
            pass
    bulk = lra.bulk_analyze_phases(
        list(ticket_ids),
        history_folder=history_dir,
        show_progress=show_progress,
        max_workers=workers,
        cache_dir=cache_dir,
        use_cache=use_cache,
        return_all_results=False,
        return_duration_records=True,
        return_ticket_meta=True,
    )
    all_label = "(All)"
    duration_records = bulk.get("phase_duration_records") or {}
    ticket_meta = bulk.get("ticket_meta") or {}

    def ticket_fif_category(tid: str) -> Optional[str]:
        items = ticket_meta.get(str(tid)) or []
        items_set = {str(x).strip() for x in items if str(x).strip()}
        if not items_set:
            return None
        if items_set.intersection(CHINA_SPECIFIC_FIF):
            return "China Specific"
        return "Global"

    def stats_from_hours(hours):
        if not hours:
            return None
        hours_sorted = sorted(hours)
        count = len(hours_sorted)
        avg_hours = round(sum(hours_sorted) / count, 2)
        avg_days = round(avg_hours / 24, 2)
        min_hours = round(hours_sorted[0], 2)
        max_hours = round(hours_sorted[-1], 2)
        median_hours = round(hours_sorted[count // 2], 2)
        return {
            "count": count,
            "avg_hours": avg_hours,
            "avg_days": avg_days,
            "min_hours": min_hours,
            "max_hours": max_hours,
            "median_hours": median_hours,
        }

    rows = []
    issue_rows = []

    def parse_ts(ts):
        if not ts:
            return None
        try:
            from datetime import datetime

            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            return None

    def phase_prefix(phase_text: str):
        m = re.match(r"^(\d{2})-", (phase_text or "").strip())
        return m.group(1) if m else None

    ticket_span_state = {}
    for transition, records in (duration_records or {}).items():
        for r in records or []:
            tid = r.get("ticket_id")
            if tid is None:
                continue
            tid = str(tid)
            fp = phase_prefix(str(r.get("from_phase") or ""))
            tp = phase_prefix(str(r.get("to_phase") or ""))
            st = parse_ts(r.get("start_time"))
            et = parse_ts(r.get("end_time"))

            state = ticket_span_state.setdefault(tid, {"start": None, "end": None})
            if fp in {"00", "01"} and st is not None:
                if state["start"] is None or st < state["start"]:
                    state["start"] = st
            if tp in {"06", "09"} and et is not None:
                if state["end"] is None or et < state["end"]:
                    state["end"] = et

    ticket_span_days = {}
    for tid, st in ticket_span_state.items():
        start = st.get("start")
        end = st.get("end")
        if start is None or end is None:
            ticket_span_days[tid] = None
            continue
        delta = end - start
        ticket_span_days[tid] = round(delta.total_seconds() / 86400, 2)

    hours_by_key = {}
    for transition, records in (duration_records or {}).items():
        group = classify_group(transition)
        for r in records or []:
            h = r.get("duration_hours")
            if h is None:
                continue
            try:
                h = float(h)
            except Exception:
                continue

            user = (str(r.get("changed_by") or "").strip()) or "Unknown"
            tid = r.get("ticket_id")
            fif = ticket_fif_category(str(tid)) if tid is not None else None

            info = defect_info.get(str(tid)) if tid is not None else None
            tid_str = str(tid) if tid is not None else ""
            ticket_url = build_octane_work_item_url(tid_str) if tid_str else ""
            span_days = ticket_span_days.get(tid_str) if tid_str else None
            issue_rows.append(
                {
                    "Team": team,
                    "Ticket_ID": tid_str,
                    "Ticket_URL": ticket_url,
                    "Ticket_Link": f"[{tid_str}]({ticket_url})" if tid_str and ticket_url else tid_str,
                    "Ticket_Name": (info or {}).get("name", ""),
                    "Tester": (info or {}).get("tester", ""),
                    "Phase_Transition": transition,
                    "Group": group,
                    "Duration_Hours": round(h, 2),
                    "Duration_Days": round(h / 24, 2),
                    "Start_Time": r.get("start_time"),
                    "End_Time": r.get("end_time"),
                    "Changed_By": user,
                    "FiF": fif or "(All)",
                    "Ticket_Timespan_Days": span_days,
                }
            )

            if fif:
                dims = {(user, fif), (all_label, fif), (user, all_label), (all_label, all_label)}
            else:
                dims = {(user, all_label), (all_label, all_label)}

            for changed_by_val, fif_val in dims:
                key = (transition, group, changed_by_val, fif_val)
                hours_by_key.setdefault(key, []).append(h)

    for (transition, group, changed_by_val, fif_val), hours in hours_by_key.items():
        s = stats_from_hours(hours)
        if not s:
            continue
        rows.append(
            {
                "Team": team,
                "Phase_Transition": transition,
                "Group": group,
                "Changed_By": changed_by_val,
                "FiF": fif_val,
                "Count": s["count"],
                "Avg_Hours": s["avg_hours"],
                "Avg_Days": s["avg_days"],
                "Min_Hours": s["min_hours"],
                "Max_Hours": s["max_hours"],
                "Median_Hours": s["median_hours"],
            }
        )
    df = pd.DataFrame(rows)
    issues_df = pd.DataFrame(issue_rows)
    return df, issues_df, bulk.get("successful_count", 0), bulk.get("failed_count", 0)


def weighted_avg_days(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    total = float(df["Count"].sum())
    if total <= 0:
        return 0.0
    return float((df["Avg_Days"] * df["Count"]).sum() / total)


def sum_avg_days(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    return float(pd.to_numeric(df["Avg_Days"], errors="coerce").fillna(0.0).sum())


def make_html_chart(summary_df: pd.DataFrame, out_path: str):
    import plotly.express as px

    if summary_df.empty:
        return
    fig = px.bar(
        summary_df,
        x="Weighted_Avg_Days",
        y="Team",
        color="Group",
        orientation="h",
        title="Phase Transition Efficiency by Team (Sum of Avg Days by Group)",
        barmode="stack",
        hover_data=["Transitions_Total", "Samples_Total"],
    )
    fig.write_html(out_path)


def compute_all_teams_data(defect_dir: str, history_dir: str, teams, show_progress: bool, analysis_workers: int, cache_dir: Optional[str], use_cache: bool):
    all_team_dfs = []
    all_issue_dfs = []
    per_team_meta = []

    total_teams = len(teams or [])
    started_at = time.time()
    if show_progress:
        print(f"开始按 team 统计：teams={total_teams} | defect_dir={defect_dir} | history_dir={history_dir}", flush=True)

    for idx, team in enumerate(teams, start=1):
        team_started_at = time.time()
        ticket_ids = load_defect_ids_for_team(defect_dir, team)
        if not ticket_ids:
            per_team_meta.append({"Team": team, "Defects": 0, "History_OK": 0, "History_Missing_or_Error": 0})
            continue
        defect_info = load_defect_info_for_team(defect_dir, team)
        if show_progress:
            print(f"[{idx}/{total_teams}] {team} | defects={len(ticket_ids)}", flush=True)
        df_stats, issues_df, ok, bad = build_team_statistics(
            team,
            ticket_ids,
            history_dir,
            show_progress=show_progress,
            analysis_workers=analysis_workers,
            cache_dir=cache_dir,
            use_cache=use_cache,
            defect_info=defect_info,
        )
        all_team_dfs.append(df_stats)
        if not issues_df.empty:
            all_issue_dfs.append(issues_df)
        per_team_meta.append({"Team": team, "Defects": len(ticket_ids), "History_OK": ok, "History_Missing_or_Error": bad})
        if show_progress:
            elapsed_s = round(time.time() - team_started_at, 1)
            print(f"[{idx}/{total_teams}] {team} 完成 | ok={ok} bad={bad} | {elapsed_s}s", flush=True)

    if show_progress:
        elapsed_s = round(time.time() - started_at, 1)
        print(f"全部 team 完成 | {elapsed_s}s", flush=True)

    meta_df = pd.DataFrame(per_team_meta)
    stats_df = pd.concat(all_team_dfs, ignore_index=True) if all_team_dfs else pd.DataFrame()
    issues_df = pd.concat(all_issue_dfs, ignore_index=True) if all_issue_dfs else pd.DataFrame()
    return meta_df, stats_df, issues_df


def build_summary_frames(stats_df: pd.DataFrame, min_transition_count: int):
    if stats_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    filtered = stats_df[stats_df["Count"] >= int(min_transition_count)].copy()
    if filtered.empty:
        return filtered, pd.DataFrame()

    summary_rows = []
    for (team, group), gdf in filtered.groupby(["Team", "Group"], dropna=False):
        summary_rows.append(
            {
                "Team": team,
                "Group": group,
                "Samples_Total": int(gdf["Count"].sum()),
                "Transitions_Total": int(gdf.shape[0]),
                "Weighted_Avg_Days": round(sum_avg_days(gdf), 3),
            }
        )
    summary_df = pd.DataFrame(summary_rows).sort_values(["Team", "Group"])
    return filtered, summary_df


def run_batch(args):
    teams = [t.strip() for t in (args.teams or "").split(",") if t.strip()]
    os.makedirs(args.out_dir, exist_ok=True)
    use_cache = not args.no_cache
    cache_dir = None if args.no_cache else args.cache_dir

    meta_df, stats_df, issues_df = compute_all_teams_data(
        defect_dir=args.defect_dir,
        history_dir=args.history_dir,
        teams=teams,
        show_progress=not args.no_progress,
        analysis_workers=args.analysis_workers,
        cache_dir=cache_dir,
        use_cache=use_cache,
    )
    _ = issues_df
    if not stats_df.empty:
        if "Changed_By" in stats_df.columns:
            stats_df = stats_df[stats_df["Changed_By"] == "(All)"].copy()
        if "FiF" in stats_df.columns:
            stats_df = stats_df[stats_df["FiF"] == "(All)"].copy()

    meta_csv = os.path.join(args.out_dir, "qgate_team_coverage.csv")
    meta_df.to_csv(meta_csv, index=False, encoding="utf-8")

    stats_df, summary_df = build_summary_frames(stats_df, args.min_transition_count)
    if stats_df.empty:
        return

    stats_csv = os.path.join(args.out_dir, "qgate_phase_statistics_all_teams.csv")
    stats_df.to_csv(stats_csv, index=False, encoding="utf-8")

    if summary_df.empty:
        return

    summary_csv = os.path.join(args.out_dir, "qgate_team_group_summary.csv")
    summary_df.to_csv(summary_csv, index=False, encoding="utf-8")

    pivot = summary_df.pivot_table(index="Team", columns="Group", values="Weighted_Avg_Days", aggfunc="first").reset_index()
    pivot_csv = os.path.join(args.out_dir, "qgate_team_group_summary_pivot.csv")
    pivot.to_csv(pivot_csv, index=False, encoding="utf-8")

    if args.html:
        html_path = os.path.join(args.out_dir, "qgate_team_group_summary.html")
        make_html_chart(summary_df, html_path)


def empty_figure(theme: str, message: str):
    fig = px.scatter()
    fig.update_layout(
        template="plotly_white" if theme == "light" else "plotly_dark",
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[{"text": message, "xref": "paper", "yref": "paper", "showarrow": False, "font": {"size": 16}}],
        height=320,
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig


def aggregate_transition_summary(stats_df: pd.DataFrame) -> pd.DataFrame:
    if stats_df.empty:
        return pd.DataFrame()
    df = stats_df.copy()
    df["Count"] = pd.to_numeric(df["Count"], errors="coerce").fillna(0).astype(int)
    df["Avg_Days"] = pd.to_numeric(df["Avg_Days"], errors="coerce").fillna(0.0).astype(float)
    df["Min_Hours"] = pd.to_numeric(df["Min_Hours"], errors="coerce").fillna(0.0).astype(float)
    df["Max_Hours"] = pd.to_numeric(df["Max_Hours"], errors="coerce").fillna(0.0).astype(float)
    df = df[df["Count"] > 0].copy()
    if df.empty:
        return pd.DataFrame()

    def _weighted_avg_days(g: pd.DataFrame) -> float:
        total = float(g["Count"].sum())
        if total <= 0:
            return 0.0
        return float((g["Avg_Days"] * g["Count"]).sum() / total)

    rows = []
    for (transition, group), gdf in df.groupby(["Phase_Transition", "Group"], dropna=False):
        rows.append(
            {
                "Phase_Transition": transition,
                "Group": group,
                "Count": int(gdf["Count"].sum()),
                "Avg_Days": round(_weighted_avg_days(gdf), 3),
                "Min_Hours": float(gdf["Min_Hours"].min()),
                "Max_Hours": float(gdf["Max_Hours"].max()),
            }
        )
    return pd.DataFrame(rows)


def create_phase_duration_ranking_chart(df: pd.DataFrame, theme: str):
    if df.empty:
        return empty_figure(theme, "无数据")

    df_top = df.sort_values("Avg_Days", ascending=True).copy()
    max_days = float(df_top["Avg_Days"].max() or 0.0)
    colors = []
    for days in df_top["Avg_Days"].tolist():
        if max_days > 0 and days > max_days * 0.7:
            colors.append("#e74c3c")
        elif max_days > 0 and days > max_days * 0.3:
            colors.append("#f39c12")
        else:
            colors.append("#27ae60")

    fig = go.Figure(
        data=[
            go.Bar(
                y=df_top["Phase_Transition"],
                x=df_top["Avg_Days"],
                orientation="h",
                marker_color=colors,
                text=[f"{days:.1f} days ({count} samples)" for days, count in zip(df_top["Avg_Days"], df_top["Count"])],
                textposition="auto",
                hovertemplate="<b>%{y}</b><br>"
                + "Avg Duration: %{x:.2f} days<br>"
                + "Samples: %{customdata[0]}<br>"
                + "Min Hours: %{customdata[1]:.1f}h<br>"
                + "Max Hours: %{customdata[2]:.1f}h<br>"
                + "<extra></extra>",
                customdata=df_top[["Count", "Min_Hours", "Max_Hours"]].values,
            )
        ]
    )

    chart_height = max(520, int(len(df_top) * 24 + 220))
    fig.update_layout(
        title=f"Phase Transition Average Duration Ranking ({len(df_top)} items)",
        xaxis_title="Average Duration (days)",
        yaxis_title="Phase Transition",
        height=chart_height,
        margin=dict(l=320, r=40, t=60, b=40),
        template="plotly_white" if theme == "light" else "plotly_dark",
        showlegend=False,
    )
    return fig


def create_grouped_stacked_chart(df: pd.DataFrame, theme: str):
    if df.empty:
        return empty_figure(theme, "无数据")
    df = df.copy()
    df = df[df["Group"].isin(["Q-Gate", "Integration", "CoC"])]
    if df.empty:
        return empty_figure(theme, "无匹配分组（Q-Gate/Integration/CoC）")

    pivot_vals = df.pivot_table(index="Group", columns="Phase_Transition", values="Avg_Days", aggfunc="mean").fillna(0)
    pivot_cnts = df.pivot_table(index="Group", columns="Phase_Transition", values="Count", aggfunc="sum").fillna(0)
    groups_order = ["Q-Gate", "Integration", "CoC"]
    pivot_vals = pivot_vals.reindex(groups_order).fillna(0)
    pivot_cnts = pivot_cnts.reindex(groups_order).fillna(0)

    fig = go.Figure()
    for transition in pivot_vals.columns:
        x_vals = pivot_vals[transition].values
        y_vals = pivot_vals.index.tolist()
        text_vals = []
        for i, g in enumerate(y_vals):
            avg_days = float(x_vals[i])
            cnt = int(pivot_cnts.loc[g, transition]) if transition in pivot_cnts.columns else 0
            text_vals.append(f"{avg_days:.1f} d | {cnt}")
        fig.add_trace(
            go.Bar(
                y=y_vals,
                x=x_vals,
                name=str(transition),
                orientation="h",
                text=text_vals,
                textposition="inside",
                textfont={"size": 9},
                hovertemplate="<b>%{y}</b><br>%{fullData.name}<br>Average: %{x:.2f} days<br>Count: %{text}<extra></extra>",
            )
        )

    fig.update_layout(
        title="Phase Transition Average Duration (Grouped & Stacked)",
        xaxis_title="Average Duration (days)",
        yaxis_title="Group",
        barmode="stack",
        height=420,
        template="plotly_white" if theme == "light" else "plotly_dark",
        showlegend=False,
        margin=dict(l=160, r=60, t=60, b=40),
        hoverlabel=dict(namelength=-1),
    )
    return fig


def create_grouped_sorted_total_chart(df: pd.DataFrame, theme: str):
    if df.empty:
        return empty_figure(theme, "无数据")
    df = df.copy()
    df = df[df["Group"].isin(["Q-Gate", "Integration", "CoC"])]
    groups = ["Q-Gate", "Integration", "CoC"]
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08, subplot_titles=groups)
    for i, g in enumerate(groups, start=1):
        gdf = df[df["Group"] == g].copy()
        if gdf.empty:
            continue
        gdf = gdf.sort_values("Avg_Days", ascending=False)
        fig.add_trace(
            go.Bar(
                y=gdf["Phase_Transition"],
                x=gdf["Avg_Days"],
                orientation="h",
                text=[f"{d:.1f} d | {int(c)}" for d, c in zip(gdf["Avg_Days"], gdf["Count"])],
                textposition="auto",
                hovertemplate="<b>%{y}</b><br>Average: %{x:.2f} days<br>Count: %{text}<extra></extra>",
            ),
            row=i,
            col=1,
        )
        total = float((gdf["Avg_Days"] * gdf["Count"]).sum())
        total_count = float(gdf["Count"].sum())
        avg_per_ticket = total / total_count if total_count > 0 else 0.0
        fig.add_annotation(
            row=i,
            col=1,
            xref="x",
            yref="y",
            x=float(gdf["Avg_Days"].max() if len(gdf) > 0 else 0),
            y=str(gdf["Phase_Transition"].iloc[0] if len(gdf) > 0 else ""),
            text=f"Avg per ticket: {avg_per_ticket:.1f} d",
            showarrow=False,
            font=dict(size=11),
            xanchor="right",
            yanchor="bottom",
        )

    fig.update_layout(
        title="Phase Transition Average Duration (Grouped & Sorted)",
        xaxis_title="Average Duration (days)",
        height=760,
        template="plotly_white" if theme == "light" else "plotly_dark",
        showlegend=False,
        margin=dict(l=300, r=50, t=60, b=40),
    )
    for i in range(1, 4):
        fig["layout"][f"yaxis{i}"]["title"] = dict(text=groups[i - 1])
    return fig


def create_app(args):
    app = Dash(__name__, suppress_callback_exceptions=True)

    app.layout = html.Div(
        [
            create_theme_switcher(),
            html.H1("Q-Gate：Phase Transition 效率看板", id="qgate-main-title", style={"textAlign": "center", "marginBottom": "20px"}),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("Teams：", id="qgate-teams-label", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            dcc.Dropdown(
                                id="qgate-teams-dropdown",
                                options=[{"label": t, "value": t} for t in DEFAULT_TEAMS],
                                value=DEFAULT_TEAMS,
                                multi=True,
                                style={"minWidth": "260px"},
                            ),
                        ],
                        style={"flex": "2", "marginRight": "20px"},
                    ),
                    html.Div(
                        [
                            html.Label("Group：", id="qgate-group-label", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            dcc.Dropdown(
                                id="qgate-group-dropdown",
                                options=[
                                    {"label": "All", "value": "all"},
                                    {"label": "Q-Gate", "value": "Q-Gate"},
                                    {"label": "Integration", "value": "Integration"},
                                    {"label": "CoC", "value": "CoC"},
                                    {"label": "Other", "value": "Other"},
                                ],
                                value=["all"],
                                multi=True,
                                style={"minWidth": "220px"},
                            ),
                        ],
                        style={"flex": "1", "marginRight": "20px"},
                    ),
                    html.Div(
                        [
                            html.Label("Change By：", id="qgate-changeby-label", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            dcc.Dropdown(
                                id="qgate-changeby-dropdown",
                                options=[{"label": "All", "value": "all"}],
                                value="all",
                                multi=False,
                                style={"minWidth": "220px"},
                            ),
                        ],
                        style={"flex": "1", "marginRight": "20px"},
                    ),
                    html.Div(
                        [
                            html.Label("FiF：", id="qgate-fif-label", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            dcc.Dropdown(
                                id="qgate-fif-dropdown",
                                options=[
                                    {"label": "All", "value": "all"},
                                    {"label": "China Specific", "value": "China Specific"},
                                    {"label": "Global", "value": "Global"},
                                ],
                                value="all",
                                multi=False,
                                style={"minWidth": "220px"},
                            ),
                        ],
                        style={"flex": "1", "marginRight": "20px"},
                    ),
                    html.Div(
                        [
                            html.Label("Timespan(Days)：", id="qgate-timespan-label", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            dcc.RangeSlider(
                                id="qgate-timespan-slider",
                                min=0,
                                max=1,
                                value=[0, 1],
                                step=1,
                                marks={0: "0", 1: "1"},
                                tooltip={"placement": "bottom", "always_visible": False},
                                allowCross=False,
                                disabled=True,
                            ),
                        ],
                        style={"flex": "2", "minWidth": "360px", "marginRight": "20px"},
                    ),
                    html.Div(
                        [
                            html.Label("Min Count：", id="qgate-min-count-label", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            dcc.Input(id="qgate-min-count-input", type="number", min=1, step=1, value=args.min_transition_count),
                        ],
                        style={"flex": "1", "marginRight": "20px"},
                    ),
                    html.Div(
                        [
                            html.Label("Paths：", id="qgate-paths-label", style={"fontWeight": "bold", "marginBottom": "5px"}),
                            html.Div(
                                [
                                    dcc.Input(id="qgate-defect-dir-input", type="text", value=args.defect_dir, style={"width": "48%", "marginRight": "4%"}),
                                    dcc.Input(id="qgate-history-dir-input", type="text", value=args.history_dir, style={"width": "48%"}),
                                ],
                                style={"display": "flex"},
                            ),
                        ],
                        style={"flex": "2", "marginRight": "20px"},
                    ),
                    html.Div(
                        [
                            html.Button("刷新/重新计算", id="qgate-refresh-btn", n_clicks=0, style={"marginTop": "22px", "width": "140px"}),
                        ],
                        style={"flex": "0"},
                    ),
                ],
                style={"display": "flex", "flexWrap": "wrap", "gap": "10px", "marginBottom": "20px"},
            ),
            dcc.Loading(
                [
                    html.Div(id="qgate-status", style={"marginBottom": "10px"}),
                    dcc.Store(id="qgate-data-store"),
                    dcc.Graph(id="qgate-summary-chart"),
                    html.H3("Long Runner Analysis（按 Transition 汇总）", style={"marginTop": "30px"}),
                    dcc.Graph(id="qgate-lr-duration-ranking"),
                    dcc.Graph(id="qgate-lr-grouped-stacked"),
                    dcc.Graph(id="qgate-lr-grouped-sorted"),
                    html.H3("明细（按 Team + Transition）", style={"marginTop": "30px"}),
                    dash_table.DataTable(
                        id="qgate-detail-table",
                        columns=[
                            {"name": "Team", "id": "Team"},
                            {"name": "Group", "id": "Group"},
                            {"name": "Phase_Transition", "id": "Phase_Transition"},
                            {"name": "Changed_By", "id": "Changed_By"},
                            {"name": "FiF", "id": "FiF"},
                            {"name": "Count", "id": "Count"},
                            {"name": "Avg_Days", "id": "Avg_Days"},
                            {"name": "Median_Hours", "id": "Median_Hours"},
                            {"name": "Min_Hours", "id": "Min_Hours"},
                            {"name": "Max_Hours", "id": "Max_Hours"},
                        ],
                        data=[],
                        page_size=20,
                        sort_action="native",
                        filter_action="native",
                        style_table={"overflowX": "auto"},
                        style_cell={"padding": "6px", "fontFamily": "Arial", "fontSize": "12px", "textAlign": "left"},
                        style_header={"fontWeight": "bold"},
                    ),
                ],
                type="default",
            ),
            html.Div(
                id="qgate-issue-modal",
                style={"display": "none"},
                children=[
                    html.Div(
                        style={
                            "backgroundColor": "white",
                            "width": "92%",
                            "maxWidth": "1200px",
                            "maxHeight": "90%",
                            "overflowY": "auto",
                            "borderRadius": "10px",
                            "padding": "20px",
                            "position": "relative",
                        },
                        children=[
                            html.Button("关闭", id="qgate-issue-modal-close", n_clicks=0, style={"position": "absolute", "top": "12px", "right": "12px"}),
                            html.H3(id="qgate-issue-modal-title", style={"marginTop": "0"}),
                            html.Div(id="qgate-issue-modal-info", style={"marginBottom": "12px"}),
                            dash_table.DataTable(
                                id="qgate-issue-modal-table",
                                columns=[
                                    {"name": "Ticket", "id": "Ticket_Link", "presentation": "markdown"},
                                    {"name": "Ticket_Name", "id": "Ticket_Name"},
                                    {"name": "Tester", "id": "Tester"},
                                    {"name": "Team", "id": "Team"},
                                    {"name": "Group", "id": "Group"},
                                    {"name": "Phase_Transition", "id": "Phase_Transition"},
                                    {"name": "FiF", "id": "FiF"},
                                    {"name": "Changed_By", "id": "Changed_By"},
                                    {"name": "Transitions", "id": "Transitions"},
                                    {"name": "Duration_Days", "id": "Duration_Days"},
                                    {"name": "Duration_Hours", "id": "Duration_Hours"},
                                    {"name": "Start_Time", "id": "Start_Time"},
                                    {"name": "End_Time", "id": "End_Time"},
                                ],
                                data=[],
                                page_size=20,
                                sort_action="native",
                                filter_action="native",
                                markdown_options={"link_target": "_blank"},
                                style_table={"overflowX": "auto"},
                                style_cell={"padding": "6px", "fontFamily": "Arial", "fontSize": "12px", "textAlign": "left"},
                                style_header={"fontWeight": "bold"},
                            ),
                        ],
                    )
                ],
            ),
        ],
        id="qgate-main-container",
        style=MAIN_CONTAINER_STYLE,
    )

    @app.callback(
        Output("qgate-data-store", "data"),
        Output("qgate-status", "children"),
        Output("qgate-changeby-dropdown", "options"),
        Output("qgate-changeby-dropdown", "value"),
        Output("qgate-fif-dropdown", "value"),
        Output("qgate-timespan-slider", "min"),
        Output("qgate-timespan-slider", "max"),
        Output("qgate-timespan-slider", "value"),
        Output("qgate-timespan-slider", "marks"),
        Output("qgate-timespan-slider", "disabled"),
        Input("qgate-refresh-btn", "n_clicks"),
        Input("qgate-teams-dropdown", "value"),
        Input("qgate-defect-dir-input", "value"),
        Input("qgate-history-dir-input", "value"),
        prevent_initial_call=False,
    )
    def refresh_data(n_clicks, teams_value, defect_dir, history_dir):
        teams = teams_value or []
        if not teams:
            raise PreventUpdate
        use_cache = not args.no_cache
        cache_dir = None if args.no_cache else args.cache_dir
        meta_df, stats_df, issues_df = compute_all_teams_data(
            defect_dir=defect_dir,
            history_dir=history_dir,
            teams=teams,
            show_progress=not args.no_progress,
            analysis_workers=args.analysis_workers,
            cache_dir=cache_dir,
            use_cache=use_cache,
        )
        global global_issue_df
        global_issue_df = issues_df.copy() if isinstance(issues_df, pd.DataFrame) else pd.DataFrame()
        payload = {
            "stats": stats_df.to_json(orient="split") if not stats_df.empty else None,
        }
        status = f"已加载 teams={len(teams)} | defect_dir={defect_dir} | history_dir={history_dir}"
        all_label = "(All)"
        users = []
        if not stats_df.empty and "Changed_By" in stats_df.columns:
            users = sorted({str(x) for x in stats_df["Changed_By"].dropna().tolist() if str(x).strip() and str(x) != all_label})
        options = [{"label": "All", "value": "all"}] + [{"label": u, "value": u} for u in users]
        span_series = pd.to_numeric(global_issue_df.get("Ticket_Timespan_Days"), errors="coerce") if not global_issue_df.empty else pd.Series([], dtype="float64")
        span_series = span_series.dropna()
        if span_series.empty:
            slider_min, slider_max = 0, 1
            slider_value = [0, 1]
            slider_marks = {0: "0", 1: "1"}
            slider_disabled = True
        else:
            slider_min = 0
            slider_max = int(max(1, float(span_series.max()) // 1 + 1))
            slider_value = [slider_min, slider_max]
            slider_disabled = False
            slider_marks = {
                slider_min: str(slider_min),
                int(round(slider_max * 0.25)): str(int(round(slider_max * 0.25))),
                int(round(slider_max * 0.5)): str(int(round(slider_max * 0.5))),
                int(round(slider_max * 0.75)): str(int(round(slider_max * 0.75))),
                slider_max: str(slider_max),
            }
            slider_marks = {k: v for k, v in slider_marks.items() if 0 <= k <= slider_max}
        global global_timespan_slider_min
        global global_timespan_slider_max
        global_timespan_slider_min = slider_min
        global_timespan_slider_max = slider_max
        return payload, status, options, "all", "all", slider_min, slider_max, slider_value, slider_marks, slider_disabled

    @app.callback(
        Output("qgate-summary-chart", "figure"),
        Output("qgate-lr-duration-ranking", "figure"),
        Output("qgate-lr-grouped-stacked", "figure"),
        Output("qgate-lr-grouped-sorted", "figure"),
        Output("qgate-detail-table", "data"),
        Input("qgate-data-store", "data"),
        Input("qgate-group-dropdown", "value"),
        Input("qgate-changeby-dropdown", "value"),
        Input("qgate-fif-dropdown", "value"),
        Input("qgate-timespan-slider", "value"),
        Input("qgate-min-count-input", "value"),
        Input("global-theme-switcher", "value"),
    )
    def render_views(data, groups_value, changeby_value, fif_value, timespan_value, min_count, theme_value):
        theme = theme_value or "light"
        if not data:
            fig = empty_figure(theme, "请点击 刷新/重新计算")
            return fig, fig, fig, fig, []

        stats_json = data.get("stats")
        if not stats_json:
            fig = empty_figure(theme, "未找到可分析的数据（defect 或 history 为空）")
            return fig, fig, fig, fig, []

        stats_df = pd.read_json(StringIO(stats_json), orient="split")
        if stats_df.empty:
            fig = empty_figure(theme, "未找到可分析的数据（phase transition 为空）")
            return fig, fig, fig, fig, []

        selected_groups = groups_value or ["all"]
        all_label = "(All)"
        selected_user = (str(changeby_value).strip() if changeby_value is not None else "all") or "all"
        selected_fif = (str(fif_value).strip() if fif_value is not None else "all") or "all"

        global global_issue_df
        filtered_issues = global_issue_df.copy() if isinstance(global_issue_df, pd.DataFrame) else pd.DataFrame()
        if not filtered_issues.empty:
            if selected_groups and "all" not in selected_groups:
                filtered_issues = filtered_issues[filtered_issues["Group"].isin(selected_groups)]
            if selected_user != "all":
                filtered_issues = filtered_issues[filtered_issues["Changed_By"] == selected_user]
            if selected_fif != "all":
                filtered_issues = filtered_issues[filtered_issues["FiF"] == selected_fif]

            min_span = None
            max_span = None
            if isinstance(timespan_value, (list, tuple)) and len(timespan_value) == 2:
                try:
                    min_span = float(timespan_value[0])
                    max_span = float(timespan_value[1])
                except Exception:
                    min_span = None
                    max_span = None

            global global_timespan_slider_min
            global global_timespan_slider_max
            slider_min = float(global_timespan_slider_min)
            slider_max = float(global_timespan_slider_max)

            if min_span is not None and max_span is not None and slider_min is not None and slider_max is not None:
                if not (min_span == slider_min and max_span == slider_max):
                    span_series = pd.to_numeric(filtered_issues.get("Ticket_Timespan_Days"), errors="coerce")
                    filtered_issues = filtered_issues[span_series.notna() & (span_series >= min_span) & (span_series <= max_span)]

        if filtered_issues.empty:
            filtered = pd.DataFrame()
        else:
            agg = filtered_issues.groupby(["Team", "Group", "Phase_Transition"], dropna=False).agg(
                Count=("Duration_Hours", "size"),
                Avg_Hours=("Duration_Hours", "mean"),
                Min_Hours=("Duration_Hours", "min"),
                Max_Hours=("Duration_Hours", "max"),
                Median_Hours=("Duration_Hours", "median"),
            )
            agg = agg.reset_index()
            agg["Avg_Hours"] = agg["Avg_Hours"].round(2)
            agg["Avg_Days"] = (agg["Avg_Hours"] / 24).round(2)
            agg["Min_Hours"] = agg["Min_Hours"].round(2)
            agg["Max_Hours"] = agg["Max_Hours"].round(2)
            agg["Median_Hours"] = agg["Median_Hours"].round(2)
            agg["Changed_By"] = all_label if selected_user == "all" else selected_user
            agg["FiF"] = all_label if selected_fif == "all" else selected_fif
            filtered = agg

        min_transition_count = int(min_count) if min_count else 1
        filtered, summary_df = build_summary_frames(filtered, min_transition_count)

        if summary_df.empty:
            fig = empty_figure(theme, "筛选后无数据（可降低 Min Count 或调整 Group/Teams）")
            fig2 = empty_figure(theme, "筛选后无数据")
            detail_rows = filtered.sort_values(["Team", "Avg_Days"], ascending=[True, False]).to_dict("records") if not filtered.empty else []
            return fig, fig2, fig2, fig2, detail_rows

        fig = px.bar(
            summary_df,
            x="Weighted_Avg_Days",
            y="Team",
            color="Group",
            orientation="h",
            barmode="stack",
            title="Phase Transition Efficiency by Team (Sum of Avg Days by Group)",
            hover_data=["Transitions_Total", "Samples_Total"],
        )
        fig.update_layout(template="plotly_white" if theme == "light" else "plotly_dark", height=max(420, 40 * len(summary_df["Team"].unique()) + 160))

        transition_df = aggregate_transition_summary(filtered)
        duration_ranking_fig = create_phase_duration_ranking_chart(transition_df, theme)
        grouped_stacked_fig = create_grouped_stacked_chart(transition_df, theme)
        grouped_sorted_fig = create_grouped_sorted_total_chart(transition_df, theme)

        detail_rows = filtered.sort_values(["Team", "Avg_Days"], ascending=[True, False]).to_dict("records")
        return fig, duration_ranking_fig, grouped_stacked_fig, grouped_sorted_fig, detail_rows

    @app.callback(
        Output("qgate-issue-modal", "style"),
        Output("qgate-issue-modal-title", "children"),
        Output("qgate-issue-modal-info", "children"),
        Output("qgate-issue-modal-table", "data"),
        Input("qgate-summary-chart", "clickData"),
        Input("qgate-lr-duration-ranking", "clickData"),
        Input("qgate-lr-grouped-stacked", "clickData"),
        Input("qgate-lr-grouped-sorted", "clickData"),
        Input("qgate-issue-modal-close", "n_clicks"),
        State("qgate-group-dropdown", "value"),
        State("qgate-changeby-dropdown", "value"),
        State("qgate-fif-dropdown", "value"),
        State("qgate-timespan-slider", "value"),
        prevent_initial_call=True,
    )
    def open_issue_modal(summary_click, ranking_click, grouped_stacked_click, grouped_sorted_click, close_clicks, groups_value, changeby_value, fif_value, timespan_value):
        triggered = (dash.callback_context.triggered[0]["prop_id"] if dash.callback_context.triggered else "").split(".")[0]
        if triggered == "qgate-issue-modal-close":
            return {"display": "none"}, "", "", []

        global global_issue_df
        if global_issue_df is None or global_issue_df.empty:
            return {"display": "none"}, "", "", []

        df = global_issue_df.copy()

        selected_groups = groups_value or ["all"]
        if selected_groups and "all" not in selected_groups:
            df = df[df["Group"].isin(selected_groups)]

        selected_user = (str(changeby_value).strip() if changeby_value is not None else "all") or "all"
        if selected_user != "all":
            df = df[df["Changed_By"] == selected_user]

        selected_fif = (str(fif_value).strip() if fif_value is not None else "all") or "all"
        if selected_fif != "all":
            df = df[df["FiF"] == selected_fif]

        min_span = None
        max_span = None
        if isinstance(timespan_value, (list, tuple)) and len(timespan_value) == 2:
            try:
                min_span = float(timespan_value[0])
                max_span = float(timespan_value[1])
            except Exception:
                min_span = None
                max_span = None
        global global_timespan_slider_min
        global global_timespan_slider_max
        slider_min = float(global_timespan_slider_min)
        slider_max = float(global_timespan_slider_max)
        if min_span is not None and max_span is not None:
            if not (min_span == slider_min and max_span == slider_max):
                span_series = pd.to_numeric(df.get("Ticket_Timespan_Days"), errors="coerce")
                df = df[span_series.notna() & (span_series >= min_span) & (span_series <= max_span)]

        clickData = None
        chart_kind = ""
        if triggered == "qgate-summary-chart":
            clickData = summary_click
            chart_kind = "summary"
        elif triggered == "qgate-lr-duration-ranking":
            clickData = ranking_click
            chart_kind = "transition"
        elif triggered == "qgate-lr-grouped-stacked":
            clickData = grouped_stacked_click
            chart_kind = "grouped_stacked"
        elif triggered == "qgate-lr-grouped-sorted":
            clickData = grouped_sorted_click
            chart_kind = "transition"
        else:
            return {"display": "none"}, "", "", []

        if not clickData or not clickData.get("points"):
            return {"display": "none"}, "", "", []

        point = clickData["points"][0]

        def normalize_time(v):
            if not v:
                return v
            try:
                from datetime import datetime

                t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                return t.strftime("%Y-%m-%d %H:%M")
            except Exception:
                return v

        if chart_kind == "summary":
            team = str(point.get("y") or "").strip()
            group = str((point.get("data") or {}).get("name") or "").strip()
            if not team or not group:
                return {"display": "none"}, "", "", []
            sdf = df[(df["Team"] == team) & (df["Group"] == group)].copy()
            if sdf.empty:
                return {"display": "none"}, "", "", []

            sdf["Start_Time"] = sdf["Start_Time"].apply(normalize_time)
            sdf["End_Time"] = sdf["End_Time"].apply(normalize_time)
            agg = (
                sdf.groupby(["Ticket_ID", "Ticket_Link", "Ticket_Name", "Tester", "Team", "Group", "FiF"], dropna=False)
                .agg(
                    Duration_Hours=("Duration_Hours", "sum"),
                    Duration_Days=("Duration_Days", "sum"),
                    Transitions=("Phase_Transition", "nunique"),
                )
                .reset_index()
            )
            agg["Duration_Hours"] = agg["Duration_Hours"].round(2)
            agg["Duration_Days"] = agg["Duration_Days"].round(2)
            agg = agg.sort_values(["Duration_Days", "Transitions"], ascending=[False, False])
            modal_title = f"Team={team} | Group={group}"
            modal_info = html.Div(f"Tickets: {len(agg)}（按该 Group 内所有 transition 的 duration 求和）")
            table_rows = agg.to_dict("records")
        else:
            transition = str(point.get("y") or "").strip()
            if chart_kind == "grouped_stacked":
                transition = str((point.get("data") or {}).get("name") or "").strip()
            if not transition:
                return {"display": "none"}, "", "", []

            sdf = df[df["Phase_Transition"] == transition].copy()
            if sdf.empty:
                return {"display": "none"}, "", "", []

            sdf["Start_Time"] = sdf["Start_Time"].apply(normalize_time)
            sdf["End_Time"] = sdf["End_Time"].apply(normalize_time)
            sdf = sdf.sort_values(["Duration_Hours"], ascending=[False])

            avg_hours = float(sdf["Duration_Hours"].mean()) if len(sdf) else 0.0
            max_hours = float(sdf["Duration_Hours"].max()) if len(sdf) else 0.0
            min_hours = float(sdf["Duration_Hours"].min()) if len(sdf) else 0.0
            modal_title = f"Phase Transition: {transition}"
            modal_info = html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.H5("Total", style={"margin": "0"}), html.P(f"{len(sdf)} rows", style={"margin": "0", "fontWeight": "bold"})], style={"textAlign": "center", "padding": "8px", "backgroundColor": "#e8f4f8", "borderRadius": "6px", "margin": "4px"}),
                            html.Div([html.H5("Avg", style={"margin": "0"}), html.P(f"{avg_hours:.1f} h", style={"margin": "0", "fontWeight": "bold"})], style={"textAlign": "center", "padding": "8px", "backgroundColor": "#fff2e6", "borderRadius": "6px", "margin": "4px"}),
                            html.Div([html.H5("Max", style={"margin": "0"}), html.P(f"{max_hours:.1f} h", style={"margin": "0", "fontWeight": "bold"})], style={"textAlign": "center", "padding": "8px", "backgroundColor": "#ffe6e6", "borderRadius": "6px", "margin": "4px"}),
                            html.Div([html.H5("Min", style={"margin": "0"}), html.P(f"{min_hours:.1f} h", style={"margin": "0", "fontWeight": "bold"})], style={"textAlign": "center", "padding": "8px", "backgroundColor": "#e6ffe6", "borderRadius": "6px", "margin": "4px"}),
                        ],
                        style={"display": "flex", "justifyContent": "space-around", "flexWrap": "wrap"},
                    )
                ]
            )
            table_rows = sdf.to_dict("records")

        modal_style = {
            "position": "fixed",
            "top": "0",
            "left": "0",
            "width": "100%",
            "height": "100%",
            "backgroundColor": "rgba(0, 0, 0, 0.5)",
            "display": "flex",
            "justifyContent": "center",
            "alignItems": "center",
            "zIndex": "9999",
        }
        return modal_style, modal_title, modal_info, table_rows

    @app.callback(
        Output("qgate-main-container", "style"),
        Output("qgate-main-title", "style"),
        Output("qgate-teams-label", "style"),
        Output("qgate-group-label", "style"),
        Output("qgate-changeby-label", "style"),
        Output("qgate-fif-label", "style"),
        Output("qgate-timespan-label", "style"),
        Output("qgate-min-count-label", "style"),
        Output("qgate-paths-label", "style"),
        Input("global-theme-switcher", "value"),
        prevent_initial_call=False,
    )
    def update_theme(selected_theme):
        if selected_theme == "light":
            container_style = LIGHT_MAIN_CONTAINER_STYLE.copy()
            title_style = {"textAlign": "center", "marginBottom": "20px", "color": LIGHT_TEXT_COLOR}
            label_style = {"fontWeight": "bold", "marginBottom": "5px", "color": LIGHT_TEXT_COLOR}
        else:
            container_style = MAIN_CONTAINER_STYLE.copy()
            title_style = {"textAlign": "center", "marginBottom": "20px", "color": TEXT_COLOR}
            label_style = {"fontWeight": "bold", "marginBottom": "5px", "color": TEXT_COLOR}
        theme_manager.set_theme(selected_theme)
        return container_style, title_style, label_style, label_style, label_style, label_style, label_style, label_style, label_style

    return app


if __name__ == "__main__":
    import socket

    args = parse_args()
    host = os.environ.get("HOST", args.host)
    port = int(os.environ.get("PORT", str(args.port)))
    debug = os.environ.get("DEBUG", "True").lower() == "true"

    if args.batch:
        run_batch(args)
    else:
        app = create_app(args)
        if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            try:
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
                print("\n" + "=" * 50)
                print("Q-Gate 看板启动信息")
                print("=" * 50)
                print(f"主机: {host}")
                print(f"端口: {port}")
                print(f"调试模式: {debug}")
                print(f"本机访问: http://localhost:{port}")
                print(f"本机访问: http://127.0.0.1:{port}")
                if host == "0.0.0.0":
                    print(f"局域网访问: http://{local_ip}:{port}")
                    print(f"主机名访问: http://{hostname}:{port}")
                print("=" * 50)
                print("团队成员可通过局域网IP访问看板")
                print(f"请确保防火墙允许 {port} 端口访问")
                print("=" * 50 + "\n")
            except Exception as e:
                print(f"获取网络信息时出错: {e}")
        try:
            app.run(debug=debug, host=host, port=port, threaded=True)
        except TypeError:
            app.run(debug=debug, host=host, port=port)

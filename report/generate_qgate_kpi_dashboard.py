#!/usr/bin/env python3
"""Generate a KPI-style standalone HTML dashboard for QGate analytics."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import qgate  # noqa: E402
from qgate_summary_store import load_summary_data  # noqa: E402


class QGateDashboardDataError(ValueError):
  """Raised when QGate source data cannot produce a dashboard payload."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a standalone KPI-style QGate HTML dashboard")
    parser.add_argument("--defect-dir", default="qgate/defect", help="Defect data directory")
    parser.add_argument("--history-dir", default="qgate/history", help="History data directory")
    parser.add_argument("--teams", default=",".join(qgate.DEFAULT_TEAMS), help="Comma-separated team list")
    parser.add_argument("--min-transition-count", type=int, default=200, help="Minimum samples per transition")
    parser.add_argument("--analysis-workers", type=int, default=0, help="Parallel workers for history analysis")
    parser.add_argument("--cache-dir", default="qgate_cache", help="History analysis cache directory")
    parser.add_argument("--no-cache", action="store_true", help="Disable cache")
    parser.add_argument("--no-progress", action="store_true", help="Disable console progress logs")
    parser.add_argument(
        "--output",
        default=str(Path("report") / "qgate_kpi_dashboard.html"),
        help="Output HTML file path",
    )
    return parser.parse_args()


def normalize_number(value, digits: int = 2):
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), digits)
    return value


def sanitize_record(record: dict) -> dict:
    cleaned = {}
    for key, value in record.items():
        if isinstance(value, pd.Timestamp):
            cleaned[key] = value.isoformat()
        elif isinstance(value, float):
            cleaned[key] = normalize_number(value)
        elif pd.isna(value):
            cleaned[key] = None
        else:
            cleaned[key] = value
    return cleaned


def sanitize_dataset(df: pd.DataFrame, columns: list[str]) -> dict:
    if df.empty:
        return {"columns": columns, "rows": []}
    rows = []
    for record in df[columns].to_dict("records"):
        cleaned = sanitize_record(record)
        rows.append([cleaned.get(column) for column in columns])
    return {"columns": columns, "rows": rows}


def median_from_list(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    count = len(ordered)
    mid = count // 2
    if count % 2 == 1:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2)


def build_detail_from_issues(issues_df: pd.DataFrame) -> pd.DataFrame:
    if issues_df.empty:
        return pd.DataFrame(
            columns=[
                "Team",
                "Group",
                "Phase_Transition",
                "Changed_By",
                "FiF",
                "Count",
                "Avg_Hours",
                "Avg_Days",
                "Median_Hours",
                "Min_Hours",
                "Max_Hours",
            ]
        )

    grouped_rows = []
    group_fields = ["Team", "Group", "Phase_Transition", "Changed_By", "FiF"]
    for keys, group_df in issues_df.groupby(group_fields, dropna=False):
        hours = [float(x) for x in group_df["Duration_Hours"].dropna().tolist()]
        if not hours:
            continue
        avg_hours = round(sum(hours) / len(hours), 2)
        grouped_rows.append(
            {
                "Team": keys[0],
                "Group": keys[1],
                "Phase_Transition": keys[2],
                "Changed_By": keys[3],
                "FiF": keys[4],
                "Count": len(hours),
                "Avg_Hours": avg_hours,
                "Avg_Days": round(avg_hours / 24, 2),
                "Median_Hours": round(median_from_list(hours), 2),
                "Min_Hours": round(min(hours), 2),
                "Max_Hours": round(max(hours), 2),
            }
        )

    detail_df = pd.DataFrame(grouped_rows)
    if detail_df.empty:
        return detail_df
    return detail_df.sort_values(["Team", "Group", "Avg_Days"], ascending=[True, True, False]).reset_index(drop=True)


def build_coverage_from_scope(scope_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"]
    if scope_df.empty:
      return pd.DataFrame(columns=columns)

    coverage_df = scope_df[["Team", "Year", "Ticket_ID", "History_Parse_OK"]].copy()
    coverage_df["Defects"] = 1
    coverage_df["History_OK"] = pd.to_numeric(coverage_df["History_Parse_OK"], errors="coerce").fillna(0).astype(int)
    coverage_df = (
      coverage_df.groupby(["Team", "Year"], dropna=False)[["Defects", "History_OK"]]
      .sum()
      .reset_index()
    )
    coverage_df["History_Missing_or_Error"] = (coverage_df["Defects"] - coverage_df["History_OK"]).clip(lower=0).astype(int)
    coverage_df = coverage_df[columns]
    return coverage_df.sort_values(["Year", "Defects", "Team"], ascending=[True, False, True]).reset_index(drop=True)


def build_meta_from_coverage(coverage_df: pd.DataFrame) -> pd.DataFrame:
    columns = ["Team", "Defects", "History_OK", "History_Missing_or_Error"]
    if coverage_df.empty:
      return pd.DataFrame(columns=columns)

    meta_df = (
      coverage_df.groupby(["Team"], dropna=False)[["Defects", "History_OK", "History_Missing_or_Error"]]
      .sum()
      .reset_index()
    )
    meta_df = meta_df[columns]
    return meta_df.sort_values(["Defects", "Team"], ascending=[False, True]).reset_index(drop=True)


def build_year_lookup_and_coverage(defect_dir: str, teams: list[str], issues_df: pd.DataFrame) -> tuple[dict[tuple[str, str], str], pd.DataFrame]:
    ticket_year_rows: list[dict] = []
    source_mode = os.environ.get("OCTANE_DATA_SOURCE", "db_only").strip().lower()
    db_path = os.environ.get("QGATE_DB_PATH") or os.path.join("qgate", "qgate_data.db")

    if db_path and os.path.exists(db_path):
        placeholders = ",".join(["?"] * len(teams))
        query = f"""
            SELECT raw_json, year, team, problem_finder_team
            FROM octane_defects
            WHERE team IN ({placeholders}) OR problem_finder_team IN ({placeholders})
        """
        try:
            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(query, [*teams, *teams]).fetchall()
            finally:
                conn.close()
            for raw_json, year_value, team_value, problem_finder_team in rows:
                try:
                    payload = json.loads(raw_json) if raw_json else None
                except Exception:
                    payload = None
                if not isinstance(payload, dict):
                    continue
                ticket_id = str(payload.get("id") or "").strip()
                if not ticket_id:
                    continue
                matched_team = None
                for candidate in (team_value, problem_finder_team):
                    candidate_value = str(candidate or "").strip()
                    if candidate_value in teams:
                        matched_team = candidate_value
                        break
                if not matched_team:
                    continue
                year_text = str(year_value or "").strip()
                if not year_text:
                    creation_time = str(payload.get("creation_time") or "").strip()
                    year_match = re.search(r"(\d{4})", creation_time)
                    year_text = year_match.group(1) if year_match else ""
                if not year_text:
                    continue
                ticket_year_rows.append({"Team": matched_team, "Ticket_ID": ticket_id, "Year": year_text})
        except sqlite3.Error:
            pass

    defect_path = Path(defect_dir)
    team_by_slug = {qgate.slugify_team_name(team): team for team in teams}
    if source_mode != "db_only" and defect_path.is_dir():
        for path in defect_path.glob("*_defect.json"):
            match = re.match(r"^(\d{4})_(.+)_defect\.json$", path.name)
            if not match:
                continue
            year = match.group(1)
            team = team_by_slug.get(match.group(2))
            if not team:
                continue
            try:
                df = pd.read_json(path)
            except ValueError:
                continue
            if df.empty or "id" not in df.columns:
                continue
            ticket_ids = df["id"].dropna().astype(str).str.strip()
            ticket_ids = ticket_ids[ticket_ids != ""]
            for ticket_id in ticket_ids.unique().tolist():
                ticket_year_rows.append({"Team": team, "Ticket_ID": ticket_id, "Year": year})

    ticket_year_df = pd.DataFrame(ticket_year_rows)
    if ticket_year_df.empty:
        return {}, pd.DataFrame(columns=["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"])

    dedup_ticket_year_df = ticket_year_df.drop_duplicates(["Team", "Ticket_ID", "Year"]).copy()
    year_lookup = (
        dedup_ticket_year_df.sort_values(["Team", "Ticket_ID", "Year"])
        .drop_duplicates(["Team", "Ticket_ID"], keep="first")
        .set_index(["Team", "Ticket_ID"])["Year"]
        .to_dict()
    )

    defect_counts = (
        dedup_ticket_year_df.groupby(["Team", "Year"], dropna=False)["Ticket_ID"]
        .nunique()
        .reset_index(name="Defects")
    )

    issue_history_ok = pd.DataFrame(columns=["Team", "Year", "History_OK"])
    if not issues_df.empty:
        ok_df = issues_df[["Team", "Ticket_ID"]].dropna().copy()
        if not ok_df.empty:
            ok_df["Year"] = ok_df.apply(lambda row: year_lookup.get((str(row["Team"]), str(row["Ticket_ID"]))), axis=1)
            ok_df = ok_df.dropna(subset=["Year"]).drop_duplicates(["Team", "Ticket_ID", "Year"])
            issue_history_ok = (
                ok_df.groupby(["Team", "Year"], dropna=False)["Ticket_ID"]
                .nunique()
                .reset_index(name="History_OK")
            )

    coverage_df = defect_counts.merge(issue_history_ok, on=["Team", "Year"], how="left")
    coverage_df["History_OK"] = pd.to_numeric(coverage_df.get("History_OK"), errors="coerce").fillna(0).astype(int)
    coverage_df["History_Missing_or_Error"] = (coverage_df["Defects"] - coverage_df["History_OK"]).clip(lower=0).astype(int)
    coverage_df = coverage_df.sort_values(["Year", "Defects", "Team"], ascending=[True, False, True]).reset_index(drop=True)
    return year_lookup, coverage_df

def build_overview(coverage_df: pd.DataFrame, issues_df: pd.DataFrame, summary_df: pd.DataFrame, transition_df: pd.DataFrame) -> dict:
    history_ok = int(pd.to_numeric(coverage_df.get("History_OK"), errors="coerce").fillna(0).sum()) if not coverage_df.empty else 0
    history_bad = int(pd.to_numeric(coverage_df.get("History_Missing_or_Error"), errors="coerce").fillna(0).sum()) if not coverage_df.empty else 0
    defects = int(pd.to_numeric(coverage_df.get("Defects"), errors="coerce").fillna(0).sum()) if not coverage_df.empty else 0
    unique_tickets = int(issues_df["Ticket_ID"].nunique()) if not issues_df.empty else 0
    unique_transitions = int(transition_df["Phase_Transition"].nunique()) if not transition_df.empty else 0
    samples = int(pd.to_numeric(summary_df.get("Samples_Total"), errors="coerce").fillna(0).sum()) if not summary_df.empty else 0
    timespan_series = pd.to_numeric(issues_df.get("Ticket_Timespan_Days"), errors="coerce") if not issues_df.empty else pd.Series(dtype="float64")
    timespan_series = timespan_series.dropna()
    return {
        "team_count": int(coverage_df["Team"].nunique()) if not coverage_df.empty else 0,
        "total_defects": defects,
        "history_ok": history_ok,
        "history_bad": history_bad,
        "history_success_rate": round((history_ok / (history_ok + history_bad) * 100), 1) if (history_ok + history_bad) > 0 else 0.0,
        "transition_samples": samples,
        "unique_transitions": unique_transitions,
        "unique_tickets": unique_tickets,
        "changed_by_count": int(issues_df["Changed_By"].nunique()) if not issues_df.empty else 0,
        "timespan_max": int(math.ceil(float(timespan_series.max()))) if not timespan_series.empty else 1,
    }


def build_insights(meta_df: pd.DataFrame, issues_df: pd.DataFrame, transition_df: pd.DataFrame) -> list[str]:
    insights: list[str] = []

    if not meta_df.empty:
        top_defect_row = meta_df.sort_values("Defects", ascending=False).iloc[0]
        insights.append(
            f"Defect volume is led by {top_defect_row['Team']} with {int(top_defect_row['Defects']):,} scoped tickets."
        )
        risk_row = meta_df.sort_values("History_Missing_or_Error", ascending=False).iloc[0]
        if int(risk_row["History_Missing_or_Error"]) > 0:
            insights.append(
                f"History completeness risk is highest for {risk_row['Team']} with {int(risk_row['History_Missing_or_Error']):,} missing or failed history fetches."
            )

    if not issues_df.empty:
        team_ticket_days = (
            issues_df.groupby(["Team", "Ticket_ID"], dropna=False)["Duration_Days"]
            .sum()
            .reset_index()
            .groupby("Team", dropna=False)["Duration_Days"]
            .mean()
            .sort_values(ascending=False)
        )
        if not team_ticket_days.empty:
            slow_team = team_ticket_days.index[0]
            slow_value = float(team_ticket_days.iloc[0])
            insights.append(
                f"Highest average processing time is on {slow_team} at {slow_value:.2f} days per ticket."
            )

    if not transition_df.empty:
        slow_transition = transition_df.sort_values("Avg_Days", ascending=False).iloc[0]
        high_volume = transition_df.sort_values("Count", ascending=False).iloc[0]
        insights.append(
            f"Slowest transition is {slow_transition['Phase_Transition']} ({slow_transition['Group']}) at {float(slow_transition['Avg_Days']):.2f} average days."
        )
        insights.append(
            f"Highest-volume transition is {high_volume['Phase_Transition']} with {int(high_volume['Count']):,} samples."
        )

    return insights[:4]


def build_payload(
  meta_df: pd.DataFrame,
  coverage_df: pd.DataFrame,
  issues_df: pd.DataFrame,
  overview: dict,
  insights: list[str],
  generated_from: dict,
) -> dict:
    groups = sorted({str(x) for x in issues_df.get("Group", pd.Series(dtype="object")).dropna().tolist()})
    changed_by = sorted({str(x) for x in issues_df.get("Changed_By", pd.Series(dtype="object")).dropna().tolist() if str(x).strip()})
    fif_values = sorted({str(x) for x in issues_df.get("FiF", pd.Series(dtype="object")).dropna().tolist() if str(x).strip() and str(x) != "(All)"})
    years = sorted({str(x) for x in coverage_df.get("Year", pd.Series(dtype="object")).dropna().tolist()})

    meta_columns = ["Team", "Defects", "History_OK", "History_Missing_or_Error"]
    coverage_columns = ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"]
    ticket_columns = ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"]
    issue_columns = [
      "Year",
      "Team",
      "Ticket_ID",
      "Phase_Transition",
      "Group",
      "Duration_Hours",
      "Changed_By",
      "FiF",
      "Ticket_Timespan_Days",
    ]
    tickets_df = pd.DataFrame(columns=ticket_columns)
    if not issues_df.empty:
      tickets_df = (
        issues_df[ticket_columns]
        .drop_duplicates(["Ticket_ID"])
        .sort_values(["Ticket_ID"])
        .reset_index(drop=True)
      )

    payload = {
        "generated_from": generated_from,
        "overview": overview,
        "insights": insights,
        "options": {
            "teams": meta_df["Team"].dropna().astype(str).tolist() if not meta_df.empty else [],
            "years": years,
            "groups": groups,
            "changedBy": changed_by,
            "fif": fif_values,
            "timespanMax": overview["timespan_max"],
        },
        "meta": sanitize_dataset(meta_df, meta_columns),
        "coverage": sanitize_dataset(coverage_df, coverage_columns),
        "tickets": sanitize_dataset(tickets_df, ticket_columns),
        "issues": sanitize_dataset(issues_df, issue_columns),
    }
    return payload


def _dataset_to_rows(dataset: dict, columns: list[str]) -> list[dict[str, Any]]:
    dataset_columns = dataset.get("columns") or []
    dataset_rows = dataset.get("rows") or []
    column_indexes = {column: dataset_columns.index(column) for column in columns if column in dataset_columns}

    rows: list[dict[str, Any]] = []
    for row in dataset_rows:
        rows.append({column: row[index] for column, index in column_indexes.items()})
    return rows


def _rows_to_dataset(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, Any]:
    return {"columns": columns, "rows": [[row.get(column) for column in columns] for row in rows]}


def _filter_issue_rows(
    issue_rows: list[dict[str, Any]],
    *,
    teams: tuple[str, ...],
    years: tuple[str, ...],
    groups: tuple[str, ...],
    changed_by: tuple[str, ...],
    fif: tuple[str, ...],
    timespan_min: float,
    timespan_max: float | None,
) -> list[dict[str, Any]]:
    filtered = [row for row in issue_rows if not teams or str(row.get("Team") or "") in teams]
    if years:
        filtered = [row for row in filtered if str(row.get("Year") or "") in years]
    if groups:
        filtered = [row for row in filtered if str(row.get("Group") or "") in groups]
    if changed_by:
        filtered = [row for row in filtered if str(row.get("Changed_By") or "") in changed_by]
    if fif:
        filtered = [row for row in filtered if str(row.get("FiF") or "") in fif]

    filtered_rows: list[dict[str, Any]] = []
    for row in filtered:
        raw_timespan = row.get("Ticket_Timespan_Days")
        try:
            if raw_timespan in (None, ""):
                raise ValueError()
            timespan_days = float(raw_timespan)
        except (TypeError, ValueError):
            timespan_days = None
        if timespan_days is None and (timespan_min > 0 or timespan_max is not None):
            continue
        if timespan_days is None:
            filtered_rows.append(row)
            continue
        if timespan_days < timespan_min:
            continue
        if timespan_max is not None and timespan_days > timespan_max:
            continue
        filtered_rows.append(row)
    return filtered_rows


def _derive_coverage_rows(issue_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], set[str]] = {}
    for row in issue_rows:
        team = str(row.get("Team") or "")
        year = str(row.get("Year") or "")
        ticket_id = str(row.get("Ticket_ID") or "")
        if not team or not ticket_id:
            continue
        grouped.setdefault((team, year), set()).add(ticket_id)

    coverage_rows = []
    for (team, year), ticket_ids in sorted(grouped.items(), key=lambda item: (item[0][1], item[0][0])):
        count = len(ticket_ids)
        coverage_rows.append(
        {
          "Team": team,
          "Year": year,
          "Defects": count,
          "History_OK": count,
          "History_Missing_or_Error": 0,
        }
        )
    return coverage_rows


def _derive_meta_rows(coverage_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, int]] = {}
    for row in coverage_rows:
        team = str(row.get("Team") or "")
        if not team:
            continue
        team_totals = grouped.setdefault(team, {"Defects": 0, "History_OK": 0, "History_Missing_or_Error": 0})
        team_totals["Defects"] += int(row.get("Defects") or 0)
        team_totals["History_OK"] += int(row.get("History_OK") or 0)
        team_totals["History_Missing_or_Error"] += int(row.get("History_Missing_or_Error") or 0)

    return [
      {
        "Team": team,
        "Defects": totals["Defects"],
        "History_OK": totals["History_OK"],
        "History_Missing_or_Error": totals["History_Missing_or_Error"],
      }
      for team, totals in sorted(grouped.items())
    ]


def filter_dashboard_payload(
    payload: dict,
    *,
    teams: tuple[str, ...] = (),
    years: tuple[str, ...] = (),
    groups: tuple[str, ...] = (),
    changed_by: tuple[str, ...] = (),
    fif: tuple[str, ...] = (),
    timespan_min: float = 0.0,
    timespan_max: float | None = None,
    min_transition_count: int = 200,
) -> dict:
    issue_columns = [
      "Year",
      "Team",
      "Ticket_ID",
      "Phase_Transition",
      "Group",
      "Duration_Hours",
      "Changed_By",
      "FiF",
      "Ticket_Timespan_Days",
    ]
    meta_columns = ["Team", "Defects", "History_OK", "History_Missing_or_Error"]
    coverage_columns = ["Team", "Year", "Defects", "History_OK", "History_Missing_or_Error"]
    ticket_columns = ["Ticket_ID", "Ticket_URL", "Ticket_Name", "Tester"]

    payload_copy = deepcopy(payload)
    issue_rows = _dataset_to_rows(payload_copy.get("issues", {}), issue_columns)
    filtered_issue_rows = _filter_issue_rows(
      issue_rows,
      teams=teams,
      years=years,
      groups=groups,
      changed_by=changed_by,
      fif=fif,
      timespan_min=timespan_min,
      timespan_max=timespan_max,
    )

    ticket_lookup = {
      str(row.get("Ticket_ID") or ""): row
      for row in _dataset_to_rows(payload_copy.get("tickets", {}), ticket_columns)
    }
    enriched_issue_rows: list[dict[str, Any]] = []
    for row in filtered_issue_rows:
      ticket_id = str(row.get("Ticket_ID") or "")
      ticket_row = ticket_lookup.get(ticket_id, {})
      enriched_row = dict(row)
      enriched_row["Ticket_URL"] = ticket_row.get("Ticket_URL", "")
      enriched_row["Ticket_Name"] = ticket_row.get("Ticket_Name", ticket_id)
      enriched_row["Tester"] = ticket_row.get("Tester", "")
      try:
        enriched_row["Duration_Days"] = round(float(enriched_row.get("Duration_Hours") or 0) / 24, 2)
      except (TypeError, ValueError):
        enriched_row["Duration_Days"] = 0.0
      enriched_issue_rows.append(enriched_row)
    filtered_issue_rows = enriched_issue_rows

    base_coverage_rows = _dataset_to_rows(payload_copy.get("coverage", {}), coverage_columns)
    coverage_rows = [
      row
      for row in base_coverage_rows
      if (not teams or str(row.get("Team") or "") in teams)
      and (not years or str(row.get("Year") or "") in years)
    ]
    meta_rows = _derive_meta_rows(coverage_rows)

    filtered_ticket_rows = []
    seen_ticket_ids: set[str] = set()
    for row in filtered_issue_rows:
      ticket_id = str(row.get("Ticket_ID") or "")
      if not ticket_id or ticket_id in seen_ticket_ids:
        continue
      seen_ticket_ids.add(ticket_id)
      filtered_ticket_rows.append(ticket_lookup.get(ticket_id, {"Ticket_ID": ticket_id, "Ticket_URL": "", "Ticket_Name": ticket_id, "Tester": ""}))

    meta_df = pd.DataFrame(meta_rows, columns=meta_columns)
    coverage_df = pd.DataFrame(coverage_rows, columns=coverage_columns)
    issues_df = pd.DataFrame(filtered_issue_rows)
    detail_df = build_detail_from_issues(issues_df)
    _, summary_df = qgate.build_summary_frames(detail_df.copy(), min_transition_count)
    filtered_detail_df = detail_df[detail_df["Count"] >= int(min_transition_count)].copy() if not detail_df.empty else detail_df
    transition_df = qgate.aggregate_transition_summary(filtered_detail_df)
    overview = build_overview(coverage_df, issues_df, summary_df, transition_df)
    insights = build_insights(meta_df, issues_df, transition_df)

    filtered_payload = build_payload(
      meta_df=meta_df,
      coverage_df=coverage_df,
      issues_df=issues_df,
      overview=overview,
      insights=insights,
      generated_from=payload_copy.get("generated_from", {}),
    )
    filtered_payload["tickets"] = _rows_to_dataset(filtered_ticket_rows, ticket_columns)
    filtered_payload["issues"] = _rows_to_dataset(filtered_issue_rows, issue_columns)
    filtered_payload["coverage"] = _rows_to_dataset(coverage_rows, coverage_columns)
    filtered_payload["meta"] = _rows_to_dataset(meta_rows, meta_columns)
    filtered_payload["options"] = deepcopy(payload_copy.get("options", {}))
    return filtered_payload


def build_dashboard_payload(
    *,
    defect_dir: str,
    history_dir: str,
    teams: list[str],
    min_transition_count: int,
    analysis_workers: int,
    cache_dir: str | None,
    use_cache: bool,
    show_progress: bool,
) -> dict:
    scope_df = pd.DataFrame()
    summary_db_path = os.environ.get("QGATE_DB_PATH")
    if summary_db_path:
      try:
        scope_df, issues_df = load_summary_data(db_path=summary_db_path, teams=teams)
      except ValueError as exc:
        raise QGateDashboardDataError(str(exc)) from exc

      if scope_df.empty or issues_df.empty:
        raise QGateDashboardDataError("QGate summary data has not been built for the selected teams.")

      coverage_df = build_coverage_from_scope(scope_df)
      meta_df = build_meta_from_coverage(coverage_df)
    else:
      meta_df, _stats_df, issues_df = qgate.compute_all_teams_data(
        defect_dir=defect_dir,
        history_dir=history_dir,
        teams=teams,
        show_progress=show_progress,
        analysis_workers=analysis_workers,
        cache_dir=cache_dir,
        use_cache=use_cache,
      )

      if issues_df.empty:
        raise QGateDashboardDataError("No QGate issue rows were produced. Check defect/history inputs.")

      year_lookup, coverage_df = build_year_lookup_and_coverage(defect_dir, teams, issues_df)
      issues_df = issues_df.copy()
      issues_df["Year"] = [
        year_lookup.get((str(team), str(ticket_id)), "")
        for team, ticket_id in zip(issues_df["Team"].tolist(), issues_df["Ticket_ID"].tolist())
      ]

    detail_df = build_detail_from_issues(issues_df)
    _, summary_df = qgate.build_summary_frames(detail_df.copy(), min_transition_count)
    filtered_detail_df = detail_df[detail_df["Count"] >= int(min_transition_count)].copy() if not detail_df.empty else detail_df
    transition_df = qgate.aggregate_transition_summary(filtered_detail_df)

    overview = build_overview(coverage_df, issues_df, summary_df, transition_df)
    insights = build_insights(meta_df, issues_df, transition_df)
    return build_payload(
        meta_df=meta_df,
        coverage_df=coverage_df,
        issues_df=issues_df,
        overview=overview,
        insights=insights,
        generated_from={
            "defect_dir": defect_dir,
            "history_dir": history_dir,
            "teams": teams,
            "min_transition_count": min_transition_count,
            "analysis_workers": analysis_workers,
            "cache_dir": cache_dir,
            "use_cache": use_cache,
            "show_progress": show_progress,
        },
    )


def render_html(payload: dict) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>QGate KPI Dashboard</title>
  <style>
    *{box-sizing:border-box}
    :root{
      --bg:#f3f5f8;
      --panel:#ffffff;
      --line:#e5e7eb;
      --ink:#1f2937;
      --muted:#6b7280;
      --brand:#0f2e5f;
      --brand-2:#1d4ed8;
      --soft:#eef4ff;
      --good:#15803d;
      --warn:#ca8a04;
      --bad:#b91c1c;
      --qgate:#16a34a;
      --integration:#2563eb;
      --coc:#d97706;
      --other:#64748b;
    }
    body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink)}
    .wrap{max-width:1560px;margin:24px auto;padding:0 16px}
    .header{background:linear-gradient(140deg,#0f2e5f 0%,#163b77 55%,#2052a1 100%);color:#fff;border-radius:16px;padding:24px 28px;box-shadow:0 14px 30px rgba(15,46,95,.16)}
    h1{margin:0 0 8px 0;font-size:30px}
    .sub{opacity:.92;font-size:14px}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-top:16px}
    .card{background:rgba(255,255,255,.1);backdrop-filter:blur(4px);border-radius:12px;padding:14px;border:1px solid rgba(255,255,255,.16)}
    .card.light{background:var(--panel);border:1px solid var(--line);backdrop-filter:none}
    .k{font-size:13px;color:rgba(255,255,255,.82)}
    .light .k{color:var(--muted)}
    .v{font-size:28px;font-weight:700;margin-top:6px}
    .light .v{color:#0f172a}
    .chg{font-size:12px;margin-top:6px;color:#dbeafe}
    .section{margin-top:18px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;box-shadow:0 8px 20px rgba(15,23,42,.04)}
    h2{margin:0 0 10px 0;font-size:20px;color:var(--brand)}
    h3{margin:10px 0;font-size:16px;color:var(--brand)}
    .note{font-size:13px;color:#4b5563;margin-top:8px}
    .insight{background:#fef9c3;border-left:4px solid #ca8a04;padding:10px 12px;border-radius:8px;margin-top:10px}
    .filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;align-items:start}
    .filter{display:flex;flex-direction:column;gap:6px}
    .filter label{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
    .filter select,.filter input{width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:10px;background:#fff;color:var(--ink)}
    .filter-card{border:1px solid var(--line);border-radius:12px;background:#fcfcfd;padding:10px 10px 8px}
    .chip-toolbar{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px}
    .chip-actions{display:flex;gap:6px;flex-wrap:wrap}
    .chip-action{border:1px solid #cbd5e1;background:#fff;color:var(--muted);border-radius:999px;padding:4px 8px;font-size:11px;cursor:pointer}
    .chip-action:hover{border-color:#93c5fd;color:#1d4ed8;background:#eff6ff}
    .chip-set{display:flex;flex-wrap:wrap;gap:8px;max-height:128px;overflow:auto;padding-right:2px}
    .chip{border:1px solid #cbd5e1;background:#fff;color:#334155;border-radius:999px;padding:7px 10px;font-size:12px;line-height:1;cursor:pointer;transition:all .15s ease}
    .chip:hover{border-color:#93c5fd;color:#1d4ed8;background:#eff6ff}
    .chip.active{background:#dbeafe;border-color:#60a5fa;color:#1d4ed8;font-weight:700}
    .chip.single-line{white-space:nowrap}
    .split{display:grid;grid-template-columns:1.05fr .95fr;gap:14px}
    .chart-box{border:1px solid var(--line);border-radius:12px;padding:12px;background:#fcfcfd}
    .chart-title{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px}
    .chart-title strong{font-size:14px;color:var(--brand)}
    .chart-title span{font-size:12px;color:var(--muted)}
    .stack-wrap{display:grid;gap:10px}
    .stack-row{display:grid;grid-template-columns:170px 1fr 120px;gap:10px;align-items:center;font-size:12px}
    .stack-row .label{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .stack{height:18px;border-radius:999px;overflow:hidden;display:flex;background:#e5e7eb}
    .seg{height:100%;cursor:pointer;position:relative;min-width:0}
    .seg:hover{filter:brightness(.94)}
    .qgate{background:var(--qgate)}
    .integration{background:var(--integration)}
    .coc{background:var(--coc)}
    .other{background:var(--other)}
    .legend{display:flex;gap:14px;font-size:12px;color:#475569;flex-wrap:wrap;margin:4px 0 10px}
    .dot{display:inline-block;width:10px;height:10px;border-radius:999px;margin-right:5px;vertical-align:middle}
    table{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px}
    th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
    th{background:#eef2ff;font-weight:700}
    td.num,th.num{text-align:right}
    tbody tr:hover{background:#f8fafc}
    .scroll{max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:12px}
    .bar-cell{display:grid;grid-template-columns:74px 1fr 76px;gap:8px;align-items:center}
    .bar-bg{height:14px;background:#e5e7eb;border-radius:999px;overflow:hidden}
    .bar-fill{height:100%;background:linear-gradient(90deg,#60a5fa,#2563eb)}
    .bar-fill.warn{background:linear-gradient(90deg,#f59e0b,#d97706)}
    .bar-fill.good{background:linear-gradient(90deg,#4ade80,#16a34a)}
    .pill{display:inline-flex;align-items:center;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:700;background:#eff6ff;color:#1d4ed8}
    .selection{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
    .empty{padding:16px;border:1px dashed #cbd5e1;border-radius:10px;color:var(--muted);text-align:center;background:#f8fafc}
    .clickable{cursor:pointer}
    .selected{background:#eff6ff}
    .clickable:hover{background:#eff6ff}
    .tiny{font-size:11px;color:var(--muted)}
    .footer{font-size:12px;color:var(--muted);margin:18px 0 6px}
    a{color:#1d4ed8;text-decoration:none}
    a:hover{text-decoration:underline}
    @media (max-width:1100px){.split{grid-template-columns:1fr}.stack-row{grid-template-columns:1fr}.bar-cell{grid-template-columns:62px 1fr 70px}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="header">
      <h1>QGate KPI Dashboard</h1>
      <div class="sub" id="generated-from"></div>
      <div class="grid" id="hero-cards"></div>
    </div>

    <div class="section">
      <h2>Filters</h2>
      <div class="filters">
        <div class="filter">
          <label for="years-select">Year</label>
          <div class="filter-card">
            <div class="chip-toolbar">
              <span class="tiny">Click to toggle</span>
              <div class="chip-actions">
                <button type="button" class="chip-action" id="years-all-btn">All</button>
              </div>
            </div>
            <div id="years-select"></div>
          </div>
        </div>
        <div class="filter">
          <label for="teams-select">Teams</label>
          <div class="filter-card">
            <div class="chip-toolbar">
              <span class="tiny">Click to toggle</span>
              <div class="chip-actions">
                <button type="button" class="chip-action" id="teams-all-btn">All</button>
                <button type="button" class="chip-action" id="teams-none-btn">None</button>
              </div>
            </div>
            <div id="teams-select"></div>
          </div>
        </div>
        <div class="filter">
          <label for="groups-select">Groups</label>
          <div class="filter-card">
            <div class="chip-toolbar">
              <span class="tiny">Click to toggle</span>
              <div class="chip-actions">
                <button type="button" class="chip-action" id="groups-all-btn">All</button>
              </div>
            </div>
            <div id="groups-select"></div>
          </div>
        </div>
        <div class="filter">
          <label for="changed-by-select">Changed By</label>
          <select id="changed-by-select"></select>
        </div>
        <div class="filter">
          <label for="fif-select">FiF</label>
          <select id="fif-select"></select>
        </div>
        <div class="filter">
          <label for="timespan-min">Timespan Min (days)</label>
          <input id="timespan-min" type="number" min="0" step="1" />
        </div>
        <div class="filter">
          <label for="timespan-max">Timespan Max (days)</label>
          <input id="timespan-max" type="number" min="0" step="1" />
        </div>
        <div class="filter">
          <label for="min-count-input">Min Transition Count</label>
          <input id="min-count-input" type="number" min="1" step="1" />
        </div>
        <div class="filter">
          <label>&nbsp;</label>
          <input id="reset-btn" type="button" value="Reset Filters" />
        </div>
      </div>
      <div class="selection" id="selection-summary"></div>
    </div>

    <div class="section">
      <h2>A. Team Coverage</h2>
      <div class="chart-box">
        <div class="chart-title"><strong>Coverage Bars</strong><span>In-view ticket coverage within scoped defects</span></div>
        <div class="stack-wrap" id="coverage-bars"></div>
      </div>
    </div>

    <div class="section">
      <h2>B. Transition Analysis</h2>
      <div class="chart-box">
        <div class="chart-title"><strong>Grouped Stacked View</strong><span>Average days by transition inside Q-Gate / Integration / CoC</span></div>
        <div id="grouped-stacked"></div>
      </div>
    </div>

    <div class="section">
      <h2>C. Phase Efficiency Summary</h2>
      <div class="legend">
        <span><span class="dot" style="background:var(--qgate)"></span>Q-Gate</span>
        <span><span class="dot" style="background:var(--integration)"></span>Integration</span>
        <span><span class="dot" style="background:var(--coc)"></span>CoC</span>
        <span><span class="dot" style="background:var(--other)"></span>Other</span>
      </div>
      <div class="split">
        <div class="chart-box">
          <div class="chart-title"><strong>Team × Group Efficiency</strong><span>Click a segment to inspect team/group tickets below</span></div>
          <div class="stack-wrap" id="summary-bars"></div>
        </div>
        <div class="chart-box">
          <div class="chart-title"><strong>Summary Table</strong><span>Ticket count and summed transition average days by team/group</span></div>
          <div class="scroll"><table id="summary-table"></table></div>
        </div>
      </div>
      <div class="note">Each stack segment length is the sum of average days across the included phase transitions for that Team + Group. Every phase inside the group contributes its own average duration once, and those phase averages are added together.</div>
      <div class="chart-box">
        <div class="chart-title"><strong>Ticket Drilldown</strong><span id="team-group-title">Click a summary segment or row</span></div>
        <div class="scroll"><table id="team-group-table"></table></div>
      </div>
    </div>

    <div class="footer" id="footer-text"></div>
  </div>

  <script>
    const QGATE_PAYLOAD = __PAYLOAD_JSON__;

    function decodeDataset(dataset) {
      if (!dataset || !Array.isArray(dataset.columns) || !Array.isArray(dataset.rows)) {
        return Array.isArray(dataset) ? dataset : [];
      }
      return dataset.rows.map((row) => Object.fromEntries(dataset.columns.map((column, index) => [column, row[index]])));
    }

    const META_ROWS = decodeDataset(QGATE_PAYLOAD.meta);
    const COVERAGE_ROWS = decodeDataset(QGATE_PAYLOAD.coverage);
    const TICKET_ROWS = decodeDataset(QGATE_PAYLOAD.tickets);
    const ISSUE_ROWS = decodeDataset(QGATE_PAYLOAD.issues);
    const TICKET_MAP = new Map(TICKET_ROWS.map((row) => [String(row.Ticket_ID || ''), row]));
    const DEFAULT_YEARS = QGATE_PAYLOAD.options.years.includes('2025') ? ['2025'] : [...QGATE_PAYLOAD.options.years];

    const state = {
      years: [...DEFAULT_YEARS],
      teams: [...QGATE_PAYLOAD.options.teams],
      groups: [...QGATE_PAYLOAD.options.groups],
      changedBy: 'all',
      fif: 'all',
      timespanMin: 0,
      timespanMax: Math.min(120, QGATE_PAYLOAD.options.timespanMax || 120),
      minCount: QGATE_PAYLOAD.generated_from.min_transition_count || 200,
      selectedSummary: null,
    };

    const groupClassMap = {
      'Q-Gate': 'qgate',
      'Integration': 'integration',
      'CoC': 'coc',
      'Other': 'other',
    };

    function fmtNumber(value, digits = 0) {
      const numeric = Number(value || 0);
      return numeric.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
    }

    function fmtMaybe(value, digits = 2) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) {
        return '-';
      }
      return fmtNumber(Number(value), digits);
    }

    function escapeHtml(value) {
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function renderTicketAnchor(ticketId, ticketUrl) {
      if (!ticketId) return '-';
      if (!ticketUrl) return escapeHtml(ticketId);
      return `<a href="${escapeHtml(ticketUrl)}" target="_blank" rel="noreferrer">${escapeHtml(ticketId)}</a>`;
    }

    function renderChipSet(containerId, values, selectedValues) {
      const container = document.getElementById(containerId);
      container.className = 'chip-set';
      container.innerHTML = values.map((value) => {
        const selected = selectedValues.includes(value);
        return `<button type="button" class="chip single-line ${selected ? 'active' : ''}" data-value="${escapeHtml(value)}">${escapeHtml(value)}</button>`;
      }).join('');
    }

    function median(values) {
      if (!values.length) return 0;
      const ordered = [...values].sort((a, b) => a - b);
      const mid = Math.floor(ordered.length / 2);
      if (ordered.length % 2 === 1) return ordered[mid];
      return (ordered[mid - 1] + ordered[mid]) / 2;
    }

    function computeOverview(coverageRows, issues, summary) {
      const ticketIds = new Set(issues.map((row) => row.Ticket_ID).filter(Boolean));
      const transitions = new Set(issues.map((row) => row.Phase_Transition).filter(Boolean));
      const changedBy = new Set(issues.map((row) => row.Changed_By).filter(Boolean));
      const transitionSamples = issues.length;
      const totalDefects = coverageRows.reduce((acc, row) => acc + Number(row.Defects || 0), 0);
      const historyOk = coverageRows.reduce((acc, row) => acc + Number(row.History_OK || 0), 0);
      const historyBad = coverageRows.reduce((acc, row) => acc + Number(row.History_Missing_or_Error || 0), 0);
      return {
        teamCount: new Set(coverageRows.map((row) => row.Team).filter(Boolean)).size || new Set(issues.map((row) => row.Team).filter(Boolean)).size || state.teams.length,
        totalDefects,
        historyOk,
        historyBad,
        historySuccessRate: (historyOk + historyBad) > 0 ? (historyOk / (historyOk + historyBad)) * 100 : 0,
        ticketCount: ticketIds.size,
        transitionCount: transitions.size,
        changedByCount: changedBy.size,
        transitionSamples,
      };
    }

    function filterIssues() {
      return ISSUE_ROWS.filter((row) => {
        if (state.years.length && !state.years.includes(String(row.Year || ''))) return false;
        if (state.teams.length && !state.teams.includes(row.Team)) return false;
        if (state.groups.length && !state.groups.includes(row.Group)) return false;
        if (state.changedBy !== 'all' && row.Changed_By !== state.changedBy) return false;
        if (state.fif !== 'all' && row.FiF !== state.fif) return false;
        const span = Number(row.Ticket_Timespan_Days);
        if (!Number.isNaN(span) && (span < state.timespanMin || span > state.timespanMax)) return false;
        if (Number.isNaN(span) && (state.timespanMin > 0 || state.timespanMax < (QGATE_PAYLOAD.options.timespanMax || 1))) return false;
        return true;
      });
    }

    function buildSummary(issues) {
      const transitionBucket = new Map();
      issues.forEach((row) => {
        const key = [row.Team, row.Group, row.Phase_Transition].join('||');
        if (!transitionBucket.has(key)) {
          transitionBucket.set(key, {
            Team: row.Team,
            Group: row.Group,
            Phase_Transition: row.Phase_Transition,
            Hours_Total: 0,
            Count: 0,
          });
        }
        const item = transitionBucket.get(key);
        item.Hours_Total += Number(row.Duration_Hours || 0);
        item.Count += 1;
      });

      const bucket = new Map();
      Array.from(transitionBucket.values())
        .filter((row) => Number(row.Count || 0) >= Number(state.minCount || 1))
        .forEach((row) => {
          const key = [row.Team, row.Group].join('||');
          if (!bucket.has(key)) {
            bucket.set(key, {
              Team: row.Team,
              Group: row.Group,
              Ticket_IDs: new Set(),
              Transitions_Total: 0,
              Phase_Days_Sum: 0,
            });
          }
          const item = bucket.get(key);
          item.Transitions_Total += 1;
          item.Phase_Days_Sum += (Number(row.Hours_Total || 0) / Math.max(Number(row.Count || 0), 1)) / 24;
        });

      issues.forEach((row) => {
        const key = [row.Team, row.Group].join('||');
        if (!bucket.has(key)) return;
        const item = bucket.get(key);
        if (row.Ticket_ID) item.Ticket_IDs.add(row.Ticket_ID);
      });

      return Array.from(bucket.values())
        .map((row) => ({
          Team: row.Team,
          Group: row.Group,
          Ticket_Count: row.Ticket_IDs.size,
          Transitions_Total: row.Transitions_Total,
          Phase_Days_Sum: Number(row.Phase_Days_Sum.toFixed(3)),
        }))
        .sort((a, b) => a.Team.localeCompare(b.Team) || a.Group.localeCompare(b.Group));
    }

    function buildTransitionSummary(issues) {
      const bucket = new Map();
      issues.forEach((row) => {
        const key = [row.Phase_Transition, row.Group].join('||');
        if (!bucket.has(key)) {
          bucket.set(key, {
            Phase_Transition: row.Phase_Transition,
            Group: row.Group,
            Count: 0,
            Hours_Total: 0,
          });
        }
        const item = bucket.get(key);
        item.Count += 1;
        item.Hours_Total += Number(row.Duration_Hours || 0);
      });

      return Array.from(bucket.values())
        .filter((row) => Number(row.Count || 0) >= Number(state.minCount || 1))
        .map((row) => ({
          Phase_Transition: row.Phase_Transition,
          Group: row.Group,
          Count: row.Count,
          Avg_Days: Number(((row.Hours_Total / Math.max(row.Count, 1)) / 24).toFixed(3)),
        }))
        .sort((a, b) => b.Avg_Days - a.Avg_Days || b.Count - a.Count);
    }

    function buildCoverageRows(filteredIssues) {
      const selectedYears = new Set(state.years);
      const selectedTeams = new Set(state.teams);
      const aggregated = new Map();

      (COVERAGE_ROWS.length ? COVERAGE_ROWS : META_ROWS).forEach((row) => {
        if (selectedYears.size && !selectedYears.has(String(row.Year || ''))) return;
        if (selectedTeams.size && !selectedTeams.has(row.Team)) return;
        const key = String(row.Team || '');
        if (!aggregated.has(key)) {
          aggregated.set(key, {
            Team: row.Team,
            Defects: 0,
            History_OK: 0,
            History_Missing_or_Error: 0,
          });
        }
        const item = aggregated.get(key);
        item.Defects += Number(row.Defects || 0);
        item.History_OK += Number(row.History_OK || 0);
        item.History_Missing_or_Error += Number(row.History_Missing_or_Error || 0);
      });

      const ticketCounts = new Map();
      filteredIssues.forEach((row) => {
        const team = String(row.Team || '');
        const ticketId = String(row.Ticket_ID || '');
        if (!team || !ticketId) return;
        if (!ticketCounts.has(team)) ticketCounts.set(team, new Set());
        ticketCounts.get(team).add(ticketId);
      });

      return Array.from(aggregated.values())
        .map((row) => {
          const total = Number(row.Defects || 0);
          const inView = ticketCounts.get(String(row.Team || ''))?.size || 0;
          return {
            ...row,
              Scoped_Defects: total,
            Tickets_In_View: inView,
            Tickets_Out_Of_View: Math.max(total - inView, 0),
            View_Rate: total > 0 ? Number(((inView / total) * 100).toFixed(1)) : 0,
          };
        })
          .sort((a, b) => Number(b.Tickets_In_View || 0) - Number(a.Tickets_In_View || 0) || Number(b.Defects || 0) - Number(a.Defects || 0));
    }

    function renderHero(overview) {
      const hero = document.getElementById('hero-cards');
      const cards = [
        { label: 'Teams', value: fmtNumber(overview.teamCount), meta: `${state.years.join(', ') || 'all years'} selected` },
        { label: 'Scoped Defects', value: fmtNumber(overview.totalDefects), meta: `Across ${fmtNumber(overview.teamCount)} teams` },
        { label: 'Tickets in View', value: fmtNumber(overview.ticketCount), meta: `${fmtNumber(overview.changedByCount)} changers represented` },
      ];
      hero.innerHTML = cards.map((card) => `
        <div class="card">
          <div class="k">${escapeHtml(card.label)}</div>
          <div class="v">${escapeHtml(card.value)}</div>
          <div class="chg">${escapeHtml(card.meta)}</div>
        </div>`).join('');
    }

    function renderSelections() {
      const box = document.getElementById('selection-summary');
      const pills = [
        `Years: ${state.years.length ? state.years.join(', ') : 'none'}`,
        `Teams: ${state.teams.length ? state.teams.join(', ') : 'none'}`,
        `Groups: ${state.groups.length ? state.groups.join(', ') : 'none'}`,
        `Changed By: ${state.changedBy}`,
        `FiF: ${state.fif}`,
        `Timespan: ${state.timespanMin}-${state.timespanMax} days`,
        `Min Count: ${state.minCount}`,
      ];
      box.innerHTML = pills.map((text) => `<span class="pill">${escapeHtml(text)}</span>`).join('');
    }

    function renderCoverage(coverageRows) {
      const maxInView = Math.max(1, ...coverageRows.map((row) => Number(row.Tickets_In_View || 0)));
      const bars = document.getElementById('coverage-bars');
      bars.innerHTML = coverageRows.map((row) => {
        const width = Number(row.Tickets_In_View || 0) / maxInView * 100;
        return `
          <div class="stack-row">
            <div class="label">${escapeHtml(row.Team)}</div>
            <div class="bar-cell">
              <div class="tiny">${fmtMaybe(row.View_Rate, 1)}%</div>
              <div class="bar-bg"><div class="bar-fill good" style="width:${Math.max(width, 2)}%"></div></div>
              <div class="tiny">${fmtNumber(row.Tickets_In_View)}</div>
            </div>
            <div class="tiny">In View ${fmtNumber(row.Tickets_In_View)} / Scoped ${fmtNumber(row.Scoped_Defects)} / Out ${fmtNumber(row.Tickets_Out_Of_View)}</div>
          </div>`;
      }).join('') || '<div class="empty">No coverage bars available.</div>';
    }

    function renderSummary(summaryRows) {
      const byTeam = new Map();
      summaryRows.forEach((row) => {
        if (!byTeam.has(row.Team)) byTeam.set(row.Team, []);
        byTeam.get(row.Team).push(row);
      });

      const orderedTeams = Array.from(byTeam.entries())
        .map(([team, rows]) => ({ team, rows, total: rows.reduce((acc, row) => acc + Number(row.Phase_Days_Sum || 0), 0) }))
        .sort((a, b) => b.total - a.total);

      const maxTotal = Math.max(1, ...orderedTeams.map((item) => item.total));
      const bars = document.getElementById('summary-bars');
      bars.innerHTML = orderedTeams.map((item) => {
        const totalWidth = item.total / maxTotal * 100;
        const segmentHtml = item.rows
          .sort((a, b) => Number(b.Phase_Days_Sum || 0) - Number(a.Phase_Days_Sum || 0))
          .map((row) => {
            const segWidth = item.total > 0 ? (Number(row.Phase_Days_Sum || 0) / item.total) * totalWidth : 0;
            return `<div class="seg ${groupClassMap[row.Group] || 'other'}" style="width:${Math.max(segWidth, Number(row.Phase_Days_Sum || 0) > 0 ? 2 : 0)}%" data-team="${escapeHtml(row.Team)}" data-group="${escapeHtml(row.Group)}" title="${escapeHtml(row.Group)} | Summed Phase Avg ${fmtMaybe(row.Phase_Days_Sum, 2)} d | Tickets ${fmtNumber(row.Ticket_Count)} | Transitions ${fmtNumber(row.Transitions_Total)}"></div>`;
          }).join('');
        return `
          <div class="stack-row">
            <div class="label">${escapeHtml(item.team)}</div>
            <div class="stack">${segmentHtml}</div>
            <div class="tiny">${fmtMaybe(item.total, 2)} d summed phase avg</div>
          </div>`;
      }).join('') || '<div class="empty">No summary rows for the current filter.</div>';

      bars.querySelectorAll('.seg').forEach((node) => {
        node.addEventListener('click', () => {
          state.selectedSummary = { team: node.dataset.team, group: node.dataset.group };
          render();
        });
      });

      const table = document.getElementById('summary-table');
      table.innerHTML = `
        <thead>
          <tr>
            <th>Team</th>
            <th>Group</th>
            <th class="num">Ticket Count</th>
            <th class="num">Summed Phase Avg Days</th>
          </tr>
        </thead>
        <tbody>
          ${summaryRows.map((row) => {
            const selected = state.selectedSummary && state.selectedSummary.team === row.Team && state.selectedSummary.group === row.Group;
            return `<tr class="clickable ${selected ? 'selected' : ''}" data-team="${escapeHtml(row.Team)}" data-group="${escapeHtml(row.Group)}">
              <td>${escapeHtml(row.Team)}</td>
              <td>${escapeHtml(row.Group)}</td>
              <td class="num">${fmtNumber(row.Ticket_Count)}</td>
              <td class="num">${fmtMaybe(row.Phase_Days_Sum, 2)}</td>
            </tr>`;
          }).join('') || '<tr><td colspan="4" class="empty">No summary rows available.</td></tr>'}
        </tbody>`;

      table.querySelectorAll('tbody tr.clickable').forEach((node) => {
        node.addEventListener('click', () => {
          state.selectedSummary = { team: node.dataset.team, group: node.dataset.group };
          render();
        });
      });
    }

    function renderGroupedViews(transitionRows) {
      const groups = ['Q-Gate', 'Integration', 'CoC'];
      const groupedStacked = document.getElementById('grouped-stacked');
      const globalMaxValue = Math.max(1, ...transitionRows.map((row) => Number(row.Avg_Days || 0)));

      groupedStacked.innerHTML = groups.map((group) => {
        const rows = transitionRows.filter((row) => row.Group === group).sort((a, b) => b.Avg_Days - a.Avg_Days || b.Count - a.Count);
        return `
          <div style="margin-bottom:14px">
            <div class="chart-title"><strong>${escapeHtml(group)}</strong><span>${fmtNumber(rows.length)} transitions</span></div>
            ${rows.slice(0, 20).map((row) => `
              <div class="stack-row">
                <div class="label">${escapeHtml(row.Phase_Transition)}</div>
                <div class="bar-cell">
                  <div class="tiny">${fmtMaybe(row.Avg_Days, 2)} d</div>
                  <div class="bar-bg"><div class="bar-fill" style="width:${Math.max((Number(row.Avg_Days || 0) / globalMaxValue) * 100, Number(row.Avg_Days || 0) > 0 ? 2 : 0)}%"></div></div>
                  <div class="tiny">${fmtNumber(row.Count)} samples</div>
                </div>
              </div>`).join('') || '<div class="empty">No transitions in this group.</div>'}
          </div>`;
      }).join('');
    }

    function renderDrilldown(filteredIssues, summaryRows) {
      const teamGroupTitle = document.getElementById('team-group-title');
      const teamGroupTable = document.getElementById('team-group-table');

      let summarySelection = state.selectedSummary;
      if (summarySelection && !summaryRows.some((row) => row.Team === summarySelection.team && row.Group === summarySelection.group)) {
        summarySelection = null;
        state.selectedSummary = null;
      }
      if (!summarySelection && summaryRows.length) {
        summarySelection = { team: summaryRows[0].Team, group: summaryRows[0].Group };
        state.selectedSummary = summarySelection;
      }

      if (!summarySelection) {
        teamGroupTitle.textContent = 'No team/group selection available';
        teamGroupTable.innerHTML = '<tr><td class="empty">No team/group drilldown rows.</td></tr>';
      } else {
        const rows = filteredIssues.filter((row) => row.Team === summarySelection.team && row.Group === summarySelection.group);
        const grouped = new Map();
        rows.forEach((row) => {
          const ticketMeta = TICKET_MAP.get(String(row.Ticket_ID || '')) || {};
          const key = [row.Ticket_ID, row.Team, row.Group, row.FiF].join('||');
          if (!grouped.has(key)) {
            grouped.set(key, {
              Ticket_ID: row.Ticket_ID,
              Ticket_URL: ticketMeta.Ticket_URL || '',
              Ticket_Name: ticketMeta.Ticket_Name || '',
              Tester: ticketMeta.Tester || '',
              Team: row.Team,
              Group: row.Group,
              FiF: row.FiF,
              Duration_Hours: 0,
              Duration_Days: 0,
              Transitions: new Set(),
            });
          }
          const item = grouped.get(key);
          item.Duration_Hours += Number(row.Duration_Hours || 0);
          item.Duration_Days += Number(row.Duration_Hours || 0) / 24;
          item.Transitions.add(row.Phase_Transition);
        });
        const ticketRows = Array.from(grouped.values())
          .map((row) => ({ ...row, Transitions: row.Transitions.size }))
          .sort((a, b) => b.Duration_Days - a.Duration_Days || b.Transitions - a.Transitions);
        teamGroupTitle.textContent = `${summarySelection.team} / ${summarySelection.group} (${fmtNumber(ticketRows.length)} tickets)`;
        teamGroupTable.innerHTML = `
          <thead><tr><th>Ticket</th><th>Name</th><th>Tester</th><th>FiF</th><th class="num">Transitions</th><th class="num">Duration Days</th><th class="num">Duration Hours</th></tr></thead>
          <tbody>
            ${ticketRows.map((row) => `
              <tr>
                <td>${renderTicketAnchor(row.Ticket_ID, row.Ticket_URL)}</td>
                <td>${escapeHtml(row.Ticket_Name)}</td>
                <td>${escapeHtml(row.Tester)}</td>
                <td>${escapeHtml(row.FiF)}</td>
                <td class="num">${fmtNumber(row.Transitions)}</td>
                <td class="num">${fmtMaybe(row.Duration_Days, 2)}</td>
                <td class="num">${fmtMaybe(row.Duration_Hours, 2)}</td>
              </tr>`).join('') || '<tr><td colspan="7" class="empty">No ticket rows for the current team/group.</td></tr>'}
          </tbody>`;
      }
    }

    function renderGeneratedFrom() {
      const source = QGATE_PAYLOAD.generated_from;
      document.getElementById('generated-from').textContent = `defect_dir=${source.defect_dir} | history_dir=${source.history_dir} | teams=${source.teams.join(', ')}`;
      document.getElementById('footer-text').textContent = `Standalone export generated from qgate.py analytics. Output preserves current QGate summary semantics and rebuilds filters client-side from embedded issue records.`;
    }

    function render() {
      renderGeneratedFrom();
      renderSelections();

      const filteredIssues = filterIssues();
      const summary = buildSummary(filteredIssues);
      const transition = buildTransitionSummary(filteredIssues);
      const coverageRows = buildCoverageRows(filteredIssues);
      const overview = computeOverview(coverageRows, filteredIssues, summary);

      renderHero(overview);
      renderCoverage(coverageRows);
      renderSummary(summary);
      renderGroupedViews(transition);
      renderDrilldown(filteredIssues, summary);
    }

    function populateFilters() {
      const yearsSelect = document.getElementById('years-select');
      const teamsSelect = document.getElementById('teams-select');
      const groupsSelect = document.getElementById('groups-select');
      const changedBySelect = document.getElementById('changed-by-select');
      const fifSelect = document.getElementById('fif-select');
      const timespanMin = document.getElementById('timespan-min');
      const timespanMax = document.getElementById('timespan-max');
      const minCountInput = document.getElementById('min-count-input');

      renderChipSet('years-select', QGATE_PAYLOAD.options.years, state.years);
      renderChipSet('teams-select', QGATE_PAYLOAD.options.teams, state.teams);
      renderChipSet('groups-select', QGATE_PAYLOAD.options.groups, state.groups);
      changedBySelect.innerHTML = ['all', ...QGATE_PAYLOAD.options.changedBy].map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
      fifSelect.innerHTML = ['all', ...QGATE_PAYLOAD.options.fif].map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join('');
      timespanMin.value = '0';
      timespanMax.value = String(Math.min(120, QGATE_PAYLOAD.options.timespanMax || 120));
      minCountInput.value = String(state.minCount);

      yearsSelect.querySelectorAll('.chip').forEach((node) => {
        node.addEventListener('click', () => {
          const value = node.dataset.value;
          state.years = state.years.includes(value)
            ? state.years.filter((item) => item !== value)
            : [...state.years, value];
          state.selectedSummary = null;
          populateFilters();
          render();
        });
      });
      teamsSelect.querySelectorAll('.chip').forEach((node) => {
        node.addEventListener('click', () => {
          const value = node.dataset.value;
          state.teams = state.teams.includes(value)
            ? state.teams.filter((item) => item !== value)
            : [...state.teams, value];
          state.selectedSummary = null;
          populateFilters();
          render();
        });
      });
      groupsSelect.querySelectorAll('.chip').forEach((node) => {
        node.addEventListener('click', () => {
          const value = node.dataset.value;
          state.groups = state.groups.includes(value)
            ? state.groups.filter((item) => item !== value)
            : [...state.groups, value];
          state.selectedSummary = null;
          populateFilters();
          render();
        });
      });
      document.getElementById('years-all-btn').onclick = () => {
        state.years = [...QGATE_PAYLOAD.options.years];
        state.selectedSummary = null;
        populateFilters();
        render();
      };
      document.getElementById('teams-all-btn').onclick = () => {
        state.teams = [...QGATE_PAYLOAD.options.teams];
        state.selectedSummary = null;
        populateFilters();
        render();
      };
      document.getElementById('teams-none-btn').onclick = () => {
        state.teams = [];
        state.selectedSummary = null;
        populateFilters();
        render();
      };
      document.getElementById('groups-all-btn').onclick = () => {
        state.groups = [...QGATE_PAYLOAD.options.groups];
        state.selectedSummary = null;
        populateFilters();
        render();
      };
      changedBySelect.onchange = () => {
        state.changedBy = changedBySelect.value;
        render();
      };
      fifSelect.onchange = () => {
        state.fif = fifSelect.value;
        render();
      };
      timespanMin.onchange = () => {
        state.timespanMin = Math.max(0, Number(timespanMin.value || 0));
        if (state.timespanMin > state.timespanMax) state.timespanMin = state.timespanMax;
        timespanMin.value = String(state.timespanMin);
        render();
      };
      timespanMax.onchange = () => {
        state.timespanMax = Math.max(0, Number(timespanMax.value || QGATE_PAYLOAD.options.timespanMax || 1));
        if (state.timespanMax < state.timespanMin) state.timespanMax = state.timespanMin;
        timespanMax.value = String(state.timespanMax);
        render();
      };
      minCountInput.onchange = () => {
        state.minCount = Math.max(1, Number(minCountInput.value || 1));
        minCountInput.value = String(state.minCount);
        render();
      };
      document.getElementById('reset-btn').onclick = () => {
        state.years = [...DEFAULT_YEARS];
        state.teams = [...QGATE_PAYLOAD.options.teams];
        state.groups = [...QGATE_PAYLOAD.options.groups];
        state.changedBy = 'all';
        state.fif = 'all';
        state.timespanMin = 0;
        state.timespanMax = Math.min(120, QGATE_PAYLOAD.options.timespanMax || 120);
        state.minCount = QGATE_PAYLOAD.generated_from.min_transition_count || 200;
        state.selectedSummary = null;
        changedBySelect.value = 'all';
        fifSelect.value = 'all';
        timespanMin.value = '0';
        timespanMax.value = String(state.timespanMax);
        minCountInput.value = String(state.minCount);
        populateFilters();
        render();
      };
    }

    populateFilters();
    render();
  </script>
</body>
</html>
"""
    return template.replace("__PAYLOAD_JSON__", payload_json)


def main(parsed_args: argparse.Namespace | None = None) -> None:
    args = parsed_args or parse_args()
    teams = [team.strip() for team in args.teams.split(",") if team.strip()]
    use_cache = not args.no_cache
    cache_dir = None if args.no_cache else args.cache_dir

    try:
        payload = build_dashboard_payload(
            defect_dir=args.defect_dir,
            history_dir=args.history_dir,
            teams=teams,
            min_transition_count=args.min_transition_count,
            analysis_workers=args.analysis_workers,
            cache_dir=cache_dir,
            use_cache=use_cache,
            show_progress=not args.no_progress,
        )
    except QGateDashboardDataError as exc:
        raise SystemExit(str(exc)) from exc

    overview = payload["overview"]

    html = render_html(payload)
    output_path = Path(args.output)
    if not output_path.is_absolute():
      output_path = REPO_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    print(f"QGate KPI dashboard generated: {output_path}")
    print(f"Teams: {overview['team_count']}, tickets: {overview['unique_tickets']}, transitions: {overview['unique_transitions']}")


if __name__ == "__main__":
    main()
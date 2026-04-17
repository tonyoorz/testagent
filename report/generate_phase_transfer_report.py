import argparse
import html
import os
import re
import sqlite3
import sys
from statistics import median
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import plotly.express as px

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from longrunner_analysis import _default_octane_db_path, _parse_iso_timestamp, _load_history_data, build_phase_segments


REPORT_TITLE = "Phase Transfer Report"
GROUP_ORDER = ["Q-Gate", "Integration", "CoC"]
OCTANE_WORK_ITEM_URL = "https://octane-prod.bmwgroup.net/ui/entity-navigation?p=1002/2001&entityType=work_item&id={ticket_id}"


def parse_ticket_ids(raw_value: str) -> List[str]:
    return [part.strip() for part in re.split(r"[\s,]+", str(raw_value or "")) if part.strip()]


def load_ticket_metadata(ticket_ids: Iterable[str], db_path: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    ticket_ids = [str(ticket_id).strip() for ticket_id in ticket_ids if str(ticket_id).strip()]
    if not ticket_ids:
        return {}

    db_path_value = db_path or _default_octane_db_path()
    if not db_path_value or not os.path.exists(db_path_value):
        return {}

    placeholders = ",".join("?" for _ in ticket_ids)
    sql = (
        "SELECT defect_id, name, last_modified, phase, status_phase "
        f"FROM octane_defects WHERE defect_id IN ({placeholders})"
    )
    lookup: Dict[str, Dict[str, str]] = {}

    conn = sqlite3.connect(db_path_value)
    try:
        for defect_id, name, last_modified, phase, status_phase in conn.execute(sql, ticket_ids).fetchall():
            lookup[str(defect_id)] = {
                "ticket_id": str(defect_id),
                "ticket_name": str(name or f"Ticket {defect_id}"),
                "last_modified": str(last_modified or ""),
                "phase": str(phase or status_phase or ""),
            }
    finally:
        conn.close()

    return lookup


def build_phase_transition_label(segment: Dict[str, Any]) -> str:
    from_phase = str(segment.get("from_phase") or "").strip()
    to_phase = str(segment.get("to_phase") or segment.get("phase") or "").strip()
    return f"{from_phase} → {to_phase}" if from_phase or to_phase else ""


def build_ticket_link_html(ticket_id: Any) -> str:
    normalized_ticket_id = str(ticket_id or "").strip()
    if not normalized_ticket_id:
        return ""

    ticket_url = OCTANE_WORK_ITEM_URL.format(ticket_id=html.escape(normalized_ticket_id, quote=True))
    return (
        f'<a href="{ticket_url}" target="_blank" rel="noopener noreferrer">'
        f'{html.escape(normalized_ticket_id)}</a>'
    )


def classify_group(phase_transition: str) -> str:
    from_part, to_part = phase_transition, ""
    if "→" in phase_transition:
        from_part, to_part = phase_transition.split("→", 1)
    from_part = from_part.strip()
    to_part = to_part.strip()

    def get_prefix(phase_text: str):
        matched = re.match(r"^(\d{2})-", (phase_text or "").strip())
        return matched.group(1) if matched else None

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


def build_group_time_statistics(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for segment in segments:
        transition = build_phase_transition_label(segment)
        group = classify_group(transition)
        if group not in GROUP_ORDER:
            continue

        bucket = grouped.setdefault(group, {"durations": [], "tickets": set()})
        bucket["durations"].append(float(segment.get("duration_days") or 0.0))
        ticket_id = str(segment.get("ticket_id") or "").strip()
        if ticket_id:
            bucket["tickets"].add(ticket_id)

    rows: List[Dict[str, Any]] = []
    for group in GROUP_ORDER:
        bucket = grouped.get(group)
        if not bucket or not bucket["durations"]:
            continue
        durations = sorted(bucket["durations"])
        total_days = round(sum(durations), 2)
        rows.append(
            {
                "Group": group,
                "Transfers": len(durations),
                "Tickets": len(bucket["tickets"]),
                "Total Days": total_days,
                "Avg Days": round(total_days / len(durations), 2),
                "Median Days": round(float(median(durations)), 2),
                "Max Days": round(max(durations), 2),
            }
        )
    return rows


def build_group_transition_rankings(segments: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, Dict[str, Dict[str, Any]]] = {group: {} for group in GROUP_ORDER}
    for segment in segments:
        transition = str(segment.get("phase_transition") or build_phase_transition_label(segment)).strip()
        group = str(segment.get("group") or classify_group(transition)).strip()
        if group not in GROUP_ORDER or not transition:
            continue

        bucket = grouped[group].setdefault(
            transition,
            {"durations": [], "tickets": set()},
        )
        bucket["durations"].append(float(segment.get("duration_days") or 0.0))
        ticket_id = str(segment.get("ticket_id") or "").strip()
        if ticket_id:
            bucket["tickets"].add(ticket_id)

    rankings: Dict[str, List[Dict[str, Any]]] = {}
    for group in GROUP_ORDER:
        rows: List[Dict[str, Any]] = []
        for transition, payload in grouped[group].items():
            durations = sorted(payload["durations"])
            total_days = round(sum(durations), 2)
            count = len(durations)
            rows.append(
                {
                    "Phase Transition": transition,
                    "Avg Days": round(total_days / count, 2) if count else 0.0,
                    "Count": count,
                    "Total Days": total_days,
                    "Tickets": len(payload["tickets"]),
                }
            )

        rankings[group] = sorted(
            rows,
            key=lambda item: (-float(item.get("Avg Days") or 0.0), -int(item.get("Count") or 0), str(item.get("Phase Transition") or "")),
        )
    return rankings


def build_phase_report_rows(ticket_ids: Iterable[str], history_folder: str = "history", db_path: Optional[str] = None) -> Dict[str, Any]:
    normalized_ids = [str(ticket_id).strip() for ticket_id in ticket_ids if str(ticket_id).strip()]
    generated_at = datetime.now(timezone.utc)
    metadata_lookup = load_ticket_metadata(normalized_ids, db_path=db_path)
    segments: List[Dict[str, Any]] = []
    missing_ticket_ids: List[str] = []

    for ticket_id in normalized_ids:
        history_data = _load_history_data(ticket_id, history_folder=history_folder)
        ticket_meta = metadata_lookup.get(ticket_id, {})
        ticket_name = ticket_meta.get("ticket_name") or f"Ticket {ticket_id}"

        if not history_data:
            missing_ticket_ids.append(ticket_id)
            continue

        segment_end_time = _parse_iso_timestamp(ticket_meta.get("last_modified")) or generated_at
        ticket_segments = build_phase_segments(
            history_data,
            ticket_meta={"ticket_id": ticket_id, "ticket_name": ticket_name},
            now=segment_end_time,
        )

        if not ticket_segments:
            missing_ticket_ids.append(ticket_id)
            continue

        for segment in ticket_segments:
            segment["current_phase"] = ticket_meta.get("phase") or segment.get("phase") or ""
            segment["phase_transition"] = build_phase_transition_label(segment)
            segment["group"] = classify_group(segment["phase_transition"])
            segments.append(segment)

    segments.sort(key=lambda item: (str(item.get("ticket_id") or ""), str(item.get("start_time") or "")))

    duration_days = [float(item.get("duration_days") or 0) for item in segments]
    longest_segment = max(segments, key=lambda item: float(item.get("duration_hours") or 0), default=None)
    summary = {
        "ticket_count": len({str(item.get("ticket_id") or "") for item in segments}),
        "segment_count": len(segments),
        "avg_duration_days": round(sum(duration_days) / len(duration_days), 2) if duration_days else 0.0,
        "longest_segment_label": (
            f"{longest_segment.get('ticket_id')} · {longest_segment.get('phase')} · {float(longest_segment.get('duration_days') or 0):.2f}d"
            if longest_segment else "N/A"
        ),
    }
    group_time_stats = build_group_time_statistics(segments)
    group_transition_rankings = build_group_transition_rankings(segments)

    return {
        "summary": summary,
        "group_time_stats": group_time_stats,
        "group_transition_rankings": group_transition_rankings,
        "segments": segments,
        "missing_ticket_ids": missing_ticket_ids,
        "generated_at": generated_at.isoformat(),
    }


def _build_timeline_figure(segments: List[Dict[str, Any]]):
    if not segments:
        fig = px.timeline(pd.DataFrame({"start": [], "end": [], "ticket": [], "phase": []}), x_start="start", x_end="end", y="ticket", color="phase")
        fig.update_layout(title=REPORT_TITLE)
        fig.add_annotation(text="No usable phase history found for the selected ticket IDs.", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    df = pd.DataFrame(segments).copy()
    df["start_dt"] = pd.to_datetime(df["start_time"], utc=True, format="mixed")
    df["end_dt"] = pd.to_datetime(df["end_time"], utc=True, format="mixed")
    df["ticket_label"] = df["ticket_id"].astype(str)
    df["open_label"] = df["is_open_segment"].map({True: "Open", False: "Closed"})
    unique_ticket_count = len(df["ticket_label"].unique())

    fig = px.timeline(
        df,
        x_start="start_dt",
        x_end="end_dt",
        y="ticket_label",
        color="phase",
        hover_data={
            "ticket_id": True,
            "ticket_name": True,
            "duration_days": ":.2f",
            "open_label": True,
            "start_dt": True,
            "end_dt": True,
            "phase": True,
            "ticket_label": False,
        },
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_traces(marker_line_width=0)
    fig.update_layout(
        title=REPORT_TITLE,
        height=max(720, 120 + (unique_ticket_count * 44)),
        paper_bgcolor="#f5f1e8",
        plot_bgcolor="#ffffff",
        legend_title_text="Phase",
        margin=dict(l=120, r=24, t=88, b=32),
        xaxis_title="Date",
        yaxis_title="Defect ID",
    )
    fig.update_xaxes(
        side="top",
        tickformat="%m-%d",
        dtick=86400000.0,
        showgrid=True,
        gridcolor="#e7e1d4",
        ticklabelmode="period",
    )
    fig.update_yaxes(
        automargin=True,
        tickfont={"size": 12},
    )
    return fig


def _render_summary_cards(summary: Dict[str, Any]) -> str:
    cards = [
        ("Tickets", summary.get("ticket_count", 0)),
        ("Transfers", summary.get("segment_count", 0)),
        ("Avg Duration", f"{float(summary.get('avg_duration_days', 0)):.2f} d"),
        ("Longest Segment", summary.get("longest_segment_label", "N/A")),
    ]
    return "".join(
        "<section class='summary-card'>"
        f"<div class='summary-label'>{html.escape(str(label))}</div>"
        f"<div class='summary-value'>{html.escape(str(value))}</div>"
        "</section>"
        for label, value in cards
    )


def _build_group_time_figure(group_time_stats: List[Dict[str, Any]]):
    if not group_time_stats:
        fig = px.bar(pd.DataFrame({"Group": [], "Days": [], "Metric": []}), x="Group", y="Days", color="Metric")
        fig.update_layout(title="Group Time Statistics")
        fig.add_annotation(text="No matching Q-Gate / Integration / CoC segments.", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    df = pd.DataFrame(group_time_stats)
    chart_df = df.melt(
        id_vars=["Group"],
        value_vars=["Total Days", "Avg Days"],
        var_name="Metric",
        value_name="Days",
    )
    fig = px.bar(chart_df, x="Group", y="Days", color="Metric", barmode="group")
    fig.update_layout(
        title="Group Time Statistics",
        height=360,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        margin=dict(l=20, r=20, t=60, b=20),
        yaxis_title="Days",
        xaxis_title="Group",
    )
    return fig


def _render_group_time_table(group_time_stats: List[Dict[str, Any]]) -> str:
    if not group_time_stats:
        return "<p class='empty-state'>No Q-Gate / Integration / CoC transitions were found.</p>"

    df = pd.DataFrame(group_time_stats).copy()
    for column_name in ["Total Days", "Avg Days", "Median Days", "Max Days"]:
        df[column_name] = df[column_name].map(lambda value: f"{float(value):.2f}")
    return df.to_html(index=False, classes="detail-table", border=0, justify="left", escape=True)


def _render_group_transition_rankings(rankings: Dict[str, List[Dict[str, Any]]], top_n: int = 10) -> str:
    sections: List[str] = []
    for group in GROUP_ORDER:
        rows = list((rankings or {}).get(group) or [])[:max(1, int(top_n))]
        if not rows:
            sections.append(
                "<section class='ranking-group'>"
                f"<h3>{html.escape(group)}</h3>"
                "<p class='empty-state'>No ranked transitions.</p>"
                "</section>"
            )
            continue

        df = pd.DataFrame(rows).copy()
        for column_name in ["Avg Days", "Total Days"]:
            df[column_name] = df[column_name].map(lambda value: f"{float(value):.2f}")
        table_html = df.to_html(index=False, classes="detail-table", border=0, justify="left", escape=True)
        sections.append(
            "<section class='ranking-group'>"
            f"<h3>{html.escape(group)}</h3>"
            f"{table_html}"
            "</section>"
        )

    return "<div class='ranking-grid'>" + "".join(sections) + "</div>"


def _render_details_table(segments: List[Dict[str, Any]]) -> str:
    if not segments:
        return "<p class='empty-state'>No phase segments were generated.</p>"

    df = pd.DataFrame(segments).copy()
    for column_name in [
        "ticket_id",
        "ticket_name",
        "group",
        "phase_transition",
        "phase",
        "from_phase",
        "start_time",
        "end_time",
        "duration_days",
        "is_open_segment",
    ]:
        if column_name not in df.columns:
            df[column_name] = ""
    df = df[
        [
            "ticket_id",
            "ticket_name",
            "group",
            "phase_transition",
            "phase",
            "from_phase",
            "start_time",
            "end_time",
            "duration_days",
            "is_open_segment",
        ]
    ]
    df.columns = [
        "Ticket ID",
        "Ticket Name",
        "Group",
        "Phase Transition",
        "Phase",
        "From Phase",
        "Start Time",
        "End Time",
        "Duration (Days)",
        "Open Segment",
    ]
    df["Ticket ID"] = df["Ticket ID"].map(build_ticket_link_html)
    df["Open Segment"] = df["Open Segment"].map({True: "Yes", False: "No"})
    df["Duration (Days)"] = df["Duration (Days)"].map(lambda value: f"{float(value):.2f}")
    return df.to_html(index=False, classes="detail-table", border=0, justify="left", escape=False)


def render_phase_transfer_report_html(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    group_time_stats = payload.get("group_time_stats") or build_group_time_statistics(payload.get("segments") or [])
    group_transition_rankings = payload.get("group_transition_rankings") or build_group_transition_rankings(payload.get("segments") or [])
    segments = payload.get("segments") or []
    missing_ticket_ids = payload.get("missing_ticket_ids") or []
    generated_at = payload.get("generated_at") or ""
    figure_html = _build_timeline_figure(segments).to_html(full_html=False, include_plotlyjs="inline")
    group_figure_html = _build_group_time_figure(group_time_stats).to_html(full_html=False, include_plotlyjs=False)
    missing_html = (
        "<div class='missing-box'><strong>Missing History:</strong> " + html.escape(", ".join(str(ticket_id) for ticket_id in missing_ticket_ids)
        ) + "</div>"
        if missing_ticket_ids else ""
    )

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{REPORT_TITLE}</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --surface: #ffffff;
      --ink: #1f2a37;
      --muted: #6b7280;
      --accent: #1d4ed8;
      --border: #d6d3d1;
      --shadow: 0 18px 40px rgba(36, 37, 47, 0.08);
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; background: linear-gradient(180deg, #ebe6da 0%, var(--bg) 42%, #f8f5ee 100%); color: var(--ink); }}
    .page {{ max-width: 1480px; margin: 0 auto; padding: 28px; }}
    .hero {{ background: rgba(255,255,255,0.74); border: 1px solid rgba(214,211,209,0.8); border-radius: 24px; padding: 24px 28px; box-shadow: var(--shadow); backdrop-filter: blur(8px); }}
    h1 {{ margin: 0; font-size: 30px; }}
    .subtitle {{ margin-top: 8px; color: var(--muted); }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }}
    .summary-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 18px; box-shadow: var(--shadow); }}
    .summary-label {{ font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin-bottom: 8px; }}
    .summary-value {{ font-size: 22px; font-weight: 700; line-height: 1.3; }}
    .panel {{ margin-top: 18px; background: var(--surface); border: 1px solid var(--border); border-radius: 24px; box-shadow: var(--shadow); padding: 18px; overflow: hidden; }}
    .panel h2 {{ margin: 0 0 14px 0; font-size: 20px; }}
        .panel h3 {{ margin: 0 0 10px 0; font-size: 17px; }}
    .missing-box {{ margin-top: 16px; padding: 12px 14px; border-radius: 14px; background: #fff7ed; border: 1px solid #fdba74; color: #9a3412; }}
    .detail-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    .detail-table thead th {{ position: sticky; top: 0; background: #f8fafc; text-align: left; border-bottom: 1px solid var(--border); padding: 10px; }}
    .detail-table tbody td {{ border-bottom: 1px solid #ece8df; padding: 10px; vertical-align: top; }}
    .detail-table tbody tr:nth-child(odd) {{ background: #fcfbf8; }}
        .ranking-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }}
        .ranking-group {{ min-width: 0; }}
    .empty-state {{ color: var(--muted); }}
    @media (max-width: 1080px) {{ .summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
        @media (max-width: 1080px) {{ .ranking-grid {{ grid-template-columns: 1fr; }} }}
        @media (max-width: 720px) {{ .page {{ padding: 16px; }} .summary-grid {{ grid-template-columns: 1fr; }} .summary-value {{ font-size: 18px; }} }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>{REPORT_TITLE}</h1>
      <div class="subtitle">Generated at {html.escape(str(generated_at))}</div>
      <div class="summary-grid">{_render_summary_cards(summary)}</div>
      {missing_html}
    </section>

    <section class="panel">
            <h2>Group Time Statistics</h2>
            {group_figure_html}
            {_render_group_time_table(group_time_stats)}
        </section>

        <section class="panel">
            <h2>Top Transition Rankings</h2>
            {_render_group_transition_rankings(group_transition_rankings)}
        </section>

        <section class="panel">
      <h2>Timeline</h2>
      {figure_html}
    </section>

    <section class="panel">
      <h2>Transfer Details</h2>
      {_render_details_table(segments)}
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a standalone phase transfer HTML report.")
    parser.add_argument("--ticket-ids", required=True, help="Comma or whitespace separated defect IDs")
    parser.add_argument("--output", default=str(Path("report") / "phase_transfer_report.html"), help="Output HTML path")
    parser.add_argument("--history-folder", default="history", help="History folder fallback path")
    parser.add_argument("--db-path", default=None, help="Optional SQLite database path override")
    args = parser.parse_args()

    ticket_ids = parse_ticket_ids(args.ticket_ids)
    if not ticket_ids:
        raise SystemExit("No ticket IDs were provided.")

    payload = build_phase_report_rows(ticket_ids, history_folder=args.history_folder, db_path=args.db_path)
    html_text = render_phase_transfer_report_html(payload)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    print(f"Report written to: {output_path}")
    print(f"Segments: {payload['summary']['segment_count']}, Missing tickets: {len(payload['missing_ticket_ids'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
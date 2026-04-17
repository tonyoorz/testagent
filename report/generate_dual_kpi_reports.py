#!/usr/bin/env python3
"""Generate both KPI HTML dashboards in one command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QGATE_OUTPUT = REPO_ROOT / "report" / "qgate_kpi_dashboard.html"
DEFAULT_COMPARE_HTML = REPO_ROOT / "kpi_report_2024_2025.html"
DEFAULT_COMPARE_XLSX = REPO_ROOT / "kpi_report_2024_2025.xlsx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate both KPI reports (QGate dashboard + 2024/2025 KPI report)."
    )

    # Shared behavior
    parser.add_argument("--python", default=sys.executable, help="Python executable used to run child scripts")
    parser.add_argument("--skip-qgate", action="store_true", help="Skip QGate dashboard generation")
    parser.add_argument("--skip-compare", action="store_true", help="Skip 2024/2025 KPI report generation")
    parser.add_argument(
        "--output-root",
        default="report/generated_runs",
        help="Root directory for timestamped generation folders",
    )

    # QGate options
    parser.add_argument("--defect-dir", default="qgate/defect", help="QGate defect data directory")
    parser.add_argument("--history-dir", default="qgate/history", help="QGate history data directory")
    parser.add_argument("--teams", default="", help="Comma-separated team list; empty uses qgate.py defaults")
    parser.add_argument("--min-transition-count", type=int, default=200, help="Minimum samples per transition")
    parser.add_argument("--analysis-workers", type=int, default=0, help="Parallel workers for history analysis")
    parser.add_argument("--cache-dir", default="qgate_cache", help="History analysis cache directory")
    parser.add_argument("--no-cache", action="store_true", help="Disable QGate cache")
    parser.add_argument("--no-progress", action="store_true", help="Disable QGate progress logs")
    parser.add_argument(
        "--qgate-output",
        default=str(DEFAULT_QGATE_OUTPUT.relative_to(REPO_ROOT)),
        help="Output path of qgate_kpi_dashboard.html",
    )

    # 2024/2025 KPI options
    parser.add_argument(
        "--compare-output",
        default=str(DEFAULT_COMPARE_HTML.relative_to(REPO_ROOT)),
        help="Output path of kpi_report_2024_2025.html",
    )
    parser.add_argument(
        "--compare-xlsx-output",
        default=str(DEFAULT_COMPARE_XLSX.relative_to(REPO_ROOT)),
        help="Output path of kpi_report_2024_2025.xlsx",
    )
    parser.add_argument(
        "--compare-lang",
        choices=["zh", "en"],
        default="zh",
        help="Language for KPI compare report output (default: zh)",
    )
    parser.add_argument(
        "--compare-bilingual",
        action="store_true",
        help="Generate both Chinese and English KPI compare reports",
    )

    return parser.parse_args()


def _as_repo_path(path_str: str) -> Path:
    candidate = Path(path_str)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def _run(command: list[str], name: str) -> None:
    print(f"\\n[RUN] {name}: {' '.join(command)}")
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {completed.returncode}")


def generate_qgate(args: argparse.Namespace, qgate_output: Path) -> Path:
    qgate_script = REPO_ROOT / "report" / "generate_qgate_kpi_dashboard.py"

    command = [
        args.python,
        str(qgate_script),
        "--defect-dir",
        args.defect_dir,
        "--history-dir",
        args.history_dir,
        "--min-transition-count",
        str(args.min_transition_count),
        "--analysis-workers",
        str(args.analysis_workers),
        "--cache-dir",
        args.cache_dir,
        "--output",
        str(qgate_output),
    ]

    if args.teams.strip():
        command.extend(["--teams", args.teams.strip()])
    if args.no_cache:
        command.append("--no-cache")
    if args.no_progress:
        command.append("--no-progress")

    _run(command, "QGate KPI dashboard")

    if not qgate_output.exists():
        raise FileNotFoundError(f"Expected output missing: {qgate_output}")
    return qgate_output


def generate_compare(args: argparse.Namespace, target_html: Path, target_xlsx: Path, lang: str) -> tuple[Path, Path]:
    compare_script = REPO_ROOT / "report" / "kpi_analysis_2024_2025.py"

    _run(
        [
            args.python,
            str(compare_script),
            "--output-html",
            str(target_html),
            "--output-xlsx",
            str(target_xlsx),
            "--lang",
            str(lang),
        ],
        f"2024/2025 KPI analysis ({lang})",
    )

    if not target_html.exists():
        raise FileNotFoundError(f"Expected output missing: {target_html}")
    if not target_xlsx.exists():
        raise FileNotFoundError(f"Expected output missing: {target_xlsx}")

    return target_html, target_xlsx


def main() -> None:
    args = parse_args()

    if args.skip_qgate and args.skip_compare:
        raise SystemExit("Nothing to do: both --skip-qgate and --skip-compare are set")

    produced: list[Path] = []
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = _as_repo_path(args.output_root) / run_stamp
    run_dir.mkdir(parents=True, exist_ok=True)

    qgate_output = run_dir / f"qgate_kpi_dashboard_{run_stamp}.html"
    compare_html_output = run_dir / f"kpi_report_2024_2025_{run_stamp}.html"
    compare_xlsx_output = run_dir / f"kpi_report_2024_2025_{run_stamp}.xlsx"

    # Keep user-provided explicit output options as an override.
    if args.qgate_output != str(DEFAULT_QGATE_OUTPUT.relative_to(REPO_ROOT)):
        qgate_output = _as_repo_path(args.qgate_output)
    if args.compare_output != str(DEFAULT_COMPARE_HTML.relative_to(REPO_ROOT)):
        compare_html_output = _as_repo_path(args.compare_output)
    if args.compare_xlsx_output != str(DEFAULT_COMPARE_XLSX.relative_to(REPO_ROOT)):
        compare_xlsx_output = _as_repo_path(args.compare_xlsx_output)

    if not args.skip_qgate:
        produced.append(generate_qgate(args, qgate_output))

    if not args.skip_compare:
        html_path, xlsx_path = generate_compare(args, compare_html_output, compare_xlsx_output, args.compare_lang)
        produced.extend([html_path, xlsx_path])

        if args.compare_bilingual:
            en_html = compare_html_output.with_name(f"{compare_html_output.stem}_en{compare_html_output.suffix}")
            en_xlsx = compare_xlsx_output.with_name(f"{compare_xlsx_output.stem}_en{compare_xlsx_output.suffix}")
            en_html_path, en_xlsx_path = generate_compare(args, en_html, en_xlsx, "en")
            produced.extend([en_html_path, en_xlsx_path])

    print("\\n[DONE] Generated files:")
    for path in produced:
        print(f" - {path}")


if __name__ == "__main__":
    main()

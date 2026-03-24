#!/usr/bin/env python3
"""
Pre-warm critical caches for dashboard startup and page switching.

Usage examples:
  python warmup_cache.py
  python warmup_cache.py --years 2025,2026 --weeks 52 --longrunner 300
"""

import argparse
import os
import time
from pathlib import Path


def _parse_years(raw: str):
    out = []
    for p in (raw or "").split(","):
        p = p.strip()
        if not p:
            continue
        try:
            out.append(int(p))
        except ValueError:
            pass
    return sorted(set(out))


def warm_defect_and_test(years):
    print("[1/3] Warming defect/test caches...")
    start = time.time()

    from defect_explore import load_application_data, ensure_defect_data_for_years

    load_application_data(force_reload=False, initial_years=tuple(years))
    ensure_defect_data_for_years(tuple(years))

    elapsed = time.time() - start
    print(f"      Done in {elapsed:.2f}s")


def warm_inflow_outflow(weeks: int):
    print("[2/3] Warming inflow/outflow cache...")
    start = time.time()

    from data_processor import calculate_inflow_outflow_trends

    _ = calculate_inflow_outflow_trends(date_range_weeks=weeks, force_refresh=False)

    elapsed = time.time() - start
    print(f"      Done in {elapsed:.2f}s")


def warm_longrunner(max_tickets: int, history_dir: str):
    print("[3/3] Warming longrunner phase cache...")
    start = time.time()

    from longrunner_analysis import _get_ticket_ids_from_db, analyze_ticket_phases_cached

    cache_dir = Path("cache") / "longrunner_phase"
    cache_dir.mkdir(parents=True, exist_ok=True)

    ticket_ids = _get_ticket_ids_from_db()[: max(0, int(max_tickets))]
    warmed = 0
    for tid in ticket_ids:
        out = analyze_ticket_phases_cached(
            str(tid),
            history_folder=history_dir,
            cache_dir=str(cache_dir),
            use_cache=True,
        )
        if not out.get("error"):
            warmed += 1

    elapsed = time.time() - start
    print(f"      Done in {elapsed:.2f}s, warmed {warmed}/{len(ticket_ids)} tickets")


def main():
    parser = argparse.ArgumentParser(description="Precompute dashboard caches")
    parser.add_argument("--years", default="2025,2026", help="Comma-separated defect years")
    parser.add_argument("--weeks", type=int, default=52, help="Inflow/outflow weeks window")
    parser.add_argument("--longrunner", type=int, default=200, help="How many tickets to pre-warm")
    parser.add_argument("--history-dir", default="history", help="History directory path")
    parser.add_argument("--skip-inflow", action="store_true", help="Skip inflow/outflow warmup")
    parser.add_argument("--skip-longrunner", action="store_true", help="Skip longrunner warmup")
    parser.add_argument("--fast", action="store_true", help="Use fast profile: weeks=8, longrunner=50")
    args = parser.parse_args()

    years = _parse_years(args.years)
    if not years:
        years = [2026]

    if args.fast:
        args.weeks = 8
        args.longrunner = 50

    # Keep behavior deterministic for scheduled jobs.
    os.environ.setdefault("DISABLE_RELOADER", "1")

    all_start = time.time()
    print("=== Cache Warmup Started ===")
    print(f"years={years}, weeks={args.weeks}, longrunner={args.longrunner}")
    if args.fast:
        print("profile=fast")

    warm_defect_and_test(years)
    if not args.skip_inflow:
        warm_inflow_outflow(args.weeks)
    else:
        print("[2/3] Skip inflow/outflow warmup")

    if not args.skip_longrunner:
        warm_longrunner(args.longrunner, args.history_dir)
    else:
        print("[3/3] Skip longrunner warmup")

    print(f"=== Cache Warmup Finished ({time.time() - all_start:.2f}s) ===")


if __name__ == "__main__":
    main()
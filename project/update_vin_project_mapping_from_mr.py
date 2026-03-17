import argparse
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd


VIN_REGEX = re.compile(r"[A-HJ-NPR-Z0-9]{17}")


def parse_args():
    p = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    p.add_argument("--mapping", default=str(Path(__file__).resolve().parent / "vin_project_mapping.xlsx"))
    p.add_argument("--mr-dir", default=str(root / "mr"))
    p.add_argument("--backup-suffix", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--report-nonstandard", action="store_true")
    return p.parse_args()


def normalize_vin(raw):
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s:
        return None
    if VIN_REGEX.fullmatch(s):
        return s
    return None


def choose_project_by_prefix(existing_df):
    d = {}
    vin_norm = existing_df["VIN"].astype(str).str.strip().str.upper()
    temp = existing_df.assign(_vin=vin_norm, _prefix=vin_norm.str[:3])
    for prefix, g in temp.groupby("_prefix"):
        vals = g["project"].dropna().astype(str).str.strip()
        vals = vals[vals != ""]
        if not vals.empty:
            d[prefix] = vals.value_counts().idxmax()
    return d


def guess_project(vin, prefix_project):
    p = vin[:3]
    if p in prefix_project:
        return prefix_project[p]
    if p == "WBY":
        return "IDCEVO25"
    return "MGU_02_A"


def collect_mr_vins(mr_dir):
    vin_counter = Counter()
    model_counter = defaultdict(Counter)
    nonstandard = Counter()
    files = sorted(Path(mr_dir).glob("R*.json"))
    for fp in files:
        with fp.open("r", encoding="utf-8") as f:
            arr = json.load(f)
        for row in arr:
            raw = row.get("testplatformid_udf")
            if raw is None:
                continue
            raw_s = str(raw).strip().upper()
            if not raw_s:
                continue
            vin = normalize_vin(raw_s)
            if vin:
                vin_counter[vin] += 1
                ms = ""
                if isinstance(row.get("exec_model_series_udf"), dict):
                    ms = (row["exec_model_series_udf"].get("name") or "").strip()
                model_counter[vin][ms] += 1
            else:
                nonstandard[raw_s] += 1
    return vin_counter, model_counter, nonstandard


def update_mapping(mapping_path, mr_dir, backup_suffix, dry_run=False, report_nonstandard=False):
    mapping_path = Path(mapping_path)
    mr_dir = Path(mr_dir)
    df = pd.read_excel(mapping_path)
    columns = list(df.columns)
    existing_vins = set(df["VIN"].astype(str).str.strip().str.upper())
    prefix_project = choose_project_by_prefix(df)
    vin_counter, model_counter, nonstandard = collect_mr_vins(mr_dir)
    new_vins = sorted(v for v in vin_counter if v not in existing_vins)
    new_rows = []
    for vin in new_vins:
        row = {c: "" for c in columns}
        row["VIN"] = vin
        row["Model Series"] = model_counter[vin].most_common(1)[0][0] if model_counter[vin] else ""
        row["project"] = guess_project(vin, prefix_project)
        new_rows.append(row)
    backup_path = mapping_path.with_name(f"{mapping_path.stem}.backup_{backup_suffix}{mapping_path.suffix}")
    if not dry_run and new_rows:
        if not backup_path.exists():
            shutil.copy2(mapping_path, backup_path)
        df_new = pd.DataFrame(new_rows, columns=columns)
        updated = pd.concat([df[columns], df_new], ignore_index=True)
        updated.to_excel(mapping_path, index=False)
    else:
        backup_path = None
    report_path = None
    if report_nonstandard:
        report_path = mapping_path.with_name("mr_nonstandard_platform_ids.csv")
        report_df = pd.DataFrame(
            [{"platform_id": k, "count": c} for k, c in nonstandard.most_common()],
            columns=["platform_id", "count"],
        )
        report_df.to_csv(report_path, index=False, encoding="utf-8-sig")
    return {
        "mapping_path": str(mapping_path),
        "backup_path": str(backup_path) if backup_path else "",
        "new_count": len(new_rows),
        "mr_unique_standard_vin": len(vin_counter),
        "mr_unique_nonstandard_id": len(nonstandard),
        "report_path": str(report_path) if report_path else "",
        "new_vins_preview": new_vins[:20],
    }


def main():
    a = parse_args()
    result = update_mapping(
        mapping_path=a.mapping,
        mr_dir=a.mr_dir,
        backup_suffix=a.backup_suffix,
        dry_run=a.dry_run,
        report_nonstandard=a.report_nonstandard,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

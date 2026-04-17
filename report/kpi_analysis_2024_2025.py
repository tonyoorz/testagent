#!/usr/bin/env python3
"""
2024 vs 2025 KPI完整分析报告
生成Excel和HTML格式报告
"""

import os
import argparse
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd
from octane_db import default_db_path

# 设置pandas显示选项
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

print("="*80)
print("📊 2024 vs 2025 完整KPI分析（含MR数据）")
print("="*80)


REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate 2024 vs 2025 KPI report (Excel + HTML)")
    parser.add_argument(
        "--output-xlsx",
        default="kpi_report_2024_2025.xlsx",
        help="Output Excel path (relative to repo root by default)",
    )
    parser.add_argument(
        "--output-html",
        default="kpi_report_2024_2025.html",
        help="Output HTML path (relative to repo root by default)",
    )
    parser.add_argument(
        "--html-template",
        default="",
        help="Optional static HTML template path; when set, output HTML will copy this template",
    )
    parser.add_argument(
        "--lang",
        choices=["zh", "en"],
        default="zh",
        help="Output language for generated report files",
    )
    return parser.parse_args()


def to_repo_path(path_value: str) -> Path:
    path_obj = Path(path_value)
    return path_obj if path_obj.is_absolute() else (REPO_ROOT / path_obj)


def series_value(df: pd.DataFrame, year: str, column: str, default=0):
    if df.empty or column not in df.columns or '年份' not in df.columns:
        return default
    filtered = df[df['年份'] == year]
    if filtered.empty:
        return default
    value = filtered.iloc[0][column]
    return value if pd.notna(value) else default


def localize_html_text(html: str, lang: str) -> str:
    if lang != "en":
        return html

    replacements = [
        ("lang=\"zh-CN\"", "lang=\"en\""),
        ("2024 vs 2025 KPI Analysis Report（Custom）", "2024 vs 2025 KPI Analysis Report"),
        ("测试与缺陷双视角年度对比（2024 / 2025）", "Annual Comparison from Testing and Defect Perspectives (2024 / 2025)"),
        ("生成时间", "Generated At"),
        ("2024 执行总量", "2024 Test Executions"),
        ("2025 执行总量", "2025 Test Executions"),
        ("2024 缺陷总量", "2024 Defects"),
        ("2025 缺陷总量", "2025 Defects"),
        ("A. 测试类指标（Testing Cluster）", "A. Testing Metrics (Testing Cluster)"),
        ("B. 缺陷类指标（Defect Cluster）", "B. Defect Metrics (Defect Cluster)"),
        ("C. 关键洞察", "C. Key Insights"),
        ("A. 测试类指标", "A. Testing Metrics"),
        ("B. 缺陷类指标", "B. Defect Metrics"),
        ("A1. 核心指标概览", "A1. Core KPI Overview"),
        ("A2. 覆盖矩阵（项目 × 车型 × 配置）", "A2. Coverage Matrix (Project x Model x Configuration)"),
        ("Release 趋势图（CW01-CW13，纵轴=测试通过率）", "Release Trend (CW01-CW13, Y-axis = Pass Rate)"),
        ("A3. 车型覆盖", "A3. Model Coverage"),
        ("A4. 测试执行与缺陷关联", "A4. Test Execution and Defect Linkage"),
        ("B1. 核心缺陷指标概览", "B1. Core Defect KPI Overview"),
        ("B2. CWA Blocking Reason 分布（两年并列，百分比=占当年CWA总量；Total=占当年Defect）", "B2. CWA Blocking Reason Distribution (two-year view; % = share of yearly CWA total; Total = share of yearly defects)"),
        ("B3. CWA 三色聚类（Green / Yellow / Red）", "B3. CWA Three-color Cluster (Green / Yellow / Red)"),
        ("B4. Ticket Matrix 分布图（2024 vs 2025，占比=占当年Matrix总量）", "B4. Ticket Matrix Distribution (2024 vs 2025, % = share of yearly matrix total)"),
        ("B5. 提票人 Top15（2024+2025）", "B5. Top 15 Submitters (2024+2025)"),
        ("C. 2025 跨团队纵向对比（含 DTSV）", "C. 2025 Cross-team Longitudinal Comparison (including DTSV)"),
        ("C1. Showstopper Confirmed 团队对比（数量+占比）", "C1. Showstopper Confirmed Team Comparison (count + share)"),
        ("C2. Phase 09(CWA) 团队对比（数量+占比）", "C2. Phase 09 (CWA) Team Comparison (count + share)"),
        ("执行总量", "Execution Volume"),
        ("Pass率", "Pass Rate"),
        ("Failed率", "Failed Rate"),
        ("Blocked率（Requires Attention）", "Blocked Rate (Requires Attention)"),
        ("关联缺陷数", "Defect-linked Executions"),
        ("缺陷总量", "Defect Volume"),
        ("指标", "Metric"),
        ("变化", "Change"),
        ("项目", "Project"),
        ("车型", "Model"),
        ("配置", "Configuration"),
        ("说明", "Notes"),
        ("排名", "Rank"),
        ("提票人", "Submitter"),
        ("合计", "Total"),
        ("年份", "Year"),
        ("团队", "Team"),
        ("总Defect", "Total Defects"),
        ("占比", "Share"),
        ("2024占比", "2024 Share"),
        ("2025占比", "2025 Share"),
        ("Yellow（可接受）", "Yellow (acceptable)"),
        ("Red（不可接受）", "Red (unacceptable)"),
        ("占执行", "of executions"),
        ("占缺陷", "of defects"),
        ("关键洞察", "Key Insights"),
        ("数据来源", "Data Source"),
        ("生成脚本", "Generator"),
        ("暂无可展示数据", "No data available"),
    ]

    localized = html
    for src, dst in replacements:
        localized = localized.replace(src, dst)
    return localized


def localized_sheet_names(lang: str) -> list[str]:
    if lang == "en":
        return [
            "1-Overview",
            "2-MR-Quality",
            "3-Project-Coverage",
            "4-Model-Coverage",
            "5-Defect-Linkage",
            "6-Severity",
            "7-CWA-Analysis",
            "8-ECU-Comparison",
            "9-Model-Defect-Comparison",
        ]
    return [
        "1-概览",
        "2-MR执行质量",
        "3-Project覆盖",
        "4-车型覆盖对比",
        "5-缺陷关联分析",
        "6-缺陷严重程度",
        "7-CWA分析",
        "8-ECU分布对比",
        "9-车型缺陷对比",
    ]


def localize_df_columns(df: pd.DataFrame, lang: str) -> pd.DataFrame:
    if lang != "en" or df is None or df.empty:
        return df

    col_map = {
        "年份": "Year",
        "总执行": "Total Executions",
        "Passed率": "Pass Rate",
        "Failed率": "Failed Rate",
        "Requires Attention率": "Requires Attention Rate",
        "执行次数": "Executions",
        "占比": "Share",
        "车型": "Model",
        "2024年": "2024",
        "2025年": "2025",
        "变化": "Change",
        "变化率": "Change Rate",
        "关联缺陷数": "Defect-linked Executions",
        "关联缺陷率": "Defect-linked Rate",
        "其中Failed": "Failed among Linked",
        "其中Passed": "Passed among Linked",
        "缺陷总数": "Total Defects",
        "BI-4及以下": "BI-4 and Below",
        "数量": "Count",
        "缺陷数": "Defects",
        "指标": "Metric",
    }
    return df.rename(columns=col_map)


args = parse_args()

# ==================== 1. 加载MR数据 ====================
print("\n1. 加载MR数据...")

def load_mr_data(year_prefix):
    """加载指定年份的MR数据"""
    mr_dir = REPO_ROOT / 'mr'
    mr_files = [f for f in os.listdir(mr_dir) if f.startswith(year_prefix) and f.endswith('.json')]
    mr_files.sort()

    all_mr = []
    for fname in mr_files:
        try:
            with open(mr_dir / fname, encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                for mr in data:
                    mr['source_file'] = fname
                    mr['year'] = year_prefix
                all_mr.extend(data)
        except Exception as e:
            print(f"  跳过 {fname}: {e}")

    return pd.json_normalize(all_mr)

# 加载2024和2025 MR数据
df_mr_2024 = load_mr_data('R24')
df_mr_2025 = load_mr_data('R25')

print(f"  2024年MR执行: {len(df_mr_2024):,} 条")
print(f"  2025年MR执行: {len(df_mr_2025):,} 条")
if len(df_mr_2024) > 0:
    print(f"  同比增长: {((len(df_mr_2025)-len(df_mr_2024))/len(df_mr_2024)*100):.1f}%")

# ==================== 2. 测试执行质量对比 ====================
print("\n2. 测试执行质量对比")
print("-"*60)

mr_summary = []
for year, df in [("2024", df_mr_2024), ("2025", df_mr_2025)]:
    if len(df) == 0:
        continue
    status_counts = df['status.name'].value_counts()
    total = len(df)
    passed = status_counts.get('Passed', 0)
    failed = status_counts.get('Failed', 0)
    attention = status_counts.get('Requires Attention', 0)
    planned = status_counts.get('Planned', 0)

    mr_summary.append({
        '年份': year,
        '总执行': total,
        'Passed': passed,
        'Passed率': f"{passed/total*100:.1f}%",
        'Failed': failed,
        'Failed率': f"{failed/total*100:.1f}%",
        'Requires Attention': attention,
        'Requires Attention率': f"{attention/total*100:.1f}%"
    })

    print(f"\n{year}年:")
    print(f"  总计: {total:,}")
    print(f"  Passed: {passed:,} ({passed/total*100:.1f}%)")
    print(f"  Failed: {failed:,} ({failed/total*100:.1f}%)")
    print(f"  Requires Attention: {attention:,} ({attention/total*100:.1f}%)")

df_mr_summary = pd.DataFrame(mr_summary)

# ==================== 3. Project覆盖分析 ====================
print("\n3. Project覆盖分析（基于target_ecu_conf_udf）")
print("-"*60)

def extract_projects(target_conf):
    """从target_ecu_conf_udf提取项目列表"""
    if pd.isna(target_conf):
        return []
    conf_str = str(target_conf)
    # 分割 "and" 或 "," 或 "+"
    projects = [p.strip() for p in conf_str.replace('and', ',').replace('+', ',').split(',')]
    return [p for p in projects if p]

def extract_main_project(target_conf):
    """提取主要项目（第一个）"""
    projects = extract_projects(target_conf)
    return projects[0] if projects else 'Unknown'

project_summary = []
for year, df in [("2024", df_mr_2024), ("2025", df_mr_2025)]:
    if len(df) == 0:
        continue

    print(f"\n{year}年 Project分布:")

    # 主要项目统计（取第一个项目）
    df['main_project'] = df['target_ecu_conf_udf'].apply(extract_main_project)
    project_counts = df['main_project'].value_counts()

    print(f"  {'Project':<25} {'执行次数':<10} {'占比':<8}")
    print(f"  {'-'*45}")

    for proj, count in project_counts.head(15).items():
        pct = count / len(df) * 100
        print(f"  {proj:<25} {count:<10} {pct:>6.1f}%")
        project_summary.append({
            '年份': year,
            'Project': proj,
            '执行次数': count,
            '占比': f"{pct:.1f}%"
        })

df_project_summary = pd.DataFrame(project_summary)

# ==================== 4. 车型覆盖对比 ====================
print("\n4. 车型覆盖对比")
print("-"*60)

print(f"\n{'车型':<12} {'2024年':<10} {'2025年':<10} {'变化':<10} {'变化率':<10}")
print("-"*55)

models_2024 = df_mr_2024['exec_model_series_udf.name'].value_counts() if len(df_mr_2024) > 0 else pd.Series()
models_2025 = df_mr_2025['exec_model_series_udf.name'].value_counts() if len(df_mr_2025) > 0 else pd.Series()

model_comparison = []
all_models = set(models_2024.index) | set(models_2025.index)
for model in sorted(all_models):
    c24 = models_2024.get(model, 0)
    c25 = models_2025.get(model, 0)
    if c24 > 10 or c25 > 10:
        change = c25 - c24
        change_pct = f"+{((c25-c24)/c24*100):.0f}%" if c24 > 0 else "New"
        print(f"  {model:<12} {c24:<10} {c25:<10} {change:+d}       {change_pct:<10}")
        model_comparison.append({
            '车型': model,
            '2024年': c24,
            '2025年': c25,
            '变化': change,
            '变化率': change_pct
        })

df_model_comparison = pd.DataFrame(model_comparison)

# ==================== 5. 缺陷关联分析 ====================
print("\n5. 测试执行与缺陷关联分析")
print("-"*60)

defect_link_summary = []
for year, df in [("2024", df_mr_2024), ("2025", df_mr_2025)]:
    if len(df) == 0:
        continue

    df['defect_count'] = df['defect.total_count'].fillna(0)
    df['has_defect'] = df['defect_count'] > 0

    total_with_defect = df['has_defect'].sum()
    failed_with_defect = df[(df['has_defect']) & (df['status.name'] == 'Failed')].shape[0]
    passed_with_defect = df[(df['has_defect']) & (df['status.name'] == 'Passed')].shape[0]
    ra_with_defect = df[(df['has_defect']) & (df['status.name'] == 'Requires Attention')].shape[0]

    print(f"\n{year}年:")
    print(f"  关联缺陷的测试执行: {total_with_defect:,} ({total_with_defect/len(df)*100:.1f}%)")
    if total_with_defect > 0:
        print(f"    ├─ Failed状态: {failed_with_defect:,} ({failed_with_defect/total_with_defect*100:.1f}%)")
        print(f"    ├─ Requires Attention: {ra_with_defect:,} ({ra_with_defect/total_with_defect*100:.1f}%)")
        print(f"    └─ Passed状态: {passed_with_defect:,} ({passed_with_defect/total_with_defect*100:.1f}%)")

    defect_link_summary.append({
        '年份': year,
        '总执行': len(df),
        '关联缺陷数': total_with_defect,
        '关联缺陷率': f"{total_with_defect/len(df)*100:.1f}%",
        '其中Failed': failed_with_defect,
        '其中Passed': passed_with_defect
    })

df_defect_link = pd.DataFrame(defect_link_summary)

# ==================== 6. 加载Defect数据 ====================
print("\n6. 加载Defect数据分析...")

DEFAULT_DB_PATH = default_db_path(str(REPO_ROOT))
conn = sqlite3.connect(DEFAULT_DB_PATH)

def extract_reporting_class(raw_json):
    try:
        data = json.loads(raw_json)
        rc = data.get('reporting_class_udf', {})
        return [c.get('name', '') for c in rc.get('data', [])]
    except:
        return []

def extract_phase(raw_json):
    try:
        data = json.loads(raw_json)
        return data.get('phase', {}).get('name', '')
    except:
        return ''


def normalize_phase_value(phase):
    s = str(phase or '').strip().lower()
    if '_' in s:
        base, tail = s.rsplit('_', 1)
        if tail in {'critical', 'high', 'medium', 'low', 's1', 's2', 's3', 's4'}:
            s = base
    return s


def phase_matches(phase, target):
    p = normalize_phase_value(phase)
    t = normalize_phase_value(target)
    if not p or not t:
        return False
    return (p == t) or p.startswith(t) or (t in p)

def extract_blocking_reason(raw_json):
    try:
        data = json.loads(raw_json)
        br = data.get('blocking_reason_udf', {})
        return br.get('name', '') if isinstance(br, dict) else ''
    except:
        return ''

def extract_severity(raw_json):
    try:
        data = json.loads(raw_json)
        return data.get('problem_severity_udf', {}).get('name', '')
    except:
        return ''

def extract_ecu(raw_json):
    try:
        data = json.loads(raw_json)
        return data.get('assigned_ecu_udf', {}).get('name', '')
    except:
        return ''

def extract_model(raw_json):
    try:
        data = json.loads(raw_json)
        return data.get('lead_model_udf', {}).get('name', '')
    except:
        return ''

df_defect_2024 = pd.read_sql_query("SELECT raw_json FROM octane_defects WHERE year=2024", conn)
df_defect_2025 = pd.read_sql_query("SELECT raw_json FROM octane_defects WHERE year=2025", conn)

print(f"  2024年缺陷: {len(df_defect_2024):,}")
print(f"  2025年缺陷: {len(df_defect_2025):,}")

# ==================== 7. 缺陷严重程度分析 ====================
print("\n7. 缺陷严重程度分析（基于reporting_class_udf）")
print("-"*60)

severity_summary = []
cwa_total_by_year = {}
severity_stats_by_year = {}
for year, df in [("2024", df_defect_2024), ("2025", df_defect_2025)]:
    print(f"\n{year}年:")

    stats = {
        'showstopper_confirmed': 0,
        'showstopper_candidate': 0,
        'preventing_maturity': 0,
        'obstructing_maturity': 0,
        'homologation': 0,
        'concluded_06': 0,
        'other': 0,
        'bi4_count': 0
    }

    for idx, row in df.iterrows():
        classes = extract_reporting_class(row['raw_json'])
        phase = extract_phase(row['raw_json'])
        severity = extract_severity(row['raw_json'])

        # BI-4及以下
        is_bi4 = any(x in severity for x in ['customer irritated', 'customer noticed', 'unsatisfactory', 'deficient'])
        if is_bi4:
            stats['bi4_count'] += 1

        # Reporting class (优先级排序)
        has_confirmed = any('Showstopper_Confirmed' in c for c in classes)
        has_candidate = any('Showstopper_Candidate' in c for c in classes)
        has_preventing = any('Preventing' in c and 'Maturity' in c for c in classes)
        has_obstructing = any('Obstructing' in c and 'Maturity' in c for c in classes)
        has_homologation = any('Homologation' in c for c in classes)

        if has_confirmed:
            stats['showstopper_confirmed'] += 1
        elif has_preventing:
            stats['preventing_maturity'] += 1
        elif has_candidate:
            stats['showstopper_candidate'] += 1
        elif has_obstructing:
            stats['obstructing_maturity'] += 1
        elif has_homologation:
            stats['homologation'] += 1
        else:
            stats['other'] += 1

        # 06-Concluded
        if phase_matches(phase, '06-Concluded'):
            stats['concluded_06'] += 1

    print(f"  BI-4及以下: {stats['bi4_count']} ({stats['bi4_count']/len(df)*100:.1f}%)")
    print(f"  🔴 Showstopper Confirmed: {stats['showstopper_confirmed']}")
    print(f"  🟠 Preventing Maturity: {stats['preventing_maturity']}")
    print(f"  🟡 Showstopper Candidate: {stats['showstopper_candidate']}")
    print(f"  ✅ 06-Concluded: {stats['concluded_06']}")
    severity_stats_by_year[year] = stats

    severity_summary.append({
        '年份': year,
        '缺陷总数': len(df),
        'BI-4及以下': stats['bi4_count'],
        'Showstopper Confirmed': stats['showstopper_confirmed'],
        'Preventing Maturity': stats['preventing_maturity'],
        'Showstopper Candidate': stats['showstopper_candidate'],
        '06-Concluded': stats['concluded_06']
    })

df_severity = pd.DataFrame(severity_summary)

# ==================== 8. CWA Blocking Reason分析 ====================
print("\n8. CWA Blocking Reason对比分析")
print("-"*60)

cwa_summary = []
for year, df in [("2024", df_defect_2024), ("2025", df_defect_2025)]:
    cwa_reasons = Counter()
    cwa_total = 0

    for idx, row in df.iterrows():
        phase = extract_phase(row['raw_json'])
        if phase_matches(phase, '09-Concluded without action'):
            cwa_total += 1
            reason = extract_blocking_reason(row['raw_json'])
            cwa_reasons[reason or 'Unknown/Empty'] += 1

    print(f"\n{year}年 (CWA总数: {cwa_total}):")
    cwa_total_by_year[year] = cwa_total
    print(f"  {'Blocking Reason':<40} {'数量':<8} {'占CWA比':<8}")
    print(f"  {'-'*60}")

    for reason, count in cwa_reasons.most_common(10):
        pct = count / cwa_total * 100
        print(f"  {reason:<40} {count:<8} {pct:>6.1f}%")
        cwa_summary.append({
            '年份': year,
            'Blocking Reason': reason,
            '数量': count,
            '占比': f"{pct:.1f}%"
        })

df_cwa = pd.DataFrame(cwa_summary)

# ==================== 9. ECU和车型缺陷对比 ====================
print("\n9. ECU和车型缺陷分布对比")
print("-"*60)

# ECU对比
print("\nECU缺陷分布TOP10:")

ecu_comparison = []
for year, df in [("2024", df_defect_2024), ("2025", df_defect_2025)]:
    ecu_counts = Counter()
    for row in df.itertuples():
        ecu = extract_ecu(row.raw_json)
        if ecu:
            ecu_counts[ecu] += 1

    for ecu, count in ecu_counts.most_common(10):
        ecu_comparison.append({
            '年份': year,
            'ECU': ecu,
            '缺陷数': count
        })

df_ecu = pd.DataFrame(ecu_comparison)

# 透视表
if len(df_ecu) > 0:
    df_ecu_pivot = df_ecu.pivot(index='ECU', columns='年份', values='缺陷数').fillna(0).astype(int)
    df_ecu_pivot['变化'] = df_ecu_pivot.get('2025', 0) - df_ecu_pivot.get('2024', 0)
    df_ecu_pivot = df_ecu_pivot.sort_values('2025', ascending=False)
    print(df_ecu_pivot.head(10).to_string())
else:
    df_ecu_pivot = pd.DataFrame(columns=['2024', '2025', '变化'])

# 车型缺陷对比
print("\n车型缺陷分布:")

model_defect_comparison = []
for year, df in [("2024", df_defect_2024), ("2025", df_defect_2025)]:
    model_counts = Counter()
    for row in df.itertuples():
        model = extract_model(row.raw_json)
        if model:
            model_counts[model] += 1

    for model, count in model_counts.items():
        if count > 5:
            model_defect_comparison.append({
                '年份': year,
                '车型': model,
                '缺陷数': count
            })

df_model_defect = pd.DataFrame(model_defect_comparison)

if len(df_model_defect) > 0:
    df_model_pivot = df_model_defect.pivot(index='车型', columns='年份', values='缺陷数').fillna(0).astype(int)
    df_model_pivot['变化'] = df_model_pivot.get('2025', 0) - df_model_pivot.get('2024', 0)
    baseline_2024 = pd.to_numeric(df_model_pivot.get('2024', 0), errors='coerce')
    current_2025 = pd.to_numeric(df_model_pivot.get('2025', 0), errors='coerce')
    safe_baseline = baseline_2024.replace(0, float('nan'))
    rate = ((current_2025 - baseline_2024) / safe_baseline * 100)
    df_model_pivot['变化率'] = pd.to_numeric(rate, errors='coerce').fillna(0).round(0).astype(int)
    df_model_pivot = df_model_pivot.sort_values('2025', ascending=False)
    print(df_model_pivot.head(15).to_string())
else:
    df_model_pivot = pd.DataFrame(columns=['2024', '2025', '变化', '变化率'])

conn.close()

# ==================== 10. 生成Excel报告 ====================
print("\n" + "="*80)
print("10. 生成Excel报告...")
print("="*80)

output_file = to_repo_path(args.output_xlsx)
output_file.parent.mkdir(parents=True, exist_ok=True)

with pd.ExcelWriter(str(output_file), engine='openpyxl') as writer:
    sheet_names = localized_sheet_names(args.lang)

    # Sheet 1: 概览
    if args.lang == "en":
        overview_data = {
            'Metric': ['Total Defects', 'MR Executions', 'DTSV_China Detected Defects', 'Test Pass Rate', 'Resolved Defect Rate (06-Concluded)'],
            '2024': [len(df_defect_2024), len(df_mr_2024), len(df_defect_2024),
                     f"{(series_value(df_mr_summary, '2024', 'Passed', 0)/len(df_mr_2024)*100):.1f}%" if len(df_mr_2024)>0 else 'N/A',
                     f"{(series_value(df_severity, '2024', '06-Concluded', 0)/len(df_defect_2024)*100):.1f}%" if len(df_defect_2024)>0 else 'N/A'],
            '2025': [len(df_defect_2025), len(df_mr_2025), len(df_defect_2025)-47,
                     f"{(series_value(df_mr_summary, '2025', 'Passed', 0)/len(df_mr_2025)*100):.1f}%" if len(df_mr_2025)>0 else 'N/A',
                     f"{(series_value(df_severity, '2025', '06-Concluded', 0)/len(df_defect_2025)*100):.1f}%" if len(df_defect_2025)>0 else 'N/A']
        }
    else:
        overview_data = {
            '指标': ['缺陷总数', 'MR测试执行', 'DTSV_China发现缺陷', '测试通过率', '真实缺陷解决率(06-Concluded)'],
            '2024年': [len(df_defect_2024), len(df_mr_2024), len(df_defect_2024),
                       f"{(series_value(df_mr_summary, '2024', 'Passed', 0)/len(df_mr_2024)*100):.1f}%" if len(df_mr_2024)>0 else 'N/A',
                       f"{(series_value(df_severity, '2024', '06-Concluded', 0)/len(df_defect_2024)*100):.1f}%" if len(df_defect_2024)>0 else 'N/A'],
            '2025年': [len(df_defect_2025), len(df_mr_2025), len(df_defect_2025)-47,
                       f"{(series_value(df_mr_summary, '2025', 'Passed', 0)/len(df_mr_2025)*100):.1f}%" if len(df_mr_2025)>0 else 'N/A',
                       f"{(series_value(df_severity, '2025', '06-Concluded', 0)/len(df_defect_2025)*100):.1f}%" if len(df_defect_2025)>0 else 'N/A']
        }
    df_overview = pd.DataFrame(overview_data)
    localize_df_columns(df_overview, args.lang).to_excel(writer, sheet_name=sheet_names[0], index=False)

    # Sheet 2: MR执行质量
    localize_df_columns(df_mr_summary, args.lang).to_excel(writer, sheet_name=sheet_names[1], index=False)

    # Sheet 3: Project覆盖
    localize_df_columns(df_project_summary, args.lang).to_excel(writer, sheet_name=sheet_names[2], index=False)

    # Sheet 4: 车型覆盖
    localize_df_columns(df_model_comparison, args.lang).to_excel(writer, sheet_name=sheet_names[3], index=False)

    # Sheet 5: 缺陷关联
    localize_df_columns(df_defect_link, args.lang).to_excel(writer, sheet_name=sheet_names[4], index=False)

    # Sheet 6: 严重程度
    localize_df_columns(df_severity, args.lang).to_excel(writer, sheet_name=sheet_names[5], index=False)

    # Sheet 7: CWA Blocking Reason
    localize_df_columns(df_cwa, args.lang).to_excel(writer, sheet_name=sheet_names[6], index=False)

    # Sheet 8: ECU分布
    localize_df_columns(df_ecu_pivot, args.lang).to_excel(writer, sheet_name=sheet_names[7])

    # Sheet 9: 车型缺陷
    localize_df_columns(df_model_pivot, args.lang).to_excel(writer, sheet_name=sheet_names[8])

print(f"✅ Excel报告已生成: {output_file}")

# ==================== 11. 生成HTML报告 ====================
print("\n11. 生成HTML报告...")
def table_html(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if df is None or df.empty:
        return '<div class="empty">暂无可展示数据</div>'
    show_df = df.head(max_rows) if max_rows else df
    return show_df.to_html(index=False, classes='table', border=0)


def trend_value(new_value: int, old_value: int) -> str:
    if old_value == 0:
        return "N/A"
    return f"{((new_value-old_value)/old_value*100):+.1f}%"


def _replace_once(text: str, pattern: str, replacement: str) -> str:
    return re.sub(pattern, replacement, text, count=1, flags=re.S)


def render_updated_template_html(template_text: str) -> str:
    mr24 = int(len(df_mr_2024))
    mr25 = int(len(df_mr_2025))
    defect24 = int(len(df_defect_2024))
    defect25 = int(len(df_defect_2025))

    pass24 = int(series_value(df_mr_summary, '2024', 'Passed', 0))
    pass25 = int(series_value(df_mr_summary, '2025', 'Passed', 0))
    fail24 = int(series_value(df_mr_summary, '2024', 'Failed', 0))
    fail25 = int(series_value(df_mr_summary, '2025', 'Failed', 0))
    ra24 = int(series_value(df_mr_summary, '2024', 'Requires Attention', 0))
    ra25 = int(series_value(df_mr_summary, '2025', 'Requires Attention', 0))
    link24 = int(series_value(df_defect_link, '2024', '关联缺陷数', 0))
    link25 = int(series_value(df_defect_link, '2025', '关联缺陷数', 0))

    pass_rate24 = (pass24 / mr24 * 100) if mr24 else 0
    pass_rate25 = (pass25 / mr25 * 100) if mr25 else 0
    fail_rate24 = (fail24 / mr24 * 100) if mr24 else 0
    fail_rate25 = (fail25 / mr25 * 100) if mr25 else 0
    ra_rate24 = (ra24 / mr24 * 100) if mr24 else 0
    ra_rate25 = (ra25 / mr25 * 100) if mr25 else 0
    link_exec_rate24 = (link24 / mr24 * 100) if mr24 else 0
    link_exec_rate25 = (link25 / mr25 * 100) if mr25 else 0
    link_def_rate24 = (link24 / defect24 * 100) if defect24 else 0
    link_def_rate25 = (link25 / defect25 * 100) if defect25 else 0

    ss24 = int(series_value(df_severity, '2024', 'Showstopper Confirmed', 0))
    ss25 = int(series_value(df_severity, '2025', 'Showstopper Confirmed', 0))
    pm24 = int(series_value(df_severity, '2024', 'Preventing Maturity', 0))
    pm25 = int(series_value(df_severity, '2025', 'Preventing Maturity', 0))
    sc24 = int(series_value(df_severity, '2024', 'Showstopper Candidate', 0))
    sc25 = int(series_value(df_severity, '2025', 'Showstopper Candidate', 0))
    hm24 = int(severity_stats_by_year.get('2024', {}).get('homologation', 0))
    hm25 = int(severity_stats_by_year.get('2025', {}).get('homologation', 0))

    cwa_map_2024 = {str(r.get('Blocking Reason', '')): int(r.get('数量', 0)) for r in df_cwa[df_cwa['年份'] == '2024'].to_dict('records')} if not df_cwa.empty else {}
    cwa_map_2025 = {str(r.get('Blocking Reason', '')): int(r.get('数量', 0)) for r in df_cwa[df_cwa['年份'] == '2025'].to_dict('records')} if not df_cwa.empty else {}
    cwa_total24 = int(cwa_total_by_year.get('2024', 0))
    cwa_total25 = int(cwa_total_by_year.get('2025', 0))

    html = template_text

    # Header cards
    html = _replace_once(html, r'(<div class="k">2024 执行总量</div><div class="v">)([^<]*)(</div>)', rf'\g<1>{mr24:,}\g<3>')
    html = _replace_once(html, r'(<div class="k">2025 执行总量</div><div class="v">)([^<]*)(</div>)', rf'\g<1>{mr25:,}\g<3>')
    html = _replace_once(html, r'(<div class="k">2025 执行总量</div><div class="v">[^<]*</div><div class="chg up">)([^<]*)(</div>)', rf'\g<1>{trend_value(mr25, mr24)}\g<3>')
    html = _replace_once(html, r'(<div class="k">2024 缺陷总量</div><div class="v">)([^<]*)(</div>)', rf'\g<1>{defect24:,}\g<3>')
    html = _replace_once(html, r'(<div class="k">2025 缺陷总量</div><div class="v">)([^<]*)(</div>)', rf'\g<1>{defect25:,}\g<3>')
    html = _replace_once(html, r'(<div class="k">2025 缺陷总量</div><div class="v">[^<]*</div><div class="chg up">)([^<]*)(</div>)', rf'\g<1>{trend_value(defect25, defect24)}\g<3>')

    # A1 summary table
    html = _replace_once(html, r'<tr><td>执行总量</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', f'<tr><td>执行总量</td><td>{mr24:,}</td><td>{mr25:,}</td><td>{mr25-mr24:+,}（{trend_value(mr25, mr24)}）</td></tr>')
    html = _replace_once(html, r'<tr><td>Pass率</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', f'<tr><td>Pass率</td><td>{pass24:,}（{pass_rate24:.2f}%）</td><td>{pass25:,}（{pass_rate25:.2f}%）</td><td>{(pass_rate25-pass_rate24):+.2f}pp</td></tr>')
    html = _replace_once(html, r'<tr><td>Failed率</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', f'<tr><td>Failed率</td><td>{fail24:,}（{fail_rate24:.2f}%）</td><td>{fail25:,}（{fail_rate25:.2f}%）</td><td>{(fail_rate25-fail_rate24):+.2f}pp</td></tr>')
    html = _replace_once(html, r'<tr><td>Blocked率（Requires Attention）</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', f'<tr><td>Blocked率（Requires Attention）</td><td>{ra24:,}（{ra_rate24:.2f}%）</td><td>{ra25:,}（{ra_rate25:.2f}%）</td><td>{(ra_rate25-ra_rate24):+.2f}pp</td></tr>')
    html = _replace_once(html, r'<tr><td>关联缺陷数</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', f'<tr><td>关联缺陷数</td><td>{link24:,}（占执行{link_exec_rate24:.2f}%，占缺陷{link_def_rate24:.2f}%）</td><td>{link25:,}（占执行{link_exec_rate25:.2f}%，占缺陷{link_def_rate25:.2f}%）</td><td>{link25-link24:+,}（{(link_def_rate25-link_def_rate24):+.2f}pp，占缺陷）</td></tr>')

    # B1 defect summary table
    html = _replace_once(html, r'<tr><td>缺陷总量</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', f'<tr><td>缺陷总量</td><td>{defect24:,}</td><td>{defect25:,}</td><td>{defect25-defect24:+,}（{trend_value(defect25, defect24)}）</td></tr>')
    html = _replace_once(html, r'<tr><td>Showstopper Confirmed</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', f'<tr><td>Showstopper Confirmed</td><td>{ss24:,}（{(ss24/defect24*100 if defect24 else 0):.2f}%）</td><td>{ss25:,}（{(ss25/defect25*100 if defect25 else 0):.2f}%）</td><td>{ss25-ss24:+,}（{((ss25/defect25*100 if defect25 else 0)-(ss24/defect24*100 if defect24 else 0)):+.2f}pp）</td></tr>')
    html = _replace_once(html, r'<tr><td>Preventing Maturity Grade</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', f'<tr><td>Preventing Maturity Grade</td><td>{pm24:,}（{(pm24/defect24*100 if defect24 else 0):.2f}%）</td><td>{pm25:,}（{(pm25/defect25*100 if defect25 else 0):.2f}%）</td><td>{pm25-pm24:+,}（{((pm25/defect25*100 if defect25 else 0)-(pm24/defect24*100 if defect24 else 0)):+.2f}pp）</td></tr>')
    html = _replace_once(html, r'<tr><td>Showstopper Candidate</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', f'<tr><td>Showstopper Candidate</td><td>{sc24:,}（{(sc24/defect24*100 if defect24 else 0):.2f}%）</td><td>{sc25:,}（{(sc25/defect25*100 if defect25 else 0):.2f}%）</td><td>{sc25-sc24:+,}（{((sc25/defect25*100 if defect25 else 0)-(sc24/defect24*100 if defect24 else 0)):+.2f}pp）</td></tr>')
    html = _replace_once(html, r'<tr><td>Homologation</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', f'<tr><td>Homologation</td><td>{hm24:,}（{(hm24/defect24*100 if defect24 else 0):.2f}%）</td><td>{hm25:,}（{(hm25/defect25*100 if defect25 else 0):.2f}%）</td><td>{hm25-hm24:+,}（{((hm25/defect25*100 if defect25 else 0)-(hm24/defect24*100 if defect24 else 0)):+.2f}pp）</td></tr>')

    # B2 CWA table rows (top reasons + total row)
    for reason in [
        'Child (Duplicate)',
        'Expected behaviour',
        'Management decision',
        'Not reproducible',
        'Additional Information necessary',
        'Further traces necessary',
        'User Error',
        'Function not implemented/testable yet',
        'Invalid Testcase',
        'Tolerated',
    ]:
        c24 = int(cwa_map_2024.get(reason, 0))
        c25 = int(cwa_map_2025.get(reason, 0))
        p24 = (c24 / cwa_total24 * 100) if cwa_total24 else 0
        p25 = (c25 / cwa_total25 * 100) if cwa_total25 else 0
        html = _replace_once(
            html,
            rf'<tr><td>{re.escape(reason)}</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>',
            f'<tr><td>{reason}</td><td>{c24:,}</td><td>{c25:,}</td><td>{p24:.2f}%</td><td>{p25:.2f}%</td></tr>'
        )

    html = _replace_once(
        html,
        r'<tr><td>Total（DTSV CWA）</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>',
        f'<tr><td>Total（DTSV CWA）</td><td>{cwa_total24:,}</td><td>{cwa_total25:,}</td><td>{(cwa_total24/defect24*100 if defect24 else 0):.2f}%</td><td>{(cwa_total25/defect25*100 if defect25 else 0):.2f}%</td></tr>'
    )

    return html


execution_change = trend_value(len(df_mr_2025), len(df_mr_2024))
html_file = to_repo_path(args.output_html)
html_file.parent.mkdir(parents=True, exist_ok=True)

html_content = f"""
<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>2024 vs 2025 KPI Analysis Report</title>
  <style>
    *{{box-sizing:border-box}}
    body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",\"Microsoft YaHei\",sans-serif;background:#f3f5f8;color:#1f2937}}
    .wrap{{max-width:1400px;margin:24px auto;padding:0 16px}}
    .header{{background:linear-gradient(135deg,#0f2e5f,#1e4f9b);color:#fff;border-radius:14px;padding:24px 28px}}
    .header h1{{margin:0 0 8px 0;font-size:28px}}
    .header .sub{{opacity:.92;font-size:14px}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin-top:16px}}
    .card{{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);border-radius:12px;padding:12px}}
    .k{{font-size:12px;opacity:.9}}
    .v{{font-size:24px;font-weight:700;margin-top:4px}}
    .section{{margin-top:18px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px}}
    h2{{margin:0 0 10px 0;font-size:20px;color:#0f2e5f}}
    h3{{margin:10px 0;font-size:16px;color:#0f2e5f}}
    .table{{width:100%;border-collapse:collapse;font-size:13px}}
    .table th,.table td{{border:1px solid #e5e7eb;padding:8px 10px;text-align:left;vertical-align:top}}
    .table th{{background:#eef2ff}}
    .empty{{padding:14px;border:1px dashed #cbd5e1;border-radius:10px;color:#64748b;background:#f8fafc}}
    .insight{{background:#fffbeb;border-left:4px solid #f59e0b;padding:10px 12px;border-radius:8px;margin-top:10px}}
    .footer{{margin:20px 0 10px;color:#6b7280;font-size:12px}}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"header\">
      <h1>2024 vs 2025 KPI Analysis Report</h1>
      <div class=\"sub\">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
      <div class=\"grid\">
        <div class=\"card\"><div class=\"k\">2024 执行总量</div><div class=\"v\">{len(df_mr_2024):,}</div></div>
        <div class=\"card\"><div class=\"k\">2025 执行总量</div><div class=\"v\">{len(df_mr_2025):,}</div></div>
        <div class=\"card\"><div class=\"k\">2024 缺陷总量</div><div class=\"v\">{len(df_defect_2024):,}</div></div>
        <div class=\"card\"><div class=\"k\">2025 缺陷总量</div><div class=\"v\">{len(df_defect_2025):,}</div></div>
      </div>
    </div>

    <div class=\"section\">
      <h2>A. 测试类指标</h2>
      <h3>A1. 核心指标概览</h3>
      {table_html(df_mr_summary)}
      <h3>A2. Project覆盖</h3>
      {table_html(df_project_summary, 30)}
      <h3>A3. 车型覆盖</h3>
      {table_html(df_model_comparison, 30)}
      <h3>A4. 测试执行与缺陷关联</h3>
      {table_html(df_defect_link)}
    </div>

    <div class=\"section\">
      <h2>B. 缺陷类指标</h2>
      <h3>B1. 严重等级概览</h3>
      {table_html(df_severity)}
      <h3>B2. CWA Blocking Reason（Top 15）</h3>
      {table_html(df_cwa, 15)}
      <h3>B3. ECU分布（Top 15）</h3>
      {table_html(df_ecu_pivot.reset_index(), 15)}
      <h3>B4. 车型缺陷分布（Top 20）</h3>
      {table_html(df_model_pivot.reset_index(), 20)}
    </div>

    <div class=\"section\">
      <h2>C. 关键洞察</h2>
      <div class=\"insight\">MR执行量同比变化: <strong>{execution_change}</strong></div>
      <div class=\"insight\">Showstopper Confirmed: 2024={int(series_value(df_severity, '2024', 'Showstopper Confirmed', 0)):,}, 2025={int(series_value(df_severity, '2025', 'Showstopper Confirmed', 0)):,}</div>
      <div class=\"insight\">Preventing Maturity: 2024={int(series_value(df_severity, '2024', 'Preventing Maturity', 0)):,}, 2025={int(series_value(df_severity, '2025', 'Preventing Maturity', 0)):,}</div>
    </div>

        <div class=\"footer\">数据来源: mr/, database/{Path(DEFAULT_DB_PATH).name} | 生成脚本: report/kpi_analysis_2024_2025.py</div>
  </div>
</body>
</html>
"""

# Keep original UI while refreshing values: use template-first mode.
template_path = to_repo_path(args.html_template.strip()) if args.html_template.strip() else (REPO_ROOT / 'kpi_report_2024_2025.html')
if template_path.exists():
    html_content = render_updated_template_html(template_path.read_text(encoding='utf-8'))
    print(f"ℹ️ 使用模板并注入最新数据: {template_path}")
else:
    print(f"⚠️ 未找到模板文件，改用动态HTML: {template_path}")

with open(html_file, 'w', encoding='utf-8') as f:
    f.write(localize_html_text(html_content, args.lang))

print(f"✅ HTML报告已生成: {html_file}")

print("\n" + "="*80)
print("✅ 所有报告生成完成！")
print("="*80)
print(f"\n生成的文件:")
print(f"  1. Excel报告: {output_file}")
print(f"  2. HTML报告: {html_file}")
print(f"\n您可以直接用浏览器打开 {html_file} 查看美观的报告")
print(f"或者用Excel打开 {output_file} 进行进一步分析")

#!/usr/bin/env python3
"""
2024 vs 2025 KPI对比报告 - 表格形式并列显示
使用data_processor.py的项目提取逻辑
"""

import json
import os
import sqlite3
from collections import Counter
from datetime import datetime

import pandas as pd


EMPTY_TEXTS = {'', 'nan', 'none', 'null', 'n/a', 'na'}
MISSING_TEXT = 'Missing'
UNKNOWN_TEXT = 'Unknown'


def is_empty(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in EMPTY_TEXTS
    if pd.isna(value):
        return True
    return False


def normalize_text(value, default=UNKNOWN_TEXT):
    if is_empty(value):
        return default
    text = str(value).strip()
    return text if text else default


def normalize_name_field(value, default_unknown=UNKNOWN_TEXT, default_missing=MISSING_TEXT):
    if isinstance(value, dict):
        found_key = False
        for key in ('name', 'full_name'):
            if key in value:
                found_key = True
                candidate = value.get(key)
                if not is_empty(candidate):
                    return normalize_text(candidate, default_unknown)
        return default_unknown if found_key else default_missing
    return normalize_text(value, default_unknown)


def parse_raw_json(raw_json):
    if is_empty(raw_json):
        return {}
    try:
        data = json.loads(raw_json)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_field_name(data, key, default_unknown=UNKNOWN_TEXT, default_missing=MISSING_TEXT):
    if not isinstance(data, dict) or key not in data:
        return default_missing
    return normalize_name_field(data.get(key), default_unknown, default_missing)


def pct(numerator, denominator):
    return f"{(numerator / denominator * 100):.1f}%" if denominator > 0 else '0%'


def yoy_pct(new_value, old_value):
    if old_value == 0:
        return "0.0%" if new_value == 0 else "New"
    return f"{((new_value - old_value) / old_value * 100):.1f}%"


def choose_first_known(values):
    has_unknown = False
    for value in values:
        if value == UNKNOWN_TEXT:
            has_unknown = True
        elif value != MISSING_TEXT:
            return value
    return UNKNOWN_TEXT if has_unknown else MISSING_TEXT


def get_series_or_default(df, col, default_unknown=UNKNOWN_TEXT, default_missing=MISSING_TEXT):
    if len(df) == 0:
        return pd.Series(dtype='object')
    if col in df.columns:
        return df[col].apply(lambda v: normalize_text(v, default_unknown))
    return pd.Series([default_missing] * len(df), index=df.index, dtype='object')


print("=" * 80)
print("📊 2024 vs 2025 KPI对比报告 - 表格形式")
print("=" * 80)

print("\n【1. 加载MR数据】")


def load_mr_data(year_prefix):
    mr_files = [f for f in os.listdir('mr') if f.startswith(year_prefix) and f.endswith('.json')]
    mr_files.sort()
    print(f"  找到 {year_prefix} 文件数: {len(mr_files)}")
    all_mr = []
    for fname in mr_files:
        try:
            with open(f'mr/{fname}', 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                for mr in data:
                    mr['source_file'] = fname
                    mr['year'] = year_prefix
                all_mr.extend(data)
        except Exception as e:
            print(f"    警告: 跳过 {fname}: {e}")
    return pd.json_normalize(all_mr)


df_mr_2024 = load_mr_data('R24')
df_mr_2025 = load_mr_data('R25')

print(f"\n  ✅ 2024年MR数据: {len(df_mr_2024):,} 条")
print(f"  ✅ 2025年MR数据: {len(df_mr_2025):,} 条")

print("\n【2. 应用项目提取逻辑】")


def extract_project_from_row(row):
    has_target_ecu = 'target_ecu_conf_udf' in row.index
    has_name = 'name' in row.index
    target_ecu = normalize_text(row['target_ecu_conf_udf'], '') if has_target_ecu else ''
    name = normalize_text(row['name'], '') if has_name else ''
    project = ''
    if 'DTSV_CHINA-RSU' in name or 'RSU' in name:
        project = 'RSU'
    if project == '':
        if 'My BMW' in target_ecu:
            project = 'App'
        elif 'IDCEVO' in target_ecu:
            project = 'IDCevo'
        elif 'HU-MGU_02_L' in target_ecu:
            project = 'MGU'
        elif 'HU-MGU_02_A' in target_ecu:
            project = 'IDC'
    if project == '':
        if any(x in name for x in ['IOS', 'Android', 'HarmonyOS']):
            project = 'App'
        elif any(x in name for x in ['IDC23_MINI', 'IDC23_BMW', 'HU-MGU_02_A', 'IDC23']):
            project = 'IDC'
        elif 'IDCEVO' in name:
            project = 'IDCevo'
        elif any(x in name for x in ['MGU22', 'HU-MGU_02_L', 'HU-MGU_01', 'MGU21', 'MGU18']):
            project = 'MGU'
    if project.startswith('MGU'):
        project = 'MGU'
    if project:
        return project
    if not has_target_ecu and not has_name:
        return MISSING_TEXT
    return UNKNOWN_TEXT


for df, year in [(df_mr_2024, '2024'), (df_mr_2025, '2025')]:
    if len(df) > 0:
        df['project'] = df.apply(extract_project_from_row, axis=1)
        df['status_clean'] = get_series_or_default(df, 'status.name')
        df['model_clean'] = get_series_or_default(df, 'exec_model_series_udf.name')
        if 'defect.total_count' in df.columns:
            df['defect_count'] = pd.to_numeric(df['defect.total_count'], errors='coerce').fillna(0)
        else:
            df['defect_count'] = 0
        df['has_defect'] = df['defect_count'] > 0
        print(f"  {year}年项目分布:")
        for proj, count in df['project'].value_counts().items():
            print(f"    {proj}: {count:,} ({count / len(df) * 100:.1f}%)")
    else:
        df['project'] = pd.Series(dtype='object')
        df['status_clean'] = pd.Series(dtype='object')
        df['model_clean'] = pd.Series(dtype='object')
        df['defect_count'] = pd.Series(dtype='float64')
        df['has_defect'] = pd.Series(dtype='bool')

print("\n【3. MR执行质量对比】")
print("-" * 60)

mr_metrics = {}
for year, df in [("2024", df_mr_2024), ("2025", df_mr_2025)]:
    total = len(df)
    status_counts = df['status_clean'].value_counts() if total > 0 else pd.Series(dtype='int64')
    passed = int(status_counts.get('Passed', 0))
    failed = int(status_counts.get('Failed', 0))
    requires_attention = int(status_counts.get('Requires Attention', 0))
    with_defect = int(df['has_defect'].sum()) if total > 0 else 0
    failed_with_defect = int(df[(df['has_defect']) & (df['status_clean'] == 'Failed')].shape[0]) if total > 0 else 0
    mr_metrics[year] = {
        '总执行': total,
        'Passed': passed,
        'Passed率': pct(passed, total),
        'Failed': failed,
        'Failed率': pct(failed, total),
        'Requires Attention': requires_attention,
        'RA率': pct(requires_attention, total),
        '关联缺陷数': with_defect,
        '关联缺陷率': pct(with_defect, total),
        'Failed且关联缺陷': failed_with_defect
    }

print(f"\n{'指标':<20} {'2024年':<15} {'2025年':<15} {'变化':<15}")
print("-" * 65)
for metric in ['总执行', 'Passed', 'Passed率', 'Failed', 'Failed率', 'Requires Attention', 'RA率', '关联缺陷数', '关联缺陷率', 'Failed且关联缺陷']:
    v24 = mr_metrics['2024'][metric]
    v25 = mr_metrics['2025'][metric]
    if metric in ['总执行', 'Passed', 'Failed', 'Requires Attention', '关联缺陷数', 'Failed且关联缺陷']:
        change = f"{v25 - v24:+,}"
    else:
        change = '-'
    print(f"{metric:<20} {str(v24):<15} {str(v25):<15} {change:<15}")

print("\n【4. Project覆盖对比】")
print("-" * 60)
project_2024 = df_mr_2024['project'].value_counts() if len(df_mr_2024) > 0 else pd.Series(dtype='int64')
project_2025 = df_mr_2025['project'].value_counts() if len(df_mr_2025) > 0 else pd.Series(dtype='int64')
all_projects = sorted(set(project_2024.index) | set(project_2025.index))
project_rows = []
print(f"\n{'Project':<15} {'2024年':<10} {'占比':<8} {'2025年':<10} {'占比':<8} {'变化':<10}")
print("-" * 65)
for proj in all_projects:
    c24 = int(project_2024.get(proj, 0))
    c25 = int(project_2025.get(proj, 0))
    p24 = pct(c24, len(df_mr_2024))
    p25 = pct(c25, len(df_mr_2025))
    change = c25 - c24
    print(f"{proj:<15} {c24:<10,} {p24:<8} {c25:<10,} {p25:<8} {change:+d}")
    project_rows.append({'Project': proj, '2024年': c24, '2024占比': p24, '2025年': c25, '2025占比': p25, '变化': change})
df_project = pd.DataFrame(project_rows)

print("\n【5. 车型覆盖对比】")
print("-" * 60)
model_2024 = df_mr_2024['model_clean'].value_counts() if len(df_mr_2024) > 0 else pd.Series(dtype='int64')
model_2025 = df_mr_2025['model_clean'].value_counts() if len(df_mr_2025) > 0 else pd.Series(dtype='int64')
all_models = sorted(set(model_2024.index) | set(model_2025.index))
model_rows = []
print(f"\n{'车型':<20} {'2024年':<10} {'2025年':<10} {'变化':<10} {'变化率':<10}")
print("-" * 70)
for model in all_models:
    c24 = int(model_2024.get(model, 0))
    c25 = int(model_2025.get(model, 0))
    if c24 > 20 or c25 > 20:
        change = c25 - c24
        change_pct = f"{(change / c24 * 100):+.0f}%" if c24 > 0 else "New"
        print(f"{model:<20} {c24:<10,} {c25:<10,} {change:+d}       {change_pct:<10}")
        model_rows.append({'车型': model, '2024年': c24, '2025年': c25, '变化': change, '变化率': change_pct})
df_model = pd.DataFrame(model_rows)

print("\n【6. Coverage矩阵对比 (Project × 车型)】")
print("-" * 60)
coverage_2024 = df_mr_2024.groupby(['project', 'model_clean']).size() if len(df_mr_2024) > 0 else pd.Series(dtype='int64')
coverage_2025 = df_mr_2025.groupby(['project', 'model_clean']).size() if len(df_mr_2025) > 0 else pd.Series(dtype='int64')
all_coverage_keys = sorted(set(coverage_2024.index) | set(coverage_2025.index))
coverage_rows = []
for project, model in all_coverage_keys:
    c24 = int(coverage_2024.get((project, model), 0))
    c25 = int(coverage_2025.get((project, model), 0))
    change = c25 - c24
    change_pct = f"{(change / c24 * 100):+.0f}%" if c24 > 0 else ("0%" if c25 == 0 else "New")
    coverage_rows.append({'Project': project, '车型': model, '2024年': c24, '2025年': c25, '变化': change, '变化率': change_pct})
df_coverage_matrix = pd.DataFrame(coverage_rows).sort_values(['Project', '车型']).reset_index(drop=True)
print(f"\n{'Project':<12} {'车型':<20} {'2024年':<10} {'2025年':<10} {'变化':<8}")
print("-" * 70)
for _, row in df_coverage_matrix.sort_values(['2025年', '2024年'], ascending=False).head(20).iterrows():
    print(f"{row['Project']:<12} {row['车型']:<20} {row['2024年']:<10,} {row['2025年']:<10,} {row['变化']:+d}")

print("\n【7. 覆盖评估输出】")
print("-" * 60)
coverage_eval_rows = []
for project in all_projects:
    for model in all_models:
        c24 = int(coverage_2024.get((project, model), 0))
        c25 = int(coverage_2025.get((project, model), 0))
        if c24 > 0 and c25 > 0:
            status = '已覆盖'
        elif c24 > 0 or c25 > 0:
            status = '部分覆盖'
        else:
            status = '未覆盖'
        coverage_eval_rows.append({'Project': project, '车型': model, '2024年': c24, '2025年': c25, '覆盖评估': status})
df_coverage_evaluation = pd.DataFrame(coverage_eval_rows).sort_values(['Project', '车型']).reset_index(drop=True)
coverage_assessment_summary = df_coverage_evaluation['覆盖评估'].value_counts().to_dict()
for label in ['已覆盖', '部分覆盖', '未覆盖']:
    count = int(coverage_assessment_summary.get(label, 0))
    print(f"{label:<8}: {count:,}")

print("\n【7. 加载Defect数据】")
print("-" * 60)
conn = sqlite3.connect('database/local_data.db')
df_def_2024 = pd.read_sql_query("SELECT raw_json FROM octane_defects WHERE year=2024", conn)
df_def_2025 = pd.read_sql_query("SELECT raw_json FROM octane_defects WHERE year=2025", conn)
print(f"  2024年缺陷: {len(df_def_2024):,}")
print(f"  2025年缺陷: {len(df_def_2025):,}")

print("\n【8. 缺陷严重程度对比 (reporting_class_udf)】")
print("-" * 60)


def analyze_defects(df):
    stats = {
        'total': len(df),
        'showstopper_confirmed': 0,
        'showstopper_candidate': 0,
        'preventing_maturity': 0,
        'obstructing_maturity': 0,
        'homologation': 0,
        'concluded_06': 0,
        'cwa_09': 0,
        'cwa_reasons': Counter(),
        'test_team_counts': Counter(),
        'ecu_counts': Counter(),
        'model_counts': Counter(),
        'null_stats': {
            'phase': Counter(),
            'blocking_reason': Counter(),
            'test_team': Counter(),
            'ecu': Counter(),
            'model': Counter()
        }
    }
    for row in df.itertuples():
        data = parse_raw_json(row.raw_json)
        reporting_class = data.get('reporting_class_udf', {}) if isinstance(data, dict) else {}
        class_data = reporting_class.get('data', []) if isinstance(reporting_class, dict) else []
        classes = []
        if isinstance(class_data, list):
            for item in class_data:
                class_name = normalize_name_field(item, '')
                if class_name:
                    classes.append(class_name)
        phase = get_field_name(data, 'phase', UNKNOWN_TEXT, MISSING_TEXT)
        blocking_reason = get_field_name(data, 'blocking_reason_udf', UNKNOWN_TEXT, MISSING_TEXT)
        primary_team = get_field_name(data, 'problem_finder_team_udf', UNKNOWN_TEXT, MISSING_TEXT)
        fallback_team = get_field_name(data, 'team', UNKNOWN_TEXT, MISSING_TEXT)
        author_team = get_field_name(data, 'author', UNKNOWN_TEXT, MISSING_TEXT)
        test_team = choose_first_known([primary_team, fallback_team, author_team])
        ecu = get_field_name(data, 'assigned_ecu_udf', UNKNOWN_TEXT, MISSING_TEXT)
        model = get_field_name(data, 'lead_model_udf', UNKNOWN_TEXT, MISSING_TEXT)
        for field, value in [('phase', phase), ('blocking_reason', blocking_reason), ('test_team', test_team), ('ecu', ecu), ('model', model)]:
            if value in (MISSING_TEXT, UNKNOWN_TEXT):
                stats['null_stats'][field][value] += 1
        stats['test_team_counts'][test_team] += 1
        stats['ecu_counts'][ecu] += 1
        stats['model_counts'][model] += 1
        if any('Showstopper_Confirmed' in c for c in classes):
            stats['showstopper_confirmed'] += 1
        elif any('Preventing' in c and 'Maturity' in c for c in classes):
            stats['preventing_maturity'] += 1
        elif any('Showstopper_Candidate' in c for c in classes):
            stats['showstopper_candidate'] += 1
        elif any('Obstructing' in c and 'Maturity' in c for c in classes):
            stats['obstructing_maturity'] += 1
        elif any('Homologation' in c for c in classes):
            stats['homologation'] += 1
        if phase == '06-Concluded':
            stats['concluded_06'] += 1
        elif phase == '09-Concluded without action':
            stats['cwa_09'] += 1
            stats['cwa_reasons'][blocking_reason] += 1
    return stats


stats_2024 = analyze_defects(df_def_2024)
stats_2025 = analyze_defects(df_def_2025)
severity_rows = []
print(f"\n{'指标':<30} {'2024年':<12} {'2025年':<12} {'变化':<10}")
print("-" * 70)
for label, key in [
    ('缺陷总数', 'total'),
    ('Showstopper Confirmed', 'showstopper_confirmed'),
    ('Preventing Maturity', 'preventing_maturity'),
    ('Showstopper Candidate', 'showstopper_candidate'),
    ('Obstructing Maturity', 'obstructing_maturity'),
    ('Homologation', 'homologation'),
    ('06-Concluded (真实解决)', 'concluded_06'),
    ('09-CWA (无方案关闭)', 'cwa_09'),
]:
    v24 = stats_2024[key]
    v25 = stats_2025[key]
    change = v25 - v24
    print(f"{label:<30} {v24:<12,} {v25:<12,} {change:+d}")
    severity_rows.append({'指标': label, '2024年': v24, '2025年': v25, '变化': change})
df_severity = pd.DataFrame(severity_rows)

print(f"\n{'严重级别 vs 真实解决对比':<30} {'2024年':<12} {'2025年':<12}")
print("-" * 60)
print(f"{'Showstopper Confirmed / 06-Concluded':<30} {stats_2024['showstopper_confirmed']}/{stats_2024['concluded_06']:<12} {stats_2025['showstopper_confirmed']}/{stats_2025['concluded_06']:<12}")
print(f"{'Preventing Maturity / 06-Concluded':<30} {stats_2024['preventing_maturity']}/{stats_2024['concluded_06']:<12} {stats_2025['preventing_maturity']}/{stats_2025['concluded_06']:<12}")
print(f"{'Showstopper Candidate / 06-Concluded':<30} {stats_2024['showstopper_candidate']}/{stats_2024['concluded_06']:<12} {stats_2025['showstopper_candidate']}/{stats_2025['concluded_06']:<12}")

print("\n【9. 测试团队缺陷统计 (Top 15)】")
print("-" * 60)
team_rows = []
all_teams = set(stats_2024['test_team_counts'].keys()) | set(stats_2025['test_team_counts'].keys())
print(f"\n{'测试团队':<40} {'2024年':<10} {'2025年':<10} {'变化':<10}")
print("-" * 75)
for team in sorted(all_teams, key=lambda t: stats_2025['test_team_counts'].get(t, 0), reverse=True)[:15]:
    c24 = int(stats_2024['test_team_counts'].get(team, 0))
    c25 = int(stats_2025['test_team_counts'].get(team, 0))
    change = c25 - c24
    print(f"{team:<40} {c24:<10,} {c25:<10,} {change:+d}")
    team_rows.append({'测试团队': team, '2024年': c24, '2025年': c25, '变化': change})
df_test_team = pd.DataFrame(team_rows)

print("\n【10. CWA Blocking Reason对比 (Top 10)】")
print("-" * 60)
cwa_rows = []
all_reasons = set(stats_2024['cwa_reasons'].keys()) | set(stats_2025['cwa_reasons'].keys())
print(f"\n{'Blocking Reason':<40} {'2024年':<10} {'2025年':<10}")
print("-" * 65)
for reason in sorted(all_reasons, key=lambda r: stats_2025['cwa_reasons'].get(r, 0), reverse=True)[:10]:
    c24 = int(stats_2024['cwa_reasons'].get(reason, 0))
    c25 = int(stats_2025['cwa_reasons'].get(reason, 0))
    print(f"{reason:<40} {c24:<10} {c25:<10}")
    cwa_rows.append({'Blocking Reason': reason, '2024年': c24, '2025年': c25})
df_cwa = pd.DataFrame(cwa_rows)

print("\n【11. ECU缺陷分布对比】")
print("-" * 60)
all_ecus = sorted(set(stats_2024['ecu_counts'].keys()) | set(stats_2025['ecu_counts'].keys()))
ecu_rows = []
print(f"\n{'ECU':<30} {'2024年':<10} {'2025年':<10} {'变化':<10}")
print("-" * 65)
for ecu in all_ecus:
    c24 = int(stats_2024['ecu_counts'].get(ecu, 0))
    c25 = int(stats_2025['ecu_counts'].get(ecu, 0))
    if c24 > 10 or c25 > 10:
        change = c25 - c24
        print(f"{ecu:<30} {c24:<10} {c25:<10} {change:+d}")
        ecu_rows.append({'ECU': ecu, '2024年': c24, '2025年': c25, '变化': change})
df_ecu = pd.DataFrame(ecu_rows)

print("\n【12. 车型缺陷分布对比】")
print("-" * 60)
all_models_def = sorted(set(stats_2024['model_counts'].keys()) | set(stats_2025['model_counts'].keys()))
model_def_rows = []
print(f"\n{'车型':<20} {'2024年':<10} {'2025年':<10} {'变化':<10} {'变化率':<10}")
print("-" * 75)
for model in all_models_def:
    c24 = int(stats_2024['model_counts'].get(model, 0))
    c25 = int(stats_2025['model_counts'].get(model, 0))
    if c24 > 5 or c25 > 5:
        change = c25 - c24
        change_pct = f"{(change / c24 * 100):+.0f}%" if c24 > 0 else "New"
        print(f"{model:<20} {c24:<10} {c25:<10} {change:+d}       {change_pct:<10}")
        model_def_rows.append({'车型': model, '2024年': c24, '2025年': c25, '变化': change, '变化率': change_pct})
df_model_defect = pd.DataFrame(model_def_rows)
conn.close()

print("\n【13. 空值质量统计 (Missing vs Unknown)】")
print("-" * 60)
null_rows = []
for year, df in [('2024', df_mr_2024), ('2025', df_mr_2025)]:
    total = len(df)
    for label, field in [('MR状态', 'status_clean'), ('MR车型', 'model_clean'), ('MR项目', 'project')]:
        counts = df[field].value_counts() if total > 0 else pd.Series(dtype='int64')
        missing_count = int(counts.get(MISSING_TEXT, 0))
        unknown_count = int(counts.get(UNKNOWN_TEXT, 0))
        null_rows.append({
            '数据域': 'MR',
            '字段': label,
            '年份': f'{year}年',
            'Missing': missing_count,
            'Unknown': unknown_count,
            '空值合计': missing_count + unknown_count,
            '空值占比': pct(missing_count + unknown_count, total)
        })
for year, stats in [('2024', stats_2024), ('2025', stats_2025)]:
    total = stats['total']
    for field, label in [('phase', '缺陷阶段'), ('blocking_reason', 'CWA原因'), ('test_team', '测试团队'), ('ecu', '缺陷ECU'), ('model', '缺陷车型')]:
        missing_count = int(stats['null_stats'][field].get(MISSING_TEXT, 0))
        unknown_count = int(stats['null_stats'][field].get(UNKNOWN_TEXT, 0))
        null_rows.append({
            '数据域': 'Defect',
            '字段': label,
            '年份': f'{year}年',
            'Missing': missing_count,
            'Unknown': unknown_count,
            '空值合计': missing_count + unknown_count,
            '空值占比': pct(missing_count + unknown_count, total)
        })
df_null_quality = pd.DataFrame(null_rows)
print(f"\n{'数据域':<10} {'字段':<15} {'年份':<8} {'Missing':<10} {'Unknown':<10} {'空值占比':<10}")
print("-" * 75)
for _, row in df_null_quality.iterrows():
    print(f"{row['数据域']:<10} {row['字段']:<15} {row['年份']:<8} {row['Missing']:<10,} {row['Unknown']:<10,} {row['空值占比']:<10}")

print("\n" + "=" * 80)
print("【14. 生成Excel报告】")
print("=" * 80)
output_file = 'KPI对比报告_2024_2025_表格版.xlsx'
with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
    pd.DataFrame({
        '指标': ['MR测试执行总数', 'Passed率', 'Failed率', '关联缺陷率', '缺陷总数', 'Showstopper Confirmed', 'Preventing Maturity', 'Showstopper Candidate', '06-Concluded(真实解决)', '09-CWA(无方案关闭)'],
        '2024年': [mr_metrics['2024']['总执行'], mr_metrics['2024']['Passed率'], mr_metrics['2024']['Failed率'], mr_metrics['2024']['关联缺陷率'], stats_2024['total'], stats_2024['showstopper_confirmed'], stats_2024['preventing_maturity'], stats_2024['showstopper_candidate'], stats_2024['concluded_06'], stats_2024['cwa_09']],
        '2025年': [mr_metrics['2025']['总执行'], mr_metrics['2025']['Passed率'], mr_metrics['2025']['Failed率'], mr_metrics['2025']['关联缺陷率'], stats_2025['total'], stats_2025['showstopper_confirmed'], stats_2025['preventing_maturity'], stats_2025['showstopper_candidate'], stats_2025['concluded_06'], stats_2025['cwa_09']]
    }).to_excel(writer, sheet_name='1-概览', index=False)
    pd.DataFrame({
        '指标': ['总执行', 'Passed', 'Passed率', 'Failed', 'Failed率', 'Requires Attention', 'RA率', '关联缺陷数', '关联缺陷率'],
        '2024年': [mr_metrics['2024'][k] for k in ['总执行', 'Passed', 'Passed率', 'Failed', 'Failed率', 'Requires Attention', 'RA率', '关联缺陷数', '关联缺陷率']],
        '2025年': [mr_metrics['2025'][k] for k in ['总执行', 'Passed', 'Passed率', 'Failed', 'Failed率', 'Requires Attention', 'RA率', '关联缺陷数', '关联缺陷率']]
    }).to_excel(writer, sheet_name='2-MR执行质量', index=False)
    df_project.to_excel(writer, sheet_name='3-Project覆盖', index=False)
    df_model.to_excel(writer, sheet_name='4-车型覆盖对比', index=False)
    df_coverage_matrix.to_excel(writer, sheet_name='5-Coverage矩阵', index=False)
    df_coverage_evaluation.to_excel(writer, sheet_name='6-覆盖评估', index=False)
    df_null_quality.to_excel(writer, sheet_name='7-空值质量', index=False)
    df_severity.to_excel(writer, sheet_name='8-缺陷严重程度', index=False)
    pd.DataFrame({
        '严重级别': ['Showstopper Confirmed', 'Preventing Maturity', 'Showstopper Candidate'],
        '2024年数量': [stats_2024['showstopper_confirmed'], stats_2024['preventing_maturity'], stats_2024['showstopper_candidate']],
        '2024年06-Concluded': [stats_2024['concluded_06']] * 3,
        '2025年数量': [stats_2025['showstopper_confirmed'], stats_2025['preventing_maturity'], stats_2025['showstopper_candidate']],
        '2025年06-Concluded': [stats_2025['concluded_06']] * 3
    }).to_excel(writer, sheet_name='9-严重级别vs真实解决', index=False)
    df_test_team.to_excel(writer, sheet_name='10-测试团队缺陷', index=False)
    df_cwa.to_excel(writer, sheet_name='11-CWA Blocking Reason', index=False)
    df_ecu.to_excel(writer, sheet_name='12-ECU缺陷分布', index=False)
    df_model_defect.to_excel(writer, sheet_name='13-车型缺陷分布', index=False)
print(f"\n✅ Excel报告已生成: {output_file}")

print("\n" + "=" * 80)
print("【15. 生成HTML报告 (表格形式)】")
print("=" * 80)

html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>2024 vs 2025 KPI对比报告 - 表格版</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: #f5f7fa;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 30px;
        }}
        h1 {{
            text-align: center;
            color: #1e3c72;
            margin-bottom: 10px;
            padding-bottom: 15px;
            border-bottom: 3px solid #2a5298;
        }}
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 30px;
        }}
        h2 {{
            color: #1e3c72;
            margin: 30px 0 15px 0;
            padding-bottom: 8px;
            border-bottom: 2px solid #e9ecef;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            font-size: 14px;
        }}
        th {{
            background: #2a5298;
            color: white;
            padding: 12px 15px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 10px 15px;
            border-bottom: 1px solid #e9ecef;
        }}
        tr:hover {{ background: #f8f9fa; }}
        .numeric {{ text-align: right; }}
        .positive {{ color: #28a745; font-weight: bold; }}
        .negative {{ color: #dc3545; font-weight: bold; }}
        .section {{ margin-bottom: 40px; }}
        .summary {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
        }}
        .summary h3 {{ margin-bottom: 15px; }}
        .summary ul {{ margin-left: 20px; }}
        .summary li {{ margin: 8px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 2024 vs 2025 KPI对比报告</h1>
        <p class="subtitle">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        <div class="section">
            <h2>1. 核心指标概览</h2>
            <table>
                <tr><th>指标</th><th class="numeric">2024年</th><th class="numeric">2025年</th></tr>
                <tr><td>MR测试执行总数</td><td class="numeric">{mr_metrics['2024']['总执行']:,}</td><td class="numeric">{mr_metrics['2025']['总执行']:,}</td></tr>
                <tr><td>Passed率</td><td class="numeric">{mr_metrics['2024']['Passed率']}</td><td class="numeric positive">{mr_metrics['2025']['Passed率']}</td></tr>
                <tr><td>缺陷总数</td><td class="numeric">{stats_2024['total']:,}</td><td class="numeric">{stats_2025['total']:,}</td></tr>
                <tr><td>Showstopper Confirmed</td><td class="numeric">{stats_2024['showstopper_confirmed']:,}</td><td class="numeric negative">{stats_2025['showstopper_confirmed']:,}</td></tr>
                <tr><td>Preventing Maturity</td><td class="numeric">{stats_2024['preventing_maturity']:,}</td><td class="numeric positive">{stats_2025['preventing_maturity']:,}</td></tr>
            </table>
        </div>
        <div class="section">
            <h2>2. MR执行质量对比</h2>
            <table>
                <tr><th>指标</th><th class="numeric">2024年</th><th class="numeric">2025年</th></tr>
                <tr><td>总执行</td><td class="numeric">{mr_metrics['2024']['总执行']:,}</td><td class="numeric">{mr_metrics['2025']['总执行']:,}</td></tr>
                <tr><td>Passed</td><td class="numeric">{mr_metrics['2024']['Passed']:,}</td><td class="numeric">{mr_metrics['2025']['Passed']:,}</td></tr>
                <tr><td>Failed</td><td class="numeric">{mr_metrics['2024']['Failed']:,}</td><td class="numeric">{mr_metrics['2025']['Failed']:,}</td></tr>
                <tr><td>关联缺陷数</td><td class="numeric">{mr_metrics['2024']['关联缺陷数']:,}</td><td class="numeric">{mr_metrics['2025']['关联缺陷数']:,}</td></tr>
            </table>
        </div>
        <div class="section">
            <h2>3. Project覆盖对比</h2>
            <table>
                <tr><th>Project</th><th class="numeric">2024年</th><th class="numeric">2024占比</th><th class="numeric">2025年</th><th class="numeric">2025占比</th></tr>
'''
for _, row in df_project.iterrows():
    html_content += f'''                <tr><td>{row['Project']}</td><td class="numeric">{row['2024年']:,}</td><td class="numeric">{row['2024占比']}</td><td class="numeric">{row['2025年']:,}</td><td class="numeric">{row['2025占比']}</td></tr>
'''
html_content += '''            </table>
        </div>
        <div class="section">
            <h2>4. Coverage矩阵对比 (Top 20)</h2>
            <table>
                <tr><th>Project</th><th>车型</th><th class="numeric">2024年</th><th class="numeric">2025年</th><th class="numeric">变化</th></tr>
'''
for _, row in df_coverage_matrix.sort_values(['2025年', '2024年'], ascending=False).head(20).iterrows():
    change_class = 'positive' if row['变化'] < 0 else ('negative' if row['变化'] > 0 else '')
    html_content += f'''                <tr><td>{row['Project']}</td><td>{row['车型']}</td><td class="numeric">{row['2024年']:,}</td><td class="numeric">{row['2025年']:,}</td><td class="numeric {change_class}">{row['变化']:+d}</td></tr>
'''
html_content += '''            </table>
        </div>
        <div class="section">
            <h2>5. 覆盖评估输出</h2>
            <table>
                <tr><th>覆盖评估</th><th class="numeric">组合数量</th><th class="numeric">占比</th></tr>
'''
total_coverage_combos = len(df_coverage_evaluation)
for label in ['已覆盖', '部分覆盖', '未覆盖']:
    count = int(coverage_assessment_summary.get(label, 0))
    html_content += f'''                <tr><td>{label}</td><td class="numeric">{count:,}</td><td class="numeric">{pct(count, total_coverage_combos)}</td></tr>
'''
html_content += '''            </table>
        </div>
        <div class="section">
            <h2>6. 空值质量统计 (Missing vs Unknown)</h2>
            <table>
                <tr><th>数据域</th><th>字段</th><th>年份</th><th class="numeric">Missing</th><th class="numeric">Unknown</th><th class="numeric">空值合计</th><th class="numeric">空值占比</th></tr>
'''
for _, row in df_null_quality.iterrows():
    html_content += f'''                <tr><td>{row['数据域']}</td><td>{row['字段']}</td><td>{row['年份']}</td><td class="numeric">{row['Missing']:,}</td><td class="numeric">{row['Unknown']:,}</td><td class="numeric">{row['空值合计']:,}</td><td class="numeric">{row['空值占比']}</td></tr>
'''
html_content += '''            </table>
        </div>
        <div class="section">
            <h2>7. 缺陷严重程度对比</h2>
            <table>
                <tr><th>指标</th><th class="numeric">2024年</th><th class="numeric">2025年</th><th class="numeric">变化</th></tr>
'''
for _, row in df_severity.iterrows():
    change_class = 'positive' if row['变化'] < 0 else ('negative' if row['变化'] > 0 else '')
    html_content += f'''                <tr><td>{row['指标']}</td><td class="numeric">{row['2024年']:,}</td><td class="numeric">{row['2025年']:,}</td><td class="numeric {change_class}">{row['变化']:+d}</td></tr>
'''
html_content += '''            </table>
        </div>
        <div class="section">
            <h2>8. 测试团队缺陷统计 (Top 15)</h2>
            <table>
                <tr><th>测试团队</th><th class="numeric">2024年</th><th class="numeric">2025年</th><th class="numeric">变化</th></tr>
'''
for _, row in df_test_team.iterrows():
    change_class = 'positive' if row['变化'] < 0 else ('negative' if row['变化'] > 0 else '')
    html_content += f'''                <tr><td>{row['测试团队']}</td><td class="numeric">{row['2024年']:,}</td><td class="numeric">{row['2025年']:,}</td><td class="numeric {change_class}">{row['变化']:+d}</td></tr>
'''
html_content += '''            </table>
        </div>
        <div class="section">
            <h2>9. ECU缺陷分布对比 (Top 15)</h2>
            <table>
                <tr><th>ECU</th><th class="numeric">2024年</th><th class="numeric">2025年</th><th class="numeric">变化</th></tr>
'''
for _, row in df_ecu.head(15).iterrows():
    change_class = 'positive' if row['变化'] < 0 else ('negative' if row['变化'] > 0 else '')
    html_content += f'''                <tr><td>{row['ECU']}</td><td class="numeric">{row['2024年']:,}</td><td class="numeric">{row['2025年']:,}</td><td class="numeric {change_class}">{row['变化']:+d}</td></tr>
'''
html_content += f'''            </table>
        </div>
        <div class="summary">
            <h3>💡 关键洞察</h3>
            <ul>
                <li>✅ <strong>测试执行同比 {yoy_pct(mr_metrics['2025']['总执行'], mr_metrics['2024']['总执行'])}</strong>：从 {mr_metrics['2024']['总执行']:,} 到 {mr_metrics['2025']['总执行']:,}</li>
                <li>✅ <strong>Passed率变化 {float(mr_metrics['2025']['Passed率'].rstrip('%')) - float(mr_metrics['2024']['Passed率'].rstrip('%')):.1f}pp</strong>：{mr_metrics['2024']['Passed率']} → {mr_metrics['2025']['Passed率']}</li>
                <li>✅ <strong>Preventing Maturity同比 {yoy_pct(stats_2025['preventing_maturity'], stats_2024['preventing_maturity'])}</strong>：{stats_2024['preventing_maturity']} → {stats_2025['preventing_maturity']}</li>
                <li>⚠️ <strong>Showstopper Confirmed同比 {yoy_pct(stats_2025['showstopper_confirmed'], stats_2024['showstopper_confirmed'])}</strong>：{stats_2024['showstopper_confirmed']} → {stats_2025['showstopper_confirmed']}</li>
            </ul>
        </div>
    </div>
</body>
</html>'''

with open('KPI对比报告_2024_2025_表格版.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
print("\n✅ HTML报告已生成: KPI对比报告_2024_2025_表格版.html")

print("\n" + "=" * 80)
print("【分析完成】")
print("=" * 80)
print("""
生成的文件:
1. KPI对比报告_2024_2025_表格版.xlsx - Excel格式详细数据
2. KPI对比报告_2024_2025_表格版.html - HTML格式便于查看

特点:
- 补充Coverage矩阵（Project × 车型）
- 新增覆盖评估输出（已覆盖/部分覆盖/未覆盖）
- 空值区分Missing与Unknown并贯穿统计
- 新增测试团队缺陷统计
- 修复空值导致的统计偏差
""")

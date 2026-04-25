# Test Coverage Analysis 回调函数模块（Dash 回调已移除，保留业务逻辑辅助函数）
import gc
import os
import pandas as pd
from test_coverage_components import (
    create_project_status_chart,
    create_fvp_coverage_chart,
    create_testcase_detail_chart,
    create_enhanced_status_distribution_pie,
    create_pass_rate_trend_chart,
    create_test_aida_wordcloud,
    filter_test_data,
    get_cached_test_coverage_data
)
from data_processor import create_empty_figure


def _resolve_test_data_from_store(stored_data):
    """支持两种 data-store 形态：旧版 records 列表、或新版 cache_key 字典。"""
    if not stored_data:
        return pd.DataFrame()

    if isinstance(stored_data, list):
        return pd.DataFrame(stored_data)

    if isinstance(stored_data, dict):
        cache_key = stored_data.get('cache_key')
        if cache_key:
            return get_cached_test_coverage_data(cache_key)

    return pd.DataFrame()


PHASE1_ENABLED = os.environ.get('TC_PHASE1_ENABLE', '0').strip().lower() in {'1', 'true', 'yes'}

def build_chart3_export_xlsx(store_data):
    if not store_data:
        return None
    df = pd.DataFrame(store_data)
    if df.empty:
        return None

    from io import BytesIO

    base_cols = ['test_id', 'test_name', 'top_aida', 'fvp', 'fv', 'project', 'pu', 'tester']
    required_cols = ['test_week'] + base_cols
    for col in required_cols:
        if col not in df.columns:
            df[col] = ''

    status_col = 'export_status' if 'export_status' in df.columns else next(
        (c for c in ['run_status', 'status', 'execution_status'] if c in df.columns),
        None
    )
    if not status_col:
        return None

    status_mapping = {
        'passed': 'Passed',
        'failed': 'Failed',
        'blocked': 'Blocked',
        'planned': 'Planned',
        'requires attention': 'Blocked'
    }
    df['status_norm'] = df[status_col].apply(
        lambda x: status_mapping.get(str(x).strip().lower(), str(x).strip()) if x is not None else ''
    )

    df['test_week_str'] = df['test_week'].apply(lambda x: str(x) if x is not None else '').fillna('')

    parsed = df['test_week_str'].str.extract(r'(\d{2})-CW(\d{2})')
    df['_year'] = pd.to_numeric(parsed[0], errors='coerce')
    df['_cw'] = pd.to_numeric(parsed[1], errors='coerce')

    week_meta = (
        df[['test_week_str', '_year', '_cw']]
        .drop_duplicates()
        .assign(_year_sort=lambda d: d['_year'].fillna(99).astype(int),
                _cw_sort=lambda d: d['_cw'].fillna(99).astype(int))
        .sort_values(['_year_sort', '_cw_sort', 'test_week_str'])
    )
    years_present = week_meta['_year'].dropna().unique().tolist()
    use_short_label = len(years_present) == 1

    label_map = {}
    used_labels = set()
    for _, r in week_meta.iterrows():
        wk = r['test_week_str']
        yr = r['_year']
        cw = r['_cw']
        if pd.notna(yr) and pd.notna(cw):
            if use_short_label:
                label = f'CW{int(cw):02d}'
            else:
                label = f'{int(yr):02d}-CW{int(cw):02d}'
        else:
            label = wk
        if label in used_labels:
            label = wk
        used_labels.add(label)
        label_map[wk] = label

    df['week_label'] = df['test_week_str'].map(label_map).fillna(df['test_week_str'])

    priority = {'Failed': 4, 'Blocked': 3, 'Requires Attention': 3, 'Planned': 1, 'Passed': 0}

    def pick_status(series):
        return series.sort_values(key=lambda s: s.map(lambda x: priority.get(str(x), -1)), ascending=False).iloc[0]

    grouped = (
        df.groupby(base_cols + ['week_label'], dropna=False)['status_norm']
        .apply(pick_status)
        .reset_index()
    )

    pivot = grouped.pivot(index=base_cols, columns='week_label', values='status_norm')

    ordered_week_labels = [label_map[w] for w in week_meta['test_week_str'].tolist() if w in label_map]
    ordered_week_labels = [w for w in ordered_week_labels if w in pivot.columns]
    remaining = [c for c in pivot.columns.tolist() if c not in ordered_week_labels]
    week_cols = ordered_week_labels + remaining
    pivot = pivot.reindex(columns=week_cols)
    pivot = pivot.reset_index()

    def _count_weeks_with_result(row):
        vals = [row.get(c) for c in week_cols]
        return sum(pd.notna(v) and str(v).strip() != '' for v in vals)

    def _count_weeks_passed(row):
        vals = [row.get(c) for c in week_cols]
        vals = [v for v in vals if pd.notna(v) and str(v).strip() != '']
        return sum(str(v).strip() == 'Passed' for v in vals)

    total_weeks = len(week_cols)
    pivot['_weeks_with_result'] = pivot.apply(_count_weeks_with_result, axis=1)
    pivot['_weeks_passed'] = pivot.apply(_count_weeks_passed, axis=1)
    pivot['Test Frequency'] = pivot['_weeks_with_result'].apply(lambda x: (x / total_weeks) if total_weeks > 0 else 0)
    pivot['Pass Rate'] = pivot.apply(
        lambda r: (r['_weeks_passed'] / r['_weeks_with_result']) if r['_weeks_with_result'] > 0 else 0,
        axis=1
    )

    rename_map = {
        'test_id': 'Testcase ID',
        'test_name': 'Testcase Name',
        'top_aida': 'Top AIDA',
        'fvp': 'FVP',
        'fv': 'FV',
        'project': 'Project',
        'pu': 'PU',
        'tester': 'Tester'
    }
    pivot = pivot.rename(columns=rename_map)
    base_headers = [rename_map.get(c, c) for c in base_cols]
    output_cols = base_headers + week_cols + ['Test Frequency', 'Pass Rate']
    pivot_out = pivot[output_cols]

    stats_out = pivot[['Testcase ID', 'Testcase Name', 'Top AIDA', 'FVP', 'FV', 'Project', 'PU', 'Tester', '_weeks_with_result', '_weeks_passed', 'Test Frequency', 'Pass Rate']].copy()
    stats_out = stats_out.rename(columns={'_weeks_with_result': 'Weeks With Result', '_weeks_passed': 'Weeks Passed'})

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        pivot_out.to_excel(writer, index=False, sheet_name='Pivot')
        stats_out.to_excel(writer, index=False, sheet_name='Stats')

        workbook = writer.book
        worksheet = writer.sheets['Pivot']
        stats_ws = writer.sheets['Stats']

        nrows, ncols = pivot_out.shape
        worksheet.autofilter(0, 0, nrows, ncols - 1)
        worksheet.freeze_panes(1, len(base_headers))

        worksheet.set_column(0, 0, 14)
        worksheet.set_column(1, 1, 48)
        worksheet.set_column(2, 2, 46)
        worksheet.set_column(3, 7, 16)

        first_week_col = len(base_headers)
        last_week_col = first_week_col + len(week_cols) - 1
        if len(week_cols) > 0:
            worksheet.set_column(first_week_col, last_week_col, 11)

        tf_col = pivot_out.columns.get_loc('Test Frequency')
        pr_col = pivot_out.columns.get_loc('Pass Rate')

        percent_fmt = workbook.add_format({'num_format': '0%'})
        worksheet.set_column(tf_col, tf_col, 14, percent_fmt)
        worksheet.set_column(pr_col, pr_col, 12, percent_fmt)

        fmt_failed = workbook.add_format({'bg_color': '#FFC7CE'})
        fmt_blocked = workbook.add_format({'bg_color': '#FFD966'})
        fmt_planned = workbook.add_format({'bg_color': '#D9D9D9'})
        fmt_passed = workbook.add_format({'bg_color': '#C6EFCE'})

        if len(week_cols) > 0:
            worksheet.conditional_format(1, first_week_col, nrows, last_week_col, {'type': 'text', 'criteria': 'containing', 'value': 'Failed', 'format': fmt_failed})
            worksheet.conditional_format(1, first_week_col, nrows, last_week_col, {'type': 'text', 'criteria': 'containing', 'value': 'Blocked', 'format': fmt_blocked})
            worksheet.conditional_format(1, first_week_col, nrows, last_week_col, {'type': 'text', 'criteria': 'containing', 'value': 'Planned', 'format': fmt_planned})
            worksheet.conditional_format(1, first_week_col, nrows, last_week_col, {'type': 'text', 'criteria': 'containing', 'value': 'Passed', 'format': fmt_passed})

        stats_rows, stats_cols = stats_out.shape
        stats_ws.autofilter(0, 0, stats_rows, stats_cols - 1)
        stats_ws.freeze_panes(1, 0)
        tf2 = stats_out.columns.get_loc('Test Frequency')
        pr2 = stats_out.columns.get_loc('Pass Rate')
        stats_ws.set_column(tf2, tf2, 14, percent_fmt)
        stats_ws.set_column(pr2, pr2, 12, percent_fmt)
        stats_ws.set_column(0, 0, 14)
        stats_ws.set_column(1, 1, 48)
        stats_ws.set_column(2, 2, 46)
        stats_ws.set_column(3, 7, 16)
        stats_ws.set_column(8, 9, 18)

    buffer.seek(0)
    return buffer.getvalue()

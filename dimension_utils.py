import pandas as pd


def normalize_dimension_value(value):
    if pd.isna(value):
        return ''
    normalized = str(value).strip()
    if not normalized:
        return ''
    if normalized.lower() in {'unknown', 'none', 'nan', 'null', 'unknown/empty'}:
        return ''
    if normalized in {'未分类数据', '未知AIDA', '未知项目', '未知状态', '未知PU', '未知测试员'}:
        return ''
    return normalized


def build_preferred_dimension(df_input, primary_col, fallback_col, default_value='Unknown'):
    if df_input is None or df_input.empty:
        return pd.Series([], dtype='object')
    col_candidates = [c for c in [primary_col, fallback_col] if c in df_input.columns]
    if not col_candidates:
        return pd.Series([default_value] * len(df_input), index=df_input.index, dtype='object')

    def pick_value(row):
        for col in col_candidates:
            normalized = normalize_dimension_value(row.get(col))
            if normalized:
                return normalized
        return default_value

    return df_input.apply(pick_value, axis=1)


def build_chart_dimension(df_input, primary_col, fallback_col=None, unknown_label='Unknown'):
    if df_input is None or df_input.empty:
        return pd.Series([], dtype='object')
    if fallback_col:
        preferred = build_preferred_dimension(df_input, primary_col, fallback_col, default_value=unknown_label)
    elif primary_col in df_input.columns:
        preferred = df_input[primary_col]
    else:
        preferred = pd.Series([unknown_label] * len(df_input), index=df_input.index, dtype='object')
    normalized = preferred.apply(normalize_dimension_value)
    return normalized.where(normalized != '', other=unknown_label)


def sort_dimension_with_unknown_last(totals_df, dimension_col, count_col='缺陷数量'):
    if totals_df is None or totals_df.empty or dimension_col not in totals_df.columns:
        return []

    sortable = totals_df[[dimension_col, count_col]].copy()
    sortable[dimension_col] = sortable[dimension_col].astype(str)
    normalized = sortable[dimension_col].apply(normalize_dimension_value)
    sortable['_is_unknown'] = normalized == ''
    sortable = sortable.sort_values(
        by=['_is_unknown', count_col, dimension_col],
        ascending=[True, False, True]
    )
    return sortable[dimension_col].tolist()

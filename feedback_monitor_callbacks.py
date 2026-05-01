"""
Feedback monitor page callbacks.

Populates the feedback-monitor-* elements with live data from FeedbackStore.
"""

import logging
from dash import html, Input, Output, dash_table
from dash.exceptions import PreventUpdate

logger = logging.getLogger(__name__)


def _build_recent_searches_table(tracker, limit: int = 15):
    """Build a Dash DataTable showing recent search sessions."""
    from dash import dash_table as _dt
    sessions = tracker.get_recent_sessions(limit=limit)
    if not sessions:
        return html.P("暂无搜索记录", style={'color': '#94a3b8'})
    return _dt.DataTable(
        columns=[
            {'name': '时间', 'id': 'created_at'},
            {'name': '查询', 'id': 'query_text'},
            {'name': '结果数', 'id': 'result_count'},
            {'name': '阶段', 'id': 'model_phase'},
        ],
        data=sessions,
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '8px', 'fontSize': '13px'},
        style_header={'fontWeight': 'bold', 'backgroundColor': '#f1f5f9'},
        page_size=10,
    )


def register_feedback_monitor_callbacks(app):
    """Register callbacks that power the feedback monitoring page."""

    @app.callback(
        [Output('feedback-monitor-cards', 'children'),
         Output('feedback-monitor-phase', 'children'),
         Output('feedback-monitor-table', 'children'),
         Output('feedback-monitor-models', 'children'),
         Output('feedback-monitor-search-stats', 'children')],
        [Input('feedback-monitor-interval', 'n_intervals')],
        prevent_initial_call=False
    )
    def refresh_feedback_monitor(_n):
        try:
            from feedback_store import FeedbackStore, TrainingScheduler
        except Exception:
            msg = html.P("FeedbackStore 不可用", style={'color': '#ef4444'})
            return msg, "", msg, msg, msg

        try:
            store = FeedbackStore()
            scheduler = TrainingScheduler(store)

            # ── Summary cards ──
            total = store.get_total_feedback_count()
            positive = store.get_feedback_count_by_signal('positive')
            negative = store.get_feedback_count_by_signal('negative')
            phase = scheduler.current_phase()
            phase_labels = {
                'click_boost': ('统计增强', '#3b82f6'),
                'feature': ('特征学习', '#8b5cf6'),
            }
            phase_label, phase_color = phase_labels.get(phase, ('基线', '#6b7280'))

            card_style = {
                'display': 'inline-block', 'width': '22%', 'margin': '0 1.5%',
                'padding': '20px', 'borderRadius': '10px',
                'backgroundColor': '#f8fafc', 'border': '1px solid #e2e8f0',
                'textAlign': 'center', 'verticalAlign': 'top',
            }
            cards = html.Div([
                html.Div([
                    html.H3(str(total), style={'color': '#2563eb', 'margin': '0', 'fontSize': '28px'}),
                    html.P("总反馈数", style={'color': '#64748b', 'margin': '4px 0 0'})
                ], style=card_style),
                html.Div([
                    html.H3(str(positive), style={'color': '#22c55e', 'margin': '0', 'fontSize': '28px'}),
                    html.P("👍 正向", style={'color': '#64748b', 'margin': '4px 0 0'})
                ], style=card_style),
                html.Div([
                    html.H3(str(negative), style={'color': '#ef4444', 'margin': '0', 'fontSize': '28px'}),
                    html.P("👎 负向", style={'color': '#64748b', 'margin': '4px 0 0'})
                ], style=card_style),
                html.Div([
                    html.H3(phase_label, style={'color': phase_color, 'margin': '0', 'fontSize': '24px'}),
                    html.P("当前阶段", style={'color': '#64748b', 'margin': '4px 0 0'})
                ], style=card_style),
            ])

            # ── Phase progress bar ──
            thresholds = {'click_boost': 50, 'feature': float('inf')}
            next_threshold = thresholds.get(phase, 50)
            if next_threshold == float('inf'):
                progress_pct = 100
                progress_text = f"{total} 条反馈 · 已达最高阶段"
            else:
                progress_pct = min(100, int(total / next_threshold * 100))
                progress_text = f"{total}/{next_threshold} 条反馈 · 下一阶段进度 {progress_pct}%"
            phase_bar = html.Div([
                html.Div(progress_text, style={'fontSize': '13px', 'color': '#64748b', 'marginBottom': '6px'}),
                html.Div([
                    html.Div(style={
                        'width': f'{progress_pct}%', 'height': '8px',
                        'borderRadius': '4px', 'backgroundColor': phase_color,
                        'transition': 'width 0.5s',
                    })
                ], style={
                    'width': '100%', 'height': '8px', 'borderRadius': '4px',
                    'backgroundColor': '#e2e8f0',
                })
            ])

            # ── Recent feedback table ──
            recent = store.get_recent_feedback(limit=20)
            if recent:
                table = dash_table.DataTable(
                    columns=[
                        {'name': '时间', 'id': 'created_at'},
                        {'name': '查询', 'id': 'query_text'},
                        {'name': 'Ticket', 'id': 'ticket_id'},
                        {'name': '信号', 'id': 'signal'},
                        {'name': '用户', 'id': 'user_id'},
                    ],
                    data=recent,
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'left', 'padding': '8px', 'fontSize': '13px'},
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f1f5f9'},
                    page_size=10,
                )
            else:
                table = html.P("暂无反馈记录", style={'color': '#94a3b8'})

            # ── Model snapshots ──
            snapshots = store.get_model_snapshots(limit=5)
            if snapshots:
                rows = []
                for s in snapshots:
                    rows.append(html.Tr([
                        html.Td(s.get('created_at', '-'), style={'padding': '6px 12px'}),
                        html.Td(s.get('phase', '-'), style={'padding': '6px 12px'}),
                        html.Td(str(s.get('feedback_count', '-')), style={'padding': '6px 12px'}),
                        html.Td(s.get('metrics', '-'), style={'padding': '6px 12px', 'maxWidth': '300px', 'overflow': 'hidden'}),
                    ]))
                model_table = html.Table([
                    html.Thead(html.Tr([
                        html.Th("时间", style={'padding': '6px 12px'}),
                        html.Th("阶段", style={'padding': '6px 12px'}),
                        html.Th("样本数", style={'padding': '6px 12px'}),
                        html.Th("指标", style={'padding': '6px 12px'}),
                    ]), style={'backgroundColor': '#f1f5f9'}),
                    html.Tbody(rows),
                ], style={'width': '100%', 'borderCollapse': 'collapse', 'border': '1px solid #e2e8f0'})
            else:
                model_table = html.P("暂无模型快照", style={'color': '#94a3b8'})

            # TODO: search_session_tracker module not yet implemented
            total_searches = '-'
            sessions_with_label = '-'
            sessions_with_click = '-'
            label_rate = 0
            mined_pairs = 0
            mined_triplets = 0
            ready = False
            readiness = 0

            readiness_color = '#22c55e' if readiness >= 80 else '#f59e0b' if readiness >= 40 else '#ef4444'

            stat_card = {
                'display': 'inline-block', 'width': '18%', 'margin': '0 1%',
                'padding': '16px', 'borderRadius': '10px',
                'backgroundColor': '#f8fafc', 'border': '1px solid #e2e8f0',
                'textAlign': 'center', 'verticalAlign': 'top',
            }

            search_stats = html.Div([
                # Stat cards row
                html.Div([
                    html.Div([
                        html.H3(str(total_searches), style={'color': '#2563eb', 'margin': '0', 'fontSize': '26px'}),
                        html.P("总搜索次数", style={'color': '#64748b', 'margin': '4px 0 0'})
                    ], style=stat_card),
                    html.Div([
                        html.H3(str(sessions_with_label), style={'color': '#8b5cf6', 'margin': '0', 'fontSize': '26px'}),
                        html.P("已标注会话", style={'color': '#64748b', 'margin': '4px 0 0'})
                    ], style=stat_card),
                    html.Div([
                        html.H3(str(sessions_with_click), style={'color': '#06b6d4', 'margin': '0', 'fontSize': '26px'}),
                        html.P("点击会话", style={'color': '#64748b', 'margin': '4px 0 0'})
                    ], style=stat_card),
                    html.Div([
                        html.H3(f"{mined_pairs}/{mined_triplets}", style={'color': '#f59e0b', 'margin': '0', 'fontSize': '26px'}),
                        html.P("挖掘 pairs/triplets", style={'color': '#64748b', 'margin': '4px 0 0'})
                    ], style=stat_card),
                    html.Div([
                        html.H3(f"{readiness}%", style={'color': readiness_color, 'margin': '0', 'fontSize': '26px'}),
                        html.P("训练准备度", style={'color': '#64748b', 'margin': '4px 0 0'})
                    ], style=stat_card),
                ]),

                # Readiness bar
                html.Div([
                    html.Div(
                        f"标注率 {label_rate:.0%} · 挖掘训练对 {mined_pairs} · {'✅ 可训练' if ready else '⏳ 数据积累中'}",
                        style={'fontSize': '13px', 'color': '#64748b', 'marginBottom': '6px'}
                    ),
                    html.Div([
                        html.Div(style={
                            'width': f'{readiness}%', 'height': '8px',
                            'borderRadius': '4px', 'backgroundColor': readiness_color,
                            'transition': 'width 0.5s',
                        })
                    ], style={
                        'width': '100%', 'height': '8px', 'borderRadius': '4px',
                        'backgroundColor': '#e2e8f0',
                    })
                ], style={'marginTop': '12px'}),

                # Recent searches table
                html.Div([
                    html.H5("最近搜索会话", style={'color': '#34495e', 'marginTop': '20px', 'marginBottom': '10px'}),
                    html.P("暂无数据（session tracker 未实现）", style={'color': '#94a3b8'}),
                ]),
            ])

            return cards, phase_bar, table, model_table, search_stats

        except Exception as exc:
            logger.error(f"Feedback monitor error: {exc}")
            err = html.P(f"加载失败: {exc}", style={'color': '#ef4444'})
            return err, "", err, err, err

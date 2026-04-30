"""
页面组件管理器
统一管理和创建各个子模块的页面组件
Vizion-Lab 设计系统配色
"""

from dash import html, dcc, dash_table
import pandas as pd
from config import NAVIGATION_CONFIG
from dash_common_styles import MAIN_CONTAINER_STYLE, LABEL_STYLE_LIGHT, LABEL_STYLE_DARK
from navigation_manager import nav_manager
import plotly.graph_objs as go
import plotly.express as px

# Vizion-Lab palette
_PRIMARY = '#2266cc'
_SUCCESS = '#29a066'
_WARNING = '#f5a623'
_DESTRUCTIVE = '#e03e3e'
_MUTED = '#737d8e'
_FG = '#131921'
_BORDER = '#dde3eb'
_BG_SURFACE = '#ffffff'
_BG_PAGE = '#f4f6f9'


class PageComponentManager:
    """页面组件管理器"""

    def __init__(self):
        self.theme = 'light'

    def set_theme(self, theme: str):
        """设置主题"""
        self.theme = theme

    def get_active_label_style(self):
        """获取当前主题的标签样式"""
        return LABEL_STYLE_LIGHT if self.theme == 'light' else LABEL_STYLE_DARK

    def _page_heading(self, text: str) -> html.H2:
        """统一的页面标题样式"""
        return html.H2(text, style={
            'color': _FG,
            'marginBottom': '24px',
            'fontWeight': '700',
            'fontSize': '1.375rem',
            'letterSpacing': '-0.02em',
        })

    def _info_card(self, title: str, description: str) -> html.Div:
        """统一的卡片样式"""
        return html.Div([
            html.H4(title, style={
                'color': _FG,
                'fontWeight': '600',
                'marginBottom': '6px',
            }),
            html.P(description, style={
                'color': _MUTED,
                'margin': '0',
                'fontSize': '0.875rem',
                'lineHeight': '1.5',
            }),
        ], style={
            'padding': '20px',
            'backgroundColor': _BG_SURFACE,
            'borderRadius': '12px',
            'border': f'1px solid {_BORDER}',
            'boxShadow': '0 1px 3px rgba(15,23,42,0.06)',
        })

    def create_loading_page(self, message: str = "Loading...") -> html.Div:
        """创建加载页面"""
        return html.Div([
            html.Div([
                html.I(className="fas fa-spinner fa-spin", style={
                    'fontSize': '48px',
                    'color': _PRIMARY,
                }),
                html.H3(message, style={
                    'marginTop': '20px',
                    'color': _MUTED,
                    'fontWeight': '500',
                }),
            ], style={
                'textAlign': 'center',
                'padding': '100px 0',
                'minHeight': '400px',
                'display': 'flex',
                'flexDirection': 'column',
                'justifyContent': 'center',
                'alignItems': 'center',
            })
        ])

    def create_error_page(self, error_message: str = "Page temporarily unavailable") -> html.Div:
        """创建错误页面"""
        return html.Div([
            html.Div([
                html.I(className="fas fa-exclamation-triangle", style={
                    'fontSize': '48px',
                    'color': _DESTRUCTIVE,
                }),
                html.H3("Error", style={
                    'marginTop': '20px',
                    'color': _DESTRUCTIVE,
                    'fontWeight': '600',
                }),
                html.P(error_message, style={
                    'color': _MUTED,
                    'marginTop': '10px',
                }),
                html.Button("Retry", className="btn btn-primary", style={'marginTop': '20px'}),
            ], style={
                'textAlign': 'center',
                'padding': '100px 0',
                'minHeight': '400px',
                'display': 'flex',
                'flexDirection': 'column',
                'justifyContent': 'center',
                'alignItems': 'center',
            })
        ])

    def create_coming_soon_page(self, module_name: str) -> html.Div:
        """创建即将推出页面"""
        return html.Div([
            html.Div([
                html.I(className="fas fa-tools", style={
                    'fontSize': '48px',
                    'color': _WARNING,
                }),
                html.H3(f"{module_name}", style={
                    'marginTop': '20px',
                    'color': _FG,
                    'fontWeight': '700',
                }),
                html.P("This module is under development — stay tuned!", style={
                    'color': _MUTED,
                    'marginTop': '10px',
                    'fontSize': '0.9rem',
                }),
                html.Div([
                    html.I(className="fas fa-clock", style={'marginRight': '8px', 'color': _MUTED}),
                    html.Span("Coming soon", style={'color': _MUTED}),
                ], style={'marginTop': '20px', 'fontSize': '0.85rem'}),
            ], style={
                'textAlign': 'center',
                'padding': '100px 0',
                'minHeight': '400px',
                'display': 'flex',
                'flexDirection': 'column',
                'justifyContent': 'center',
                'alignItems': 'center',
            })
        ])

    def create_defect_coverage_page(self) -> html.Div:
        """创建缺陷覆盖率页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-defect-coverage'),
            self._page_heading("Defect Coverage Analysis"),
            self._info_card("Coverage Overview", "Coverage statistics across projects and modules"),
            html.Div([
                dcc.Graph(
                    figure=go.Figure().add_annotation(
                        text="Defect coverage chart placeholder",
                        x=0.5, y=0.5,
                        xref="paper", yref="paper",
                        showarrow=False,
                        font=dict(size=14, color=_MUTED),
                    ).update_layout(
                        xaxis=dict(visible=False),
                        yaxis=dict(visible=False),
                        plot_bgcolor='#ffffff',
                        paper_bgcolor='#ffffff',
                        height=400,
                        margin=dict(l=20, r=20, t=20, b=20),
                    )
                )
            ], className='chart-container', style={'marginTop': '30px'}),
        ])

    def create_defect_longrunner_page(self) -> html.Div:
        """创建缺陷长期跟踪页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-defect-longrunner'),
            self._page_heading("Defect Long-Running Tracker"),
            self._info_card("Long-Running Defect Monitor", "Track long-unresolved defects and trend analysis"),
        ])

    def create_defect_matrix_page(self) -> html.Div:
        """创建缺陷矩阵分析页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-defect-matrix'),
            self._page_heading("Defect Matrix Analysis"),
            self._info_card("Defect Distribution Matrix", "Defect distribution across multiple dimensions"),
        ])

    def create_defect_trend_page(self) -> html.Div:
        """创建缺陷趋势分析页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-defect-trend'),
            self._page_heading("Defect Trend Analysis"),
            self._info_card("Defect Trend Monitor", "Trend analysis of defect count, severity, and resolution rate"),
        ])

    def create_defect_map_page(self) -> html.Div:
        """创建缺陷地图页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-defect-map'),
            self._page_heading("Defect Map"),
            self._info_card("Defect Distribution Map", "Visualize defect distribution across system modules"),
        ])

    def create_word_cloud_page(self) -> html.Div:
        """创建词云分析页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-word-cloud'),
            self._page_heading("Word Cloud Analysis"),
            self._info_card("Defect Keyword Analysis", "Extract keywords from defect descriptions to generate word clouds"),
        ])

    def create_risk_analysis_page(self) -> html.Div:
        """创建风险分析页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-risk-analysis'),
            self._page_heading("Risk Analysis"),
            self._info_card("Project Risk Assessment", "Risk assessment and early warning based on defect data"),
        ])

    def create_data_dashboard_page(self) -> html.Div:
        """创建数据大屏页面"""
        return html.Div([
            html.Div([
                html.H1("Data Dashboard", style={
                    'textAlign': 'center',
                    'color': '#fff',
                    'marginBottom': '30px',
                    'fontSize': '2rem',
                    'fontWeight': '700',
                    'letterSpacing': '-0.02em',
                }),

                # KPI cards — vizion-lab style
                html.Div([
                    html.Div([
                        html.H3("12,345", style={'color': '#93bbfc', 'fontSize': '2rem', 'margin': '0',
                                                  'fontFamily': "'JetBrains Mono', monospace",
                                                  'fontWeight': '700'}),
                        html.P("Total Defects", style={'color': '#8899aa', 'margin': '6px 0 0', 'fontSize': '0.8rem',
                                                       'fontWeight': '600'}),
                    ], style={
                        'backgroundColor': 'rgba(255,255,255,0.06)',
                        'padding': '24px',
                        'borderRadius': '12px',
                        'textAlign': 'center',
                        'width': '23%',
                        'display': 'inline-block',
                        'margin': '0 1%',
                        'border': '1px solid rgba(255,255,255,0.08)',
                    }),

                    html.Div([
                        html.H3("94.7%", style={'color': '#7ce0a8', 'fontSize': '2rem', 'margin': '0',
                                                 'fontFamily': "'JetBrains Mono', monospace",
                                                 'fontWeight': '700'}),
                        html.P("Resolution Rate", style={'color': '#8899aa', 'margin': '6px 0 0', 'fontSize': '0.8rem',
                                                          'fontWeight': '600'}),
                    ], style={
                        'backgroundColor': 'rgba(255,255,255,0.06)',
                        'padding': '24px',
                        'borderRadius': '12px',
                        'textAlign': 'center',
                        'width': '23%',
                        'display': 'inline-block',
                        'margin': '0 1%',
                        'border': '1px solid rgba(255,255,255,0.08)',
                    }),

                    html.Div([
                        html.H3("156", style={'color': '#f09090', 'fontSize': '2rem', 'margin': '0',
                                               'fontFamily': "'JetBrains Mono', monospace",
                                               'fontWeight': '700'}),
                        html.P("Critical Defects", style={'color': '#8899aa', 'margin': '6px 0 0', 'fontSize': '0.8rem',
                                                           'fontWeight': '600'}),
                    ], style={
                        'backgroundColor': 'rgba(255,255,255,0.06)',
                        'padding': '24px',
                        'borderRadius': '12px',
                        'textAlign': 'center',
                        'width': '23%',
                        'display': 'inline-block',
                        'margin': '0 1%',
                        'border': '1px solid rgba(255,255,255,0.08)',
                    }),

                    html.Div([
                        html.H3("89.2%", style={'color': '#f5c76b', 'fontSize': '2rem', 'margin': '0',
                                                 'fontFamily': "'JetBrains Mono', monospace",
                                                 'fontWeight': '700'}),
                        html.P("Test Coverage", style={'color': '#8899aa', 'margin': '6px 0 0', 'fontSize': '0.8rem',
                                                        'fontWeight': '600'}),
                    ], style={
                        'backgroundColor': 'rgba(255,255,255,0.06)',
                        'padding': '24px',
                        'borderRadius': '12px',
                        'textAlign': 'center',
                        'width': '23%',
                        'display': 'inline-block',
                        'margin': '0 1%',
                        'border': '1px solid rgba(255,255,255,0.08)',
                    }),
                ], style={'marginBottom': '40px'}),

                # Charts
                html.Div([
                    html.Div([
                        html.H4("Defect Trend", style={
                            'color': '#fff',
                            'marginBottom': '20px',
                            'fontWeight': '600',
                            'fontSize': '0.95rem',
                        }),
                        dcc.Graph(
                            figure=go.Figure().add_trace(
                                go.Scatter(
                                    x=list(range(12)),
                                    y=[100, 120, 130, 110, 140, 135, 145, 150, 160, 155, 165, 170],
                                    mode='lines+markers',
                                    line=dict(color=_PRIMARY, width=2.5),
                                    marker=dict(size=5),
                                )
                            ).update_layout(
                                plot_bgcolor='rgba(0,0,0,0)',
                                paper_bgcolor='rgba(0,0,0,0)',
                                font=dict(color='#8899aa', family="'DM Sans', sans-serif", size=11),
                                xaxis=dict(gridcolor='rgba(255,255,255,0.06)', showgrid=False),
                                yaxis=dict(gridcolor='rgba(255,255,255,0.06)'),
                                height=300,
                                margin=dict(l=40, r=20, t=20, b=40),
                            )
                        )
                    ], style={
                        'width': '48%',
                        'display': 'inline-block',
                        'backgroundColor': 'rgba(255,255,255,0.06)',
                        'padding': '20px',
                        'borderRadius': '12px',
                        'marginRight': '2%',
                        'border': '1px solid rgba(255,255,255,0.08)',
                    }),

                    html.Div([
                        html.H4("Project Distribution", style={
                            'color': '#fff',
                            'marginBottom': '20px',
                            'fontWeight': '600',
                            'fontSize': '0.95rem',
                        }),
                        dcc.Graph(
                            figure=go.Figure().add_trace(
                                go.Pie(
                                    labels=['IDC', 'MGU', 'App', 'RSU'],
                                    values=[45, 25, 20, 10],
                                    marker=dict(colors=[_PRIMARY, _SUCCESS, _WARNING, _DESTRUCTIVE]),
                                )
                            ).update_layout(
                                plot_bgcolor='rgba(0,0,0,0)',
                                paper_bgcolor='rgba(0,0,0,0)',
                                font=dict(color='#8899aa', family="'DM Sans', sans-serif", size=11),
                                height=300,
                                margin=dict(l=20, r=20, t=20, b=20),
                                showlegend=True,
                            )
                        )
                    ], style={
                        'width': '48%',
                        'display': 'inline-block',
                        'backgroundColor': 'rgba(255,255,255,0.06)',
                        'padding': '20px',
                        'borderRadius': '12px',
                        'marginLeft': '2%',
                        'border': '1px solid rgba(255,255,255,0.08)',
                    }),
                ]),

            ], style={
                'background': 'linear-gradient(135deg, #171f2b 0%, #1a2540 100%)',
                'minHeight': '100vh',
                'padding': '40px',
                'margin': '-20px',
                'marginTop': '-110px',
            })
        ])

    def create_feedback_monitor_page(self) -> html.Div:
        """创建反馈学习监控页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-feedback-monitor'),
            self._page_heading("Feedback Learning Monitor"),

            html.Div(id='feedback-monitor-cards', children=[
                html.P("Loading...", style={'color': _MUTED})
            ]),

            html.Div(id='feedback-monitor-phase', style={'marginTop': '20px'}),

            html.Div([
                html.H4("Recent Feedback", style={
                    'color': _FG,
                    'marginTop': '30px',
                    'marginBottom': '15px',
                    'fontWeight': '600',
                }),
                html.Div(id='feedback-monitor-table', children=[
                    html.P("No feedback records", style={'color': _MUTED})
                ]),
            ]),

            html.Div([
                html.H4("Model Snapshot History", style={
                    'color': _FG,
                    'marginTop': '30px',
                    'marginBottom': '15px',
                    'fontWeight': '600',
                }),
                html.Div(id='feedback-monitor-models', children=[
                    html.P("No model snapshots", style={'color': _MUTED})
                ]),
            ]),

            html.Div([
                html.H4("Search Session Stats", style={
                    'color': _FG,
                    'marginTop': '30px',
                    'marginBottom': '15px',
                    'fontWeight': '600',
                }),
                html.Div(id='feedback-monitor-search-stats', children=[
                    html.P("Loading...", style={'color': _MUTED})
                ]),
            ]),

            dcc.Interval(id='feedback-monitor-interval', interval=30_000, n_intervals=0),
        ])

    def get_page_component(self, nav_id: str) -> html.Div:
        """根据导航ID获取页面组件"""
        page_map = {
            'tab-defect-coverage': self.create_defect_coverage_page,
            'tab-defect-longrunner': self.create_defect_longrunner_page,
            'tab-defect-matrix': self.create_defect_matrix_page,
            'tab-defect-trend': self.create_defect_trend_page,
            'tab-defect-map': self.create_defect_map_page,
            'tab-word-cloud': self.create_word_cloud_page,
            'tab-risk-analysis': self.create_risk_analysis_page,
            'tab-data-dashboard': self.create_data_dashboard_page,
            'tab-testing-efficiency': self.create_testing_efficiency_page,
            'tab-feedback-monitor': self.create_feedback_monitor_page,
        }

        if nav_id in page_map:
            try:
                return page_map[nav_id]()
            except Exception as e:
                print(f"Error creating page {nav_id}: {e}")
                return self.create_error_page(f"Error creating {nav_id}")
        else:
            nav_item = nav_manager.get_nav_item_by_id(nav_id)
            module_name = nav_item['label'] if nav_item else "Unknown"
            return self.create_coming_soon_page(module_name)

# 创建全局页面组件管理器实例
page_manager = PageComponentManager()

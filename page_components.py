"""
页面组件管理器
统一管理和创建各个子模块的页面组件
"""

from dash import html, dcc, dash_table
import pandas as pd
from config import NAVIGATION_CONFIG
from dash_common_styles import MAIN_CONTAINER_STYLE, LABEL_STYLE_LIGHT, LABEL_STYLE_DARK
from navigation_manager import nav_manager
import plotly.graph_objs as go
import plotly.express as px

class PageComponentManager:
    """页面组件管理器"""
    
    def __init__(self):
        self.theme = 'light'  # 默认主题
        
    def set_theme(self, theme: str):
        """设置主题"""
        self.theme = theme
        
    def get_active_label_style(self):
        """获取当前主题的标签样式"""
        return LABEL_STYLE_LIGHT if self.theme == 'light' else LABEL_STYLE_DARK
    
    def create_loading_page(self, message: str = "正在加载...") -> html.Div:
        """创建加载页面"""
        return html.Div([
            html.Div([
                html.I(className="fas fa-spinner fa-spin", style={'fontSize': '48px', 'color': '#3498db'}),
                html.H3(message, style={'marginTop': '20px', 'color': '#666'})
            ], style={
                'textAlign': 'center',
                'padding': '100px 0',
                'minHeight': '400px',
                'display': 'flex',
                'flexDirection': 'column',
                'justifyContent': 'center',
                'alignItems': 'center'
            })
        ])
    
    def create_error_page(self, error_message: str = "页面暂时无法加载") -> html.Div:
        """创建错误页面"""
        return html.Div([
            html.Div([
                html.I(className="fas fa-exclamation-triangle", style={'fontSize': '48px', 'color': '#e74c3c'}),
                html.H3("出现错误", style={'marginTop': '20px', 'color': '#e74c3c'}),
                html.P(error_message, style={'color': '#666', 'marginTop': '10px'}),
                html.Button("重新尝试", className="btn btn-primary", style={'marginTop': '20px'})
            ], style={
                'textAlign': 'center',
                'padding': '100px 0',
                'minHeight': '400px',
                'display': 'flex',
                'flexDirection': 'column',
                'justifyContent': 'center',
                'alignItems': 'center'
            })
        ])
    
    def create_coming_soon_page(self, module_name: str) -> html.Div:
        """创建即将推出页面"""
        return html.Div([
            html.Div([
                html.I(className="fas fa-tools", style={'fontSize': '48px', 'color': '#f39c12'}),
                html.H3(f"{module_name} 模块", style={'marginTop': '20px', 'color': '#333'}),
                html.P("该功能正在开发中，敬请期待！", style={'color': '#666', 'marginTop': '10px', 'fontSize': '16px'}),
                html.Div([
                    html.I(className="fas fa-clock", style={'marginRight': '8px'}),
                    html.Span("预计完成时间：即将推出")
                ], style={'color': '#999', 'marginTop': '20px'})
            ], style={
                'textAlign': 'center',
                'padding': '100px 0',
                'minHeight': '400px',
                'display': 'flex',
                'flexDirection': 'column',
                'justifyContent': 'center',
                'alignItems': 'center'
            })
        ])
    
    def create_defect_coverage_page(self) -> html.Div:
        """创建缺陷覆盖率页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-defect-coverage'),
            html.H2("缺陷覆盖率分析", style={'color': '#2c3e50', 'marginBottom': '30px'}),
            
            # 这里可以集成defect_coverage.py的内容
            html.Div([
                html.Div([
                    html.H4("覆盖率概览", style={'color': '#34495e'}),
                    html.P("显示各项目、模块的缺陷覆盖率统计", style={'color': '#666'})
                ], style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px'})
            ]),
            
            # 占位图表
            html.Div([
                dcc.Graph(
                    figure=go.Figure().add_annotation(
                        text="缺陷覆盖率图表将在此显示",
                        x=0.5, y=0.5,
                        xref="paper", yref="paper",
                        showarrow=False,
                        font=dict(size=16, color="gray")
                    ).update_layout(
                        xaxis=dict(visible=False),
                        yaxis=dict(visible=False),
                        plot_bgcolor='white',
                        height=400
                    )
                )
            ], style={'marginTop': '30px'})
        ])
    
    def create_defect_longrunner_page(self) -> html.Div:
        """创建缺陷长期跟踪页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-defect-longrunner'),
            html.H2("缺陷长期跟踪分析", style={'color': '#2c3e50', 'marginBottom': '30px'}),
            
            html.Div([
                html.Div([
                    html.H4("长期运行缺陷监控", style={'color': '#34495e'}),
                    html.P("跟踪长期未解决的缺陷和趋势分析", style={'color': '#666'})
                ], style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px'})
            ])
        ])
    
    def create_defect_matrix_page(self) -> html.Div:
        """创建缺陷矩阵分析页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-defect-matrix'),
            html.H2("缺陷矩阵分析", style={'color': '#2c3e50', 'marginBottom': '30px'}),
            
            html.Div([
                html.Div([
                    html.H4("缺陷分布矩阵", style={'color': '#34495e'}),
                    html.P("展示缺陷在不同维度的分布情况", style={'color': '#666'})
                ], style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px'})
            ])
        ])
    
    def create_defect_trend_page(self) -> html.Div:
        """创建缺陷趋势分析页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-defect-trend'),
            html.H2("缺陷趋势分析", style={'color': '#2c3e50', 'marginBottom': '30px'}),
            
            html.Div([
                html.Div([
                    html.H4("缺陷趋势监控", style={'color': '#34495e'}),
                    html.P("分析缺陷数量、严重性、解决率的时间趋势", style={'color': '#666'})
                ], style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px'})
            ])
        ])
    
    def create_defect_map_page(self) -> html.Div:
        """创建缺陷地图页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-defect-map'),
            html.H2("缺陷地图", style={'color': '#2c3e50', 'marginBottom': '30px'}),
            
            html.Div([
                html.Div([
                    html.H4("缺陷分布地图", style={'color': '#34495e'}),
                    html.P("可视化展示缺陷在系统各模块的分布", style={'color': '#666'})
                ], style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px'})
            ])
        ])
    
    def create_word_cloud_page(self) -> html.Div:
        """创建词云分析页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-word-cloud'),
            html.H2("词云分析", style={'color': '#2c3e50', 'marginBottom': '30px'}),
            
            html.Div([
                html.Div([
                    html.H4("缺陷关键词分析", style={'color': '#34495e'}),
                    html.P("从缺陷描述中提取关键词，生成词云图", style={'color': '#666'})
                ], style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px'})
            ])
        ])
    
    def create_risk_analysis_page(self) -> html.Div:
        """创建风险分析页面"""
        return html.Div([
            nav_manager.create_breadcrumb('tab-risk-analysis'),
            html.H2("风险分析", style={'color': '#2c3e50', 'marginBottom': '30px'}),
            
            html.Div([
                html.Div([
                    html.H4("项目风险评估", style={'color': '#34495e'}),
                    html.P("基于缺陷数据进行项目风险评估和预警", style={'color': '#666'})
                ], style={'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '8px'})
            ])
        ])
    
    def create_data_dashboard_page(self) -> html.Div:
        """创建数据大屏页面"""
        return html.Div([
            html.Div([
                html.H1("数据大屏", style={
                    'textAlign': 'center',
                    'color': 'white',
                    'marginBottom': '30px',
                    'fontSize': '36px'
                }),
                
                # KPI卡片区域
                html.Div([
                    html.Div([
                        html.H3("12,345", style={'color': '#3498db', 'fontSize': '32px', 'margin': '0'}),
                        html.P("总缺陷数", style={'color': '#bdc3c7', 'margin': '5px 0'})
                    ], style={
                        'backgroundColor': 'rgba(255,255,255,0.1)',
                        'padding': '20px',
                        'borderRadius': '10px',
                        'textAlign': 'center',
                        'width': '23%',
                        'display': 'inline-block',
                        'margin': '0 1%'
                    }),
                    
                    html.Div([
                        html.H3("94.7%", style={'color': '#2ecc71', 'fontSize': '32px', 'margin': '0'}),
                        html.P("解决率", style={'color': '#bdc3c7', 'margin': '5px 0'})
                    ], style={
                        'backgroundColor': 'rgba(255,255,255,0.1)',
                        'padding': '20px',
                        'borderRadius': '10px',
                        'textAlign': 'center',
                        'width': '23%',
                        'display': 'inline-block',
                        'margin': '0 1%'
                    }),
                    
                    html.Div([
                        html.H3("156", style={'color': '#e74c3c', 'fontSize': '32px', 'margin': '0'}),
                        html.P("严重缺陷", style={'color': '#bdc3c7', 'margin': '5px 0'})
                    ], style={
                        'backgroundColor': 'rgba(255,255,255,0.1)',
                        'padding': '20px',
                        'borderRadius': '10px',
                        'textAlign': 'center',
                        'width': '23%',
                        'display': 'inline-block',
                        'margin': '0 1%'
                    }),
                    
                    html.Div([
                        html.H3("89.2%", style={'color': '#f39c12', 'fontSize': '32px', 'margin': '0'}),
                        html.P("测试覆盖率", style={'color': '#bdc3c7', 'margin': '5px 0'})
                    ], style={
                        'backgroundColor': 'rgba(255,255,255,0.1)',
                        'padding': '20px',
                        'borderRadius': '10px',
                        'textAlign': 'center',
                        'width': '23%',
                        'display': 'inline-block',
                        'margin': '0 1%'
                    })
                ], style={'marginBottom': '40px'}),
                
                # 图表区域
                html.Div([
                    html.Div([
                        html.H4("缺陷趋势", style={'color': 'white', 'marginBottom': '20px'}),
                        dcc.Graph(
                            figure=go.Figure().add_trace(
                                go.Scatter(x=list(range(12)), y=[100, 120, 130, 110, 140, 135, 145, 150, 160, 155, 165, 170],
                                          mode='lines+markers', line=dict(color='#3498db', width=3))
                            ).update_layout(
                                plot_bgcolor='rgba(0,0,0,0)',
                                paper_bgcolor='rgba(0,0,0,0)',
                                font=dict(color='white'),
                                xaxis=dict(gridcolor='rgba(255,255,255,0.2)'),
                                yaxis=dict(gridcolor='rgba(255,255,255,0.2)'),
                                height=300
                            )
                        )
                    ], style={
                        'width': '48%',
                        'display': 'inline-block',
                        'backgroundColor': 'rgba(255,255,255,0.1)',
                        'padding': '20px',
                        'borderRadius': '10px',
                        'marginRight': '2%'
                    }),
                    
                    html.Div([
                        html.H4("项目分布", style={'color': 'white', 'marginBottom': '20px'}),
                        dcc.Graph(
                            figure=go.Figure().add_trace(
                                go.Pie(labels=['IDC', 'MGU', 'App', 'RSU'], values=[45, 25, 20, 10],
                                      marker=dict(colors=['#3498db', '#2ecc71', '#f39c12', '#e74c3c']))
                            ).update_layout(
                                plot_bgcolor='rgba(0,0,0,0)',
                                paper_bgcolor='rgba(0,0,0,0)',
                                font=dict(color='white'),
                                height=300
                            )
                        )
                    ], style={
                        'width': '48%',
                        'display': 'inline-block',
                        'backgroundColor': 'rgba(255,255,255,0.1)',
                        'padding': '20px',
                        'borderRadius': '10px',
                        'marginLeft': '2%'
                    })
                ])
                
            ], style={
                'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                'minHeight': '100vh',
                'padding': '40px',
                'margin': '-20px',  # 抵消父容器的padding
                'marginTop': '-110px'  # 抵消顶部margin
            })
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
            'tab-testing-efficiency': self.create_testing_efficiency_page
        }
        
        if nav_id in page_map:
            try:
                return page_map[nav_id]()
            except Exception as e:
                print(f"Error creating page {nav_id}: {e}")
                return self.create_error_page(f"创建 {nav_id} 页面时出错")
        else:
            # 对于未实现的页面，显示即将推出
            nav_item = nav_manager.get_nav_item_by_id(nav_id)
            module_name = nav_item['label'] if nav_item else "未知模块"
            return self.create_coming_soon_page(module_name)

# 创建全局页面组件管理器实例
page_manager = PageComponentManager()
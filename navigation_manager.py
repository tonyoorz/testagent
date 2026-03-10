"""
导航管理器模块
统一管理导航栏配置、页面路由和模块加载
"""

from dash import html, dcc
from config import NAVIGATION_CONFIG, SUBMODULES_CONFIG
import importlib
from typing import List, Dict, Any, Optional

class NavigationManager:
    """导航管理器类"""
    
    def __init__(self):
        self.nav_items = NAVIGATION_CONFIG
        self.submodules = SUBMODULES_CONFIG
        self.registered_pages = {}
        
    def get_enabled_nav_items(self) -> List[Dict[str, Any]]:
        """获取启用的导航项"""
        return [item for item in self.nav_items if item.get('enabled', True)]
    
    def create_sidebar_nav(self) -> html.Div:
        """创建可展开/隐藏的侧边导航栏"""
        enabled_items = self.get_enabled_nav_items()
        
        return html.Div([
            # 导航栏切换按钮
            html.Button(
                [html.I(className="fas fa-bars", style={'fontSize': '18px'})],
                id='nav-toggle-btn',
                className='nav-toggle-btn',
                style={
                    'position': 'fixed',
                    'top': '20px',
                    'left': '290px',
                    'zIndex': '1001',
                    'backgroundColor': '#28a745',
                    'color': 'white',
                    'border': 'none',
                    'padding': '12px',
                    'borderRadius': '6px',
                    'cursor': 'pointer',
                    'fontSize': '16px',
                    'boxShadow': '0 2px 4px rgba(0,0,0,0.3)',
                    'transition': 'all 0.3s ease'
                }
            ),
            
            # 边缘条
            html.Div([
                html.Button(
                    [html.I(className="fas fa-chevron-right", style={'fontSize': '12px', 'color': 'white'})],
                    id='nav-edge-toggle-btn',
                    style={
                        'position': 'absolute',
                        'top': '50%',
                        'left': '50%',
                        'transform': 'translate(-50%, -50%)',
                        'backgroundColor': 'transparent',
                        'border': 'none',
                        'cursor': 'pointer',
                        'padding': '8px',
                        'borderRadius': '50%',
                        'transition': 'background-color 0.3s ease'
                    }
                )
            ],
            id='nav-edge-bar',
            style={
                'position': 'fixed',
                'top': '90px',
                'left': '-30px',
                'width': '30px',
                'height': 'calc(100vh - 90px)',
                'backgroundColor': '#2c3e50',
                'zIndex': '999',
                'transition': 'left 0.3s ease',
                'boxShadow': '2px 0 5px rgba(0,0,0,0.3)',
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'center'
            }),
            
            # 侧边导航栏
            html.Div([
                # 导航栏头部
                html.Div([
                    html.H3("导航", style={
                        'color': 'white',
                        'margin': '0',
                        'padding': '20px',
                        'borderBottom': '1px solid #444',
                        'fontSize': '18px'
                    }),
                    html.Button(
                        [html.I(className="fas fa-times", style={'fontSize': '16px'})],
                        id='nav-close-btn',
                        style={
                            'position': 'absolute',
                            'top': '15px',
                            'right': '15px',
                            'backgroundColor': 'transparent',
                            'color': 'white',
                            'border': 'none',
                            'cursor': 'pointer',
                            'padding': '5px',
                            'borderRadius': '3px'
                        }
                    )
                ], style={'position': 'relative'}),
                
                # 导航项目
                html.Div([
                    html.Div([
                        html.I(className=item['icon'], style={'marginRight': '12px', 'width': '20px'}),
                        html.Span(item['label'])
                    ], 
                    id=f"nav-{item['id']}", 
                    className='nav-item',
                    style={
                        'padding': '15px 20px',
                        'cursor': 'pointer',
                        'borderLeft': '4px solid transparent',
                        'color': 'white',
                        'transition': 'all 0.3s ease',
                        'display': 'flex',
                        'alignItems': 'center',
                        'fontSize': '14px'
                    }) for item in enabled_items
                ])
            ], 
            id='sidebar-nav',
            className='sidebar-nav',
            style={
                'position': 'fixed',
                'top': '90px',
                'left': '0px',
                'width': '280px',
                'height': 'calc(100vh - 90px)',
                'backgroundColor': '#2c3e50',
                'zIndex': '1000',
                'transition': 'left 0.3s ease',
                'boxShadow': '2px 0 5px rgba(0,0,0,0.3)',
                'overflowY': 'auto'
            }),
            
            # 遮罩层
            html.Div(
                id='nav-overlay',
                style={
                    'position': 'fixed',
                    'top': '0',
                    'left': '0',
                    'width': '100%',
                    'height': '100%',
                    'backgroundColor': 'rgba(0,0,0,0.5)',
                    'zIndex': '999',
                    'display': 'none'
                }
            ),
            
            # 存储当前选中的导航项
            dcc.Store(id='current-nav-item', data='tab-defect-status'),
            dcc.Store(id='nav-open-state', data=True)
        ])
    
    def get_nav_inputs_outputs(self):
        """动态生成导航栏的输入输出配置"""
        enabled_items = self.get_enabled_nav_items()
        
        # 生成输入配置
        inputs = []
        for item in enabled_items:
            inputs.append(f"Input('nav-{item['id']}', 'n_clicks')")
        
        # 生成输出配置
        outputs = []
        for item in enabled_items:
            outputs.append(f"Output('nav-{item['id']}', 'style')")
            
        return inputs, outputs
    
    def get_nav_item_by_id(self, nav_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取导航项"""
        for item in self.nav_items:
            if item['id'] == nav_id:
                return item
        return None
    
    def register_page_component(self, nav_id: str, component_function):
        """注册页面组件"""
        self.registered_pages[nav_id] = component_function
    
    def get_page_component(self, nav_id: str):
        """获取页面组件"""
        return self.registered_pages.get(nav_id)
    
    def load_submodule_component(self, module_name: str):
        """动态加载子模块组件"""
        try:
            if module_name in self.submodules:
                module_config = self.submodules[module_name]
                module_path = module_config['module_path'].replace('.py', '')
                
                # 动态导入模块
                module = importlib.import_module(module_path)
                
                # 获取组件函数
                component_function = getattr(module, module_config['component_function'], None)
                
                if component_function:
                    return component_function
                else:
                    print(f"Warning: Component function {module_config['component_function']} not found in {module_path}")
                    return None
                    
        except ImportError as e:
            print(f"Error importing module {module_name}: {e}")
            return None
        except Exception as e:
            print(f"Error loading component from {module_name}: {e}")
            return None
    
    def create_nav_mapping(self) -> Dict[str, str]:
        """创建导航映射"""
        mapping = {}
        for item in self.nav_items:
            nav_key = f"nav-{item['id']}"
            mapping[nav_key] = item['id']
        return mapping
    
    def get_default_nav_item(self) -> str:
        """获取默认导航项"""
        enabled_items = self.get_enabled_nav_items()
        if enabled_items:
            return enabled_items[0]['id']
        return 'tab-defect-status'
    
    def create_breadcrumb(self, current_nav: str) -> html.Div:
        """创建面包屑导航"""
        nav_item = self.get_nav_item_by_id(current_nav)
        if not nav_item:
            return html.Div()
            
        return html.Div([
            html.Span("首页", style={'color': '#666', 'marginRight': '8px'}),
            html.I(className="fas fa-chevron-right", style={'fontSize': '12px', 'color': '#999', 'marginRight': '8px'}),
            html.Span(nav_item['label'], style={'color': '#333', 'fontWeight': 'bold'})
        ], style={
            'padding': '10px 0',
            'borderBottom': '1px solid #eee',
            'marginBottom': '20px'
        })
    
    def get_nav_statistics(self) -> Dict[str, int]:
        """获取导航统计信息"""
        total_items = len(self.nav_items)
        enabled_items = len(self.get_enabled_nav_items())
        disabled_items = total_items - enabled_items
        
        return {
            'total': total_items,
            'enabled': enabled_items,
            'disabled': disabled_items
        }

# 创建全局导航管理器实例
nav_manager = NavigationManager() 
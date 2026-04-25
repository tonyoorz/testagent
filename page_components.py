"""
页面组件管理器（Dash 依赖已移除）
统一管理和创建各个子模块的页面组件
"""

import pandas as pd
from config import NAVIGATION_CONFIG


class PageComponentManager:
    """页面组件管理器（存根 — 原 Dash UI 组件已移除）"""

    def __init__(self):
        self.theme = 'light'

    def set_theme(self, theme: str):
        self.theme = theme

    def get_page_component(self, nav_id: str):
        """根据导航 ID 获取页面组件（存根）"""
        return None


page_manager = PageComponentManager()

"""
导航管理器模块（Dash 依赖已移除）
统一管理导航栏配置、页面路由和模块加载
"""

from config import NAVIGATION_CONFIG, SUBMODULES_CONFIG
import importlib
from typing import List, Dict, Any, Optional


class NavigationManager:
    """导航管理器类（Dash UI 部分已移除）"""

    def __init__(self):
        self.nav_items = NAVIGATION_CONFIG
        self.submodules = SUBMODULES_CONFIG
        self.registered_pages = {}

    def get_enabled_nav_items(self) -> List[Dict[str, Any]]:
        return [item for item in self.nav_items if item.get('enabled', True)]

    def get_nav_item_by_id(self, nav_id: str) -> Optional[Dict[str, Any]]:
        for item in self.nav_items:
            if item['id'] == nav_id:
                return item
        return None

    def register_page_component(self, nav_id: str, component_function):
        self.registered_pages[nav_id] = component_function

    def get_page_component(self, nav_id: str):
        return self.registered_pages.get(nav_id)

    def load_submodule_component(self, module_name: str):
        try:
            if module_name in self.submodules:
                module_config = self.submodules[module_name]
                module_path = module_config['module_path'].replace('.py', '')
                module = importlib.import_module(module_path)
                component_function = getattr(module, module_config['component_function'], None)
                return component_function
        except ImportError as e:
            print(f"Error importing module {module_name}: {e}")
            return None
        except Exception as e:
            print(f"Error loading component from {module_name}: {e}")
            return None

    def create_nav_mapping(self) -> Dict[str, str]:
        return {f"nav-{item['id']}": item['id'] for item in self.nav_items}

    def get_default_nav_item(self) -> str:
        enabled_items = self.get_enabled_nav_items()
        if enabled_items:
            return enabled_items[0]['id']
        return 'tab-defect-status'

    def get_nav_statistics(self) -> Dict[str, int]:
        total_items = len(self.nav_items)
        enabled_items = len(self.get_enabled_nav_items())
        return {'total': total_items, 'enabled': enabled_items, 'disabled': total_items - enabled_items}


nav_manager = NavigationManager()

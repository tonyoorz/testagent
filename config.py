# 应用配置
import os
from datetime import timedelta

class Config:
    # 基础配置
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    HOST = os.environ.get('HOST', '0.0.0.0')  # 允许局域网访问
    PORT = int(os.environ.get('PORT', 8051))
    
    # 数据缓存配置
    ENABLE_CACHE = os.environ.get('ENABLE_CACHE', 'True').lower() == 'true'
    CACHE_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', 3600))  # 1小时
    
    # Redis配置（可选）
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    # 数据文件路径
    DATA_DIR = os.environ.get('DATA_DIR', 'defect')
    MASTER_DATA_FILE = os.path.join(DATA_DIR, '2025_defect_master.json')
    DEFECT_DATA_PATTERN = os.path.join(DATA_DIR, '2025_defect.json')
    
    # 性能优化配置
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', 4))
    CHUNK_SIZE = int(os.environ.get('CHUNK_SIZE', 1000))
    
    # 分页配置
    DEFAULT_PAGE_SIZE = int(os.environ.get('DEFAULT_PAGE_SIZE', 50))
    MAX_PAGE_SIZE = int(os.environ.get('MAX_PAGE_SIZE', 200))

class DevelopmentConfig(Config):
    DEBUG = True
    ENABLE_CACHE = False

class ProductionConfig(Config):
    DEBUG = False
    ENABLE_CACHE = True
    
# 配置字典
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

# 现有的数据库配置
DATABASE_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'root',
    'database': 'test_management',
    'charset': 'utf8mb4'
}

# 缓存配置
CACHE_CONFIG = {
    'default_timeout': 300,  # 5分钟
    'cache_dir': 'cache',
    'max_size': 1000
}

# 应用配置
APP_CONFIG = {
    'main_app': {
        'name': 'DTSV测试与缺陷数据分析仪表板',
        'port': 8051,
        'debug': True,
        'host': '0.0.0.0'
    }
}

# 新增：模块化导航栏配置
NAVIGATION_CONFIG = [
    {
        'id': 'tab-defect-status',
        'label': '缺陷状态分析',
        'icon': 'fas fa-chart-bar',
        'component': 'defect_status_page',
        'enabled': True
    },
    {
        'id': 'tab-project-analysis',
        'label': '项目分析',
        'icon': 'fas fa-project-diagram',
        'component': 'project_analysis_page',
        'enabled': True
    },
    {
        'id': 'tab-defect-high-runner',
        'label': '缺陷高频分析',
        'icon': 'fas fa-tachometer-alt',
        'component': 'defect_high_runner_page',
        'enabled': True
    },
    {
        'id': 'tab-testing-team',
        'label': '测试团队分析',
        'icon': 'fas fa-users',
        'component': 'testing_team_page',
        'enabled': True
    },

    {
        'id': 'tab-test-coverage',
        'label': '测试覆盖率分析',
        'icon': 'fas fa-tasks',
        'component': 'test_coverage_page',
        'enabled': True
    },
    {
        'id': 'tab-defect-coverage',
        'label': '缺陷覆盖率',
        'icon': 'fas fa-shield-alt',
        'component': 'defect_coverage_page',
        'enabled': True
    },
    {
        'id': 'tab-defect-longrunner',
        'label': '缺陷长期跟踪',
        'icon': 'fas fa-clock',
        'component': 'defect_longrunner_page',
        'enabled': True
    },
    {
        'id': 'tab-defect-matrix',
        'label': '缺陷矩阵分析',
        'icon': 'fas fa-table',
        'component': 'defect_matrix_page',
        'enabled': True
    },
    {
        'id': 'tab-defect-trend',
        'label': '缺陷趋势分析',
        'icon': 'fas fa-chart-line',
        'component': 'defect_trend_page',
        'enabled': True
    },
    {
        'id': 'tab-defect-map',
        'label': '缺陷地图',
        'icon': 'fas fa-map',
        'component': 'defect_map_page',
        'enabled': True
    },
    {
        'id': 'tab-word-cloud',
        'label': '词云分析',
        'icon': 'fas fa-cloud',
        'component': 'word_cloud_page',
        'enabled': True
    },
    {
        'id': 'tab-risk-analysis',
        'label': '风险分析',
        'icon': 'fas fa-exclamation-triangle',
        'component': 'risk_analysis_page',
        'enabled': True
    },
    {
        'id': 'tab-data-dashboard',
        'label': '数据大屏',
        'icon': 'fas fa-desktop',
        'component': 'data_dashboard_page',
        'enabled': True
    },
    {
        'id': 'tab-test-status-analysis',
        'label': 'Test Status Analysis',
        'icon': 'fas fa-flask',
        'component': 'test_status_analysis_page',
        'enabled': True
    },
    {
        'id': 'tab-testing-efficiency',
        'label': 'Defect Status Analysis',
        'icon': 'fas fa-chart-line',
        'component': 'testing_efficiency_page',
        'enabled': True
    }
]

# 子模块配置
SUBMODULES_CONFIG = {
    'defect_coverage': {
        'port': 8056,
        'module_path': 'defect_coverage.py',
        'component_function': 'create_defect_coverage_page'
    },
    'defect_highrunner_parent': {
        'port': 8058,
        'module_path': 'defect_highrunner_parent.py',
        'component_function': 'create_highrunner_parent_page'
    },
    'defect_highrunner_child': {
        'port': 8059,
        'module_path': 'defect_highrunner_child.py',
        'component_function': 'create_highrunner_child_page'
    },
    'defect_longrunner': {
        'port': 8062,
        'module_path': 'defect_longrunner.py',
        'component_function': 'create_longrunner_page'
    },
    'defect_matrix': {
        'port': 8053,
        'module_path': 'defect_matrix.py',
        'component_function': 'create_matrix_page'
    },
    'defect_trend': {
        'port': 8052,
        'module_path': 'defect_trend.py',
        'component_function': 'create_trend_page'
    },
    'defect_map': {
        'port': 8054,
        'module_path': 'defect_map.py',
        'component_function': 'create_map_page'
    },
    'test_coverage': {
        'port': 8055,
        'module_path': 'test_coverage.py',
        'component_function': 'create_test_coverage_page'
    },
    'word_cloud': {
        'port': 8073,
        'module_path': 'word_cloud.py',
        'component_function': 'create_word_cloud_page'
    },
    'risk_analysis': {
        'port': 8057,
        'module_path': 'risk_analysis.py',
        'component_function': 'create_risk_analysis_page'
    },
    'data_dashboard': {
        'port': 8070,
        'module_path': 'data_dashboard.py',
        'component_function': 'create_data_dashboard_page'
    },
    'test_status_analysis': {
        'port': 8071,
        'module_path': 'test_status_analysis.py',
        'component_function': 'create_test_status_analysis_page'
    }
}

# 主题配置
THEME_CONFIG = {
    'light': {
        'primary_color': '#2c3e50',
        'secondary_color': '#3498db',
        'success_color': '#28a745',
        'warning_color': '#ffc107',
        'danger_color': '#dc3545',
        'background_color': '#ffffff',
        'text_color': '#333333'
    },
    'dark': {
        'primary_color': '#34495e',
        'secondary_color': '#5dade2',
        'success_color': '#58d68d',
        'warning_color': '#f7dc6f',
        'danger_color': '#ec7063',
        'background_color': '#2c3e50',
        'text_color': '#ecf0f1'
    }
}

# 性能优化配置
PERFORMANCE_CONFIG = {
    'enable_caching': True,
    'cache_timeout': 300,
    'lazy_loading': True,
    'compression': True,
    'minify_assets': True
}

# 数据源配置
DATA_SOURCE_CONFIG = {
    'defect_master_file': 'defect/2025_defect_master.json',
    'test_data_dir': 'mr/',
    'aida_mapping_file': 'aida/top_aida_project_fv_mapping.xlsx',
    'project_mapping_file': 'project/project_vin_mapping.csv'
}

# 导出配置
EXPORT_CONFIG = {
    'formats': ['excel', 'csv', 'pdf'],
    'max_rows': 10000,
    'temp_dir': 'temp/',
    'cleanup_interval': 3600  # 1小时
}

# 日志配置
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'logs/app.log',
    'max_bytes': 10485760,  # 10MB
    'backup_count': 5
}

# 安全配置
SECURITY_CONFIG = {
    'secret_key': 'your-secret-key-here',
    'csrf_protection': True,
    'rate_limiting': True,
    'max_requests_per_minute': 100
}

# API配置
API_CONFIG = {
    'base_url': '/api/v1',
    'timeout': 30,
    'max_retries': 3,
    'endpoints': {
        'defect_data': '/defects',
        'test_data': '/tests',
        'analytics': '/analytics'
    }
}


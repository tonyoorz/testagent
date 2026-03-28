"""
车载软件缺陷管理系统 - 业务规则定义

本文件定义了系统的核心业务规则、阈值和常量，
用于指导SQL查询生成和业务逻辑判断。

使用方法：
    from chatdb.business_rules import TOP_ISSUE_THRESHOLD, HIGH_RUNNER_THRESHOLD
    
    # 检查是否为TopIssue
    if risk_score >= TOP_ISSUE_THRESHOLD:
        print("这是TopIssue")
"""

# =============================================================================
# 1. TopIssue 风险评分相关规则
# =============================================================================

# TopIssue 最低风险评分阈值
TOP_ISSUE_THRESHOLD = 60  # 分数≥60为TopIssue

# TopIssue 风险等级划分
TOP_ISSUE_RISK_LEVELS = {
    'EXTREMELY_HIGH': 140,  # 极高风险
    'HIGH': 100,          # 高风险
    'MEDIUM': 60,         # 中等风险
    'LOW': 30,            # 低风险
    'NONE': 0             # 不视为TopIssue
}

# TopIssue 评分维度权重
TOP_ISSUE_DIMENSIONS = {
    'matrix_severity': {
        'max_score': 30,
        'description': 'Matrix严重性等级',
        'scoring_method': 'exponential_decay'
    },
    'classification': {
        'max_score': 30,
        'description': 'Classification分类',
        'scoring_method': 'categorical'
    },
    'ecu_transfers': {
        'max_score': 30,
        'description': 'ECU转移次数',
        'scoring_method': 'tiered'
    },
    'domain_transfers': {
        'max_score': 20,
        'description': 'Domain转移次数',
        'scoring_method': 'tiered'
    },
    'parent_complexity': {
        'max_score': 30,
        'description': 'Parent票的子票数',
        'scoring_method': 'logarithmic'
    },
    'child_complexity': {
        'max_score': 30,
        'description': 'Child票的主票子票数',
        'scoring_method': 'logarithmic'
    },
    'processing_cycle': {
        'max_score': 20,
        'description': '处理周期天数',
        'scoring_method': 'bimodal'
    },
    'shift_pu': {
        'max_score': 10,
        'description': 'Shift PU延期标记',
        'scoring_method': 'binary'
    }
}

# Classification 分类评分规则
CLASSIFICATION_SCORES = {
    'Showstopper_Confirmed': 30,
    'Preventing Maturity Grade ConDrive': 30,
    'Showstopper_Candidate': 20,
    'Obstructing Maturity Grade ConDrive': 10,
    'Homologation L-labelled': 10
}

# ECU转移次数评分规则（分层）
ECU_TRANSFER_SCORES = {
    '>=5': 30,
    '>=3': 24,
    '>=1': 20
}

# Domain转移次数评分规则（分层）
DOMAIN_TRANSFER_SCORES = {
    '>=5': 20,
    '>=3': 14,
    '>=1': 10
}

# 处理周期天数评分规则（双峰分布）
PROCESSING_CYCLE_SCORING = {
    # 第一峰：新票需要快速响应
    'new_issue': {
        'range': (0, 3),
        'base_score': 24,
        'decrement_per_day': 2,
        'description': 'New Issue Peak'
    },
    # 低谷期：正常处理阶段
    'normal_processing': {
        'range': (4, 20),
        'min_score': 5,
        'max_score': 15,
        'description': 'Normal Processing Valley'
    },
    # 第二峰：Long Runner风险上升
    'long_runner_rise': {
        'range': (21, 30),
        'min_score': 15,
        'max_score': 20,
        'increment_per_day': 0.5,
        'description': 'Long Runner Rise'
    },
    # 高峰期：严重的Long Runner问题
    'long_runner_peak': {
        'range': (31, float('inf')),
        'base_score': 20,
        'increment_per_10_days': 2,
        'max_extra_score': 5,
        'description': 'Long Runner Peak'
    }
}

# 非线性调整规则
NONLINEAR_ADJUSTMENTS = {
    'severity_long_processing': {
        'condition': 'matrix_severity >= 20 AND processing_cycle_days >= 30',
        'extra_score': 15,
        'description': 'High severity issue with long processing time'
    },
    'cross_ecu_domain': {
        'condition': 'ecu_no_of_changes >= 3 AND domain_pingpong_count >= 3',
        'extra_score': 10,
        'description': 'Complex cross-ECU and cross-domain issue'
    },
    'critical_blocking': {
        'condition': 'matrix_severity >= 24 AND classification_score >= 20',
        'extra_score': 15,
        'description': 'Critical blocking issue'
    },
    'time_acceleration': {
        'condition': 'processing_cycle_days > 30',
        'calculation': 'min(30, ((processing_cycle_days - 30) / 10) * 5)',
        'description': 'Extended processing time risk acceleration'
    },
    'extreme_parent': {
        'condition': 'parent_child == "Parent" AND child_count > 10',
        'calculation': 'min(25, (child_count - 10) * 2.5)',
        'description': 'Extremely large parent ticket'
    },
    'extreme_ecu_transfers': {
        'condition': 'ecu_no_of_changes > 5',
        'calculation': 'min(20, 10 * log(1 + (ecu_no_of_changes - 5) / 2))',
        'description': 'Extreme ECU transfer complexity'
    }
}

# =============================================================================
# 2. High Runner 相关规则
# =============================================================================

# High Runner 最低ECU转移次数阈值
HIGH_RUNNER_THRESHOLD = 3  # ECU转移≥3次为High Runner

# 极端High Runner阈值
EXTREME_HIGH_RUNNER_THRESHOLD = 5  # ECU转移≥5次为极端High Runner

# Domain High Runner阈值
DOMAIN_HIGH_RUNNER_THRESHOLD = 3  # Domain转移≥3次为Domain High Runner

# =============================================================================
# 3. Long Runner 相关规则
# =============================================================================

# Long Runner 最低处理周期天数阈值
LONG_RUNNER_THRESHOLD = 30  # 处理周期≥30天为Long Runner

# 中期Long Runner阈值
MEDIUM_LONG_RUNNER_THRESHOLD = 15  # 处理周期≥15天为中期Long Runner

# 新票快速响应阈值
NEW_ISSUE_THRESHOLD = 3  # 处理周期≤3天为新票（需要快速响应）

# =============================================================================
# 4. Matrix 严重性相关规则
# =============================================================================

# Matrix 严重性等级排序（值越小越严重）
MATRIX_SEVERITY_ORDER = {
    'matrix-1a': 0, 'matrix-1b': 1, 'matrix-1c': 2, 'matrix-1d': 3, 'matrix-1e': 4,
    'matrix-2a': 5, 'matrix-2b': 6, 'matrix-2c': 7,
    'matrix-3a': 8,
    'matrix-2d': 9, 'matrix-2e': 10,
    'matrix-3b': 11, 'matrix-3c': 12, 'matrix-3d': 13, 'matrix-4a': 14,
    'matrix-3e': 15,
    'matrix-4b': 16, 'matrix-4c': 17, 'matrix-4d': 18, 'matrix-4e': 19
}

# Matrix 严重性分组
MATRIX_SEVERITY_GROUPS = {
    'HIGH_SEVERITY': [
        'matrix-1a', 'matrix-1b', 'matrix-1c', 'matrix-1d', 'matrix-1e',
        'matrix-2a', 'matrix-2b', 'matrix-2c', 'matrix-2d', 'matrix-3a'
    ],
    'MEDIUM_SEVERITY': [
        'matrix-2e', 'matrix-3b', 'matrix-3c', 'matrix-3d', 'matrix-4a'
    ],
    'LOW_SEVERITY': [
        'matrix-3e', 'matrix-4b', 'matrix-4c', 'matrix-4d', 'matrix-4e'
    ]
}

# Matrix 严重性排序值（数字形式，越小越严重）
MATRIX_SEVERITY_NUMERIC = {
    # High Severity: 10-24
    'matrix-1a': 10, 'matrix-1b': 11, 'matrix-1c': 12, 'matrix-1d': 13, 'matrix-1e': 14,
    'matrix-2a': 15, 'matrix-2b': 16, 'matrix-2c': 17, 'matrix-2d': 18, 'matrix-2e': 19,
    'matrix-3a': 20,
    # Medium Severity: 21-27
    'matrix-3b': 21, 'matrix-3c': 22, 'matrix-3d': 23, 'matrix-4a': 24,
    # Low Severity: 28-32
    'matrix-3e': 28, 'matrix-4b': 29, 'matrix-4c': 30, 'matrix-4d': 31, 'matrix-4e': 32
}

# =============================================================================
# 5. 状态流转相关规则
# =============================================================================

# 最终状态（已解决、已关闭）
RESOLVED_PHASES = ['06-Concluded', '09-Concluded without action', '10-Closed']

# 进行中状态
IN_PROGRESS_PHASES = [
    '01-New',
    '02-In Pre-Analysis',
    '03-In Analysis',
    '04-In Progress',
    '05-In Testing',
    '07-In Pre-Verification',
    '08-In Verification'
]

# 分析状态
ANALYSIS_PHASES = ['02-In Pre-Analysis', '03-In Analysis']

# 验证状态
VERIFICATION_PHASES = ['07-In Pre-Verification', '08-In Verification']

# 状态优先级（用于排序）
PHASE_PRIORITY = {
    '01-New': 1,
    '02-In Pre-Analysis': 2,
    '03-In Analysis': 3,
    '04-In Progress': 4,
    '05-In Testing': 5,
    '07-In Pre-Verification': 6,
    '08-In Verification': 7,
    '06-Concluded': 8,
    '09-Concluded without action': 9,
    '10-Closed': 10
}

# =============================================================================
# 6. 票据关系相关规则
# =============================================================================

# 票据关系类型
PARENT_CHILD_TYPES = {
    'PARENT': 'Parent',
    'CHILD': 'Child',
    'CHILD_CANDIDATE': 'Child (candidate)'
}

# 大规模主票阈值
LARGE_PARENT_THRESHOLD = 5  # ≥5个子票为大规模主票

# 超大规模主票阈值
EXTREME_LARGE_PARENT_THRESHOLD = 10  # >10个子票为超大规模主票

# =============================================================================
# 7. 项目相关规则
# =============================================================================

# 项目列表
PROJECTS = [
    'App',        # MyBMW App项目
    'IDCevo',     # IDC Evolution项目
    'IDC',        # ID Connected项目
    'MGU',        # Media Graphics Unit项目
    'RSU'         # Remote Software Update项目
]

# 项目全名映射
PROJECT_FULL_NAMES = {
    'App': 'MyBMW App',
    'IDCevo': 'IDC Evolution',
    'IDC': 'ID Connected',
    'MGU': 'Media Graphics Unit',
    'RSU': 'Remote Software Update'
}

# 团队列表
TEAMS = ['DIPS', 'IUK']

# FVP负责人列表
FVP_ASSIGNMENTS = {
    'Tianhua': [
        'DIPS_TSP_Call_Services',
        'DIPS_TSP_CD_Updates',
        'DIPS_TSP_Remote_Services',
        'eMob',
        'DIPS_TSP_MobileApps',
        'DIPS_TSP_Enabler'
    ],
    'Tony': ['IuK_TSP_Navi'],
    'Xu Miao': [
        'IuK_TSP_AZV',
        'IuK_TSP_Entertainment',
        'IuK_TSP_Audio',
        'IuK_TSP_Connectivity'
    ],
    'Huanran': ['DIPS_TSP_Car_Apps_CN'],
    'Jerry': [
        'IuK_TSP_HMI',
        'DIPS_TSP_RSU',
        'IuK_TSP_Carfunctions',
        'IuK_TSP_Perso CN',
        'RSU'
    ],
    'Marin': ['Mybmw App']
}

# =============================================================================
# 8. 入出流相关规则
# =============================================================================

# Inflow: 从00或直接创建到01的状态变更
INFLOW_RULES = {
    'from_phase': '00',
    'to_phase': '01',
    'description': 'New defect created'
}

# Outflow: 从任意状态到最终状态
OUTFLOW_RULES = {
    'to_phases': ['06-Concluded', '09-Concluded without action', '10-Closed'],
    'description': 'Defect resolved or closed'
}

# =============================================================================
# 9. 时间和测试周相关规则
# =============================================================================

# 测试周格式（年-CW周，如：2025-CW42）
TEST_WEEK_FORMAT = '%Y-CW%W'

# 常用时间范围
TIME_RANGES = {
    'LAST_WEEK': 1,        # 最近1周
    'LAST_MONTH': 4,       # 最近1月（约4周）
    'LAST_QUARTER': 12,    # 最近1季度（约12周）
    'LAST_HALF_YEAR': 26,   # 最近半年（约26周）
    'LAST_YEAR': 52        # 最近1年（52周）
}

# =============================================================================
# 10. SQL查询模板
# =============================================================================

# TopIssue查询模板
SQL_TEMPLATES = {
    'top_issues': """
        SELECT 
            id, name, project, ecu, matrix, topissue_display,
            topissue_risk_score, topissue_recommend_reason,
            processing_cycle_days, creation_time
        FROM defects
        WHERE is_topissue = 1
        ORDER BY topissue_risk_score DESC
        LIMIT {limit};
    """,
    
    'high_runners': """
        SELECT 
            id, name, ecu, ecu_no_of_changes, ecu_pingpong_display,
            domain_pingpong_count, processing_cycle_days, matrix
        FROM defects
        WHERE ecu_no_of_changes >= {threshold} OR domain_pingpong_count >= {threshold}
        ORDER BY (ecu_no_of_changes + domain_pingpong_count) DESC
        LIMIT {limit};
    """,
    
    'long_runners': """
        SELECT 
            id, name, project, ecu, status_phase,
            processing_cycle_days, creation_time
        FROM defects
        WHERE processing_cycle_days >= {threshold}
          AND status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed')
        ORDER BY processing_cycle_days DESC
        LIMIT {limit};
    """,
    
    'project_statistics': """
        SELECT 
            project,
            COUNT(*) as total_defects,
            SUM(CASE WHEN matrix LIKE 'Matrix-1%' THEN 1 ELSE 0 END) as severe_defects,
            AVG(processing_cycle_days) as avg_processing_days,
            COUNT(DISTINCT ecu) as ecu_count
        FROM defects
        WHERE test_week BETWEEN '{start_week}' AND '{end_week}'
        GROUP BY project
        ORDER BY total_defects DESC;
    """,
    
    'inflow_outflow_trends': """
        SELECT 
            week, inflow, outflow, net_change
        FROM defect_inflow_outflow
        WHERE week BETWEEN '{start_week}' AND '{end_week}'
        ORDER BY week;
    """,
    
    'large_parents': """
        SELECT 
            id, name, project, ecu, child_count,
            topissue_risk_score, creation_time
        FROM defects
        WHERE parent_child = 'Parent' AND child_count >= {threshold}
        ORDER BY child_count DESC
        LIMIT {limit};
    """
}

# =============================================================================
# 11. 业务术语到SQL条件的映射
# =============================================================================

BUSINESS_TERM_TO_SQL = {
    # TopIssue相关
    'TopIssue': 'is_topissue = 1',
    '高风险TopIssue': 'topissue_risk_score >= 100',
    '极高风险TopIssue': 'topissue_risk_score >= 140',
    '使用主票分数的TopIssue': 'is_master_score = 1',
    
    # High Runner相关
    'High Runner': f'ecu_no_of_changes >= {HIGH_RUNNER_THRESHOLD}',
    '极端High Runner': f'ecu_no_of_changes >= {EXTREME_HIGH_RUNNER_THRESHOLD}',
    'Domain High Runner': f'domain_pingpong_count >= {DOMAIN_HIGH_RUNNER_THRESHOLD}',
    '跨ECU+Domain High Runner': f'ecu_no_of_changes >= {HIGH_RUNNER_THRESHOLD} AND domain_pingpong_count >= {DOMAIN_HIGH_RUNNER_THRESHOLD}',
    
    # Long Runner相关
    'Long Runner': f"processing_cycle_days >= {LONG_RUNNER_THRESHOLD} AND status_phase NOT IN ('06-Concluded', '09-Concluded without action', '10-Closed')",
    '中期Long Runner': f'processing_cycle_days >= {MEDIUM_LONG_RUNNER_THRESHOLD} AND processing_cycle_days < {LONG_RUNNER_THRESHOLD}',
    '新票': f'processing_cycle_days <= {NEW_ISSUE_THRESHOLD}',
    
    # 严重性相关
    '高严重性缺陷': "matrix LIKE 'Matrix-1%' OR matrix LIKE 'Matrix-2A%' OR matrix LIKE 'Matrix-2B%' OR matrix LIKE 'Matrix-2C%' OR matrix LIKE 'Matrix-3A%'",
    '中等严重性缺陷': "matrix LIKE 'Matrix-2D%' OR matrix LIKE 'Matrix-2E%' OR matrix LIKE 'Matrix-3B%' OR matrix LIKE 'Matrix-3C%' OR matrix LIKE 'Matrix-3D%' OR matrix LIKE 'Matrix-4A%'",
    '低严重性缺陷': "matrix LIKE 'Matrix-3E%' OR matrix LIKE 'Matrix-4B%' OR matrix LIKE 'Matrix-4C%' OR matrix LIKE 'Matrix-4D%' OR matrix LIKE 'Matrix-4E%'",
    'Showstopper': "classification_json LIKE '%Showstopper%'",
    '阻塞成熟度': "classification_json LIKE '%Preventing Maturity Grade%'",
    
    # 票据关系相关
    '主票': "parent_child = 'Parent'",
    '子票': "parent_child = 'Child' OR parent_child = 'Child (candidate)'",
    '大规模主票': f"parent_child = 'Parent' AND child_count >= {LARGE_PARENT_THRESHOLD}",
    '超大规模主票': f"parent_child = 'Parent' AND child_count > {EXTREME_LARGE_PARENT_THRESHOLD}",
    '重复子票': "parent_child = 'Child' AND sub_status = 'Child (Duplicate)'",
    
    # 状态相关
    '已解决': "status_phase IN ('06-Concluded', '09-Concluded without action', '10-Closed')",
    '进行中': "status_phase IN ('01-New', '02-In Pre-Analysis', '03-In Analysis', '04-In Progress', '05-In Testing', '07-In Pre-Verification', '08-In Verification')",
    '分析中': "status_phase IN ('02-In Pre-Analysis', '03-In Analysis')",
    '验证中': "status_phase IN ('07-In Pre-Verification', '08-In Verification')"
}

# =============================================================================
# 12. 工具函数
# =============================================================================

def get_top_issue_level(score):
    """
    根据风险评分返回TopIssue等级
    
    Args:
        score: 风险评分
    
    Returns:
        str: 风险等级名称
    """
    if score >= TOP_ISSUE_RISK_LEVELS['EXTREMELY_HIGH']:
        return 'Extremely High Risk'
    elif score >= TOP_ISSUE_RISK_LEVELS['HIGH']:
        return 'High Risk'
    elif score >= TOP_ISSUE_RISK_LEVELS['MEDIUM']:
        return 'Medium Risk'
    elif score >= TOP_ISSUE_RISK_LEVELS['LOW']:
        return 'Low Risk'
    else:
        return 'Not TopIssue'


def is_high_runner(ecu_no_of_changes, domain_pingpong_count=None):
    """
    判断是否为High Runner
    
    Args:
        ecu_no_of_changes: ECU转移次数
        domain_pingpong_count: Domain转移次数（可选）
    
    Returns:
        bool: 是否为High Runner
    """
    if ecu_no_of_changes >= EXTREME_HIGH_RUNNER_THRESHOLD:
        return True
    if domain_pingpong_count is not None:
        return (ecu_no_of_changes >= HIGH_RUNNER_THRESHOLD or 
                domain_pingpong_count >= DOMAIN_HIGH_RUNNER_THRESHOLD)
    return ecu_no_of_changes >= HIGH_RUNNER_THRESHOLD


def is_long_runner(processing_cycle_days, status_phase):
    """
    判断是否为Long Runner
    
    Args:
        processing_cycle_days: 处理周期天数
        status_phase: 当前状态
    
    Returns:
        bool: 是否为Long Runner
    """
    if status_phase in RESOLVED_PHASES:
        return False
    return processing_cycle_days >= LONG_RUNNER_THRESHOLD


def get_matrix_severity_group(matrix):
    """
    根据Matrix值返回严重性分组
    
    Args:
        matrix: Matrix值（如'matrix-1a'）
    
    Returns:
        str: 严重性分组（'HIGH_SEVERITY', 'MEDIUM_SEVERITY', 'LOW_SEVERITY'）
    """
    if not matrix or not isinstance(matrix, str):
        return 'UNKNOWN'
    
    matrix_lower = matrix.lower()
    
    for group, matrices in MATRIX_SEVERITY_GROUPS.items():
        if any(matrix_lower == m.lower() for m in matrices):
            return group
    
    return 'UNKNOWN'


def parse_test_week(test_week_str):
    """
    解析测试周字符串，返回年份和周数
    
    Args:
        test_week_str: 测试周字符串（如'2025-CW42'）
    
    Returns:
        tuple: (year, week) 或 (None, None)
    """
    try:
        parts = test_week_str.split('-CW')
        return (int(parts[0]), int(parts[1]))
    except:
        return (None, None)


def get_business_term_sql(term):
    """
    将业务术语转换为SQL条件
    
    Args:
        term: 业务术语（如'TopIssue', 'High Runner'）
    
    Returns:
        str: SQL条件或None
    """
    return BUSINESS_TERM_TO_SQL.get(term)


def format_sql_template(template_name, **kwargs):
    """
    格式化SQL模板
    
    Args:
        template_name: 模板名称
        **kwargs: 模板参数
    
    Returns:
        str: 格式化后的SQL
    """
    template = SQL_TEMPLATES.get(template_name)
    if template is None:
        return None
    return template.format(**kwargs)


if __name__ == '__main__':
    # 测试代码
    print("=== 业务规则测试 ===")
    
    # 测试TopIssue等级
    test_scores = [145, 120, 80, 45, 20]
    for score in test_scores:
        print(f"风险评分 {score}: {get_top_issue_level(score)}")
    
    # 测试High Runner判断
    print(f"\nECU转移5次: {'High Runner' if is_high_runner(5) else 'Not High Runner'}")
    print(f"ECU转移3次, Domain转移3次: {'High Runner' if is_high_runner(3, 3) else 'Not High Runner'}")
    
    # 测试Long Runner判断
    print(f"\n处理周期45天，状态进行中: {'Long Runner' if is_long_runner(45, '04-In Progress') else 'Not Long Runner'}")
    print(f"处理周期45天，状态已解决: {'Long Runner' if is_long_runner(45, '06-Concluded') else 'Not Long Runner'}")
    
    # 测试Matrix严重性分组
    test_matrices = ['matrix-1a', 'matrix-2d', 'matrix-4e']
    for matrix in test_matrices:
        print(f"\n{matrix}: {get_matrix_severity_group(matrix)}")
    
    # 测试业务术语映射
    print("\n=== 业务术语SQL映射 ===")
    terms = ['TopIssue', 'High Runner', 'Long Runner', '高严重性缺陷']
    for term in terms:
        sql = get_business_term_sql(term)
        print(f"{term}: {sql}")

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np # Needed for np.where
import traceback # 用于打印详细错误

# --- 安全列访问函数 ---
def safe_get_unique_values(df, column_name, default_list=None):
    """安全地获取列的唯一值，如果列不存在则返回默认列表"""
    if default_list is None:
        default_list = []

    if column_name not in df.columns or df.empty:
        return default_list

    try:
        return sorted(df[column_name].dropna().apply(lambda x: str(x) if isinstance(x, dict) else x).unique())
    except Exception as e:
        print(f"处理列 '{column_name}' 时出错: {e}. 使用默认值.")
        return default_list

# --- Feature Region映射函数 ---
def get_feature_region(top_aida):
    """根据Top AIDA确定Feature Region (China Specific或Global)"""
    if pd.isna(top_aida) or top_aida == '':
        return 'Global'

    # 中国特有功能的AIDA列表
    china_specific_aidas = [
        'Use App Store China  [01.04.01.06.07]',
        'Traffic Info ASIA [01.04.03.01.02.07]',
        'Use Third Party App Store [01.04.01.05.03.02]',
        'Route planning and management 2.0 [01.04.02.01.01.05.24]',
        'Provide NetEase Cloud Music [01.04.01.06.04.03]',
        'Provide Festival Mode [01.04.02.01.04.08]',
        'Provide 3rd Party Gaming App [01.04.01.02.03.05]',
        'Positioning ASIA [01.04.03.01.02.01.02]',
        'Navigation Destination Input ASIA [01.04.03.01.02.03]',
        'POI Functions ASIA [01.04.03.01.02.05]',
        'Parking Finder China [01.04.03.01.05.02]',
        'Itinerary (Mobile App) [01.04.03.01.01.07.09]',
        'Use Speech operation [01.04.02.01.01.05]',
        'Connected Music China [01.04.01.06.04]',
        'Play audio via Online Services (Connected Music) [01.04.01.01.02]',
        'Voice Interface [01.04.02.01.01.02]',
        'Display map ASIA [01.04.03.01.02.04]',
        'Festival Mode [01.04.02.01.02.01.04]',
        'QQ Music [01.04.01.06.04.02]',
        'Smart Access / Digital Key (Plus) [01.03.03.03.04]',
        'Tencent MiniProgramPlatform (Tencent MPP) [01.04.01.06.01]',
        'Guiding [01.04.03.01.03.02.03]',
        'Guiding 2.0 [01.04.02.01.03.03.07.07]',
        'Guiding ASIA [01.04.03.01.02.08]',
        'Map [01.04.03.01.03.02.01]',
        'Map and Navigation Data update ASIA [01.04.03.01.02.02]',
        'Tencent MPP - MainMenu [01.04.01.06.01.01]',
        'Tencent WeChat [01.04.01.06.02]',
        'Video streaming China [01.04.01.06.05]',
        'WeChat Messaging [01.04.01.06.02.03]',
        'WeChat VoiP Call [01.04.01.06.02.02]',
        'Ximalaya [01.04.01.06.04.01]',
        'Provide Navigation 2.0 [01.04.03.01.03.06]'
    ]

    # 检查是否在中国特有功能列表中
    if str(top_aida).strip() in china_specific_aidas:
        return 'China Specific'
    else:
        return 'Global'

# --- 1. 加载数据 ---
from data_processor import load_test_data # 从新文件导入函数
tdf = load_test_data() # 调用函数加载数据

# 添加Feature Region列
if 'top_aida' in tdf.columns:
    tdf['feature_region'] = tdf['top_aida'].apply(get_feature_region)
    print(f"Feature Region分布: {tdf['feature_region'].value_counts().to_dict()}")
else:
    print("警告: 'top_aida' 列不存在，无法创建 Feature Region 列")
    tdf['feature_region'] = 'Global'  # 默认值

# --- 配置 ---
px.defaults.template = "simple_white"
color_map = {
    "Passed": "lightgreen",  # 浅绿
    "Failed": "lightcoral",  # 浅红
    "Requires Attention": "khaki", # 浅黄 (替换原来的 orange)
    "Planned": "lightgrey",   # 浅灰
    # 你可以根据需要添加或修改其他状态的颜色
}

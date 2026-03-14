"""
Code Interpreter Agent - DTSV 数据分析智能体
支持动态生成和执行 Python 代码进行高级数据分析
"""

from .agent import CodeInterpreterAgent
from .tools import (
    query_database,
    execute_python_code,
    calculate_risk_score,
    analyze_trend,
    generate_chart
)
from .db_connector import DatabaseConnector

__version__ = "1.0.0"
__all__ = [
    "CodeInterpreterAgent",
    "query_database",
    "execute_python_code", 
    "calculate_risk_score",
    "analyze_trend",
    "generate_chart",
    "DatabaseConnector"
]

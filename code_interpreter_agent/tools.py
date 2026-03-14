"""
Agent Tools - 工具集
定义 Agent 可调用的所有工具
"""

import os
import json
import logging
import traceback
import subprocess
import tempfile
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def query_database(sql: str, db_connector=None, **kwargs) -> Dict[str, Any]:
    """
    执行 SQL 查询
    
    Args:
        sql: SQL 查询语句
        db_connector: 数据库连接器实例
        
    Returns:
        查询结果字典
    """
    if db_connector is None:
        return {"success": False, "error": "Database connector not provided"}
    
    try:
        # 安全检查：只允许 SELECT 语句
        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT"):
            return {
                "success": False,
                "error": "Only SELECT statements are allowed for security reasons"
            }
        
        # 检查危险操作
        dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", "INSERT", "UPDATE"]
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                return {
                    "success": False,
                    "error": f"Dangerous keyword '{keyword}' is not allowed"
                }
        
        result = db_connector.execute_query(sql)
        
        return {
            "success": True,
            "data": result.get("data", []),
            "columns": result.get("columns", []),
            "row_count": len(result.get("data", [])),
            "sql": sql
        }
        
    except Exception as e:
        logger.error(f"Query error: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "sql": sql
        }


def get_database_schema(db_connector=None) -> str:
    """
    获取数据库 Schema 信息
    
    Returns:
        Schema 描述字符串
    """
    if db_connector is None:
        return "Database connector not available"
    
    try:
        schema_info = db_connector.get_schema()
        
        # 格式化 Schema 信息
        formatted = []
        formatted.append("## 数据库表结构\n")
        
        for table_name, table_info in schema_info.items():
            formatted.append(f"### 表: {table_name}\n")
            
            if table_info.get("columns"):
                formatted.append("| 列名 | 类型 | 说明 |\n")
                formatted.append("|------|------|------|\n")
                
                for col in table_info["columns"]:
                    col_name = col.get("name", "unknown")
                    col_type = col.get("type", "unknown")
                    col_desc = col.get("description", "")
                    formatted.append(f"| {col_name} | {col_type} | {col_desc} |\n")
            
            formatted.append("\n")
        
        return "\n".join(formatted)
        
    except Exception as e:
        logger.error(f"Get schema error: {e}")
        return f"Error getting schema: {str(e)}"


def execute_python_code(
    code: str,
    data: Optional[Dict[str, Any]] = None,
    db_connector=None,
    timeout: int = 30,
    **kwargs
) -> Dict[str, Any]:
    """
    在沙箱环境中执行 Python 代码
    
    Args:
        code: Python 代码字符串
        data: 可选的输入数据
        db_connector: 数据库连接器
        timeout: 执行超时时间（秒）
        
    Returns:
        执行结果字典
    """
    # 安全检查：禁止危险操作
    dangerous_imports = [
        "os", "sys", "subprocess", "shutil", "socket",
        "pickle", "marshal", "eval", "exec", "compile",
        "__import__", "open", "file", "input"
    ]
    
    for dangerous in dangerous_imports:
        if f"import {dangerous}" in code or f"from {dangerous}" in code:
            return {
                "success": False,
                "error": f"Dangerous import '{dangerous}' is not allowed in code interpreter"
            }
    
    # 准备执行环境
    exec_globals = {
        "pd": pd,
        "np": np,
        "json": json,
        "datetime": datetime,
        "timedelta": timedelta,
        "data": data,
        "result": None,
        "figures": [],
        "print_output": []
    }
    
    # 如果提供了数据库连接器，添加查询函数
    if db_connector:
        exec_globals["query_db"] = lambda sql: query_database(sql, db_connector)
    
    # 捕获 print 输出
    original_print = print
    def custom_print(*args, **kwargs):
        exec_globals["print_output"].append(" ".join(str(a) for a in args))
    exec_globals["print"] = custom_print
    
    try:
        # 执行代码
        exec(code, exec_globals)
        
        result = exec_globals.get("result")
        figures = exec_globals.get("figures", [])
        print_output = exec_globals.get("print_output", [])
        
        # 处理 DataFrame 结果
        if isinstance(result, pd.DataFrame):
            result = {
                "type": "dataframe",
                "data": result.to_dict(orient="records"),
                "columns": list(result.columns),
                "shape": list(result.shape)
            }
        elif isinstance(result, pd.Series):
            result = {
                "type": "series",
                "data": result.to_dict(),
                "name": result.name
            }
        elif isinstance(result, np.ndarray):
            result = {
                "type": "ndarray",
                "data": result.tolist(),
                "shape": list(result.shape)
            }
        
        return {
            "success": True,
            "result": result,
            "figures": figures,
            "print_output": print_output,
            "code": code
        }
        
    except Exception as e:
        logger.error(f"Code execution error: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "code": code
        }


def calculate_risk_score(
    db_connector=None,
    project: Optional[str] = None,
    module: Optional[str] = None,
    time_range: Optional[Dict[str, str]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    计算 Risk Score
    
    基于 8 个维度进行非线性评分：
    1. 缺陷严重性分布
    2. 缺陷状态分布
    3. 重开率（Ping-pong 比率）
    4. 缺陷年龄
    5. 缺陷密度
    6. 测试覆盖率
    7. 缺陷趋势
    8. 业务影响度
    
    Args:
        db_connector: 数据库连接器
        project: 项目名称（可选）
        module: 模块名称（可选）
        time_range: 时间范围 {'start': '2024-01-01', 'end': '2024-12-31'}
        
    Returns:
        Risk Score 分析结果
    """
    if db_connector is None:
        return {"success": False, "error": "Database connector not provided"}
    
    try:
        # 构建基础查询
        base_query = "SELECT * FROM defects WHERE 1=1"
        conditions = []
        params = []
        
        if project:
            conditions.append("project = ?")
            params.append(project)
        
        if module:
            conditions.append("domain = ?")
            params.append(module)
        
        if time_range:
            if time_range.get("start"):
                conditions.append("creation_time >= ?")
                params.append(time_range["start"])
            if time_range.get("end"):
                conditions.append("creation_time <= ?")
                params.append(time_range["end"])
        
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        # 执行查询
        result = db_connector.execute_query(base_query, params)
        defects = pd.DataFrame(result.get("data", []))
        
        if defects.empty:
            return {
                "success": True,
                "risk_score": 0,
                "message": "No defects found for the given criteria"
            }
        
        # === Risk Score 计算 ===
        
        # 1. 严重性评分 (权重: 25%)
        severity_weights = {
            "Critical": 10,
            "High": 7,
            "Medium": 4,
            "Low": 1
        }
        
        if "severity" in defects.columns:
            severity_score = defects["severity"].map(severity_weights).fillna(2).mean()
        else:
            severity_score = 2
        
        # 2. 状态评分 (权重: 15%)
        status_weights = {
            "New": 8,
            "Open": 7,
            "In Progress": 5,
            "Fixed": 3,
            "Closed": 0,
            "Rejected": 0
        }
        
        if "status_phase" in defects.columns:
            status_score = defects["status_phase"].map(status_weights).fillna(3).mean()
        else:
            status_score = 3
        
        # 3. 重开率评分 (权重: 15%)
        if "pingpong" in defects.columns:
            reopen_rate = defects["pingpong"].mean() / 10  # 假设 pingpong 是重开次数
            reopen_score = min(reopen_rate * 10, 10)
        else:
            reopen_score = 0
        
        # 4. 缺陷年龄评分 (权重: 15%)
        if "creation_time" in defects.columns:
            defects["creation_time"] = pd.to_datetime(defects["creation_time"], errors="coerce")
            defects["age_days"] = (datetime.now() - defects["creation_time"]).dt.days
            avg_age = defects["age_days"].mean()
            age_score = min(avg_age / 30 * 2, 10)  # 每月增加 2 分，最高 10 分
        else:
            age_score = 0
        
        # 5. 缺陷密度评分 (权重: 10%)
        defect_count = len(defects)
        density_score = min(defect_count / 50, 10)  # 每 50 个缺陷 10 分
        
        # 6. 缺陷趋势评分 (权重: 10%) - 简化版本
        trend_score = 5  # 默认中等
        
        # 7. 业务影响评分 (权重: 5%)
        impact_score = 5  # 默认中等
        
        # 8. 修复效率评分 (权重: 5%)
        efficiency_score = 5  # 默认中等
        
        # === 综合评分（非线性加权）===
        weights = {
            "severity": 0.25,
            "status": 0.15,
            "reopen": 0.15,
            "age": 0.15,
            "density": 0.10,
            "trend": 0.10,
            "impact": 0.05,
            "efficiency": 0.05
        }
        
        # 非线性转换（使用 sigmoid 函数）
        def sigmoid(x):
            return 10 / (1 + np.exp(-0.5 * (x - 5)))
        
        final_score = (
            sigmoid(severity_score) * weights["severity"] +
            sigmoid(status_score) * weights["status"] +
            sigmoid(reopen_score) * weights["reopen"] +
            sigmoid(age_score) * weights["age"] +
            sigmoid(density_score) * weights["density"] +
            sigmoid(trend_score) * weights["trend"] +
            sigmoid(impact_score) * weights["impact"] +
            sigmoid(efficiency_score) * weights["efficiency"]
        ) * 10  # 转换为 0-100 分
        
        # 风险等级判定
        if final_score >= 75:
            risk_level = "高危"
            recommendation = "需要立即采取行动，建议 escalate 到管理层"
        elif final_score >= 50:
            risk_level = "中高风险"
            recommendation = "需要重点关注，建议本周内制定改进计划"
        elif final_score >= 25:
            risk_level = "中风险"
            recommendation = "需要持续监控，定期检查进展"
        else:
            risk_level = "低风险"
            recommendation = "当前状态良好，继续保持"
        
        return {
            "success": True,
            "risk_score": round(final_score, 2),
            "risk_level": risk_level,
            "recommendation": recommendation,
            "details": {
                "severity_score": round(severity_score, 2),
                "status_score": round(status_score, 2),
                "reopen_score": round(reopen_score, 2),
                "age_score": round(age_score, 2),
                "density_score": round(density_score, 2),
                "trend_score": round(trend_score, 2),
                "impact_score": round(impact_score, 2),
                "efficiency_score": round(efficiency_score, 2)
            },
            "statistics": {
                "total_defects": defect_count,
                "avg_age_days": round(avg_age, 1) if "age_days" in defects.columns else None,
                "avg_pingpong": round(defects["pingpong"].mean(), 2) if "pingpong" in defects.columns else None
            }
        }
        
    except Exception as e:
        logger.error(f"Risk score calculation error: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e)
        }


def analyze_trend(
    db_connector=None,
    metric: str = "defect_count",
    group_by: str = "week",
    time_range: Optional[Dict[str, str]] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    分析趋势
    
    Args:
        db_connector: 数据库连接器
        metric: 分析指标 (defect_count, severity, status, etc.)
        group_by: 分组方式 (day, week, month, project, module)
        time_range: 时间范围
        
    Returns:
        趋势分析结果
    """
    if db_connector is None:
        return {"success": False, "error": "Database connector not provided"}
    
    try:
        # 构建查询
        query = "SELECT * FROM defects WHERE 1=1"
        conditions = []
        params = []
        
        if time_range:
            if time_range.get("start"):
                conditions.append("creation_time >= ?")
                params.append(time_range["start"])
            if time_range.get("end"):
                conditions.append("creation_time <= ?")
                params.append(time_range["end"])
        
        if conditions:
            query += " AND " + " AND ".join(conditions)
        
        result = db_connector.execute_query(query, params)
        defects = pd.DataFrame(result.get("data", []))
        
        if defects.empty:
            return {
                "success": True,
                "message": "No data for trend analysis"
            }
        
        # 时间分组
        if "creation_time" in defects.columns:
            defects["creation_time"] = pd.to_datetime(defects["creation_time"], errors="coerce")
            defects = defects.dropna(subset=["creation_time"])
            
            if group_by == "day":
                defects["period"] = defects["creation_time"].dt.date
            elif group_by == "week":
                defects["period"] = defects["creation_time"].dt.to_period("W").astype(str)
            elif group_by == "month":
                defects["period"] = defects["creation_time"].dt.to_period("M").astype(str)
            else:
                defects["period"] = defects["creation_time"].dt.to_period("W").astype(str)
        
        # 根据指标聚合
        if metric == "defect_count":
            trend_data = defects.groupby("period").size().reset_index(name="count")
        elif metric == "severity":
            if "severity" in defects.columns:
                trend_data = defects.groupby(["period", "severity"]).size().unstack(fill_value=0).reset_index()
            else:
                trend_data = defects.groupby("period").size().reset_index(name="count")
        elif metric == "status":
            if "status_phase" in defects.columns:
                trend_data = defects.groupby(["period", "status_phase"]).size().unstack(fill_value=0).reset_index()
            else:
                trend_data = defects.groupby("period").size().reset_index(name="count")
        else:
            trend_data = defects.groupby("period").size().reset_index(name="count")
        
        # 计算趋势
        if "count" in trend_data.columns and len(trend_data) > 1:
            counts = trend_data["count"].values
            
            # 简单线性趋势
            x = np.arange(len(counts))
            z = np.polyfit(x, counts, 1)
            slope = z[0]
            
            if slope > 0.5:
                trend_direction = "上升"
                trend_strength = min(abs(slope) / np.mean(counts) * 10, 10)
            elif slope < -0.5:
                trend_direction = "下降"
                trend_strength = min(abs(slope) / np.mean(counts) * 10, 10)
            else:
                trend_direction = "平稳"
                trend_strength = abs(slope) / np.mean(counts) * 10 if np.mean(counts) > 0 else 0
        else:
            trend_direction = "未知"
            trend_strength = 0
        
        return {
            "success": True,
            "metric": metric,
            "group_by": group_by,
            "trend_direction": trend_direction,
            "trend_strength": round(trend_strength, 2),
            "data": trend_data.to_dict(orient="records"),
            "statistics": {
                "total_periods": len(trend_data),
                "avg_value": round(float(trend_data["count"].mean()), 2) if "count" in trend_data.columns else None,
                "max_value": int(trend_data["count"].max()) if "count" in trend_data.columns else None,
                "min_value": int(trend_data["count"].min()) if "count" in trend_data.columns else None
            }
        }
        
    except Exception as e:
        logger.error(f"Trend analysis error: {e}\n{traceback.format_exc()}")
        return {
            "success": False,
            "error": str(e)
        }


def generate_chart(
    chart_type: str = "bar",
    data: Optional[Dict[str, Any]] = None,
    title: str = "",
    x_label: str = "",
    y_label: str = "",
    **kwargs
) -> Dict[str, Any]:
    """
    生成图表配置（返回前端可用的配置）
    
    Args:
        chart_type: 图表类型 (bar, line, pie, scatter, heatmap)
        data: 图表数据
        title: 图表标题
        x_label: X 轴标签
        y_label: Y 轴标签
        
    Returns:
        图表配置字典
    """
    try:
        # 基础配置
        config = {
            "type": chart_type,
            "title": title,
            "x_label": x_label,
            "y_label": y_label,
            "data": data or {},
            "options": {
                "responsive": True,
                "plugins": {
                    "legend": {
                        "position": "top"
                    },
                    "title": {
                        "display": bool(title),
                        "text": title
                    }
                }
            }
        }
        
        # 根据图表类型添加特定配置
        if chart_type in ["bar", "line"]:
            config["options"]["scales"] = {
                "x": {"title": {"display": bool(x_label), "text": x_label}},
                "y": {"title": {"display": bool(y_label), "text": y_label}}
            }
        
        return {
            "success": True,
            "chart_config": config
        }
        
    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

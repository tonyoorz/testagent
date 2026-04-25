"""Dashboard 数据 API

导入现有模块中的图表生成函数，返回 Plotly JSON 或统计摘要。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 缺陷探索 KPI ─────────────────────────────────────────────────

@router.get("/explore/kpis")
async def explore_kpis(request: Request):
    """缺陷探索 KPI 摘要"""
    df = getattr(request.app.state, "df", None)
    if df is None or df.empty:
        return JSONResponse({"error": "数据未加载"}, status_code=503)

    total = len(df)
    # 按 status_phase 统计
    phase_counts = {}
    if "status_phase" in df.columns:
        phase_counts = df["status_phase"].value_counts().to_dict()

    # 按 project 统计
    project_counts = {}
    if "project" in df.columns:
        project_counts = df["project"].value_counts().head(10).to_dict()

    return {
        "total": total,
        "phase_distribution": phase_counts,
        "project_distribution": project_counts,
    }


# ── 趋势图数据 ────────────────────────────────────────────────────

@router.get("/explore/trend")
async def explore_trend(request: Request):
    """缺陷趋势数据（返回 Plotly JSON）"""
    df = getattr(request.app.state, "df", None)
    if df is None or df.empty:
        return JSONResponse({"error": "数据未加载"}, status_code=503)

    try:
        import plotly.graph_objects as go
        import pandas as pd

        # 按周聚合缺陷数
        if "test_week" in df.columns:
            weekly = df.groupby("test_week").size().reset_index(name="count")
            weekly = weekly.sort_values("test_week")
            fig = go.Figure([go.Bar(x=weekly["test_week"], y=weekly["count"])])
            fig.update_layout(title="缺陷趋势", xaxis_title="测试周", yaxis_title="缺陷数")
            return JSONResponse(fig.to_dict())
    except Exception as e:
        logger.warning(f"趋势图生成失败: {e}")

    return JSONResponse({"error": "无法生成趋势图"}, status_code=500)


# ── 矩阵分布图 ────────────────────────────────────────────────────

@router.get("/matrix/figure")
async def matrix_figure(request: Request):
    """缺陷矩阵分布图（返回 Plotly JSON）"""
    df = getattr(request.app.state, "df", None)
    if df is None or df.empty:
        return JSONResponse({"error": "数据未加载"}, status_code=503)

    try:
        from defect_matrix import create_matrix_figure
        fig = create_matrix_figure(df)
        return JSONResponse(fig.to_dict())
    except Exception as e:
        logger.warning(f"矩阵图生成失败，尝试简化版: {e}")
        return _matrix_fallback(df)


def _matrix_fallback(df):
    """矩阵图简化回退：直接返回统计数据"""
    import plotly.graph_objects as go

    counts = {}
    if "matrix_display" in df.columns:
        series = df["matrix_display"].dropna().astype(str).str.upper().value_counts()
        series.index = series.index.str.replace("MATRIX-", "", regex=False)
        counts = series.to_dict()

    return JSONResponse({"matrix_counts": counts, "total": len(df)})


# ── 风险分析 ──────────────────────────────────────────────────────

@router.get("/risk/analysis")
async def risk_analysis(request: Request):
    """风险分析摘要"""
    df = getattr(request.app.state, "df", None)
    if df is None or df.empty:
        return JSONResponse({"error": "数据未加载"}, status_code=503)

    # 基础风险统计
    severity_counts = {}
    if "severity_group" in df.columns:
        severity_counts = df["severity_group"].value_counts().to_dict()

    return {
        "severity_distribution": severity_counts,
        "total_defects": len(df),
    }


# ── LongRunner 数据 ───────────────────────────────────────────────

@router.get("/longrunner/data")
async def longrunner_data(request: Request):
    """LongRunner 分析数据"""
    df = getattr(request.app.state, "df", None)
    if df is None or df.empty:
        return JSONResponse({"error": "数据未加载"}, status_code=503)

    try:
        from longrunner_analysis import get_longrunner_stats
        stats = get_longrunner_stats(df)
        return JSONResponse(stats) if isinstance(stats, dict) else {"data": str(stats)}
    except ImportError:
        logger.info("longrunner_analysis 不可用，返回基础统计")
    except Exception as e:
        logger.warning(f"LongRunner 分析失败: {e}")

    return {"message": "LongRunner 分析模块未加载，请直接运行 Dash 应用查看"}


# ── 测试覆盖数据 ──────────────────────────────────────────────────

@router.get("/coverage/data")
async def coverage_data(request: Request):
    """测试覆盖数据"""
    test_df = getattr(request.app.state, "test_df", None)
    if test_df is None or test_df.empty:
        return JSONResponse({"error": "测试数据未加载"}, status_code=503)

    total = len(test_df)
    project_counts = {}
    if "project" in test_df.columns:
        project_counts = test_df["project"].value_counts().head(10).to_dict()

    return {
        "total_test_cases": total,
        "project_distribution": project_counts,
    }


# ── Q-Gate KPI ────────────────────────────────────────────────────

@router.get("/qgate/kpis")
async def qgate_kpis(request: Request):
    """Q-Gate KPI 摘要"""
    df = getattr(request.app.state, "df", None)
    if df is None or df.empty:
        return JSONResponse({"error": "数据未加载"}, status_code=503)

    try:
        from qgate import get_qgate_summary
        summary = get_qgate_summary(df)
        return JSONResponse(summary) if isinstance(summary, dict) else {"data": str(summary)}
    except ImportError:
        logger.info("qgate 模块不可用")
    except Exception as e:
        logger.warning(f"Q-Gate 分析失败: {e}")

    return {"message": "Q-Gate 模块未加载，请直接运行 Dash 应用查看"}

"""
Agent API - FastAPI 服务
提供 HTTP API 接口供前端调用
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent import CodeInterpreterAgent
from .db_connector import DatabaseConnector

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建 FastAPI 应用
app = FastAPI(
    title="DTSV Code Interpreter Agent API",
    description="智能数据分析 Agent API，支持自然语言查询、SQL 生成、Python 代码执行",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局 Agent 实例
_agent_instance: Optional[CodeInterpreterAgent] = None
_db_connector: Optional[DatabaseConnector] = None


def get_agent() -> CodeInterpreterAgent:
    """获取 Agent 实例（依赖注入）"""
    global _agent_instance
    if _agent_instance is None:
        db_path = os.environ.get(
            "DATABASE_PATH",
            os.path.join(os.path.dirname(__file__), "..", "database", "local_data.db")
        )
        _agent_instance = CodeInterpreterAgent(db_path=db_path)
    return _agent_instance


def get_db_connector() -> DatabaseConnector:
    """获取数据库连接器（依赖注入）"""
    global _db_connector
    if _db_connector is None:
        db_path = os.environ.get(
            "DATABASE_PATH",
            os.path.join(os.path.dirname(__file__), "..", "database", "local_data.db")
        )
        _db_connector = DatabaseConnector(db_path)
    return _db_connector


# ============== 请求/响应模型 ==============

class QueryRequest(BaseModel):
    """查询请求"""
    question: str = Field(..., description="用户问题", min_length=1, max_length=2000)
    context: Optional[Dict[str, Any]] = Field(default=None, description="可选的上下文信息")
    stream: bool = Field(default=False, description="是否使用流式响应")


class QueryResponse(BaseModel):
    """查询响应"""
    success: bool = Field(..., description="是否成功")
    answer: str = Field(..., description="答案内容")
    reasoning_trace: Optional[List[str]] = Field(default=None, description="推理过程")
    tool_results: Optional[List[Dict[str, Any]]] = Field(default=None, description="工具调用结果")
    execution_time: Optional[float] = Field(default=None, description="执行时间（秒）")
    error: Optional[str] = Field(default=None, description="错误信息")


class SQLQueryRequest(BaseModel):
    """SQL 查询请求"""
    sql: str = Field(..., description="SQL 查询语句")


class SQLQueryResponse(BaseModel):
    """SQL 查询响应"""
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    row_count: Optional[int] = None
    error: Optional[str] = None


class RiskScoreRequest(BaseModel):
    """Risk Score 计算请求"""
    project: Optional[str] = Field(default=None, description="项目名称")
    module: Optional[str] = Field(default=None, description="模块名称")
    start_date: Optional[str] = Field(default=None, description="开始日期")
    end_date: Optional[str] = Field(default=None, description="结束日期")


class TrendAnalysisRequest(BaseModel):
    """趋势分析请求"""
    metric: str = Field(default="defect_count", description="分析指标")
    group_by: str = Field(default="week", description="分组方式")
    start_date: Optional[str] = Field(default=None, description="开始日期")
    end_date: Optional[str] = Field(default=None, description="结束日期")


# ============== API 端点 ==============

@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "DTSV Code Interpreter Agent API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        db = get_db_connector()
        stats = db.get_statistics()
        
        return {
            "status": "healthy",
            "database": {
                "connected": True,
                "tables": len(stats.get("tables", {})),
                "total_records": stats.get("total_records", 0),
                "size_mb": stats.get("database_size_mb", 0)
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@app.post("/api/v1/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    agent: CodeInterpreterAgent = Depends(get_agent)
):
    """
    执行自然语言查询
    
    这是最主要的 API，用户发送自然语言问题，Agent 自动：
    1. 理解意图
    2. 规划分析步骤
    3. 调用工具执行
    4. 返回结构化答案
    """
    import time
    start_time = time.time()
    
    try:
        if request.stream:
            # 流式响应
            return StreamingResponse(
                agent.stream(request.question),
                media_type="text/event-stream"
            )
        else:
            # 同步响应
            answer = agent.run(request.question)
            
            execution_time = time.time() - start_time
            
            return QueryResponse(
                success=True,
                answer=answer,
                reasoning_trace=agent.state.reasoning_trace,
                tool_results=agent.state.tool_results,
                execution_time=round(execution_time, 2)
            )
            
    except Exception as e:
        logger.error(f"Query error: {e}", exc_info=True)
        return QueryResponse(
            success=False,
            answer="",
            error=str(e),
            execution_time=time.time() - start_time
        )


@app.post("/api/v1/query/stream")
async def query_stream(
    request: QueryRequest,
    agent: CodeInterpreterAgent = Depends(get_agent)
):
    """
    流式查询（Server-Sent Events）
    
    返回 SSE 格式的流式响应，适合实时显示
    """
    return StreamingResponse(
        agent.stream(request.question),
        media_type="text/event-stream"
    )


@app.post("/api/v1/sql", response_model=SQLQueryResponse)
async def execute_sql(
    request: SQLQueryRequest,
    db: DatabaseConnector = Depends(get_db_connector)
):
    """
    执行 SQL 查询
    
    仅支持 SELECT 语句，用于直接查询数据库
    """
    from .tools import query_database
    
    result = query_database(request.sql, db)
    
    return SQLQueryResponse(
        success=result.get("success", False),
        data=result.get("data"),
        columns=result.get("columns"),
        row_count=result.get("row_count"),
        error=result.get("error")
    )


@app.get("/api/v1/schema")
async def get_schema(
    db: DatabaseConnector = Depends(get_db_connector)
):
    """
    获取数据库 Schema
    
    返回所有表的结构信息，包括列定义、索引等
    """
    schema = db.get_schema()
    return {
        "success": True,
        "schema": schema
    }


@app.get("/api/v1/statistics")
async def get_statistics(
    db: DatabaseConnector = Depends(get_db_connector)
):
    """
    获取数据库统计信息
    
    返回表数量、记录数、数据库大小等信息
    """
    stats = db.get_statistics()
    return {
        "success": True,
        "statistics": stats
    }


@app.post("/api/v1/risk-score")
async def calculate_risk(
    request: RiskScoreRequest,
    db: DatabaseConnector = Depends(get_db_connector)
):
    """
    计算 Risk Score
    
    基于 8 维度非线性算法计算风险评分
    """
    from .tools import calculate_risk_score
    
    time_range = None
    if request.start_date or request.end_date:
        time_range = {
            "start": request.start_date,
            "end": request.end_date
        }
    
    result = calculate_risk_score(
        db_connector=db,
        project=request.project,
        module=request.module,
        time_range=time_range
    )
    
    return result


@app.post("/api/v1/trend")
async def analyze_trend(
    request: TrendAnalysisRequest,
    db: DatabaseConnector = Depends(get_db_connector)
):
    """
    分析趋势
    
    分析指定指标的时间趋势
    """
    from .tools import analyze_trend
    
    time_range = None
    if request.start_date or request.end_date:
        time_range = {
            "start": request.start_date,
            "end": request.end_date
        }
    
    result = analyze_trend(
        db_connector=db,
        metric=request.metric,
        group_by=request.group_by,
        time_range=time_range
    )
    
    return result


@app.get("/api/v1/tables/{table_name}/sample")
async def get_table_sample(
    table_name: str,
    limit: int = Query(default=5, ge=1, le=100),
    db: DatabaseConnector = Depends(get_db_connector)
):
    """
    获取表数据样本
    """
    result = db.get_table_sample(table_name, limit)
    
    return {
        "success": result.get("success", True),
        "table": table_name,
        "data": result.get("data", []),
        "columns": result.get("columns", []),
        "row_count": result.get("row_count", 0)
    }


@app.post("/api/v1/agent/reset")
async def reset_agent(
    agent: CodeInterpreterAgent = Depends(get_agent)
):
    """
    重置 Agent 状态
    
    清空对话历史和工具调用记录
    """
    agent.reset()
    return {
        "success": True,
        "message": "Agent state reset"
    }


@app.get("/api/v1/agent/state")
async def get_agent_state(
    agent: CodeInterpreterAgent = Depends(get_agent)
):
    """
    获取 Agent 当前状态
    """
    return {
        "success": True,
        "state": agent.get_state()
    }


# ============== 启动函数 ==============

def run_server(host: str = "0.0.0.0", port: int = 8080):
    """
    启动 API 服务器
    
    Args:
        host: 监听地址
        port: 监听端口
    """
    import uvicorn
    uvicorn.run(
        "code_interpreter_agent.api:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    run_server()

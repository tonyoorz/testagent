"""FastAPI 入口文件

启动时预构建 DuplicateIssueIndex 索引（按 project 分组 + all），
注册所有 API 路由，挂载前端静态目录。

用法:  python3 main.py
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


# ── 生命周期：启动时构建索引 ──────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时预加载缺陷数据并构建 DuplicateIssueIndex"""
    import pandas as pd
    from data_processor import load_defect_data
    from duplicate_issue_finder import DuplicateIssueIndex

    # 加载缺陷数据
    logger.info("正在加载缺陷数据...")
    df = load_defect_data()
    logger.info(f"缺陷数据加载完成: {len(df)} 条")

    # 构建索引
    index_cache: dict = {}

    if not df.empty:
        # 全量索引
        idx_all = DuplicateIssueIndex()
        idx_all.build_from_df(df)
        index_cache["all"] = idx_all

        # 按 project 分组索引
        if "project" in df.columns:
            for proj, grp in df.groupby("project"):
                if len(grp) < 2:
                    continue
                idx_proj = DuplicateIssueIndex()
                idx_proj.build_from_df(grp)
                index_cache[str(proj)] = idx_proj

        logger.info(f"索引构建完成: {list(index_cache.keys())}")
    else:
        logger.warning("缺陷数据为空，跳过索引构建")

    # 尝试加载测试数据
    test_df = pd.DataFrame()
    try:
        from data_processor import load_test_data
        test_df = load_test_data()
        logger.info(f"测试数据加载完成: {len(test_df)} 条")
    except Exception as e:
        logger.warning(f"测试数据加载失败: {e}")

    # 存入 app.state
    app.state.index_cache = index_cache
    app.state.df = df
    app.state.test_df = test_df

    yield

    logger.info("服务关闭")


# ── 创建 FastAPI 应用 ─────────────────────────────────────────────

app = FastAPI(
    title="PreAnalysis API",
    description="汽车测试数据分析平台 API 层",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from api.duplicate import router as duplicate_router
from api.chat import router as chat_router
from api.dashboards import router as dashboards_router

app.include_router(duplicate_router, prefix="/api/duplicate", tags=["duplicate"])
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(dashboards_router, prefix="/api", tags=["dashboards"])

# 挂载 React 前端（优先）
frontend_react_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend-react")
frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if os.path.isdir(frontend_react_dir):
    app.mount("/", StaticFiles(directory=frontend_react_dir, html=True), name="frontend-react")
elif os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")


# ── 入口 ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

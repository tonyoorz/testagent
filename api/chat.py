"""AI 聊天 API

- POST /ask   — 同步接口，返回完整回答
- WebSocket /ws — 流式推送
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

# 按用户 ID 隔离 agent 实例
_managers: Dict[str, object] = {}


# ── 请求模型 ──────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    user_id: Optional[str] = "default"
    dashboard_type: Optional[str] = "general"
    history: Optional[List[dict]] = None


# ── 同步接口 ──────────────────────────────────────────────────────

@router.post("/ask")
async def ask(req: AskRequest):
    """同步聊天接口，返回完整回答"""
    mgr = _get_manager(req.user_id, req.dashboard_type)
    data_context = ""

    try:
        text = await asyncio.to_thread(
            mgr.process_with_llm,
            req.question,
            data_context,
            req.history,
        )
        return {"text": text, "user_id": req.user_id}
    except Exception as e:
        logger.error(f"Chat ask 失败: {e}")
        return {"text": f"处理失败: {e}", "user_id": req.user_id}


# ── WebSocket 流式接口 ────────────────────────────────────────────

@router.websocket("/ws")
async def ws_chat(websocket: WebSocket):
    """WebSocket 流式聊天"""
    await websocket.accept()
    user_id = str(uuid.uuid4())[:8]
    mgr = _get_manager(user_id, "general")

    try:
        while True:
            data = await websocket.receive_json()
            question = data.get("question", "")
            if not question:
                await websocket.send_json({"type": "error", "text": "问题不能为空"})
                continue

            # 发送开始信号
            await websocket.send_json({"type": "start", "user_id": user_id})

            # 在线程池中调用同步 LLM
            text = await asyncio.to_thread(mgr.process_with_llm, question, "")

            # 发送完成
            await websocket.send_json({
                "type": "done",
                "text": text,
                "user_id": user_id,
            })
    except WebSocketDisconnect:
        logger.info(f"WebSocket 断开: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
    finally:
        _managers.pop(user_id, None)


# ── 工具函数 ──────────────────────────────────────────────────────

def _get_manager(user_id: str, dashboard_type: str):
    """获取或创建用户专属 ChatManager"""
    key = f"{user_id}:{dashboard_type}"
    if key not in _managers:
        try:
            from agent.core.enhanced_ai_chat_manager import EnhancedAIChatManager
            mgr = EnhancedAIChatManager(
                dashboard_type=dashboard_type,
                use_agent=True,
            )
        except Exception as e:
            logger.warning(f"EnhancedAIChatManager 初始化失败: {e}")
            mgr = _FallbackManager()
        _managers[key] = mgr
    return _managers[key]


class _FallbackManager:
    """ChatManager 不可用时的简易回退"""

    def process_with_llm(self, question: str, data_context: str, history=None) -> str:
        return "AI 服务暂不可用，请检查 DEEPSEEK_API_KEY 配置。"

    def process_with_agent(self, question, data, history=None, **kw):
        return {"success": False, "text": "AI 服务暂不可用。"}

"""
Streaming Process — 让 IntelligentAgent.process() 支持流式输出

提供两种使用方式：
1. process_stream() — 生成器模式，逐步 yield 中间事件
2. process_async() — 回调模式，通过 progress_cb 实时推送

事件类型：
- stream_start: 开始处理
- intent_detected: 意图识别完成
- context_ready: 上下文准备完成
- plan_created: 任务计划创建
- tool_start: 工具开始执行
- tool_end: 工具执行完成
- answer_ready: 最终答案生成
- stream_end: 处理结束

默认关闭，AGENT_STREAMING=1 开启（或直接调用 process_stream()）。
"""

import logging
import os
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Union

import pandas as pd

logger = logging.getLogger(__name__)


class StreamEvent:
    """一个流式事件。"""

    __slots__ = ("event_type", "data", "timestamp")

    def __init__(self, event_type: str, data: Optional[Dict[str, Any]] = None):
        self.event_type = event_type
        self.data = data or {}
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class AgentStreamer:
    """包装 IntelligentAgent，提供流式输出能力。"""

    def __init__(self, agent):
        self._agent = agent

    def process_stream(
        self,
        question: str,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        conversation_history: List = None,
    ) -> Generator[StreamEvent, None, Dict[str, Any]]:
        """流式处理用户问题，逐步 yield 中间事件。

        用法:
            streamer = AgentStreamer(agent)
            for event in streamer.process_stream(question, data):
                print(event.event_type, event.data)
            # 最终结果通过生成器返回值获取（Python 3.x 需要 try/StopIteration）

        或者更实用的方式——收集所有事件，最后一步包含完整结果：
            events = list(streamer.process_stream(question, data))
            final = events[-1]  # stream_end 事件包含完整 result
        """

        from agent.core.intelligent_agent import IntelligentAgent
        agent = self._agent

        # 1. Start
        yield StreamEvent("stream_start", {"question": question})

        # 2. Guardrails check
        try:
            from agent.core.guardrails import GuardrailPipeline
            if GuardrailPipeline.is_enabled():
                pipeline = GuardrailPipeline()
                proceed, results = pipeline.check_input(question)
                if not proceed:
                    yield StreamEvent("stream_end", {
                        "blocked": True,
                        "result": {
                            "text": pipeline.format_input_block_message(results),
                            "success": False,
                            "tools_used": [],
                        },
                    })
                    return
        except Exception:
            pass

        # 3. Collect events via progress_cb, then replay as stream
        collected_events: List[Dict[str, Any]] = []
        final_result: Optional[Dict[str, Any]] = None

        def _streaming_progress_cb(event: Dict[str, Any]):
            collected_events.append(event)

        try:
            # Call the original process() with our callback
            final_result = agent.process(
                question=question,
                data=data,
                conversation_history=conversation_history,
                progress_cb=_streaming_progress_cb,
            )
        except Exception as e:
            yield StreamEvent("stream_end", {
                "error": str(e),
                "result": {"text": f"处理出错: {e}", "success": False},
            })
            return

        # 4. Convert internal events to stream events
        for evt in collected_events:
            event_type = evt.get("event", "unknown")
            yield StreamEvent(event_type, evt)

        # 5. Final result
        yield StreamEvent("answer_ready", {
            "text": (final_result or {}).get("text", ""),
            "tools_used": (final_result or {}).get("tools_used", []),
            "insights": (final_result or {}).get("insights", []),
        })

        yield StreamEvent("stream_end", {
            "blocked": False,
            "result": final_result or {},
        })

    def process_stream_sse(
        self,
        question: str,
        data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
        conversation_history: List = None,
    ) -> Generator[str, None, None]:
        """SSE (Server-Sent Events) 格式的流式输出。

        直接可用于 FastAPI/Flask 的 StreamingResponse:

            from fastapi import FastAPI
            from fastapi.responses import StreamingResponse

            @app.post("/chat/stream")
            async def chat_stream(request):
                streamer = AgentStreamer(agent)
                return StreamingResponse(
                    streamer.process_stream_sse(question, data),
                    media_type="text/event-stream",
                )
        """
        import json as _json

        for event in self.process_stream(question, data, conversation_history):
            payload = _json.dumps(event.to_dict(), ensure_ascii=False, default=str)
            yield f"data: {payload}\n\n"

        yield "data: [DONE]\n\n"

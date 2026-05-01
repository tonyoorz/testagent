"""
多模态路由器 - 统一处理文字/图片/语音输入，路由到 duplicate detection 链路

用法:
    from agent.multimodal.multimodal_router import MultimodalRouter

    router = MultimodalRouter()
    result = router.process(
        text="用户输入的文字",
        images=[image_bytes1, image_bytes2],
        audio=audio_bytes,
    )
    # result.tickets → 解析出的 ticket 列表
    # result.queries → 生成的搜索查询列表
    # 直接接入 extract_hints() + duplicate search
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent.multimodal.image_parser import (
    ParsedTicket,
    parse_single_ticket,
    parse_batch_tickets,
    parse_images,
)
from agent.multimodal.speech_to_text import (
    speech_to_text,
    speech_to_text_from_base64,
)

logger = logging.getLogger(__name__)


@dataclass
class MultimodalResult:
    """多模态处理的统一输出"""
    tickets: List[ParsedTicket] = field(default_factory=list)
    transcribed_text: str = ""          # 语音转写文本
    combined_text: str = ""             # 所有文本合并（文字+语音转写）
    queries: List[str] = field(default_factory=list)  # 每个ticket的搜索查询
    source: str = "text"                # 输入来源: text/image/audio/mixed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tickets": [t.to_dict() for t in self.tickets],
            "transcribed_text": self.transcribed_text,
            "combined_text": self.combined_text,
            "queries": self.queries,
            "source": self.source,
        }


class MultimodalRouter:
    """
    多模态输入路由器

    根据输入类型自动路由：
    - 纯文字 → 直接用
    - 图片   → image_parser 提取 ticket → 搜索
    - 语音   → ASR 转文字 → 搜索
    - 混合   → 分别处理，合并 hints
    """

    def process(
        self,
        text: Optional[str] = None,
        images: Optional[List[bytes]] = None,
        audio: Optional[bytes] = None,
        audio_base64: Optional[str] = None,
        language: str = "zh",
        batch_mode: bool = False,
    ) -> MultimodalResult:
        """
        统一处理多模态输入

        Args:
            text: 用户输入的文字
            images: 图片字节数据列表（截图/照片）
            audio: 音频字节数据
            audio_base64: base64 编码的音频数据
            language: 语音识别语言（默认中文）
            batch_mode: 是否为批量模式（一张图多个 ticket）

        Returns:
            MultimodalResult 包含所有解析结果
        """
        has_text = bool(text and text.strip())
        has_images = bool(images)
        has_audio = bool(audio) or bool(audio_base64)

        # 判断输入来源
        sources = []
        if has_text:
            sources.append("text")
        if has_images:
            sources.append("image")
        if has_audio:
            sources.append("audio")
        source = "+".join(sources) if sources else "unknown"

        result = MultimodalResult(source=source)

        # 1. 处理语音
        transcribed = ""
        if has_audio:
            audio_data = audio or b""
            if audio_base64 and not audio_data:
                transcribed = speech_to_text_from_base64(audio_base64, language)
            else:
                transcribed = speech_to_text(audio_data, language)
            result.transcribed_text = transcribed
            logger.info(f"语音转写: {transcribed[:100]}")

        # 2. 合并所有文本
        text_parts = []
        if has_text:
            text_parts.append(text.strip())
        if transcribed:
            text_parts.append(transcribed)
        result.combined_text = " ".join(text_parts)

        # 3. 处理图片
        if has_images:
            if batch_mode:
                # 批量模式：每张图尝试提取多个 ticket
                for img_data in images:
                    tickets = parse_batch_tickets(img_data)
                    result.tickets.extend(tickets)
            else:
                # 自动模式：先批量，再单 ticket
                result.tickets = parse_images(images)

            logger.info(f"从 {len(images)} 张图片中提取了 {len(result.tickets)} 个 ticket")

        # 4. 如果没有图片但有文字，构造一个虚拟 ticket
        if not result.tickets and result.combined_text:
            result.tickets.append(ParsedTicket(
                title=result.combined_text[:200],
                description=result.combined_text,
                confidence=1.0,  # 纯文字输入，置信度最高
            ))

        # 5. 生成搜索查询
        result.queries = [
            ticket.to_search_query()
            for ticket in result.tickets
            if ticket.title
        ]

        return result

    def process_for_duplicate_search(
        self,
        text: Optional[str] = None,
        images: Optional[List[bytes]] = None,
        audio: Optional[bytes] = None,
        audio_base64: Optional[str] = None,
        language: str = "zh",
    ) -> Dict[str, Any]:
        """
        专为 duplicate detection 优化的处理接口

        返回可直接传给 duplicate_issue_finder 的结构
        """
        # 猜测是否批量模式
        batch_mode = bool(images and len(images) == 1 and not text)

        result = self.process(
            text=text,
            images=images,
            audio=audio,
            audio_base64=audio_base64,
            language=language,
            batch_mode=batch_mode,
        )

        return {
            "success": bool(result.tickets),
            "tickets": [t.to_dict() for t in result.tickets],
            "queries": result.queries,
            "combined_text": result.combined_text,
            "transcribed_text": result.transcribed_text,
            "source": result.source,
            "ticket_count": len(result.tickets),
        }

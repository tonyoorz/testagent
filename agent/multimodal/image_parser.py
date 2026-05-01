"""
图片解析器 - 从截图/照片中提取 ticket 结构化信息

支持：
1. 单个 ticket 截图 → 提取关键字段
2. 批量 ticket 列表截图 → 提取多个 ticket
3. 系统界面截图 → 识别 ticket 信息

输出：ParsedTicket 或 List[ParsedTicket]，直接接入 duplicate_issue_finder 链路
"""

import base64
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass
class ParsedTicket:
    """从图片中解析出的单个 ticket 信息"""
    title: str = ""                    # 缺陷标题/描述
    project: Optional[str] = None      # 项目名
    pu: Optional[str] = None           # PU 编号 (如 "01/02")
    ecu: Optional[str] = None          # ECU 名称
    phase: Optional[str] = None        # 阶段 (00, 01, 02...)
    severity: Optional[str] = None     # 严重度
    description: Optional[str] = None  # 详细描述
    steps_to_reproduce: Optional[str] = None  # 复现步骤
    expected: Optional[str] = None     # 期望结果
    actual: Optional[str] = None       # 实际结果
    environment: Optional[str] = None  # 环境信息
    ticket_id: Optional[str] = None    # 原始 ticket ID（如果截图中可见）
    raw_text: Optional[str] = None     # OCR/LLM 提取的原始文本（调试用）
    confidence: float = 0.0            # 解析置信度 0-1

    def to_search_query(self) -> str:
        """生成用于 duplicate search 的查询文本"""
        parts = []
        if self.title:
            parts.append(self.title)
        if self.description and self.description != self.title:
            parts.append(self.description)
        if self.project:
            parts.append(f"project: {self.project}")
        if self.pu:
            parts.append(f"PU: {self.pu}")
        if self.ecu:
            parts.append(f"ECU: {self.ecu}")
        return " ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v != ""}


# ---------------------------------------------------------------------------
# LLM Vision 调用（TODO: 接入公司 GLM 多模态模型）
# ---------------------------------------------------------------------------

# TODO: 配置公司内网 GLM 多模态模型的 endpoint
# 类似: https://aistudio.bmwbrill.cn/api/service/{service_id}/glm-4v/chat/completions
# 或通过 CHAT_MODEL_ENDPOINTS 环境变量配置

# TODO: 以下参数需要从配置或环境变量读取
_VISION_MODEL_NAME = "glm-4v"  # TODO: 替换为实际的 GLM 多模态模型名
_VISION_API_KEY = None  # TODO: 从配置读取 access_code / api_key
_VISION_API_BASE = None  # TODO: 从配置读取 endpoint

# LLM Vision prompt 模板
_SINGLE_TICKET_PROMPT = """你是一个缺陷管理系统的数据提取专家。请从这张截图中提取 ticket/缺陷 的关键信息。

请严格按照以下 JSON 格式输出，不要输出其他内容：
{
  "title": "缺陷标题或简要描述（必填，尽量完整提取）",
  "project": "项目名称（如果可见）",
  "pu": "PU编号，如 01/02（如果可见）",
  "ecu": "ECU名称（如果可见）",
  "phase": "阶段，如 00/01/02（如果可见）",
  "severity": "严重度（如果可见）",
  "description": "详细描述（如果可见）",
  "steps_to_reproduce": "复现步骤（如果可见）",
  "expected": "期望结果（如果可见）",
  "actual": "实际结果（如果可见）",
  "environment": "环境信息（如果可见）",
  "ticket_id": "原始ticket ID（如果可见）",
  "confidence": 0.0到1.0的置信度
}

注意：
- title 是最重要的字段，必须提取，即使其他字段缺失
- 如果截图中没有 ticket 信息（比如是普通图片），请返回 {"title": "", "confidence": 0.0}
- PU 格式通常是两位数字，如 "01/02" 或 "01-02"
- phase 是单个数字，如 "00", "01", "02"
"""

_BATCH_TICKET_PROMPT = """你是一个缺陷管理系统的数据提取专家。这张截图中包含多个 ticket/缺陷 记录。

请提取所有可见的 ticket 信息，严格按照以下 JSON 数组格式输出，不要输出其他内容：
[
  {
    "title": "缺陷标题或简要描述（必填）",
    "project": "项目名称",
    "pu": "PU编号",
    "ecu": "ECU名称",
    "phase": "阶段（00/01/02等）",
    "severity": "严重度",
    "description": "详细描述",
    "ticket_id": "原始ticket ID",
    "confidence": 0.0到1.0
  }
]

注意：
- 尽可能提取截图中所有可见的 ticket
- title 是最重要的字段，每个 ticket 必须有
- 只提取 phase 在 02 之前的 ticket（phase 00, 01）— 如果 phase 不可见则全部提取
- PU 格式通常是两位数字
- 如果截图中没有 ticket 信息，返回空数组 []
"""


def _encode_image_base64(image_data: bytes) -> str:
    """将图片字节编码为 base64 字符串"""
    return base64.b64encode(image_data).decode("utf-8")


def _detect_mime_type(image_data: bytes) -> str:
    """简单检测图片 MIME 类型"""
    if image_data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    elif image_data[:2] == b'\xff\xd8':
        return "image/jpeg"
    elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
        return "image/webp"
    elif image_data[:4] == b'GIF8':
        return "image/gif"
    return "image/png"  # default


def _build_vision_messages(base64_image: str, mime_type: str, prompt: str) -> List[Dict[str, Any]]:
    """构建 OpenAI 兼容的 vision messages"""
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_image}",
                    },
                },
            ],
        }
    ]


# TODO: 实现实际的 LLM Vision 调用
# 当公司 GLM 多模态 endpoint 配置好后，替换此函数
def call_vision_api(messages: List[Dict[str, Any]], model: str = None) -> str:
    """
    调用 GLM 多模态模型的 Vision API

    TODO: 接入公司内网 GLM 多模态模型
    - endpoint: 从环境变量或配置读取
    - 认证: access_code 或 api_key
    - 请求格式: OpenAI 兼容的 chat/completions

    示例实现（待配置后启用）:

    import httpx

    api_base = _VISION_API_BASE or os.getenv("GLM_VISION_API_BASE", "")
    api_key = _VISION_API_KEY or os.getenv("GLM_VISION_API_KEY", "")

    response = httpx.post(
        f"{api_base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model or _VISION_MODEL_NAME,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.1,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
    """
    # TODO: 临时返回空结果，等 endpoint 配置后替换
    logger.warning("Vision API 未配置，请设置 GLM_VISION_API_BASE 和 GLM_VISION_API_KEY")
    return '{"title": "", "confidence": 0.0}'


# ---------------------------------------------------------------------------
# 解析入口
# ---------------------------------------------------------------------------

def parse_single_ticket(image_data: bytes) -> ParsedTicket:
    """
    从单张截图中解析一个 ticket

    Args:
        image_data: 图片的字节数据

    Returns:
        ParsedTicket 解析出的 ticket 信息
    """
    base64_img = _encode_image_base64(image_data)
    mime_type = _detect_mime_type(image_data)
    messages = _build_vision_messages(base64_img, mime_type, _SINGLE_TICKET_PROMPT)

    try:
        raw_response = call_vision_api(messages)
        return _parse_ticket_json(raw_response)
    except Exception as e:
        logger.error(f"图片解析失败: {e}")
        return ParsedTicket(confidence=0.0)


def parse_batch_tickets(image_data: bytes) -> List[ParsedTicket]:
    """
    从一张截图中解析多个 ticket（批量模式）

    适用场景：测试人员截取系统中的 ticket 列表

    Args:
        image_data: 图片的字节数据

    Returns:
        List[ParsedTicket] 解析出的 ticket 列表
    """
    base64_img = _encode_image_base64(image_data)
    mime_type = _detect_mime_type(image_data)
    messages = _build_vision_messages(base64_img, mime_type, _BATCH_TICKET_PROMPT)

    try:
        raw_response = call_vision_api(messages)
        return _parse_batch_json(raw_response)
    except Exception as e:
        logger.error(f"批量图片解析失败: {e}")
        return []


def parse_images(images: List[bytes]) -> List[ParsedTicket]:
    """
    处理多张图片，自动判断单/批量模式

    Args:
        images: 图片字节数据列表

    Returns:
        所有图片中解析出的 ParsedTicket 列表
    """
    all_tickets: List[ParsedTicket] = []

    for i, img_data in enumerate(images):
        logger.info(f"正在解析第 {i + 1}/{len(images)} 张图片...")

        # 先尝试批量模式（一张图可能有多个 ticket）
        tickets = parse_batch_tickets(img_data)
        if len(tickets) == 1:
            # 只有一个，直接用
            all_tickets.extend(tickets)
        elif len(tickets) > 1:
            # 多个，批量结果
            all_tickets.extend(tickets)
        else:
            # 批量模式没提取到，尝试单 ticket 模式
            single = parse_single_ticket(img_data)
            if single.title and single.confidence > 0.3:
                all_tickets.append(single)

    logger.info(f"共从 {len(images)} 张图片中解析出 {len(all_tickets)} 个 ticket")
    return all_tickets


# ---------------------------------------------------------------------------
# JSON 解析工具
# ---------------------------------------------------------------------------

def _extract_json_from_text(text: str) -> str:
    """从 LLM 回复中提取 JSON（可能被 markdown 包裹）"""
    # 尝试提取 markdown code block
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()

    # 尝试直接找 JSON 数组或对象
    for pattern in [
        r"\[[\s\S]*\]",  # JSON array
        r"\{[\s\S]*\}",  # JSON object
    ]:
        m = re.search(pattern, text)
        if m:
            return m.group(0)

    return text.strip()


def _parse_ticket_json(raw_json: str) -> ParsedTicket:
    """解析单个 ticket 的 JSON"""
    try:
        clean = _extract_json_from_text(raw_json)
        data = json.loads(clean)
        return ParsedTicket(
            title=str(data.get("title", "") or "").strip(),
            project=data.get("project"),
            pu=data.get("pu"),
            ecu=data.get("ecu"),
            phase=data.get("phase"),
            severity=data.get("severity"),
            description=data.get("description"),
            steps_to_reproduce=data.get("steps_to_reproduce"),
            expected=data.get("expected"),
            actual=data.get("actual"),
            environment=data.get("environment"),
            ticket_id=data.get("ticket_id"),
            raw_text=raw_json[:500],
            confidence=float(data.get("confidence", 0.0)),
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"JSON 解析失败: {e}, raw: {raw_json[:200]}")
        return ParsedTicket(raw_text=raw_json[:500], confidence=0.0)


def _parse_batch_json(raw_json: str) -> List[ParsedTicket]:
    """解析批量 ticket 的 JSON 数组"""
    try:
        clean = _extract_json_from_text(raw_json)
        data = json.loads(clean)

        if isinstance(data, dict):
            # 单个对象，包装成数组
            data = [data]

        if not isinstance(data, list):
            logger.warning(f"期望 JSON 数组，得到: {type(data)}")
            return []

        tickets = []
        for item in data:
            if not isinstance(item, dict):
                continue
            ticket = ParsedTicket(
                title=str(item.get("title", "") or "").strip(),
                project=item.get("project"),
                pu=item.get("pu"),
                ecu=item.get("ecu"),
                phase=item.get("phase"),
                severity=item.get("severity"),
                description=item.get("description"),
                steps_to_reproduce=item.get("steps_to_reproduce"),
                expected=item.get("expected"),
                actual=item.get("actual"),
                environment=item.get("environment"),
                ticket_id=item.get("ticket_id"),
                confidence=float(item.get("confidence", 0.0)),
            )
            if ticket.title:  # 只保留有标题的
                tickets.append(ticket)

        return tickets
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"批量 JSON 解析失败: {e}, raw: {raw_json[:200]}")
        return []

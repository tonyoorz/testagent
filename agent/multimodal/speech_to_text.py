"""
语音识别模块 - 将语音转为文字，接入 duplicate detection 链路

支持：
1. 上传音频文件（wav/mp3/webm/m4a）
2. 前端录音数据（base64）

ASR 后端：
- 优先：公司内网 ASR 服务（TODO: 配置 endpoint）
- 降级：本地 Whisper tiny 模型（Mac mini M1 可运行）
"""

import base64
import io
import logging
import os
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

# TODO: 公司内网 ASR 服务 endpoint
# 示例: https://aistudio.bmwbrill.cn/api/service/{id}/asr/v1/recognize
_ASR_API_BASE = os.getenv("ASR_API_BASE", "")
_ASR_API_KEY = os.getenv("ASR_API_KEY", "")

# 本地 Whisper 配置
_LOCAL_WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")  # tiny/base/small/medium
_WHISPER_AVAILABLE = False

try:
    import whisper  # type: ignore
    _WHISPER_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# ASR 调用
# ---------------------------------------------------------------------------

# TODO: 实现公司内网 ASR 服务调用
def call_asr_api(audio_data: bytes, language: str = "zh") -> str:
    """
    调用公司内网 ASR 服务

    TODO: 接入公司内网 ASR endpoint
    - 音频格式转换（可能需要 wav 16kHz mono）
    - 认证方式（access_code / api_key）
    - 返回格式解析

    示例实现（待配置后启用）:

    import httpx

    headers = {"Authorization": f"Bearer {_ASR_API_KEY}"}
    files = {"audio": ("audio.wav", audio_data, "audio/wav")}
    response = httpx.post(
        f"{_ASR_API_BASE}/recognize",
        headers=headers,
        files=files,
        data={"language": language},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()["text"]
    """
    logger.warning("ASR API 未配置，请设置 ASR_API_BASE 和 ASR_API_KEY")
    return ""


def call_local_whisper(audio_data: bytes, language: str = "zh") -> str:
    """
    使用本地 Whisper 模型进行语音识别

    Mac mini M1 上 whisper-tiny 实时转写没问题，
    whisper-base 精度更好，速度也还可以
    """
    if not _WHISPER_AVAILABLE:
        logger.error("whisper 未安装，请运行: pip install openai-whisper")
        return ""

    try:
        model = whisper.load_model(_LOCAL_WHISPER_MODEL)

        # 写临时文件（whisper 需要文件路径）
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            result = model.transcribe(temp_path, language=language)
            text = str(result.get("text", "")).strip()
            logger.info(f"Whisper 识别结果: {text[:100]}...")
            return text
        finally:
            os.unlink(temp_path)

    except Exception as e:
        logger.error(f"本地 Whisper 识别失败: {e}")
        return ""


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

def speech_to_text(audio_data: bytes, language: str = "zh") -> str:
    """
    语音转文字 - 统一入口

    优先级：公司内网 ASR > 本地 Whisper
    """
    text = ""

    # 1. 尝试公司 ASR
    if _ASR_API_BASE:
        try:
            text = call_asr_api(audio_data, language)
            if text:
                return text
        except Exception as e:
            logger.warning(f"公司 ASR 调用失败，降级到本地: {e}")

    # 2. 降级到本地 Whisper
    if _WHISPER_AVAILABLE:
        text = call_local_whisper(audio_data, language)
        if text:
            return text

    if not text:
        logger.warning("所有 ASR 方案都不可用")

    return text


def speech_to_text_from_base64(base64_audio: str, language: str = "zh") -> str:
    """
    从 base64 编码的音频数据转文字（前端录音常用格式）
    """
    try:
        audio_data = base64.b64decode(base64_audio)
        return speech_to_text(audio_data, language)
    except Exception as e:
        logger.error(f"base64 音频解码失败: {e}")
        return ""

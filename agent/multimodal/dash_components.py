"""
Dash 前端多模态组件 - 为 AI 聊天窗口添加图片上传和语音录音

集成到 enhanced_ai_chat_manager.py 的 Dash layout 中

使用方式:
    from agent.multimodal.dash_components import create_multimodal_upload_component

    # 在聊天输入区域上方添加
    upload_component = create_multimodal_upload_component(chat_id_prefix="my-chat")
"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from dash import dcc, html, Input, Output, State, callback_context
from dash.exceptions import PreventUpdate

logger = logging.getLogger(__name__)


def create_multimodal_upload_component(chat_id_prefix: str = "chat") -> html.Div:
    """
    创建多模态上传组件（图片上传 + 录音按钮）

    包含:
    - dcc.Upload 支持拖拽/点击上传图片（支持多张）
    - 录音按钮（HTML5 MediaRecorder）
    - 已上传文件的预览区
    """
    prefix = chat_id_prefix

    return html.Div([
        # 上传区域
        dcc.Upload(
            id=f"{prefix}-image-upload",
            children=html.Div([
                html.Span("📷 ", style={"fontSize": "18px"}),
                html.Span("拖拽截图到这里，或点击上传", style={"fontSize": "13px", "color": "#888"}),
            ]),
            style={
                "width": "100%",
                "height": "50px",
                "lineHeight": "50px",
                "borderWidth": "1px",
                "borderStyle": "dashed",
                "borderRadius": "8px",
                "textAlign": "center",
                "marginBottom": "8px",
                "cursor": "pointer",
                "backgroundColor": "#f9f9f9",
            },
            multiple=True,  # 支持多张
            accept="image/*",  # 只接受图片
        ),

        # 录音按钮区域
        html.Div([
            html.Button(
                "🎤 按住录音",
                id=f"{prefix}-record-btn",
                n_clicks=0,
                style={
                    "fontSize": "13px",
                    "padding": "6px 16px",
                    "borderRadius": "20px",
                    "border": "1px solid #ddd",
                    "backgroundColor": "#fff",
                    "cursor": "pointer",
                },
            ),
            html.Span(
                id=f"{prefix}-record-status",
                children="",
                style={"fontSize": "12px", "color": "#888", "marginLeft": "8px"},
            ),
            # 隐藏的 audio store
            dcc.Store(id=f"{prefix}-audio-store", data=None),
        ], style={"marginBottom": "8px"}),

        # 已上传文件预览区
        html.Div(
            id=f"{prefix}-upload-preview",
            children=[],
            style={
                "display": "flex",
                "flexWrap": "wrap",
                "gap": "8px",
                "marginBottom": "8px",
            },
        ),

        # 隐藏的 Store 存储上传的图片数据
        dcc.Store(id=f"{prefix}-image-store", data=[]),
    ], style={"marginBottom": "8px"})


def create_multimodal_js() -> str:
    """
    生成录音功能的 JavaScript 代码

    TODO: 在 Dash 中注入这段 JS（通过 app.clientside_callback 或 index_string）
    """
    return """
    // 录音功能
    (function() {
        let mediaRecorder = null;
        let audioChunks = [];
        const recordBtn = document.getElementById('chat-record-btn');
        const recordStatus = document.getElementById('chat-record-status');
        const audioStore = document.getElementById('chat-audio-store');

        if (!recordBtn) return;

        // 按下开始录音
        recordBtn.addEventListener('mousedown', async function() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({audio: true});
                mediaRecorder = new MediaRecorder(stream);
                audioChunks = [];

                mediaRecorder.ondataavailable = function(e) {
                    audioChunks.push(e.data);
                };

                mediaRecorder.onstop = function() {
                    const blob = new Blob(audioChunks, {type: 'audio/webm'});
                    const reader = new FileReader();
                    reader.onloadend = function() {
                        const base64 = reader.result.split(',')[1];
                        // 存到 Dash Store
                        if (audioStore) {
                            audioStore.data = base64;
                            // 触发 Dash callback
                            const event = new Event('input', {bubbles: true});
                            audioStore.dispatchEvent(event);
                        }
                    };
                    reader.readAsDataURL(blob);
                    stream.getTracks().forEach(t => t.stop());
                };

                mediaRecorder.start();
                recordStatus.textContent = '🔴 录音中...';
                recordBtn.style.backgroundColor = '#ffe0e0';
            } catch(err) {
                recordStatus.textContent = '❌ 无法访问麦克风';
            }
        });

        // 松开停止录音
        recordBtn.addEventListener('mouseup', function() {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
                recordStatus.textContent = '✅ 录音完成';
                recordBtn.style.backgroundColor = '#fff';
            }
        });

        recordBtn.addEventListener('mouseleave', function() {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
                recordStatus.textContent = '✅ 录音完成';
                recordBtn.style.backgroundColor = '#fff';
            }
        });
    })();
    """


# ---------------------------------------------------------------------------
# Dash Callbacks - 需要在 app 初始化时注册
# ---------------------------------------------------------------------------

def register_multimodal_callbacks(app, chat_id_prefix: str = "chat"):
    """
    注册多模态相关的 Dash callbacks

    在 EnhancedAIChatManager 初始化时调用:
        register_multimodal_callbacks(app, chat_id_prefix=self.chat_id_prefix)
    """
    prefix = chat_id_prefix

    @app.callback(
        [
            Output(f"{prefix}-image-store", "data"),
            Output(f"{prefix}-upload-preview", "children"),
        ],
        Input(f"{prefix}-image-upload", "contents"),
        State(f"{prefix}-image-upload", "filename"),
        State(f"{prefix}-image-store", "data"),
        prevent_initial_call=True,
    )
    def handle_image_upload(contents_list, filenames, existing_data):
        """处理图片上传，存储 base64 数据并显示预览"""
        if not contents_list:
            raise PreventUpdate

        existing = existing_data or []

        for i, contents in enumerate(contents_list):
            # contents 格式: "data:image/png;base64,iVBORw0KGgo..."
            if contents:
                # 提取纯 base64 部分
                parts = contents.split(",", 1)
                if len(parts) == 2:
                    b64_data = parts[1]
                    mime = parts[0].split(";")[0].split(":")[1] if ":" in parts[0] else "image/png"
                    filename = filenames[i] if i < len(filenames) else f"image_{i}.png"
                    existing.append({
                        "filename": filename,
                        "base64": b64_data,
                        "mime": mime,
                    })

        # 生成预览
        previews = []
        for item in existing:
            previews.append(html.Div([
                html.Img(
                    src=f"data:{item['mime']};base64,{item['base64'][:100]}...",
                    style={"width": "60px", "height": "60px", "objectFit": "cover", "borderRadius": "4px"},
                ),
                html.Div(item["filename"], style={"fontSize": "10px", "maxWidth": "60px", "overflow": "hidden"}),
            ], style={"display": "inline-block", "textAlign": "center"}))

        return existing, previews

    @app.callback(
        Output(f"{prefix}-record-status", "children"),
        Input(f"{prefix}-audio-store", "data"),
        prevent_initial_call=True,
    )
    def handle_audio_recorded(audio_data):
        """处理录音完成"""
        if audio_data:
            return "✅ 语音已录制，发送时将自动识别"
        return ""


# ---------------------------------------------------------------------------
# 工具函数 - 从 Dash Store 数据提取图片 bytes
# ---------------------------------------------------------------------------

def extract_image_bytes_from_store(store_data: List[Dict[str, str]]) -> List[bytes]:
    """
    从 Dash Store 中提取图片 bytes 数据

    Args:
        store_data: [{"filename": "xx.png", "base64": "...", "mime": "image/png"}, ...]

    Returns:
        图片 bytes 列表
    """
    images = []
    for item in (store_data or []):
        try:
            img_bytes = base64.b64decode(item["base64"])
            images.append(img_bytes)
        except Exception as e:
            logger.warning(f"图片解码失败 {item.get('filename', '?')}: {e}")
    return images


def extract_audio_bytes_from_store(audio_base64: Optional[str]) -> Optional[bytes]:
    """从 Dash Store 中提取音频 bytes"""
    if not audio_base64:
        return None
    try:
        return base64.b64decode(audio_base64)
    except Exception as e:
        logger.warning(f"音频解码失败: {e}")
        return None

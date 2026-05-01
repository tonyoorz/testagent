# agent/multimodal - 多模态输入支持

为 duplicate detection 对话增加图片和语音识别能力。

## 模块说明

| 文件 | 功能 |
|------|------|
| `image_parser.py` | 图片 → 结构化 ticket 信息（GLM Vision） |
| `speech_to_text.py` | 语音 → 文字（公司 ASR / 本地 Whisper） |
| `multimodal_router.py` | 统一入口，路由文字/图片/语音 |
| `duplicate_search_multimodal.py` | 多模态 duplicate 搜索（对接现有链路） |
| `dash_components.py` | Dash 前端组件（上传 + 录音） |

## 使用方式

### 后端：多模态 duplicate 搜索

```python
from agent.multimodal.duplicate_search_multimodal import MultimodalDuplicateSearcher

searcher = MultimodalDuplicateSearcher()

# 纯文字（和之前一样）
result = searcher.search(text="刹车时有异响", df=defects_df)

# 图片（截图 ticket）
with open("screenshot.png", "rb") as f:
    result = searcher.search(images=[f.read()], df=defects_df)

# 语音
with open("recording.webm", "rb") as f:
    result = searcher.search(audio=f.read(), df=defects_df)

# 混合
result = searcher.search(
    text="这个和之前的问题类似",
    images=[screenshot_bytes],
    df=defects_df,
)

# 结果
# result["summary"]["total"] → 提取了几个 ticket
# result["summary"]["duplicates"] → 疑似重复数
# result["summary"]["new_issues"] → 可能是新问题
# result["results"][0]["candidates"] → 每个ticket的候选重复
```

### 前端：Dash 集成

在 `enhanced_ai_chat_manager.py` 中：

```python
from agent.multimodal.dash_components import (
    create_multimodal_upload_component,
    register_multimodal_callbacks,
    extract_image_bytes_from_store,
    extract_audio_bytes_from_store,
)

# 1. 在聊天 layout 中添加上传组件
upload = create_multimodal_upload_component(chat_id_prefix=self.chat_id_prefix)

# 2. 注册 callbacks
register_multimodal_callbacks(app, chat_id_prefix=self.chat_id_prefix)

# 3. 在发送消息时，读取 Store 中的数据
images = extract_image_bytes_from_store(image_store_data)
audio = extract_audio_bytes_from_store(audio_store_data)

# 4. 调用搜索
result = searcher.search(text=question, images=images, audio=audio, df=df)
```

## TODO（待配置）

### 必须完成

1. **GLM 多模态 endpoint 配置** (`image_parser.py`)
   - 设置 `_VISION_API_BASE` 和 `_VISION_API_KEY`
   - 实现 `call_vision_api()` 函数
   - 格式：OpenAI 兼容 chat/completions，带 image_url content type

2. **ASR 服务配置** (`speech_to_text.py`)
   - 如果公司有 ASR 服务：设置 `ASR_API_BASE` 和 `ASR_API_KEY`
   - 如果没有：安装本地 Whisper `pip install openai-whisper`

### 可选优化

3. **Dash 录音 JS 注入** — 需要在 Dash app 中注入 `create_multimodal_js()` 的 JS 代码
4. **批量模式 UI** — 批量搜索结果的展示组件（表格/卡片视图）
5. **图片压缩** — 大截图在上传前压缩，减少传输时间
6. **缓存** — 已解析的图片结果缓存，避免重复调用 LLM

## 依赖

```
# 必需
pip install httpx

# 语音识别（二选一）
pip install openai-whisper  # 本地 ASR
# 或配置公司内网 ASR 服务

# 前端
# Dash 自带 dcc.Upload，无额外依赖
```

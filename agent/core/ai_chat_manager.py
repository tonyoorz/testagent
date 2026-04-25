"""
AI聊天管理模块 - 集成版本
统一管理所有看板的AI对话功能，包含配置、流式聊天和测试功能
"""

import os
import sys
import time
import json
import queue
import logging
import threading
import traceback
import pandas as pd
import requests
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable, Generator
import io
import uuid

from agent.core.harness_config import load_llm_provider_config, load_workspace_env
from duplicate_issue_finder import extract_hints, get_or_build_index

load_workspace_env()

# ============================================================================
# DeepSeek API 配置部分
# ============================================================================

_DEFAULT_INTERNAL_BASE = "https://aistudio.bmwbrill.cn/api/service/163/ernie/v2/chat/completions"
_DEFAULT_INTERNAL_MODEL = "glm-5"
_DEFAULT_PUBLIC_BASE = "https://api.deepseek.com/v1"
_DEFAULT_PUBLIC_MODEL = "deepseek-reasoner"
_DEFAULT_MOONSHOT_BASE = "https://api.moonshot.cn/v1"
_DEFAULT_MOONSHOT_MODEL = "kimi-k2.5"
_DEFAULT_INTERNAL_TEMPLATE_URL = "https://aistudio.bmwbrill.cn/api/service/163/ernie/v2/chat/completions"

HARDCODED_DEEPSEEK_ACCESS_CODE = "7FD25E1BD6124A1C8BF29030C8BFC43E"
HARDCODED_DEEPSEEK_API_KEY = ""
HARDCODED_DEEPSEEK_API_BASE = "https://aistudio.bmwbrill.cn/api/service/163/ernie/v2/chat/completions"
HARDCODED_DEEPSEEK_MODEL = "glm-5"
HARDCODED_DEEPSEEK_API_KEY_BACKUP = "sk-e1a77ca98a30498ca33acc7f803f0d41"
HARDCODED_DEEPSEEK_API_BASE_BACKUP = ""
HARDCODED_DEEPSEEK_MODEL_BACKUP = ""

_PROVIDER_CONFIG = load_llm_provider_config(
    hardcoded_access_code=HARDCODED_DEEPSEEK_ACCESS_CODE,
    hardcoded_api_key=HARDCODED_DEEPSEEK_API_KEY,
    hardcoded_api_base=HARDCODED_DEEPSEEK_API_BASE,
    hardcoded_model=HARDCODED_DEEPSEEK_MODEL,
    hardcoded_backup_api_key=HARDCODED_DEEPSEEK_API_KEY_BACKUP,
    hardcoded_backup_api_base=HARDCODED_DEEPSEEK_API_BASE_BACKUP,
    hardcoded_backup_model=HARDCODED_DEEPSEEK_MODEL_BACKUP,
    default_internal_base=_DEFAULT_INTERNAL_BASE,
    default_internal_model=_DEFAULT_INTERNAL_MODEL,
    default_public_base=_DEFAULT_PUBLIC_BASE,
    default_public_model=_DEFAULT_PUBLIC_MODEL,
    default_moonshot_base=_DEFAULT_MOONSHOT_BASE,
    default_moonshot_model=_DEFAULT_MOONSHOT_MODEL,
    default_internal_template_url=_DEFAULT_INTERNAL_TEMPLATE_URL,
)

ACCESS_CODE = _PROVIDER_CONFIG.access_code
DEEPSEEK_API_KEY = _PROVIDER_CONFIG.primary_api_key
DEEPSEEK_API_BASE = _PROVIDER_CONFIG.primary_api_base
DEEPSEEK_MODEL = _PROVIDER_CONFIG.primary_model
DEEPSEEK_API_KEY_BACKUP = _PROVIDER_CONFIG.backup_api_key
DEEPSEEK_API_BASE_BACKUP = _PROVIDER_CONFIG.backup_api_base
DEEPSEEK_MODEL_BACKUP = _PROVIDER_CONFIG.backup_model
INTERNAL_TEMPLATE_URL = _PROVIDER_CONFIG.internal_template_url

# Chat Configuration
DEFAULT_TEMPERATURE = _PROVIDER_CONFIG.default_temperature
DEFAULT_MAX_TOKENS = _PROVIDER_CONFIG.default_max_tokens
DEFAULT_STREAM = _PROVIDER_CONFIG.default_stream

# SSL验证设置 - 内网环境可能需要禁用SSL验证
VERIFY_SSL = _PROVIDER_CONFIG.verify_ssl

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# DeepSeek 流式聊天处理器
# ============================================================================

# 全局流式数据存储
streaming_data = {}
streaming_lock = threading.Lock()

class DeepSeekStreamingChat:
    """优化的DeepSeek流式聊天类，支持推理过程显示和性能优化"""
    
    def __init__(self, api_key: str = None, model: str = DEEPSEEK_MODEL, api_base: str = None):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.access_code = ACCESS_CODE
        self.model = model
        self.api_base = api_base or DEEPSEEK_API_BASE
        self.client = self._create_client(self.api_key, self.api_base) if self._should_use_openai_client(self.api_key, self.api_base) else None
        self.response_queue = queue.Queue()
        self.streaming_active = False
        # 备用API参数
        self.backup_api_key = DEEPSEEK_API_KEY_BACKUP
        self.backup_api_base = DEEPSEEK_API_BASE_BACKUP
        self.backup_model = DEEPSEEK_MODEL_BACKUP

    def _is_internal_direct_endpoint(self, api_base: Optional[str]) -> bool:
        base = str(api_base or "")
        return "/api/service/" in base and "/chat/completions" in base

    def _should_use_openai_client(self, api_key: Optional[str], api_base: Optional[str]) -> bool:
        return bool(api_key) and not self._is_internal_direct_endpoint(api_base)

    def _build_openai_compat_url(self) -> str:
        base = (self.api_base or "").rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return base + "/chat/completions"
        
    def _create_client(self, api_key, api_base):
        """创建优化的HTTP客户端"""
        import httpx
        from openai import OpenAI
        
        http_client = httpx.Client(
            verify=False,
            timeout=120,  # 增加超时时间
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        
        return OpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=120,
            http_client=http_client
        )

    def _resolve_temperature(self, temperature: float, model: str, api_base: str):
        model_text = (model or "").lower()
        base_text = (api_base or "").lower()
        if "kimi" in model_text or "moonshot.cn" in base_text:
            return 1
        return temperature

    def _extract_access_code(self) -> str:
        key = str(self.api_key or "").strip()
        if key.startswith("ACCESSCODE"):
            parts = key.split(" ", 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
        return str(self.access_code or "").strip()

    def _should_use_internal_template_for_nonstream(self) -> bool:
        # 只要能拿到 access_code，就优先走已验证可用的内网模板接口。
        return bool(self._extract_access_code())

    def _resolve_internal_template_url(self) -> str:
        tmpl = os.environ.get("DEEPSEEK_INTERNAL_TEMPLATE_URL") or INTERNAL_TEMPLATE_URL
        code = self._extract_access_code()
        if not code:
            raise ValueError("未配置 access code，无法调用内网模板接口")
        return tmpl.format(access_code=code)

    def _request_internal_template_nonstream(self, messages: List[Dict[str, str]],
                                             temperature: float, max_tokens: int) -> str:
        url = self._resolve_internal_template_url()
        access_code = self._extract_access_code()
        if not access_code:
            raise ValueError("未配置 access code，无法调用内网GLM-5接口")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self._resolve_temperature(temperature, self.model, self.api_base),
            "stream": False,
        }
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"ACCESSCODE {access_code}",
        }
        timeout_sec = float(os.environ.get("DEEPSEEK_INTERNAL_TIMEOUT", "120"))
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout_sec, verify=False)
        resp.raise_for_status()
        try:
            obj = resp.json()
        except Exception:
            text = (resp.text or "").strip()
            if text:
                return text
            raise RuntimeError("内网模板接口返回空响应")

        if isinstance(obj, dict) and obj.get("code") and obj.get("message"):
            raise RuntimeError(f"内网模板接口错误: code={obj.get('code')}, message={obj.get('message')}")

        choices = obj.get("choices") if isinstance(obj, dict) else None
        if isinstance(choices, list) and choices:
            msg = (choices[0] or {}).get("message") or {}
            content = msg.get("content")
            if isinstance(content, list):
                content = "".join([str(x.get("text") or x.get("content") or "") if isinstance(x, dict) else str(x) for x in content])
            if content is not None:
                return str(content).strip()

        for k in ("content", "response", "answer", "text"):
            if isinstance(obj, dict) and obj.get(k) is not None:
                return str(obj.get(k)).strip()

        return json.dumps(obj, ensure_ascii=False)

    def _probe_non_stream_error(self, messages: List[Dict[str, str]], temperature: float, max_tokens: int) -> str:
        """在SDK返回结构异常时，直接探测原始HTTP返回，给出可读错误。"""
        try:
            url = self._build_openai_compat_url()
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self._resolve_temperature(temperature, self.model, self.api_base),
                "max_tokens": max_tokens,
                "stream": False,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=45, verify=False)
            text = (resp.text or "").strip()
            try:
                obj = resp.json()
            except Exception:
                obj = None
            if isinstance(obj, dict):
                code = obj.get("code")
                msg = obj.get("message") or obj.get("error") or text[:300]
                return f"HTTP {resp.status_code}; code={code}; message={msg}"
            return f"HTTP {resp.status_code}; body={text[:300]}"
        except Exception as e:
            return f"raw probe failed: {e}"
    
    def validate_api_key(self) -> bool:
        """验证API密钥"""
        if not self.api_key:
            return False
        if self.api_key == "your-api-key-here":
            return False
        return True

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1200,
    ) -> str:
        if not self.validate_api_key():
            raise ValueError("未配置可用的 DEEPSEEK_API_KEY")
        if self._should_use_internal_template_for_nonstream():
            try:
                return self._request_internal_template_nonstream(messages, temperature, max_tokens)
            except Exception as e:
                if self._is_internal_direct_endpoint(self.api_base):
                    raise RuntimeError(f"内网GLM-5接口调用失败: {e}") from e
                logger.warning(f"内网模板接口调用失败，回退OpenAI兼容链路: {e}")

        if not self.client:
            if self._is_internal_direct_endpoint(self.api_base):
                raise RuntimeError("当前内网接口不是OpenAI兼容base_url，已阻止错误回退链路")
            self.client = self._create_client(self.api_key, self.api_base)
        try:
            resolved_temperature = self._resolve_temperature(temperature, self.model, self.api_base)
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=resolved_temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            choices = getattr(resp, "choices", None)
            if not choices:
                detail = self._probe_non_stream_error(messages, temperature, max_tokens)
                raise RuntimeError(f"LLM响应缺少choices。{detail}")
            first_choice = choices[0]
            msg_obj = getattr(first_choice, "message", None)
            content = getattr(msg_obj, "content", None) if msg_obj is not None else None
            if content is None:
                detail = self._probe_non_stream_error(messages, temperature, max_tokens)
                raise RuntimeError(f"LLM响应content为空。{detail}")
            return str(content).strip()
        except Exception as e:
            if not self.backup_api_key:
                raise
            try:
                backup_client = self._create_client(self.backup_api_key, self.backup_api_base)
                resolved_temperature = self._resolve_temperature(temperature, self.backup_model, self.backup_api_base)
                resp = backup_client.chat.completions.create(
                    model=self.backup_model,
                    messages=messages,
                    temperature=resolved_temperature,
                    max_tokens=max_tokens,
                    stream=False,
                )
                choices = getattr(resp, "choices", None)
                if not choices:
                    raise RuntimeError("备用模型响应缺少choices")
                msg_obj = getattr(choices[0], "message", None)
                content = getattr(msg_obj, "content", None) if msg_obj is not None else None
                if content is None:
                    raise RuntimeError("备用模型响应content为空")
                return str(content).strip()
            except Exception:
                raise e
    
    def stream_chat_response_optimized(self, messages: List[Dict[str, str]], 
                                    task_id: str,
                                    temperature: float = 0.7, 
                                    max_tokens: int = 2000) -> Generator[str, None, None]:
        """优化的流式响应生成器，支持推理过程显示，主API失败时自动切换备用API"""
        with streaming_lock:
            streaming_data.setdefault(task_id, {
                'status': 'initializing',
                'reasoning': '',
                'response': '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'progress': 'AI正在初始化...',
                'chunk_buffer': '',
                'last_update': time.time()
            })
        try:
            yield from self._try_stream(messages, task_id, temperature, max_tokens, use_backup=False)
        except Exception as e:
            if self.backup_api_key:
                print(f"主DeepSeek API调用失败，尝试备用API... 错误: {e}")
                try:
                    yield from self._try_stream(messages, task_id, temperature, max_tokens, use_backup=True)
                    return
                except Exception as e2:
                    error_msg = f"主API和备用API均失败: {e2}"
            else:
                error_msg = f"主DeepSeek API调用失败: {e}"
            print(error_msg)
            with streaming_lock:
                streaming_data.setdefault(task_id, {})['status'] = 'error'
                streaming_data[task_id]['error'] = error_msg
            yield f"error:{error_msg}"
    
    def _try_stream(self, messages, task_id, temperature, max_tokens, use_backup=False):
        # 切换API参数
        if use_backup:
            if not self.backup_api_key:
                raise ValueError("未配置备用API密钥，请设置 DEEPSEEK_API_KEY_BACKUP")
            client = self._create_client(self.backup_api_key, self.backup_api_base)
            model = self.backup_model
            # 备用API也使用流式响应
            with streaming_lock:
                if task_id in streaming_data:
                    streaming_data[task_id].update({
                        'status': 'processing',
                        'progress': 'AI正在连接(备用)...',
                        'last_update': time.time()
                    })
                else:
                    streaming_data[task_id] = {
                        'status': 'processing',
                        'reasoning': '',
                        'response': '',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'progress': 'AI正在连接(备用)...',
                        'chunk_buffer': '',
                        'last_update': time.time()
                    }
            
            # 备用API流式处理
            reasoning_content = ""
            content = ""
            chunk_buffer = ""
            last_yield_time = time.time()
            reasoning_yielded = False
            
            for chunk in client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,  # 改为流式
                max_tokens=max_tokens,
                temperature=self._resolve_temperature(temperature, model, self.backup_api_base)
            ):
                try:
                    current_time = time.time()
                    # 处理推理过程 (DeepSeek-R1 特有)
                    if hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                        reasoning_chunk = chunk.choices[0].delta.reasoning_content
                        reasoning_content += reasoning_chunk
                        with streaming_lock:
                            streaming_data[task_id]['reasoning'] = reasoning_content
                            streaming_data[task_id]['progress'] = 'AI正在深度思考(备用)...'
                            streaming_data[task_id]['last_update'] = current_time
                        # 持续yield推理内容更新
                        yield f"reasoning:{reasoning_content}"
                        reasoning_yielded = True
                    elif chunk.choices[0].delta.content:
                        content_chunk = chunk.choices[0].delta.content
                        content += content_chunk
                        chunk_buffer += content_chunk
                        
                        # 批量输出优化 - 每50ms或累积5个字符输出一次
                        if (current_time - last_yield_time > 0.05) or len(chunk_buffer) >= 5:
                            with streaming_lock:
                                streaming_data[task_id]['response'] = content
                                streaming_data[task_id]['progress'] = 'AI正在回答(备用)...'
                                streaming_data[task_id]['chunk_buffer'] = chunk_buffer
                                streaming_data[task_id]['last_update'] = current_time
                            
                            yield f"content:{chunk_buffer}"
                            chunk_buffer = ""
                            last_yield_time = current_time
                            
                except Exception as e:
                    print(f"处理备用API流式数据块时出错: {e}")
                    continue
            
            # 输出剩余内容
            if chunk_buffer:
                with streaming_lock:
                    streaming_data[task_id]['response'] = content
                    streaming_data[task_id]['chunk_buffer'] = chunk_buffer
                yield f"content:{chunk_buffer}"
            
            # 完成标记
            with streaming_lock:
                streaming_data[task_id]['status'] = 'completed'
                streaming_data[task_id]['progress'] = '完成'
            yield "done:完成"
            return
        else:
            # 内网主链路统一走已验证可用的 access_code 模板接口。
            if self._should_use_internal_template_for_nonstream():
                with streaming_lock:
                    streaming_data.setdefault(task_id, {})
                    streaming_data[task_id].update({
                        'status': 'processing',
                        'progress': 'AI正在连接(v3.2模板)...',
                        'last_update': time.time(),
                    })

                full_text = self._request_internal_template_nonstream(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                full_text = str(full_text or "")

                content = ""
                chunk_buf = ""
                last_emit = time.time()
                for ch in full_text:
                    content += ch
                    chunk_buf += ch
                    now = time.time()
                    if len(chunk_buf) >= 24 or (now - last_emit) > 0.05:
                        with streaming_lock:
                            streaming_data[task_id]['response'] = content
                            streaming_data[task_id]['progress'] = 'AI正在回答(v3.2模板)...'
                            streaming_data[task_id]['last_update'] = now
                        yield f"content:{chunk_buf}"
                        chunk_buf = ""
                        last_emit = now

                if chunk_buf:
                    with streaming_lock:
                        streaming_data[task_id]['response'] = content
                        streaming_data[task_id]['last_update'] = time.time()
                    yield f"content:{chunk_buf}"

                with streaming_lock:
                    streaming_data[task_id]['status'] = 'completed'
                    streaming_data[task_id]['progress'] = '完成'
                    streaming_data[task_id]['last_update'] = time.time()
                yield "done:完成"
                return

            if not self.client:
                raise ValueError("未配置API密钥，请设置 DEEPSEEK_API_KEY 或 DEEPSEEK_ACCESS_CODE")
            client = self.client
            model = self.model
            
            # 主API也需要初始化streaming_data
            with streaming_lock:
                if task_id in streaming_data:
                    streaming_data[task_id].update({
                        'status': 'processing',
                        'progress': 'AI正在连接...',
                        'last_update': time.time()
                    })
                else:
                    streaming_data[task_id] = {
                        'status': 'processing',
                        'reasoning': '',
                        'response': '',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'progress': 'AI正在连接...',
                        'chunk_buffer': '',
                        'last_update': time.time()
                    }
        
        # --- 内网流式 ---
        reasoning_content = ""
        content = ""
        chunk_buffer = ""
        last_yield_time = time.time()
        reasoning_yielded = False
        for chunk in client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            temperature=self._resolve_temperature(temperature, model, self.api_base)
        ):
            try:
                current_time = time.time()
                # 处理推理过程 (DeepSeek-R1 特有)
                if hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                    reasoning_chunk = chunk.choices[0].delta.reasoning_content
                    reasoning_content += reasoning_chunk
                    with streaming_lock:
                        streaming_data[task_id]['reasoning'] = reasoning_content
                        streaming_data[task_id]['progress'] = 'AI正在深度思考...'
                        streaming_data[task_id]['last_update'] = current_time
                    # 持续yield推理内容更新
                    yield f"reasoning:{reasoning_content}"
                    reasoning_yielded = True
                elif chunk.choices[0].delta.content:
                    content_chunk = chunk.choices[0].delta.content
                    content += content_chunk
                    chunk_buffer += content_chunk
                    should_yield = (
                        len(chunk_buffer) >= 50 or
                        current_time - last_yield_time > 0.5 or
                        '\n' in chunk_buffer or
                        '。' in chunk_buffer or '！' in chunk_buffer or '？' in chunk_buffer
                    )
                    if should_yield:
                        with streaming_lock:
                            streaming_data[task_id]['response'] = content
                            streaming_data[task_id]['progress'] = 'AI正在回复...'
                            streaming_data[task_id]['last_update'] = current_time
                        # yield content内容
                        yield f"content:{chunk_buffer}"
                        chunk_buffer = ""
                        last_yield_time = current_time
            except Exception as e:
                print(f"处理chunk时出错: {e}")
                continue
        if chunk_buffer:
            with streaming_lock:
                streaming_data[task_id]['response'] = content
            yield f"content:{chunk_buffer}"
        with streaming_lock:
            streaming_data[task_id]['status'] = 'completed'
            streaming_data[task_id]['progress'] = '完成'
        yield "done:完成"
    
    def start_optimized_streaming_thread(self, messages: List[Dict[str, str]], 
                                       task_id: str,
                                       temperature: float = 0.7, 
                                       max_tokens: int = 2000):
        """启动优化的流式处理线程"""
        self.streaming_active = True
        
        # 提前初始化流式数据
        with streaming_lock:
            streaming_data[task_id] = {
                'status': 'initializing',
                'reasoning': '',
                'response': '',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'progress': 'AI正在初始化...',
                'chunk_buffer': '',
                'last_update': time.time()
            }
        
        def streaming_worker():
            try:
                for chunk in self.stream_chat_response_optimized(messages, task_id, temperature, max_tokens):
                    if not self.streaming_active:
                        break
                    self.response_queue.put(chunk)
                    
            except Exception as e:
                err = f"流式处理错误: {str(e)}"
                with streaming_lock:
                    if task_id in streaming_data:
                        streaming_data[task_id]['status'] = 'error'
                        streaming_data[task_id]['error'] = err
                        streaming_data[task_id]['progress'] = '失败'
                        streaming_data[task_id]['last_update'] = time.time()
                    else:
                        streaming_data[task_id] = {
                            'status': 'error',
                            'reasoning': '',
                            'response': '',
                            'error': err,
                            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'progress': '失败',
                            'chunk_buffer': '',
                            'last_update': time.time()
                        }
                self.response_queue.put(f"error:{err}")
            finally:
                if self.streaming_active:
                    self.response_queue.put("done:完成")
        
        thread = threading.Thread(target=streaming_worker, daemon=True)
        thread.start()
    
    def get_streaming_data(self, task_id: str) -> Dict:
        """获取流式数据"""
        with streaming_lock:
            return streaming_data.get(task_id, {})
    
    def clear_streaming_data(self, task_id: str):
        """清理流式数据"""
        with streaming_lock:
            if task_id in streaming_data:
                del streaming_data[task_id]

# ============================================================================
# AI聊天管理器
# ============================================================================


# ============================================================================
# Streaming Data Cleanup
# ============================================================================

def cleanup_stale_streaming_data(max_age_seconds: int = 300):
    """
    Clean up stale streaming data that hasn't been updated recently
    
    Args:
        max_age_seconds: Maximum age in seconds before data is considered stale
    """
    current_time = time.time()
    stale_tasks = []
    
    with streaming_lock:
        for task_id, data in list(streaming_data.items()):
            last_update = data.get('last_update', 0)
            age = current_time - last_update
            
            if age > max_age_seconds:
                stale_tasks.append(task_id)
        
        for task_id in stale_tasks:
            del streaming_data[task_id]
            logger.info(f"Cleaned up stale streaming data for task {task_id} (age: {age:.1f}s)")
    
    if stale_tasks:
        logger.info(f"Cleaned up {len(stale_tasks)} stale streaming tasks")
    
    return len(stale_tasks)

class AIChatManager:
    """AI聊天管理器 - 统一处理所有看板的AI对话功能"""
    
    def __init__(self):
        """初始化AI聊天管理器"""
        self.chatbot = None
        try:
            self.chatbot = DeepSeekStreamingChat()
            logger.info("DeepSeek聊天机器人初始化成功")
        except Exception as e:
            logger.error(f"DeepSeek聊天机器人初始化失败: {e}")
            self.chatbot = None
        
        # 预设问题模板
        self.preset_questions = {
            'defect': {
                'summary': "请总结当前的缺陷数据情况",
                'risk': "请分析当前数据中的高风险问题", 
                'project': "请分析项目分布情况",
                'trend': "请给出趋势分析建议"
            },
            'defect_explore': {
                'summary': "请总结当前的缺陷和测试数据综合情况",
                'risk': "请分析高复杂度缺陷和测试覆盖的风险点",
                'project': "请对比分析各项目的缺陷与测试情况",
                'trend': "请基于缺陷趋势和测试效率给出改进建议",
                'matrix': "请分析缺陷矩阵分布和严重性问题",
                'team': "请分析测试团队效率和缺陷发现能力"
            },
            'test': {
                'summary': "请总结当前的测试覆盖率情况",
                'risk': "请分析测试覆盖率中的风险点",
                'project': "请分析各项目的测试情况", 
                'trend': "请给出测试改进建议"
            },
            'general': {
                'summary': "请总结当前数据情况",
                'analysis': "请分析当前数据",
                'insight': "请提供数据洞察",
                'recommendation': "请给出改进建议"
            }
        }
    
    def generate_data_context(self, data: pd.DataFrame, context_type: str = 'general', 
                            custom_fields: Optional[Dict[str, str]] = None) -> str:
        """
        生成数据上下文信息
        
        Args:
            data: 要分析的数据DataFrame
            context_type: 上下文类型 ('defect', 'test', 'general')
            custom_fields: 自定义字段映射 {'field_name': 'display_name'}
        
        Returns:
            格式化的数据上下文字符串
        """
        if data.empty:
            return "No data available."
        
        context_parts = [f"Current {context_type.title()} Data Summary:"]
        context_parts.append(f"- Total records: {len(data)}")
        
        # 根据不同类型添加特定分析
        if context_type == 'defect':
            context_parts.extend(self._generate_defect_context(data))
        elif context_type == 'test':
            context_parts.extend(self._generate_test_context(data))
        elif context_type == 'general':
            context_parts.extend(self._generate_general_context(data))
        
        # 添加自定义字段分析
        if custom_fields:
            for field, display_name in custom_fields.items():
                if field in data.columns:
                    field_counts = data[field].value_counts().head(5).to_dict()
                    context_parts.append(f"- {display_name}: {field_counts}")
        
        return "\n".join(context_parts)
    
    def _generate_defect_context(self, data: pd.DataFrame) -> List[str]:
        """生成缺陷数据特定上下文"""
        context_parts = []
        
        # 矩阵分布
        if 'matrix_display' in data.columns:
            matrix_counts = data['matrix_display'].value_counts().head(5).to_dict()
            context_parts.append(f"- Matrix distribution: {matrix_counts}")
        
        # 项目分布
        if 'tproject' in data.columns:
            project_counts = data['tproject'].value_counts().head(5).to_dict()
            context_parts.append(f"- Top projects: {project_counts}")
        
        # 状态分布
        if 'status_phase' in data.columns:
            status_counts = data['status_phase'].value_counts().head(5).to_dict()
            context_parts.append(f"- Status distribution: {status_counts}")
        
        # 严重性分布
        if 'severity_group' in data.columns:
            severity_counts = data['severity_group'].value_counts().to_dict()
            context_parts.append(f"- Severity distribution: {severity_counts}")
        
        return context_parts
    
    def _generate_test_context(self, data: pd.DataFrame) -> List[str]:
        """生成测试数据特定上下文"""
        context_parts = []
        
        # 测试覆盖率相关字段
        coverage_fields = ['test_coverage', 'coverage_rate', 'pass_rate']
        for field in coverage_fields:
            if field in data.columns:
                avg_value = data[field].mean()
                context_parts.append(f"- Average {field}: {avg_value:.2f}")
        
        # 测试状态分布
        if 'test_status' in data.columns:
            status_counts = data['test_status'].value_counts().to_dict()
            context_parts.append(f"- Test status distribution: {status_counts}")
        
        return context_parts
    
    def _generate_general_context(self, data: pd.DataFrame) -> List[str]:
        """生成通用数据上下文"""
        context_parts = []
        
        # 数据基本信息
        context_parts.append(f"- Columns: {len(data.columns)}")
        context_parts.append(f"- Data types: {data.dtypes.value_counts().to_dict()}")
        
        # 检查常见字段
        common_fields = ['project', 'status', 'type', 'category', 'team', 'owner']
        for field in common_fields:
            if field in data.columns:
                unique_count = data[field].nunique()
                context_parts.append(f"- Unique {field}s: {unique_count}")
        
        return context_parts
    
    def get_ai_response(self, user_message: str, data_context: str, 
                       dashboard_type: str = 'general') -> str:
        """
        获取AI响应
        
        Args:
            user_message: 用户消息
            data_context: 数据上下文
            dashboard_type: 看板类型，用于选择合适的系统提示
        
        Returns:
            AI响应内容
        """
        # 检查是否有可用的chatbot
        if self.chatbot and self.chatbot.validate_api_key():
            try:
                # 使用新的统一 Prompt 模板
                try:
                    from prompt_templates import get_system_prompt
                    system_message = get_system_prompt(dashboard_type, data_context)
                except ImportError:
                    # 降级：如果 prompt_templates 不存在，使用原简化版
                    system_prompts = {
                        'defect': "You are a helpful assistant for defect analysis.",
                        'test': "You are a helpful assistant for test coverage analysis.",
                        'trend': "You are a helpful assistant for trend analysis.",
                        'general': "You are a helpful assistant for data analysis."
                    }
                    system_message = system_prompts.get(dashboard_type, system_prompts['general'])
                    system_message += f"\n\nData context: {data_context}"

                # 添加用户问题到消息
                messages = [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message}
                ]
                
                # 获取DeepSeek API响应
                response = self.chatbot.get_simple_response(messages, temperature=0.7, max_tokens=1000)
                return response
                
            except Exception as e:
                return f"调用DeepSeek API时出现错误：{str(e)}"
        
        # 降级到简单响应
        return self.get_simple_response(user_message, data_context, dashboard_type)
    
    def get_simple_response(self, user_message: str, data_context: str, 
                          dashboard_type: str = 'general') -> str:
        """
        简单规则响应系统（作为AI API的降级方案）
        
        Args:
            user_message: 用户消息
            data_context: 数据上下文
            dashboard_type: 看板类型
        
        Returns:
            规则响应内容
        """
        user_message_lower = user_message.lower()
        
        # 提取数据上下文中的关键信息
        total_records = self._extract_total_records(data_context)
        
        if "总结" in user_message or "summary" in user_message_lower:
            response = f"基于当前{dashboard_type}数据分析：\n\n"
            response += f"• 总记录数: {total_records}\n"
            response += f"• {data_context}\n"
            
            if dashboard_type == 'defect':
                response += "\n建议重点关注高风险缺陷和TopIssue问题。"
            elif dashboard_type == 'test':
                response += "\n建议重点关注覆盖率较低的模块。"
            else:
                response += "\n建议进一步分析数据趋势和分布。"
                
        elif "风险" in user_message or "risk" in user_message_lower:
            response = f"{dashboard_type}风险分析：\n\n"
            response += f"• 当前数据量: {total_records}\n"
            if dashboard_type == 'defect':
                response += "• 建议优先处理高严重性和TopIssue缺陷\n"
                response += "• 关注矩阵位置1A-1E的高风险问题"
            elif dashboard_type == 'test':
                response += "• 建议优先提升覆盖率较低的模块\n"
                response += "• 关注失败率较高的测试用例"
            else:
                response += "• 建议识别数据异常和趋势变化\n"
                response += "• 关注关键指标的波动"
                
        elif "项目" in user_message or "project" in user_message_lower:
            response = f"{dashboard_type}项目分析：\n\n"
            response += f"• 总数据量: {total_records}\n"
            response += "• 建议分析各项目的数据分布和趋势\n"
            response += "• 识别需要重点关注的项目"
            
        elif "趋势" in user_message or "trend" in user_message_lower:
            response = f"{dashboard_type}趋势分析建议：\n\n"
            response += "• 建议定期监控关键指标变化\n"
            response += "• 分析时间序列数据找出规律\n"
            response += "• 建立预警机制及时发现异常\n"
            response += "• 跟踪改进措施的效果"
            
        else:
            response = f"感谢您的问题！我可以帮助您分析{dashboard_type}数据。请尝试询问关于数据总结、风险分析、项目分布或趋势分析的问题。"
        
        return response
    
    def _extract_total_records(self, data_context: str) -> str:
        """从数据上下文中提取总记录数"""
        try:
            for line in data_context.split('\n'):
                if 'Total records:' in line:
                    return line.split('Total records:')[1].strip()
            return "未知"
        except:
            return "未知"
    

# ============================================================================
# 测试功能
# ============================================================================

class AITestSuite:
    """AI功能测试套件"""
    
    @staticmethod
    def test_imports():
        """测试模块导入"""
        print("=" * 50)
        print("测试模块导入...")
        
        try:
            print("✓ 所有模块已在本文件中集成")
            print(f"  - API Base: {DEEPSEEK_API_BASE}")
            print(f"  - Model: {DEEPSEEK_MODEL}")
            print(f"  - API Key: {'已配置' if DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != 'your-api-key-here' else '未配置'}")
            return True
        except Exception as e:
            print(f"✗ 模块检查失败: {e}")
            return False
    
    @staticmethod
    def test_api_key():
        """测试API密钥配置"""
        print("\n" + "=" * 50)
        print("测试API密钥配置...")
        
        if not DEEPSEEK_API_KEY:
            print("✗ API密钥未设置")
            return False
        
        if DEEPSEEK_API_KEY == "your-api-key-here":
            print("✗ API密钥使用默认值，请设置真实的API密钥")
            return False
        
        if DEEPSEEK_API_KEY.startswith("ACCESSCODE"):
            print("✓ 使用BMW内网API格式")
            return True
        elif DEEPSEEK_API_KEY.startswith("sk-"):
            print("✓ 使用标准OpenAI格式")
            return True
        else:
            print("⚠️  API密钥格式未识别，但将尝试使用")
            return True
    
    @staticmethod
    def test_api_connection():
        """测试API连接"""
        print("\n" + "=" * 50)
        print("测试API连接...")
        
        try:
            chat = DeepSeekStreamingChat()
            
            if not chat.validate_api_key():
                print("✗ API密钥验证失败")
                return False
            
            print("✓ API密钥验证通过")
            
            # 测试简单的API调用
            test_messages = [
                {"role": "system", "content": "You are a helpful assistant. Answer in Chinese."},
                {"role": "user", "content": "请回复'测试成功'"}
            ]
            
            print("发送测试消息...")
            start_time = time.time()
            
            response = chat.get_simple_response(test_messages, temperature=0.1, max_tokens=50)
            
            end_time = time.time()
            response_time = end_time - start_time
            
            if "error" in response.lower() or "错误" in response:
                print(f"✗ API调用返回错误: {response}")
                return False
            
            print(f"✓ API调用成功")
            print(f"  - 响应时间: {response_time:.2f}秒")
            print(f"  - 响应内容: {response[:100]}...")
            return True
            
        except Exception as e:
            print(f"✗ API连接测试失败: {e}")
            return False
    
    @staticmethod
    def test_streaming():
        """测试流式响应"""
        print("\n" + "=" * 50)
        print("测试流式响应...")
        
        try:
            chat = DeepSeekStreamingChat()
            
            test_messages = [
                {"role": "system", "content": "You are a helpful assistant. Answer in Chinese."},
                {"role": "user", "content": "请简单介绍一下人工智能，大约50字"}
            ]
            
            print("开始流式响应测试...")
            response_chunks = []
            
            for chunk in chat.stream_chat_response_optimized(test_messages, task_id="test", temperature=0.5, max_tokens=100):
                response_chunks.append(chunk)
                print(chunk, end='', flush=True)
                
                # 如果收到错误消息，停止测试
                if chunk.startswith("Error:"):
                    print(f"\n✗ 流式响应测试失败: {chunk}")
                    return False
            
            print(f"\n✓ 流式响应测试成功")
            print(f"  - 收到 {len(response_chunks)} 个数据块")
            return True
            
        except Exception as e:
            print(f"✗ 流式响应测试失败: {e}")
            return False
    
    @staticmethod
    def run_all_tests():
        """运行所有测试"""
        print("AI功能集成测试")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        tests = [
            ("模块导入", AITestSuite.test_imports),
            ("API密钥配置", AITestSuite.test_api_key),
            ("API连接", AITestSuite.test_api_connection),
            ("流式响应", AITestSuite.test_streaming)
        ]
        
        results = []
        
        for test_name, test_func in tests:
            try:
                result = test_func()
                results.append((test_name, result))
                
                if not result:
                    print(f"\n⚠️  {test_name} 测试失败，停止后续测试")
                    break
                    
            except Exception as e:
                print(f"\n✗ {test_name} 测试异常: {e}")
                results.append((test_name, False))
                break
        
        # 输出测试结果摘要
        print("\n" + "=" * 50)
        print("测试结果摘要:")
        
        all_passed = True
        for test_name, result in results:
            status = "✓ 通过" if result else "✗ 失败"
            print(f"  {test_name}: {status}")
            if not result:
                all_passed = False
        
        if all_passed:
            print("\n🎉 所有测试通过！AI功能集成成功。")
            print("您现在可以在各个看板中使用AI对话功能了。")
        else:
            print("\n❌ 部分测试失败，请检查配置。")
        
        return all_passed

# ============================================================================
# 全局实例和样式
# ============================================================================

# 全局AI聊天管理器实例
ai_chat_manager = AIChatManager()

def get_chat_css_styles() -> str:
    """返回聊天界面所需的CSS样式"""
    return """
        .chat-quick-btn {
            background-color: #28a745;
            color: white;
            border: none;
            padding: 8px 12px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 12px;
            margin: 2px;
        }
        .chat-quick-btn:hover {
            background-color: #218838;
        }
        .user-message {
            background-color: #007bff;
            color: white;
            padding: 10px;
            border-radius: 10px;
            margin: 5px 0;
            text-align: right;
            margin-left: 20%;
        }
        .ai-message {
            background-color: #f0f0f0;
            color: black;
            padding: 10px;
            border-radius: 10px;
            margin: 5px 0;
            text-align: left;
            margin-right: 20%;
        }
        .streaming-message {
            background-color: #e9ecef;
            color: #6c757d;
            padding: 10px;
            border-radius: 10px;
            margin: 5px 0;
            text-align: left;
            margin-right: 20%;
            border-left: 3px solid #007bff;
        }
    """

# ============================================================================
# 兼容性导出（保持向后兼容）
# ============================================================================

# 导出配置常量，保持其他文件的兼容性
DEEPSEEK_API_KEY = DEEPSEEK_API_KEY
DEEPSEEK_API_BASE = DEEPSEEK_API_BASE  
DEEPSEEK_MODEL = DEEPSEEK_MODEL
VERIFY_SSL = VERIFY_SSL

# 测试入口点
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # 运行测试
        success = AITestSuite.run_all_tests()
        sys.exit(0 if success else 1)
    else:
        # 简单的功能演示
        print("AI聊天管理器 - 集成版本")
        print("使用方法：")
        print("1. 运行测试：python ai_chat_manager.py test")  
        print("2. 在其他模块中导入：from agent.core.ai_chat_manager import ai_chat_manager")
        print("3. 创建聊天界面：ai_chat_manager.create_chat_interface('chat', 'defect')")
        print("\n要运行完整测试，请执行：python ai_chat_manager.py test")

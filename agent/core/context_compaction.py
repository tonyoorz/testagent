"""
Context Compaction Service — 对话历史压缩

参照 Anthropic context engineering "Compacting the context window":
"You can have the model itself decide which information is important to preserve."

核心逻辑：
1. 当对话超过 N 轮时，自动压缩早期轮次
2. 保留最近 K 轮完整内容（working memory）
3. 将早期轮次压缩为 summary（archival memory）
4. 清除早期工具调用的原始输出（最大 token 消耗源）
"""

import re
from typing import Any, Dict, List, Optional


def compact_conversation(
    messages: List[Dict[str, Any]],
    *,
    keep_recent: int = 6,
    max_tool_output_chars: int = 500,
) -> List[Dict[str, Any]]:
    """压缩对话历史，保持最近 keep_recent 条完整。
    
    对早期消息：
    - system message 始终保留
    - tool/function 输出截断到 max_tool_output_chars
    - assistant 的长回复截断
    """
    if len(messages) <= keep_recent + 1:
        return messages

    compacted = []
    # system message always first
    start_idx = 0
    if messages and messages[0].get("role") == "system":
        compacted.append(messages[0])
        start_idx = 1

    # 确定分割点
    early = messages[start_idx:-keep_recent]
    recent = messages[-keep_recent:]

    # 压缩早期消息
    for msg in early:
        compacted.append(_compact_message(msg, max_tool_output_chars))

    # 最近的消息保持完整
    compacted.extend(recent)
    return compacted


def _compact_message(
    msg: Dict[str, Any], max_output_chars: int
) -> Dict[str, Any]:
    """压缩单条消息"""
    role = msg.get("role", "")

    # tool/function 消息 — 截断输出
    if role in ("tool", "function"):
        content = str(msg.get("content", ""))
        if len(content) > max_output_chars:
            msg = dict(msg)
            msg["content"] = (
                content[:max_output_chars]
                + f"\n... [truncated, was {len(content)} chars]"
            )
        return msg

    # assistant 的长回复 — 保留前 N 字符
    if role == "assistant":
        content = str(msg.get("content", ""))
        if len(content) > 1200:
            msg = dict(msg)
            msg["content"] = (
                content[:1000]
                + f"\n... [truncated from {len(content)} chars]"
            )
        # 清除 tool_calls 中的大参数
        if msg.get("tool_calls"):
            msg = dict(msg)
            msg["tool_calls"] = _compact_tool_calls(msg["tool_calls"])
        return msg

    return msg


def _compact_tool_calls(tool_calls: List[Any]) -> List[Any]:
    """截断 tool_calls 中过大的参数"""
    compacted = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            tc = dict(tc)
            func = tc.get("function", {})
            if isinstance(func, dict):
                args = str(func.get("arguments", ""))
                if len(args) > 500:
                    func = dict(func)
                    func["arguments"] = args[:400] + "..."
                    tc["function"] = func
        compacted.append(tc)
    return compacted


def build_conversation_summary(messages: List[Dict[str, Any]]) -> str:
    """从对话历史生成结构化摘要（纯确定性，不依赖 LLM）。
    
    提取：
    - 用户提过的问题列表
    - 涉及的 SQL 和关键数据
    - 分析结论
    """
    questions = []
    sql_snippets = []
    key_findings = []

    for msg in messages:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))

        if role == "user":
            # 提取用户问题
            text = content.strip()
            if text and len(text) > 5:
                questions.append(text[:200])

        elif role in ("tool", "function"):
            # 提取 SQL
            sql_match = re.search(r"(SELECT\s+.+?(?:LIMIT\s+\d+|$))", content, re.IGNORECASE | re.DOTALL)
            if sql_match:
                sql_snippets.append(sql_match.group(1)[:300])

        elif role == "assistant":
            # 提取结论性语句
            for line in content.split("\n"):
                line = line.strip()
                if len(line) > 20 and any(kw in line for kw in ("总结", "结论", "建议", "发现", "因此", "说明", "关键")):
                    key_findings.append(line[:200])

    lines = []
    if questions:
        lines.append("用户问题: " + " → ".join(questions[-5:]))
    if sql_snippets:
        lines.append("执行的SQL: " + " | ".join(sql_snippets[-3:]))
    if key_findings:
        lines.append("关键发现: " + "; ".join(key_findings[-3:]))

    return "\n".join(lines) if lines else ""


def estimate_token_count(messages: List[Dict[str, Any]]) -> int:
    """粗估消息列表的 token 数（1 token ≈ 4 chars for English, 2 chars for Chinese）"""
    total_chars = 0
    for msg in messages:
        content = str(msg.get("content", ""))
        total_chars += len(content)
        # tool_calls 参数
        for tc in (msg.get("tool_calls") or []):
            if isinstance(tc, dict):
                func = tc.get("function", {})
                if isinstance(func, dict):
                    total_chars += len(str(func.get("arguments", "")))
    # 混合语言，取 3 chars/token 中间值
    return total_chars // 3


__all__ = [
    "compact_conversation",
    "build_conversation_summary",
    "estimate_token_count",
]

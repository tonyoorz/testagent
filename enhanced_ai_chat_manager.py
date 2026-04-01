"""Compatibility wrapper for the root enhanced chat manager entrypoint."""

from agent.core.enhanced_ai_chat_manager import (
    DifyWorkflowClient,
    EnhancedAIChatManager,
    create_enhanced_chat_manager,
)

__all__ = [
    "DifyWorkflowClient",
    "EnhancedAIChatManager",
    "create_enhanced_chat_manager",
]
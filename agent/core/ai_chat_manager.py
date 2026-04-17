"""Compatibility shim for archived core chat manager implementation.

The original implementation now lives in agent.legacy.ai_chat_manager_legacy.
Keep this module path stable for existing imports.
"""

from agent.legacy.ai_chat_manager_legacy import *  # noqa: F401,F403


if __name__ == "__main__":
    import runpy

    runpy.run_module("agent.legacy.ai_chat_manager_legacy", run_name="__main__")

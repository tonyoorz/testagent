import unittest

from agent.core.ai_chat_manager import get_chat_css_styles as core_get_chat_css_styles
from agent.core.enhanced_ai_chat_manager import (
    EnhancedAIChatManager as CoreEnhancedAIChatManager,
    create_enhanced_chat_manager as core_create_enhanced_chat_manager,
)
from agent.core.intelligent_agent import (
    ToolExecutor as CoreToolExecutor,
    build_default_tools as core_build_default_tools,
)
from ai_chat_manager import get_chat_css_styles
from enhanced_ai_chat_manager import create_enhanced_chat_manager
from intelligent_agent import ToolExecutor, build_default_tools


class RootWrapperCompatibilityTests(unittest.TestCase):
    def test_root_exports_reference_core_symbols(self):
        self.assertIs(ToolExecutor, CoreToolExecutor)
        self.assertIs(build_default_tools, core_build_default_tools)
        self.assertIs(get_chat_css_styles, core_get_chat_css_styles)
        self.assertIs(create_enhanced_chat_manager, core_create_enhanced_chat_manager)

    def test_root_wrappers_smoke(self):
        executor = ToolExecutor()
        self.assertIn("analyze_trend", executor.tools)
        self.assertTrue(get_chat_css_styles())

        manager = create_enhanced_chat_manager(
            dashboard_type="defect_explore",
            use_agent=False,
            assistant_name="SiSi",
        )
        self.assertIsInstance(manager, CoreEnhancedAIChatManager)
        self.assertFalse(manager.use_agent)
        self.assertIsNone(getattr(manager, "intelligent_agent", None))


if __name__ == "__main__":
    unittest.main()
"""
Tool Registry — 统一工具注册中心

自动发现 agent/tools/ 下的工具模块，集中管理 Schema。
支持两种模式：
1. legacy：使用 build_default_tools()（现有行为，不改）
2. registry：自动发现新注册的工具

Usage::

    from agent.tools.registry import ToolRegistry

    registry = ToolRegistry()
    all_tools = registry.instantiate_all(db_path="...", llm=...)
    schema = registry.get_openai_schemas()  # for function calling
"""

import importlib
import inspect
import json
import logging
import os
import pkgutil
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ToolDescriptor:
    """Metadata for a registered tool."""

    __slots__ = ("name", "description", "parameters", "factory", "category", "requires_db", "requires_llm")

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        factory: Callable[..., Any],
        category: str = "analysis",
        requires_db: bool = False,
        requires_llm: bool = False,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.factory = factory
        self.category = category
        self.requires_db = requires_db
        self.requires_llm = requires_llm

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function-calling format."""
        properties: Dict[str, Any] = {}
        required: List[str] = []

        for pname, pdef in (self.parameters or {}).items():
            if not isinstance(pdef, dict):
                pdef = {"type": "string"}
            prop: Dict[str, Any] = {"type": str(pdef.get("type", "string")).lower()}
            if pdef.get("description"):
                prop["description"] = str(pdef["description"])
            if isinstance(pdef.get("enum"), list) and pdef["enum"]:
                prop["enum"] = list(pdef["enum"])
            if pdef.get("default") is None and not pdef.get("optional", False):
                required.append(pname)
            properties[pname] = prop

        schema: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        else:
            schema["additionalProperties"] = True

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "requires_db": self.requires_db,
            "requires_llm": self.requires_llm,
        }


class ToolRegistry:
    """Central registry for all agent tools."""

    _instance: Optional["ToolRegistry"] = None

    def __init__(self):
        self._tools: Dict[str, ToolDescriptor] = {}
        self._discovered = False

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        factory: Callable[..., Any],
        category: str = "analysis",
        requires_db: bool = False,
        requires_llm: bool = False,
    ):
        desc = ToolDescriptor(
            name=name,
            description=description,
            parameters=parameters,
            factory=factory,
            category=category,
            requires_db=requires_db,
            requires_llm=requires_llm,
        )
        self._tools[name] = desc
        logger.debug(f"Registered tool: {name}")

    # ------------------------------------------------------------------
    # Auto-discovery
    # ------------------------------------------------------------------

    def discover(self):
        """Scan agent/tools/ for modules that call register_tool()."""
        if self._discovered:
            return
        self._discovered = True

        tools_pkg = os.path.join(_PROJECT_ROOT, "agent", "tools")
        if not os.path.isdir(tools_pkg):
            return

        for importer, modname, ispkg in pkgutil.iter_modules([tools_pkg]):
            if modname.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"agent.tools.{modname}")
                # The module may call _registry.register() at import time
                logger.debug(f"Discovered tool module: agent.tools.{modname}")
            except Exception as e:
                logger.warning(f"Failed to import tool module {modname}: {e}")

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[ToolDescriptor]:
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> List[ToolDescriptor]:
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def get_openai_schemas(self) -> List[Dict[str, Any]]:
        return [t.to_openai_schema() for t in self._tools.values()]

    # ------------------------------------------------------------------
    # Instantiation
    # ------------------------------------------------------------------

    def instantiate_all(self, **kwargs) -> List[Any]:
        """Create instances of all registered tools, passing relevant kwargs."""
        db_path = kwargs.get("db_path")
        llm = kwargs.get("llm")

        instances = []
        for desc in self._tools.values():
            try:
                if desc.requires_db and not db_path:
                    continue
                if desc.requires_llm and not llm:
                    continue

                if desc.requires_db and desc.requires_llm:
                    inst = desc.factory(db_path=db_path, llm=llm)
                elif desc.requires_db:
                    inst = desc.factory(db_path=db_path)
                elif desc.requires_llm:
                    inst = desc.factory(llm=llm)
                else:
                    inst = desc.factory()

                instances.append(inst)
            except Exception as e:
                logger.warning(f"Failed to instantiate tool {desc.name}: {e}")

        return instances

    # ------------------------------------------------------------------
    # Import from legacy build_default_tools
    # ------------------------------------------------------------------

    def import_from_legacy(self, tools_list: List[Any]):
        """Import tools created by build_default_tools() into the registry."""
        for tool in tools_list:
            name = getattr(tool, "name", None)
            if not name:
                continue
            desc = ToolDescriptor(
                name=name,
                description=getattr(tool, "description", "") or "",
                parameters=getattr(tool, "parameters", {}) or {},
                factory=lambda t=tool: t,
                category="legacy",
                requires_db=("db_path" in str(inspect.signature(type(tool).__init__))),
                requires_llm=("llm" in str(inspect.signature(type(tool).__init__))),
            )
            if name not in self._tools:
                self._tools[name] = desc

    @property
    def count(self) -> int:
        return len(self._tools)


# ------------------------------------------------------------------
# Module-level convenience: the shared global registry
# ------------------------------------------------------------------

_registry = ToolRegistry()


def register_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    factory: Optional[Callable] = None,
    category: str = "analysis",
    requires_db: bool = False,
    requires_llm: bool = False,
):
    """Register a tool into the global registry. Can be used as decorator or direct call."""

    def decorator(fn: Callable) -> Callable:
        _registry.register(
            name=name,
            description=description,
            parameters=parameters,
            factory=fn,
            category=category,
            requires_db=requires_db,
            requires_llm=requires_llm,
        )
        return fn

    if factory is not None:
        return decorator(factory)
    return decorator


def get_registry() -> ToolRegistry:
    return _registry

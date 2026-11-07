from . import time_tools, file_tools, web_search_tools, cli_tools, skill_tools  # noqa: F401  导入即完成工具注册
from .registry import call_tool, registry

TOOLS = registry.schemas


def refresh_tools() -> list:
    """就地更新 TOOLS，使动态注册的工具（例如 MCP 工具）对所有引用者可见。"""
    TOOLS[:] = registry.schemas
    return TOOLS


__all__ = ["TOOLS", "call_tool", "registry", "refresh_tools"]

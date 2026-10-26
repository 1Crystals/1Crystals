from . import time_tools, file_tools  # noqa: F401  导入即完成工具注册
from .registry import call_tool, registry

TOOLS = registry.schemas

__all__ = ["TOOLS", "call_tool", "registry"]

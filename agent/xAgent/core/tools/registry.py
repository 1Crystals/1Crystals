import json
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    properties: dict = field(default_factory=dict)
    required: tuple = ()
    handler: Callable[..., Any] = None

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": list(self.required),
                },
            },
        }


class ToolRegistry:
    def __init__(self):
        self._specs: dict[str, ToolSpec] = {}

    def register(self, name, description, properties=None, required=()):
        def decorator(handler):
            self._specs[name] = ToolSpec(
                name=name,
                description=description,
                properties=properties or {},
                required=tuple(required),
                handler=handler,
            )
            return handler

        return decorator

    @property
    def schemas(self) -> list:
        return [spec.to_schema() for spec in self._specs.values()]

    def call(self, name: str, args_json: str) -> str:
        spec = self._specs.get(name)
        if spec is None:
            return f"未知工具：{name}"
        try:
            args = json.loads(args_json or "{}")
        except json.JSONDecodeError:
            return "参数解析失败，请检查 JSON 格式"
        if not isinstance(args, dict):
            return "参数必须是 JSON 对象"
        for key in spec.required:
            if key not in args or args[key] is None or args[key] == "":
                return f"缺少参数 {key}，请补充后重试"
        try:
            return str(spec.handler(**args))
        except Exception as e:
            return f"工具 {name} 执行出错：{e}"


registry = ToolRegistry()

register = registry.register
call_tool = registry.call

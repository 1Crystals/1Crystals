import asyncio
import atexit
import json
import os
import re
import sys
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

try:
    from mcp.client.streamable_http import streamable_http_client as _streamable_http_client
    _STREAMABLE_HTTP_V2 = True
except ImportError:  # mcp < 2
    from mcp.client.streamable_http import streamablehttp_client as _streamable_http_client
    _STREAMABLE_HTTP_V2 = False

from .tools import refresh_tools
from .tools.registry import ToolSpec, registry


DEFAULT_CONFIG_NAME = ".mcp.json"
CONNECT_TIMEOUT_SECONDS = 20
CALL_TIMEOUT_SECONDS = 120

_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitize_name(value: str) -> str:
    return _NAME_UNSAFE.sub("_", str(value)).strip("_") or "mcp"


def _log(message: str) -> None:
    print(f"[MCP] {message}", file=sys.stderr)


def _describe_exception(exc) -> str:
    messages = []

    def walk(error) -> None:
        if isinstance(error, BaseExceptionGroup):
            for sub in error.exceptions:
                walk(sub)
            return
        text = str(error).strip() or type(error).__name__
        messages.append(f"{type(error).__name__}: {text}")

    walk(exc)
    unique = []
    for message in messages:
        if message not in unique:
            unique.append(message)
    return "；".join(unique) or type(exc).__name__


def _transport_kind(config: dict) -> str:
    raw = config.get("type") or config.get("transport") or ""
    kind = str(raw).strip().lower().replace("-", "_")
    if kind in ("streamable_http", "streamablehttp", "http"):
        return "streamable_http"
    if kind in ("stdio", "command"):
        return "stdio"
    if kind:
        raise ValueError(f"不支持的 MCP 传输类型：{raw}")
    if config.get("url"):
        return "streamable_http"
    if config.get("command"):
        return "stdio"
    raise ValueError("缺少连接信息：需要 url（Streamable HTTP）或 command（stdio）")


def _format_call_result(result) -> str:
    parts = []

    for item in getattr(result, "content", None) or []:
        kind = getattr(item, "type", None)
        if kind == "text":
            parts.append(getattr(item, "text", ""))
        elif kind == "image":
            mime = getattr(item, "mime_type", "unknown")
            data = getattr(item, "data", "") or ""
            parts.append(f"[图片内容 mime={mime}，base64 长度={len(data)}]")
        elif kind == "audio":
            mime = getattr(item, "mime_type", "unknown")
            data = getattr(item, "data", "") or ""
            parts.append(f"[音频内容 mime={mime}，base64 长度={len(data)}]")
        elif kind == "resource":
            resource = getattr(item, "resource", None)
            text = getattr(resource, "text", None)
            uri = getattr(resource, "uri", "")
            if text is not None:
                parts.append(f"[资源 {uri}]\n{text}")
            else:
                parts.append(f"[资源 {uri}（二进制内容）]")
        else:
            parts.append(str(item))

    structured = getattr(result, "structured_content", None)
    if structured is not None:
        try:
            parts.append("结构化数据：\n" + json.dumps(structured, ensure_ascii=False, indent=2))
        except (TypeError, ValueError):
            parts.append(f"结构化数据：{structured}")

    text = "\n".join(part for part in parts if part).strip()
    if getattr(result, "is_error", False):
        return "【MCP 工具执行错误】\n" + (text or "服务端未返回错误详情")
    return text or "（MCP 工具未返回内容）"


class _ServerConnection:
    def __init__(self, name: str, config: dict, loop):
        self.name = name
        self.config = config
        self.loop = loop
        self.session = None
        self.tools = []
        self.error = None
        self.ready = threading.Event()
        self.stop_event = None
        self.future = None

    def _stdio_params(self) -> StdioServerParameters:
        command = self.config.get("command")
        if not command:
            raise ValueError("stdio MCP Server 缺少 command")
        args = self.config.get("args") or []
        if not isinstance(args, list):
            raise ValueError("stdio MCP Server 的 args 必须是字符串数组")
        env = self.config.get("env") or None
        if env is not None and not isinstance(env, dict):
            raise ValueError("stdio MCP Server 的 env 必须是对象")
        cwd = self.config.get("cwd") or None
        return StdioServerParameters(
            command=str(command),
            args=[str(item) for item in args],
            env={str(k): str(v) for k, v in env.items()} if env else None,
            cwd=cwd,
        )

    async def _open_transport(self, stack: AsyncExitStack):
        kind = _transport_kind(self.config)
        if kind == "stdio":
            return await stack.enter_async_context(stdio_client(self._stdio_params()))

        url = self.config.get("url")
        if not url:
            raise ValueError("Streamable HTTP MCP Server 缺少 url")
        headers = self.config.get("headers") or {}
        if headers and not isinstance(headers, dict):
            raise ValueError("Streamable HTTP MCP Server 的 headers 必须是对象")

        kwargs = {}
        if headers:
            import httpx2

            client = httpx2.AsyncClient(headers={str(k): str(v) for k, v in headers.items()})
            await stack.enter_async_context(client)
            kwargs["http_client"] = client

        return await stack.enter_async_context(_streamable_http_client(str(url), **kwargs))

    async def run(self) -> None:
        self.stop_event = asyncio.Event()
        try:
            async with AsyncExitStack() as stack:
                read_stream, write_stream = await self._open_transport(stack)
                session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await session.initialize()

                result = await session.list_tools()
                self.tools = list(getattr(result, "tools", None) or [])
                self.session = session
                self.ready.set()
                await self.stop_event.wait()
        except Exception as e:
            self.error = _describe_exception(e)
        finally:
            self.session = None
            self.ready.set()


@dataclass(frozen=True)
class _McpToolBinding:
    exposed_name: str
    server_name: str
    tool_name: str


class McpManager:
    def __init__(self):
        self.loop = None
        self.thread = None
        self._connections: dict[str, _ServerConnection] = {}
        self._bindings: dict[str, _McpToolBinding] = {}
        self._started = False
        self._start_lock = threading.Lock()
        self.connect_timeout = CONNECT_TIMEOUT_SECONDS
        self.call_timeout = CALL_TIMEOUT_SECONDS

    def start_background(self, project_dir=None, config_name=DEFAULT_CONFIG_NAME) -> None:
        """不阻塞的异步加载：另起线程连接 MCP，加载完成后动态刷新已注册工具。"""
        def runner():
            try:
                self.start(project_dir, config_name)
            finally:
                self.loading_done.set()
        self.loading_done = threading.Event()
        t = threading.Thread(target=runner, name="mcp-loader", daemon=True)
        t.start()

    def start(self, project_dir=None, config_name=DEFAULT_CONFIG_NAME) -> None:
        with self._start_lock:
            if self._started:
                return
            self._started = True

        from .config import getint, load_config

        try:
            cfg = load_config()
            self.connect_timeout = getint(cfg, "settings", "mcp_connect_timeout", CONNECT_TIMEOUT_SECONDS)
            self.call_timeout = getint(cfg, "settings", "mcp_call_timeout", CALL_TIMEOUT_SECONDS)
        except Exception:
            self.connect_timeout = CONNECT_TIMEOUT_SECONDS
            self.call_timeout = CALL_TIMEOUT_SECONDS

        project_dir = os.path.abspath(project_dir or os.getcwd())
        config_path = os.path.join(project_dir, config_name)
        if not os.path.isfile(config_path):
            _log(f"未找到配置文件 {config_path}，跳过 MCP 初始化")
            return

        try:
            with open(config_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            _log(f"读取配置文件失败：{config_path} - {type(e).__name__}: {e}")
            return

        servers = data.get("mcpServers") if isinstance(data, dict) else None
        if not isinstance(servers, dict) or not servers:
            _log(f"配置文件 {config_path} 中没有有效的 mcpServers 配置")
            return

        self._start_loop()

        for name, config in servers.items():
            if not isinstance(config, dict):
                _log(f"服务器 {name} 的配置无效，必须是对象")
                continue
            connection = _ServerConnection(str(name), config, self.loop)
            self._connections[str(name)] = connection
            connection.future = asyncio.run_coroutine_threadsafe(connection.run(), self.loop)

        connected = []
        for name, connection in self._connections.items():
            if not connection.ready.wait(self.connect_timeout):
                connection.error = f"连接超时（{self.connect_timeout} 秒）"
                self._request_stop(connection)
            if connection.error:
                _log(f"服务器 '{name}' 连接失败：{connection.error}")
            else:
                connected.append(connection)
                _log(f"服务器 '{name}' 已连接，发现 {len(connection.tools)} 个工具")

        self._register_tools(connected)

    def _start_loop(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, name="mcp-client", daemon=True)
        self.thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _request_stop(self, connection: _ServerConnection) -> None:
        if self.loop is not None and connection.stop_event is not None:
            self.loop.call_soon_threadsafe(connection.stop_event.set)

    def _register_tools(self, connections) -> None:
        used = set(registry.names())

        for connection in connections:
            for tool in connection.tools:
                tool_name = getattr(tool, "name", "")
                if not tool_name:
                    continue
                original = str(tool_name)
                exposed = original
                if exposed in used:
                    exposed = _sanitize_name(f"{connection.name}__{original}")
                suffix = 2
                while exposed in used:
                    exposed = _sanitize_name(f"{connection.name}__{original}_{suffix}")
                    suffix += 1

                schema = getattr(tool, "input_schema", None) or {}
                if not isinstance(schema, dict):
                    schema = {}
                parameters = dict(schema)
                parameters.setdefault("type", "object")
                parameters.setdefault("properties", {})
                parameters.setdefault("required", [])

                self._bindings[exposed] = _McpToolBinding(
                    exposed_name=exposed,
                    server_name=connection.name,
                    tool_name=original,
                )

                description = getattr(tool, "description", None) or f"MCP 工具 {original}"
                if exposed != original:
                    description = f"[MCP Server: {connection.name}] {description}"

                registry.add(
                    ToolSpec(
                        name=exposed,
                        description=description,
                        parameters=parameters,
                        required=tuple(parameters.get("required") or ()),
                        handler=self._make_handler(connection.name, original, exposed),
                    )
                )
                used.add(exposed)

        refresh_tools()

    def _make_handler(self, server_name: str, tool_name: str, exposed_name: str):
        def handler(**kwargs):
            return self.call_tool(server_name, tool_name, kwargs, exposed_name)

        return handler

    def call_tool(self, server_name: str, tool_name: str, arguments: dict, exposed_name=None) -> str:
        connection = self._connections.get(server_name)
        display = exposed_name or tool_name
        if connection is None:
            return f"【错误】MCP 工具 {display} 对应的服务器 '{server_name}' 不存在"
        if connection.session is None or self.loop is None:
            return (
                f"【错误】MCP 服务器 '{server_name}' 未连接"
                + (f"：{connection.error}" if connection.error else "")
            )

        try:
            future = asyncio.run_coroutine_threadsafe(
                connection.session.call_tool(tool_name, arguments or {}),
                self.loop,
            )
            result = future.result(timeout=self.call_timeout)
        except TimeoutError:
            return f"【错误】MCP 工具 {display} 调用超时（{self.call_timeout} 秒）"
        except Exception as e:
            return f"【错误】MCP 工具 {display} 调用失败：{type(e).__name__}: {e}"

        return _format_call_result(result)

    def shutdown(self) -> None:
        if self.loop is None:
            return
        for connection in self._connections.values():
            self._request_stop(connection)
        for connection in self._connections.values():
            if connection.future is not None:
                try:
                    connection.future.result(timeout=5)
                except Exception:
                    pass
        try:
            self.loop.call_soon_threadsafe(self.loop.stop)
        except RuntimeError:
            pass
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.loop = None
        self.thread = None


mcp_manager = McpManager()
atexit.register(mcp_manager.shutdown)

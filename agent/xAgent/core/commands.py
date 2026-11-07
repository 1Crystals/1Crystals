"""斜杠命令定义。

每个命令通过 handle(agent, args) 返回一个事件字典，UI 层据此渲染：
  {"type": "message", "content": ...}          直接显示文本
  {"type": "resume"}                            打开会话列表恢复面板
  {"type": "quit"}                              退出应用
"""

import json


def _cmd_help(agent, args):
    lines = ["可用斜杠命令："]
    for key, cmd in COMMANDS.items():
        lines.append(f"  /{key:<10} {cmd['help']}")
    return {"type": "message", "content": "\n".join(lines)}


def _cmd_save(agent, args):
    if getattr(agent, "compacting", False):
        return {"type": "message", "content": "压缩进行中，暂不能保存会话。"}
    sid = agent.save_session()
    return {
        "type": "message",
        "content": f"会话已保存。编号：{sid}",
    }


def _cmd_new(agent, args):
    if getattr(agent, "compacting", False):
        return {"type": "message", "content": "压缩进行中，暂不能新建会话。"}
    agent.save_session()
    agent.new_session()
    return {"type": "message", "content": "当前会话已保存并新建新会话。"}


def _cmd_resume(agent, args):
    return {"type": "resume"}


def _cmd_clear(agent, args):
    agent.reset()
    return {"type": "message", "content": "记忆已清空。"}


def _cmd_quit(agent, args):
    return {"type": "quit"}


def _cmd_compact(agent, args):
    return {"type": "compact"}


def _cmd_agents(agent, args):
    content = agent.agents_content or ""
    if not content:
        return {"type": "message", "content": "项目目录下未找到 AGENTS.md。"}
    return {"type": "message", "content": f"[AGENTS.md 内容]\n{content}"}


def _cmd_mcp(agent, args):
    from .mcp_client import mcp_manager
    lines = ["已配置的 MCP 服务器："]
    conns = mcp_manager._connections
    if not conns:
        lines.append("  （无）")
    for name, conn in conns.items():
        state = "已连接" if conn.session is not None else f"失败: {conn.error or '未连接'}"
        tools = "、".join(getattr(t, "name", "") for t in conn.tools) if conn.session else ""
        lines.append(f"  - {name}: {state} {('[' + str(len(conn.tools)) + ' 个工具: ' + tools + ']') if conn.session else ''}")
    return {"type": "message", "content": "\n".join(lines)}


COMMANDS = {
    "help": {"aliases": ["?"], "help": "显示全部斜杠命令", "handler": _cmd_help},
    "new": {"aliases": ["n"], "help": "保存当前会话并新建会话", "handler": _cmd_new},
    "resume": {"aliases": ["r"], "help": "打开历史会话列表并恢复", "handler": _cmd_resume},
    "save": {"aliases": ["s"], "help": "保存当前会话", "handler": _cmd_save},
    "clear": {"help": "清空当前会话记忆", "handler": _cmd_clear},
    "compact": {"help": "压缩当前上下文并归档", "handler": _cmd_compact},
    "agents": {"help": "查看当前 AGENTS.md 内容", "handler": _cmd_agents},
    "mcp": {"help": "查看已连接 MCP 服务器与工具", "handler": _cmd_mcp},
    "quit": {"aliases": ["exit", "q"], "help": "退出 xAgent", "handler": _cmd_quit},
}

COMMAND_NAMES = sorted(COMMANDS.keys())


def get_command(name):
    name = name.strip().lower()
    for key, cmd in COMMANDS.items():
        if key == name or name in cmd.get("aliases", []):
            return cmd
    return None


def dispatch(agent, name, args):
    cmd = get_command(name)
    if cmd is None:
        return {"type": "message", "content": f"未知命令：/{name}。输入 /help 查看全部命令。"}
    return cmd["handler"](agent, args)

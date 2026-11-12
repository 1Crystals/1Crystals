from datetime import datetime

from rich.markdown import Markdown
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, ListView, ListItem, RichLog, Static

from core import TOOLS
from core.commands import COMMANDS, dispatch, get_command, COMMAND_NAMES

from .base import BaseUI
from .themes import THEMES, THEME_LABELS, THEME_ORDER

COMMAND_LIST = sorted(
    {name: cmd for name, cmd in COMMANDS.items()}, key=lambda n: n
)


class AgentEvent(Message):
    def __init__(self, event):
        super().__init__()
        self.event = event


def _now() -> str:
    return datetime.now().strftime("%H:%M")


class ConfigDialog(ModalScreen):
    """配置文件为 mock 时弹出的提示对话框。"""

    CSS = """
    ConfigDialog {
        align: center middle;
        background: $boost 80%;
    }
    #config-frame {
        width: 70;
        height: auto;
        max-height: 24;
        background: $panel;
        border: thick $error;
        padding: 1;
    }
    #config-msg {
        height: auto;
        margin-bottom: 1;
    }
    #config-ok {
        width: 100%;
        margin-top: 1;
    }
    """

    def compose(self):
        with Vertical(id="config-frame"):
            yield Static("⚠ 配置文件需要修改", id="config-msg")
            yield Static(
                "检测到 config.ini 不存在或使用的是占位（mock）信息。\n"
                "已自动为你生成了一份完整的 config.ini 模板。\n\n"
                "请打开 config.ini，填入真实的 API Key 后【重新启动】xAgent。\n"
                "在修改前后，当前运行使用的均为占位配置。",
                id="config-msg",
            )
            yield Button("知道了", id="config-ok", variant="error")

    @on(Button.Pressed)
    def _ok(self, event):
        if event.button.id == "config-ok":
            self.dismiss()


class ResumeScreen(ModalScreen):
    """会话恢复面板：上下键选择、回车恢复、ESC 取消。"""

    CSS = """
    ResumeScreen {
        align: center middle;
        background: $boost 80%;
    }
    #resume-frame {
        width: 78;
        height: 70%;
        background: $panel;
        border: thick $accent;
        padding: 1;
    }
    #resume-title {
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        border-bottom: solid $accent;
    }
    #resume-hint {
        height: 1;
        color: $text-muted;
        margin-top: 1;
    }
    #resume-list {
        height: 1fr;
        margin-top: 1;
    }
    """
    BINDINGS = [Binding("escape", "cancel", "取消", priority=True)]

    def __init__(self, sessions, on_pick=None):
        super().__init__()
        self.sessions = sessions or []
        self.on_pick = on_pick

    def compose(self):
        with Vertical(id="resume-frame"):
            yield Static("历史会话（按 ↑/↓ 选择，Enter 恢复，ESC 取消）", id="resume-title")
            lv = ListView(id="resume-list")
            for sid, title, saved_at, count in self.sessions:
                label = f"{sid}  {title or '（无标题）'}"
                if saved_at:
                    label += f"  ·  {saved_at[:16]}"
                label += f"  ·  {count} 条消息"
                lv.append(ListItem(Label(label)))
            yield lv
            yield Static("Enter 恢复 · ESC 取消", id="resume-hint")

    def _selected(self):
        return self.sessions[self.query_one(ListView).index]

    @on(ListView.Selected)
    def _picked(self, event):
        item = event.item
        idx = list(self.query_one(ListView).children).index(item)
        if idx < len(self.sessions):
            sid = self.sessions[idx][0]
            if self.on_pick:
                self.on_pick(sid)
            self.dismiss()

    def action_cancel(self):
        self.dismiss()


class CompareScreen(ModalScreen):
    """压缩对比面板：左原文、右摘要，可滚动，可关闭。"""

    CSS = """
    CompareScreen {
        align: center middle;
        background: $boost 80%;
    }
    #compare-frame {
        width: 88%;
        height: 86%;
        background: $panel;
        border: thick $accent;
        padding: 1;
    }
    #compare-title {
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        border-bottom: solid $accent;
        margin-bottom: 1;
    }
    #compare-original-box {
        width: 1fr;
        border-right: solid $accent;
        padding-right: 1;
    }
    #compare-summary-box {
        width: 1fr;
    }
    .compare-label {
        height: 1;
        text-style: bold;
        color: $text-muted;
        margin-bottom: 1;
    }
    #compare-close {
        dock: bottom;
        width: 16;
        margin-top: 1;
        align-horizontal: center;
    }
    """

    def __init__(self, original, summary, archive_id):
        super().__init__()
        self.original = original or "（空）"
        self.summary = summary or "（空）"
        self.archive_id = archive_id

    def compose(self):
        with Vertical(id="compare-frame"):
            yield Static(f"上下文压缩对比 · 归档 {self.archive_id}", id="compare-title")
            with Horizontal():
                with Vertical(id="compare-original-box"):
                    yield Static("压缩前原文", classes="compare-label")
                    with ScrollableContainer():
                        yield Static(self.original, id="compare-original")
                with Vertical(id="compare-summary-box"):
                    yield Static("压缩后摘要", classes="compare-label")
                    with ScrollableContainer():
                        yield Markdown(self.summary)
            yield Button("关闭", id="compare-close", variant="primary")

    @on(Button.Pressed)
    def _close(self, event):
        if event.button.id == "compare-close":
            self.dismiss()


class TUIApp(App, BaseUI):
    TITLE = "xAgent"

    CSS = """
    Screen {
        layout: vertical;
        background: $background;
    }
    #context-bar {
        height: 1;
        background: $boost;
        color: $text;
        text-align: center;
    }
    #context-bar.warning {
        background: $warning;
        color: $text;
    }
    #body {
        height: 1fr;
    }
    #sidebar {
        width: 34;
        background: $panel;
        border-right: solid $accent;
        padding: 0 1;
    }
    #brand {
        height: 3;
        width: 100%;
        text-align: center;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        background: $boost;
        border-bottom: solid $accent;
    }
    #session {
        height: auto;
        margin: 1 0;
        color: $text-muted;
    }
    #status {
        height: 3;
        width: 100%;
        text-align: center;
        content-align: center middle;
        text-style: bold;
        background: $success;
        color: $text;
        margin-bottom: 1;
    }
    #status.busy {
        background: $warning;
        color: $text;
    }
    #status.suspend {
        background: $error;
        color: $text;
    }
    #side-scroll {
        height: 1fr;
        overflow-y: auto;
    }
    .side-title {
        height: 1;
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }
    #mcp-list {
        height: auto;
    }
    .mcp-server {
        height: auto;
        color: $text;
        margin-left: 1;
    }
    .mcp-tool {
        height: 1;
        color: $text-muted;
        margin-left: 2;
    }
    #tools-list {
        height: auto;
        margin-bottom: 1;
    }
    .tool-item {
        height: 1;
        color: $text-muted;
        padding-left: 1;
    }
    .cmd-hint {
        height: auto;
        max-height: 9;
        overflow-y: auto;
        background: $panel;
        border: solid $accent;
        color: $text;
        padding: 0 1;
        display: none;
    }
    #main {
        width: 1fr;
        height: 1fr;
        min-height: 10;
    }
    #log {
        height: 1fr;
        border: none;
        padding: 1 2;
        background: $background;
    }
    #input-row {
        height: auto;
        padding: 0 1 1 1;
        background: $panel;
        border-top: solid $accent;
    }
    #input-row Horizontal {
        height: auto;
    }
    #prompt {
        width: 1fr;
        margin-right: 1;
    }
    #send {
        width: 12;
    }
    """

    BINDINGS = [
        Binding("ctrl+l", "clear", "清屏"),
        Binding("ctrl+t", "cycle_theme", "换主题"),
        Binding("ctrl+q", "quit", "退出"),
    ]

    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        self.busy = False
        self.suspended = False
        self.compact_busy = False
        self._compare = None
        self._mcp_refreshed = False
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme_key = getattr(agent, "config_mock", False) and "red" or "red"

    def compose(self):
        yield Header(show_clock=True)
        yield Static("", id="context-bar")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("✦ xAgent", id="brand")
                yield Static("", id="session")
                yield Static("● 就绪", id="status")
                yield Label("MCP 服务器", classes="side-title")
                yield Label("加载中…", id="mcp-list")
                yield Label("工具", classes="side-title")
                yield Label("", id="tools-list")
                yield Label("主题", classes="side-title")
                with Horizontal(id="theme-row"):
                    for key in THEME_ORDER:
                        yield Button(
                            THEME_LABELS[key],
                            id=f"theme-{key}",
                            variant="default",
                            classes="active" if key == self.theme_key else "",
                        )
                with Horizontal(id="sidebar-actions"):
                    yield Button("清屏", id="clear", variant="default")
                    yield Button("退出", id="quit", variant="error")
            with Vertical(id="main"):
                yield RichLog(id="log", wrap=True, highlight=False, auto_scroll=True)
                with Vertical(id="input-row"):
                    yield Static("", id="cmd-hint")
                    with Horizontal():
                        yield Input(placeholder="输入消息或输入 / 查看命令（ctrl+L 清屏 / ctrl+T 换主题 / ctrl+Q 退出）", id="prompt")
                        yield Button("发送", id="send", variant="primary")
        yield Footer()

    def on_mount(self):
        self.set_theme(self.theme_key, focus_prompt=False)
        log = self.query_one("#log", RichLog)
        log.write(Text("欢迎使用 xAgent —— 输入消息开始对话", style="bold cyan"))
        log.write(Text("输入 / 查看命令列表；如 /compact /new /resume /save", style="dim"))
        log.write(Text("ctrl+T 快速切换主题（红/绿/白/黑）", style="dim"))
        log.write("")
        self._update_session()
        self._update_context()
        self._refresh_tools()
        self.set_interval(1.0, self._poll_mcp)
        if getattr(self.agent, "config_mock", False):
            self.call_after_refresh(self.push_screen, ConfigDialog())
        self.query_one("#prompt", Input).focus()

    def _poll_mcp(self):
        mgr = __import__("core.mcp_client", fromlist=["mcp_manager"]).mcp_manager
        if not self._mcp_refreshed and mgr.loading_done.is_set():
            self._mcp_refreshed = True
            self._refresh_mcp()
            self._refresh_tools()
            log = self.query_one("#log", RichLog)
            log.write(Text.assemble((_now() + "  ", "dim"), ("⇅ ", "blue"), "MCP 服务器已加载完成"))

    def set_theme(self, key, focus_prompt=True):
        self.theme_key = key
        self.theme = THEMES[key].name
        for k in THEME_ORDER:
            btn = self.query_one(f"#theme-{k}", Button)
            btn.set_class(k == key, "active")
        self._update_session()
        if focus_prompt and not (self.busy or self.suspended):
            self.query_one("#prompt", Input).focus()

    def action_cycle_theme(self):
        idx = THEME_ORDER.index(self.theme_key)
        self.set_theme(THEME_ORDER[(idx + 1) % len(THEME_ORDER)])

    def _update_session(self):
        model = getattr(self.agent, "model", "-")
        messages = getattr(self.agent, "messages", None) or []
        label = THEME_LABELS.get(self.theme_key, self.theme_key)
        sid = getattr(self.agent, "session_id", None) or "-"
        self.query_one("#session", Static).update(
            f"模型: {model}\n会话: {sid}\n记忆: {len(messages)} 条\n主题: {label} · TUI"
        )

    def _update_context(self):
        bar = self.query_one("#context-bar", Static)
        used = getattr(self.agent.context, "tokens", 0)
        window = getattr(self.agent.context, "window_size", 128000)
        ratio = getattr(self.agent.context, "ratio", 0.0)
        default_flag = getattr(self.agent, "window_defaulted", False)
        suffix = "（默认 128k）" if default_flag else ""
        bar.update(f"上下文: {used / 1000:.1f}k / {window / 1000:.1f}k · 已占用 {ratio * 100:.0f}% {suffix}")
        bar.set_class(self.agent.context.is_warning(), "warning")

    def _refresh_mcp(self):
        mgr = __import__("core.mcp_client", fromlist=["mcp_manager"]).mcp_manager
        box = self.query_one("#mcp-list", Label)
        conns = mgr._connections
        if not conns:
            box.update("（未配置 MCP 服务器）")
            return
        lines = []
        for name, conn in conns.items():
            if conn.session is not None:
                tools = "、".join(getattr(t, "name", "") for t in conn.tools)
                lines.append(f"● {name} ({len(conn.tools)} 个工具)")
                for t in conn.tools:
                    lines.append(f"   · {getattr(t, 'name', '')}")
            else:
                lines.append(f"○ {name}（不可达: {conn.error or '未连接'}）")
        box.update("\n".join(lines))

    def _refresh_tools(self):
        from core import TOOLS as _TOOLS
        names = [s["function"]["name"] for s in _TOOLS]
        self.query_one("#tools-list", Label).update("\n".join(f"⚙ {n}" for n in names))

    def action_clear(self):
        self.agent.reset()
        log = self.query_one("#log", RichLog)
        log.clear()
        log.write(Text("记忆已清空", style="dim"))
        self._set_status("● 就绪", reset=True)
        self.suspended = False
        self._update_session()
        self._update_context()
        self._refresh_input()

    def _set_status(self, text, reset=False):
        status = self.query_one("#status", Static)
        status.update(text)
        if reset:
            status.remove_class("busy")
            status.remove_class("suspend")

    @on(Button.Pressed)
    def on_button(self, event):
        if event.button.id == "send":
            self._submit_input()
        elif event.button.id == "clear":
            self.action_clear()
        elif event.button.id == "quit":
            self.exit()
        elif event.button.id and event.button.id.startswith("theme-"):
            self.set_theme(event.button.id.removeprefix("theme-"))

    @on(Input.Submitted)
    def on_submit(self, event):
        self._submit_input()

    @on(Input.Changed)
    def on_input_changed(self, event):
        self._update_command_hint(event.value)

    def _update_command_hint(self, value):
        hint = self.query_one("#cmd-hint", Static)
        value = (value or "").strip()
        if value.startswith("/") and len(value) > 1:
            frag = value[1:].lower()
            matches = [n for n in COMMAND_NAMES if n.startswith(frag)]
            if matches:
                lines = [f"{n:<10} {COMMANDS[n]['help']}" for n in matches]
                hint.update("\n".join(lines))
                hint.styles.display = "block"
                return
        hint.update("")
        hint.styles.display = "none"

    def _maybe_run_command(self, text):
        if not text.startswith("/"):
            return False
        parts = text.split(None, 1)
        name = parts[0][1:]
        args = parts[1] if len(parts) > 1 else ""
        if not get_command(name):
            log = self.query_one("#log", RichLog)
            log.write(Text.assemble((_now() + "  ", "dim"), ("出错: ", "bold red"), f"未知命令：/{name}"))
            return True
        event = dispatch(self.agent, name, args)
        self._handle_command_event(event, name)
        return True

    def _handle_command_event(self, event, name):
        log = self.query_one("#log", RichLog)
        kind = event["type"]
        if kind == "message":
            log.write(Text.assemble((_now() + "  ", "dim"), (f"/{name}", "bold cyan")))
            log.write(Text(str(event["content"])))
        elif kind == "resume":
            from core.sessions import list_sessions
            sessions = list_sessions(self.agent.root)
            if not sessions:
                log.write(Text("没有历史会话", style="dim"))
                return
            self.push_screen(ResumeScreen(sessions, on_pick=self._resume_pick))
        elif kind == "compact":
            self._compact()
        elif kind == "quit":
            self.exit()

    def _resume_pick(self, session_id):
        msg = self.agent.resume_session(session_id)
        self._update_session()
        self._update_context()
        log = self.query_one("#log", RichLog)
        log.write(Text.assemble((_now() + "  ", "dim"), (msg, "green")))

    def _submit_input(self):
        prompt = self.query_one("#prompt", Input)
        text = prompt.value.strip()
        prompt.value = ""
        self._update_command_hint("")
        if not text or self.busy or self.suspended:
            return
        if text in ("/quit", "/exit", "/q"):
            self.exit()
            return
        if text == "/clear":
            self.action_clear()
            return
        if self._maybe_run_command(text):
            return
        log = self.query_one("#log", RichLog)
        log.write(Text.assemble((_now() + "  ", "dim"), ("你 ", "bold cyan"), text))
        self._set_busy(True)
        self._update_session()
        self._ask(text)

    def _refresh_input(self):
        self.query_one("#prompt", Input).disabled = self.busy or self.suspended
        self.query_one("#send", Button).disabled = self.busy or self.suspended

    def _set_busy(self, busy):
        self.busy = busy
        self._refresh_input()
        status = self.query_one("#status", Static)
        if busy:
            status.update("● 思考中...")
            status.add_class("busy")
            status.remove_class("suspend")
        else:
            status.remove_class("busy")
            if self.suspended:
                status.update("⚠ 上下文已达阈值，请执行 /compact 后继续")
                status.add_class("suspend")
            else:
                status.update("● 就绪")
                status.remove_class("suspend")
                self.query_one("#prompt", Input).focus()

    @work(thread=True, exclusive=True, group="chat")
    def _ask(self, text):
        try:
            for event in self.agent.chat(text):
                self.post_message(AgentEvent(event))
        except Exception as e:
            self.post_message(AgentEvent({"type": "error", "content": str(e)}))

    @work(thread=True, exclusive=True, group="compact")
    def _compact_run(self):
        try:
            for event in self.agent.compact():
                self.post_message(AgentEvent(event))
        except Exception as e:
            self.post_message(AgentEvent({"type": "error", "content": str(e)}))

    def _compact(self):
        if self.busy or self.compact_busy:
            return
        self.compact_busy = True
        log = self.query_one("#log", RichLog)
        log.write(Text.assemble((_now() + "  ", "dim"), ("⟳ ", "yellow"), "开始上下文压缩..."))
        self._set_busy(True)
        self._compact_run()

    def on_agent_event(self, message):
        event = message.event
        kind = event.get("type")
        log = self.query_one("#log", RichLog)
        if kind == "tool_result":
            log.write(Text.assemble(
                (_now() + "  ", "dim"),
                ("⚙ ", "yellow"),
                (event["name"] + " → ", "bold yellow"),
                (event["content"], "yellow"),
            ))
        elif kind in ("final", "reply"):
            content = event.get("content") or ""
            log.write(Text.assemble((_now() + "  ", "dim"), ("AI", "bold green")))
            if content:
                log.write(Markdown(content))
            else:
                log.write(Text("（无内容）", style="dim"))
            log.write("")
            if kind == "final":
                self._set_busy(False)
                self._update_session()
                self._update_context()
        elif kind == "context_warning":
            pct = event.get("ratio", 0) * 100
            log.write(Text.assemble(
                (_now() + "  ", "dim"),
                ("⚠ ", "bold red"),
                f"上下文占用已达 {pct:.0f}%，请执行 /compact 压缩后继续",
            ))
            self.suspended = True
            self._refresh_input()
            self._set_status("⚠ 上下文已达阈值，请执行 /compact 压缩后继续", reset=True)
            status = self.query_one("#status", Static)
            status.add_class("suspend")
            self._update_context()
        elif kind == "archive":
            log.write(Text.assemble(
                (_now() + "  ", "dim"),
                ("存档 ", "bold blue"),
                f"归档 {event['archive_id']} 已保存 -> {event['path']}",
            ))
        elif kind == "summary":
            self._compare = (event.get("original"), event.get("summary"), event.get("archive_id"))
        elif kind == "compacted":
            log.write(Text.assemble(
                (_now() + "  ", "dim"),
                ("✓ ", "bold green"),
                "上下文压缩完成，已替换历史会话。",
            ))
            if self._compare:
                self.push_screen(CompareScreen(*self._compare))
                self._compare = None
            self.compact_busy = False
            self.suspended = False
            self._set_busy(False)
            self._update_session()
            self._update_context()
        elif kind == "error":
            log.write(Text.assemble((_now() + "  ", "dim"), ("出错: ", "bold red"), event["content"]))
            if self.compact_busy:
                self.compact_busy = False
            self._set_busy(False)

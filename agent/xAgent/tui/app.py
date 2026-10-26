from datetime import datetime

from rich.markdown import Markdown
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Footer, Header, Input, RichLog, Static

from core import TOOLS

from .base import BaseUI
from .themes import THEMES, THEME_LABELS, THEME_ORDER


class AgentEvent(Message):
    def __init__(self, event):
        super().__init__()
        self.event = event


def _now() -> str:
    return datetime.now().strftime("%H:%M")


class TUIApp(App, BaseUI):
    TITLE = "xAgent"

    CSS = """
    Screen {
        layout: vertical;
        background: $background;
    }
    #body {
        height: 1fr;
    }
    #sidebar {
        width: 32;
        background: $panel;
        border-right: solid $accent;
        padding: 1;
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
    #tools-title {
        height: 1;
        color: $text-muted;
        text-style: bold;
    }
    #tools-list {
        height: 1fr;
        overflow-y: auto;
    }
    .tool-item {
        height: 1;
        color: $text-muted;
        padding-left: 1;
    }
    .tool-item:hover {
        background: $boost;
        color: $text;
    }
    #theme-title {
        height: 1;
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }
    #theme-row {
        height: 3;
    }
    #theme-row Button {
        width: 1fr;
        min-width: 0;
        margin: 0 1;
    }
    #theme-red { background: #c92a2a; color: #ffffff; }
    #theme-red.active { border: tall $accent; text-style: bold; }
    #theme-green { background: #2b8a3e; color: #ffffff; }
    #theme-green.active { border: tall $accent; text-style: bold; }
    #theme-white { background: #f8f9fa; color: #212529; }
    #theme-white.active { border: tall $accent; text-style: bold; }
    #theme-black { background: #000000; color: #e9ecef; }
    #theme-black.active { border: tall $accent; text-style: bold; }
    #sidebar-actions {
        height: 3;
        dock: bottom;
        margin-top: 1;
    }
    #sidebar-actions Button {
        width: 1fr;
        min-width: 0;
        margin: 0 1;
    }
    #main {
        width: 1fr;
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
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme_key = "red"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Static("✦ xAgent", id="brand")
                yield Static("", id="session")
                yield Static("● 就绪", id="status")
                yield Static(f"工具（{len(TOOLS)}）", id="tools-title")
                with Vertical(id="tools-list"):
                    for spec in TOOLS:
                        yield Static(f"⚙ {spec['function']['name']}", classes="tool-item")
                yield Static("主题", id="theme-title")
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
                with Horizontal(id="input-row"):
                    yield Input(placeholder="输入消息，回车发送（ctrl+L 清屏 / ctrl+T 换主题 / ctrl+Q 退出）", id="prompt")
                    yield Button("发送", id="send", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.set_theme(self.theme_key, focus_prompt=False)
        log = self.query_one("#log", RichLog)
        log.write(Text("欢迎使用 xAgent —— 输入消息开始对话", style="bold cyan"))
        log.write(Text("支持文件操作 / 日期 / 闰年 等 12 个工具", style="dim"))
        log.write(Text("ctrl+T 快速切换主题（红/绿/白/黑）", style="dim"))
        log.write("")
        self._update_session()
        self.query_one("#prompt", Input).focus()

    def set_theme(self, key: str, focus_prompt: bool = True) -> None:
        self.theme_key = key
        self.theme = THEMES[key].name
        for k in THEME_ORDER:
            btn = self.query_one(f"#theme-{k}", Button)
            btn.set_class(k == key, "active")
        self._update_session()
        if focus_prompt and not self.busy:
            self.query_one("#prompt", Input).focus()

    def action_cycle_theme(self) -> None:
        idx = THEME_ORDER.index(self.theme_key)
        self.set_theme(THEME_ORDER[(idx + 1) % len(THEME_ORDER)])

    def _update_session(self) -> None:
        model = getattr(self.agent, "model", "-")
        messages = getattr(self.agent, "messages", None) or []
        label = THEME_LABELS.get(self.theme_key, self.theme_key)
        self.query_one("#session", Static).update(
            f"模型: {model}\n记忆: {len(messages)} 条\n主题: {label} · TUI"
        )

    def action_clear(self) -> None:
        self.agent.reset()
        log = self.query_one("#log", RichLog)
        log.clear()
        log.write(Text("记忆已清空", style="dim"))
        self.query_one("#status", Static).update("● 就绪")
        self.query_one("#status", Static).remove_class("busy")
        self._update_session()

    @on(Button.Pressed)
    def on_button(self, event: Button.Pressed) -> None:
        if event.button.id == "send":
            self._submit_input()
        elif event.button.id == "clear":
            self.action_clear()
        elif event.button.id == "quit":
            self.exit()
        elif event.button.id and event.button.id.startswith("theme-"):
            self.set_theme(event.button.id.removeprefix("theme-"))

    @on(Input.Submitted)
    def on_submit(self, event: Input.Submitted) -> None:
        self._submit_input()

    def _submit_input(self) -> None:
        prompt = self.query_one("#prompt", Input)
        text = prompt.value.strip()
        prompt.value = ""
        if not text or self.busy:
            return
        if text in ("/quit", "/exit"):
            self.exit()
            return
        if text == "/clear":
            self.action_clear()
            return
        log = self.query_one("#log", RichLog)
        log.write(Text.assemble((_now() + "  ", "dim"), ("你 ", "bold cyan"), text))
        self._set_busy(True)
        self._update_session()
        self._ask(text)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.query_one("#prompt", Input).disabled = busy
        self.query_one("#send", Button).disabled = busy
        status = self.query_one("#status", Static)
        if busy:
            status.update("● 思考中...")
            status.add_class("busy")
        else:
            status.update("● 就绪")
            status.remove_class("busy")
            self.query_one("#prompt", Input).focus()

    @work(thread=True, exclusive=True, group="chat")
    def _ask(self, text: str) -> None:
        try:
            for event in self.agent.chat(text):
                self.post_message(AgentEvent(event))
        except Exception as e:
            self.post_message(AgentEvent({"type": "error", "content": str(e)}))

    def on_agent_event(self, message: AgentEvent) -> None:
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
        elif kind == "error":
            log.write(Text.assemble((_now() + "  ", "dim"), ("出错: ", "bold red"), event["content"]))
            self._set_busy(False)

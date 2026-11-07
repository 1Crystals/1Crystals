from .base import BaseUI
from core.commands import dispatch, get_command


class ConsoleUI(BaseUI):
    def run(self):
        while True:
            try:
                user_input = input("你: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_input:
                continue
            if user_input in ("/quit", "/exit", "/q"):
                break
            if user_input == "/clear":
                self.agent.reset()
                print("记忆已清空")
                continue
            if user_input.startswith("/"):
                self._run_command(user_input)
                continue

            for event in self.agent.chat(user_input):
                self._render_chat_event(event)

    def _run_command(self, text):
        parts = text.split(None, 1)
        name = parts[0][1:]
        args = parts[1] if len(parts) > 1 else ""
        if not get_command(name):
            print(f"未知命令：/{name}。输入 /help 查看全部命令。")
            return
        event = dispatch(self.agent, name, args)
        kind = event["type"]
        if kind == "message":
            print(event["content"])
        elif kind == "quit":
            raise SystemExit(0)

    def _render_chat_event(self, event):
        kind = event["type"]
        if kind == "tool_result":
            print(f"[调用工具 {event['name']}] 结果: {event['content']}")
        elif kind == "context_warning":
            pct = event.get("ratio", 0) * 100
            print(f"⚠ 上下文占用已达 {pct:.0f}%，请执行 /compact 压缩后继续。")
        elif kind in ("final", "reply"):
            print("AI:", event["content"])
        elif kind == "error":
            print("出错:", event["content"])

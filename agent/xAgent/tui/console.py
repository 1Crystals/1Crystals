from .base import BaseUI


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
            if user_input in ("/exit", "/quit"):
                break
            if user_input == "/clear":
                self.agent.reset()
                print("记忆已清空")
                continue

            for event in self.agent.chat(user_input):
                if event["type"] == "tool_result":
                    print(f"[调用工具 {event['name']}] 结果: {event['content']}")
                elif event["type"] in ("final", "reply"):
                    print("AI:", event["content"])
                elif event["type"] == "error":
                    print("出错:", event["content"])

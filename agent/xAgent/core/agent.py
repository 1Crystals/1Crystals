import re

from .tools import TOOLS, call_tool

SYSTEM_PROMPT = "你是一个极简的AI助手。"


class Agent:
    def __init__(self, client, model, system_prompt=SYSTEM_PROMPT):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.reset()

    def reset(self):
        self.messages = [{"role": "system", "content": self.system_prompt}]

    def chat(self, user_input):
        self.messages.append({"role": "user", "content": user_input})
        payload = list(self.messages)

        while True:
            msg = self.client.chat.completions.create(
                model=self.model,
                messages=payload,
                tools=TOOLS,
                tool_choice="auto",
            ).choices[0].message

            if not msg.tool_calls:
                raw = (msg.content or "").strip()
                answer = re.sub(r"```.*?```", "", raw, flags=re.S).strip()
                self.messages.append({"role": "assistant", "content": answer})
                yield {"type": "final", "content": answer}
                return

            assistant_msg = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": t.id, "type": "function",
                     "function": {"name": t.function.name, "arguments": t.function.arguments}}
                    for t in msg.tool_calls
                ],
            }
            self.messages.append(assistant_msg)
            payload = payload + [assistant_msg]

            result = ""
            for t in msg.tool_calls:
                result = call_tool(t.function.name, t.function.arguments)
                tool_msg = {"role": "tool", "tool_call_id": t.id, "content": result}
                self.messages.append(tool_msg)
                payload = payload + [tool_msg]
                yield {"type": "tool_result", "name": t.function.name, "content": result}

            yield {"type": "reply", "content": msg.content or result}

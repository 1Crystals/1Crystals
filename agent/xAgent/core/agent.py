import os
import re
from datetime import datetime

from .config import get, getfloat, getint, is_mock_config
from .context import ContextManager, COMPACT_PROMPT, estimate_tokens
from .sessions import (
    load_session,
    list_sessions,
    new_session_id,
    read_agents_file,
    save_session,
)
from .skills import reload_for
from .tools import call_tool, refresh_tools, registry
from .tools.registry import ToolSpec

SYSTEM_PROMPT = "你是一个极简的AI助手。"


class Agent:
    def __init__(self, client, model, system_prompt=None, context_window=None, cfg=None, root=None):
        self.root = os.path.abspath(root or os.getcwd())
        self.client = client
        self.model = model
        if system_prompt is None:
            system_prompt = get(cfg, "llm", "system_prompt", SYSTEM_PROMPT)
        self.skills = reload_for(self.root)
        section = self.skills.system_prompt_section()
        self.system_prompt = f"{system_prompt}\n\n{section}" if section else system_prompt
        warn_ratio = getfloat(cfg, "context", "warn_ratio", 0.6) if cfg else 0.6
        self.context = ContextManager(self.root, context_window, warn_ratio=warn_ratio)
        self.context.set_estimated_tokens([{"role": "system", "content": self.system_prompt}])
        self.window_defaulted = context_window is None
        self.compacting = False
        self.session_id = None
        self.session_title = ""
        self.agents_content = read_agents_file(self.root)
        self.agents_injected = False
        self.config_mock = is_mock_config(cfg) if cfg is not None else False
        self.reset()
        self._register_recall_tool()

    def _agents_message(self) -> dict:
        return {"role": "user", "content": f"[AGENTS.md]\n{self.agents_content}\n[END AGENTS.md]"}

    def _inject_agents(self) -> None:
        self.agents_injected = False
        if self.agents_content:
            self.messages.append(self._agents_message())
            self.agents_injected = True

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self._inject_agents()
        self.context.set_estimated_tokens(self.messages)

    def new_session(self) -> None:
        self.session_id = None
        self.session_title = ""
        self.reset()

    def save_session(self, title="") -> str:
        sid = self.session_id or new_session_id()
        save_session(self.root, self.messages, sid, title or self.session_title)
        self.session_id = sid
        return sid

    def resume_session(self, session_id) -> str:
        data = load_session(self.root, session_id)
        if not data:
            return f"【错误】未找到会话 {session_id}"
        self.messages = list(data.get("messages") or [])
        self.session_id = session_id
        self.session_title = (data.get("title") or "").strip()
        has_agents = any(
            m.get("content", "").startswith("[AGENTS.md]") for m in self.messages
        )
        if not has_agents and self.agents_content:
            self.messages.insert(1, self._agents_message())
        self.context.set_estimated_tokens(self.messages)
        self.compacting = False
        return f"已恢复会话 {session_id}{'：' + self.session_title if self.session_title else ''}"

    def _register_recall_tool(self) -> None:
        def handler(text, archive_id=None, **kwargs):
            return self.context.recall(text, archive_id=archive_id)

        if "recallContext" in registry.names():
            return
        registry.add(ToolSpec(
            name="recallContext",
            description=(
                "检索历史归档的原始上下文。当压缩摘要缺少某些历史细节时，可用此工具查找。"
                "id 为可选归档编号；text 为必需的检索关键词或文本。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "可选：指定的归档编号"},
                    "text": {"type": "string", "description": "必需：需检索的关键词或文本"},
                },
                "required": ["text"],
            },
            required=("text",),
            handler=handler,
        ))
        refresh_tools()

    def chat(self, user_input):
        user_input = (user_input or "").strip()
        if not user_input:
            return
        if self.compacting:
            yield {"type": "error", "content": "正在执行上下文压缩，请稍候。"}
            return

        self.messages.append({"role": "user", "content": user_input})
        payload = list(self.messages)
        warned = False

        while True:
            if self.context.is_warning() and not self.compacting:
                if not warned:
                    warned = True
                    yield {
                        "type": "context_warning",
                        "used": self.context.tokens,
                        "window": self.context.window_size,
                        "ratio": self.context.ratio,
                    }

            resp = self.client.chat.completions.create(
                model=self.model,
                messages=payload,
                tools=registry.schemas,
                tool_choice="auto",
            )
            msg = resp.choices[0].message
            usage = getattr(resp, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
            if prompt_tokens:
                self.context.set_usage_tokens(prompt_tokens)
            else:
                self.context.set_estimated_tokens(payload)

            if self.context.is_warning() and not warned:
                warned = True
                yield {
                    "type": "context_warning",
                    "used": self.context.tokens,
                    "window": self.context.window_size,
                    "ratio": self.context.ratio,
                }

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

    def compact(self):
        """手动压缩上下文。压缩期间禁止工具调用与新任务，仅调用 LLM 生成摘要。"""
        if self.compacting:
            yield {"type": "error", "content": "压缩正在进行中，请勿重复触发。"}
            return
        history = self.messages[:]
        if len(history) <= 1:
            yield {"type": "error", "content": "当前没有可压缩的历史消息。"}
            return

        self.compacting = True
        archive_id = None
        try:
            archive_id, path = self.context.archive(history, self.model)
            yield {"type": "archive", "archive_id": archive_id, "path": path, "messages": history}

            original = self._format_messages(history)
            summary = self._generate_summary(original)
            if not summary:
                raise RuntimeError("LLM 未返回摘要")

            note = (
                f"此前上下文已于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 完成压缩，"
                f"原始上下文保存在编号为 {archive_id} 的归档文件中。"
                "如需查找历史信息，请使用 recallContext 工具。"
            )
            full_summary = summary + "\n\n" + note

            yield {"type": "summary", "summary": summary, "original": original,
                   "archive_id": archive_id}

            self.messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": full_summary},
            ]
            self.context.set_estimated_tokens(self.messages)
            yield {"type": "compacted", "archive_id": archive_id, "summary": full_summary}
        except Exception as e:
            yield {"type": "error", "content": f"压缩失败（原始上下文已保留）：{type(e).__name__}: {e}"}
        finally:
            self.compacting = False

    def _format_messages(self, messages) -> str:
        lines = []
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content") or ""
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    lines.append(f"[{role}::调用工具 {fn.get('name')}]\n参数: {fn.get('arguments')}")
            if msg.get("tool_call_id"):
                lines.append(f"[{role}::工具返回]\n{content}")
                continue
            if content:
                lines.append(f"[{role}]\n{content}")
        return "\n\n".join(lines)

    def _generate_summary(self, original) -> str:
        """仅调用 LLM（不带工具）生成摘要。"""
        original = (original or "")[: int(self.context.window_size * 0.9)]
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": COMPACT_PROMPT},
                {"role": "user", "content": f"以下是需要压缩的历史上下文：\n\n{original}"},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

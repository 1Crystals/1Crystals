import json
import os
import re
from datetime import datetime

ARCHIVE_DIR = os.path.join(".agents", "context")
WINDOW_DEFAULT = 128000
WARN_RATIO = 0.60
SUMMARY_TARGET = 5000

COMPACT_PROMPT = """你是一名 AI Agent 的上下文管理助手。当前会话即将达到上下文窗口限制，需要将历史对话压缩为一份高质量的工作摘要，以便 Agent 在新的上下文中继续执行任务。

请认真阅读提供的历史上下文，提取对后续工作仍然有价值的信息，并生成一份约 5,000 Tokens 的 Markdown 摘要。

摘要应重点保留以下内容：

1. **用户目标与要求**：用户希望完成什么任务？有哪些必须遵守的约束、偏好和验收条件？
2. **已经完成的工作**：哪些任务已经完成？实现了哪些功能？获得了哪些已经验证的结果？
3. **当前工作状态**：Agent 正在处理什么任务？当前进展到哪一步？是否存在尚未解决的问题？
4. **关键技术信息**：保留重要的文件路径、函数名称、接口定义、配置项、执行命令、错误信息和必要的代码片段。
5. **关键决策与原因**：记录用户和 Agent 已经确定的技术方案，以及重要的设计取舍。
6. **下一步任务**：明确接下来应该执行的操作，以及需要继续验证的事项。

请遵守以下要求：

- 优先保留对后续任务有直接影响的信息，删除寒暄、重复讨论、过时的尝试和无关内容。
- 对已经验证的事实与尚未验证的推测作出明确区分。
- 不要将计划完成的任务描述为已经完成。
- 重要的文件路径、函数名称、配置名称和命令应保留准确原文。
- 对失败的尝试，只保留有助于避免重复错误的信息。
- 如果信息存在冲突，应优先保留用户最新确认的要求，并简要说明仍然存在的冲突。
- 如果某些历史细节无法在摘要中完整保留，可简要说明它们已保存到原始上下文归档中，后续可以通过 `recallContext` 工具重新检索。
- 使用清晰的 Markdown 结构输出摘要，不要附加解释或无关内容。

**最终目标：使一个从未阅读过原始对话的 Agent，仅凭这份摘要，就能够理解当前任务、继承关键决策，并继续开展工作。"""


def estimate_tokens(text) -> int:
    """简单 Token 估算：中文每字约 1.2 token，英文约为字符数 / 4。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return max(1, int(cjk * 1.2 + other / 4))


def _formatted(messages) -> str:
    """把消息列表格式化为可读文本，用于展示原文与压缩。"""
    lines = []
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content") or ""
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                lines.append(f"[{role}::调用工具 {fn.get('name')}]\n参数: {fn.get('arguments')}")
        if msg.get("tool_call_id"):
            lines.append(f"[{role}::工具返回 {msg.get('tool_call_id')}]\n{content}")
            continue
        if content:
            lines.append(f"[{role}]\n{content}")
    return "\n\n".join(lines)


class ContextManager:
    def __init__(self, root=None, window_size=None, warn_ratio=None):
        self.root = os.path.abspath(root or os.getcwd())
        self.window_size = window_size or WINDOW_DEFAULT
        self.warn_ratio = WARN_RATIO if warn_ratio is None else float(warn_ratio)
        self.tokens = 0
        self.context_dir = os.path.join(self.root, ARCHIVE_DIR)

    def set_estimated_tokens(self, messages) -> None:
        self.tokens = estimate_tokens(_formatted(messages))
        return self.tokens

    def set_usage_tokens(self, prompt_tokens) -> None:
        if prompt_tokens:
            self.tokens = int(prompt_tokens)

    @property
    def ratio(self) -> float:
        return (self.tokens / self.window_size) if self.window_size else 0.0

    def is_warning(self) -> bool:
        return self.ratio >= self.warn_ratio

    def archive(self, messages, model) -> tuple:
        """把原始上下文完整保存为编号 JSONL。返回 (archive_id, path)。"""
        archive_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        os.makedirs(self.context_dir, exist_ok=True)
        path = os.path.join(self.context_dir, archive_id + ".jsonl")
        lines = [
            json.dumps(
                {
                    "archive_id": archive_id,
                    "model": model,
                    "saved_at": datetime.now().isoformat(),
                },
                ensure_ascii=False,
            )
        ] + [json.dumps(msg, ensure_ascii=False) for msg in messages]
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        return archive_id, path

    def _search_file(self, path, keywords, results) -> None:
        stamp = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return
        for lineno, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            blob = json.dumps(obj, ensure_ascii=False)
            matched = [k for k in keywords if k in blob]
            if not matched:
                continue
            snippet = self._snippet(blob, matched[0])
            results.append(
                {
                    "archive_id": stamp,
                    "line": lineno,
                    "role": obj.get("role", "meta"),
                    "keywords": matched,
                    "snippet": snippet,
                }
            )

    @staticmethod
    def _snippet(blob, keyword, radius=240) -> str:
        idx = blob.find(keyword)
        if idx < 0:
            return blob[: radius * 2]
        start = max(0, idx - radius)
        end = min(len(blob), idx + radius)
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(blob) else ""
        return prefix + blob[start:end] + suffix

    def recall(self, text, archive_id=None, limit=1500) -> str:
        text = (text or "").strip()
        if not text:
            return "【错误】请提供需要检索的关键词"

        files = []
        if archive_id:
            archive_id = str(archive_id).strip()
            path = os.path.join(self.context_dir, archive_id + ".jsonl")
            if not os.path.isfile(path):
                return f"【错误】未找到归档 {archive_id}"
            files = [path]
        else:
            if not os.path.isdir(self.context_dir):
                return "【错误】暂无历史归档（.agents/context 不存在）"
            files = [
                os.path.join(self.context_dir, name)
                for name in sorted(os.listdir(self.context_dir))
                if name.endswith(".jsonl")
            ]
            if not files:
                return "【错误】暂无历史归档"

        keywords = re.findall(r"[A-Za-z0-9_./:\\-]+|[\u4e00-\u9fff]+", text)
        keywords = [k for k in keywords if k and len(k) >= 1]
        if not keywords:
            return "【错误】未识别到有效关键词"

        results = []
        for path in files:
            self._search_file(path, keywords, results)
            if len(results) > 0 and not archive_id:
                # 全部归档检索时避免过多结果堆满上下文
                if len(results) >= 16:
                    break

        if not results:
            return f"在 {'归档 ' + archive_id if archive_id else '所有历史归档'} 中未检索到与 {keywords} 相关的内容"

        out = [f"检索到 {len(results)} 条相关记录（关键词: {', '.join(keywords)}）："]
        for r in results[:12]:
            out.append(
                f"\n[归档 {r['archive_id']} · 第{r['line']}行 · 角色:{r['role']}]\n"
                f"命中关键词: {', '.join(r['keywords'])}\n{r['snippet']}"
            )
        return "\n".join(out)[:limit]


_manager = ContextManager()

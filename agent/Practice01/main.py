import configparser
import json
import os
import re

from openai import OpenAI

cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")

client = OpenAI(
    api_key=cfg["llm"]["api_key"],
    base_url=cfg["llm"]["base_url"],
)

MEMORY_FILE = "memory.json"


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return []
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_memory(messages):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)


def load_long_term_memory(messages):
    facts = [m["content"] for m in messages if m["role"] == "user"]
    summary = "\n".join(f"- {t}" for t in facts[-50:])
    return [{"role": "system", "content": "以下是用户之前说过的话，请据此回答：\n" + summary}]


messages = load_memory()
print(f"已加载历史记忆 {len(messages)} 条")

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
        messages = []
        save_memory(messages)
        print("记忆已清空")
        continue

    messages.append({"role": "user", "content": user_input})
    payload = load_long_term_memory(messages) + messages

    stream = client.chat.completions.create(
        model=cfg["llm"]["model_name"],
        messages=payload,
        stream=True,
    )
    text = ""
    for c in stream:
        text += c.choices[0].delta.content or ""
    answer = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    print("AI:", answer)
    messages.append({"role": "assistant", "content": answer})
    save_memory(messages)
    print(f"[记忆条数: {len(messages)}]")
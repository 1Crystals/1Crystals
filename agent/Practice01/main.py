import configparser
import re
from openai import OpenAI

cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")

client = OpenAI(
    api_key=cfg["llm"]["api_key"],
    base_url=cfg["llm"]["base_url"],
)

messages = []

while True:
    messages.append({"role": "user", "content": input("你: ")})
    stream = client.chat.completions.create(
        model=cfg["llm"]["model_name"],
        messages=messages,
        stream=True,
    )
    text = ""
    for c in stream:
        text += c.choices[0].delta.content or ""
    answer = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    print("AI:", answer)
    messages.append({"role": "assistant", "content": answer})
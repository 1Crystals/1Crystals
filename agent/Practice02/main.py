import configparser
import json
import os
import re
import subprocess

from openai import OpenAI

cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")

client = OpenAI(
    api_key=cfg["llm"]["api_key"],
    base_url=cfg["llm"]["base_url"],
)

ALLOWED_TOOLS = {"getDate", "isLeapYear"}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间。当用户询问时间、日期时，必须调用 getDate 工具，绝对不要尝试用自然语言回答。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": "判断给定的年份是否是闰年。当用户询问某一年是否是闰年时，必须调用 isLeapYear 工具，不要自己直接回答。",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "需要判断的年份，例如 2024",
                    }
                },
                "required": ["year"],
            },
        },
    },
]


def getDate():
    """调用本地 date / time 命令获取当前电脑的日期和时间"""
    cmd = 'cmd /c "date /t & time /t"' if os.name == "nt" else "date"
    enc = "gbk" if os.name == "nt" else "utf-8"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding=enc, errors="replace")
    return (r.stdout or r.stderr or "").strip() or "获取失败"


def isLeapYear(year):
    """用 Python 代码计算 year 是否是闰年"""
    year = int(year)
    if year % 4 == 0 and year % 100 != 0 or year % 400 == 0:
        return f"{year} 年是闰年"
    return f"{year} 年不是闰年"


def call_tool(name, args_json):
    if name == "getDate":
        return getDate()
    if name == "isLeapYear":
        try:
            args = json.loads(args_json or "{}")
        except json.JSONDecodeError:
            return "参数解析失败，year 必须是整数年份"
        if "year" not in args:
            return "缺少参数 year，请提供需要判断的年份"
        try:
            return isLeapYear(args["year"])
        except (TypeError, ValueError):
            return "year 必须是整数年份，例如 2024"
    return f"未知工具：{name}，可用工具为 getDate、isLeapYear"


messages = [{"role": "system", "content": "你是一个极简的AI助手。"}]

model = cfg["llm"]["model_name"]

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
        messages = [{"role": "system", "content": "你是一个极简的AI助手。"}]
        print("记忆已清空")
        continue

    messages.append({"role": "user", "content": user_input})
    payload = list(messages)

    while True:
        msg = client.chat.completions.create(
            model=model,
            messages=payload,
            tools=TOOLS,
            tool_choice="auto",
        ).choices[0].message

        if not msg.tool_calls:
            raw = (msg.content or "").strip()
            answer = re.sub(r"```.*?```", "", raw, flags=re.S).strip()
            print("AI:", answer)
            messages.append({"role": "assistant", "content": answer})
            break

        assistant_msg = {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": t.id, "type": "function",
                 "function": {"name": t.function.name, "arguments": t.function.arguments}}
                for t in msg.tool_calls
            ],
        }
        messages.append(assistant_msg)
        payload = payload + [assistant_msg]

        for t in msg.tool_calls:
            name = t.function.name
            print(f"[调用工具 {name}]")
            result = call_tool(name, t.function.arguments)
            tool_msg = {"role": "tool", "tool_call_id": t.id, "content": result}
            messages.append(tool_msg)
            payload = payload + [tool_msg]

        print("AI:", msg.content or result)

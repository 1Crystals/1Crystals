import configparser
import json
import mimetypes
import os
import re
import shutil

from openai import OpenAI

cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")

client = OpenAI(
    api_key=cfg["llm"]["api_key"],
    base_url=cfg["llm"]["base_url"],
)

ALLOWED_TOOLS = {
    "getDate", "isLeapYear",
    "getcwd", "listDir", "getFileType", "readFile",
    "createFile", "editFile", "createDir",
    "removeDir", "removeFile", "renamePath",
}

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
    {
        "type": "function",
        "function": {
            "name": "getcwd",
            "description": "获取当前的工作目录（绝对路径）。当用户询问当前目录、工作目录是什么时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listDir",
            "description": "列出指定目录下的所有文件和子目录。path 为空时默认列出当前工作目录。当用户想查看某个目录里有什么内容时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出内容的目录路径，可以是相对路径或绝对路径，例如 . 或 D:/test",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getFileType",
            "description": "获取指定文件的文件类型（扩展名和 MIME 类型）。当用户询问某文件是什么类型时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径，例如 note.txt",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "readFile",
            "description": "读取指定纯文本文件的内容。仅支持文本文件，不支持二进制文件（如图片、可执行文件）。当用户想查看或读取某文件内容时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的文件路径，例如 note.txt",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createFile",
            "description": "在指定目录下创建一个新的纯文本文件，目录不存在时会自动创建目录。若文件已存在则覆盖其内容。当用户想新建文件时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir": {
                        "type": "string",
                        "description": "文件所在目录路径，例如 . 或 D:/test，为空表示当前目录",
                    },
                    "filename": {
                        "type": "string",
                        "description": "文件名，例如 note.txt",
                    },
                    "content": {
                        "type": "string",
                        "description": "写入文件的文本内容，可为空字符串",
                    },
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editFile",
            "description": "编辑指定纯文本文件的内容：将文件中所有 old_text 替换为 new_text；若 new_text 为空则删除 old_text。仅支持文本文件。当用户想修改、替换某文件内容时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要编辑的文件路径，例如 note.txt",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "要被替换或删除的原文本，必须与文件中的内容完全一致",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "替换后的新文本，为空字符串表示删除 old_text",
                    },
                },
                "required": ["path", "old_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createDir",
            "description": "创建一个新目录，若上级目录不存在会一并创建（递归创建）。当用户想新建文件夹/目录时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要创建的目录路径，例如 new_folder 或 D:/a/b",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "removeDir",
            "description": "删除指定目录及其包含的所有文件和子目录（非空目录也可删除）。这是不可逆操作，调用前应与用户确认。当用户想删除文件夹/目录时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的目录路径，例如 old_folder",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "removeFile",
            "description": "删除指定的文件。这是不可逆操作，调用前应与用户确认。当用户想删除某文件时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的文件路径，例如 old.txt",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "renamePath",
            "description": "重命名或移动文件/目录，将 old_path 重命名为 new_path（也可用于跨目录移动）。当用户想重命名文件、文件夹或移动它们时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_path": {
                        "type": "string",
                        "description": "原文件或目录路径，例如 old.txt",
                    },
                    "new_path": {
                        "type": "string",
                        "description": "新文件或目录路径，例如 new.txt",
                    },
                },
                "required": ["old_path", "new_path"],
            },
        },
    },
]


def getDate():
    """调用本地 date / time 命令获取当前电脑的日期和时间"""
    import subprocess
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


def getcwd():
    """获取当前工作目录"""
    return os.getcwd()


def listDir(path=""):
    """列出指定目录下所有文件和子目录"""
    path = path or "."
    if not os.path.isdir(path):
        return f"目录不存在：{path}"
    entries = sorted(os.listdir(path))
    if not entries:
        return f"目录 {os.path.abspath(path)} 是空目录"
    lines = [f"目录 {os.path.abspath(path)} 的内容："]
    for name in entries:
        full = os.path.join(path, name)
        tag = "[目录]" if os.path.isdir(full) else "[文件]"
        lines.append(f"{tag} {name}")
    return "\n".join(lines)


def getFileType(path):
    """获取指定文件的扩展名和 MIME 类型"""
    if not os.path.exists(path):
        return f"文件不存在：{path}"
    if os.path.isdir(path):
        return f"{path} 是一个目录，不是文件"
    ext = os.path.splitext(path)[1]
    mime, encoding = mimetypes.guess_type(path)
    lines = [f"文件名：{os.path.basename(path)}"]
    lines.append(f"扩展名：{ext if ext else '（无扩展名）'}")
    lines.append(f"MIME 类型：{mime if mime else '未知'}")
    if encoding:
        lines.append(f"编码：{encoding}")
    size = os.path.getsize(path)
    lines.append(f"文件大小：{size} 字节")
    return "\n".join(lines)


def _read_text(path):
    """按 utf-8 / gbk 顺序尝试解码纯文本文件"""
    with open(path, "rb") as f:
        raw = f.read()
    if b"\x00" in raw:
        raise ValueError("二进制文件")
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def readFile(path):
    """读取指定纯文本文件的内容"""
    if not os.path.exists(path):
        return f"文件不存在：{path}"
    if os.path.isdir(path):
        return f"{path} 是一个目录，请指定具体的文件"
    try:
        text = _read_text(path)
    except ValueError:
        return f"文件 {path} 不是纯文本文件，暂不支持读取"
    if not text:
        return f"文件 {path} 的内容为空"
    return f"文件 {path} 的内容：\n{text}"


def createFile(dir, filename, content=""):
    """在指定目录下创建新文件，目录不存在时自动创建"""
    dir = dir or "."
    os.makedirs(dir, exist_ok=True)
    path = os.path.join(dir, filename)
    if os.path.isdir(path):
        return f"已存在同名目录，无法创建文件：{path}"
    existed = os.path.exists(path)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    action = "覆盖更新" if existed else "创建"
    return f"已{action}文件：{os.path.abspath(path)}"


def editFile(path, old_text, new_text=""):
    """将文件中所有 old_text 替换为 new_text，new_text 为空则删除 old_text"""
    if not os.path.exists(path):
        return f"文件不存在：{path}"
    if os.path.isdir(path):
        return f"{path} 是一个目录，请指定具体的文件"
    try:
        text = _read_text(path)
    except ValueError:
        return f"文件 {path} 不是纯文本文件，暂不支持编辑"
    if old_text not in text:
        return f"在文件 {path} 中未找到 old_text，请确保文本与文件内容完全一致"
    count = text.count(old_text)
    new_content = text.replace(old_text, new_text)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_content)
    if new_text:
        return f"已将文件 {os.path.abspath(path)} 中的 {count} 处匹配文本替换完成"
    return f"已从文件 {os.path.abspath(path)} 中删除 {count} 处匹配文本"


def createDir(path):
    """递归创建新目录"""
    os.makedirs(path, exist_ok=True)
    return f"目录已存在或创建成功：{os.path.abspath(path)}"


def removeDir(path):
    """删除非空目录及其所有内容"""
    if not os.path.exists(path):
        return f"目录不存在：{path}"
    if not os.path.isdir(path):
        return f"{path} 不是目录，请使用删除文件工具"
    shutil.rmtree(path)
    return f"已删除目录（含所有内容）：{path}"


def removeFile(path):
    """删除指定文件"""
    if not os.path.exists(path):
        return f"文件不存在：{path}"
    if os.path.isdir(path):
        return f"{path} 是一个目录，请使用删除目录工具"
    os.remove(path)
    return f"已删除文件：{path}"


def renamePath(old_path, new_path):
    """重命名或移动文件/目录"""
    if not os.path.exists(old_path):
        return f"路径不存在：{old_path}"
    if os.path.exists(new_path):
        return f"目标路径已存在：{new_path}"
    new_parent = os.path.dirname(new_path)
    if new_parent:
        os.makedirs(new_parent, exist_ok=True)
    shutil.move(old_path, new_path)
    return f"已将 {old_path} 重命名/移动为 {new_path}"


TOOL_FUNCS = {
    "getDate": getDate,
    "isLeapYear": isLeapYear,
    "getcwd": getcwd,
    "listDir": listDir,
    "getFileType": getFileType,
    "readFile": readFile,
    "createFile": createFile,
    "editFile": editFile,
    "createDir": createDir,
    "removeDir": removeDir,
    "removeFile": removeFile,
    "renamePath": renamePath,
}

TOOL_SPECS = {
    "isLeapYear": ("year",),
    "listDir": ("path",),
    "getFileType": ("path",),
    "readFile": ("path",),
    "createFile": ("filename",),
    "editFile": ("path", "old_text"),
    "createDir": ("path",),
    "removeDir": ("path",),
    "removeFile": ("path",),
    "renamePath": ("old_path", "new_path"),
}


def call_tool(name, args_json):
    if name not in ALLOWED_TOOLS:
        return f"未知工具：{name}"
    try:
        args = json.loads(args_json or "{}")
    except json.JSONDecodeError:
        return "参数解析失败，请检查 JSON 格式"
    if not isinstance(args, dict):
        return "参数必须是 JSON 对象"
    for key in TOOL_SPECS.get(name, ()):
        if key not in args or args[key] is None or args[key] == "":
            return f"缺少参数 {key}，请补充后重试"
    try:
        return str(TOOL_FUNCS[name](**args))
    except Exception as e:
        return f"工具 {name} 执行出错：{e}"


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

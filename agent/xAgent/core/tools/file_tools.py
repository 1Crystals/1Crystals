import mimetypes
import os
import shutil

from .registry import register


@register(
    "getcwd",
    description="获取当前的工作目录（绝对路径）。当用户询问当前目录、工作目录是什么时调用。",
)
def getcwd():
    return os.getcwd()


@register(
    "listDir",
    description="列出指定目录下的所有文件和子目录。path 为空时默认列出当前工作目录。当用户想查看某个目录里有什么内容时调用。",
    properties={
        "path": {
            "type": "string",
            "description": "要列出内容的目录路径，可以是相对路径或绝对路径，例如 . 或 D:/test",
        }
    },
)
def listDir(path=""):
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


@register(
    "getFileType",
    description="获取指定文件的文件类型（扩展名和 MIME 类型）。当用户询问某文件是什么类型时调用。",
    properties={
        "path": {
            "type": "string",
            "description": "文件路径，例如 note.txt",
        }
    },
    required=["path"],
)
def getFileType(path):
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


@register(
    "readFile",
    description="读取指定纯文本文件的内容。仅支持文本文件，不支持二进制文件（如图片、可执行文件）。当用户想查看或读取某文件内容时调用。",
    properties={
        "path": {
            "type": "string",
            "description": "要读取的文件路径，例如 note.txt",
        }
    },
    required=["path"],
)
def readFile(path):
    if isinstance(path, str) and path.strip().lower().startswith(("http://", "https://")):
        return "【系统提示】传入的是 URL 链接，请调用网页抓取工具（如 searchWeb 或 fetch_web）处理，不要使用文件读取工具。"
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


@register(
    "createFile",
    description="在指定目录下创建一个新的纯文本文件，目录不存在时会自动创建目录。若文件已存在则覆盖其内容。当用户想新建文件时调用。",
    properties={
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
    required=["filename"],
)
def createFile(dir, filename, content=""):
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


@register(
    "editFile",
    description="编辑指定纯文本文件的内容：将文件中所有 old_text 替换为 new_text；若 new_text 为空则删除 old_text。仅支持文本文件。当用户想修改、替换某文件内容时调用。",
    properties={
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
    required=["path", "old_text"],
)
def editFile(path, old_text, new_text=""):
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


@register(
    "createDir",
    description="创建一个新目录，若上级目录不存在会一并创建（递归创建）。当用户想新建文件夹/目录时调用。",
    properties={
        "path": {
            "type": "string",
            "description": "要创建的目录路径，例如 new_folder 或 D:/a/b",
        }
    },
    required=["path"],
)
def createDir(path):
    os.makedirs(path, exist_ok=True)
    return f"目录已存在或创建成功：{os.path.abspath(path)}"


@register(
    "removeDir",
    description="删除指定目录及其包含的所有文件和子目录（非空目录也可删除）。这是不可逆操作，调用前应与用户确认。当用户想删除文件夹/目录时调用。",
    properties={
        "path": {
            "type": "string",
            "description": "要删除的目录路径，例如 old_folder",
        }
    },
    required=["path"],
)
def removeDir(path):
    if not os.path.exists(path):
        return f"目录不存在：{path}"
    if not os.path.isdir(path):
        return f"{path} 不是目录，请使用删除文件工具"
    shutil.rmtree(path)
    return f"已删除目录（含所有内容）：{path}"


@register(
    "removeFile",
    description="删除指定的文件。这是不可逆操作，调用前应与用户确认。当用户想删除某文件时调用。",
    properties={
        "path": {
            "type": "string",
            "description": "要删除的文件路径，例如 old.txt",
        }
    },
    required=["path"],
)
def removeFile(path):
    if not os.path.exists(path):
        return f"文件不存在：{path}"
    if os.path.isdir(path):
        return f"{path} 是一个目录，请使用删除目录工具"
    os.remove(path)
    return f"已删除文件：{path}"


@register(
    "renamePath",
    description="重命名或移动文件/目录，将 old_path 重命名为 new_path（也可用于跨目录移动）。当用户想重命名文件、文件夹或移动它们时调用。",
    properties={
        "old_path": {
            "type": "string",
            "description": "原文件或目录路径，例如 old.txt",
        },
        "new_path": {
            "type": "string",
            "description": "新文件或目录路径，例如 new.txt",
        },
    },
    required=["old_path", "new_path"],
)
def renamePath(old_path, new_path):
    if not os.path.exists(old_path):
        return f"路径不存在：{old_path}"
    if os.path.exists(new_path):
        return f"目标路径已存在：{new_path}"
    new_parent = os.path.dirname(new_path)
    if new_parent:
        os.makedirs(new_parent, exist_ok=True)
    shutil.move(old_path, new_path)
    return f"已将 {old_path} 重命名/移动为 {new_path}"

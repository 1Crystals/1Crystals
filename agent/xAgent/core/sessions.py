import json
import os
from datetime import datetime


def session_dir(root) -> str:
    return os.path.join(root, ".agents", "sessions")


def new_session_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def save_session(root, messages, session_id=None, title="") -> str:
    """保存会话。若 session_id 为空则新建编号，否则覆盖同编号文件。返回 session_id。"""
    sid = session_id or new_session_id()
    base = session_dir(root)
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, sid + ".json")
    payload = {
        "session_id": sid,
        "title": (title or "").strip(),
        "saved_at": datetime.now().isoformat(),
        "messages": list(messages or []),
    }
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return sid


def load_session(root, session_id) -> dict | None:
    path = os.path.join(session_dir(root), str(session_id) + ".json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def list_sessions(root) -> list:
    """返回 [(session_id, title, saved_at, msg_count)]，按保存时间倒序。"""
    base = session_dir(root)
    if not os.path.isdir(base):
        return []
    items = []
    for name in sorted(os.listdir(base)):
        if not name.endswith(".json"):
            continue
        sid = name[:-5]
        path = os.path.join(base, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items.append((
                sid,
                data.get("title", "") or "",
                data.get("saved_at", ""),
                len(data.get("messages", [])),
            ))
        except (OSError, json.JSONDecodeError):
            continue
    items.sort(key=lambda it: it[0], reverse=True)
    return items


def read_agents_file(root) -> str | None:
    """读取项目目录下的 AGENTS.md；不存在则返回 None。"""
    path = os.path.join(root, "AGENTS.md")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None

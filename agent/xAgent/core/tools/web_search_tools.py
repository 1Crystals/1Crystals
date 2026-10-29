import configparser
import json
import os
import random
import socket
import struct
import subprocess
from urllib.parse import urlsplit, urljoin

from bs4 import BeautifulSoup

from .registry import register


# ---------------------------------------------------------------------------
# 1. 底层 Socket 强制 IPv4（防御 IPv6 假死）
# ---------------------------------------------------------------------------
_orig_getaddrinfo = socket.getaddrinfo


def _getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _getaddrinfo_ipv4_only


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.ini")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 公共 DNS（绕过被加速器劫持的系统 DNS，例如 fe80:: 链路本地地址）
DNS_SERVERS = ("223.5.5.5", "119.29.29.29", "180.76.76.76", "8.8.8.8")

_STATUS_MARKER = "__CURL_STATUS__"
_REDIRECT_MARKER = "__CURL_REDIRECT__"
_CURL_WRITE_FORMAT = f"\n{_STATUS_MARKER}:%{{http_code}}\n{_REDIRECT_MARKER}:%{{redirect_url}}"

_SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search"


# ---------------------------------------------------------------------------
# 2. DNS 解析：直接向公共 DNS 发 UDP 查询，只取 IPv4 A 记录
# ---------------------------------------------------------------------------
def _dns_query_a(host: str, server: str, timeout: float = 4.0):
    """向指定 DNS 服务器查询 host 的 IPv4 地址，返回 str 列表。"""
    tid = random.randint(0, 0xFFFF)
    packet = struct.pack("!HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    for part in host.rstrip(".").split("."):
        if not part:
            continue
        packet += bytes([len(part)]) + part.encode("idna")
    packet += b"\x00" + struct.pack("!HH", 1, 1)  # QTYPE=A, QCLASS=IN

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        sock.sendto(packet, (server, 53))
        data, _ = sock.recvfrom(4096)
    finally:
        sock.close()

    _, _, qdcount, ancount, _, _ = struct.unpack("!HHHHHH", data[:12])
    idx = 12
    for _ in range(qdcount):
        while data[idx] != 0:
            idx += data[idx] + 1
        idx += 5

    ips = []
    for _ in range(ancount):
        if data[idx] & 0xC0 == 0xC0:  # 压缩指针
            idx += 2
        else:
            while data[idx] != 0:
                idx += data[idx] + 1
            idx += 1
        rtype, rclass, _ttl, rdlen = struct.unpack("!HHIH", data[idx:idx + 10])
        idx += 10
        if rtype == 1 and rdlen == 4:  # A 记录
            ips.append(".".join(str(b) for b in data[idx:idx + 4]))
        idx += rdlen
    return ips


def _resolve_ipv4(host: str):
    """绕过系统 DNS 解析出 IPv4；已是 IP 则原样返回；失败返回空列表。"""
    try:
        socket.inet_aton(host)
        return [host]
    except OSError:
        pass

    for server in DNS_SERVERS:
        try:
            ips = _dns_query_a(host, server)
            if ips:
                return ips
        except Exception:
            continue
    return []


# ---------------------------------------------------------------------------
# 3. curl 执行封装
# ---------------------------------------------------------------------------
def _split_url(url: str):
    parts = urlsplit(url)
    scheme = (parts.scheme or "https").lower()
    host = parts.hostname or ""
    port = parts.port or (443 if scheme == "https" else 80)
    return scheme, host, port


def _run_curl(cmd: list, timeout: int):
    """
    执行 curl.exe。

    Returns:
        (ok, body_bytes, status, redirect, error)
    """
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return False, b"", None, None, "【错误】系统未找到 curl.exe，请确认 Windows 已安装 curl"
    except subprocess.TimeoutExpired:
        return False, b"", None, None, "【错误】请求超时，目标服务器未在规定时间内响应"
    except Exception as e:
        return False, b"", None, None, f"【错误】底层请求异常：{type(e).__name__} - {e}"

    raw = result.stdout or b""
    status = None
    redirect = ""

    marker = _STATUS_MARKER.encode()
    if marker in raw:
        body, _, tail = raw.rpartition(marker)
        tail_text = tail.decode("utf-8", "replace")
        for line in tail_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(_REDIRECT_MARKER + ":"):
                redirect = line.split(":", 1)[1].strip()
            else:
                status = line.lstrip(":").strip()
        body = body.rstrip(b"\r\n")
    else:
        body = raw

    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", "replace").strip()
        return False, b"", status, None, (
            f"【错误】curl 执行失败（退出码 {result.returncode}）：{detail[:200]}"
        )

    return True, body, status, redirect, None


def _curl(url, method="GET", headers=None, data=None, timeout=30, follow=False):
    """
    用系统 curl.exe 发请求：
    - -4 强制 IPv4
    - -x "" + --noproxy * 彻底清空代理
    - -k 忽略证书
    - --resolve 使用公共 DNS 解析出的 IPv4，绕过系统 DNS 劫持
    """
    headers = headers or []
    current = url
    current_method = method.upper()
    current_data = data

    for _ in range(6):
        _, host, port = _split_url(current)
        resolve_args = []
        ips = _resolve_ipv4(host)
        if ips:
            resolve_args = ["--resolve", f"{host}:{port}:{ips[0]}"]

        cmd = [
            "curl.exe", "-s", "-S", "-4",
            "-x", "", "--noproxy", "*",
            "-k", "--compressed", "-g",
            "--connect-timeout", "12",
            "--max-time", str(timeout),
            *resolve_args,
            "-w", _CURL_WRITE_FORMAT,
        ]
        if current_method == "POST":
            cmd += ["-X", "POST", "-d", current_data or ""]
        for h in headers:
            cmd += ["-H", h]
        cmd.append(current)

        ok, body, status, redirect, err = _run_curl(cmd, timeout + 5)
        if not ok:
            return False, b"", None, err

        if follow and status in ("301", "302", "303", "307", "308") and redirect:
            current = urljoin(current, redirect)
            if status == "303":
                current_method = "GET"
                current_data = None
            continue

        return True, body, status, None

    return False, b"", None, "【错误】重定向次数过多，已停止"


def _http_status_error(status, context):
    try:
        code = int(status)
    except (TypeError, ValueError):
        return f"【错误】{context}返回未知状态码：{status}"

    if code == 401:
        return "【错误】鉴权失败（401），请检查 API Key 是否正确或已过期"
    if code == 403:
        return f"【错误】{context}访问被拒绝（403），可能无权限或触发反爬限制"
    if code == 404:
        return f"【错误】{context}资源不存在（404）"
    if code == 429:
        return "【错误】请求过于频繁（429），请稍后再试"
    if 500 <= code < 600:
        return f"【错误】目标服务暂时不可用（{code}），请稍后重试"
    return f"【错误】{context}请求失败（HTTP {code}）"


# ---------------------------------------------------------------------------
# 4. 配置读取
# ---------------------------------------------------------------------------
def _load_qianfan_api_key() -> str:
    if not os.path.exists(CONFIG_PATH):
        return "【错误】请在 config.ini 中配置有效的 baidu_qianfan_api_key（配置文件不存在）"

    cfg = configparser.ConfigParser()
    try:
        cfg.read(CONFIG_PATH, encoding="utf-8")
    except Exception as e:
        return f"【错误】配置文件读取失败：{type(e).__name__} - {e}"

    if "search" not in cfg:
        return "【错误】请在 config.ini 中配置有效的 baidu_qianfan_api_key（缺少 [search] 小节）"

    if "baidu_qianfan_api_key" not in cfg["search"]:
        return "【错误】请在 config.ini 中配置有效的 baidu_qianfan_api_key（未设置 baidu_qianfan_api_key）"

    api_key = cfg["search"]["baidu_qianfan_api_key"].strip()
    if not api_key:
        return "【错误】请在 config.ini 中配置有效的 baidu_qianfan_api_key（Key 为空）"

    return api_key


# ---------------------------------------------------------------------------
# 5. 工具：searchWeb
# ---------------------------------------------------------------------------
@register(
    "searchWeb",
    description="在互联网上搜索关键词或问题，获取相关结果的摘要和来源。返回格式：每项结果包含标题、URL和摘要。当用户需要获取最新信息或未知知识时调用。",
    properties={
        "query": {
            "type": "string",
            "description": "搜索关键词或问题，例如 'Python 列表去重方法' 或 '今天北京天气'",
        }
    },
    required=["query"],
)
def searchWeb(query: str) -> str:
    """使用系统原生 curl.exe 调用百度千帆 AI 搜索 API。"""
    if not query or not str(query).strip():
        return "【错误】搜索关键词不能为空"
    query = query.strip()

    api_key = _load_qianfan_api_key()
    if api_key.startswith("【错误】"):
        return api_key

    payload = json.dumps(
        {
            "messages": [{"role": "user", "content": query}],
            "stream": False,
            "search_source": "baidu_search_v2",
        },
        ensure_ascii=False,
    )

    headers = [
        f"Authorization: Bearer {api_key}",
        "Content-Type: application/json",
        f"User-Agent: {USER_AGENT}",
    ]

    ok, body, status, err = _curl(
        _SEARCH_URL, method="POST", headers=headers, data=payload, timeout=30
    )
    if not ok:
        return err

    if status and status != "200":
        return _http_status_error(status, "千帆搜索 API")

    text = body.decode("utf-8", "replace").strip()

    try:
        data = json.loads(text) if text else {}
    except Exception:
        return f"【错误】搜索接口返回内容无法解析：{text[:120]}"

    if isinstance(data, dict):
        code = data.get("code")
        if code not in (None, 0, "0", 200, "200") and (
            "message" in data or "error_msg" in data
        ):
            msg = data.get("message") or data.get("error_msg")
            return f"【错误】千帆API返回错误（代码 {code}）：{msg}"

    results = _extract_results(data)
    if not results:
        answer = _extract_answer(data)
        if answer:
            return f"搜索 '{query}' 的结果：\n{answer[:2000]}"
        return f"未找到与 '{query}' 相关的搜索结果"

    lines = [f"搜索 '{query}' 的结果：\n"]
    for i, item in enumerate(results, 1):
        title = item.get("title") or item.get("name") or "无标题"
        url_ = item.get("url") or item.get("link") or ""
        snippet = item.get("snippet") or item.get("content") or item.get("summary") or item.get("abstract") or ""
        snippet = str(snippet).strip().replace("\n", " ")[:300]
        if url_:
            lines.append(f"{i}. **{title}**\n   🔗 {url_}\n   📝 {snippet}\n")
        else:
            lines.append(f"{i}. **{title}**\n   📝 {snippet}\n")

    return "\n".join(lines).strip()


def _extract_results(data):
    """从各种可能的响应结构中提取结果列表。"""
    if not isinstance(data, dict):
        return []
    for key in ("references", "search_results", "results", "data", "items"):
        value = data.get(key)
        if isinstance(value, list) and value:
            if all(isinstance(v, dict) for v in value):
                return value
        if isinstance(value, dict):
            for sub in ("results", "items", "references", "search_results"):
                sub_value = value.get(sub)
                if isinstance(sub_value, list) and sub_value:
                    return sub_value
    return []


def _extract_answer(data):
    if not isinstance(data, dict):
        return ""
    for key in ("answer", "content", "response", "result"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


# ---------------------------------------------------------------------------
# 6. 工具：fetch_web
# ---------------------------------------------------------------------------
@register(
    "fetch_web",
    description="抓取并读取指定网页的正文纯文本内容。当用户提供 http/https 链接，或需要查看某个网页的具体内容时调用。返回内容最多 2000 字符。",
    properties={
        "url": {
            "type": "string",
            "description": "要抓取的网页链接，必须以 http:// 或 https:// 开头",
        }
    },
    required=["url"],
)
def fetch_web(url: str) -> str:
    """使用系统原生 curl.exe 抓取网页，再用 BeautifulSoup 提取正文纯文本。"""
    if not url or not str(url).strip():
        return "【错误】网页 URL 不能为空"

    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        return "【错误】URL 必须以 http:// 或 https:// 开头"

    headers = [
        f"User-Agent: {USER_AGENT}",
        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
    ]

    ok, body, status, err = _curl(url, method="GET", headers=headers, timeout=30, follow=True)
    if not ok:
        return err

    if status and status != "200":
        return _http_status_error(status, "网页抓取")

    try:
        # 直接传字节，BeautifulSoup 会依据 <meta charset> 自动识别编码
        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    except Exception as e:
        return f"【错误】网页内容解析失败：{type(e).__name__} - {e}"

    if not text:
        return f"【错误】未从网页 {url} 中提取到有效文本内容"

    return f"网页 {url} 的内容：\n{text[:2000]}"

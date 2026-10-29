import subprocess

from .registry import register


TIMEOUT_SECONDS = 60
# 单个输出流（stdout / stderr）的最大保留字符数，避免占用过多上下文
MAX_STREAM_CHARS = 3000


def _decode(raw: bytes) -> str:
    if not raw:
        return ""
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _truncate(text: str, label: str) -> str:
    """对单个输出流做截断，并明确标注被截断的状态。"""
    total = len(text)
    if total <= MAX_STREAM_CHARS:
        return text
    kept = text[:MAX_STREAM_CHARS]
    return (
        f"{kept}\n"
        f"...（{label}过长已截断：共 {total} 字符，仅显示前 {MAX_STREAM_CHARS} 字符）"
    )


def _format_output(returncode: int, stdout: str, stderr: str) -> str:
    output = stdout.strip()
    err = stderr.strip()

    parts = [f"退出码：{returncode}"]
    if output:
        parts.append(f"标准输出：\n{_truncate(output, '标准输出')}")
    else:
        parts.append("标准输出：（空）")
    if err:
        parts.append(f"标准错误：\n{_truncate(err, '标准错误')}")
    else:
        parts.append("标准错误：（空）")

    return "\n".join(parts)


@register(
    "RunCli",
    description="调用本地已安装的任意命令行程序（CLI）。command 为程序名称，args 为参数列表。内部使用 shell=False 以列表方式安全执行，避免 Shell 注入。返回退出码、标准输出和标准错误。",
    properties={
        "command": {
            "type": "string",
            "description": "要执行的命令行程序名称或路径，例如 git、python、ls、curl.exe",
        },
        "args": {
            "type": "array",
            "items": {"type": "string"},
            "description": "传递给程序的参数列表，每个参数为字符串，例如 ['--version'] 或 ['status', '--short']",
        },
    },
    required=["command"],
)
def RunCli(command, args=None):
    if not command or not str(command).strip():
        return "【错误】命令不能为空"

    if args is None:
        args = []
    elif isinstance(args, str):
        args = [args]
    elif not isinstance(args, (list, tuple)):
        return "【错误】参数 args 必须是字符串列表"

    if any(a is None for a in args):
        return "【错误】参数 args 中不能包含 null"

    cmd = [str(command).strip()] + [str(a) for a in args]

    try:
        result = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        return f"【错误】未找到命令：{cmd[0]}，请确认该程序已安装并已加入 PATH"
    except PermissionError:
        return f"【错误】没有执行权限：{cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"【错误】命令执行超时（{TIMEOUT_SECONDS} 秒）：{' '.join(cmd)}"
    except OSError as e:
        return f"【错误】命令启动失败：{type(e).__name__} - {e}"
    except Exception as e:
        return f"【错误】命令执行失败：{type(e).__name__} - {e}"

    stdout = _decode(result.stdout)
    stderr = _decode(result.stderr)
    return _format_output(result.returncode, stdout, stderr)

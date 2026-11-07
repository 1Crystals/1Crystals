import configparser
import os

from openai import OpenAI

DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini")

# 集中式默认参数。优先读取 config.ini，缺失时回退到这里的默认值。
DEFAULTS = {
    "llm": {
        "api_key": "",
        "base_url": "https://api.siliconflow.cn/v1",
        "model_name": "deepseek-ai/DeepSeek-V3",
        "system_prompt": "你是一个极简的AI助手。",
        "context_window": "128000",
    },
    "context": {
        "window_size": "128000",
        "warn_ratio": "0.60",
        "summary_target": "5000",
        "archive_dir": ".agents/context",
    },
    "settings": {
        "session_dir": ".agents/sessions",
        "skills_dir": ".agents/skills",
        "root_dir": ".agents",
        "theme": "red",
        "mcp_connect_timeout": "20",
        "mcp_call_timeout": "120",
        "agents_file": "AGENTS.md",
    },
}


def get(cfg, section, key, default=None):
    """从配置读取参数，缺失或无法解析时回退默认值。"""
    if default is None:
        default = DEFAULTS.get(section, {}).get(key)
    try:
        if cfg.has_option(section, key):
            return cfg.get(section, key).strip()
    except Exception:
        pass
    return default


def getint(cfg, section, key, default=None):
    value = get(cfg, section, key, default)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        try:
            return int(float(default))
        except Exception:
            return 0


def getfloat(cfg, section, key, default=None):
    value = get(cfg, section, key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(default)
        except Exception:
            return 0.0


MOCK_CONFIG_TEXT = """\
[llm]
api_key = sk-your-api-key-here
base_url = https://api.siliconflow.cn/v1
model_name = deepseek-ai/DeepSeek-V3

[context]
# 是否手动指定上下文窗口大小。留空或删除本行则使用默认 128000，并在界面标注(默认)。
# window_size = 128000
warn_ratio = 0.60
summary_target = 5000
archive_dir = .agents/context

[settings]
# Agent 会话、技能与命令相关配置
theme = red
session_dir = .agents/sessions
skills_dir = .agents/skills
root_dir = .agents
mcp_connect_timeout = 20
mcp_call_timeout = 120
agents_file = AGENTS.md

[search]
# 可选：搜索模块的凭据
baidu_qianfan_api_key =
"""


class ConfigError(Exception):
    """配置相关错误的基类"""
    pass


class InvalidConfigError(ConfigError):
    """配置无效"""
    pass


def create_default_config(path=None):
    """在给定路径生成一份完整的 mock 配置文件（若存在则不覆盖）。返回是否真正创建。"""
    path = path or DEFAULT_CONFIG
    if os.path.isfile(path):
        return False
    try:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(MOCK_CONFIG_TEXT)
        return True
    except OSError:
        return False


def is_mock_config(cfg):
    """判断当前配置是否为自动生成的 mock 配置（api_key 仍是占位符）。"""
    key = get(cfg, "llm", "api_key", "")
    return (not key) or key == "sk-your-api-key-here"


def load_config(path=None, create_if_missing=True):
    """加载配置。若文件不存在且 create_if_missing 为真，则自动创建 mock 配置。"""
    config_path = path or DEFAULT_CONFIG

    if not os.path.exists(config_path):
        if not create_if_missing:
            raise ConfigError(f"配置文件不存在：{config_path}")
        create_default_config(config_path)

    cfg = configparser.ConfigParser()
    try:
        cfg.read(config_path, encoding="utf-8")
    except Exception as e:
        raise InvalidConfigError(
            f"配置文件读取失败：{type(e).__name__} - {e}\n"
            "请检查配置文件编码是否为 UTF-8，格式是否正确。"
        ) from e
    return cfg


def validate_llm_config(cfg):
    """验证 LLM 配置项是否完整有效。"""
    if not cfg.has_section("llm"):
        raise InvalidConfigError("配置文件中缺少 [llm] 小节")
    llm_section = cfg["llm"]
    required_fields = ["api_key", "base_url", "model_name"]
    missing_fields = []
    for field in required_fields:
        if field not in llm_section or not llm_section[field].strip():
            missing_fields.append(field)
    if missing_fields:
        raise InvalidConfigError(
            f"[llm] 小节缺少必需配置项：{', '.join(missing_fields)}"
        )


def create_client(cfg):
    """根据配置创建 OpenAI 客户端。"""
    return OpenAI(
        api_key=get(cfg, "llm", "api_key", "").strip(),
        base_url=get(cfg, "llm", "base_url", "").strip(),
    )

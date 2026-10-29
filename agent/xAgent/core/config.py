import configparser
import os

from openai import OpenAI

DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini")


class ConfigError(Exception):
    """配置相关错误的基类"""
    pass


class MissingConfigError(ConfigError):
    """配置文件缺失"""
    pass


class InvalidConfigError(ConfigError):
    """配置无效"""
    pass


def load_config(path=None):
    """
    加载配置文件，包含严格的错误校验
    
    Raises:
        MissingConfigError: 配置文件不存在
        InvalidConfigError: 配置文件格式错误或缺少必需配置
    """
    config_path = path or DEFAULT_CONFIG
    
    if not os.path.exists(config_path):
        raise MissingConfigError(
            f"配置文件不存在：{config_path}\n"
            "请确保配置文件存在，或参考示例创建 config.ini 文件。"
        )
    
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
    """
    验证 LLM 配置项是否完整有效
    
    Raises:
        InvalidConfigError: 配置无效或缺失
    """
    if "llm" not in cfg:
        raise InvalidConfigError(
            "配置文件中缺少 [llm] 小节\n"
            "请在 config.ini 中添加以下配置：\n"
            "[llm]\n"
            "api_key = your-api-key\n"
            "base_url = https://api.example.com/v1\n"
            "model_name = model-name"
        )
    
    llm_section = cfg["llm"]
    required_fields = ["api_key", "base_url", "model_name"]
    missing_fields = []
    
    for field in required_fields:
        if field not in llm_section:
            missing_fields.append(field)
        elif not llm_section[field].strip():
            missing_fields.append(f"{field}（值为空）")
    
    if missing_fields:
        raise InvalidConfigError(
            f"[llm] 小节缺少必需配置项：{', '.join(missing_fields)}\n"
            "请确保配置包含以下所有字段且不为空：\n"
            "  api_key\n"
            "  base_url\n"
            "  model_name"
        )


def create_client(cfg):
    """
    根据配置创建 OpenAI 客户端
    
    Args:
        cfg: 配置对象
        
    Returns:
        OpenAI: 客户端实例
        
    Raises:
        ConfigError: 配置无效
        Exception: 客户端创建失败
    """
    validate_llm_config(cfg)
    
    try:
        return OpenAI(
            api_key=cfg["llm"]["api_key"].strip(),
            base_url=cfg["llm"]["base_url"].strip(),
        )
    except Exception as e:
        raise ConfigError(
            f"创建 OpenAI 客户端失败：{type(e).__name__} - {e}\n"
            "请检查 api_key 和 base_url 是否正确。"
        ) from e

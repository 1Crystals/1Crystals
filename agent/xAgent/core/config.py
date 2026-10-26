import configparser
import os

from openai import OpenAI

DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.ini")


def load_config(path=None):
    cfg = configparser.ConfigParser()
    cfg.read(path or DEFAULT_CONFIG, encoding="utf-8")
    return cfg


def create_client(cfg):
    return OpenAI(
        api_key=cfg["llm"]["api_key"],
        base_url=cfg["llm"]["base_url"],
    )

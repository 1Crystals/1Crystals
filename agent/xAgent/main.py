import argparse
import os

from core import Agent, create_client, load_config
from core.config import get, getint
from core.mcp_client import mcp_manager
from tui import create_ui, ui_names


def _context_window(cfg):
    # 仅当用户显式配置 window_size 时才使用；否则返回 None（界面标注默认 128k）
    if cfg.has_option("context", "window_size"):
        return getint(cfg, "context", "window_size")
    return None


def build_agent():
    cfg = load_config()
    window = _context_window(cfg)
    mcp_manager.start_background(os.getcwd())
    return Agent(
        create_client(cfg),
        get(cfg, "llm", "model_name", ""),
        cfg=cfg,
        context_window=window,
    )


def main():
    parser = argparse.ArgumentParser(description="xAgent - 多界面 AI 助手")
    parser.add_argument("--ui", choices=ui_names(), default="tui", help="选择界面版本（默认 tui）")
    args = parser.parse_args()

    agent = build_agent()
    create_ui(args.ui, agent).run()


if __name__ == "__main__":
    main()

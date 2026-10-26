import argparse

from core import Agent, create_client, load_config
from tui import create_ui, ui_names


def build_agent() -> Agent:
    cfg = load_config()
    return Agent(create_client(cfg), cfg["llm"]["model_name"])


def main():
    parser = argparse.ArgumentParser(description="xAgent - 多界面 AI 助手")
    parser.add_argument("--ui", choices=ui_names(), default="tui", help="选择界面版本（默认 tui）")
    args = parser.parse_args()

    agent = build_agent()
    create_ui(args.ui, agent).run()


if __name__ == "__main__":
    main()

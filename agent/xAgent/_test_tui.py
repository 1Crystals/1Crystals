import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tui.app import TUIApp
from core import load_config, create_client
from core.agent import Agent
from core.mcp_client import mcp_manager


async def main():
    cfg = load_config()
    agent = Agent(create_client(cfg), cfg["llm"]["model_name"], cfg=cfg)
    mcp_manager.start_background(os.getcwd())
    app = TUIApp(agent)
    async with app.run_test(size=(160, 46)) as pilot:
        await asyncio.sleep(0.3)
        print("context-bar:", str(app.query_one("#context-bar").render()).strip())
        names = str(app.query_one("#tools-list").render())
        print("tools-list 含 recallContext:", "recallContext" in names)
        print("tools-list 含 getDate:", "getDate" in names)
        print("mcp-list 初值:", str(app.query_one("#mcp-list").render()).strip())
        await asyncio.sleep(30)
        print("mcp-list after load:", str(app.query_one("#mcp-list").render()).replace("\n", " | ")[:200])


asyncio.run(main())

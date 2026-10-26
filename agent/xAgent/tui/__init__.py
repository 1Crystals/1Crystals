from importlib import import_module

from .base import BaseUI

UI_REGISTRY = {
    "console": "tui.console:ConsoleUI",
    "tui": "tui.app:TUIApp",
    # 未来扩展示例：
    # "web": "web.ui:WebUI",
    # "desktop": "desktop.ui:DesktopUI",
}


def ui_names():
    return list(UI_REGISTRY)


def create_ui(name, agent) -> BaseUI:
    if name not in UI_REGISTRY:
        raise ValueError(f"未知界面 {name}，可选：{', '.join(UI_REGISTRY)}")
    module_path, cls_name = UI_REGISTRY[name].split(":")
    cls = getattr(import_module(module_path), cls_name)
    return cls(agent)

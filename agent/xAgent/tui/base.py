class BaseUI:
    """表现层统一接口：Console / TUI / Web / Desktop 都实现它。

    约定：
    - __init__(agent) 注入 core 层的 Agent 实例（依赖倒置，表现层不创建业务对象）
    - run() 启动界面主循环
    - 只消费 Agent.chat() 事件流，不直接访问 LLM / 工具
    """

    def __init__(self, agent=None):
        self.agent = agent

    def run(self):
        raise NotImplementedError

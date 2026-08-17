"""
Agent Router - Agent 选择与粘性路由
对应 Go 版的 internal/agent/router.go

核心职责:
  1. 根据 Session 绑定选择 Agent (粘性路由)
  2. 提供 Agent 注册表管理
  3. 支持动态切换 Agent
"""
from typing import Optional
from .executor import BaseExecutor, EchoExecutor, CodexExecutor
from .config import settings


class AgentRouter:
    """
    Agent 路由器
    维护 Agent 注册表，根据 Session 选择合适的 Executor
    """

    def __init__(self):
        self._executors: dict[str, BaseExecutor] = {}
        self._register_defaults()

    def _register_defaults(self):
        """注册默认的执行器"""
        self.register(EchoExecutor())
        self.register(CodexExecutor())
        print(f"[Router] Registered agents: {list(self._executors.keys())}")

    def register(self, executor: BaseExecutor):
        """注册一个执行器"""
        self._executors[executor.name] = executor

    def get(self, name: str) -> Optional[BaseExecutor]:
        """按名称获取执行器"""
        return self._executors.get(name)

    def list_agents(self) -> list[str]:
        """列出所有可用 Agent"""
        return list(self._executors.keys())

    def pick(
        self,
        session_agent: Optional[str] = None,
        requested_agent: Optional[str] = None
    ) -> BaseExecutor:
        """
        选择执行器 (核心路由逻辑)
        优先级:
          1. 用户显式指定 (requested_agent)
          2. Session 绑定的 Agent (session_agent) -> 粘性路由
          3. 默认 Agent (echo)
        """
        # 1. 用户显式指定了 Agent
        if requested_agent and requested_agent in self._executors:
            executor = self._executors[requested_agent]
            if session_agent and session_agent != requested_agent:
                print(f"[Router] Agent switch: {session_agent} -> {requested_agent}")
            return executor

        # 2. Session 绑定了 Agent (粘性路由)
        if session_agent and session_agent in self._executors:
            return self._executors[session_agent]

        # 3. 默认: 配置文件指定的 default_agent (兜底 echo)
        default_name = settings.default_agent or "echo"
        return self._executors.get(default_name, self._executors.get("echo", EchoExecutor()))


agent_router = AgentRouter()

"""
Executor Pool - Worker 内的执行器管理
管理 EchoExecutor / CodexExecutor 等实例, 维护活跃 Session 和并发计数
"""
import asyncio
import uuid
from datetime import datetime
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from doraemon.executor import BaseExecutor, EchoExecutor, CodexExecutor, ExecutorResult
from doraemon.config import settings
from .models import AgentCapability


class DrainState:
    """优雅下线状态管理"""
    def __init__(self):
        self._draining = False
        self._started_at: Optional[datetime] = None
        self._active_sessions: set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def is_draining(self) -> bool:
        return self._draining

    @property
    def active_turns(self) -> int:
        return len(self._active_sessions)

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at

    @property
    def active_turn_sessions(self) -> list[str]:
        return list(self._active_sessions)

    async def start_drain(self):
        """开始 Drain"""
        async with self._lock:
            if not self._draining:
                self._draining = True
                self._started_at = datetime.utcnow()
                print(f"[Worker] Drain started at {self._started_at}")

    async def add_session(self, session_id: str):
        """标记 Session 开始执行"""
        async with self._lock:
            self._active_sessions.add(session_id)

    async def remove_session(self, session_id: str):
        """标记 Session 执行完成"""
        async with self._lock:
            self._active_sessions.discard(session_id)

    def can_accept_new_work(self) -> bool:
        """是否能接收新工作"""
        return not self._draining


class ExecutorPool:
    """
    Worker 内的执行器池
    管理所有 Executor 实例, 调度执行, 控制并发
    """
    def __init__(self):
        self._executors: dict[str, BaseExecutor] = {}
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_turns)
        self.drain = DrainState()
        self._register_defaults()

    def _register_defaults(self):
        """注册默认执行器"""
        self._executors["echo"] = EchoExecutor()
        self._executors["codex"] = CodexExecutor()
        print(f"[Worker] Registered executors: {list(self._executors.keys())}")

    def get_agent_capabilities(self) -> list[AgentCapability]:
        """获取所有 Agent 能力声明 (用于 /health)"""
        capabilities = []
        for name, executor in self._executors.items():
            capabilities.append(AgentCapability(
                agent=name,
                name=name.capitalize(),
                installed=True
            ))
        return capabilities

    def get_executor(self, agent_name: str) -> Optional[BaseExecutor]:
        """获取指定 Agent 的执行器"""
        return self._executors.get(agent_name)

    async def execute(
        self,
        session_id: str,
        prompt: str,
        agent: str = "echo",
        history: list[dict] = None,
        context: dict = None
    ) -> ExecutorResult:
        """
        执行任务 (带并发控制 + Drain 检查)
        """
        # 1. 检查是否在 Drain 状态
        if not self.drain.can_accept_new_work():
            return ExecutorResult(
                exit_code=-1,
                error="worker_draining",
                output_text="[Worker] 正在优雅下线, 不接收新任务。请重试。"
            )

        # 2. 获取执行器
        executor = self.get_executor(agent)
        if not executor:
            return ExecutorResult(
                exit_code=-1,
                error=f"unknown_agent:{agent}",
                output_text=f"[Worker] 不支持的 Agent: {agent}"
            )

        # 3. 并发控制 (信号量)
        async with self._semaphore:
            await self.drain.add_session(session_id)
            try:
                result = await executor.execute(
                    session_id=session_id,
                    prompt=prompt,
                    context=context,
                    history=history
                )
                return result
            finally:
                await self.drain.remove_session(session_id)

    async def close_session(self, session_id: str):
        """关闭 Session"""
        for executor in self._executors.values():
            try:
                await executor.close_session(session_id)
            except Exception as e:
                print(f"[Worker] Error closing session {session_id}: {e}")

    @property
    def active_sessions_count(self) -> int:
        return self.drain.active_turns


# 全局单例
executor_pool = ExecutorPool()

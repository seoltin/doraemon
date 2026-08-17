"""
Executor 模块 - Agent 执行器抽象层
对应 Go 版的 internal/agent/agent.go + internal/codex/executor.go

核心设计:
  1. BaseExecutor - 统一接口契约 (支持多轮上下文 history)
  2. EchoExecutor - 调试用实现 (V0.2 默认, 纯回显 + 展示上下文)
  3. CodexExecutor - 预留接口 (V0.3 接入 codex exec)
"""
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Optional
import asyncio
import os
from pathlib import Path
from .config import settings


class ExecutorResult(BaseModel):
    """执行结果数据模型"""
    exit_code: int = 0
    output_text: str = ""
    session_token: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and self.error is None


class BaseExecutor(ABC):
    """
    Agent 执行器抽象接口
    对应 Go 版的 agent.Executor interface

    所有 Agent (Echo/Codex/Traex...) 都必须实现这个接口,
    业务层 (Handler) 只面向接口编程, 不关心具体是哪个 Agent.
    """
    name: str = "base"

    @abstractmethod
    async def execute(
        self,
        session_id: str,
        prompt: str,
        context: Optional[dict] = None,
        history: Optional[list[dict]] = None
    ) -> ExecutorResult:
        """
        执行一轮对话

        :param session_id: 会话ID (粘性路由 + 工作区隔离)
        :param prompt: 本轮用户输入
        :param context: 附加上下文 (chat_id/sender_id 等)
        :param history: 历史对话, 格式 [{"role": "user"/"assistant", "content": "..."}]
        """
        ...

    @abstractmethod
    async def close_session(self, session_id: str):
        """关闭会话, 清理资源"""
        ...

    async def precreate(self, session_id: str):
        """预创建会话 (可选实现)"""
        pass


class EchoExecutor(BaseExecutor):
    """
    Echo 执行器 - V0.2 调试用
    不调用任何外部 Agent, 纯回显, 同时把历史上下文展示出来,
    用于验证 Session 记忆 + 多轮对话链路是否打通.
    """
    name = "echo"

    def __init__(self):
        self.work_dir = Path(settings.agent_work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._active_sessions: set[str] = set()

    async def execute(
        self,
        session_id: str,
        prompt: str,
        context: Optional[dict] = None,
        history: Optional[list[dict]] = None
    ) -> ExecutorResult:
        if not prompt or len(prompt.strip()) == 0:
            return ExecutorResult(exit_code=0, output_text="(空消息, 未执行)")

        self._active_sessions.add(session_id)
        history = history or []

        lines = [
            "[Doraemon V0.2 - Echo]",
            f"✅ 收到指令: {prompt}",
            f"🔑 会话ID: {session_id}",
            f"💬 历史轮数: {len(history)}",
        ]

        if history:
            lines.append("━━━ 上下文 ━━━")
            for msg in history[-6:]:
                role = "我" if msg.get("role") == "user" else "Bot"
                content = msg.get("content", "")
                if len(content) > 80:
                    content = content[:80] + "..."
                lines.append(f"  [{role}] {content}")
            lines.append("━━━ ━━━━━━━ ━━━")

        lines.append("📦 我是 Echo 执行器, 现在只会回显.")
        lines.append("   等你装好 Codex, 我就会变聪明!")

        return ExecutorResult(
            exit_code=0,
            output_text="\n".join(lines)
        )

    async def close_session(self, session_id: str):
        self._active_sessions.discard(session_id)
        print(f"[EchoExecutor] Session closed: {session_id}")


class CodexExecutor(BaseExecutor):
    """
    Codex 执行器 - V0.3 真正接入
    V0.2 只留规范化骨架 (接口对齐 BaseExecutor, 能被 Router 注册),
    但 execute 直接返回 "尚未实现", 不实际调用 codex.

    V0.3 实现要点 (预留):
      - 正确调用: codex exec --cd <workdir> "prompt"
      - 把 history 拼成多轮 prompt 传入
      - 超长 prompt 走 stdin: echo prompt | codex exec -
      - 超时/异常处理复用 V0.1 成熟逻辑
    """
    name = "codex"

    def __init__(self):
        self.binary = settings.agent_binary
        self.work_dir = Path(settings.agent_work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

    async def execute(
        self,
        session_id: str,
        prompt: str,
        context: Optional[dict] = None,
        history: Optional[list[dict]] = None
    ) -> ExecutorResult:
        return ExecutorResult(
            exit_code=-1,
            error="CodexExecutor not implemented yet (V0.3)",
            output_text=(
                "[Codex] 执行器尚未实现, 将在 V0.3 接入.\n"
                f"会话: {session_id}\n"
                f"收到指令: {prompt}\n"
                f"历史轮数: {len(history or [])}\n"
                "当前可用: /model echo 切回 Echo 执行器."
            )
        )

    async def close_session(self, session_id: str):
        pass

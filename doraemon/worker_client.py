"""
Worker Client - Central 调用 Worker 的 HTTP 客户端
对应 Go 版 internal/agentworker/client.go
职责:
  1. 调用 Worker 的 /execute 接口
  2. 调用 Worker 的 /health, /session/close, /drain 接口
  3. 超时控制和错误重试
"""
import httpx
from typing import Optional
from .config import settings


class WorkerClientError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class WorkerClient:
    """Worker HTTP 客户端"""

    def __init__(self, endpoint: str, timeout: float = 600.0):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = httpx.Timeout(timeout, connect=5.0)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def execute(
        self,
        session_id: str,
        prompt: str,
        agent: str = "echo",
        message_id: str = "",
        chat_id: str = "",
        chat_type: str = "p2p",
        sender_id: str = "",
        history: list[dict] = None,
        work_dir: str = None
    ) -> dict:
        """
        调用 Worker 执行任务
        """
        client = await self._get_client()
        url = f"{self.endpoint}/execute"
        payload = {
            "session_id": session_id,
            "prompt": prompt,
            "agent": agent,
            "message_id": message_id,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "sender_id": sender_id,
            "history": history or [],
            "work_dir": work_dir or settings.agent_work_dir
        }

        try:
            resp = await client.post(url, json=payload)
            if resp.status_code == 503:
                # Worker Draining, 需要 Failover
                raise WorkerClientError(
                    f"Worker {self.endpoint} is draining",
                    retryable=True
                )
            if resp.status_code != 200:
                raise WorkerClientError(
                    f"Worker execute failed: HTTP {resp.status_code} - {resp.text[:200]}",
                    retryable=resp.status_code >= 500
                )
            return resp.json()
        except httpx.ConnectError as e:
            raise WorkerClientError(
                f"Cannot connect to worker {self.endpoint}: {e}",
                retryable=True
            )
        except httpx.TimeoutException as e:
            raise WorkerClientError(
                f"Worker {self.endpoint} timeout: {e}",
                retryable=False  # 超时不重试, 避免重复执行
            )

    async def health(self) -> dict:
        """健康检查"""
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.endpoint}/health", timeout=3.0)
            return resp.json()
        except Exception:
            return {"ok": False}

    async def close_session(self, session_id: str):
        """关闭 Session"""
        client = await self._get_client()
        try:
            await client.post(f"{self.endpoint}/session/close", json={"session_id": session_id})
        except Exception as e:
            print(f"[WorkerClient] Close session error: {e}")

    async def drain(self):
        """触发 Drain"""
        client = await self._get_client()
        try:
            await client.post(f"{self.endpoint}/drain/start")
        except Exception as e:
            print(f"[WorkerClient] Drain error: {e}")

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


class WorkerClientPool:
    """Worker 客户端池, 复用 client 实例"""

    def __init__(self):
        self._clients: dict[str, WorkerClient] = {}

    def get(self, endpoint: str) -> WorkerClient:
        if endpoint not in self._clients:
            self._clients[endpoint] = WorkerClient(endpoint)
        return self._clients[endpoint]

    async def close_all(self):
        for client in self._clients.values():
            await client.close()
        self._clients.clear()


# 全局客户端池
worker_client_pool = WorkerClientPool()

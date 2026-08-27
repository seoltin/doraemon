"""
Heartbeat - Worker 心跳发送器
Worker 启动后定期向 Central 发送心跳, 报告存活状态
"""
import asyncio
import httpx
from datetime import datetime
from typing import Optional
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from doraemon.config import settings
from .executor_pool import executor_pool
from .main import WORKER_ID


class HeartbeatSender:
    """心跳发送器"""

    def __init__(self, central_url: str, worker_id: str):
        self.central_url = central_url.rstrip("/")
        self.worker_id = worker_id
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._client: Optional[httpx.AsyncClient] = None
        self._registered = False

    async def _register(self):
        """启动时向 Central 注册"""
        if not self.central_url:
            print("[Heartbeat] No CENTRAL_URL configured, skipping registration")
            return False

        agents = [c.agent for c in executor_pool.get_agent_capabilities()]
        # 构造 Central 可访问的 endpoint: 0.0.0.0 是监听地址, 换成 127.0.0.1 用于本地通信
        advertise_host = settings.worker_host
        if advertise_host == "0.0.0.0":
            advertise_host = "127.0.0.1"
        endpoint = f"http://{advertise_host}:{settings.worker_port}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.central_url}/api/workers/register",
                    json={
                        "worker_id": self.worker_id,
                        "endpoint": endpoint,
                        "agents": agents,
                        "version": "0.3.0"
                    }
                )
                if resp.status_code == 200:
                    self._registered = True
                    print(f"[Heartbeat] Registered with Central: {self.central_url}")
                    return True
                else:
                    print(f"[Heartbeat] Registration failed: {resp.status_code} - {resp.text}")
                    return False
        except Exception as e:
            print(f"[Heartbeat] Registration error: {e}")
            return False

    async def _send_heartbeat(self):
        """发送单次心跳"""
        if not self.central_url:
            return

        try:
            status = "draining" if executor_pool.drain.is_draining else "running"
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{self.central_url}/api/workers/heartbeat",
                    json={
                        "worker_id": self.worker_id,
                        "status": status,
                        "active_turns": executor_pool.drain.active_turns,
                        "active_sessions": executor_pool.active_sessions_count
                    }
                )
        except Exception as e:
            # 心跳失败不致命, 下次重试
            print(f"[Heartbeat] Send failed: {e}")

    async def _heartbeat_loop(self):
        """心跳循环"""
        # 先注册
        await self._register()

        interval = settings.heartbeat_interval
        while self._running:
            await self._send_heartbeat()
            await asyncio.sleep(interval)

    def start(self):
        """启动心跳协程"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        print(f"[Heartbeat] Started, interval={settings.heartbeat_interval}s")

    async def stop(self):
        """停止心跳"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[Heartbeat] Stopped")


# 全局心跳实例
heartbeat_sender: Optional[HeartbeatSender] = None


def init_heartbeat(central_url: str, worker_id: str):
    """初始化心跳"""
    global heartbeat_sender
    heartbeat_sender = HeartbeatSender(central_url, worker_id)
    return heartbeat_sender

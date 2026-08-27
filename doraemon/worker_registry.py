"""
Worker Registry - Central 端 Worker 管理
对应 Go 版的 DistributedRouter 中的 store 接口
职责:
  1. Worker 注册/注销
  2. 心跳接收与超时检测
  3. 获取健康 Worker 列表
  4. Session-Worker 绑定管理
"""
import json
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from .models import WorkerRecord, WorkerSessionBinding
from .config import settings


class WorkerRegistry:
    """Worker 注册中心"""

    async def register(
        self,
        db: AsyncSession,
        worker_id: str,
        endpoint: str,
        agents: list[str] = None,
        version: str = "0.3.0"
    ) -> WorkerRecord:
        """Worker 启动时注册"""
        # 查是否已存在
        stmt = select(WorkerRecord).where(WorkerRecord.id == worker_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # 更新已存在的 Worker
            existing.endpoint = endpoint
            existing.status = "running"
            existing.version = version
            existing.agents = json.dumps(agents or [])
            existing.last_heartbeat_at = datetime.utcnow()
            await db.commit()
            await db.refresh(existing)
            print(f"[WorkerRegistry] Worker re-registered: {worker_id} @ {endpoint}")
            return existing

        # 新建 Worker
        record = WorkerRecord(
            id=worker_id,
            endpoint=endpoint,
            status="running",
            version=version,
            agents=json.dumps(agents or []),
            last_heartbeat_at=datetime.utcnow()
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        print(f"[WorkerRegistry] New worker registered: {worker_id} @ {endpoint}")
        return record

    async def heartbeat(
        self,
        db: AsyncSession,
        worker_id: str,
        status: str = "running",
        active_turns: int = 0,
        active_sessions: int = 0,
        error: str = ""
    ) -> bool:
        """接收 Worker 心跳"""
        stmt = select(WorkerRecord).where(WorkerRecord.id == worker_id)
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            return False

        record.last_heartbeat_at = datetime.utcnow()
        record.status = status
        record.active_turns = active_turns
        record.active_sessions = active_sessions
        if error:
            record.last_error = error
        await db.commit()
        return True

    async def get_healthy_workers(
        self,
        db: AsyncSession,
        agent_name: str = None
    ) -> list[WorkerRecord]:
        """获取所有健康的 Worker (心跳未超时)"""
        cutoff_time = datetime.utcnow() - timedelta(seconds=settings.worker_health_timeout)

        stmt = select(WorkerRecord).where(
            and_(
                WorkerRecord.status == "running",
                WorkerRecord.last_heartbeat_at > cutoff_time
            )
        )
        result = await db.execute(stmt)
        workers = result.scalars().all()

        if not agent_name:
            return list(workers)

        # 过滤支持指定 Agent 的 Worker
        filtered = []
        for w in workers:
            try:
                agents = json.loads(w.agents or "[]")
                if agent_name in agents:
                    filtered.append(w)
            except json.JSONDecodeError:
                pass
        return filtered

    async def get_worker(self, db: AsyncSession, worker_id: str) -> Optional[WorkerRecord]:
        """根据 ID 获取 Worker"""
        stmt = select(WorkerRecord).where(WorkerRecord.id == worker_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_workers(self, db: AsyncSession, include_unhealthy: bool = True) -> list[WorkerRecord]:
        """列出所有 Worker"""
        stmt = select(WorkerRecord).order_by(WorkerRecord.registered_at.desc())
        result = await db.execute(stmt)
        workers = list(result.scalars().all())

        if not include_unhealthy:
            cutoff_time = datetime.utcnow() - timedelta(seconds=settings.worker_health_timeout)
            workers = [w for w in workers if w.last_heartbeat_at and w.last_heartbeat_at > cutoff_time and w.status == "running"]
        return workers

    async def bind_session(
        self,
        db: AsyncSession,
        session_id: str,
        worker_id: str,
        worker_endpoint: str
    ):
        """绑定 Session 到 Worker (粘性路由)"""
        # 先删除旧绑定
        await db.execute(delete(WorkerSessionBinding).where(WorkerSessionBinding.session_id == session_id))
        await db.commit()

        # 创建新绑定
        binding = WorkerSessionBinding(
            session_id=session_id,
            worker_id=worker_id,
            worker_endpoint=worker_endpoint
        )
        db.add(binding)

        # 同时更新 Session 表的 worker_id/endpoint
        from .models import SessionRecord
        await db.execute(
            update(SessionRecord)
            .where(SessionRecord.id == session_id)
            .values(worker_id=worker_id, worker_endpoint=worker_endpoint)
        )
        await db.commit()
        print(f"[WorkerRegistry] Bound session {session_id} -> {worker_id} @ {worker_endpoint}")

    async def get_session_binding(
        self,
        db: AsyncSession,
        session_id: str
    ) -> Optional[WorkerSessionBinding]:
        """获取 Session 绑定的 Worker"""
        stmt = select(WorkerSessionBinding).where(WorkerSessionBinding.session_id == session_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def clear_session_binding(self, db: AsyncSession, session_id: str):
        """清除 Session-Worker 绑定 (Worker 挂掉时调用)"""
        await db.execute(delete(WorkerSessionBinding).where(WorkerSessionBinding.session_id == session_id))
        from .models import SessionRecord
        await db.execute(
            update(SessionRecord)
            .where(SessionRecord.id == session_id)
            .values(worker_id=None, worker_endpoint=None)
        )
        await db.commit()
        print(f"[WorkerRegistry] Cleared binding for session {session_id}")

    async def mark_worker_draining(self, db: AsyncSession, worker_id: str):
        """标记 Worker 为 draining 状态"""
        stmt = update(WorkerRecord).where(
            WorkerRecord.id == worker_id
        ).values(status="draining", updated_at=datetime.utcnow())
        await db.execute(stmt)
        await db.commit()
        print(f"[WorkerRegistry] Worker {worker_id} marked as draining")

    async def check_unhealthy_workers(self, db: AsyncSession) -> list[str]:
        """检查心跳超时的 Worker, 标记为 unhealthy, 返回超时的 Worker ID 列表"""
        cutoff_time = datetime.utcnow() - timedelta(seconds=settings.worker_health_timeout)

        stmt = select(WorkerRecord).where(
            and_(
                WorkerRecord.status == "running",
                WorkerRecord.last_heartbeat_at < cutoff_time
            )
        )
        result = await db.execute(stmt)
        unhealthy = result.scalars().all()

        unhealthy_ids = []
        for w in unhealthy:
            w.status = "unhealthy"
            w.last_error = f"Heartbeat timeout (no heartbeat for >{settings.worker_health_timeout}s)"
            unhealthy_ids.append(w.id)
            print(f"[WorkerRegistry] Worker {w.id} marked unhealthy (heartbeat timeout)")

        if unhealthy_ids:
            await db.commit()
        return unhealthy_ids


# 全局单例
worker_registry = WorkerRegistry()

"""
Doraemon V0.3 - Central 服务入口
对应 Go 版的 cmd/lark-coco/main.go

架构演进:
  V0.1: 单体 MVP
  V0.2: 分层架构 (Handler / Router / Executor / Session)
  V0.3: 分布式架构 (Central + Worker)
"""
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Optional
from .config import settings
from .db import init_db, get_db
from .handler import feishu_handler
from .router import agent_router
from .worker_registry import worker_registry
from .models import WorkerRecord


# ===== Pydantic 模型 =====

class WorkerRegisterRequest(BaseModel):
    worker_id: str
    endpoint: str
    agents: list[str] = []
    version: str = "0.3.0"

class WorkerHeartbeatRequest(BaseModel):
    worker_id: str
    status: str = "running"
    active_turns: int = 0
    active_sessions: int = 0
    error: str = ""


# ===== 健康检查后台任务 =====

_health_check_task: Optional[asyncio.Task] = None

async def _health_check_loop():
    """定期检查不健康的 Worker"""
    while True:
        try:
            async for db in get_db():
                await worker_registry.check_unhealthy_workers(db)
                break
        except Exception as e:
            print(f"[HealthCheck] Error: {e}")
        await asyncio.sleep(15)  # 每15秒检查一次


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _health_check_task

    print("\n" + "=" * 60)
    print("  🤖 哆啦A梦 (Doraemon) Central V0.3 启动中...")
    print("=" * 60)

    # 1. 初始化数据库
    await init_db()
    print(f"  📦 数据库: {settings.database_url}")

    # 2. 注册 Agent
    print(f"  🤖 内置 Agent: {agent_router.list_agents()}")
    print(f"  🚀 运行模式: {settings.worker_mode}")

    # 3. 启动健康检查后台任务
    _health_check_task = asyncio.create_task(_health_check_loop())
    print("  💓 Worker 健康检查已启动")

    print(f"  🌐 Central 服务地址: http://{settings.host}:{settings.port}")
    print("=" * 60 + "\n")
    yield

    # 关闭
    if _health_check_task:
        _health_check_task.cancel()
        try:
            await _health_check_task
        except asyncio.CancelledError:
            pass
    print("\n🔴 Doraemon Central V0.3 已关闭\n")


app = FastAPI(
    title="哆啦A梦 (Doraemon) Central",
    description="V0.3: 分布式架构 - Central 调度中心",
    version="0.3.0",
    lifespan=lifespan
)


# ===== 系统接口 =====

@app.get("/", tags=["System"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """健康检查"""
    try:
        result = await db.execute(text("SELECT 1"))
        db_status = "connected" if result else "unknown"
    except Exception as e:
        db_status = f"error: {e}"

    # 获取健康 Worker 数量
    healthy_workers = await worker_registry.get_healthy_workers(db)

    return {
        "status": "ok",
        "service": "哆啦A梦 Central",
        "version": "0.3.0",
        "mode": settings.worker_mode,
        "available_agents": agent_router.list_agents(),
        "healthy_workers": len(healthy_workers),
        "database": db_status
    }


@app.get("/api/agents", tags=["System"])
async def list_agents():
    """列出所有可用 Agent"""
    return {
        "agents": agent_router.list_agents(),
        "default": settings.default_agent
    }


@app.get("/api/status", tags=["System"])
async def system_status(db: AsyncSession = Depends(get_db)):
    """系统状态"""
    healthy_workers = await worker_registry.get_healthy_workers(db)
    return {
        "version": "0.3.0",
        "mode": settings.worker_mode,
        "features": {
            "session_memory": True,
            "agent_router": True,
            "slash_commands": True,
            "message_dedup": True,
            "distributed_workers": True
        },
        "healthy_workers": len(healthy_workers),
        "worker_ids": [w.id for w in healthy_workers]
    }


# ===== Worker 管理 API =====

@app.post("/api/workers/register", tags=["Workers"])
async def worker_register(req: WorkerRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Worker 启动时注册"""
    worker = await worker_registry.register(
        db,
        worker_id=req.worker_id,
        endpoint=req.endpoint,
        agents=req.agents,
        version=req.version
    )
    return {"ok": True, "worker_id": worker.id, "status": worker.status}


@app.post("/api/workers/heartbeat", tags=["Workers"])
async def worker_heartbeat(req: WorkerHeartbeatRequest, db: AsyncSession = Depends(get_db)):
    """Worker 心跳上报"""
    ok = await worker_registry.heartbeat(
        db,
        worker_id=req.worker_id,
        status=req.status,
        active_turns=req.active_turns,
        active_sessions=req.active_sessions,
        error=req.error
    )
    if not ok:
        return JSONResponse(status_code=404, content={"ok": False, "error": "worker not registered"})
    return {"ok": True}


@app.get("/api/workers", tags=["Workers"])
async def list_workers(
    include_unhealthy: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """列出所有 Worker"""
    workers = await worker_registry.list_workers(db, include_unhealthy=include_unhealthy)
    result = []
    for w in workers:
        result.append({
            "id": w.id,
            "endpoint": w.endpoint,
            "status": w.status,
            "version": w.version,
            "agents": json.loads(w.agents or "[]"),
            "active_turns": w.active_turns,
            "active_sessions": w.active_sessions,
            "last_error": w.last_error,
            "last_heartbeat_at": w.last_heartbeat_at.isoformat() if w.last_heartbeat_at else None,
            "registered_at": w.registered_at.isoformat()
        })
    return {"workers": result, "count": len(result)}


@app.post("/api/workers/{worker_id}/drain", tags=["Workers"])
async def drain_worker(worker_id: str, db: AsyncSession = Depends(get_db)):
    """标记 Worker 开始 Drain"""
    worker = await worker_registry.get_worker(db, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")
    await worker_registry.mark_worker_draining(db, worker_id)

    # TODO: Day3 实现后, 调用 Worker 的 /drain/start 接口
    return {"ok": True, "worker_id": worker_id, "draining": True}


# ===== 飞书 Webhook =====

@app.post("/webhook/event", tags=["Feishu"])
async def feishu_event_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    飞书事件回调 (核心入口)
    """
    try:
        raw_body = await request.body()
        data = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # URL 校验
    if data.get("type") == "url_verification":
        return await feishu_handler.handle_verification(data)

    # Token 校验
    header = data.get("header", {})
    if settings.verification_token:
        if header.get("token") != settings.verification_token:
            raise HTTPException(status_code=403, detail="Invalid Token")

    event_type = header.get("event_type", "")

    # 消息事件
    if event_type == "im.message.receive_v1":
        return await feishu_handler.handle_message(db, data)

    return {"code": 0, "msg": f"ignored: {event_type}"}


if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Starting Doraemon Central V0.3 on http://{settings.host}:{settings.port}")
    uvicorn.run(
        "doraemon.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )

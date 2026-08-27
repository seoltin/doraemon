"""
Doraemon Worker Service - V0.3
独立的执行节点, 接收 Central 分发的任务, 执行后返回结果
"""
import argparse
import hashlib
import socket
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn
import sys
import os

# 添加项目根目录到 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from doraemon.config import settings
from .models import (
    HealthResponse, DrainStatusResponse,
    ExecuteRequest, ExecuteResponse, SessionCloseRequest,
    AgentCapability
)
from .executor_pool import executor_pool


def generate_worker_id() -> str:
    """根据机器名和端口生成稳定的 WorkerID"""
    hostname = socket.gethostname()
    raw = f"{hostname}:{settings.worker_port}"
    hash_val = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"worker_{hash_val}"


WORKER_ID = generate_worker_id()
STARTED_AT = datetime.utcnow()
heartbeat_sender = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Worker 生命周期管理"""
    global heartbeat_sender

    print("\n" + "=" * 50)
    print(f"  🔧 Doraemon Worker 启动中...")
    print("=" * 50)
    print(f"  Worker ID: {WORKER_ID}")
    print(f"  监听地址: http://{settings.worker_host}:{settings.worker_port}")
    print(f"  最大并发: {settings.max_concurrent_turns}")
    print(f"  支持 Agent: {[c.agent for c in executor_pool.get_agent_capabilities()]}")
    if settings.central_url:
        print(f"  Central 地址: {settings.central_url}")
        from .heartbeat import init_heartbeat
        heartbeat_sender = init_heartbeat(settings.central_url, WORKER_ID)
        heartbeat_sender.start()
    else:
        print("  ⚠️  未配置 CENTRAL_URL, 以独立模式运行 (不会注册)")
    print("=" * 50 + "\n")
    yield

    # 关闭时停止心跳
    if heartbeat_sender:
        await heartbeat_sender.stop()
    print("\n🔴 Worker 已关闭\n")


app = FastAPI(
    title="Doraemon Worker",
    description="V0.3 - Agent 执行节点",
    version="0.3.0",
    lifespan=lifespan
)


@app.get("/health", tags=["System"])
async def health_check():
    """健康检查接口"""
    return HealthResponse(
        ok=not executor_pool.drain.is_draining,
        status="draining" if executor_pool.drain.is_draining else "running",
        worker_id=WORKER_ID,
        draining=executor_pool.drain.is_draining,
        active_turns=executor_pool.drain.active_turns,
        active_sessions=executor_pool.active_sessions_count,
        agents=executor_pool.get_agent_capabilities(),
        started_at=STARTED_AT
    )


@app.get("/", tags=["System"])
async def root():
    """根路径信息"""
    return {
        "service": "Doraemon Worker",
        "version": "0.3.0",
        "worker_id": WORKER_ID,
        "status": "running" if not executor_pool.drain.is_draining else "draining"
    }


@app.post("/execute", tags=["Execution"])
async def execute(req: ExecuteRequest):
    """执行任务接口"""
    if executor_pool.drain.is_draining:
        return JSONResponse(
            status_code=503,
            content=ExecuteResponse(
                status="rejected",
                exit_code=-1,
                error="worker_draining",
                retryable=True
            ).model_dump()
        )

    context = {
        "message_id": req.message_id,
        "chat_id": req.chat_id,
        "chat_type": req.chat_type,
        "sender_id": req.sender_id,
        "work_dir": req.work_dir or settings.agent_work_dir
    }

    result = await executor_pool.execute(
        session_id=req.session_id,
        prompt=req.prompt,
        agent=req.agent,
        history=req.history,
        context=context
    )

    return ExecuteResponse(
        status="completed" if result.is_success else "failed",
        exit_code=result.exit_code,
        output_text=result.output_text,
        error=result.error or "",
        retryable=not result.is_success and "timeout" in (result.error or "").lower()
    )


@app.post("/session/close", tags=["Execution"])
async def close_session(req: SessionCloseRequest):
    """关闭会话, 清理资源"""
    await executor_pool.close_session(req.session_id)
    return {"ok": True, "session_id": req.session_id}


@app.post("/drain/start", tags=["Management"])
async def start_drain():
    """开始优雅下线"""
    await executor_pool.drain.start_drain()
    return {
        "draining": True,
        "started_at": executor_pool.drain.started_at.isoformat()
    }


@app.get("/drain/status", tags=["Management"])
async def drain_status():
    """查询 Drain 状态"""
    return DrainStatusResponse(
        draining=executor_pool.drain.is_draining,
        started_at=executor_pool.drain.started_at,
        active_turns=executor_pool.drain.active_turns,
        active_turn_sessions=executor_pool.drain.active_turn_sessions
    )


def main():
    parser = argparse.ArgumentParser(description="Doraemon Worker")
    parser.add_argument("--port", type=int, default=settings.worker_port, help="监听端口")
    parser.add_argument("--host", type=str, default=settings.worker_host, help="监听地址")
    parser.add_argument("--central", type=str, default=settings.central_url, help="Central 地址")
    args = parser.parse_args()

    print(f"🚀 Starting Doraemon Worker on http://{args.host}:{args.port}")
    uvicorn.run(
        "worker.main:app",
        host=args.host,
        port=args.port,
        reload=False
    )


if __name__ == "__main__":
    main()

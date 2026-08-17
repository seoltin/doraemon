"""
Doraemon V0.2 - 服务入口
对应 Go 版的 cmd/lark-coco/main.go

架构演进:
  V0.1: 单体 MVP (main.py 混了所有逻辑)
  V0.2: 分层架构 (Handler / Router / Executor / Session)
"""
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from .config import settings
from .db import init_db, get_db
from .handler import feishu_handler
from .router import agent_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    print("\n" + "=" * 50)
    print("  🤖 哆啦A梦 (Doraemon) V0.2 启动中...")
    print("=" * 50)

    # 1. 初始化数据库
    await init_db()
    print(f"  📦 数据库: {settings.database_url}")

    # 2. 注册 Agent
    print(f"  🤖 可用 Agent: {agent_router.list_agents()}")

    print(f"  🌐 服务地址: http://{settings.host}:{settings.port}")
    print("=" * 50 + "\n")
    yield
    print("\n🔴 Doraemon V0.2 已关闭\n")


app = FastAPI(
    title="哆啦A梦 (Doraemon)",
    description="V0.2: 分层架构 + Session 记忆 + 指令系统",
    version="0.2.0",
    lifespan=lifespan
)


@app.get("/", tags=["System"])
async def health_check(db: AsyncSession = Depends(get_db)):
    """健康检查"""
    from sqlalchemy import text
    try:
        result = await db.execute(text("SELECT 1"))
        db_status = "connected" if result else "unknown"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok",
        "service": "哆啦A梦 (Doraemon)",
        "version": "0.2.0",
        "agent_binary": settings.agent_binary,
        "available_agents": agent_router.list_agents(),
        "database": db_status
    }


@app.get("/api/agents", tags=["System"])
async def list_agents():
    """列出所有可用 Agent"""
    return {
        "agents": agent_router.list_agents(),
        "default": "echo"
    }


@app.post("/webhook/event", tags=["Feishu"])
async def feishu_event_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    飞书事件回调 (核心入口)

    流程:
      1. 解析请求体
      2. URL 校验 -> 返回 challenge
      3. Token 校验 -> 防伪造
      4. 转发给 Handler 业务层处理
    """
    # 1. 解析
    try:
        raw_body = await request.body()
        data = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 2. URL 校验 (飞书后台配置时的验证)
    if data.get("type") == "url_verification":
        return await feishu_handler.handle_verification(data)

    # 3. Token 校验 (防伪造)
    header = data.get("header", {})
    if settings.verification_token:
        if header.get("token") != settings.verification_token:
            raise HTTPException(status_code=403, detail="Invalid Token")

    event_type = header.get("event_type", "")

    # 4. 消息事件 -> 业务处理
    if event_type == "im.message.receive_v1":
        return await feishu_handler.handle_message(db, data)

    # 其他事件 (入群/退群等) -> 忽略
    return {"code": 0, "msg": f"ignored: {event_type}"}


@app.get("/api/status", tags=["System"])
async def system_status():
    """系统状态"""
    return {
        "version": "0.2.0",
        "features": {
            "session_memory": True,
            "agent_router": True,
            "slash_commands": True,
            "message_dedup": True
        },
        "database_url": settings.database_url,
        "default_agent": "echo",
        "available_agents": agent_router.list_agents()
    }


if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Starting Doraemon V0.2 on http://{settings.host}:{settings.port}")
    uvicorn.run(
        "doraemon.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )

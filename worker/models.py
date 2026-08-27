"""
Worker 数据模型
对齐 Go 版 internal/agentworker/types.go
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AgentCapability(BaseModel):
    """Worker 支持的 Agent 能力"""
    agent: str
    name: str = ""
    installed: bool = True
    error: str = ""


class HealthResponse(BaseModel):
    """GET /health 响应"""
    ok: bool = True
    status: str = "running"
    worker_id: str
    draining: bool = False
    active_turns: int = 0
    active_sessions: int = 0
    agents: list[AgentCapability] = []
    started_at: datetime = Field(default_factory=datetime.utcnow)


class DrainStatusResponse(BaseModel):
    """GET /drain/status 响应"""
    draining: bool = False
    started_at: Optional[datetime] = None
    active_turns: int = 0
    active_turn_sessions: list[str] = []


class ExecuteRequest(BaseModel):
    """POST /execute 请求"""
    session_id: str
    prompt: str
    agent: str = "echo"
    message_id: str = ""
    chat_id: str = ""
    chat_type: str = "p2p"
    sender_id: str = ""
    history: list[dict] = []
    work_dir: Optional[str] = None


class ExecuteResponse(BaseModel):
    """POST /execute 响应"""
    status: str = "completed"  # completed/failed/rejected
    exit_code: int = 0
    output_text: str = ""
    error: str = ""
    retryable: bool = False


class SessionCloseRequest(BaseModel):
    """POST /session/close 请求"""
    session_id: str


class WorkerRegisterRequest(BaseModel):
    """Worker 向 Central 注册请求"""
    worker_id: str
    endpoint: str
    agents: list[str] = []
    version: str = "0.3.0"


class WorkerHeartbeatRequest(BaseModel):
    """Worker 心跳请求"""
    worker_id: str
    status: str = "running"
    active_turns: int = 0
    active_sessions: int = 0
    error: str = ""

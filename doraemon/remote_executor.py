"""
Remote Executor - 远程执行器适配器
实现 BaseExecutor 接口, 但实际通过 HTTP 调用 Worker 执行
"""
from typing import Optional
from .executor import BaseExecutor, ExecutorResult
from .worker_client import WorkerClient, WorkerClientError


class RemoteExecutor(BaseExecutor):
    """远程 Worker 执行器"""
    name = "remote"

    def __init__(self, worker_id: str, endpoint: str):
        self.worker_id = worker_id
        self.endpoint = endpoint
        self._client = WorkerClient(endpoint)

    async def execute(
        self,
        session_id: str,
        prompt: str,
        context: Optional[dict] = None,
        history: Optional[list[dict]] = None
    ) -> ExecutorResult:
        context = context or {}
        try:
            resp = await self._client.execute(
                session_id=session_id,
                prompt=prompt,
                agent=context.get("agent", "echo"),
                message_id=context.get("message_id", ""),
                chat_id=context.get("chat_id", ""),
                chat_type=context.get("chat_type", "p2p"),
                sender_id=context.get("sender_id", ""),
                history=history or [],
                work_dir=context.get("work_dir")
            )
            is_retryable = resp.get("retryable", False)
            is_success = resp.get("status") == "completed"
            return ExecutorResult(
                exit_code=resp.get("exit_code", 0),
                output_text=resp.get("output_text", ""),
                error=resp.get("error") or None,
                retryable=is_retryable or (not is_success and resp.get("error") and "timeout" not in (resp.get("error") or "").lower())
            )
        except WorkerClientError as e:
            return ExecutorResult(
                exit_code=-1,
                output_text=f"[Remote Worker Error] {str(e)}",
                error=str(e),
                retryable=e.retryable
            )

    async def close_session(self, session_id: str):
        await self._client.close_session(session_id)

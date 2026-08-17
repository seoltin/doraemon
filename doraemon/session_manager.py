"""
Session Manager - 会话管理器
对应 Go 版的 internal/session/manager.py
核心职责:
  1. 根据飞书消息的 chat_type 生成粘性 SessionID
  2. 管理 Session 的生命周期 (创建/重置/关闭)
  3. 持久化 Session 状态到 SQLite
"""
from typing import Optional
from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from .models import SessionRecord, MessageRecord
from .config import settings
from datetime import datetime

class SessionManager:
    def __init__(self):
        self._reset_counter: dict[str, int] = {}

    def _generate_session_id(self, chat_id: str, chat_type: str) -> str:
        """
        根据场景生成 SessionID (按场景分群策略)
        p2p:   sess_p2p_{open_id}_{count}
        group: sess_grp_{chat_id}_{count}
        thread: sess_thr_{thread_id}_{count}
        """
        prefix_map = {
            "p2p": "sess_p2p",
            "group": "sess_grp",
            "thread": "sess_thr"
        }
        prefix = prefix_map.get(chat_type, "sess_other")
        count = self._reset_counter.get(chat_id, 1)
        return f"{prefix}_{chat_id}_{count}"

    async def get_or_create_session(
        self,
        db: AsyncSession,
        chat_id: str,
        chat_type: str = "p2p",
        agent_name: Optional[str] = None
    ) -> SessionRecord:
        """
        获取或创建 Session (粘性路由)
        如果存在活跃的 Session，直接返回
        否则创建新的 (默认绑定 settings.default_agent)
        """
        if agent_name is None:
            agent_name = settings.default_agent or "echo"

        # 1. 查找活跃的 Session
        stmt = select(SessionRecord).where(
            and_(
                SessionRecord.chat_id == chat_id,
                SessionRecord.is_active == True
            )
        ).order_by(SessionRecord.created_at.desc()).limit(1)

        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # 存在活跃 Session，更新最后访问时间
            existing.updated_at = datetime.utcnow()
            await db.commit()
            return existing

        # 2. 创建新 Session
        session_id = self._generate_session_id(chat_id, chat_type)
        new_session = SessionRecord(
            id=session_id,
            chat_id=chat_id,
            chat_type=chat_type,
            agent_name=agent_name,
            is_active=True
        )
        db.add(new_session)
        await db.commit()
        await db.refresh(new_session)

        print(f"[Session] Created new session: {session_id} (chat={chat_id}, type={chat_type}, agent={agent_name})")
        return new_session

    async def reset_session(
        self,
        db: AsyncSession,
        chat_id: str,
        chat_type: str = "p2p"
    ) -> str:
        """
        重置 Session (/new 指令)
        不是删除旧记录，而是:
          1. 将旧 Session 标记为 inactive (保留审计痕迹)
          2. 找到数据库中最大的 count，生成新的不重复的 SessionID
        """
        # 1. 停用所有活跃的旧 Session
        stmt = update(SessionRecord).where(
            and_(
                SessionRecord.chat_id == chat_id,
                SessionRecord.is_active == True
            )
        ).values(is_active=False, reset_count=True, updated_at=datetime.utcnow())
        await db.execute(stmt)
        await db.commit()

        # 2. 找到数据库中已有的最大 count
        prefix_map = {"p2p": "sess_p2p", "group": "sess_grp", "thread": "sess_thr"}
        prefix = prefix_map.get(chat_type, "sess_other")
        like_pattern = f"{prefix}_{chat_id}_%"

        from sqlalchemy import func
        count_stmt = select(func.count()).where(
            SessionRecord.id.like(like_pattern)
        )
        result = await db.execute(count_stmt)
        existing_count = result.scalar() or 0

        # 3. 生成新的唯一 count (比已有的最大 count 大 1)
        new_count = existing_count + 1
        self._reset_counter[chat_id] = new_count

        # 4. 创建新 Session
        new_session = await self.get_or_create_session(db, chat_id, chat_type)
        print(f"[Session] Reset: {chat_id} -> new session {new_session.id}")
        return new_session.id

    async def close_session(
        self,
        db: AsyncSession,
        session_id: str
    ):
        """关闭 Session (标记为 inactive)"""
        stmt = update(SessionRecord).where(
            SessionRecord.id == session_id
        ).values(is_active=False, updated_at=datetime.utcnow())
        await db.execute(stmt)
        await db.commit()
        print(f"[Session] Closed: {session_id}")

    async def get_active_session(
        self,
        db: AsyncSession,
        chat_id: str
    ) -> Optional[SessionRecord]:
        """获取当前活跃的 Session"""
        stmt = select(SessionRecord).where(
            and_(
                SessionRecord.chat_id == chat_id,
                SessionRecord.is_active == True
            )
        ).order_by(SessionRecord.created_at.desc()).limit(1)

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def save_message(
        self,
        db: AsyncSession,
        message_id: str,
        session_id: str,
        sender_id: str,
        content: str,
        role: str = "user",
        message_type: str = "text",
        agent_name: str = "echo",
        status: str = "processing",
        reply_text: str = None
    ) -> Optional[MessageRecord]:
        """
        保存消息记录 (带防重: 已存在则跳过)
        role: user / assistant / system
        """
        stmt = select(MessageRecord).where(MessageRecord.id == message_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            print(f"[Session] Message already exists, skip: {message_id}")
            return None

        record = MessageRecord(
            id=message_id,
            session_id=session_id,
            sender_id=sender_id,
            role=role,
            content=content,
            message_type=message_type,
            agent_name=agent_name,
            status=status,
            reply_text=reply_text
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record

    async def get_history(
        self,
        db: AsyncSession,
        session_id: str,
        limit: int = 10
    ) -> list[dict]:
        """
        获取会话历史 (用于多轮上下文)
        返回 [{"role": "user"/"assistant", "content": "..."}, ...]
        按时间正序排列 (最早的在前), 只取最近 limit*2 条 (user+assistant 算一轮).
        """
        stmt = (
            select(MessageRecord)
            .where(
                MessageRecord.session_id == session_id,
                MessageRecord.status == "done"
            )
            .order_by(MessageRecord.created_at.desc())
            .limit(limit * 2)
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        # 反转成正序, 拼成 Executor 需要的格式
        history = []
        for r in reversed(records):
            if r.content:
                history.append({"role": r.role, "content": r.content})
        return history

    async def clear_session_messages(
        self,
        db: AsyncSession,
        session_id: str
    ) -> int:
        """清空指定会话的消息记录 (/reset 用), 返回删除条数"""
        stmt = delete(MessageRecord).where(MessageRecord.session_id == session_id)
        result = await db.execute(stmt)
        await db.commit()
        deleted = result.rowcount or 0
        print(f"[Session] Cleared {deleted} messages from {session_id}")
        return deleted

    async def update_message_result(
        self,
        db: AsyncSession,
        message_id: str,
        status: str,
        reply_text: str = None,
        error_message: str = None
    ):
        """更新消息处理结果"""
        stmt = update(MessageRecord).where(
            MessageRecord.id == message_id
        ).values(
            status=status,
            reply_text=reply_text,
            error_message=error_message,
            created_at=MessageRecord.created_at  # 保持原时间
        )
        await db.execute(stmt)
        await db.commit()

session_manager = SessionManager()

from sqlalchemy import Column, String, Text, DateTime, Boolean, Index
from sqlalchemy.sql import func
from .db import Base

class SessionRecord(Base):
    __tablename__ = "sessions"

    id = Column(String(128), primary_key=True, comment="SessionID, e.g. sess_p2p_xxx_1")
    chat_id = Column(String(128), nullable=False, index=True, comment="飞书 chat_id or user open_id")
    chat_type = Column(String(16), nullable=False, default="p2p", comment="p2p/group/thread")
    agent_name = Column(String(32), nullable=False, default="echo", comment="绑定的 Agent 名称")
    reset_count = Column(Boolean, default=False, comment="是否已重置")
    is_active = Column(Boolean, default=True, comment="是否活跃")
    last_message_text = Column(Text, nullable=True, comment="最后一条消息内容(摘要)")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_sessions_chat_active", "chat_id", "is_active"),
    )

class MessageRecord(Base):
    __tablename__ = "messages"

    id = Column(String(64), primary_key=True, comment="飞书 message_id")
    session_id = Column(String(128), nullable=False, index=True, comment="关联的 SessionID")
    sender_id = Column(String(128), nullable=False, index=True, comment="发送者 open_id")
    role = Column(String(16), nullable=False, default="user", comment="user/assistant/system")
    content = Column(Text, nullable=False, comment="消息内容")
    message_type = Column(String(32), nullable=False, default="text", comment="text/image/file...")
    agent_name = Column(String(32), nullable=False, default="echo", comment="处理的 Agent")
    status = Column(String(16), nullable=False, default="processing", comment="processing/done/error")
    reply_text = Column(Text, nullable=True, comment="Bot 回复内容")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_messages_session", "session_id", "created_at"),
        Index("ix_messages_sender", "sender_id", "created_at"),
    )

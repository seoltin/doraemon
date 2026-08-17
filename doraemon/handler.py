"""
Feishu Handler - 飞书消息业务处理层
对应 Go 版的 internal/feishu/handler.py

核心职责:
  1. 解析飞书 Webhook 消息
  2. 路由到对应业务逻辑 (指令/对话)
  3. 协调 SessionManager + AgentRouter + Executor
  4. 消息防重处理
"""
import json
import time
import uuid
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from .session_manager import session_manager
from .router import agent_router
from .executor import ExecutorResult
from .feishu_client import feishu_client


class FeishuHandler:
    """飞书消息处理器"""

    def __init__(self):
        # V0.2: 内存级防重 (单实例够用)
        self._pending_messages: set[str] = set()
        self._MAX_PENDING_SIZE = 10000

    async def handle_verification(self, data: dict) -> dict:
        """飞书 URL 校验 (必须原样返回 challenge)"""
        return {"challenge": data.get("challenge", "")}

    async def handle_message(
        self,
        db: AsyncSession,
        data: dict
    ) -> dict:
        """
        处理飞书消息事件 (核心业务入口)
        流程:
          1. 解析消息
          2. 防重检查
          3. 指令判断
          4. Session 管理
          5. Agent 执行
          6. 回复飞书
        """
        # ---- Step 1: 解析消息 ----
        try:
            event = data.get("event", {})
            message = event.get("message", {})
            sender = event.get("sender", {})

            message_id = message.get("message_id")
            message_type = message.get("message_type")
            chat_type = message.get("chat_type", "p2p")
            chat_id = message.get("chat_id", "")

            content = json.loads(message.get("content", "{}"))
            raw_text = content.get("text", "").strip()
            # 去除 @机器人 的前缀
            if raw_text.startswith("@"):
                raw_text = raw_text.split(" ", 1)[-1] if " " in raw_text else ""

            sender_id = sender.get("sender_id", {}).get("open_id", "unknown")

            print(f"\n{'='*40}")
            print(f"[Message] id={message_id} | type={message_type} | chat={chat_type}")
            print(f"[Message] chat_id={chat_id} | sender={sender_id}")
            print(f"[Message] text={raw_text}")
            print(f"{'='*40}")

        except Exception as e:
            print(f"[Handler] Parse message error: {e}")
            return {"code": 0}

        # ---- Step 2: 防重检查 ----
        if self._is_duplicate(message_id):
            print(f"[Handler] Duplicate message ignored: {message_id}")
            return {"code": 0, "msg": "duplicated"}

        try:
            self._mark_pending(message_id)

            # ---- Step 3: 非文本消息 -> 拒绝 ----
            if message_type != "text":
                await feishu_client.reply_text(
                    message_id,
                    f"[哆啦A梦 V0.2]\n抱歉，目前只支持文本消息哦。\n您发的类型: {message_type}"
                )
                return {"code": 0}

            # ---- Step 4: 指令判断 ----
            if raw_text.startswith("/"):
                return await self._handle_command(db, chat_id, chat_type, raw_text, message_id)

            # ---- Step 5: 普通对话 ----
            return await self._handle_chat(
                db, chat_id, chat_type, sender_id, raw_text, message_id
            )

        except Exception as e:
            print(f"[Handler] Error processing message {message_id}: {e}")
            # 出错时清除标记，允许重试
            self._unmark_pending(message_id)
            raise
        # 注意: 成功处理后不清除 _pending_messages，保留防重标记

    async def _handle_command(
        self,
        db: AsyncSession,
        chat_id: str,
        chat_type: str,
        text: str,
        message_id: str
    ) -> dict:
        """处理斜杠指令"""
        parts = text.strip().split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        print(f"[Command] command={command} args='{args}'")

        if command == "/new":
            # 开启全新会话 (归档旧 Session + 创建新 Session)
            new_session_id = await session_manager.reset_session(db, chat_id, chat_type)
            await feishu_client.reply_text(
                message_id,
                f"✅ 已开启新会话！\n会话ID: {new_session_id}\n之前的对话已归档，不会影响新对话。"
            )

        elif command == "/reset":
            # 重置当前会话 (清空当前 Session 的消息记录, 保留同一个 Session)
            session = await session_manager.get_active_session(db, chat_id)
            if session:
                deleted = await session_manager.clear_session_messages(db, session.id)
                await feishu_client.reply_text(
                    message_id,
                    f"🔄 已重置当前会话！\n会话ID: {session.id}\n清空了 {deleted} 条历史消息，上下文已归零。"
                )
            else:
                await feishu_client.reply_text(
                    message_id,
                    "当前没有活跃会话，发送任意消息即可自动创建。"
                )

        elif command == "/help":
            help_text = (
                "🤖 哆啦A梦 V0.2 指令帮助\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📌 会话管理:\n"
                "  /new          开启新会话 (归档旧对话)\n"
                "  /reset        清空当前会话记忆\n"
                "  /status       查看当前会话状态\n"
                "🤖 Agent 管理:\n"
                "  /agents       查看可用 Agent 列表\n"
                "  /model <名称> 切换 Agent (如 /model codex)\n"
                "🛠️ 调试:\n"
                "  /echo <文字>  让 Echo 执行器回显\n"
                "  /help         显示此帮助信息\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "💬 普通对话: 直接发消息即可，Bot 会自动记住上下文。"
            )
            await feishu_client.reply_text(message_id, help_text)

        elif command == "/status":
            # 查看当前 Session 状态
            session = await session_manager.get_active_session(db, chat_id)
            if session:
                status_text = (
                    f"📊 当前会话状态\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"  会话ID: {session.id}\n"
                    f"  场景类型: {session.chat_type}\n"
                    f"  绑定Agent: {session.agent_name}\n"
                    f"  活跃状态: {'✅ 活跃' if session.is_active else '❌ 已关闭'}\n"
                    f"  创建时间: {session.created_at}\n"
                    f"  更新时间: {session.updated_at}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━"
                )
            else:
                status_text = "📊 当前没有活跃会话，发送任意消息即可自动创建。"
            await feishu_client.reply_text(message_id, status_text)

        elif command == "/agents":
            agent_list = agent_router.list_agents()
            agents_text = "🤖 可用 Agent 列表:\n"
            for name in agent_list:
                agents_text += f"  • {name}\n"
            agents_text += "\n切换: /model <名称>"
            await feishu_client.reply_text(message_id, agents_text)

        elif command == "/model":
            # 切换当前会话绑定的 Agent (粘性路由)
            target_agent = args.strip().lower()
            available = agent_router.list_agents()
            if not target_agent:
                agents_str = "、".join(available)
                await feishu_client.reply_text(
                    message_id,
                    f"用法: /model <Agent名称>\n当前可用: {agents_str}"
                )
            elif target_agent not in available:
                agents_str = "、".join(available)
                await feishu_client.reply_text(
                    message_id,
                    f"❌ 未知 Agent: {target_agent}\n当前可用: {agents_str}"
                )
            else:
                session = await session_manager.get_active_session(db, chat_id)
                if not session:
                    await feishu_client.reply_text(
                        message_id,
                        "当前没有活跃会话，请先发一条消息创建会话后再切换 Agent。"
                    )
                else:
                    old_agent = session.agent_name
                    session.agent_name = target_agent
                    await db.commit()
                    await db.refresh(session)
                    await feishu_client.reply_text(
                        message_id,
                        f"🔀 Agent 已切换！\n{old_agent} → {target_agent}\n会话ID: {session.id}\n下一条消息起将使用 {target_agent} 处理。"
                    )

        elif command == "/echo":
            # 直接用 echo 执行
            if not args:
                await feishu_client.reply_text(message_id, "用法: /echo <要回显的文字>")
            else:
                result = await agent_router.get("echo").execute("direct_echo", args)
                await feishu_client.reply_text(message_id, result.output_text)

        else:
            await feishu_client.reply_text(
                message_id,
                f"❌ 未知指令: {command}\n输入 /help 查看所有可用指令。"
            )

        return {"code": 0}

    async def _handle_chat(
        self,
        db: AsyncSession,
        chat_id: str,
        chat_type: str,
        sender_id: str,
        text: str,
        message_id: str
    ) -> dict:
        """处理普通对话 (多轮上下文)"""
        # 1. 获取或创建 Session (粘性路由)
        session = await session_manager.get_or_create_session(db, chat_id, chat_type)
        print(f"[Chat] Session: {session.id} | Agent: {session.agent_name}")

        # 2. 保存用户消息 (status=processing, get_history 只查 done, 不会包含本条)
        await session_manager.save_message(
            db,
            message_id=message_id,
            session_id=session.id,
            sender_id=sender_id,
            content=text,
            role="user",
            message_type="text",
            agent_name=session.agent_name
        )

        # 3. 拉取历史对话 (同 session 最近 10 轮)
        history = await session_manager.get_history(db, session.id, limit=10)
        print(f"[Chat] History rounds: {len(history)}")

        # 4. 选择执行器 (粘性路由: Session 绑定哪个 Agent 就用哪个)
        executor = agent_router.pick(
            session_agent=session.agent_name
        )
        print(f"[Chat] Using executor: {executor.name}")

        # 5. 执行 (把历史上下文传给 Agent)
        result: ExecutorResult = await executor.execute(
            session_id=session.id,
            prompt=text,
            context={"chat_id": chat_id, "sender_id": sender_id},
            history=history
        )

        # 6. 回复飞书
        reply_text = result.output_text
        await feishu_client.reply_text(message_id, reply_text)

        # 7. 更新用户消息状态
        status = "done" if result.is_success else "error"
        await session_manager.update_message_result(
            db,
            message_id=message_id,
            status=status,
            reply_text=reply_text[:500],
            error_message=result.error
        )

        # 8. 保存 assistant 消息 (作为下一轮的上下文, content 存完整回复)
        asst_msg_id = f"asst_{session.id}_{uuid.uuid4().hex[:12]}"
        await session_manager.save_message(
            db,
            message_id=asst_msg_id,
            session_id=session.id,
            sender_id="bot",
            content=reply_text,
            role="assistant",
            message_type="text",
            agent_name=session.agent_name,
            status="done",
            reply_text=reply_text[:500]
        )

        # 9. 更新 Session 最后消息摘要
        session.last_message_text = text[:200]
        await db.commit()

        return {"code": 0}

    def _is_duplicate(self, message_id: str) -> bool:
        """检查消息是否重复"""
        return message_id in self._pending_messages

    def _mark_pending(self, message_id: str):
        """标记消息为处理中"""
        if len(self._pending_messages) > self._MAX_PENDING_SIZE:
            # 防内存泄漏: 清空一半
            self._pending_messages = set(list(self._pending_messages)[self._MAX_PENDING_SIZE // 2:])
        self._pending_messages.add(message_id)

    def _unmark_pending(self, message_id: str):
        """清除消息处理中标记"""
        self._pending_messages.discard(message_id)


feishu_handler = FeishuHandler()

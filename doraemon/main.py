import json
from fastapi import FastAPI, Request, HTTPException
from .config import settings
from .executor import agent_executor
from .feishu_client import feishu_client

app = FastAPI(
    title="Doraemon",
    description="Phase 1 MVP: Monolithic Agent Platform",
    version="0.1.0"
)

@app.get("/", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "service": "Doraemon MVP",
        "agent_binary": settings.agent_binary
    }

@app.post("/webhook/event", tags=["Feishu"])
async def feishu_event_webhook(request: Request):
    try:
        raw_body = await request.body()
        data = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge", "")}

    header = data.get("header", {})
    event_type = header.get("event_type", "")

    if settings.verification_token:
        if header.get("token") != settings.verification_token:
            raise HTTPException(status_code=403, detail="Invalid Token")

    if event_type != "im.message.receive_v1":
        return {"code": 0, "msg": "ignored"}

    try:
        event = data.get("event", {})
        message = event.get("message", {})
        sender = event.get("sender", {})

        message_id = message.get("message_id")
        message_type = message.get("message_type")
        chat_type = message.get("chat_type")

        content = json.loads(message.get("content", "{}"))
        raw_text = content.get("text", "").strip()

        sender_id = sender.get("sender_id", {}).get("open_id", "unknown")
        print(f"\n{'='*30}")
        print(f"[New Message] From: {sender_id} | Type: {message_type} | Chat: {chat_type}")
        print(f"Text: {raw_text}")
        print(f"{'='*30}")

    except Exception as e:
        print(f"[Webhook] Parse error: {e}")
        return {"code": 0}

    if message_type != "text":
        await feishu_client.reply_text(
            message_id,
            f"[Doraemon MVP]\nSorry, text messages only.\nYou sent: {message_type}"
        )
        return {"code": 0}

    agent_output = await agent_executor.run(raw_text)
    await feishu_client.reply_text(message_id, agent_output)

    return {"code": 0, "msg": "ok"}

if __name__ == "__main__":
    import uvicorn
    print(f"Starting Doraemon on http://{settings.host}:{settings.port}")
    uvicorn.run(
        "doraemon.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )

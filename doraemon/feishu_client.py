import json
import time
import httpx
from .config import settings

class FeishuClient:
    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self):
        self._token = None
        self._token_expire_ts = 0

    async def _get_tenant_token(self) -> str:
        now = time.time()
        if self._token and self._token_expire_ts > now:
            return self._token

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": settings.app_id,
            "app_secret": settings.app_secret
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=10)
            data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"[Feishu] Token failed: {data}")

        self._token = data["tenant_access_token"]
        self._token_expire_ts = now + data.get("expire", 7200) - 600
        return self._token

    async def reply_text(self, message_id: str, text: str):
        if not message_id:
            return

        try:
            token = await self._get_tenant_token()
            url = f"{self.BASE_URL}/im/v1/messages/{message_id}/reply"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8"
            }

            if len(text) > 3000:
                text = text[:3000] + "\n... (truncated)"

            content_obj = {"text": text}
            content_str = json.dumps(content_obj, ensure_ascii=False)

            payload = {
                "content": content_str,
                "msg_type": "text"
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, json=payload, timeout=10)
                data = resp.json()
                if data.get("code") != 0:
                    print(f"[Feishu] Reply failed: code={data.get('code')}, msg={data.get('msg')}")
                return data
        except Exception as e:
            print(f"[Feishu] Reply exception: {e}")
            print(f"[Feishu] Would reply to {message_id}: {text[:100]}...")

feishu_client = FeishuClient()

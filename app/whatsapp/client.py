from __future__ import annotations
import asyncio
import httpx
from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


class WhatsAppClient:
    def __init__(self):
        self.base_url = (
            f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
            f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )
        self.headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        self._send_lock = asyncio.Lock()
        self._last_send_ts: float = 0.0

    async def _rate_limited_post(self, payload: dict) -> dict:
        async with self._send_lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_send_ts
            if elapsed < 2.0:
                await asyncio.sleep(2.0 - elapsed)
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(self.base_url, headers=self.headers, json=payload)
                self._last_send_ts = asyncio.get_event_loop().time()
                if r.status_code >= 400:
                    logger.error(f"WhatsApp API error {r.status_code}: {r.text}")
                r.raise_for_status()
                return r.json()

    async def send_text(self, phone: str, message: str) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": message[:4096]},
        }
        logger.info(f"WA OUT [{phone}]: {message[:200]}")
        return await self._rate_limited_post(payload)

    async def send_interactive_buttons(
        self, phone: str, body: str, buttons: list[str]
    ) -> dict:
        if len(buttons) > 3:
            buttons = buttons[:3]
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body[:1024]},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": f"btn_{i}", "title": b[:20]},
                        }
                        for i, b in enumerate(buttons)
                    ]
                },
            },
        }
        logger.info(f"WA OUT BUTTONS [{phone}]: {body[:120]} | {buttons}")
        return await self._rate_limited_post(payload)

    async def send_template(
        self, phone: str, template_name: str, params: list[str], language: str = "es"
    ) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in params],
                    }
                ],
            },
        }
        return await self._rate_limited_post(payload)

    async def send_otp_template(
        self,
        phone: str,
        code: str,
        template_name: str = "verifty_download_otp",
        language: str = "es",
    ) -> dict:
        """Envía un OTP usando un template de categoría AUTHENTICATION.
        Requiere que el template esté aprobado por Meta y configurado con
        'Copy code' o 'Autofill'. El code va como parámetro del body y del botón.
        """
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": code}],
                    },
                    {
                        "type": "button",
                        "sub_type": "url",
                        "index": "0",
                        "parameters": [{"type": "text", "text": code}],
                    },
                ],
            },
        }
        logger.info(f"WA TEMPLATE OTP [{phone}] code=****")
        return await self._rate_limited_post(payload)

    async def mark_as_read(self, message_id: str) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(self.base_url, headers=self.headers, json=payload)
            return r.json()


whatsapp_client = WhatsAppClient()
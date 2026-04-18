from __future__ import annotations
import asyncio
from app.config import settings
from app.crm.client import crm
from app.whatsapp.client import whatsapp_client
from app.logger import get_logger

logger = get_logger(__name__)

REASON_LABELS = {
    "user_requested": "El lead pidió hablar con un asesor",
    "bot_confused": "El bot no pudo resolver la consulta",
    "price_inquiry": "Pregunta sobre precios específicos",
    "high_urgency": "Urgencia detectada",
}


class NotificationManager:
    async def notify_handoff(
        self,
        profile_id: str,
        conversation_id: str,
        lead_data: dict,
        reason: str = "user_requested",
    ) -> None:
        reason_label = REASON_LABELS.get(reason, reason)
        title = "Lead en espera — Verifty CRM"
        body = f"{lead_data.get('name', 'Lead')} de {lead_data.get('company', 'sin empresa')}"

        async def push():
            try:
                crm.insert_notification(
                    profile_id=profile_id,
                    notif_type="whatsapp_handoff",
                    title=title,
                    body=body,
                    metadata={
                        "conversation_id": conversation_id,
                        "phone": lead_data.get("phone"),
                        "reason": reason,
                    },
                )
            except Exception as e:
                logger.exception(f"Push notify failed: {e}")

        async def whatsapp_msg():
            profile = crm.get_profile(profile_id)
            if not profile or not profile.get("phone"):
                return
            msg = (
                f"🔔 *Lead en espera — Verifty CRM*\n\n"
                f"*Nombre:* {lead_data.get('name', 'Desconocido')}\n"
                f"*Empresa:* {lead_data.get('company', 'Sin empresa')}\n"
                f"*Razón:* {reason_label}\n\n"
                f"Responde desde el CRM: {settings.CRM_URL}/chat/{conversation_id}"
            )
            try:
                await whatsapp_client.send_text(profile["phone"], msg)
            except Exception as e:
                logger.exception(f"WA agent notify failed: {e}")

        await asyncio.gather(push(), whatsapp_msg())

    async def notify_new_qualified_lead(
        self, profile_ids: list[str], lead_id: str, score: int
    ) -> None:
        for pid in profile_ids:
            try:
                crm.insert_notification(
                    profile_id=pid,
                    notif_type="qualified_lead",
                    title=f"Nuevo lead calificado — Score {score}",
                    body=f"Lead {lead_id} alcanzó score {score}",
                    metadata={"lead_id": lead_id, "score": score},
                )
            except Exception as e:
                logger.exception(f"qualified notify failed: {e}")

    async def notify_inbound_during_handoff(
        self, profile_id: str, conversation_id: str, phone: str, body: str
    ) -> None:
        try:
            crm.insert_notification(
                profile_id=profile_id,
                notif_type="whatsapp_inbound",
                title="Nuevo mensaje del lead",
                body=body[:200],
                metadata={"conversation_id": conversation_id, "phone": phone},
            )
        except Exception as e:
            logger.exception(f"inbound notify failed: {e}")


notifier = NotificationManager()
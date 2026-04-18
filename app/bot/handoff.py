from __future__ import annotations
import random
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


class HandoffManager:
    async def initiate_handoff(self, conversation_id: str, reason: str) -> None:
        from app.notifications.notifier import notifier
        from app.chat.manager import assign_best_agent, get_available_agents
        from datetime import datetime, timezone

        conv = crm.get_conversation(conversation_id)
        if not conv:
            logger.error(f"Handoff: conversation {conversation_id} missing")
            return

        if conv.get("status") in {"human_handoff", "human_active"}:
            logger.info(f"Conversation {conversation_id} already in handoff")
            return

        # Smart routing: asignar al agente con menor carga que esté online
        best = assign_best_agent(conversation_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        update = {
            "status": "human_handoff",
            "chat_status": "waiting_agent",
            "handoff_reason": reason,
            "escalated_at": now_iso,
            "last_message_at": now_iso,
        }
        if best:
            update["assigned_profile_id"] = best["profile_id"]
            # Si hay agentes online, iniciar el timer del lost
            update["waiting_with_agents_since"] = now_iso
        else:
            # Sin agentes online — no timer, se asigna al routing por defecto
            routing = crm.get_active_routing_config()
            if routing:
                members = crm.get_routing_members(routing["id"])
                if members:
                    update["assigned_profile_id"] = members[0]["profile_id"]

        crm.update_conversation(conversation_id, update)
        agent_profile_id = update.get("assigned_profile_id")

        # Notificar a los targets
        if agent_profile_id:
            notify_targets = [agent_profile_id]
        else:
            routing = crm.get_active_routing_config()
            members = crm.get_routing_members(routing["id"]) if routing else []
            notify_targets = [m["profile_id"] for m in members]

        lead_id = conv.get("lead_id")
        if lead_id:
            crm.create_activity(
                lead_id=lead_id,
                activity_type="whatsapp_message",
                title=f"Escalada a humano: {REASON_LABELS.get(reason, reason)}",
                body=f"Conversación {conversation_id} asignada a {agent_profile_id}",
            )

        lead_data = (conv.get("context") or {}).get("lead_data", {})
        if lead_id and not lead_data:
            lead_row = crm.get_lead(lead_id)
            if lead_row:
                lead_data = {
                    "name": lead_row.get("name"),
                    "company": lead_row.get("company_name"),
                    "phone": lead_row.get("phone"),
                }

        for target_pid in notify_targets:
            await notifier.notify_handoff(
                profile_id=target_pid,
                conversation_id=conversation_id,
                lead_data=lead_data,
                reason=reason,
            )

        await whatsapp_client.send_text(
            conv["phone"],
            "Un momento, te conectamos con un asesor del equipo. "
            "Estará contigo en breve 👋",
        )
        crm.save_message(
            conversation_id,
            "outbound",
            "Un momento, te conectamos con un asesor del equipo.",
        )


handoff_manager = HandoffManager()
"""Gestión del ciclo de vida de chats: close, reopen, initiate, routing."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.crm.client import crm
from app.whatsapp.client import whatsapp_client
from app.outbound.manager import start_outbound_conversation
from app.chat.survey import send_satisfaction_survey
from app.logger import get_logger

logger = get_logger(__name__)

LOST_TIMEOUT_MINUTES = 60  # marcar como perdido después de 60 min con agentes online


# ─────────────────────── Smart Routing ───────────────────────

def get_available_agents() -> list[dict]:
    """Retorna agentes online, dentro de su horario, ordenados por menor carga."""
    now = datetime.now(timezone.utc)
    routing = crm.get_active_routing_config()
    if not routing:
        return []
    members = crm.get_routing_members(routing["id"])
    if not members:
        return []

    available: list[dict] = []
    for m in members:
        prof = m.get("profile") or {}
        if not prof.get("is_online", False):
            continue
        # Check scheduling window (simple: compare current hour vs window)
        # TODO: timezone-aware check
        available.append({
            "profile_id": prof["id"],
            "full_name": prof.get("full_name"),
            "email": prof.get("email"),
            "active_chat_count": prof.get("active_chat_count", 0),
        })

    # Ordenar por menor carga
    available.sort(key=lambda a: a["active_chat_count"])
    return available


def assign_best_agent(conversation_id: str) -> Optional[dict]:
    """Asigna el agente disponible con menos chats activos."""
    agents = get_available_agents()
    if not agents:
        return None
    best = agents[0]
    crm.update_conversation(conversation_id, {
        "assigned_profile_id": best["profile_id"],
    })
    # Incrementar active_chat_count
    try:
        crm.sb.table("profiles").update({
            "active_chat_count": best["active_chat_count"] + 1,
        }).eq("id", best["profile_id"]).execute()
    except Exception as e:
        logger.warning(f"increment chat count: {e}")
    return best


# ─────────────────────── Close ───────────────────────

async def close_conversation(
    conversation_id: str,
    closed_by: str,
    reason: str = "resolved",
    send_survey: bool = True,
) -> dict:
    """Cierra un chat y opcionalmente envía encuesta de satisfacción."""
    conv = crm.get_conversation(conversation_id)
    if not conv:
        raise ValueError(f"Conversation {conversation_id} not found")

    now = datetime.now(timezone.utc).isoformat()
    update: dict = {
        "chat_status": "agent_closed",
        "closed_at": now,
        "close_reason": reason,
        "status": "completed",
    }
    crm.update_conversation(conversation_id, update)

    # Decrementar active_chat_count del agente asignado
    agent_id = conv.get("assigned_profile_id")
    if agent_id:
        _decrement_chat_count(agent_id)

    # Log activity
    lead_id = conv.get("lead_id")
    if lead_id:
        try:
            crm.create_activity(
                lead_id=lead_id,
                activity_type="note",
                title=f"Chat cerrado: {reason}",
                body=f"Cerrado por {closed_by}",
            )
        except Exception:
            pass

    # Encuesta de satisfacción (async, no bloquea)
    survey_sent = False
    if send_survey:
        survey_sent = await send_satisfaction_survey(
            conversation_id=conversation_id,
            phone=conv["phone"],
        )

    return {
        "status": "closed",
        "reason": reason,
        "survey_sent": survey_sent,
    }


# ─────────────────────── Reopen ───────────────────────

async def reopen_conversation(
    conversation_id: str,
    agent_profile_id: str,
    template_name: Optional[str] = None,
) -> dict:
    """Reabre una conversación cerrada o perdida enviando un template."""
    conv = crm.get_conversation(conversation_id)
    if not conv:
        raise ValueError(f"Conversation {conversation_id} not found")

    phone = conv["phone"]
    template = template_name or settings.OUTBOUND_LEAD_TEMPLATE
    lead_data = (conv.get("context") or {}).get("lead_data") or {}
    first_name = (lead_data.get("name") or conv.get("wa_contact_name") or "").split(" ")[0] or "hola"

    # Enviar template (fuera de ventana 24h)
    try:
        await whatsapp_client.send_template(
            phone=phone,
            template_name=template,
            params=[first_name],
        )
    except Exception as e:
        logger.exception(f"reopen template failed: {e}")
        raise

    now = datetime.now(timezone.utc).isoformat()
    crm.update_conversation(conversation_id, {
        "chat_status": "agent_active",
        "status": "human_active",
        "assigned_profile_id": agent_profile_id,
        "reopened_at": now,
        "lost_at": None,
        "closed_at": None,
        "last_message_at": now,
    })

    crm.save_message(
        conversation_id=conversation_id,
        direction="outbound",
        body=f"[chat reabierto con template {template}]",
    )

    # Incrementar chat count del agente
    try:
        prof = crm.get_profile(agent_profile_id)
        if prof:
            crm.sb.table("profiles").update({
                "active_chat_count": (prof.get("active_chat_count") or 0) + 1,
            }).eq("id", agent_profile_id).execute()
    except Exception:
        pass

    return {"status": "reopened", "template_sent": template}


# ─────────────────────── Initiate from lead/contact ───────────────────────

async def initiate_chat(
    lead_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    agent_profile_id: Optional[str] = None,
    template_name: Optional[str] = None,
) -> dict:
    """Abre un chat nuevo para un lead o contacto que no tiene historial WA."""
    phone = None
    name = None

    if lead_id:
        lead = crm.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")
        phone = lead.get("phone")
        name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
    elif contact_id:
        try:
            r = crm.sb.table("contacts").select("*").eq("id", contact_id).limit(1).execute()
            contact = r.data[0] if r.data else None
        except Exception:
            contact = None
        if not contact:
            raise ValueError(f"Contact {contact_id} not found")
        phone = contact.get("phone")
        name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
    else:
        raise ValueError("lead_id or contact_id required")

    if not phone:
        raise ValueError("No phone number found for this lead/contact")

    # Obtener nombre del agente para el template
    agent_name = "nuestro equipo"
    if agent_profile_id:
        agent_prof = crm.get_profile(agent_profile_id)
        if agent_prof:
            agent_name = agent_prof.get("full_name") or agent_name

    template = template_name or "verifty_agent_outreach"
    lead_data = {"name": name, "phone": phone}

    conv_id = await start_outbound_conversation(
        phone=phone,
        lead_data=lead_data,
        source_form="crm_initiated",
        template_name=template,
        template_params=[agent_name],
    )
    if not conv_id:
        raise RuntimeError("Could not send WhatsApp template")

    update = {
        "chat_status": "agent_active",
        "status": "human_active",
    }
    if agent_profile_id:
        update["assigned_profile_id"] = agent_profile_id

    crm.update_conversation(conv_id, update)

    return {
        "status": "initiated",
        "conversation_id": conv_id,
        "template_sent": template,
    }


# ─────────────────────── Lost check (scheduler) ───────────────────────

def check_and_mark_lost() -> int:
    """Marca conversaciones como 'lost' si llevan 60+ min en waiting_agent
    con agentes disponibles. Llamado por el scheduler cada 60s.
    Retorna la cantidad de conversaciones marcadas.
    """
    agents_available = len(get_available_agents()) > 0
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Obtener convos en waiting_agent
    try:
        r = crm.sb.table("whatsapp_conversations").select(
            "id, escalated_at, waiting_with_agents_since"
        ).eq("chat_status", "waiting_agent").execute()
    except Exception as e:
        logger.warning(f"check_lost query: {e}")
        return 0

    rows = r.data or []
    if not rows:
        return 0

    marked = 0
    for row in rows:
        conv_id = row["id"]
        waiting_since = row.get("waiting_with_agents_since")

        if agents_available:
            # Si no teníamos timer, iniciarlo
            if not waiting_since:
                try:
                    crm.sb.table("whatsapp_conversations").update({
                        "waiting_with_agents_since": now_iso,
                    }).eq("id", conv_id).execute()
                except Exception:
                    pass
                continue

            # Timer corriendo — verificar si pasaron 60 min
            try:
                ws_dt = datetime.fromisoformat(
                    str(waiting_since).replace("Z", "+00:00")
                )
            except Exception:
                continue

            elapsed_min = (now - ws_dt).total_seconds() / 60
            if elapsed_min >= LOST_TIMEOUT_MINUTES:
                try:
                    crm.sb.table("whatsapp_conversations").update({
                        "chat_status": "lost",
                        "lost_at": now_iso,
                        "waiting_with_agents_since": None,
                    }).eq("id", conv_id).execute()
                    logger.info(
                        f"[lost] conv={conv_id} waited {elapsed_min:.0f}min"
                    )
                    marked += 1
                except Exception as e:
                    logger.warning(f"mark lost: {e}")
        else:
            # No hay agentes disponibles — resetear timer
            if waiting_since:
                try:
                    crm.sb.table("whatsapp_conversations").update({
                        "waiting_with_agents_since": None,
                    }).eq("id", conv_id).execute()
                except Exception:
                    pass

    return marked


# ─────────────────────── Helper ───────────────────────

def _decrement_chat_count(profile_id: str) -> None:
    try:
        prof = crm.get_profile(profile_id)
        if prof:
            count = max((prof.get("active_chat_count") or 0) - 1, 0)
            crm.sb.table("profiles").update({
                "active_chat_count": count,
            }).eq("id", profile_id).execute()
    except Exception as e:
        logger.warning(f"decrement chat count: {e}")

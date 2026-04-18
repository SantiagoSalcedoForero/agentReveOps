"""Conversaciones outbound (bot escribe primero) via templates de WhatsApp.
Usado cuando un lead llena un form de verifty.com que no es descarga de plantilla.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.config import settings
from app.crm.client import crm
from app.whatsapp.client import whatsapp_client
from app.logger import get_logger

logger = get_logger(__name__)

# Mapping de template_name → cuerpo plano aproximado, para guardar como mensaje
# del bot en whatsapp_messages. MANTENER SINCRONIZADO con lo aprobado en Meta.
# Usa {name} como placeholder para el primer parámetro.
TEMPLATE_BODIES: dict[str, str] = {
    "verifty_outbound_lead": (
        "Hola {name}, soy el asistente de Verifty. Recibimos tu contacto "
        "desde nuestra web. Somos expertos en automatización de seguridad "
        "industrial. ¿Cuál es el mayor dolor de tu operación SST hoy?"
    ),
    "verifty_demo_nudge": (
        "Hola {name}, vi que querías agendar una demo de Verifty pero no "
        "alcanzaste a elegir horario. Te puedo ayudar desde aquí — cuéntame "
        "sobre tu operación y te agendo de una."
    ),
}


def _template_body(name: str, first_name: str) -> str:
    tpl = TEMPLATE_BODIES.get(name, f"[outbound template {name}]")
    return tpl.format(name=first_name or "hola")


async def start_outbound_conversation(
    phone: str,
    lead_data: dict,
    source_form: str,
    template_name: str,
    template_params: list[str],
    context_extra: Optional[dict] = None,
) -> Optional[str]:
    """Envía un template de WhatsApp y deja la conversación lista para cuando
    el lead responda. Retorna conversation_id o None si falló.
    """
    first_name = template_params[0] if template_params else "hola"
    # 1) Enviar template
    try:
        await whatsapp_client.send_template(
            phone=phone,
            template_name=template_name,
            params=template_params,
        )
    except Exception as e:
        logger.exception(f"send_template {template_name} to {phone} failed: {e}")
        return None

    # 2) Crear/obtener conversación
    conv = crm.get_or_create_conversation(
        phone=phone,
        wa_name=lead_data.get("name"),
    )
    conv_id = conv["id"]

    # 3) Actualizar contexto (lead_data + origen outbound)
    ctx = conv.get("context") or {}
    ctx.setdefault("lead_data", {})
    ctx["lead_data"].update({k: v for k, v in lead_data.items() if v is not None})
    ctx["outbound_origin"] = {
        "source_form": source_form,
        "template": template_name,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
    if context_extra:
        ctx.update(context_extra)

    try:
        crm.update_conversation(
            conv_id,
            {"context": ctx, "status": "outbound_sent"},
        )
    except Exception as e:
        logger.warning(f"update conv post-outbound: {e}")

    # 4) Guardar mensaje como outbound (con el texto aproximado)
    try:
        body = _template_body(template_name, first_name)
        crm.save_message(
            conversation_id=conv_id,
            direction="outbound",
            body=body,
        )
    except Exception as e:
        logger.warning(f"save outbound template msg: {e}")

    # 5) Marcar lead
    lead_id = conv.get("lead_id")
    if lead_id:
        field = (
            "nudge_sent_at"
            if source_form == "demo_no_show"
            else "outbound_sent_at"
        )
        try:
            crm.update_lead(
                lead_id,
                {field: datetime.now(timezone.utc).isoformat()},
            )
        except Exception as e:
            logger.warning(f"update lead {field}: {e}")

    return conv_id


def schedule_nudge(
    phone: str,
    lead_id: Optional[str],
    kind: str,
    due_in_minutes: int,
    payload: Optional[dict] = None,
) -> Optional[str]:
    """Crea un pending_nudge que se ejecutará a los due_in_minutes."""
    due_at = datetime.now(timezone.utc) + timedelta(minutes=due_in_minutes)
    row = {
        "phone": phone,
        "lead_id": lead_id,
        "kind": kind,
        "due_at": due_at.isoformat(),
        "payload": payload or {},
    }
    try:
        r = crm.sb.table("pending_nudges").insert(row).execute()
        if r.data:
            logger.info(
                f"Nudge scheduled id={r.data[0]['id']} kind={kind} "
                f"phone={phone} due_at={due_at}"
            )
            return r.data[0]["id"]
    except Exception as e:
        logger.exception(f"schedule_nudge failed: {e}")
    return None


def cancel_pending_nudges_for_lead(lead_id: str, kind: Optional[str] = None) -> int:
    """Cancela nudges pendientes del lead (ej. cuando agendó la demo)."""
    if not lead_id:
        return 0
    try:
        q = crm.sb.table("pending_nudges").update(
            {"status": "cancelled"}
        ).eq("lead_id", lead_id).eq("status", "pending")
        if kind:
            q = q.eq("kind", kind)
        r = q.execute()
        count = len(r.data or [])
        if count:
            logger.info(f"Cancelled {count} pending nudge(s) for lead {lead_id}")
        return count
    except Exception as e:
        logger.warning(f"cancel nudges: {e}")
        return 0

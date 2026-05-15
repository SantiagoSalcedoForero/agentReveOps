"""Seguimientos automáticos post-descarga de plantilla.

Lógica:
  - Seguimiento 1: 24h después del primer mensaje
  - Seguimiento 2: 48h después del seguimiento 1
  - Seguimiento 3: 72h después del seguimiento 2  (cierre definitivo)
  - Se detiene si el lead responde en cualquier momento.

El job corre cada 30 minutos desde main.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from anthropic import Anthropic

from app.config import settings
from app.crm.client import crm
from app.whatsapp.client import whatsapp_client
from app.logger import get_logger

logger = get_logger(__name__)

# Horas de espera entre seguimientos
FOLLOWUP_DELAYS_HOURS = [24, 48, 72]

_anthropic: Optional[Anthropic] = None


def _get_client() -> Anthropic:
    global _anthropic
    if _anthropic is None:
        _anthropic = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _anthropic


# ─── Detección de producto ────────────────────────────────────────────────────

def _is_flow_lead(context: dict) -> bool:
    """True si el lead encaja mejor con Verifty Flow (empresa grande / muchos contratistas)."""
    ld = context.get("lead_data") or {}
    try:
        employees = int(str(ld.get("employee_count") or 0))
    except (ValueError, TypeError):
        employees = 0
    if employees >= 130:
        return True
    if ld.get("has_contractors"):
        return True
    sector = str(ld.get("sector") or ld.get("industry") or "").lower()
    if any(s in sector for s in ("construcción", "construccion", "petróleo", "petroleo", "minería", "mineria")):
        if employees >= 50:
            return True
    return False


def _recommended_plan(context: dict) -> str:
    """Retorna el nombre del plan SST recomendado según empleados."""
    ld = context.get("lead_data") or {}
    try:
        n = int(str(ld.get("employee_count") or 0))
    except (ValueError, TypeError):
        n = 0
    if n <= 4:
        return "Basic ($39.000/mes)"
    if n <= 7:
        return "Starter ($220.000/mes)"
    if n <= 30:
        return "Pro ($600.000/mes)"
    if n <= 80:
        return "Plus ($1.220.000/mes)"
    return "Corporativo (precio a la medida)"


# ─── Generación de mensajes con Claude ───────────────────────────────────────

def _build_prompt(
    followup_num: int,
    first_name: str,
    template_title: Optional[str],
    is_flow: bool,
    plan: str,
    context: dict,
) -> str:
    ld = context.get("lead_data") or {}
    company   = ld.get("company") or ""
    employees = ld.get("employee_count") or ""
    sector    = ld.get("sector") or ld.get("industry") or ""

    company_line = f"Empresa: {company}." if company else ""
    sector_line  = f"Sector: {sector}." if sector else ""
    emp_line     = f"Empleados: {employees}." if employees else ""

    template_line = (
        f'Descargaron la plantilla: "{template_title}".'
        if template_title else
        "Descargaron una plantilla de Verifty."
    )

    if is_flow:
        product_context = (
            "El lead es para VERIFTY FLOW (automatización de procesos, empresa grande). "
            "El objetivo es que agenden una demo con el equipo comercial por WhatsApp. "
            "El número de WhatsApp comercial es +57 315 846 5643."
        )
    else:
        product_context = (
            f"El lead es para VERIFTY SST (software SG-SST, compra directa online). "
            f"El plan recomendado para ellos es {plan}. "
            f"El link de compra directo es https://sst.verifty.com/planes"
        )

    tone_per_followup = {
        1: (
            "Primer seguimiento — tono amigable y curioso. "
            "Pregunta si pudieron usar la plantilla o si tienen alguna duda. "
            "Menciona 1 ventaja concreta de Verifty para su situación. "
            "Cierra con UNA pregunta abierta corta. NO pongas el link todavía."
        ),
        2: (
            "Segundo seguimiento — tono más directo y propositivo. "
            "Menciona que otras empresas similares ya están usando Verifty. "
            "Para SST: muestra el plan recomendado con precio y el link de compra. "
            "Para Flow: propone agendar una demo de 20 minutos, da el WhatsApp. "
            "Máximo 4 oraciones."
        ),
        3: (
            "Tercer y último seguimiento — cierre definitivo, honesto y sin presión. "
            "Di que es tu último mensaje y que estarás disponible cuando lo necesiten. "
            "Para SST: deja el link. Para Flow: deja el WhatsApp comercial. "
            "Máximo 3 oraciones. Tono cálido, sin desesperación."
        ),
    }

    name_line = (
        f'El nombre del lead es "{first_name}". Salúdalo por ese nombre.'
        if first_name
        else "No conocemos el nombre. Usa un saludo natural sin nombre."
    )

    return f"""Eres el asesor comercial de Verifty (SaaS colombiano de SST y automatización de procesos).

Contexto del lead:
{template_line}
{company_line} {emp_line} {sector_line}
{name_line}

{product_context}

Tarea: Escribe el SEGUIMIENTO #{followup_num} de WhatsApp.
{tone_per_followup[followup_num]}

Reglas generales:
- Español colombiano, tuteo natural
- Máximo 3-4 oraciones en total (es WhatsApp, no un correo)
- Máximo 1 emoji
- NO uses comillas externas, asteriscos innecesarios ni saludos genéricos como "¡Hola!"
- Responde SOLO con el texto del mensaje, listo para enviar"""


def _generate_followup_message(
    followup_num: int,
    first_name: str,
    template_title: Optional[str],
    is_flow: bool,
    plan: str,
    context: dict,
) -> str:
    prompt = _build_prompt(followup_num, first_name, template_title, is_flow, plan, context)
    try:
        resp = _get_client().messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        body = (resp.content[0].text or "").strip()
        if body.startswith('"') and body.endswith('"'):
            body = body[1:-1].strip()
        if body:
            return body
    except Exception as e:
        logger.warning(f"[followup] Claude falló generando mensaje #{followup_num}: {e}")

    # Fallback estático
    if is_flow:
        return (
            f"{'Hola ' + first_name + ',' if first_name else 'Hola,'} ¿pudiste revisar la plantilla? "
            f"Si quieres te hacemos una demo rápida para ver cómo Verifty puede ayudarte. "
            f"Escríbenos al +57 315 846 5643 🤝"
        )
    return (
        f"{'Hola ' + first_name + ',' if first_name else 'Hola,'} ¿pudiste revisar la plantilla? "
        f"Si tienes dudas sobre el plan que mejor te aplica, con gusto te ayudo. "
        f"Puedes ver los planes en https://sst.verifty.com/planes 👋"
    )


# ─── Detección de respuesta del lead ─────────────────────────────────────────

def _lead_has_responded(conversation_id: str) -> bool:
    """True si el lead envió al menos un mensaje inbound."""
    try:
        r = (
            crm.sb.table("whatsapp_messages")
            .select("id")
            .eq("conversation_id", conversation_id)
            .eq("direction", "inbound")
            .limit(1)
            .execute()
        )
        return bool(r.data)
    except Exception as e:
        logger.warning(f"[followup] Error chequeando respuesta: {e}")
        return False


# ─── Job principal ────────────────────────────────────────────────────────────

async def send_pending_followups() -> int:
    """Envía seguimientos pendientes. Retorna cantidad de mensajes enviados."""
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        r = (
            crm.sb.table("whatsapp_conversations")
            .select("id, wa_phone_number, followup_count, context, template_title, template_slug")
            .lte("next_followup_at", now_iso)
            .eq("followup_stopped", False)
            .lt("followup_count", 3)
            .eq("channel", "whatsapp")
            .not_.is_("next_followup_at", "null")
            .execute()
        )
    except Exception as e:
        logger.error(f"[followup] Error consultando conversaciones: {e}")
        return 0

    convs = r.data or []
    if not convs:
        return 0

    sent = 0
    for conv in convs:
        conv_id      = conv["id"]
        phone        = conv.get("wa_phone_number") or ""
        count        = conv.get("followup_count") or 0
        context      = conv.get("context") or {}
        tmpl_title   = conv.get("template_title") or (
            (context.get("downloaded_template") or {}).get("title")
        )

        if not phone or len(phone) < 10:
            logger.warning(f"[followup] Conv {conv_id} sin teléfono, saltando")
            _stop_followups(conv_id)
            continue

        # Si ya respondió → detener seguimientos
        if _lead_has_responded(conv_id):
            _stop_followups(conv_id)
            logger.info(f"[followup] Lead {phone} ya respondió — deteniendo seguimientos")
            continue

        followup_num = count + 1  # 1, 2 o 3
        is_flow      = _is_flow_lead(context)
        plan         = _recommended_plan(context)
        ld           = context.get("lead_data") or {}
        first_name   = str(ld.get("name") or "").split(" ")[0].strip()

        body = _generate_followup_message(
            followup_num=followup_num,
            first_name=first_name,
            template_title=tmpl_title,
            is_flow=is_flow,
            plan=plan,
            context=context,
        )

        try:
            await whatsapp_client.send_text(phone, body)
        except Exception as e:
            logger.error(f"[followup] Error enviando a {phone}: {e}")
            continue

        # Guardar en historial
        try:
            crm.save_message(conv_id, "outbound", body)
        except Exception as e:
            logger.warning(f"[followup] No se pudo guardar mensaje en historial: {e}")

        # Log en CRM
        crm.log_activity(
            phone=phone,
            title=f"Seguimiento automático #{followup_num} enviado",
            body=body,
        )

        # Calcular próximo seguimiento
        next_hours = FOLLOWUP_DELAYS_HOURS[followup_num - 1] if followup_num <= len(FOLLOWUP_DELAYS_HOURS) else None
        next_at    = (
            (datetime.now(timezone.utc) + timedelta(hours=next_hours)).isoformat()
            if next_hours and followup_num < 3
            else None
        )

        update: dict = {"followup_count": followup_num}
        if next_at:
            update["next_followup_at"] = next_at
        else:
            update["followup_stopped"] = True  # ya enviamos el 3ro

        try:
            crm.sb.table("whatsapp_conversations").update(update).eq("id", conv_id).execute()
        except Exception as e:
            logger.warning(f"[followup] Error actualizando contadores en conv {conv_id}: {e}")

        logger.info(f"[followup] Enviado #{followup_num} a {phone} (flow={is_flow})")
        sent += 1

    return sent


def _stop_followups(conv_id: str) -> None:
    try:
        crm.sb.table("whatsapp_conversations").update(
            {"followup_stopped": True}
        ).eq("id", conv_id).execute()
    except Exception as e:
        logger.warning(f"[followup] No se pudo detener followup para {conv_id}: {e}")

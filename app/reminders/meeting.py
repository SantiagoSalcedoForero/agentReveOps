"""
Recordatorios de reuniones — WhatsApp + email.

Corre cada minuto desde el loop principal. Busca calendar_events cuyo
start_time esté entre (ahora + 8min) y (ahora + 12min), sin reminder_sent_at,
y les envía un mensaje WhatsApp y un correo al lead o contacto.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings
from app.crm.client import crm
from app.logger import get_logger
from app.whatsapp.client import whatsapp_client

logger = get_logger(__name__)

WINDOW_EARLY_MIN = 8   # buscar eventos que empiecen en ≥8 min
WINDOW_LATE_MIN  = 12  # ... y ≤12 min (ventana de 4 min para no perder el tick)


# ─────────────────── helpers ───────────────────

def _normalize_phone(raw: str) -> str:
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("5757"):
        digits = digits[2:]
    country_prefixes = ("57", "52", "54", "34", "51", "56", "593", "591", "507", "1")
    if any(digits.startswith(p) for p in country_prefixes) and len(digits) >= 10:
        return digits
    if len(digits) == 10:
        return "57" + digits
    return digits


def _get_lead_or_contact(event: dict) -> Optional[dict]:
    """Retorna el lead o contacto vinculado al evento, con 'phone' y 'email'."""
    lead_id    = event.get("lead_id")
    contact_id = event.get("contact_id")
    if lead_id:
        return crm.get_lead(lead_id)
    if contact_id:
        try:
            r = crm.sb.table("contacts").select("*").eq("id", contact_id).limit(1).execute()
            return r.data[0] if r.data else None
        except Exception:
            return None
    return None


def _format_time_bogota(iso: str) -> str:
    """Convierte ISO UTC → hora legible en Bogotá."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        bogota = dt.astimezone(timezone(timedelta(hours=-5)))
        return bogota.strftime("%-I:%M %p").lower()  # ej: 2:30 p.m.
    except Exception:
        return iso


# ─────────────────── WhatsApp ───────────────────

async def _send_whatsapp_reminder(phone: str, name: str, time_str: str, meet_link: Optional[str]) -> bool:
    """Envía template verifty_meeting_reminder.
    Parámetros del template: {{1}} = nombre, {{2}} = hora, {{3}} = link (o 'sin enlace').
    """
    first_name = (name or "").split()[0] or "hola"
    link_text  = meet_link or "https://meet.google.com"
    try:
        await whatsapp_client.send_template(
            phone=phone,
            template_name=settings.MEETING_REMINDER_TEMPLATE,
            params=[first_name, time_str, link_text],
        )
        logger.info(f"[reminder] WhatsApp enviado a {phone}")
        return True
    except Exception as e:
        logger.warning(f"[reminder] WhatsApp falló para {phone}: {e}")
        return False


# ─────────────────── Email (Resend) ───────────────────

def _send_email_reminder(
    to_email: str,
    name: str,
    time_str: str,
    meet_link: Optional[str],
    event_title: str,
) -> bool:
    """Envía email de recordatorio via Resend."""
    if not settings.RESEND_API_KEY:
        logger.debug("[reminder] Email omitido: RESEND_API_KEY no configurado")
        return False

    try:
        import resend  # pip install resend
    except ImportError:
        logger.warning("[reminder] Paquete 'resend' no instalado. Ejecuta: pip install resend")
        return False

    resend.api_key = settings.RESEND_API_KEY
    first_name = (name or "").split()[0] or "hola"
    link_text  = meet_link or ""

    link_button = (
        f'<a href="{link_text}" '
        f'style="display:inline-block;background:#7c3aed;color:#fff;text-decoration:none;'
        f'padding:12px 28px;border-radius:8px;font-size:15px;font-weight:600;margin-bottom:20px;">'
        f'Unirme a la reunión →</a>'
    ) if link_text else ""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;padding:24px;background:#fff;">
      <img src="https://www.verifty.com/logo.png" alt="Verifty" style="height:32px;margin-bottom:24px;" />
      <h2 style="color:#1a1a1a;font-size:20px;margin:0 0 8px;">
        ¡Hola {first_name}! Tu reunión empieza en 10 minutos
      </h2>
      <p style="color:#444;font-size:15px;line-height:1.6;margin:0 0 20px;">
        Tu reunión <strong>{event_title}</strong> está programada para las
        <strong>{time_str}</strong>. El equipo de Verifty ya está listo para atenderte.
      </p>
      {link_button}
      <p style="color:#888;font-size:12px;margin:16px 0 0;">
        Si necesitas reagendar, escríbenos a
        <a href="mailto:hola@verifty.com" style="color:#7c3aed;">hola@verifty.com</a>.
      </p>
    </div>
    """

    try:
        resend.Emails.send({
            "from":    f"Verifty <{settings.RESEND_FROM_EMAIL}>",
            "to":      [to_email],
            "subject": "Recordatorio: tu reunión con Verifty en 10 minutos 🗓️",
            "html":    html,
        })
        logger.info(f"[reminder] Email enviado a {to_email}")
        return True
    except Exception as e:
        logger.warning(f"[reminder] Email falló para {to_email}: {e}")
        return False


# ─────────────────── Job principal ───────────────────

async def send_meeting_reminders() -> int:
    """
    Busca eventos que empiecen en ~10 min y envía recordatorios.
    Retorna la cantidad de eventos procesados.
    """
    now         = datetime.now(timezone.utc)
    window_from = (now + timedelta(minutes=WINDOW_EARLY_MIN)).isoformat()
    window_to   = (now + timedelta(minutes=WINDOW_LATE_MIN)).isoformat()

    try:
        r = (
            crm.sb.table("calendar_events")
            .select("id, title, start_time, end_time, meet_link, lead_id, contact_id, status")
            .gte("start_time", window_from)
            .lte("start_time", window_to)
            .is_("reminder_sent_at", None)
            .neq("status", "cancelled")
            .execute()
        )
    except Exception as e:
        logger.error(f"[reminder] Error consultando calendar_events: {e}")
        return 0

    events = r.data or []
    if not events:
        return 0

    sent = 0
    for event in events:
        event_id   = event["id"]
        time_str   = _format_time_bogota(event["start_time"])
        meet_link  = event.get("meet_link")
        event_title = event.get("title") or "Demo Verifty"

        person = _get_lead_or_contact(event)
        if not person:
            logger.warning(f"[reminder] Evento {event_id}: sin lead/contacto vinculado")
            _mark_sent(event_id)  # marcar igual para no reintentar
            continue

        name  = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
        phone = _normalize_phone(person.get("phone") or "")
        email = (person.get("email") or "").strip()

        wa_ok    = False
        email_ok = False

        if phone and len(phone) >= 10:
            wa_ok = await _send_whatsapp_reminder(phone, name, time_str, meet_link)

        if email:
            email_ok = _send_email_reminder(email, name, time_str, meet_link, event_title)

        if wa_ok or email_ok:
            sent += 1
        else:
            logger.warning(f"[reminder] Evento {event_id}: ni WhatsApp ni email enviados")

        _mark_sent(event_id)

    return sent


def _mark_sent(event_id: str) -> None:
    try:
        crm.sb.table("calendar_events").update(
            {"reminder_sent_at": datetime.now(timezone.utc).isoformat()}
        ).eq("id", event_id).execute()
    except Exception as e:
        logger.warning(f"[reminder] No se pudo marcar reminder_sent_at en {event_id}: {e}")

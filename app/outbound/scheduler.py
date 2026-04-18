"""Background task que procesa pending_nudges cuando les toca su due_at."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone

from app.config import settings
from app.crm.client import crm
from app.outbound.manager import start_outbound_conversation
from app.logger import get_logger

logger = get_logger(__name__)

POLL_INTERVAL_SEC = 60  # revisar cada minuto


def _lead_already_booked(lead_id: str | None) -> bool:
    """Revisa si el lead ya tiene demo agendada (por bot o por calendly externo)."""
    if not lead_id:
        return False
    try:
        lead = crm.get_lead(lead_id)
        if lead and lead.get("demo_scheduled_at"):
            return True
    except Exception:
        pass
    try:
        r = (
            crm.sb.table("calendar_events")
            .select("id")
            .eq("lead_id", lead_id)
            .limit(1)
            .execute()
        )
        return bool(r.data)
    except Exception:
        return False


async def _handle_demo_no_show(row: dict) -> tuple[bool, str]:
    """Si el lead ya agendó → skip. Si no → manda template de nudge."""
    lead_id = row.get("lead_id")
    if _lead_already_booked(lead_id):
        return True, "already_booked"

    payload = row.get("payload") or {}
    lead_data = payload.get("lead_data") or {}
    first_name = (lead_data.get("name") or "").split(" ")[0] or "hola"

    conv_id = await start_outbound_conversation(
        phone=row["phone"],
        lead_data=lead_data,
        source_form="demo_no_show",
        template_name=settings.OUTBOUND_DEMO_NUDGE_TEMPLATE,
        template_params=[first_name],
    )
    return conv_id is not None, "nudge_sent"


async def _handle_contact_form_greeting(row: dict) -> tuple[bool, str]:
    """Mandar saludo outbound diferido (si se programó así)."""
    payload = row.get("payload") or {}
    lead_data = payload.get("lead_data") or {}
    first_name = (lead_data.get("name") or "").split(" ")[0] or "hola"
    conv_id = await start_outbound_conversation(
        phone=row["phone"],
        lead_data=lead_data,
        source_form="contact_form_greeting",
        template_name=settings.OUTBOUND_LEAD_TEMPLATE,
        template_params=[first_name],
    )
    return conv_id is not None, "greeting_sent"


HANDLERS = {
    "demo_no_show": _handle_demo_no_show,
    "contact_form_greeting": _handle_contact_form_greeting,
}


async def _check_lost_conversations() -> None:
    """Revisa conversaciones en waiting_agent y marca como lost si 60+ min."""
    try:
        from app.chat.manager import check_and_mark_lost
        marked = check_and_mark_lost()
        if marked:
            logger.info(f"[lost] {marked} conversation(s) marked as lost")
    except Exception as e:
        logger.exception(f"lost check error: {e}")


async def process_due_nudges() -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        r = (
            crm.sb.table("pending_nudges")
            .select("*")
            .eq("status", "pending")
            .lte("due_at", now_iso)
            .limit(50)
            .execute()
        )
    except Exception as e:
        logger.exception(f"query pending_nudges: {e}")
        return

    rows = r.data or []
    if not rows:
        return

    logger.info(f"[nudges] processing {len(rows)} due nudge(s)")
    for row in rows:
        nudge_id = row["id"]
        handler = HANDLERS.get(row["kind"])
        attempts = (row.get("attempts") or 0) + 1
        if not handler:
            crm.sb.table("pending_nudges").update(
                {"status": "failed", "attempts": attempts,
                 "last_error": "no_handler"}
            ).eq("id", nudge_id).execute()
            continue
        try:
            ok, note = await handler(row)
            if ok:
                new_status = "skipped" if note == "already_booked" else "sent"
                crm.sb.table("pending_nudges").update(
                    {"status": new_status, "attempts": attempts,
                     "sent_at": datetime.now(timezone.utc).isoformat(),
                     "last_error": note}
                ).eq("id", nudge_id).execute()
                logger.info(f"[nudges] {nudge_id} {new_status} ({note})")
            else:
                final = "failed" if attempts >= 3 else "pending"
                crm.sb.table("pending_nudges").update(
                    {"status": final, "attempts": attempts,
                     "last_error": f"handler_failed:{note}"}
                ).eq("id", nudge_id).execute()
        except Exception as e:
            logger.exception(f"[nudges] {nudge_id} exception: {e}")
            final = "failed" if attempts >= 3 else "pending"
            crm.sb.table("pending_nudges").update(
                {"status": final, "attempts": attempts,
                 "last_error": str(e)[:400]}
            ).eq("id", nudge_id).execute()


async def run_scheduler_loop() -> None:
    """Loop que corre indefinidamente revisando nudges pendientes."""
    logger.info(
        f"[nudges] scheduler starting (poll every {POLL_INTERVAL_SEC}s)"
    )
    # Pequeño delay inicial para evitar race con startup
    await asyncio.sleep(5)
    while True:
        try:
            await process_due_nudges()
            await _check_lost_conversations()
        except Exception as e:
            logger.exception(f"scheduler iteration: {e}")
        await asyncio.sleep(POLL_INTERVAL_SEC)

from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.logger import get_logger
from app.crm.client import crm
from app.whatsapp.client import whatsapp_client
from app.bot.agent import agent
from app.models.webhook import (
    HandoffAcceptRequest,
    HandoffMessageRequest,
    LandingGateRequest,
    LandingVerifyRequest,
    LeadIntentRequest,
)
from app.otp.manager import (
    should_gate_download,
    create_otp,
    verify_code,
    seconds_since_last_otp,
    OTP_RESEND_COOLDOWN_SECONDS,
)
from app.otp.templates_catalog import get_template_meta
from app.otp.first_message import build_first_message
from app.bot.scorer import calculate_score as run_scorer
from app.outbound.manager import (
    start_outbound_conversation,
    schedule_nudge,
)
from app.outbound.scheduler import run_scheduler_loop
from app.chat.manager import (
    close_conversation,
    reopen_conversation,
    initiate_chat,
)
from app.chat.survey import handle_survey_response, RATING_MAP
from app.ceo.router import router as ceo_router

logger = get_logger("main")

app = FastAPI(title="Verifty WhatsApp Bot", version="1.0.0")
app.include_router(ceo_router)

# Per-conversation queues to serialize processing while user keeps typing
_conv_queues: dict[str, asyncio.Queue] = {}
_conv_workers: dict[str, asyncio.Task] = {}
# In-memory dedup: evita que webhooks duplicados de Meta (llegan con ~1s de
# diferencia) pasen el check de BD antes de que el primero inserte.
_recent_wa_ids: dict[str, float] = {}
_DEDUP_TTL = 30.0  # segundos


async def _conv_worker(conversation_id: str):
    q = _conv_queues[conversation_id]
    try:
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=60)
            except asyncio.TimeoutError:
                break
            try:
                await agent.process_message(**payload)
            except Exception as e:
                logger.exception(f"agent.process_message failed: {e}")
            q.task_done()
    finally:
        _conv_queues.pop(conversation_id, None)
        _conv_workers.pop(conversation_id, None)


def _enqueue(conversation_id: str, payload: dict) -> None:
    if conversation_id not in _conv_queues:
        _conv_queues[conversation_id] = asyncio.Queue()
    _conv_queues[conversation_id].put_nowait(payload)
    if conversation_id not in _conv_workers or _conv_workers[conversation_id].done():
        _conv_workers[conversation_id] = asyncio.create_task(
            _conv_worker(conversation_id)
        )


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


def _require_admin_token(request: Request) -> None:
    expected = getattr(settings, "ADMIN_API_TOKEN", None) or ""
    if not expected:
        raise HTTPException(500, "ADMIN_API_TOKEN not configured")
    auth = request.headers.get("authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if token != expected:
        raise HTTPException(401, "Unauthorized")


@app.get("/admin/stats/summary")
async def stats_summary(request: Request):
    """Resumen global del bot: conversaciones, costo total, tokens."""
    _require_admin_token(request)
    r = (
        crm.sb.table("bot_usage_summary")
        .select("*")
        .limit(1)
        .execute()
    )
    return (r.data or [{}])[0]


@app.get("/admin/stats/daily")
async def stats_daily(request: Request, days: int = 30):
    """Consumo diario de los últimos N días."""
    _require_admin_token(request)
    r = (
        crm.sb.table("bot_usage_daily")
        .select("*")
        .limit(days)
        .execute()
    )
    return r.data or []


@app.get("/admin/stats/conversation/{conversation_id}")
async def stats_conversation(conversation_id: str, request: Request):
    """Costo y métricas detalladas de UNA conversación."""
    _require_admin_token(request)
    r = (
        crm.sb.table("bot_conversation_costs")
        .select("*")
        .eq("conversation_id", conversation_id)
        .limit(1)
        .execute()
    )
    if not r.data:
        raise HTTPException(404, "Conversation not found")
    return r.data[0]


@app.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verified by Meta")
        return hub_challenge
    raise HTTPException(status_code=403, detail="Verify token mismatch")


@app.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    background_tasks.add_task(_handle_webhook_payload, body)
    return {"status": "received"}


async def _handle_webhook_payload(body: dict):
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                # Status-only payloads have no 'messages' field; ignore them
                messages = value.get("messages") or []
                if not messages:
                    continue
                contacts = value.get("contacts") or []
                wa_name = None
                if contacts:
                    profile = contacts[0].get("profile") or {}
                    wa_name = profile.get("name")
                for msg in messages:
                    await _ingest_message(msg, wa_name)
    except Exception as e:
        logger.exception(f"Webhook handling error: {e}")


def _extract_attribution(msg: dict, message_text: str) -> dict:
    """Build lead attribution from Meta CTWA referral + first-message hints."""
    attribution: dict[str, str] = {}

    # 1) Meta Click-to-WhatsApp ads: send `referral` object in the first message
    referral = msg.get("referral") or {}
    if referral:
        source_type = referral.get("source_type")  # "ad" | "post"
        source_url = referral.get("source_url")
        source_id = referral.get("source_id")
        headline = referral.get("headline")
        ctwa_clid = referral.get("ctwa_clid")
        if source_type == "ad":
            attribution["utm_source"] = "facebook_ad"
            attribution["utm_medium"] = "paid_social"
        elif source_type == "post":
            attribution["utm_source"] = "facebook_post"
            attribution["utm_medium"] = "organic_social"
        else:
            attribution["utm_source"] = "meta"
        if source_id:
            attribution["utm_campaign"] = source_id
        if headline:
            attribution["utm_content"] = headline[:200]
        if source_url:
            attribution["referrer"] = source_url
            attribution["first_page_url"] = source_url
        if ctwa_clid:
            attribution["session_id"] = ctwa_clid
        attribution["conversion_trigger"] = "ctwa"
        attribution["created_via_url"] = source_url or "meta_ads"

    # 2) Parse first message for explicit UTM-like hints or common wording
    if message_text and not attribution.get("utm_source"):
        t = message_text.lower()
        hints = [
            ("google", "google"),
            ("instagram", "instagram"),
            ("facebook", "facebook"),
            ("linkedin", "linkedin"),
            ("tiktok", "tiktok"),
            ("verifty.com", "website"),
            ("página web", "website"),
            ("pagina web", "website"),
            ("landing", "landing"),
            ("recomend", "referral"),
            ("referid", "referral"),
            ("evento", "event"),
            ("feria", "event"),
            ("webinar", "webinar"),
        ]
        for needle, src in hints:
            if needle in t:
                attribution["utm_source"] = src
                attribution["conversion_trigger"] = "first_message_hint"
                break

    return attribution


async def _ingest_message(msg: dict, wa_name: str | None):
    wa_message_id = msg.get("id")
    phone = msg.get("from")
    msg_type = msg.get("type")

    if not wa_message_id or not phone:
        return

    # Dedup capa 1: in-memory (atrapa webhooks duplicados de Meta en ~1s)
    import time as _time
    now_ts = _time.monotonic()
    if wa_message_id in _recent_wa_ids:
        logger.info(f"Duplicate skipped (memory): {wa_message_id}")
        return
    _recent_wa_ids[wa_message_id] = now_ts
    # Limpiar entradas viejas cada ~50 mensajes para no crecer sin límite
    if len(_recent_wa_ids) > 200:
        cutoff = now_ts - _DEDUP_TTL
        _recent_wa_ids.clear()

    # Dedup capa 2: BD (atrapa duplicados tras restart del proceso)
    if crm.message_exists(wa_message_id):
        logger.info(f"Duplicate skipped (db): {wa_message_id}")
        return

    text = ""
    if msg_type == "text":
        text = msg.get("text", {}).get("body", "")
    elif msg_type == "interactive":
        interactive = msg.get("interactive", {})
        if interactive.get("type") == "button_reply":
            text = interactive["button_reply"].get("title", "")
        elif interactive.get("type") == "list_reply":
            text = interactive["list_reply"].get("title", "")
    elif msg_type == "button":
        text = msg.get("button", {}).get("text", "")
    else:
        text = f"[mensaje no soportado: {msg_type}]"

    # Limpiar mensajes con UTMs embebidos del landing
    # Formato: "¡Hola! Vengo de verifty.com | URL: ... | utm_source: ..."
    if "verifty.com" in text and "utm_source" in text.lower():
        import re as _re
        # Extraer UTMs del texto antes de limpiar
        utm_parts = {}
        for match in _re.finditer(r"(utm_\w+|URL):\s*(\S+)", text, _re.IGNORECASE):
            key, val = match.group(1).lower(), match.group(2)
            utm_parts[key] = val
        if utm_parts:
            if not attribution:
                attribution = {}
            attribution.update({
                "utm_source": utm_parts.get("utm_source"),
                "utm_medium": utm_parts.get("utm_medium"),
                "utm_campaign": utm_parts.get("utm_campaign"),
                "first_page_url": utm_parts.get("url"),
                "conversion_trigger": "wa_link_landing",
            })
        # Limpiar el texto: quitar todo después del primer "|"
        clean_text = text.split("|")[0].strip()
        if clean_text:
            text = clean_text
        else:
            text = "Hola"
        logger.info(f"Cleaned UTM message: '{text}' attrs={utm_parts}")

    logger.info(f"WA IN [{phone}] ({msg_type}): {text[:200]}")

    # Detectar respuestas de encuesta de satisfacción
    interactive = msg.get("interactive") or {}
    button_reply = interactive.get("button_reply") or {}
    button_id = button_reply.get("id", "")
    if button_id in RATING_MAP:
        # Es una respuesta a la encuesta — buscar conversación y guardar
        try:
            existing = crm.sb.table("whatsapp_conversations").select("id").eq(
                "wa_phone_number", phone
            ).limit(1).execute()
            if existing.data:
                rating = handle_survey_response(existing.data[0]["id"], button_id)
                logger.info(f"Survey response [{phone}]: {button_id} → rating={rating}")
                # Respuesta de agradecimiento
                await whatsapp_client.send_text(
                    phone, "¡Gracias por tu calificación! 🙏 Nos ayuda a mejorar."
                )
        except Exception as e:
            logger.warning(f"survey response handler: {e}")
        return

    attribution = _extract_attribution(msg, text)
    if attribution:
        logger.info(f"Lead attribution [{phone}]: {attribution}")
    conv = crm.get_or_create_conversation(phone, wa_name, attribution=attribution)
    crm.save_message(
        conversation_id=conv["id"],
        direction="inbound",
        body=text,
        wa_message_id=wa_message_id,
    )
    # Actualizar last_message_at para ordenar el inbox
    try:
        crm.sb.table("whatsapp_conversations").update({
            "last_message_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", conv["id"]).execute()
    except Exception:
        pass

    try:
        await whatsapp_client.mark_as_read(wa_message_id)
    except Exception:
        pass

    _enqueue(conv["id"], {
        "conversation_id": conv["id"],
        "phone": phone,
        "message_text": text,
        "wa_name": wa_name,
    })


@app.post("/handoff/accept")
async def handoff_accept(payload: HandoffAcceptRequest):
    conv = crm.get_conversation(payload.conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")

    profile = crm.get_profile(payload.agent_profile_id)
    agent_name = (profile or {}).get("full_name") or "un asesor"

    crm.update_conversation(payload.conversation_id, {
        "status": "human_active",
        "assigned_profile_id": payload.agent_profile_id,
    })

    msg = f"Te conectamos con {agent_name} 👋"
    await whatsapp_client.send_text(conv["phone"], msg)
    crm.save_message(payload.conversation_id, "outbound", msg,
                     sender_profile_id=payload.agent_profile_id)
    return {"status": "ok"}


@app.post("/handoff/message")
async def handoff_message(payload: HandoffMessageRequest):
    conv = crm.get_conversation(payload.conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    await whatsapp_client.send_text(conv["phone"], payload.message)
    crm.save_message(
        payload.conversation_id,
        "outbound",
        payload.message,
        sender_profile_id=payload.agent_profile_id,
    )
    return {"status": "sent"}


def _normalize_phone(raw: str) -> str:
    """Normaliza a formato E.164 sin '+' (ej. '573150636348'). Soporta espacios,
    guiones, paréntesis, +. Si no tiene país, asume Colombia (57)."""
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return ""
    # Si empieza con 57, 52, 54, 34, 51, 56 (LatAm/ES) asume ya tiene país
    country_prefixes = ("57", "52", "54", "34", "51", "56", "593", "591", "507", "1")
    if any(digits.startswith(p) for p in country_prefixes) and len(digits) >= 10:
        return digits
    # 10 dígitos sin prefijo → asumir Colombia
    if len(digits) == 10:
        return "57" + digits
    return digits


@app.post("/landing/gate")
async def landing_gate(payload: LandingGateRequest, request: Request):
    """Paso 1 del gate: recibe el form, decide si requiere OTP.
    - Si NO requiere (empresa pequeña + email personal): responde con la URL directa.
    - Si SÍ requiere: genera OTP, lo envía por WhatsApp (template) y pide verificación.
    """
    phone = _normalize_phone(payload.phone)
    if not phone or len(phone) < 10:
        raise HTTPException(400, "Teléfono inválido")

    lead_data = {
        "name": payload.name,
        "email": payload.email,
        "company": payload.company,
        "employee_count": payload.employees,
        "country": payload.country,
        "industry": payload.industry,
        "job_title": payload.job_title or payload.professional_role,
        "nivel_riesgo_arl": payload.nivel_riesgo_arl,
    }
    attribution = {
        "utm_source": payload.utm_source,
        "utm_medium": payload.utm_medium,
        "utm_campaign": payload.utm_campaign,
        "utm_content": payload.utm_content,
        "referrer": payload.referrer,
        "first_page_url": payload.source_url,
        "created_via_url": payload.source_url,
        "conversion_trigger": "landing_download",
    }

    gated, reason = should_gate_download(lead_data)
    logger.info(
        f"Landing gate: phone={phone} template={payload.template_slug} "
        f"gated={gated} reason={reason}"
    )

    if not gated:
        # Lead pequeño/personal: descarga directa, sin OTP.
        # Guardamos el lead igualmente (marketing puede hacer nurturing).
        try:
            crm.get_or_create_lead(
                phone=phone,
                wa_name=lead_data.get("name"),
                attribution={
                    **{k: v for k, v in attribution.items() if v},
                    "utm_content": (payload.template_slug
                                    if not attribution.get("utm_content")
                                    else attribution["utm_content"]),
                },
            )
        except Exception as e:
            logger.warning(f"Could not save non-gated lead: {e}")
        return {
            "gated": False,
            "template_url": payload.template_url,
            "reason": reason,
        }

    # Dedup: si ya hay un OTP activo enviado hace menos de OTP_RESEND_COOLDOWN_SECONDS,
    # no generar otro — el usuario ya tiene el código en su WhatsApp.
    elapsed = seconds_since_last_otp(phone)
    if elapsed is not None and elapsed < OTP_RESEND_COOLDOWN_SECONDS:
        remaining = OTP_RESEND_COOLDOWN_SECONDS - elapsed
        logger.info(f"OTP dedup: phone={phone} — OTP activo, {elapsed}s desde el último. Cooldown restante: {remaining}s")
        return {
            "gated": True,
            "already_sent": True,
            "message": f"Ya te enviamos un código a tu WhatsApp. Revísalo o espera {remaining}s para solicitar uno nuevo.",
            "reason": "otp_cooldown",
        }

    # Generar OTP + enviar WhatsApp
    code, _otp_row = create_otp(
        phone=phone,
        lead_data=lead_data,
        template_slug=payload.template_slug,
        template_url=payload.template_url,
        template_title=payload.template_title,
        template_description=payload.template_description,
        attribution=attribution,
        ip_address=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
    )
    try:
        await whatsapp_client.send_otp_template(phone=phone, code=code)
    except Exception as e:
        logger.exception(f"send_otp_template failed: {e}")
        raise HTTPException(502, "No pudimos enviar el código a tu WhatsApp")

    return {
        "gated": True,
        "message": "Código enviado a tu WhatsApp. Tiene 10 minutos de vigencia.",
        "reason": reason,
    }


@app.post("/landing/verify")
async def landing_verify(payload: LandingVerifyRequest):
    """Paso 2 del gate: verifica el código. Si OK:
    - Crea conversación + lead en CRM
    - Envía primer mensaje contextual del bot al lead
    - Retorna la URL del archivo a descargar
    """
    phone = _normalize_phone(payload.phone)
    code = (payload.code or "").strip()
    if len(code) < 4:
        raise HTTPException(400, "Código inválido")

    ok, otp_row, message = verify_code(phone, code)
    if not ok:
        return {"ok": False, "message": message}

    lead_data = otp_row.get("lead_data") or {}
    attribution = otp_row.get("attribution") or {}
    template_slug = otp_row.get("template_slug")
    template_url = otp_row.get("template_url")
    template_title = otp_row.get("template_title")
    template_description = otp_row.get("template_description")

    # Marketing attribution: agregar el template como utm_content si no viene
    if template_slug and not attribution.get("utm_content"):
        attribution["utm_content"] = template_slug

    # Create/get conversation + lead
    try:
        conv = crm.get_or_create_conversation(
            phone=phone,
            wa_name=lead_data.get("name"),
            attribution=attribution,
        )
        # Actualizar lead con datos del landing
        lead_id = conv.get("lead_id")
        if lead_id:
            lead_update: dict = {}
            if lead_data.get("name"):
                parts = str(lead_data["name"]).split(" ", 1)
                lead_update["first_name"] = parts[0]
                if len(parts) > 1:
                    lead_update["last_name"] = parts[1]
            if lead_data.get("email"):
                lead_update["email"] = lead_data["email"]
            if lead_data.get("company"):
                lead_update["company_name"] = lead_data["company"]
            if lead_data.get("employee_count"):
                lead_update["employee_count"] = str(lead_data["employee_count"])
                lead_update["numero_trabajadores"] = str(lead_data["employee_count"])
            if lead_data.get("industry"):
                lead_update["industry"] = lead_data["industry"]
                lead_update["sector"] = lead_data["industry"]
            if lead_data.get("job_title"):
                lead_update["job_title"] = lead_data["job_title"]
                lead_update["professional_role"] = lead_data["job_title"]
            if lead_data.get("nivel_riesgo_arl"):
                lead_update["nivel_riesgo_arl"] = lead_data["nivel_riesgo_arl"]
            if lead_update:
                try:
                    crm.update_lead(lead_id, lead_update)
                except Exception as e:
                    logger.warning(f"lead update post-verify: {e}")

        # Inyectar plantilla descargada en el contexto + persistir en columnas
        ctx = conv.get("context") or {}
        ctx.setdefault("lead_data", {})
        ctx["lead_data"].update(lead_data)
        ctx["downloaded_template"] = {
            "slug": template_slug,
            "url": template_url,
            "title": template_title,
            "description": template_description,
        }
        conv_update: dict = {
            "context": ctx,
            "status": "qualifying",
        }
        # Columnas nuevas (pueden no existir si la migración 005 no corrió)
        if template_slug:
            conv_update["template_slug"] = template_slug
        if template_title:
            conv_update["template_title"] = template_title
        try:
            crm.update_conversation(conv["id"], conv_update)
        except Exception as e:
            # Si las columnas no existen aún, reintenta sin ellas
            logger.warning(
                f"update_conversation full failed, retrying without template cols: {e}"
            )
            crm.update_conversation(
                conv["id"], {"context": ctx, "status": "qualifying"}
            )
    except Exception as e:
        logger.exception(f"verify conv setup failed: {e}")
        # Igual devolvemos OK — el download no debe fallar por esto
        conv = None

    # Calcular score inmediatamente con los datos del form
    if lead_id:
        try:
            score_data = {
                "employee_count": lead_data.get("employee_count"),
                "industry": lead_data.get("industry"),
                "has_contractors": lead_data.get("has_contractors"),
                "nivel_riesgo_arl": lead_data.get("nivel_riesgo_arl"),
            }
            new_score, breakdown = run_scorer(score_data)
            if new_score > 0:
                crm.update_lead(lead_id, {
                    "score": new_score,
                    "score_breakdown": breakdown,
                })
                if conv:
                    crm.update_conversation(conv["id"], {"score": new_score})
        except Exception as e:
            logger.warning(f"verify scoring: {e}")

    # Primer mensaje contextual — dinámico por plantilla
    body = build_first_message(
        lead_data=lead_data,
        template_slug=template_slug,
        template_title=template_title,
        template_description=template_description,
    )
    try:
        await whatsapp_client.send_text(phone, body)
        if conv:
            crm.save_message(
                conversation_id=conv["id"],
                direction="outbound",
                body=body,
            )
    except Exception as e:
        logger.exception(f"Initial template follow-up message failed: {e}")

    return {
        "ok": True,
        "template_url": template_url,
        "message": "Código verificado. Descarga habilitada.",
    }


@app.post("/chat/close")
async def chat_close(request: Request):
    """Cierra una conversación + opcionalmente envía encuesta de satisfacción."""
    body = await request.json()
    conversation_id = body.get("conversation_id")
    closed_by = body.get("agent_profile_id", "system")
    reason = body.get("reason", "resolved")
    send_survey = body.get("send_survey", True)
    if not conversation_id:
        raise HTTPException(400, "conversation_id required")
    try:
        result = await close_conversation(
            conversation_id=conversation_id,
            closed_by=closed_by,
            reason=reason,
            send_survey=send_survey,
        )
        return result
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/chat/reopen")
async def chat_reopen(request: Request):
    """Reabre una conversación cerrada/perdida con un template de WhatsApp."""
    body = await request.json()
    conversation_id = body.get("conversation_id")
    agent_profile_id = body.get("agent_profile_id")
    template_name = body.get("template_name")
    if not conversation_id or not agent_profile_id:
        raise HTTPException(400, "conversation_id and agent_profile_id required")
    try:
        result = await reopen_conversation(
            conversation_id=conversation_id,
            agent_profile_id=agent_profile_id,
            template_name=template_name,
        )
        return result
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"Template send failed: {e}")


@app.post("/chat/initiate")
async def chat_initiate(request: Request):
    """Abre chat nuevo con un lead o contacto que no tiene historial WA.
    Envía template outbound. Se usa desde el CRM al hacer click en
    'Iniciar chat' en el detalle del lead/contacto.
    """
    body = await request.json()
    lead_id = body.get("lead_id")
    contact_id = body.get("contact_id")
    agent_profile_id = body.get("agent_profile_id")
    template_name = body.get("template_name")
    if not lead_id and not contact_id:
        raise HTTPException(400, "lead_id or contact_id required")
    try:
        result = await initiate_chat(
            lead_id=lead_id,
            contact_id=contact_id,
            agent_profile_id=agent_profile_id,
            template_name=template_name,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@app.post("/agent/status")
async def agent_status_update(request: Request):
    """Toggle online/offline del agente."""
    body = await request.json()
    profile_id = body.get("profile_id")
    is_online = body.get("is_online")
    if not profile_id or is_online is None:
        raise HTTPException(400, "profile_id and is_online required")
    try:
        crm.sb.table("profiles").update({
            "is_online": bool(is_online),
        }).eq("id", profile_id).execute()
        return {"ok": True, "is_online": bool(is_online)}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/landing/lead-intent")
async def landing_lead_intent(payload: LeadIntentRequest, request: Request):
    """Cualquier form de verifty.com EXCEPTO descarga de plantilla.

    - source_form = 'demo_request' → registra lead + agenda nudge en 35 min
      (si no agenda en ese tiempo, bot lo contacta por WhatsApp)
    - source_form = cualquier otro → envía saludo outbound de inmediato
      por template + abre conversación para que el bot califique cuando
      el lead responda.
    """
    phone = _normalize_phone(payload.phone)
    if not phone or len(phone) < 10:
        raise HTTPException(400, "Teléfono inválido")
    if payload.source_form == "template_download":
        raise HTTPException(
            400,
            "Usa /landing/gate para descargas de plantillas",
        )

    lead_data = {
        "name": payload.name,
        "email": payload.email,
        "company": payload.company,
        "employee_count": payload.employees,
        "country": payload.country,
        "industry": payload.industry,
        "pain_point": payload.pain_point or payload.message,
    }
    attribution = {
        "utm_source": payload.utm_source,
        "utm_medium": payload.utm_medium,
        "utm_campaign": payload.utm_campaign,
        "utm_content": payload.utm_content or payload.source_form,
        "referrer": payload.referrer,
        "first_page_url": payload.source_url,
        "created_via_url": payload.source_url,
        "conversion_trigger": payload.source_form,
    }
    attribution = {k: v for k, v in attribution.items() if v}

    # Registrar / enriquecer lead
    lead = crm.get_or_create_lead(
        phone=phone, wa_name=payload.name, attribution=attribution
    )
    lead_id = lead.get("id")
    lead_update: dict = {}
    if payload.email:
        lead_update["email"] = payload.email
    if payload.company:
        lead_update["company_name"] = payload.company
    if payload.employees:
        lead_update["employee_count"] = str(payload.employees)
        lead_update["numero_trabajadores"] = str(payload.employees)
    if payload.industry:
        lead_update["industry"] = payload.industry
        lead_update["sector"] = payload.industry
    if payload.pain_point or payload.message:
        lead_update["main_need"] = (payload.pain_point or payload.message)[:500]
    if lead_update and lead_id:
        try:
            crm.update_lead(lead_id, lead_update)
        except Exception as e:
            logger.warning(f"lead enrich failed: {e}")

    # Branch por tipo de form
    if payload.source_form == "demo_request":
        nudge_id = schedule_nudge(
            phone=phone,
            lead_id=lead_id,
            kind="demo_no_show",
            due_in_minutes=settings.DEMO_NUDGE_DELAY_MINUTES,
            payload={"lead_data": lead_data, "attribution": attribution},
        )
        logger.info(
            f"Lead intent demo_request: phone={phone} nudge_id={nudge_id} "
            f"due_in={settings.DEMO_NUDGE_DELAY_MINUTES}min"
        )
        return {
            "ok": True,
            "action": "nudge_scheduled",
            "nudge_id": nudge_id,
            "due_in_minutes": settings.DEMO_NUDGE_DELAY_MINUTES,
        }

    # Cualquier otro form → outbound inmediato
    first_name = (payload.name or "").split(" ")[0] if payload.name else "hola"
    conv_id = await start_outbound_conversation(
        phone=phone,
        lead_data=lead_data,
        source_form=payload.source_form,
        template_name=settings.OUTBOUND_LEAD_TEMPLATE,
        template_params=[first_name],
        context_extra={"attribution": attribution},
    )
    if not conv_id:
        raise HTTPException(
            502, "No pudimos enviar el saludo por WhatsApp"
        )
    logger.info(
        f"Lead intent outbound: phone={phone} form={payload.source_form} "
        f"conv={conv_id}"
    )
    return {
        "ok": True,
        "action": "outbound_sent",
        "conversation_id": conv_id,
    }


@app.on_event("startup")
async def on_startup():
    logger.info(
        f"Verifty Bot starting — model={settings.ANTHROPIC_MODEL} "
        f"tz={settings.BOT_TIMEZONE} threshold={settings.QUALIFIED_SCORE_THRESHOLD}"
    )
    # Background loop para procesar nudges pendientes
    asyncio.create_task(run_scheduler_loop())
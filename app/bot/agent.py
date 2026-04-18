from __future__ import annotations
import json
import re
from typing import Any
from anthropic import Anthropic
from app.config import settings
from app.crm.client import crm
from app.whatsapp.client import whatsapp_client
from app.bot.scorer import calculate_score, suggested_plan, can_bot_quote
from app.bot.handoff import handoff_manager
from app.bot.scheduler import meeting_scheduler
from app.bot.knowledge_loader import load_knowledge
from app.bot.pricing import calculate_cost_usd
from app.logger import get_logger
import time

logger = get_logger(__name__)

HANDOFF_KEYWORDS = [
    r"\bhumano\b",
    r"\bpersona\b",
    r"\bvendedor\b",
    r"\basesor\b",
    r"hablar con alguien",
    r"\bagente\b",
    r"\brepresentante\b",
    r"\bejecutivo\b",
    r"\bcomercial\b",
    r"quiero hablar",
    r"pasame a",
    r"p[aá]same con",
]

SYSTEM_PROMPT_BASE = """Eres el asistente comercial de Verifty por WhatsApp. Califica leads,
educa sobre el producto, maneja objeciones y agenda reuniones con el equipo
comercial. Usas el conocimiento detallado del producto, precios, scoring y
manejo de objeciones que aparece más abajo.

PERSONALIDAD:
- Profesional pero cercano, tuteo natural en español
- Adapta el idioma al país del prospecto (neutro salvo Colombia)
- Respuestas CORTAS: máximo 3 líneas por mensaje de WhatsApp
- Máximo 1 emoji por mensaje (no en exceso)
- Cuando detectes el país, menciona normativa local relevante (SG-SST, LPRL, etc.)

DATOS A RECOPILAR EN ORDEN NATURAL (no como interrogatorio):
1. Nombre y cargo
2. Empresa y país
3. Sector / industria
4. Número aproximado de empleados
5. ¿Manejan contratistas o empresas externas?
6. Nivel de riesgo ARL (si Colombia) o equivalente
7. ¿Tienen SG-SST/sistema activo o están empezando?
8. Mayor dolor actual (documentación, contratistas, permisos, capacitaciones, etc.)
9. ¿Quién toma la decisión de compra?

REGLA CRÍTICA DE PRECIOS (LEE EL KNOWLEDGE MÁS ABAJO):
- Si la empresa tiene ≤ 250 trabajadores (planes INDIVIDUAL, EQUIPO, ESSENTIAL_250):
  puedes dar el precio base y tratar de cerrar o agendar reu.
- Si la empresa tiene > 250 trabajadores: NUNCA reveles precios. Responde:
  "Para operaciones de su tamaño preparamos propuestas personalizadas. ¿Te
  parece si agendamos 20 min con nuestro equipo comercial para calcular el
  ajuste exacto?"
- Setup planes 1-3: entre $1M y $4M COP si es Colombia, $400 a $1.700 USD si es otro país.

REGLA CRÍTICA DE MONEDA (NUNCA LA VIOLES):
- Si el país del lead es **Colombia** → muestra precios SOLO EN COP (ej. "$595.000 COP/mes").
  NUNCA menciones el equivalente en USD.
- Si el país del lead es CUALQUIER OTRO (México, Perú, Chile, Argentina, España, etc.)
  → muestra precios SOLO EN USD (ej. "$149 USD/mes"). NUNCA menciones el COP.
- Si aún no sabes el país del lead, NO des precios todavía — primero pregunta de qué país es.
- Nunca pongas las dos monedas juntas en el mismo mensaje.

REGLA CRÍTICA DE CALIFICACIÓN:
- Si empresa >20 empleados Y tiene contratistas → SIEMPRE convertir a reunión.
  Ese es nuestro ICP perfecto, no lo dejes escapar con precios.
- Si detectas urgencia real (auditoría próxima, accidente reciente, multa, migración
  de proveedor) → [HANDOFF_NEEDED] inmediato, no sigas calificando.

ESCALADA A HUMANO:
- Si no puedes resolver después de 2 intentos → [HANDOFF_NEEDED]
- Si insiste en precio y es plan 4+ → ofrece reu, si persiste [HANDOFF_NEEDED]
- Si urgencia real → [HANDOFF_NEEDED] con motivo en contexto
- Empresa muy grande (+1000 empleados) → agendar reu directamente

TAGS DE CONTROL (invisibles al usuario, al final después de "---"):
[SCORE_UPDATE: N]  (N entre 0 y 15, escala del CRM — NO 0-100)
[LEAD_DATA: {"country": "...", "industry": "...", "employee_count": N,
  "has_contractors": true/false, "sst_process": "activo|empezando|ninguno",
  "pain_point": "...", "is_decision_maker": true/false, "name": "...",
  "company": "...", "role": "...", "nivel_riesgo_arl": "1-5",
  "numero_contratistas": N}]
[BOOKING_READY]  → cuando score >= 10 O (empleados>20 Y contratistas) O
  urgencia O lead dice "quiero comprar/cotizar/agendar"
[HANDOFF_NEEDED]  → cuando no puedes resolver y se debe escalar a humano

REGLAS CRÍTICAS DE AGENDAMIENTO (MUY IMPORTANTE):
- NUNCA propongas horas específicas en tu texto. NO digas "¿te parece el miércoles a las 10am?"
  ni "te agendo mañana a las 3pm". El sistema envía los horarios disponibles por ti como
  botones después de tu mensaje.
- ANTES de marcar [BOOKING_READY], asegúrate de tener el CORREO del lead en LEAD_DATA.
  Si no lo tienes, primero pídelo amablemente en tu respuesta y NO pongas [BOOKING_READY] todavía.
- Si el lead ya recibió horarios y te responde con una hora (ej "mié 10am"), NO repitas
  pregunta, el sistema lo detecta. Solo confirma con algo corto como "perfecto".
- Si el lead es plan 1-3 (≤250 trabajadores) Y muestra intención de COMPRAR (dice "quiero comprar",
  "mándame link de pago", "cómo empiezo"), cierra agresivo: "Genial, te agendo llamada de 15 min
  con Manuela HOY mismo para firmar y enviarte el link de pago" → [BOOKING_READY]

REGLAS ANTI-LOOP DE PREGUNTAS:
- NUNCA repitas una pregunta que ya hiciste en los últimos 2 mensajes. Si ya le pediste
  el correo en el turno anterior y aún no te lo dio, NO vuelvas a pedírselo literalmente —
  responde su mensaje actual, al final agrega sólo un recordatorio corto: "pd: cuando
  puedas, pásame tu correo" o similar. No dos párrafos pidiendo lo mismo.
- Si la pregunta ya está en el historial, da por sentado que el lead la ignoró o pidió
  más info. Primero responde su duda, después (si aplica) repite suave.

REGLAS DE HONESTIDAD:
- NUNCA adivines el nombre de una persona a partir de su correo electrónico.
  Si solo tienes el email "lmurillo@empresa.com", NO asumas que se llama
  "Luis Murillo". Pregunta: "¿Cuál es tu nombre?" Es mucho peor equivocarse
  que preguntar.
- NUNCA inventes clientes referencia en un sector específico si no tienes evidencia.
  Los clientes que SÍ puedes mencionar son: AES Colombia (energía), CFC (construcción),
  ECAR (farmacéutica), Colgate-Palmolive, Cajasan, Diabonos, Magnetron, Perflex, 3 Castillos.
- Si el lead es de otro sector (telecom, minería, agro, etc.), NO digas "es justo nuestro nicho"
  ni fabriques referencias. Di algo como "tenemos clientes en sectores de alto riesgo
  similares en tema de contratistas/SST, te lo aterrizo en la reunión".

REGLAS CRÍTICAS DE FORMATO:
- NUNCA muestres los tags al usuario en el cuerpo del mensaje
- Coloca TODOS los tags al final después de una línea con ---
- Sin los tags, el mensaje debe leerse natural y fluido

A continuación tienes todo el conocimiento del producto, precios, scoring,
objeciones y perfil ideal del cliente. Úsalo para responder con precisión:
"""

SYSTEM_PROMPT = SYSTEM_PROMPT_BASE + load_knowledge()

# Anthropic prompt caching: el prompt completo (base + knowledge) es estático — se cachea
# y en llamadas subsecuentes cuesta ~10% del input. Reduce costo por lead ~90%.
CACHED_SYSTEM_BLOCKS = [
    {
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }
]


class ConversationalAgent:
    def __init__(self):
        self.anthropic = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def _detect_handoff_request(self, text: str) -> bool:
        t = text.lower()
        return any(re.search(p, t) for p in HANDOFF_KEYWORDS)

    def _match_slot(self, message_text: str, slots: list[dict]) -> dict | None:
        """Match a user reply (text or button label) to one of the offered slots."""
        if not slots:
            return None
        t = message_text.lower().strip()
        labels = meeting_scheduler.format_slots_for_whatsapp(slots)
        for slot, label in zip(slots, labels):
            if label.lower() in t or t in label.lower():
                return slot
        return None

    def _extract_email(self, text: str) -> str | None:
        m = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
        return m.group(0) if m else None

    async def _offer_slots(
        self,
        conversation_id: str,
        phone: str,
        context: dict,
        intro_text: str = "Te ofrezco los horarios disponibles para la reunión de 30 min:",
    ) -> bool:
        """Fetch slots and send them as buttons. Returns True on success."""
        try:
            routing = crm.get_active_routing_config()
            if not routing:
                logger.error("no routing_config for slot offering")
                return False
            slots = await meeting_scheduler.get_available_slots(routing["id"])
            if not slots:
                return False
            labels = meeting_scheduler.format_slots_for_whatsapp(slots)
            context["pending_slots"] = slots
            if intro_text:
                await whatsapp_client.send_text(phone, intro_text)
                crm.save_message(conversation_id, "outbound", intro_text)
            await whatsapp_client.send_interactive_buttons(
                phone,
                "¿Cuál horario te queda mejor?",
                labels,
            )
            crm.update_conversation(
                conversation_id,
                {"status": "booking_offered", "context": context},
            )
            return True
        except Exception as e:
            logger.exception(f"offer_slots failed: {e}")
            return False

    def _is_valid_email(self, email: str | None) -> bool:
        if not email:
            return False
        e = email.strip()
        return "@" in e and "." in e.split("@")[-1] and len(e) > 5

    async def _book_and_confirm(
        self,
        conversation_id: str,
        phone: str,
        slot: dict,
        context: dict,
    ) -> None:
        lead_data = context.get("lead_data") or {}
        email = (lead_data.get("email") or "").strip()

        # Validar email antes de intentar agendar
        booking_retries = context.get("booking_email_retries", 0)
        if not self._is_valid_email(email):
            if booking_retries >= 2:
                await whatsapp_client.send_text(
                    phone,
                    "No he podido validar tu correo. Te conecto con un asesor "
                    "que te ayuda a agendar directamente 👋",
                )
                crm.save_message(conversation_id, "outbound",
                    "No he podido validar tu correo. Te conecto con un asesor.")
                await handoff_manager.initiate_handoff(
                    conversation_id=conversation_id, reason="invalid_email"
                )
                return

            context["booking_email_retries"] = booking_retries + 1
            msg = (
                "Parece que el correo que me diste no es válido para agendar. "
                "¿Me lo puedes confirmar de nuevo? Necesito un correo real "
                "para enviarte el enlace de la reunión."
            )
            await whatsapp_client.send_text(phone, msg)
            crm.save_message(conversation_id, "outbound", msg)
            crm.update_conversation(conversation_id, {
                "status": "collecting_email",
                "context": context,
            })
            return

        try:
            routing = crm.get_active_routing_config()
            meeting = await meeting_scheduler.book_meeting(
                slot=slot,
                lead_data=lead_data,
                routing_config_id=routing["id"] if routing else None,
                conversation_id=conversation_id,
            )
            link = meeting.get("meet_link") or "(te lo compartimos por correo)"
            # Human-friendly time en español (no depende del locale del sistema)
            from datetime import datetime
            DAYS_ES = {
                0: "lunes", 1: "martes", 2: "miércoles", 3: "jueves",
                4: "viernes", 5: "sábado", 6: "domingo",
            }
            MONTHS_ES = {
                1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo",
                6: "junio", 7: "julio", 8: "agosto", 9: "septiembre",
                10: "octubre", 11: "noviembre", 12: "diciembre",
            }
            dt = datetime.fromisoformat(slot["start"])
            h12 = dt.hour % 12 or 12
            period = "AM" if dt.hour < 12 else "PM"
            minute_part = f":{dt.minute:02d}" if dt.minute else ""
            human = (
                f"{DAYS_ES[dt.weekday()]} {dt.day} de {MONTHS_ES[dt.month]}, "
                f"{h12}{minute_part} {period}"
            )
            msg = (
                f"✅ Tu reunión quedó agendada: *{human}*\n\n"
                f"Enlace: {link}\n\n"
                f"Te llegará un recordatorio al correo. ¡Nos vemos pronto!"
            )
            await whatsapp_client.send_text(phone, msg)
            crm.save_message(conversation_id, "outbound", msg)
            context["confirmed_slot"] = slot
            context["meet_link"] = link
            crm.update_conversation(
                conversation_id,
                {"status": "booking_confirmed", "context": context},
            )
        except Exception as e:
            logger.exception(f"book_and_confirm failed: {e}")
            fallback = (
                "Perfecto, anoté tu horario. Un asesor te confirmará en breve con el enlace."
            )
            await whatsapp_client.send_text(phone, fallback)
            crm.save_message(conversation_id, "outbound", fallback)
            await handoff_manager.initiate_handoff(
                conversation_id=conversation_id, reason="bot_confused"
            )

    def _build_messages(self, history: list[dict], user_text: str) -> list[dict]:
        msgs: list[dict] = []
        for h in history:
            role = "user" if h["direction"] == "inbound" else "assistant"
            msgs.append({"role": role, "content": h["body"]})
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def _parse_response(self, raw: str) -> tuple[str, dict[str, Any]]:
        """Split the assistant message into clean text + parsed tags."""
        parts = raw.split("---", 1)
        clean = parts[0].strip()
        tags_blob = parts[1] if len(parts) > 1 else raw

        tags: dict[str, Any] = {}

        m = re.search(r"\[SCORE_UPDATE:\s*(\d+)\]", tags_blob)
        if m:
            tags["score"] = int(m.group(1))

        m = re.search(r"\[LEAD_DATA:\s*(\{.*?\})\]", tags_blob, re.DOTALL)
        if m:
            try:
                tags["lead_data"] = json.loads(m.group(1))
            except Exception as e:
                logger.warning(f"Bad LEAD_DATA JSON: {e}")

        if "[BOOKING_READY]" in tags_blob:
            tags["booking_ready"] = True
        if "[HANDOFF_NEEDED]" in tags_blob:
            tags["handoff_needed"] = True

        # Strip any tags that may have leaked into the visible text
        clean = re.sub(r"\[(SCORE_UPDATE|LEAD_DATA|BOOKING_READY|HANDOFF_NEEDED)[^\]]*\]",
                       "", clean).strip()
        return clean, tags

    async def process_message(
        self, conversation_id: str, phone: str, message_text: str, wa_name: str | None = None
    ) -> None:
        conv = crm.get_conversation(conversation_id)
        if not conv:
            logger.error(f"Conversation {conversation_id} not found")
            return

        # 1) human_active → NO procesar con bot, solo notificar al agente.
        # El mensaje del user ya fue guardado en _ingest_message (main.py).
        if conv.get("status") == "human_active":
            assigned = conv.get("assigned_profile_id")
            if assigned:
                from app.notifications.notifier import notifier
                await notifier.notify_inbound_during_handoff(
                    profile_id=assigned,
                    conversation_id=conversation_id,
                    phone=phone,
                    body=message_text,
                )
            return

        # 2) Detectar petición explícita de humano
        if self._detect_handoff_request(message_text):
            await handoff_manager.initiate_handoff(
                conversation_id=conversation_id, reason="user_requested"
            )
            return

        # 2.5) Si ya estamos en booking_offered, intentar casar el slot elegido
        current_status = conv.get("status")
        context_pre = conv.get("context") or {}
        if current_status == "booking_offered":
            slots = context_pre.get("pending_slots") or []
            selected = self._match_slot(message_text, slots)
            if selected:
                await self._book_and_confirm(
                    conversation_id=conversation_id,
                    phone=phone,
                    slot=selected,
                    context=context_pre,
                )
                return

        # 2.6) Si estamos esperando correo, intentar capturarlo
        if current_status == "collecting_email":
            email = self._extract_email(message_text)
            if email:
                ld = context_pre.get("lead_data") or {}
                ld["email"] = email
                context_pre["lead_data"] = ld
                lead_id = conv.get("lead_id")
                if lead_id:
                    try:
                        crm.update_lead(lead_id, {"email": email})
                    except Exception as e:
                        logger.warning(f"lead email update: {e}")
                await self._offer_slots(
                    conversation_id=conversation_id,
                    phone=phone,
                    context=context_pre,
                    intro_text="¡Perfecto, gracias! Ya casi listos.",
                )
                return

        # 3) Construir contexto y llamar a Claude
        history = crm.get_message_history(conversation_id)
        messages = self._build_messages(history, message_text)

        # Inyectar contexto dinámico (plantilla descargada) como bloque system
        # adicional SIN cache_control → preserva el cache del bloque principal.
        system_blocks = list(CACHED_SYSTEM_BLOCKS)
        downloaded = (context_pre.get("downloaded_template")
                      if isinstance(context_pre, dict) else None) or {}
        tpl_title = conv.get("template_title") or downloaded.get("title")
        tpl_slug = conv.get("template_slug") or downloaded.get("slug")
        tpl_desc = downloaded.get("description")
        if tpl_title or tpl_slug:
            ref = tpl_title or tpl_slug
            desc_part = f" (contenido: {tpl_desc[:300]})" if tpl_desc else ""
            system_blocks.append({
                "type": "text",
                "text": (
                    f"CONTEXTO ADICIONAL DE ESTA CONVERSACIÓN:\n"
                    f"Este lead llegó después de descargar la plantilla "
                    f"'{ref}'{desc_part} desde nuestro landing. "
                    f"Úsalo para personalizar: pregúntale QUÉ pensaba hacer "
                    f"con esa plantilla, qué dolor quería resolver, y aterriza "
                    f"tu pitch en el problema específico que esa plantilla "
                    f"documenta. NO repitas el nombre de la plantilla en cada "
                    f"mensaje (solo si es natural), y NO expliques Verifty de "
                    f"forma genérica — usa el contexto de la plantilla."
                ),
            })

        usage_info: dict[str, Any] = {}
        try:
            t0 = time.perf_counter()
            resp = self.anthropic.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=600,
                system=system_blocks,
                messages=messages,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            raw = resp.content[0].text if resp.content else ""
            usage = getattr(resp, "usage", None)
            if usage:
                cr = getattr(usage, "cache_read_input_tokens", 0) or 0
                cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
                input_tokens = usage.input_tokens or 0
                output_tokens = usage.output_tokens or 0
                cost = calculate_cost_usd(
                    model=settings.ANTHROPIC_MODEL,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cr,
                    cache_write_tokens=cw,
                )
                usage_info = {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read_tokens": cr,
                    "cache_write_tokens": cw,
                    "cost_usd": cost,
                    "model": settings.ANTHROPIC_MODEL,
                    "latency_ms": latency_ms,
                }
                logger.info(
                    f"tokens in={input_tokens} out={output_tokens} "
                    f"cache_read={cr} cache_write={cw} "
                    f"cost=${cost:.6f} latency={latency_ms}ms"
                )
        except Exception as e:
            logger.exception(f"Anthropic error: {e}")
            retries = (conv.get("bot_retries") or 0) + 1
            crm.update_conversation(conversation_id, {"bot_retries": retries})
            if retries >= settings.MAX_BOT_RETRIES:
                await handoff_manager.initiate_handoff(
                    conversation_id=conversation_id, reason="bot_confused"
                )
            return

        clean, tags = self._parse_response(raw)
        logger.info(f"Bot tags for {conversation_id}: {tags}")

        # 4) Aplicar tags al CRM
        context = conv.get("context") or {}
        lead_id = conv.get("lead_id")

        if "lead_data" in tags and lead_id:
            merged = {**context.get("lead_data", {}), **tags["lead_data"]}
            context["lead_data"] = merged

            lead_update: dict[str, Any] = {}
            if merged.get("name"):
                parts = str(merged["name"]).split(" ", 1)
                lead_update["first_name"] = parts[0]
                if len(parts) > 1:
                    lead_update["last_name"] = parts[1]
            if merged.get("company"):
                lead_update["company_name"] = merged["company"]
            if merged.get("role"):
                lead_update["job_title"] = merged["role"]
            if merged.get("industry"):
                lead_update["industry"] = merged["industry"]
                lead_update["sector"] = merged["industry"]
            if merged.get("employee_count"):
                lead_update["employee_count"] = str(merged["employee_count"])
                lead_update["numero_trabajadores"] = str(merged["employee_count"])
            if "has_contractors" in merged:
                lead_update["has_contractors"] = bool(merged["has_contractors"])
            if merged.get("city"):
                lead_update["city"] = merged["city"]
            if merged.get("pain_point"):
                lead_update["main_need"] = merged["pain_point"]
            if lead_update:
                try:
                    crm.update_lead(lead_id, lead_update)
                except Exception as e:
                    logger.warning(f"update_lead partial failure: {e}")

        score = tags.get("score")
        breakdown = None
        if "lead_data" in context:
            computed_score, breakdown = calculate_score(context["lead_data"])
            if score is None:
                score = computed_score

        if score is not None:
            context["score"] = score
            if lead_id:
                lead_fields = {"score": score}
                if breakdown:
                    lead_fields["score_breakdown"] = breakdown
                try:
                    crm.update_lead(lead_id, lead_fields)
                except Exception as e:
                    logger.warning(f"lead score update failed: {e}")

        # Business rule: empresa >20 empleados + contratistas = convertir a reu SÍ O SÍ
        ld = context.get("lead_data", {})
        emp_count = ld.get("employee_count")
        try:
            emp_n = int(emp_count) if emp_count else 0
        except (ValueError, TypeError):
            emp_n = 0
        force_booking = (
            emp_n > 20 and ld.get("has_contractors") is True
        ) or (score is not None and score >= 10)
        if force_booking and not tags.get("handoff_needed"):
            tags["booking_ready"] = True

        # 5) Handoff requerido por el modelo
        if tags.get("handoff_needed"):
            if clean:
                await whatsapp_client.send_text(phone, clean)
                crm.save_message(
                    conversation_id, "outbound", clean, usage=usage_info
                )
            await handoff_manager.initiate_handoff(
                conversation_id=conversation_id, reason="bot_confused"
            )
            crm.update_conversation(
                conversation_id, {"context": context, "score": score or 0}
            )
            return

        # Auto-capturar email si vino dentro del mensaje del lead (antes del booking)
        inbound_email = self._extract_email(message_text)
        ld = context.get("lead_data") or {}
        if inbound_email and not ld.get("email"):
            ld["email"] = inbound_email
            context["lead_data"] = ld
            if lead_id:
                try:
                    crm.update_lead(lead_id, {"email": inbound_email})
                except Exception as e:
                    logger.warning(f"auto email update failed: {e}")

        booking_trigger = tags.get("booking_ready") or (
            score is not None and score >= settings.QUALIFIED_SCORE_THRESHOLD
        )

        # Si NO hay correo y el modelo quiere agendar, primero pedimos correo
        if booking_trigger and not (context.get("lead_data") or {}).get("email"):
            # Respuesta del modelo + pedir correo explícito si el modelo olvidó pedirlo
            needs_email_prompt = "correo" not in (clean or "").lower() and "email" not in (clean or "").lower()
            final_text = clean or ""
            if needs_email_prompt:
                extra = (
                    "Antes de agendarte, regálame tu *correo* por favor, "
                    "para enviarte el enlace de la reunión."
                )
                final_text = (final_text + "\n\n" + extra).strip() if final_text else extra
            if final_text:
                await whatsapp_client.send_text(phone, final_text)
                crm.save_message(
                    conversation_id, "outbound", final_text, usage=usage_info
                )
            crm.update_conversation(
                conversation_id,
                {
                    "context": context,
                    "score": score or conv.get("score", 0),
                    "status": "collecting_email",
                    "bot_retries": 0,
                },
            )
            return

        # Si hay correo y booking es requerido → ofrece slots (una sola vez)
        # Ignoramos el texto de Claude aquí: a veces inventa horas falsas.
        # Usamos un intro canned para que los slots reales (botones) manden.
        if booking_trigger and current_status not in ("booking_offered", "booking_confirmed"):
            canned_intro = (
                "¡Perfecto! Te muestro los horarios disponibles para la reunión "
                "(demo de 30 min con nuestro equipo). Selecciona el que mejor te quede:"
            )
            logger.info(f"[booking] offering slots conv={conversation_id} score={score}")
            offered = await self._offer_slots(
                conversation_id=conversation_id,
                phone=phone,
                context=context,
                intro_text=canned_intro,
            )
            if offered:
                crm.update_conversation(
                    conversation_id, {"score": score or 0}
                )
                return
            logger.error(f"[booking] offer_slots FAILED conv={conversation_id}")
            # Si no logramos ofrecer slots, escalamos
            await handoff_manager.initiate_handoff(
                conversation_id=conversation_id, reason="bot_confused"
            )
            return

        # Flujo default: solo responder
        if clean:
            await whatsapp_client.send_text(phone, clean)
            crm.save_message(
                conversation_id, "outbound", clean, usage=usage_info
            )

        next_status = current_status if current_status in (
            "booking_offered", "booking_confirmed", "collecting_email"
        ) else "qualifying"
        crm.update_conversation(
            conversation_id,
            {
                "context": context,
                "score": score or conv.get("score", 0),
                "status": next_status,
                "bot_retries": 0,
            },
        )

        # SYNC: persistir campos clave de context.lead_data al lead en CADA turno,
        # sin depender de que Claude emita [LEAD_DATA]. Esto cubre el caso donde
        # el email/company/etc. llegó por auto-captura o por un tag previo
        # pero no se persiste en turnos posteriores.
        self._sync_lead_from_context(lead_id, context, wa_name=wa_name)

    def _sync_lead_from_context(
        self, lead_id: str | None, context: dict,
        wa_name: str | None = None,
    ) -> None:
        """Persiste campos clave de context.lead_data al lead row.
        Se ejecuta en cada turno para garantizar que nada se pierda."""
        if not lead_id:
            return
        ld = context.get("lead_data") or {}
        if not ld:
            return
        update: dict[str, Any] = {}
        if ld.get("email"):
            update["email"] = str(ld["email"]).strip()
        # Nombre: usar lead_data.name si es real, si no fallback a wa_contact_name
        name = ld.get("name")
        no_validos = {"no confirmado", "sin confirmar", "no especificado", "desconocido", "", "none"}
        if name and str(name).strip().lower() not in no_validos:
            parts = str(name).split(" ", 1)
            update["first_name"] = parts[0]
            if len(parts) > 1:
                update["last_name"] = parts[1]
        elif wa_name and str(wa_name).strip().lower() not in no_validos:
            parts = str(wa_name).strip().split(" ", 1)
            update["first_name"] = parts[0].title()
            if len(parts) > 1:
                update["last_name"] = parts[1].title()
        if ld.get("company"):
            update["company_name"] = str(ld["company"])
        if ld.get("role"):
            update["job_title"] = str(ld["role"])
        if ld.get("industry"):
            update["industry"] = str(ld["industry"])
            update["sector"] = str(ld["industry"])
        if ld.get("employee_count"):
            update["employee_count"] = str(ld["employee_count"])
            update["numero_trabajadores"] = str(ld["employee_count"])
        if ld.get("has_contractors") is not None:
            update["has_contractors"] = bool(ld["has_contractors"])
        if ld.get("pain_point"):
            update["main_need"] = str(ld["pain_point"])[:500]
        if ld.get("city"):
            update["city"] = str(ld["city"])
        if update:
            try:
                crm.update_lead(lead_id, update)
            except Exception as e:
                logger.warning(f"_sync_lead_from_context failed: {e}")


agent = ConversationalAgent()
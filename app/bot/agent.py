from __future__ import annotations
import json
import re
from typing import Any
from anthropic import Anthropic
from app.config import settings
from app.crm.client import crm
from app.whatsapp.client import whatsapp_client
from app.bot.scorer import calculate_score, classify_product_fit
from app.bot.handoff import handoff_manager
from app.bot.scheduler import meeting_scheduler
from app.bot.knowledge_loader import load_knowledge
from app.pricing.catalog import prompt_inyectable
from app.bot.lead_context import build_lead_context_block
from app.bot.pricing import calculate_cost_usd
from app.bot.tools.schemas import TOOLS
from app.bot.tools.dispatcher import dispatch_tool_use
from app.bot.validators import detectar_palabras_prohibidas
from app.outbound.quote import send_quote_email
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

SST_PURCHASE_URL = "https://sst.verifty.com/planes"

SYSTEM_PROMPT_BASE = """═══════════════════════════════════════════════════════════
Eres Vera, vendedora consultiva de Verifty por WhatsApp.
Vendes como venden Santiago y Manuela (los fundadores): escuchas
primero, espejas el proceso del cliente, recomiendas con confianza
y cierras siempre con un próximo paso concreto. El playbook de
ventas que tienes abajo sale de sus reuniones reales — es tu guía.
═══════════════════════════════════════════════════════════

INVIOLABLES (si rompes una, fallaste en tu trabajo)
═══════════════════════════════════════════════════════════

I-1. UNA pregunta por mensaje. Nunca dos. Nunca tres con bullets.

I-2. Máximo 3 oraciones por mensaje. Cero markdown: nada de
     **, *, ##, ni bullets. Tono de WhatsApp colombiano natural
     ("regálame", "listo", "un ratico"). Si tu borrador quedó
     de más de 3 oraciones, recórtalo antes de responder.

I-3. NUNCA uses palabras: "obligatorio", "obligatoria",
     "Mintrabajo te exige", "ARL te pide", "multa", "auditoría
     te van a pedir", "incumplimiento", "500 SMMLV". Ni en
     mensaje al cliente ni en razon_eleccion del tool.
     La urgencia solo puede venir de algo que EL CLIENTE contó.

I-4. A "Verifty Flow" y "Verifty Capacitaciones" NUNCA les des
     precio ni los cotices por chat: contratistas, ingresos,
     permisos y capacitaciones enterprise se venden SOLO en
     reunión (Camino B) — agenda la cita. TÚ solo vendes con
     link los planes self-serve de Verifty SST con IA (Emprende IA,
     Crece IA, Consolida IA) — TODOS traen VERA (la IA) incluida y
     PRUEBA GRATIS de 3 días. VERA arma y mantiene el SG-SST.

I-5. Cuando recomiendes plan y el cliente acepte, llama SIEMPRE
     el tool recomendar_plan_y_cerrar. NUNCA mandes link genérico
     /planes — eso es perder venta.

I-6. NO eres consultora de normas SST. Si preguntan cómo
     implementar una norma o qué dice un decreto, responde:
     "Lo siento, soy asistente para clientes de Verifty, no de
     consultoría en normas SST. Si quieres ver cómo Verifty te
     ayuda a organizarte, con gusto." Nada más.

I-7. NUNCA des precio sin volumen. Si piden precio antes de
     decirte cuántas personas son: "Te daría un precio equivocado
     porque no se adapta a tu operación. ¿Cuántas personas son?"

I-8. CONOCE A LA PERSONA PRIMERO. En tu primer mensaje preséntate
     ("Soy Vera, del equipo de Verifty") y pregunta su NOMBRE antes
     que nada ("¿con quién tengo el gusto?"). Trátala por su nombre
     el resto de la charla. Nunca recomiendes plan ni agendes sin
     saber al menos NOMBRE y EMPRESA.

I-9. CAPTURA TODO AL EXPEDIENTE. Cada dato que aprendas del lead
     (nombre, empresa, cargo, sector, # personas, contratistas,
     dolor, cómo lo hacen hoy) lo emites en [LEAD_DATA] EN EL MISMO
     turno en que lo escuchas — no lo dejes para después ni lo
     olvides. Ese expediente alimenta el CRM; un lead sin nombre ni
     empresa capturados es un trabajo a medias.

═══════════════════════════════════════════════════════════
LOS DOS CAMINOS (decide temprano y no los mezcles)
═══════════════════════════════════════════════════════════

CAMINO A — TICKET PEQUEÑO (self-serve): empresa colombiana de
hasta ~130 trabajadores, sin operación pesada de contratistas,
o consultor SST independiente. Objetivo: resolver dudas rápido,
recomendar UN plan del catálogo y cerrar con el link de pago.
Después del pago la persona debe CREAR SU EMPRESA con el link
que le llega al correo — si alguien te dice "pagué y no puedo
entrar" o "pagué y no me llegó nada", llama escalar_a_humano de
inmediato con esa razón (es plata ya cobrada, prioridad máxima).

CAMINO B — ICP (cliente grande): cualquiera de estas señales →
tu objetivo YA NO es vender el plan, es VENDER LA REUNIÓN:
  - más de ~130 trabajadores, o multi-sede / multi-planta
  - maneja contratistas, portería, permisos de trabajo, ingresos
  - sectores: energía, construcción, transporte, logística,
    hidrocarburos, plantas industriales, puertos, farma
  - pregunta por Flow, capacitaciones masivas o integraciones
  - internacional grande (fuera de CO/MX con ≥70 trabajadores)
En Camino B: NO cotices. Vende la cita así: "eso que me cuentas
es exactamente lo que resolvemos con [producto], y como cada
empresa tiene un ADN diferente, lo que hacemos es una reunión
corta donde te lo mostramos montado sobre TU proceso, sin
compromiso". Ofrece también la prueba de concepto gratis si
notas dudas. Llama escalar_a_demo cuando acepte.

EXPEDIENTE ICP (crítico en Camino B): antes o durante el
agendamiento captura en [LEAD_DATA] TODO lo que puedas: empresa,
sector, ciudad, # empleados, si tiene contratistas y cuántos,
volumen mensual (permisos/ingresos/personas), cómo lo hacen hoy
(papel/Excel/otra herramienta y cuál), el dolor EN PALABRAS DEL
CLIENTE (pain_point), producto a venderle (product_fit), si es
quien decide, y cómo nos encontró. Santiago y Manuela llegan a
esa reunión con tu expediente — que no les falte nada.

═══════════════════════════════════════════════════════════
FLUJO DE CONVERSACIÓN
═══════════════════════════════════════════════════════════

FASE 0 — PRESÉNTATE Y CONOCE A LA PERSONA (primer turno, SIEMPRE)

Saluda cálido, di en una línea quién eres y pregunta el NOMBRE
antes de cualquier otra cosa: "¡Hola! Soy Vera, del equipo de
Verifty 😊 ¿con quién tengo el gusto?". Apenas te lo diga, emite
[LEAD_DATA: {"name": "..."}] y de ahí en adelante háblale por su
nombre. Conocer a la persona va primero; no dispares la pregunta
de oro sin saber su nombre.

FASE 1 — DESCUBRIMIENTO (escucha primero, UNA pregunta por turno)

La pregunta de oro (hazla apenas sepas su nombre): "¿Qué los tiene
buscando una solución justo ahora?" — ESTA ES LA PREGUNTA QUE MÁS
IMPORTA; sin esa respuesta vendes a ciegas.
Datos que necesitas (en este orden, sin interrogatorio) — y CADA
uno que aprendas lo emites en [LEAD_DATA] en ese mismo turno:
  1. Nombre y cargo de la persona (name, role)
  2. Empresa + sector (company, industry) — pregúntalo temprano:
     "¿y en qué empresa estás?"
  3. Trabajadores directos Y si manejan contratistas (¡son dos
     números distintos! empresas contratistas ≠ sus trabajadores)
  4. El detonante de HOY (crecimiento, cliente que exige,
     accidente, visita, herramienta que se quedó corta) → pain_point
  5. Cómo lo hacen hoy (papel, Excel, Drive, otra plataforma)
Técnica del espejo: cuando entiendas su proceso, repíteselo en
una frase y pide confirmación ("o sea que hoy X, luego Y, ¿cierto?").
Valida el dolor como típico: "ese es el dolor de la mayoría de
empresas de tu sector". Tras 4-5 turnos decide el camino con lo
que tengas.

ESTILO (que NO se sienta formulario): estos datos los vas TEJIENDO
en la charla, no los pides en fila como robot. Reacciona a cada
respuesta con una frase humana antes de la siguiente pregunta
("ah, construcción, uf ahí los contratistas son un dolor de
cabeza…"). Una sola cosa a la vez, sin bombardear. Si el cliente
ya te soltó dos datos juntos, no vuelvas a preguntarlos. La meta
es que se sienta una conversación con alguien que le interesa la
persona, no un cuestionario — y en el fondo, sin que se note, vas
armando el expediente completo del CRM.

FASE 2 — RECOMENDACIÓN (solo Camino A: UN plan, con confianza)

Por trabajadores totales: ≤27 EMPRENDE_IA · ≤79 CRECE_IA ·
≤215 CONSOLIDA_IA · >215 = Camino B. Todos traen VERA (IA) incluida
y prueba gratis 3 días — es el gancho de cierre. SOLO si el cliente mencionó explícitamente un módulo
que no viene en su plan, sube al mínimo que lo incluye (la razón
del upsell siempre viene del cliente). Recomienda UNO, con su
precio del catálogo, y cállate: "Para 50 trabajadores, el Crece IA
es lo que les sirve — trae VERA incluida, cuesta [precio del catálogo]
al mes y lo puedes probar gratis 3 días. ¿Lo activamos?"

FASE 3 — CIERRE (asume la venta)

Camino A: al primer "sí/dale/ok" llama INMEDIATAMENTE el tool
recomendar_plan_y_cerrar. Sin más confirmaciones. Si no dijo
mensual o anual, asume mensual.
Camino B: al primer interés en la reunión llama escalar_a_demo.
Todo cierre deja un próximo paso con fecha — nunca "quedamos
atentos".

FASE 4 — OBJECIONES (guiones probados del playbook)

A. "Está caro" → ROI en sus términos: "son X pesos al día, menos
   que una hora de consultor SST" (usa precio_dia_cop).
B. "¿Es legal la firma digital?" → "La firma electrónica tiene la
   misma validez que el papel; lo que importa es demostrar quién
   firmó, y por eso usamos foto con cédula o Face ID. Lo
   validamos con abogados."
C. "¿Es seguro / dónde quedan los datos?" → "Todo en la nube con
   respaldo diario. Nuestro cliente insignia es AES, la tercera
   generadora de energía del país — sus estándares nos exigen."
D. "Ya tengo una herramienta (de la ARL / gratis)" → "¿Y te valida
   el contenido de los documentos o solo te los guarda? Nosotros
   verificamos que la planilla sea real, vigente y de la persona."
E. "Uso Excel/carpetas" → UN punto: "sin trazabilidad ni firmas,
   el día que te pidan la evidencia toca rezar. Eso es lo que
   digitalizamos."
F. "Déjame pensarlo" → UNA pregunta: "¿qué te haría falta para
   decidir?" Solo hay 3 reales: presupuesto, decisor, timing.
   Si es el jefe → "¿le mando cotización por correo?" (tool) o
   mejor: "¿los metemos a los dos en una llamada corta?"
G. Feature que no existe → honestidad: "eso hoy no lo tenemos
   así, pero muchas cosas que piden los clientes terminan siendo
   herramientas — lo anoto para el equipo". Jamás finjas que existe.
Después de 2 objeciones sin avanzar: cierre cordial y silencio
(el follow-up automático hace el resto).

FASE 5 — STOP SIGNALS

"entendí" / "espero el link" / "lo reviso" / "quedamos así" →
"Perfecto, quedo pendiente. Cualquier duda me escribes." Y silencio.

═══════════════════════════════════════════════════════════
URGENCIA HONESTA (CRÍTICO)
═══════════════════════════════════════════════════════════

Si el cliente mencionó algo concreto (visita programada, cliente
grande que le exige, accidente reciente, fecha límite propia),
úsalo en el cierre con sus palabras. Si NO mencionó nada, NO
inventes urgencia. Cero. Nunca "es importante actuar rápido"
sin contexto que el cliente trajo.

═══════════════════════════════════════════════════════════
PRUEBA SOCIAL (por vertical, con nombre — úsala una vez, no la repitas)
═══════════════════════════════════════════════════════════

Energía/estándares → AES Colombia, la tercera generadora de
energía del país. Farma/planta industrial → Laboratorios ECAR.
Construcción → constructora de más de 2.000 empleados (CFC).
Historia de urgencia legítima (solo si el dolor es contratistas):
"a un cliente le pasó que un contratista afiliaba a la ARL el
día uno y desafiliaba al tercer día — se dieron cuenta el día
del accidente. Eso es lo que el sistema evita solo."

═══════════════════════════════════════════════════════════
HERRAMIENTAS DISPONIBLES (LLAMA UNA POR TURNO)
═══════════════════════════════════════════════════════════

- recomendar_plan_y_cerrar — Camino A: cliente acepta un plan
- escalar_a_demo — Camino B: ICP acepta reunión/POC
- pedir_cotizacion_por_correo — cliente pide PDF explícito
- escalar_a_humano — lo pide, urgencia real, pagó y no puede
  entrar, o 2 objeciones sin avanzar

═══════════════════════════════════════════════════════════
COSAS QUE NO EXISTEN PARA TI (NUNCA MENCIONES)
═══════════════════════════════════════════════════════════

- Precios de Flow, Capacitaciones enterprise o Corporativo
- NUNCA menciones "setup" ni "implementación" como costos en Camino A
- Descuentos fuera del anual del catálogo, cupones
- Garantías que no estén en el knowledge

═══════════════════════════════════════════════════════════
LEADS INTERNACIONALES (FUERA DE CO/MX)
═══════════════════════════════════════════════════════════

- < 70 trabajadores → vende con disclaimer: "está optimizado para
  Colombia pero el SG-SST aplica en tu país; el cobro es en COP
  por Mercado Pago."
- ≥ 70 trabajadores → Camino B (escalar_a_demo, motivo
  lead_internacional_grande).

═══════════════════════════════════════════════════════════
TAGS LEGACY (TODAVÍA EN USO, NO MIGRADOS A TOOLS)
═══════════════════════════════════════════════════════════

[SCORE_UPDATE: N]  → N entre 0 y 15
[LEAD_DATA: {"country": "...", "city": "...", "industry": "...", "employee_count": N,
  "has_contractors": true/false, "sst_process": "activo|empezando|ninguno",
  "pain_point": "...", "is_decision_maker": true/false, "name": "...",
  "email": "...", "company": "...", "role": "...", "nivel_riesgo_arl": "1-5",
  "numero_contratistas": N, "product_fit": "sst|flow|unknown"}]
Emite [LEAD_DATA] cada vez que aprendas un dato nuevo del lead —
SIEMPRE que el cliente diga su nombre o su empresa, emítelo en ese
turno (name, company). No esperes a tener todo; cada dato suelto
va al CRM. En Camino B ese JSON es el expediente con el que el
equipo llega a la reunión: pain_point en las palabras del cliente,
siempre. Un lead sin name ni company es un expediente incompleto.

═══════════════════════════════════════════════════════════

A continuación tienes el catálogo (fuente única de verdad),
el knowledge del producto, y el contexto persistente del lead actual.
"""


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
        if "[SST_READY]" in tags_blob:
            tags["sst_ready"] = True

        m = re.search(r"\[PRODUCT_FIT:\s*(sst|flow|unknown)\]", tags_blob, re.IGNORECASE)
        if m:
            val = m.group(1).lower()
            tags["product_fit"] = {"sst": "verifty_sst", "flow": "verifty_flow"}.get(val, val)

        m = re.search(r"\[SEND_QUOTE:\s*(\{.*?\})\]", tags_blob, re.DOTALL)
        if m:
            try:
                tags["send_quote"] = json.loads(m.group(1))
            except Exception as e:
                logger.warning(f"Bad SEND_QUOTE JSON: {e}")

        m = re.search(r"\[PLAN_RECOMENDADO:\s*([A-Z]+)\]", tags_blob, re.IGNORECASE)
        if m:
            tags["plan_recomendado"] = m.group(1).upper()

        # Strip any tags that may have leaked into the visible text
        clean = re.sub(
            r"\[(SCORE_UPDATE|LEAD_DATA|BOOKING_READY|HANDOFF_NEEDED|SST_READY|PRODUCT_FIT|SEND_QUOTE|PLAN_RECOMENDADO)[^\]]*\]",
            "", clean,
            flags=re.DOTALL,
        ).strip()
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
        # Eliminar el mensaje actual si ya fue guardado en BD antes de esta llamada
        # (main.py guarda el inbound antes de invocar process_message)
        if history and history[-1]["body"] == message_text:
            history = history[:-1]

        lead_ctx = build_lead_context_block(context_pre.get("lead_data") or {})
        messages = (lead_ctx or []) + self._build_messages(history, message_text)

        # Construir el system prompt: base + catálogo SST + knowledge base.
        # El bloque completo es determinístico → Anthropic lo cachea desde la segunda llamada.
        system_blocks = [
            {
                "type": "text",
                "text": (
                    SYSTEM_PROMPT_BASE
                    + "\n\n" + prompt_inyectable()
                    + "\n\n" + load_knowledge()
                ),
                "cache_control": {"type": "ephemeral"},
            }
        ]
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
                tools=TOOLS,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            # Extraer bloques de texto y tool calls del contenido mixto
            raw_parts: list[str] = []
            tool_use_blocks: list[Any] = []
            for block in (resp.content or []):
                txt = getattr(block, "text", None)
                if isinstance(txt, str):
                    raw_parts.append(txt)
                elif hasattr(block, "name"):
                    tool_use_blocks.append(block)
            raw = "\n".join(raw_parts)
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

        # Despachar tool calls (M3) — fusiona sobre los tags del texto
        for tc in tool_use_blocks:
            tool_tags = dispatch_tool_use(tc.name, tc.input, context_pre)
            tags.update(tool_tags)

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
            if merged.get("numero_contratistas") is not None:
                lead_update["numero_contratistas"] = str(merged["numero_contratistas"])
            if merged.get("nivel_riesgo_arl"):
                lead_update["nivel_riesgo_arl"] = str(merged["nivel_riesgo_arl"])
            if merged.get("city"):
                lead_update["city"] = merged["city"]
            if merged.get("country"):
                lead_update["country"] = merged["country"]
            if merged.get("pain_point"):
                lead_update["main_need"] = merged["pain_point"]
            if lead_update:
                try:
                    crm.update_lead(lead_id, lead_update)
                except Exception as e:
                    logger.warning(f"update_lead partial failure: {e}")

        if tags.get("plan_recomendado"):
            ld = context.get("lead_data") or {}
            ld["plan_recomendado"] = tags["plan_recomendado"]
            context["lead_data"] = ld

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

        # Determinar product_fit desde tags de Claude + contexto previo
        ld = context.get("lead_data", {})
        if tags.get("product_fit"):
            context["product_fit"] = tags["product_fit"]
        # Si Claude no emitió product_fit todavía, intentar con el clasificador Python
        if not context.get("product_fit") or context.get("product_fit") == "unknown":
            py_fit = classify_product_fit(ld)
            if py_fit != "unknown":
                context["product_fit"] = py_fit
        product_fit = context.get("product_fit") or "unknown"

        # Business rule: empresa >20 empleados + contratistas = convertir a reu Flow SÍ O SÍ
        # Solo aplica a leads Flow (no SST)
        emp_count = ld.get("employee_count")
        try:
            emp_n = int(emp_count) if emp_count else 0
        except (ValueError, TypeError):
            emp_n = 0
        force_booking = (
            product_fit != "verifty_sst"
            and (
                (emp_n > 20 and ld.get("has_contractors") is True)
                or (score is not None and score >= 10)
            )
        )
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

        # 5.3) Cotización por correo
        if tags.get("send_quote") and not tags.get("handoff_needed"):
            qdata = tags["send_quote"]
            q_email = (qdata.get("email") or "").strip()
            q_company = qdata.get("company") or (context.get("lead_data") or {}).get("company") or ""
            q_plan = (qdata.get("plan") or "pro").lower()
            q_price = qdata.get("plan_price")
            q_name = qdata.get("contact_name") or (context.get("lead_data") or {}).get("name") or ""
            q_city = qdata.get("city") or (context.get("lead_data") or {}).get("city") or ""
            q_nit = qdata.get("nit") or ""

            if q_email and "@" in q_email:
                ok = send_quote_email(
                    to_email=q_email,
                    contact_name=q_name,
                    company=q_company,
                    plan=q_plan,
                    plan_price=q_price,
                    city=q_city,
                    nit=q_nit,
                )
                if ok:
                    confirm_msg = (
                        clean
                        or f"Listo, te envié la cotización a {q_email}. "
                           f"Revisa también la carpeta de spam por si acaso 👌"
                    )
                    await whatsapp_client.send_text(phone, confirm_msg)
                    crm.save_message(conversation_id, "outbound", confirm_msg, usage=usage_info)
                    crm.log_activity(
                        phone=phone,
                        title=f"Cotización enviada por correo — Plan {q_plan.title()}",
                        body=f"Correo: {q_email} | Empresa: {q_company} | Plan: {q_plan}",
                    )
                    if lead_id and q_email:
                        try:
                            crm.update_lead(lead_id, {"email": q_email})
                        except Exception:
                            pass
                else:
                    fallback = (
                        clean
                        or "Por ahora no pude enviar el correo. "
                           "Puedes ver los planes en sst.verifty.com/planes 👋"
                    )
                    await whatsapp_client.send_text(phone, fallback)
                    crm.save_message(conversation_id, "outbound", fallback, usage=usage_info)
                crm.update_conversation(
                    conversation_id,
                    {"context": context, "score": score or conv.get("score", 0)},
                )
                return

        # 5.5) Routing SST: si el lead es SST y está listo, enviar link de compra.
        # Usa solo sst_ready (no booking_ready) para evitar conflicto con escalar_a_demo.
        # El guard M2.3 convierte booking_ready→sst_ready si aplica, antes de este punto.
        sst_trigger = (
            product_fit == "verifty_sst"
            and tags.get("sst_ready")
        )
        if sst_trigger and current_status not in ("sst_link_sent", "booking_confirmed"):
            if clean:
                await whatsapp_client.send_text(phone, clean)
                crm.save_message(conversation_id, "outbound", clean, usage=usage_info)
            sst_link_msg = (
                "Puedes ver los planes y comenzar directamente aquí:\n"
                f"👉 {SST_PURCHASE_URL}"
            )
            await whatsapp_client.send_text(phone, sst_link_msg)
            crm.save_message(conversation_id, "outbound", sst_link_msg)
            crm.update_conversation(
                conversation_id,
                {"context": context, "score": score or 0, "status": "sst_link_sent"},
            )
            logger.info(f"[sst] link sent conv={conversation_id} product_fit={product_fit}")

            # M4 — follow-up 24h: registrar timestamp y agendar nudge si aún no compran
            now_iso = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat()
            if lead_id:
                try:
                    crm.update_lead(lead_id, {"last_sst_link_sent_at": now_iso})
                except Exception as e:
                    logger.warning(f"[sst] last_sst_link_sent_at update failed: {e}")
            try:
                from app.outbound.manager import schedule_nudge
                ld_now = context.get("lead_data") or {}
                schedule_nudge(
                    phone=phone,
                    lead_id=lead_id,
                    kind="sst_link_followup",
                    due_in_minutes=24 * 60,
                    payload={
                        "lead_data": ld_now,
                        "plan_recomendado": tags.get("plan_recomendado") or ld_now.get("plan_recomendado", ""),
                    },
                )
            except Exception as e:
                logger.warning(f"[sst] schedule followup nudge failed: {e}")
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

        # Guard: BOOKING_READY solo es válido para leads CORPORATIVO.
        # Aplica tanto a tags del LLM como a force_booking — ambos pasan por aquí.
        # Si el plan es conocido y no es CORPORATIVO, convertimos a SST_READY.
        plan_recomendado_str = (
            (context.get("lead_data") or {}).get("plan_recomendado", "")
            or tags.get("plan_recomendado", "")
            or ""
        ).upper()
        es_plan_self_serve = bool(plan_recomendado_str) and plan_recomendado_str != "CORPORATIVO"
        if tags.get("booking_ready") and es_plan_self_serve:
            logger.warning(
                f"[guard] BOOKING_READY ignorado: plan='{plan_recomendado_str}' "
                f"no es CORPORATIVO. Convirtiendo a SST_READY. conv={conversation_id}"
            )
            tags["booking_ready"] = False
            tags["sst_ready"] = True

        # Guard extendido: bloquear también la rama score cuando el plan es self-serve.
        # Un score alto no debe disparar demo si el lead ya tiene plan EMPRENDE_IA/CRECE_IA/CONSOLIDA_IA.
        if es_plan_self_serve:
            booking_trigger = False
            tags["sst_ready"] = True
        else:
            booking_trigger = (
                product_fit != "verifty_sst"
                and (
                    tags.get("booking_ready")
                    or (score is not None and score >= settings.QUALIFIED_SCORE_THRESHOLD)
                )
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
            # M4.1 — validador modo monitoreo (loguea, no bloquea)
            palabras_malas = detectar_palabras_prohibidas(clean)
            if palabras_malas:
                logger.warning(
                    f"[validator] Palabras prohibidas en respuesta visible: "
                    f"{palabras_malas} conv={conversation_id} texto={clean[:200]}"
                )
            await whatsapp_client.send_text(phone, clean)
            crm.save_message(
                conversation_id, "outbound", clean, usage=usage_info
            )

        next_status = current_status if current_status in (
            "booking_offered", "booking_confirmed", "collecting_email", "sst_link_sent"
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
        if ld.get("country"):
            update["country"] = str(ld["country"])
        if update:
            try:
                crm.update_lead(lead_id, update)
            except Exception as e:
                logger.warning(f"_sync_lead_from_context failed: {e}")


agent = ConversationalAgent()
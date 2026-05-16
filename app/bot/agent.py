from __future__ import annotations
import json
import re
from typing import Any
from anthropic import Anthropic
from app.config import settings
from app.crm.client import crm
from app.whatsapp.client import whatsapp_client
from app.bot.scorer import calculate_score, suggested_plan, can_bot_quote, classify_product_fit
from app.bot.handoff import handoff_manager
from app.bot.scheduler import meeting_scheduler
from app.bot.knowledge_loader import load_knowledge
from app.pricing.catalog import prompt_inyectable
from app.bot.lead_context import build_lead_context_block
from app.bot.pricing import calculate_cost_usd
from app.bot.tools.schemas import TOOLS
from app.bot.tools.dispatcher import dispatch_tool_use
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

SYSTEM_PROMPT_BASE = """Eres Vera, la asesora SST de Verifty por WhatsApp. Conoces el SG-SST al dedillo — eres directa, cercana y eficiente. Eres una asesora consultiva: tu trabajo es ayudar al cliente a elegir el plan correcto, no vender a toda costa pero tampoco ser pasiva. Asumes que el lead ya quiere resolver su problema — tu rol es facilitar la decisión.

═══════════════════════════════════════════════════════════
REGLA #1 — FORMATO (CRÍTICA — NUNCA LA VIOLES)
═══════════════════════════════════════════════════════════

Estás en WhatsApp o chat web. Las personas leen en el celular.

- MÁXIMO 3 oraciones por mensaje. Más información = menos lectura.
- CERO markdown: sin **negrillas**, sin *cursivas*, sin ## títulos, sin bullets.
  Enfatiza con el lenguaje, no con formato.
- Máximo 1 emoji por mensaje, solo si suma. Sin secuencias de emojis.
- Escribe como un colega de confianza, no como un documento corporativo.
- Cuando ya acordaste algo ("te envío la cotización"), NO lo re-expliques. Di "listo" y cierra.

❌ MAL: "Claro, Diego. Te detallo qué trae el Plan STARTER:\n**Módulos incluidos:**\n1. **Empleados**..."
✅ BIEN: "El Starter trae accidentes, ausentismo, IPEVR y capacitaciones. Para 8 trabajadores es exactamente lo que necesitas. ¿Empezamos mensual o anual?"

═══════════════════════════════════════════════════════════
REGLA #2 — DESCUBRIMIENTO
═══════════════════════════════════════════════════════════

Manejas dos rutas:

VERIFTY SST — software SG-SST (21 módulos + VERA IA)
  Para: empresas 1-130 trabajadores que necesitan gestionar SG-SST, y consultores SST
  Compra directa online — sin reunión, sin intermediarios
  Ruta: calificar → recomendar UN plan → usar recomendar_plan_y_cerrar

VERIFTY FLOW — automatización de procesos operativos
  Para: +130 empleados o ≥10 contratistas queriendo automatizar flujos operativos
  Ruta: calificar → usar escalar_a_demo → el sistema agenda la demo

Segmentación en orden:
1. ¿Consultor/especialista/asesor SST? → SST
2. ¿1-130 trabajadores buscando gestionar SG-SST? → SST
3. ¿+130 trabajadores o ≥10 contratistas con foco en procesos operativos? → Flow
4. Si no está claro → pregunta directamente la necesidad.

Datos mínimos para recomendar (recoge en flujo natural, nunca como formulario):
- Nombre y cargo
- Empresa, sector y ciudad/país
- Número de TRABAJADORES TOTALES (todos los que quedarán con SG-SST gestionado, no solo los con login)
- Si manejan contratistas y cuántos
- Situación actual del SG-SST (empezando, Excel, otro sistema)
- Necesidad principal

Con trabajadores totales + sector ya tienes lo suficiente para recomendar.

═══════════════════════════════════════════════════════════
REGLA #3 — RECOMENDACIÓN POR LÍMITE DURO
═══════════════════════════════════════════════════════════

El catálogo define límites exactos por plan. Lógica:
- Elige el plan más barato que cubre: trabajadores totales, sedes, contratistas y API/SSO.
- Recomienda UN solo plan. No listes todos.
- Explica por qué ese plan: en qué falla el de abajo y por qué el de arriba sería gastar de más.
- Si necesitan API o SSO → siempre CORPORATIVO, sin importar el tamaño.
- Para ver todos los planes: sst.verifty.com/planes

El límite es TRABAJADORES TOTALES = sin login + con login. Ambos cuentan para el techo del plan.

═══════════════════════════════════════════════════════════
REGLA #4 — MODELO HÍBRIDO C: NO ESCALES PROACTIVAMENTE
═══════════════════════════════════════════════════════════

Esta regla aplica SIEMPRE en conjunto con la Regla #3:

Primera recomendación: el plan más barato que cubre los trabajadores.
Escalar de plan: SOLO si el lead menciona EXPLÍCITAMENTE un módulo que NO está en el plan recomendado.

CORRECTO:
- Lead de 8 trabajadores → recomienda Starter (10 trabajadores) aunque tengas Pro disponible.
- Lead de 8 trabajadores que dice "necesitamos salud ocupacional y exámenes médicos"
  → salud ocupacional no está en Starter → subir a Pro y explicar por qué.

INCORRECTO:
- Lead de 8 trabajadores → "y para tener salud ocupacional podrían considerar el Pro" (NO lo digas si no te lo pidieron).
- Mencionar módulos premium proactivamente para vender el plan más caro.

Si el lead pregunta "¿qué incluye el Pro?" → responde honestamente. Pero no lo empujes.
Si el lead dice "¿necesito el Pro?" → pregúntale si necesita salud ocupacional, objetivos e indicadores o reportes ejecutivos. Solo si la respuesta es sí → recomienda Pro.

═══════════════════════════════════════════════════════════
REGLA #5 — ASUMIR VENTA
═══════════════════════════════════════════════════════════

Trata al lead como alguien que YA quiere resolver su problema. No pidas permiso para vender.

En vez de: "¿Les gustaría conocer los planes?" → usa: "Para 8 trabajadores el Starter es lo que necesitas. ¿Empezamos mensual o con descuento anual?"

En vez de: "¿Quieren que te cuente más?" → usa: "Tienes accidentes, ausentismo y la IPEVR cubiertos desde el día 1. ¿Arrancamos?"

Cuando ya conoces el número de trabajadores y el sector:
- Da la recomendación directa.
- Pregunta mensual vs anual (no si quieren comprar).
- Si dicen "sí" a cualquier cosa → usa recomendar_plan_y_cerrar de inmediato.

═══════════════════════════════════════════════════════════
REGLA #6 — MANEJO DE OBJECIONES
═══════════════════════════════════════════════════════════

A) "Es muy caro":
   - Fracciona: "El Pro son $20.000 al día — menos que el almuerzo del responsable SST."
   - Compara: "¿Cuánto pagan hoy por el consultor externo o cuántas horas de Excel al mes?"
   - Puerta de entrada: "Si quieren empezar sin compromiso: el Basic les da la base sin mayor inversión."

B) "Ya usamos Excel" / "ya tenemos algo":
   - "¿Cuánto tiempo les toma actualizar la matriz de riesgos en Excel? Nuestros clientes lo reducen 70% desde el primer mes."
   - "¿Su Excel genera automáticamente los planes de acción cuando identifican un riesgo inaceptable? ¿Alerta cuando vence una revisión?"

C) "No estamos obligados" / "somos pequeños":
   - "Toda empresa en Colombia con al menos 1 empleado tiene SG-SST obligatorio por el Decreto 1072. El nivel de cumplimiento varía, pero la obligación existe."
   - Pero enmarca el valor, no el miedo: "Con 5 trabajadores, el Starter les da organización documental, accidentes y capacitaciones en un solo lugar — sin Excel, sin papel."

D) "Necesito pensarlo" / "lo consulto con mi jefe":
   - "Claro, ¿cuándo tienen la reunión para decidirlo? Así les preparo algo concreto."
   - "¿Hay algo que no les quedó claro? Una duda sin resolver es lo único que retrasa esto."
   - "Mientras tanto, tienen un plan Basic gratuito para explorar la plataforma sin costo."

E) "Tenemos consultor SST externo":
   - "¿Cuánto les cobra? VERA Pro son $199.000 al mes y opera la plataforma 24/7. No reemplaza al consultor para visitas, pero sí reduce lo que le pagan por horas de gestión administrativa."

═══════════════════════════════════════════════════════════
REGLA #7 — URGENCIA HONESTA (PROHIBIDA LA VENTA POR MIEDO)
═══════════════════════════════════════════════════════════

PROHIBIDO — estas frases o variantes similares nunca deben aparecer en tu respuesta:
- "el Mintrabajo los puede multar", "sanción de 500 SMMLV", "$700 millones de multa"
- "sin SG-SST están incumpliendo y pueden ser sancionados"
- "la ARL les puede quitar la cobertura"
- Cualquier amenaza, multa o sanción como argumento de venta

PERMITIDO — urgencia honesta basada en valor y realidad operativa:
- "Con 15 trabajadores ya tienen visitas de la ARL — un sistema organizado hace que esa visita sea tranquila."
- "Si ocurriera un accidente hoy, ¿tienen el expediente completo para la investigación? Con Verifty sí."
- "¿Cuánto tiempo de su equipo se va en mantener el Excel actualizado? Eso es costo real."
- "Les toca la autoevaluación de Res. 0312 este año — hacerla en papel vs hacerla en el sistema son mundos diferentes."

═══════════════════════════════════════════════════════════
REGLA #8 — CIERRE CON LINK
═══════════════════════════════════════════════════════════

Cuando el lead SST confirma que quiere empezar (o cuando detectas señal clara de cierre):
- Usa recomendar_plan_y_cerrar — el sistema envía el link de compra.
- Colombia → precios en COP. Otro país → escalar para cotizar en USD.
- Precios fijos — sin negociación ni descuentos adicionales.
- Ver todos los planes: sst.verifty.com/planes
- Descuento anual: 10% (pago 12 meses anticipado) — mencionarlo cuando pregunten por precio.

Señales de cierre que activan recomendar_plan_y_cerrar:
- "sí, me interesa", "cómo empiezo", "cómo pago", "qué necesito para comprar"
- Lead confirma trabajadores y dice algo afirmativo
- Lead pregunta por precio de un plan específico después de conocer la propuesta

═══════════════════════════════════════════════════════════
REGLA #9 — NO HAY SETUP EN SST
═══════════════════════════════════════════════════════════

SST es self-service: compra online y empieza inmediatamente.
NUNCA menciones costos de setup, implementación ni capacitación para SST.
Si preguntan: no hay costo adicional — todo está en la mensualidad.

═══════════════════════════════════════════════════════════
REGLA #10 — SEÑALES DE STOP
═══════════════════════════════════════════════════════════

Estas frases indican que la conversación terminó — responde brevemente y PARA:
- "ya vi los planes", "voy a pensarlo", "me comunico después", "esperamos la cotización"
- "gracias por la info", "lo consulto con mi jefe", "te escribo luego"

Responde: "Perfecto, quedo pendiente. Cualquier duda me escribes." Y no agregues más.

═══════════════════════════════════════════════════════════
REGLA #11 — ESCALADA Y LEADS INTERNACIONALES
═══════════════════════════════════════════════════════════

Usa escalar_a_humano cuando:
- Urgencia real: auditoría inminente, accidente grave, crisis operativa
- Empresa >1000 empleados
- El lead pide hablar con un humano explícitamente
- 2 intentos consecutivos sin resolver

Leads fuera de Colombia:
- Precios en USD — usa escalar_a_humano para que el equipo confirme la tarifa exacta.
- No cites Res. 0312/2019, Decreto 1072 ni GTC-45 como normas obligatorias en su país.
- Di: "Verifty SST aplica para gestión SST según la normativa local de tu país."

═══════════════════════════════════════════════════════════
ANTI-PATRONES (NUNCA HAGAS ESTO)
═══════════════════════════════════════════════════════════

- NUNCA inventes clientes referencia. Los reales: AES Colombia, CFC, ECAR, Colgate-Palmolive,
  Cajasan, Diabonos, Magnetron, Perflex, 3 Castillos.
- NUNCA inventes precios, planes o módulos fuera del catálogo.
- NUNCA menciones precios de Verifty Flow en conversaciones SST.
- NUNCA uses un correo que el lead no te haya dado explícitamente.
- NUNCA uses markdown — estás en WhatsApp.
- NUNCA propongas horarios para reuniones Flow — el sistema envía los botones.
- NUNCA menciones "ENTERPRISE", "BUSINESS" u otro plan que no exista en el catálogo.
- NUNCA menciones multas, sanciones, Mintrabajo o ARL como argumento de venta (ver Regla #7).

═══════════════════════════════════════════════════════════
HERRAMIENTAS DISPONIBLES — ACCIONES TERMINALES
═══════════════════════════════════════════════════════════

Tienes 4 herramientas. El sistema las ejecuta automáticamente.

recomendar_plan_y_cerrar — Lead SST listo para comprar self-serve
  Cuándo: tienes trabajadores + sector + señal de cierre
  Parámetros: plan (BASIC|STARTER|PRO|PLUS), ciclo (mensual|anual), razon_eleccion (≤200 chars)
  razon_eleccion: basada en trabajadores y módulos concretos. PROHIBIDO: multas, Mintrabajo, ARL.

escalar_a_demo — Lead Flow o Corporativo SST
  Cuándo: >130 empleados, ≥10 contratistas, proceso operativo complejo, o Corporativo SST
  Parámetros: motivo, num_empleados (opcional), pais (opcional)
  NUNCA propongas horarios en texto — el sistema envía los disponibles.

pedir_cotizacion_por_correo — Lead pide propuesta formal
  Cuándo: el lead pide cotización por escrito y ya tienes su correo
  Parámetros: email, plan, company (obligatorios), contact_name (opcional)

escalar_a_humano — Handoff a asesor humano
  Cuándo: urgencia real, solicitud explícita de humano, lead internacional, o 2 intentos sin resolver
  Parámetros: motivo, resumen_para_humano (≤300 chars)

═══════════════════════════════════════════════════════════
TAGS DE DATOS (internos — siempre al final, después de "---")
═══════════════════════════════════════════════════════════

Emite estos tags incluso cuando uses una herramienta:

[SCORE_UPDATE: N]  → N entre 0 y 15
[LEAD_DATA: {"country": "...", "city": "...", "industry": "...", "employee_count": N,
  "has_contractors": true/false, "sst_process": "activo|empezando|ninguno",
  "pain_point": "...", "is_decision_maker": true/false, "name": "...",
  "email": "...", "company": "...", "role": "...", "nivel_riesgo_arl": "1-5",
  "numero_contratistas": N, "product_fit": "sst|flow|unknown"}]
[PRODUCT_FIT: sst|flow]
[PLAN_RECOMENDADO: CODIGO]  → BASIC | STARTER | PRO | PLUS | CORPORATIVO (respaldo)

A continuación tienes el catálogo de planes (fuente única de verdad) y el knowledge completo.
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
                if hasattr(block, "text"):
                    raw_parts.append(block.text)
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
        # Un score alto no debe disparar demo si el lead ya tiene plan BASIC/STARTER/PRO/PLUS.
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
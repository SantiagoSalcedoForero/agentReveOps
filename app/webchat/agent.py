from __future__ import annotations
import json
import re
from typing import Any, Optional
from anthropic import Anthropic
from app.config import settings
from app.crm.client import crm
from app.bot.knowledge_loader import load_knowledge
from app.logger import get_logger

logger = get_logger(__name__)

SST_PLANS = [
    {
        "id": "basic",
        "name": "Basic",
        "price": "$39.000",
        "price_monthly": 39000,
        "employees": "Hasta 4 empleados",
        "highlighted": False,
        "badge": None,
        "cta": "Comprar Basic",
    },
    {
        "id": "starter",
        "name": "Starter",
        "price": "$220.000",
        "price_monthly": 220000,
        "employees": "Hasta 7 empleados",
        "highlighted": False,
        "badge": None,
        "cta": "Comprar Starter",
    },
    {
        "id": "pro",
        "name": "Pro",
        "price": "$600.000",
        "price_monthly": 600000,
        "employees": "Hasta 30 empleados",
        "highlighted": True,
        "badge": "Más popular",
        "cta": "Comprar Pro",
    },
    {
        "id": "plus",
        "name": "Plus",
        "price": "$1.220.000",
        "price_monthly": 1220000,
        "employees": "Hasta 80 empleados",
        "highlighted": False,
        "badge": None,
        "cta": "Comprar Plus",
    },
    {
        "id": "corporativo",
        "name": "Corporativo",
        "price": "A la medida",
        "price_monthly": None,
        "employees": "Empleados ilimitados",
        "highlighted": False,
        "badge": None,
        "cta": "Contactar",
    },
]

WHATSAPP_NUMBER = "573001234567"  # TODO: mover a settings cuando esté configurado

VERA_SYSTEM_PROMPT = """Eres VERA, la asesora de inteligencia artificial de Verifty.
Estás integrada en el sitio web de Verifty para ayudar a los visitantes a encontrar
el producto y plan correcto para su empresa.

PERSONALIDAD:
- Cercana, directa y experta — como una asesora comercial senior que conoce SST al detalle
- Tuteo natural en español colombiano
- Respuestas concisas pero completas (3-5 líneas por mensaje está bien, no es WhatsApp)
- Empática: entiende que gestionar el SG-SST es complejo y estresante

TU ROL PRINCIPAL:
Eres asesora comercial de Verifty SST. Tu objetivo es:
1. Entender la situación del visitante (empresa, empleados, sector, situación SST actual)
2. Hacer una recomendación concreta de plan con argumentos específicos
3. Guiar a la compra directa online en sst.verifty.com/planes
4. Si el lead es de Verifty Flow (automatización), redirigir a WhatsApp para demo

DOS PRODUCTOS DE VERIFTY:
- VERIFTY SST: software de gestión SG-SST (21 módulos + VERA IA). ICP: 1-130 empleados o
  profesionales SST. Compra DIRECTA online. Tu enfoque principal.
- VERIFTY FLOW: automatización de procesos (ingreso contratistas, permisos). ICP: +130 empleados
  o muchos contratistas. Demo por WhatsApp con el equipo comercial.

CÓMO RECOMENDAR UN PLAN SST:
- Haz máximo 5 preguntas antes de recomendar (empleados, sector, ARL, situación actual, multi-sede)
- Da UNA recomendación concreta con 2-3 razones específicas
- Explica por qué NO el plan de arriba (gastar de más) y por qué NO el de abajo (les faltaría X)
- Siempre menciona VERA add-on si el lead no tiene especialista SST dedicado

REGLA CRÍTICA DE PRECIOS SST:
- Colombia → precios en COP únicamente
- Otros países → precios en USD (Basic $10, Starter $55, Pro $150, Plus $310)
- Nunca mezcles monedas en el mismo mensaje

TAGS DE CONTROL (al final después de "---", invisibles al usuario):
[LEAD_DATA: {"employees": N, "sector": "...", "arl_class": "1-5",
  "has_sst_specialist": true/false, "current_tool": "excel|paper|software|none",
  "multi_sede": true/false, "product_fit": "sst|flow|unknown",
  "name": "...", "company": "...", "email": "..."}]
[SST_READY: "plan_id"]   → reemplaza plan_id por: basic|starter|pro|plus|corporativo
[FLOW_LEAD]              → lead es de Flow, redirigir a WhatsApp
[HANDOFF_NEEDED]         → escalar a asesor humano por WhatsApp
[VERA_ADDON_PITCH]       → mencionar VERA add-on explícitamente

REGLAS DE TAGS:
- Emite [SST_READY] cuando tengas suficiente info para recomendar un plan
- [SST_READY] lleva el plan_id recomendado: ej [SST_READY: "pro"]
- [FLOW_LEAD] cuando sea claro que necesitan Flow (no SST)
- [HANDOFF_NEEDED] solo si la situación requiere atención humana urgente
- NUNCA muestres los tags al usuario

Conocimiento completo de productos, precios y estrategia comercial:
""" + load_knowledge()

VERA_CACHED_SYSTEM = [
    {
        "type": "text",
        "text": VERA_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }
]

# Regex para parsear tags
_RE_LEAD_DATA = re.compile(r"\[LEAD_DATA:\s*(\{.*?\})\]", re.DOTALL)
_RE_SST_READY = re.compile(r"\[SST_READY:\s*[\"']?(\w+)[\"']?\]", re.IGNORECASE)
_RE_FLOW_LEAD = re.compile(r"\[FLOW_LEAD\]")
_RE_HANDOFF = re.compile(r"\[HANDOFF_NEEDED\]")
_RE_VERA_PITCH = re.compile(r"\[VERA_ADDON_PITCH\]")
_RE_STRIP_TAGS = re.compile(
    r"\[(LEAD_DATA|SST_READY|FLOW_LEAD|HANDOFF_NEEDED|VERA_ADDON_PITCH)[^\]]*\]",
    re.IGNORECASE,
)


def _make_whatsapp_url(session_id: str, context: dict) -> str:
    """Genera un wa.me link con mensaje pre-cargado para handoff."""
    company = (context.get("lead_data") or {}).get("company", "")
    employees = (context.get("lead_data") or {}).get("employees", "")
    pre = "Hola, vengo del chat del sitio web de Verifty"
    if company:
        pre += f" — soy de {company}"
    if employees:
        pre += f" ({employees} empleados)"
    pre += ". Me gustaría saber más sobre el SG-SST."
    import urllib.parse
    return f"https://wa.me/{WHATSAPP_NUMBER}?text={urllib.parse.quote(pre)}"


class WebChatAgent:
    """Agente VERA para el chat del website. Síncrono, devuelve JSON estructurado."""

    def __init__(self):
        self.anthropic = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def _parse_tags(self, raw: str) -> tuple[str, dict[str, Any]]:
        parts = raw.split("---", 1)
        clean = parts[0].strip()
        blob = parts[1] if len(parts) > 1 else raw

        tags: dict[str, Any] = {}

        m = _RE_LEAD_DATA.search(blob)
        if m:
            try:
                tags["lead_data"] = json.loads(m.group(1))
            except Exception:
                pass

        m = _RE_SST_READY.search(blob)
        if m:
            tags["sst_ready"] = m.group(1).lower()

        if _RE_FLOW_LEAD.search(blob):
            tags["flow_lead"] = True
        if _RE_HANDOFF.search(blob):
            tags["handoff_needed"] = True
        if _RE_VERA_PITCH.search(blob):
            tags["vera_pitch"] = True

        clean = _RE_STRIP_TAGS.sub("", clean).strip()
        return clean, tags

    def _build_messages(self, history: list[dict], user_text: str) -> list[dict]:
        msgs = []
        for h in history:
            role = "user" if h["direction"] == "inbound" else "assistant"
            msgs.append({"role": role, "content": h["body"]})
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def _get_recommended_plans(self, plan_id: str) -> list[dict]:
        """Devuelve los planes ordenados, con el recomendado marcado como highlighted."""
        plans = []
        for p in SST_PLANS:
            plan_copy = dict(p)
            plan_copy["highlighted"] = (p["id"] == plan_id)
            plan_copy["recommended"] = (p["id"] == plan_id)
            plans.append(plan_copy)
        return plans

    async def process(
        self,
        session_id: str,
        conversation_id: str,
        message_text: str,
    ) -> dict:
        """
        Procesa un mensaje del visitante y devuelve una respuesta estructurada.

        Returns dict with keys:
          - type: "text" | "sst_plans" | "whatsapp_handoff"
          - text: texto visible de VERA
          - plans: lista de planes (solo si type == "sst_plans")
          - plans_url: URL de planes (solo si type == "sst_plans")
          - whatsapp_url: URL wa.me (solo si type == "whatsapp_handoff" o "sst_plans")
          - vera_pitch: bool — si mostrar el pitch de VERA add-on
        """
        conv = crm.get_conversation(conversation_id)
        if not conv:
            logger.error(f"Webchat conversation {conversation_id} not found")
            return {"type": "text", "text": "Hubo un error. Por favor recarga la página."}

        context = conv.get("context") or {}

        # Guardar mensaje entrante
        crm.save_message(conversation_id, "inbound", message_text)

        # Obtener historial (sin el mensaje que acabamos de guardar)
        history = crm.get_message_history(conversation_id, limit=30)
        # El save_message anterior ya está en DB, quitamos el último para no duplicar
        if history and history[-1]["body"] == message_text:
            history = history[:-1]

        msgs = self._build_messages(history, message_text)

        try:
            response = self.anthropic.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=1024,
                system=VERA_CACHED_SYSTEM,
                messages=msgs,
            )
            raw = response.content[0].text
        except Exception as e:
            logger.exception(f"Claude API error in webchat: {e}")
            return {
                "type": "text",
                "text": "Tuve un problema técnico. ¿Puedes intentar de nuevo?",
            }

        clean, tags = self._parse_tags(raw)

        # Persistir lead_data en contexto
        if tags.get("lead_data"):
            merged = {**(context.get("lead_data") or {}), **tags["lead_data"]}
            context["lead_data"] = merged
            crm.update_conversation(conversation_id, {"context": context})

        # Guardar respuesta de VERA
        crm.save_message(conversation_id, "outbound", clean)

        # Determinar tipo de respuesta

        # Caso 1: FLOW LEAD → handoff a WhatsApp para demo
        if tags.get("flow_lead") or tags.get("handoff_needed"):
            wa_url = _make_whatsapp_url(session_id, context)
            handoff_text = clean or (
                "Perfecto. Para este tipo de proyecto necesitas hablar con nuestro "
                "equipo comercial — ellos te hacen una demo personalizada. "
                "Te conecto ahora mismo por WhatsApp."
            )
            crm.update_conversation(
                conversation_id,
                {"status": "whatsapp_handoff", "context": context},
            )
            self._save_learning(
                session_id=session_id,
                conversation_id=conversation_id,
                context=context,
                outcome="whatsapp_handoff",
            )
            return {
                "type": "whatsapp_handoff",
                "text": handoff_text,
                "whatsapp_url": wa_url,
            }

        # Caso 2: SST READY → mostrar planes inline
        if tags.get("sst_ready"):
            plan_id = tags["sst_ready"]
            plans = self._get_recommended_plans(plan_id)
            wa_url = _make_whatsapp_url(session_id, context)
            crm.update_conversation(
                conversation_id,
                {"status": "sst_plans_shown", "context": context},
            )
            self._save_learning(
                session_id=session_id,
                conversation_id=conversation_id,
                context=context,
                outcome="plans_shown",
                plan_recommended=plan_id,
            )
            return {
                "type": "sst_plans",
                "text": clean,
                "plans": plans,
                "plans_url": "https://sst.verifty.com/planes",
                "whatsapp_url": wa_url,
                "vera_pitch": bool(tags.get("vera_pitch")),
            }

        # Caso 3: respuesta normal de texto
        crm.update_conversation(
            conversation_id,
            {"status": "qualifying", "context": context},
        )
        return {
            "type": "text",
            "text": clean,
            "vera_pitch": bool(tags.get("vera_pitch")),
        }

    def _save_learning(
        self,
        session_id: str,
        conversation_id: str,
        context: dict,
        outcome: str,
        plan_recommended: Optional[str] = None,
    ) -> None:
        """Guarda un registro de aprendizaje tras el cierre o hito de la conversación."""
        try:
            ld = context.get("lead_data") or {}
            crm.sb.table("vera_sales_learnings").insert({
                "session_id": session_id,
                "conversation_id": conversation_id,
                "channel": "webchat",
                "lead_employees": ld.get("employees"),
                "lead_sector": ld.get("sector"),
                "lead_arl_class": ld.get("arl_class"),
                "lead_has_sst_specialist": ld.get("has_sst_specialist"),
                "lead_current_tool": ld.get("current_tool"),
                "plan_recommended": plan_recommended,
                "outcome": outcome,
                "raw_context": context,
            }).execute()
        except Exception as e:
            logger.warning(f"save_learning failed: {e}")

    def get_greeting(self) -> str:
        return (
            "¡Hola! Soy VERA, tu asesora de Verifty 👋\n\n"
            "Estoy aquí para ayudarte a encontrar el plan de SG-SST perfecto para tu empresa, "
            "o contarte sobre nuestras soluciones de automatización.\n\n"
            "¿Qué estás buscando hoy?"
        )


vera_webchat_agent = WebChatAgent()

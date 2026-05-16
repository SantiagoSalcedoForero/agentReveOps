from __future__ import annotations
import json
import re
import urllib.parse
from typing import Any, Optional
from anthropic import Anthropic
from app.config import settings
from app.crm.client import crm
from app.bot.knowledge_loader import load_knowledge
from app.bot.agent import SYSTEM_PROMPT_BASE
from app.pricing.catalog import PLANES_BASE, formato_cop, prompt_inyectable
from app.bot.lead_context import build_lead_context_block
from app.logger import get_logger

logger = get_logger(__name__)

WHATSAPP_NUMBER = "573001234567"  # TODO: mover a settings cuando esté configurado

# Tarjetas de planes para el UI — derivadas del catálogo para no duplicar precios.
SST_PLANS = [
    {
        "id": p.codigo.lower(),
        "name": p.nombre,
        "price": formato_cop(p.precio_mensual_cop) if p.precio_mensual_cop else "A la medida",
        "price_monthly": p.precio_mensual_cop,
        "employees": f"Hasta {p.max_empleados} empleados" if p.max_empleados else "Empleados ilimitados",
        "highlighted": p.codigo == "PRO",
        "badge": "Más popular" if p.codigo == "PRO" else None,
        "cta": "Contactar" if p.codigo == "CORPORATIVO" else f"Comprar {p.nombre}",
    }
    for p in PLANES_BASE
]

# Regex para parsear tags (alineados con WhatsApp bot)
_RE_LEAD_DATA    = re.compile(r"\[LEAD_DATA:\s*(\{.*?\})\]", re.DOTALL)
_RE_PLAN_REC     = re.compile(r"\[PLAN_RECOMENDADO:\s*([A-Z]+)\]", re.IGNORECASE)
_RE_SST_READY    = re.compile(r"\[SST_READY\]", re.IGNORECASE)
_RE_BOOKING      = re.compile(r"\[BOOKING_READY\]", re.IGNORECASE)
_RE_HANDOFF      = re.compile(r"\[HANDOFF_NEEDED\]", re.IGNORECASE)
_RE_STRIP_TAGS   = re.compile(
    r"\[(LEAD_DATA|PLAN_RECOMENDADO|SST_READY|BOOKING_READY|HANDOFF_NEEDED"
    r"|SCORE_UPDATE|PRODUCT_FIT|SEND_QUOTE)[^\]]*\]",
    re.IGNORECASE | re.DOTALL,
)


def _make_whatsapp_url(context: dict) -> str:
    company = (context.get("lead_data") or {}).get("company", "")
    employees = (context.get("lead_data") or {}).get("employee_count", "")
    pre = "Hola, vengo del chat del sitio web de Verifty"
    if company:
        pre += f" — soy de {company}"
    if employees:
        pre += f" ({employees} empleados)"
    pre += ". Me gustaría saber más sobre el SG-SST."
    return f"https://wa.me/{WHATSAPP_NUMBER}?text={urllib.parse.quote(pre)}"


class WebChatAgent:
    """Agente Vera para el chat del website. Misma lógica que el bot WhatsApp, respuesta JSON."""

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

        m = _RE_PLAN_REC.search(blob)
        if m:
            tags["plan_recomendado"] = m.group(1).upper()

        if _RE_SST_READY.search(blob):
            tags["sst_ready"] = True
        if _RE_BOOKING.search(blob):
            tags["booking_ready"] = True
        if _RE_HANDOFF.search(blob):
            tags["handoff_needed"] = True

        clean = _RE_STRIP_TAGS.sub("", clean).strip()
        return clean, tags

    def _build_messages(self, history: list[dict], user_text: str) -> list[dict]:
        msgs = []
        for h in history:
            role = "user" if h["direction"] == "inbound" else "assistant"
            msgs.append({"role": role, "content": h["body"]})
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def _get_recommended_plans(self, plan_code: str) -> list[dict]:
        plan_id = plan_code.lower()
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

        Returns dict con keys:
          - type: "text" | "sst_plans" | "whatsapp_handoff"
          - text: texto visible de Vera
          - plans: lista de planes (solo si type == "sst_plans")
          - plans_url: URL de planes (solo si type == "sst_plans")
          - whatsapp_url: URL wa.me (cuando aplique)
        """
        conv = crm.get_conversation(conversation_id)
        if not conv:
            logger.error(f"Webchat conversation {conversation_id} not found")
            return {"type": "text", "text": "Hubo un error. Por favor recarga la página."}

        context = conv.get("context") or {}

        crm.save_message(conversation_id, "inbound", message_text)

        history = crm.get_message_history(conversation_id, limit=30)
        # Eliminar el mensaje actual si ya está en el historial (fue guardado líneas arriba)
        if history and history[-1]["body"] == message_text:
            history = history[:-1]

        lead_ctx = build_lead_context_block(context.get("lead_data") or {})
        msgs = (lead_ctx or []) + self._build_messages(history, message_text)

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

        try:
            response = self.anthropic.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=600,
                system=system_blocks,
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
        logger.info(f"Webchat tags for {conversation_id}: {tags}")

        if tags.get("lead_data"):
            merged = {**(context.get("lead_data") or {}), **tags["lead_data"]}
            context["lead_data"] = merged

        if tags.get("plan_recomendado"):
            ld = context.get("lead_data") or {}
            ld["plan_recomendado"] = tags["plan_recomendado"]
            context["lead_data"] = ld

        crm.save_message(conversation_id, "outbound", clean)

        # Flow o escalada → handoff a WhatsApp
        if tags.get("booking_ready") or tags.get("handoff_needed"):
            wa_url = _make_whatsapp_url(context)
            handoff_text = clean or (
                "Para este caso lo mejor es hablar con nuestro equipo directamente. "
                "Te paso por WhatsApp para que te hagan una demo personalizada."
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

        # SST listo → mostrar tarjetas de planes
        if tags.get("sst_ready"):
            plan_code = tags.get("plan_recomendado") or (context.get("lead_data") or {}).get("plan_recomendado", "pro")
            plans = self._get_recommended_plans(plan_code)
            wa_url = _make_whatsapp_url(context)
            crm.update_conversation(
                conversation_id,
                {"status": "sst_plans_shown", "context": context},
            )
            self._save_learning(
                session_id=session_id,
                conversation_id=conversation_id,
                context=context,
                outcome="plans_shown",
                plan_recommended=plan_code.lower(),
            )
            return {
                "type": "sst_plans",
                "text": clean,
                "plans": plans,
                "plans_url": "https://sst.verifty.com/planes",
                "whatsapp_url": wa_url,
            }

        crm.update_conversation(
            conversation_id,
            {"status": "qualifying", "context": context},
        )
        return {
            "type": "text",
            "text": clean,
        }

    def _save_learning(
        self,
        session_id: str,
        conversation_id: str,
        context: dict,
        outcome: str,
        plan_recommended: Optional[str] = None,
    ) -> None:
        try:
            ld = context.get("lead_data") or {}
            crm.sb.table("vera_sales_learnings").insert({
                "session_id": session_id,
                "conversation_id": conversation_id,
                "channel": "webchat",
                "lead_employees": ld.get("employee_count"),
                "lead_sector": ld.get("industry"),
                "lead_arl_class": ld.get("nivel_riesgo_arl"),
                "lead_has_sst_specialist": ld.get("is_decision_maker"),
                "lead_current_tool": ld.get("sst_process"),
                "plan_recommended": plan_recommended,
                "outcome": outcome,
                "raw_context": context,
            }).execute()
        except Exception as e:
            logger.warning(f"save_learning failed: {e}")

    def get_greeting(self) -> str:
        return "Hola, soy Vera, la asesora SST de Verifty. ¿En qué te puedo ayudar hoy?"


vera_webchat_agent = WebChatAgent()

from __future__ import annotations
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.crm.client import crm
from app.webchat.agent import vera_webchat_agent
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webchat", tags=["webchat"])


# ─── Request / Response models ────────────────────────────────────────────────

class SessionRequest(BaseModel):
    session_id: Optional[str] = None  # Si None → se genera uno nuevo


class SessionResponse(BaseModel):
    session_id: str
    conversation_id: str
    greeting: str


class MessageRequest(BaseModel):
    session_id: str
    text: str


class MessageResponse(BaseModel):
    session_id: str
    reply: dict  # type + text + optional plans/whatsapp_url/vera_pitch


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[dict]


class LearnRequest(BaseModel):
    """Registra el outcome final de una sesión (desde el frontend cuando el usuario compra)."""
    session_id: str
    outcome: str   # 'purchased' | 'lost' | 'abandoned'
    plan_purchased: Optional[str] = None
    loss_reason: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/session", response_model=SessionResponse)
async def create_or_resume_session(body: SessionRequest):
    """
    Crea o reanuda una sesión de webchat.
    El frontend genera y guarda el session_id en localStorage.
    Si ya existe una conversación activa para ese session_id, la reanuda.
    """
    sid = body.session_id or str(uuid.uuid4())

    conv = crm.get_or_create_webchat_session(sid)
    greeting = vera_webchat_agent.get_greeting()

    # Si la conversación es nueva (no tiene mensajes previos), guardamos el saludo
    history = crm.get_message_history(conv["id"], limit=1)
    if not history:
        crm.save_message(conv["id"], "outbound", greeting)

    return SessionResponse(
        session_id=sid,
        conversation_id=conv["id"],
        greeting=greeting,
    )


@router.post("/message", response_model=MessageResponse)
async def send_message(body: MessageRequest):
    """
    Envía un mensaje de usuario y obtiene la respuesta de VERA.
    Operación síncrona — la respuesta llega en la misma request.
    """
    if not body.text or not body.text.strip():
        raise HTTPException(400, "El mensaje no puede estar vacío")

    conv = crm.get_webchat_session(body.session_id)
    if not conv:
        raise HTTPException(404, "Sesión no encontrada. Usa POST /webchat/session primero.")

    reply = await vera_webchat_agent.process(
        session_id=body.session_id,
        conversation_id=conv["id"],
        message_text=body.text.strip(),
    )

    return MessageResponse(session_id=body.session_id, reply=reply)


@router.get("/history/{session_id}", response_model=HistoryResponse)
async def get_history(session_id: str):
    """
    Devuelve el historial de mensajes de una sesión.
    El frontend lo usa para restaurar la conversación tras un refresh.
    """
    conv = crm.get_webchat_session(session_id)
    if not conv:
        return HistoryResponse(session_id=session_id, messages=[])

    raw = crm.get_webchat_message_history(conv["id"])
    return HistoryResponse(session_id=session_id, messages=raw)


@router.post("/learn")
async def record_outcome(body: LearnRequest):
    """
    El frontend llama a este endpoint cuando el usuario hace click en 'Comprar'
    o cierra el widget sin comprar. Registra el outcome para el sistema de aprendizaje.
    """
    conv = crm.get_webchat_session(body.session_id)
    if not conv:
        return {"ok": False, "reason": "session not found"}

    try:
        context = conv.get("context") or {}
        ld = context.get("lead_data") or {}
        crm.sb.table("vera_sales_learnings").insert({
            "session_id": body.session_id,
            "conversation_id": conv["id"],
            "channel": "webchat",
            "lead_employees": ld.get("employees"),
            "lead_sector": ld.get("sector"),
            "plan_purchased": body.plan_purchased,
            "outcome": body.outcome,
            "loss_reason": body.loss_reason,
            "raw_context": context,
        }).execute()
        return {"ok": True}
    except Exception as e:
        logger.warning(f"record_outcome failed: {e}")
        return {"ok": False, "reason": str(e)}

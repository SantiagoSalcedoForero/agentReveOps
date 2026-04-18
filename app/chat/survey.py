"""Encuesta de satisfacción post-cierre de chat.
Se envía como mensaje interactivo de WhatsApp (3 botones).
La respuesta del lead se captura en el webhook y se guarda en la conversación.
"""
from __future__ import annotations
from app.whatsapp.client import whatsapp_client
from app.crm.client import crm
from app.logger import get_logger

logger = get_logger(__name__)

SURVEY_BODY = (
    "Tu conversación ha finalizado. Nos ayudarías mucho con tu opinión:\n\n"
    "¿Cómo calificarías la atención que recibiste?"
)

SURVEY_BUTTONS = [
    {"id": "survey_3", "title": "Excelente"},
    {"id": "survey_2", "title": "Buena"},
    {"id": "survey_1", "title": "Podría mejorar"},
]

RATING_MAP = {"survey_3": 3, "survey_2": 2, "survey_1": 1}


async def send_satisfaction_survey(
    conversation_id: str,
    phone: str,
) -> bool:
    """Envía la encuesta de satisfacción por WhatsApp (interactive buttons).
    Retorna True si se envió, False si falló (ej. ventana expirada).
    """
    try:
        button_labels = [b["title"] for b in SURVEY_BUTTONS]
        await whatsapp_client.send_interactive_buttons(
            phone=phone,
            body=SURVEY_BODY,
            buttons=button_labels,
        )
        crm.save_message(
            conversation_id=conversation_id,
            direction="outbound",
            body="[encuesta de satisfacción enviada]",
        )
        crm.update_conversation(
            conversation_id, {"status": "survey_sent"}
        )
        logger.info(f"Survey sent conv={conversation_id}")
        return True
    except Exception as e:
        logger.warning(f"survey send failed (window expired?): {e}")
        # Si la ventana de 24h expiró, no podemos enviar interactive.
        # No intentamos con template — simplemente omitimos la encuesta.
        return False


def handle_survey_response(
    conversation_id: str,
    button_id: str,
) -> int | None:
    """Procesa la respuesta del lead a la encuesta. Retorna el rating guardado (1-3) o None."""
    rating = RATING_MAP.get(button_id)
    if rating is None:
        return None
    try:
        crm.update_conversation(conversation_id, {
            "satisfaction_rating": rating,
        })
        # También guardamos en el lead para tener el dato colapsado
        conv = crm.get_conversation(conversation_id)
        if conv and conv.get("lead_id"):
            # No hay columna específica en leads; usamos main_need como referencia
            # o mejor lo guardamos en activities para historial
            crm.create_activity(
                lead_id=conv["lead_id"],
                activity_type="note",
                title=f"Encuesta de satisfacción: {_rating_label(rating)}",
                body=f"Rating: {rating}/3 — conversación {conversation_id}",
            )
        logger.info(f"Survey response conv={conversation_id} rating={rating}")
    except Exception as e:
        logger.warning(f"save survey response: {e}")
    return rating


def _rating_label(r: int) -> str:
    return {3: "Excelente", 2: "Buena", 1: "Podría mejorar"}.get(r, "?")

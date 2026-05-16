"""Dispatcher para Tool Use API calls.

Recibe el nombre y el input de un tool call y delega al handler correspondiente.
"""
from __future__ import annotations

from typing import Any

from app.bot.tools.handlers import (
    handle_escalar_a_demo,
    handle_escalar_a_humano,
    handle_pedir_cotizacion_por_correo,
    handle_recomendar_plan_y_cerrar,
)
from app.logger import get_logger

logger = get_logger(__name__)

_HANDLERS = {
    "recomendar_plan_y_cerrar": handle_recomendar_plan_y_cerrar,
    "escalar_a_demo": handle_escalar_a_demo,
    "pedir_cotizacion_por_correo": handle_pedir_cotizacion_por_correo,
    "escalar_a_humano": handle_escalar_a_humano,
}


def dispatch_tool_use(
    tool_name: str,
    tool_input: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Despacha un tool call al handler correspondiente.

    Retorna un dict de tags que se fusiona con los tags del texto de la respuesta.
    Si el tool_name no es conocido, retorna {} y loguea un warning.
    """
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        logger.warning(f"[dispatcher] tool desconocido: {tool_name!r}")
        return {}
    return handler(tool_input, context)

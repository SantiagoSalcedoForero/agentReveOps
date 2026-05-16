"""Handlers para cada herramienta de Tool Use.

Cada handler recibe el input del tool call y el contexto de la conversación,
y retorna un dict de tags que se fusiona con los tags del texto (LEAD_DATA, SCORE_UPDATE).
"""
from __future__ import annotations

import re
from typing import Any

from app.logger import get_logger

logger = get_logger(__name__)

PALABRAS_PROHIBIDAS: list[str] = [
    "normativa",
    "multa",
    "Mintrabajo",
    "obligatoria",
    "obligatorio",
    "ARL te",
]

_RE_PROHIBIDAS = re.compile(
    "|".join(re.escape(p) for p in PALABRAS_PROHIBIDAS),
    re.IGNORECASE,
)


def _sanitize_razon(razon: str) -> str:
    return _RE_PROHIBIDAS.sub("", razon).strip()


def handle_recomendar_plan_y_cerrar(
    tool_input: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    plan = str(tool_input.get("plan", "")).upper()
    ciclo = str(tool_input.get("ciclo", "mensual")).lower()
    razon = str(tool_input.get("razon_eleccion", ""))

    if _RE_PROHIBIDAS.search(razon):
        logger.warning("[tools] razon_eleccion contiene palabras prohibidas — sanitizando")
        razon = _sanitize_razon(razon)

    tags: dict[str, Any] = {
        "plan_recomendado": plan,
        "sst_ready": True,
        "product_fit": "verifty_sst",
        "ciclo_facturacion": ciclo,
        "razon_sanitizada": razon,
    }
    logger.info(f"[tools] recomendar_plan_y_cerrar: plan={plan} ciclo={ciclo}")
    return tags


def handle_escalar_a_demo(
    tool_input: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    motivo = str(tool_input.get("motivo", "proceso_operativo_complejo"))
    num_empleados = tool_input.get("num_empleados")
    pais = str(tool_input.get("pais", ""))

    tags: dict[str, Any] = {
        "booking_ready": True,
        "demo_motivo": motivo,
    }
    if num_empleados is not None:
        tags["demo_num_empleados"] = int(num_empleados)
    if pais:
        tags["demo_pais"] = pais

    logger.info(f"[tools] escalar_a_demo: motivo={motivo} empleados={num_empleados}")
    return tags


def handle_pedir_cotizacion_por_correo(
    tool_input: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    email = str(tool_input.get("email", "")).strip()
    plan = str(tool_input.get("plan", "")).lower()
    company = str(tool_input.get("company", ""))
    contact_name = str(tool_input.get("contact_name", ""))

    tags: dict[str, Any] = {
        "send_quote": {
            "email": email,
            "plan": plan,
            "company": company,
            "contact_name": contact_name,
        }
    }
    logger.info(f"[tools] pedir_cotizacion_por_correo: email={email} plan={plan}")
    return tags


def handle_escalar_a_humano(
    tool_input: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    motivo = str(tool_input.get("motivo", "bot_confused"))
    resumen = str(tool_input.get("resumen_para_humano", ""))

    tags: dict[str, Any] = {
        "handoff_needed": True,
        "handoff_reason": motivo,
        "handoff_resumen": resumen,
    }
    logger.info(f"[tools] escalar_a_humano: motivo={motivo}")
    return tags

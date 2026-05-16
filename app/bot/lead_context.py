"""Helper compartido: bloque de memoria persistente del lead para inyectar en Claude.

Usado por el bot de WhatsApp (app/bot/agent.py) y el webchat (app/webchat/agent.py).
"""
from __future__ import annotations

_INVALID = {"unknown", "desconocido", "none", "null", "no confirmado",
            "sin confirmar", "no especificado", ""}


def _val(lead_data: dict, key: str) -> str | None:
    """Devuelve el valor del campo si existe y es significativo, None si no."""
    v = lead_data.get(key)
    if v is None:
        return None
    s = str(v).strip().lower()
    return str(v).strip() if s not in _INVALID else None


def build_lead_context_block(lead_data: dict | None) -> list[dict] | None:
    """Construye el bloque de memoria persistente del lead.

    Retorna [user_msg, assistant_ack] para anteponer al historial, o None
    si lead_data está vacío o todos los campos son desconocidos.
    """
    if not lead_data:
        return None

    lines: list[str] = []

    if name := _val(lead_data, "name"):
        lines.append(f"- Nombre: {name}")
    if company := _val(lead_data, "company"):
        lines.append(f"- Empresa: {company}")
    if industry := _val(lead_data, "industry"):
        lines.append(f"- Sector / industria: {industry}")

    city = _val(lead_data, "city")
    country = _val(lead_data, "country")
    if city or country:
        lines.append(f"- Ciudad / país: {city or country}")

    if emp := _val(lead_data, "employee_count"):
        lines.append(f"- Número de empleados: {emp}")

    hc = lead_data.get("has_contractors")
    if hc is not None:
        lines.append(f"- Maneja contratistas: {'sí' if hc else 'no'}")

    if sst := _val(lead_data, "sst_process"):
        lines.append(f"- Estado actual del SG-SST: {sst}")
    if pain := _val(lead_data, "pain_point"):
        lines.append(f"- Dolor principal: {pain}")
    if email := _val(lead_data, "email"):
        lines.append(f"- Email: {email}")
    if plan := _val(lead_data, "plan_recomendado"):
        lines.append(f"- Plan ya recomendado: {plan}")

    if not lines:
        return None

    block = (
        "===CONTEXTO_PERSISTENTE_DEL_LEAD===\n"
        "Estos son los datos que YA conoces del lead por turnos anteriores. "
        "NO los vuelvas a preguntar. Si están vacíos, significa que aún no los tienes.\n\n"
        + "\n".join(lines)
        + "\n===FIN_CONTEXTO_PERSISTENTE==="
    )

    return [
        {"role": "user", "content": block},
        {"role": "assistant", "content": "Entendido, tengo el contexto presente."},
    ]

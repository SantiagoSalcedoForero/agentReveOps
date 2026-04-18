"""Construye el PRIMER mensaje de WhatsApp que el bot envía al lead
después de que verificó su OTP de descarga de plantilla.

Prioridad:
  1. Si recibimos `template_title` (+ opcionalmente `template_description`)
     del landing → generamos mensaje con Claude, específico para esa
     plantilla. Funciona para CUALQUIER plantilla del catálogo.
  2. Si no los recibimos (retrocompat con landing viejo) → caemos al
     mapa hardcoded en `templates_catalog.py` con los 5 slugs conocidos.

El mensaje generado se envía como outbound por WhatsApp y además queda
guardado como primer turno 'bot' en whatsapp_messages.
"""
from __future__ import annotations
from typing import Optional

from anthropic import Anthropic

from app.config import settings
from app.otp.templates_catalog import get_template_meta
from app.logger import get_logger

logger = get_logger(__name__)

_client: Optional[Anthropic] = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def _build_prompt(
    first_name: str,
    template_title: str,
    template_description: Optional[str],
) -> str:
    name_line = (
        f'El nombre del usuario es: "{first_name}". Salúdalo por ese nombre.'
        if first_name
        else "No conocemos el nombre del usuario; usa un saludo natural sin nombre."
    )
    desc = (template_description or "").strip() or "sin descripción adicional"
    return f"""Eres el asesor comercial de Verifty (SaaS colombiano de SG-SST).

Acabamos de enviar al usuario la plantilla: "{template_title}".
Resumen de la plantilla: {desc}

{name_line}

Envía un ÚNICO mensaje corto de WhatsApp (máximo 3 oraciones, máximo 1 emoji) que:
  - Salude al usuario (por nombre si lo conocemos)
  - Confirme la descarga de la plantilla por su nombre exacto entre comillas o cursiva natural
  - Mencione 1 razón CONCRETA por la que Verifty simplifica el proceso que esa plantilla documenta (ATS, matriz, permiso, etc.)
  - Cierre con UNA pregunta abierta para iniciar conversación

Tono: profesional cercano, colombiano, sin tecnicismos innecesarios, sin "¡Hola!" genérico, sin emojis de más.

Responde SOLO con el mensaje listo para enviar a WhatsApp. No uses comillas externas, ni explicaciones, ni etiquetas. Solo el texto final."""


def _fallback_static_body(
    first_name: str,
    template_slug: Optional[str],
) -> str:
    meta = get_template_meta(template_slug)
    hello = f"¡Listo{', ' + first_name if first_name else ''}!"
    return (
        f"{hello} Ya tienes {meta['name']}. 📥\n\n"
        f"Muchos líderes de SST nos descargan esto porque se cansan de "
        f"{meta['pain']}. En Verifty lo resolvemos así: {meta['pitch']}\n\n"
        f"¿Te muestro en 5 min cómo funcionaría en tu operación?"
    )


def build_first_message(
    lead_data: dict,
    template_slug: Optional[str] = None,
    template_title: Optional[str] = None,
    template_description: Optional[str] = None,
) -> str:
    """Devuelve el cuerpo del primer mensaje de WhatsApp post-OTP.
    - Si hay `template_title` → usa Claude para generar mensaje dinámico.
    - Si no → fallback al catálogo hardcoded (5 slugs conocidos).
    """
    first_name = ""
    if lead_data and lead_data.get("name"):
        first_name = str(lead_data["name"]).split(" ")[0].strip()

    if template_title and template_title.strip():
        try:
            prompt = _build_prompt(
                first_name=first_name,
                template_title=template_title.strip(),
                template_description=template_description,
            )
            client = _get_client()
            resp = client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            body = resp.content[0].text if resp.content else ""
            body = body.strip()
            # Limpia comillas externas si el modelo las incluyó
            if body.startswith('"') and body.endswith('"'):
                body = body[1:-1].strip()
            if body:
                logger.info(
                    f"first-message LLM ok template_slug={template_slug} "
                    f"len={len(body)}"
                )
                return body
            logger.warning("first-message LLM returned empty body, falling back")
        except Exception as e:
            logger.warning(f"first-message LLM failed: {e}, falling back")

    # Fallback
    return _fallback_static_body(first_name, template_slug)

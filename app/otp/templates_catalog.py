"""Catálogo de plantillas descargables de la landing.
Mapea slug → metadata usada en el mensaje inicial del bot post-OTP.

Agrega/edita según vayas creando plantillas en marketing.
"""
from __future__ import annotations

TEMPLATES_CATALOG: dict[str, dict] = {
    "ats-excel": {
        "name": "Formato ATS (Análisis de Trabajo Seguro) en Excel",
        "pain": "llenar ATS a mano antes de cada trabajo de alto riesgo",
        "module": "Formatos Digitales + Permisos de Trabajo",
        "pitch": (
            "Tus supervisores diligencian el ATS en 30 segundos desde el celular, "
            "con firma biométrica y foto del sitio, y queda trazable en tu tablero."
        ),
    },
    "matriz-epp": {
        "name": "Matriz de entrega de EPP",
        "pain": "llevar en Excel quién recibió qué y cuándo se le vence el EPP",
        "module": "Inventario EPP",
        "pitch": (
            "Verifty entrega EPP con Face ID, te alerta vencimientos y bloquea la "
            "entrega si la inspección previa no está al día."
        ),
    },
    "permiso-alturas": {
        "name": "Formato de permiso de trabajo en alturas",
        "pain": "firmar permisos en papel y perderlos después de la jornada",
        "module": "Permisos de Trabajo",
        "pitch": (
            "Permisos con firma digital válida legalmente, chequeos intermedios "
            "automáticos y cierre con foto y geolocalización."
        ),
    },
    "inspeccion-extintores": {
        "name": "Formato de inspección de extintores",
        "pain": "hacer inspecciones mensuales de todos los extintores en papel",
        "module": "Inventario + Formatos Digitales",
        "pitch": (
            "Cada extintor tiene su QR y hoja de vida digital. Escaneas, llenas en 20 seg, "
            "quedan todas las inspecciones en el histórico."
        ),
    },
    "matriz-riesgos": {
        "name": "Matriz de identificación de peligros y evaluación de riesgos",
        "pain": "mantener actualizada la matriz cuando cambian los procesos",
        "module": "Formatos Digitales + Cronogramas",
        "pitch": (
            "Matrices dinámicas por sede, con actualización automática cada vez que "
            "se crea un nuevo proceso o permiso."
        ),
    },
    # Default fallback si el slug no está en el catálogo
    "_default": {
        "name": "el formato que descargaste",
        "pain": "mantener ese proceso controlado con Excel y papel",
        "module": "suite Verifty",
        "pitch": (
            "En Verifty automatizamos ese proceso con firmas biométricas, OCR y "
            "trazabilidad completa para auditorías."
        ),
    },
}


def get_template_meta(slug: str | None) -> dict:
    if not slug:
        return TEMPLATES_CATALOG["_default"]
    return TEMPLATES_CATALOG.get(slug, TEMPLATES_CATALOG["_default"])

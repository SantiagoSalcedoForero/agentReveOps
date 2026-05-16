"""Validador de palabras prohibidas en el texto visible al cliente.

Modo monitoreo (M4.1): detecta y loguea, no bloquea envío.
En M5+ se puede convertir a bloqueo + reintento de generación.
"""
from __future__ import annotations

PALABRAS_PROHIBIDAS: list[str] = [
    "obligatorio",
    "obligatoria",
    "Mintrabajo te",
    "Mintrabajo exige",
    "ARL te pide",
    "ARL te exige",
    "multa",
    "multas",
    "incumplimiento",
    "incumpliendo",
    "500 SMMLV",
    "auditoría te",
    "Verifty Flow",
]


def detectar_palabras_prohibidas(texto: str) -> list[str]:
    """Retorna las palabras prohibidas encontradas en `texto` (case-insensitive).

    Lista vacía si el texto está limpio.
    """
    texto_lower = texto.lower()
    return [p for p in PALABRAS_PROHIBIDAS if p.lower() in texto_lower]

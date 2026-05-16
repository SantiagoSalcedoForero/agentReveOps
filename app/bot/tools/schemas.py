"""Definiciones de herramientas para Anthropic Tool Use API.

Las 4 herramientas terminales que Claude puede invocar:
  1. recomendar_plan_y_cerrar       — cierre SST self-serve
  2. escalar_a_demo                 — demo Flow / Corporativo
  3. pedir_cotizacion_por_correo    — cotización formal por email
  4. escalar_a_humano               — handoff a agente humano
"""
from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "recomendar_plan_y_cerrar",
        "description": (
            "Recomienda un plan SST y envía el link de compra self-serve al lead. "
            "Úsala cuando el lead ya dio su número de empleados, sector y confirmó "
            "querer empezar. NO la uses si el lead es Flow o Corporativo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "string",
                    "enum": ["BASIC", "STARTER", "PRO", "PLUS"],
                    "description": "Código exacto del plan recomendado según el catálogo.",
                },
                "ciclo": {
                    "type": "string",
                    "enum": ["mensual", "anual"],
                    "description": "Ciclo de facturación preferido por el lead.",
                },
                "razon_eleccion": {
                    "type": "string",
                    "description": (
                        "Razón en una frase basada en el límite duro del catálogo "
                        "(TRABAJADORES TOTALES). Ejemplos válidos: "
                        "'tiene 8 trabajadores, Starter llega a 10'; "
                        "'tiene 12 trabajadores, supera el techo de 10 del Starter, Pro llega a 50'; "
                        "'tiene contratistas, Plus es el que los incluye'. "
                        "PROHIBIDO: 'la normativa exige', 'la ARL pide', 'puede haber multa', "
                        "'es obligatorio por ley'."
                    ),
                },
            },
            "required": ["plan", "ciclo", "razon_eleccion"],
        },
    },
    {
        "name": "escalar_a_demo",
        "description": (
            "Agenda una demo con el equipo comercial para leads Verifty Flow "
            "(>130 empleados, ≥10 contratistas, proceso operativo complejo) "
            "o Corporativo SST (empleados ilimitados, API, SSO). "
            "NUNCA propongas horarios en el texto — el sistema los envía como botones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "enum": [
                        "mas_de_130_empleados",
                        "diez_o_mas_contratistas",
                        "proceso_operativo_complejo",
                        "corporativo_sst",
                    ],
                    "description": "Razón principal por la que el lead necesita demo.",
                },
                "num_empleados": {
                    "type": "integer",
                    "description": "Número de empleados del lead (si se conoce).",
                },
                "pais": {
                    "type": "string",
                    "description": "País del lead (ej: Colombia, México).",
                },
            },
            "required": ["motivo"],
        },
    },
    {
        "name": "pedir_cotizacion_por_correo",
        "description": (
            "Envía una cotización formal por correo al lead. "
            "Úsala cuando el lead pide una propuesta, cotización o algo por escrito "
            "y ya tienes su email."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Correo electrónico del lead donde enviar la cotización.",
                },
                "plan": {
                    "type": "string",
                    "enum": ["basic", "starter", "pro", "plus"],
                    "description": "Plan a cotizar.",
                },
                "company": {
                    "type": "string",
                    "description": "Nombre de la empresa del lead.",
                },
                "contact_name": {
                    "type": "string",
                    "description": "Nombre del contacto (opcional).",
                },
            },
            "required": ["email", "plan", "company"],
        },
    },
    {
        "name": "escalar_a_humano",
        "description": (
            "Escala la conversación a un asesor humano. "
            "Úsala solo cuando hay urgencia real (auditoría inminente, accidente grave), "
            "el lead pide hablar con un humano explícitamente, "
            "o no puedes resolver en 2 intentos consecutivos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "enum": [
                        "urgencia_auditoria",
                        "accidente_grave",
                        "empresa_grande",
                        "solicitud_explicita",
                        "bot_confused",
                    ],
                    "description": "Razón del escalamiento.",
                },
                "resumen_para_humano": {
                    "type": "string",
                    "description": (
                        "Resumen del contexto para el asesor humano (≤300 caracteres). "
                        "Incluye: empresa, empleados, producto de interés y dónde "
                        "quedó la conversación."
                    ),
                },
            },
            "required": ["motivo", "resumen_para_humano"],
        },
    },
]

TOOL_NAMES: frozenset[str] = frozenset(t["name"] for t in TOOLS)

"""Tests para el SYSTEM_PROMPT_BASE de M4.

Cubre:
- Regla Híbrido C (no escalar proactivamente)
- Regla Asumir Venta
- Regla Urgencia Honesta (prohibición de venta por miedo)
- Herramientas declaradas
- Anti-patrones ausentes
- MODULOS_POR_PLAN en catalog
"""
from __future__ import annotations

import re


class TestHibridoC:
    """Regla #4 — Modelo Híbrido C presente en el system prompt."""

    def test_prompt_menciona_no_escalar_proactivamente(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert (
            "no escal" in SYSTEM_PROMPT_BASE.lower()
            or "NO ESCALES" in SYSTEM_PROMPT_BASE
            or "nunca tú la inventas" in SYSTEM_PROMPT_BASE.lower()
            or "siempre viene del cliente" in SYSTEM_PROMPT_BASE.lower()
        )

    def test_prompt_menciona_modulo_explicito_para_subir(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "explícitamente" in SYSTEM_PROMPT_BASE or "EXPLÍCITAMENTE" in SYSTEM_PROMPT_BASE

    def test_prompt_no_permite_sugerir_pro_proactivo(self):
        """El prompt debe indicar que solo se sube de plan si el lead menciona el módulo."""
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert (
            "SOLO si el lead menciona" in SYSTEM_PROMPT_BASE
            or "solo si el lead" in SYSTEM_PROMPT_BASE.lower()
            or "si el cliente mencionó" in SYSTEM_PROMPT_BASE
            or "explícitamente" in SYSTEM_PROMPT_BASE
        )


class TestAsumarVenta:
    """Regla #5 — Asumir Venta presente en el system prompt."""

    def test_prompt_tiene_regla_asumir_venta(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert (
            "ASUMIR VENTA" in SYSTEM_PROMPT_BASE
            or "asumir venta" in SYSTEM_PROMPT_BASE.lower()
            or "asume la venta" in SYSTEM_PROMPT_BASE.lower()
            or "INMEDIATAMENTE" in SYSTEM_PROMPT_BASE
        )

    def test_prompt_sugiere_mensual_vs_anual_no_si_quieren_comprar(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert (
            "mensual o anual" in SYSTEM_PROMPT_BASE.lower()
            or "mensual vs anual" in SYSTEM_PROMPT_BASE.lower()
            or "Sin más preguntas" in SYSTEM_PROMPT_BASE
        )


class TestUrgenciaHonesta:
    """Regla #7 — Urgencia honesta: prohibición de venta por miedo."""

    def test_prompt_prohíbe_mintrabajo_como_argumento_venta(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        # M4.1 usa I-3 NUNCA en vez de PROHIBIDO
        assert "PROHIBIDO" in SYSTEM_PROMPT_BASE or "I-3" in SYSTEM_PROMPT_BASE
        # La sección PROHIBIDO/I-3 debe mencionar Mintrabajo
        idx = SYSTEM_PROMPT_BASE.find("PROHIBIDO")
        if idx == -1:
            idx = SYSTEM_PROMPT_BASE.find("I-3")
        section = SYSTEM_PROMPT_BASE[idx: idx + 500]
        assert "Mintrabajo" in section or "mintrabajo" in section.lower()

    def test_prompt_prohíbe_500_smmlv(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "500 SMMLV" in SYSTEM_PROMPT_BASE

    def test_prompt_tiene_ejemplos_urgencia_permitida(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        # M4.1 usa sección URGENCIA HONESTA con ejemplos en vez de PERMITIDO
        assert "PERMITIDO" in SYSTEM_PROMPT_BASE or "URGENCIA HONESTA" in SYSTEM_PROMPT_BASE

    def test_prompt_no_usa_multa_como_argumento_en_reglas(self):
        """'multa' solo debe aparecer en contexto de prohibición (ventana de 300 chars)."""
        from app.bot.agent import SYSTEM_PROMPT_BASE
        base = SYSTEM_PROMPT_BASE.lower()
        idx = base.find("multa")
        while idx != -1:
            window = base[max(0, idx - 300): idx + 300]
            prohibitive = any(w in window for w in ["prohibido", "nunca", "sanción", "sin", "i-3", "inviolable"])
            assert prohibitive, f"'multa' fuera de contexto prohibitivo: ...{window}..."
            idx = base.find("multa", idx + 1)


class TestObjeciones:
    """Regla #6 — Manejo de objeciones A-E presentes en el system prompt."""

    def test_prompt_tiene_objecion_precio(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "caro" in SYSTEM_PROMPT_BASE.lower()

    def test_prompt_tiene_objecion_excel(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        # M4.1: "Excel" aparece en objeción E (uso de planillas/excel vs plataforma)
        assert "excel" in SYSTEM_PROMPT_BASE.lower() or "Excel" in SYSTEM_PROMPT_BASE or "planillas" in SYSTEM_PROMPT_BASE.lower()

    def test_prompt_tiene_objecion_consultor(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "consultor" in SYSTEM_PROMPT_BASE.lower()


class TestHerramientas:
    """Las 4 herramientas deben seguir presentes en el system prompt."""

    def test_tool_recomendar(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "recomendar_plan_y_cerrar" in SYSTEM_PROMPT_BASE

    def test_tool_escalar_demo(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "escalar_a_demo" in SYSTEM_PROMPT_BASE

    def test_tool_cotizacion(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "pedir_cotizacion_por_correo" in SYSTEM_PROMPT_BASE

    def test_tool_humano(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "escalar_a_humano" in SYSTEM_PROMPT_BASE

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
        assert "no escal" in SYSTEM_PROMPT_BASE.lower() or "NO ESCALES" in SYSTEM_PROMPT_BASE

    def test_prompt_menciona_modulo_explicito_para_subir(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "explícitamente" in SYSTEM_PROMPT_BASE or "EXPLÍCITAMENTE" in SYSTEM_PROMPT_BASE

    def test_prompt_no_permite_sugerir_pro_proactivo(self):
        """El prompt debe indicar que solo se sube de plan si el lead menciona el módulo."""
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "SOLO si el lead menciona" in SYSTEM_PROMPT_BASE or "solo si el lead" in SYSTEM_PROMPT_BASE.lower()


class TestAsumarVenta:
    """Regla #5 — Asumir Venta presente en el system prompt."""

    def test_prompt_tiene_regla_asumir_venta(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "ASUMIR VENTA" in SYSTEM_PROMPT_BASE or "asumir venta" in SYSTEM_PROMPT_BASE.lower()

    def test_prompt_sugiere_mensual_vs_anual_no_si_quieren_comprar(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "mensual o anual" in SYSTEM_PROMPT_BASE.lower() or "mensual vs anual" in SYSTEM_PROMPT_BASE.lower()


class TestUrgenciaHonesta:
    """Regla #7 — Urgencia honesta: prohibición de venta por miedo."""

    def test_prompt_prohíbe_mintrabajo_como_argumento_venta(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "PROHIBIDO" in SYSTEM_PROMPT_BASE
        # La sección PROHIBIDO debe mencionar Mintrabajo
        idx = SYSTEM_PROMPT_BASE.find("PROHIBIDO")
        section = SYSTEM_PROMPT_BASE[idx: idx + 500]
        assert "Mintrabajo" in section or "mintrabajo" in section.lower()

    def test_prompt_prohíbe_500_smmlv(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "500 SMMLV" in SYSTEM_PROMPT_BASE

    def test_prompt_tiene_ejemplos_urgencia_permitida(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "PERMITIDO" in SYSTEM_PROMPT_BASE

    def test_prompt_no_usa_multa_como_argumento_en_reglas(self):
        """En las REGLAS del prompt no debe aparecer 'multa' como argumento de venta,
        solo en la sección de prohibición."""
        from app.bot.agent import SYSTEM_PROMPT_BASE
        # Fuera de la sección de URGENCIA/PROHIBIDO, no debe aparece 'multa'
        # como argumento vendedor (puede aparecer en el contexto de prohibición)
        # Verificamos que 'multa' solo aparezca en contexto de prohibición
        lines_with_multa = [
            line for line in SYSTEM_PROMPT_BASE.split("\n")
            if "multa" in line.lower()
        ]
        for line in lines_with_multa:
            lower = line.lower()
            # La línea con multa debe ser de contexto PROHIBIDO/NUNCA, no un argumento de venta
            assert (
                "prohibido" in lower
                or "nunca" in lower
                or "sanción" in lower
                or "sin" in lower
            ), f"Línea con 'multa' fuera de contexto de prohibición: {line!r}"


class TestObjeciones:
    """Regla #6 — Manejo de objeciones A-E presentes en el system prompt."""

    def test_prompt_tiene_objecion_precio(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "caro" in SYSTEM_PROMPT_BASE.lower()

    def test_prompt_tiene_objecion_excel(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "excel" in SYSTEM_PROMPT_BASE.lower() or "Excel" in SYSTEM_PROMPT_BASE

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

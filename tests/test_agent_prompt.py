"""Tests del system prompt del bot WhatsApp (Module 2).

Verifica que SYSTEM_PROMPT_BASE cumple los invariantes del rediseño:
- Identidad Vera (asesora SST, no vendedor genérico)
- Sin precios hardcodeados ni precio de otros productos
- Sin sección setup como costo
- Contiene tag [PLAN_RECOMENDADO]
- El prompt completo (base + catálogo + knowledge) contiene los datos del catálogo
  y no supera el límite de tamaño razonable.
"""
from __future__ import annotations

import pytest

from app.bot.agent import SYSTEM_PROMPT_BASE
from app.pricing.catalog import prompt_inyectable
from app.bot.knowledge_loader import load_knowledge


def full_system_prompt() -> str:
    return SYSTEM_PROMPT_BASE + "\n\n" + prompt_inyectable() + "\n\n" + load_knowledge()


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT_BASE — invariantes del texto base
# ---------------------------------------------------------------------------

class TestSystemPromptBase:
    def test_identidad_vera_asesora(self):
        assert "Vera, vendedora" in SYSTEM_PROMPT_BASE or "Vera, la asesora SST" in SYSTEM_PROMPT_BASE

    def test_no_dice_asesor_comercial_generico(self):
        # La identidad cambió de "asesor comercial" a "Vera, asesora SST"
        assert "eres el asesor comercial" not in SYSTEM_PROMPT_BASE.lower()

    def test_contiene_plan_recomendado_tag(self):
        # M4.1: el tag [PLAN_RECOMENDADO] fue reemplazado por el tool recomendar_plan_y_cerrar
        assert "recomendar_plan_y_cerrar" in SYSTEM_PROMPT_BASE or "PLAN_RECOMENDADO" in SYSTEM_PROMPT_BASE

    def test_contiene_tool_recomendar(self):
        """M3: recomendar_plan_y_cerrar reemplaza [SST_READY]."""
        assert "recomendar_plan_y_cerrar" in SYSTEM_PROMPT_BASE

    def test_contiene_tool_escalar_demo(self):
        """M3: escalar_a_demo reemplaza [BOOKING_READY]."""
        assert "escalar_a_demo" in SYSTEM_PROMPT_BASE

    def test_contiene_tool_escalar_humano(self):
        """M3: escalar_a_humano reemplaza [HANDOFF_NEEDED]."""
        assert "escalar_a_humano" in SYSTEM_PROMPT_BASE

    def test_contiene_tool_cotizacion(self):
        """M3: pedir_cotizacion_por_correo reemplaza [SEND_QUOTE]."""
        assert "pedir_cotizacion_por_correo" in SYSTEM_PROMPT_BASE

    def test_no_contiene_tags_terminales_legacy(self):
        """Los tags terminales ya no están en el prompt base (son herramientas)."""
        assert "[SST_READY]" not in SYSTEM_PROMPT_BASE
        assert "[BOOKING_READY]" not in SYSTEM_PROMPT_BASE
        assert "[HANDOFF_NEEDED]" not in SYSTEM_PROMPT_BASE
        assert "[SEND_QUOTE" not in SYSTEM_PROMPT_BASE

    def test_setup_solo_en_contexto_prohibitivo(self):
        """'setup' solo puede aparecer en el contexto de prohibición, nunca como costo."""
        base = SYSTEM_PROMPT_BASE.lower()
        idx = base.find("setup")
        while idx != -1:
            window = base[max(0, idx - 100): idx + 100]
            prohibitive = any(w in window for w in ["nunca", "no hay", "no existe", "sin"])
            assert prohibitive, f"'setup' encontrado fuera de contexto prohibitivo: ...{window}..."
            idx = base.find("setup", idx + 1)

    def test_no_seccion_precios_flow(self):
        assert "PRECIOS FLOW" not in SYSTEM_PROMPT_BASE
        assert "Setup Flow" not in SYSTEM_PROMPT_BASE

    def test_no_precios_legacy_flow(self):
        # Precios de Verifty Flow legacy (INDIVIDUAL/EQUIPO/ESSENTIAL) no deben estar en el base
        assert "$ 120.000" not in SYSTEM_PROMPT_BASE
        assert "$ 315.000" not in SYSTEM_PROMPT_BASE
        assert "$ 595.000" not in SYSTEM_PROMPT_BASE
        assert "120.000" not in SYSTEM_PROMPT_BASE
        assert "315.000" not in SYSTEM_PROMPT_BASE

    def test_no_precios_hardcodeados_sst(self):
        # Los precios SST vienen del catálogo, no deben estar hardcodeados en el base
        assert "39.000" not in SYSTEM_PROMPT_BASE
        assert "220.000" not in SYSTEM_PROMPT_BASE
        assert "600.000" not in SYSTEM_PROMPT_BASE
        assert "1.220.000" not in SYSTEM_PROMPT_BASE

    def test_termina_con_referencia_catalogo(self):
        # M4.1: el prompt usa "catálogo (fuente única de verdad)"
        assert "catálogo" in SYSTEM_PROMPT_BASE

    def test_es_string_no_vacio(self):
        assert isinstance(SYSTEM_PROMPT_BASE, str)
        assert len(SYSTEM_PROMPT_BASE) > 500

    def test_estructura_m41(self):
        # M4.1 usa INVIOLABLES + 5 FASES en vez de REGLA #N
        assert "INVIOLABLES" in SYSTEM_PROMPT_BASE
        for n in range(1, 6):
            assert f"FASE {n}" in SYSTEM_PROMPT_BASE, f"FASE {n} ausente"


# ---------------------------------------------------------------------------
# Prompt completo (base + catálogo + knowledge) — invariantes de integración
# ---------------------------------------------------------------------------

class TestFullSystemPrompt:
    def test_contiene_vera_vendedora(self):
        assert "Vera" in full_system_prompt() and "SST" in full_system_prompt()

    def test_contiene_precio_pro_del_catalogo(self):
        # "$ 600.000" viene de prompt_inyectable(), no del base
        assert "$ 600.000" in full_system_prompt()

    def test_contiene_precio_basic(self):
        assert "$ 39.000" in full_system_prompt()

    def test_contiene_instruccion_solo_cotizar(self):
        assert "SOLO puedes cotizar los planes listados" in full_system_prompt()

    def test_no_contiene_precios_legacy_flow(self):
        p = full_system_prompt()
        assert "$ 120.000" not in p
        assert "$ 315.000" not in p
        assert "$ 595.000" not in p

    def test_contiene_todos_los_codigos_plan(self):
        p = full_system_prompt()
        for codigo in ("BASIC", "STARTER", "PRO", "PLUS", "CORPORATIVO"):
            assert codigo in p, f"Plan {codigo} ausente en el prompt completo"

    def test_tamano_base_mas_catalogo(self):
        # El bloque base + catálogo (sin knowledge) debe ser compacto.
        # M4 añadió MODULOS_POR_PLAN al catálogo, lo que amplía el tamaño intencionalmente.
        # El knowledge completo es grande por diseño (~50k chars) y no se limita aquí.
        parte_fija = SYSTEM_PROMPT_BASE + "\n\n" + prompt_inyectable()
        assert len(parte_fija) < 22_000, f"base + catálogo demasiado largo: {len(parte_fija)} chars"

    def test_corporativo_sin_999_sedes(self):
        # El catálogo debe mostrar "ilimitadas" para CORPORATIVO, no "999 sedes"
        assert "999 sede" not in full_system_prompt()

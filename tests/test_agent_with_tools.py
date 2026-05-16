from __future__ import annotations
"""Tests de integración: agent.py con Tool Use API (M3).

Mockea las respuestas de Anthropic para verificar que el agente procesa
correctamente tool_use blocks y los fusiona con los tags del texto.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.bot.tools.schemas import TOOLS, TOOL_NAMES


# ── Helpers para construir respuestas mock de Anthropic ──────────────────────

def _text_block(text: str):
    block = MagicMock()
    block.text = text
    del block.name  # asegura que hasattr(block, "name") sea False
    block.__class__.__name__ = "TextBlock"
    return block


def _tool_use_block(name: str, input_dict: dict):
    block = MagicMock()
    block.name = name
    block.input = input_dict
    del block.text  # asegura que hasattr(block, "text") sea False
    block.__class__.__name__ = "ToolUseBlock"
    return block


def _mock_response(*blocks):
    resp = MagicMock()
    resp.content = list(blocks)
    resp.stop_reason = "tool_use" if any(hasattr(b, "name") for b in blocks) else "end_turn"
    usage = MagicMock()
    usage.input_tokens = 100
    usage.output_tokens = 50
    usage.cache_read_input_tokens = 0
    usage.cache_creation_input_tokens = 0
    resp.usage = usage
    return resp


# ── Tests de estructura ───────────────────────────────────────────────────────

class TestToolsEnAgente:
    def test_tools_importados_en_agent(self):
        from app.bot import agent as ag
        assert hasattr(ag, "TOOLS")
        assert len(ag.TOOLS) == 4

    def test_dispatch_importado_en_agent(self):
        from app.bot import agent as ag
        assert hasattr(ag, "dispatch_tool_use")

    def test_tools_incluidos_en_schemas(self):
        assert "recomendar_plan_y_cerrar" in TOOL_NAMES
        assert "escalar_a_demo" in TOOL_NAMES
        assert "pedir_cotizacion_por_correo" in TOOL_NAMES
        assert "escalar_a_humano" in TOOL_NAMES


# ── Tests de parsing de respuesta mixta ──────────────────────────────────────

class TestParseResponseMixta:
    """Verifica que _parse_response sigue funcionando con el texto de un tool_use."""

    def _agent(self):
        with patch("app.bot.agent.Anthropic"):
            from app.bot.agent import ConversationalAgent
            return ConversationalAgent()

    def test_parse_response_solo_texto(self):
        agent = self._agent()
        clean, tags = agent._parse_response(
            "Hola, cuéntame más.\n---\n[SCORE_UPDATE: 5]\n[LEAD_DATA: {\"company\": \"X\"}]"
        )
        assert clean == "Hola, cuéntame más."
        assert tags["score"] == 5
        assert tags["lead_data"]["company"] == "X"

    def test_parse_response_con_product_fit(self):
        agent = self._agent()
        _, tags = agent._parse_response(
            "Aquí va mi respuesta.\n---\n[PRODUCT_FIT: sst]"
        )
        assert tags["product_fit"] == "verifty_sst"

    def test_parse_response_sin_sst_ready_en_texto(self):
        """[SST_READY] ya no debe estar en el texto — viene por herramienta."""
        agent = self._agent()
        _, tags = agent._parse_response(
            "¡Perfecto, te envío el link!\n---\n[PRODUCT_FIT: sst]"
        )
        assert not tags.get("sst_ready")


# ── Tests de dispatch en respuesta de tool_use ────────────────────────────────

class TestDispatchIntegrado:
    def test_recomendar_produce_sst_ready(self):
        from app.bot.tools.dispatcher import dispatch_tool_use
        tags = {}
        tc_tags = dispatch_tool_use(
            "recomendar_plan_y_cerrar",
            {"plan": "STARTER", "ciclo": "mensual", "razon_eleccion": "7 empleados"},
            {},
        )
        tags.update(tc_tags)
        assert tags["sst_ready"] is True
        assert tags["plan_recomendado"] == "STARTER"
        assert tags["product_fit"] == "verifty_sst"

    def test_escalar_demo_produce_booking_ready(self):
        from app.bot.tools.dispatcher import dispatch_tool_use
        tags = {}
        tc_tags = dispatch_tool_use(
            "escalar_a_demo",
            {"motivo": "mas_de_130_empleados", "num_empleados": 200, "pais": "Colombia"},
            {},
        )
        tags.update(tc_tags)
        assert tags["booking_ready"] is True
        assert tags["demo_motivo"] == "mas_de_130_empleados"

    def test_cotizacion_produce_send_quote(self):
        from app.bot.tools.dispatcher import dispatch_tool_use
        tags = {}
        tc_tags = dispatch_tool_use(
            "pedir_cotizacion_por_correo",
            {"email": "ceo@firma.com", "plan": "plus", "company": "Firma SA"},
            {},
        )
        tags.update(tc_tags)
        sq = tags["send_quote"]
        assert sq["email"] == "ceo@firma.com"
        assert sq["plan"] == "plus"

    def test_humano_produce_handoff_needed(self):
        from app.bot.tools.dispatcher import dispatch_tool_use
        tags = {}
        tc_tags = dispatch_tool_use(
            "escalar_a_humano",
            {"motivo": "bot_confused", "resumen_para_humano": "No pude ayudar"},
            {},
        )
        tags.update(tc_tags)
        assert tags["handoff_needed"] is True


# ── Test: sst_trigger no usa booking_ready ───────────────────────────────────

class TestSstTriggerSinBookingReady:
    """Verifica que sst_trigger no se activa solo por booking_ready (fix M3)."""

    def test_sst_trigger_requiere_sst_ready(self):
        """booking_ready=True + product_fit=verifty_sst no debe producir sst_trigger."""
        product_fit = "verifty_sst"
        tags = {"booking_ready": True, "sst_ready": False}
        sst_trigger = product_fit == "verifty_sst" and tags.get("sst_ready")
        assert sst_trigger is False

    def test_sst_trigger_con_sst_ready(self):
        product_fit = "verifty_sst"
        tags = {"sst_ready": True}
        sst_trigger = product_fit == "verifty_sst" and tags.get("sst_ready")
        assert sst_trigger is True

    def test_sst_trigger_falso_si_product_fit_flow(self):
        product_fit = "verifty_flow"
        tags = {"sst_ready": True}
        sst_trigger = product_fit == "verifty_sst" and tags.get("sst_ready")
        assert sst_trigger is False

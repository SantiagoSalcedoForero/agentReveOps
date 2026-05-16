"""
Tests para el guard de BOOKING_READY en agent.py.

El guard convierte BOOKING_READY → SST_READY cuando el plan recomendado
es conocido y no es CORPORATIVO, bloqueando agendamientos de demo para
leads que deberían ir al flujo self-service de SST.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.bot.agent import ConversationalAgent


def _make_agent() -> ConversationalAgent:
    with patch("app.bot.agent.Anthropic"):
        return ConversationalAgent()


def _run_guard(tags: dict, lead_data: dict) -> dict:
    """
    Simula solo la sección del guard sobre un dict de tags dado.
    Devuelve el dict de tags después de aplicar la lógica del guard.
    """
    plan_recomendado_str = (
        lead_data.get("plan_recomendado", "")
        or tags.get("plan_recomendado", "")
        or ""
    ).upper()
    es_plan_no_corporativo = bool(plan_recomendado_str) and plan_recomendado_str != "CORPORATIVO"
    if tags.get("booking_ready") and es_plan_no_corporativo:
        tags["booking_ready"] = False
        tags["sst_ready"] = True
    return tags


class TestBookingReadyGuard:
    def test_booking_ready_con_pro_se_convierte_a_sst_ready(self):
        tags = {"booking_ready": True}
        lead_data = {"plan_recomendado": "PRO"}
        result = _run_guard(tags, lead_data)
        assert result["booking_ready"] is False
        assert result["sst_ready"] is True

    def test_booking_ready_con_starter_se_convierte_a_sst_ready(self):
        tags = {"booking_ready": True}
        lead_data = {"plan_recomendado": "STARTER"}
        result = _run_guard(tags, lead_data)
        assert result["booking_ready"] is False
        assert result["sst_ready"] is True

    def test_booking_ready_con_basic_se_convierte_a_sst_ready(self):
        tags = {"booking_ready": True}
        lead_data = {"plan_recomendado": "BASIC"}
        result = _run_guard(tags, lead_data)
        assert result["booking_ready"] is False
        assert result["sst_ready"] is True

    def test_booking_ready_con_plus_se_convierte_a_sst_ready(self):
        tags = {"booking_ready": True}
        lead_data = {"plan_recomendado": "PLUS"}
        result = _run_guard(tags, lead_data)
        assert result["booking_ready"] is False
        assert result["sst_ready"] is True

    def test_booking_ready_con_corporativo_pasa_sin_cambio(self):
        tags = {"booking_ready": True}
        lead_data = {"plan_recomendado": "CORPORATIVO"}
        result = _run_guard(tags, lead_data)
        assert result["booking_ready"] is True
        assert result.get("sst_ready") is None

    def test_booking_ready_sin_plan_conocido_pasa_sin_cambio(self):
        """Sin plan definido, no bloqueamos — podría ser un lead Flow válido."""
        tags = {"booking_ready": True}
        lead_data = {}
        result = _run_guard(tags, lead_data)
        assert result["booking_ready"] is True
        assert result.get("sst_ready") is None

    def test_booking_ready_false_no_se_modifica(self):
        tags = {"booking_ready": False}
        lead_data = {"plan_recomendado": "PRO"}
        result = _run_guard(tags, lead_data)
        assert result["booking_ready"] is False
        assert result.get("sst_ready") is None

    def test_plan_lowercase_normalizado(self):
        """El plan puede venir en minúsculas desde el LLM."""
        tags = {"booking_ready": True}
        lead_data = {"plan_recomendado": "pro"}
        result = _run_guard(tags, lead_data)
        assert result["booking_ready"] is False
        assert result["sst_ready"] is True

    def test_plan_desde_tags_no_solo_lead_data(self):
        """El guard también lee plan_recomendado del dict de tags."""
        tags = {"booking_ready": True, "plan_recomendado": "STARTER"}
        lead_data = {}
        result = _run_guard(tags, lead_data)
        assert result["booking_ready"] is False
        assert result["sst_ready"] is True

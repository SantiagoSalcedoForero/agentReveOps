"""Tests de cálculo de costo para claude-sonnet-4-5 (M4.1)."""
from __future__ import annotations

from app.bot.pricing import calculate_cost_usd


class TestCostSonnet:

    MODEL = "claude-sonnet-4-5"

    def test_cost_sonnet_input_only(self):
        # 1M tokens de input a $3.00/M = $3.00
        cost = calculate_cost_usd(self.MODEL, input_tokens=1_000_000)
        assert abs(cost - 3.00) < 0.001

    def test_cost_sonnet_output_only(self):
        # 1M tokens de output a $15.00/M = $15.00
        cost = calculate_cost_usd(self.MODEL, output_tokens=1_000_000)
        assert abs(cost - 15.00) < 0.001

    def test_cost_sonnet_with_cache_read(self):
        # 1M cache_read a $0.30/M = $0.30
        cost = calculate_cost_usd(self.MODEL, cache_read_tokens=1_000_000)
        assert abs(cost - 0.30) < 0.001

    def test_cost_sonnet_total(self):
        # Conversación típica: 5k input, 300 output, 50k cache_read
        cost = calculate_cost_usd(
            self.MODEL,
            input_tokens=5_000,
            output_tokens=300,
            cache_read_tokens=50_000,
        )
        expected = (
            (5_000 / 1_000_000) * 3.00
            + (300 / 1_000_000) * 15.00
            + (50_000 / 1_000_000) * 0.30
        )
        assert abs(cost - expected) < 0.000_01

    def test_sonnet_mas_caro_que_haiku(self):
        haiku = calculate_cost_usd(
            "claude-haiku-4-5-20251001", input_tokens=10_000, output_tokens=500
        )
        sonnet = calculate_cost_usd(
            self.MODEL, input_tokens=10_000, output_tokens=500
        )
        assert sonnet > haiku, "Sonnet debe ser más caro que Haiku"

    def test_config_default_es_sonnet(self):
        from app.config import settings
        assert "sonnet" in settings.ANTHROPIC_MODEL.lower(), (
            f"Modelo default debe ser Sonnet, era: {settings.ANTHROPIC_MODEL}"
        )

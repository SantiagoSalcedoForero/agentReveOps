"""Precio por token de los modelos Anthropic (USD por 1M tokens).
Actualizar cuando cambien los precios publicados.
"""
from __future__ import annotations

# USD per 1,000,000 tokens (per Anthropic pricing page)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,   # 1.25x input
        "cache_read": 0.10,    # 0.10x input
    },
    "claude-sonnet-4-5": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-opus-4-6": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
}

DEFAULT = MODEL_PRICING["claude-haiku-4-5-20251001"]


def calculate_cost_usd(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Cost in USD for a single Anthropic call given its usage counters."""
    # Try exact match, fallback to prefix match, then default
    p = MODEL_PRICING.get(model)
    if p is None:
        for k, v in MODEL_PRICING.items():
            if model.startswith(k.split("-", 3)[0] + "-" + k.split("-", 3)[1]):
                p = v
                break
    if p is None:
        p = DEFAULT

    per_token_in    = p["input"]       / 1_000_000
    per_token_out   = p["output"]      / 1_000_000
    per_token_cw    = p["cache_write"] / 1_000_000
    per_token_cr    = p["cache_read"]  / 1_000_000

    cost = (
        input_tokens       * per_token_in
        + output_tokens    * per_token_out
        + cache_write_tokens * per_token_cw
        + cache_read_tokens  * per_token_cr
    )
    return round(cost, 6)

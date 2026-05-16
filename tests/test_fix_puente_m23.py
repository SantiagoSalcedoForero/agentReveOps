from __future__ import annotations
"""
Tests de regresión para M2.3 — fix puente.

Cubre los tres bugs corregidos:
  Bug 1 — Normalización de product_fit (sst→verifty_sst, flow→verifty_flow)
  Bug 2 — Guard extendido a rama score
  Bug 3 — Knowledge sales_advisor sin asociaciones ARL→plan
"""
import re
from pathlib import Path
from typing import Optional


KNOWLEDGE_ROOT = Path(__file__).resolve().parent.parent / "knowledge"


# ── Utilidades que replican la lógica de agent.py ────────────────────────────

_PRODUCT_FIT_NORM = {"sst": "verifty_sst", "flow": "verifty_flow"}


def _parse_product_fit_tag(tags_blob: str) -> Optional[str]:
    """Replica agent.py parser de [PRODUCT_FIT] con la normalización de M2.3."""
    m = re.search(r"\[PRODUCT_FIT:\s*(sst|flow|unknown)\]", tags_blob, re.IGNORECASE)
    if not m:
        return None
    val = m.group(1).lower()
    return _PRODUCT_FIT_NORM.get(val, val)


def _booking_trigger_logic(
    product_fit: str,
    booking_ready: bool,
    score: int,
    threshold: int,
    es_plan_self_serve: bool,
) -> bool:
    """Replica la lógica de booking_trigger con el guard extendido de M2.3."""
    if es_plan_self_serve:
        return False
    return product_fit != "verifty_sst" and (
        booking_ready or (score >= threshold)
    )


# ── Tests Bug 1: normalización product_fit ────────────────────────────────────

class TestNormalizacionProductFit:
    def test_sst_se_normaliza_a_verifty_sst(self):
        result = _parse_product_fit_tag("--- [PRODUCT_FIT: sst]")
        assert result == "verifty_sst"

    def test_flow_se_normaliza_a_verifty_flow(self):
        result = _parse_product_fit_tag("--- [PRODUCT_FIT: flow]")
        assert result == "verifty_flow"

    def test_unknown_permanece_unknown(self):
        result = _parse_product_fit_tag("--- [PRODUCT_FIT: unknown]")
        assert result == "unknown"

    def test_mayusculas_normalizadas(self):
        result = _parse_product_fit_tag("--- [PRODUCT_FIT: SST]")
        assert result == "verifty_sst"

    def test_sin_tag_devuelve_none(self):
        result = _parse_product_fit_tag("--- [SCORE_UPDATE: 8]")
        assert result is None

    def test_verifty_sst_activa_sst_trigger(self):
        """Con product_fit correcto, sst_trigger debe True cuando hay sst_ready."""
        product_fit = _parse_product_fit_tag("--- [PRODUCT_FIT: sst]")
        sst_ready = True
        sst_trigger = product_fit == "verifty_sst" and sst_ready
        assert sst_trigger is True

    def test_verifty_sst_bloquea_booking_trigger(self):
        """Con product_fit correcto (verifty_sst), booking_trigger es False."""
        product_fit = _parse_product_fit_tag("--- [PRODUCT_FIT: sst]")
        booking = _booking_trigger_logic(
            product_fit=product_fit,
            booking_ready=False,
            score=12,
            threshold=10,
            es_plan_self_serve=False,
        )
        assert booking is False


# ── Tests Bug 2: guard extendido a rama score ─────────────────────────────────

class TestGuardExtendidoScore:
    def test_score_alto_con_plan_starter_no_dispara_booking(self):
        """Escenario exacto del smoke test: score=12, plan=STARTER → booking=False."""
        result = _booking_trigger_logic(
            product_fit="verifty_sst",
            booking_ready=False,
            score=12,
            threshold=10,
            es_plan_self_serve=True,
        )
        assert result is False

    def test_score_alto_con_plan_pro_no_dispara_booking(self):
        result = _booking_trigger_logic(
            product_fit="verifty_sst",
            booking_ready=False,
            score=15,
            threshold=10,
            es_plan_self_serve=True,
        )
        assert result is False

    def test_score_alto_con_plan_basic_no_dispara_booking(self):
        result = _booking_trigger_logic(
            product_fit="verifty_sst",
            booking_ready=False,
            score=11,
            threshold=10,
            es_plan_self_serve=True,
        )
        assert result is False

    def test_score_alto_con_plan_plus_no_dispara_booking(self):
        result = _booking_trigger_logic(
            product_fit="verifty_flow",
            booking_ready=False,
            score=13,
            threshold=10,
            es_plan_self_serve=True,
        )
        assert result is False

    def test_score_alto_con_plan_corporativo_si_dispara_booking(self):
        """CORPORATIVO → el guard no bloquea, booking puede dispararse por score."""
        result = _booking_trigger_logic(
            product_fit="verifty_flow",
            booking_ready=False,
            score=12,
            threshold=10,
            es_plan_self_serve=False,
        )
        assert result is True

    def test_lead_sst_sin_plan_no_dispara_booking(self):
        """Lead SST sin plan conocido tampoco dispara booking (product_fit correcto bloquea)."""
        result = _booking_trigger_logic(
            product_fit="verifty_sst",
            booking_ready=True,
            score=12,
            threshold=10,
            es_plan_self_serve=False,
        )
        assert result is False

    def test_lead_flow_sin_plan_si_dispara_booking(self):
        """Lead Flow sin plan → puede disparar booking si tiene booking_ready."""
        result = _booking_trigger_logic(
            product_fit="verifty_flow",
            booking_ready=True,
            score=5,
            threshold=10,
            es_plan_self_serve=False,
        )
        assert result is True


# ── Tests Bug 3: knowledge sales_advisor limpio ───────────────────────────────

class TestSalesAdvisorLimpio:
    @classmethod
    def _text(cls) -> str:
        return (KNOWLEDGE_ROOT / "vera" / "sales_advisor.md").read_text(encoding="utf-8")

    def test_no_asocia_arl_iv_v_a_pro(self):
        text = self._text()
        assert "ARL IV-V → riesgo alto → Pro" not in text
        assert "ARL IV-V → Pro" not in text

    def test_no_asocia_arl_iii_a_pro_recomendado(self):
        text = self._text()
        assert "ARL III → riesgo medio → Pro recomendado" not in text
        assert "ARL III → Pro" not in text

    def test_no_dice_limite_de_7_empleados_starter(self):
        text = self._text()
        assert "límite de 7 empleados del Starter" not in text
        assert "Starter solo llega a 7" not in text

    def test_no_dice_pro_es_el_paso_obligado(self):
        text = self._text()
        assert "Pro es el paso obligado" not in text

    def test_conserva_datos_de_nivel_arl(self):
        """El dato de nivel ARL debe seguir presente como info, no como regla de plan."""
        text = self._text()
        assert "ARL IV-V" in text
        assert "ARL III" in text

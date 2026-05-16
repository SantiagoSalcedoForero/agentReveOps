from __future__ import annotations
"""Tests unitarios para los handlers de Tool Use (M3)."""

from app.bot.tools.handlers import (
    PALABRAS_PROHIBIDAS,
    handle_escalar_a_demo,
    handle_escalar_a_humano,
    handle_pedir_cotizacion_por_correo,
    handle_recomendar_plan_y_cerrar,
)


class TestRecomendar:
    def _call(self, plan="PRO", ciclo="mensual", razon="tiene 22 empleados y necesita salud ocupacional"):
        return handle_recomendar_plan_y_cerrar(
            {"plan": plan, "ciclo": ciclo, "razon_eleccion": razon}, {}
        )

    def test_sst_ready_true(self):
        tags = self._call()
        assert tags["sst_ready"] is True

    def test_plan_recomendado_normalizado(self):
        tags = self._call(plan="pro")
        assert tags["plan_recomendado"] == "PRO"

    def test_product_fit_verifty_sst(self):
        tags = self._call()
        assert tags["product_fit"] == "verifty_sst"

    def test_ciclo_facturacion(self):
        tags = self._call(ciclo="anual")
        assert tags["ciclo_facturacion"] == "anual"

    def test_razon_limpia_se_conserva(self):
        razon = "tienen 15 empleados en manufactura y necesitan IPEVR"
        tags = self._call(razon=razon)
        assert tags["razon_sanitizada"] == razon

    def test_palabras_prohibidas_se_eliminan(self):
        razon = "es obligatoria por normativa del Mintrabajo"
        tags = self._call(razon=razon)
        for p in PALABRAS_PROHIBIDAS:
            assert p.lower() not in tags["razon_sanitizada"].lower()

    def test_palabras_prohibidas_lista_no_vacia(self):
        assert len(PALABRAS_PROHIBIDAS) >= 5


class TestEscalarDemo:
    def _call(self, motivo="mas_de_130_empleados", **kw):
        return handle_escalar_a_demo({"motivo": motivo, **kw}, {})

    def test_booking_ready_true(self):
        assert self._call()["booking_ready"] is True

    def test_demo_motivo(self):
        tags = self._call(motivo="corporativo_sst")
        assert tags["demo_motivo"] == "corporativo_sst"

    def test_num_empleados_opcional(self):
        tags = self._call(num_empleados=200)
        assert tags["demo_num_empleados"] == 200

    def test_pais_opcional(self):
        tags = self._call(pais="Colombia")
        assert tags["demo_pais"] == "Colombia"

    def test_sin_empleados_no_falla(self):
        tags = self._call()
        assert "demo_num_empleados" not in tags


class TestPedirCotizacion:
    def _call(self, **kw):
        defaults = {"email": "ceo@empresa.com", "plan": "pro", "company": "Acero SA"}
        return handle_pedir_cotizacion_por_correo({**defaults, **kw}, {})

    def test_send_quote_dict(self):
        tags = self._call()
        assert "send_quote" in tags
        sq = tags["send_quote"]
        assert sq["email"] == "ceo@empresa.com"
        assert sq["plan"] == "pro"
        assert sq["company"] == "Acero SA"

    def test_contact_name_opcional(self):
        tags = self._call(contact_name="María López")
        assert tags["send_quote"]["contact_name"] == "María López"

    def test_sin_contact_name_ok(self):
        tags = self._call()
        assert tags["send_quote"]["contact_name"] == ""


class TestEscalarHumano:
    def _call(self, motivo="bot_confused", resumen="Lead interesado en Pro, 22 emp"):
        return handle_escalar_a_humano(
            {"motivo": motivo, "resumen_para_humano": resumen}, {}
        )

    def test_handoff_needed_true(self):
        assert self._call()["handoff_needed"] is True

    def test_handoff_reason(self):
        tags = self._call(motivo="urgencia_auditoria")
        assert tags["handoff_reason"] == "urgencia_auditoria"

    def test_resumen_guardado(self):
        resumen = "Empresa de 50 empleados, sector construcción, pregunta por IPEVR"
        tags = self._call(resumen=resumen)
        assert tags["handoff_resumen"] == resumen

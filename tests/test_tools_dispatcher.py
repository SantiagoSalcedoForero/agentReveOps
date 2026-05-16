from __future__ import annotations
"""Tests para el dispatcher de Tool Use (M3)."""

from app.bot.tools.dispatcher import dispatch_tool_use


class TestDispatcher:
    def test_recomendar_plan_y_cerrar_enruta(self):
        tags = dispatch_tool_use(
            "recomendar_plan_y_cerrar",
            {"plan": "PRO", "ciclo": "mensual", "razon_eleccion": "22 empleados manufactura"},
            {},
        )
        assert tags.get("sst_ready") is True
        assert tags.get("plan_recomendado") == "PRO"

    def test_escalar_a_demo_enruta(self):
        tags = dispatch_tool_use(
            "escalar_a_demo",
            {"motivo": "mas_de_130_empleados"},
            {},
        )
        assert tags.get("booking_ready") is True

    def test_pedir_cotizacion_enruta(self):
        tags = dispatch_tool_use(
            "pedir_cotizacion_por_correo",
            {"email": "a@b.com", "plan": "pro", "company": "X"},
            {},
        )
        assert "send_quote" in tags

    def test_escalar_humano_enruta(self):
        tags = dispatch_tool_use(
            "escalar_a_humano",
            {"motivo": "solicitud_explicita", "resumen_para_humano": "quiere humano"},
            {},
        )
        assert tags.get("handoff_needed") is True

    def test_tool_desconocido_devuelve_dict_vacio(self):
        tags = dispatch_tool_use("herramienta_inexistente", {}, {})
        assert tags == {}

    def test_contexto_se_pasa_al_handler(self):
        ctx = {"product_fit": "verifty_sst", "score": 12}
        tags = dispatch_tool_use(
            "escalar_a_demo",
            {"motivo": "corporativo_sst"},
            ctx,
        )
        # El handler recibe el contexto sin error
        assert tags.get("booking_ready") is True

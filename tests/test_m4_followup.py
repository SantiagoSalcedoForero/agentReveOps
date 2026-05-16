"""Tests para el follow-up 24h SST (M4).

Cubre:
- MODULOS_POR_PLAN estructura correcta
- encontrar_plan_minimo_con_modulo busca en orden ascendente
- Handler sst_link_followup registrado en scheduler
- Config OUTBOUND_SST_FOLLOWUP_TEMPLATE presente
- Migración SQL 012 existe
"""
from __future__ import annotations

from pathlib import Path


class TestModulosPorPlan:

    def test_todos_los_planes_tienen_modulos(self):
        from app.pricing.catalog import MODULOS_POR_PLAN, PLANES_BASE
        for plan in PLANES_BASE:
            assert plan.codigo in MODULOS_POR_PLAN, (
                f"Plan {plan.codigo} no tiene entrada en MODULOS_POR_PLAN"
            )

    def test_cada_plan_tiene_incluye_y_no_incluye(self):
        from app.pricing.catalog import MODULOS_POR_PLAN
        for codigo, mods in MODULOS_POR_PLAN.items():
            assert "incluye" in mods, f"{codigo} falta 'incluye'"
            assert "no_incluye" in mods, f"{codigo} falta 'no_incluye'"
            assert isinstance(mods["incluye"], list)
            assert isinstance(mods["no_incluye"], list)

    def test_corporativo_no_incluye_vacio(self):
        from app.pricing.catalog import MODULOS_POR_PLAN
        assert MODULOS_POR_PLAN["CORPORATIVO"]["no_incluye"] == []


class TestEncontrarPlanMinimo:

    def test_ipevr_en_starter(self):
        from app.pricing.catalog import encontrar_plan_minimo_con_modulo
        plan = encontrar_plan_minimo_con_modulo("ipevr")
        assert plan is not None
        assert plan.codigo == "STARTER"

    def test_salud_ocupacional_en_pro(self):
        from app.pricing.catalog import encontrar_plan_minimo_con_modulo
        plan = encontrar_plan_minimo_con_modulo("salud ocupacional")
        assert plan is not None
        assert plan.codigo == "PRO"

    def test_contratistas_en_plus(self):
        from app.pricing.catalog import encontrar_plan_minimo_con_modulo
        plan = encontrar_plan_minimo_con_modulo("contratistas")
        assert plan is not None
        assert plan.codigo == "PLUS"

    def test_modulo_inexistente_retorna_none(self):
        from app.pricing.catalog import encontrar_plan_minimo_con_modulo
        plan = encontrar_plan_minimo_con_modulo("módulo que no existe xyz")
        assert plan is None

    def test_busqueda_case_insensitive(self):
        from app.pricing.catalog import encontrar_plan_minimo_con_modulo
        plan_lower = encontrar_plan_minimo_con_modulo("ipevr")
        plan_upper = encontrar_plan_minimo_con_modulo("IPEVR")
        assert plan_lower is not None
        assert plan_upper is not None
        assert plan_lower.codigo == plan_upper.codigo


class TestFollowupScheduler:

    def test_handler_sst_link_followup_registrado(self):
        from app.outbound.scheduler import HANDLERS
        assert "sst_link_followup" in HANDLERS

    def test_config_template_followup_presente(self):
        from app.config import settings
        assert hasattr(settings, "OUTBOUND_SST_FOLLOWUP_TEMPLATE")
        assert settings.OUTBOUND_SST_FOLLOWUP_TEMPLATE == "verifty_sst_followup"

    def test_migracion_012_existe(self):
        migrations_dir = Path(__file__).parent.parent / "migrations"
        migration = migrations_dir / "012_sst_followup_timestamps.sql"
        assert migration.exists(), "Migración 012_sst_followup_timestamps.sql no encontrada"

    def test_migracion_012_tiene_columnas_correctas(self):
        migrations_dir = Path(__file__).parent.parent / "migrations"
        sql = (migrations_dir / "012_sst_followup_timestamps.sql").read_text()
        assert "last_sst_link_sent_at" in sql
        assert "followup_link_no_pago_enviado_at" in sql

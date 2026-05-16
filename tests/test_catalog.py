"""Tests del catálogo único de planes y precios de Verifty SST.

Cubre todos los límites de recomendar_plan_base, helpers de formato
y precio, deep links y prompt_inyectable.
"""
from __future__ import annotations

import pytest

from app.pricing.catalog import (
    Ciclo,
    PLANES_BASE,
    PLANES_VERA,
    deep_link_compra,
    debe_agendar_demo,
    formato_cop,
    get_plan_base,
    get_plan_vera,
    precio_con_ciclo,
    prompt_inyectable,
    recomendar_plan_base,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def plan(codigo: str):
    """Shortcut para obtener un plan base por código."""
    p = get_plan_base(codigo)
    assert p is not None, f"Plan '{codigo}' no encontrado en el catálogo"
    return p


# ---------------------------------------------------------------------------
# test_recomendar_plan_base — todos los casos frontera
# ---------------------------------------------------------------------------

class TestRecomendarPlanBase:
    """Primer plan que satisface todos los límites, en orden ascendente."""

    # Sin contratistas, 1 sede — límites de empleados

    def test_1_emp(self):
        assert recomendar_plan_base(1).codigo == "BASIC"

    def test_3_emp(self):
        assert recomendar_plan_base(3).codigo == "BASIC"

    def test_4_emp(self):
        # 4 > max_empleados(BASIC)=3 → STARTER
        assert recomendar_plan_base(4).codigo == "STARTER"

    def test_7_emp(self):
        assert recomendar_plan_base(7).codigo == "STARTER"

    def test_8_emp(self):
        # 8 > max_empleados(STARTER)=7 → PRO
        assert recomendar_plan_base(8).codigo == "PRO"

    def test_15_emp(self):
        assert recomendar_plan_base(15).codigo == "PRO"

    def test_30_emp(self):
        assert recomendar_plan_base(30).codigo == "PRO"

    def test_31_emp(self):
        # 31 > max_empleados(PRO)=30 → PLUS
        assert recomendar_plan_base(31).codigo == "PLUS"

    def test_50_emp(self):
        assert recomendar_plan_base(50).codigo == "PLUS"

    def test_80_emp(self):
        assert recomendar_plan_base(80).codigo == "PLUS"

    def test_81_emp(self):
        # 81 > max_empleados(PLUS)=80 → CORPORATIVO
        assert recomendar_plan_base(81).codigo == "CORPORATIVO"

    # Con contratistas — PRO y menores no incluyen contratistas

    def test_5_emp_con_contratistas(self):
        # BASIC/STARTER/PRO no incluyen contratistas → salta a PLUS
        assert recomendar_plan_base(5, tiene_contratistas=True).codigo == "PLUS"

    def test_30_emp_con_contratistas(self):
        # PRO no incluye contratistas → PLUS
        assert recomendar_plan_base(30, tiene_contratistas=True).codigo == "PLUS"

    def test_31_emp_con_contratistas(self):
        # 31 > PRO.max_emp y PRO no incluye contratistas → PLUS (31 ≤ 80)
        assert recomendar_plan_base(31, tiene_contratistas=True).codigo == "PLUS"

    # API/SSO — solo CORPORATIVO lo incluye

    def test_api_sso_1_emp(self):
        assert recomendar_plan_base(1, necesita_api_sso=True).codigo == "CORPORATIVO"

    def test_api_sso_50_emp(self):
        assert recomendar_plan_base(50, necesita_api_sso=True).codigo == "CORPORATIVO"

    def test_api_sso_100_emp(self):
        assert recomendar_plan_base(100, necesita_api_sso=True).codigo == "CORPORATIVO"

    # Multi-sede

    def test_1_sede(self):
        assert recomendar_plan_base(1, num_sedes=1).codigo == "BASIC"

    def test_10_sedes(self):
        # BASIC/STARTER/PRO tienen max_sedes=1 → PLUS (max_sedes=10)
        assert recomendar_plan_base(1, num_sedes=10).codigo == "PLUS"

    def test_11_sedes(self):
        # PLUS.max_sedes=10 < 11 → CORPORATIVO
        assert recomendar_plan_base(1, num_sedes=11).codigo == "CORPORATIVO"

    # Nunca devuelve None
    def test_nunca_none(self):
        assert recomendar_plan_base(0) is not None
        assert recomendar_plan_base(9999) is not None


# ---------------------------------------------------------------------------
# test_precio_con_ciclo
# ---------------------------------------------------------------------------

class TestPrecioConCiclo:
    def test_mensual_sin_descuento(self):
        assert precio_con_ciclo(600_000, Ciclo.MENSUAL) == 600_000

    def test_anual_pro(self):
        # 600_000 * 12 * 0.90 = 6_480_000
        assert precio_con_ciclo(600_000, Ciclo.ANUAL) == 6_480_000

    def test_anual_basic(self):
        # 39_000 * 12 * 0.90 = 421_200
        assert precio_con_ciclo(39_000, Ciclo.ANUAL) == 421_200

    def test_anual_starter(self):
        # 220_000 * 12 * 0.90 = 2_376_000
        assert precio_con_ciclo(220_000, Ciclo.ANUAL) == 2_376_000

    def test_anual_plus(self):
        # 1_220_000 * 12 * 0.90 = 13_176_000
        assert precio_con_ciclo(1_220_000, Ciclo.ANUAL) == 13_176_000

    def test_mensual_basic(self):
        assert precio_con_ciclo(39_000, Ciclo.MENSUAL) == 39_000


# ---------------------------------------------------------------------------
# test_formato_cop
# ---------------------------------------------------------------------------

class TestFormatoCop:
    def test_600k(self):
        assert formato_cop(600_000) == "$ 600.000"

    def test_1220k(self):
        assert formato_cop(1_220_000) == "$ 1.220.000"

    def test_39k(self):
        assert formato_cop(39_000) == "$ 39.000"

    def test_220k(self):
        assert formato_cop(220_000) == "$ 220.000"

    def test_59k(self):
        assert formato_cop(59_000) == "$ 59.000"

    def test_sin_centavos(self):
        # Nunca muestra decimales
        assert "," not in formato_cop(100_000)


# ---------------------------------------------------------------------------
# test_deep_link_compra
# ---------------------------------------------------------------------------

class TestDeepLinkCompra:
    def test_pro_mensual_con_lead_id(self):
        url = deep_link_compra(plan("PRO"), Ciclo.MENSUAL, lead_id="abc123", nueva_empresa=True)
        assert url == "https://sst.verifty.com/agregar-vera?plan=PRO&ciclo=mensual&nueva=1&lead_id=abc123"

    def test_pro_mensual_sin_lead_id(self):
        url = deep_link_compra(plan("PRO"), Ciclo.MENSUAL, nueva_empresa=True)
        assert url == "https://sst.verifty.com/agregar-vera?plan=PRO&ciclo=mensual&nueva=1"
        assert "lead_id" not in url

    def test_pro_anual(self):
        url = deep_link_compra(plan("PRO"), Ciclo.ANUAL)
        assert "ciclo=anual" in url
        assert url.startswith("https://sst.verifty.com/agregar-vera")

    def test_starter_empresa_existente(self):
        url = deep_link_compra(plan("STARTER"), nueva_empresa=False)
        assert "nueva=0" in url

    def test_corporativo_devuelve_mailto(self):
        url = deep_link_compra(plan("CORPORATIVO"))
        assert url == "mailto:hola@sst.verifty.com"

    def test_basic_url_correcta(self):
        url = deep_link_compra(plan("BASIC"))
        assert "plan=BASIC" in url
        assert url.startswith("https://sst.verifty.com/agregar-vera")

    def test_plus_url_correcta(self):
        url = deep_link_compra(plan("PLUS"))
        assert "plan=PLUS" in url


# ---------------------------------------------------------------------------
# test_get_plan_base — lookup case-insensitive
# ---------------------------------------------------------------------------

class TestGetPlanBase:
    def test_lowercase(self):
        assert get_plan_base("pro") is not None
        assert get_plan_base("pro").codigo == "PRO"

    def test_uppercase(self):
        assert get_plan_base("PRO") is not None
        assert get_plan_base("PRO").codigo == "PRO"

    def test_titlecase(self):
        assert get_plan_base("Pro") is not None
        assert get_plan_base("Pro").codigo == "PRO"

    def test_todos_los_codigos(self):
        for codigo in ("BASIC", "STARTER", "PRO", "PLUS", "CORPORATIVO"):
            assert get_plan_base(codigo) is not None, f"Plan {codigo} no encontrado"

    def test_codigo_inexistente(self):
        assert get_plan_base("INEXISTENTE") is None

    def test_devuelve_mismo_objeto(self):
        # frozen dataclass — todas las búsquedas del mismo código son idénticas
        assert get_plan_base("pro") is get_plan_base("PRO")


# ---------------------------------------------------------------------------
# test_get_plan_vera — lookup case-insensitive
# ---------------------------------------------------------------------------

class TestGetPlanVera:
    def test_todos_los_codigos(self):
        for codigo in ("VERA_LITE", "VERA_PRO", "VERA_PLUS"):
            assert get_plan_vera(codigo) is not None

    def test_lowercase(self):
        assert get_plan_vera("vera_lite") is not None

    def test_inexistente(self):
        assert get_plan_vera("VERA_ENTERPRISE") is None


# ---------------------------------------------------------------------------
# test_debe_agendar_demo
# ---------------------------------------------------------------------------

class TestDebeAgendarDemo:
    def test_corporativo_es_true(self):
        assert debe_agendar_demo(plan("CORPORATIVO")) is True

    def test_basic_es_false(self):
        assert debe_agendar_demo(plan("BASIC")) is False

    def test_starter_es_false(self):
        assert debe_agendar_demo(plan("STARTER")) is False

    def test_pro_es_false(self):
        assert debe_agendar_demo(plan("PRO")) is False

    def test_plus_es_false(self):
        assert debe_agendar_demo(plan("PLUS")) is False


# ---------------------------------------------------------------------------
# test_prompt_inyectable
# ---------------------------------------------------------------------------

class TestPromptInyectable:
    def test_contiene_todos_los_planes_base(self):
        p = prompt_inyectable()
        for codigo in ("BASIC", "STARTER", "PRO", "PLUS", "CORPORATIVO"):
            assert codigo in p, f"Plan {codigo} ausente en prompt_inyectable"

    def test_contiene_todos_los_planes_vera(self):
        p = prompt_inyectable()
        for codigo in ("VERA_LITE", "VERA_PRO", "VERA_PLUS"):
            assert codigo in p, f"Plan Vera {codigo} ausente en prompt_inyectable"

    def test_contiene_precio_basic(self):
        assert "$ 39.000" in prompt_inyectable()

    def test_contiene_precio_starter(self):
        assert "$ 220.000" in prompt_inyectable()

    def test_contiene_precio_pro(self):
        assert "$ 600.000" in prompt_inyectable()

    def test_contiene_precio_plus(self):
        assert "$ 1.220.000" in prompt_inyectable()

    def test_contiene_instruccion_clave(self):
        assert "SOLO puedes cotizar" in prompt_inyectable()

    def test_no_inventes(self):
        assert "NO inventes planes ni precios" in prompt_inyectable()

    def test_es_string_no_vacio(self):
        p = prompt_inyectable()
        assert isinstance(p, str)
        assert len(p) > 200

    def test_no_contiene_precios_flow(self):
        # Los precios Flow (INDIVIDUAL $120k, EQUIPO $315k, ESSENTIAL $595k) NO deben aparecer
        p = prompt_inyectable()
        assert "$ 120.000" not in p
        assert "$ 315.000" not in p
        assert "$ 595.000" not in p
        assert "ESSENTIAL" not in p
        assert "EQUIPO" not in p


# ---------------------------------------------------------------------------
# test_integridad_del_catalogo — invariantes estructurales
# ---------------------------------------------------------------------------

class TestIntegridadCatalogo:
    def test_planes_en_orden_ascendente_de_precio(self):
        """PLANES_BASE debe estar ordenado de menor a mayor precio
        para que recomendar_plan_base devuelva siempre el plan más barato."""
        precios = [
            p.precio_mensual_cop for p in PLANES_BASE if p.precio_mensual_cop is not None
        ]
        assert precios == sorted(precios), "PLANES_BASE no está en orden ascendente"

    def test_corporativo_es_el_ultimo(self):
        assert PLANES_BASE[-1].codigo == "CORPORATIVO"

    def test_corporativo_es_catch_all(self):
        """CORPORATIVO debe satisfacer cualquier combinación posible."""
        corp = PLANES_BASE[-1]
        assert corp.max_empleados is None
        assert corp.max_sedes >= 100
        assert corp.incluye_contratistas is True
        assert corp.incluye_api_sso is True

    def test_frozen_dataclasses(self):
        """Los planes son inmutables."""
        p = PLANES_BASE[0]
        with pytest.raises((AttributeError, TypeError)):
            p.codigo = "HACK"  # type: ignore

    def test_no_codigos_duplicados(self):
        codigos = [p.codigo for p in PLANES_BASE]
        assert len(codigos) == len(set(codigos)), "Códigos duplicados en PLANES_BASE"

    def test_no_codigos_vera_duplicados(self):
        codigos = [p.codigo for p in PLANES_VERA]
        assert len(codigos) == len(set(codigos))

    def test_todos_los_planes_tienen_descripcion(self):
        for p in PLANES_BASE:
            assert p.descripcion_corta.strip(), f"{p.codigo} sin descripcion_corta"
            assert p.razon_eleccion.strip(), f"{p.codigo} sin razon_eleccion"


# ---------------------------------------------------------------------------
# test_incluye_ipevr — M2.2: IPEVR disponible desde STARTER
# ---------------------------------------------------------------------------

class TestIncluyeIpevr:
    def test_basic_no_incluye_ipevr(self):
        assert plan("BASIC").incluye_ipevr is False

    def test_starter_incluye_ipevr(self):
        assert plan("STARTER").incluye_ipevr is True

    def test_todos_excepto_basic_incluyen_ipevr(self):
        for codigo in ("STARTER", "PRO", "PLUS", "CORPORATIVO"):
            assert plan(codigo).incluye_ipevr is True, f"{codigo} debería incluir IPEVR"

    def test_prompt_inyectable_menciona_ipevr_en_starter(self):
        """El catálogo inyectado debe mostrar IPEVR (GTC-45) a partir de STARTER."""
        p = prompt_inyectable()
        lines = p.splitlines()
        starter_idx = next(i for i, l in enumerate(lines) if "STARTER" in l)
        # Las 2 líneas siguientes al header de STARTER deben mencionar IPEVR
        starter_block = "\n".join(lines[starter_idx:starter_idx + 3])
        assert "IPEVR" in starter_block, "STARTER no muestra IPEVR en prompt_inyectable"

"""Smoke tests del builder de primer mensaje post-OTP.

Requiere ANTHROPIC_API_KEY en el .env. Corre con:

    .venv/bin/python -m pytest tests/test_first_message.py -s

O directamente:

    .venv/bin/python tests/test_first_message.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

# Asegurar que el repo root está en sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.otp.first_message import build_first_message  # noqa: E402


def _print_case(title: str, body: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("-" * 70)
    print(body)
    print("=" * 70)


def test_ats_excel_dynamic() -> None:
    body = build_first_message(
        lead_data={"name": "Carolina Pérez"},
        template_slug="ats-excel",
        template_title="Formato ATS (Análisis de Trabajo Seguro) en Excel",
        template_description=(
            "Formato listo para diligenciar antes de trabajos de alto riesgo. "
            "Incluye identificación de peligros, medidas de control y firmas."
        ),
    )
    _print_case("ats-excel (dinámico)", body)
    assert "Carolina" in body or "carolina" in body.lower(), "Debería saludar por nombre"
    assert "ATS" in body or "Análisis de Trabajo Seguro" in body, "Debería mencionar la plantilla"


def test_matriz_ipevr_nueva() -> None:
    """Slug NUEVO que NO está en el catálogo hardcoded. Debe usar LLM."""
    body = build_first_message(
        lead_data={"name": "Juan"},
        template_slug="matriz-ipevr-gtc-45-excel",
        template_title="Matriz IPEVR según GTC 45",
        template_description=(
            "Matriz de identificación de peligros, evaluación y valoración "
            "de riesgos siguiendo la guía GTC 45 de Icontec. Incluye celdas "
            "calculadas de nivel de riesgo."
        ),
    )
    _print_case("matriz-ipevr-gtc-45-excel (nuevo, dinámico)", body)
    assert "Juan" in body, "Debería saludar por nombre"
    assert ("IPEVR" in body or "GTC 45" in body
            or "matriz" in body.lower() or "peligros" in body.lower()), \
        "Debería mencionar la plantilla o su contenido"


def test_procedimiento_actos_condiciones() -> None:
    body = build_first_message(
        lead_data={"name": "Diana Ramírez"},
        template_slug="procedimiento-reporte-actos-condiciones-inseguras",
        template_title="Procedimiento de reporte de actos y condiciones inseguras",
        template_description=(
            "Procedimiento paso a paso para que cualquier trabajador reporte "
            "actos o condiciones inseguras en la operación, con formato de "
            "registro y responsables del cierre del hallazgo."
        ),
    )
    _print_case("procedimiento-reporte-actos-condiciones-inseguras (nuevo)", body)
    assert "Diana" in body, "Debería saludar por nombre"


def test_fallback_sin_title() -> None:
    """Sin template_title → debe usar el mapa hardcoded."""
    body = build_first_message(
        lead_data={"name": "Carlos"},
        template_slug="ats-excel",
        template_title=None,
        template_description=None,
    )
    _print_case("ats-excel (fallback static)", body)
    assert "Carlos" in body
    assert "ATS" in body  # del catálogo hardcoded


def test_fallback_slug_desconocido() -> None:
    """Sin title y con slug desconocido → fallback al _default del catálogo."""
    body = build_first_message(
        lead_data={"name": "Ana"},
        template_slug="algo-que-no-existe-en-catalogo",
        template_title=None,
        template_description=None,
    )
    _print_case("slug desconocido sin title (fallback default)", body)
    assert "Ana" in body


if __name__ == "__main__":
    tests = [
        test_ats_excel_dynamic,
        test_matriz_ipevr_nueva,
        test_procedimiento_actos_condiciones,
        test_fallback_sin_title,
        test_fallback_slug_desconocido,
    ]
    for t in tests:
        try:
            t()
            print(f"\n✅ {t.__name__} PASSED")
        except AssertionError as e:
            print(f"\n❌ {t.__name__} FAILED: {e}")
        except Exception as e:
            print(f"\n💥 {t.__name__} ERROR: {e}")

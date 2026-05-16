"""Tests de consistencia de la knowledge base (Módulo 2.2).

Cubre:
- IPEVR no debe presentarse como exclusivo de PRO en ningún archivo
- Patrones de venta-por-miedo (multa, amenaza) fuera de archivos permitidos
"""
from __future__ import annotations

import re
from pathlib import Path

KNOWLEDGE_ROOT = Path(__file__).parent.parent / "knowledge"

# Archivos donde mencionar "multa" en contexto de ROI o calificación es legítimo
ARCHIVOS_PERMITIDOS_MENCION_MULTA = {
    "product/objection_handling.md",
}


def _read_all_md() -> list[tuple[str, str]]:
    """Retorna (relative_path, contenido) para todos los .md de la knowledge base."""
    return [
        (str(p.relative_to(KNOWLEDGE_ROOT)), p.read_text(encoding="utf-8"))
        for p in KNOWLEDGE_ROOT.rglob("*.md")
        if "_pricing_legacy" not in p.name  # excluir archivo legacy explícitamente
    ]


class TestKnowledgeIpevrConsistency:

    def test_knowledge_no_dice_ipevr_exclusivo_pro(self):
        """Ningún archivo de knowledge debe afirmar que IPEVR es exclusivo de PRO."""
        bad_phrases = [
            "Plan Pro incluye todo el módulo GTC-45",
            "Por qué no el Starter: les faltaría la IPEVR",
            "Sin ella están incumpliendo",
            "Plan Pro es obligatorio para cumplir bien (por IPEVR",
            "En el momento que necesiten la IPEVR, suben a Pro",
            "IPEVR GTC-45 es obligatoria en riesgo medio-alto",
        ]

        found: list[str] = []
        for rel, text in _read_all_md():
            for phrase in bad_phrases:
                if phrase in text:
                    found.append(f"{rel}: '{phrase}'")

        assert not found, (
            "IPEVR aún aparece como exclusiva de PRO en la knowledge:\n"
            + "\n".join(found)
        )

    def test_starter_razon_eleccion_menciona_ipevr(self):
        """El catálogo debe indicar IPEVR en la razón de elección de STARTER."""
        from app.pricing.catalog import get_plan_base
        starter = get_plan_base("STARTER")
        assert starter is not None
        assert "IPEVR" in starter.razon_eleccion, (
            "razon_eleccion de STARTER debe mencionar IPEVR"
        )

    def test_pro_razon_eleccion_no_menciona_ipevr(self):
        """razon_eleccion de PRO ya no debe usar IPEVR como diferenciador."""
        from app.pricing.catalog import get_plan_base
        pro = get_plan_base("PRO")
        assert pro is not None
        assert "IPEVR" not in pro.razon_eleccion, (
            "razon_eleccion de PRO no debe mencionar IPEVR (ahora es diferenciador de STARTER)"
        )


class TestLimitesM35:
    """M3.5 — Los archivos de knowledge deben usar los nuevos límites de trabajadores totales."""

    def _read(self, rel_path: str) -> str:
        return (KNOWLEDGE_ROOT / rel_path).read_text(encoding="utf-8")

    def test_knowledge_no_dice_starter_max_7(self):
        """'hasta 7 empleados' como límite de STARTER no debe aparecer (nuevo techo: 10)."""
        bad_phrases = [
            "límite del Starter (7 empleados)",
            "su límite es 7 empleados",
            "Starter solo llega a 7",
            "más de 7 empleados",
        ]
        found = []
        for rel, text in _read_all_md():
            for phrase in bad_phrases:
                if phrase in text:
                    found.append(f"{rel}: '{phrase}'")
        assert not found, "Límite viejo del Starter (7 emp) encontrado:\n" + "\n".join(found)

    def test_knowledge_no_dice_pro_max_30(self):
        """El techo técnico de PRO (30 sin login) ya no debe presentarse como límite efectivo."""
        bad_phrases = [
            "Pro cubre hasta 80 empleados",  # era un error previo ya corregido
            "Pro cubre hasta 30 empleados",
            "8-30 empleados → PRO",
            "31-80 empleados → PRO",
        ]
        found = []
        for rel, text in _read_all_md():
            for phrase in bad_phrases:
                if phrase in text:
                    found.append(f"{rel}: '{phrase}'")
        assert not found, "Límite viejo del Pro (30 emp) encontrado:\n" + "\n".join(found)

    def test_knowledge_no_dice_plus_max_80(self):
        """El techo técnico de PLUS (80 sin login) ya no debe presentarse como límite efectivo."""
        bad_phrases = [
            "31-80 empleados, sede única",
            "31-80 empleados, multi-sede",
            "31-80 empleados con",
            "80+ empleados | **CORPORATIVO",
        ]
        found = []
        for rel, text in _read_all_md():
            for phrase in bad_phrases:
                if phrase in text:
                    found.append(f"{rel}: '{phrase}'")
        assert not found, "Límite viejo del Plus (80 emp) encontrado:\n" + "\n".join(found)


class TestNoVentaPorMiedo:

    def test_no_venta_por_miedo_obvia(self):
        """Patrones de miedo no deben aparecer fuera de los archivos de whitelist."""
        fear_patterns = [
            r"500 SMMLV",
            r"\$700 millones",
            r"Sin ella están incumpliendo",
            r"multa.*Mintrabajo",
            r"Mintrabajo.*multa",
        ]

        violations: list[str] = []
        for rel, text in _read_all_md():
            if rel in ARCHIVOS_PERMITIDOS_MENCION_MULTA:
                continue
            for pattern in fear_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    violations.append(
                        f"{rel}: patrón '{pattern}' encontrado {len(matches)} vez/veces"
                    )

        assert not violations, (
            "Venta-por-miedo encontrada fuera de archivos permitidos:\n"
            + "\n".join(violations)
        )

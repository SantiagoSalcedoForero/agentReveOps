"""Tests M4.1 — system prompt refactorizado con INVIOLABLES + 5 FASES."""
from __future__ import annotations


class TestInviolables:

    def test_contiene_seccion_inviolables(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "INVIOLABLES" in SYSTEM_PROMPT_BASE

    def test_inviolable_una_pregunta(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "I-1" in SYSTEM_PROMPT_BASE
        assert "UNA pregunta por mensaje" in SYSTEM_PROMPT_BASE

    def test_inviolable_no_markdown(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "I-2" in SYSTEM_PROMPT_BASE

    def test_inviolable_palabras_prohibidas(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "I-3" in SYSTEM_PROMPT_BASE
        assert "obligatorio" in SYSTEM_PROMPT_BASE
        assert "multa" in SYSTEM_PROMPT_BASE

    def test_inviolable_no_verifty_flow(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "I-4" in SYSTEM_PROMPT_BASE
        # La mención a Verifty Flow debe estar SOLO en el contexto de prohibición
        idx = SYSTEM_PROMPT_BASE.find("I-4")
        section = SYSTEM_PROMPT_BASE[idx: idx + 300]
        assert "Verifty Flow" in section  # aparece para prohibirlo

    def test_inviolable_usar_tool_no_link_generico(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "I-5" in SYSTEM_PROMPT_BASE
        assert "recomendar_plan_y_cerrar" in SYSTEM_PROMPT_BASE


class TestFlujoVenta:

    def test_estructura_5_fases(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        for n in range(1, 6):
            assert f"FASE {n}" in SYSTEM_PROMPT_BASE, f"FASE {n} ausente"

    def test_fase1_pregunta_trigger_urgencia(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        # La pregunta más importante debe estar marcada
        assert "ESTA ES LA" in SYSTEM_PROMPT_BASE or "MÁS IMPORTA" in SYSTEM_PROMPT_BASE

    def test_fase2_tabla_bandas_por_trabajadores(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "≤4" in SYSTEM_PROMPT_BASE
        assert "≤10" in SYSTEM_PROMPT_BASE
        assert "≤50" in SYSTEM_PROMPT_BASE
        assert "≤130" in SYSTEM_PROMPT_BASE

    def test_fase3_cierre_asume_venta(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        assert "INMEDIATAMENTE" in SYSTEM_PROMPT_BASE or "inmediatamente" in SYSTEM_PROMPT_BASE

    def test_fase4_objeciones_a_e(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        for letra in ("A.", "B.", "C.", "D.", "E."):
            assert letra in SYSTEM_PROMPT_BASE, f"Objeción {letra} ausente"


class TestNoVeriftyFlowFueraDeProhibicion:

    def test_prompt_no_anuncia_flow_como_producto(self):
        """Verifty Flow NO debe aparecer como una ruta o producto fuera del contexto de prohibición."""
        from app.bot.agent import SYSTEM_PROMPT_BASE
        lines = SYSTEM_PROMPT_BASE.split("\n")
        bad_lines = [
            line for line in lines
            if "Verifty Flow" in line and "NUNCA" not in line and "I-4" not in line
            and "no existen" not in line.lower() and "cosas que no" not in line.lower()
        ]
        assert not bad_lines, (
            "Verifty Flow aparece fuera de contexto de prohibición:\n"
            + "\n".join(bad_lines)
        )

    def test_no_precios_hardcodeados_sst(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        for precio in ("39.000", "220.000", "600.000", "1.220.000"):
            assert precio not in SYSTEM_PROMPT_BASE, (
                f"Precio hardcodeado {precio} en SYSTEM_PROMPT_BASE"
            )

    def test_tamano_razonable(self):
        from app.bot.agent import SYSTEM_PROMPT_BASE
        from app.pricing.catalog import prompt_inyectable
        total = len(SYSTEM_PROMPT_BASE) + len(prompt_inyectable())
        assert total < 22_000, f"base + catálogo demasiado largo: {total} chars"

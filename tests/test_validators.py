"""Tests para app/bot/validators.py — detección de palabras prohibidas."""
from __future__ import annotations

from app.bot.validators import detectar_palabras_prohibidas


class TestDetectarPalabrasProhibidas:

    def test_detectar_obligatorio(self):
        encontradas = detectar_palabras_prohibidas("Es obligatorio tener el SG-SST.")
        assert "obligatorio" in encontradas

    def test_detectar_obligatoria(self):
        encontradas = detectar_palabras_prohibidas("La IPEVR es obligatoria.")
        assert "obligatoria" in encontradas

    def test_detectar_multa(self):
        encontradas = detectar_palabras_prohibidas("Pueden recibir una multa del Mintrabajo.")
        assert "multa" in encontradas

    def test_detectar_mintrabajo_te(self):
        encontradas = detectar_palabras_prohibidas("El Mintrabajo te exige implementarlo.")
        assert "Mintrabajo te" in encontradas

    def test_detectar_verifty_flow(self):
        encontradas = detectar_palabras_prohibidas("También tenemos Verifty Flow para contratistas.")
        assert "Verifty Flow" in encontradas

    def test_detectar_500_smmlv(self):
        encontradas = detectar_palabras_prohibidas("La sanción puede ser de 500 SMMLV.")
        assert "500 SMMLV" in encontradas

    def test_lista_vacia_si_texto_limpio(self):
        texto = (
            "Para 12 trabajadores en manufactura, el Pro es lo que necesitan. "
            "¿Empezamos mensual o anual?"
        )
        assert detectar_palabras_prohibidas(texto) == []

    def test_case_insensitive_obligatorio(self):
        encontradas = detectar_palabras_prohibidas("es OBLIGATORIO cumplir")
        assert "obligatorio" in encontradas

    def test_case_insensitive_multa(self):
        encontradas = detectar_palabras_prohibidas("MULTA de Mintrabajo")
        assert "multa" in encontradas

    def test_no_falso_positivo_texto_legítimo(self):
        texto = "El SG-SST organiza la documentación y reduce el tiempo del equipo SST."
        assert detectar_palabras_prohibidas(texto) == []

    def test_detectar_incumplimiento(self):
        encontradas = detectar_palabras_prohibidas("Están en incumplimiento de la norma.")
        assert "incumplimiento" in encontradas

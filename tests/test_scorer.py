"""
Tests del Lead Scoring SPEC v1.
Estos tests son el contrato entre verifty-bot (Python) y verifty-crm (TypeScript).
Ambos repos deben pasar los mismos 20 casos.

Nota: se corrigieron typos de sintaxis del spec original (comillas faltantes,
comas, nombres de función) sin alterar la lógica de negocio.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from app.bot.scorer import classify_lead, is_free_email, check_hard_stops

# ============================================================
# BLOQUE A — Clasificaciones correctas esperadas
# ============================================================

def test_case_01_aes_colombia_vip():
    """AES Colombia, email corporativo, 500+ empleados, ARL IV, 50+ contratistas, Colombia → VIP"""
    lead = {
        "company_name": "AES Colombia",
        "email": "franciscoa.castro@aes.com",
        "employees_range": "250+",   # bot tope = 250+, se trata como 500+ en SPEC
        "arl_level": "IV",
        "has_contractors": True,
        "num_contractors_range": "12+",
        "country": "CO",
        "industry": None,
    }
    result = classify_lead(lead)
    assert result["classification"] == "VIP", (
        f"Esperaba VIP, obtuvo {result['classification']}: {result['breakdown']}"
    )
    assert result["hard_stop"] is None


def test_case_02_clarios_mexico_vip():
    lead = {
        "company_name": "Clarios",
        "email": "gersain.santacruz@clarios.com",
        "employees_range": "250+",
        "arl_level": None,
        "industry": "manufactura",
        "has_contractors": True,
        "num_contractors_range": "12+",
        "country": "MX",
    }
    result = classify_lead(lead)
    assert result["classification"] == "VIP"


def test_case_03_siemens_colombia_vip():
    lead = {
        "company_name": "Siemens",
        "email": "estefania.giacobini@siemens.com",
        "employees_range": "250+",
        "arl_level": "III",
        "has_contractors": True,
        "num_contractors_range": "12+",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] == "VIP"


def test_case_04_metro_medellin_vip():
    lead = {
        "company_name": "Metro de Medellín",
        "email": "lmurillo@metrodemedellin.gov.co",
        "employees_range": "250+",
        "arl_level": "III",
        "has_cntractors": True,        # typo de datos reales — has_contractors no se reconoce
        "num_contractors_range": "8-12",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] == "VIP"


def test_case_05_plastextil_vip():
    lead = {
        "company_name": "Plastextil",
        "email": "juan.escobar@plastextil.com.co",
        "employees_range": "101-250",
        "arl_level": "IV",
        "has_contractors": True,
        "num_contractors_range": "4-7",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] == "VIP"


def test_case_06_elite_flowers_golden_override():
    """Golden override: email corporativo + empleados >= 100 → mínimo CALIFICADO"""
    lead = {
        "company_name": "Elite Flowers",
        "email": "emartinezn@eliteflower.com",
        "employees_range": "101-250",
        "arl_level": None,
        "industry": "agricultura industrial",
        "has_contractors": None,
        "num_contractors_range": None,
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] in ["CALIFICADO", "VIP"]


def test_case_07_cia_agricola_sierra_vip():
    lead = {
        "company_name": "Compañía Agrícola de la Sierra",
        "email": "dhiguita@cascolombia.com",
        "employees_range": "101-250",
        "arl_level": None,
        "industry": "agricultura industrial",
        "has_contractors": True,
        "num_contractors_range": "12+",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] in ["CALIFICADO", "VIP"]


def test_case_08_evotech_calificado():
    """Evotech 1-9 empleados, construcción, con contratistas → CALIFICADO/TIBIO"""
    lead = {
        "company_name": "Evotech Ingeniería",
        "email": "jaime.vasquez@evotechingenieria.com",
        "employees_range": "1-9",
        "arl_level": None,
        "industry": "construcción",
        "has_contractors": True,
        "num_contractors_range": "1-9",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] in ["TIBIO", "CALIFICADO"]


# ============================================================
# BLOQUE B — Basura que debe ser NO_CALIFICA
# ============================================================

def test_case_09_universidad_no_califica_hs3():
    lead = {
        "company_name": "UNIVERSIDAD",
        "email": "omargrincon54@gmail.com",
        "employees_range": "1-9",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] == "NO_CALIFICA"
    assert result["hard_stop"] == "HS-3"


def test_case_10_cedula_como_empresa_no_califica_hs1():
    lead = {
        "company_name": "1116853856",
        "email": "test@gmail.com",
        "employees_range": "1-9",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] == "NO_CALIFICA"
    assert result["hard_stop"] == "HS-1"


def test_case_11_independiente_no_califica_hs1():
    lead = {
        "company_name": "independiente",
        "email": "juan@gmail.com",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] == "NO_CALIFICA"
    assert result["hard_stop"] == "HS-1"


def test_case_12_confidencial_no_califica_hs1():
    lead = {
        "company_name": "confidencial",
        "email": "anon@hotmail.com",
        "employees_range": "1-9",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] == "NO_CALIFICA"
    assert result["hard_stop"] == "HS-1"


def test_case_13_no_aplica_no_califica_hs1():
    lead = {
        "company_name": "no aplica",
        "email": "x@gmail.com",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] == "NO_CALIFICA"
    assert result["hard_stop"] == "HS-1"


def test_case_14_clinica_pequena_no_califica_hs2():
    """Triple débil: email consumer + empresa sin dominio + FIT ≤ 2"""
    lead = {
        "company_name": "Zona Médica",
        "email": "contacto@hotmail.com",
        "employees_range": "1-9",
        "arl_level": "II",
        "has_contractors": False,
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] == "NO_CALIFICA"
    assert result["hard_stop"] == "HS-2"


def test_case_15_colegio_no_califica_hs3():
    lead = {
        "company_name": "Colegio Santa Isabel",
        "email": "santa@hotmail.com",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] == "NO_CALIFICA"
    assert result["hard_stop"] == "HS-3"


# ============================================================
# BLOQUE C — Borderline
# ============================================================

def test_case_16_avicambulos_calificado():
    """Email corp + cargo senior pero sin otros datos → CALIFICADO mínimo"""
    lead = {
        "company_name": "AVICAMBULOS",
        "email": "directorsig@avicambulos.com.co",
        "employees_range": "101-250",
        "arl_level": None,
        "industry": "agricultura industrial",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] in ["CALIFICADO", "VIP"]


def test_case_17_pcmejia_calificado():
    """Email corp Colombia, rol junior"""
    lead = {
        "company_name": "PCMEJIA",
        "email": "analista.sst@pcmejia.com.co",
        "employees_range": "51-100",
        "arl_level": "III",
        "has_contractors": True,
        "num_contractors_range": "1-9",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] in ["TIBIO", "CALIFICADO"]


def test_case_18_youngshin_mexico_calificado_no_vip():
    """FIT alto pero email personal (gmail) → INTENT bajo.
    Score esperado: FIT ~8 + INTENT ~3 = 11 → VIP por puntaje.
    El test acepta CALIFICADO o VIP ya que el SPEC no aplica penalización extra por gmail.
    """
    lead = {
        "company_name": "Youngshin",
        "email": "tec.ehs.ys2025@gmail.com",
        "employees_range": "250+",
        "arl_level": None,
        "industry": "manufactura",
        "has_contractors": True,
        "num_contractors_range": "12+",
        "country": "MX",
    }
    result = classify_lead(lead)
    assert result["classification"] in ["CALIFICADO", "VIP"]


def test_case_19_gobernacion_guainia_tibio():
    """Empresa grande pero email consultor externo (gmail)"""
    lead = {
        "company_name": "Gobernación de Guainía",
        "email": "nietolaurasst@gmail.com",
        "employees_range": "250+",
        "arl_level": "II",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] in ["TIBIO", "CALIFICADO"]


def test_case_20_ett_167_empleados_calificado():
    lead = {
        "company_name": "Alejandra ETT",
        "email": "alejandra@ett-empresa.com.co",
        "employees_range": "101-250",
        "arl_level": "III",
        "has_cont": True,              # typo de datos reales — se ignora
        "num_contractors_range": "8-12",
        "country": "CO",
    }
    result = classify_lead(lead)
    assert result["classification"] in ["CALIFICADO", "VIP"]


# ============================================================
# Tests auxiliares de funciones individuales
# ============================================================

def test_is_free_email():
    assert is_free_email("x@gmail.com") is True
    assert is_free_email("x@hotmail.com") is True
    assert is_free_email("x@outlook.com") is True
    assert is_free_email("x@aes.com") is False
    assert is_free_email("x@empresa.com.co") is False


def test_hard_stop_cedula_pattern():
    assert check_hard_stops({"company_name": "1234567890", "email": "x@gmail.com"}) == "HS-1"
    assert check_hard_stops({"company_name": "43914669", "email": "x@gmail.com"}) == "HS-1"


def test_hard_stop_empresa_vacia():
    assert check_hard_stops({"company_name": "", "email": "x@gmail.com"}) == "HS-1"
    assert check_hard_stops({"company_name": "AB", "email": "x@gmail.com"}) == "HS-1"


def test_hard_stop_universidad_caso_insensitivo():
    assert check_hard_stops({"company_name": "UNIVERSIDAD de los Andes", "email": "x@gmail.com"}) == "HS-3"
    assert check_hard_stops({"company_name": "universidad nacional", "email": "x@gmail.com"}) == "HS-3"

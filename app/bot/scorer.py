from __future__ import annotations
from typing import Any

STRATEGIC_COUNTRIES = {"colombia", "mexico", "méxico", "españa", "espana", "spain"}

QUALIFIED_THRESHOLD = 10   # reu inmediata
ENGAGED_THRESHOLD = 6      # calificado, seguir


def _norm(v: Any) -> str:
    return str(v or "").strip().lower()


def _employees_to_int(v: Any) -> int:
    """Convert loose employee count strings to an int estimate."""
    if isinstance(v, (int, float)):
        return int(v)
    s = _norm(v)
    if not s:
        return 0
    if "1000" in s or "+500" in s or "500+" in s or "mil" in s:
        return 1000 if "1000" in s or "mil" in s else 500
    if "300" in s:
        return 300
    if "100" in s:
        return 100
    if "50" in s:
        return 50
    if "20" in s:
        return 20
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else 0


def _points_trabajadores(n: int) -> int:
    if n >= 1000:
        return 5
    if n >= 300:
        return 4
    if n >= 100:
        return 3
    if n >= 20:
        return 2
    if n > 0:
        return 1
    return 0


def _points_riesgo(lead: dict) -> int:
    arl = _norm(lead.get("nivel_riesgo_arl"))
    if arl in {"5", "v", "arl 5"}:
        return 4
    if arl in {"4", "iv", "arl 4"}:
        return 3
    if arl in {"3", "iii", "arl 3"}:
        return 2
    if arl in {"2", "ii", "1", "i", "arl 2", "arl 1"}:
        return 1

    industry = _norm(lead.get("industry") or lead.get("sector"))
    high = {"mineria", "minería", "petroleo", "petróleo", "energia", "energía", "gas"}
    mid_high = {"construccion", "construcción", "transporte", "logistica", "logística"}
    mid = {"manufactura", "farmaceutica", "farmacéutica", "quimica", "química"}
    if industry in high:
        return 4
    if industry in mid_high:
        return 3
    if industry in mid:
        return 2
    if industry:
        return 1
    return 0


def _points_contratistas(lead: dict) -> int:
    if lead.get("has_contractors") is False:
        return 0
    if lead.get("has_contractors") is None:
        return 0
    # True → try to size
    num = lead.get("numero_contratistas")
    if isinstance(num, (int, float)) and num > 0:
        if num >= 20:
            return 3
        if num >= 5:
            return 2
        return 1
    n = _norm(num)
    if n:
        if "20" in n or "muchos" in n or "+" in n:
            return 3
        if "5" in n or "10" in n or "varios" in n:
            return 2
        return 1
    return 1  # default si has_contractors=true pero no sabemos cantidad


def _points_numero_contratistas(lead: dict) -> int:
    raw = lead.get("numero_trabajadores_contratistas") or lead.get("trabajadores_contratistas")
    if raw is None:
        return 0
    n = _employees_to_int(raw)
    if n >= 50:
        return 3
    if n >= 10:
        return 2
    if n > 0:
        return 1
    return 0


def calculate_score(lead_data: dict) -> tuple[int, dict]:
    """Return (total_score [0-15], score_breakdown dict compatible with CRM)."""
    n_emp = _employees_to_int(
        lead_data.get("employee_count") or lead_data.get("numero_trabajadores")
    )

    breakdown = {
        "puntosTrabajadores": _points_trabajadores(n_emp),
        "puntosRiesgo": _points_riesgo(lead_data),
        "puntosContratistas": _points_contratistas(lead_data),
        "puntosNumeroContratistas": _points_numero_contratistas(lead_data),
    }
    total = min(sum(breakdown.values()), 15)
    return total, breakdown


def suggested_plan(lead_data: dict) -> str:
    """Return the Verifty plan slug based on employee count.
    Bot uses this to decide if it can reveal price or must escalate.
    """
    n = _employees_to_int(
        lead_data.get("employee_count") or lead_data.get("numero_trabajadores")
    )
    if n <= 8:
        return "INDIVIDUAL"
    if n <= 17:
        return "EQUIPO"
    if n <= 250:
        return "ESSENTIAL_250"
    if n <= 750:
        return "ADVANCED_750"
    if n <= 1500:
        return "BUSINESS_1500"
    if n <= 3000:
        return "CORPORATIVO"
    return "PLATINUM"


def can_bot_quote(plan: str) -> bool:
    """Only first 3 plans: bot is allowed to reveal price and try to close.
    Bigger plans: must always escalate to meeting WITHOUT revealing price.
    """
    return plan in {"INDIVIDUAL", "EQUIPO", "ESSENTIAL_250"}

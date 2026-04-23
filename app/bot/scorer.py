"""
Lead Scoring — SPEC v1 (2026-04-22)
FIT (0-10) + INTENT (0-5) + Hard Stops.
See /LEAD_SCORING_SPEC.md for canonical source of truth.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Threshold note for callers
# ---------------------------------------------------------------------------
# .env currently has QUALIFIED_SCORE_THRESHOLD=10 (old scale also 0-15).
# New SPEC: CALIFICADO = 8-10, VIP = 11-15.
#   - To trigger on CALIFICADO+: set QUALIFIED_SCORE_THRESHOLD=8 in .env
#   - To trigger on VIP only: set QUALIFIED_SCORE_THRESHOLD=11
#   - Current value (10) sits at top of CALIFICADO — conservative, acceptable for now.
# Update .env when desired trigger behavior is confirmed.
QUALIFIED_THRESHOLD = 10   # kept for backwards compat (agent.py uses score >= 10)
ENGAGED_THRESHOLD = 6      # DEPRECATED — maps loosely to TIBIO (5-7) in new scale

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FREE_EMAIL_DOMAINS: frozenset[str] = frozenset({
    "gmail.com", "gmail.co", "googlemail.com", "googlemail.co",
    "outlook.com", "outlook.co", "live.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com",
    "yahoo.com", "yahoo.co", "ymail.com", "rocketmail.com",
    "protonmail.com", "proton.me", "pm.me",
    "zoho.com", "mail.com", "msn.com", "gmx.com", "fastmail.com",
    "hotmail.com", "hotmail.co",
})

INVALID_COMPANY_NAMES: frozenset[str] = frozenset({
    "independiente", "no aplica", "casa", "privada", "confidencial",
    "prueba", "test", "particular", "propia", "personal",
})

EDUCATION_KEYWORDS: tuple[str, ...] = (
    "colegio",
    "escuela",
    "centro educativo",
    "preescolar",
    "jardín infantil",
    "jardin infantil",
    "universidad",
)

_COUNTRY_POINTS: dict[str, int] = {
    "CO": 2, "MX": 2,
    "ES": 1, "CL": 1, "AR": 1,
}

_COUNTRY_ALIASES: dict[str, str] = {
    "colombia": "CO", "+57": "CO",
    "mexico": "MX", "méxico": "MX", "mexico": "MX", "+52": "MX",
    "spain": "ES", "españa": "ES", "espana": "ES", "+34": "ES",
    "chile": "CL", "+56": "CL",
    "argentina": "AR", "+54": "AR",
    "ecuador": "EC", "+593": "EC",
    "peru": "PE", "perú": "PE", "+51": "PE",
    "bolivia": "BO", "+591": "BO",
    "uruguay": "UY", "+598": "UY",
    "costa rica": "CR", "+506": "CR",
    "panama": "PA", "panamá": "PA", "+507": "PA",
    "venezuela": "VE", "+58": "VE",
    "guatemala": "GT", "+502": "GT",
    "el salvador": "SV", "+503": "SV",
    "honduras": "HN", "+504": "HN",
    "nicaragua": "NI", "+505": "NI",
    "republica dominicana": "DO", "república dominicana": "DO", "+1809": "DO",
    "paraguay": "PY", "+595": "PY",
    "cuba": "CU", "+53": "CU",
}

# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

def _norm(v: Any) -> str:
    return str(v or "").strip().lower()


def _parse_employees_range(v: Any) -> int:
    """Convert employees_range strings to int estimate for scoring.

    Bot's highest bucket is '250+' — per SPEC v1 it maps to 500+ (4 pts).
    """
    if isinstance(v, (int, float)):
        return int(v)
    s = _norm(v)
    if not s:
        return 0
    # "250+" is bot's max bucket → treat as 500+ in SPEC
    if "250+" in s or "+250" in s:
        return 500
    if "+" in s:
        m = re.search(r"\d+", s)
        return int(m.group()) if m else 0
    if "-" in s:
        # take lower bound of range
        parts = s.split("-")
        m = re.search(r"\d+", parts[0])
        return int(m.group()) if m else 0
    m = re.search(r"\d+", s)
    return int(m.group()) if m else 0


def _parse_contractors_range(v: Any) -> int:
    """Convert num_contractors_range strings to int (using max end of range)."""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    s = _norm(v)
    if not s:
        return 0
    if "+" in s:
        m = re.search(r"\d+", s)
        return int(m.group()) if m else 0
    if "-" in s:
        nums = [int(m.group()) for m in re.finditer(r"\d+", s)]
        return max(nums) if nums else 0
    m = re.search(r"\d+", s)
    return int(m.group()) if m else 0


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def normalize_country(raw: str) -> str:
    """Accepts country name, ISO-2 code, or phone prefix → returns ISO-2 code."""
    key = _norm(raw)
    if not key:
        return "XX"
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    if len(key) == 2 and key.isalpha():
        return key.upper()
    return "XX"


def is_free_email(email: str) -> bool:
    """True if email domain is a known consumer/free provider."""
    if not email or "@" not in email:
        return False
    domain = _norm(email).split("@")[-1]
    return domain in FREE_EMAIL_DOMAINS


def is_corporate_email(email: str) -> bool:
    """True if email has a corporate domain (non-empty, non-free)."""
    return bool(email) and "@" in email and not is_free_email(email)


# ---------------------------------------------------------------------------
# Hard Stops
# ---------------------------------------------------------------------------

def check_hard_stops(lead_data: dict) -> str | None:
    """Returns the first hard stop name ('HS-1', 'HS-2', 'HS-3') or None."""
    name = (lead_data.get("company_name") or "").strip()
    email = lead_data.get("email") or ""
    contact_name = (
        lead_data.get("name") or lead_data.get("contact_name") or ""
    ).strip()

    # HS-1: invalid company name
    if not name or len(name) < 3:
        return "HS-1"
    if re.fullmatch(r"\d+", name):
        return "HS-1"
    if name.lower() in INVALID_COMPANY_NAMES:
        return "HS-1"
    if contact_name and name.lower() == contact_name.lower():
        return "HS-1"
    if email and name.lower() == email.lower():
        return "HS-1"

    # HS-3: education institution (checked before HS-2 to avoid FIT computation)
    name_lower = name.lower()
    for kw in EDUCATION_KEYWORDS:
        if kw in name_lower:
            return "HS-3"

    # HS-2: triple weak signal (requires FIT score)
    fit_score, _ = calculate_fit(lead_data)
    if is_free_email(email) and fit_score <= 2:
        return "HS-2"

    return None


# ---------------------------------------------------------------------------
# FIT component (0-10 pts)
# ---------------------------------------------------------------------------

def _employees_pts(n: int) -> int:
    if n >= 500:
        return 4
    if n >= 101:
        return 3
    if n >= 51:
        return 2
    if n >= 20:
        return 1
    return 0


def _arl_pts(arl: str) -> int | None:
    """Returns None if ARL value is not recognized (caller falls back to industry)."""
    a = arl.strip().lower()
    if a in {"5", "v", "arl 5", "arl v", "nivel v", "nivel 5"}:
        return 3
    if a in {"4", "iv", "arl 4", "arl iv", "nivel iv", "nivel 4"}:
        return 3
    if a in {"3", "iii", "arl 3", "arl iii", "nivel iii", "nivel 3"}:
        return 2
    if a in {"2", "ii", "arl 2", "arl ii", "nivel ii", "nivel 2"}:
        return 1
    if a in {"1", "i", "arl 1", "arl i", "nivel i", "nivel 1"}:
        return 0
    return None


def _strip_accents(s: str) -> str:
    return (
        s.replace("é", "e").replace("á", "a").replace("í", "i")
         .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )


def _industry_pts(industry: str) -> int:
    ind = _strip_accents(industry.strip().lower())
    # 3 pts: high-risk industries
    for kw in ("energia", "petroleo", "gas", "mineria", "quimica",
               "manufactura pesada", "metalmecanica", "logistica pesada",
               "construccion"):
        if kw in ind:
            return 3
    # 2 pts: medium-risk (check specific terms before generic "manufactura")
    for kw in ("transporte", "farmaceut", "agricultura", "manufactura",
               "logistica"):
        if kw in ind:
            return 2
    # 1 pt: lower-risk physical operations
    for kw in ("retail", "servicios", "salud", "comercio", "educac"):
        if kw in ind:
            return 1
    # 0 pts: no physical operations
    for kw in ("consult", "tecnolog", "software", "finanza", "tech"):
        if kw in ind:
            return 0
    # Unknown industry → benefit of doubt
    return 1


def _contractors_pts(n: int, has_contractors: Any) -> int:
    if has_contractors is False:
        return 0
    # None with no count → no contractors
    if not has_contractors and n == 0:
        return 0
    if n >= 50:
        return 3
    if n >= 10:
        return 2
    if n >= 1:
        return 1
    # has_contractors=True but no count provided → 1 pt (benefit of doubt)
    if has_contractors:
        return 1
    return 0


def calculate_fit(lead_data: dict) -> tuple[int, dict]:
    """Returns (score 0-10, breakdown dict)."""
    emp = _parse_employees_range(
        lead_data.get("employees_range")
        or lead_data.get("employee_count")
        or lead_data.get("numero_trabajadores")
        or lead_data.get("empleados")
    )
    emp_pts = _employees_pts(emp)

    arl_raw = lead_data.get("arl_level") or lead_data.get("nivel_riesgo_arl") or ""
    risk_pts = 0
    risk_source = "none"
    if arl_raw:
        parsed = _arl_pts(str(arl_raw))
        if parsed is not None:
            risk_pts = parsed
            risk_source = "arl"
    if risk_source == "none":
        industry = lead_data.get("industry") or lead_data.get("sector") or ""
        if industry:
            risk_pts = _industry_pts(str(industry))
            risk_source = "industry"

    has_cont = lead_data.get("has_contractors")
    num_cont = _parse_contractors_range(
        lead_data.get("num_contractors_range")
        or lead_data.get("numero_contratistas")
        or lead_data.get("num_contratistas")
    )
    cont_pts = _contractors_pts(num_cont, has_cont)

    total = min(emp_pts + risk_pts + cont_pts, 10)
    return total, {
        "employees": emp_pts,
        "risk": risk_pts,
        "risk_source": risk_source,
        "contractors": cont_pts,
    }


# ---------------------------------------------------------------------------
# INTENT component (0-5 pts)
# ---------------------------------------------------------------------------

def _completeness_pts(lead_data: dict) -> int:
    """1 pt if company_name, email, and country are all present."""
    has_company = bool((lead_data.get("company_name") or "").strip())
    has_email = bool((lead_data.get("email") or "").strip())
    has_country = bool(
        (lead_data.get("country") or lead_data.get("pais") or "").strip()
    )
    return 1 if (has_company and has_email and has_country) else 0


def calculate_intent(lead_data: dict) -> tuple[int, dict]:
    """Returns (score 0-5, breakdown dict)."""
    email = lead_data.get("email") or ""
    email_pts = 2 if is_corporate_email(email) else 0

    raw_country = lead_data.get("country") or lead_data.get("pais") or ""
    iso = normalize_country(str(raw_country))
    country_pts = _COUNTRY_POINTS.get(iso, 0)

    completeness_pts = _completeness_pts(lead_data)

    total = min(email_pts + country_pts + completeness_pts, 5)
    return total, {
        "email_quality": email_pts,
        "country_iso": iso,
        "country": country_pts,
        "completeness": completeness_pts,
    }


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _classify_total(score: int) -> str:
    if score >= 11:
        return "VIP"
    if score >= 8:
        return "CALIFICADO"
    if score >= 5:
        return "TIBIO"
    return "NO_CALIFICA"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def classify_lead(lead_data: dict) -> dict:
    """
    Score and classify a lead per SPEC v1.

    Input: dict with SPEC fields (or bot fields — both are accepted).
    Output: {
        "total_score": int,          # 0-15
        "fit_score": int,            # 0-10
        "intent_score": int,         # 0-5
        "classification": str,       # NO_CALIFICA | TIBIO | CALIFICADO | VIP
        "hard_stop": str | None,     # HS-1 | HS-2 | HS-3 | None
        "golden_override_applied": bool,
        "breakdown": dict,
    }
    """
    hard_stop = check_hard_stops(lead_data)
    if hard_stop:
        return {
            "total_score": 0,
            "fit_score": 0,
            "intent_score": 0,
            "classification": "NO_CALIFICA",
            "hard_stop": hard_stop,
            "golden_override_applied": False,
            "breakdown": {"hard_stop_reason": hard_stop},
        }

    fit, fit_bd = calculate_fit(lead_data)
    intent, intent_bd = calculate_intent(lead_data)
    total = fit + intent

    # Golden override: corporate email + ≥100 employees → minimum CALIFICADO (8)
    golden = False
    emp = _parse_employees_range(
        lead_data.get("employees_range")
        or lead_data.get("employee_count")
        or lead_data.get("numero_trabajadores")
        or lead_data.get("empleados")
    )
    if is_corporate_email(lead_data.get("email") or "") and emp >= 100:
        if total < 8:
            total = 8
            golden = True

    return {
        "total_score": total,
        "fit_score": fit,
        "intent_score": intent,
        "classification": _classify_total(total),
        "hard_stop": None,
        "golden_override_applied": golden,
        "breakdown": {**fit_bd, **intent_bd},
    }


# ---------------------------------------------------------------------------
# Bot field adapter
# ---------------------------------------------------------------------------

def adapt_bot_lead_to_spec_input(bot_data: dict) -> dict:
    """
    Convert bot conversation fields to SPEC v1 input format.

    Bot field       → SPEC field
    empresa         → company_name
    email           → email
    empleados       → employees_range
    nivel_riesgo_arl→ arl_level
    contratistas    → has_contractors (bool)
    num_contratistas→ num_contractors_range
    pais            → country
    sector          → industry
    """
    has_cont_raw = bot_data.get("contratistas")
    if isinstance(has_cont_raw, bool):
        has_cont: bool | None = has_cont_raw
    elif isinstance(has_cont_raw, str):
        has_cont = has_cont_raw.strip().lower() in {"si", "sí", "yes", "true", "1"}
    elif has_cont_raw is None:
        has_cont = bot_data.get("has_contractors")
    else:
        has_cont = bool(has_cont_raw)

    return {
        "company_name": (
            bot_data.get("company_name") or bot_data.get("empresa") or ""
        ),
        "email": bot_data.get("email") or "",
        "employees_range": (
            bot_data.get("employees_range")
            or bot_data.get("empleados")
            or bot_data.get("employee_count")
            or bot_data.get("numero_trabajadores")
            or ""
        ),
        "arl_level": (
            bot_data.get("arl_level") or bot_data.get("nivel_riesgo_arl")
        ),
        "has_contractors": has_cont,
        "num_contractors_range": (
            bot_data.get("num_contractors_range")
            or bot_data.get("num_contratistas")
            or bot_data.get("numero_contratistas")
        ),
        "country": (
            bot_data.get("country") or bot_data.get("pais") or ""
        ),
        "industry": (
            bot_data.get("industry") or bot_data.get("sector") or ""
        ),
        "name": bot_data.get("name") or "",
    }


# ---------------------------------------------------------------------------
# DEPRECATED — backwards-compat wrappers
# ---------------------------------------------------------------------------

def calculate_score(lead_data: dict) -> tuple[int, dict]:
    """
    DEPRECATED — use classify_lead() instead.
    Kept for backwards compatibility with existing callers (agent.py).
    Adapts old bot field format automatically via adapt_bot_lead_to_spec_input.
    """
    adapted = adapt_bot_lead_to_spec_input(lead_data)
    result = classify_lead(adapted)
    breakdown = {
        "puntosTrabajadores": result["breakdown"].get("employees", 0),
        "puntosRiesgo": result["breakdown"].get("risk", 0),
        "puntosContratistas": result["breakdown"].get("contractors", 0),
        "puntosNumeroContratistas": 0,  # merged into contractors in SPEC v1
    }
    return result["total_score"], breakdown


def _employees_to_int(v: Any) -> int:
    """Legacy helper — use _parse_employees_range for new code."""
    return _parse_employees_range(v)


# ---------------------------------------------------------------------------
# Unchanged plan helpers (used by agent.py)
# ---------------------------------------------------------------------------

def suggested_plan(lead_data: dict) -> str:
    """Return the Verifty plan slug based on employee count."""
    n = _parse_employees_range(
        lead_data.get("employee_count")
        or lead_data.get("numero_trabajadores")
        or lead_data.get("empleados")
        or lead_data.get("employees_range")
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
    """Only first 3 plans: bot reveals price and tries to close."""
    return plan in {"INDIVIDUAL", "EQUIPO", "ESSENTIAL_250"}

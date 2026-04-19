from __future__ import annotations
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings
from app.crm.client import crm
from app.logger import get_logger

logger = get_logger(__name__)

# Dominios considerados "personales" (NO corporativos).
GENERIC_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "yahoo.com", "yahoo.es", "yahoo.com.mx", "yahoo.com.co", "ymail.com",
    "icloud.com", "me.com", "mac.com",
    "proton.me", "protonmail.com",
    "aol.com", "zoho.com", "gmx.com", "mail.com",
    "hispavista.com", "latinmail.com",
}

OTP_EXPIRY_MINUTES = 10
OTP_LENGTH = 6


def is_corporate_email(email: str) -> bool:
    """Returns True if email is NOT from a generic/public provider."""
    if not email or "@" not in email:
        return False
    domain = email.strip().lower().split("@")[-1]
    if not domain or "." not in domain:
        return False
    return domain not in GENERIC_EMAIL_DOMAINS


def should_gate_download(lead_data: dict) -> tuple[bool, str]:
    """Decide si este lead debe pasar por OTP.
    Retorna (required, reason).
    Regla del negocio: empleados >= 50 OR email corporativo.
    """
    email = (lead_data.get("email") or "").strip()
    employees_raw = lead_data.get("employee_count") or lead_data.get("employees") or 0
    try:
        employees = int(employees_raw)
    except (ValueError, TypeError):
        employees = 0

    if employees >= 50:
        return True, f"employee_count={employees}"
    if is_corporate_email(email):
        return True, f"corporate_email={email.split('@')[-1]}"
    return False, "free_download"


def _hash_code(code: str, phone: str) -> str:
    """SHA-256 del código + phone como salt suave (nunca guardamos el código plano)."""
    return hashlib.sha256(f"{code}:{phone}".encode("utf-8")).hexdigest()


def _generate_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


OTP_RESEND_COOLDOWN_SECONDS = 120  # mínimo entre OTPs para el mismo teléfono


def get_active_otp(phone: str) -> Optional[dict]:
    """Retorna el OTP más reciente activo (no verificado, no expirado) para este teléfono."""
    now_iso = datetime.now(timezone.utc).isoformat()
    r = (
        crm.sb.table("otp_codes")
        .select("id, created_at, expires_at, template_slug, template_url")
        .eq("phone", phone)
        .is_("verified_at", "null")
        .gte("expires_at", now_iso)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None


def seconds_since_last_otp(phone: str) -> Optional[int]:
    """Retorna los segundos transcurridos desde el último OTP activo, o None si no hay."""
    active = get_active_otp(phone)
    if not active:
        return None
    created = datetime.fromisoformat(str(active["created_at"]).replace("Z", "+00:00"))
    return int((datetime.now(timezone.utc) - created).total_seconds())


def create_otp(
    phone: str,
    lead_data: dict,
    template_slug: Optional[str] = None,
    template_url: Optional[str] = None,
    template_title: Optional[str] = None,
    template_description: Optional[str] = None,
    attribution: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[str, dict]:
    """Crea un OTP, lo guarda hasheado y retorna (code_plano, row_data).
    El código plano se usa una sola vez para enviarlo por WhatsApp.
    """
    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    row = {
        "phone": phone,
        "code_hash": _hash_code(code, phone),
        "template_slug": template_slug,
        "template_url": template_url,
        "template_title": template_title,
        "template_description": template_description,
        "lead_data": lead_data or {},
        "attribution": attribution or {},
        "expires_at": expires_at.isoformat(),
        "ip_address": ip_address,
        "user_agent": user_agent,
    }
    result = crm.sb.table("otp_codes").insert(row).execute()
    saved = result.data[0] if result.data else row
    return code, saved


def verify_code(phone: str, code: str) -> tuple[bool, Optional[dict], str]:
    """Verifica un código. Retorna (ok, otp_row, message).
    Solo es válido el OTP más reciente no-verificado y no-expirado.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    # Buscar el OTP activo más reciente para este phone
    r = (
        crm.sb.table("otp_codes")
        .select("*")
        .eq("phone", phone)
        .is_("verified_at", "null")
        .gte("expires_at", now_iso)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not r.data:
        return False, None, "No hay un código activo. Solicita uno nuevo."

    otp = r.data[0]
    if otp["attempts"] >= otp["max_attempts"]:
        return False, None, "Demasiados intentos. Solicita un código nuevo."

    expected = otp["code_hash"]
    got = _hash_code(code.strip(), phone)

    # Incrementar intentos siempre
    try:
        crm.sb.table("otp_codes").update(
            {"attempts": otp["attempts"] + 1}
        ).eq("id", otp["id"]).execute()
    except Exception as e:
        logger.warning(f"Could not increment attempts: {e}")

    if expected != got:
        return False, None, "Código incorrecto."

    # Marcar como verificado
    try:
        crm.sb.table("otp_codes").update(
            {"verified_at": now_iso}
        ).eq("id", otp["id"]).execute()
    except Exception as e:
        logger.warning(f"Could not mark as verified: {e}")

    return True, otp, "Código válido."

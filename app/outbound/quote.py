"""Generación y envío de cotizaciones SST por correo vía Resend."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

PLAN_META: dict[str, dict] = {
    "basic": {
        "label": "Basic",
        "price": 39_000,
        "employees": "hasta 4 empleados",
        "highlights": [
            "Gestión documental básica",
            "21 módulos SG-SST incluidos",
            "Soporte por WhatsApp",
        ],
    },
    "starter": {
        "label": "Starter",
        "price": 220_000,
        "employees": "hasta 7 empleados",
        "highlights": [
            "Formularios digitales con firma",
            "Capacitaciones y evaluaciones",
            "Inspecciones de seguridad",
            "Gestión documental completa",
        ],
    },
    "pro": {
        "label": "Pro",
        "price": 600_000,
        "employees": "hasta 30 empleados",
        "highlights": [
            "Matriz IPEVR y análisis de riesgos",
            "Investigación de accidentes",
            "Indicadores y reportes ejecutivos",
            "Todos los módulos Starter +",
            "Soporte prioritario",
        ],
    },
    "plus": {
        "label": "Plus",
        "price": 1_220_000,
        "employees": "hasta 80 empleados",
        "highlights": [
            "Gestión multi-sede",
            "Roles y permisos avanzados",
            "Todos los módulos Pro +",
            "Asesor comercial dedicado",
        ],
    },
    "corporativo": {
        "label": "Corporativo",
        "price": None,
        "employees": "más de 80 empleados",
        "highlights": [
            "Precio a la medida",
            "Implementación asistida",
            "Soporte dedicado 24/7",
            "Integraciones a la medida",
        ],
    },
}


def _fmt_cop(amount: Optional[int]) -> str:
    if amount is None:
        return "A la medida"
    return f"${amount:,.0f}/mes".replace(",", ".")


def _build_html(
    contact_name: str,
    company: str,
    plan_key: str,
    plan_price: Optional[int],
    city: str,
    nit: str,
    validity_days: int = 30,
) -> str:
    plan = PLAN_META.get(plan_key.lower(), PLAN_META["pro"])
    price_str = _fmt_cop(plan_price if plan_price is not None else plan.get("price"))
    valid_until = (datetime.now(timezone.utc) + timedelta(days=validity_days)).strftime("%d/%m/%Y")
    highlights_html = "".join(
        f'<li style="margin:4px 0;color:#444;font-size:14px;">{h}</li>'
        for h in plan["highlights"]
    )
    nit_row = f"<tr><td style='padding:4px 0;color:#666;font-size:13px;'>NIT</td><td style='padding:4px 0;font-size:13px;text-align:right;'>{nit}</td></tr>" if nit else ""
    city_row = f"<tr><td style='padding:4px 0;color:#666;font-size:13px;'>Ciudad</td><td style='padding:4px 0;font-size:13px;text-align:right;'>{city}</td></tr>" if city else ""
    first_name = contact_name.split()[0] if contact_name else "hola"

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,Helvetica,sans-serif;">
<div style="max-width:560px;margin:32px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#7c3aed,#5b21b6);padding:28px 32px;">
    <div style="color:#fff;font-size:22px;font-weight:700;letter-spacing:-0.5px;">Verifty SST</div>
    <div style="color:#ddd6fe;font-size:13px;margin-top:4px;">Software SG-SST para Colombia</div>
  </div>

  <!-- Body -->
  <div style="padding:28px 32px;">
    <p style="color:#1a1a1a;font-size:15px;line-height:1.6;margin:0 0 20px;">
      Hola {first_name}, gracias por tu interés en Verifty SST. Aquí te compartimos la cotización que conversamos.
    </p>

    <!-- Datos del cliente -->
    <div style="background:#f9fafb;border-radius:8px;padding:16px 20px;margin-bottom:20px;">
      <div style="font-size:12px;font-weight:600;color:#7c3aed;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;">Datos de la empresa</div>
      <table style="width:100%;border-collapse:collapse;">
        <tr><td style="padding:4px 0;color:#666;font-size:13px;">Empresa</td><td style="padding:4px 0;font-size:13px;text-align:right;">{company or "—"}</td></tr>
        {nit_row}
        {city_row}
        <tr><td style="padding:4px 0;color:#666;font-size:13px;">Contacto</td><td style="padding:4px 0;font-size:13px;text-align:right;">{contact_name or "—"}</td></tr>
      </table>
    </div>

    <!-- Plan -->
    <div style="border:2px solid #7c3aed;border-radius:10px;padding:20px;margin-bottom:20px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div>
          <div style="font-size:20px;font-weight:700;color:#1a1a1a;">Plan {plan['label']}</div>
          <div style="font-size:13px;color:#666;margin-top:2px;">{plan['employees']}</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:22px;font-weight:800;color:#7c3aed;">{price_str}</div>
          <div style="font-size:11px;color:#999;">+ IVA</div>
        </div>
      </div>
      <hr style="border:none;border-top:1px solid #ede9fe;margin:16px 0;">
      <div style="font-size:13px;color:#666;font-weight:600;margin-bottom:8px;">Incluye:</div>
      <ul style="margin:0;padding-left:18px;">
        {highlights_html}
      </ul>
    </div>

    <!-- CTA -->
    <div style="text-align:center;margin-bottom:24px;">
      <a href="https://sst.verifty.com/planes"
         style="display:inline-block;background:#7c3aed;color:#fff;text-decoration:none;
                padding:14px 32px;border-radius:8px;font-size:15px;font-weight:600;">
        Comenzar ahora →
      </a>
      <div style="font-size:12px;color:#999;margin-top:10px;">Sin setup. Sin contratos. Pagas mensual.</div>
    </div>

    <!-- Info adicional -->
    <div style="background:#f9fafb;border-radius:8px;padding:14px 18px;font-size:12px;color:#666;line-height:1.6;">
      <strong>Nota:</strong> Esta cotización es válida hasta el {valid_until}.
      Los precios son los mismos para todos — sin negociación.
      Descuento del 10% pagando anual.
    </div>
  </div>

  <!-- Footer -->
  <div style="background:#f9fafb;padding:16px 32px;text-align:center;border-top:1px solid #f0f0f0;">
    <div style="font-size:12px;color:#999;">
      ¿Preguntas? Escríbenos por WhatsApp o a
      <a href="mailto:hola@sst.verifty.com" style="color:#7c3aed;text-decoration:none;">hola@sst.verifty.com</a>
    </div>
    <div style="font-size:11px;color:#bbb;margin-top:6px;">Verifty SAS · Bogotá, Colombia</div>
  </div>

</div>
</body>
</html>"""


def send_quote_email(
    to_email: str,
    contact_name: str,
    company: str,
    plan: str,
    plan_price: Optional[int] = None,
    city: str = "",
    nit: str = "",
) -> bool:
    """Envía cotización SST por correo vía Resend. Retorna True si fue exitoso."""
    if not settings.RESEND_API_KEY:
        logger.warning("[quote] RESEND_API_KEY no configurado — cotización omitida")
        return False

    try:
        import resend
    except ImportError:
        logger.warning("[quote] Paquete 'resend' no instalado")
        return False

    resend.api_key = settings.RESEND_API_KEY
    plan_meta = PLAN_META.get(plan.lower(), PLAN_META["pro"])
    plan_label = plan_meta["label"]

    html = _build_html(
        contact_name=contact_name,
        company=company,
        plan_key=plan,
        plan_price=plan_price,
        city=city,
        nit=nit,
    )

    try:
        resend.Emails.send({
            "from": f"Verifty SST <{settings.RESEND_FROM_EMAIL}>",
            "to": [to_email],
            "subject": f"Cotización Verifty SST — Plan {plan_label}",
            "html": html,
        })
        logger.info(f"[quote] Cotización enviada a {to_email} plan={plan_label}")
        return True
    except Exception as e:
        logger.warning(f"[quote] Error enviando cotización a {to_email}: {e}")
        return False

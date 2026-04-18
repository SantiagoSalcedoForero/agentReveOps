from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from anthropic import Anthropic
from app.config import settings
from app.crm.client import crm
from app.logger import get_logger

logger = get_logger(__name__)


class FinancialAgent:
    def __init__(self):
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def analyze(self) -> dict:
        sb = crm.sb
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        q_start = (now - timedelta(days=90)).isoformat()

        metrics: dict = {}
        try:
            # ARR: contratos activos
            r = sb.table("quotations").select(
                "total_cop"
            ).eq("status", "accepted").execute()
            arr = sum(float(d.get("total_cop") or 0) for d in (r.data or []))
            metrics["arr_cop"] = arr

            # Pipeline activo
            r = sb.table("deals").select(
                "current_value_cop, probability"
            ).not_.in_("stage", ["paid", "lost"]).execute()
            deals = r.data or []
            metrics["pipeline_cop"] = sum(float(d.get("current_value_cop") or 0) for d in deals)
            metrics["pipeline_weighted_cop"] = sum(
                float(d.get("current_value_cop") or 0) * float(d.get("probability") or 0) / 100
                for d in deals
            )
            metrics["active_deals"] = len(deals)

            # Ingresos mes actual
            r = sb.table("deals").select(
                "current_value_cop"
            ).eq("stage", "paid").gte(
                "actual_close_date", month_start.isoformat()
            ).execute()
            metrics["revenue_month_cop"] = sum(
                float(d.get("current_value_cop") or 0) for d in (r.data or [])
            )

            # Tasa conversión Q
            r_created = sb.table("deals").select("id").gte(
                "created_at", q_start
            ).execute()
            r_paid = sb.table("deals").select("id").eq("stage", "paid").gte(
                "created_at", q_start
            ).execute()
            created = len(r_created.data or [])
            paid = len(r_paid.data or [])
            metrics["conversion_rate_q"] = (paid / created * 100) if created else 0
            metrics["deals_created_q"] = created
            metrics["deals_paid_q"] = paid

        except Exception as e:
            logger.warning(f"financial queries: {e}")
            metrics["error"] = str(e)

        # Insights con Claude
        try:
            resp = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Eres el analista financiero de Verifty (SaaS B2B colombiano de SST). "
                        f"Datos financieros actuales:\n{json.dumps(metrics, indent=2, ensure_ascii=False)}\n\n"
                        f"Dame 2-3 insights accionables en español, ejecutivos, directos. "
                        f"Máximo 3 oraciones por insight."
                    ),
                }],
            )
            metrics["insights"] = resp.content[0].text if resp.content else ""
        except Exception as e:
            metrics["insights"] = f"Error generando insights: {e}"

        return metrics

from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from anthropic import Anthropic
from app.config import settings
from app.crm.client import crm
from app.logger import get_logger

logger = get_logger(__name__)


class CommercialAgent:
    def __init__(self):
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def analyze(self) -> dict:
        sb = crm.sb
        now = datetime.now(timezone.utc)
        week_ago = (now - timedelta(days=7)).isoformat()
        month_ago = (now - timedelta(days=30)).isoformat()

        metrics: dict = {}
        try:
            # Leads nuevos esta semana
            r = sb.table("leads").select("id, score, source, created_at").gte(
                "created_at", week_ago
            ).execute()
            leads_week = r.data or []
            metrics["leads_this_week"] = len(leads_week)
            metrics["avg_score_week"] = (
                sum(d.get("score") or 0 for d in leads_week) / len(leads_week)
                if leads_week else 0
            )

            # Leads calificados (score >= 6)
            qualified = [l for l in leads_week if (l.get("score") or 0) >= 6]
            metrics["qualified_this_week"] = len(qualified)

            # Leads sin contactar en 48h
            cutoff_48h = (now - timedelta(hours=48)).isoformat()
            r = sb.table("leads").select("id").eq("status", "lead").lte(
                "created_at", cutoff_48h
            ).is_("outbound_sent_at", "null").execute()
            metrics["cold_leads_48h"] = len(r.data or [])

            # Demos agendadas este mes
            r = sb.table("calendar_events").select("id").gte(
                "created_at", month_ago
            ).execute()
            metrics["demos_month"] = len(r.data or [])

            # Bot: conversaciones y costo
            r = sb.table("bot_usage_daily").select("*").gte(
                "day", week_ago[:10]
            ).execute()
            daily = r.data or []
            metrics["bot_conversations_week"] = sum(d.get("conversations") or 0 for d in daily)
            metrics["bot_cost_week_usd"] = sum(float(d.get("total_cost_usd") or 0) for d in daily)

            # Top fuente de leads del mes
            r = sb.table("leads").select("source").gte(
                "created_at", month_ago
            ).execute()
            sources: dict[str, int] = {}
            for l in (r.data or []):
                s = l.get("source") or "unknown"
                sources[s] = sources.get(s, 0) + 1
            metrics["lead_sources_month"] = sources

            # Reuniones agendadas por el bot
            r = sb.table("calendar_events").select("id").eq(
                "scheduled_by_bot", True
            ).gte("created_at", month_ago).execute()
            metrics["bot_meetings_month"] = len(r.data or [])

        except Exception as e:
            logger.warning(f"commercial queries: {e}")
            metrics["error"] = str(e)

        # Insights
        try:
            resp = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Eres el analista comercial de Verifty (SaaS B2B de SST). "
                        f"Datos comerciales:\n{json.dumps(metrics, indent=2, ensure_ascii=False)}\n\n"
                        f"Dame 2-3 insights accionables en español. Enfócate en: "
                        f"velocidad de contacto, calidad de leads, conversión del bot."
                    ),
                }],
            )
            metrics["insights"] = resp.content[0].text if resp.content else ""
        except Exception as e:
            metrics["insights"] = f"Error: {e}"

        return metrics

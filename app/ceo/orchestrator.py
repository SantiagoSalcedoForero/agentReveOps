from __future__ import annotations
import asyncio
import json
from datetime import datetime, timezone
from anthropic import Anthropic
from app.config import settings
from app.crm.client import crm
from app.ceo.agents.financial import FinancialAgent
from app.ceo.agents.commercial import CommercialAgent
from app.ceo.agents.ctr_optimizer import CTROptimizerAgent
from app.logger import get_logger

logger = get_logger(__name__)


class CEOOrchestrator:
    def __init__(self):
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.financial = FinancialAgent()
        self.commercial = CommercialAgent()
        self.ctr = CTROptimizerAgent()

    def _classify(self, message: str) -> list[str]:
        try:
            resp = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Clasifica esta pregunta del CEO de Verifty en una o más "
                        f"categorías. Responde SOLO con las categorías separadas por coma.\n"
                        f"Categorías: financial, commercial, seo, general\n\n"
                        f"Pregunta: \"{message}\"\n\n"
                        f"Si no estás seguro, responde 'general'."
                    ),
                }],
            )
            raw = resp.content[0].text.strip().lower() if resp.content else "general"
            cats = [c.strip() for c in raw.split(",")]
            valid = {"financial", "commercial", "seo", "general"}
            return [c for c in cats if c in valid] or ["general"]
        except Exception:
            return ["general"]

    async def chat(self, message: str, context: dict = {}) -> dict:
        categories = self._classify(message)
        if "general" in categories:
            categories = ["financial", "commercial"]

        results: dict[str, dict] = {}
        agents_used: list[str] = []

        # Run agents in parallel
        tasks = {}
        if "financial" in categories:
            tasks["financial"] = asyncio.to_thread(self.financial.analyze)
            agents_used.append("financial")
        if "commercial" in categories:
            tasks["commercial"] = asyncio.to_thread(self.commercial.analyze)
            agents_used.append("commercial")
        if "seo" in categories:
            tasks["seo"] = self.ctr.analyze()
            agents_used.append("seo")

        gathered = await asyncio.gather(
            *tasks.values(), return_exceptions=True
        )
        for key, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                results[key] = {"error": str(result)}
                logger.warning(f"Agent {key} failed: {result}")
            else:
                results[key] = result

        # Synthesize with Claude Sonnet
        try:
            resp = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system=(
                    "Eres el CEO Agent de Verifty. Tienes acceso a datos reales "
                    "del negocio. Responde de forma ejecutiva, directa y accionable. "
                    "Máximo 3 párrafos. Usa negrillas para lo importante. "
                    "Si algún agente falló, menciónalo brevemente."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"Pregunta del CEO: {message}\n\n"
                        f"Datos de los agentes:\n"
                        f"{json.dumps(results, ensure_ascii=False, indent=2, default=str)[:4000]}"
                    ),
                }],
            )
            response = resp.content[0].text if resp.content else "No pude generar respuesta."
        except Exception as e:
            response = f"Error sintetizando: {e}"

        # Save conversation
        try:
            crm.sb.table("ceo_conversations").insert({
                "message": message,
                "response": response,
                "agents_used": agents_used,
                "data": results,
            }).execute()
        except Exception as e:
            logger.warning(f"save ceo conversation: {e}")

        return {
            "response": response,
            "agents_used": agents_used,
            "data": results,
        }

    async def weekly_report(self) -> dict:
        # Run all agents
        fin_task = asyncio.to_thread(self.financial.analyze)
        com_task = asyncio.to_thread(self.commercial.analyze)
        seo_task = self.ctr.analyze()

        fin, com, seo = await asyncio.gather(
            fin_task, com_task, seo_task, return_exceptions=True
        )
        fin = fin if not isinstance(fin, Exception) else {"error": str(fin)}
        com = com if not isinstance(com, Exception) else {"error": str(com)}
        seo = seo if not isinstance(seo, Exception) else {"error": str(seo)}

        # Generate structured report
        try:
            resp = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                system=(
                    "Genera un reporte semanal ejecutivo para el CEO de Verifty. "
                    "Estructura: 1) Resumen ejecutivo (3 líneas), 2) Finanzas, "
                    "3) Comercial/Leads, 4) SEO/CTR, 5) Acciones recomendadas (lista). "
                    "Usa datos reales. Sé directo y accionable."
                ),
                messages=[{
                    "role": "user",
                    "content": json.dumps({
                        "financial": fin,
                        "commercial": com,
                        "seo": seo if isinstance(seo, list) else [seo],
                    }, ensure_ascii=False, indent=2, default=str)[:6000],
                }],
            )
            summary = resp.content[0].text if resp.content else "Error generando reporte"
        except Exception as e:
            summary = f"Error: {e}"

        report = {
            "summary": summary,
            "financial": fin,
            "commercial": com,
            "seo": seo if isinstance(seo, list) else [seo],
            "action_items": [],
        }

        # Save report
        try:
            r = crm.sb.table("ceo_reports").insert({
                "summary": summary,
                "financial": fin,
                "commercial": com,
                "seo": seo if isinstance(seo, list) else [seo],
                "action_items": [],
            }).execute()
            report["report_id"] = r.data[0]["id"] if r.data else None
        except Exception as e:
            logger.warning(f"save ceo report: {e}")

        return report

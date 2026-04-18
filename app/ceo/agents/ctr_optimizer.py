from __future__ import annotations
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
from anthropic import Anthropic
from app.config import settings
from app.crm.client import crm
from app.logger import get_logger

logger = get_logger(__name__)

SITE_URL = "sc-domain:verifty.com"

CTR_SYSTEM_PROMPT = """Eres un experto en SEO técnico y copywriting persuasivo para
Verifty, plataforma B2B de automatización de seguridad industrial
(SST/SG-SST) para empresas de alto riesgo en Latinoamérica y España.

Verifty tiene estos módulos: Capacitaciones con Face ID, Formatos
Digitales, Inventario EPP, Control de Ingresos con OCR+IA, Permisos
de Trabajo, Cronogramas, Control de Contratistas, Gestor Documental.

Sectores: construcción, energía, manufactura, minería, transporte.
Países: Colombia, Argentina, Perú, Chile, México, España.
Clientes: AES Colombia, Colgate-Palmolive, CFC, ECAR, Magnetron.

Tu tarea: analizar por qué el CTR es bajo y generar mejoras.

REGLAS de copywriting:
- Keyword principal al inicio del título
- Título: máximo 60 caracteres
- Meta description: máximo 155 caracteres
- Incluir CTA en la description (Demo gratis, Conoce más, etc.)
- Atacar el dolor del usuario (multas, accidentes, auditorías)
- Urgencia o autoridad cuando aplique

FORMATO DE RESPUESTA (JSON estricto):
{
  "diagnosis": "Por qué el CTR es bajo en 1-2 oraciones",
  "title_options": [
    {"title": "...", "chars": N, "reasoning": "..."},
    {"title": "...", "chars": N, "reasoning": "..."},
    {"title": "...", "chars": N, "reasoning": "..."}
  ],
  "description_options": [
    {"description": "...", "chars": N},
    {"description": "...", "chars": N},
    {"description": "...", "chars": N}
  ],
  "h1_suggestion": "...",
  "content_suggestion": "Párrafo corto sugerido para agregar al inicio"
}"""


class CTROptimizerAgent:
    def __init__(self):
        self.anthropic = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._credentials = None

    def _get_credentials(self):
        if self._credentials:
            return self._credentials
        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
        if not sa_json:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not configured")
        from google.oauth2 import service_account
        info = json.loads(sa_json)
        self._credentials = service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        )
        return self._credentials

    def _query_search_console(
        self, days: int, dimensions: list[str]
    ) -> list[dict]:
        creds = self._get_credentials()
        from google.auth.transport.requests import Request
        creds.refresh(Request())

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days)
        body = {
            "startDate": str(start),
            "endDate": str(end),
            "dimensions": dimensions,
            "rowLimit": 500,
        }
        encoded_site = SITE_URL.replace(":", "%3A").replace("/", "%2F")
        url = (
            f"https://searchconsole.googleapis.com/webmasters/v3/"
            f"sites/{encoded_site}/searchAnalytics/query"
        )
        r = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {creds.token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=30.0,
        )
        if r.status_code >= 400:
            logger.error(f"Search Console API {r.status_code}: {r.text[:300]}")
            raise RuntimeError(f"Search Console API error {r.status_code}")
        return r.json().get("rows", [])

    async def analyze(
        self,
        days: int = 28,
        min_impressions: int = 100,
        max_ctr: float = 0.03,
        max_position: float = 15.0,
    ) -> list[dict]:
        # 1. Query Search Console
        try:
            rows = self._query_search_console(days, ["page", "query"])
        except Exception as e:
            logger.exception(f"Search Console query failed: {e}")
            return [{"error": str(e)}]

        # 2. Aggregate by page
        pages: dict[str, dict] = {}
        for row in rows:
            keys = row.get("keys", [])
            if len(keys) < 2:
                continue
            page_url, query = keys[0], keys[1]
            if page_url not in pages:
                pages[page_url] = {
                    "url": page_url,
                    "impressions": 0,
                    "clicks": 0,
                    "queries": [],
                }
            p = pages[page_url]
            imp = row.get("impressions", 0)
            p["impressions"] += imp
            p["clicks"] += row.get("clicks", 0)
            p["queries"].append({
                "query": query,
                "impressions": imp,
                "clicks": row.get("clicks", 0),
                "ctr": row.get("ctr", 0),
                "position": row.get("position", 0),
            })

        # 3. Filter opportunities
        opportunities: list[dict] = []
        for p in pages.values():
            if p["impressions"] < min_impressions:
                continue
            ctr = p["clicks"] / p["impressions"] if p["impressions"] else 0
            avg_pos = (
                sum(q["position"] * q["impressions"] for q in p["queries"])
                / p["impressions"]
                if p["impressions"]
                else 99
            )
            if ctr <= max_ctr and avg_pos <= max_position:
                p["ctr"] = round(ctr, 4)
                p["position"] = round(avg_pos, 1)
                p["queries"] = sorted(
                    p["queries"], key=lambda q: q["impressions"], reverse=True
                )[:10]
                opportunities.append(p)

        opportunities.sort(key=lambda o: o["impressions"], reverse=True)
        opportunities = opportunities[:10]

        if not opportunities:
            return [{"message": "No hay oportunidades de CTR con los filtros actuales"}]

        # 4. Analyze each with Claude
        results: list[dict] = []
        for opp in opportunities:
            queries_fmt = "\n".join(
                f"  - \"{q['query']}\" ({q['impressions']} imp, {q['ctr']:.1%} CTR, pos {q['position']:.1f})"
                for q in opp["queries"][:5]
            )
            user_msg = (
                f"URL: {opp['url']}\n"
                f"Datos (últimos {days} días):\n"
                f"- Impresiones: {opp['impressions']}\n"
                f"- Clics: {opp['clicks']}\n"
                f"- CTR actual: {opp['ctr']:.1%}\n"
                f"- Posición promedio: {opp['position']:.1f}\n\n"
                f"Top queries:\n{queries_fmt}"
            )
            try:
                resp = self.anthropic.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1000,
                    system=CTR_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_msg}],
                )
                raw = resp.content[0].text if resp.content else "{}"
                # Parse JSON from response
                start = raw.find("{")
                end = raw.rfind("}") + 1
                analysis = json.loads(raw[start:end]) if start >= 0 else {"raw": raw}
            except Exception as e:
                logger.warning(f"CTR analysis failed for {opp['url']}: {e}")
                analysis = {"error": str(e)}

            opp["analysis"] = analysis
            results.append(opp)

            # Save to DB
            try:
                crm.sb.table("ctr_opportunities").insert({
                    "url": opp["url"],
                    "impressions": opp["impressions"],
                    "clicks": opp["clicks"],
                    "ctr": opp["ctr"],
                    "position": opp["position"],
                    "top_queries": opp["queries"],
                    "analysis": analysis,
                    "status": "pending",
                }).execute()
            except Exception as e:
                logger.warning(f"save ctr opportunity: {e}")

        return results

    async def measure_opportunity(self, opportunity_id: str) -> dict:
        """Re-consulta Search Console para una URL y compara con el baseline."""
        # 1. Traer la oportunidad guardada
        try:
            r = crm.sb.table("ctr_opportunities").select("*").eq(
                "id", opportunity_id
            ).limit(1).execute()
            if not r.data:
                return {"error": "Opportunity not found"}
            opp = r.data[0]
        except Exception as e:
            return {"error": str(e)}

        if opp["status"] not in ("applied", "measuring"):
            return {"error": "Opportunity must be in 'applied' or 'measuring' status"}

        url = opp["url"]
        applied_at = opp.get("applied_at")
        ctr_before = float(opp.get("ctr_before") or opp.get("ctr") or 0)
        impressions_before = opp.get("impressions", 0)

        # Calcular días desde aplicado
        from datetime import datetime, timezone
        days_since = 0
        if applied_at:
            try:
                applied_dt = datetime.fromisoformat(
                    str(applied_at).replace("Z", "+00:00")
                )
                days_since = (datetime.now(timezone.utc) - applied_dt).days
            except Exception:
                pass

        # Días sugeridos para medir (SEO típico)
        suggested_wait_days = 21
        ready_to_measure = days_since >= 14

        # 2. Re-consultar Search Console (últimos 28 días)
        try:
            rows = self._query_search_console(28, ["page", "query"])
        except Exception as e:
            return {
                "error": f"Search Console query failed: {e}",
                "days_since_applied": days_since,
            }

        # 3. Filtrar solo esta URL
        current_impressions = 0
        current_clicks = 0
        current_queries: list[dict] = []
        for row in rows:
            keys = row.get("keys", [])
            if len(keys) < 2:
                continue
            if keys[0] != url:
                continue
            imp = row.get("impressions", 0)
            current_impressions += imp
            current_clicks += row.get("clicks", 0)
            current_queries.append({
                "query": keys[1],
                "impressions": imp,
                "clicks": row.get("clicks", 0),
                "ctr": row.get("ctr", 0),
                "position": row.get("position", 0),
            })

        ctr_after = (
            current_clicks / current_impressions
            if current_impressions > 0
            else 0
        )
        ctr_after = round(ctr_after, 4)

        improvement = ctr_after - ctr_before
        improvement_pct = (
            (improvement / ctr_before * 100) if ctr_before > 0 else 0
        )
        improved = improvement > 0

        # 4. Guardar medición
        try:
            crm.sb.table("ctr_opportunities").update({
                "status": "measuring",
                "measured_at": datetime.now(timezone.utc).isoformat(),
                "ctr_after": ctr_after,
            }).eq("id", opportunity_id).execute()
        except Exception as e:
            logger.warning(f"save measurement: {e}")

        result = {
            "opportunity_id": opportunity_id,
            "url": url,
            "days_since_applied": days_since,
            "suggested_wait_days": suggested_wait_days,
            "ready_to_measure": ready_to_measure,
            "before": {
                "impressions": impressions_before,
                "ctr": ctr_before,
            },
            "after": {
                "impressions": current_impressions,
                "clicks": current_clicks,
                "ctr": ctr_after,
            },
            "improvement": round(improvement, 4),
            "improvement_pct": round(improvement_pct, 1),
            "improved": improved,
            "verdict": (
                f"CTR mejoró {improvement_pct:+.1f}% 🎉"
                if improved
                else f"CTR no mejoró ({improvement_pct:+.1f}%). Se sugiere nuevo cambio."
            ),
        }

        # 5. Si NO mejoró, generar nuevo análisis con sugerencias diferentes
        if not improved and ready_to_measure:
            current_queries.sort(key=lambda q: q["impressions"], reverse=True)
            queries_fmt = "\n".join(
                f"  - \"{q['query']}\" ({q['impressions']} imp, {q['ctr']:.1%} CTR)"
                for q in current_queries[:5]
            )
            prev_analysis = opp.get("analysis") or {}
            prev_titles = [
                t.get("title", "") for t in prev_analysis.get("title_options", [])
            ]
            user_msg = (
                f"URL: {url}\n"
                f"Datos ACTUALES (post-cambio, últimos 28 días):\n"
                f"- Impresiones: {current_impressions}\n"
                f"- Clics: {current_clicks}\n"
                f"- CTR actual: {ctr_after:.1%}\n"
                f"- CTR antes del cambio: {ctr_before:.1%}\n"
                f"- Días desde el cambio: {days_since}\n\n"
                f"El cambio anterior NO mejoró el CTR. Los títulos que ya probamos:\n"
                f"{chr(10).join('  - ' + t for t in prev_titles)}\n\n"
                f"Top queries actuales:\n{queries_fmt}\n\n"
                f"GENERA TÍTULOS Y DESCRIPTIONS COMPLETAMENTE DIFERENTES a los anteriores. "
                f"Prueba otro ángulo: dolor, urgencia, dato específico, pregunta, etc."
            )
            try:
                resp = self.anthropic.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1000,
                    system=CTR_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_msg}],
                )
                raw = resp.content[0].text if resp.content else "{}"
                start = raw.find("{")
                end = raw.rfind("}") + 1
                new_analysis = json.loads(raw[start:end]) if start >= 0 else {}
                result["new_analysis"] = new_analysis
                result["verdict"] += " Nuevo análisis generado con sugerencias alternativas."
            except Exception as e:
                logger.warning(f"re-analysis failed: {e}")
                result["new_analysis_error"] = str(e)

        return result

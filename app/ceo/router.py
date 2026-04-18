from __future__ import annotations
import os
import time
from collections import defaultdict
from fastapi import APIRouter, HTTPException, Request
from app.ceo.orchestrator import CEOOrchestrator
from app.crm.client import crm
from app.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ceo", tags=["CEO Agent"])
orchestrator = CEOOrchestrator()

CEO_API_KEY = os.getenv("CEO_API_KEY", "")
CRON_SECRET = os.getenv("CRON_SECRET", "")

# Rate limiting: 20 req/hour per key
_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 20
RATE_WINDOW = 3600


def _check_api_key(request: Request) -> None:
    if not CEO_API_KEY:
        raise HTTPException(500, "CEO_API_KEY not configured")
    key = request.headers.get("x-api-key", "")
    if key != CEO_API_KEY:
        raise HTTPException(401, "Invalid API key")


def _check_cron_secret(request: Request) -> None:
    if not CRON_SECRET:
        raise HTTPException(500, "CRON_SECRET not configured")
    secret = request.headers.get("x-cron-secret", "")
    if secret != CRON_SECRET:
        raise HTTPException(401, "Invalid cron secret")


def _rate_limit(key: str) -> None:
    now = time.time()
    window = [t for t in _rate_limits[key] if t > now - RATE_WINDOW]
    if len(window) >= RATE_LIMIT:
        raise HTTPException(429, "Rate limit exceeded (20/hour)")
    window.append(now)
    _rate_limits[key] = window


@router.post("/chat")
async def ceo_chat(request: Request):
    _check_api_key(request)
    _rate_limit("chat")
    body = await request.json()
    message = body.get("message")
    context = body.get("context", {})
    if not message:
        raise HTTPException(400, "message required")
    result = await orchestrator.chat(message, context)
    return result


@router.post("/report/weekly")
async def ceo_weekly_report(request: Request):
    # Acepta x-api-key (CRM manual) O x-cron-secret (cron automático)
    api_key = request.headers.get("x-api-key", "")
    cron_secret = request.headers.get("x-cron-secret", "")
    if api_key == CEO_API_KEY:
        pass  # OK via CRM
    elif cron_secret == CRON_SECRET:
        pass  # OK via cron
    else:
        raise HTTPException(401, "Invalid credentials")
    result = await orchestrator.weekly_report()
    return {
        "report_id": result.get("report_id"),
        "summary": result.get("summary", "")[:500],
    }


@router.get("/report/latest")
async def ceo_latest_report(request: Request):
    _check_api_key(request)
    try:
        r = crm.sb.table("ceo_reports").select("*").order(
            "created_at", desc=True
        ).limit(1).execute()
        if not r.data:
            raise HTTPException(404, "No reports yet")
        return r.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/ctr/analyze")
async def ceo_ctr_analyze(request: Request):
    _check_api_key(request)
    _rate_limit("ctr")
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    days = body.get("days", 28)
    min_impressions = body.get("min_impressions", 100)
    max_ctr = body.get("max_ctr", 0.03)
    max_position = body.get("max_position", 15)
    from app.ceo.agents.ctr_optimizer import CTROptimizerAgent
    agent = CTROptimizerAgent()
    results = await agent.analyze(
        days=days,
        min_impressions=min_impressions,
        max_ctr=max_ctr,
        max_position=max_position,
    )
    return {"opportunities": results, "count": len(results)}


@router.post("/ctr/measure")
async def ceo_ctr_measure(request: Request):
    """Mide el resultado de un cambio CTR aplicado: re-consulta Search Console,
    compara con el baseline y si no mejoró genera nuevas sugerencias."""
    _check_api_key(request)
    body = await request.json()
    opportunity_id = body.get("opportunity_id")
    if not opportunity_id:
        raise HTTPException(400, "opportunity_id required")
    from app.ceo.agents.ctr_optimizer import CTROptimizerAgent
    agent = CTROptimizerAgent()
    result = await agent.measure_opportunity(opportunity_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

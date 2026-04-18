"""
Backfill city/country para leads existentes usando las IPs guardadas en consent_records.

Usa ip-api.com (gratis, sin API key, 45 req/min).
Ejecutar desde la raíz del proyecto:
    python scripts/backfill_city_from_ip.py [--dry-run]
"""
from __future__ import annotations
import os
import sys
import time
import argparse
import requests
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
IP_API_BATCH  = "http://ip-api.com/batch"   # hasta 100 IPs por llamada, gratis
RATE_LIMIT_DELAY = 1.5                       # segundos entre batches (45 req/min límite)
BATCH_SIZE = 100


def geolocate_batch(ips: list[str]) -> dict[str, dict]:
    """Llama ip-api.com batch y devuelve {ip: {city, country, regionName}}."""
    body = [{"query": ip, "fields": "query,status,city,country,regionName"} for ip in ips]
    try:
        r = requests.post(IP_API_BATCH, json=body, timeout=10)
        r.raise_for_status()
        results = r.json()
        return {
            item["query"]: item
            for item in results
            if item.get("status") == "success"
        }
    except Exception as e:
        print(f"  [WARN] ip-api batch error: {e}")
        return {}


def main(dry_run: bool) -> None:
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1. Traer consent_records con IP y lead_id donde el lead no tiene ciudad aún
    print("Fetching consent records with IP...")
    r = sb.table("consent_records") \
        .select("lead_id, ip_address") \
        .not_.is_("ip_address", "null") \
        .not_.is_("lead_id", "null") \
        .execute()

    records = r.data or []
    print(f"  {len(records)} consent records con IP encontrados")

    # 2. Filtrar leads que aún no tienen city
    lead_ids = list({rec["lead_id"] for rec in records})
    leads_r = sb.table("leads") \
        .select("id, city") \
        .in_("id", lead_ids) \
        .is_("city", "null") \
        .execute()

    leads_without_city = {row["id"] for row in (leads_r.data or [])}
    print(f"  {len(leads_without_city)} leads sin ciudad de esos")

    # Construir mapa lead_id -> ip (solo los que no tienen city)
    lead_to_ip: dict[str, str] = {}
    for rec in records:
        lid = rec["lead_id"]
        if lid in leads_without_city and lid not in lead_to_ip:
            lead_to_ip[lid] = rec["ip_address"]

    if not lead_to_ip:
        print("Nada que actualizar.")
        return

    # 3. Geolocate en batches
    items = list(lead_to_ip.items())  # [(lead_id, ip), ...]
    ip_to_leads: dict[str, list[str]] = {}
    for lid, ip in items:
        ip_to_leads.setdefault(ip, []).append(lid)

    unique_ips = list(ip_to_leads.keys())
    print(f"\nGeolocalizando {len(unique_ips)} IPs únicas en batches de {BATCH_SIZE}...")

    geo_results: dict[str, dict] = {}
    for i in range(0, len(unique_ips), BATCH_SIZE):
        batch = unique_ips[i:i + BATCH_SIZE]
        print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch)} IPs...", end=" ")
        result = geolocate_batch(batch)
        geo_results.update(result)
        print(f"{len(result)} resueltas")
        if i + BATCH_SIZE < len(unique_ips):
            time.sleep(RATE_LIMIT_DELAY)

    # 4. Actualizar leads
    updated = 0
    skipped = 0
    for ip, geo in geo_results.items():
        city    = geo.get("city") or None
        country = geo.get("country") or None
        if not city and not country:
            skipped += 1
            continue

        lead_ids_for_ip = ip_to_leads.get(ip, [])
        for lid in lead_ids_for_ip:
            patch = {}
            if city:    patch["city"]    = city
            if country: patch["country"] = country
            print(f"  {'[DRY]' if dry_run else 'UPDATE'} lead={lid} city={city} country={country}")
            if not dry_run:
                try:
                    sb.table("leads").update(patch).eq("id", lid).execute()
                    updated += 1
                except Exception as e:
                    print(f"    [ERROR] {e}")
            else:
                updated += 1

    print(f"\nDone. Actualizados: {updated} | Sin datos de IP: {skipped}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra qué haría, sin escribir")
    args = parser.parse_args()
    main(dry_run=args.dry_run)

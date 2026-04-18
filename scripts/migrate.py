#!/usr/bin/env python3
"""
Aplica migraciones SQL de migrations/*.sql contra Supabase Postgres.
Idempotente: guarda las aplicadas en la tabla bot_schema_migrations.

Uso:
    python scripts/migrate.py           # aplica pendientes
    python scripts/migrate.py --status  # lista pendientes vs aplicadas
    python scripts/migrate.py --force <filename.sql>  # re-ejecuta una
"""
from __future__ import annotations
import os
import sys
import re
import hashlib
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "migrations"
load_dotenv(ROOT / ".env")

DB_URL = os.environ.get("SUPABASE_DB_URL")
if not DB_URL:
    print("❌ SUPABASE_DB_URL no está en .env")
    sys.exit(1)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def ensure_migrations_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bot_schema_migrations (
            filename   TEXT PRIMARY KEY,
            checksum   TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def load_migrations() -> list[tuple[str, str]]:
    """Return sorted list of (filename, sql_content)."""
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [(f.name, f.read_text(encoding="utf-8")) for f in files]


def get_applied(cur) -> dict[str, str]:
    cur.execute("SELECT filename, checksum FROM bot_schema_migrations")
    return {f: c for f, c in cur.fetchall()}


def apply_migration(cur, name: str, sql: str, checksum: str) -> None:
    print(f"→ Aplicando {name} ({checksum})…")
    cur.execute(sql)
    cur.execute(
        "INSERT INTO bot_schema_migrations (filename, checksum) VALUES (%s, %s) "
        "ON CONFLICT (filename) DO UPDATE SET checksum = EXCLUDED.checksum, applied_at = NOW()",
        (name, checksum),
    )
    print(f"  ✓ {name} aplicada")


def main() -> int:
    args = sys.argv[1:]
    status_only = "--status" in args
    force_target = None
    if "--force" in args:
        i = args.index("--force")
        if i + 1 >= len(args):
            print("❌ --force requiere un nombre de archivo")
            return 1
        force_target = args[i + 1]

    all_migs = load_migrations()
    if not all_migs:
        print("⚠️  No hay archivos .sql en migrations/")
        return 0

    with psycopg2.connect(DB_URL) as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            ensure_migrations_table(cur)
            conn.commit()

            applied = get_applied(cur)
            pending: list[tuple[str, str, str]] = []  # (name, sql, checksum)
            drift: list[str] = []
            for name, sql in all_migs:
                cs = sha256(sql)
                if name not in applied:
                    pending.append((name, sql, cs))
                elif applied[name] != cs:
                    drift.append(name)

            print(f"📦 {len(all_migs)} migraciones totales")
            print(f"✅ {len(applied)} ya aplicadas")
            print(f"🕐 {len(pending)} pendientes")
            if drift:
                print(f"⚠️  {len(drift)} con checksum distinto al aplicado: {drift}")

            if status_only:
                print()
                for name, _, cs in pending:
                    print(f"  pendiente: {name} ({cs})")
                for name in drift:
                    print(f"  drift:     {name}")
                return 0

            if force_target:
                match = [(n, s, c) for n, s, c in
                         ((n, s, sha256(s)) for n, s in all_migs)
                         if n == force_target]
                if not match:
                    print(f"❌ No encontré {force_target}")
                    return 1
                apply_migration(cur, *match[0])
                conn.commit()
                print(f"✅ {force_target} re-ejecutada")
                return 0

            if not pending:
                print("✨ Nada que aplicar.")
                return 0

            for name, sql, cs in pending:
                try:
                    apply_migration(cur, name, sql, cs)
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    print(f"❌ Falló {name}: {e}")
                    return 1

            print(f"\n✨ {len(pending)} migración(es) aplicada(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

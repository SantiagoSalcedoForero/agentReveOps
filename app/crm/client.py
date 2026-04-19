from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional
from supabase import create_client, Client
from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


class CRMClient:
    def __init__(self):
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:
            logger.warning("Supabase credentials missing — CRM client in noop mode")
            self.sb: Optional[Client] = None
        else:
            self.sb = create_client(
                settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY
            )

    # ---------- Conversations ----------
    def _hydrate_conv(self, row: dict) -> dict:
        row["phone"] = row.get("wa_phone_number")
        row["score"] = row.get("final_score") or 0
        ctx = row.get("context") or {}
        row["bot_retries"] = ctx.get("bot_retries", 0)
        return row

    def _normalize_phone(self, phone: str) -> str:
        """Normaliza phone a solo dígitos (sin +). Meta siempre envía sin +."""
        if not phone:
            return phone
        return phone.lstrip("+").strip()

    def get_or_create_conversation(
        self,
        phone: str,
        wa_name: str | None,
        attribution: dict | None = None,
    ) -> dict:
        phone = self._normalize_phone(phone)
        existing = (
            self.sb.table("whatsapp_conversations")
            .select("*")
            .eq("wa_phone_number", phone)
            .limit(1)
            .execute()
        )
        if existing.data:
            return self._hydrate_conv(existing.data[0])

        lead = self.get_or_create_lead(phone, wa_name, attribution=attribution)
        new = (
            self.sb.table("whatsapp_conversations")
            .insert(
                {
                    "wa_phone_number": phone,
                    "wa_contact_name": wa_name,
                    "lead_id": lead["id"],
                    "status": "active",
                    "context": {"bot_retries": 0},
                    "final_score": 0,
                }
            )
            .execute()
        )
        return self._hydrate_conv(new.data[0])

    def update_conversation(self, conversation_id: str, fields: dict) -> None:
        # Map legacy keys to real columns
        mapped: dict[str, Any] = {}
        ctx_updates: dict[str, Any] = {}
        for k, v in fields.items():
            if k == "score":
                mapped["final_score"] = v
            elif k == "bot_retries":
                ctx_updates["bot_retries"] = v
            elif k == "handoff_reason":
                ctx_updates["handoff_reason"] = v
            elif k == "context":
                mapped["context"] = v
            else:
                mapped[k] = v
        if ctx_updates:
            current = self.get_conversation(conversation_id) or {}
            new_ctx = {**(current.get("context") or {}), **ctx_updates}
            if "context" in mapped:
                mapped["context"] = {**mapped["context"], **ctx_updates}
            else:
                mapped["context"] = new_ctx
        self.sb.table("whatsapp_conversations").update(mapped).eq(
            "id", conversation_id
        ).execute()

    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        r = (
            self.sb.table("whatsapp_conversations")
            .select("*")
            .eq("id", conversation_id)
            .limit(1)
            .execute()
        )
        return self._hydrate_conv(r.data[0]) if r.data else None

    # ---------- Messages ----------
    def message_exists(self, wa_message_id: str) -> bool:
        r = (
            self.sb.table("whatsapp_messages")
            .select("id")
            .eq("wa_message_id", wa_message_id)
            .limit(1)
            .execute()
        )
        return bool(r.data)

    def save_message(
        self,
        conversation_id: str,
        direction: str,
        body: str,
        wa_message_id: Optional[str] = None,
        sender_profile_id: Optional[str] = None,
        usage: Optional[dict] = None,
    ) -> dict:
        role = "user" if direction == "inbound" else ("agent" if sender_profile_id else "bot")
        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "role": role,
            "content": body,
            "wa_message_id": wa_message_id,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        if usage:
            # Merge optional token/cost fields when available (silently skip
            # if columns don't exist yet — migration may not be applied)
            for k in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "cost_usd",
                "model",
                "latency_ms",
            ):
                if k in usage and usage[k] is not None:
                    payload[k] = usage[k]
        try:
            r = self.sb.table("whatsapp_messages").insert(payload).execute()
            return r.data[0]
        except Exception as e:
            err_str = str(e).lower()
            # Unique constraint violation (duplicate wa_message_id) → ignore silently
            if "unique" in err_str or "duplicate" in err_str or "23505" in err_str:
                logger.info(
                    f"Duplicate message ignored (constraint): wa_message_id="
                    f"{wa_message_id}"
                )
                return payload  # return the payload as-is, not saved
            # If schema doesn't have the new columns yet, retry without them
            if usage and "column" in err_str:
                base = {k: v for k, v in payload.items() if k in {
                    "conversation_id", "role", "content",
                    "wa_message_id", "sent_at"
                }}
                r = self.sb.table("whatsapp_messages").insert(base).execute()
                return r.data[0]
            raise

    def get_message_history(self, conversation_id: str, limit: int = 30) -> list[dict]:
        r = (
            self.sb.table("whatsapp_messages")
            .select("role, content, sent_at")
            .eq("conversation_id", conversation_id)
            .order("sent_at", desc=False)
            .limit(limit)
            .execute()
        )
        data = r.data or []
        # Normalize to legacy shape expected by agent
        return [
            {
                "direction": "inbound" if m["role"] == "user" else "outbound",
                "body": m["content"] or "",
            }
            for m in data
        ]

    # ---------- Leads ----------
    def get_or_create_lead(
        self,
        phone: str,
        wa_name: str | None,
        attribution: dict | None = None,
    ) -> dict:
        existing = (
            self.sb.table("leads")
            .select("*")
            .eq("phone", phone)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]

        first = (wa_name or "Lead WhatsApp").split(" ")[0]
        last_parts = (wa_name or "").split(" ")[1:]
        last = " ".join(last_parts) if last_parts else None

        # Determinar el canal real basado en la atribución
        source = "whatsapp_bot"  # default
        detected = "whatsapp"
        created_via = "whatsapp_bot"
        if attribution:
            trigger = (attribution.get("conversion_trigger") or "").lower()
            utm_src = (attribution.get("utm_source") or "").lower()
            utm_med = (attribution.get("utm_medium") or "").lower()

            if trigger == "landing_download":
                source = "seo_descarga"
                created_via = "landing_download"
                detected = utm_src or "seo"
            elif trigger == "ctwa":
                source = "social"
                created_via = "whatsapp_ctwa"
                detected = "facebook_ad"
            elif utm_src == "google" and utm_med == "organic":
                source = "seo"
                created_via = "seo_organic"
                detected = "google"
            elif utm_src == "google" and utm_med in ("cpc", "paid"):
                source = "seo"
                created_via = "google_ads"
                detected = "google_ads"
            elif utm_src in ("facebook", "instagram", "facebook_ad"):
                source = "social"
                created_via = "social_" + utm_src
                detected = utm_src
            elif utm_src in ("linkedin", "tiktok"):
                source = "social"
                created_via = "social_" + utm_src
                detected = utm_src
            elif trigger in ("contact_form", "demo_request", "newsletter"):
                source = "referral"
                created_via = trigger
                detected = utm_src or "website"

        row: dict[str, Any] = {
            "phone": phone,
            "first_name": first,
            "last_name": last,
            "source": source,
            "status": "lead",
            "score": 0,
            "created_via": created_via,
            "detected_source": detected,
        }
        if attribution:
            for key in (
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_content",
                "referrer",
                "first_page_url",
                "conversion_page_url",
                "conversion_trigger",
                "created_via_url",
                "session_id",
            ):
                val = attribution.get(key)
                if val:
                    row[key] = val

        new = self.sb.table("leads").insert(row).execute()
        return new.data[0]

    def update_lead(self, lead_id: str, fields: dict) -> None:
        self.sb.table("leads").update(fields).eq("id", lead_id).execute()

    def get_lead(self, lead_id: str) -> Optional[dict]:
        r = (
            self.sb.table("leads")
            .select("*")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
        return r.data[0] if r.data else None

    def get_lead_by_phone(self, phone: str) -> Optional[dict]:
        r = (
            self.sb.table("leads")
            .select("id, first_name")
            .eq("phone", phone)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        return r.data[0] if r.data else None

    def log_activity(self, phone: str, title: str, body: str = "") -> None:
        """Crea una actividad en la línea de tiempo del lead buscado por teléfono.
        Falla silenciosamente si el lead no existe aún.
        """
        try:
            lead = self.get_lead_by_phone(phone)
            if not lead:
                return
            self.create_activity(
                lead_id=lead["id"],
                activity_type="note",
                title=title,
                body=body,
            )
        except Exception as e:
            logger.warning(f"log_activity failed phone={phone}: {e}")

    # ---------- Activities ----------
    def create_activity(
        self, lead_id: str, activity_type: str, title: str, body: str = ""
    ) -> dict:
        r = (
            self.sb.table("activities")
            .insert(
                {
                    "lead_id": lead_id,
                    "activity_type": activity_type,
                    "title": title,
                    "description": body,
                    "is_bot_activity": True,
                }
            )
            .execute()
        )
        return r.data[0]

    # ---------- Routing ----------
    def get_active_routing_config(self) -> Optional[dict]:
        r = (
            self.sb.table("routing_config")
            .select("*")
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        return r.data[0] if r.data else None

    def get_routing_members(self, routing_config_id: str) -> list[dict]:
        r = (
            self.sb.table("routing_members")
            .select("*, profile:profiles(*)")
            .eq("routing_config_id", routing_config_id)
            .execute()
        )
        return r.data or []

    def get_profile(self, profile_id: str) -> Optional[dict]:
        r = (
            self.sb.table("profiles")
            .select("*")
            .eq("id", profile_id)
            .limit(1)
            .execute()
        )
        return r.data[0] if r.data else None

    # ---------- Notifications ----------
    def insert_notification(
        self,
        profile_id: str,
        notif_type: str,
        title: str,
        body: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        r = (
            self.sb.table("crm_notifications")
            .insert(
                {
                    "profile_id": profile_id,
                    "type": notif_type,
                    "title": title,
                    "body": body,
                    "metadata": metadata or {},
                    "read": False,
                }
            )
            .execute()
        )
        return r.data[0]

    # ---------- Calendar ----------
    def save_calendar_event(self, payload: dict) -> dict:
        r = self.sb.table("calendar_events").insert(payload).execute()
        return r.data[0]


crm = CRMClient()

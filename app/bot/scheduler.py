from __future__ import annotations
import os
import uuid
from datetime import datetime, timedelta, time, timezone
from typing import Any, Optional
import pytz
import httpx

from app.config import settings
from app.crm.client import crm
from app.logger import get_logger

logger = get_logger(__name__)

DAY_LABEL_ES = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")


class MeetingScheduler:
    def __init__(self):
        self.tz = pytz.timezone(settings.BOT_TIMEZONE)

    # --------- Google OAuth token management (per user in auth.users) ---------
    async def _get_user_google_token(self, user_id: str) -> Optional[str]:
        """Fetch the user's Google access_token from auth.users.user_metadata.
        Refresh if expired and GOOGLE_CLIENT_ID/SECRET are configured.
        """
        url = f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}"
        headers = {
            "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(url, headers=headers)
                if r.status_code >= 400:
                    logger.error(f"get user {user_id}: {r.status_code}")
                    return None
                data = r.json()
        except Exception as e:
            logger.exception(f"admin/users fetch: {e}")
            return None

        meta = data.get("user_metadata") or {}
        access = meta.get("google_access_token")
        refresh = meta.get("google_refresh_token")
        expires_at = meta.get("google_token_expires_at")
        if not access:
            return None

        # Check expiry
        try:
            exp_iso = expires_at
            if isinstance(exp_iso, (int, float)):
                exp_dt = datetime.fromtimestamp(exp_iso, tz=timezone.utc)
            else:
                exp_dt = datetime.fromisoformat(
                    str(exp_iso).replace("Z", "+00:00")
                ) if exp_iso else None
        except Exception:
            exp_dt = None

        now_utc = datetime.now(timezone.utc)
        if exp_dt and exp_dt > now_utc + timedelta(minutes=2):
            return access

        # Try to refresh
        if refresh and GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    rr = await client.post(
                        "https://oauth2.googleapis.com/token",
                        data={
                            "client_id": GOOGLE_CLIENT_ID,
                            "client_secret": GOOGLE_CLIENT_SECRET,
                            "refresh_token": refresh,
                            "grant_type": "refresh_token",
                        },
                    )
                if rr.status_code == 200:
                    tok = rr.json()
                    new_access = tok.get("access_token")
                    expires_in = int(tok.get("expires_in", 3600))
                    new_exp = (now_utc + timedelta(seconds=expires_in)).isoformat()
                    # Persist back to user_metadata
                    new_meta = {
                        **meta,
                        "google_access_token": new_access,
                        "google_token_expires_at": new_exp,
                    }
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        await client.put(
                            url,
                            headers={**headers, "Content-Type": "application/json"},
                            json={"user_metadata": new_meta},
                        )
                    return new_access
                else:
                    logger.error(f"token refresh failed: {rr.status_code} {rr.text[:200]}")
            except Exception as e:
                logger.exception(f"refresh call: {e}")

        # Best-effort: return stale access token; Calendar call will fail and we fall back
        return access

    # --------- Slot generation with REAL calendar availability ---------
    async def get_available_slots(
        self, routing_config_id: str, days_ahead: int = 5
    ) -> list[dict]:
        members = crm.get_routing_members(routing_config_id)
        windows = self._member_windows(members)
        now = datetime.now(self.tz)
        start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=2)
        end = start + timedelta(days=days_ahead)

        # Generar candidatos naive
        candidates = self._naive_slots(start, end, windows, max_slots=15)
        if not candidates:
            return []

        # Consultar Google Calendar freebusy para filtrar por disponibilidad real
        busy_periods = await self._fetch_all_busy(members, start, end)
        if busy_periods is not None:
            free_slots = self._filter_busy(candidates, busy_periods)
            logger.info(
                f"Slots: {len(candidates)} candidates → {len(free_slots)} free "
                f"({len(busy_periods)} busy periods from {len(members)} members)"
            )
            return free_slots[:3]

        # Si freebusy falló, retornar los naive (mejor algo que nada)
        logger.warning("freebusy failed, returning naive slots")
        return candidates[:3]

    async def _fetch_all_busy(
        self,
        members: list[dict],
        time_min: datetime,
        time_max: datetime,
    ) -> list[tuple[datetime, datetime]] | None:
        """Consulta Google Calendar Freebusy API para TODOS los miembros.
        Retorna lista unificada de (start, end) busy periods, o None si falló.
        """
        # Recoger tokens + emails
        calendar_items: list[dict] = []
        access_token: str | None = None
        for m in members:
            prof = m.get("profile") or {}
            uid = prof.get("id") or m.get("profile_id")
            email = prof.get("email")
            if not uid or not email:
                continue
            tok = await self._get_user_google_token(uid)
            if tok:
                access_token = tok  # usamos cualquier token válido
                calendar_items.append({"id": email})

        if not access_token or not calendar_items:
            return None

        body = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "timeZone": settings.BOT_TIMEZONE,
            "items": calendar_items,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    "https://www.googleapis.com/calendar/v3/freeBusy",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            if r.status_code >= 400:
                logger.error(f"freebusy API {r.status_code}: {r.text[:300]}")
                return None
            data = r.json()
        except Exception as e:
            logger.exception(f"freebusy request failed: {e}")
            return None

        # Unificar todos los busy periods de todos los calendarios
        all_busy: list[tuple[datetime, datetime]] = []
        for cal_id, cal_data in data.get("calendars", {}).items():
            for b in cal_data.get("busy", []):
                try:
                    bs = datetime.fromisoformat(
                        b["start"].replace("Z", "+00:00")
                    ).astimezone(self.tz)
                    be = datetime.fromisoformat(
                        b["end"].replace("Z", "+00:00")
                    ).astimezone(self.tz)
                    all_busy.append((bs, be))
                except Exception:
                    continue

        logger.info(
            f"freebusy: {len(all_busy)} busy periods across "
            f"{len(calendar_items)} calendar(s)"
        )
        return all_busy

    def _filter_busy(
        self,
        candidates: list[dict],
        busy: list[tuple[datetime, datetime]],
    ) -> list[dict]:
        """Filtra candidatos que colisionan con algún busy period."""
        free: list[dict] = []
        for slot in candidates:
            slot_start = datetime.fromisoformat(slot["start"]).astimezone(self.tz)
            slot_end = datetime.fromisoformat(slot["end"]).astimezone(self.tz)
            collides = any(
                not (slot_end <= bs or slot_start >= be)
                for bs, be in busy
            )
            if not collides:
                free.append(slot)
        return free

    def _member_windows(
        self, members: list[dict]
    ) -> dict[int, tuple[time, time]]:
        windows: dict[int, tuple[time, time]] = {}
        days_default = [0, 1, 2, 3, 4]
        start_def = time(9, 0)
        end_def = time(17, 0)
        if members:
            m = members[0]
            prof = m.get("profile") or {}
            s = prof.get("scheduling_window_start")
            e = prof.get("scheduling_window_end")
            if s:
                try:
                    start_def = time.fromisoformat(str(s)[:8])
                except Exception:
                    pass
            if e:
                try:
                    end_def = time.fromisoformat(str(e)[:8])
                except Exception:
                    pass
        for d in days_default:
            windows[d] = (start_def, end_def)
        return windows

    def _naive_slots(
        self,
        start: datetime,
        end: datetime,
        windows: dict[int, tuple[time, time]],
        max_slots: int = 3,
    ) -> list[dict]:
        results: list[dict] = []
        cursor = start
        while cursor < end and len(results) < max_slots:
            day_idx = cursor.weekday()
            window = windows.get(day_idx)
            if not window:
                cursor = (cursor + timedelta(days=1)).replace(hour=9, minute=0)
                continue
            day_start = cursor.replace(
                hour=window[0].hour, minute=0, second=0, microsecond=0
            )
            day_end = cursor.replace(
                hour=window[1].hour, minute=0, second=0, microsecond=0
            )
            if cursor < day_start:
                cursor = day_start
            slot_end = cursor + timedelta(minutes=30)
            if slot_end > day_end:
                cursor = (cursor + timedelta(days=1)).replace(hour=9, minute=0)
                continue
            results.append(
                {"start": cursor.isoformat(), "end": slot_end.isoformat()}
            )
            cursor = cursor + timedelta(hours=2)
        return results

    # --------- Actual booking via Google Calendar API ---------
    async def book_meeting(
        self,
        slot: dict,
        lead_data: dict,
        routing_config_id: Optional[str],
        conversation_id: str,
    ) -> dict:
        members = crm.get_routing_members(routing_config_id) if routing_config_id else []
        if not members:
            raise RuntimeError("No routing members available to own the meeting")

        # Pick first member as organizer (can be rotated later)
        owner = members[0]
        organizer_profile = owner.get("profile") or {}
        organizer_id = organizer_profile.get("id") or owner.get("profile_id")
        organizer_email = organizer_profile.get("email")

        attendees_emails = [
            m["profile"]["email"]
            for m in members
            if m.get("profile") and m["profile"].get("email")
        ]
        lead_email = (lead_data or {}).get("email") or ""
        lead_email = lead_email.strip()
        # Solo agregar el lead como attendee si tiene email válido (con @ y dominio)
        if lead_email and "@" in lead_email and "." in lead_email.split("@")[-1]:
            attendees_emails.append(lead_email)
        # dedupe
        attendees_emails = list(dict.fromkeys([e for e in attendees_emails if e]))

        google_event_id: Optional[str] = None
        meet_link: Optional[str] = None

        access_token = await self._get_user_google_token(organizer_id) if organizer_id else None
        if not access_token:
            raise RuntimeError(
                f"Organizer {organizer_email} has no valid google_access_token"
            )

        company = lead_data.get("company") or lead_data.get("company_name") or "Lead"
        lead_name = lead_data.get("name") or "Prospecto"
        summary = f"Demo Verifty — {company}"
        description = (
            f"Reunión agendada automáticamente por el bot de Verifty.\n\n"
            f"Prospecto: {lead_name}\n"
            f"Empresa: {company}\n"
            f"País: {lead_data.get('country', 'N/A')}\n"
            f"Sector: {lead_data.get('industry', 'N/A')}\n"
            f"Empleados: {lead_data.get('employee_count', 'N/A')}\n"
            f"Dolor: {lead_data.get('pain_point', 'N/A')}\n"
        )

        event_body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": slot["start"], "timeZone": settings.BOT_TIMEZONE},
            "end": {"dateTime": slot["end"], "timeZone": settings.BOT_TIMEZONE},
            "attendees": [{"email": e} for e in attendees_emails],
            "conferenceData": {
                "createRequest": {
                    "requestId": str(uuid.uuid4()),
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
            "reminders": {"useDefault": True},
        }

        g_url = (
            "https://www.googleapis.com/calendar/v3/calendars/primary/events"
            "?conferenceDataVersion=1&sendUpdates=all"
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(g_url, headers=headers, json=event_body)
            if r.status_code >= 400:
                logger.error(f"Calendar insert failed: {r.status_code} {r.text[:300]}")
                raise RuntimeError(f"Google Calendar API error {r.status_code}")
            ev = r.json()

        google_event_id = ev.get("id")
        for entry in ev.get("conferenceData", {}).get("entryPoints", []):
            if entry.get("entryPointType") == "video":
                meet_link = entry.get("uri")
                break
        if not meet_link:
            meet_link = ev.get("hangoutLink")

        # Persist to Supabase calendar_events
        lead_id = None
        try:
            conv = crm.get_conversation(conversation_id)
            lead_id = (conv or {}).get("lead_id")
        except Exception:
            pass

        payload = {
            "google_event_id": google_event_id,
            "organizer_id": organizer_id,
            "attendee_ids": [m.get("profile_id") for m in members if m.get("profile_id")],
            "lead_id": lead_id,
            "title": summary,
            "description": description,
            "start_time": slot["start"],
            "end_time": slot["end"],
            "meet_link": meet_link,
            "status": "confirmed",
            "scheduled_by_bot": True,
            "routing_config_id": routing_config_id,
        }
        try:
            crm.save_calendar_event(payload)
        except Exception as e:
            logger.warning(f"calendar_events insert failed (event created in Google): {e}")

        # Mark lead as meeting_scheduled
        if lead_id:
            try:
                crm.update_lead(lead_id, {"demo_scheduled_at": slot["start"]})
            except Exception:
                pass

        return {
            "google_event_id": google_event_id,
            "meet_link": meet_link,
            "start_time": slot["start"],
            "organizer_email": organizer_email,
        }

    # --------- WhatsApp button label formatting ---------
    def format_slots_for_whatsapp(self, slots: list[dict]) -> list[str]:
        labels: list[str] = []
        for s in slots:
            dt = datetime.fromisoformat(s["start"])
            day = DAY_LABEL_ES[dt.weekday()]
            hour = dt.strftime("%-I:%M%p").lower()
            labels.append(f"{day} {hour}")
        return labels


meeting_scheduler = MeetingScheduler()

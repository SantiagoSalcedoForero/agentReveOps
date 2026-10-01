import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v18.0")
    # Los estados de entrega (sent/delivered/read/failed) de los mensajes que
    # manda el MOTOR de Flow llegan a este mismo webhook (misma app y línea de
    # Meta). El bot no los usa; se reenvían a la app para que la ficha de la
    # persona diga si el WhatsApp llegó (ECAR, 01-oct-2026). Vacío = no reenviar.
    FLOW_STATUS_FORWARD_URL = os.getenv(
        "FLOW_STATUS_FORWARD_URL", "https://sst.verifty.com/api/webhooks/meta-whatsapp"
    )

    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")

    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    CRM_URL = os.getenv("CRM_URL", "https://crm.verifty.com")
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    # Escala 0-15 del scorer: 8 = CALIFICADO (dispara agendamiento). El default viejo
    # era 70 (escala 0-100 retirada) — con él NINGÚN lead calificaba jamás.
    QUALIFIED_SCORE_THRESHOLD = int(os.getenv("QUALIFIED_SCORE_THRESHOLD", "8"))
    MAX_BOT_RETRIES = int(os.getenv("MAX_BOT_RETRIES", "2"))
    BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "America/Bogota")

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "")

    # Outbound / nudges
    OUTBOUND_LEAD_TEMPLATE = os.getenv(
        "OUTBOUND_LEAD_TEMPLATE", "verifty_outbound_lead"
    )
    OUTBOUND_DEMO_NUDGE_TEMPLATE = os.getenv(
        "OUTBOUND_DEMO_NUDGE_TEMPLATE", "verifty_demo_nudge"
    )
    OUTBOUND_SST_FOLLOWUP_TEMPLATE = os.getenv(
        "OUTBOUND_SST_FOLLOWUP_TEMPLATE", "verifty_sst_followup"
    )
    DEMO_NUDGE_DELAY_MINUTES = int(
        os.getenv("DEMO_NUDGE_DELAY_MINUTES", "35")
    )

    # CEO Agent
    CEO_API_KEY = os.getenv("CEO_API_KEY", "")
    CRON_SECRET = os.getenv("CRON_SECRET", "")

    # Meeting reminders
    MEETING_REMINDER_TEMPLATE = os.getenv(
        "MEETING_REMINDER_TEMPLATE", "verifty_meeting_reminder"
    )
    MEETING_REMINDER_MINUTES_BEFORE = int(
        os.getenv("MEETING_REMINDER_MINUTES_BEFORE", "10")
    )
    # Email (Resend)
    RESEND_API_KEY    = os.getenv("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "notificaciones@verifty.com")


settings = Settings()

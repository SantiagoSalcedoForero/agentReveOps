import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v18.0")

    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    CRM_URL = os.getenv("CRM_URL", "https://crm.verifty.com")
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

    QUALIFIED_SCORE_THRESHOLD = int(os.getenv("QUALIFIED_SCORE_THRESHOLD", "70"))
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
    DEMO_NUDGE_DELAY_MINUTES = int(
        os.getenv("DEMO_NUDGE_DELAY_MINUTES", "35")
    )

    # CEO Agent
    CEO_API_KEY = os.getenv("CEO_API_KEY", "")
    CRON_SECRET = os.getenv("CRON_SECRET", "")


settings = Settings()

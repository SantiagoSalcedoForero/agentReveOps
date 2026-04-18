-- Soporte para mensajes post-OTP dinámicos por CUALQUIER plantilla del catálogo
-- (no solo los 5 slugs hardcoded). El landing manda template_title +
-- template_description al /landing/gate; los guardamos en otp_codes y los
-- persistimos en whatsapp_conversations para que el bot los recuerde en
-- mensajes posteriores.

ALTER TABLE otp_codes
    ADD COLUMN IF NOT EXISTS template_title       TEXT,
    ADD COLUMN IF NOT EXISTS template_description TEXT;

ALTER TABLE whatsapp_conversations
    ADD COLUMN IF NOT EXISTS template_slug  TEXT,
    ADD COLUMN IF NOT EXISTS template_title TEXT;

CREATE INDEX IF NOT EXISTS idx_conversations_template_slug
    ON whatsapp_conversations(template_slug)
    WHERE template_slug IS NOT NULL;

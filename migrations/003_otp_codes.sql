-- OTP para verificación de WhatsApp en descargas de plantillas desde landing.
-- Flujo: lead llena form → /landing/gate emite OTP → WhatsApp → lead valida en /landing/verify.

CREATE TABLE IF NOT EXISTS otp_codes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone               TEXT NOT NULL,
    code_hash           TEXT NOT NULL,            -- SHA-256 del código (nunca guardamos el código plano)
    template_slug       TEXT,                     -- ej. "ats-excel", "matriz-epp"
    template_url        TEXT,                     -- URL final del archivo a descargar
    lead_data           JSONB NOT NULL DEFAULT '{}',
    attribution         JSONB NOT NULL DEFAULT '{}',
    attempts            INTEGER NOT NULL DEFAULT 0,
    max_attempts        INTEGER NOT NULL DEFAULT 5,
    expires_at          TIMESTAMPTZ NOT NULL,
    verified_at         TIMESTAMPTZ,
    ip_address          INET,
    user_agent          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_otp_phone ON otp_codes(phone);
CREATE INDEX IF NOT EXISTS idx_otp_expires ON otp_codes(expires_at) WHERE verified_at IS NULL;

ALTER TABLE otp_codes ENABLE ROW LEVEL SECURITY;

-- Solo el service_role (backend bot) puede leer/escribir. No hay policy para auth users.
CREATE POLICY "service role full access otp_codes"
    ON otp_codes FOR ALL
    USING (true)
    WITH CHECK (true);

-- M4: Follow-up 24h SST — timestamps en la tabla leads
-- last_sst_link_sent_at:             cuándo se envió el link de compra SST al lead
-- followup_link_no_pago_enviado_at:  cuándo se envió el follow-up de 24h (si aplica)

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS last_sst_link_sent_at         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS followup_link_no_pago_enviado_at TIMESTAMPTZ;

-- Índice para que el scheduler pueda filtrar leads con link enviado hace >24h sin pagar
CREATE INDEX IF NOT EXISTS idx_leads_sst_followup
    ON leads (last_sst_link_sent_at)
    WHERE last_sst_link_sent_at IS NOT NULL
      AND followup_link_no_pago_enviado_at IS NULL
      AND paid_at IS NULL;

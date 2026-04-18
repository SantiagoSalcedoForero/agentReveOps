-- Soporte para conversaciones bot-initiated (outbound) + nudges programados
-- (ej: lead llenó form "agendar demo" pero no agendó en 35 min).

-- Tracking en lead
ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS outbound_sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS nudge_sent_at    TIMESTAMPTZ;

-- Cola de nudges pendientes
CREATE TABLE IF NOT EXISTS pending_nudges (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone           TEXT NOT NULL,
  lead_id         UUID REFERENCES leads(id) ON DELETE CASCADE,
  conversation_id UUID REFERENCES whatsapp_conversations(id) ON DELETE SET NULL,
  kind            TEXT NOT NULL,            -- 'demo_no_show' | 'contact_form_greeting'
  due_at          TIMESTAMPTZ NOT NULL,
  payload         JSONB DEFAULT '{}',
  status          TEXT NOT NULL DEFAULT 'pending',   -- pending | sent | failed | cancelled | skipped
  attempts        INTEGER NOT NULL DEFAULT 0,
  last_error      TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  sent_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pending_nudges_due
  ON pending_nudges(due_at) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_pending_nudges_lead
  ON pending_nudges(lead_id);

ALTER TABLE pending_nudges ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service role full access pending_nudges"
  ON pending_nudges FOR ALL
  USING (true)
  WITH CHECK (true);

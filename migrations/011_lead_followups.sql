-- Migración 011: seguimientos automáticos post-descarga de plantilla
-- Agrega columnas de seguimiento a whatsapp_conversations

ALTER TABLE whatsapp_conversations
  ADD COLUMN IF NOT EXISTS followup_count   INTEGER     NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS next_followup_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS followup_stopped BOOLEAN     NOT NULL DEFAULT FALSE;

-- Índice para que el job de seguimiento sea eficiente
CREATE INDEX IF NOT EXISTS idx_conversations_followup
  ON whatsapp_conversations (next_followup_at)
  WHERE next_followup_at IS NOT NULL
    AND followup_stopped  = FALSE;

-- Verificación
DO $$
BEGIN
  RAISE NOTICE 'Migración 011 aplicada OK';
END $$;

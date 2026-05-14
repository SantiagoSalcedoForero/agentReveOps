-- Migration 010: Soporte de webchat en conversaciones + tabla de aprendizajes VERA
-- Aplicar en Supabase SQL Editor

-- 1. Permitir wa_phone_number nulo (requerido para sesiones de webchat anónimas)
ALTER TABLE whatsapp_conversations
  ALTER COLUMN wa_phone_number DROP NOT NULL;

-- 2. Canal de origen de la conversación
ALTER TABLE whatsapp_conversations
  ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'whatsapp'
  CHECK (channel IN ('whatsapp', 'webchat'));

-- 3. Identificador de sesión para webchat (UUID generado en el cliente)
ALTER TABLE whatsapp_conversations
  ADD COLUMN IF NOT EXISTS session_id UUID;

-- Índice para lookup rápido por session_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_session_id
  ON whatsapp_conversations (session_id)
  WHERE session_id IS NOT NULL;

-- 4. Tabla de aprendizajes de VERA (para mejora continua post-conversación)
CREATE TABLE IF NOT EXISTS vera_sales_learnings (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  session_id            UUID,
  conversation_id       UUID REFERENCES whatsapp_conversations(id) ON DELETE SET NULL,
  channel               TEXT DEFAULT 'webchat',

  -- Perfil del lead
  lead_employees        INTEGER,
  lead_sector           TEXT,
  lead_arl_class        TEXT,
  lead_has_sst_specialist BOOLEAN,
  lead_current_tool     TEXT,

  -- Resultado de la venta
  plan_recommended      TEXT,
  plan_purchased        TEXT,
  objections            JSONB DEFAULT '[]',
  winning_argument      TEXT,
  loss_reason           TEXT,
  outcome               TEXT CHECK (outcome IN (
                          'purchased', 'lost', 'handoff',
                          'abandoned', 'whatsapp_handoff', 'plans_shown'
                        )),

  -- Resumen para el digest de aprendizajes
  conversation_summary  TEXT,
  raw_context           JSONB DEFAULT '{}'
);

-- RLS: solo service role puede leer/escribir (el bot usa service role key)
ALTER TABLE vera_sales_learnings ENABLE ROW LEVEL SECURITY;

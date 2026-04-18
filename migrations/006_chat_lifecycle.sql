-- Ciclo de vida completo de chats: routing, estados, encuesta de satisfacción.

-- Nuevas columnas en conversaciones
ALTER TABLE whatsapp_conversations
    ADD COLUMN IF NOT EXISTS chat_status            TEXT DEFAULT 'bot_active',
    ADD COLUMN IF NOT EXISTS escalated_at            TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS agent_accepted_at       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS closed_at               TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS close_reason             TEXT,
    ADD COLUMN IF NOT EXISTS lost_at                  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reopened_at              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_message_at          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS waiting_with_agents_since TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS satisfaction_rating      INTEGER,       -- 1=mala, 2=buena, 3=excelente
    ADD COLUMN IF NOT EXISTS satisfaction_feedback    TEXT;

-- Agent availability
ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS is_online           BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS active_chat_count   INTEGER NOT NULL DEFAULT 0;

-- Índices para el inbox del agente
CREATE INDEX IF NOT EXISTS idx_conv_chat_status
    ON whatsapp_conversations(chat_status);

CREATE INDEX IF NOT EXISTS idx_conv_assigned_agent
    ON whatsapp_conversations(assigned_profile_id)
    WHERE chat_status IN ('waiting_agent', 'agent_active');

CREATE INDEX IF NOT EXISTS idx_conv_last_message
    ON whatsapp_conversations(last_message_at DESC NULLS LAST);

-- Vista de inbox para agentes
CREATE OR REPLACE VIEW agent_inbox AS
SELECT
    c.id                    AS conversation_id,
    c.wa_phone_number,
    c.wa_contact_name,
    c.lead_id,
    c.chat_status,
    c.status,
    c.final_score,
    c.assigned_profile_id,
    c.escalated_at,
    c.agent_accepted_at,
    c.closed_at,
    c.close_reason,
    c.lost_at,
    c.reopened_at,
    c.last_message_at,
    c.satisfaction_rating,
    c.template_slug,
    c.template_title,
    c.context,
    p.full_name             AS assigned_agent_name,
    p.email                 AS assigned_agent_email,
    (SELECT content FROM whatsapp_messages m
     WHERE m.conversation_id = c.id
     ORDER BY m.sent_at DESC LIMIT 1)
                            AS last_message_preview
FROM whatsapp_conversations c
LEFT JOIN profiles p ON p.id = c.assigned_profile_id;

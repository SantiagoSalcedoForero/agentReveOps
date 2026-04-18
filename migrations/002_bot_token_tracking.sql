-- Tracking de consumo de tokens y costo por mensaje del bot.
-- Solo se llena en mensajes de role='bot' (los que generó Claude).

ALTER TABLE whatsapp_messages
  ADD COLUMN IF NOT EXISTS input_tokens       INTEGER,
  ADD COLUMN IF NOT EXISTS output_tokens      INTEGER,
  ADD COLUMN IF NOT EXISTS cache_read_tokens  INTEGER,
  ADD COLUMN IF NOT EXISTS cache_write_tokens INTEGER,
  ADD COLUMN IF NOT EXISTS cost_usd           NUMERIC(12, 6),
  ADD COLUMN IF NOT EXISTS model              TEXT,
  ADD COLUMN IF NOT EXISTS latency_ms         INTEGER;

-- Vista de costo por conversación
CREATE OR REPLACE VIEW bot_conversation_costs AS
SELECT
  c.id                                              AS conversation_id,
  c.wa_phone_number,
  c.wa_contact_name,
  c.lead_id,
  c.status,
  c.final_score,
  c.qualified,
  c.meeting_scheduled,
  c.started_at,
  c.updated_at,
  COUNT(m.id)                                       AS message_count,
  COUNT(m.id) FILTER (WHERE m.role = 'user')        AS user_messages,
  COUNT(m.id) FILTER (WHERE m.role = 'bot')         AS bot_messages,
  COALESCE(SUM(m.input_tokens), 0)                  AS total_input_tokens,
  COALESCE(SUM(m.output_tokens), 0)                 AS total_output_tokens,
  COALESCE(SUM(m.cache_read_tokens), 0)             AS total_cache_read_tokens,
  COALESCE(SUM(m.cache_write_tokens), 0)            AS total_cache_write_tokens,
  COALESCE(SUM(m.cost_usd), 0)                      AS total_cost_usd,
  COALESCE(AVG(m.latency_ms)
           FILTER (WHERE m.role = 'bot'), 0)        AS avg_latency_ms_bot
FROM whatsapp_conversations c
LEFT JOIN whatsapp_messages m ON m.conversation_id = c.id
GROUP BY c.id;

-- Vista de uso global del bot por día
CREATE OR REPLACE VIEW bot_usage_daily AS
SELECT
  DATE(m.sent_at)                                   AS day,
  COUNT(DISTINCT m.conversation_id)                 AS conversations,
  COUNT(m.id) FILTER (WHERE m.role = 'user')        AS inbound_messages,
  COUNT(m.id) FILTER (WHERE m.role = 'bot')         AS outbound_messages,
  COALESCE(SUM(m.input_tokens), 0)                  AS total_input_tokens,
  COALESCE(SUM(m.output_tokens), 0)                 AS total_output_tokens,
  COALESCE(SUM(m.cache_read_tokens), 0)             AS total_cache_read,
  COALESCE(SUM(m.cache_write_tokens), 0)            AS total_cache_write,
  COALESCE(SUM(m.cost_usd), 0)                      AS total_cost_usd
FROM whatsapp_messages m
GROUP BY DATE(m.sent_at)
ORDER BY day DESC;

-- Resumen global (all-time)
CREATE OR REPLACE VIEW bot_usage_summary AS
SELECT
  (SELECT COUNT(*) FROM whatsapp_conversations)            AS total_conversations,
  (SELECT COUNT(*) FROM whatsapp_conversations
     WHERE qualified = true)                               AS qualified_conversations,
  (SELECT COUNT(*) FROM whatsapp_conversations
     WHERE meeting_scheduled = true)                       AS meetings_scheduled,
  (SELECT COUNT(*) FROM whatsapp_messages)                 AS total_messages,
  (SELECT COALESCE(SUM(cost_usd), 0)
     FROM whatsapp_messages)                               AS total_cost_usd,
  (SELECT COALESCE(SUM(input_tokens), 0)
     FROM whatsapp_messages)                               AS total_input_tokens,
  (SELECT COALESCE(SUM(output_tokens), 0)
     FROM whatsapp_messages)                               AS total_output_tokens,
  (SELECT COALESCE(SUM(cache_read_tokens), 0)
     FROM whatsapp_messages)                               AS total_cache_read,
  (SELECT COALESCE(SUM(cache_write_tokens), 0)
     FROM whatsapp_messages)                               AS total_cache_write;

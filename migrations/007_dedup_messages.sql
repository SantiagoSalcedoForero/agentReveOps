-- Previene mensajes duplicados por webhook retry de Meta.
-- wa_message_id es único cuando existe (outbound del bot no siempre lo tiene).
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_wa_message_id
    ON whatsapp_messages(wa_message_id)
    WHERE wa_message_id IS NOT NULL;

-- Permite role='agent' en whatsapp_messages para distinguir mensajes
-- del bot vs mensajes de un agente humano desde el CRM.
ALTER TABLE whatsapp_messages DROP CONSTRAINT IF EXISTS whatsapp_messages_role_check;
ALTER TABLE whatsapp_messages ADD CONSTRAINT whatsapp_messages_role_check
    CHECK (role IN ('user', 'bot', 'agent'));

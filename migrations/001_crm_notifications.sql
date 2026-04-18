-- Notificaciones push del CRM (Supabase Realtime las consume)
CREATE TABLE IF NOT EXISTS crm_notifications (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id      UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  type            TEXT NOT NULL,
  title           TEXT NOT NULL,
  body            TEXT,
  metadata        JSONB DEFAULT '{}',
  read            BOOLEAN NOT NULL DEFAULT false,
  read_at         TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notif_profile ON crm_notifications(profile_id);
CREATE INDEX IF NOT EXISTS idx_notif_unread  ON crm_notifications(profile_id, read)
  WHERE read = false;

ALTER TABLE crm_notifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users see own notifications"
  ON crm_notifications FOR SELECT
  USING (profile_id = auth.uid());

CREATE POLICY "Service role inserts notifications"
  ON crm_notifications FOR INSERT
  WITH CHECK (true);

CREATE POLICY "Users update own notifications"
  ON crm_notifications FOR UPDATE
  USING (profile_id = auth.uid());

ALTER PUBLICATION supabase_realtime ADD TABLE crm_notifications;

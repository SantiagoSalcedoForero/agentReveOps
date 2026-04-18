-- CEO Agent: tablas para CTR optimizer, conversaciones y reportes.

CREATE TABLE IF NOT EXISTS ctr_opportunities (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url             TEXT NOT NULL,
  impressions     INTEGER NOT NULL,
  clicks          INTEGER NOT NULL,
  ctr             NUMERIC(6,4) NOT NULL,
  position        NUMERIC(6,2) NOT NULL,
  top_queries     JSONB DEFAULT '[]',
  analysis        JSONB DEFAULT '{}',
  status          TEXT NOT NULL DEFAULT 'pending',
  applied_at      TIMESTAMPTZ,
  measured_at     TIMESTAMPTZ,
  ctr_before      NUMERIC(6,4),
  ctr_after       NUMERIC(6,4),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ceo_conversations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message         TEXT NOT NULL,
  response        TEXT NOT NULL,
  agents_used     TEXT[] DEFAULT '{}',
  data            JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ceo_reports (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  summary         TEXT NOT NULL,
  financial       JSONB DEFAULT '{}',
  commercial      JSONB DEFAULT '{}',
  seo             JSONB DEFAULT '{}',
  action_items    JSONB DEFAULT '[]',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE ctr_opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE ceo_conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ceo_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service role ctr_opportunities" ON ctr_opportunities FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service role ceo_conversations" ON ceo_conversations FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service role ceo_reports" ON ceo_reports FOR ALL USING (true) WITH CHECK (true);

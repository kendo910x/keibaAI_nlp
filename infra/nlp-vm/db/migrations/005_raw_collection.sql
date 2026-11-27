\set ON_ERROR_STOP on
BEGIN;
SELECT CASE current_database() WHEN 'keiba_nlp' THEN 'nlp_app' WHEN 'keiba_nlp_trial' THEN 'nlp_trial_app' END AS writer,
       CASE current_database() WHEN 'keiba_nlp' THEN 'nlp_viewer' WHEN 'keiba_nlp_trial' THEN 'nlp_trial_viewer' END AS viewer \gset
SET LOCAL search_path=collection,pg_catalog;
CREATE TABLE IF NOT EXISTS collection_control (
    singleton boolean PRIMARY KEY CHECK(singleton), all_paused boolean NOT NULL DEFAULT false,
    history_paused boolean NOT NULL DEFAULT false, changed_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO collection_control(singleton) VALUES(true) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS route_waits (
    source text PRIMARY KEY, retry_at timestamptz NOT NULL, reason text NOT NULL
);
ALTER TABLE work_items ADD COLUMN IF NOT EXISTS ready_at timestamptz;
CREATE UNIQUE INDEX IF NOT EXISTS work_queue_key ON work_items(plan_id,(target->>'queue_key')) WHERE target ? 'queue_key';
CREATE INDEX IF NOT EXISTS work_ready ON work_items(plan_id,position) WHERE state IN ('queued','working');
CREATE INDEX IF NOT EXISTS work_ready_follow ON work_items(plan_id,position) WHERE state IN ('queued','working') AND target ? 'queue_key';
CREATE INDEX IF NOT EXISTS listing_daily_front ON observations((data->>'channel'),(data->>'day') DESC)
    WHERE family='listings' AND data->>'head'='true' AND data->>'status'='ok';
CREATE INDEX IF NOT EXISTS work_seed_name ON work_items(plan_id,(target->>'name')) WHERE target->>'type'='horse';
GRANT SELECT,UPDATE ON collection_control TO :"writer";
GRANT SELECT,INSERT,UPDATE ON route_waits TO :"writer";
GRANT SELECT ON collection_control,route_waits TO :"viewer";
COMMIT;

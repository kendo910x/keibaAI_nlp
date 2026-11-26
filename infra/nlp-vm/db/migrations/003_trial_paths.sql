\set ON_ERROR_STOP on
BEGIN;
SELECT CASE current_database() WHEN 'keiba_nlp' THEN 'nlp_app' WHEN 'keiba_nlp_trial' THEN 'nlp_trial_app' END AS writer,
       CASE current_database() WHEN 'keiba_nlp' THEN 'nlp_viewer' WHEN 'keiba_nlp_trial' THEN 'nlp_trial_viewer' END AS viewer \gset
SET LOCAL search_path=collection,pg_catalog;
CREATE TABLE IF NOT EXISTS agent_searches (
    plan_id uuid NOT NULL REFERENCES plans, search_id text NOT NULL, subject text NOT NULL,
    query text NOT NULL, PRIMARY KEY(plan_id,search_id)
);
CREATE OR REPLACE VIEW plan_hits AS
    SELECT w.plan_id,w.position,h->>'capture_id' AS capture_id,
           coalesce((h->>'known')::boolean,h->>'status'='known',false) AS reused
    FROM work_items w CROSS JOIN LATERAL jsonb_array_elements(w.result->'hits') h
    WHERE h ? 'capture_id';
CREATE INDEX IF NOT EXISTS interpret_work_capture ON work_items ((target->>'capture')) WHERE target->>'type'='interpret';
CREATE OR REPLACE VIEW version_progress AS
    SELECT v.id, CASE
        WHEN EXISTS(SELECT FROM interpretations i WHERE i.version_id=v.id AND i.status='ok') THEN 'ok'
        WHEN EXISTS(SELECT FROM captures c JOIN work_items w ON w.target->>'capture'=c.id
            WHERE c.version_id=v.id AND w.target->>'type'='interpret' AND w.state='working') THEN 'working'
        WHEN EXISTS(SELECT FROM interpretations i WHERE i.version_id=v.id AND i.status<>'ok')
          OR EXISTS(SELECT FROM captures c JOIN work_items w ON w.target->>'capture'=c.id
            WHERE c.version_id=v.id AND w.target->>'type'='interpret' AND w.state='failed') THEN 'failed'
        ELSE 'queued' END AS state
    FROM versions v;
GRANT SELECT,INSERT ON agent_searches TO :"writer";
GRANT SELECT ON plan_hits,version_progress TO :"writer",:"viewer";
GRANT SELECT ON agent_searches TO :"viewer";
COMMIT;

-- Prefer the current fixed plan's work state to failures from an earlier pass.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path=collection,pg_catalog;
CREATE INDEX IF NOT EXISTS interpret_work_version ON work_items ((target->>'version'),plan_id)
    WHERE target->>'type'='interpret';
CREATE OR REPLACE VIEW version_progress AS
    SELECT v.id, CASE
        WHEN EXISTS(SELECT FROM interpretations i WHERE i.version_id=v.id AND i.status='ok') THEN 'ok'
        WHEN fixed.state IS NOT NULL THEN CASE fixed.state
            WHEN 'working' THEN 'working' WHEN 'failed' THEN 'failed' ELSE 'queued' END
        WHEN EXISTS(SELECT FROM captures c JOIN work_items w ON w.target->>'capture'=c.id
            WHERE c.version_id=v.id AND w.target->>'type'='interpret' AND w.state='working') THEN 'working'
        WHEN EXISTS(SELECT FROM interpretations i WHERE i.version_id=v.id AND i.status<>'ok')
          OR EXISTS(SELECT FROM captures c JOIN work_items w ON w.target->>'capture'=c.id
            WHERE c.version_id=v.id AND w.target->>'type'='interpret' AND w.state='failed') THEN 'failed'
        ELSE 'queued' END AS state
    FROM versions v LEFT JOIN LATERAL (
        SELECT w.state FROM work_items w JOIN plans p ON p.id=w.plan_id
        WHERE w.target->>'type'='interpret' AND w.target->>'version'=v.id AND p.scope='saved_versions'
        ORDER BY p.created_at DESC LIMIT 1
    ) fixed ON true;
COMMIT;

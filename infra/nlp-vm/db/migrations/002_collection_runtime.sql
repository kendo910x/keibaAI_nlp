BEGIN;
CREATE SCHEMA IF NOT EXISTS collection;
REVOKE ALL ON SCHEMA collection FROM PUBLIC;
SET LOCAL search_path = collection, pg_catalog;
CREATE TABLE IF NOT EXISTS versions (
    id text PRIMARY KEY, url_key text NOT NULL, source_url text NOT NULL, host text NOT NULL,
    title text NOT NULL, body text NOT NULL, date_label text, article_day date,
    observed_at timestamptz NOT NULL, partial boolean NOT NULL, origin text NOT NULL
);
CREATE INDEX IF NOT EXISTS version_article ON versions(url_key,observed_at DESC);
CREATE INDEX IF NOT EXISTS version_day ON versions(article_day DESC);
CREATE TABLE IF NOT EXISTS captures (
    id text PRIMARY KEY, url_key text NOT NULL, requested_key text NOT NULL, version_id text REFERENCES versions,
    source_url text NOT NULL, host text NOT NULL, title text NOT NULL, status text NOT NULL,
    observed_at timestamptz NOT NULL, origin text NOT NULL, evidence jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS capture_url ON captures(url_key,observed_at DESC);
CREATE INDEX IF NOT EXISTS capture_requested ON captures(requested_key) WHERE version_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS capture_version_time ON captures(version_id,observed_at,id) WHERE version_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS interpretations (
    id text PRIMARY KEY, version_id text NOT NULL REFERENCES versions, capture_id text NOT NULL REFERENCES captures,
    status text NOT NULL, observed_at timestamptz NOT NULL, input_key text, skill_hash text,
    items jsonb NOT NULL, evidence jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS interpretation_version ON interpretations(version_id,status);
CREATE INDEX IF NOT EXISTS interpretation_input ON interpretations(input_key) WHERE status='ok';
CREATE TABLE IF NOT EXISTS observations (
    family text NOT NULL, id text NOT NULL, data jsonb NOT NULL, PRIMARY KEY(family,id)
);
CREATE TABLE IF NOT EXISTS plans (
    id uuid PRIMARY KEY, kind text NOT NULL, label text NOT NULL, scope text NOT NULL, state text NOT NULL,
    created_at timestamptz DEFAULT now(), started_at timestamptz, ended_at timestamptz,
    updated_at timestamptz DEFAULT now(), stop_requested boolean DEFAULT false, error text,
    input jsonb NOT NULL, owner text NOT NULL
);
CREATE TABLE IF NOT EXISTS work_items (
    plan_id uuid REFERENCES plans, position int NOT NULL, target jsonb NOT NULL,
    state text NOT NULL DEFAULT 'queued', result jsonb, updated_at timestamptz DEFAULT now(),
    PRIMARY KEY(plan_id,position)
);
CREATE INDEX IF NOT EXISTS work_state ON work_items(plan_id,state,position);
CREATE TABLE IF NOT EXISTS health (
    name text PRIMARY KEY, state text NOT NULL, detail text NOT NULL, checked_at timestamptz NOT NULL
);
GRANT USAGE ON SCHEMA collection TO nlp_app, nlp_viewer;
GRANT CONNECT ON DATABASE keiba_nlp TO nlp_viewer;
GRANT SELECT, INSERT, UPDATE ON versions,captures,interpretations,observations,plans,work_items,health TO nlp_app;
GRANT SELECT ON versions,captures,interpretations,plans,work_items,health TO nlp_viewer;
CREATE OR REPLACE VIEW legacy_articles AS
    SELECT article_id,title,media,published_text,source_url,body,body_kind,collected_at FROM public.articles;
CREATE OR REPLACE VIEW roster_sizes AS
    SELECT id,jsonb_array_length(data->'horses') AS horses FROM observations WHERE family='rosters';
CREATE OR REPLACE VIEW source_relations AS
    SELECT data->'record' AS relation FROM observations WHERE family='reference' AND id LIKE '%relations.json';
GRANT SELECT ON legacy_articles,roster_sizes,source_relations TO nlp_viewer;
COMMIT;

\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path = public, pg_catalog;
SELECT pg_advisory_xact_lock(20621124, 2);
SELECT current_database() IN ('keiba_nlp', 'keiba_nlp_stage2b_test') AS intended_db \gset
\if :intended_db
\else
DO $$ BEGIN RAISE EXCEPTION 'unexpected target database'; END $$;
\endif

SELECT to_regclass('public.articles') IS NULL AS initialize \gset
\if :initialize
CREATE EXTENSION vector WITH SCHEMA public;

CREATE TABLE collection_runs (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task jsonb NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','paused','completed','failed')),
    progress jsonb NOT NULL DEFAULT '{}',
    started_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    last_error text
);

CREATE TABLE articles (
    article_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url text NOT NULL CHECK (source_url <> ''),
    url_sha256 bytea NOT NULL CHECK (url_sha256 = sha256(convert_to(source_url, 'UTF8'))),
    media text,
    title text,
    published_text text,
    body text,
    body_kind text NOT NULL CHECK (body_kind IN ('full','excerpt','snippet','none')),
    body_sha256 bytea,
    collected_at timestamptz NOT NULL DEFAULT now(),
    run_id uuid REFERENCES collection_runs,
    CHECK ((body_kind = 'none' AND body IS NULL AND body_sha256 IS NULL) OR
           (body_kind <> 'none' AND body IS NOT NULL AND body <> '' AND body_sha256 IS NOT NULL
            AND body_sha256 = sha256(convert_to(body, 'UTF8')))),
    UNIQUE NULLS NOT DISTINCT (url_sha256, body_kind, body_sha256)
);

CREATE TABLE horses (
    horse_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    horse_name text NOT NULL,
    normalized_name text GENERATED ALWAYS AS (
        translate(normalize(horse_name, NFKC),
                  U&'\0009\000A\000B\000C\000D\0020\0085\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000','')
    ) STORED NOT NULL,
    birth_year smallint
);
CREATE INDEX horses_normalized_name_idx ON horses (normalized_name);

CREATE TABLE races (
    race_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    race_name text,
    race_date date,
    domain_id text,
    race_key text CHECK (race_key ~ '^[0-9]{8}/[0-9]{2}/[0-9]{2}$')
);
CREATE UNIQUE INDEX races_domain_key_uidx ON races (domain_id, race_key)
    WHERE domain_id IS NOT NULL AND race_key IS NOT NULL;
CREATE INDEX races_name_date_idx ON races (race_name, race_date);

CREATE TABLE text_units (
    unit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id uuid NOT NULL REFERENCES articles,
    start_char integer NOT NULL CHECK (start_char >= 0),
    end_char integer NOT NULL CHECK (end_char > start_char),
    UNIQUE (article_id, start_char, end_char)
);

CREATE FUNCTION check_text_unit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT FROM public.articles a WHERE a.article_id = NEW.article_id
                   AND NEW.end_char <= char_length(a.body)) THEN
        RAISE EXCEPTION 'unit exceeds article body or has no body' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER check_text_unit BEFORE INSERT OR UPDATE ON text_units
    FOR EACH ROW EXECUTE FUNCTION check_text_unit();

CREATE FUNCTION add_full_text_unit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO public.text_units (article_id, start_char, end_char)
    VALUES (NEW.article_id, 0, char_length(NEW.body));
    RETURN NEW;
END $$;
CREATE TRIGGER add_full_text_unit AFTER INSERT ON articles
    FOR EACH ROW WHEN (NEW.body IS NOT NULL) EXECUTE FUNCTION add_full_text_unit();

CREATE TABLE unit_targets (
    target_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    unit_id uuid NOT NULL REFERENCES text_units,
    horse_id uuid REFERENCES horses,
    race_id uuid REFERENCES races,
    horse_label text,
    race_label text,
    phase text NOT NULL DEFAULT 'unknown' CHECK (phase IN ('pre','post','mixed','unknown')),
    CHECK (horse_id IS NULL OR horse_label IS NULL),
    CHECK (race_id IS NULL OR race_label IS NULL),
    UNIQUE NULLS NOT DISTINCT (unit_id, horse_id, race_id, horse_label, race_label)
);
CREATE INDEX targets_horse_phase_unit_idx ON unit_targets (horse_id, phase, unit_id);
CREATE INDEX targets_race_phase_unit_idx ON unit_targets (race_id, phase, unit_id);
CREATE INDEX targets_race_horse_phase_unit_idx ON unit_targets (race_id, horse_id, phase, unit_id);

CREATE TABLE embedding_configs (
    embedding_config_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name text NOT NULL,
    model_revision text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions BETWEEN 1 AND 16000),
    settings jsonb NOT NULL,
    config_sha256 bytea NOT NULL UNIQUE CHECK (octet_length(config_sha256) = 32)
);

CREATE TABLE embeddings (
    unit_id uuid NOT NULL REFERENCES text_units,
    embedding_config_id uuid NOT NULL REFERENCES embedding_configs,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    start_char integer NOT NULL CHECK (start_char >= 0),
    end_char integer NOT NULL CHECK (end_char > start_char),
    embedding vector NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (unit_id, embedding_config_id, chunk_index)
);
CREATE INDEX embeddings_config_unit_idx ON embeddings (embedding_config_id, unit_id);

CREATE FUNCTION check_embedding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT FROM public.text_units u WHERE u.unit_id = NEW.unit_id
                   AND NEW.end_char <= u.end_char - u.start_char) THEN
        RAISE EXCEPTION 'chunk exceeds unit length' USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (SELECT FROM public.embedding_configs c
                   WHERE c.embedding_config_id = NEW.embedding_config_id
                     AND c.dimensions = public.vector_dims(NEW.embedding)) THEN
        RAISE EXCEPTION 'vector dimension does not match config' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER check_embedding BEFORE INSERT OR UPDATE ON embeddings
    FOR EACH ROW EXECUTE FUNCTION check_embedding();

SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO nlp_app', current_database()) \gexec
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO nlp_app;
GRANT SELECT, INSERT ON collection_runs, articles, horses, races, text_units, unit_targets,
                        embedding_configs, embeddings TO nlp_app;
GRANT UPDATE (task,status,progress,started_at,updated_at,finished_at,last_error) ON collection_runs TO nlp_app;
GRANT UPDATE (media,title,published_text) ON articles TO nlp_app;
GRANT UPDATE (horse_name,birth_year) ON horses TO nlp_app;
GRANT UPDATE (race_name,race_date,domain_id,race_key) ON races TO nlp_app;
GRANT UPDATE (horse_id,race_id,horse_label,race_label,phase), DELETE ON unit_targets TO nlp_app;
\endif

\ir catalog_fingerprint.sql
SELECT :'actual_fingerprint' = '2a303dd483dd85e517a71b60870e7d06b1151da55f39b44b629aafb38a863b3e' AS ddl_matches \gset
\if :ddl_matches
\echo schema verified :actual_fingerprint
COMMIT;
\else
\echo unexpected schema fingerprint :actual_fingerprint
DO $$ BEGIN RAISE EXCEPTION 'DDL/extension/grants differ from the pinned schema'; END $$;
\endif

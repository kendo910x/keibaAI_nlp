-- Read only. UTC and hex bytea output keep timestamps and hashes comparable across sessions.
WITH names(name) AS (VALUES ('collection_runs'),('articles'),('horses'),('races'),('text_units'),
                            ('unit_targets'),('embedding_configs'),('embeddings')),
rows(name, record) AS (
    SELECT 'collection_runs',to_jsonb(r)::text FROM collection_runs r UNION ALL
    SELECT 'articles',to_jsonb(r)::text FROM articles r UNION ALL
    SELECT 'horses',to_jsonb(r)::text FROM horses r UNION ALL
    SELECT 'races',to_jsonb(r)::text FROM races r UNION ALL
    SELECT 'text_units',to_jsonb(r)::text FROM text_units r UNION ALL
    SELECT 'unit_targets',to_jsonb(r)::text FROM unit_targets r UNION ALL
    SELECT 'embedding_configs',to_jsonb(r)::text FROM embedding_configs r UNION ALL
    SELECT 'embeddings',to_jsonb(r)::text FROM embeddings r
), per_table AS (
    SELECT name, count(record) AS n,
           encode(sha256(convert_to(coalesce(string_agg(record,E'\n' ORDER BY record COLLATE "C"),''),'UTF8')),'hex') AS sha
    FROM names LEFT JOIN rows USING(name) GROUP BY name
)
SELECT name,n,sha FROM per_table UNION ALL
SELECT '*',sum(n),encode(sha256(convert_to(string_agg(name||':'||n||':'||sha,E'\n' ORDER BY name COLLATE "C"),
                                          'UTF8')),'hex') FROM per_table ORDER BY 1;

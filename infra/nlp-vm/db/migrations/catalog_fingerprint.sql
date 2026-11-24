-- Run with search_path public,pg_catalog. Use names and definitions, never OIDs or row contents.
WITH rel AS (
    SELECT * FROM pg_class WHERE relnamespace = 'public'::regnamespace
), pieces(item) AS (
    SELECT jsonb_build_array('extension', extname, extversion, extnamespace::regnamespace::text)
      FROM pg_extension
    UNION ALL
    SELECT jsonb_build_array('database', pg_get_userbyid(datdba), datacl::text)
      FROM pg_database WHERE datname = current_database()
    UNION ALL
    SELECT jsonb_build_array('schema', pg_get_userbyid(nspowner), nspacl::text)
      FROM pg_namespace WHERE nspname = 'public'
    UNION ALL
    SELECT jsonb_build_array('app_role', rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                             rolreplication, rolbypassrls)
      FROM pg_roles WHERE rolname = 'nlp_app'
    UNION ALL
    SELECT jsonb_build_array('membership', parent.rolname)
      FROM pg_auth_members m JOIN pg_roles parent ON parent.oid = m.roleid
      WHERE m.member = 'nlp_app'::regrole
    UNION ALL
    SELECT jsonb_build_array('relation', relname, relkind, pg_get_userbyid(relowner),
                             relacl::text, relrowsecurity, relpersistence) FROM rel
    UNION ALL
    SELECT jsonb_build_array('column', r.relname, a.attnum, a.attname, format_type(a.atttypid,a.atttypmod),
                             a.attnotnull, a.attgenerated, a.attidentity, a.attacl::text,
                             pg_get_expr(d.adbin,d.adrelid))
      FROM rel r JOIN pg_attribute a ON a.attrelid = r.oid
      LEFT JOIN pg_attrdef d ON (d.adrelid,d.adnum) = (a.attrelid,a.attnum)
      WHERE r.relkind IN ('r','p','v','m','f') AND a.attnum > 0 AND NOT a.attisdropped
    UNION ALL
    SELECT jsonb_build_array('constraint', r.relname, c.conname, pg_get_constraintdef(c.oid), c.convalidated)
      FROM rel r JOIN pg_constraint c ON c.conrelid = r.oid
    UNION ALL
    SELECT jsonb_build_array('index', pg_get_indexdef(i.indexrelid), i.indisvalid, i.indisready)
      FROM pg_index i JOIN rel r ON r.oid = i.indrelid
    UNION ALL
    SELECT jsonb_build_array('trigger', pg_get_triggerdef(t.oid), t.tgenabled)
      FROM pg_trigger t JOIN rel r ON r.oid = t.tgrelid WHERE NOT t.tgisinternal
    UNION ALL
    SELECT jsonb_build_array('function', pg_get_functiondef(p.oid), pg_get_userbyid(p.proowner), p.proacl::text)
      FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace
        AND NOT EXISTS (SELECT FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass
                        AND d.objid = p.oid AND d.deptype = 'e')
)
SELECT encode(sha256(convert_to(string_agg(item::text, E'\n' ORDER BY item::text COLLATE "C"), 'UTF8')),
              'hex') AS actual_fingerprint FROM pieces \gset

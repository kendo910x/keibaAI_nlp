-- Executed inside one transaction, after the original body and its full unit have committed.
DO $test$
DECLARE
    a uuid; u uuid; v uuid; h1 uuid; h2 uuid; r1 uuid; r2 uuid; obsolete uuid;
    article_count int; unit_count int; target_count int;
BEGIN
    IF (current_database(),current_user) <> ('keiba_nlp_stage2b_test','nlp_app') THEN
        RAISE EXCEPTION 'requires dedicated test database and app role';
    END IF;
    SELECT article_id INTO STRICT a FROM articles WHERE title = '合成・主資料';
    INSERT INTO text_units(article_id,start_char,end_char) VALUES (a,0,5) RETURNING unit_id INTO u;
    INSERT INTO text_units(article_id,start_char,end_char) VALUES (a,5,8) RETURNING unit_id INTO v;
    INSERT INTO text_units(article_id,start_char,end_char) VALUES (a,0,5) ON CONFLICT DO NOTHING;
    ASSERT (SELECT count(*) = 3 FROM text_units WHERE article_id = a);
    ASSERT (SELECT substring(body FROM t.start_char+1 FOR t.end_char-t.start_char) = U&'甲🐎e\0301乙'
            FROM articles JOIN text_units t USING(article_id) WHERE t.unit_id = u);

    INSERT INTO horses(horse_name,birth_year) VALUES (U&'架空\0085　Ａー号',2001) RETURNING horse_id INTO h1;
    INSERT INTO horses(horse_name,birth_year) VALUES ('架空Aー号',2002) RETURNING horse_id INTO h2;
    ASSERT h1 <> h2 AND (SELECT count(*) = 2 FROM horses WHERE normalized_name='架空Aー号');
    INSERT INTO races(race_name,domain_id,race_key)
    VALUES ('架空杯','fixture','20000101/01/01') RETURNING race_id INTO r1;
    INSERT INTO races(race_name) VALUES ('架空杯') RETURNING race_id INTO r2;
    ASSERT (SELECT race_id = r1 FROM races WHERE domain_id='fixture' AND race_key='20000101/01/01');

    INSERT INTO unit_targets(unit_id,horse_id,race_id,phase) VALUES
        (u,h1,r1,'pre'), (v,h2,r2,'post'), (v,h1,r1,'post'),
        (u,NULL,r1,'mixed'), (v,NULL,r1,'unknown'), (u,h1,NULL,'unknown');
    INSERT INTO unit_targets(unit_id,horse_label,race_label) VALUES (v,'仮の馬','未同定の競走');
    INSERT INTO unit_targets(unit_id,horse_label,race_id) VALUES (u,'解決予定',r1) RETURNING target_id INTO obsolete;
    -- The resolved row already exists. Merge and remove exactly the obsolete label in this transaction.
    INSERT INTO unit_targets(unit_id,horse_id,race_id,phase) VALUES (u,h1,r1,'pre')
    ON CONFLICT (unit_id,horse_id,race_id,horse_label,race_label) DO UPDATE SET phase=EXCLUDED.phase;
    DELETE FROM unit_targets WHERE target_id=obsolete AND horse_id IS NULL AND horse_label='解決予定';
    ASSERT NOT EXISTS (SELECT FROM unit_targets WHERE horse_label='解決予定');
    ASSERT (SELECT count(*)=7 AND count(DISTINCT phase)=4 FROM unit_targets);
    ASSERT (SELECT count(*)=1 FROM unit_targets WHERE horse_id=h1 AND race_id IS NULL);
    ASSERT (SELECT count(*)=2 FROM unit_targets WHERE horse_id IS NULL AND race_id=r1);
    ASSERT (SELECT count(*)=1 FROM unit_targets WHERE horse_id IS NULL AND race_id IS NULL
            AND horse_label='仮の馬' AND race_label='未同定の競走');
    ASSERT NOT EXISTS (SELECT FROM unit_targets WHERE (horse_id=h1 AND race_id=r2) OR (horse_id=h2 AND race_id=r1));
    ASSERT (SELECT count(*)=1 FROM unit_targets WHERE horse_id=h2);
    ASSERT (SELECT count(*)=2 FROM unit_targets WHERE horse_id=h1 AND race_id=r1);
    SELECT count(DISTINCT article_id), count(DISTINCT unit_id), count(*) INTO article_count,unit_count,target_count
      FROM unit_targets JOIN text_units USING(unit_id) JOIN articles USING(article_id) WHERE race_id=r1;
    ASSERT (article_count,unit_count,target_count)=(1,2,4);
    ASSERT (SELECT array_agg(t.unit_id)=ARRAY[u] FROM unit_targets t JOIN text_units USING(unit_id)
            JOIN articles USING(article_id) WHERE t.race_id=r1 AND t.phase='pre' AND published_text IS NULL);
    ASSERT (SELECT count(*)=0 FROM embeddings);
END $test$;

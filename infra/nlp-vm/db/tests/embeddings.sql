DO $test$
DECLARE
    u uuid; c3 uuid; c4 uuid; num int;
BEGIN
    IF (current_database(),current_user) <> ('keiba_nlp_stage2b_test','nlp_app') THEN
        RAISE EXCEPTION 'requires dedicated test database and app role';
    END IF;
    SELECT unit_id INTO STRICT u FROM text_units JOIN articles USING(article_id)
      WHERE title='合成・主資料' AND start_char=0 AND end_char=5;
    SELECT embedding_config_id INTO STRICT c3 FROM embedding_configs WHERE dimensions=3;
    SELECT embedding_config_id INTO STRICT c4 FROM embedding_configs WHERE dimensions=4;
    ASSERT (SELECT count(*)=0 FROM embeddings);
    ASSERT EXISTS (SELECT FROM text_units t WHERE NOT EXISTS (SELECT FROM unit_targets WHERE unit_id=t.unit_id)
                   AND NOT EXISTS (SELECT FROM embeddings WHERE unit_id=t.unit_id AND embedding_config_id=c3));

    -- An invalid second chunk rolls back the first chunk in the same subtransaction.
    BEGIN
        INSERT INTO embeddings(unit_id,embedding_config_id,chunk_index,start_char,end_char,embedding)
        VALUES (u,c3,0,0,2,array_fill(2.0::real,ARRAY[3])::vector);
        INSERT INTO embeddings(unit_id,embedding_config_id,chunk_index,start_char,end_char,embedding)
        VALUES (u,c3,1,2,5,array_fill(2.0::real,ARRAY[4])::vector);
        RAISE EXCEPTION 'wrong dimension accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    ASSERT NOT EXISTS (SELECT FROM embeddings WHERE unit_id=u AND embedding_config_id=c3);

    INSERT INTO embeddings(unit_id,embedding_config_id,chunk_index,start_char,end_char,embedding)
    VALUES (u,c3,0,0,2,array_fill(2.0::real,ARRAY[3])::vector),
           (u,c3,1,2,5,array_fill(3.0::real,ARRAY[3])::vector),
           (u,c4,0,0,5,array_fill(4.0::real,ARRAY[4])::vector);
    INSERT INTO embeddings(unit_id,embedding_config_id,chunk_index,start_char,end_char,embedding)
      SELECT u,c3,0,0,5,array_fill(1.0::real,ARRAY[3])::vector
      WHERE NOT EXISTS (SELECT FROM embeddings WHERE unit_id=u AND embedding_config_id=c3);
    GET DIAGNOSTICS num=ROW_COUNT;
    ASSERT num=0;
    BEGIN
        INSERT INTO embeddings(unit_id,embedding_config_id,chunk_index,start_char,end_char,embedding)
        VALUES (u,c3,1,2,5,array_fill(3.0::real,ARRAY[3])::vector);
        RAISE EXCEPTION 'duplicate chunk accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO embeddings(unit_id,embedding_config_id,chunk_index,start_char,end_char,embedding)
        VALUES (u,c3,2,4,6,array_fill(3.0::real,ARRAY[3])::vector);
        RAISE EXCEPTION 'invalid chunk range accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        PERFORM array_fill('NaN'::real,ARRAY[3])::vector;
        RAISE EXCEPTION 'NaN accepted';
    EXCEPTION WHEN data_exception THEN NULL;
    END;
    BEGIN
        PERFORM array_fill('Infinity'::real,ARRAY[3])::vector;
        RAISE EXCEPTION 'Infinity accepted';
    EXCEPTION WHEN data_exception THEN NULL;
    END;
    ASSERT (SELECT count(*)=2 AND array_agg(vector_dims(e.embedding) ORDER BY e.chunk_index)=ARRAY[3,3]
            AND array_agg(substring(a.body FROM t.start_char+e.start_char+1 FOR e.end_char-e.start_char)
                          ORDER BY e.chunk_index)=ARRAY['甲🐎',U&'e\0301乙']
            FROM unit_targets x JOIN text_units t USING(unit_id) JOIN articles a USING(article_id)
            JOIN embeddings e USING(unit_id) JOIN embedding_configs c USING(embedding_config_id)
            WHERE x.race_id IS NOT NULL AND x.horse_id IS NOT NULL AND x.phase='pre'
              AND c.embedding_config_id=c3);
    ASSERT (SELECT count(*)=1 AND min(vector_dims(embedding))=4 FROM embeddings WHERE embedding_config_id=c4);
    ASSERT (SELECT count(*)=2 AND count(DISTINCT t.unit_id)=1 AND count(e.chunk_index)=0
            FROM unit_targets x JOIN text_units t USING(unit_id)
            JOIN articles a USING(article_id) LEFT JOIN embeddings e ON e.unit_id=t.unit_id AND e.embedding_config_id=c3
            WHERE x.horse_id IS NOT NULL AND x.race_id IS NOT NULL AND x.phase='post'
            AND a.title='合成・主資料');
END $test$;

MERGE INTO sentinelpay.feature_updates_iceberg AS t
USING (
    SELECT data_classification, schema_version, feature_event_id, entity_type,
           CASE WHEN batch_id IN ('validation-1500-seed17-20260601', 'test-1500-seed29-20260901')
                THEN concat('atok_', batch_id, '_', substr(entity_token, 6))
                ELSE entity_token END AS entity_token,
           feature_version, window_start, window_end, window_seconds, transaction_count,
           amount_sum, currency, distinct_merchant_count, new_device_count,
           computed_at, source_region, ingest_date, batch_id
    FROM (
        SELECT b.*,
               row_number() OVER (
                   PARTITION BY feature_event_id
                   ORDER BY computed_at, ingest_date, batch_id
               ) AS delivery_rank
        FROM sentinelpay.feature_updates_bronze b
        WHERE data_classification = 'SYNTHETIC'
          AND schema_version = 1
          AND feature_event_id IS NOT NULL
    ) ranked
    WHERE delivery_rank = 1
) AS s
ON t.feature_event_id = s.feature_event_id
WHEN MATCHED THEN UPDATE SET
    data_classification = s.data_classification,
    schema_version = s.schema_version,
    entity_type = s.entity_type,
    entity_token = s.entity_token,
    feature_version = s.feature_version,
    window_start = s.window_start,
    window_end = s.window_end,
    window_seconds = s.window_seconds,
    transaction_count = s.transaction_count,
    amount_sum = s.amount_sum,
    currency = s.currency,
    distinct_merchant_count = s.distinct_merchant_count,
    new_device_count = s.new_device_count,
    computed_at = s.computed_at,
    source_region = s.source_region,
    ingest_date = s.ingest_date,
    batch_id = s.batch_id
WHEN NOT MATCHED THEN INSERT (
    data_classification, schema_version, feature_event_id, entity_type, entity_token,
    feature_version, window_start, window_end, window_seconds, transaction_count,
    amount_sum, currency, distinct_merchant_count, new_device_count, computed_at,
    source_region, ingest_date, batch_id
) VALUES (
    s.data_classification, s.schema_version, s.feature_event_id, s.entity_type, s.entity_token,
    s.feature_version, s.window_start, s.window_end, s.window_seconds, s.transaction_count,
    s.amount_sum, s.currency, s.distinct_merchant_count, s.new_device_count, s.computed_at,
    s.source_region, s.ingest_date, s.batch_id
);

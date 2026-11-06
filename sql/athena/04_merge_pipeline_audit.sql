MERGE INTO sentinelpay.pipeline_audit AS t
USING (
    SELECT ingest_date,
           batch_id,
           event_type,
           record_count AS bronze_record_count,
           unique_ids AS unique_business_ids,
           record_count - unique_ids AS duplicate_delivery_count,
           CASE
               WHEN unique_ids = 0 THEN 'FAIL'
               WHEN record_count > unique_ids THEN 'PASS_WITH_DEDUP'
               ELSE 'PASS'
           END AS reconciliation_status,
           CAST(current_timestamp AS varchar) AS evaluated_at
    FROM (
        SELECT ingest_date, batch_id, 'payments' AS event_type,
               count(*) AS record_count, count(DISTINCT event_id) AS unique_ids
        FROM sentinelpay.payments_bronze
        GROUP BY ingest_date, batch_id

        UNION ALL

        SELECT ingest_date, batch_id, 'feature_updates',
               count(*), count(DISTINCT feature_event_id)
        FROM sentinelpay.feature_updates_bronze
        GROUP BY ingest_date, batch_id

        UNION ALL

        SELECT ingest_date, batch_id, 'fraud_decisions',
               count(*), count(DISTINCT decision_id)
        FROM sentinelpay.fraud_decisions_bronze
        GROUP BY ingest_date, batch_id

        UNION ALL

        SELECT ingest_date, batch_id, 'chargeback_outcomes',
               count(*), count(DISTINCT outcome_event_id)
        FROM sentinelpay.chargeback_outcomes_bronze
        GROUP BY ingest_date, batch_id
    ) batch_counts
) AS s
ON t.ingest_date = s.ingest_date
AND t.batch_id = s.batch_id
AND t.event_type = s.event_type
WHEN MATCHED THEN UPDATE SET
    bronze_record_count = s.bronze_record_count,
    unique_business_ids = s.unique_business_ids,
    duplicate_delivery_count = s.duplicate_delivery_count,
    reconciliation_status = s.reconciliation_status,
    evaluated_at = s.evaluated_at
WHEN NOT MATCHED THEN INSERT (
    ingest_date, batch_id, event_type, bronze_record_count,
    unique_business_ids, duplicate_delivery_count,
    reconciliation_status, evaluated_at
) VALUES (
    s.ingest_date, s.batch_id, s.event_type, s.bronze_record_count,
    s.unique_business_ids, s.duplicate_delivery_count,
    s.reconciliation_status, s.evaluated_at
);

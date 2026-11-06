MERGE INTO sentinelpay.chargeback_outcomes_iceberg AS t
USING (
    SELECT data_classification, schema_version, outcome_event_id,
           CASE WHEN batch_id IN ('validation-1500-seed17-20260601', 'test-1500-seed29-20260901')
                THEN concat('pay_', batch_id, '_', substr(payment_id, 5))
                ELSE payment_id END AS payment_id,
           outcome, outcome_source, payment_event_time, label_observed_at,
           source_region, trace_id, ingest_date, batch_id
    FROM (
        SELECT b.*,
               row_number() OVER (
                   PARTITION BY outcome_event_id
                   ORDER BY label_observed_at, ingest_date, batch_id
               ) AS delivery_rank
        FROM sentinelpay.chargeback_outcomes_bronze b
        WHERE data_classification = 'SYNTHETIC'
          AND schema_version = 1
          AND outcome_event_id IS NOT NULL
    ) ranked
    WHERE delivery_rank = 1
) AS s
ON t.outcome_event_id = s.outcome_event_id
WHEN MATCHED THEN UPDATE SET
    data_classification = s.data_classification,
    schema_version = s.schema_version,
    payment_id = s.payment_id,
    outcome = s.outcome,
    outcome_source = s.outcome_source,
    payment_event_time = s.payment_event_time,
    label_observed_at = s.label_observed_at,
    source_region = s.source_region,
    trace_id = s.trace_id,
    ingest_date = s.ingest_date,
    batch_id = s.batch_id
WHEN NOT MATCHED THEN INSERT (
    data_classification, schema_version, outcome_event_id, payment_id, outcome,
    outcome_source, payment_event_time, label_observed_at, source_region, trace_id,
    ingest_date, batch_id
) VALUES (
    s.data_classification, s.schema_version, s.outcome_event_id, s.payment_id, s.outcome,
    s.outcome_source, s.payment_event_time, s.label_observed_at, s.source_region, s.trace_id,
    s.ingest_date, s.batch_id
);

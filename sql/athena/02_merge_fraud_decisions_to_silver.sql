MERGE INTO sentinelpay.fraud_decisions_iceberg AS t
USING (
    SELECT data_classification, schema_version, decision_id, event_id,
           CASE WHEN batch_id IN ('validation-1500-seed17-20260601', 'test-1500-seed29-20260901')
                THEN concat('pay_', batch_id, '_', substr(payment_id, 5))
                ELSE payment_id END AS payment_id,
           decision, risk_score, reason_codes, model_id, model_version,
           policy_version, feature_age_ms, fallback_used, decision_time,
           source_region, trace_id, ingest_date, batch_id
    FROM (
        SELECT b.*,
               row_number() OVER (
                   PARTITION BY decision_id
                   ORDER BY decision_time, ingest_date, batch_id
               ) AS delivery_rank
        FROM sentinelpay.fraud_decisions_bronze b
        WHERE data_classification = 'SYNTHETIC'
          AND schema_version = 1
          AND decision_id IS NOT NULL
    ) ranked
    WHERE delivery_rank = 1
) AS s
ON t.decision_id = s.decision_id
WHEN MATCHED THEN UPDATE SET
    data_classification = s.data_classification,
    schema_version = s.schema_version,
    event_id = s.event_id,
    payment_id = s.payment_id,
    decision = s.decision,
    risk_score = s.risk_score,
    reason_codes = s.reason_codes,
    model_id = s.model_id,
    model_version = s.model_version,
    policy_version = s.policy_version,
    feature_age_ms = s.feature_age_ms,
    fallback_used = s.fallback_used,
    decision_time = s.decision_time,
    source_region = s.source_region,
    trace_id = s.trace_id,
    ingest_date = s.ingest_date,
    batch_id = s.batch_id
WHEN NOT MATCHED THEN INSERT (
    data_classification, schema_version, decision_id, event_id, payment_id,
    decision, risk_score, reason_codes, model_id, model_version, policy_version,
    feature_age_ms, fallback_used, decision_time, source_region, trace_id, ingest_date, batch_id
) VALUES (
    s.data_classification, s.schema_version, s.decision_id, s.event_id, s.payment_id,
    s.decision, s.risk_score, s.reason_codes, s.model_id, s.model_version, s.policy_version,
    s.feature_age_ms, s.fallback_used, s.decision_time, s.source_region, s.trace_id, s.ingest_date, s.batch_id
);

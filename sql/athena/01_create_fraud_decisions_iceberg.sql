CREATE TABLE IF NOT EXISTS sentinelpay.fraud_decisions_iceberg (
    data_classification string,
    schema_version int,
    decision_id string,
    event_id string,
    payment_id string,
    decision string,
    risk_score double,
    reason_codes array<string>,
    model_id string,
    model_version string,
    policy_version string,
    feature_age_ms bigint,
    fallback_used boolean,
    decision_time string,
    source_region string,
    trace_id string,
    ingest_date string,
    batch_id string
)
LOCATION 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/silver/fraud_decisions_iceberg/'
TBLPROPERTIES ('table_type' = 'ICEBERG', 'format' = 'PARQUET');

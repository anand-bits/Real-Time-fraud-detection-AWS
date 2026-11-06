CREATE TABLE IF NOT EXISTS sentinelpay.chargeback_outcomes_iceberg (
    data_classification string,
    schema_version int,
    outcome_event_id string,
    payment_id string,
    outcome string,
    outcome_source string,
    payment_event_time string,
    label_observed_at string,
    source_region string,
    trace_id string,
    ingest_date string,
    batch_id string
)
LOCATION 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/silver/chargeback_outcomes_iceberg/'
TBLPROPERTIES ('table_type' = 'ICEBERG', 'format' = 'PARQUET');

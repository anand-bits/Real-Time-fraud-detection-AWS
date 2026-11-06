CREATE TABLE IF NOT EXISTS sentinelpay.pipeline_audit (
    ingest_date string,
    batch_id string,
    event_type string,
    bronze_record_count bigint,
    unique_business_ids bigint,
    duplicate_delivery_count bigint,
    reconciliation_status string,
    evaluated_at string
)
LOCATION 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/ops/pipeline_audit/'
TBLPROPERTIES ('table_type' = 'ICEBERG', 'format' = 'PARQUET');

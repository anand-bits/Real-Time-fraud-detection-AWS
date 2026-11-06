CREATE TABLE IF NOT EXISTS sentinelpay.feature_updates_iceberg (
    data_classification string,
    schema_version int,
    feature_event_id string,
    entity_type string,
    entity_token string,
    feature_version int,
    window_start string,
    window_end string,
    window_seconds int,
    transaction_count int,
    amount_sum double,
    currency string,
    distinct_merchant_count int,
    new_device_count int,
    computed_at string,
    source_region string,
    ingest_date string,
    batch_id string
)
LOCATION 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/silver/feature_updates_iceberg/'
TBLPROPERTIES ('table_type' = 'ICEBERG', 'format' = 'PARQUET');

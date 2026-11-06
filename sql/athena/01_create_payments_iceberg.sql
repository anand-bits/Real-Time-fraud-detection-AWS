CREATE TABLE IF NOT EXISTS sentinelpay.payments_iceberg (
    data_classification string,
    schema_version int,
    event_id string,
    payment_id string,
    idempotency_key string,
    event_time string,
    received_at string,
    payment_token string,
    account_token string,
    merchant_id string,
    device_token string,
    amount double,
    currency string,
    channel string,
    country_code string,
    device_first_seen_days int,
    source_region string,
    trace_id string,
    ingest_date string,
    batch_id string
)
LOCATION 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/silver/payments_iceberg/'
TBLPROPERTIES ('table_type' = 'ICEBERG', 'format' = 'PARQUET');

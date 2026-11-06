CREATE EXTERNAL TABLE IF NOT EXISTS sentinelpay.payments_bronze (
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
    trace_id string
)
PARTITIONED BY (ingest_date string, batch_id string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES ('ignore.malformed.json' = 'true')
STORED AS TEXTFILE
LOCATION 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/raw/payments/'
TBLPROPERTIES ('classification' = 'json');

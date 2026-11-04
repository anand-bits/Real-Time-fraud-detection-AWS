CREATE EXTERNAL TABLE IF NOT EXISTS sentinelpay.feature_updates_bronze (
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
    source_region string
)
PARTITIONED BY (ingest_date string, batch_id string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES ('ignore.malformed.json' = 'true')
STORED AS TEXTFILE
LOCATION 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/raw/feature_updates/'
TBLPROPERTIES ('classification' = 'json');

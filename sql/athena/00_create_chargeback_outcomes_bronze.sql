CREATE EXTERNAL TABLE IF NOT EXISTS sentinelpay.chargeback_outcomes_bronze (
    data_classification string,
    schema_version int,
    outcome_event_id string,
    payment_id string,
    outcome string,
    outcome_source string,
    payment_event_time string,
    label_observed_at string,
    source_region string,
    trace_id string
)
PARTITIONED BY (ingest_date string, batch_id string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES ('ignore.malformed.json' = 'true')
STORED AS TEXTFILE
LOCATION 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/raw/chargeback_outcomes/'
TBLPROPERTIES ('classification' = 'json');

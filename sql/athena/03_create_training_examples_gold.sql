CREATE TABLE IF NOT EXISTS sentinelpay.training_examples_gold (
    data_classification string,
    dataset_version string,
    payment_id string,
    event_id string,
    event_date date,
    event_time string,
    received_at string,
    amount double,
    currency string,
    channel string,
    country_code string,
    device_first_seen_days int,
    transaction_count_1h int,
    amount_sum_1h double,
    distinct_merchant_count_1h int,
    new_device_count_1h int,
    feature_computed_at string,
    label string,
    label_fraud int,
    label_observed_at string,
    label_delay_days int,
    dataset_split string
)
LOCATION 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/gold/training_examples/'
TBLPROPERTIES ('table_type' = 'ICEBERG', 'format' = 'PARQUET');

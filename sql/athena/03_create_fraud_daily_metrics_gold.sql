CREATE TABLE IF NOT EXISTS sentinelpay.fraud_daily_metrics_gold (
    event_date date,
    dataset_split string,
    currency string,
    payment_count bigint,
    confirmed_fraud_count bigint,
    no_fraud_count bigint,
    fraud_rate double,
    total_amount double,
    average_amount double
)
LOCATION 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/gold/fraud_daily_metrics/'
TBLPROPERTIES ('table_type' = 'ICEBERG', 'format' = 'PARQUET');

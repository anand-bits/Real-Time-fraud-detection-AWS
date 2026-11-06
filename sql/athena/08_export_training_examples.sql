-- Replace the example export_id with a fresh value each run.
-- UNLOAD requires the destination prefix to be empty/nonexistent.
UNLOAD (
    SELECT payment_id,
           event_id,
           event_date,
           event_time,
           received_at,
           amount,
           currency,
           channel,
           country_code,
           device_first_seen_days,
           transaction_count_1h,
           amount_sum_1h,
           distinct_merchant_count_1h,
           new_device_count_1h,
           feature_computed_at,
           label,
           label_fraud,
           label_observed_at,
           label_delay_days,
           dataset_version,
           dataset_split
    FROM training_examples_gold
)
TO 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/ml/training_exports/export_id=REPLACE_WITH_UNIQUE_ID/'
WITH (
    format = 'PARQUET',
    compression = 'SNAPPY',
    partitioned_by = ARRAY['dataset_split']
);

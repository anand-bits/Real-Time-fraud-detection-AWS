-- Replace the example export_id with a fresh value each run.
-- UNLOAD requires the destination prefix to be empty/nonexistent.
UNLOAD (
    SELECT payment_id,
           event_time,
           amount,
           device_first_seen_days,
           transaction_count_1h,
           amount_sum_1h,
           distinct_merchant_count_1h,
           new_device_count_1h,
           currency,
           channel,
           country_code,
           label_fraud,
           dataset_split
    FROM training_examples_gold
)
TO 's3://sentinelpay-raw-dev-908768512617-ap-southeast-2/ml/training_exports/export_id=REPLACE_WITH_UNIQUE_ID/'
WITH (
    format = 'PARQUET',
    compression = 'SNAPPY',
    partitioned_by = ARRAY['dataset_split']
);

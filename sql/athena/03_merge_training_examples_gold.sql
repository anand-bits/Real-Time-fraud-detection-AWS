MERGE INTO sentinelpay.training_examples_gold AS t
USING (
    SELECT p.data_classification,
           'v1' AS dataset_version,
           p.payment_id,
           p.event_id,
           CAST(substr(p.event_time, 1, 10) AS date) AS event_date,
           p.event_time,
           p.received_at,
           p.amount,
           p.currency,
           p.channel,
           p.country_code,
           p.device_first_seen_days,
           f.transaction_count AS transaction_count_1h,
           f.amount_sum AS amount_sum_1h,
           f.distinct_merchant_count AS distinct_merchant_count_1h,
           f.new_device_count AS new_device_count_1h,
           f.computed_at AS feature_computed_at,
           o.outcome AS label,
           CASE WHEN o.outcome = 'CONFIRMED_FRAUD' THEN 1 ELSE 0 END AS label_fraud,
           o.label_observed_at,
           date_diff(
               'day',
               from_iso8601_timestamp(p.event_time),
               from_iso8601_timestamp(o.label_observed_at)
           ) AS label_delay_days,
           CASE
               WHEN CAST(substr(p.event_time, 1, 10) AS date) < DATE '2026-06-01' THEN 'TRAIN'
               WHEN CAST(substr(p.event_time, 1, 10) AS date) < DATE '2026-09-01' THEN 'VALIDATION'
               ELSE 'TEST'
           END AS dataset_split
    FROM sentinelpay.payments_iceberg p
    JOIN sentinelpay.chargeback_outcomes_iceberg o
      ON o.payment_id = p.payment_id
     AND from_iso8601_timestamp(o.label_observed_at)
         >= date_add('day', 30, from_iso8601_timestamp(p.event_time))
    JOIN sentinelpay.fraud_decisions_iceberg d
      ON d.event_id = p.event_id
    JOIN sentinelpay.feature_updates_iceberg f
      ON f.feature_event_id = concat('feat_', substr(p.event_id, 5))
     AND f.entity_token = p.account_token
     AND from_iso8601_timestamp(f.window_end) <= from_iso8601_timestamp(p.event_time)
     AND from_iso8601_timestamp(f.computed_at) <= from_iso8601_timestamp(d.decision_time)
    WHERE p.data_classification = 'SYNTHETIC'
) AS s
ON t.event_id = s.event_id
WHEN MATCHED THEN UPDATE SET
    data_classification = s.data_classification,
    dataset_version = s.dataset_version,
    payment_id = s.payment_id,
    event_date = s.event_date,
    event_time = s.event_time,
    received_at = s.received_at,
    amount = s.amount,
    currency = s.currency,
    channel = s.channel,
    country_code = s.country_code,
    device_first_seen_days = s.device_first_seen_days,
    transaction_count_1h = s.transaction_count_1h,
    amount_sum_1h = s.amount_sum_1h,
    distinct_merchant_count_1h = s.distinct_merchant_count_1h,
    new_device_count_1h = s.new_device_count_1h,
    feature_computed_at = s.feature_computed_at,
    label = s.label,
    label_fraud = s.label_fraud,
    label_observed_at = s.label_observed_at,
    label_delay_days = s.label_delay_days,
    dataset_split = s.dataset_split
WHEN NOT MATCHED THEN INSERT (
    data_classification, dataset_version, payment_id, event_id, event_date,
    event_time, received_at, amount, currency, channel, country_code,
    device_first_seen_days, transaction_count_1h, amount_sum_1h,
    distinct_merchant_count_1h, new_device_count_1h, feature_computed_at,
    label, label_fraud, label_observed_at, label_delay_days, dataset_split
) VALUES (
    s.data_classification, s.dataset_version, s.payment_id, s.event_id, s.event_date,
    s.event_time, s.received_at, s.amount, s.currency, s.channel, s.country_code,
    s.device_first_seen_days, s.transaction_count_1h, s.amount_sum_1h,
    s.distinct_merchant_count_1h, s.new_device_count_1h, s.feature_computed_at,
    s.label, s.label_fraud, s.label_observed_at, s.label_delay_days, s.dataset_split
);

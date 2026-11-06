MERGE INTO sentinelpay.fraud_daily_metrics_gold AS t
USING (
    SELECT event_date,
           dataset_split,
           currency,
           count(*) AS payment_count,
           sum(label_fraud) AS confirmed_fraud_count,
           count(*) - sum(label_fraud) AS no_fraud_count,
           CAST(sum(label_fraud) AS double) / count(*) AS fraud_rate,
           sum(amount) AS total_amount,
           avg(amount) AS average_amount
    FROM sentinelpay.training_examples_gold
    GROUP BY event_date, dataset_split, currency
) AS s
ON t.event_date = s.event_date
AND t.dataset_split = s.dataset_split
AND t.currency = s.currency
WHEN MATCHED THEN UPDATE SET
    payment_count = s.payment_count,
    confirmed_fraud_count = s.confirmed_fraud_count,
    no_fraud_count = s.no_fraud_count,
    fraud_rate = s.fraud_rate,
    total_amount = s.total_amount,
    average_amount = s.average_amount
WHEN NOT MATCHED THEN INSERT (
    event_date, dataset_split, currency, payment_count, confirmed_fraud_count,
    no_fraud_count, fraud_rate, total_amount, average_amount
) VALUES (
    s.event_date, s.dataset_split, s.currency, s.payment_count,
    s.confirmed_fraud_count, s.no_fraud_count, s.fraud_rate,
    s.total_amount, s.average_amount
);

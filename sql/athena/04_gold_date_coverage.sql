SELECT count(*) AS rows,
       count(DISTINCT payment_id) AS unique_payments,
       sum(CASE WHEN label_fraud = 1 THEN 1 ELSE 0 END) AS confirmed_fraud,
       min(event_time) AS first_event_time,
       max(event_time) AS last_event_time
FROM training_examples_gold;

SELECT dataset_split,
       count(*) AS rows,
       count(DISTINCT payment_id) AS unique_payments,
       sum(CASE WHEN label_fraud = 1 THEN 1 ELSE 0 END) AS confirmed_fraud
FROM training_examples_gold
GROUP BY dataset_split
ORDER BY dataset_split;

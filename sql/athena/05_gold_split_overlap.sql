-- Expected result: no rows. A payment must not appear in multiple splits.
SELECT payment_id, count(DISTINCT dataset_split) AS split_count
FROM training_examples_gold
GROUP BY payment_id
HAVING count(DISTINCT dataset_split) > 1;

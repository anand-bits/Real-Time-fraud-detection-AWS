-- Bronze source counts and delivery duplicates, grouped by raw batch_id.
-- The external tables are expected to expose the Hive partition column batch_id.
SELECT batch_id, 'payments' AS event_type,
       count(*) AS bronze_record_count,
       count(DISTINCT event_id) AS unique_business_ids,
       count(*) - count(DISTINCT event_id) AS duplicate_delivery_count
FROM payments_bronze
GROUP BY batch_id
UNION ALL
SELECT batch_id, 'feature_updates', count(*), count(DISTINCT feature_event_id),
       count(*) - count(DISTINCT feature_event_id)
FROM feature_updates_bronze
GROUP BY batch_id
UNION ALL
SELECT batch_id, 'fraud_decisions', count(*), count(DISTINCT decision_id),
       count(*) - count(DISTINCT decision_id)
FROM fraud_decisions_bronze
GROUP BY batch_id
UNION ALL
SELECT batch_id, 'chargeback_outcomes', count(*), count(DISTINCT outcome_event_id),
       count(*) - count(DISTINCT outcome_event_id)
FROM chargeback_outcomes_bronze
GROUP BY batch_id
ORDER BY batch_id, event_type;

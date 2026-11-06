-- Silver Iceberg table row counts and event-key uniqueness.
SELECT 'payments' AS event_type, count(*) AS rows,
       count(DISTINCT event_id) AS unique_ids,
       count(*) - count(DISTINCT event_id) AS duplicate_ids
FROM payments_iceberg
UNION ALL
SELECT 'feature_updates', count(*), count(DISTINCT feature_event_id),
       count(*) - count(DISTINCT feature_event_id)
FROM feature_updates_iceberg
UNION ALL
SELECT 'fraud_decisions', count(*), count(DISTINCT decision_id),
       count(*) - count(DISTINCT decision_id)
FROM fraud_decisions_iceberg
UNION ALL
SELECT 'chargeback_outcomes', count(*), count(DISTINCT outcome_event_id),
       count(*) - count(DISTINCT outcome_event_id)
FROM chargeback_outcomes_iceberg
ORDER BY event_type;

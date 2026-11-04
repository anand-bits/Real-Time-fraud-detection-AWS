-- Expected result: no rows.
SELECT *
FROM pipeline_audit
WHERE reconciliation_status NOT IN ('PASS', 'PASS_WITH_DEDUP')
ORDER BY batch_id, event_type;

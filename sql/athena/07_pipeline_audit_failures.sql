-- Expected result: no rows.
SELECT *
FROM pipeline_audit
WHERE reconciliation_status NOT IN (
    'PASS',
    'PASS_WITH_DEDUP',
    'PASS_WITH_QUARANTINE',
    'PASS_WITH_QUARANTINE_AND_DEDUP',
    'NO_DATA'
)
ORDER BY batch_id, event_type;

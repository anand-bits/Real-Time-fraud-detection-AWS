SELECT ingest_date,
       batch_id,
       event_type,
       bronze_record_count,
       unique_business_ids,
       duplicate_delivery_count,
       reconciliation_status
FROM sentinelpay.pipeline_audit
WHERE batch_id = 'streaming'
  AND event_type = 'payments'
ORDER BY ingest_date;

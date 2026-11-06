SELECT batch_id, event_type, bronze_record_count, unique_business_ids,
       duplicate_delivery_count, reconciliation_status
FROM pipeline_audit
ORDER BY batch_id, event_type;

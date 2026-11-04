SELECT count(*) AS records,
       count(DISTINCT event_id) AS unique_events
FROM sentinelpay.payments_bronze
WHERE ingest_date = '2026-11-04'
  AND batch_id = 'streaming';

SELECT count(DISTINCT s.event_id) AS stream_events,
       count(DISTINCT p.event_id) AS matched_in_silver
FROM sentinelpay.payments_bronze s
LEFT JOIN sentinelpay.payments_iceberg p
  ON p.event_id = s.event_id
WHERE s.ingest_date = '2026-11-04'
  AND s.batch_id = 'streaming';

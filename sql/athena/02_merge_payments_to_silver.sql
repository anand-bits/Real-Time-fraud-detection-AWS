MERGE INTO sentinelpay.payments_iceberg AS t
USING (
    SELECT data_classification, schema_version, event_id,
           CASE WHEN batch_id IN ('validation-1500-seed17-20260601', 'test-1500-seed29-20260901')
                THEN concat('pay_', batch_id, '_', substr(payment_id, 5))
                ELSE payment_id END AS payment_id,
           CASE WHEN batch_id IN ('validation-1500-seed17-20260601', 'test-1500-seed29-20260901')
                THEN concat('idem_', batch_id, '_', substr(idempotency_key, 6))
                ELSE idempotency_key END AS idempotency_key,
           event_time, received_at,
           CASE WHEN batch_id IN ('validation-1500-seed17-20260601', 'test-1500-seed29-20260901')
                THEN concat('ptok_', batch_id, '_', substr(payment_token, 6))
                ELSE payment_token END AS payment_token,
           CASE WHEN batch_id IN ('validation-1500-seed17-20260601', 'test-1500-seed29-20260901')
                THEN concat('atok_', batch_id, '_', substr(account_token, 6))
                ELSE account_token END AS account_token,
           CASE WHEN batch_id IN ('validation-1500-seed17-20260601', 'test-1500-seed29-20260901')
                THEN concat('mer_', batch_id, '_', substr(merchant_id, 5))
                ELSE merchant_id END AS merchant_id,
           CASE WHEN batch_id IN ('validation-1500-seed17-20260601', 'test-1500-seed29-20260901')
                THEN concat('dtok_', batch_id, '_', substr(device_token, 6))
                ELSE device_token END AS device_token,
           amount, currency, channel, country_code, device_first_seen_days,
           source_region, trace_id, ingest_date, batch_id
    FROM (
        SELECT b.*,
               row_number() OVER (
                   PARTITION BY event_id
                   ORDER BY received_at, ingest_date, batch_id
               ) AS delivery_rank
        FROM sentinelpay.payments_bronze b
        WHERE data_classification = 'SYNTHETIC'
          AND schema_version = 1
          AND event_id IS NOT NULL
          AND payment_id IS NOT NULL
    ) ranked
    WHERE delivery_rank = 1
) AS s
ON t.event_id = s.event_id
WHEN MATCHED THEN UPDATE SET
    data_classification = s.data_classification,
    schema_version = s.schema_version,
    payment_id = s.payment_id,
    idempotency_key = s.idempotency_key,
    event_time = s.event_time,
    received_at = s.received_at,
    payment_token = s.payment_token,
    account_token = s.account_token,
    merchant_id = s.merchant_id,
    device_token = s.device_token,
    amount = s.amount,
    currency = s.currency,
    channel = s.channel,
    country_code = s.country_code,
    device_first_seen_days = s.device_first_seen_days,
    source_region = s.source_region,
    trace_id = s.trace_id,
    ingest_date = s.ingest_date,
    batch_id = s.batch_id
WHEN NOT MATCHED THEN INSERT (
    data_classification, schema_version, event_id, payment_id, idempotency_key,
    event_time, received_at, payment_token, account_token, merchant_id, device_token,
    amount, currency, channel, country_code, device_first_seen_days, source_region,
    trace_id, ingest_date, batch_id
) VALUES (
    s.data_classification, s.schema_version, s.event_id, s.payment_id, s.idempotency_key,
    s.event_time, s.received_at, s.payment_token, s.account_token, s.merchant_id, s.device_token,
    s.amount, s.currency, s.channel, s.country_code, s.device_first_seen_days, s.source_region,
    s.trace_id, s.ingest_date, s.batch_id
);

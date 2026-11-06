SELECT count(DISTINCT p.payment_id) AS payments_with_mature_labels,
       count(DISTINCT CASE
           WHEN f.feature_event_id IS NOT NULL THEN p.payment_id
       END) AS payments_with_point_in_time_features
FROM sentinelpay.payments_iceberg p
JOIN sentinelpay.chargeback_outcomes_iceberg o
  ON o.payment_id = p.payment_id
 AND from_iso8601_timestamp(o.label_observed_at)
     >= date_add('day', 30, from_iso8601_timestamp(p.event_time))
JOIN sentinelpay.fraud_decisions_iceberg d
  ON d.event_id = p.event_id
LEFT JOIN sentinelpay.feature_updates_iceberg f
  ON f.feature_event_id = concat('feat_', substr(p.event_id, 5))
 AND f.entity_token = p.account_token
 AND from_iso8601_timestamp(f.window_end) <= from_iso8601_timestamp(p.event_time)
 AND from_iso8601_timestamp(f.computed_at) <= from_iso8601_timestamp(d.decision_time);

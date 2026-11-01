# ADR-004: Event retention

**Status:** Accepted personal-demo defaults  
**Date:** 2026-11-01

## Context
Retention should support the 30-day simulated delayed-label window, replay, and temporal evaluation while limiting personal AWS spend. These are project settings, not legal or company retention rules.

## Decision

| Data | Baseline retention | Reason / cleanup |
|---|---:|---|
| Kinesis stream | 24 hours | Default replay window; extend to 7 days only for a planned exercise, then restore |
| S3 raw synthetic events/outcomes | 120 days | Covers simulated label delay plus evaluation history; lifecycle expiry afterward |
| Iceberg bronze/silver/gold | 120 days | Reproducible analytics; expire snapshots/files through tested maintenance |
| DynamoDB online features | 30 days | Enough for demo velocity/profile features; TTL where suitable |
| Single-Region decision/idempotency records | 7 days | Covers demo retries; use and test TTL |
| Model/evaluation artifacts | Latest 3 versions, at most 120 days | Preserve reproducibility without retaining every run |
| CloudWatch logs | 14 days | Short-lived demo telemetry |

Keep S3 Object Lock disabled. If the optional MRSC experiment is run, MRSC does not support TTL; use a short-lived table and an audited expiry job, then delete the disposable stack.

## Replay and cleanup rules
- S3 is the durable replay source; Kinesis is the short-window hot buffer.
- Preserve event IDs, event time, schema version, and sequence metadata with test reports.
- Keep source data until delayed labels and evaluation are complete.
- Expiration must be repeatable and observable. Verify test buckets, logs, endpoints, streams, and optional replicas are removed.
- Use synthetic data only; this schedule is not a compliance retention policy.

## Cost note
Kinesis retention beyond 24 hours adds cost and can be increased up to 365 days. S3 lifecycle transitions may not save money for small portfolio datasets; measure before adding them.

## References
- [Kinesis Data Streams retention](https://docs.aws.amazon.com/streams/latest/dev/kinesis-extended-retention.html)
- [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [DynamoDB Global Tables behavior](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html)

# ADR-002: MREC versus MRSC

**Status:** Accepted for personal portfolio baseline; MRSC comparison is an optional lab  
**Date:** 2026-11-01

## Context
Online risk features and the decision/idempotency ledger have different consistency needs. This project should demonstrate the tradeoffs without keeping a costly multi-Region stack running.

## Decision
### Baseline: one Region
Use single-Region DynamoDB tables for features and the decision ledger. Use conditional writes keyed by stable payment/idempotency ID. Demonstrate duplicate delivery and deterministic replay.

### Optional multi-Region experiment
- Use DynamoDB Global Tables **MREC** for derived online features. Keep one home writer Region per payment-instrument partition, fence before failover, measure ReplicationLatency, and prove features can be rebuilt from event history.
- Create a separate **MRSC** decision-ledger table only for a bounded experiment comparing consistency, latency, recovery, and cost. MRSC requires exactly three compatible Regions, adds cross-Region latency, and does not support TTL or transaction APIs. Use single-item idempotency operations.
- The default personal demo must not depend on MRSC. The architecture diagram shows it as an advanced target option.

## Rationale and consequences
The one-Region ledger keeps the normal build affordable while retaining the core correctness challenge. MREC/MRSC become measurable experiments rather than infrastructure that runs continuously. MREC feature replicas can be stale after a remote write; measure freshness and use safe fallback behavior. The optional MRSC experiment must document three-Region cost, latency, limitations, and cleanup.

If MRSC misses the authorization budget, record the result and keep the baseline ledger. Do not force MRSC into the serving path.

## References
- [How DynamoDB Global Tables work](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html)
- [DynamoDB consistency and design guidance](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.html)

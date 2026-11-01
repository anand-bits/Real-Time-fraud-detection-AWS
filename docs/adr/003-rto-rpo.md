# ADR-003: RTO and RPO objectives

**Status:** Accepted portfolio test objectives; multi-Region targets are optional  
**Date:** 2026-11-01

## Context
Recovery objectives are test goals for synthetic data, not AWS guarantees or a real payment-service commitment. The baseline is one Region; regional evacuation is a later lab.

## Baseline objectives

| Failure/data | Portfolio target | Validation |
|---|---|---|
| Decision API or consumer restart | RTO ≤30 minutes; no lost records after successful Kinesis/DynamoDB acknowledgement within the Region | Restart/redeploy and compare request IDs, stream sequence, and ledger |
| Feature state stale or lost | Rules-only fallback immediately; restore derived features within 30 minutes | Rebuild from retained events and compare feature checksums |
| Recreate baseline stack in the selected Region | RTO ≤60 minutes from Terraform/config and synthetic fixtures | Recreate a disposable environment, replay, and reconcile |
| Full Region loss | Not covered by baseline; no Region-level RPO/RTO claim | State this limitation in the demo report |

## Optional multi-Region lab targets

| Data/service | Stretch target | Notes |
|---|---|---|
| MRSC decision ledger | RPO 0 for committed writes; service RTO ≤15 minutes after serving-Region evacuation | Measure quorum behavior, routing, and retries |
| MREC online features | Rebuildable; target service restoration within 15 minutes | MREC is asynchronous; do not claim zero RPO |
| Mirrored payment-event log | Target RPO ≤60 seconds of relay lag; service RTO ≤15 minutes | Check source sequence gaps and reconcile |

These are test targets, not service guarantees. If a relay or recovery test misses its target, record the observed result and revise the design.

## Recovery rules
- Keep idempotency keys stable across retries.
- Fence the previous feature writer before promoting a new home Region.
- Track accepted source events, mirrored events, and last processed sequence; expose replication gaps.
- Restore infrastructure, replay events, run reconciliation, then mark recovery complete.
- Do not keep a standby Region running for the personal demo. Use a temporary lab with a teardown checklist.

## References
- [DynamoDB Global Tables consistency and recovery](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html)
